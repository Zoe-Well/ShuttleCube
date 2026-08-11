from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from shuttlecube.application.audit.scheduling import record_schedule_change
from shuttlecube.application.commands.schedule import create_schedule
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.scheduling.conflicts import Resource


def test_schedule_creation_can_be_audited(db: Session, admin) -> None:
    start = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=6, minute=0, second=0, microsecond=0
    )
    entry = create_schedule(
        db,
        source_type="manual",
        source_id="source-1",
        title="审计排期",
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        resources=[Resource("court", "court-1")],
    )
    record_schedule_change(
        db, actor_id=admin.id, action="schedule.created", entry=entry, request_id="request-1"
    )
    db.commit()
    audit = db.query(AuditLog).one()
    assert audit.entity_id == entry.id
    assert audit.request_id == "request-1"
