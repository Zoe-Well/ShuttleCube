from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope, request_scope, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.operations.access import (
    project_followup_context,
    project_report_payload,
    require_scope_capability,
)
from shuttlecube.application.operations.activities import (
    FollowupActivityInput,
    activity_payload,
)
from shuttlecube.application.operations.approvals import decide_approval
from shuttlecube.application.operations.assignments import assign_case
from shuttlecube.application.operations.briefs import build_daily_brief
from shuttlecube.application.operations.candidates import generate_replacement_candidates
from shuttlecube.application.operations.cases import dismiss_case
from shuttlecube.application.operations.detectors import DetectorRegistry
from shuttlecube.application.operations.evidence import (
    receivable_followup_context,
    renewal_followup_context,
)
from shuttlecube.application.operations.idempotency import (
    IdempotencyConflict,
    canonical_hash,
    persist_tool_result,
    resolve_idempotent_result,
)
from shuttlecube.application.operations.policies import (
    PolicyNotConfigured,
    activate_policy,
    copy_policy_as_draft,
    create_policy_draft,
    delete_policy_draft,
    get_active_policy,
    get_policy,
    update_policy_draft,
)
from shuttlecube.application.operations.reconciliation_workflow import (
    enqueue_reconciliation_explanation,
    reconciliation_case_context,
)
from shuttlecube.application.operations.replacement_workflow import (
    approval_payload,
    create_replacement_proposal,
)
from shuttlecube.application.operations.report_snapshots import (
    get_report_snapshot,
    report_snapshot_payload,
)
from shuttlecube.application.operations.report_workflow import (
    enqueue_narrative_run,
    enqueue_report_run,
)
from shuttlecube.application.operations.repositories import OperationsRepository
from shuttlecube.application.operations.revenue_workflow import enqueue_revenue_analysis
from shuttlecube.application.operations.runtime import checkpoint_run
from shuttlecube.application.operations.scan_runs import enqueue_scan_run
from shuttlecube.application.operations.state_machine import transition_run
from shuttlecube.application.operations.tools import (
    CapabilityDenied,
    ToolDisabled,
    ToolExecutionContext,
    ToolRegistry,
)
from shuttlecube.application.operations.verifiers import VerifierRegistry
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.operations.models import (
    CaseActivity,
    OperationApproval,
    OperationCase,
    OperationEvent,
    OperationRun,
    OperationsReportSnapshot,
    OperationToolCall,
)
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.operations.schemas import OperationsPolicyConfig
from shuttlecube.domain.private_lessons.models import PrivateLessonPackage
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(prefix="/operations", tags=["Intelligent Operations"])


class PolicyDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    schema_version: Literal["1"]
    config: OperationsPolicyConfig


class PolicyUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    config: OperationsPolicyConfig
    expected_version: int = Field(ge=1)


class PolicyCopyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)


class PolicyActivationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ScanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detector_keys: list[str] | None = Field(default=None, max_length=20)


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_case_version: int = Field(ge=1)


class AssignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignee_membership_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=1, max_length=500)
    expected_case_version: int = Field(ge=1)


class DismissInput(VersionInput):
    reason: str = Field(min_length=1, max_length=500)


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_case_version: int | None = Field(default=None, ge=1)


class ReportRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_type: Literal["day", "week", "month"]
    anchor_date: date
    include_narrative: bool = True


class ReplacementCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_start: datetime
    window_end: datetime
    expected_case_version: int = Field(ge=1)
    max_candidates: int = Field(default=20, ge=1, le=50)


class ReplacementProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_plan_id: str = Field(min_length=1, max_length=36)
    coordination_confirmed: Literal[True]
    expected_case_version: int = Field(ge=1)


class ApprovalDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_approval_version: int = Field(ge=1)
    expected_input_hash: str = Field(min_length=16, max_length=128)
    reason: str = Field(min_length=1, max_length=500)


def _policy_payload(policy: OperationsPolicy) -> dict[str, object]:
    return {
        "id": policy.id,
        "name": policy.name,
        "policy_key": policy.policy_key,
        "policy_version": policy.policy_version,
        "schema_version": str(policy.schema_version),
        "config": policy.config,
        "config_hash": policy.config_hash,
        "state": policy.state,
        "effective_from": policy.effective_from,
        "effective_to": policy.effective_to,
        "created_by": policy.created_by,
        "activated_by": policy.activated_by,
        "activated_at": policy.activated_at,
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
        "version": policy.version,
    }


def _case_payload(case: OperationCase) -> dict[str, object]:
    return {
        "id": case.id,
        "case_type": case.case_type,
        "subject_type": case.subject_type,
        "subject_id": case.subject_id,
        "occurrence_no": case.occurrence_no,
        "severity": case.severity,
        "priority_score": case.priority_score,
        "title": case.title,
        "business_summary": case.business_summary,
        "state": case.state,
        "first_detected_at": case.first_detected_at,
        "last_detected_at": case.last_detected_at,
        "next_check_at": case.next_check_at,
        "due_at": case.due_at,
        "queue_key": case.queue_key,
        "required_capability": case.required_capability,
        "assigned_to": case.assigned_to,
        "assigned_at": case.assigned_at,
        "assigned_by": case.assigned_by,
        "current_run_id": case.current_run_id,
        "evidence": case.evidence,
        "evidence_hash": case.evidence_hash,
        "resolved_at": case.resolved_at,
        "dismissed_reason": case.dismissed_reason,
        "policy_version": case.policy_version,
        "version": case.version,
    }


