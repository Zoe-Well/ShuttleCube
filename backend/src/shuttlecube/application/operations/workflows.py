from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.access import capabilities_for_role
from shuttlecube.application.operations.briefs import build_daily_brief
from shuttlecube.application.operations.cases import upsert_detected_case
from shuttlecube.application.operations.detectors import DetectorRegistry
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.application.operations.policies import get_active_policy
from shuttlecube.application.operations.repositories import OperationsRepository
from shuttlecube.application.operations.runtime import (
    RunBudget,
    checkpoint_run,
    register_workflow,
)
from shuttlecube.application.operations.tracing import TraceRecorder
from shuttlecube.application.operations.verifiers import VerifierRegistry
from shuttlecube.domain.operations.models import OperationCase, OperationRun
from shuttlecube.domain.operations.schemas import OperationsPolicyConfig

SCAN_WORKFLOW_KEY = "operations.scan.v1"
BRIEF_WORKFLOW_KEY = "operations.brief.v1"


def _scope_for_run(run: OperationRun) -> RequestScope:
    return RequestScope(
        organization_id=run.organization_id,
        venue_id=run.venue_id,
        user_id="system",
        membership_id="system",
        capabilities=frozenset(),
    )


def execute_scan_workflow(db: Session, run: OperationRun, budget: RunBudget) -> None:
    scope = _scope_for_run(run)
    policy = get_active_policy(db, scope=scope, policy_key=run.policy_key)
    if policy.policy_version != run.policy_version:
        raise RuntimeError("policy_stale")
    config = OperationsPolicyConfig.model_validate(policy.config)
    registry = DetectorRegistry.default()
    requested = run.checkpoint.get("detector_keys") if run.checkpoint else None
    detector_keys = set(requested) if isinstance(requested, list) else None
    definitions = [
        definition
        for definition in registry.enabled()
        if detector_keys is None or definition.detector_key in detector_keys
    ]
    if not definitions:
        raise RuntimeError("no_enabled_detector")

    repository = OperationsRepository(db, scope)
    trace = TraceRecorder(repository, trace_id=str(uuid4()))
    detected_ids: list[str] = []
    found_subjects: dict[str, set[str]] = {}
    now = datetime.now(UTC)
    trace.record(
        run,
        event_type="scan_started",
        actor_type="system",
        payload={"detector_keys": [item.detector_key for item in definitions]},
    )
    for definition in definitions:
        budget.consume_step()
        assert definition.implementation is not None
        evidence_items = definition.implementation(db, scope, policy, now)
        subjects = found_subjects.setdefault(definition.detector_key, set())
        for evidence in evidence_items[:500]:
            subjects.add(evidence.subject_id)
            case, created = upsert_detected_case(
                db,
                scope=scope,
                definition=definition,
                evidence=evidence,
                case_sla_days=config.runtime.case_sla_days,
                detected_at=now,
            )
            case.current_run_id = run.id
            detected_ids.append(case.id)
            trace.record(
                run,
                event_type="case_created" if created else "case_refreshed",
                actor_type="system",
                payload={
                    "case_id": case.id,
                    "detector_key": definition.detector_key,
                    "evidence_hash": evidence.evidence_hash,
                },
            )

    verifier = VerifierRegistry.default()
    active_cases = db.scalars(
        select(OperationCase).where(
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
            OperationCase.detector_key.in_([item.detector_key for item in definitions]),
            OperationCase.state.not_in(("resolved", "dismissed")),
        )
    ).all()
    verified: list[dict[str, str]] = []
    for case in active_cases:
        if case.subject_id in found_subjects.get(case.detector_key, set()):
            continue
        result = verifier.verify(db, scope, case)
        verified.append({"case_id": case.id, "outcome": result.outcome})
        trace.record(
            run,
            event_type="case_verified",
            actor_type="system",
            payload={
                "case_id": case.id,
                "outcome": result.outcome,
                "reason_code": result.reason_code,
            },
        )
    checkpoint_run(
        run,
        {
            "workflow_step": "scan_complete",
            "completed_steps": ["detect", "upsert", "verify"],
            "state": {
                "detected_case_ids": detected_ids,
                "verification_results": verified,
                "completed_at": now.isoformat(),
            },
        },
    )
    trace.record(
        run,
        event_type="scan_completed",
        actor_type="system",
        payload={"detected_count": len(detected_ids), "verified_count": len(verified)},
    )
    if any(
        isinstance(ref, dict) and str(ref.get("id", "")).startswith("daily-catchup:")
        for ref in run.input_refs
    ):
        _enqueue_first_success_brief(db, run)


def _enqueue_first_success_brief(db: Session, scan_run: OperationRun) -> OperationRun:
    input_hash = canonical_hash(
        {
            "workflow_key": BRIEF_WORKFLOW_KEY,
            "venue_id": scan_run.venue_id,
            "scan_run_id": scan_run.id,
        }
    )
    existing = db.scalar(
        select(OperationRun).where(
            OperationRun.organization_id == scan_run.organization_id,
            OperationRun.venue_id == scan_run.venue_id,
            OperationRun.run_type == "brief",
            OperationRun.input_hash == input_hash,
        )
    )
    if existing is not None:
        return existing
    now = datetime.now(UTC)
    brief = OperationRun(
        organization_id=scan_run.organization_id,
        venue_id=scan_run.venue_id,
        case_id=None,
        parent_run_id=scan_run.id,
        run_type="brief",
        trigger_type=scan_run.trigger_type,
        workflow_key=BRIEF_WORKFLOW_KEY,
        workflow_version=1,
        policy_key=scan_run.policy_key,
        policy_version=scan_run.policy_version,
        prompt_version=None,
        toolset_version=1,
        model_profile=None,
        input_refs=[{"kind": "scan_run", "id": scan_run.id}],
        input_hash=input_hash,
        checkpoint={},
        state="queued",
        attempt=1,
        next_attempt_at=None,
        max_steps=5,
        max_model_calls=0,
        max_tool_calls=0,
        max_write_calls=0,
        deadline_at=now + timedelta(minutes=1),
        step_count=0,
        model_call_count=0,
        tool_call_count=0,
        write_call_count=0,
        token_usage_summary={},
    )
    db.add(brief)
    db.flush()
    return brief


def execute_brief_workflow(db: Session, run: OperationRun, budget: RunBudget) -> None:
    budget.consume_step()
    scope = RequestScope(
        organization_id=run.organization_id,
        venue_id=run.venue_id,
        user_id="system",
        membership_id="system",
        capabilities=capabilities_for_role("operations_manager"),
    )
    brief = build_daily_brief(db, scope=scope)
    checkpoint_run(
        run,
        {
            "workflow_step": "brief_complete",
            "completed_steps": ["group_cases"],
            "state": {"brief": brief},
        },
    )


register_workflow(SCAN_WORKFLOW_KEY, execute_scan_workflow)
register_workflow(BRIEF_WORKFLOW_KEY, execute_brief_workflow)
