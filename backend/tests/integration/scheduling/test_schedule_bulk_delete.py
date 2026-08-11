from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.application.commands.events import create_event
from shuttlecube.application.commands.private_lessons import book_private_lesson
from shuttlecube.application.commands.schedule import create_schedule
from shuttlecube.application.commands.venue_bookings import create_booking
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.customers.models import Student, WalkInCustomer
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.domain.scheduling.conflicts import Resource
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry
from shuttlecube.domain.venue_bookings.models import VenueBooking


def test_bulk_delete_mixed_schedule_sources_is_atomic_and_removes_business_records(
    authenticated: tuple[TestClient, dict[str, str]], db: Session, zero_price_rules: None
) -> None:
    client, headers = authenticated
    customer = WalkInCustomer(display_name="批量删除客户")
    student = Student(name="批量删除学员")
    coach = CoachProfile(name="批量删除教练")
    db.add_all([customer, student, coach])
    db.flush()
    starts_at = datetime(2026, 8, 20, 2, 0, tzinfo=UTC)
    ends_at = datetime(2026, 8, 20, 3, 0, tzinfo=UTC)
    booking = create_booking(
        db, customer.id, starts_at, ends_at, ["court-1"], Decimal("0"), None, None, []
    )
    lesson = book_private_lesson(
        db,
        student_id=student.id,
        coach_id=coach.id,
        package_id=None,
        billing_mode="single",
        starts_at=starts_at,
        ends_at=ends_at,
        court_ids=["court-2"],
        actual_receivable=Decimal("0"),
        coach_fee=Decimal("0"),
        notes=None,
        warning_acknowledgements=[],
    )
    event = create_event(
        db,
        event_type="exclusive",
        name="批量删除活动",
        starts_at=starts_at,
        ends_at=ends_at,
        court_ids=["court-3"],
        coach_id=None,
        coach_fee=Decimal("0"),
        actual_receivable=Decimal("0"),
        expense_amount=Decimal("0"),
        track_participants=False,
        requires_attendance=False,
        participant_ids=[],
        notes=None,
        warning_acknowledgements=[],
    )
    manual = create_schedule(
        db,
        source_type="manual",
        source_id="manual-bulk-1",
        title="批量删除手工排期",
        starts_at=starts_at,
        ends_at=ends_at,
        resources=[Resource("court", "court-4")],
        acknowledged_warnings=[],
    )
    schedule_ids = [
        booking.schedule_entry_id,
        lesson.schedule_entry_id,
        event.schedule_entry_id,
        manual.id,
    ]
    assert all(schedule_ids)

    response = client.post(
        "/api/v1/schedule/bulk-delete",
        headers=headers,
        json={"ids": schedule_ids, "reason": "统一排期批量清理"},
    )

    assert response.status_code == 200
    assert response.json() == {"ids": schedule_ids, "status": "deleted"}
    assert db.get(VenueBooking, booking.id) is None
    assert db.get(PrivateLesson, lesson.id) is None
    assert db.get(TemporaryEvent, event.id) is None
    assert db.query(ScheduleEntry).filter(ScheduleEntry.id.in_(schedule_ids)).count() == 0
    assert (
        db.query(ScheduleAllocation)
        .filter(ScheduleAllocation.schedule_entry_id.in_(schedule_ids))
        .count()
        == 0
    )
    assert db.get(WalkInCustomer, customer.id) is not None
    assert db.get(Student, student.id) is not None
    assert db.get(CoachProfile, coach.id) is not None
    assert db.query(AuditLog).filter(AuditLog.action_type == "schedule.deleted").count() == 4


def test_bulk_delete_rejects_fixed_class_and_keeps_every_selection(
    authenticated: tuple[TestClient, dict[str, str]], db: Session
) -> None:
    client, headers = authenticated
    starts_at = datetime(2026, 8, 21, 2, 0, tzinfo=UTC)
    ends_at = datetime(2026, 8, 21, 3, 0, tzinfo=UTC)
    manual = create_schedule(
        db,
        source_type="manual",
        source_id="manual-kept",
        title="应保留手工排期",
        starts_at=starts_at,
        ends_at=ends_at,
        resources=[Resource("court", "court-1")],
        acknowledged_warnings=[],
    )
    fixed_session = create_schedule(
        db,
        source_type="class_session",
        source_id="class-session-kept",
        title="不可批量删除固定课",
        starts_at=starts_at,
        ends_at=ends_at,
        resources=[Resource("court", "court-2")],
        acknowledged_warnings=[],
    )

    response = client.post(
        "/api/v1/schedule/bulk-delete",
        headers=headers,
        json={"ids": [manual.id, fixed_session.id], "reason": "不应部分删除"},
    )

    assert response.status_code == 409
    assert response.json()["title"] == "schedule_not_bulk_deletable"
    assert db.get(ScheduleEntry, manual.id) is not None
    assert db.get(ScheduleEntry, fixed_session.id) is not None
