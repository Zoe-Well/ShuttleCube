from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.classes import enroll_student
from shuttlecube.application.commands.payments import record_payment
from shuttlecube.application.commands.private_lessons import create_package
from shuttlecube.application.commands.student_entitlements import terminate_student_entitlement
from shuttlecube.application.queries.receivables import receivable_for_source
from shuttlecube.application.queries.student_entitlements import get_student_entitlements
from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.coach import CoachProfile


def test_student_can_hold_multiple_entitlements_and_soft_terminate_unpaid_one(
    db: Session, admin
) -> None:
    student = Student(name="多权益学员")
    fixed_class = FixedClass(
        name="周末班",
        class_type="training",
        start_date=date(2026, 8, 1),
        default_start_time=time(10),
        duration_minutes=60,
        session_count=10,
        capacity=12,
        default_coach_id="coach-1",
        required_court_count=1,
        student_unit_price=Decimal("100"),
        status="active",
    )
    coach = CoachProfile(name="多权益教练")
    db.add_all([student, fixed_class, coach])
    db.commit()
    enrollment = enroll_student(
        db,
        student_id=student.id,
        fixed_class=fixed_class,
        enrolled_on=date(2026, 8, 1),
        purchased_units=4,
        actual_receivable=None,
        reason=None,
        actor_id=admin.id,
    )
    package = create_package(
        db,
        student.id,
        coach.id,
        10,
        Decimal("300"),
        None,
        None,
        admin.id,
    )

    result = get_student_entitlements(db, student.id)
    assert result["fixed_classes"][0]["remaining_units"] == 4
    assert result["private_packages"][0]["remaining_units"] == 10

    terminate_student_entitlement(
        db,
        student_id=student.id,
        entitlement_type="private_package",
        entitlement_id=package.id,
        version=package.version,
        reason="录入错误",
        actor_id=admin.id,
        request_id="terminate-package",
    )
    result = get_student_entitlements(db, student.id)
    assert result["private_packages"][0]["remaining_units"] == 0
    assert result["private_packages"][0]["status"] == "void"
    assert enrollment.status == "active"


def test_paid_entitlement_requires_refund_before_termination(db: Session, admin) -> None:
    student = Student(name="已付款学员")
    coach = CoachProfile(name="已付款课包教练")
    db.add_all([student, coach])
    db.commit()
    package = create_package(
        db,
        student.id,
        coach.id,
        2,
        Decimal("100"),
        None,
        None,
        admin.id,
    )
    receivable = receivable_for_source(db, "private_package", package.id)
    assert receivable is not None
    record_payment(
        db,
        receivable,
        paid_at=datetime(2026, 8, 4, tzinfo=UTC),
        amount=Decimal("200"),
        method="wechat",
        payer_name=None,
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="paid-package",
        request_id="paid-package",
    )
    with pytest.raises(BusinessError) as caught:
        terminate_student_entitlement(
            db,
            student_id=student.id,
            entitlement_type="private_package",
            entitlement_id=package.id,
            version=package.version,
            reason="申请删除",
            actor_id=admin.id,
            request_id="terminate-paid-package",
        )
    assert caught.value.code == "entitlement_refund_required"
