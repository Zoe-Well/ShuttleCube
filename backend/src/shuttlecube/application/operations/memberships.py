from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError, ConcurrentChange
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
from shuttlecube.domain.scheduling.court import Venue


def _authorize(scope: RequestScope, capability: str) -> None:
    try:
        require_capability(scope, capability)
    except AccessDenied as exc:
        raise PermissionError(str(exc)) from exc


def review_organization_membership(
    db: Session,
    *,
    scope: RequestScope,
    membership: OrganizationMembership,
    status: str,
    organization_role: str,
    reason: str,
    expected_version: int,
    request_id: str = "operations-membership",
) -> OrganizationMembership:
    _authorize(scope, "operations.membership.manage")
    if membership.organization_id != scope.organization_id:
        raise BusinessError(404, "scope_not_found", "成员关系不存在")
    if membership.version != expected_version:
        raise ConcurrentChange()
    if status not in {"active", "disabled"}:
        raise BusinessError(422, "invalid_membership_status", "复核结果必须是启用或停用")
    if organization_role not in {"owner", "admin", "member"}:
        raise BusinessError(422, "invalid_organization_role", "组织角色无效")
    before: dict[str, object] = {
        "status": membership.status,
        "organization_role": membership.organization_role,
    }
    membership.status = status
    membership.organization_role = organization_role
    membership.reviewed_by = scope.user_id
    membership.reviewed_at = datetime.now(UTC)
    record_audit(
        db,
        actor_id=scope.user_id,
        action="organization_membership.reviewed",
        entity_type="organization_membership",
        entity_id=membership.id,
        request_id=request_id,
        before=before,
        after={"status": status, "organization_role": organization_role},
        reason=reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    return membership


def update_venue_membership(
    db: Session,
    *,
    scope: RequestScope,
    membership: VenueMembership,
    status: str,
    role_key: str,
    reason: str,
    expected_version: int,
    request_id: str = "operations-membership",
) -> VenueMembership:
    _authorize(scope, "operations.membership.manage")
    if (
        membership.organization_id != scope.organization_id
        or membership.venue_id != scope.venue_id
    ):
        raise BusinessError(404, "scope_not_found", "场馆成员关系不存在")
    if membership.version != expected_version:
        raise ConcurrentChange()
    if status not in {"active", "disabled"}:
        raise BusinessError(422, "invalid_membership_status", "成员状态无效")
    capabilities_for_role(role_key)
    before: dict[str, object] = {
        "status": membership.status,
        "role_key": membership.role_key,
    }
    membership.status = status
    membership.role_key = role_key
    organization_membership = db.get(
        OrganizationMembership, membership.organization_membership_id
    )
    if organization_membership is None:
        raise BusinessError(409, "membership_inconsistent", "成员关系数据不完整")
    allowed_capabilities = capabilities_for_role(role_key) if status == "active" else frozenset()
    assigned_cases = db.scalars(
        select(OperationCase).where(
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
            OperationCase.assigned_to == organization_membership.user_id,
            OperationCase.state.not_in(("resolved", "dismissed", "cancelled")),
        )
    ).all()
    for case in assigned_cases:
        if case.required_capability in allowed_capabilities:
            continue
        case.assigned_to = None
        case.assigned_at = None
        case.assigned_by = None
        record_audit(
            db,
            actor_id=scope.user_id,
            action="operation_case.requeued_after_membership_change",
            entity_type="operation_case",
            entity_id=case.id,
            request_id=request_id,
            before={"assigned_to": organization_membership.user_id},
            after={"assigned_to": None, "queue_key": case.queue_key},
            reason=reason,
            organization_id=scope.organization_id,
            venue_id=scope.venue_id,
        )
    record_audit(
        db,
        actor_id=scope.user_id,
        action="venue_membership.updated",
        entity_type="venue_membership",
        entity_id=membership.id,
        request_id=request_id,
        before=before,
        after={"status": status, "role_key": role_key},
        reason=reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    return membership


def set_venue_model_enabled(
    db: Session,
    *,
    scope: RequestScope,
    venue: Venue,
    enabled: bool,
    reason: str,
    expected_version: int,
    request_id: str = "operations-model-setting",
) -> Venue:
    _authorize(scope, "operations.model.manage")
    if venue.id != scope.venue_id or venue.organization_id != scope.organization_id:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    if venue.version != expected_version:
        raise ConcurrentChange()
    before: dict[str, object] = {"model_enabled": venue.model_enabled}
    venue.model_enabled = enabled
    venue.model_enabled_by = scope.user_id
    venue.model_enabled_at = datetime.now(UTC)
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.model_enabled" if enabled else "operations.model_disabled",
        entity_type="venue",
        entity_id=venue.id,
        request_id=request_id,
        before=before,
        after={"model_enabled": enabled},
        reason=reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    return venue


def set_venue_runtime_settings(
    db: Session,
    *,
    scope: RequestScope,
    venue: Venue,
    operations_enabled: bool,
    write_tools_enabled: bool,
    reason: str,
    expected_version: int,
    request_id: str = "operations-runtime-setting",
) -> Venue:
    _authorize(scope, "operations.policy.manage")
    if venue.id != scope.venue_id or venue.organization_id != scope.organization_id:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    if venue.version != expected_version:
        raise ConcurrentChange()
    if write_tools_enabled and not operations_enabled:
        raise BusinessError(
            422,
            "operations_required_for_write_tools",
            "启用写工具前必须先启用智能运营",
        )
    before: dict[str, object] = {
        "active_for_operations": venue.active_for_operations,
        "write_tools_enabled": venue.write_tools_enabled,
    }
    venue.active_for_operations = operations_enabled
    venue.write_tools_enabled = write_tools_enabled
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.runtime_settings_updated",
        entity_type="venue",
        entity_id=venue.id,
        request_id=request_id,
        before=before,
        after={
            "active_for_operations": operations_enabled,
            "write_tools_enabled": write_tools_enabled,
        },
        reason=reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    return venue
