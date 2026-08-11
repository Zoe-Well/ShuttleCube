from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.config import Settings, get_settings
from shuttlecube.domain.identity.models import SystemUser, UserSession
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.database.session import get_db
from shuttlecube.infrastructure.security.sessions import token_hash


@dataclass(frozen=True, slots=True)
class RequestScope:
    organization_id: str
    venue_id: str
    user_id: str
    membership_id: str
    capabilities: frozenset[str]
    resolved_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def current_session(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_cookie: Annotated[str | None, Cookie(alias="shuttlecube_session")] = None,
) -> tuple[SystemUser, UserSession]:
    if not session_cookie:
        raise BusinessError(401, "unauthenticated", "请先登录")
    stored = db.query(UserSession).filter_by(token_hash=token_hash(session_cookie)).one_or_none()
    if not stored or _expired(stored.expires_at):
        raise BusinessError(401, "unauthenticated", "会话已过期")
    user = db.get(SystemUser, stored.user_id)
    if not user or not user.is_active:
        raise BusinessError(401, "unauthenticated", "账号不可用")
    request.state.user = user
    return user, stored


def require_csrf(
    pair: Annotated[tuple[SystemUser, UserSession], Depends(current_session)],
    csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> SystemUser:
    user, session = pair
    if not csrf or not secrets_compare(csrf, session.csrf_token):
        raise BusinessError(403, "csrf_failed", "安全校验失败，请刷新页面后重试")
    return user


def request_scope(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    pair: Annotated[tuple[SystemUser, UserSession], Depends(current_session)],
    venue_header: Annotated[str | None, Header(alias="X-Venue-Id")] = None,
) -> RequestScope:
    from shuttlecube.application.operations.access import capabilities_for_role

    user, _ = pair
    statement = (
        select(VenueMembership, OrganizationMembership, Organization, Venue)
        .join(
            OrganizationMembership,
            OrganizationMembership.id == VenueMembership.organization_membership_id,
        )
        .join(Organization, Organization.id == VenueMembership.organization_id)
        .join(Venue, Venue.id == VenueMembership.venue_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
            VenueMembership.status == "active",
            Organization.status == "active",
            Venue.organization_id == Organization.id,
        )
    )
    if venue_header:
        statement = statement.where(Venue.id == venue_header)
    rows = list(db.execute(statement).all())
    if not rows:
        pending = db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.status == "pending_review",
            )
        )
        code = "membership_review_required" if pending else "scope_not_found"
        detail = "成员关系尚待复核" if pending else "当前账号没有可用场馆范围"
        raise BusinessError(403, code, detail)
    if len(rows) > 1:
        raise BusinessError(409, "venue_selection_required", "请明确选择当前场馆")
    venue_membership, organization_membership, organization, venue = rows[0]
    if venue_membership.organization_id != organization_membership.organization_id:
        raise BusinessError(403, "scope_not_found", "成员范围不一致")
    scope = RequestScope(
        organization_id=organization.id,
        venue_id=venue.id,
        user_id=user.id,
        membership_id=venue_membership.id,
        capabilities=capabilities_for_role(venue_membership.role_key),
    )
    request.state.scope = scope
    return scope


def secrets_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


def _expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)
