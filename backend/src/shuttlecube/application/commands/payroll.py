from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.expenses import create_expense
from shuttlecube.application.queries.operations_report import _bounds
from shuttlecube.application.queries.receivables import money
from shuttlecube.domain.finance.models import Expense
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement
from shuttlecube.infrastructure.database.base import new_id


def create_payroll_settlement(
    db: Session,
    *,
    coach_id: str,
    period_month: date,
    actual_amount: Decimal,
    adjustment_reason: str | None,
    paid_at: datetime,
    actor_id: str,
    idempotency_key: str,
    request_id: str,
    scope: RequestScope,
) -> PayrollSettlement:
    existing = db.scalar(
        select(PayrollSettlement).where(
            PayrollSettlement.organization_id == scope.organization_id,
            PayrollSettlement.venue_id == scope.venue_id,
            PayrollSettlement.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    period_start = period_month.replace(day=1)
    period_end = period_start.replace(day=monthrange(period_start.year, period_start.month)[1])
    starts_at, ends_at, _ = _bounds(db, scope, period_start, period_end)
    confirmed = db.scalar(
        select(PayrollSettlement).where(
            PayrollSettlement.coach_id == coach_id,
            PayrollSettlement.organization_id == scope.organization_id,
            PayrollSettlement.venue_id == scope.venue_id,
            PayrollSettlement.period_start == period_start,
            PayrollSettlement.status == "confirmed",
        )
    )
    if confirmed:
        raise BusinessError(409, "payroll_month_already_settled", "该教练本月已经完成结算")
    fees = list(
        db.scalars(
            select(CoachFee)
            .where(
                CoachFee.coach_id == coach_id,
                CoachFee.organization_id == scope.organization_id,
                CoachFee.venue_id == scope.venue_id,
                CoachFee.status == "pending",
                CoachFee.occurred_at >= starts_at,
                CoachFee.occurred_at < ends_at,
            )
            .order_by(CoachFee.occurred_at, CoachFee.id)
            .with_for_update()
        ).all()
    )
    if not fees:
        raise BusinessError(422, "coach_fees_required", "该教练本月没有待结算费用")
    calculated = money(sum((fee.base_amount + fee.adjustment_amount for fee in fees), Decimal(0)))
    actual = money(actual_amount)
    if actual < 0:
        raise BusinessError(422, "invalid_settlement_amount", "实际结算金额不得为负数")
    if actual != calculated and not adjustment_reason:
        raise BusinessError(422, "adjustment_reason_required", "调整结算金额必须填写原因")
    settlement_id = new_id()
    coach = db.get(CoachProfile, coach_id)
    expense = create_expense(
        db,
        category="coach_payroll",
        spent_at=paid_at,
        amount=actual,
        payee=f"教练 {coach.name if coach else coach_id}",
        payment_method="payroll",
        source_type="payroll_settlement",
        source_id=settlement_id,
        notes=adjustment_reason,
        actor_id=actor_id,
        idempotency_key=f"payroll-expense:{idempotency_key}",
        request_id=request_id,
        commit=False,
        allow_zero=True,
        allow_payroll_source=True,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    settlement = PayrollSettlement(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        id=settlement_id,
        coach_id=coach_id,
        period_start=period_start,
        period_end=period_end,
        calculated_amount=calculated,
        adjustment_amount=money(actual - calculated),
        actual_amount=actual,
        adjustment_reason=adjustment_reason,
        paid_at=paid_at,
        settled_by=actor_id,
        expense_id=expense.id,
        idempotency_key=idempotency_key,
    )
    db.add(settlement)
    db.flush()
    for fee in fees:
        fee.status = "settled"
        fee.settlement_id = settlement.id
    record_audit(
        db,
        actor_id=actor_id,
        action="payroll.settled",
        entity_type="payroll_settlement",
        entity_id=settlement.id,
        request_id=request_id,
        after={
            "coach_id": coach_id,
            "fee_ids": [fee.id for fee in fees],
            "calculated_amount": str(calculated),
            "actual_amount": str(actual),
            "expense_id": expense.id,
        },
        reason=adjustment_reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    return settlement


def void_payroll_settlement(
    db: Session,
    item: PayrollSettlement,
    *,
    reason: str,
    actor_id: str,
    request_id: str,
) -> PayrollSettlement:
    if item.status != "confirmed":
        return item
    fees = list(
        db.scalars(
            select(CoachFee).where(
                CoachFee.organization_id == item.organization_id,
                CoachFee.venue_id == item.venue_id,
                CoachFee.settlement_id == item.id,
            )
        ).all()
    )
    for fee in fees:
        fee.status = "pending"
        fee.settlement_id = None
    expense = db.get(Expense, item.expense_id)
    if expense:
        expense.status = "void"
        expense.void_reason = reason
    item.status = "void"
    record_audit(
        db,
        actor_id=actor_id,
        action="payroll.voided",
        entity_type="payroll_settlement",
        entity_id=item.id,
        request_id=request_id,
        before={"status": "confirmed", "fee_ids": [fee.id for fee in fees]},
        after={"status": "void", "expense_status": "void"},
        reason=reason,
        organization_id=item.organization_id,
        venue_id=item.venue_id,
    )
    db.commit()
    return item
