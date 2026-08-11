from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.domain.customers.models import Student, WalkInCustomer
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.domain.scheduling.models import ScheduleEntry
from shuttlecube.domain.venue_bookings.models import VenueBooking


def booking_schedule_title(db: Session, booking: VenueBooking) -> str:
    customer_name = db.scalar(
        select(WalkInCustomer.display_name).where(WalkInCustomer.id == booking.customer_id)
    )
    return f"{customer_name} · 散客订场" if customer_name else "散客订场"


def private_lesson_schedule_title(db: Session, lesson: PrivateLesson) -> str:
    student_name = db.scalar(select(Student.name).where(Student.id == lesson.student_id))
    return f"{student_name or lesson.student_id} · 私教课程"


def schedule_display_titles(db: Session, entries: list[ScheduleEntry]) -> dict[str, str]:
    booking_ids = [entry.source_id for entry in entries if entry.source_type == "venue_booking"]
    lesson_ids = [entry.source_id for entry in entries if entry.source_type == "private_lesson"]
    source_titles: dict[tuple[str, str], str] = {}

    if booking_ids:
        rows = db.execute(
            select(VenueBooking.id, WalkInCustomer.display_name)
            .join(WalkInCustomer, WalkInCustomer.id == VenueBooking.customer_id)
            .where(VenueBooking.id.in_(booking_ids))
        )
        source_titles.update(
            {
                ("venue_booking", booking_id): f"{customer_name} · 散客订场"
                for booking_id, customer_name in rows
            }
        )
    if lesson_ids:
        rows = db.execute(
            select(PrivateLesson.id, PrivateLesson.student_id, Student.name)
            .outerjoin(Student, Student.id == PrivateLesson.student_id)
            .where(PrivateLesson.id.in_(lesson_ids))
        )
        source_titles.update(
            {
                ("private_lesson", lesson_id): f"{student_name or student_id} · 私教课程"
                for lesson_id, student_id, student_name in rows
            }
        )

    return {
        entry.id: source_titles.get((entry.source_type, entry.source_id), entry.title)
        for entry in entries
    }
