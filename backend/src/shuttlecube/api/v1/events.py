from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.api.serialization import as_utc
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.events import (
    complete_event,
    create_event,
    delete_event,
    reschedule_event,
)
from shuttlecube.application.queries.receivables import receivable_for_source, receivable_summary
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Events"])


class EventWrite(BaseModel):
    event_type: str
    name: str
    starts_at: datetime
    ends_at: datetime
    court_ids: list[str] = Field(min_length=1)
    coach_id: str | None = None
    coach_fee: Decimal = Decimal("0")
    actual_receivable: Decimal = Decimal("0")
    expense_amount: Decimal = Decimal("0")
    track_participants: bool = False
    requires_attendance: bool = False
    participant_ids: list[str] = Field(default_factory=list)
    notes: str | None = None
    warning_acknowledgements: list[str] = Field(default_factory=list)


class EventReschedule(BaseModel):
    starts_at: datetime
    ends_at: datetime
    court_ids: list[str] = Field(min_length=1)
    warning_acknowledgements: list[str] = Field(default_factory=list)


class CancelWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class BulkCancelWrite(CancelWrite):
    ids: list[str] = Field(min_length=1)


def hard_delete_event(
    db: Session,
    item: TemporaryEvent,
    *,
    actor_id: str,
    request_id: str,
    reason: str,
    commit: bool = True,
) -> str:
    item_id = delete_event(db, item, commit=False)
    record_audit(
        db,
        actor_id=actor_id,
        action="event.deleted",
        entity_type="event",
        entity_id=item_id,
        request_id=request_id,
        reason=reason,
    )
    if commit:
        db.commit()
    return item_id


@router.get("/events")
def events(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for x in db.scalars(
        select(TemporaryEvent)
        .where(TemporaryEvent.status != "cancelled")
        .order_by(TemporaryEvent.starts_at.desc())
    ).all():
        receivable = receivable_for_source(db, "event", x.id)
        finance = receivable_summary(db, receivable) if receivable else None
        result.append(
            {
            "id": x.id,
            "schedule_entry_id": x.schedule_entry_id,
            "name": x.name,
            "event_type": x.event_type,
            "starts_at": as_utc(x.starts_at),
            "ends_at": as_utc(x.ends_at),
            "court_ids": x.court_ids_csv.split(","),
            "actual_receivable": x.actual_receivable,
            "finance": (
                {
                    "receivable_id": finance.receivable_id,
                    "outstanding_amount": finance.outstanding_amount,
                    "refundable_amount": finance.refundable_amount,
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


@router.post("/events", status_code=201)
def post_event(
    p: EventWrite,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    x = create_event(db, **p.model_dump())
    return {
        "id": x.id,
        "schedule_entry_id": x.schedule_entry_id,
        "status": x.status,
        "version": x.version,
    }


@router.post("/events/bulk-delete")
@router.post("/events/bulk-cancel")
def bulk_cancel_events(
    p: BulkCancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    items = [db.get(TemporaryEvent, item_id) for item_id in p.ids]
    if any(item is None for item in items):
        raise BusinessError(404, "event_not_found", "部分活动不存在")
    for item in items:
        if item is not None:
            hard_delete_event(
                db,
                item,
                actor_id=user.id,
                request_id=getattr(request.state, "request_id", "unknown"),
                reason=p.reason,
                commit=False,
            )
    db.commit()
    return {"ids": p.ids, "status": "deleted"}


@router.delete("/events/{event_id}", status_code=204)
def delete_temporary_event(
    event_id: str,
    p: CancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> Response:
    item = db.get(TemporaryEvent, event_id)
    if not item:
        raise BusinessError(404, "event_not_found", "活动不存在")
    hard_delete_event(
        db,
        item,
        actor_id=user.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        reason=p.reason,
    )
    return Response(status_code=204)


@router.post("/events/{event_id}/complete")
def finish_event(
    event_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(TemporaryEvent, event_id)
    if not item:
        raise BusinessError(404, "event_not_found", "活动不存在")
    item = complete_event(db, item)
    return {"id": item.id, "status": item.status, "version": item.version}


@router.post("/events/{event_id}/reschedule")
def post_reschedule_event(
    event_id: str,
    p: EventReschedule,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(TemporaryEvent, event_id)
    if not item:
        raise BusinessError(404, "event_not_found", "活动不存在")
    item = reschedule_event(db, item, **p.model_dump())
    return {
        "id": item.id,
        "schedule_entry_id": item.schedule_entry_id,
        "starts_at": as_utc(item.starts_at),
        "ends_at": as_utc(item.ends_at),
        "court_ids": item.court_ids_csv.split(","),
        "status": item.status,
        "version": item.version,
    }


@router.post("/events/{event_id}/cancel")
def post_cancel_event(
    event_id: str,
    p: CancelWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    item = db.get(TemporaryEvent, event_id)
    if not item:
        raise BusinessError(404, "event_not_found", "活动不存在")
    item_id = hard_delete_event(
        db,
        item,
        actor_id=user.id,
        request_id=getattr(request.state, "request_id", "unknown"),
        reason=p.reason,
    )
    return {"id": item_id, "status": "deleted"}
