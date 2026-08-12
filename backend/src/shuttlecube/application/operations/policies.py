import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError, ConcurrentChange
from shuttlecube.application.operations.access import AccessDenied, require_capability
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.operations.schemas import OperationsPolicyConfig


class PolicyNotConfigured(LookupError):
    pass


class StalePolicy(RuntimeError):
    pass


def _authorize(scope: RequestScope) -> None:
    try:
        require_capability(scope, "operations.policy.manage")
    except AccessDenied as exc:
        raise BusinessError(403, "capability_denied", "没有管理运营策略的权限") from exc


def _normalized_config(config: OperationsPolicyConfig) -> dict[str, object]:
    return config.model_dump(mode="json")


def _config_hash(config: dict[str, object]) -> str:
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_policy_draft(
    db: Session,
    *,
    scope: RequestScope,
    schema_version: int,
    config: dict[str, object],
    name: str = "运营规则",
    policy_key: str = "default_operations",
) -> OperationsPolicy:
    _authorize(scope)
    if schema_version != 1:
        raise BusinessError(422, "unsupported_policy_schema", "不支持的策略 Schema 版本")
    validated = OperationsPolicyConfig.model_validate(config)
    normalized = _normalized_config(validated)
    current_version = db.scalar(
        select(func.max(OperationsPolicy.policy_version)).where(
            OperationsPolicy.venue_id == scope.venue_id,
            OperationsPolicy.policy_key == policy_key,
        )
    )
    policy = OperationsPolicy(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        name=name.strip(),
        policy_key=policy_key,
        policy_version=int(current_version or 0) + 1,
        schema_version=schema_version,
        config=normalized,
        config_hash=_config_hash(normalized),
        state="draft",
        effective_from=datetime.now(UTC),
        created_by=scope.user_id,
    )
    db.add(policy)
    db.flush()
    return policy


def get_policy(db: Session, *, scope: RequestScope, policy_id: str) -> OperationsPolicy:
    _authorize(scope)
    policy = db.scalar(
        select(OperationsPolicy).where(
            OperationsPolicy.id == policy_id,
            OperationsPolicy.organization_id == scope.organization_id,
            OperationsPolicy.venue_id == scope.venue_id,
        )
    )
    if policy is None:
        raise BusinessError(404, "scope_not_found", "运营规则版本不存在")
    return policy


def update_policy_draft(
    db: Session,
    *,
    scope: RequestScope,
    policy_id: str,
    name: str,
    config: dict[str, object],
    expected_version: int,
) -> OperationsPolicy:
    policy = get_policy(db, scope=scope, policy_id=policy_id)
    if policy.version != expected_version:
        raise ConcurrentChange()
    if policy.state != "draft":
        raise BusinessError(409, "policy_not_draft", "只有草稿版本可以编辑")
    validated = OperationsPolicyConfig.model_validate(config)
    normalized = _normalized_config(validated)
    policy.name = name.strip()
    policy.config = normalized
    policy.config_hash = _config_hash(normalized)
    db.flush()
    return policy


def copy_policy_as_draft(
    db: Session,
    *,
    scope: RequestScope,
    policy_id: str,
    name: str,
) -> OperationsPolicy:
    source = get_policy(db, scope=scope, policy_id=policy_id)
    return create_policy_draft(
        db,
        scope=scope,
        schema_version=source.schema_version,
        config=source.config,
        name=name,
        policy_key=source.policy_key,
    )


def delete_policy_draft(
    db: Session,
    *,
    scope: RequestScope,
    policy_id: str,
    expected_version: int,
) -> OperationsPolicy:
    policy = get_policy(db, scope=scope, policy_id=policy_id)
    if policy.version != expected_version:
        raise ConcurrentChange()
    if policy.state != "draft":
        raise BusinessError(409, "policy_not_draft", "生效或历史版本不能删除")
    db.delete(policy)
    db.flush()
    return policy


def activate_policy(
    db: Session,
    *,
    scope: RequestScope,
    policy_id: str,
    expected_version: int,
) -> OperationsPolicy:
    _authorize(scope)
    policy = db.scalar(
        select(OperationsPolicy)
        .where(
            OperationsPolicy.id == policy_id,
            OperationsPolicy.organization_id == scope.organization_id,
            OperationsPolicy.venue_id == scope.venue_id,
        )
        .with_for_update()
    )
    if policy is None:
        raise BusinessError(404, "scope_not_found", "策略不存在")
    if policy.version != expected_version:
        raise ConcurrentChange()
    if policy.state != "draft":
        raise BusinessError(409, "policy_not_draft", "只有草稿策略可以激活")
    now = datetime.now(UTC)
    active = list(
        db.scalars(
            select(OperationsPolicy)
            .where(
                OperationsPolicy.organization_id == scope.organization_id,
                OperationsPolicy.venue_id == scope.venue_id,
                OperationsPolicy.policy_key == policy.policy_key,
                OperationsPolicy.state == "active",
            )
            .with_for_update()
        ).all()
    )
    for previous in active:
        previous.state = "retired"
        previous.effective_to = now
    # Flush the retirement first. Migrated databases enforce one active policy
    # with a partial unique index, so activating both states in one unordered
    # ORM flush can otherwise violate that index.
    db.flush()
    policy.state = "active"
    policy.effective_from = now
    policy.activated_by = scope.user_id
    policy.activated_at = now
    db.flush()
    return policy


def get_active_policy(
    db: Session,
    *,
    scope: RequestScope,
    policy_key: str = "default_operations",
) -> OperationsPolicy:
    policy = db.scalar(
        select(OperationsPolicy).where(
            OperationsPolicy.organization_id == scope.organization_id,
            OperationsPolicy.venue_id == scope.venue_id,
            OperationsPolicy.policy_key == policy_key,
            OperationsPolicy.state == "active",
        )
    )
    if policy is None:
        raise PolicyNotConfigured(policy_key)
    return policy


def assert_policy_current(
    db: Session,
    *,
    scope: RequestScope,
    policy_key: str,
    policy_version: int,
    config_hash: str,
) -> OperationsPolicy:
    active = get_active_policy(db, scope=scope, policy_key=policy_key)
    if active.policy_version != policy_version or active.config_hash != config_hash:
        raise StalePolicy(policy_key)
    return active
