from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import VenueScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, utc_now


class AuditLog(VenueScopeMixin, IdMixin, Base):
    __tablename__ = "audit_logs"
    actor_user_id: Mapped[str] = mapped_column(String(36), index=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    before_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    after_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
