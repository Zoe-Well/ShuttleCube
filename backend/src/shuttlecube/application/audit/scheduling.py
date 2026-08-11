from sqlalchemy.orm import Session

from shuttlecube.application.audit.writer import record_audit
from shuttlecube.domain.scheduling.models import ScheduleEntry


def record_schedule_change(
    db: Session,
    *,
    actor_id: str,
    action: str,
    entry: ScheduleEntry,
    request_id: str,
    before: dict[str, object] | None = None,
    reason: str | None = None,
) -> None:
    record_audit(
        db,
        actor_id=actor_id,
        action=action,
        entity_type="schedule_entry",
        entity_id=entry.id,
        request_id=request_id,
        before=before,
        after={
            "status": entry.status,
            "starts_at": entry.starts_at.isoformat(),
            "ends_at": entry.ends_at.isoformat(),
        },
        reason=reason,
    )
