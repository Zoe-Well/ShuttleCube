from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def as_utc(value: datetime) -> datetime:
    """Restore UTC information lost by SQLite while preserving aware database values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def beijing_today() -> date:
    return datetime.now(BEIJING_TIMEZONE).date()
