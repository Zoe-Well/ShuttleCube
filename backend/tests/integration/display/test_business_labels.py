from datetime import date, time
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.queries.business_display import audit_change_items
from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.finance.models import Receivable


def _fixed_class() -> FixedClass:
    return FixedClass(
        name="周末提高班",
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


def test_student_finance_and_audit_apis_return_human_readable_business_labels(
    authenticated: tuple[TestClient, dict[str, str]], db: Session, admin
) -> None:
    client, _ = authenticated
    active_student = Student(name="胡东东")
    expired_student = Student(name="已失效学员")
    empty_student = Student(name="无权益学员")
    fixed_class = _fixed_class()
    db.add_all([active_student, expired_student, empty_student, fixed_class])
    db.flush()
    active_enrollment = Enrollment(
        student_id=active_student.id,
        fixed_class_id=fixed_class.id,
        enrolled_on=date(2026, 8, 1),
        purchased_units=10,
        unit_price=Decimal("100"),
        suggested_receivable=Decimal("1000"),
        actual_receivable=Decimal("1000"),
        status="active",
    )
    expired_enrollment = Enrollment(
        student_id=expired_student.id,
        fixed_class_id=fixed_class.id,
        enrolled_on=date(2026, 7, 1),
        purchased_units=10,
        unit_price=Decimal("100"),
        suggested_receivable=Decimal("1000"),
        actual_receivable=Decimal("1000"),
        status="cancelled",
    )
    db.add_all([active_enrollment, expired_enrollment])
    db.flush()
    receivable = Receivable(
        source_type="enrollment",
        source_id=active_enrollment.id,
        suggested_amount=Decimal("1000"),
        actual_amount=Decimal("1000"),
    )
    db.add(receivable)
    db.flush()
    record_audit(
        db,
        actor_id=admin.id,
        action="payment.recorded",
        entity_type="receivable",
        entity_id=receivable.id,
        request_id="readable-audit",
    )
    db.commit()

    finance = client.get("/api/v1/receivables").json()
    assert finance[0]["business_name"] == "固定班-周末提高班-胡东东"

    students = {
        item["name"]: item["entitlement_summary"]
        for item in client.get("/api/v1/students").json()["items"]
    }
    assert students["胡东东"] == {
        "active_labels": ["固定班：周末提高班"],
        "has_history": True,
        "has_invalid": False,
    }
    assert students["已失效学员"] == {
        "active_labels": [],
        "has_history": True,
        "has_invalid": True,
    }
    assert students["无权益学员"] == {
        "active_labels": [],
        "has_history": False,
        "has_invalid": False,
    }

    audit = client.get("/api/v1/audit?action_type=payment.recorded").json()[0]
    assert audit["action_label"] == "登记收款"
    assert audit["entity_label"] == "应收业务"
    assert audit["entity_name"] == "固定班-周末提高班-胡东东"


def test_audit_change_items_translate_business_fields_and_status_values() -> None:
    changes = audit_change_items(
        {
            "payment_status": "unpaid",
            "fixed_class_fee_effective_from": None,
            "invalid_coach_fees": 2,
        },
        {
            "payment_status": "paid",
            "fixed_class_fee_effective_from": "2026-08-05",
            "invalid_coach_fees": 0,
        },
    )

    assert changes == [
        {
            "field": "固定班教练费生效日期",
            "before": "无",
            "after": "2026-08-05",
        },
        {"field": "无效教练费用", "before": "2", "after": "0"},
        {"field": "收款状态", "before": "待收款", "after": "已结清"},
    ]
