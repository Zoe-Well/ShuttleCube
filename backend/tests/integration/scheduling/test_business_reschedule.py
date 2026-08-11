from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.application.commands.events import create_event, delete_event, reschedule_event
from shuttlecube.application.commands.private_lessons import (
    book_private_lesson,
    delete_private_lesson,
    reschedule_private_lesson,
)
from shuttlecube.application.commands.venue_bookings import (
    create_booking,
    delete_booking,
    reschedule_booking,
)
from shuttlecube.domain.customers.models import Student, WalkInCustomer
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry


def assert_replaced(db: Session, old_id: str, new_id: str, court_id: str) -> None:
    old = db.get(ScheduleEntry, old_id)
    new = db.get(ScheduleEntry, new_id)
    assert old is None
    assert new is not None and new.original_entry_id is None
    courts = (
        db.query(ScheduleAllocation)
        .filter_by(schedule_entry_id=new.id, resource_type="court", active=True)
        .all()
    )
    assert [row.resource_id for row in courts] == [court_id]


def test_business_reschedules_keep_domain_and_schedule_in_sync(
    db: Session, zero_price_rules: None
) -> None:
    customer = WalkInCustomer(display_name="林先生")
    student = Student(name="胡东东")
    coach = CoachProfile(name="陈教练")
    db.add_all([customer, student, coach])
    db.flush()
    starts = datetime(2026, 8, 15, 2, 0, tzinfo=UTC)
    ends = datetime(2026, 8, 15, 3, 0, tzinfo=UTC)
    next_starts = datetime(2026, 8, 15, 3, 0, tzinfo=UTC)
    next_ends = datetime(2026, 8, 15, 4, 0, tzinfo=UTC)

    booking = create_booking(
        db, customer.id, starts, ends, ["court-1"], Decimal("0"), None, None, []
    )
    lesson = book_private_lesson(
        db,
        student_id=student.id,
        coach_id=coach.id,
        package_id=None,
        billing_mode="single",
        starts_at=starts,
        ends_at=ends,
        court_ids=["court-2"],
        actual_receivable=Decimal("0"),
        coach_fee=Decimal("200"),
        notes=None,
        warning_acknowledgements=[],
    )
    event = create_event(
        db,
        event_type="exclusive",
        name="测试包场",
        starts_at=starts,
        ends_at=ends,
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
    old_booking_id = booking.schedule_entry_id
    old_lesson_id = lesson.schedule_entry_id
    old_event_id = event.schedule_entry_id
    assert old_booking_id and old_lesson_id and old_event_id

    reschedule_booking(
        db,
        booking,
        starts_at=next_starts,
        ends_at=next_ends,
        court_ids=["court-4"],
        warning_acknowledgements=[],
    )
    reschedule_private_lesson(
        db,
        lesson,
        starts_at=next_starts,
        ends_at=next_ends,
        court_ids=["court-5"],
        warning_acknowledgements=[],
    )
    reschedule_event(
        db,
        event,
        starts_at=next_starts,
        ends_at=next_ends,
        court_ids=["court-6"],
        warning_acknowledgements=[],
    )

    assert booking.starts_at == next_starts and booking.ends_at == next_ends
    assert lesson.starts_at == next_starts and lesson.ends_at == next_ends
    assert event.starts_at == next_starts and event.ends_at == next_ends
    assert booking.schedule_entry_id and lesson.schedule_entry_id and event.schedule_entry_id
    assert_replaced(db, old_booking_id, booking.schedule_entry_id, "court-4")
    assert_replaced(db, old_lesson_id, lesson.schedule_entry_id, "court-5")
    assert_replaced(db, old_event_id, event.schedule_entry_id, "court-6")


def test_business_deletion_removes_records_schedules_and_allocations(
    db: Session, zero_price_rules: None
) -> None:
    customer = WalkInCustomer(display_name="待删除客户")
    student = Student(name="待删除学员")
    coach = CoachProfile(name="待删除教练")
    db.add_all([customer, student, coach])
    db.flush()
    starts = datetime(2026, 8, 16, 2, 0, tzinfo=UTC)
    ends = datetime(2026, 8, 16, 3, 0, tzinfo=UTC)
    booking = create_booking(
        db, customer.id, starts, ends, ["delete-court-1"], Decimal("0"), None, None, []
    )
    lesson = book_private_lesson(
        db,
        student_id=student.id,
        coach_id=coach.id,
        package_id=None,
        billing_mode="single",
        starts_at=starts,
        ends_at=ends,
        court_ids=["delete-court-2"],
        actual_receivable=Decimal("0"),
        coach_fee=Decimal("0"),
        notes=None,
        warning_acknowledgements=[],
    )
    event = create_event(
        db,
        event_type="exclusive",
        name="待删除活动",
        starts_at=starts,
        ends_at=ends,
        court_ids=["delete-court-3"],
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
    business_ids = [booking.id, lesson.id, event.id]
    schedule_ids = [booking.schedule_entry_id, lesson.schedule_entry_id, event.schedule_entry_id]
    assert all(schedule_ids)

    delete_booking(db, booking)
    delete_private_lesson(db, lesson)
    delete_event(db, event)

    assert db.get(type(booking), business_ids[0]) is None
    assert db.get(type(lesson), business_ids[1]) is None
    assert db.get(type(event), business_ids[2]) is None
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
