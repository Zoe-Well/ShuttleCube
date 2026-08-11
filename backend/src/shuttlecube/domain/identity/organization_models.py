from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class Organization(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')", name="ck_organization_status"),
    )


class OrganizationMembership(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "organization_memberships"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("system_users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending_review", index=True)
    organization_role: Mapped[str] = mapped_column(String(20), default="member")
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_membership_user"
        ),
        CheckConstraint(
            "status IN ('pending_review', 'active', 'disabled')",
            name="ck_organization_membership_status",
        ),
        CheckConstraint(
            "organization_role IN ('owner', 'admin', 'member')",
            name="ck_organization_membership_role",
        ),
    )


class VenueMembership(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "venue_memberships"
    organization_membership_id: Mapped[str] = mapped_column(
        ForeignKey("organization_memberships.id", ondelete="RESTRICT"), index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    role_key: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="pending_review", index=True)
    __table_args__ = (
        UniqueConstraint(
            "organization_membership_id", "venue_id", name="uq_venue_membership_member"
        ),
        CheckConstraint(
            "role_key IN ('owner', 'operations_manager', 'operator', 'finance_viewer')",
            name="ck_venue_membership_role",
        ),
        CheckConstraint(
            "status IN ('pending_review', 'active', 'disabled')",
            name="ck_venue_membership_status",
        ),
    )
