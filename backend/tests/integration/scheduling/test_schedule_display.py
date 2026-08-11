from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.api.v1.private_lessons import lessons
from shuttlecube.api.v1.venue_bookings import bookings
from shuttlecube.application.commands.private_lessons import book_private_lesson
from shuttlecube.application.commands.venue_bookings import create_booking
from shuttlecube.application.queries.schedule_display import schedule_display_titles
from shuttlecube.domain.customers.models import Student, WalkInCustomer
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.scheduling.models import ScheduleEntry


def test_booking_and_private_lesson_names_are_used_everywhere(
    db: Session, zero_price_rules: None
) -> None:
    customer = WalkInCustomer(display_name="林先生")
    student = Student(name="胡东东")
    coach = CoachProfile(name="陈教练")
    db.add_all([customer, student, coach])
    db.flush()
    starts_at = datetime(2026, 8, 1, 2, 0, tzinfo=UTC)
    ends_at = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)

    booking = create_booking(
        db,
        customer.id,
        starts_at,
        ends_at,
        ["court-booking"],
        Decimal("0"),
        None,
        None,
        ["past_time"],
    )
    lesson = book_private_lesson(
        db,
        student_id=student.id,
        coach_id=coach.id,
        package_id=None,
        billing_mode="single",
        starts_at=starts_at,
        ends_at=ends_at,
        court_ids=["court-private"],
        actual_receivable=Decimal("0"),
        coach_fee=Decimal("200"),
        notes=None,
        warning_acknowledgements=["past_time"],
    )

    booking_entry = db.get(ScheduleEntry, booking.schedule_entry_id)
    lesson_entry = db.get(ScheduleEntry, lesson.schedule_entry_id)
    assert booking_entry is not None
    assert lesson_entry is not None
    assert booking_entry.title == "林先生 · 散客订场"
    assert lesson_entry.title == "胡东东 · 私教课程"

    # The resolver also enriches historical entries whose stored title was generic.
    booking_entry.title = "散客订场"
    lesson_entry.title = "私教课程"
    titles = schedule_display_titles(db, [booking_entry, lesson_entry])
    assert titles[booking_entry.id] == "林先生 · 散客订场"
    assert titles[lesson_entry.id] == "胡东东 · 私教课程"

    booking_view = bookings(db, (object(), object()))[0]
    lesson_view = lessons(db, (object(), object()))[0]
    assert booking_view["customer_name"] == "林先生"
    assert lesson_view["student_name"] == "胡东东"
    assert lesson_view["coach_name"] == "陈教练"

    lesson.student_id = "临时录入学员"
    db.flush()
    fallback_titles = schedule_display_titles(db, [lesson_entry])
    assert fallback_titles[lesson_entry.id] == "临时录入学员 · 私教课程"
