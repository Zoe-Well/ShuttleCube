from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.commands.receivables import create_receivable
from shuttlecube.application.commands.schedule import create_schedule
from shuttlecube.application.queries.receivables import (
    receivable_for_source,
    sync_receivable_status,
)
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment, LessonUnitLedger
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.scheduling.conflicts import Resource
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry
from shuttlecube.infrastructure.database.base import utc_now


@dataclass(frozen=True)
class EnrollmentRenewal:
    enrollment_id: str
    added_units: int
    added_actual_amount: Decimal | None
    adjustment_reason: str | None


def _require_version(item: FixedClass | ClassSession, version: int, label: str) -> None:
    if item.version != version:
        raise BusinessError(409, "concurrent_change", f"{label}已经发生变化，请刷新后重试")


def _resources_for_session(db: Session, session: ClassSession) -> list[Resource]:
    if not session.schedule_entry_id:
        raise BusinessError(409, "schedule_missing", "课程排期不存在")
    rows = list(
        db.scalars(
            select(ScheduleAllocation).where(
                ScheduleAllocation.schedule_entry_id == session.schedule_entry_id
            )
        ).all()
    )
    if not rows:
        raise BusinessError(409, "schedule_resources_missing", "课程排期没有可复用的资源")
    return [Resource(row.resource_type, row.resource_id) for row in rows]


def reschedule_class_session(
    db: Session,
    session: ClassSession,
    *,
    starts_at: datetime,
    ends_at: datetime,
    reason: str,
    actor_id: str,
    request_id: str,
    version: int,
) -> ClassSession:
    _require_version(session, version, "课程")
    if session.status != "scheduled":
        raise BusinessError(409, "invalid_session_state", "只有待上课课程可以修改时间")
    if not session.schedule_entry_id:
        raise BusinessError(409, "schedule_missing", "课程排期不存在")
    old_entry = db.get(ScheduleEntry, session.schedule_entry_id)
    if old_entry is None:
        raise BusinessError(409, "schedule_missing", "课程排期不存在")
    resources = _resources_for_session(db, session)
    before: dict[str, object] = {
        "scheduled_start": session.scheduled_start.isoformat(),
        "scheduled_end": session.scheduled_end.isoformat(),
    }
    old_entry.status = "rescheduled"
    old_entry.cancellation_reason = reason
    db.execute(
        update(ScheduleAllocation)
        .where(ScheduleAllocation.schedule_entry_id == old_entry.id)
        .values(active=False)
    )
    fixed_class = db.get(FixedClass, session.fixed_class_id)
    entry = create_schedule(
        db,
        source_type="class_session",
        source_id=session.id,
        title=fixed_class.name if fixed_class else old_entry.title,
        starts_at=starts_at,
        ends_at=ends_at,
        resources=resources,
        commit=False,
    )
    entry.original_entry_id = old_entry.id
    session.scheduled_start = starts_at
    session.scheduled_end = ends_at
    session.schedule_entry_id = entry.id
    record_audit(
        db,
        actor_id=actor_id,
        action="class_session.rescheduled",
        entity_type="class_session",
        entity_id=session.id,
        request_id=request_id,
        before=before,
        after={"scheduled_start": starts_at.isoformat(), "scheduled_end": ends_at.isoformat()},
        reason=reason,
    )
    db.commit()
    db.refresh(session)
    return session


def update_class_capacity(
    db: Session,
    fixed_class: FixedClass,
    *,
    capacity: int,
    actor_id: str,
    request_id: str,
    version: int,
) -> FixedClass:
    _require_version(fixed_class, version, "固定班")
    active_count = (
        db.scalar(
            select(func.count())
            .select_from(Enrollment)
            .where(
                Enrollment.fixed_class_id == fixed_class.id,
                Enrollment.status == "active",
            )
        )
        or 0
    )
    if capacity < active_count:
        raise BusinessError(
            422,
            "capacity_below_active_enrollments",
            f"班级容量不能低于当前 {active_count} 名有效学员",
        )
    before = fixed_class.capacity
    fixed_class.capacity = capacity
    record_audit(
        db,
        actor_id=actor_id,
        action="fixed_class.capacity_changed",
        entity_type="fixed_class",
        entity_id=fixed_class.id,
        request_id=request_id,
        before={"capacity": before},
        after={"capacity": capacity},
    )
    db.commit()
    db.refresh(fixed_class)
    return fixed_class


