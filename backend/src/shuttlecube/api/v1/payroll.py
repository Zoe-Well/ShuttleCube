from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope, require_csrf
from shuttlecube.api.errors import ConcurrentChange
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.coach_fees import adjust_coach_fee
from shuttlecube.application.commands.payroll import (
    create_payroll_settlement,
    void_payroll_settlement,
)
from shuttlecube.application.operations.access import (
    require_scope_capability,
    scoped_object_or_404,
)
from shuttlecube.application.queries.payroll import list_coach_fees, list_settlements
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Payroll"])


class CoachFeeAdjustWrite(BaseModel):
    adjustment_amount: Decimal
    reason: str = Field(min_length=1)
    version: int


class PayrollSettlementWrite(BaseModel):
    coach_id: str
    period_month: date
    actual_amount: Decimal = Field(ge=0)
    adjustment_reason: str | None = None
    paid_at: datetime


class VoidWrite(BaseModel):
    reason: str = Field(min_length=1)


def fee_source(db: Session, item: CoachFee) -> tuple[str, str, str | None]:
    if item.source_type == "class_session":
        session = db.get(ClassSession, item.source_id)
        fixed_class = db.get(FixedClass, session.fixed_class_id) if session else None
        if session and fixed_class:
            return (
                f"固定班-{fixed_class.name}-第 {session.sequence_number} 节",
                f"/classes/{fixed_class.id}",
                session.status,
            )
    if item.source_type == "private_lesson":
        lesson = db.get(PrivateLesson, item.source_id)
        student = db.get(Student, lesson.student_id) if lesson else None
        if lesson:
            return (
                f"私教-{student.name if student else '未知学员'}",
                f"/private-lessons?lesson_id={lesson.id}",
                lesson.status,
            )
    if item.source_type == "event":
        event = db.get(TemporaryEvent, item.source_id)
        if event:
            return f"活动-{event.name}", "/events", event.status
    return item.source_type, "", None


def fee_dict(db: Session, item: CoachFee) -> dict[str, object]:
    business_name, business_path, source_status = fee_source(db, item)
    coach = db.get(CoachProfile, item.coach_id)
    return {
        "id": item.id,
        "coach_id": item.coach_id,
        "coach_name": coach.name if coach else item.coach_id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "occurred_at": item.occurred_at.isoformat(),
        "base_amount": float(item.base_amount),
        "adjustment_amount": float(item.adjustment_amount),
        "amount": float(item.base_amount + item.adjustment_amount),
        "adjustment_reason": item.adjustment_reason,
        "status": item.status,
        "settlement_id": item.settlement_id,
        "business_name": business_name,
        "business_path": business_path,
        "source_status": source_status,
        "version": item.version,
    }


def settlement_dict(
    db: Session, item: PayrollSettlement, scope: RequestScope
) -> dict[str, object]:
    return {
        "id": item.id,
        "coach_id": item.coach_id,
        "period_start": item.period_start,
        "period_end": item.period_end,
        "calculated_amount": float(item.calculated_amount),
        "adjustment_amount": float(item.adjustment_amount),
        "actual_amount": float(item.actual_amount),
        "adjustment_reason": item.adjustment_reason,
        "paid_at": item.paid_at,
        "status": item.status,
        "expense_id": item.expense_id,
        "fee_ids": list(
            db.scalars(
                select(CoachFee.id).where(
                    CoachFee.organization_id == scope.organization_id,
                    CoachFee.venue_id == scope.venue_id,
                    CoachFee.settlement_id == item.id,
                )
            ).all()
        ),
        "version": item.version,
    }


@router.get("/coach-fees")
def get_coach_fees(
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.payroll.read"))
    ],
    coach_id: str | None = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    status: str | None = None,
) -> dict[str, object]:
    result = list_coach_fees(
        db,
        scope=scope,
        coach_id=coach_id,
        period_start=from_,
        period_end=to,
        status=status,
    )
    return {
        "coach_id": coach_id,
        "calculated_amount": float(result.calculated_amount),
        "items": [fee_dict(db, item) for item in result.items],
    }


@router.get("/coach-fees/{fee_id}")
def get_coach_fee(
    fee_id: str,
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.payroll.read"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, CoachFee, fee_id, scope)
    return fee_dict(db, item)


@router.patch("/coach-fees/{fee_id}")
def patch_coach_fee(
    fee_id: str,
    payload: CoachFeeAdjustWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.payroll.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, CoachFee, fee_id, scope)
    if item.version != payload.version:
        raise ConcurrentChange()
    before = fee_dict(db, item)
    adjust_coach_fee(
        db,
        item,
        adjustment_amount=payload.adjustment_amount,
        reason=payload.reason,
        commit=False,
    )
    record_audit(
        db,
        actor_id=user.id,
        action="coach_fee.adjusted",
        entity_type="coach_fee",
        entity_id=item.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        before=before,
        after=fee_dict(db, item),
        reason=payload.reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    db.refresh(item)
    return fee_dict(db, item)


@router.get("/payroll-settlements")
def get_settlements(
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.payroll.read"))
    ],
    coach_id: str | None = None,
    period_month: date | None = None,
) -> list[dict[str, object]]:
    return [
        settlement_dict(db, item, scope)
        for item in list_settlements(db, scope, coach_id, period_month)
    ]


@router.post("/payroll-settlements", status_code=201)
def post_settlement(
    payload: PayrollSettlementWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.payroll.manage"))
    ],
) -> dict[str, object]:
    item = create_payroll_settlement(
        db,
        **payload.model_dump(),
        actor_id=user.id,
        idempotency_key=idempotency_key,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        scope=scope,
    )
    return settlement_dict(db, item, scope)


@router.get("/payroll-settlements/{settlement_id}")
def get_settlement(
    settlement_id: str,
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.payroll.read"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, PayrollSettlement, settlement_id, scope)
    return settlement_dict(db, item, scope)


@router.post("/payroll-settlements/{settlement_id}/void")
def post_void_settlement(
    settlement_id: str,
    payload: VoidWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.payroll.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, PayrollSettlement, settlement_id, scope)
    void_payroll_settlement(
        db,
        item,
        reason=payload.reason,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    return settlement_dict(db, item, scope)
