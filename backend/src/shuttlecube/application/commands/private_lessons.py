from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.commands.coach_fees import ensure_private_lesson_fee
from shuttlecube.application.commands.receivables import create_receivable
from shuttlecube.application.commands.schedule import (
    cancel_schedule,
    create_schedule,
    delete_schedule_entries,
    delete_schedule_source,
)
from shuttlecube.application.queries.schedule_display import private_lesson_schedule_title
from shuttlecube.domain.classes.enrollment_models import LessonUnitLedger
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.private_lessons.models import PrivateLesson, PrivateLessonPackage
from shuttlecube.domain.scheduling.conflicts import Resource
from shuttlecube.domain.scheduling.models import ScheduleEntry
from shuttlecube.infrastructure.database.base import utc_now


def private_lesson_has_ended(item: PrivateLesson) -> bool:
    ends_at = item.ends_at.replace(tzinfo=UTC) if item.ends_at.tzinfo is None else item.ends_at
    return ends_at.astimezone(UTC) <= utc_now()


def create_package(
    db: Session,
    student_id: str,
    coach_id: str,
    units: int,
    unit_price: Decimal,
    actual: Decimal | None,
    valid_until: datetime | None,
    actor_id: str,
    notes: str | None = None,
) -> PrivateLessonPackage:
    student = db.get(Student, student_id)
    if student is None:
        raise BusinessError(404, "student_not_found", "学员不存在")
    if not student.is_active:
        raise BusinessError(422, "student_inactive", "学员已停用，不能购买私教课包")
    coach = db.get(CoachProfile, coach_id)
    if coach is None:
        raise BusinessError(404, "coach_not_found", "教练不存在")
    if not coach.is_active:
        raise BusinessError(422, "coach_inactive", "教练已停用，不能绑定私教课包")
    value = actual if actual is not None else unit_price * units
    item = PrivateLessonPackage(
        student_id=student_id,
        bound_coach_id=coach_id,
        purchased_units=units,
        unit_price=unit_price,
        actual_receivable=value,
        valid_until=valid_until,
        notes=notes,
    )
    db.add(item)
    db.flush()
    db.add(
        LessonUnitLedger(
            owner_type="private_package",
            owner_id=item.id,
            change_type="purchase",
            delta=units,
            balance_before=0,
            balance_after=units,
            source_type="private_package",
            source_id=item.id,
            operated_by=actor_id,
            operated_at=utc_now(),
            idempotency_key=f"private-package:{item.id}",
        )
    )
    create_receivable(
        db,
        source_type="private_package",
        source_id=item.id,
        suggested_amount=unit_price * units,
        actual_amount=value,
        adjustment_reason="课包金额调整" if value != unit_price * units else None,
    )
    db.commit()
    return item


def book_private_lesson(
    db: Session,
    student_id: str,
    coach_id: str,
    package_id: str | None,
    billing_mode: str,
    starts_at: datetime,
    ends_at: datetime,
    court_ids: list[str],
    actual_receivable: Decimal,
    coach_fee: Decimal,
    notes: str | None,
    warning_acknowledgements: list[str] | None = None,
) -> PrivateLesson:
    if billing_mode == "package" and not package_id:
        raise BusinessError(422, "package_required", "课包模式必须选择课包")
    if package_id:
        package = db.get(PrivateLessonPackage, package_id)
        if (
            not package
            or package.status != "active"
            or package.bound_coach_id != coach_id
            or package.student_id != student_id
            or (
                package.valid_until is not None
                and (
                    package.valid_until.replace(tzinfo=UTC)
                    if package.valid_until.tzinfo is None
                    else package.valid_until
                )
                < utc_now()
            )
            or balance(db, package.id) < 1
        ):
            raise BusinessError(422, "invalid_package", "课包不可用或绑定教练不匹配")
    item = PrivateLesson(
        student_id=student_id,
        coach_id=coach_id,
        package_id=package_id,
        billing_mode=billing_mode,
        starts_at=starts_at,
        ends_at=ends_at,
        actual_receivable=actual_receivable,
        coach_fee=coach_fee,
        notes=notes,
    )
    db.add(item)
    db.flush()
    entry = create_schedule(
        db,
        source_type="private_lesson",
        source_id=item.id,
        title=private_lesson_schedule_title(db, item),
        starts_at=starts_at,
        ends_at=ends_at,
        resources=[
            *[Resource("court", court_id) for court_id in court_ids],
            Resource("coach", coach_id),
            Resource("student", student_id),
        ],
        acknowledged_warnings=warning_acknowledgements,
        commit=False,
    )
    item.schedule_entry_id = entry.id
    if billing_mode == "single":
        create_receivable(
            db,
            source_type="private_lesson",
            source_id=item.id,
            suggested_amount=actual_receivable,
            actual_amount=actual_receivable,
        )
    db.commit()
    return item