def renew_fixed_class(
    db: Session,
    fixed_class: FixedClass,
    *,
    additional_sessions: int,
    enrollment_renewals: list[EnrollmentRenewal],
    actor_id: str,
    request_id: str,
    version: int,
) -> tuple[list[ClassSession], list[Enrollment]]:
    _require_version(fixed_class, version, "固定班")
    if fixed_class.status != "active":
        raise BusinessError(409, "class_not_active", "只有启用中的固定班可以续期")
    if additional_sessions <= 0:
        raise BusinessError(422, "invalid_session_count", "新增课次数必须大于零")
    sessions = list(
        db.scalars(
            select(ClassSession)
            .where(ClassSession.fixed_class_id == fixed_class.id)
            .order_by(ClassSession.scheduled_start.desc())
        ).all()
    )
    if not sessions:
        raise BusinessError(409, "class_has_no_sessions", "固定班没有可续期的课程基准")
    anchor = next(
        (session for session in sessions if session.replacement_for_session_id is None),
        sessions[0],
    )
    anchor_start = anchor.scheduled_start
    if anchor_start.tzinfo is None:
        anchor_start = anchor_start.replace(tzinfo=UTC)
    resources = _resources_for_session(db, anchor)
    next_sequence = max(item.sequence_number for item in sessions) + 1
    created: list[ClassSession] = []
    for index in range(additional_sessions):
        starts_at = anchor_start + timedelta(weeks=index + 1)
        ends_at = starts_at + timedelta(minutes=fixed_class.duration_minutes)
        session = ClassSession(
            fixed_class_id=fixed_class.id,
            sequence_number=next_sequence + index,
            scheduled_start=starts_at,
            scheduled_end=ends_at,
            actual_coach_id=fixed_class.default_coach_id,
        )
        db.add(session)
        db.flush()
        entry = create_schedule(
            db,
            source_type="class_session",
            source_id=session.id,
            title=fixed_class.name,
            starts_at=starts_at,
            ends_at=ends_at,
            resources=resources,
            commit=False,
        )
        session.schedule_entry_id = entry.id
        created.append(session)

    renewed_enrollments: list[Enrollment] = []
    seen: set[str] = set()
    now = utc_now()
    for renewal in enrollment_renewals:
        if renewal.enrollment_id in seen:
            raise BusinessError(422, "duplicate_enrollment_renewal", "同一学员不能重复续期")
        seen.add(renewal.enrollment_id)
        enrollment = db.get(Enrollment, renewal.enrollment_id)
        if (
            enrollment is None
            or enrollment.fixed_class_id != fixed_class.id
            or enrollment.status != "active"
        ):
            raise BusinessError(422, "invalid_enrollment_renewal", "续期学员权益不属于当前有效班级")
        if renewal.added_units <= 0:
            raise BusinessError(422, "invalid_renewal_units", "学员新增课时必须大于零")
        suggested_addition = enrollment.unit_price * renewal.added_units
        actual_addition = (
            suggested_addition
            if renewal.added_actual_amount is None
            else renewal.added_actual_amount
        )
        if actual_addition < 0:
            raise BusinessError(422, "invalid_receivable_amount", "新增应收不能为负数")
        if actual_addition != suggested_addition and not renewal.adjustment_reason:
            raise BusinessError(422, "adjustment_reason_required", "调整续期应收必须填写原因")
        before_balance = balance(db, enrollment.id)
        before_enrollment: dict[str, object] = {
            "purchased_units": enrollment.purchased_units,
            "remaining_units": before_balance,
            "suggested_receivable": str(enrollment.suggested_receivable),
            "actual_receivable": str(enrollment.actual_receivable),
        }
        db.add(
            LessonUnitLedger(
                owner_type="enrollment",
                owner_id=enrollment.id,
                change_type="renewal",
                delta=renewal.added_units,
                balance_before=before_balance,
                balance_after=before_balance + renewal.added_units,
                source_type="fixed_class_renewal",
                source_id=fixed_class.id,
                reason=renewal.adjustment_reason or "固定班续期",
                operated_by=actor_id,
                operated_at=now,
                idempotency_key=f"fixed-class-renewal:{fixed_class.id}:{version}:{enrollment.id}",
            )
        )
        enrollment.purchased_units += renewal.added_units
        enrollment.suggested_receivable += suggested_addition
        enrollment.actual_receivable += actual_addition
        receivable = receivable_for_source(db, "enrollment", enrollment.id)
        if receivable is None:
            receivable = create_receivable(
                db,
                source_type="enrollment",
                source_id=enrollment.id,
                suggested_amount=enrollment.suggested_receivable,
                actual_amount=enrollment.actual_receivable,
                adjustment_reason=renewal.adjustment_reason,
            )
        else:
            receivable.suggested_amount += suggested_addition
            receivable.actual_amount += actual_addition
        if renewal.adjustment_reason:
            receivable.adjustment_reason = renewal.adjustment_reason
        sync_receivable_status(db, receivable)
        record_audit(
            db,
            actor_id=actor_id,
            action="student.entitlement_renewed",
            entity_type="enrollment",
            entity_id=enrollment.id,
            request_id=request_id,
            before=before_enrollment,
            after={
                "purchased_units": enrollment.purchased_units,
                "remaining_units": before_balance + renewal.added_units,
                "suggested_receivable": str(enrollment.suggested_receivable),
                "actual_receivable": str(enrollment.actual_receivable),
            },
            reason=renewal.adjustment_reason or "固定班续期",
        )
        renewed_enrollments.append(enrollment)

    old_count = fixed_class.session_count
    fixed_class.session_count += additional_sessions
    record_audit(
        db,
        actor_id=actor_id,
        action="fixed_class.renewed",
        entity_type="fixed_class",
        entity_id=fixed_class.id,
        request_id=request_id,
        before={"session_count": old_count},
        after={
            "session_count": fixed_class.session_count,
            "additional_sessions": additional_sessions,
            "renewed_enrollment_ids": [item.id for item in renewed_enrollments],
        },
    )
    db.commit()
    return created, renewed_enrollments


