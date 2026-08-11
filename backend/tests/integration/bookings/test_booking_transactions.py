from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.venue_bookings import quote_booking
from shuttlecube.domain.venue_bookings.models import VenuePriceRule


def test_quote_multiplies_hours_and_courts(db: Session) -> None:
    db.add(
        VenuePriceRule(
            name="周末",
            day_type="weekend",
            time_start=time(8),
            time_end=time(22),
            price_per_court_hour=Decimal("80"),
            priority=1,
        )
    )
    db.commit()
    z = ZoneInfo("Asia/Shanghai")
    amount, _ = quote_booking(
        db, datetime(2026, 8, 1, 10, tzinfo=z), datetime(2026, 8, 1, 12, tzinfo=z), ["1", "2"]
    )
    assert amount == Decimal("320.00")


def test_quote_sums_each_hour_across_weekday_price_periods(db: Session) -> None:
    db.add_all(
        [
            VenuePriceRule(
                name="工作日白天场",
                day_type="weekday",
                time_start=time(8),
                time_end=time(18),
                price_per_court_hour=Decimal("50"),
                priority=100,
            ),
            VenuePriceRule(
                name="工作日晚间场",
                day_type="weekday",
                time_start=time(18),
                time_end=time(23),
                price_per_court_hour=Decimal("80"),
                priority=100,
            ),
        ]
    )
    db.commit()
    zone = ZoneInfo("Asia/Shanghai")

    amount, rules = quote_booking(
        db,
        datetime(2026, 8, 3, 17, tzinfo=zone),
        datetime(2026, 8, 3, 20, tzinfo=zone),
        ["court-1", "court-2"],
    )

    assert amount == Decimal("420.00")
    assert {rule.name for rule in rules} == {"工作日白天场", "工作日晚间场"}


def test_quote_rejects_an_unpriced_hour(db: Session) -> None:
    db.add(
        VenuePriceRule(
            name="工作日白天场",
            day_type="weekday",
            time_start=time(8),
            time_end=time(18),
            price_per_court_hour=Decimal("50"),
            priority=100,
        )
    )
    db.commit()
    zone = ZoneInfo("Asia/Shanghai")

    with pytest.raises(BusinessError) as caught:
        quote_booking(
            db,
            datetime(2026, 8, 3, 17, tzinfo=zone),
            datetime(2026, 8, 3, 19, tzinfo=zone),
            ["court-1"],
        )

    assert caught.value.code == "price_rule_missing"
    assert "18:00-19:00" in caught.value.detail
