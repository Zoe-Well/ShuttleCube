import os
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope, request_scope, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
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
from shuttlecube.infrastructure.ai.credentials import (
    PROVIDER_DEFAULTS,
    CredentialStorageUnavailable,
    CredentialValidationFailed,
    DesktopOpenAICredentialStore,
    ModelProviderConfiguration,
    credential_store,
    normalize_provider_configuration,
    resolve_model_provider,
    validate_model_provider,
)
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(prefix="/operations", tags=["Operations Context"])


class ModelSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_enabled: bool
    reason: str | None = Field(default=None, min_length=1, max_length=500)
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
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


class ModelCredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai", "deepseek", "custom"]
    base_url: str = Field(min_length=8, max_length=500)
    api_mode: Literal["responses", "chat_completions"]
    model_profile: str = Field(min_length=1, max_length=120)
    api_key: SecretStr = Field(min_length=8, max_length=500)


class ModelSetting(BaseModel):
    model_enabled: bool
    provider_configured: bool
    provider_editable: bool
    provider_source: Literal["desktop", "environment"] | None
    provider_verified_at: datetime | None
    provider_key: Literal["openai", "deepseek", "custom"]
    provider_label: str
    provider_base_url: str
    provider_api_mode: Literal["responses", "chat_completions"]
    provider_model_profile: str
    enabled_by: str | None = None
    enabled_at: datetime | None = None
    updated_at: datetime
    version: int


class RuntimeSetting(BaseModel):
    operations_enabled: bool
    write_tools_enabled: bool
    updated_at: datetime
    version: int


def _model_setting(venue: Venue, settings: Settings) -> dict[str, object]:
    store = credential_store(settings)
    stored = store is not None and store.exists()
    metadata = store.metadata() if stored and store is not None else None
    environment_configured = settings.openai_api_key is not None
    defaults = PROVIDER_DEFAULTS.get(settings.operations_model_provider)
    provider = metadata.provider if metadata else settings.operations_model_provider
    base_url = metadata.base_url if metadata else (
        settings.operations_model_base_url or (defaults[0] if defaults else "")
    )
    api_mode = metadata.api_mode if metadata else (
        defaults[1] if defaults else settings.operations_model_api_mode
    )
    model_profile = metadata.model_profile if metadata else settings.operations_model_profile
    return {
        "model_enabled": venue.model_enabled,
        "provider_configured": stored or environment_configured,
        "provider_editable": store is not None and os.name == "nt",
        "provider_source": "desktop" if stored else "environment" if environment_configured else None,
        "provider_verified_at": metadata.verified_at if metadata else None,
        "provider_key": provider,
        "provider_label": {
            "openai": "OpenAI",
            "deepseek": "DeepSeek",
            "custom": "其他兼容服务",
        }[provider],
        "provider_base_url": base_url,
        "provider_api_mode": api_mode,
        "provider_model_profile": model_profile,
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


@router.get(
    "/settings/runtime",
    operation_id="getOperationsRuntimeSetting",
    response_model=RuntimeSetting,
)
def get_runtime_setting(
    scope: Annotated[RequestScope, Depends(request_scope)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    venue = db.get(Venue, scope.venue_id)
    if venue is None:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    return _runtime_setting(venue)


@router.patch(
    "/settings/runtime",
    operation_id="updateOperationsRuntimeSetting",
    response_model=RuntimeSetting,
)
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
        reason=payload.reason or (
            "用户通过运营设置开启可执行模式"
            if payload.write_tools_enabled
            else "用户通过运营设置开启自动发现模式"
            if payload.operations_enabled
            else "用户通过运营设置关闭智能运营"
        ),
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


@router.get(
    "/settings/model",
    operation_id="getOperationsModelSetting",
    response_model=ModelSetting,
)
def get_model_setting(
    scope: Annotated[RequestScope, Depends(request_scope)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    venue = db.get(Venue, scope.venue_id)
    if venue is None:
        raise BusinessError(404, "scope_not_found", "场馆不存在")
    return _model_setting(venue, settings)


@router.patch(
    "/settings/model",
    operation_id="updateOperationsModelSetting",
    response_model=ModelSetting,
)
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
    if payload.model_enabled and resolve_model_provider(settings) is None:
        raise BusinessError(422, "model_provider_not_configured", "请先配置并验证 API Key")
    set_venue_model_enabled(
        db,
        scope=scope,
        venue=venue,
        enabled=payload.model_enabled,
        reason=payload.reason or (
            "用户通过运营设置开启 AI 服务"
            if payload.model_enabled
            else "用户通过运营设置关闭 AI 服务"
        ),
        expected_version=payload.expected_version,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    db.commit()
    db.refresh(venue)
    return _model_setting(venue, settings)


def _editable_store(settings: Settings) -> DesktopOpenAICredentialStore:
    store = credential_store(settings)
    if store is None or os.name != "nt":
        raise BusinessError(
            403,
            "credential_editing_desktop_only",
            "服务器版 API Key 由部署环境统一配置",
        )
    return store


@router.put(
    "/settings/model/credential",
    operation_id="configureOperationsModelCredential",
    response_model=ModelSetting,
)
def configure_model_credential(
    payload: ModelCredentialUpdate,
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
    store = _editable_store(settings)
    was_configured = store.exists() or settings.openai_api_key is not None
    try:
        provider, base_url, api_mode, model_profile = normalize_provider_configuration(
            provider=payload.provider,
            base_url=payload.base_url,
            api_mode=payload.api_mode,
            model_profile=payload.model_profile,
        )
        configuration = ModelProviderConfiguration(
            api_key=payload.api_key,
            provider=provider,
            base_url=base_url,
            api_mode=api_mode,
            model_profile=model_profile,
        )
        verified_at = validate_model_provider(configuration, settings)
        store.save(
            payload.api_key,
            provider=provider,
            base_url=base_url,
            api_mode=api_mode,
            model_profile=model_profile,
            verified_at=verified_at,
        )
    except ValueError as exc:
        raise BusinessError(422, "invalid_provider_configuration", str(exc)) from exc
    except CredentialValidationFailed as exc:
        raise BusinessError(422, exc.code, str(exc)) from exc
    except CredentialStorageUnavailable as exc:
        raise BusinessError(503, "credential_storage_unavailable", "无法安全保存 API Key") from exc
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.model_credential_configured",
        entity_type="venue",
        entity_id=venue.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        before={"provider_configured": was_configured},
        after={
            "provider_configured": True,
            "provider": provider,
            "base_url": base_url,
            "api_mode": api_mode,
            "model_profile": model_profile,
            "verified_at": verified_at.isoformat(),
        },
        reason="用户在桌面版验证并保存 AI 服务凭据",
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.commit()
    return _model_setting(venue, settings)


@router.delete(
    "/settings/model/credential",
    operation_id="deleteOperationsModelCredential",
    response_model=ModelSetting,
)
def delete_model_credential(
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
    store = _editable_store(settings)
    store.delete()
    if venue.model_enabled:
        set_venue_model_enabled(
            db,
            scope=scope,
            venue=venue,
            enabled=False,
            reason="移除 API Key 时自动关闭 AI 服务",
            expected_version=venue.version,
            request_id=str(getattr(request.state, "request_id", "unknown")),
        )
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operations.model_credential_removed",
        entity_type="venue",
        entity_id=venue.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
        before={"provider_configured": True},
        after={"provider_configured": bool(settings.openai_api_key)},
        reason="用户在桌面版移除 AI 服务凭据",
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
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
