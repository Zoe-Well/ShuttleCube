from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.application.operations.model_client import (
    ModelOutputInvalid,
    ModelUnavailable,
    VenueModelClient,
)
from shuttlecube.application.operations.policies import get_active_policy
from shuttlecube.application.operations.report_anomalies import (
    ANOMALY_RULE_VERSION,
    evaluate_report_anomalies,
)
from shuttlecube.application.operations.report_narrative import (
    PROMPT_VERSION,
    generate_report_narrative,
)
from shuttlecube.application.operations.report_snapshots import create_report_snapshot
from shuttlecube.application.operations.reports import METRIC_VERSION, build_report_facts
from shuttlecube.application.operations.runtime import RunBudget, checkpoint_run, register_workflow
from shuttlecube.config import get_settings
from shuttlecube.domain.operations.models import OperationRun, OperationsReportSnapshot
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.ai.credentials import (
    configured_model_profile,
    resolve_model_provider,
)
from shuttlecube.infrastructure.ai.openai_client import model_provider_client

REPORT_WORKFLOW_KEY = "operations.report.v1"
REPORT_NARRATIVE_WORKFLOW_KEY = "operations.report_narrative.v1"


def natural_period(period_type: str, anchor_date: date) -> tuple[date, date]:
    if period_type == "day":
        return anchor_date, anchor_date
    if period_type == "week":
        start = anchor_date - timedelta(days=anchor_date.weekday())
        return start, start + timedelta(days=6)
    if period_type == "month":
        start = anchor_date.replace(day=1)
        return start, start.replace(day=monthrange(start.year, start.month)[1])
    raise ValueError("period_type must be day, week or month")


def previous_period(period_type: str, start: date, end: date) -> tuple[date, date]:
    if period_type == "month":
        previous_end = start - timedelta(days=1)
        return previous_end.replace(day=1), previous_end
    days = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=days - 1), previous_end


def _comparison_status(facts: dict[str, object]) -> str:
    metrics = facts.get("metrics")
    if not isinstance(metrics, list):
        return "data_insufficient"
    for item in metrics:
        if not isinstance(item, dict) or item.get("scope") != "period":
            continue
        if item.get("data_status") == "insufficient":
            continue
        try:
            if Decimal(str(item.get("value", "0"))) != 0:
                return "available"
        except InvalidOperation:
            continue
    return "data_insufficient"


def period_cutoff(
    venue: Venue,
    *,
    period_start: date,
    period_end: date,
    now: datetime,
) -> tuple[datetime, datetime, str]:
    zone = ZoneInfo(venue.timezone)
    starts_at = datetime.combine(period_start, time.min, zone).astimezone(UTC)
    ends_at = datetime.combine(period_end + timedelta(days=1), time.min, zone).astimezone(UTC)
    current = now if now.tzinfo else now.replace(tzinfo=UTC)
    if starts_at > current:
        raise ValueError("future periods cannot be generated")
    effective_end = min(current, ends_at)
    return starts_at, effective_end, "complete" if effective_end >= ends_at else "in_progress"


def _scope_for_run(run: OperationRun) -> RequestScope:
    return RequestScope(
        organization_id=run.organization_id,
        venue_id=run.venue_id,
        user_id="system",
        membership_id="system",
        capabilities=frozenset(
            {
                "operations.report.read",
                "operations.report.financial.read",
                "operations.payroll.read",
            }
        ),
    )


def enqueue_report_run(
    db: Session,
    *,
    scope: RequestScope,
    period_type: str,
    anchor_date: date,
    include_narrative: bool,
    trigger_key: str,
) -> OperationRun:
    policy = get_active_policy(db, scope=scope)
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if venue is None:
        raise LookupError("scope venue not found")
    period_start, period_end = natural_period(period_type, anchor_date)
    period_cutoff(
        venue,
        period_start=period_start,
        period_end=period_end,
        now=datetime.now(UTC),
    )
    normalized = {
        "period_type": period_type,
        "anchor_date": anchor_date.isoformat(),
        "include_narrative": include_narrative,
        "trigger_key": trigger_key,
    }
    input_hash = canonical_hash(normalized)
    existing = db.scalar(
        select(OperationRun).where(
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
            OperationRun.workflow_key == REPORT_WORKFLOW_KEY,
            OperationRun.input_hash == input_hash,
        )
    )
    if existing is not None:
        return existing
    now = datetime.now(UTC)
    run = OperationRun(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        case_id=None,
        parent_run_id=None,
        run_type="report",
        trigger_type="manual",
        workflow_key=REPORT_WORKFLOW_KEY,
        workflow_version=1,
        policy_key=policy.policy_key,
        policy_version=policy.policy_version,
        prompt_version=None,
        toolset_version=1,
        model_profile=None,
        input_refs=[{"kind": "venue", "id": venue.id, "version": venue.version}],
        input_hash=input_hash,
        checkpoint={
            "workflow_step": "queued",
            "state": {
                **normalized,
                "generated_by": scope.user_id,
            },
        },
        state="queued",
        max_steps=5,
        max_model_calls=0,
        max_tool_calls=0,
        max_write_calls=0,
        deadline_at=now + timedelta(minutes=2),
    )
    db.add(run)
    db.flush()
    return run


