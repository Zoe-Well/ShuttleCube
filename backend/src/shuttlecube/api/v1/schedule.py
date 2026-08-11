from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Self

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.api.serialization import as_utc
from shuttlecube.application.audit.scheduling import record_schedule_change
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.events import delete_event
from shuttlecube.application.commands.private_lessons import delete_private_lesson
from shuttlecube.application.commands.schedule import (
    create_schedule,
    delete_schedule_source,
    replace_schedule,
)
from shuttlecube.application.commands.venue_bookings import delete_booking
from shuttlecube.application.queries.schedule import list_schedule
from shuttlecube.application.queries.schedule_display import schedule_display_titles
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.domain.scheduling.conflicts import Resource, find_conflicts
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.scheduling.models import CourtBlock, ScheduleAllocation, ScheduleEntry
from shuttlecube.domain.scheduling.policies import collect_schedule_warnings
from shuttlecube.domain.venue_bookings.models import VenueBooking
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Schedule"])


class ResourceRef(BaseModel):
    type: str = Field(pattern="^(court|coach|student)$")
    id: str


class ScheduleWrite(BaseModel):
    source_type: str
    source_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    resources: list[ResourceRef] = Field(min_length=1)
    notes: str | None = None
    warning_acknowledgements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class CancelInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class BulkDeleteInput(CancelInput):
    ids: list[str] = Field(min_length=1)


class RescheduleWrite(ScheduleWrite):
    reason: str = Field(min_length=1, max_length=500)


def entry_view(
    entry: ScheduleEntry,
    resources: Sequence[ScheduleAllocation] | None = None,
    *,
    title: str | None = None,
) -> dict[str, object]:
    resources = resources or []
    return {
        "id": entry.id,
        "source_type": entry.source_type,
        "source_id": entry.source_id,
        "title": title or entry.title,
        "starts_at": as_utc(entry.starts_at),
        "ends_at": as_utc(entry.ends_at),
        "status": entry.status,
        "resources": [{"type": r.resource_type, "id": r.resource_id} for r in resources],
        "version": entry.version,
    }


DELETABLE_SOURCE_TYPES = {"manual", "court_block", "private_lesson", "venue_booking", "event"}
BULK_DELETABLE_SOURCE_TYPES = {"manual", "private_lesson", "venue_booking", "event"}


def ensure_schedule_deletable(db: Session, entry: ScheduleEntry, *, bulk: bool = False) -> None:
    supported_types = BULK_DELETABLE_SOURCE_TYPES if bulk else DELETABLE_SOURCE_TYPES
    if entry.source_type not in supported_types:
        detail = (
            "固定班课次不能在统一排期中批量删除"
            if entry.source_type == "class_session"
            else "此类排期不能批量删除，请单条处理"
        )
        raise BusinessError(409, "schedule_not_bulk_deletable", detail)
    if entry.status == "completed":
        raise BusinessError(409, "completed_schedule_cannot_delete", "已完成排期不能删除")
    if entry.source_type == "private_lesson":
        lesson = db.get(PrivateLesson, entry.source_id)
        if lesson and lesson.status == "completed":
            raise BusinessError(409, "completed_lesson_cannot_delete", "已完成私教不可删除")
    if entry.source_type == "event":
        event = db.get(TemporaryEvent, entry.source_id)
        if event and event.status == "completed":
            raise BusinessError(409, "completed_event_cannot_delete", "已完成活动不可删除")


def hard_delete_schedule(
    db: Session,
    entry: ScheduleEntry,
    *,
    actor_id: str,
    request_id: str,
    reason: str,
    commit: bool = True,
) -> str:
    ensure_schedule_deletable(db, entry)
    entry_id = entry.id
    source_type = entry.source_type
    source_id = entry.source_id
    if source_type == "private_lesson":
        lesson = db.get(PrivateLesson, source_id)
        if lesson:
            delete_private_lesson(db, lesson, commit=False)
        else:
            delete_schedule_source(db, source_type, source_id, commit=False)
    elif source_type == "venue_booking":
        booking = db.get(VenueBooking, source_id)
        if booking:
            delete_booking(db, booking, commit=False)
        else:
            delete_schedule_source(db, source_type, source_id, commit=False)
    elif source_type == "event":
        event = db.get(TemporaryEvent, source_id)
        if event:
            delete_event(db, event, commit=False)
        else:
            delete_schedule_source(db, source_type, source_id, commit=False)
    elif source_type == "court_block":
        block = db.get(CourtBlock, source_id)
        if block:
            db.delete(block)
            db.flush()
        delete_schedule_source(db, source_type, source_id, commit=False)
    else:
        delete_schedule_source(db, source_type, source_id, commit=False)
    record_audit(
        db,
        actor_id=actor_id,
        action="schedule.deleted",
        entity_type="schedule_source",
        entity_id=source_id,
        request_id=request_id,
        reason=reason,
    )
    if commit:
        db.commit()
    return entry_id


