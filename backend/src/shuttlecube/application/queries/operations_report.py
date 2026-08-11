from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.queries.receivables import money, receivable_summary
from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.finance.models import Expense, OtherIncome, Payment, Receivable, Refund
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation


@dataclass
class FixedClassFinance:
    class_id: str
    class_name: str
    payment_amount: Decimal = Decimal("0.00")
    refund_amount: Decimal = Decimal("0.00")
    outstanding_amount: Decimal = Decimal("0.00")


def _bounds(
    db: Session, scope: RequestScope, start: date, end: date
) -> tuple[datetime, datetime, ZoneInfo]:
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if venue is None:
        raise LookupError("scope venue not found")
    zone = ZoneInfo(venue.timezone)
    starts_at = datetime.combine(start, time.min, zone).astimezone(UTC)
    ends_at = datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(UTC)
    return starts_at, ends_at, zone


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def get_operations_report(
    db: Session,
    scope: RequestScope,
    period_start: date,
    period_end: date,
    effective_end: datetime | None = None,
) -> dict[str, object]:
    if period_end < period_start:
        raise ValueError("period_end must not be before period_start")
    starts_at, ends_at, zone = _bounds(db, scope, period_start, period_end)
    if effective_end is not None:
        ends_at = min(ends_at, _aware(effective_end))
    payments = list(
        db.scalars(
            select(Payment).where(
                Payment.status == "effective",
                Payment.organization_id == scope.organization_id,
                Payment.venue_id == scope.venue_id,
                Payment.paid_at >= starts_at,
                Payment.paid_at < ends_at,
            )
        ).all()
    )
    refunds = list(
        db.scalars(
            select(Refund).where(
                Refund.status == "effective",
                Refund.organization_id == scope.organization_id,
                Refund.venue_id == scope.venue_id,
                Refund.refunded_at >= starts_at,
                Refund.refunded_at < ends_at,
            )
        ).all()
    )
    expenses = list(
        db.scalars(
            select(Expense).where(
                Expense.status == "effective",
                Expense.organization_id == scope.organization_id,
                Expense.venue_id == scope.venue_id,
                Expense.category != "refund",
                Expense.spent_at >= starts_at,
                Expense.spent_at < ends_at,
            )
        ).all()
    )
    other_incomes = list(
        db.scalars(
            select(OtherIncome).where(
                OtherIncome.status == "effective",
                OtherIncome.organization_id == scope.organization_id,
                OtherIncome.venue_id == scope.venue_id,
                OtherIncome.received_at >= starts_at,
                OtherIncome.received_at < ends_at,
            )
        ).all()
    )
    income = money(
        sum((row.amount for row in payments), Decimal(0))
        + sum((row.amount for row in other_incomes), Decimal(0))
    )
    refund_total = money(sum((row.actual_amount for row in refunds), Decimal(0)))
    expense_total = money(sum((row.amount for row in expenses), Decimal(0)))
    all_receivables = list(
        db.scalars(
            select(Receivable).where(
                Receivable.organization_id == scope.organization_id,
                Receivable.venue_id == scope.venue_id,
            )
        ).all()
    )
    receivable_by_id = {receivable.id: receivable for receivable in all_receivables}
    outstanding = money(
        sum(
            (
                receivable_summary(db, row).outstanding_amount
                for row in all_receivables
                if row.status != "void"
            ),
            Decimal(0),
        )
    )
    fee_items = list(
        db.scalars(
            select(CoachFee).where(
                CoachFee.occurred_at >= starts_at,
                CoachFee.occurred_at < ends_at,
                CoachFee.organization_id == scope.organization_id,
                CoachFee.venue_id == scope.venue_id,
            )
        ).all()
    )
    coach_pending = money(
        sum(
            (
                row.base_amount + row.adjustment_amount
                for row in fee_items
                if row.status == "pending"
            ),
            Decimal(0),
        )
    )
    coach_earned = money(
        sum(
            (
                row.base_amount + row.adjustment_amount
                for row in fee_items
                if row.status != "void"
            ),
            Decimal(0),
        )
    )
    current_coach_pending = money(
        sum(
            (
                row.base_amount + row.adjustment_amount
                for row in db.scalars(
                    select(CoachFee).where(
                        CoachFee.status == "pending",
                        CoachFee.organization_id == scope.organization_id,
                        CoachFee.venue_id == scope.venue_id,
                    )
                ).all()
            ),
            Decimal(0),
        )
    )
    settlements = list(
        db.scalars(
            select(PayrollSettlement).where(
                PayrollSettlement.status == "confirmed",
                PayrollSettlement.organization_id == scope.organization_id,
                PayrollSettlement.venue_id == scope.venue_id,
                PayrollSettlement.paid_at >= starts_at,
                PayrollSettlement.paid_at < ends_at,
            )
        ).all()
    )
    coach_settled = money(sum((row.actual_amount for row in settlements), Decimal(0)))
    income_by_source: dict[str, Decimal] = {}
    income_by_class: dict[str, Decimal] = {}
    enrollments = list(
        db.scalars(
            select(Enrollment).where(
                Enrollment.organization_id == scope.organization_id,
                Enrollment.venue_id == scope.venue_id,
            )
        ).all()
    )
    enrollment_by_id = {enrollment.id: enrollment for enrollment in enrollments}
    class_ids = {enrollment.fixed_class_id for enrollment in enrollments}
    fixed_classes = (
        list(
            db.scalars(
                select(FixedClass).where(
                    FixedClass.organization_id == scope.organization_id,
                    FixedClass.venue_id == scope.venue_id,
                    FixedClass.id.in_(class_ids),
                )
            ).all()
        )
        if class_ids
        else []
    )
    class_finance: dict[str, FixedClassFinance] = {
        fixed_class.id: FixedClassFinance(fixed_class.id, fixed_class.name)
        for fixed_class in fixed_classes
    }
    receivable_class_id: dict[str, str] = {}
    for receivable in all_receivables:
        if receivable.source_type != "enrollment":
            continue
        enrollment = enrollment_by_id.get(receivable.source_id)
        if enrollment is None or enrollment.fixed_class_id not in class_finance:
            continue
        receivable_class_id[receivable.id] = enrollment.fixed_class_id
        if receivable.status != "void":
            class_finance[enrollment.fixed_class_id].outstanding_amount += receivable_summary(
                db, receivable
            ).outstanding_amount

    for payment in payments:
        payment_receivable = receivable_by_id.get(payment.receivable_id)
        if payment_receivable is None:
            continue
        income_by_source[payment_receivable.source_type] = money(
            income_by_source.get(payment_receivable.source_type, Decimal(0)) + payment.amount
        )
        class_id = receivable_class_id.get(payment_receivable.id)
        if class_id:
            income_by_class[class_id] = money(
                income_by_class.get(class_id, Decimal(0)) + payment.amount
            )
            class_finance[class_id].payment_amount += payment.amount
    if other_incomes:
        income_by_source["other_income"] = money(
            sum((row.amount for row in other_incomes), Decimal(0))
        )
    for refund in refunds:
        class_id = receivable_class_id.get(refund.receivable_id)
        if class_id:
            class_finance[class_id].refund_amount += refund.actual_amount

    fixed_class_finance = [
        {
            "class_id": row.class_id,
            "class_name": row.class_name,
            "payment_amount": money(row.payment_amount),
            "refund_amount": money(row.refund_amount),
            "net_received": money(row.payment_amount - row.refund_amount),
            "outstanding_amount": money(row.outstanding_amount),
        }
        for row in sorted(
            class_finance.values(),
            key=lambda item: (-money(item.payment_amount - item.refund_amount), item.class_name),
        )
    ]
    usage_hours, utilization = _court_usage(
        db, scope, period_start, period_end, starts_at, ends_at, zone
    )
    court_ids = set(usage_hours) | set(utilization)
    court_names = {
        court.id: court.name
        for court in db.scalars(
            select(Court).where(Court.venue_id == scope.venue_id, Court.id.in_(court_ids))
        ).all()
    }
    return {
        "from": period_start,
        "to": period_end,
        "income": income,
        "refunds": refund_total,
        "expense": expense_total,
        "profit": money(income - refund_total - expense_total),
        "outstanding": outstanding,
        "coach_pending": coach_pending,
        "coach_earned": coach_earned,
        "current_coach_pending": current_coach_pending,
        "coach_settled": coach_settled,
        "income_by_source": income_by_source,
        "income_by_class": income_by_class,
        "fixed_class_finance": fixed_class_finance,
        "court_usage_hours": usage_hours,
        "court_utilization": utilization,
        "court_names": court_names,
    }


