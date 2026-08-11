from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.domain.operations.models import OperationRun
from shuttlecube.domain.operations.policy_models import OperationsPolicy


def enqueue_scan_run(
    db: Session,
    *,
    scope: RequestScope,
    policy: OperationsPolicy,
    detector_keys: list[str],
    trigger_type: str,
    trigger_key: str,
    now: datetime | None = None,
) -> OperationRun:
    queued_at = now or datetime.now(UTC)
    input_hash = canonical_hash(
        {
            "organization_id": scope.organization_id,
            "venue_id": scope.venue_id,
            "detector_keys": sorted(detector_keys),
            "trigger_key": trigger_key,
        }
    )
    existing = db.scalar(
        select(OperationRun).where(
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
            OperationRun.run_type == "scan",
            OperationRun.input_hash == input_hash,
        )
    )
    if existing is not None:
        return existing
    run = OperationRun(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        case_id=None,
        parent_run_id=None,
        run_type="scan",
        trigger_type=trigger_type,
        workflow_key="operations.scan.v1",
        workflow_version=1,
        policy_key=policy.policy_key,
        policy_version=policy.policy_version,
        prompt_version=None,
        toolset_version=1,
        model_profile=None,
        input_refs=[{"kind": trigger_type, "id": trigger_key}],
        input_hash=input_hash,
        checkpoint={"detector_keys": sorted(detector_keys)},
        state="queued",
        attempt=1,
        next_attempt_at=None,
        max_steps=max(20, len(detector_keys) * 5),
        max_model_calls=0,
        max_tool_calls=0,
        max_write_calls=0,
        deadline_at=queued_at + timedelta(minutes=5),
        step_count=0,
        model_call_count=0,
        tool_call_count=0,
        write_call_count=0,
        token_usage_summary={},
    )
    db.add(run)
    db.flush()
    return run
