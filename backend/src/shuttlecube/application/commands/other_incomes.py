from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.queries.receivables import money
from shuttlecube.domain.finance.models import OtherIncome


def create_other_income(
    db: Session,
    *,
    category: str,
    received_at: datetime,
    amount: Decimal,
    payer: str,
    payment_method: str,
    notes: str | None,
    actor_id: str,
    idempotency_key: str,
    request_id: str,
    organization_id: str | None = None,
    venue_id: str | None = None,
) -> OtherIncome:
    statement = select(OtherIncome).where(OtherIncome.idempotency_key == idempotency_key)
    if organization_id is not None and venue_id is not None:
        statement = statement.where(
            OtherIncome.organization_id == organization_id,
            OtherIncome.venue_id == venue_id,
        )
    existing = db.scalar(statement)
    if existing:
        return existing
    value = money(amount)
    if value <= 0:
        raise BusinessError(422, "invalid_other_income_amount", "其他收入金额必须大于零")
    item = OtherIncome(
        organization_id=organization_id,
        venue_id=venue_id,
        category=category.strip(),
        received_at=received_at,
        amount=value,
        payer=payer.strip(),
        payment_method=payment_method.strip(),
        notes=notes,
        operated_by=actor_id,
        idempotency_key=idempotency_key,
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor_id=actor_id,
        action="other_income.created",
        entity_type="other_income",
        entity_id=item.id,
        request_id=request_id,
        after={"category": item.category, "amount": str(value), "payer": item.payer},
        organization_id=organization_id,
        venue_id=venue_id,
    )
    db.commit()
    return item


def void_other_income(
    db: Session,
    item: OtherIncome,
    *,
    reason: str,
    actor_id: str,
    request_id: str,
) -> OtherIncome:
    if item.status != "effective":
        return item
    item.status = "void"
    item.void_reason = reason
    record_audit(
        db,
        actor_id=actor_id,
        action="other_income.voided",
        entity_type="other_income",
        entity_id=item.id,
        request_id=request_id,
        before={"status": "effective", "amount": str(item.amount)},
        after={"status": "void", "amount": str(item.amount)},
        reason=reason,
        organization_id=item.organization_id,
        venue_id=item.venue_id,
    )
    db.commit()
    return item
