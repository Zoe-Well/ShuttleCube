from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.api.serialization import as_utc
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.commands.coach_rates import coach_rate, venue_business_date
from shuttlecube.application.commands.private_lessons import (
    book_private_lesson,
    complete_private_lesson,
    create_package,
    delete_private_lesson,
    reschedule_private_lesson,
)
from shuttlecube.application.queries.receivables import receivable_for_source, receivable_summary
from shuttlecube.domain.classes.enrollment_models import LessonUnitLedger
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.payroll.models import CoachFee
from shuttlecube.domain.private_lessons.models import PrivateLesson, PrivateLessonPackage
from shuttlecube.domain.scheduling.models import ScheduleAllocation
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["PrivateLessons"])


class PackageWrite(BaseModel):
    student_id: str
    bound_coach_id: str
    purchased_units: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    actual_receivable: Decimal | None = None
    valid_until: datetime | None = None
    notes: str | None = None


class LessonWrite(BaseModel):
    student_id: str
    coach_id: str
    package_id: str | None = None
    billing_mode: str
    starts_at: datetime
    ends_at: datetime
    court_ids: list[str] = Field(min_length=1)
    actual_receivable: Decimal = Field(default=Decimal("0"), ge=0)
    coach_fee: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
    warning_acknowledgements: list[str] = Field(default_factory=list)


class LessonReschedule(BaseModel):
    starts_at: datetime
    ends_at: datetime
    court_ids: list[str] = Field(min_length=1)
    coach_id: str | None = None
    warning_acknowledgements: list[str] = Field(default_factory=list)


class CancelWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class BulkCancelWrite(CancelWrite):
    ids: list[str] = Field(min_length=1)


def student_name(db: Session, student_id: str) -> str:
    item = db.get(Student, student_id)
    return item.name if item else student_id


def coach_name(db: Session, coach_id: str) -> str:
    item = db.get(CoachProfile, coach_id)
    return item.name if item else coach_id


def finance_summary(db: Session, source_type: str, source_id: str) -> dict[str, object] | None:
    receivable = receivable_for_source(db, source_type, source_id)
    if receivable is None:
        return None
    summary = receivable_summary(db, receivable)
    return {
        "receivable_id": summary.receivable_id,
        "received_amount": float(summary.received_amount),
        "outstanding_amount": float(summary.outstanding_amount),
        "refundable_amount": float(summary.refundable_amount),
        "payment_status": summary.payment_status,
    }


def hard_delete_lesson(
    db: Session,
    item: PrivateLesson,
    *,
    actor_id: str,
    request_id: str,
    reason: str,
    commit: bool = True,
) -> str:
    item_id = delete_private_lesson(db, item, commit=False)
    record_audit(
        db,
        actor_id=actor_id,
        action="private_lesson.deleted",
        entity_type="private_lesson",
        entity_id=item_id,
        request_id=request_id,
        reason=reason,
    )
    if commit:
        db.commit()
    return item_id