def _run_summary(run: OperationRun) -> dict[str, object]:
    return {
        "id": run.id,
        "case_id": run.case_id,
        "parent_run_id": run.parent_run_id,
        "run_type": run.run_type,
        "trigger_type": run.trigger_type,
        "workflow_key": run.workflow_key,
        "workflow_version": str(run.workflow_version),
        "policy_version": run.policy_version,
        "state": run.state,
        "attempt": run.attempt,
        "error_code": run.error_code,
        "error_summary": run.error_summary,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
    }


def _visible_case(db: Session, scope: RequestScope, case_id: str) -> OperationCase:
    case = db.scalar(
        select(OperationCase).where(
            OperationCase.id == case_id,
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
            OperationCase.required_capability.in_(scope.capabilities),
        )
    )
    if case is None:
        raise BusinessError(404, "scope_not_found", "运营案件不存在")
    return case


def _visible_approval(
    db: Session,
    scope: RequestScope,
    approval_id: str,
) -> OperationApproval:
    approval = db.scalar(
        select(OperationApproval).where(
            OperationApproval.id == approval_id,
            OperationApproval.organization_id == scope.organization_id,
            OperationApproval.venue_id == scope.venue_id,
        )
    )
    if approval is None:
        raise BusinessError(404, "scope_not_found", "审批不存在")
    if approval.case_id:
        _visible_case(db, scope, approval.case_id)
    return approval


def _activity_by_reference(
    db: Session,
    *,
    scope: RequestScope,
    reference: str | None,
) -> CaseActivity | None:
    prefix = "case_activity:"
    if not reference or not reference.startswith(prefix):
        return None
    return db.scalar(
        select(CaseActivity).where(
            CaseActivity.id == reference[len(prefix) :],
            CaseActivity.organization_id == scope.organization_id,
            CaseActivity.venue_id == scope.venue_id,
        )
    )


