from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import VenueScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class TemporaryEvent(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "temporary_events"
    event_type: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(160))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    court_ids_csv: Mapped[str] = mapped_column(Text)
    coach_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    coach_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    suggested_receivable: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    actual_receivable: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    expense_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    track_participants: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_attendance: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="confirmed", index=True)
    schedule_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("schedule_entries.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventParticipant(VenueScopeMixin, IdMixin, Base):
    __tablename__ = "event_participants"
    event_id: Mapped[str] = mapped_column(
        ForeignKey("temporary_events.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    attendance_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
