from datetime import datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from shuttlecube.api.errors import BusinessError
from shuttlecube.domain.scheduling.policies import (
    collect_schedule_warnings,
    validate_schedule_range,
)

ZONE = ZoneInfo("Asia/Shanghai")
VENUE = SimpleNamespace(
    timezone="Asia/Shanghai",
    weekday_open_time=time(14, 0),
    weekday_close_time=time(22, 0),
    weekend_open_time=time(8, 0),
    weekend_close_time=time(22, 0),
)


def test_schedule_range_requires_end_after_start() -> None:
    start = datetime(2026, 7, 31, 14, 0, tzinfo=ZONE)

    with pytest.raises(BusinessError) as caught:
        validate_schedule_range(start, start)

    assert caught.value.code == "invalid_time_range"


def test_schedule_range_requires_hour_boundaries() -> None:
    start = datetime(2026, 7, 31, 14, 30, tzinfo=ZONE)

    with pytest.raises(BusinessError) as caught:
        validate_schedule_range(start, datetime(2026, 7, 31, 15, 0, tzinfo=ZONE))

    assert caught.value.code == "invalid_time_increment"


def test_past_and_outside_business_hours_are_confirmable_warnings() -> None:
    warnings = collect_schedule_warnings(
        datetime(2026, 7, 31, 13, 0, tzinfo=ZONE),
        datetime(2026, 7, 31, 14, 0, tzinfo=ZONE),
        venue=VENUE,
        now=datetime(2026, 7, 31, 15, 0, tzinfo=ZONE),
    )

    assert {warning.code for warning in warnings} == {
        "past_time",
        "outside_business_hours",
    }


def test_valid_weekend_slot_has_no_warning() -> None:
    warnings = collect_schedule_warnings(
        datetime(2026, 8, 1, 8, 0, tzinfo=ZONE),
        datetime(2026, 8, 1, 10, 0, tzinfo=ZONE),
        venue=VENUE,
        now=datetime(2026, 7, 31, 15, 0, tzinfo=ZONE),
    )

    assert warnings == []
