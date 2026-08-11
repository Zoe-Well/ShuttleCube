from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import OrganizationScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class Student(OrganizationScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "students"
    name: Mapped[str] = mapped_column(String(120), index=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    level_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Guardian(OrganizationScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "guardians"
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32), index=True)
    wechat_note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class StudentGuardian(OrganizationScopeMixin, Base):
    __tablename__ = "student_guardians"
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), primary_key=True
    )
    guardian_id: Mapped[str] = mapped_column(
        ForeignKey("guardians.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_label: Mapped[str] = mapped_column(String(40))
    is_primary_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("student_id", "guardian_id"),)


class WalkInCustomer(OrganizationScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "walk_in_customers"
    display_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    wechat_note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
