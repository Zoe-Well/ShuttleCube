from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.coach_fees import ensure_event_fee
from shuttlecube.application.commands.receivables import create_receivable
from shuttlecube.application.commands.schedule import (
    cancel_schedule,
    create_schedule,
    delete_schedule_entries,
    delete_schedule_source,
)
from shuttlecube.domain.events.models import EventParticipant, TemporaryEvent
from shuttlecube.domain.scheduling.conflicts import Resource
from shuttlecube.domain.scheduling.models import ScheduleEntry


def create_event(
    db: Session,
    *,
    event_type: str,
    name: str,
    starts_at: datetime,
    ends_at: datetime,
    court_ids: list[str],
    coach_id: str | None,
    coach_fee: Decimal,
    actual_receivable: Decimal,
    expense_amount: Decimal,
    track_participants: bool,
    requires_attendance: bool,
    participant_ids: list[str],
    notes: str | None,
    warning_acknowledgements: list[str] | None = None,
) -> TemporaryEvent:
    item = TemporaryEvent(
        event_type=event_type,
        name=name,
        starts_at=starts_at,
        ends_at=ends_at,
        court_ids_csv=",".join(court_ids),
        coach_id=coach_id,
        coach_fee=coach_fee,
        actual_receivable=actual_receivable,
        suggested_receivable=actual_receivable,
        expense_amount=expense_amount,
        track_participants=track_participants,
        requires_attendance=requires_attendance,
        notes=notes,
    )
    db.add(item)
    db.flush()
    resources = [
        *[Resource("court", x) for x in court_ids],
        *([Resource("coach", coach_id)] if coach_id else []),
        *([Resource("student", x) for x in participant_ids] if track_participants else []),
    ]
    entry = create_schedule(
        db,
        source_type="event",
        source_id=item.id,
        title=name,
        starts_at=starts_at,
        ends_at=ends_at,
        resources=resources,
        acknowledged_warnings=warning_acknowledgements,
        commit=False,
    )
    item.schedule_entry_id = entry.id
    if track_participants:
        db.add_all(
            [
                EventParticipant(
                    event_id=item.id,
                    student_id=x,
                    attendance_status="unprocessed" if requires_attendance else None,
                )
                for x in participant_ids
            ]
        )
    create_receivable(
        db,
        source_type="event",
        source_id=item.id,
        suggested_amount=item.suggested_receivable,
        actual_amount=item.actual_receivable,
    )
    db.commit()
    return item


def complete_event(db: Session, item: TemporaryEvent) -> TemporaryEvent:
    if item.status != "confirmed":
        raise BusinessError(409, "invalid_event_state", "当前活动不可完成")
    item.status = "completed"
    ensure_event_fee(db, item)
    db.commit()
    return item


def reschedule_event(
    db: Session,
    item: TemporaryEvent,
    *,
    starts_at: datetime,
    ends_at: datetime,
    court_ids: list[str],
    warning_acknowledgements: list[str] | None = None,
) -> TemporaryEvent:
    if item.status != "confirmed" or not item.schedule_entry_id:
        raise BusinessError(409, "invalid_event_state", "当前活动不可修改")
    old_entry = db.get(ScheduleEntry, item.schedule_entry_id)
    if old_entry is None:
        raise BusinessError(409, "schedule_missing", "活动排期不存在")
    cancel_schedule(db, old_entry, "修改临时活动", commit=False)
    resources = [
        *[Resource("court", court_id) for court_id in court_ids],
        *([Resource("coach", item.coach_id)] if item.coach_id else []),
    ]
    if item.track_participants:
        participants = db.scalars(
            select(EventParticipant).where(EventParticipant.event_id == item.id)
        ).all()
        resources.extend(Resource("student", row.student_id) for row in participants)
    replacement = create_schedule(
        db,
        source_type="event",
        source_id=item.id,
        title=item.name,
        starts_at=starts_at,
        ends_at=ends_at,
        resources=resources,
        acknowledged_warnings=warning_acknowledgements,
        commit=False,
    )
    delete_schedule_entries(db, [old_entry], commit=False)
    item.starts_at = starts_at
    item.ends_at = ends_at
    item.court_ids_csv = ",".join(court_ids)
    item.schedule_entry_id = replacement.id
    db.commit()
    return item


def cancel_event(
    db: Session, item: TemporaryEvent, reason: str, *, commit: bool = True
) -> TemporaryEvent:
    if item.status != "confirmed":
        raise BusinessError(409, "invalid_event_state", "当前活动不可取消")
    if item.schedule_entry_id:
        entry = db.get(ScheduleEntry, item.schedule_entry_id)
        if entry:
            cancel_schedule(db, entry, reason, commit=False)
    item.status = "cancelled"
    item.notes = f"{item.notes or ''}\n取消原因：{reason}".strip()
    if commit:
        db.commit()
    return item


def delete_event(db: Session, item: TemporaryEvent, *, commit: bool = True) -> str:
    if item.status == "completed":
        raise BusinessError(409, "completed_event_cannot_delete", "已完成活动不可删除")
    item_id = item.id
    db.execute(delete(EventParticipant).where(EventParticipant.event_id == item_id))
    db.delete(item)
    db.flush()
    delete_schedule_source(db, "event", item_id, commit=False)
    if commit:
        db.commit()
    return item_id
