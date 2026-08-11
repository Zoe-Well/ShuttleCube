from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.operations.access import AccessDenied, require_capability
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.application.operations.policies import PolicyNotConfigured, get_active_policy
from shuttlecube.application.operations.state_machine import transition_case, transition_run
from shuttlecube.application.operations.tools import ToolRegistry
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.operations.models import (
    OperationApproval,
    OperationCase,
    OperationRun,
    OperationToolCall,
)


def _mark_stale(
    approval: OperationApproval,
    tool_call: OperationToolCall,
    run: OperationRun,
    case: OperationCase | None,
    *,
    reason: str,
) -> None:
    approval.state = "stale"
    approval.decision_reason = reason
    approval.decided_at = datetime.now(UTC)
    tool_call.state = "stale"
    tool_call.error_code = reason
    if run.state == "waiting_approval":
        transition_run(run, "cancelled")
    if case is not None and case.state == "waiting_approval":
        transition_case(case, "waiting_human")


def _record_terminal_conflict(
    db: Session,
    *,
    scope: RequestScope,
    approval: OperationApproval,
    tool_call: OperationToolCall,
    request_id: str,
    state: str,
    reason: str,
) -> None:
    record_audit(
        db,
        actor_id=scope.user_id,
        action=f"operation_approval.{state}",
        entity_type="operation_approval",
        entity_id=approval.id,
        request_id=request_id,
        before={"state": "pending", "input_hash": approval.input_hash},
        after={"state": state, "tool_call_id": tool_call.id, "tool_state": tool_call.state},
        reason=reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.flush()


def decide_approval(
    db: Session,
    *,
    scope: RequestScope,
    approval: OperationApproval,
    approve: bool,
    expected_version: int,
    expected_input_hash: str,
    reason: str,
    request_id: str,
) -> tuple[OperationApproval, OperationRun | None]:
    try:
        require_capability(scope, "operations.approval.decide")
    except AccessDenied as exc:
        raise BusinessError(403, "capability_denied", "没有审批补排方案的权限") from exc
    if approval.organization_id != scope.organization_id or approval.venue_id != scope.venue_id:
        raise BusinessError(404, "scope_not_found", "审批不存在")
    target_state = "approved" if approve else "rejected"
    tool_call = db.scalar(
        select(OperationToolCall).where(
            OperationToolCall.id == approval.tool_call_id,
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
        )
    )
    if tool_call is None:
        raise BusinessError(409, "tool_call_missing", "审批对应的工具调用不存在")
    run = db.scalar(
        select(OperationRun).where(
            OperationRun.id == tool_call.run_id,
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
        )
    )
    if run is None:
        raise BusinessError(409, "run_missing", "审批对应的运行不存在")
    case = (
        db.scalar(
            select(OperationCase).where(
                OperationCase.id == approval.case_id,
                OperationCase.organization_id == scope.organization_id,
                OperationCase.venue_id == scope.venue_id,
            )
        )
        if approval.case_id
        else None
    )
    if approval.state == target_state and approval.input_hash == expected_input_hash:
        return approval, run if approve else None
    if approval.state != "pending":
        raise BusinessError(409, "approval_not_pending", "审批已处理或已失效")
    if approval.version != expected_version:
        raise BusinessError(409, "concurrent_change", "审批已被其他人员更新")
    if approval.input_hash != expected_input_hash or tool_call.input_hash != expected_input_hash:
        _mark_stale(approval, tool_call, run, case, reason="input_hash_changed")
        _record_terminal_conflict(
            db,
            scope=scope,
            approval=approval,
            tool_call=tool_call,
            request_id=request_id,
            state="stale",
            reason="input_hash_changed",
        )
        raise BusinessError(409, "approval_stale", "审批内容已变化")
    now = datetime.now(UTC)
    expires_at = approval.expires_at if approval.expires_at.tzinfo else approval.expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        approval.state = "expired"
        approval.decided_at = now
        approval.decision_reason = "approval_expired"
        tool_call.state = "stale"
        if run.state == "waiting_approval":
            transition_run(run, "cancelled", now=now)
        if case is not None and case.state == "waiting_approval":
            transition_case(case, "waiting_human", now=now)
        _record_terminal_conflict(
            db,
            scope=scope,
            approval=approval,
            tool_call=tool_call,
            request_id=request_id,
            state="expired",
            reason="approval_expired",
        )
        raise BusinessError(409, "approval_expired", "审批已过期")
    try:
        active_policy = get_active_policy(db, scope=scope, policy_key=approval.policy_key)
    except PolicyNotConfigured as exc:
        _mark_stale(approval, tool_call, run, case, reason="policy_missing")
        _record_terminal_conflict(
            db,
            scope=scope,
            approval=approval,
            tool_call=tool_call,
            request_id=request_id,
            state="stale",
            reason="policy_missing",
        )
        raise BusinessError(409, "approval_stale", "运营规则已失效") from exc
    definition = ToolRegistry.default().get(tool_call.tool_key)
    session_id = str(tool_call.normalized_input.get("cancelled_session_id", ""))
    session = db.scalar(
        select(ClassSession).where(
            ClassSession.id == session_id,
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
        )
    )
    stale = (
        active_policy.policy_version != approval.policy_version
        or definition.tool_version != tool_call.tool_version
        or approval.subject_versions != tool_call.subject_versions
        or canonical_hash(approval.impact_snapshot) != canonical_hash(tool_call.impact_snapshot)
        or case is None
        or case.version != int(tool_call.subject_versions.get("operation_case", -1))
        or session is None
        or session.version != int(tool_call.subject_versions.get("class_session", -1))
        or session.status != "cancelled"
        or session.replacement_decision != "pending"
    )
    if stale:
        _mark_stale(approval, tool_call, run, case, reason="subject_or_policy_changed")
        _record_terminal_conflict(
            db,
            scope=scope,
            approval=approval,
            tool_call=tool_call,
            request_id=request_id,
            state="stale",
            reason="subject_or_policy_changed",
        )
        raise BusinessError(409, "approval_stale", "业务事实或规则已变化，请重新生成方案")

    approval.state = target_state
    approval.decided_by = scope.user_id
    approval.decision_reason = reason.strip()
    approval.decided_at = now
    if approve:
        tool_call.state = "approved"
        transition_run(run, "queued", now=now)
    else:
        tool_call.state = "cancelled"
        transition_run(run, "cancelled", now=now)
        if case.state == "waiting_approval":
            transition_case(case, "waiting_human", now=now)
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operation_approval.approved" if approve else "operation_approval.rejected",
        entity_type="operation_approval",
        entity_id=approval.id,
        request_id=request_id,
        before={"state": "pending", "input_hash": approval.input_hash},
        after={"state": approval.state, "tool_call_id": tool_call.id},
        reason=reason.strip(),
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.flush()
    return approval, run if approve else None
