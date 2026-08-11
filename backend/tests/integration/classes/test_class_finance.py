from datetime import UTC, date, datetime, time
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.application.commands.classes import enroll_student
from shuttlecube.application.commands.payments import record_payment
from shuttlecube.application.queries.receivables import receivable_for_source
from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.customers.models import Student


def test_class_detail_exposes_enrollment_cash_facts(
    authenticated: tuple[TestClient, dict[str, str]], db: Session, admin
) -> None:
    client, _ = authenticated
    student = Student(name="林小羽")
    fixed_class = FixedClass(
        name="周六青少年班",
        class_type="training",
        start_date=date(2026, 8, 1),
        default_start_time=time(18),
        duration_minutes=60,
        session_count=12,
        capacity=12,
        default_coach_id="coach-1",
        required_court_count=1,
        student_unit_price=Decimal("100.00"),
    )
    db.add_all([student, fixed_class])
    db.commit()
    enrollment = enroll_student(
        db,
        student_id=student.id,
        fixed_class=fixed_class,
        enrolled_on=date(2026, 8, 4),
        purchased_units=4,
        actual_receivable=Decimal("400.00"),
        reason=None,
        actor_id=admin.id,
    )
    receivable = receivable_for_source(db, "enrollment", enrollment.id)
    assert receivable is not None
    record_payment(
        db,
        receivable,
        paid_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        amount=Decimal("150.00"),
        method="wechat",
        payer_name="林女士",
        received_by=None,
        notes="历史收款补录",
        actor_id=admin.id,
        idempotency_key="class-detail-payment",
        request_id="class-detail-payment-request",
    )

    response = client.get(f"/api/v1/classes/{fixed_class.id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["finance"] == {
        "actual_amount": 400.0,
        "received_amount": 150.0,
        "refunded_amount": 0.0,
        "net_received": 150.0,
        "outstanding_amount": 250.0,
    }
    assert detail["enrollments"][0]["student_name"] == "林小羽"
    assert detail["enrollments"][0]["finance"]["receivable_id"] == receivable.id
    assert detail["enrollments"][0]["finance"]["payment_status"] == "partial"
