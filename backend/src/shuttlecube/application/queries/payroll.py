from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.queries.operations_report import _bounds
from shuttlecube.application.queries.receivables import money
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement


@dataclass(frozen=True)
class CoachFeeResult:
    coach_id: str | None
    calculated_amount: Decimal
    items: list[CoachFee]


def list_coach_fees(
    db: Session,
    *,
    scope: RequestScope,
    coach_id: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    status: str | None = None,
) -> CoachFeeResult:
    statement = (
        select(CoachFee)
        .where(
            CoachFee.organization_id == scope.organization_id,
            CoachFee.venue_id == scope.venue_id,
        )
        .order_by(CoachFee.occurred_at.desc())
    )
    if coach_id:
        statement = statement.where(CoachFee.coach_id == coach_id)
    if status:
        statement = statement.where(CoachFee.status == status)
    if period_start:
        starts_at, _, _ = _bounds(db, scope, period_start, period_start)
        statement = statement.where(CoachFee.occurred_at >= starts_at)
    if period_end:
        _, ends_at, _ = _bounds(db, scope, period_end, period_end)
        statement = statement.where(CoachFee.occurred_at < ends_at)
    items = list(db.scalars(statement).all())
    total = sum((money(item.base_amount + item.adjustment_amount) for item in items), Decimal(0))
    return CoachFeeResult(coach_id, money(total), items)


def list_settlements(
    db: Session,
    scope: RequestScope,
    coach_id: str | None = None,
    period_month: date | None = None,
) -> list[PayrollSettlement]:
    statement = (
        select(PayrollSettlement)
        .where(
            PayrollSettlement.organization_id == scope.organization_id,
            PayrollSettlement.venue_id == scope.venue_id,
        )
        .order_by(PayrollSettlement.paid_at.desc())
    )
    if coach_id:
        statement = statement.where(PayrollSettlement.coach_id == coach_id)
    if period_month:
        statement = statement.where(PayrollSettlement.period_start == period_month.replace(day=1))
    return list(db.scalars(statement).all())