@router.get("/private-packages")
def packages(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    result = []
    for x in db.scalars(
        select(PrivateLessonPackage).order_by(PrivateLessonPackage.created_at.desc())
    ).all():
        receivable = receivable_for_source(db, "private_package", x.id)
        finance = receivable_summary(db, receivable) if receivable else None
        result.append(
            {
                "id": x.id,
                "student_id": x.student_id,
                "student_name": student_name(db, x.student_id),
                "bound_coach_id": x.bound_coach_id,
                "coach_name": coach_name(db, x.bound_coach_id),
                "purchased_units": x.purchased_units,
                "remaining_units": balance(db, x.id),
                "unit_price": float(x.unit_price),
                "actual_receivable": float(x.actual_receivable),
                "valid_until": as_utc(x.valid_until) if x.valid_until else None,
                "finance": (
                    {
                        "receivable_id": finance.receivable_id,
                        "received_amount": float(finance.received_amount),
                        "outstanding_amount": float(finance.outstanding_amount),
                        "payment_status": finance.payment_status,
                    }
                    if finance
                    else None
                ),
                "status": x.status,
                "version": x.version,
            }
        )
    return result


@router.get("/private-packages/{package_id}/ledger")
def package_ledger(
    package_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    if db.get(PrivateLessonPackage, package_id) is None:
        raise BusinessError(404, "package_not_found", "私教课包不存在")
    return [
        {
            "id": row.id,
            "change_type": row.change_type,
            "delta": row.delta,
            "balance_before": row.balance_before,
            "balance_after": row.balance_after,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "reason": row.reason,
            "operated_at": as_utc(row.operated_at),
        }
        for row in db.scalars(
            select(LessonUnitLedger)
            .where(
                LessonUnitLedger.owner_type == "private_package",
                LessonUnitLedger.owner_id == package_id,
                LessonUnitLedger.status == "effective",
            )
            .order_by(LessonUnitLedger.operated_at)
        ).all()
    ]


@router.post("/private-packages", status_code=201)
def post_package(
    p: PackageWrite,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    x = create_package(
        db,
        p.student_id,
        p.bound_coach_id,
        p.purchased_units,
        p.unit_price,
        p.actual_receivable,
        p.valid_until,
        user.id,
        p.notes,
    )
    return {"id": x.id, "status": x.status, "version": x.version}


def court_ids(db: Session, schedule_entry_id: str | None) -> list[str]:
    if not schedule_entry_id:
        return []
    return list(
        db.scalars(
            select(ScheduleAllocation.resource_id).where(
                ScheduleAllocation.schedule_entry_id == schedule_entry_id,
                ScheduleAllocation.resource_type == "court",
                ScheduleAllocation.active.is_(True),
            )
        ).all()
    )


@router.get("/private-lessons")
def lessons(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    items = list(
        db.scalars(
            select(PrivateLesson)
            .where(PrivateLesson.status != "cancelled")
            .order_by(PrivateLesson.starts_at.desc())
        ).all()
    )
    fees = (
        list(
            db.scalars(
                select(CoachFee).where(
                    CoachFee.source_type == "private_lesson",
                    CoachFee.source_id.in_([item.id for item in items]),
                )
            ).all()
        )
        if items
        else []
    )
    fee_by_lesson = {fee.source_id: fee for fee in fees}
    return [
        {
            "id": x.id,
            "schedule_entry_id": x.schedule_entry_id,
            "student_id": x.student_id,
            "student_name": student_name(db, x.student_id),
            "coach_id": x.coach_id,
            "coach_name": coach_name(db, x.coach_id),
            "package_id": x.package_id,
            "package_remaining_units": balance(db, x.package_id) if x.package_id else None,
            "billing_mode": x.billing_mode,
            "actual_receivable": float(x.actual_receivable),
            "finance": (
                finance_summary(db, "private_lesson", x.id)
                if x.billing_mode == "single"
                else None
            ),
            "coach_fee": float(x.coach_fee),
            "starts_at": as_utc(x.starts_at),
            "ends_at": as_utc(x.ends_at),
            "court_ids": court_ids(db, x.schedule_entry_id),
            "status": x.status,
            "generated_coach_fee": (
                {
                    "id": fee_by_lesson[x.id].id,
                    "amount": float(
                        fee_by_lesson[x.id].base_amount + fee_by_lesson[x.id].adjustment_amount
                    ),
                    "status": fee_by_lesson[x.id].status,
                    "settlement_id": fee_by_lesson[x.id].settlement_id,
                }
                if x.id in fee_by_lesson
                else None
            ),
            "version": x.version,
        }
        for x in items
    ]


@router.post("/private-lessons", status_code=201)
def post_lesson(
    p: LessonWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    values = p.model_dump()
    if values["coach_fee"] is None:
        rate = coach_rate(db, p.coach_id, "private_lesson", venue_business_date(db, p.starts_at))
        values["coach_fee"] = rate.amount if rate else Decimal("0.00")
    x = book_private_lesson(db, **values)
    return {
        "id": x.id,
        "schedule_entry_id": x.schedule_entry_id,
        "status": x.status,
        "version": x.version,
    }


@router.post("/private-lessons/bulk-delete")
@router.post("/private-lessons/bulk-cancel")
def bulk_cancel_lessons(
    p: BulkCancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    items = [db.get(PrivateLesson, item_id) for item_id in p.ids]
    if any(item is None for item in items):
        raise BusinessError(404, "lesson_not_found", "部分私教课程不存在")
    for item in items:
        if item is not None:
            hard_delete_lesson(
                db,
                item,
                actor_id=user.id,
                request_id=getattr(request.state, "request_id", "unknown"),
                reason=p.reason,
                commit=False,
            )
    db.commit()
    return {"ids": p.ids, "status": "deleted"}


@router.delete("/private-lessons/{lesson_id}", status_code=204)
def delete_lesson(
    lesson_id: str,
    p: CancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> Response:
    item = db.get(PrivateLesson, lesson_id)
    if not item:
        raise BusinessError(404, "lesson_not_found", "私教不存在")
    hard_delete_lesson(
        db,
        item,
        actor_id=user.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        reason=p.reason,
    )
    return Response(status_code=204)


@router.post("/private-lessons/{lesson_id}/complete")
def finish_lesson(
    lesson_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    item = db.get(PrivateLesson, lesson_id)
    if not item:
        raise BusinessError(404, "lesson_not_found", "私教不存在")
    item = complete_private_lesson(db, item, user.id, key)
    return {"id": item.id, "status": item.status, "version": item.version}


@router.post("/private-lessons/{lesson_id}/reschedule")
def reschedule_lesson(
    lesson_id: str,
    p: LessonReschedule,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(PrivateLesson, lesson_id)
    if not item:
        raise BusinessError(404, "lesson_not_found", "私教不存在")
    item = reschedule_private_lesson(db, item, **p.model_dump())
    return {
        "id": item.id,
        "schedule_entry_id": item.schedule_entry_id,
        "starts_at": item.starts_at,
        "ends_at": item.ends_at,
        "coach_id": item.coach_id,
        "status": item.status,
        "version": item.version,
    }


@router.post("/private-lessons/{lesson_id}/cancel")
def cancel_lesson(
    lesson_id: str,
    p: CancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(PrivateLesson, lesson_id)
    if not item:
        raise BusinessError(404, "lesson_not_found", "私教不存在")
    item_id = hard_delete_lesson(
        db,
        item,
        actor_id=user.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        reason=p.reason,
    )
    return {"id": item_id, "status": "deleted"}
