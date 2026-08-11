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
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.finance.models import Expense
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement
from shuttlecube.domain.private_lessons.models import PrivateLesson


def _source(db: Session, fee: CoachFee):
    models = {
        "class_session": ClassSession,
        "private_lesson": PrivateLesson,
        "event": TemporaryEvent,
    }
    model = models.get(fee.source_type)
    return db.get(model, fee.source_id) if model else None


def _source_valid(fee: CoachFee, source: object | None, scope: RequestScope) -> bool:
    if source is None:
        return False
    return (
        getattr(source, "organization_id", None) == scope.organization_id
        and getattr(source, "venue_id", None) == scope.venue_id
        and getattr(source, "status", None) == "completed"
        and getattr(source, "coach_id", getattr(source, "actual_coach_id", None))
        == fee.coach_id
    )


def check_coach_fee_sources(db: Session, scope: RequestScope):
    expected_sources: list[tuple[str, object, str]] = []
    for item in db.scalars(
        select(ClassSession).where(
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
            ClassSession.status == "completed",
        )
    ).all():
        expected_sources.append(("class_session", item, item.actual_coach_id))
    for item in db.scalars(
        select(PrivateLesson).where(
            PrivateLesson.organization_id == scope.organization_id,
            PrivateLesson.venue_id == scope.venue_id,
            PrivateLesson.status == "completed",
        )
    ).all():
        expected_sources.append(("private_lesson", item, item.coach_id))
    for item in db.scalars(
        select(TemporaryEvent).where(
            TemporaryEvent.organization_id == scope.organization_id,
            TemporaryEvent.venue_id == scope.venue_id,
            TemporaryEvent.status == "completed",
            TemporaryEvent.coach_id.is_not(None),
        )
    ).all():
        expected_sources.append(("event", item, str(item.coach_id)))

    failures = []
    checked_fee_ids: set[str] = set()
    for source_type, source, coach_id in expected_sources:
        fees = db.scalars(
            select(CoachFee).where(
                CoachFee.organization_id == scope.organization_id,
                CoachFee.venue_id == scope.venue_id,
                CoachFee.source_type == source_type,
                CoachFee.source_id == source.id,
                CoachFee.coach_id == coach_id,
                CoachFee.status != "void",
            )
        ).all()
        checked_fee_ids.update(item.id for item in fees)
        if len(fees) == 1:
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="coach_fee.source",
                rule_version=1,
                subject_type=source_type,
                subject_id=source.id,
                severity="high",
                invariants=[
                    InvariantCheck(
                        key="completed_source_fee",
                        expected="completed source has exactly one non-void coach fee",
                        actual=f"fee ids: {[item.id for item in fees]}",
                        passed=False,
                    )
                ],
                affected_refs=[
                    AffectedReference(
                        kind=source_type, id=source.id, version=getattr(source, "version", None)
                    ),
                    *[AffectedReference(kind="coach_fee", id=item.id, version=item.version) for item in fees],
                ],
                repair_entry_points=[
                    RepairEntryPoint(label="查看教练费用", route="/payroll")
                ],
                impact=ReconciliationImpact(downstream_records=len(fees)),
            )
        )

    fees = db.scalars(
        select(CoachFee).where(
            CoachFee.organization_id == scope.organization_id,
            CoachFee.venue_id == scope.venue_id,
            CoachFee.status != "void",
        )
    ).all()
    for fee in fees:
        if fee.id in checked_fee_ids:
            continue
        source = _source(db, fee)
        if _source_valid(fee, source, scope):
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="coach_fee.source",
                rule_version=1,
                subject_type="coach_fee",
                subject_id=fee.id,
                severity="high",
                invariants=[
                    InvariantCheck(
                        key="fee_source_state",
                        expected="non-void fee source exists, is completed and uses the same coach",
                        actual=(
                            "source missing"
                            if source is None
                            else f"status={getattr(source, 'status', None)}, coach={getattr(source, 'coach_id', getattr(source, 'actual_coach_id', None))}"
                        ),
                        passed=False,
                    )
                ],
                affected_refs=[
                    AffectedReference(kind="coach_fee", id=fee.id, version=fee.version),
                    AffectedReference(kind=fee.source_type, id=fee.source_id),
                ],
                repair_entry_points=[
                    RepairEntryPoint(label="查看教练费用", route="/payroll")
                ],
                impact=ReconciliationImpact(
                    affected_amount=str(fee.base_amount + fee.adjustment_amount),
                    downstream_records=1,
                ),
            )
        )
    return failures


