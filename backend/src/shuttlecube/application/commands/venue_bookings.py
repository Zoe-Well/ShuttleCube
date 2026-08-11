from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.receivables import create_receivable
from shuttlecube.application.commands.schedule import (
    cancel_schedule,
    create_schedule,
    delete_schedule_entries,
    delete_schedule_source,
)
from shuttlecube.application.queries.receivables import receivable_for_source
from shuttlecube.application.queries.schedule_display import booking_schedule_title
from shuttlecube.domain.scheduling.conflicts import Resource
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.scheduling.models import ScheduleEntry
from shuttlecube.domain.scheduling.policies import validate_schedule_range
from shuttlecube.domain.venue_bookings.models import VenueBooking, VenuePriceRule
from shuttlecube.infrastructure.database.base import utc_now


def booking_has_ended(item: VenueBooking) -> bool:
    ends_at = item.ends_at.replace(tzinfo=UTC) if item.ends_at.tzinfo is None else item.ends_at
    return ends_at.astimezone(UTC) <= utc_now()


def complete_booking(db: Session, item: VenueBooking) -> VenueBooking:
    if item.status == "completed":
        return item
    if item.status not in {"booked", "confirmed"}:
        raise BusinessError(409, "invalid_booking_state", "当前订场不可完成")
    if not booking_has_ended(item):
        raise BusinessError(409, "booking_not_ended", "订场尚未结束，不能提前确认完成")
    item.status = "completed"
    db.commit()
    return item


def quote_booking(
    db: Session, starts_at: datetime, ends_at: datetime, court_ids: list[str]
) -> tuple[Decimal, list[VenuePriceRule]]:
    validate_schedule_range(starts_at, ends_at)
    venue = db.scalar(select(Venue).limit(1))
    zone = ZoneInfo(venue.timezone if venue else "Asia/Shanghai")
    local_start = starts_at.replace(tzinfo=zone) if starts_at.tzinfo is None else starts_at.astimezone(zone)
    local_end = ends_at.replace(tzinfo=zone) if ends_at.tzinfo is None else ends_at.astimezone(zone)
    if local_start.date() != local_end.date():
        raise BusinessError(422, "invalid_price_range", "订场价格不能跨日期计算")

    rules = list(
        db.scalars(
            select(VenuePriceRule)
            .where(VenuePriceRule.is_active.is_(True))
            .order_by(VenuePriceRule.priority.desc(), VenuePriceRule.created_at.desc())
        ).all()
    )
    amount = Decimal("0")
    applied: list[VenuePriceRule] = []
    missing: list[str] = []
    slot_start = local_start
    while slot_start < local_end:
        slot_end = slot_start + timedelta(hours=1)
        day_type = "weekend" if slot_start.weekday() >= 5 else "weekday"
        applicable = next(
            (
                rule
                for rule in rules
                if rule.day_type in {day_type, "custom"}
                and (rule.effective_from is None or rule.effective_from <= slot_start.date())
                and (rule.effective_to is None or rule.effective_to >= slot_start.date())
                and rule.time_start <= slot_start.time().replace(tzinfo=None)
                and rule.time_end >= slot_end.time().replace(tzinfo=None)
            ),
            None,
        )
        if applicable is None:
            missing.append(f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}")
        else:
            amount += applicable.price_per_court_hour * len(court_ids)
            if all(rule.id != applicable.id for rule in applied):
                applied.append(applicable)
        slot_start = slot_end
    if missing:
        raise BusinessError(
            422,
            "price_rule_missing",
            f"以下时段尚未配置默认价格：{'、'.join(missing)}",
        )
    return amount.quantize(Decimal("0.01")), applied


