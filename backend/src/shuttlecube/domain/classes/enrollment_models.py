from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import VenueScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class Enrollment(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "enrollments"
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    fixed_class_id: Mapped[str] = mapped_column(ForeignKey("fixed_classes.id"), index=True)
    enrolled_on: Mapped[date] = mapped_column(Date)
    purchased_units: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    suggested_receivable: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    actual_receivable: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_midterm: Mapped[bool] = mapped_column(Boolean, default=False)
    price_adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    acquisition_type: Mapped[str] = mapped_column(String(30), default="purchase")
    source_enrollment_id: Mapped[str | None] = mapped_column(
        ForeignKey("enrollments.id"), nullable=True
    )
    transferred_to_enrollment_id: Mapped[str | None] = mapped_column(
        ForeignKey("enrollments.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class LessonUnitLedger(VenueScopeMixin, IdMixin, Base):
    __tablename__ = "lesson_unit_ledgers"
    owner_type: Mapped[str] = mapped_column(String(30), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    change_type: Mapped[str] = mapped_column(String(40))
    delta: Mapped[int] = mapped_column(Integer)
    balance_before: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="effective")
    reversal_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("lesson_unit_ledgers.id"), nullable=True
    )
    operated_by: Mapped[str] = mapped_column(String(36))
    operated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)


class AttendanceRecord(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "attendance_records"
    class_session_id: Mapped[str] = mapped_column(ForeignKey("class_sessions.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("enrollments.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="present")
    deduct_units: Mapped[int] = mapped_column(Integer, default=1)
    grants_makeup: Mapped[bool] = mapped_column(Boolean, default=False)
    lesson_ledger_id: Mapped[str | None] = mapped_column(
        ForeignKey("lesson_unit_ledgers.id"), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "class_session_id",
            "student_id",
            name="uq_attendance_scope_session_student",
        ),
    )


class MakeupRecord(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "makeup_records"
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    origin_attendance_id: Mapped[str] = mapped_column(
        ForeignKey("attendance_records.id"), unique=True
    )
    target_class_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("class_sessions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    deduct_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
