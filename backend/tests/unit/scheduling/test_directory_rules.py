from datetime import UTC, datetime

import pytest

from shuttlecube.api.errors import BusinessError
from shuttlecube.domain.scheduling.policies import validate_business_hours


def test_rejects_cross_day_schedule() -> None:
    with pytest.raises(BusinessError):
        validate_business_hours(
            datetime(2026, 7, 29, 20, tzinfo=UTC), datetime(2026, 7, 30, 1, tzinfo=UTC)
        )
