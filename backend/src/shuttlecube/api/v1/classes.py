from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.api.serialization import as_utc
from shuttlecube.application.commands.attendance import (
    AttendanceDecision,
    balance,
    finalize_attendance,
)
from shuttlecube.application.commands.class_cancellation import (
    cancel_and_replace,
    schedule_cancelled_session_replacement,
)
from shuttlecube.application.commands.classes import create_fixed_class, enroll_student
from shuttlecube.application.commands.coach_rates import coach_rate
from shuttlecube.application.commands.fixed_class_management import (
    EnrollmentRenewal,
    archive_fixed_class,
    renew_fixed_class,
    reschedule_class_session,
    update_class_capacity,
)
from shuttlecube.application.queries.dashboard import EndingWithinDays, get_ending_classes
from shuttlecube.application.queries.receivables import ReceivableSummary, receivable_summary
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import (
    AttendanceRecord,
    Enrollment,
    LessonUnitLedger,
)
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.payroll.models import CoachFee
from shuttlecube.domain.scheduling.court import Court
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Classes"])


class FixedClassWrite(BaseModel):
    name: str
    class_type: str = "training"
    age_or_level: str | None = None
    start_date: date
    default_start_time: time
    duration_minutes: int = Field(ge=60, multiple_of=60)
    session_count: int = Field(gt=0)
    capacity: int = Field(gt=0)
    default_coach_id: str
    court_ids: list[str] = Field(min_length=1)
    required_court_count: int = Field(default=1, gt=0)
    student_unit_price: Decimal = Field(ge=0)
    coach_fee_per_session: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_hourly_schedule(self) -> FixedClassWrite:
        if self.default_start_time.minute or self.default_start_time.second:
            raise ValueError("每周上课时间必须选择整点")
        return self


class EnrollmentWrite(BaseModel):
    student_id: str
    enrolled_on: date
    purchased_units: int | None = Field(default=None, gt=0)
    actual_receivable: Decimal | None = Field(default=None, ge=0)
    adjustment_reason: str | None = None


class DecisionWrite(BaseModel):
    student_id: str
    enrollment_id: str
    status: str = Field(default="present", pattern="^(present|leave|absent|unprocessed)$")
    deduct_units: int = Field(default=1, ge=0, le=1)
    note: str | None = None


class AttendanceWrite(BaseModel):
    decisions: list[DecisionWrite] = Field(min_length=1)


class CancelReplaceWrite(BaseModel):
    reason: str = Field(min_length=1)
    replacement_decision: str = Field(pattern="^(pending|scheduled|waived)$")
    replacement_start: datetime | None = None
    replacement_end: datetime | None = None
    version: int


class SessionRescheduleWrite(BaseModel):
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=1, max_length=500)
    version: int


class ReplacementWrite(BaseModel):
    starts_at: datetime
    ends_at: datetime
    version: int


class CapacityWrite(BaseModel):
    capacity: int = Field(gt=0)
    version: int


class EnrollmentRenewalWrite(BaseModel):
    enrollment_id: str
    added_units: int = Field(gt=0)
    added_actual_amount: Decimal | None = Field(default=None, ge=0)
    adjustment_reason: str | None = None


class ClassRenewalWrite(BaseModel):
    additional_sessions: int = Field(gt=0)
    enrollment_renewals: list[EnrollmentRenewalWrite] = Field(default_factory=list)
    version: int


class ArchiveClassWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    version: int


def class_view(item: FixedClass) -> dict[str, object]:
    return {
        "id": item.id,
        "name": item.name,
        "class_type": item.class_type,
        "start_date": item.start_date,
        "default_start_time": item.default_start_time,
        "duration_minutes": item.duration_minutes,
        "session_count": item.session_count,
        "capacity": item.capacity,
        "default_coach_id": item.default_coach_id,
        "student_unit_price": item.student_unit_price,
        "coach_fee_per_session": item.coach_fee_per_session,
        "status": item.status,
        "version": item.version,
    }


