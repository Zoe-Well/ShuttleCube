from datetime import UTC, datetime

from shuttlecube.domain.operations.models import OperationCase, OperationRun


class InvalidTransition(ValueError):
    pass


CASE_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset(
        {"analyzing", "monitoring", "waiting_human", "escalated", "resolved", "dismissed"}
    ),
    "analyzing": frozenset(
        {"action_proposed", "monitoring", "waiting_human", "escalated"}
    ),
    "action_proposed": frozenset(
        {"waiting_approval", "monitoring", "waiting_human", "escalated"}
    ),
    "waiting_approval": frozenset({"executing", "waiting_human", "escalated"}),
    "executing": frozenset({"verifying", "waiting_human", "escalated"}),
    "verifying": frozenset({"resolved", "monitoring", "waiting_human", "escalated"}),
    "monitoring": frozenset(
        {"analyzing", "waiting_human", "escalated", "resolved", "dismissed"}
    ),
    "waiting_human": frozenset(
        {"analyzing", "monitoring", "escalated", "resolved", "dismissed"}
    ),
    "escalated": frozenset({"analyzing", "monitoring", "waiting_human", "resolved"}),
    "resolved": frozenset({"open"}),
    "dismissed": frozenset({"open"}),
}

RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset(
        {
            "waiting_approval",
            "waiting_human",
            "retry_scheduled",
            "succeeded",
            "failed",
            "escalated",
            "cancelled",
        }
    ),
    "waiting_approval": frozenset({"queued", "cancelled", "escalated"}),
    "waiting_human": frozenset({"queued", "cancelled", "escalated"}),
    "retry_scheduled": frozenset({"queued", "cancelled", "escalated"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "escalated": frozenset(),
    "cancelled": frozenset(),
}


def transition_case(
    case: OperationCase,
    target: str,
    *,
    reason: str | None = None,
    now: datetime | None = None,
) -> OperationCase:
    current = case.state or "open"
    if target not in CASE_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(f"case:{current}->{target}")
    changed_at = now or datetime.now(UTC)
    if target == "dismissed" and not reason:
        raise InvalidTransition("dismissed requires a human reason")
    if current in {"resolved", "dismissed"} and target == "open":
        case.occurrence_no += 1
        case.resolved_at = None
        case.dismissed_reason = None
    case.state = target
    if target == "resolved":
        case.resolved_at = changed_at
    if target == "dismissed":
        case.dismissed_reason = reason
    return case


def transition_run(
    run: OperationRun,
    target: str,
    *,
    now: datetime | None = None,
) -> OperationRun:
    current = run.state or "queued"
    if target not in RUN_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(f"run:{current}->{target}")
    changed_at = now or datetime.now(UTC)
    run.state = target
    if target == "running" and run.started_at is None:
        run.started_at = changed_at
    if target in {"succeeded", "failed", "escalated", "cancelled"}:
        run.finished_at = changed_at
        run.lease_owner = None
        run.lease_expires_at = None
    if target in {"waiting_approval", "waiting_human", "retry_scheduled"}:
        run.lease_owner = None
        run.lease_expires_at = None
    return run
