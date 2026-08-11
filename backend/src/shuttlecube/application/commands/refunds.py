from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.queries.receivables import (
    money,
    receivable_summary,
    sync_receivable_status,
)
from shuttlecube.domain.classes.enrollment_models import Enrollment, LessonUnitLedger
from shuttlecube.domain.finance.models import Receivable, Refund
from shuttlecube.domain.private_lessons.models import PrivateLessonPackage
from shuttlecube.infrastructure.database.base import utc_now


def record_refund(
    db: Session,
    item: Receivable,
    *,
    payment_id: str | None,
    refunded_at: datetime,
    suggested_amount: Decimal | None,
    actual_amount: Decimal,
    reason: str,
    lesson_units_to_remove: int,
    actor_id: str,
    idempotency_key: str,
    request_id: str,
) -> Refund:
    existing = db.scalar(
        select(Refund).where(
            Refund.organization_id == item.organization_id,
            Refund.venue_id == item.venue_id,
            Refund.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    value = money(actual_amount)
    if value <= 0:
        raise BusinessError(422, "invalid_refund_amount", "退款金额必须大于零")
    before = receivable_summary(db, item)
    if value > before.refundable_amount:
        raise BusinessError(422, "refund_exceeds_available", "退款金额超过当前可退金额")
    if value > money(item.actual_amount):
        raise BusinessError(422, "refund_exceeds_receivable", "退款金额超过剩余应收责任")
    if lesson_units_to_remove < 0:
        raise BusinessError(422, "invalid_lesson_units", "退款扣减课时不得为负数")
    refund = Refund(
        organization_id=item.organization_id,
        venue_id=item.venue_id,
        receivable_id=item.id,
        payment_id=payment_id,
        refunded_at=refunded_at,
        suggested_amount=money(suggested_amount) if suggested_amount is not None else None,
        actual_amount=value,
        reason=reason,
        operated_by=actor_id,
        idempotency_key=idempotency_key,
    )
    db.add(refund)
    db.flush()
    item.actual_amount = money(item.actual_amount - value)
    item.adjustment_reason = reason
    _adjust_lesson_rights(
        db,
        item,
        units=lesson_units_to_remove,
        reason=reason,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        refund_id=refund.id,
    )
    after = sync_receivable_status(db, item)
    record_audit(
        db,
        actor_id=actor_id,
        action="refund.recorded",
        entity_type="receivable",
        entity_id=item.id,
        request_id=request_id,
        before=before.audit_dict(),
        after=after.audit_dict(),
        reason=reason,
        organization_id=item.organization_id,
        venue_id=item.venue_id,
    )
    db.commit()
    return refund


def void_refund(
    db: Session,
    refund: Refund,
    *,
    reason: str,
    actor_id: str,
    request_id: str,
) -> Refund:
    if refund.status != "effective":
        return refund
    item = db.get(Receivable, refund.receivable_id)
    if item is None:
        raise BusinessError(404, "receivable_not_found", "应收记录不存在")
    before = receivable_summary(db, item)
    refund.status = "void"
    refund.void_reason = reason
    item.actual_amount = money(item.actual_amount + refund.actual_amount)
    item.adjustment_reason = reason
    _reverse_refund_lesson_rights(
        db,
        item,
        refund_id=refund.id,
        reason=reason,
        actor_id=actor_id,
    )
    after = sync_receivable_status(db, item)
    record_audit(
        db,
        actor_id=actor_id,
        action="refund.voided",
        entity_type="refund",
        entity_id=refund.id,
        request_id=request_id,
        before=before.audit_dict(),
        after=after.audit_dict(),
        reason=reason,
        organization_id=refund.organization_id,
        venue_id=refund.venue_id,
    )
    db.commit()
    return refund


def _reverse_refund_lesson_rights(
    db: Session,
    item: Receivable,
    *,
    refund_id: str,
    reason: str,
    actor_id: str,
) -> None:
    ledgers = list(
        db.scalars(
            select(LessonUnitLedger)
            .where(
                LessonUnitLedger.source_type == "refund",
                LessonUnitLedger.source_id == refund_id,
                LessonUnitLedger.change_type == "refund",
                LessonUnitLedger.status == "effective",
            )
            .order_by(LessonUnitLedger.operated_at, LessonUnitLedger.id)
        ).all()
    )
    if not ledgers:
        return
    current = balance(db, item.source_id)
    for original in ledgers:
        restored = current - original.delta
        original.status = "reversed"
        db.add(
            LessonUnitLedger(
                owner_type=original.owner_type,
                owner_id=original.owner_id,
                change_type="refund_void",
                delta=-original.delta,
                balance_before=current,
                balance_after=restored,
                source_type="refund_void",
                source_id=refund_id,
                reason=reason,
                reversal_of_id=original.id,
                operated_by=actor_id,
                operated_at=utc_now(),
                idempotency_key=f"refund-void:{refund_id}:{original.id}",
            )
        )
        current = restored

    if item.source_type == "enrollment":
        enrollment = db.get(Enrollment, item.source_id)
        if enrollment and enrollment.status == "withdrawn":
            enrollment.status = "active"
    elif item.source_type == "private_package":
        package = db.get(PrivateLessonPackage, item.source_id)
        if package and package.status == "refunded":
            package.status = "active"


def _adjust_lesson_rights(
    db: Session,
    item: Receivable,
    *,
    units: int,
    reason: str,
    actor_id: str,
    idempotency_key: str,
    refund_id: str,
) -> None:
    if units == 0 or item.source_type not in {"enrollment", "private_package"}:
        return
    current = balance(db, item.source_id)
    if units > current:
        raise BusinessError(422, "refund_units_exceed_balance", "退款扣减课时超过当前余额")
    db.add(
        LessonUnitLedger(
            owner_type=item.source_type,
            owner_id=item.source_id,
            change_type="refund",
            delta=-units,
            balance_before=current,
            balance_after=current - units,
            source_type="refund",
            source_id=refund_id,
            reason=reason,
            operated_by=actor_id,
            operated_at=utc_now(),
            idempotency_key=f"refund-units:{idempotency_key}",
        )
    )
    if current - units == 0:
        if item.source_type == "enrollment":
            owner = db.get(Enrollment, item.source_id)
            if owner:
                owner.status = "withdrawn"
        else:
            package = db.get(PrivateLessonPackage, item.source_id)
            if package:
                package.status = "refunded"
