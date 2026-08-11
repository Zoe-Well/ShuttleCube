from decimal import Decimal

from shuttlecube.infrastructure.database.types import money


def test_private_price_uses_decimal() -> None:
    assert money(Decimal("299.999")) == Decimal("300.00")