@router.get("/classes")
def list_classes(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
    business_date: date | None = None,
    ending_within_days: EndingWithinDays | None = None,
) -> list[dict[str, object]]:
    if ending_within_days is not None:
        return [
            {
                **class_view(item.fixed_class),
                "last_scheduled_end": item.last_scheduled_end,
                "remaining_scheduled_sessions": item.remaining_scheduled_sessions,
            }
            for item in get_ending_classes(
                db, business_date or date.today(), ending_within_days=ending_within_days
            )
        ]
    return [
        class_view(x)
        for x in db.scalars(select(FixedClass).order_by(FixedClass.start_date.desc())).all()
    ]


@router.post("/classes", status_code=201)
def post_class(
    payload: FixedClassWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    coach = db.get(CoachProfile, payload.default_coach_id)
    if coach is None or not coach.is_active:
        raise BusinessError(422, "invalid_class_coach", "请选择有效的系统教练")
    if len(set(payload.court_ids)) != len(payload.court_ids):
        raise BusinessError(422, "duplicate_class_court", "固定班场地不能重复选择")
    courts = list(db.scalars(select(Court).where(Court.id.in_(payload.court_ids))).all())
    if len(courts) != len(payload.court_ids) or any(not court.is_active for court in courts):
        raise BusinessError(422, "invalid_class_court", "请选择有效的系统场地")
    values = payload.model_dump(exclude={"court_ids"})
    if values["coach_fee_per_session"] is None:
        rate = coach_rate(db, payload.default_coach_id, "fixed_class", payload.start_date)
        values["coach_fee_per_session"] = rate.amount if rate else Decimal("0.00")
    item = FixedClass(**values)
    item, sessions = create_fixed_class(db, item, payload.court_ids)
    return {"class_id": item.id, "session_ids": [s.id for s in sessions], "version": item.version}


@router.get("/classes/{class_id}")
def get_class(
    class_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> dict[str, object]:
    item = db.get(FixedClass, class_id)
    if not item:
        raise BusinessError(404, "class_not_found", "班级不存在")
    sessions = db.scalars(
        select(ClassSession)
        .where(ClassSession.fixed_class_id == class_id)
        .order_by(ClassSession.sequence_number)
    ).all()
    sessions_by_id = {session.id: session for session in sessions}
    session_ids = [session.id for session in sessions]
    attendance_records = (
        list(
            db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.class_session_id.in_(session_ids)
                )
            ).all()
        )
        if session_ids
        else []
    )
    attendance_by_session: dict[str, list[AttendanceRecord]] = {}
    for record in attendance_records:
        attendance_by_session.setdefault(record.class_session_id, []).append(record)
    coach_fees = (
        list(
            db.scalars(
                select(CoachFee).where(
                    CoachFee.source_type == "class_session",
                    CoachFee.source_id.in_(session_ids),
                )
            ).all()
        )
        if session_ids
        else []
    )
    coach_fee_by_session = {fee.source_id: fee for fee in coach_fees}
    enrollments = db.scalars(select(Enrollment).where(Enrollment.fixed_class_id == class_id)).all()
    enrollment_ids = [enrollment.id for enrollment in enrollments]
    receivables = (
        db.scalars(
            select(Receivable).where(
                Receivable.source_type == "enrollment",
                Receivable.source_id.in_(enrollment_ids),
            )
        ).all()
        if enrollment_ids
        else []
    )
    receivable_by_enrollment = {receivable.source_id: receivable for receivable in receivables}
    finance_by_enrollment: dict[str, ReceivableSummary] = {
        enrollment_id: receivable_summary(db, receivable)
        for enrollment_id, receivable in receivable_by_enrollment.items()
    }
    student_ids = {
        enrollment.student_id for enrollment in enrollments
    } | {record.student_id for record in attendance_records}
    students = (
        db.scalars(select(Student).where(Student.id.in_(student_ids))).all() if student_ids else []
    )
    student_names = {student.id: student.name for student in students}
    class_finance = {
        "actual_amount": float(sum(
            (summary.actual_amount for summary in finance_by_enrollment.values()), Decimal("0.00")
        )),
        "received_amount": float(sum(
            (summary.received_amount for summary in finance_by_enrollment.values()),
            Decimal("0.00"),
        )),
        "refunded_amount": float(sum(
            (summary.refunded_amount for summary in finance_by_enrollment.values()),
            Decimal("0.00"),
        )),
        "net_received": float(sum(
            (summary.net_received for summary in finance_by_enrollment.values()), Decimal("0.00")
        )),
        "outstanding_amount": float(sum(
            (summary.outstanding_amount for summary in finance_by_enrollment.values()),
            Decimal("0.00"),
        )),
    }

    def enrollment_view(enrollment: Enrollment) -> dict[str, object]:
        finance = finance_by_enrollment.get(enrollment.id)
        return {
            "id": enrollment.id,
            "student_id": enrollment.student_id,
            "student_name": student_names.get(enrollment.student_id, "未知学员"),
            "purchased_units": enrollment.purchased_units,
            "remaining_units": balance(db, enrollment.id),
            "unit_price": enrollment.unit_price,
            "actual_receivable": enrollment.actual_receivable,
            "status": enrollment.status,
            "acquisition_type": enrollment.acquisition_type,
            "finance": (
                {
                    "receivable_id": finance.receivable_id,
                    "actual_amount": float(finance.actual_amount),
                    "received_amount": float(finance.received_amount),
                    "refunded_amount": float(finance.refunded_amount),
                    "net_received": float(finance.net_received),
                    "outstanding_amount": float(finance.outstanding_amount),
                    "payment_status": finance.payment_status,
                }
                if finance
                else None
            ),
        }

    return {
        **class_view(item),
        "finance": class_finance,
        "sessions": [
            {
                "id": s.id,
                "sequence_number": s.sequence_number,
                "scheduled_start": as_utc(s.scheduled_start),
                "scheduled_end": as_utc(s.scheduled_end),
                "status": s.status,
                "version": s.version,
                "replacement_for_session_id": s.replacement_for_session_id,
                "replacement_for_sequence": (
                    sessions_by_id[s.replacement_for_session_id].sequence_number
                    if s.replacement_for_session_id in sessions_by_id
                    else None
                ),
                "replacement_decision": s.replacement_decision,
                "attendance_finalized_at": (
                    as_utc(s.attendance_finalized_at) if s.attendance_finalized_at else None
                ),
                "attendance": [
                    {
                        "id": record.id,
                        "student_id": record.student_id,
                        "student_name": student_names.get(record.student_id, "未知学员"),
                        "status": record.status,
                        "deduct_units": record.deduct_units,
                        "grants_makeup": record.grants_makeup,
                        "decision_note": record.decision_note,
                    }
                    for record in attendance_by_session.get(s.id, [])
                ],
                "coach_fee": (
                    {
                        "id": coach_fee_by_session[s.id].id,
                        "base_amount": float(coach_fee_by_session[s.id].base_amount),
                        "adjustment_amount": float(
                            coach_fee_by_session[s.id].adjustment_amount
                        ),
                        "amount": float(
                            coach_fee_by_session[s.id].base_amount
                            + coach_fee_by_session[s.id].adjustment_amount
                        ),
                        "status": coach_fee_by_session[s.id].status,
                        "settlement_id": coach_fee_by_session[s.id].settlement_id,
                    }
                    if s.id in coach_fee_by_session
                    else None
                ),
            }
            for s in sessions
        ],
        "enrollments": [enrollment_view(enrollment) for enrollment in enrollments],
    }


