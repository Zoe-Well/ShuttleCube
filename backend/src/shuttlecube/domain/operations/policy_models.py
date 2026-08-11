from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class OperationsPolicy(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "operations_policies"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    policy_key: Mapped[str] = mapped_column(String(80), default="default_operations")
    policy_version: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict[str, object]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36))
    activated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "policy_key",
            "policy_version",
            name="uq_operations_policy_version",
        ),
        CheckConstraint(
            "state IN ('draft', 'active', 'retired')",
            name="ck_operations_policy_state",
        ),
    )
