from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import VenueScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class PrivateLessonPackage(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "private_lesson_packages"
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    bound_coach_id: Mapped[str] = mapped_column(String(36), index=True)
    purchased_units: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    actual_receivable: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrivateLesson(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "private_lessons"
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    coach_id: Mapped[str] = mapped_column(String(36), index=True)
    package_id: Mapped[str | None] = mapped_column(
        ForeignKey("private_lesson_packages.id"), nullable=True
    )
    billing_mode: Mapped[str] = mapped_column(String(20))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_receivable: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    coach_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="booked", index=True)
    schedule_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("schedule_entries.id"), nullable=True
    )
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
