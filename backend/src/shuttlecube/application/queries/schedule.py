from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry


def list_schedule(
    db: Session, starts_at: datetime, ends_at: datetime
) -> list[tuple[ScheduleEntry, list[ScheduleAllocation]]]:
    entries = db.scalars(
        select(ScheduleEntry)
        .where(
            ScheduleEntry.starts_at < ends_at,
            ScheduleEntry.ends_at > starts_at,
            ScheduleEntry.status.notin_(["cancelled", "rescheduled"]),
        )
        .order_by(ScheduleEntry.starts_at)
    ).all()
    result = []
    for entry in entries:
        if entry.source_type == "class_session":
            session = db.get(ClassSession, entry.source_id)
            fixed_class = db.get(FixedClass, session.fixed_class_id) if session else None
            if fixed_class and fixed_class.status == "archived":
                continue
        allocations = db.scalars(
            select(ScheduleAllocation).where(
                ScheduleAllocation.schedule_entry_id == entry.id,
                ScheduleAllocation.active.is_(True),
            )
        ).all()
        result.append((entry, list(allocations)))
    return result
