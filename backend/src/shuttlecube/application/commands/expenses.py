from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.queries.receivables import money
from shuttlecube.domain.finance.models import Expense


def create_expense(
    db: Session,
    *,
    category: str,
    spent_at: datetime,
    amount: Decimal,
    payee: str,
    payment_method: str,
    source_type: str | None,
    source_id: str | None,
    notes: str | None,
    actor_id: str,
    idempotency_key: str,
    request_id: str,
    organization_id: str | None = None,
    venue_id: str | None = None,
    commit: bool = True,
    allow_zero: bool = False,
    allow_payroll_source: bool = False,
) -> Expense:
    existing_statement = select(Expense).where(Expense.idempotency_key == idempotency_key)
    if organization_id is not None and venue_id is not None:
        existing_statement = existing_statement.where(
            Expense.organization_id == organization_id,
            Expense.venue_id == venue_id,
        )
    existing = db.scalar(existing_statement)
    if existing:
        return existing
    value = money(amount)
    if value < 0 or (value == 0 and not allow_zero):
        raise BusinessError(422, "invalid_expense_amount", "支出金额必须大于零")
    if category == "refund":
        raise BusinessError(422, "refund_expense_not_allowed", "退款必须通过退款业务登记")
    if category == "coach_payroll" or source_type == "payroll_settlement":
        if not allow_payroll_source:
            raise BusinessError(
                422,
                "payroll_expense_requires_settlement",
                "教练工资必须通过教练结算登记",
            )
    item = Expense(
        organization_id=organization_id,
        venue_id=venue_id,
        category=category,
        spent_at=spent_at,
        amount=value,
        payee=payee,
        payment_method=payment_method,
        source_type=source_type,
        source_id=source_id,
        operated_by=actor_id,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor_id=actor_id,
        action="expense.created",
        entity_type="expense",
        entity_id=item.id,
        request_id=request_id,
        after={"category": category, "amount": str(value), "payee": payee},
        organization_id=organization_id,
        venue_id=venue_id,
    )
    if commit:
        db.commit()
    return item


def void_expense(
    db: Session,
    item: Expense,
    *,
    reason: str,
    actor_id: str,
    request_id: str,
) -> Expense:
    if item.status != "effective":
        return item
    if item.category == "coach_payroll" or item.source_type == "payroll_settlement":
        raise BusinessError(
            409,
            "payroll_expense_requires_settlement_void",
            "教练工资必须在教练结算中作废",
        )
    item.status = "void"
    item.void_reason = reason
    record_audit(
        db,
        actor_id=actor_id,
        action="expense.voided",
        entity_type="expense",
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
