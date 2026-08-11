from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry

COMMERCIAL_SOURCE_TYPES = frozenset(
    {"class_session", "private_lesson", "venue_booking", "event"}
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _hours(seconds: float) -> Decimal:
    return (Decimal(str(seconds)) / Decimal("3600")).quantize(Decimal("0.01"))


def _union_seconds(intervals: Iterable[tuple[datetime, datetime]]) -> float:
    ordered = sorted(
        ((start, end) for start, end in intervals if end > start),
        key=lambda item: (item[0], item[1]),
    )
    if not ordered:
        return 0.0
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        total += (current_end - current_start).total_seconds()
        current_start, current_end = start, end
    return total + (current_end - current_start).total_seconds()


def _intersections(
    intervals: Iterable[tuple[datetime, datetime]],
    windows: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    result: list[tuple[datetime, datetime]] = []
    materialized_windows = list(windows)
    for start, end in intervals:
        for window_start, window_end in materialized_windows:
            clipped_start = max(start, window_start)
            clipped_end = min(end, window_end)
            if clipped_end > clipped_start:
                result.append((clipped_start, clipped_end))
    return result


def _business_windows(
    venue: Venue,
    *,
    period_start: date,
    period_end: date,
    effective_end: datetime,
) -> list[tuple[datetime, datetime]]:
    zone = ZoneInfo(venue.timezone)
    windows: list[tuple[datetime, datetime]] = []
    cursor = period_start
    effective = _aware(effective_end)
    while cursor <= period_end:
        opening = venue.weekend_open_time if cursor.weekday() >= 5 else venue.weekday_open_time
        closing = venue.weekend_close_time if cursor.weekday() >= 5 else venue.weekday_close_time
        opened = datetime.combine(cursor, opening, zone).astimezone(UTC)
        closed = datetime.combine(cursor, closing, zone).astimezone(UTC)
        closed = min(closed, effective)
        if closed > opened:
            windows.append((opened, closed))
        cursor += timedelta(days=1)
    return windows


def build_court_capacity(
    db: Session,
    *,
    scope: RequestScope,
    period_start: date,
    period_end: date,
    effective_end: datetime,
) -> dict[str, object]:
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if venue is None:
        raise LookupError("scope venue not found")
    courts = list(
        db.scalars(
            select(Court)
            .where(Court.venue_id == scope.venue_id, Court.is_active.is_(True))
            .order_by(Court.code, Court.id)
        ).all()
    )
    zone = ZoneInfo(venue.timezone)
    period_starts_at = datetime.combine(period_start, time.min, zone).astimezone(UTC)
    period_ends_at = min(
        datetime.combine(period_end + timedelta(days=1), time.min, zone).astimezone(UTC),
        _aware(effective_end),
    )
    windows = _business_windows(
        venue,
        period_start=period_start,
        period_end=period_end,
        effective_end=period_ends_at,
    )
    base_seconds = _union_seconds(windows)
    allocations = list(
        db.execute(
            select(ScheduleAllocation, ScheduleEntry)
            .join(ScheduleEntry, ScheduleEntry.id == ScheduleAllocation.schedule_entry_id)
            .where(
                ScheduleAllocation.organization_id == scope.organization_id,
                ScheduleAllocation.venue_id == scope.venue_id,
                ScheduleAllocation.resource_type == "court",
                ScheduleAllocation.active.is_(True),
                ScheduleAllocation.starts_at < period_ends_at,
                ScheduleAllocation.ends_at > period_starts_at,
                ScheduleEntry.organization_id == scope.organization_id,
                ScheduleEntry.venue_id == scope.venue_id,
                ScheduleEntry.status.not_in(("cancelled", "deleted")),
            )
        ).all()
    )
    per_court: list[dict[str, object]] = []
    for court in courts:
        court_rows = [row for row in allocations if row[0].resource_id == court.id]
        block_intervals = [
            (
                max(_aware(allocation.starts_at), period_starts_at),
                min(_aware(allocation.ends_at), period_ends_at),
            )
            for allocation, entry in court_rows
            if entry.source_type == "court_block"
        ]
        commercial_intervals = [
            (
                max(_aware(allocation.starts_at), period_starts_at),
                min(_aware(allocation.ends_at), period_ends_at),
            )
            for allocation, entry in court_rows
            if entry.source_type in COMMERCIAL_SOURCE_TYPES
        ]
        block_business = _intersections(block_intervals, windows)
        usage_business = _intersections(commercial_intervals, windows)
        block_seconds = _union_seconds(block_business)
        usage_seconds = _union_seconds(usage_business)
        all_usage_seconds = _union_seconds(commercial_intervals)
        outside_seconds = max(all_usage_seconds - usage_seconds, 0.0)
        usage_during_block_seconds = _union_seconds(
            _intersections(usage_business, block_business)
        )
        available_seconds = max(base_seconds - block_seconds, 0.0)
        raw = Decimal("0")
        if available_seconds > 0:
            raw = Decimal(str(usage_seconds / available_seconds)).quantize(Decimal("0.0001"))
        display = min(max(raw, Decimal("0")), Decimal("1"))
        quality: list[str] = []
        if outside_seconds > 0:
            quality.append("commercial_usage_outside_business_hours")
        if usage_during_block_seconds > 0:
            quality.append("commercial_usage_overlaps_court_block")
        if available_seconds <= 0 and usage_seconds > 0:
            quality.append("usage_with_zero_available_capacity")
        per_court.append(
            {
                "court_id": court.id,
                "court_name": court.name,
                "base_business_hours": str(_hours(base_seconds)),
                "court_block_unavailable_hours": str(_hours(block_seconds)),
                "available_hours": str(_hours(available_seconds)),
                "commercial_usage_hours": str(_hours(usage_seconds)),
                "outside_business_hours": str(_hours(outside_seconds)),
                "usage_during_block_hours": str(_hours(usage_during_block_seconds)),
                "raw_utilization": str(raw),
                "display_utilization": str(display),
                "data_quality": quality,
            }
        )
    totals = {
        key: str(
            sum(
                (Decimal(str(item[key])) for item in per_court),
                Decimal("0"),
            ).quantize(Decimal("0.01"))
        )
        for key in (
            "base_business_hours",
            "court_block_unavailable_hours",
            "available_hours",
            "commercial_usage_hours",
            "outside_business_hours",
            "usage_during_block_hours",
        )
    }
    available = Decimal(totals["available_hours"])
    used = Decimal(totals["commercial_usage_hours"])
    raw_total = (used / available).quantize(Decimal("0.0001")) if available > 0 else Decimal("0")
    totals["raw_utilization"] = str(raw_total)
    totals["display_utilization"] = str(min(max(raw_total, Decimal("0")), Decimal("1")))
    return {
        "method": "commercial_usage_over_business_hours_minus_court_blocks",
        "per_court": per_court,
        "totals": totals,
        "data_quality": sorted(
            {issue for item in per_court for issue in item["data_quality"]}
        ),
    }

