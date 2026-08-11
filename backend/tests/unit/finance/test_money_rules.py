from decimal import Decimal

from shuttlecube.application.queries.receivables import calculate_money_summary


def test_money_summary_tracks_partial_and_settled_payments() -> None:
    partial = calculate_money_summary(
        Decimal("100.00"), Decimal("60.00"), Decimal("0.00")
    )
    assert partial.outstanding_amount == Decimal("40.00")
    assert partial.payment_status == "partial"

    settled = calculate_money_summary(
        Decimal("100.00"), Decimal("100.00"), Decimal("0.00")
    )
    assert settled.outstanding_amount == Decimal("0.00")
    assert settled.payment_status == "paid"


def test_refund_uses_net_cash_and_explicitly_reduced_receivable() -> None:
    summary = calculate_money_summary(
        Decimal("75.00"), Decimal("100.00"), Decimal("25.00")
    )
    assert summary.net_received == Decimal("75.00")
    assert summary.outstanding_amount == Decimal("0.00")
    assert summary.payment_status == "partially_refunded"


def test_full_refund_has_no_outstanding_balance() -> None:
    summary = calculate_money_summary(
        Decimal("0.00"), Decimal("100.00"), Decimal("100.00")
    )
    assert summary.net_received == Decimal("0.00")
    assert summary.outstanding_amount == Decimal("0.00")
    assert summary.payment_status == "refunded"