def complete_private_lesson(
    db: Session, item: PrivateLesson, actor_id: str, idempotency_key: str
) -> PrivateLesson:
    if item.status == "completed":
        return item
    if item.status != "booked":
        raise BusinessError(409, "invalid_lesson_state", "当前私教不可完成")
    if not private_lesson_has_ended(item):
        raise BusinessError(409, "lesson_not_ended", "私教尚未结束，不能提前确认完成")
    if item.billing_mode == "package" and item.package_id:
        before = balance(db, item.package_id)
        if before < 1:
            raise BusinessError(422, "insufficient_units", "私教课包课时不足")
        db.add(
            LessonUnitLedger(
                owner_type="private_package",
                owner_id=item.package_id,
                change_type="attendance",
                delta=-1,
                balance_before=before,
                balance_after=before - 1,
                source_type="private_lesson",
                source_id=item.id,
                operated_by=actor_id,
                operated_at=utc_now(),
                idempotency_key=idempotency_key,
            )
        )
        if before == 1:
            package = db.get(PrivateLessonPackage, item.package_id)
            if package:
                package.status = "exhausted"
    item.status = "completed"
    ensure_private_lesson_fee(db, item)
    db.commit()
    return item


def reschedule_private_lesson(
    db: Session,
    item: PrivateLesson,
    *,
    starts_at: datetime,
    ends_at: datetime,
    court_ids: list[str],
    coach_id: str | None = None,
    warning_acknowledgements: list[str] | None = None,
) -> PrivateLesson:
    if item.status != "booked" or not item.schedule_entry_id:
        raise BusinessError(409, "invalid_lesson_state", "当前私教不可改期")
    if private_lesson_has_ended(item):
        raise BusinessError(409, "past_lesson_requires_completion", "已结束私教请先确认完成")
    old_entry = db.get(ScheduleEntry, item.schedule_entry_id)
    if old_entry is None:
        raise BusinessError(409, "schedule_missing", "私教排期不存在")
    next_coach = coach_id or item.coach_id
    if item.package_id:
        package = db.get(PrivateLessonPackage, item.package_id)
        if package and package.bound_coach_id != next_coach:
            raise BusinessError(422, "package_coach_mismatch", "课包仅可由绑定教练履约")
    cancel_schedule(db, old_entry, "私教改期", commit=False)
    replacement = create_schedule(
        db,
        source_type="private_lesson",
        source_id=item.id,
        title=private_lesson_schedule_title(db, item),
        starts_at=starts_at,
        ends_at=ends_at,
        resources=[
            *[Resource("court", court_id) for court_id in court_ids],
            Resource("coach", next_coach),
            Resource("student", item.student_id),
        ],
        acknowledged_warnings=warning_acknowledgements,
        commit=False,
    )
    delete_schedule_entries(db, [old_entry], commit=False)
    item.starts_at = starts_at
    item.ends_at = ends_at
    item.coach_id = next_coach
    item.schedule_entry_id = replacement.id
    db.commit()
    return item


def cancel_private_lesson(
    db: Session, item: PrivateLesson, reason: str, *, commit: bool = True
) -> PrivateLesson:
    if item.status != "booked":
        raise BusinessError(409, "invalid_lesson_state", "当前私教不可取消")
    if item.schedule_entry_id:
        entry = db.get(ScheduleEntry, item.schedule_entry_id)
        if entry:
            cancel_schedule(db, entry, reason, commit=False)
    item.status = "cancelled"
    item.adjustment_reason = reason
    if commit:
        db.commit()
    return item


def delete_private_lesson(db: Session, item: PrivateLesson, *, commit: bool = True) -> str:
    if item.status == "completed":
        raise BusinessError(409, "completed_lesson_cannot_delete", "已完成私教不可删除")
    if private_lesson_has_ended(item):
        raise BusinessError(409, "past_lesson_requires_completion", "已结束私教请先确认完成")
    item_id = item.id
    db.delete(item)
    db.flush()
    delete_schedule_source(db, "private_lesson", item_id, commit=False)
    if commit:
        db.commit()
    return item_id
