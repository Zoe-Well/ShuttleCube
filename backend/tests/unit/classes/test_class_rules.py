from datetime import date, time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from shuttlecube.api.v1.classes import FixedClassWrite
from shuttlecube.domain.classes.class_models import FixedClass


def test_fixed_class_keeps_explicit_capacity_and_price() -> None:
    item = FixedClass(
        name="周六班",
        class_type="training",
        start_date=date(2026, 8, 1),
        default_start_time=time(10),
        duration_minutes=120,
        session_count=12,
        capacity=12,
        default_coach_id="coach",
        required_court_count=2,
        student_unit_price=Decimal("100"),
        coach_fee_per_session=Decimal("200"),
    )
    assert item.session_count == 12 and item.student_unit_price == Decimal("100")


@pytest.mark.parametrize(
    ("start_time", "duration_minutes"),
    [(time(10, 30), 60), (time(10), 90), (time(10), 30)],
)
def test_fixed_class_requires_hourly_sessions(
    start_time: time, duration_minutes: int
) -> None:
    with pytest.raises(ValidationError):
        FixedClassWrite(
            name="整点班",
            start_date=date(2026, 8, 1),
            default_start_time=start_time,
            duration_minutes=duration_minutes,
            session_count=1,
            capacity=8,
            default_coach_id="coach",
            court_ids=["court"],
            student_unit_price=Decimal("100"),
        )
