from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.schedule import create_schedule
from shuttlecube.domain.scheduling.conflicts import Resource


def test_overlapping_court_is_rejected_atomically(db: Session) -> None:
    zone = ZoneInfo("Asia/Shanghai")
    start = datetime(2026, 8, 1, 10, tzinfo=zone)
    end = datetime(2026, 8, 1, 12, tzinfo=zone)
    create_schedule(
        db,
        source_type="event",
        source_id="a",
        title="A",
        starts_at=start,
        ends_at=end,
        resources=[Resource("court", "court-1")],
    )
    with pytest.raises(BusinessError) as caught:
        create_schedule(
            db,
            source_type="booking",
            source_id="b",
            title="B",
            starts_at=start,
            ends_at=end,
            resources=[Resource("court", "court-1")],
        )
    assert caught.value.code == "schedule_conflict"


def test_past_schedule_requires_and_accepts_explicit_acknowledgement(db: Session) -> None:
    zone = ZoneInfo("Asia/Shanghai")
    start = datetime(2020, 8, 1, 10, tzinfo=zone)
    end = datetime(2020, 8, 1, 11, 0, tzinfo=zone)

    with pytest.raises(BusinessError) as caught:
        create_schedule(
            db,
            source_type="event",
            source_id="past-warning",
            title="历史补录",
            starts_at=start,
            ends_at=end,
            resources=[Resource("court", "court-past")],
            acknowledged_warnings=[],
        )

    assert caught.value.code == "schedule_warning_confirmation_required"
    entry = create_schedule(
        db,
        source_type="event",
        source_id="past-warning",
        title="历史补录",
        starts_at=start,
        ends_at=end,
        resources=[Resource("court", "court-past")],
        acknowledged_warnings=["past_time"],
    )
    assert entry.id