def archive_fixed_class(
    db: Session,
    fixed_class: FixedClass,
    *,
    reason: str,
    actor_id: str,
    request_id: str,
    version: int,
) -> FixedClass:
    _require_version(fixed_class, version, "固定班")
    if fixed_class.status == "archived":
        return fixed_class
    if fixed_class.status != "active":
        raise BusinessError(409, "class_not_active", "只有启用中的固定班可以归档")
    sessions = list(
        db.scalars(
            select(ClassSession).where(
                ClassSession.fixed_class_id == fixed_class.id,
                ClassSession.status == "scheduled",
                ClassSession.scheduled_start >= utc_now(),
            )
        ).all()
    )
    for session in sessions:
        session.status = "cancelled"
        session.cancellation_reason = f"固定班归档：{reason}"
        session.replacement_decision = "waived"
        if session.schedule_entry_id:
            entry = db.get(ScheduleEntry, session.schedule_entry_id)
            if entry:
                entry.status = "cancelled"
                entry.cancellation_reason = session.cancellation_reason
                db.execute(
                    update(ScheduleAllocation)
                    .where(ScheduleAllocation.schedule_entry_id == entry.id)
                    .values(active=False)
                )
    enrollments = list(
        db.scalars(
            select(Enrollment).where(
                Enrollment.fixed_class_id == fixed_class.id,
                Enrollment.status == "active",
            )
        ).all()
    )
    for enrollment in enrollments:
        enrollment.status = "expired"
    fixed_class.status = "archived"
    record_audit(
        db,
        actor_id=actor_id,
        action="fixed_class.archived",
        entity_type="fixed_class",
        entity_id=fixed_class.id,
        request_id=request_id,
        before={"status": "active"},
        after={
            "status": "archived",
            "cancelled_session_ids": [item.id for item in sessions],
            "expired_enrollment_ids": [item.id for item in enrollments],
        },
        reason=reason,
    )
    db.commit()
    db.refresh(fixed_class)
    return fixed_class