def check_payroll_integrity(db: Session, scope: RequestScope):
    settlements = db.scalars(
        select(PayrollSettlement).where(
            PayrollSettlement.organization_id == scope.organization_id,
            PayrollSettlement.venue_id == scope.venue_id,
        )
    ).all()
    failures = []
    for settlement in settlements:
        expense = db.scalar(
            select(Expense).where(
                Expense.id == settlement.expense_id,
                Expense.organization_id == scope.organization_id,
                Expense.venue_id == scope.venue_id,
            )
        )
        fees = db.scalars(
            select(CoachFee).where(
                CoachFee.organization_id == scope.organization_id,
                CoachFee.venue_id == scope.venue_id,
                CoachFee.settlement_id == settlement.id,
            )
        ).all()
        if settlement.status == "confirmed":
            expense_ok = (
                expense is not None
                and expense.status == "effective"
                and expense.category == "coach_payroll"
                and expense.source_type == "payroll_settlement"
                and expense.source_id == settlement.id
                and expense.amount == settlement.actual_amount
            )
            fee_scope_ok = bool(fees) and all(
                item.coach_id == settlement.coach_id
                and item.status == "settled"
                and settlement.period_start <= item.occurred_at.date() <= settlement.period_end
                for item in fees
            )
            calculated = sum(
                (item.base_amount + item.adjustment_amount for item in fees), Decimal("0.00")
            )
            amount_ok = (
                calculated == settlement.calculated_amount
                and settlement.actual_amount
                == settlement.calculated_amount + settlement.adjustment_amount
            )
        else:
            expense_ok = expense is None or expense.status == "void"
            fee_scope_ok = not fees
            amount_ok = True
        if expense_ok and fee_scope_ok and amount_ok:
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="payroll.integrity",
                rule_version=1,
                subject_type="payroll_settlement",
                subject_id=settlement.id,
                severity="critical",
                invariants=[
                    InvariantCheck(
                        key="payroll_expense",
                        expected="settlement has one matching expense; void settlement has no effective expense",
                        actual=f"expense_id={expense.id if expense else None}, status={expense.status if expense else None}",
                        passed=expense_ok,
                    ),
                    InvariantCheck(
                        key="settled_fee_membership",
                        expected="fees belong to the same coach and natural month and match settlement state",
                        actual=f"fee ids: {[item.id for item in fees]}",
                        passed=fee_scope_ok,
                    ),
                    InvariantCheck(
                        key="settlement_amount",
                        expected="calculated and actual amounts match fee sum and adjustment",
                        actual=(
                            f"calculated={settlement.calculated_amount}, actual={settlement.actual_amount}, "
                            f"fee_sum={calculated if settlement.status == 'confirmed' else 'n/a'}"
                        ),
                        passed=amount_ok,
                    ),
                ],
                affected_refs=[
                    AffectedReference(
                        kind="payroll_settlement", id=settlement.id, version=settlement.version
                    ),
                    *[AffectedReference(kind="coach_fee", id=item.id, version=item.version) for item in fees],
                    *([AffectedReference(kind="expense", id=expense.id)] if expense else []),
                ],
                repair_entry_points=[
                    RepairEntryPoint(label="查看工资结算", route="/payroll")
                ],
                impact=ReconciliationImpact(
                    affected_amount=str(settlement.actual_amount),
                    downstream_records=len(fees) + (1 if expense else 0),
                ),
            )
        )
    return failures


PAYROLL_RULES = (
    ReconciliationRule("coach_fee.source", 1, 1, check_coach_fee_sources),
    ReconciliationRule("payroll.integrity", 1, 1, check_payroll_integrity),
)
