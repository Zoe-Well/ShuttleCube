from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class OperationsPolicy(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "operations_policies"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(80), default="运营规则")
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
        Index(
            "uq_operations_policy_active",
            "venue_id",
            "policy_key",
            unique=True,
            sqlite_where=text("state = 'active'"),
            postgresql_where=text("state = 'active'"),
        ),
    )
