from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.queries.receivables import (
    money,
    receivable_summary,
    sync_receivable_status,
)
from shuttlecube.domain.finance.models import Payment, Receivable


def record_payment(
    db: Session,
    item: Receivable,
    *,
    paid_at: datetime,
    amount: Decimal,
    method: str,
    payer_name: str | None,
    received_by: str | None,
    notes: str | None,
    actor_id: str,
    idempotency_key: str,
    request_id: str,
) -> Payment:
    existing = db.scalar(
        select(Payment).where(
            Payment.organization_id == item.organization_id,
            Payment.venue_id == item.venue_id,
            Payment.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    value = money(amount)
    if value <= 0:
        raise BusinessError(422, "invalid_payment_amount", "收款金额必须大于零")
    before = receivable_summary(db, item)
    if value > before.outstanding_amount:
        raise BusinessError(422, "payment_exceeds_outstanding", "收款金额超过当前待收款金额")
    payment = Payment(
        organization_id=item.organization_id,
        venue_id=item.venue_id,
        receivable_id=item.id,
        paid_at=paid_at,
        amount=value,
        method=method,
        payer_name=payer_name,
        received_by=received_by,
        operated_by=actor_id,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    db.flush()
    after = sync_receivable_status(db, item)
    record_audit(
        db,
        actor_id=actor_id,
        action="payment.recorded",
        entity_type="receivable",
        entity_id=item.id,
        request_id=request_id,
        before=before.audit_dict(),
        after=after.audit_dict(),
        organization_id=item.organization_id,
        venue_id=item.venue_id,
    )
    db.commit()
    return payment


def void_payment(
    db: Session,
    payment: Payment,
    *,
    reason: str,
    actor_id: str,
    request_id: str,
) -> Payment:
    if payment.status != "effective":
        return payment
    item = db.get(Receivable, payment.receivable_id)
    if item is None:
        raise BusinessError(404, "receivable_not_found", "应收记录不存在")
    before = receivable_summary(db, item)
    if before.refunded_amount > before.received_amount - money(payment.amount):
        raise BusinessError(409, "payment_has_refunds", "该收款已被退款引用，不能直接作废")
    payment.status = "void"
    payment.void_reason = reason
    after = sync_receivable_status(db, item)
    record_audit(
        db,
        actor_id=actor_id,
        action="payment.voided",
        entity_type="payment",
        entity_id=payment.id,
        request_id=request_id,
        before=before.audit_dict(),
        after=after.audit_dict(),
        reason=reason,
        organization_id=payment.organization_id,
        venue_id=payment.venue_id,
    )
    db.commit()
    return payment
