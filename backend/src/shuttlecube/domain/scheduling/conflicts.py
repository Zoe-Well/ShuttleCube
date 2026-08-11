from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.domain.scheduling.models import ScheduleAllocation


@dataclass(frozen=True)
class Resource:
    type: str
    id: str


@dataclass(frozen=True)
class Conflict:
    resource_type: str
    resource_id: str
    schedule_entry_id: str
    starts_at: datetime
    ends_at: datetime


def find_conflicts(
    db: Session,
    resources: list[Resource],
    starts_at: datetime,
    ends_at: datetime,
    exclude_entry_id: str | None = None,
) -> list[Conflict]:
    if ends_at <= starts_at:
        raise BusinessError(422, "invalid_time_range", "结束时间必须晚于开始时间")
    found: list[Conflict] = []
    for resource in resources:
        query = select(ScheduleAllocation).where(
            and_(
                ScheduleAllocation.active.is_(True),
                ScheduleAllocation.resource_type == resource.type,
                ScheduleAllocation.resource_id == resource.id,
                ScheduleAllocation.starts_at < ends_at,
                ScheduleAllocation.ends_at > starts_at,
            )
        )
        if exclude_entry_id:
            query = query.where(ScheduleAllocation.schedule_entry_id != exclude_entry_id)
        for row in db.scalars(query).all():
            found.append(
                Conflict(
                    row.resource_type,
                    row.resource_id,
                    row.schedule_entry_id,
                    row.starts_at,
                    row.ends_at,
                )
            )
    return found


def ensure_available(
    db: Session,
    resources: list[Resource],
    starts_at: datetime,
    ends_at: datetime,
    exclude_entry_id: str | None = None,
) -> None:
    conflicts = find_conflicts(db, resources, starts_at, ends_at, exclude_entry_id)
    if conflicts:
        raise BusinessError(
            409,
            "schedule_conflict",
            "所选资源在该时段已被占用",
            conflicts=[c.__dict__ for c in conflicts],
        )