def _court_usage(
    db: Session,
    scope: RequestScope,
    period_start: date,
    period_end: date,
    starts_at: datetime,
    ends_at: datetime,
    zone: ZoneInfo,
) -> tuple[dict[str, Decimal], dict[str, float]]:
    courts = list(
        db.scalars(
            select(Court).where(
                Court.venue_id == scope.venue_id,
                Court.is_active.is_(True),
            )
        ).all()
    )
    allocations = list(
        db.scalars(
            select(ScheduleAllocation).where(
                ScheduleAllocation.resource_type == "court",
                ScheduleAllocation.organization_id == scope.organization_id,
                ScheduleAllocation.venue_id == scope.venue_id,
                ScheduleAllocation.active.is_(True),
                ScheduleAllocation.starts_at < ends_at,
                ScheduleAllocation.ends_at > starts_at,
            )
        ).all()
    )
    usage_seconds: dict[str, float] = {court.id: 0 for court in courts}
    for row in allocations:
        if row.resource_id not in usage_seconds:
            continue
        clipped_start = max(_aware(row.starts_at), starts_at)
        clipped_end = min(_aware(row.ends_at), ends_at)
        usage_seconds[row.resource_id] = usage_seconds.get(row.resource_id, 0) + max(
            (clipped_end - clipped_start).total_seconds(), 0
        )
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    available_hours = Decimal(0)
    cursor = period_start
    while cursor <= period_end:
        if venue:
            opening = venue.weekend_open_time if cursor.weekday() >= 5 else venue.weekday_open_time
            closing = (
                venue.weekend_close_time if cursor.weekday() >= 5 else venue.weekday_close_time
            )
            opened = datetime.combine(cursor, opening, zone)
            closed = datetime.combine(cursor, closing, zone)
            available_hours += Decimal(str((closed - opened).total_seconds() / 3600))
        cursor += timedelta(days=1)
    usage_hours = {
        court_id: money(Decimal(str(seconds / 3600))) for court_id, seconds in usage_seconds.items()
    }
    utilization = {
        court_id: min(float(hours / available_hours), 1.0) if available_hours else 0.0
        for court_id, hours in usage_hours.items()
    }
    return usage_hours, utilization
