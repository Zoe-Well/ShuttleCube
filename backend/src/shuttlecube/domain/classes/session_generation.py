from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.schedule import create_schedule
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.scheduling.conflicts import Resource


def generate_sessions(
    db: Session, fixed_class: FixedClass, court_ids: list[str], timezone: str = "Asia/Shanghai"
) -> list[ClassSession]:
    if (
        fixed_class.session_count <= 0
        or fixed_class.capacity <= 0
        or fixed_class.duration_minutes <= 0
    ):
        raise BusinessError(422, "invalid_class_rules", "课次数、容量和时长必须为正数")
    if len(court_ids) < fixed_class.required_court_count:
        raise BusinessError(422, "insufficient_courts", "默认场地数量不足")
    zone = ZoneInfo(timezone)
    created: list[ClassSession] = []
    for index in range(fixed_class.session_count):
        local_start = datetime.combine(
            fixed_class.start_date + timedelta(weeks=index), fixed_class.default_start_time, zone
        )
        starts_at = local_start.astimezone(UTC)
        ends_at = starts_at + timedelta(minutes=fixed_class.duration_minutes)
        session = ClassSession(
            fixed_class_id=fixed_class.id,
            sequence_number=index + 1,
            scheduled_start=starts_at,
            scheduled_end=ends_at,
            actual_coach_id=fixed_class.default_coach_id,
        )
        db.add(session)
        db.flush()
        resources = [
            Resource("coach", fixed_class.default_coach_id),
            *[Resource("court", court) for court in court_ids[: fixed_class.required_court_count]],
        ]
        schedule = create_schedule(
            db,
            source_type="class_session",
            source_id=session.id,
            title=fixed_class.name,
            starts_at=starts_at,
            ends_at=ends_at,
            resources=resources,
            commit=False,
        )
        session.schedule_entry_id = schedule.id
        created.append(session)
    db.commit()
    return created
