from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.reconciliation import (
    AffectedReference,
    InvariantCheck,
    ReconciliationImpact,
    ReconciliationRule,
    RepairEntryPoint,
    failed_result,
)
from shuttlecube.application.queries.receivables import receivable_summary
from shuttlecube.domain.finance.models import Payment, Receivable, Refund


def _expected_status(payment_status: str, outstanding: Decimal) -> str:
    if payment_status == "refunded":
        return "refunded"
    if payment_status == "partially_refunded":
        return "partially_refunded"
    if outstanding <= 0:
        return "settled"
    return "open"


def check_receivable_summaries(db: Session, scope: RequestScope):
    receivables = db.scalars(
        select(Receivable).where(
            Receivable.organization_id == scope.organization_id,
            Receivable.venue_id == scope.venue_id,
        )
    ).all()
    failures = []
    for receivable in receivables:
        payments = db.scalars(
            select(Payment).where(Payment.receivable_id == receivable.id)
        ).all()
        refunds = db.scalars(
            select(Refund).where(Refund.receivable_id == receivable.id)
        ).all()
        effective_payments = [item for item in payments if item.status == "effective"]
        effective_refunds = [item for item in refunds if item.status == "effective"]
        summary = receivable_summary(db, receivable)
        wrong_scope = [
            item.id
            for item in [*payments, *refunds]
            if item.organization_id != scope.organization_id or item.venue_id != scope.venue_id
        ]
        invalid_amounts = [
            item.id
            for item in [*effective_payments, *effective_refunds]
            if (item.amount if isinstance(item, Payment) else item.actual_amount) <= 0
        ]
        invalid_refund_payment = []
        payment_by_id = {item.id: item for item in payments}
        for refund in effective_refunds:
            if refund.payment_id and (
                refund.payment_id not in payment_by_id
                or payment_by_id[refund.payment_id].receivable_id != receivable.id
            ):
                invalid_refund_payment.append(refund.id)
        bounds_ok = (
            receivable.actual_amount >= 0
            and summary.refunded_amount <= summary.received_amount
            and summary.net_received >= 0
            and summary.net_received <= summary.actual_amount
        )
        expected_status = _expected_status(summary.payment_status, summary.outstanding_amount)
        status_ok = receivable.status == "void" or receivable.status == expected_status
        if not (wrong_scope or invalid_amounts or invalid_refund_payment) and bounds_ok and status_ok:
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="receivable.summary",
                rule_version=1,
                subject_type="receivable",
                subject_id=receivable.id,
                severity="critical" if not bounds_ok or wrong_scope else "high",
                invariants=[
                    InvariantCheck(
                        key="payment_refund_scope",
                        expected="payments and refunds share the receivable Scope",
                        actual=f"wrong-scope ids: {wrong_scope}",
                        passed=not wrong_scope,
                    ),
                    InvariantCheck(
                        key="positive_effective_amounts",
                        expected="effective payment and refund amounts are positive",
                        actual=f"invalid ids: {invalid_amounts}",
                        passed=not invalid_amounts,
                    ),
                    InvariantCheck(
                        key="refund_payment_relation",
                        expected="linked payment belongs to the same receivable",
                        actual=f"invalid refund ids: {invalid_refund_payment}",
                        passed=not invalid_refund_payment,
                    ),
                    InvariantCheck(
                        key="receivable_bounds",
                        expected="0 <= net received <= actual and refunds <= received",
                        actual=(
                            f"actual={summary.actual_amount}, received={summary.received_amount}, "
                            f"refunded={summary.refunded_amount}, net={summary.net_received}"
                        ),
                        passed=bounds_ok,
                    ),
                    InvariantCheck(
                        key="derived_status",
                        expected=expected_status if receivable.status != "void" else "void",
                        actual=receivable.status,
                        passed=status_ok,
                    ),
                ],
                affected_refs=[
                    AffectedReference(
                        kind="receivable", id=receivable.id, version=receivable.version
                    ),
                    *[AffectedReference(kind="payment", id=item.id) for item in payments],
                    *[AffectedReference(kind="refund", id=item.id) for item in refunds],
                ],
                repair_entry_points=[
                    RepairEntryPoint(
                        label="查看应收明细", route=f"/finance/receivables/{receivable.id}"
                    )
                ],
                impact=ReconciliationImpact(
                    affected_amount=str(
                        max(summary.actual_amount, summary.received_amount, summary.refunded_amount)
                    ),
                    downstream_records=len(payments) + len(refunds),
                ),
            )
        )
    return failures


FINANCE_RULES = (
    ReconciliationRule("receivable.summary", 1, 1, check_receivable_summaries),
)
