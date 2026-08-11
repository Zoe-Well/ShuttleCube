from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import VenueScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class CoachFee(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "coach_fees"
    coach_id: Mapped[str] = mapped_column(String(36), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    settlement_id: Mapped[str | None] = mapped_column(
        ForeignKey("payroll_settlements.id"), nullable=True, index=True
    )
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "source_type",
            "source_id",
            "coach_id",
            name="uq_coach_fee_scope_source",
        ),
    )


class PayrollSettlement(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "payroll_settlements"
    coach_id: Mapped[str] = mapped_column(String(36), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    calculated_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    settled_by: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="confirmed", index=True)
    expense_id: Mapped[str] = mapped_column(ForeignKey("expenses.id"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    __table_args__ = (
        Index(
            "uq_payroll_confirmed_coach_month",
            "coach_id",
            "period_start",
            unique=True,
            sqlite_where=text("status = 'confirmed'"),
            postgresql_where=text("status = 'confirmed'"),
        ),
    )
