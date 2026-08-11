from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.reconciliation import (
    AffectedReference,
    InvariantCheck,
    ReconciliationImpact,
    ReconciliationRule,
    RepairEntryPoint,
    failed_result,
)
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.domain.scheduling.court import Court
from shuttlecube.domain.scheduling.models import CourtBlock, ScheduleAllocation, ScheduleEntry
from shuttlecube.domain.venue_bookings.models import VenueBooking


def _source(db: Session, entry: ScheduleEntry):
    models = {
        "class_session": ClassSession,
        "private_lesson": PrivateLesson,
        "venue_booking": VenueBooking,
        "event": TemporaryEvent,
        "court_block": CourtBlock,
    }
    model = models.get(entry.source_type)
    return db.get(model, entry.source_id) if model else None


def _source_times(source: object) -> tuple[object | None, object | None]:
    starts = getattr(source, "starts_at", getattr(source, "scheduled_start", None))
    ends = getattr(source, "ends_at", getattr(source, "scheduled_end", None))
    return starts, ends


def _should_have_active_allocations(entry: ScheduleEntry, source: object | None) -> bool:
    if entry.status in {"cancelled", "rescheduled"} or source is None:
        return False
    status = getattr(source, "status", None)
    active_states = {
        "class_session": {"scheduled", "completed"},
        "private_lesson": {"booked", "completed"},
        "venue_booking": {"booked", "completed"},
        "event": {"confirmed", "completed"},
        "court_block": {"confirmed"},
    }
    return status in active_states.get(entry.source_type, set())


def check_schedule_integrity(db: Session, scope: RequestScope):
    entries = db.scalars(
        select(ScheduleEntry).where(
            ScheduleEntry.organization_id == scope.organization_id,
            ScheduleEntry.venue_id == scope.venue_id,
        )
    ).all()
    failures = []
    for entry in entries:
        source = _source(db, entry)
        allocations = db.scalars(
            select(ScheduleAllocation).where(
                ScheduleAllocation.schedule_entry_id == entry.id
            )
        ).all()
        active = [item for item in allocations if item.active]
        source_scope_ok = source is not None and (
            getattr(source, "organization_id", None) == scope.organization_id
            and getattr(source, "venue_id", None) == scope.venue_id
        )
        starts, ends = _source_times(source) if source is not None else (None, None)
        head_ok = (
            source_scope_ok
            and entry.ends_at > entry.starts_at
            and starts == entry.starts_at
            and ends == entry.ends_at
            and (
                entry.source_type == "court_block"
                or getattr(source, "schedule_entry_id", None) == entry.id
            )
        )
        allocation_shape_ok = all(
            item.organization_id == scope.organization_id
            and item.venue_id == scope.venue_id
            and item.starts_at == entry.starts_at
            and item.ends_at == entry.ends_at
            for item in allocations
        )
        active_expected = _should_have_active_allocations(entry, source)
        active_state_ok = bool(active) if active_expected else not active
        court_ids = [item.resource_id for item in active if item.resource_type == "court"]
        valid_courts = set(
            db.scalars(
                select(Court.id).where(
                    Court.venue_id == scope.venue_id,
                    Court.id.in_(court_ids or ["__none__"]),
                )
            ).all()
        )
        resource_ok = set(court_ids) == valid_courts
        if head_ok and allocation_shape_ok and active_state_ok and resource_ok:
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="schedule.integrity",
                rule_version=1,
                subject_type="schedule_entry",
                subject_id=entry.id,
                severity="critical" if not source_scope_ok or not allocation_shape_ok else "high",
                invariants=[
                    InvariantCheck(
                        key="schedule_head",
                        expected="entry Scope, source relation and time range match the business source",
                        actual=(
                            f"source={entry.source_type}:{entry.source_id}, "
                            f"entry={entry.starts_at}/{entry.ends_at}, source={starts}/{ends}"
                        ),
                        passed=head_ok,
                    ),
                    InvariantCheck(
                        key="allocation_shape",
                        expected="allocations share entry Scope and time range",
                        actual=f"allocation ids: {[item.id for item in allocations]}",
                        passed=allocation_shape_ok,
                    ),
                    InvariantCheck(
                        key="allocation_state",
                        expected=(
                            "active source has active allocations"
                            if active_expected
                            else "inactive source has no active allocations"
                        ),
                        actual=f"active allocation ids: {[item.id for item in active]}",
                        passed=active_state_ok,
                    ),
                    InvariantCheck(
                        key="court_scope",
                        expected="active court resources belong to the current Venue",
                        actual=f"court ids: {court_ids}",
                        passed=resource_ok,
                    ),
                ],
                affected_refs=[
                    AffectedReference(kind="schedule_entry", id=entry.id, version=entry.version),
                    AffectedReference(kind=entry.source_type, id=entry.source_id),
                    *[AffectedReference(kind="schedule_allocation", id=item.id) for item in allocations],
                ],
                repair_entry_points=[
                    RepairEntryPoint(label="查看排期", route="/schedule")
                ],
                impact=ReconciliationImpact(
                    affected_schedules=1,
                    downstream_records=len(allocations),
                ),
            )
        )
    source_models = (
        ("class_session", ClassSession, {"scheduled", "completed"}),
        ("private_lesson", PrivateLesson, {"booked", "completed"}),
        ("venue_booking", VenueBooking, {"booked", "completed"}),
        ("event", TemporaryEvent, {"confirmed", "completed"}),
    )
    for source_type, model, active_states in source_models:
        sources = db.scalars(
            select(model).where(
                model.organization_id == scope.organization_id,
                model.venue_id == scope.venue_id,
                model.status.in_(active_states),
            )
        ).all()
        for source in sources:
            referenced = (
                db.scalar(
                    select(ScheduleEntry).where(
                        ScheduleEntry.id == source.schedule_entry_id,
                        ScheduleEntry.organization_id == scope.organization_id,
                        ScheduleEntry.venue_id == scope.venue_id,
                        ScheduleEntry.source_type == source_type,
                        ScheduleEntry.source_id == source.id,
                    )
                )
                if source.schedule_entry_id
                else None
            )
            if referenced is not None:
                continue
            failures.append(
                failed_result(
                    scope=scope,
                    rule_key="schedule.integrity",
                    rule_version=1,
                    subject_type=source_type,
                    subject_id=source.id,
                    severity="high",
                    invariants=[
                        InvariantCheck(
                            key="source_schedule_relation",
                            expected="active business source points to a scoped matching schedule entry",
                            actual=f"schedule_entry_id={source.schedule_entry_id}",
                            passed=False,
                        )
                    ],
                    affected_refs=[
                        AffectedReference(
                            kind=source_type, id=source.id, version=source.version
                        )
                    ],
                    repair_entry_points=[
                        RepairEntryPoint(label="查看排期", route="/schedule")
                    ],
                    impact=ReconciliationImpact(affected_schedules=1),
                )
            )
    return failures


SCHEDULE_RULES = (
    ReconciliationRule("schedule.integrity", 1, 1, check_schedule_integrity),
)