def transfer_fixed_class_entitlement(
    db: Session,
    *,
    student_id: str,
    source_enrollment: Enrollment,
    target_class: FixedClass,
    target_units: int,
    reason: str,
    actor_id: str,
    request_id: str,
    version: int,
) -> Enrollment:
    if source_enrollment.version != version:
        raise BusinessError(409, "concurrent_change", "培训权益已经发生变化，请刷新后重试")
    if source_enrollment.student_id != student_id:
        raise BusinessError(404, "entitlement_not_found", "固定班权益不存在")
    if source_enrollment.status not in {"active", "expired"}:
        raise BusinessError(409, "entitlement_not_transferable", "该固定班权益当前不可转移")
    if target_class.status != "active":
        raise BusinessError(409, "target_class_not_active", "目标固定班不是启用状态")
    if target_class.id == source_enrollment.fixed_class_id:
        raise BusinessError(422, "same_target_class", "目标固定班不能与原班级相同")
    student = db.get(Student, student_id)
    if student is None or not student.is_active:
        raise BusinessError(422, "student_inactive", "只有系统内有效学员可以转移权益")
    if target_units <= 0:
        raise BusinessError(422, "invalid_transfer_units", "转移后的新课时数量必须大于零")
    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.fixed_class_id == target_class.id,
            Enrollment.status == "active",
        )
    )
    if existing:
        raise BusinessError(409, "target_entitlement_exists", "学员已拥有目标班级的有效权益")
    active_count = (
        db.scalar(
            select(func.count())
            .select_from(Enrollment)
            .where(
                Enrollment.fixed_class_id == target_class.id,
                Enrollment.status == "active",
            )
        )
        or 0
    )
    if active_count >= target_class.capacity:
        raise BusinessError(409, "class_full", "目标固定班已满员")
    source_balance = balance(db, source_enrollment.id)
    if source_balance <= 0:
        raise BusinessError(409, "no_units_to_transfer", "原权益没有可转移的剩余课时")
    venue = db.query(Venue).first()
    business_zone = ZoneInfo(venue.timezone if venue else "Asia/Shanghai")
    target = Enrollment(
        student_id=student_id,
        fixed_class_id=target_class.id,
        enrolled_on=utc_now().astimezone(business_zone).date(),
        purchased_units=target_units,
        unit_price=target_class.student_unit_price,
        suggested_receivable=Decimal("0.00"),
        actual_receivable=Decimal("0.00"),
        is_midterm=True,
        price_adjustment_reason="权益转入，不新增应收",
        status="active",
        acquisition_type="transfer",
        source_enrollment_id=source_enrollment.id,
        notes=reason,
    )
    db.add(target)
    db.flush()
    now = utc_now()
    db.add_all(
        [
            LessonUnitLedger(
                owner_type="enrollment",
                owner_id=source_enrollment.id,
                change_type="transfer",
                delta=-source_balance,
                balance_before=source_balance,
                balance_after=0,
                source_type="entitlement_transfer",
                source_id=target.id,
                reason=reason,
                operated_by=actor_id,
                operated_at=now,
                idempotency_key=f"entitlement-transfer-out:{source_enrollment.id}:{version}",
            ),
            LessonUnitLedger(
                owner_type="enrollment",
                owner_id=target.id,
                change_type="transfer",
                delta=target_units,
                balance_before=0,
                balance_after=target_units,
                source_type="entitlement_transfer",
                source_id=source_enrollment.id,
                reason=reason,
                operated_by=actor_id,
                operated_at=now,
                idempotency_key=f"entitlement-transfer-in:{source_enrollment.id}:{version}",
            ),
        ]
    )
    source_status_before = source_enrollment.status
    source_enrollment.status = "transferred"
    source_enrollment.transferred_to_enrollment_id = target.id
    record_audit(
        db,
        actor_id=actor_id,
        action="student.entitlement_transferred",
        entity_type="enrollment",
        entity_id=source_enrollment.id,
        request_id=request_id,
        before={
            "fixed_class_id": source_enrollment.fixed_class_id,
            "remaining_units": source_balance,
            "status": source_status_before,
        },
        after={
            "target_enrollment_id": target.id,
            "target_fixed_class_id": target_class.id,
            "target_units": target_units,
            "status": "transferred",
        },
        reason=reason,
    )
    db.commit()
    db.refresh(target)
    return target
