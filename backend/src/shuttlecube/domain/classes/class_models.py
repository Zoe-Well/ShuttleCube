from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import VenueScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class FixedClass(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "fixed_classes"
    name: Mapped[str] = mapped_column(String(160), index=True)
    class_type: Mapped[str] = mapped_column(String(80))
    age_or_level: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recurrence_rule: Mapped[str] = mapped_column(String(200), default="FREQ=WEEKLY")
    start_date: Mapped[date] = mapped_column(Date)
    default_start_time: Mapped[time] = mapped_column(Time)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    session_count: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)
    default_coach_id: Mapped[str] = mapped_column(String(36), index=True)
    required_court_count: Mapped[int] = mapped_column(Integer, default=1)
    student_unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    coach_fee_per_session: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClassSession(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "class_sessions"
    fixed_class_id: Mapped[str] = mapped_column(ForeignKey("fixed_classes.id"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_coach_id: Mapped[str] = mapped_column(String(36))
    coach_fee_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", index=True)
    replacement_for_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("class_sessions.id"), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    replacement_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    attendance_finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    schedule_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("schedule_entries.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "fixed_class_id",
            "sequence_number",
            name="uq_class_session_scope_sequence",
        ),
    )
