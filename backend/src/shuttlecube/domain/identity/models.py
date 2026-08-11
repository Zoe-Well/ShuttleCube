from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class SystemUser(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "system_users"
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("system_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
