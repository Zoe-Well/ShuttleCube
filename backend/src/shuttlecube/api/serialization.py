from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Restore UTC information lost by SQLite while preserving aware database values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
