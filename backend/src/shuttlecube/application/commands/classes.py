from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.receivables import create_receivable
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment, LessonUnitLedger
from shuttlecube.domain.classes.session_generation import generate_sessions
from shuttlecube.domain.customers.models import Student
from shuttlecube.infrastructure.database.base import utc_now


def create_fixed_class(
    db: Session, fixed_class: FixedClass, court_ids: list[str]
) -> tuple[FixedClass, list[ClassSession]]:
    db.add(fixed_class)
    db.flush()
    sessions = generate_sessions(db, fixed_class, court_ids)
    fixed_class.status = "active"
    db.commit()
    return fixed_class, sessions


def enroll_student(
    db: Session,
    *,
    student_id: str,
    fixed_class: FixedClass,
    enrolled_on: date,
    purchased_units: int | None,
    actual_receivable: Decimal | None,
    reason: str | None,
    actor_id: str,
) -> Enrollment:
    student = db.get(Student, student_id)
    if student is None:
        raise BusinessError(404, "student_not_found", "学员不存在")
    if not student.is_active:
        raise BusinessError(422, "student_inactive", "学员已停用，不能绑定固定班权益")
    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.fixed_class_id == fixed_class.id,
            Enrollment.status == "active",
        )
    )
    if existing:
        raise BusinessError(409, "student_already_enrolled", "学员已经拥有该固定班权益")
    enrolled = (
        db.scalar(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.fixed_class_id == fixed_class.id, Enrollment.status == "active")
        )
        or 0
    )
    if enrolled >= fixed_class.capacity:
        raise BusinessError(409, "class_full", "班级已满")
    remaining = (
        db.scalar(
            select(func.count())
            .select_from(ClassSession)
            .where(
                ClassSession.fixed_class_id == fixed_class.id,
                ClassSession.scheduled_start >= utc_now(),
                ClassSession.status == "scheduled",
            )
        )
        or 0
    )
    units = purchased_units if purchased_units is not None else remaining
    suggested = fixed_class.student_unit_price * units
    actual = actual_receivable if actual_receivable is not None else suggested
    if actual != suggested and not reason:
        raise BusinessError(422, "adjustment_reason_required", "调整应收金额必须填写原因")
    enrollment = Enrollment(
        student_id=student_id,
        fixed_class_id=fixed_class.id,
        enrolled_on=enrolled_on,
        purchased_units=units,
        unit_price=fixed_class.student_unit_price,
        suggested_receivable=suggested,
        actual_receivable=actual,
        is_midterm=units < fixed_class.session_count,
        price_adjustment_reason=reason,
    )
    db.add(enrollment)
    db.flush()
    db.add(
        LessonUnitLedger(
            owner_type="enrollment",
            owner_id=enrollment.id,
            change_type="purchase",
            delta=units,
            balance_before=0,
            balance_after=units,
            source_type="enrollment",
            source_id=enrollment.id,
            operated_by=actor_id,
            operated_at=utc_now(),
            idempotency_key=f"enroll:{enrollment.id}",
        )
    )
    create_receivable(
        db,
        source_type="enrollment",
        source_id=enrollment.id,
        suggested_amount=suggested,
        actual_amount=actual,
        adjustment_reason=reason,
    )
    db.commit()
    return enrollment