def enqueue_narrative_run(
    db: Session,
    *,
    snapshot: OperationsReportSnapshot,
    parent_run: OperationRun,
    trigger_key: str,
) -> OperationRun:
    input_hash = canonical_hash(
        {
            "snapshot_id": snapshot.id,
            "evidence_hash": snapshot.evidence_hash,
            "trigger_key": trigger_key,
        }
    )
    existing = db.scalar(
        select(OperationRun).where(
            OperationRun.organization_id == snapshot.organization_id,
            OperationRun.venue_id == snapshot.venue_id,
            OperationRun.workflow_key == REPORT_NARRATIVE_WORKFLOW_KEY,
            OperationRun.input_hash == input_hash,
        )
    )
    if existing is not None:
        return existing
    now = datetime.now(UTC)
    child = OperationRun(
        organization_id=snapshot.organization_id,
        venue_id=snapshot.venue_id,
        case_id=None,
        parent_run_id=parent_run.id,
        run_type="report_narrative",
        trigger_type="manual",
        workflow_key=REPORT_NARRATIVE_WORKFLOW_KEY,
        workflow_version=1,
        policy_key=parent_run.policy_key,
        policy_version=parent_run.policy_version,
        prompt_version=PROMPT_VERSION,
        toolset_version=1,
        model_profile=configured_model_profile(get_settings()),
        input_refs=[
            {
                "kind": "operations_report_snapshot",
                "id": snapshot.id,
                "evidence_hash": snapshot.evidence_hash,
            }
        ],
        input_hash=input_hash,
        checkpoint={"workflow_step": "queued", "state": {"snapshot_id": snapshot.id}},
        state="queued",
        max_steps=3,
        max_model_calls=1,
        max_tool_calls=0,
        max_write_calls=0,
        deadline_at=now + timedelta(minutes=2),
    )
    db.add(child)
    db.flush()
    snapshot.narrative_state = "queued"
    snapshot.narrative_run_id = child.id
    snapshot.model_profile = child.model_profile
    snapshot.prompt_version = PROMPT_VERSION
    return child


