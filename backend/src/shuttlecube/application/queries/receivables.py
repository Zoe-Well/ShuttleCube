from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.domain.finance.models import Payment, Receivable, Refund

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ReceivableSummary:
    receivable_id: str
    source_type: str
    source_id: str
    suggested_amount: Decimal
    actual_amount: Decimal
    received_amount: Decimal
    refunded_amount: Decimal
    net_received: Decimal
    outstanding_amount: Decimal
    refundable_amount: Decimal
    payment_status: str
    status: str
    version: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def audit_dict(self) -> dict[str, object]:
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(self).items()
        }


@dataclass(frozen=True)
class MoneySummary:
    net_received: Decimal
    outstanding_amount: Decimal
    refundable_amount: Decimal
    payment_status: str


def money(value: Decimal | int | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def calculate_money_summary(
    actual_amount: Decimal, received_amount: Decimal, refunded_amount: Decimal
) -> MoneySummary:
    actual = money(actual_amount)
    received = money(received_amount)
    refunded = money(refunded_amount)
    net = money(received - refunded)
    outstanding = money(max(actual - net, ZERO))
    refundable = money(max(net, ZERO))
    if received > ZERO and refunded >= received:
        payment_status = "refunded"
    elif refunded > ZERO:
        payment_status = "partially_refunded"
    elif outstanding == ZERO:
        payment_status = "paid"
    elif net > ZERO:
        payment_status = "partial"
    else:
        payment_status = "unpaid"
    return MoneySummary(net, outstanding, refundable, payment_status)


def _sum_payments(db: Session, receivable_id: str) -> Decimal:
    return money(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.receivable_id == receivable_id, Payment.status == "effective"
            )
        )
    )


def _sum_refunds(db: Session, receivable_id: str) -> Decimal:
    return money(
        db.scalar(
            select(func.coalesce(func.sum(Refund.actual_amount), 0)).where(
                Refund.receivable_id == receivable_id, Refund.status == "effective"
            )
        )
    )


def receivable_summary(db: Session, item: Receivable) -> ReceivableSummary:
    received = _sum_payments(db, item.id)
    refunded = _sum_refunds(db, item.id)
    calculated = calculate_money_summary(item.actual_amount, received, refunded)
    return ReceivableSummary(
        receivable_id=item.id,
        source_type=item.source_type,
        source_id=item.source_id,
        suggested_amount=money(item.suggested_amount),
        actual_amount=money(item.actual_amount),
        received_amount=received,
        refunded_amount=refunded,
        net_received=calculated.net_received,
        outstanding_amount=calculated.outstanding_amount,
        refundable_amount=calculated.refundable_amount,
        payment_status=calculated.payment_status,
        status=item.status,
        version=item.version,
    )


def receivable_for_source(db: Session, source_type: str, source_id: str) -> Receivable | None:
    return db.scalar(
        select(Receivable).where(
            Receivable.source_type == source_type, Receivable.source_id == source_id
        )
    )


def list_receivable_summaries(
    db: Session,
    *,
    scope: RequestScope | None = None,
    source_type: str | None = None,
    status: str | None = None,
) -> list[ReceivableSummary]:
    statement = select(Receivable).order_by(Receivable.created_at.desc())
    if scope is not None:
        statement = statement.where(
            Receivable.organization_id == scope.organization_id,
            Receivable.venue_id == scope.venue_id,
        )
    if source_type:
        statement = statement.where(Receivable.source_type == source_type)
    if status:
        statement = statement.where(Receivable.status == status)
    return [receivable_summary(db, item) for item in db.scalars(statement).all()]


def sync_receivable_status(db: Session, item: Receivable) -> ReceivableSummary:
    summary = receivable_summary(db, item)
    if item.status != "void":
        if summary.payment_status == "refunded":
            item.status = "refunded"
        elif summary.payment_status == "partially_refunded":
            item.status = "partially_refunded"
        elif summary.outstanding_amount == ZERO:
            item.status = "settled"
        else:
            item.status = "open"
    return receivable_summary(db, item)