def create_booking(
    db: Session,
    customer_id: str,
    starts_at: datetime,
    ends_at: datetime,
    court_ids: list[str],
    actual: Decimal | None,
    reason: str | None,
    notes: str | None,
    warning_acknowledgements: list[str] | None = None,
) -> VenueBooking:
    suggested, rules = quote_booking(db, starts_at, ends_at, court_ids)
    value = actual if actual is not None else suggested
    if value != suggested and not reason:
        raise BusinessError(422, "adjustment_reason_required", "调整订场金额必须填写原因")
    item = VenueBooking(
        customer_id=customer_id,
        starts_at=starts_at,
        ends_at=ends_at,
        court_ids_csv=",".join(court_ids),
        price_rule_id=rules[0].id if len(rules) == 1 else None,
        suggested_receivable=suggested,
        actual_receivable=value,
        price_adjustment_reason=reason,
        notes=notes,
    )
    db.add(item)
    db.flush()
    entry = create_schedule(
        db,
        source_type="venue_booking",
        source_id=item.id,
        title=booking_schedule_title(db, item),
        starts_at=starts_at,
        ends_at=ends_at,
        resources=[Resource("court", x) for x in court_ids],
        acknowledged_warnings=warning_acknowledgements,
        commit=False,
    )
    item.schedule_entry_id = entry.id
    create_receivable(
        db,
        source_type="venue_booking",
        source_id=item.id,
        suggested_amount=suggested,
        actual_amount=value,
        adjustment_reason=reason,
    )
    db.commit()
    return item


def reschedule_booking(
    db: Session,
    item: VenueBooking,
    *,
    starts_at: datetime,
    ends_at: datetime,
    court_ids: list[str],
    warning_acknowledgements: list[str] | None = None,
) -> VenueBooking:
    if item.status not in {"booked", "confirmed"} or not item.schedule_entry_id:
        raise BusinessError(409, "invalid_booking_state", "当前订场不可修改")
    if booking_has_ended(item):
        raise BusinessError(409, "past_booking_requires_completion", "已结束订场请先确认完成")
    old_entry = db.get(ScheduleEntry, item.schedule_entry_id)
    if old_entry is None:
        raise BusinessError(409, "schedule_missing", "订场排期不存在")
    suggested, rules = quote_booking(db, starts_at, ends_at, court_ids)
    cancel_schedule(db, old_entry, "修改散客订场", commit=False)
    replacement = create_schedule(
        db,
        source_type="venue_booking",
        source_id=item.id,
        title=booking_schedule_title(db, item),
        starts_at=starts_at,
        ends_at=ends_at,
        resources=[Resource("court", court_id) for court_id in court_ids],
        acknowledged_warnings=warning_acknowledgements,
        commit=False,
    )
    delete_schedule_entries(db, [old_entry], commit=False)
    if item.actual_receivable == item.suggested_receivable:
        item.actual_receivable = suggested
    item.starts_at = starts_at
    item.ends_at = ends_at
    item.court_ids_csv = ",".join(court_ids)
    item.price_rule_id = rules[0].id if len(rules) == 1 else None
    item.suggested_receivable = suggested
    item.schedule_entry_id = replacement.id
    receivable = receivable_for_source(db, "venue_booking", item.id)
    if receivable:
        if receivable.actual_amount == receivable.suggested_amount:
            receivable.actual_amount = suggested
        receivable.suggested_amount = suggested
    db.commit()
    return item


def cancel_booking(
    db: Session, item: VenueBooking, reason: str, *, commit: bool = True
) -> VenueBooking:
    if item.status not in {"booked", "confirmed"}:
        raise BusinessError(409, "invalid_booking_state", "当前订场不可取消")
    if booking_has_ended(item):
        raise BusinessError(409, "past_booking_requires_completion", "已结束订场请先确认完成")
    if item.schedule_entry_id:
        entry = db.get(ScheduleEntry, item.schedule_entry_id)
        if entry:
            cancel_schedule(db, entry, reason, commit=False)
    item.status = "cancelled"
    item.notes = f"{item.notes or ''}\n取消原因：{reason}".strip()
    if commit:
        db.commit()
    return item


def delete_booking(db: Session, item: VenueBooking, *, commit: bool = True) -> str:
    if item.status == "completed":
        raise BusinessError(409, "completed_booking_cannot_delete", "已完成订场不可删除")
    if booking_has_ended(item):
        raise BusinessError(409, "past_booking_requires_completion", "已结束订场请先确认完成")
    item_id = item.id
    db.delete(item)
    db.flush()
    delete_schedule_source(db, "venue_booking", item_id, commit=False)
    if commit:
        db.commit()
    return item_id
