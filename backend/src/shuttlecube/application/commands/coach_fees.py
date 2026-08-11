from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.queries.receivables import money
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.payroll.models import CoachFee
from shuttlecube.domain.private_lessons.models import PrivateLesson


def ensure_coach_fee(
    db: Session,
    *,
    source_type: str,
    source_id: str,
    coach_id: str,
    occurred_at: datetime,
    amount: Decimal,
    organization_id: str,
    venue_id: str,
) -> CoachFee:
    existing = db.scalar(
        select(CoachFee).where(
            CoachFee.source_type == source_type,
            CoachFee.source_id == source_id,
            CoachFee.coach_id == coach_id,
            CoachFee.organization_id == organization_id,
            CoachFee.venue_id == venue_id,
        )
    )
    if existing:
        return existing
    value = money(amount)
    if value < 0:
        raise BusinessError(422, "invalid_coach_fee", "教练费用不得为负数")
    item = CoachFee(
        organization_id=organization_id,
        venue_id=venue_id,
        source_type=source_type,
        source_id=source_id,
        coach_id=coach_id,
        occurred_at=occurred_at,
        base_amount=value,
        adjustment_amount=Decimal("0.00"),
    )
    db.add(item)
    db.flush()
    return item


def ensure_class_session_fee(db: Session, session: ClassSession) -> CoachFee:
    fixed_class = db.get(FixedClass, session.fixed_class_id)
    if fixed_class is None:
        raise BusinessError(409, "fixed_class_missing", "课程所属固定班不存在")
    amount = session.coach_fee_override
    if amount is None:
        amount = fixed_class.coach_fee_per_session
    return ensure_coach_fee(
        db,
        source_type="class_session",
        source_id=session.id,
        coach_id=session.actual_coach_id or fixed_class.default_coach_id,
        occurred_at=session.scheduled_end,
        amount=amount,
        organization_id=session.organization_id,
        venue_id=session.venue_id,
    )


def ensure_private_lesson_fee(db: Session, item: PrivateLesson) -> CoachFee:
    return ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id=item.id,
        coach_id=item.coach_id,
        occurred_at=item.ends_at,
        amount=item.coach_fee,
        organization_id=item.organization_id,
        venue_id=item.venue_id,
    )


def ensure_event_fee(db: Session, item: TemporaryEvent) -> CoachFee | None:
    if item.coach_id is None:
        return None
    return ensure_coach_fee(
        db,
        source_type="event",
        source_id=item.id,
        coach_id=item.coach_id,
        occurred_at=item.ends_at,
        amount=item.coach_fee,
        organization_id=item.organization_id,
        venue_id=item.venue_id,
    )


def adjust_coach_fee(
    db: Session,
    item: CoachFee,
    *,
    adjustment_amount: Decimal,
    reason: str,
    commit: bool = True,
) -> CoachFee:
    if item.status != "pending":
        raise BusinessError(409, "coach_fee_locked", "已结算或作废费用不能调整")
    item.adjustment_amount = money(adjustment_amount)
    item.adjustment_reason = reason
    if money(item.base_amount + item.adjustment_amount) < 0:
        raise BusinessError(422, "invalid_coach_fee_adjustment", "调整后教练费用不得为负数")
    if commit:
        db.commit()
    return item
