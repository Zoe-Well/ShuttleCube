from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.operations.access import (
    AccessDenied,
    capabilities_for_role,
    require_capability,
)
from shuttlecube.domain.identity.organization_models import (
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.operations.models import OperationCase


def _assignable_user(
    db: Session,
    *,
    scope: RequestScope,
    user_id: str,
    required_capability: str,
) -> None:
    membership = db.scalar(
        select(VenueMembership)
        .join(
            OrganizationMembership,
            OrganizationMembership.id == VenueMembership.organization_membership_id,
        )
        .where(
            VenueMembership.organization_id == scope.organization_id,
            VenueMembership.venue_id == scope.venue_id,
            VenueMembership.status == "active",
            OrganizationMembership.organization_id == scope.organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
    )
    if membership is None or required_capability not in capabilities_for_role(
        membership.role_key
    ):
        raise BusinessError(422, "invalid_assignee", "所选人员不能处理该工作队列")


def assign_case(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    assignee_user_id: str,
    expected_version: int,
    request_id: str,
    self_claim: bool = False,
    reason: str | None = None,
) -> OperationCase:
    if case.organization_id != scope.organization_id or case.venue_id != scope.venue_id:
        raise BusinessError(404, "scope_not_found", "运营案件不存在")
    if case.version != expected_version:
        raise BusinessError(409, "concurrent_change", "案件已被其他人员更新")
    if case.state in {"resolved", "dismissed"}:
        raise BusinessError(409, "case_closed", "已关闭案件不能分配")
    if self_claim:
        if assignee_user_id != scope.user_id:
            raise BusinessError(422, "invalid_assignee", "认领人必须是当前用户")
        capability = case.required_capability
    else:
        capability = "operations.case.assign"
    try:
        require_capability(scope, capability)
    except AccessDenied as exc:
        raise BusinessError(403, "capability_denied", "没有分配该案件的权限") from exc
    _assignable_user(
        db,
        scope=scope,
        user_id=assignee_user_id,
        required_capability=case.required_capability,
    )
    before = case.assigned_to
    case.assigned_to = assignee_user_id
    case.assigned_at = datetime.now(UTC)
    case.assigned_by = scope.user_id
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operation_case.claimed" if self_claim else "operation_case.assigned",
        entity_type="operation_case",
        entity_id=case.id,
        request_id=request_id,
        before={"assigned_to": before},
        after={"assigned_to": assignee_user_id},
        reason=reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.flush()
    return case
