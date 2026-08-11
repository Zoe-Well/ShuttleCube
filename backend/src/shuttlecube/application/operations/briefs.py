from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.domain.operations.models import OperationCase


def build_daily_brief(
    db: Session,
    *,
    scope: RequestScope,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    cases = db.scalars(
        select(OperationCase)
        .where(
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
            OperationCase.state.not_in(("resolved", "dismissed")),
            OperationCase.required_capability.in_(scope.capabilities),
        )
        .order_by(
            OperationCase.priority_score.desc(),
            OperationCase.due_at,
            OperationCase.first_detected_at,
        )
    ).all()
    groups: dict[str, dict[str, object]] = {}
    for case in cases:
        group = groups.setdefault(
            case.queue_key,
            {
                "queue_key": case.queue_key,
                "required_capability": case.required_capability,
                "total": 0,
                "overdue": 0,
                "unassigned": 0,
                "cases": [],
            },
        )
        group["total"] = int(group["total"]) + 1
        now = generated_at or datetime.now(UTC)
        if case.due_at is not None:
            due_at = case.due_at if case.due_at.tzinfo else case.due_at.replace(tzinfo=UTC)
            if due_at < now:
                group["overdue"] = int(group["overdue"]) + 1
        if case.assigned_to is None:
            group["unassigned"] = int(group["unassigned"]) + 1
        group["cases"].append(
            {
                "id": case.id,
                "title": case.title,
                "severity": case.severity,
                "state": case.state,
                "due_at": case.due_at,
                "assigned_to": case.assigned_to,
                "next_action": "处理并复核" if case.assigned_to else "认领案件",
            }
        )
    return {
        "generated_at": generated_at or datetime.now(UTC),
        "total": len(cases),
        "groups": list(groups.values()),
    }