def execute_report_workflow(db: Session, run: OperationRun, budget: RunBudget) -> None:
    existing_snapshot = db.scalar(
        select(OperationsReportSnapshot).where(
            OperationsReportSnapshot.organization_id == run.organization_id,
            OperationsReportSnapshot.venue_id == run.venue_id,
            OperationsReportSnapshot.run_id == run.id,
        )
    )
    if existing_snapshot is not None:
        checkpoint_run(
            run,
            {
                "workflow_step": "report_complete",
                "completed_steps": ["period", "metrics", "anomalies", "snapshot"],
                "state": {
                    "snapshot_id": existing_snapshot.id,
                    "narrative_run_id": existing_snapshot.narrative_run_id,
                },
            },
        )
        return
    budget.consume_step()
    scope = _scope_for_run(run)
    policy = get_active_policy(db, scope=scope, policy_key=run.policy_key)
    if policy.policy_version != run.policy_version:
        raise RuntimeError("policy_stale")
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if venue is None:
        raise RuntimeError("venue_not_found")
    state = (run.checkpoint or {}).get("state", {})
    if not isinstance(state, dict):
        raise RuntimeError("invalid_report_checkpoint")
    period_type = str(state["period_type"])
    anchor_date = date.fromisoformat(str(state["anchor_date"]))
    include_narrative = bool(state.get("include_narrative", True))
    generated_by = str(state.get("generated_by", "system"))
    period_start, period_end = natural_period(period_type, anchor_date)
    now = datetime.now(UTC)
    current_start, effective_end, period_state = period_cutoff(
        venue,
        period_start=period_start,
        period_end=period_end,
        now=now,
    )
    comparison_start, comparison_end = previous_period(period_type, period_start, period_end)
    comparison_start_at, comparison_full_end, _ = period_cutoff(
        venue,
        period_start=comparison_start,
        period_end=comparison_end,
        now=now,
    )
    elapsed = effective_end - current_start
    comparison_effective_end = min(comparison_start_at + elapsed, comparison_full_end)
    facts = build_report_facts(
        db,
        scope=scope,
        period_start=period_start,
        period_end=period_end,
        effective_end=effective_end,
        calculated_at=now,
    )
    comparison_facts = build_report_facts(
        db,
        scope=scope,
        period_start=comparison_start,
        period_end=comparison_end,
        effective_end=comparison_effective_end,
        calculated_at=now,
    )
    anomalies = evaluate_report_anomalies(
        current=facts,
        comparison=comparison_facts,
        policy_config=policy.config,
    )
    budget.consume_step()
    snapshot = create_report_snapshot(
        db,
        scope=scope,
        run=run,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        effective_end=effective_end,
        business_timezone=venue.timezone,
        period_state=period_state,
        generated_at=now,
        generated_by=generated_by,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
        comparison_status=_comparison_status(comparison_facts),
        policy_version=policy.policy_version,
        metric_version=METRIC_VERSION,
        anomaly_rule_version=ANOMALY_RULE_VERSION,
        metrics=list(facts["metrics"]),
        breakdowns={
            **dict(facts["breakdowns"]),
            "comparison_metrics": comparison_facts["metrics"],
        },
        anomalies=anomalies,
        source_refs=list(facts["source_refs"]),
        caveats=list(facts["caveats"]),
        include_narrative=include_narrative,
    )
    child: OperationRun | None = None
    if include_narrative:
        child = enqueue_narrative_run(
            db,
            snapshot=snapshot,
            parent_run=run,
            trigger_key=f"initial:{snapshot.id}",
        )
    checkpoint_run(
        run,
        {
            "workflow_step": "report_complete",
            "completed_steps": ["period", "metrics", "anomalies", "snapshot"],
            "state": {
                "snapshot_id": snapshot.id,
                "narrative_run_id": child.id if child else None,
            },
        },
    )


def execute_report_narrative_workflow(
    db: Session,
    run: OperationRun,
    budget: RunBudget,
) -> None:
    snapshot_id = next(
        (
            str(ref.get("id"))
            for ref in run.input_refs
            if isinstance(ref, dict) and ref.get("kind") == "operations_report_snapshot"
        ),
        "",
    )
    snapshot = db.scalar(
        select(OperationsReportSnapshot).where(
            OperationsReportSnapshot.id == snapshot_id,
            OperationsReportSnapshot.organization_id == run.organization_id,
            OperationsReportSnapshot.venue_id == run.venue_id,
        )
    )
    venue = db.scalar(
        select(Venue).where(
            Venue.id == run.venue_id,
            Venue.organization_id == run.organization_id,
        )
    )
    if snapshot is None or venue is None:
        raise RuntimeError("snapshot_not_found")
    settings = get_settings()
    configuration = resolve_model_provider(settings)
    if venue.model_enabled is not True or configuration is None:
        snapshot.narrative_state = "unavailable"
        checkpoint_run(
            run,
            {
                "workflow_step": "narrative_unavailable",
                "completed_steps": ["model_gate"],
                "state": {"snapshot_id": snapshot.id, "reason": "model_disabled"},
            },
        )
        return
    scope = _scope_for_run(run)
    try:
        result, usage, provider = generate_report_narrative(
            snapshot,
            model_client=VenueModelClient(db, scope, model_provider_client(settings)),
            model_profile=configuration.model_profile,
        )
        budget.consume_model_call(tokens=usage)
        snapshot.summary = str(result["summary"])
        snapshot.anomaly_explanations = list(result["anomaly_explanations"])
        snapshot.recommendations = list(result["recommendations"])
        snapshot.narrative_state = "available"
        checkpoint_run(
            run,
            {
                "workflow_step": "narrative_complete",
                "completed_steps": ["snapshot", "model", "citation_validation", "render"],
                "state": {"snapshot_id": snapshot.id, "provider": provider},
            },
        )
    except (ModelUnavailable, ModelOutputInvalid, ValueError) as exc:
        snapshot.narrative_state = "failed"
        checkpoint_run(
            run,
            {
                "workflow_step": "narrative_failed",
                "completed_steps": ["snapshot", "model_attempt"],
                "state": {"snapshot_id": snapshot.id, "reason": type(exc).__name__},
            },
        )


register_workflow(REPORT_WORKFLOW_KEY, execute_report_workflow)
register_workflow(REPORT_NARRATIVE_WORKFLOW_KEY, execute_report_narrative_workflow)
