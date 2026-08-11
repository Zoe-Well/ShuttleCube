from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.operations.models import OperationCase, OperationRun
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.operations.schemas import OperationsPolicyConfig
from shuttlecube.domain.scheduling.conflicts import Resource, find_conflicts
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation

CANDIDATE_WORKFLOW_KEY = "operations.replacement_candidates.v1"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _original_resources(
    db: Session,
    *,
    scope: RequestScope,
    session: ClassSession,
) -> tuple[list[str], list[str]]:
    allocations = db.scalars(
        select(ScheduleAllocation).where(
            ScheduleAllocation.organization_id == scope.organization_id,
            ScheduleAllocation.venue_id == scope.venue_id,
            ScheduleAllocation.schedule_entry_id == session.schedule_entry_id,
        )
    ).all()
    coach_ids = sorted(
        {item.resource_id for item in allocations if item.resource_type == "coach"}
        or {session.actual_coach_id}
    )
    court_ids = sorted(
        {item.resource_id for item in allocations if item.resource_type == "court"}
    )
    return coach_ids, court_ids


def generate_replacement_candidates(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    policy: OperationsPolicy,
    window_start: datetime,
    window_end: datetime,
    expected_case_version: int,
    max_candidates: int = 20,
    now: datetime | None = None,
) -> tuple[OperationRun, dict[str, object]]:
    current = _aware(now or datetime.now(UTC))
    if case.organization_id != scope.organization_id or case.venue_id != scope.venue_id:
        raise BusinessError(404, "scope_not_found", "运营案件不存在")
    if case.case_type != "class_replacement_pending":
        raise BusinessError(422, "replacement_not_supported", "该案件不是待补排课程")
    if case.version != expected_case_version:
        raise BusinessError(409, "concurrent_change", "案件已发生变化")
    session = db.scalar(
        select(ClassSession).where(
            ClassSession.id == case.subject_id,
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
        )
    )
    if session is None:
        raise BusinessError(404, "scope_not_found", "取消课程不存在")
    if session.status != "cancelled" or session.replacement_decision != "pending":
        raise BusinessError(409, "replacement_not_pending", "课程已不再等待补排")
    fixed_class = db.scalar(
        select(FixedClass).where(
            FixedClass.id == session.fixed_class_id,
            FixedClass.organization_id == scope.organization_id,
            FixedClass.venue_id == scope.venue_id,
        )
    )
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if fixed_class is None or venue is None:
        raise BusinessError(409, "replacement_context_missing", "补排所需业务资料不完整")
    config = OperationsPolicyConfig.model_validate(policy.config)
    starts = _aware(window_start)
    ends = _aware(window_end)
    if starts < current or ends <= starts:
        raise BusinessError(422, "invalid_candidate_window", "候选窗口必须是未来有效时段")
    if ends - starts > timedelta(days=config.replacement.window_days):
        raise BusinessError(422, "candidate_window_too_large", "候选窗口超过当前运营规则")
    if max_candidates < 1 or max_candidates > 50:
        raise BusinessError(422, "invalid_candidate_limit", "候选数量必须为 1 到 50")
    duration = _aware(session.scheduled_end) - _aware(session.scheduled_start)
    if duration.total_seconds() <= 0 or duration.total_seconds() % 3600 != 0:
        raise BusinessError(409, "unsupported_session_duration", "当前课程时长不能生成整点补排候选")
    coach_ids, court_ids = _original_resources(db, scope=scope, session=session)
    if len(court_ids) != fixed_class.required_court_count or not coach_ids:
        raise BusinessError(409, "original_resources_missing", "原课程资源不完整")
    resources = [
        *(Resource("coach", item) for item in coach_ids),
        *(Resource("court", item) for item in court_ids),
    ]
    zone = ZoneInfo(venue.timezone)
    local_cursor = starts.astimezone(zone).replace(minute=0, second=0, microsecond=0)
    if local_cursor < starts.astimezone(zone):
        local_cursor += timedelta(hours=1)
    local_end = ends.astimezone(zone)
    original_start = _aware(session.scheduled_start)
    plans: list[dict[str, object]] = []
    rejected = {"outside_business_hours": 0, "resource_conflict": 0}
    checked_at = current
    while local_cursor < local_end and len(plans) < max_candidates:
        candidate_end_local = local_cursor + duration
        weekend = local_cursor.weekday() >= 5
        opening = venue.weekend_open_time if weekend else venue.weekday_open_time
        closing = venue.weekend_close_time if weekend else venue.weekday_close_time
        if (
            candidate_end_local.date() != local_cursor.date()
            or local_cursor.time().replace(tzinfo=None) < opening
            or candidate_end_local.time().replace(tzinfo=None) > closing
        ):
            rejected["outside_business_hours"] += 1
            local_cursor += timedelta(hours=1)
            continue
        candidate_start = local_cursor.astimezone(UTC)
        candidate_end = candidate_end_local.astimezone(UTC)
        if candidate_end > ends or find_conflicts(
            db,
            resources,
            candidate_start,
            candidate_end,
        ):
            rejected["resource_conflict"] += 1
            local_cursor += timedelta(hours=1)
            continue
        plan_body = {
            "session_id": session.id,
            "session_version": session.version,
            "resource_policy_version": policy.policy_version,
            "starts_at": candidate_start.isoformat(),
            "ends_at": candidate_end.isoformat(),
            "coach_ids": coach_ids,
            "court_ids": court_ids,
            "required_court_count": fixed_class.required_court_count,
        }
        plans.append(
            {
                "resource_plan_id": str(uuid4()),
                **plan_body,
                "conflict_checked_at": checked_at.isoformat(),
                "evidence_hash": canonical_hash(plan_body),
                "expires_at": min(
                    current + timedelta(minutes=config.runtime.approval_expiry_minutes),
                    ends,
                ).isoformat(),
                "student_availability_verified": False,
                "ranking_explanation": (
                    f"与原课程相隔 {abs((candidate_start - original_start).days)} 天；"
                    "仅复用原教练和原场地，学生可用性需人工确认。"
                ),
            }
        )
        local_cursor += timedelta(hours=1)
    plans.sort(
        key=lambda item: (
            abs(datetime.fromisoformat(str(item["starts_at"])) - original_start),
            str(item["starts_at"]),
        )
    )
    response_body = {
        "schema_version": "1",
        "generated_at": current.isoformat(),
        "policy_version": policy.policy_version,
        "candidates": plans,
        "caveats": ["学生可用性未由系统验证；选择方案前必须完成人工协调。"],
        "rejected_counts_by_reason": rejected,
    }
    response_body["evidence_hash"] = canonical_hash(response_body)
    run = OperationRun(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        case_id=case.id,
        parent_run_id=case.current_run_id,
        run_type="case_analysis",
        trigger_type="manual",
        workflow_key=CANDIDATE_WORKFLOW_KEY,
        workflow_version=1,
        policy_key=policy.policy_key,
        policy_version=policy.policy_version,
        prompt_version=None,
        toolset_version=1,
        model_profile=None,
        input_refs=[
            {"kind": "class_session", "id": session.id, "version": session.version},
            {"kind": "operation_case", "id": case.id, "version": case.version},
        ],
        input_hash=canonical_hash(
            {
                "case_id": case.id,
                "window_start": starts.isoformat(),
                "window_end": ends.isoformat(),
                "policy_version": policy.policy_version,
            }
        ),
        checkpoint={
            "workflow_step": "candidates_complete",
            "completed_steps": ["original_resources", "business_hours", "conflicts"],
            "state": response_body,
        },
        state="succeeded",
        max_steps=1,
        max_model_calls=0,
        max_tool_calls=1,
        max_write_calls=0,
        deadline_at=current + timedelta(minutes=1),
        started_at=current,
        finished_at=current,
    )
    db.add(run)
    db.flush()
    case.current_run_id = run.id
    return run, response_body


def find_frozen_resource_plan(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    resource_plan_id: str,
    now: datetime | None = None,
) -> tuple[OperationRun, dict[str, object]]:
    current = _aware(now or datetime.now(UTC))
    runs = db.scalars(
        select(OperationRun)
        .where(
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
            OperationRun.case_id == case.id,
            OperationRun.workflow_key == CANDIDATE_WORKFLOW_KEY,
            OperationRun.state == "succeeded",
        )
        .order_by(OperationRun.finished_at.desc())
    ).all()
    for run in runs:
        state = (run.checkpoint or {}).get("state", {})
        candidates = state.get("candidates", []) if isinstance(state, dict) else []
        for plan in candidates if isinstance(candidates, list) else []:
            if not isinstance(plan, dict) or plan.get("resource_plan_id") != resource_plan_id:
                continue
            expires_at = datetime.fromisoformat(str(plan["expires_at"]))
            if _aware(expires_at) <= current:
                raise BusinessError(409, "resource_plan_expired", "候选方案已过期")
            return run, dict(plan)
    raise BusinessError(404, "resource_plan_not_found", "候选方案不存在")

