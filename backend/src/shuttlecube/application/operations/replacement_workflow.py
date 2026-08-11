from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.operations.candidates import find_frozen_resource_plan
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.application.operations.state_machine import transition_case, transition_run
from shuttlecube.application.operations.tools import ToolRegistry
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.operations.models import (
    OperationApproval,
    OperationCase,
    OperationRun,
    OperationToolCall,
)
from shuttlecube.domain.operations.policy_models import OperationsPolicy

REPLACEMENT_EXECUTION_WORKFLOW_KEY = "operations.replacement_execute.v1"


def approval_payload(item: OperationApproval) -> dict[str, object]:
    return {
        "id": item.id,
        "tool_call_id": item.tool_call_id,
        "case_id": item.case_id,
        "policy_version": item.policy_version,
        "approval_policy": item.approval_policy,
        "risk_level": item.risk_level,
        "action_summary": item.action_summary,
        "impact_snapshot": item.impact_snapshot,
        "input_hash": item.input_hash,
        "subject_versions": item.subject_versions,
        "required_capability": item.required_capability,
        "state": item.state,
        "expires_at": item.expires_at,
        "decided_by": item.decided_by,
        "decision_reason": item.decision_reason,
        "decided_at": item.decided_at,
        "version": item.version,
        "created_at": item.created_at,
    }


def create_replacement_proposal(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    policy: OperationsPolicy,
    resource_plan_id: str,
    coordination_confirmed: bool,
    expected_case_version: int,
    idempotency_key: str,
) -> tuple[OperationToolCall, OperationApproval, OperationRun]:
    if not coordination_confirmed:
        raise BusinessError(422, "coordination_required", "必须先确认已完成人员协调")
    if case.version != expected_case_version:
        raise BusinessError(409, "concurrent_change", "案件已发生变化")
    candidate_run, plan = find_frozen_resource_plan(
        db,
        scope=scope,
        case=case,
        resource_plan_id=resource_plan_id,
    )
    plan_body = {
        key: plan[key]
        for key in (
            "session_id",
            "session_version",
            "resource_policy_version",
            "starts_at",
            "ends_at",
            "coach_ids",
            "court_ids",
            "required_court_count",
        )
    }
    if (
        int(plan["resource_policy_version"]) != policy.policy_version
        or canonical_hash(plan_body) != plan.get("evidence_hash")
    ):
        raise BusinessError(409, "resource_plan_stale", "候选方案的规则或证据已变化，请重新生成")
    session = db.scalar(
        select(ClassSession).where(
            ClassSession.id == case.subject_id,
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
        )
    )
    if session is None:
        raise BusinessError(404, "scope_not_found", "取消课程不存在")
    if session.version != int(plan["session_version"]):
        raise BusinessError(409, "resource_plan_stale", "课程版本已变化，请重新生成候选")
    definition = ToolRegistry.default().get("schedule_cancelled_class_replacement")
    normalized_input = {
        "case_id": case.id,
        "resource_plan_id": resource_plan_id,
        "cancelled_session_id": session.id,
        "cancelled_session_version": session.version,
        "starts_at": plan["starts_at"],
        "ends_at": plan["ends_at"],
        "coach_ids": plan["coach_ids"],
        "court_ids": plan["court_ids"],
        "resource_policy_version": plan["resource_policy_version"],
        "coordination_confirmed": True,
        "evidence_hash": plan["evidence_hash"],
        "expires_at": plan["expires_at"],
    }
    input_hash = canonical_hash(normalized_input)
    existing = db.scalar(
        select(OperationToolCall).where(
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
            OperationToolCall.tool_key == definition.tool_key,
            OperationToolCall.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.input_hash != input_hash:
            raise BusinessError(409, "idempotency_conflict", "同一幂等键不能用于不同补排方案")
        approval = db.scalar(
            select(OperationApproval).where(OperationApproval.tool_call_id == existing.id)
        )
        run = db.get(OperationRun, existing.run_id)
        if approval is None or run is None:
            raise BusinessError(409, "proposal_incomplete", "补排提议状态不完整")
        return existing, approval, run
    now = datetime.now(UTC)
    run = OperationRun(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        case_id=case.id,
        parent_run_id=candidate_run.id,
        run_type="tool_execution",
        trigger_type="approval",
        workflow_key=REPLACEMENT_EXECUTION_WORKFLOW_KEY,
        workflow_version=1,
        policy_key=policy.policy_key,
        policy_version=policy.policy_version,
        prompt_version=None,
        toolset_version=1,
        model_profile=None,
        input_refs=[
            {"kind": "operation_case", "id": case.id, "version": case.version},
            {"kind": "class_session", "id": session.id, "version": session.version},
            {"kind": "resource_plan", "id": resource_plan_id, "evidence_hash": plan["evidence_hash"]},
        ],
        input_hash=input_hash,
        checkpoint={"workflow_step": "waiting_approval", "state": {}},
        state="queued",
        max_steps=4,
        max_model_calls=0,
        max_tool_calls=1,
        max_write_calls=1,
        deadline_at=now + timedelta(minutes=30),
    )
    db.add(run)
    db.flush()
    transition_run(run, "running", now=now)
    transition_run(run, "waiting_approval", now=now)
    if case.state == "open":
        transition_case(case, "analyzing")
    if case.state == "analyzing":
        transition_case(case, "action_proposed")
    if case.state == "action_proposed":
        transition_case(case, "waiting_approval")
    case.current_run_id = run.id
    db.flush()
    tool_call = OperationToolCall(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        run_id=run.id,
        case_id=case.id,
        policy_key=policy.policy_key,
        policy_version=policy.policy_version,
        tool_key=definition.tool_key,
        tool_version=definition.tool_version,
        risk_level=definition.risk_level,
        normalized_input=normalized_input,
        input_hash=input_hash,
        impact_snapshot={
            "resource_plan": plan,
            "student_availability_verified": False,
            "coordination_confirmed": True,
            "business_effect": "create_one_replacement_class_session",
            "finance_effect": "none",
            "lesson_unit_effect": "none",
        },
        subject_versions={
            "operation_case": case.version,
            "class_session": session.version,
            "tool_version": definition.tool_version,
        },
        required_capability=definition.required_capability,
        state="awaiting_approval",
        idempotency_key=idempotency_key,
    )
    db.add(tool_call)
    db.flush()
    expires_at = min(
        datetime.fromisoformat(str(plan["expires_at"])),
        now + timedelta(minutes=30),
    )
    approval = OperationApproval(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        tool_call_id=tool_call.id,
        case_id=case.id,
        policy_key=policy.policy_key,
        policy_version=policy.policy_version,
        requested_by=scope.user_id,
        approval_policy="mandatory_approval",
        risk_level=definition.risk_level,
        action_summary=(
            f"为取消课程创建补排：{plan['starts_at']} 至 {plan['ends_at']}；"
            "仅使用原教练和原场地，不修改资金、课时或考勤。"
        ),
        impact_snapshot=tool_call.impact_snapshot,
        input_hash=input_hash,
        subject_versions=tool_call.subject_versions,
        required_capability="operations.approval.decide",
        state="pending",
        expires_at=expires_at,
    )
    db.add(approval)
    db.flush()
    return tool_call, approval, run
