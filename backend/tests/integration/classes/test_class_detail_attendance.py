from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import AttendanceRecord, Enrollment
from shuttlecube.domain.customers.models import Student


def test_class_detail_returns_readable_completed_attendance(
    db: Session, authenticated
) -> None:
    client, _ = authenticated
    student = Student(name="考勤学员")
    fixed_class = FixedClass(
        name="周末基础班",
        class_type="training",
        start_date=date(2026, 8, 1),
        default_start_time=time(10),
        duration_minutes=60,
        session_count=1,
        capacity=12,
        default_coach_id="coach-attendance",
        required_court_count=1,
        student_unit_price=Decimal("100.00"),
        status="active",
    )
    db.add_all([student, fixed_class])
    db.flush()
    enrollment = Enrollment(
        student_id=student.id,
        fixed_class_id=fixed_class.id,
        enrolled_on=date(2026, 8, 1),
        purchased_units=1,
        unit_price=Decimal("100.00"),
        suggested_receivable=Decimal("100.00"),
        actual_receivable=Decimal("100.00"),
    )
    session = ClassSession(
        fixed_class_id=fixed_class.id,
        sequence_number=1,
        scheduled_start=datetime(2026, 8, 4, 10, tzinfo=UTC),
        scheduled_end=datetime(2026, 8, 4, 11, tzinfo=UTC),
        actual_coach_id=fixed_class.default_coach_id,
        status="completed",
        attendance_finalized_at=datetime(2026, 8, 4, 11, 5, tzinfo=UTC),
    )
    db.add_all([enrollment, session])
    db.flush()
    db.add(
        AttendanceRecord(
            class_session_id=session.id,
            student_id=student.id,
            enrollment_id=enrollment.id,
            status="leave",
            deduct_units=0,
            grants_makeup=False,
            decision_note="已提前请假",
        )
    )
    db.commit()

    response = client.get(f"/api/v1/classes/{fixed_class.id}")

    assert response.status_code == 200
    attendance = response.json()["sessions"][0]["attendance"][0]
    assert attendance == {
        "id": attendance["id"],
        "student_id": student.id,
        "student_name": "考勤学员",
        "status": "leave",
        "deduct_units": 0,
        "grants_makeup": False,
        "decision_note": "已提前请假",
    }
    assert response.json()["sessions"][0]["attendance_finalized_at"].startswith(
        "2026-08-04T11:05:00"
    )
    assert response.json()["sessions"][0]["scheduled_start"] == "2026-08-04T10:00:00Z"
    assert response.json()["sessions"][0]["scheduled_end"] == "2026-08-04T11:00:00Z"
    assert response.json()["sessions"][0]["attendance_finalized_at"] == (
        "2026-08-04T11:05:00Z"
    )