@router.post("/classes/{class_id}/enrollments", status_code=201)
def post_enrollment(
    class_id: str,
    payload: EnrollmentWrite,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(FixedClass, class_id)
    if not item:
        raise BusinessError(404, "class_not_found", "班级不存在")
    if item.status != "active":
        raise BusinessError(409, "class_not_active", "只有启用中的固定班可以绑定培训权益")
    enrollment = enroll_student(
        db,
        student_id=payload.student_id,
        fixed_class=item,
        enrolled_on=payload.enrolled_on,
        purchased_units=payload.purchased_units,
        actual_receivable=payload.actual_receivable,
        reason=payload.adjustment_reason,
        actor_id=user.id,
    )
    return {
        "id": enrollment.id,
        "suggested_receivable": enrollment.suggested_receivable,
        "actual_receivable": enrollment.actual_receivable,
        "purchased_units": enrollment.purchased_units,
        "status": enrollment.status,
        "version": enrollment.version,
    }


@router.get("/enrollments/{enrollment_id}/ledger")
def get_ledger(
    enrollment_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    rows = db.scalars(
        select(LessonUnitLedger)
        .where(LessonUnitLedger.owner_id == enrollment_id)
        .order_by(LessonUnitLedger.operated_at)
    ).all()
    return [
        {
            "id": x.id,
            "change_type": x.change_type,
            "delta": x.delta,
            "balance_before": x.balance_before,
            "balance_after": x.balance_after,
            "reason": x.reason,
            "operated_at": x.operated_at,
        }
        for x in rows
    ]


@router.post("/class-sessions/{session_id}/attendance:finalize")
def post_attendance(
    session_id: str,
    payload: AttendanceWrite,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    item = db.get(ClassSession, session_id)
    if not item:
        raise BusinessError(404, "session_not_found", "课程不存在")
    records = finalize_attendance(
        db,
        item,
        [AttendanceDecision(**x.model_dump()) for x in payload.decisions],
        user.id,
        idempotency_key,
    )
    return {
        "session_id": item.id,
        "attendance_ids": [x.id for x in records],
        "status": item.status,
        "version": item.version,
    }


@router.post("/class-sessions/{session_id}/cancel-and-replace")
def post_cancel_replace(
    session_id: str,
    payload: CancelReplaceWrite,
    db: Annotated[Session, Depends(get_db)],
    request: Request,
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(ClassSession, session_id)
    if not item:
        raise BusinessError(404, "session_not_found", "课程不存在")
    replacement = cancel_and_replace(
        db,
        item,
        reason=payload.reason,
        replacement_decision=payload.replacement_decision,
        replacement_start=payload.replacement_start,
        replacement_end=payload.replacement_end,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        version=payload.version,
    )
    return {
        "cancelled_session_id": item.id,
        "replacement_session_id": replacement.id if replacement else None,
    }


@router.post("/class-sessions/{session_id}/reschedule")
def post_class_session_reschedule(
    session_id: str,
    payload: SessionRescheduleWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(ClassSession, session_id)
    if item is None:
        raise BusinessError(404, "session_not_found", "课程不存在")
    item = reschedule_class_session(
        db,
        item,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        reason=payload.reason,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        version=payload.version,
    )
    return {
        "id": item.id,
        "scheduled_start": as_utc(item.scheduled_start),
        "scheduled_end": as_utc(item.scheduled_end),
        "version": item.version,
    }


@router.post("/class-sessions/{session_id}/replacement", status_code=201)
def post_class_session_replacement(
    session_id: str,
    payload: ReplacementWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(ClassSession, session_id)
    if item is None:
        raise BusinessError(404, "session_not_found", "课程不存在")
    replacement = schedule_cancelled_session_replacement(
        db,
        item,
        replacement_start=payload.starts_at,
        replacement_end=payload.ends_at,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        version=payload.version,
    )
    return {"id": replacement.id, "version": replacement.version}


@router.patch("/classes/{class_id}/capacity")
def patch_class_capacity(
    class_id: str,
    payload: CapacityWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(FixedClass, class_id)
    if item is None:
        raise BusinessError(404, "class_not_found", "固定班不存在")
    item = update_class_capacity(
        db,
        item,
        capacity=payload.capacity,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        version=payload.version,
    )
    return {"id": item.id, "capacity": item.capacity, "version": item.version}


@router.post("/classes/{class_id}/renew")
def post_class_renewal(
    class_id: str,
    payload: ClassRenewalWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(FixedClass, class_id)
    if item is None:
        raise BusinessError(404, "class_not_found", "固定班不存在")
    sessions, enrollments = renew_fixed_class(
        db,
        item,
        additional_sessions=payload.additional_sessions,
        enrollment_renewals=[EnrollmentRenewal(**row.model_dump()) for row in payload.enrollment_renewals],
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        version=payload.version,
    )
    return {
        "id": item.id,
        "session_count": item.session_count,
        "created_session_ids": [session.id for session in sessions],
        "renewed_enrollment_ids": [enrollment.id for enrollment in enrollments],
        "version": item.version,
    }


@router.post("/classes/{class_id}/archive")
def post_class_archive(
    class_id: str,
    payload: ArchiveClassWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(FixedClass, class_id)
    if item is None:
        raise BusinessError(404, "class_not_found", "固定班不存在")
    item = archive_fixed_class(
        db,
        item,
        reason=payload.reason,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        version=payload.version,
    )
    return {"id": item.id, "status": item.status, "version": item.version}
