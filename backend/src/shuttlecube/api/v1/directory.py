from datetime import date, time
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope, current_session, request_scope, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.coach_rates import (
    coach_rate,
    set_coach_rate,
    venue_business_date,
)
from shuttlecube.application.queries.student_entitlements import student_entitlement_summary
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.coach import CoachProfile, CoachRate
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter()


class DirectoryWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    notes: str | None = None
    fixed_class_fee: Decimal | None = Field(default=None, ge=0)
    private_lesson_fee: Decimal | None = Field(default=None, ge=0)
    rate_effective_from: date | None = None


class DirectoryUpdate(DirectoryWrite):
    version: int


class CourtWrite(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class VenueWrite(BaseModel):
    name: str
    timezone: str = "Asia/Shanghai"
    weekday_open_time: time
    weekday_close_time: time
    weekend_open_time: time
    weekend_close_time: time
    version: int


class StatusWrite(BaseModel):
    is_active: bool
    reason: str = Field(min_length=1, max_length=500)
    version: int


def view(item: object) -> dict[str, object]:
    fields = ["id", "name", "code", "phone", "notes", "is_active", "version"]
    return {key: getattr(item, key) for key in fields if hasattr(item, key)}


def coach_view(db: Session, item: CoachProfile) -> dict[str, object]:
    fixed_class_rate = coach_rate(db, item.id, "fixed_class")
    private_lesson_rate = coach_rate(db, item.id, "private_lesson")
    return {
        "id": item.id,
        "name": item.name,
        "phone": item.phone,
        "notes": item.specialties,
        "is_active": item.is_active,
        "fixed_class_fee": float(fixed_class_rate.amount) if fixed_class_rate else 0.0,
        "private_lesson_fee": float(private_lesson_rate.amount) if private_lesson_rate else 0.0,
        "fixed_class_fee_effective_from": (
            fixed_class_rate.effective_from.isoformat() if fixed_class_rate else None
        ),
        "private_lesson_fee_effective_from": (
            private_lesson_rate.effective_from.isoformat() if private_lesson_rate else None
        ),
        "version": item.version,
    }


def apply_coach_rates(db: Session, coach_id: str, payload: DirectoryWrite) -> None:
    effective_from = payload.rate_effective_from or venue_business_date(db)
    if payload.fixed_class_fee is not None:
        set_coach_rate(
            db,
            coach_id=coach_id,
            business_type="fixed_class",
            amount=payload.fixed_class_fee,
            effective_from=effective_from,
        )
    if payload.private_lesson_fee is not None:
        set_coach_rate(
            db,
            coach_id=coach_id,
            business_type="private_lesson",
            amount=payload.private_lesson_fee,
            effective_from=effective_from,
        )


@router.get("/courts", tags=["Directory"])
def courts(
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[RequestScope, Depends(request_scope)],
) -> list[dict[str, object]]:
    return [
        view(x)
        for x in db.query(Court)
        .filter(Court.venue_id == scope.venue_id)
        .order_by(Court.code)
        .all()
    ]


@router.post("/courts", tags=["Directory"], status_code=201)
def create_court(
    payload: CourtWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[RequestScope, Depends(request_scope)],
) -> dict[str, object]:
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if not venue:
        raise BusinessError(422, "venue_required", "请先配置场馆")
    item = Court(venue_id=venue.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return view(item)


@router.patch("/courts/{court_id}/status", tags=["Directory"])
def update_court_status(
    court_id: str,
    payload: StatusWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[RequestScope, Depends(request_scope)],
) -> dict[str, object]:
    item = db.scalar(
        select(Court).where(Court.id == court_id, Court.venue_id == scope.venue_id)
    )
    if not item:
        raise BusinessError(404, "court_not_found", "场地不存在")
    if item.version != payload.version:
        raise BusinessError(409, "concurrent_change", "场地资料已变化")
    before: dict[str, object] = {"is_active": item.is_active}
    item.is_active = payload.is_active
    record_audit(
        db,
        actor_id=user.id,
        action="court.status_changed",
        entity_type="court",
        entity_id=item.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        before=before,
        after={"is_active": item.is_active},
        reason=payload.reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    db.refresh(item)
    return view(item)


@router.get("/coaches", tags=["Directory"])
def coaches(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    return [coach_view(db, x) for x in db.query(CoachProfile).order_by(CoachProfile.name).all()]


@router.get("/coaches/{coach_id}/rates", tags=["Directory"])
def coach_rates(
    coach_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    if db.get(CoachProfile, coach_id) is None:
        raise BusinessError(404, "coach_not_found", "教练不存在")
    return [
        {
            "id": item.id,
            "business_type": item.business_type,
            "amount": float(item.amount),
            "effective_from": item.effective_from,
            "effective_to": item.effective_to,
            "version": item.version,
        }
        for item in db.query(CoachRate)
        .filter(CoachRate.coach_id == coach_id)
        .order_by(CoachRate.business_type, CoachRate.effective_from.desc())
        .all()
    ]


@router.post("/coaches", tags=["Directory"], status_code=201)
def create_coach(
    payload: DirectoryWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = CoachProfile(name=payload.name, phone=payload.phone, specialties=payload.notes)
    db.add(item)
    db.flush()
    apply_coach_rates(db, item.id, payload)
    record_audit(
        db,
        actor_id=user.id,
        action="coach.created",
        entity_type="coach",
        entity_id=item.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        after=coach_view(db, item),
    )
    db.commit()
    db.refresh(item)
    return coach_view(db, item)


@router.put("/coaches/{coach_id}", tags=["Directory"])
def update_coach(
    coach_id: str,
    payload: DirectoryUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(CoachProfile, coach_id)
    if not item:
        raise BusinessError(404, "coach_not_found", "教练不存在")
    if item.version != payload.version:
        raise BusinessError(409, "concurrent_change", "教练资料已变化")
    before = coach_view(db, item)
    item.name = payload.name
    item.phone = payload.phone
    item.specialties = payload.notes
    apply_coach_rates(db, item.id, payload)
    record_audit(
        db,
        actor_id=user.id,
        action="coach.updated",
        entity_type="coach",
        entity_id=item.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        before=before,
        after=coach_view(db, item),
    )
    db.commit()
    db.refresh(item)
    return coach_view(db, item)


@router.patch("/coaches/{coach_id}/status", tags=["Directory"])
def update_coach_status(
    coach_id: str,
    payload: StatusWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(CoachProfile, coach_id)
    if not item:
        raise BusinessError(404, "coach_not_found", "教练不存在")
    if item.version != payload.version:
        raise BusinessError(409, "concurrent_change", "教练资料已变化")
    before: dict[str, object] = {"is_active": item.is_active}
    item.is_active = payload.is_active
    record_audit(
        db,
        actor_id=user.id,
        action="coach.status_changed",
        entity_type="coach",
        entity_id=item.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        before=before,
        after={"is_active": item.is_active},
        reason=payload.reason,
    )
    db.commit()
    db.refresh(item)
    return coach_view(db, item)


@router.get("/students", tags=["Customers"])
def students(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
    q: str | None = None,
) -> dict[str, object]:
    query = db.query(Student)
    if q:
        query = query.filter(or_(Student.name.contains(q), Student.phone.contains(q)))
    items = []
    for student in query.order_by(Student.name).all():
        item = view(student)
        item["entitlement_summary"] = student_entitlement_summary(db, student.id)
        items.append(item)
    return {"items": items, "next_cursor": None}


@router.post("/students", tags=["Customers"], status_code=201)
def create_student(
    payload: DirectoryWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = Student(name=payload.name, phone=payload.phone, notes=payload.notes)
    db.add(item)
    db.commit()
    db.refresh(item)
    return view(item)


@router.get("/venue/settings", tags=["Directory"])
def get_venue(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> dict[str, object]:
    item = db.query(Venue).first()
    if not item:
        raise BusinessError(404, "venue_not_found", "场馆尚未配置")
    return {
        k: getattr(item, k)
        for k in [
            "id",
            "name",
            "timezone",
            "weekday_open_time",
            "weekday_close_time",
            "weekend_open_time",
            "weekend_close_time",
            "version",
        ]
    }


@router.put("/venue/settings", tags=["Directory"])
def update_venue(
    payload: VenueWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    if payload.weekday_close_time <= payload.weekday_open_time:
        raise BusinessError(422, "invalid_business_hours", "工作日关门时间必须晚于开门时间")
    if payload.weekend_close_time <= payload.weekend_open_time:
        raise BusinessError(422, "invalid_business_hours", "周末关门时间必须晚于开门时间")
    item = db.query(Venue).first()
    created = item is None
    if not item:
        item = Venue()
        db.add(item)
    elif item.version != payload.version:
        raise BusinessError(409, "concurrent_change", "场馆设置已变化")
    before: dict[str, object] | None = (
        None
        if created
        else {
            "weekday_open_time": item.weekday_open_time.isoformat(),
            "weekday_close_time": item.weekday_close_time.isoformat(),
            "weekend_open_time": item.weekend_open_time.isoformat(),
            "weekend_close_time": item.weekend_close_time.isoformat(),
        }
    )
    for k, v in payload.model_dump(exclude={"version"}).items():
        setattr(item, k, v)
    record_audit(
        db,
        actor_id=user.id,
        action="venue.business_hours_updated",
        entity_type="venue",
        entity_id=item.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        before=before,
        after={
            "weekday_open_time": item.weekday_open_time.isoformat(),
            "weekday_close_time": item.weekday_close_time.isoformat(),
            "weekend_open_time": item.weekend_open_time.isoformat(),
            "weekend_close_time": item.weekend_close_time.isoformat(),
        },
    )
    db.commit()
    db.refresh(item)
    return {"id": item.id, **payload.model_dump(exclude={"version"}), "version": item.version}
