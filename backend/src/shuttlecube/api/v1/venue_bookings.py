from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.api.serialization import as_utc
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.venue_bookings import (
    complete_booking,
    create_booking,
    delete_booking,
    quote_booking,
    reschedule_booking,
)
from shuttlecube.application.queries.receivables import receivable_for_source, receivable_summary
from shuttlecube.domain.customers.models import WalkInCustomer
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.venue_bookings.models import VenueBooking, VenuePriceRule
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["VenueBookings"])


class PriceRuleWrite(BaseModel):
    name: str
    day_type: str = "weekday"
    effective_from: date | None = None
    effective_to: date | None = None
    time_start: time
    time_end: time
    price_per_court_hour: Decimal = Field(gt=0)
    priority: int = 0


PricePeriodType = Literal["weekday_day", "weekday_evening", "weekend"]
DEFAULT_PRICE_NAMES: dict[str, str] = {
    "weekday_day": "工作日白天场",
    "weekday_evening": "工作日晚间场",
    "weekend": "周末场",
}


class DefaultPricePeriodWrite(BaseModel):
    period_type: PricePeriodType
    time_start: time
    time_end: time
    price_per_court_hour: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def validate_period(self) -> DefaultPricePeriodWrite:
        if any(
            value.minute or value.second or value.microsecond
            for value in (self.time_start, self.time_end)
        ):
            raise ValueError("默认价格时段必须使用整点")
        if self.time_end <= self.time_start:
            raise ValueError("默认价格时段的结束时间必须晚于开始时间")
        return self


class DefaultPriceRulesWrite(BaseModel):
    periods: list[DefaultPricePeriodWrite] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_periods(self) -> DefaultPriceRulesWrite:
        by_type = {period.period_type: period for period in self.periods}
        if set(by_type) != set(DEFAULT_PRICE_NAMES):
            raise ValueError("必须完整设置工作日白天、工作日晚间和周末价格")
        if by_type["weekday_day"].time_end > by_type["weekday_evening"].time_start:
            raise ValueError("工作日白天与晚间价格时段不能重叠")
        return self


class QuoteWrite(BaseModel):
    starts_at: datetime
    ends_at: datetime
    court_ids: list[str] = Field(min_length=1)


class BookingWrite(QuoteWrite):
    customer_id: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    actual_receivable: Decimal | None = None
    price_adjustment_reason: str | None = None
    notes: str | None = None
    warning_acknowledgements: list[str] = Field(default_factory=list)


class BookingReschedule(QuoteWrite):
    warning_acknowledgements: list[str] = Field(default_factory=list)


class CancelWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class BulkCancelWrite(CancelWrite):
    ids: list[str] = Field(min_length=1)


def customer_name(db: Session, customer_id: str) -> str:
    item = db.get(WalkInCustomer, customer_id)
    return item.display_name if item else customer_id


def hard_delete_booking(
    db: Session,
    item: VenueBooking,
    *,
    actor_id: str,
    request_id: str,
    reason: str,
    commit: bool = True,
) -> str:
    item_id = delete_booking(db, item, commit=False)
    record_audit(
        db,
        actor_id=actor_id,
        action="venue_booking.deleted",
        entity_type="venue_booking",
        entity_id=item_id,
        request_id=request_id,
        reason=reason,
    )
    if commit:
        db.commit()
    return item_id


