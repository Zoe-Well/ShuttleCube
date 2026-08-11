from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope, request_scope, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.operations.access import (
    capabilities_for_role,
    require_scope_capability,
)
from shuttlecube.application.operations.memberships import (
    set_venue_model_enabled,
    set_venue_runtime_settings,
    update_venue_membership,
)
from shuttlecube.config import Settings, get_settings
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(prefix="/operations", tags=["Operations Context"])


class ModelSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_enabled: bool
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


class MembershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "disabled"]
    role_key: Literal["owner", "operations_manager", "operator", "finance_viewer"]
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


class RuntimeSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations_enabled: bool
    write_tools_enabled: bool
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


def _model_setting(venue: Venue, settings: Settings) -> dict[str, object]:
    return {
        "model_enabled": venue.model_enabled,
        "provider_configured": bool(settings.openai_api_key),
        "enabled_by": venue.model_enabled_by,
        "enabled_at": venue.model_enabled_at,
        "updated_at": venue.updated_at,
        "version": venue.version,
    }


def _runtime_setting(venue: Venue) -> dict[str, object]:
    return {
        "operations_enabled": venue.active_for_operations,
        "write_tools_enabled": venue.write_tools_enabled,
        "updated_at": venue.updated_at,
        "version": venue.version,
    }


@router.get("/settings/runtime", operation_id="getOperationsRuntimeSetting")
def get_runtime_setting(
    scope: Annotated[RequestScope, Depends(request_scope)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    venue = db.get(Venue, scope.venue_id)
    if venue is None:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    return _runtime_setting(venue)


@router.patch("/settings/runtime", operation_id="updateOperationsRuntimeSetting")
def patch_runtime_setting(
    payload: RuntimeSettingUpdate,
    request: Request,
    scope: Annotated[
        RequestScope,
        Depends(require_scope_capability("operations.policy.manage")),
    ],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    venue = db.get(Venue, scope.venue_id)
    if venue is None:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    set_venue_runtime_settings(
        db,
        scope=scope,
        venue=venue,
        operations_enabled=payload.operations_enabled,
        write_tools_enabled=payload.write_tools_enabled,
        reason=payload.reason,
        expected_version=payload.expected_version,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    db.commit()
    db.refresh(venue)
    return _runtime_setting(venue)


def _membership_summary(
    membership: VenueMembership,
    organization_membership: OrganizationMembership,
    user: SystemUser,
) -> dict[str, object]:
    return {
        "id": membership.id,
        "user_id": user.id,
        "display_name": user.display_name,
        "status": membership.status,
        "role_key": membership.role_key,
        "capabilities": sorted(capabilities_for_role(membership.role_key)),
        "reviewed_by": organization_membership.reviewed_by,
        "reviewed_at": organization_membership.reviewed_at,
        "version": membership.version,
    }


@router.get("/settings/model", operation_id="getOperationsModelSetting")
def get_model_setting(
    scope: Annotated[RequestScope, Depends(request_scope)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    venue = db.get(Venue, scope.venue_id)
    if venue is None:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    return _model_setting(venue, settings)


@router.patch("/settings/model", operation_id="updateOperationsModelSetting")
def patch_model_setting(
    payload: ModelSettingUpdate,
    request: Request,
    scope: Annotated[
        RequestScope,
        Depends(require_scope_capability("operations.model.manage")),
    ],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    venue = db.get(Venue, scope.venue_id)
    if venue is None:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    set_venue_model_enabled(
        db,
        scope=scope,
        venue=venue,
        enabled=payload.model_enabled,
        reason=payload.reason,
        expected_version=payload.expected_version,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    db.commit()
    db.refresh(venue)
    return _model_setting(venue, settings)


@router.get("/memberships", operation_id="listOperationsMemberships")
def list_memberships(
    scope: Annotated[
        RequestScope,
        Depends(require_scope_capability("operations.membership.manage")),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, object]]:
    rows = db.execute(
        select(VenueMembership, OrganizationMembership, SystemUser)
        .join(
            OrganizationMembership,
            OrganizationMembership.id == VenueMembership.organization_membership_id,
        )
        .join(SystemUser, SystemUser.id == OrganizationMembership.user_id)
        .where(
            VenueMembership.organization_id == scope.organization_id,
            VenueMembership.venue_id == scope.venue_id,
        )
        .order_by(SystemUser.display_name, SystemUser.id)
    ).all()
    return [_membership_summary(*row) for row in rows]


@router.patch(
    "/memberships/{membership_id}",
    operation_id="updateOperationsMembership",
)
def patch_membership(
    membership_id: str,
    payload: MembershipUpdate,
    request: Request,
    scope: Annotated[
        RequestScope,
        Depends(require_scope_capability("operations.membership.manage")),
    ],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    del idempotency_key
    membership = db.get(VenueMembership, membership_id)
    if (
        membership is None
        or membership.organization_id != scope.organization_id
        or membership.venue_id != scope.venue_id
    ):
        raise BusinessError(404, "scope_not_found", "成员关系不存在")
    update_venue_membership(
        db,
        scope=scope,
        membership=membership,
        status=payload.status,
        role_key=payload.role_key,
        reason=payload.reason,
        expected_version=payload.expected_version,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    organization_membership = db.get(
        OrganizationMembership, membership.organization_membership_id
    )
    user = (
        db.get(SystemUser, organization_membership.user_id)
        if organization_membership is not None
        else None
    )
    if organization_membership is None or user is None:
        raise BusinessError(409, "membership_inconsistent", "成员关系数据不完整")
    if organization_membership.status == "pending_review":
        organization_membership.status = payload.status
        organization_membership.reviewed_by = scope.user_id
        organization_membership.reviewed_at = datetime.now().astimezone()
    db.commit()
    db.refresh(membership)
    return _membership_summary(membership, organization_membership, user)
