from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.config import Settings
from shuttlecube.domain.identity.models import SystemUser, UserSession
from shuttlecube.infrastructure.security.passwords import verify_password
from shuttlecube.infrastructure.security.sessions import SessionTokens, issue_tokens, token_hash


def login(
    db: Session, settings: Settings, username: str, password: str
) -> tuple[SystemUser, SessionTokens]:
    user = db.query(SystemUser).filter_by(username=username).one_or_none()
    if not user or not user.is_active or not verify_password(user.password_hash, password):
        raise BusinessError(401, "invalid_credentials", "用户名或密码错误")
    tokens = issue_tokens()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_hash(tokens.session),
            csrf_token=tokens.csrf,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        )
    )
    db.commit()
    return user, tokens


def logout(db: Session, stored: UserSession) -> None:
    db.delete(stored)
    db.commit()
