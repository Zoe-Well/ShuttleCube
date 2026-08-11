from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.application.commands.coach_fees import ensure_coach_fee
from shuttlecube.application.commands.coach_rates import coach_rate, set_coach_rate
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.payroll.models import CoachFee


def test_completed_source_generates_one_pending_fee(db: Session) -> None:
    first = ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="lesson-1",
        coach_id="coach-1",
        occurred_at=datetime(2026, 8, 4, tzinfo=UTC),
        amount=Decimal("180.00"),
    )
    second = ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="lesson-1",
        coach_id="coach-1",
        occurred_at=datetime(2026, 8, 4, tzinfo=UTC),
        amount=Decimal("180.00"),
    )
    assert first.id == second.id
    assert first.status == "pending"
    assert db.query(CoachFee).count() == 1


def test_zero_amount_completed_source_still_generates_fee_fact(db: Session) -> None:
    fee = ensure_coach_fee(
        db,
        source_type="class_session",
        source_id="zero-fee-session",
        coach_id="coach-zero",
        occurred_at=datetime(2026, 8, 4, tzinfo=UTC),
        amount=Decimal("0.00"),
    )

    assert fee.base_amount == Decimal("0.00")
    assert fee.status == "pending"


def test_effective_dated_coach_rates_preserve_history(db: Session) -> None:
    coach = CoachProfile(name="费率教练")
    db.add(coach)
    db.flush()
    august = set_coach_rate(
        db,
        coach_id=coach.id,
        business_type="fixed_class",
        amount=Decimal("180.00"),
        effective_from=date(2026, 8, 1),
    )
    september = set_coach_rate(
        db,
        coach_id=coach.id,
        business_type="fixed_class",
        amount=Decimal("200.00"),
        effective_from=date(2026, 9, 1),
    )

    assert august.effective_to == date(2026, 8, 31)
    assert coach_rate(db, coach.id, "fixed_class", date(2026, 8, 20)) is august
    assert coach_rate(db, coach.id, "fixed_class", date(2026, 9, 20)) is september
