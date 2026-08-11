from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.schedule import create_schedule
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.scheduling.conflicts import Resource
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry


def _session_resources(
    db: Session,
    session: ClassSession,
    scope: RequestScope | None = None,
) -> list[Resource]:
    if not session.schedule_entry_id:
        raise BusinessError(409, "schedule_missing", "课程排期不存在")
    statement = select(ScheduleAllocation).where(
        ScheduleAllocation.schedule_entry_id == session.schedule_entry_id
    )
    if scope is not None:
        statement = statement.where(
            ScheduleAllocation.organization_id == scope.organization_id,
            ScheduleAllocation.venue_id == scope.venue_id,
        )
    rows = list(db.scalars(statement).all())
    if not rows:
        raise BusinessError(409, "schedule_resources_missing", "课程排期没有可复用的资源")
    return [Resource(row.resource_type, row.resource_id) for row in rows]


def _release_entry(db: Session, entry: ScheduleEntry, status: str, reason: str) -> None:
    entry.status = status
    entry.cancellation_reason = reason
    db.execute(
        update(ScheduleAllocation)
        .where(ScheduleAllocation.schedule_entry_id == entry.id)
        .values(active=False)
    )


def _create_replacement(
    db: Session,
    session: ClassSession,
    replacement_start: datetime,
    replacement_end: datetime,
    resources: list[Resource],
    scope: RequestScope | None = None,
) -> ClassSession:
    fixed_class = db.get(FixedClass, session.fixed_class_id)
    if fixed_class is None:
        raise BusinessError(404, "class_not_found", "固定班不存在")
    next_sequence = (
        db.scalar(
            select(func.coalesce(func.max(ClassSession.sequence_number), 0)).where(
                ClassSession.fixed_class_id == session.fixed_class_id
            )
        )
        or 0
    ) + 1
    replacement = ClassSession(
        organization_id=scope.organization_id if scope else session.organization_id,
        venue_id=scope.venue_id if scope else session.venue_id,
        fixed_class_id=session.fixed_class_id,
        sequence_number=next_sequence,
        scheduled_start=replacement_start,
        scheduled_end=replacement_end,
        actual_coach_id=session.actual_coach_id,
        replacement_for_session_id=session.id,
    )
    db.add(replacement)
    db.flush()
    entry = create_schedule(
        db,
        source_type="class_session",
        source_id=replacement.id,
        title=f"{fixed_class.name}（补排）",
        starts_at=replacement_start,
        ends_at=replacement_end,
        resources=resources,
        scope=scope,
        commit=False,
    )
    replacement.schedule_entry_id = entry.id
    session.replacement_decision = "scheduled"
    return replacement


def cancel_and_replace(
    db: Session,
    session: ClassSession,
    *,
    reason: str,
    replacement_decision: str,
    replacement_start: datetime | None,
    replacement_end: datetime | None,
    actor_id: str,
    request_id: str,
    version: int,
) -> ClassSession | None:
    if session.version != version:
        raise BusinessError(409, "concurrent_change", "课程已经发生变化，请刷新后重试")
    if session.status != "scheduled":
        raise BusinessError(409, "invalid_session_state", "课程当前不可取消")
    if replacement_decision not in {"pending", "scheduled", "waived"}:
        raise BusinessError(422, "invalid_replacement_decision", "请选择稍后补排、立即补排或无需补排")
    if replacement_decision == "scheduled" and not (replacement_start and replacement_end):
        raise BusinessError(422, "replacement_time_required", "立即补排时必须填写整班补排时间")
    if replacement_decision != "scheduled" and (replacement_start or replacement_end):
        raise BusinessError(422, "unexpected_replacement_time", "当前补排选择不应填写整班补排时间")

    resources = _session_resources(db, session)
    entry = db.get(ScheduleEntry, session.schedule_entry_id)
    if entry is None:
        raise BusinessError(409, "schedule_missing", "课程排期不存在")
    before: dict[str, object] = {
        "status": session.status,
        "scheduled_start": session.scheduled_start.isoformat(),
        "scheduled_end": session.scheduled_end.isoformat(),
    }
    _release_entry(db, entry, "cancelled", reason)
    session.status = "cancelled"
    session.cancellation_reason = reason
    session.replacement_decision = replacement_decision
    replacement = None
    if replacement_decision == "scheduled":
        assert replacement_start is not None and replacement_end is not None
        replacement = _create_replacement(
            db, session, replacement_start, replacement_end, resources
        )
    record_audit(
        db,
        actor_id=actor_id,
        action="class_session.cancelled",
        entity_type="class_session",
        entity_id=session.id,
        request_id=request_id,
        before=before,
        after={
            "status": "cancelled",
            "replacement_decision": session.replacement_decision,
            "replacement_session_id": replacement.id if replacement else None,
        },
        reason=reason,
    )
    db.commit()
    return replacement


def schedule_cancelled_session_replacement(
    db: Session,
    session: ClassSession,
    *,
    replacement_start: datetime,
    replacement_end: datetime,
    actor_id: str,
    request_id: str,
    version: int,
    scope: RequestScope | None = None,
    commit: bool = True,
) -> ClassSession:
    if scope is not None and (
        session.organization_id != scope.organization_id or session.venue_id != scope.venue_id
    ):
        raise BusinessError(404, "scope_not_found", "课程不存在")
    if session.version != version:
        raise BusinessError(409, "concurrent_change", "课程已经发生变化，请刷新后重试")
    if session.status != "cancelled" or session.replacement_decision != "pending":
        raise BusinessError(409, "replacement_not_pending", "该课程当前没有待安排的补排计划")
    resources = _session_resources(db, session, scope)
    replacement = _create_replacement(
        db, session, replacement_start, replacement_end, resources, scope
    )
    record_audit(
        db,
        actor_id=actor_id,
        action="class_session.replacement_scheduled",
        entity_type="class_session",
        entity_id=session.id,
        request_id=request_id,
        after={
            "replacement_decision": "scheduled",
            "replacement_session_id": replacement.id,
            "scheduled_start": replacement_start.isoformat(),
            "scheduled_end": replacement_end.isoformat(),
        },
        organization_id=scope.organization_id if scope else session.organization_id,
        venue_id=scope.venue_id if scope else session.venue_id,
    )
    if commit:
        db.commit()
    return replacement