@router.post("/schedule/bulk-delete")
def bulk_delete_schedule(
    payload: BulkDeleteInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    requested_ids = list(dict.fromkeys(payload.ids))
    entries = list(db.scalars(select(ScheduleEntry).where(ScheduleEntry.id.in_(requested_ids))))
    if len(entries) != len(requested_ids):
        raise BusinessError(404, "schedule_not_found", "部分排期不存在，请刷新后重试")
    for entry in entries:
        ensure_schedule_deletable(db, entry, bulk=True)

    processed_sources: set[tuple[str, str]] = set()
    for entry in entries:
        source = (entry.source_type, entry.source_id)
        if source in processed_sources:
            continue
        processed_sources.add(source)
        hard_delete_schedule(
            db,
            entry,
            actor_id=user.id,
            request_id=getattr(request.state, "request_id", "unknown"),
            reason=payload.reason,
            commit=False,
        )
    db.commit()
    return {"ids": requested_ids, "status": "deleted"}


@router.get("/schedule")
def get_schedule(
    from_: datetime,
    to: datetime,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    rows = list_schedule(db, from_, to)
    titles = schedule_display_titles(db, [entry for entry, _ in rows])
    return [entry_view(entry, resources, title=titles[entry.id]) for entry, resources in rows]


@router.post("/schedule/conflicts:check")
def check_conflicts(
    payload: ScheduleWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> dict[str, object]:
    conflicts = find_conflicts(
        db, [Resource(r.type, r.id) for r in payload.resources], payload.starts_at, payload.ends_at
    )
    warnings = collect_schedule_warnings(
        payload.starts_at, payload.ends_at, venue=db.query(Venue).first()
    )
    return {
        "has_conflicts": bool(conflicts),
        "can_save": not conflicts,
        "conflicts": [c.__dict__ for c in conflicts],
        "warnings": [{"code": warning.code, "message": warning.message} for warning in warnings],
    }


@router.post("/schedule", status_code=201)
def post_schedule(
    payload: ScheduleWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    entry = create_schedule(
        db,
        **payload.model_dump(exclude={"resources", "warning_acknowledgements"}),
        resources=[Resource(r.type, r.id) for r in payload.resources],
        acknowledged_warnings=payload.warning_acknowledgements,
    )
    record_schedule_change(
        db,
        actor_id=user.id,
        action="schedule.created",
        entry=entry,
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    db.commit()
    return entry_view(entry)


@router.delete("/schedule/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: str,
    payload: CancelInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    if_match: int | None = Header(default=None, alias="If-Match-Version"),
) -> Response:
    entry = db.get(ScheduleEntry, schedule_id)
    if not entry:
        raise BusinessError(404, "schedule_not_found", "排期不存在")
    if if_match is not None and entry.version != if_match:
        raise BusinessError(409, "concurrent_change", "排期已变化")
    hard_delete_schedule(
        db,
        entry,
        actor_id=user.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        reason=payload.reason,
    )
    return Response(status_code=204)


@router.post("/schedule/{schedule_id}/cancel")
def post_cancel(
    schedule_id: str,
    payload: CancelInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    if_match: int | None = Header(default=None, alias="If-Match-Version"),
) -> dict[str, object]:
    entry = db.get(ScheduleEntry, schedule_id)
    if not entry:
        raise BusinessError(404, "schedule_not_found", "排期不存在")
    if if_match is not None and entry.version != if_match:
        raise BusinessError(409, "concurrent_change", "排期已变化")
    entry_id = hard_delete_schedule(
        db,
        actor_id=user.id,
        entry=entry,
        request_id=getattr(request.state, "request_id", "unknown"),
        reason=payload.reason,
    )
    return {"id": entry_id, "status": "deleted"}


@router.post("/schedule/{schedule_id}/reschedule", status_code=201)
def post_reschedule(
    schedule_id: str,
    payload: RescheduleWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    if_match: int | None = Header(default=None, alias="If-Match-Version"),
) -> dict[str, object]:
    entry = db.get(ScheduleEntry, schedule_id)
    if not entry:
        raise BusinessError(404, "schedule_not_found", "排期不存在")
    if if_match is not None and entry.version != if_match:
        raise BusinessError(409, "concurrent_change", "排期已变化")
    before: dict[str, object] = {
        "status": entry.status,
        "starts_at": entry.starts_at.isoformat(),
        "ends_at": entry.ends_at.isoformat(),
    }
    replacement = replace_schedule(
        db,
        entry,
        reason=payload.reason,
        title=payload.title,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        resources=[Resource(r.type, r.id) for r in payload.resources],
        notes=payload.notes,
        acknowledged_warnings=payload.warning_acknowledgements,
    )
    record_schedule_change(
        db,
        actor_id=user.id,
        action="schedule.rescheduled",
        entry=replacement,
        request_id=getattr(request.state, "request_id", "unknown"),
        before=before,
        reason=payload.reason,
    )
    db.commit()
    return entry_view(replacement)