@router.get("/context", operation_id="getOperationsContext")
def get_operations_context(
    scope: Annotated[RequestScope, Depends(request_scope)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    organization = db.get(Organization, scope.organization_id)
    venue = db.get(Venue, scope.venue_id)
    if organization is None or venue is None:
        raise BusinessError(404, "scope_not_found", "当前运营范围不存在")
    active_policy = db.scalar(
        select(OperationsPolicy.id).where(
            OperationsPolicy.organization_id == scope.organization_id,
            OperationsPolicy.venue_id == scope.venue_id,
            OperationsPolicy.policy_key == "default_operations",
            OperationsPolicy.state == "active",
        )
    )
    return {
        "organization": {"id": organization.id, "name": organization.name},
        "venue": {"id": venue.id, "name": venue.name},
        "user_id": scope.user_id,
        "membership_id": scope.membership_id,
        "capabilities": sorted(scope.capabilities),
        "operations_enabled": venue.active_for_operations,
        "write_tools_enabled": venue.write_tools_enabled,
        "model_enabled": venue.model_enabled,
        "policy_status": "active" if active_policy else "policy_not_configured",
    }


@router.get("/policies", operation_id="listOperationsPolicies")
def list_operations_policies(
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.policy.manage"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, object]]:
    policies = db.scalars(
        select(OperationsPolicy)
        .where(
            OperationsPolicy.organization_id == scope.organization_id,
            OperationsPolicy.venue_id == scope.venue_id,
        )
        .order_by(
            OperationsPolicy.policy_key,
            OperationsPolicy.policy_version.desc(),
        )
    ).all()
    return [_policy_payload(policy) for policy in policies]


@router.get("/policies/{policy_id}", operation_id="getOperationsPolicy")
def get_operations_policy(
    policy_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.policy.manage"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return _policy_payload(get_policy(db, scope=scope, policy_id=policy_id))


@router.post("/scans", operation_id="startOperationsScan", status_code=status.HTTP_202_ACCEPTED)
def start_operations_scan(
    payload: ScanInput,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    enabled_keys = {item.detector_key for item in DetectorRegistry.default().enabled()}
    requested = payload.detector_keys or sorted(enabled_keys)
    unknown = set(requested) - enabled_keys
    if unknown:
        raise BusinessError(422, "unknown_detector", "请求包含尚未启用的扫描器")
    try:
        policy = get_active_policy(db, scope=scope)
    except PolicyNotConfigured as exc:
        raise BusinessError(409, "policy_not_configured", "请先激活运营规则") from exc
    run = enqueue_scan_run(
        db,
        scope=scope,
        policy=policy,
        detector_keys=sorted(requested),
        trigger_type="manual",
        trigger_key=idempotency_key,
    )
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "state": run.state}


@router.get("/cases", operation_id="listOperationCases")
def list_operation_cases(
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.read"))],
    db: Annotated[Session, Depends(get_db)],
    queue_key: str | None = None,
    case_states: Annotated[
        list[str] | None,
        Query(
            alias="state",
            description=(
                "Repeat to select states. When omitted, resolved and dismissed cases "
                "are excluded."
            ),
        ),
    ] = None,
    case_type: str | None = None,
    assigned_to: str | None = None,
    cursor: str | None = None,
    limit: int = 30,
) -> dict[str, object]:
    page_size = min(max(limit, 1), 100)
    statement = select(OperationCase).where(
        OperationCase.organization_id == scope.organization_id,
        OperationCase.venue_id == scope.venue_id,
        OperationCase.required_capability.in_(scope.capabilities),
    )
    if queue_key:
        statement = statement.where(OperationCase.queue_key == queue_key)
    if case_states:
        statement = statement.where(OperationCase.state.in_(case_states))
    else:
        statement = statement.where(
            OperationCase.state.not_in(("resolved", "dismissed"))
        )
    if case_type:
        statement = statement.where(OperationCase.case_type == case_type)
    if assigned_to:
        statement = statement.where(OperationCase.assigned_to == assigned_to)
    if case_states and set(case_states).issubset({"resolved", "dismissed"}):
        statement = statement.order_by(
            func.coalesce(OperationCase.resolved_at, OperationCase.updated_at).desc(),
            OperationCase.id.desc(),
        )
    else:
        statement = statement.order_by(
            OperationCase.priority_score.desc(),
            OperationCase.due_at,
            OperationCase.last_detected_at.desc(),
            OperationCase.id.desc(),
        )
    cases = db.scalars(statement).all()
    start = 0
    if cursor:
        positions = [index for index, item in enumerate(cases) if item.id == cursor]
        if not positions:
            raise BusinessError(422, "invalid_cursor", "案件分页游标无效")
        start = positions[0] + 1
    visible = cases[start : start + page_size]
    has_more = start + page_size < len(cases)
    return {
        "items": [_case_payload(case) for case in visible],
        "next_cursor": visible[-1].id if has_more and visible else None,
    }


@router.get("/cases/{case_id}", operation_id="getOperationCase")
def get_operation_case(
    case_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.read"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    activities = db.scalars(
        select(CaseActivity)
        .where(
            CaseActivity.organization_id == scope.organization_id,
            CaseActivity.venue_id == scope.venue_id,
            CaseActivity.case_id == case.id,
        )
        .order_by(CaseActivity.happened_at.desc(), CaseActivity.id.desc())
    ).all()
    runs = db.scalars(
        select(OperationRun)
        .where(
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
            OperationRun.case_id == case.id,
        )
        .order_by(OperationRun.created_at.desc(), OperationRun.id.desc())
        .limit(20)
    ).all()
    raw_links = (case.evidence or {}).get("business_links", [])
    links = raw_links if isinstance(raw_links, list) else []
    return {
        **_case_payload(case),
        "activities": [activity_payload(item) for item in activities],
        "latest_runs": [_run_summary(item) for item in runs],
        "business_links": [
            {"label": "查看业务记录", "route": route}
            for route in links
            if isinstance(route, str) and route.startswith("/")
        ],
    }


@router.get(
    "/cases/{case_id}/action-context",
    operation_id="getOperationCaseActionContext",
)
def get_operation_case_action_context(
    case_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.read"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    if case.state in {"resolved", "dismissed"}:
        raise BusinessError(409, "case_closed", "已完成事项只能查看，不能继续处理")

    if case.case_type == "attendance_overdue":
        session = db.scalar(
            select(ClassSession).where(
                ClassSession.id == case.subject_id,
                ClassSession.organization_id == scope.organization_id,
                ClassSession.venue_id == scope.venue_id,
            )
        )
        if session is None:
            raise BusinessError(404, "scope_not_found", "待考勤课程不存在")
        fixed_class = db.scalar(
            select(FixedClass).where(
                FixedClass.id == session.fixed_class_id,
                FixedClass.organization_id == scope.organization_id,
                FixedClass.venue_id == scope.venue_id,
            )
        )
        enrollments = db.scalars(
            select(Enrollment).where(
                Enrollment.organization_id == scope.organization_id,
                Enrollment.venue_id == scope.venue_id,
                Enrollment.fixed_class_id == session.fixed_class_id,
                Enrollment.status == "active",
            )
        ).all()
        student_ids = {item.student_id for item in enrollments}
        students = (
            db.scalars(
                select(Student).where(
                    Student.organization_id == scope.organization_id,
                    Student.id.in_(student_ids),
                )
            ).all()
            if student_ids
            else []
        )
        student_names = {item.id: item.name for item in students}
        return {
            "kind": "attendance",
            "session": {
                "id": session.id,
                "fixed_class_id": session.fixed_class_id,
                "fixed_class_name": fixed_class.name if fixed_class else case.title,
                "sequence_number": session.sequence_number,
                "scheduled_start": session.scheduled_start,
                "scheduled_end": session.scheduled_end,
                "status": session.status,
                "attendance_finalized_at": session.attendance_finalized_at,
                "version": session.version,
            },
            "enrollments": [
                {
                    "id": item.id,
                    "student_id": item.student_id,
                    "student_name": student_names.get(item.student_id, "未知学员"),
                }
                for item in enrollments
            ],
        }

    if case.case_type == "receivable_followup":
        context = receivable_followup_context(db, scope=scope, case=case)
        return {
            "kind": "receivable",
            **project_followup_context(context, scope=scope, case_type=case.case_type),
        }

    if case.case_type == "fixed_class_renewal":
        fixed_class = db.scalar(
            select(FixedClass).where(
                FixedClass.id == case.subject_id,
                FixedClass.organization_id == scope.organization_id,
                FixedClass.venue_id == scope.venue_id,
            )
        )
        if fixed_class is None:
            raise BusinessError(404, "scope_not_found", "固定班不存在")
        enrollments = db.scalars(
            select(Enrollment).where(
                Enrollment.organization_id == scope.organization_id,
                Enrollment.venue_id == scope.venue_id,
                Enrollment.fixed_class_id == fixed_class.id,
                Enrollment.status == "active",
            )
        ).all()
        student_ids = {item.student_id for item in enrollments}
        students = (
            db.scalars(
                select(Student).where(
                    Student.organization_id == scope.organization_id,
                    Student.id.in_(student_ids),
                )
            ).all()
            if student_ids
            else []
        )
        student_names = {item.id: item.name for item in students}
        followup = renewal_followup_context(db, scope=scope, case=case)
        return {
            "kind": "fixed_class_renewal",
            **project_followup_context(followup, scope=scope, case_type=case.case_type),
            "fixed_class": {
                "id": fixed_class.id,
                "name": fixed_class.name,
                "version": fixed_class.version,
                "session_count": fixed_class.session_count,
            },
            "enrollments": [
                {
                    "id": item.id,
                    "student_name": student_names.get(item.student_id, "未知学员"),
                    "unit_price": str(item.unit_price),
                    "status": item.status,
                }
                for item in enrollments
            ],
        }

    if case.case_type == "private_package_renewal":
        package = db.scalar(
            select(PrivateLessonPackage).where(
                PrivateLessonPackage.id == case.subject_id,
                PrivateLessonPackage.organization_id == scope.organization_id,
                PrivateLessonPackage.venue_id == scope.venue_id,
            )
        )
        if package is None:
            raise BusinessError(404, "scope_not_found", "私教课包不存在")
        student = db.scalar(
            select(Student).where(
                Student.id == package.student_id,
                Student.organization_id == scope.organization_id,
            )
        )
        coach = db.scalar(
            select(CoachProfile).where(
                CoachProfile.id == package.bound_coach_id,
                CoachProfile.organization_id == scope.organization_id,
            )
        )
        followup = renewal_followup_context(db, scope=scope, case=case)
        return {
            "kind": "private_package_renewal",
            **project_followup_context(followup, scope=scope, case_type=case.case_type),
            "package": {
                "id": package.id,
                "student_id": package.student_id,
                "student_name": student.name if student else "未知学员",
                "coach_id": package.bound_coach_id,
                "coach_name": coach.name if coach else "未知教练",
                "unit_price": str(package.unit_price),
                "valid_until": package.valid_until,
            },
        }

    if case.case_type == "reconciliation_failure":
        return {"kind": "reconciliation", **reconciliation_case_context(case)}
    if case.case_type == "class_replacement_pending":
        return {"kind": "replacement", "facts": (case.evidence or {}).get("facts", {})}
    raise BusinessError(422, "case_action_not_supported", "该事项暂不支持在案件内处理")


@router.post(
    "/cases/{case_id}:verify",
    operation_id="verifyOperationCaseNow",
)
def verify_operation_case_now(
    case_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.manage"))],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    request: Request,
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    if case.state in {"resolved", "dismissed"}:
        return {"state": case.state, "outcome": case.state, "reason_code": "case_closed"}
    result = VerifierRegistry.default().verify(db, scope, case)
    record_audit(
        db,
        actor_id=user.id,
        action="operation_case.verified_now",
        entity_type="operation_case",
        entity_id=case.id,
        request_id=request.state.request_id,
        before=None,
        after={
            "outcome": result.outcome,
            "reason_code": result.reason_code,
            "state": case.state,
        },
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    db.refresh(case)
    return {
        "state": case.state,
        "outcome": result.outcome,
        "reason_code": result.reason_code,
    }


@router.get(
    "/cases/{case_id}/followup-context",
    operation_id="getOperationCaseFollowupContext",
)
def get_operation_case_followup_context(
    case_id: str,
    scope: Annotated[RequestScope, Depends(request_scope)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    if case.case_type == "receivable_followup":
        if "operations.receivable.followup.read" not in scope.capabilities:
            raise BusinessError(403, "capability_denied", "没有查看欠费跟进的权限")
        context = receivable_followup_context(db, scope=scope, case=case)
        return project_followup_context(context, scope=scope, case_type=case.case_type)
    if case.case_type in {"fixed_class_renewal", "private_package_renewal"}:
        context = renewal_followup_context(db, scope=scope, case=case)
        return project_followup_context(context, scope=scope, case_type=case.case_type)
    raise BusinessError(422, "followup_not_supported", "该案件没有跟进上下文")


@router.get(
    "/cases/{case_id}/reconciliation-context",
    operation_id="getOperationCaseReconciliationContext",
)
def get_operation_case_reconciliation_context(
    case_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.read"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    if case.case_type != "reconciliation_failure":
        raise BusinessError(422, "reconciliation_not_supported", "该案件不是数据一致性异常")
    try:
        return reconciliation_case_context(case)
    except ValueError as exc:
        raise BusinessError(409, "reconciliation_result_missing", str(exc)) from exc


@router.post(
    "/cases/{case_id}/replacement-candidates",
    operation_id="listReplacementCandidates",
)
def list_replacement_candidates(
    case_id: str,
    payload: ReplacementCandidateInput,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[SystemUser, Depends(require_csrf)],
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    try:
        policy = get_active_policy(db, scope=scope, policy_key=case.policy_key)
    except PolicyNotConfigured as exc:
        raise BusinessError(409, "policy_not_configured", "请先激活运营规则") from exc
    _, result = generate_replacement_candidates(
        db,
        scope=scope,
        case=case,
        policy=policy,
        window_start=payload.window_start,
        window_end=payload.window_end,
        expected_case_version=payload.expected_case_version,
        max_candidates=payload.max_candidates,
    )
    db.commit()
    return result


@router.post(
    "/cases/{case_id}/replacement-proposals",
    operation_id="proposeReplacement",
    status_code=status.HTTP_201_CREATED,
)
def propose_replacement(
    case_id: str,
    payload: ReplacementProposalInput,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    try:
        policy = get_active_policy(db, scope=scope, policy_key=case.policy_key)
    except PolicyNotConfigured as exc:
        raise BusinessError(409, "policy_not_configured", "请先激活运营规则") from exc
    tool_call, approval, _ = create_replacement_proposal(
        db,
        scope=scope,
        case=case,
        policy=policy,
        resource_plan_id=payload.resource_plan_id,
        coordination_confirmed=payload.coordination_confirmed,
        expected_case_version=payload.expected_case_version,
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(approval)
    return {
        "tool_call_id": tool_call.id,
        "state": "awaiting_approval",
        "approval": approval_payload(approval),
    }


@router.post(
    "/cases/{case_id}:analyze",
    operation_id="analyzeOperationCase",
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_operation_case(
    case_id: str,
    scope: Annotated[RequestScope, Depends(request_scope)],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    payload: AnalysisInput | None = None,
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    if payload and payload.expected_case_version not in {None, case.version}:
        raise BusinessError(409, "concurrent_change", "案件已发生变化")
    if case.case_type == "reconciliation_failure":
        run = enqueue_reconciliation_explanation(
            db,
            scope=scope,
            case=case,
            trigger_key=idempotency_key,
        )
        db.commit()
        db.refresh(run)
        return {"run_id": run.id, "state": run.state}
    if case.case_type not in {
        "receivable_followup",
        "fixed_class_renewal",
        "private_package_renewal",
    }:
        raise BusinessError(422, "analysis_not_supported", "该案件暂不支持智能分析")
    run = enqueue_revenue_analysis(
        db,
        scope=scope,
        case=case,
        policy_version=case.policy_version,
        trigger_key=idempotency_key,
    )
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "state": run.state}


@router.post(
    "/cases/{case_id}/activities",
    operation_id="recordOperationCaseActivity",
    status_code=status.HTTP_201_CREATED,
)
def post_operation_case_activity(
    case_id: str,
    payload: FollowupActivityInput,
    request: Request,
    scope: Annotated[
        RequestScope,
        Depends(require_scope_capability("operations.receivable.followup.write")),
    ],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    case = _visible_case(db, scope, case_id)
    normalized_input = {"case_id": case.id, **payload.model_dump(mode="json")}
    try:
        existing = resolve_idempotent_result(
            db,
            scope=scope,
            tool_key="record_followup_outcome",
            idempotency_key=idempotency_key,
            normalized_input=normalized_input,
        )
    except IdempotencyConflict as exc:
        raise BusinessError(
            409,
            "idempotency_conflict",
            "同一幂等键不能用于不同的跟进内容",
        ) from exc
    if existing is not None:
        activity = _activity_by_reference(
            db,
            scope=scope,
            reference=existing.result_reference,
        )
        if existing.state == "succeeded" and activity is not None:
            return activity_payload(activity)
        raise BusinessError(409, "activity_in_progress", "该跟进正在处理，请稍后重试")

    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if venue is None:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    registry = ToolRegistry.default()
    try:
        definition = registry.authorize(
            "record_followup_outcome",
            scope=scope,
            write_tools_enabled=venue.write_tools_enabled,
        )
    except CapabilityDenied as exc:
        raise BusinessError(403, "capability_denied", "没有记录运营跟进的权限") from exc
    except ToolDisabled as exc:
        raise BusinessError(409, "write_tool_disabled", "当前场馆尚未启用受控写操作") from exc
    now = datetime.now(UTC)
    run = OperationRun(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        case_id=case.id,
        parent_run_id=case.current_run_id,
        run_type="human_tool",
        trigger_type="manual",
        workflow_key="operations.human_tool.v1",
        workflow_version=1,
        policy_key=case.policy_key,
        policy_version=case.policy_version,
        prompt_version=None,
        toolset_version=1,
        model_profile=None,
        input_refs=[{"kind": "operation_case", "id": case.id, "version": case.version}],
        input_hash=canonical_hash(normalized_input),
        checkpoint={"workflow_step": "tool_execution", "state": {}},
        state="queued",
        max_steps=1,
        max_model_calls=0,
        max_tool_calls=1,
        max_write_calls=1,
        deadline_at=now + timedelta(minutes=1),
    )
    db.add(run)
    db.flush()
    transition_run(run, "running", now=now)
    tool_call = OperationToolCall(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        run_id=run.id,
        case_id=case.id,
        policy_key=case.policy_key,
        policy_version=case.policy_version,
        tool_key=definition.tool_key,
        tool_version=definition.tool_version,
        risk_level=definition.risk_level,
        normalized_input=normalized_input,
        input_hash=canonical_hash(normalized_input),
        impact_snapshot={"case_id": case.id, "outcome_code": payload.outcome_code},
        subject_versions={"operation_case": case.version},
        required_capability=definition.required_capability,
        state="executing",
        idempotency_key=idempotency_key,
        started_at=now,
    )
    db.add(tool_call)
    db.flush()
    output = registry.execute(
        definition.tool_key,
        context=ToolExecutionContext(
            db=db,
            scope=scope,
            request_id=str(getattr(request.state, "request_id", "unknown")),
            run_id=run.id,
        ),
        value=normalized_input,
        write_tools_enabled=venue.write_tools_enabled,
    )
    data = output.model_dump(mode="json").get("data", {})
    activity_id = str(data.get("id", "")) if isinstance(data, dict) else ""
    activity = db.get(CaseActivity, activity_id) if activity_id else None
    if activity is None:
        raise BusinessError(500, "activity_result_missing", "跟进结果未能确认")
    persist_tool_result(
        tool_call,
        result_reference=f"case_activity:{activity.id}",
        result_summary=f"recorded {activity.outcome_code}",
    )
    tool_call.finished_at = datetime.now(UTC)
    checkpoint_run(
        run,
        {
            "workflow_step": "tool_complete",
            "completed_steps": ["validate", "write", "verify"],
            "state": {"activity_id": activity.id},
        },
    )
    transition_run(run, "succeeded")
    db.commit()
    db.refresh(activity)
    return activity_payload(activity)


@router.get("/approvals", operation_id="listOperationApprovals")
def list_operation_approvals(
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.approval.decide"))],
    db: Annotated[Session, Depends(get_db)],
    approval_states: Annotated[list[str] | None, Query(alias="state")] = None,
) -> list[dict[str, object]]:
    statement = select(OperationApproval).where(
        OperationApproval.organization_id == scope.organization_id,
        OperationApproval.venue_id == scope.venue_id,
    )
    if approval_states:
        allowed = {"pending", "approved", "rejected", "expired", "stale", "cancelled"}
        if unknown := set(approval_states) - allowed:
            raise BusinessError(422, "invalid_approval_state", f"未知审批状态: {sorted(unknown)}")
        statement = statement.where(OperationApproval.state.in_(approval_states))
    approvals = db.scalars(
        statement.order_by(OperationApproval.created_at.desc(), OperationApproval.id.desc())
    ).all()
    return [approval_payload(item) for item in approvals]


def _decide_operation_approval(
    *,
    approval_id: str,
    payload: ApprovalDecisionInput,
    approve: bool,
    request: Request,
    scope: RequestScope,
    db: Session,
) -> dict[str, object]:
    approval = _visible_approval(db, scope, approval_id)
    try:
        approval, run = decide_approval(
            db,
            scope=scope,
            approval=approval,
            approve=approve,
            expected_version=payload.expected_approval_version,
            expected_input_hash=payload.expected_input_hash,
            reason=payload.reason,
            request_id=str(getattr(request.state, "request_id", "unknown")),
        )
    except BusinessError as exc:
        if exc.code in {"approval_stale", "approval_expired"}:
            db.commit()
        raise
    db.commit()
    db.refresh(approval)
    if run is not None:
        db.refresh(run)
    return {
        "approval": approval_payload(approval),
        "execution_run": _run_summary(run) if run is not None else None,
    }


@router.post(
    "/approvals/{approval_id}:approve",
    operation_id="approveOperationToolCall",
    status_code=status.HTTP_202_ACCEPTED,
)
def approve_operation_tool_call(
    approval_id: str,
    payload: ApprovalDecisionInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.approval.decide"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    return _decide_operation_approval(
        approval_id=approval_id,
        payload=payload,
        approve=True,
        request=request,
        scope=scope,
        db=db,
    )


@router.post(
    "/approvals/{approval_id}:reject",
    operation_id="rejectOperationToolCall",
)
def reject_operation_tool_call(
    approval_id: str,
    payload: ApprovalDecisionInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.approval.decide"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    return _decide_operation_approval(
        approval_id=approval_id,
        payload=payload,
        approve=False,
        request=request,
        scope=scope,
        db=db,
    )


@router.get("/brief", operation_id="getOperationsDailyBrief")
def get_operations_daily_brief(
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.read"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return build_daily_brief(db, scope=scope)


@router.get("/reports", operation_id="listOperationsReports")
def list_operations_reports(
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.report.read"))],
    db: Annotated[Session, Depends(get_db)],
    period_type: Literal["day", "week", "month"] | None = None,
    cursor: str | None = None,
    limit: int = 30,
) -> dict[str, object]:
    page_size = min(max(limit, 1), 100)
    statement = select(OperationsReportSnapshot).where(
        OperationsReportSnapshot.organization_id == scope.organization_id,
        OperationsReportSnapshot.venue_id == scope.venue_id,
    )
    if period_type:
        statement = statement.where(OperationsReportSnapshot.period_type == period_type)
    if cursor:
        cursor_item = db.scalar(
            select(OperationsReportSnapshot).where(
                OperationsReportSnapshot.id == cursor,
                OperationsReportSnapshot.organization_id == scope.organization_id,
                OperationsReportSnapshot.venue_id == scope.venue_id,
            )
        )
        if cursor_item is None:
            raise BusinessError(422, "invalid_cursor", "报告分页游标无效")
        statement = statement.where(
            OperationsReportSnapshot.generated_at < cursor_item.generated_at
        )
    rows = db.scalars(
        statement.order_by(
            OperationsReportSnapshot.generated_at.desc(),
            OperationsReportSnapshot.id.desc(),
        ).limit(page_size + 1)
    ).all()
    visible = rows[:page_size]
    return {
        "items": [
            {
                "id": item.id,
                "run_id": item.run_id,
                "period_type": item.period_type,
                "period_start": item.period_start,
                "period_end": item.period_end,
                "effective_end": item.effective_end,
                "period_state": item.period_state,
                "generated_at": item.generated_at,
                "narrative_state": item.narrative_state,
                "evidence_hash": item.evidence_hash,
            }
            for item in visible
        ],
        "next_cursor": visible[-1].id if len(rows) > page_size and visible else None,
    }


@router.post(
    "/reports",
    operation_id="generateOperationsReport",
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_operations_report(
    payload: ReportRequestInput,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.report.read"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    try:
        run = enqueue_report_run(
            db,
            scope=scope,
            period_type=payload.period_type,
            anchor_date=payload.anchor_date,
            include_narrative=payload.include_narrative,
            trigger_key=idempotency_key,
        )
    except ValueError as exc:
        raise BusinessError(422, "invalid_report_period", str(exc)) from exc
    except PolicyNotConfigured as exc:
        raise BusinessError(409, "policy_not_configured", "请先激活运营规则") from exc
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "state": run.state}


@router.get("/reports/{report_id}", operation_id="getOperationsReport")
def get_operations_report_snapshot_endpoint(
    report_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.report.read"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    snapshot = get_report_snapshot(db, scope=scope, snapshot_id=report_id)
    payload = report_snapshot_payload(snapshot)
    projected = project_report_payload(payload, scope=scope)
    projected["access_projection"] = {
        "financial_metrics_included": "operations.report.financial.read" in scope.capabilities,
        "payroll_metrics_included": "operations.payroll.read" in scope.capabilities,
        "omitted_sections": [
            section
            for section, included in (
                ("financial", "operations.report.financial.read" in scope.capabilities),
                ("receivables", "operations.report.financial.read" in scope.capabilities),
                ("source_breakdowns", "operations.report.financial.read" in scope.capabilities),
                ("payroll", "operations.payroll.read" in scope.capabilities),
            )
            if not included
        ],
    }
    return projected


@router.post(
    "/reports/{report_id}/narrative:retry",
    operation_id="retryOperationsReportNarrative",
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_operations_report_narrative(
    report_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.report.read"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    snapshot = get_report_snapshot(db, scope=scope, snapshot_id=report_id)
    parent = db.scalar(
        select(OperationRun).where(
            OperationRun.id == snapshot.run_id,
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
        )
    )
    if parent is None:
        raise BusinessError(409, "report_run_missing", "报告运行记录不存在")
    child = enqueue_narrative_run(
        db,
        snapshot=snapshot,
        parent_run=parent,
        trigger_key=idempotency_key,
    )
    db.commit()
    db.refresh(child)
    return {"run_id": child.id, "state": child.state}


@router.post("/cases/{case_id}:claim", operation_id="claimOperationCase")
def claim_operation_case(
    case_id: str,
    payload: VersionInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(request_scope)],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    case = _visible_case(db, scope, case_id)
    assign_case(
        db,
        scope=scope,
        case=case,
        assignee_user_id=scope.user_id,
        expected_version=payload.expected_case_version,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        self_claim=True,
    )
    db.commit()
    db.refresh(case)
    return _case_payload(case)


@router.post("/cases/{case_id}:assign", operation_id="assignOperationCase")
def assign_operation_case(
    case_id: str,
    payload: AssignInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.assign"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    case = _visible_case(db, scope, case_id)
    assignee = db.scalar(
        select(OrganizationMembership)
        .join(
            VenueMembership,
            VenueMembership.organization_membership_id == OrganizationMembership.id,
        )
        .where(
            VenueMembership.id == payload.assignee_membership_id,
            VenueMembership.organization_id == scope.organization_id,
            VenueMembership.venue_id == scope.venue_id,
            VenueMembership.status == "active",
            OrganizationMembership.organization_id == scope.organization_id,
            OrganizationMembership.status == "active",
        )
    )
    if assignee is None:
        raise BusinessError(422, "invalid_assignee", "所选成员不能处理该案件")
    assign_case(
        db,
        scope=scope,
        case=case,
        assignee_user_id=assignee.user_id,
        expected_version=payload.expected_case_version,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        reason=payload.reason,
    )
    db.commit()
    db.refresh(case)
    return _case_payload(case)


@router.post("/cases/{case_id}:dismiss", operation_id="dismissOperationCase")
def dismiss_operation_case(
    case_id: str,
    payload: DismissInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    case = _visible_case(db, scope, case_id)
    dismiss_case(
        db,
        scope=scope,
        case=case,
        reason=payload.reason,
        expected_version=payload.expected_case_version,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    db.commit()
    db.refresh(case)
    return _case_payload(case)


@router.post(
    "/policies",
    operation_id="createOperationsPolicyDraft",
    status_code=status.HTTP_201_CREATED,
)
def post_operations_policy_draft(
    payload: PolicyDraftInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.policy.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    policy = create_policy_draft(
        db,
        scope=scope,
        schema_version=1,
        config=payload.config.model_dump(mode="json"),
        name=payload.name,
    )
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.policy_draft_created",
        entity_type="operations_policy",
        entity_id=policy.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        after={
            "name": policy.name,
            "policy_version": policy.policy_version,
            "state": "draft",
            "config_hash": policy.config_hash,
        },
        reason="创建运营规则草稿",
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    db.refresh(policy)
    return _policy_payload(policy)


@router.patch("/policies/{policy_id}", operation_id="updateOperationsPolicyDraft")
def patch_operations_policy_draft(
    policy_id: str,
    payload: PolicyUpdateInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.policy.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    current = get_policy(db, scope=scope, policy_id=policy_id)
    before = {"name": current.name, "config_hash": current.config_hash, "version": current.version}
    policy = update_policy_draft(
        db,
        scope=scope,
        policy_id=policy_id,
        name=payload.name,
        config=payload.config.model_dump(mode="json"),
        expected_version=payload.expected_version,
    )
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.policy_draft_updated",
        entity_type="operations_policy",
        entity_id=policy.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        before=before,
        after={"name": policy.name, "config_hash": policy.config_hash, "version": policy.version},
        reason="编辑运营规则草稿",
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    db.refresh(policy)
    return _policy_payload(policy)


@router.post(
    "/policies/{policy_id}:copy",
    operation_id="copyOperationsPolicyDraft",
    status_code=status.HTTP_201_CREATED,
)
def post_operations_policy_copy(
    policy_id: str,
    payload: PolicyCopyInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.policy.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    source = get_policy(db, scope=scope, policy_id=policy_id)
    policy = copy_policy_as_draft(
        db,
        scope=scope,
        policy_id=policy_id,
        name=payload.name,
    )
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.policy_draft_copied",
        entity_type="operations_policy",
        entity_id=policy.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        before={"source_policy_id": source.id, "source_policy_version": source.policy_version},
        after={
            "name": policy.name,
            "policy_version": policy.policy_version,
            "state": "draft",
            "config_hash": policy.config_hash,
        },
        reason="复制运营规则为新草稿",
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    db.refresh(policy)
    return _policy_payload(policy)


@router.delete(
    "/policies/{policy_id}",
    operation_id="deleteOperationsPolicyDraft",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_operations_policy_draft(
    policy_id: str,
    request: Request,
    expected_version: Annotated[int, Query(ge=1)],
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.policy.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> None:
    del idempotency_key
    policy = delete_policy_draft(
        db,
        scope=scope,
        policy_id=policy_id,
        expected_version=expected_version,
    )
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.policy_draft_deleted",
        entity_type="operations_policy",
        entity_id=policy.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        before={
            "name": policy.name,
            "policy_version": policy.policy_version,
            "state": policy.state,
            "config_hash": policy.config_hash,
        },
        reason="删除运营规则草稿",
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()


@router.post(
    "/policies/{policy_id}:activate",
    operation_id="activateOperationsPolicy",
)
def post_operations_policy_activation(
    policy_id: str,
    payload: PolicyActivationInput,
    request: Request,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.policy.manage"))],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    current = db.scalar(
        select(OperationsPolicy).where(
            OperationsPolicy.id == policy_id,
            OperationsPolicy.organization_id == scope.organization_id,
            OperationsPolicy.venue_id == scope.venue_id,
        )
    )
    if current is None:
        raise BusinessError(404, "scope_not_found", "策略不存在")
    policy = activate_policy(
        db,
        scope=scope,
        policy_id=current.id,
        expected_version=payload.expected_version,
    )
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.policy_activated",
        entity_type="operations_policy",
        entity_id=policy.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        before={"name": current.name, "policy_version": current.policy_version, "state": "draft"},
        after={
            "name": policy.name,
            "policy_version": policy.policy_version,
            "state": "active",
            "config_hash": policy.config_hash,
        },
        reason="激活运营规则版本",
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    db.refresh(policy)
    return _policy_payload(policy)


@router.get("/runs/{run_id}", operation_id="getOperationRun")
def get_operation_run(
    run_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.read"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    run = OperationsRepository(db, scope).get_run(run_id)
    if run.case_id is not None:
        _visible_case(db, scope, run.case_id)
    first_event = db.scalar(
        select(OperationEvent)
        .where(
            OperationEvent.organization_id == scope.organization_id,
            OperationEvent.venue_id == scope.venue_id,
            OperationEvent.run_id == run.id,
        )
        .order_by(OperationEvent.sequence)
    )
    tool_call = db.scalar(
        select(OperationToolCall).where(
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
            OperationToolCall.run_id == run.id,
            OperationToolCall.result_reference.is_not(None),
        )
    )
    checkpoint = run.checkpoint or {}
    completed = checkpoint.get("completed_steps", [])
    completed_count = len(completed) if isinstance(completed, list) else 0
    return {
        **_run_summary(run),
        "checkpoint": run.checkpoint,
        "updated_at": run.updated_at,
        "version": run.version,
        "progress": {
            "stage": str(checkpoint.get("workflow_step", run.state)),
            "completed_steps": completed_count,
            "total_steps": run.max_steps,
        },
        "budgets": {
            "max_steps": run.max_steps,
            "max_model_calls": run.max_model_calls,
            "max_tool_calls": run.max_tool_calls,
            "max_write_calls": run.max_write_calls,
        },
        "counters": {
            "steps": run.step_count,
            "model_calls": run.model_call_count,
            "tool_calls": run.tool_call_count,
            "write_calls": run.write_call_count,
        },
        "trace_id": first_event.trace_id if first_event else run.id,
        "result_ref": (
            {"kind": "tool_result", "id": tool_call.result_reference}
            if tool_call and tool_call.result_reference
            else None
        ),
    }


@router.get("/runs/{run_id}/events", operation_id="listOperationRunEvents")
def list_operation_run_events(
    run_id: str,
    scope: Annotated[RequestScope, Depends(require_scope_capability("operations.case.read"))],
    db: Annotated[Session, Depends(get_db)],
    after_sequence: int = 0,
) -> list[dict[str, object]]:
    run = OperationsRepository(db, scope).get_run(run_id)
    if run.case_id is not None:
        _visible_case(db, scope, run.case_id)
    events = db.scalars(
        select(OperationEvent)
        .where(
            OperationEvent.organization_id == scope.organization_id,
            OperationEvent.venue_id == scope.venue_id,
            OperationEvent.run_id == run_id,
            OperationEvent.sequence > max(after_sequence, 0),
        )
        .order_by(OperationEvent.sequence)
    ).all()
    return [
        {
            "id": event.id,
            "sequence": event.sequence,
            "event_type": event.event_type,
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "trace_id": event.trace_id,
            "request_id": event.request_id,
            "payload": event.payload_redacted,
            "payload_hash": event.payload_hash,
            "occurred_at": event.occurred_at,
        }
        for event in events
    ]
