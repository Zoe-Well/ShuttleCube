from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import OrganizationScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class CoachProfile(OrganizationScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "coach_profiles"
    name: Mapped[str] = mapped_column(String(120), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    specialties: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CoachRate(OrganizationScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "coach_rates"
    coach_id: Mapped[str] = mapped_column(ForeignKey("coach_profiles.id"), index=True)
    business_type: Mapped[str] = mapped_column(String(40), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "coach_id", "business_type", "effective_from", name="uq_coach_rate_effective"
        ),
    )
