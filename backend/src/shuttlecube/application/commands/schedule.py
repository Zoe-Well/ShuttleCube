from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.scheduling.conflicts import Resource, ensure_available
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry
from shuttlecube.domain.scheduling.policies import (
    OUTSIDE_BUSINESS_HOURS,
    collect_schedule_warnings,
    require_schedule_warning_acknowledgements,
    validate_business_hours,
    validate_schedule_range,
)


def create_schedule(
    db: Session,
    *,
    source_type: str,
    source_id: str,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    resources: list[Resource],
    notes: str | None = None,
    status: str = "confirmed",
    acknowledged_warnings: list[str] | None = None,
    scope: RequestScope | None = None,
    commit: bool = True,
) -> ScheduleEntry:
    validate_schedule_range(starts_at, ends_at)
    venue = (
        db.scalar(
            select(Venue).where(
                Venue.id == scope.venue_id,
                Venue.organization_id == scope.organization_id,
            )
        )
        if scope is not None
        else db.query(Venue).first()
    )
    warnings = collect_schedule_warnings(starts_at, ends_at, venue=venue)
    if acknowledged_warnings is None:
        # Internal scheduling callers retain the historical hard-hours policy.
        if any(warning.code == OUTSIDE_BUSINESS_HOURS for warning in warnings):
            validate_business_hours(starts_at, ends_at)
    else:
        require_schedule_warning_acknowledgements(warnings, set(acknowledged_warnings))
    ensure_available(db, resources, starts_at, ends_at)
    entry = ScheduleEntry(
        organization_id=scope.organization_id if scope else None,
        venue_id=scope.venue_id if scope else None,
        source_type=source_type,
        source_id=source_id,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        notes=notes,
    )
    db.add(entry)
    db.flush()
    db.add_all(
        [
            ScheduleAllocation(
                organization_id=scope.organization_id if scope else None,
                venue_id=scope.venue_id if scope else None,
                schedule_entry_id=entry.id,
                resource_type=r.type,
                resource_id=r.id,
                starts_at=starts_at,
                ends_at=ends_at,
            )
            for r in resources
        ]
    )
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def cancel_schedule(
    db: Session, entry: ScheduleEntry, reason: str, *, commit: bool = True
) -> ScheduleEntry:
    entry.status = "cancelled"
    entry.cancellation_reason = reason
    db.execute(
        update(ScheduleAllocation)
        .where(ScheduleAllocation.schedule_entry_id == entry.id)
        .values(active=False)
    )
    if commit:
        db.commit()
    return entry


def delete_schedule_entries(
    db: Session, entries: list[ScheduleEntry], *, commit: bool = True
) -> list[str]:
    """Permanently remove schedule rows, allocations, and content-bearing audit history."""
    entry_ids = [entry.id for entry in entries]
    if not entry_ids:
        return []
    db.execute(
        update(ScheduleEntry)
        .where(ScheduleEntry.original_entry_id.in_(entry_ids))
        .values(original_entry_id=None)
    )
    db.execute(
        delete(AuditLog).where(
            AuditLog.entity_type == "schedule_entry", AuditLog.entity_id.in_(entry_ids)
        )
    )
    db.execute(
        delete(ScheduleAllocation).where(ScheduleAllocation.schedule_entry_id.in_(entry_ids))
    )
    db.execute(delete(ScheduleEntry).where(ScheduleEntry.id.in_(entry_ids)))
    if commit:
        db.commit()
    return entry_ids


def delete_schedule_source(
    db: Session, source_type: str, source_id: str, *, commit: bool = True
) -> list[str]:
    entries = list(
        db.scalars(
            select(ScheduleEntry).where(
                ScheduleEntry.source_type == source_type, ScheduleEntry.source_id == source_id
            )
        ).all()
    )
    return delete_schedule_entries(db, entries, commit=commit)


def replace_schedule(
    db: Session,
    entry: ScheduleEntry,
    *,
    reason: str,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    resources: list[Resource],
    notes: str | None = None,
    acknowledged_warnings: list[str] | None = None,
) -> ScheduleEntry:
    """Atomically preserve the old entry, release it, and create its replacement."""
    cancel_schedule(db, entry, reason, commit=False)
    replacement = create_schedule(
        db,
        source_type=entry.source_type,
        source_id=entry.source_id,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        resources=resources,
        notes=notes,
        acknowledged_warnings=acknowledged_warnings,
        commit=False,
    )
    delete_schedule_entries(db, [entry], commit=False)
    db.commit()
    db.refresh(replacement)
    return replacement
