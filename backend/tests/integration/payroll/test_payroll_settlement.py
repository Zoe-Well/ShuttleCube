from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.coach_fees import ensure_coach_fee
from shuttlecube.application.commands.expenses import create_expense, void_expense
from shuttlecube.application.commands.payroll import (
    create_payroll_settlement,
    void_payroll_settlement,
)
from shuttlecube.domain.finance.models import Expense
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement


def test_settlement_locks_fees_and_creates_one_payroll_expense(db: Session, admin) -> None:
    now = datetime(2026, 8, 4, tzinfo=UTC)
    ensure_coach_fee(
        db,
        source_type="class_session",
        source_id="session-1",
        coach_id="coach-1",
        occurred_at=now,
        amount=Decimal("100"),
    )
    ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="lesson-1",
        coach_id="coach-1",
        occurred_at=now,
        amount=Decimal("180"),
    )
    settlement = create_payroll_settlement(
        db,
        coach_id="coach-1",
        period_month=date(2026, 8, 1),
        actual_amount=Decimal("300.00"),
        adjustment_reason="额外交通补贴",
        paid_at=now,
        actor_id=admin.id,
        idempotency_key="settlement-1",
        request_id="settlement-request",
    )
    assert settlement.calculated_amount == Decimal("280.00")
    assert settlement.actual_amount == Decimal("300.00")
    assert db.query(Expense).filter_by(category="coach_payroll").count() == 1
    assert all(item.status == "settled" for item in db.query(CoachFee).all())

    repeated = create_payroll_settlement(
        db,
        coach_id="coach-1",
        period_month=date(2026, 8, 1),
        actual_amount=Decimal("300.00"),
        adjustment_reason="额外交通补贴",
        paid_at=now,
        actor_id=admin.id,
        idempotency_key="settlement-1",
        request_id="settlement-request",
    )
    assert repeated.id == settlement.id
    assert db.query(PayrollSettlement).count() == 1
    assert db.query(Expense).filter_by(category="coach_payroll").count() == 1


def test_settlement_does_not_allow_manual_cross_coach_or_partial_selection(
    db: Session, admin
) -> None:
    ensure_coach_fee(
        db,
        source_type="event",
        source_id="event-1",
        coach_id="coach-2",
        occurred_at=datetime(2026, 8, 4, tzinfo=UTC),
        amount=Decimal("80"),
    )
    with pytest.raises(BusinessError) as caught:
        create_payroll_settlement(
            db,
            coach_id="coach-1",
            period_month=date(2026, 8, 1),
            actual_amount=Decimal("80"),
            adjustment_reason=None,
            paid_at=datetime(2026, 8, 4, tzinfo=UTC),
            actor_id=admin.id,
            idempotency_key="wrong-coach",
            request_id="wrong-coach-request",
        )
    assert caught.value.code == "coach_fees_required"


def test_zero_amount_fee_can_be_included_in_monthly_settlement(db: Session, admin) -> None:
    occurred_at = datetime(2026, 8, 4, tzinfo=UTC)
    fee = ensure_coach_fee(
        db,
        source_type="class_session",
        source_id="zero-fee-session",
        coach_id="coach-zero",
        occurred_at=occurred_at,
        amount=Decimal("0.00"),
    )

    settlement = create_payroll_settlement(
        db,
        coach_id="coach-zero",
        period_month=date(2026, 8, 1),
        actual_amount=Decimal("0.00"),
        adjustment_reason=None,
        paid_at=occurred_at,
        actor_id=admin.id,
        idempotency_key="zero-settlement",
        request_id="zero-settlement-request",
    )

    assert settlement.calculated_amount == Decimal("0.00")
    assert settlement.actual_amount == Decimal("0.00")
    assert fee.status == "settled"
    expense = db.get(Expense, settlement.expense_id)
    assert expense is not None
    assert expense.amount == Decimal("0.00")


def test_payroll_expense_cannot_be_created_or_voided_outside_settlement(db: Session, admin) -> None:
    now = datetime(2026, 8, 4, tzinfo=UTC)
    with pytest.raises(BusinessError) as manual:
        create_expense(
            db,
            category="coach_payroll",
            spent_at=now,
            amount=Decimal("100.00"),
            payee="教练",
            payment_method="bank",
            source_type=None,
            source_id=None,
            notes=None,
            actor_id=admin.id,
            idempotency_key="manual-payroll-expense",
            request_id="manual-payroll-expense-request",
        )
    assert manual.value.code == "payroll_expense_requires_settlement"

    fee = ensure_coach_fee(
        db,
        source_type="class_session",
        source_id="protected-payroll-session",
        coach_id="coach-1",
        occurred_at=now,
        amount=Decimal("100.00"),
    )
    settlement = create_payroll_settlement(
        db,
        coach_id="coach-1",
        period_month=date(2026, 8, 1),
        actual_amount=Decimal("100.00"),
        adjustment_reason=None,
        paid_at=now,
        actor_id=admin.id,
        idempotency_key="protected-payroll-settlement",
        request_id="protected-payroll-settlement-request",
    )
    expense = db.get(Expense, settlement.expense_id)
    assert expense is not None

    with pytest.raises(BusinessError) as direct_void:
        void_expense(
            db,
            expense,
            reason="错误作废入口",
            actor_id=admin.id,
            request_id="direct-payroll-expense-void",
        )
    assert direct_void.value.code == "payroll_expense_requires_settlement_void"
    assert expense.status == "effective"
    assert settlement.status == "confirmed"
    assert fee.status == "settled"

    void_payroll_settlement(
        db,
        settlement,
        reason="结算登记错误",
        actor_id=admin.id,
        request_id="payroll-settlement-void",
    )
    assert expense.status == "void"
    assert settlement.status == "void"
    assert fee.status == "pending"
