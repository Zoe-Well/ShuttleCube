from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.classes import enroll_student
from shuttlecube.application.commands.fixed_class_management import (
    transfer_fixed_class_entitlement as transfer_fixed_class_entitlement_command,
)
from shuttlecube.application.commands.private_lessons import create_package
from shuttlecube.application.commands.student_entitlements import terminate_student_entitlement
from shuttlecube.application.queries.student_entitlements import get_student_entitlements
from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["StudentEntitlements"])


class FixedClassEntitlementWrite(BaseModel):
    fixed_class_id: str
    enrolled_on: date
    purchased_units: int | None = Field(default=None, gt=0)
    actual_receivable: Decimal | None = Field(default=None, ge=0)
    adjustment_reason: str | None = None


class PrivatePackageEntitlementWrite(BaseModel):
    coach_id: str
    purchased_units: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    actual_receivable: Decimal | None = Field(default=None, ge=0)
    valid_until: datetime | None = None
    notes: str | None = None


class TerminateEntitlementWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    version: int


class TransferFixedClassEntitlementWrite(BaseModel):
    target_fixed_class_id: str
    target_units: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)
    version: int


def require_student(db: Session, student_id: str) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise BusinessError(404, "student_not_found", "学员不存在")
    return student


@router.get("/students/{student_id}/entitlements")
def student_entitlements(
    student_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> dict[str, object]:
    require_student(db, student_id)
    return get_student_entitlements(db, student_id)


@router.post("/students/{student_id}/entitlements/fixed-classes", status_code=201)
def add_fixed_class_entitlement(
    student_id: str,
    payload: FixedClassEntitlementWrite,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    require_student(db, student_id)
    fixed_class = db.get(FixedClass, payload.fixed_class_id)
    if fixed_class is None:
        raise BusinessError(404, "class_not_found", "固定班不存在")
    if fixed_class.status != "active":
        raise BusinessError(409, "class_not_active", "只有启用中的固定班可以绑定培训权益")
    item = enroll_student(
        db,
        student_id=student_id,
        fixed_class=fixed_class,
        enrolled_on=payload.enrolled_on,
        purchased_units=payload.purchased_units,
        actual_receivable=payload.actual_receivable,
        reason=payload.adjustment_reason,
        actor_id=user.id,
    )
    return {"id": item.id, "status": item.status, "version": item.version}


@router.post("/students/{student_id}/entitlements/private-packages", status_code=201)
def add_private_package_entitlement(
    student_id: str,
    payload: PrivatePackageEntitlementWrite,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    require_student(db, student_id)
    item = create_package(
        db,
        student_id,
        payload.coach_id,
        payload.purchased_units,
        payload.unit_price,
        payload.actual_receivable,
        payload.valid_until,
        user.id,
        payload.notes,
    )
    return {"id": item.id, "status": item.status, "version": item.version}


@router.post("/students/{student_id}/entitlements/{entitlement_type}/{entitlement_id}/terminate")
def terminate_entitlement(
    student_id: str,
    entitlement_type: str,
    entitlement_id: str,
    payload: TerminateEntitlementWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = terminate_student_entitlement(
        db,
        student_id=student_id,
        entitlement_type=entitlement_type,
        entitlement_id=entitlement_id,
        version=payload.version,
        reason=payload.reason,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    return {"id": item.id, "status": item.status, "version": item.version}


@router.post(
    "/students/{student_id}/entitlements/fixed-classes/{enrollment_id}/transfer",
    status_code=201,
)
def transfer_fixed_class_entitlement(
    student_id: str,
    enrollment_id: str,
    payload: TransferFixedClassEntitlementWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    source = db.get(Enrollment, enrollment_id)
    if source is None:
        raise BusinessError(404, "entitlement_not_found", "固定班权益不存在")
    target_class = db.get(FixedClass, payload.target_fixed_class_id)
    if target_class is None:
        raise BusinessError(404, "class_not_found", "目标固定班不存在")
    target = transfer_fixed_class_entitlement_command(
        db,
        student_id=student_id,
        source_enrollment=source,
        target_class=target_class,
        target_units=payload.target_units,
        reason=payload.reason,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        version=payload.version,
    )
    return {"id": target.id, "status": target.status, "version": target.version}
