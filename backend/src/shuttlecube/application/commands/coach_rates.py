from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.queries.receivables import money
from shuttlecube.domain.identity.coach import CoachRate
from shuttlecube.domain.scheduling.court import Venue

RATE_TYPES = ("fixed_class", "private_lesson")


def venue_business_date(db: Session, value: datetime | None = None) -> date:
    venue = db.scalar(select(Venue).limit(1))
    zone = ZoneInfo(venue.timezone if venue else "Asia/Shanghai")
    instant = value or datetime.now(UTC)
    aware = instant if instant.tzinfo else instant.replace(tzinfo=UTC)
    return aware.astimezone(zone).date()


def coach_rate(
    db: Session, coach_id: str, business_type: str, on_date: date | None = None
) -> CoachRate | None:
    effective_date = on_date or venue_business_date(db)
    return db.scalar(
        select(CoachRate)
        .where(
            CoachRate.coach_id == coach_id,
            CoachRate.business_type == business_type,
            CoachRate.effective_from <= effective_date,
            (CoachRate.effective_to.is_(None)) | (CoachRate.effective_to >= effective_date),
        )
        .order_by(CoachRate.effective_from.desc())
    )


def set_coach_rate(
    db: Session,
    *,
    coach_id: str,
    business_type: str,
    amount: Decimal,
    effective_from: date,
) -> CoachRate:
    if business_type not in RATE_TYPES:
        raise BusinessError(422, "invalid_coach_rate_type", "不支持的教练费用类型")
    value = money(amount)
    if value < 0:
        raise BusinessError(422, "invalid_coach_rate", "教练费用标准不得为负数")
    existing = db.scalar(
        select(CoachRate).where(
            CoachRate.coach_id == coach_id,
            CoachRate.business_type == business_type,
            CoachRate.effective_from == effective_from,
        )
    )
    if existing:
        existing.amount = value
        return existing
    future = db.scalar(
        select(CoachRate).where(
            CoachRate.coach_id == coach_id,
            CoachRate.business_type == business_type,
            CoachRate.effective_from > effective_from,
        )
    )
    if future:
        raise BusinessError(422, "coach_rate_backdating_not_allowed", "已有更晚生效的费用标准")
    previous = db.scalar(
        select(CoachRate)
        .where(
            CoachRate.coach_id == coach_id,
            CoachRate.business_type == business_type,
            CoachRate.effective_from < effective_from,
        )
        .order_by(CoachRate.effective_from.desc())
    )
    if previous:
        previous.effective_to = effective_from - timedelta(days=1)
    item = CoachRate(
        coach_id=coach_id,
        business_type=business_type,
        amount=value,
        effective_from=effective_from,
    )
    db.add(item)
    db.flush()
    return item
