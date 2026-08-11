from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.application.commands.attendance import AttendanceDecision, finalize_attendance
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment, LessonUnitLedger
from shuttlecube.domain.customers.models import Student
from shuttlecube.infrastructure.database.base import utc_now


def test_attendance_deducts_once(db: Session, admin) -> None:
    student = Student(name="小羽")
    fixed = FixedClass(
        name="班",
        class_type="training",
        start_date=date.today(),
        default_start_time=utc_now().time(),
        duration_minutes=60,
        session_count=1,
        capacity=10,
        default_coach_id="coach",
        required_court_count=1,
        student_unit_price=Decimal("100"),
        coach_fee_per_session=Decimal("100"),
    )
    db.add_all([student, fixed])
    db.flush()
    session = ClassSession(
        fixed_class_id=fixed.id,
        sequence_number=1,
        scheduled_start=utc_now(),
        scheduled_end=utc_now(),
        actual_coach_id="coach",
    )
    enrollment = Enrollment(
        student_id=student.id,
        fixed_class_id=fixed.id,
        enrolled_on=date.today(),
        purchased_units=1,
        unit_price=Decimal("100"),
        suggested_receivable=Decimal("100"),
        actual_receivable=Decimal("100"),
    )
    db.add_all([session, enrollment])
    db.flush()
    db.add(
        LessonUnitLedger(
            owner_type="enrollment",
            owner_id=enrollment.id,
            change_type="purchase",
            delta=1,
            balance_before=0,
            balance_after=1,
            source_type="enrollment",
            source_id=enrollment.id,
            operated_by=admin.id,
            operated_at=utc_now(),
            idempotency_key="purchase",
        )
    )
    db.commit()
    first = finalize_attendance(
        db,
        session,
        [AttendanceDecision(student.id, enrollment.id, "present", 1)],
        admin.id,
        "attendance",
    )
    second = finalize_attendance(
        db,
        session,
        [AttendanceDecision(student.id, enrollment.id, "present", 1)],
        admin.id,
        "attendance",
    )
    assert first[0].id == second[0].id and db.query(LessonUnitLedger).count() == 2
