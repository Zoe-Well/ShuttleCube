from dataclasses import dataclass
from datetime import datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

from shuttlecube.api.errors import BusinessError
from shuttlecube.infrastructure.database.base import utc_now

PAST_TIME = "past_time"
OUTSIDE_BUSINESS_HOURS = "outside_business_hours"


class VenueHours(Protocol):
    timezone: str
    weekday_open_time: time
    weekday_close_time: time
    weekend_open_time: time
    weekend_close_time: time


@dataclass(frozen=True)
class ScheduleTimeWarning:
    code: str
    message: str


def _local(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def validate_schedule_range(starts_at: datetime, ends_at: datetime) -> None:
    if ends_at <= starts_at:
        raise BusinessError(422, "invalid_time_range", "结束时间必须晚于开始时间")
    if any(
        value.minute != 0 or value.second or value.microsecond
        for value in (starts_at, ends_at)
    ):
        raise BusinessError(422, "invalid_time_increment", "开始和结束时间必须选择整点")


def collect_schedule_warnings(
    starts_at: datetime,
    ends_at: datetime,
    *,
    venue: VenueHours | None = None,
    now: datetime | None = None,
) -> list[ScheduleTimeWarning]:
    zone = ZoneInfo(venue.timezone if venue else "Asia/Shanghai")
    local_start = _local(starts_at, zone)
    local_end = _local(ends_at, zone)
    local_now = _local(now or utc_now(), zone)
    warnings: list[ScheduleTimeWarning] = []

    if local_start < local_now:
        warnings.append(ScheduleTimeWarning(PAST_TIME, "所选开始时间已经过去，是否仍要创建？"))

    weekend = local_start.weekday() >= 5
    open_time = (
        venue.weekend_open_time
        if venue and weekend
        else venue.weekday_open_time
        if venue
        else time(8, 0)
    )
    close_time = (
        venue.weekend_close_time
        if venue and weekend
        else venue.weekday_close_time
        if venue
        else time(22, 0)
    )
    outside = (
        local_start.date() != local_end.date()
        or local_start.time().replace(tzinfo=None) < open_time
        or local_end.time().replace(tzinfo=None) > close_time
    )
    if outside:
        warnings.append(
            ScheduleTimeWarning(
                OUTSIDE_BUSINESS_HOURS,
                f"所选时间不在球馆营业时段 {open_time.strftime('%H:%M')}–{close_time.strftime('%H:%M')} 内，是否仍要创建？",
            )
        )
    return warnings


def require_schedule_warning_acknowledgements(
    warnings: list[ScheduleTimeWarning], acknowledged: set[str]
) -> None:
    missing = [warning for warning in warnings if warning.code not in acknowledged]
    if missing:
        raise BusinessError(
            422,
            "schedule_warning_confirmation_required",
            "该排期包含需要确认的时间警告",
            warnings=[{"code": warning.code, "message": warning.message} for warning in missing],
        )


def validate_business_hours(
    starts_at: datetime, ends_at: datetime, open_hour: int = 8, close_hour: int = 22
) -> None:
    """Retained for callers that require the legacy hard business-hours rule."""
    validate_schedule_range(starts_at, ends_at)
    zone = ZoneInfo("Asia/Shanghai")
    local_start = _local(starts_at, zone)
    local_end = _local(ends_at, zone)
    if (
        local_start.date() != local_end.date()
        or local_start.time() < time(open_hour, 0, tzinfo=zone)
        or local_end.time() > time(close_hour, 0, tzinfo=zone)
    ):
        raise BusinessError(422, "outside_business_hours", "排期超出营业时间或跨越日期")
