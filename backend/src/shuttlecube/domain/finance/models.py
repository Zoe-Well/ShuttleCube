from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import OrganizationScopeMixin, VenueScopeMixin
from shuttlecube.infrastructure.database.base import (
    Base,
    IdMixin,
    TimestampMixin,
    VersionMixin,
    utc_now,
)


class Receivable(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "receivables"
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    suggested_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    __table_args__ = (
        UniqueConstraint(
            "venue_id", "source_type", "source_id", name="uq_receivable_scope_source"
        ),
    )


class Payment(VenueScopeMixin, IdMixin, Base):
    __tablename__ = "payments"
    receivable_id: Mapped[str] = mapped_column(ForeignKey("receivables.id"), index=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(40))
    payer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    received_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    operated_by: Mapped[str] = mapped_column(String(36), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="effective", index=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)


class Refund(VenueScopeMixin, IdMixin, Base):
    __tablename__ = "refunds"
    receivable_id: Mapped[str] = mapped_column(ForeignKey("receivables.id"), index=True)
    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    refunded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    suggested_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(Text)
    operated_by: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="effective", index=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)


class Expense(VenueScopeMixin, IdMixin, TimestampMixin, Base):
    __tablename__ = "expenses"
    category: Mapped[str] = mapped_column(String(40), index=True)
    spent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payee: Mapped[str] = mapped_column(String(160))
    payment_method: Mapped[str] = mapped_column(String(40))
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    operated_by: Mapped[str] = mapped_column(String(36), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="effective", index=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    __table_args__ = (Index("ix_expense_source", "source_type", "source_id"),)


class OtherIncome(VenueScopeMixin, IdMixin, TimestampMixin, Base):
    __tablename__ = "other_incomes"
    category: Mapped[str] = mapped_column(String(80), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payer: Mapped[str] = mapped_column(String(160))
    payment_method: Mapped[str] = mapped_column(String(40))
    operated_by: Mapped[str] = mapped_column(String(36), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="effective", index=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)


class Attachment(OrganizationScopeMixin, IdMixin, Base):
    __tablename__ = "attachments"
    owner_type: Mapped[str] = mapped_column(String(40), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    storage_key: Mapped[str] = mapped_column(String(240), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int]
    uploaded_by: Mapped[str] = mapped_column(String(36), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    deleted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_attachment_owner", "owner_type", "owner_id"),)
