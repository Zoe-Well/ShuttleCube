from datetime import UTC, datetime, timedelta, timezone

from fastapi.encoders import jsonable_encoder

from shuttlecube.api.serialization import as_utc


def test_as_utc_restores_timezone_removed_by_sqlite() -> None:
    value = as_utc(datetime(2026, 7, 29, 16, 0))

    assert value.tzinfo is UTC
    assert jsonable_encoder(value) == "2026-07-29T16:00:00+00:00"


def test_as_utc_normalizes_aware_database_values() -> None:
    value = as_utc(datetime(2026, 7, 30, 0, 0, tzinfo=timezone(timedelta(hours=8))))

    assert value == datetime(2026, 7, 29, 16, 0, tzinfo=UTC)
