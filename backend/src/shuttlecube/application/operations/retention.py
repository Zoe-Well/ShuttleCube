from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.domain.operations.models import (
    CaseActivity,
    OperationApproval,
    OperationCase,
    OperationEvent,
    OperationRun,
    OperationsReportSnapshot,
    OperationToolCall,
)

BUSINESS_RETENTION = timedelta(days=365 * 2)
MODEL_SUMMARY_RETENTION = timedelta(days=180)
TERMINAL_RUN_STATES = {"succeeded", "failed", "escalated", "cancelled"}


@dataclass(frozen=True)
class RetentionSelection:
    archivable_run_ids: tuple[str, ...]
    protected_case_ids: tuple[str, ...]
    protected_activity_ids: tuple[str, ...]
    protected_approval_ids: tuple[str, ...]
    protected_write_tool_call_ids: tuple[str, ...]


def _deadline(created_at: datetime, duration: timedelta) -> datetime:
    aware = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return aware + duration


def _retention_deadline(
    existing: datetime | None,
    created_at: datetime,
    duration: timedelta,
) -> datetime:
    target = _deadline(created_at, duration)
    if existing is None:
        return target
    aware_existing = existing if existing.tzinfo else existing.replace(tzinfo=UTC)
    return existing if aware_existing >= target else target


def apply_retention_deadlines(
    db: Session,
    *,
    scope: RequestScope,
) -> None:
    cases = db.scalars(
        select(OperationCase).where(
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
        )
    ).all()
    for item in cases:
        item.retention_until = _retention_deadline(
            item.retention_until, item.created_at, BUSINESS_RETENTION
        )
    activities = db.scalars(
        select(CaseActivity).where(
            CaseActivity.organization_id == scope.organization_id,
            CaseActivity.venue_id == scope.venue_id,
        )
    ).all()
    for item in activities:
        item.retention_until = _retention_deadline(
            item.retention_until, item.created_at, BUSINESS_RETENTION
        )
    approvals = db.scalars(
        select(OperationApproval).where(
            OperationApproval.organization_id == scope.organization_id,
            OperationApproval.venue_id == scope.venue_id,
        )
    ).all()
    for item in approvals:
        item.retention_until = _retention_deadline(
            item.retention_until, item.created_at, BUSINESS_RETENTION
        )
    tool_calls = db.scalars(
        select(OperationToolCall).where(
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
        )
    ).all()
    for item in tool_calls:
        duration = BUSINESS_RETENTION if item.risk_level != "read" else MODEL_SUMMARY_RETENTION
        item.retention_until = _retention_deadline(
            item.retention_until, item.created_at, duration
        )
    runs = db.scalars(
        select(OperationRun).where(
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
        )
    ).all()
    write_run_ids = {item.run_id for item in tool_calls if item.risk_level != "read"}
    for item in runs:
        duration = BUSINESS_RETENTION if item.id in write_run_ids else MODEL_SUMMARY_RETENTION
        item.retention_until = _retention_deadline(
            item.retention_until, item.created_at, duration
        )
    db.flush()


def select_retention_candidates(
    db: Session,
    *,
    scope: RequestScope,
    now: datetime | None = None,
) -> RetentionSelection:
    current = now or datetime.now(UTC)
    apply_retention_deadlines(db, scope=scope)
    runs = db.scalars(
        select(OperationRun).where(
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
            OperationRun.state.in_(TERMINAL_RUN_STATES),
            OperationRun.retention_until.is_not(None),
            OperationRun.retention_until <= current,
        )
    ).all()
    cases = db.scalars(
        select(OperationCase).where(
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
            OperationCase.retention_until > current,
        )
    ).all()
    activities = db.scalars(
        select(CaseActivity).where(
            CaseActivity.organization_id == scope.organization_id,
            CaseActivity.venue_id == scope.venue_id,
            CaseActivity.retention_until > current,
        )
    ).all()
    approvals = db.scalars(
        select(OperationApproval).where(
            OperationApproval.organization_id == scope.organization_id,
            OperationApproval.venue_id == scope.venue_id,
            OperationApproval.retention_until > current,
        )
    ).all()
    write_calls = db.scalars(
        select(OperationToolCall).where(
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
            OperationToolCall.risk_level != "read",
            OperationToolCall.retention_until > current,
        )
    ).all()
    return RetentionSelection(
        archivable_run_ids=tuple(item.id for item in runs),
        protected_case_ids=tuple(item.id for item in cases),
        protected_activity_ids=tuple(item.id for item in activities),
        protected_approval_ids=tuple(item.id for item in approvals),
        protected_write_tool_call_ids=tuple(item.id for item in write_calls),
    )


def safely_archive_run_checkpoint(
    db: Session,
    *,
    scope: RequestScope,
    run_id: str,
    now: datetime | None = None,
) -> OperationRun:
    current = now or datetime.now(UTC)
    run = db.scalar(
        select(OperationRun).where(
            OperationRun.id == run_id,
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
        )
    )
    if run is None:
        raise ValueError("run_not_found")
    if run.state not in TERMINAL_RUN_STATES:
        raise ValueError("active_run_cannot_be_archived")
    retention_until = (
        run.retention_until
        if run.retention_until is None or run.retention_until.tzinfo
        else run.retention_until.replace(tzinfo=UTC)
    )
    if retention_until is None or retention_until > current:
        raise ValueError("run_retention_not_expired")
    checkpoint = run.checkpoint or {}
    if checkpoint.get("workflow_step") == "archived":
        return run
    events = db.scalars(
        select(OperationEvent.id).where(
            OperationEvent.organization_id == scope.organization_id,
            OperationEvent.venue_id == scope.venue_id,
            OperationEvent.run_id == run.id,
        )
    ).all()
    tool_references = db.scalars(
        select(OperationToolCall.result_reference).where(
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
            OperationToolCall.run_id == run.id,
            OperationToolCall.result_reference.is_not(None),
        )
    ).all()
    snapshot_ids = db.scalars(
        select(OperationsReportSnapshot.id).where(
            OperationsReportSnapshot.organization_id == scope.organization_id,
            OperationsReportSnapshot.venue_id == scope.venue_id,
            OperationsReportSnapshot.run_id == run.id,
        )
    ).all()
    run.checkpoint = {
        "workflow_step": "archived",
        "completed_steps": ["safe_archive"],
        "state": {
            "archived_at": current.isoformat(),
            "original_checkpoint_hash": canonical_hash(checkpoint),
            "event_ids": list(events),
            "business_result_references": [item for item in tool_references if item],
            "report_snapshot_ids": list(snapshot_ids),
            "business_facts_deleted": False,
            "audit_logs_deleted": False,
            "case_activities_deleted": False,
        },
    }
    db.flush()
    return run