@router.get("/venue-price-rules")
def rules(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    return [
        {
            "id": x.id,
            "name": x.name,
            "day_type": x.day_type,
            "time_start": x.time_start,
            "time_end": x.time_end,
            "price_per_court_hour": x.price_per_court_hour,
            "priority": x.priority,
            "status": "active" if x.is_active else "inactive",
            "version": x.version,
        }
        for x in db.scalars(select(VenuePriceRule)).all()
    ]


def default_rule_view(period_type: str, item: VenuePriceRule) -> dict[str, object]:
    return {
        "id": item.id,
        "period_type": period_type,
        "name": item.name,
        "time_start": item.time_start,
        "time_end": item.time_end,
        "price_per_court_hour": item.price_per_court_hour,
        "version": item.version,
    }


def default_rule_summary(period_type: str, item: VenuePriceRule) -> dict[str, object]:
    return {
        "period_type": period_type,
        "time_start": item.time_start.isoformat(),
        "time_end": item.time_end.isoformat(),
        "price_per_court_hour": str(item.price_per_court_hour),
    }


def active_default_rules(db: Session) -> list[tuple[str, VenuePriceRule]]:
    items = list(
        db.scalars(
            select(VenuePriceRule).where(
                VenuePriceRule.is_active.is_(True),
                VenuePriceRule.effective_from.is_(None),
                VenuePriceRule.effective_to.is_(None),
                VenuePriceRule.day_type.in_(["weekday", "weekend"]),
            )
        ).all()
    )
    exact = {name: code for code, name in DEFAULT_PRICE_NAMES.items()}
    result: list[tuple[str, VenuePriceRule]] = []
    claimed: set[str] = set()
    for item in items:
        code = exact.get(item.name)
        if code and code not in claimed:
            result.append((code, item))
            claimed.add(code)
    weekday_fallbacks = sorted(
        (item for item in items if item.day_type == "weekday" and item.name not in exact),
        key=lambda item: item.time_start,
    )
    for code, item in zip(
        (code for code in ("weekday_day", "weekday_evening") if code not in claimed),
        weekday_fallbacks,
        strict=False,
    ):
        result.append((code, item))
        claimed.add(code)
    if "weekend" not in claimed:
        fallback = next(
            (item for item in items if item.day_type == "weekend" and item.name not in exact),
            None,
        )
        if fallback:
            result.append(("weekend", fallback))
    return result


@router.get("/venue-price-rules/defaults")
def get_default_price_rules(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    return [default_rule_view(code, item) for code, item in active_default_rules(db)]


@router.put("/venue-price-rules/defaults")
def put_default_price_rules(
    payload: DefaultPriceRulesWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> list[dict[str, object]]:
    previous = active_default_rules(db)
    before = [default_rule_summary(code, item) for code, item in previous]
    old_defaults = db.scalars(
        select(VenuePriceRule).where(
            VenuePriceRule.is_active.is_(True),
            VenuePriceRule.effective_from.is_(None),
            VenuePriceRule.effective_to.is_(None),
            VenuePriceRule.day_type.in_(["weekday", "weekend"]),
        )
    ).all()
    for item in old_defaults:
        item.is_active = False
    created: list[tuple[str, VenuePriceRule]] = []
    for period in payload.periods:
        item = VenuePriceRule(
            name=DEFAULT_PRICE_NAMES[period.period_type],
            day_type="weekend" if period.period_type == "weekend" else "weekday",
            time_start=period.time_start,
            time_end=period.time_end,
            price_per_court_hour=period.price_per_court_hour,
            priority=100,
        )
        db.add(item)
        created.append((period.period_type, item))
    db.flush()
    after = [default_rule_view(code, item) for code, item in created]
    record_audit(
        db,
        actor_id=user.id,
        action="venue.default_prices_updated",
        entity_type="venue_price_rules",
        entity_id="defaults",
        request_id=getattr(request.state, "request_id", "unknown"),
        before={"periods": before},
        after={"periods": [default_rule_summary(code, item) for code, item in created]},
    )
    db.commit()
    return after


@router.post("/venue-price-rules", status_code=201)
def post_rule(
    p: PriceRuleWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    x = VenuePriceRule(**p.model_dump())
    db.add(x)
    db.commit()
    db.refresh(x)
    return {"id": x.id, "version": x.version}


@router.post("/venue-bookings/quote")
def quote(
    p: QuoteWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> dict[str, object]:
    amount, rules = quote_booking(db, p.starts_at, p.ends_at, p.court_ids)
    return {
        "suggested_receivable": amount,
        "price_rule_id": rules[0].id if len(rules) == 1 else None,
        "price_rule_ids": [rule.id for rule in rules],
        "court_count": len(p.court_ids),
    }


@router.get("/venue-bookings")
def bookings(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, object]]:
    if from_date and to_date and from_date > to_date:
        raise BusinessError(422, "invalid_booking_date_range", "开始日期不能晚于结束日期")
    statement = select(VenueBooking).where(VenueBooking.status != "cancelled")
    venue = db.scalar(select(Venue).limit(1))
    zone = ZoneInfo(venue.timezone if venue else "Asia/Shanghai")
    if from_date:
        starts_at = datetime.combine(from_date, time.min, zone).astimezone(UTC)
        statement = statement.where(VenueBooking.starts_at >= starts_at)
    if to_date:
        ends_at = datetime.combine(to_date + timedelta(days=1), time.min, zone).astimezone(UTC)
        statement = statement.where(VenueBooking.starts_at < ends_at)
    statement = statement.order_by(VenueBooking.starts_at.desc())
    result: list[dict[str, object]] = []
    for x in db.scalars(statement).all():
        receivable = receivable_for_source(db, "venue_booking", x.id)
        finance = receivable_summary(db, receivable) if receivable else None
        result.append(
            {
            "id": x.id,
            "schedule_entry_id": x.schedule_entry_id,
            "customer_id": x.customer_id,
            "customer_name": customer_name(db, x.customer_id),
            "starts_at": as_utc(x.starts_at),
            "ends_at": as_utc(x.ends_at),
            "court_ids": x.court_ids_csv.split(","),
            "suggested_receivable": x.suggested_receivable,
            "actual_receivable": x.actual_receivable,
            "receivable_id": finance.receivable_id if finance else None,
            "outstanding_amount": finance.outstanding_amount if finance else x.actual_receivable,
            "refundable_amount": finance.refundable_amount if finance else Decimal("0.00"),
            "payment_status": finance.payment_status if finance else x.payment_status,
            "status": x.status,
            "version": x.version,
            }
        )
    return result


@router.post("/venue-bookings/{booking_id}/complete")
def post_complete_booking(
    booking_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(VenueBooking, booking_id)
    if not item:
        raise BusinessError(404, "booking_not_found", "订场不存在")
    item = complete_booking(db, item)
    return {"id": item.id, "status": item.status, "version": item.version}


@router.post("/venue-bookings", status_code=201)
def post_booking(
    p: BookingWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    customer_id = p.customer_id
    if not customer_id:
        customer = WalkInCustomer(display_name=p.customer_name or "散客", phone=p.customer_phone)
        db.add(customer)
        db.flush()
        customer_id = customer.id
    x = create_booking(
        db,
        customer_id,
        p.starts_at,
        p.ends_at,
        p.court_ids,
        p.actual_receivable,
        p.price_adjustment_reason,
        p.notes,
        p.warning_acknowledgements,
    )
    return {
        "id": x.id,
        "schedule_entry_id": x.schedule_entry_id,
        "suggested_receivable": x.suggested_receivable,
        "actual_receivable": x.actual_receivable,
        "status": x.status,
        "version": x.version,
    }


@router.post("/venue-bookings/bulk-delete")
@router.post("/venue-bookings/bulk-cancel")
def bulk_cancel_bookings(
    p: BulkCancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    items = [db.get(VenueBooking, item_id) for item_id in p.ids]
    if any(item is None for item in items):
        raise BusinessError(404, "booking_not_found", "部分订场不存在")
    for item in items:
        if item is not None:
            hard_delete_booking(
                db,
                item,
                actor_id=user.id,
                request_id=getattr(request.state, "request_id", "unknown"),
                reason=p.reason,
                commit=False,
            )
    db.commit()
    return {"ids": p.ids, "status": "deleted"}


@router.delete("/venue-bookings/{booking_id}", status_code=204)
def delete_venue_booking(
    booking_id: str,
    p: CancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> Response:
    item = db.get(VenueBooking, booking_id)
    if not item:
        raise BusinessError(404, "booking_not_found", "订场不存在")
    hard_delete_booking(
        db,
        item,
        actor_id=user.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        reason=p.reason,
    )
    return Response(status_code=204)


@router.post("/venue-bookings/{booking_id}/reschedule")
def post_reschedule_booking(
    booking_id: str,
    p: BookingReschedule,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(VenueBooking, booking_id)
    if not item:
        raise BusinessError(404, "booking_not_found", "订场不存在")
    item = reschedule_booking(db, item, **p.model_dump())
    return {
        "id": item.id,
        "schedule_entry_id": item.schedule_entry_id,
        "starts_at": as_utc(item.starts_at),
        "ends_at": as_utc(item.ends_at),
        "court_ids": item.court_ids_csv.split(","),
        "status": item.status,
        "version": item.version,
    }


@router.post("/venue-bookings/{booking_id}/cancel")
def post_cancel_booking(
    booking_id: str,
    p: CancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(VenueBooking, booking_id)
    if not item:
        raise BusinessError(404, "booking_not_found", "订场不存在")
    item_id = hard_delete_booking(
        db,
        item,
        actor_id=user.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        reason=p.reason,
    )
    return {"id": item_id, "status": "deleted"}
