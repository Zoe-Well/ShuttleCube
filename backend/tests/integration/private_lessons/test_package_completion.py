from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.commands.private_lessons import complete_private_lesson, create_package
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.payroll.models import CoachFee
from shuttlecube.domain.private_lessons.models import PrivateLesson, PrivateLessonPackage


def test_package_lesson_completion_deducts_once_and_creates_one_coach_fee(
    db: Session, admin
) -> None:
    student = Student(name="私教学员")
    coach = CoachProfile(name="私教教练")
    db.add_all([student, coach])
    db.commit()
    package = create_package(
        db,
        student.id,
        coach.id,
        2,
        Decimal("300"),
        None,
        None,
        admin.id,
    )
    starts_at = datetime(2026, 8, 4, 10, tzinfo=UTC)
    lesson = PrivateLesson(
        student_id=student.id,
        coach_id=coach.id,
        package_id=package.id,
        billing_mode="package",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        coach_fee=Decimal("180"),
        status="booked",
    )
    db.add(lesson)
    db.commit()

    complete_private_lesson(db, lesson, admin.id, "complete-private-package")
    complete_private_lesson(db, lesson, admin.id, "complete-private-package")

    assert balance(db, package.id) == 1
    assert (
        db.query(CoachFee).filter_by(source_type="private_lesson", source_id=lesson.id).count() == 1
    )


def test_private_lesson_cannot_be_completed_before_it_ends(db: Session, admin) -> None:
    starts_at = datetime.now(UTC) + timedelta(hours=1)
    lesson = PrivateLesson(
        student_id="future-student",
        coach_id="future-coach",
        billing_mode="single",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        actual_receivable=Decimal("200"),
        coach_fee=Decimal("100"),
        status="booked",
    )
    db.add(lesson)
    db.commit()

    with pytest.raises(BusinessError) as caught:
        complete_private_lesson(db, lesson, admin.id, "complete-future-private-lesson")

    assert caught.value.code == "lesson_not_ended"


@pytest.mark.parametrize(
    ("student_exists", "student_active", "coach_exists", "coach_active", "expected_code"),
    [
        (False, True, True, True, "student_not_found"),
        (True, False, True, True, "student_inactive"),
        (True, True, False, True, "coach_not_found"),
        (True, True, True, False, "coach_inactive"),
    ],
)
def test_package_requires_existing_active_student_and_coach(
    db: Session,
    admin,
    student_exists: bool,
    student_active: bool,
    coach_exists: bool,
    coach_active: bool,
    expected_code: str,
) -> None:
    student = Student(name="课包校验学员", is_active=student_active)
    coach = CoachProfile(name="课包校验教练", is_active=coach_active)
    if student_exists:
        db.add(student)
    if coach_exists:
        db.add(coach)
    db.commit()

    with pytest.raises(BusinessError) as caught:
        create_package(
            db,
            student.id if student_exists else "missing-student",
            coach.id if coach_exists else "missing-coach",
            10,
            Decimal("300"),
            None,
            None,
            admin.id,
        )

    assert caught.value.code == expected_code
    assert db.query(PrivateLessonPackage).count() == 0
