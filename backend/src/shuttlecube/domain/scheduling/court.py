from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class Venue(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "venues"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), default="ShuttleCube 羽毛球馆")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    weekday_open_time: Mapped[time] = mapped_column(Time, default=lambda: time(14, 0))
    weekday_close_time: Mapped[time] = mapped_column(Time, default=lambda: time(22, 0))
    weekend_open_time: Mapped[time] = mapped_column(Time, default=lambda: time(8, 0))
    weekend_close_time: Mapped[time] = mapped_column(Time, default=lambda: time(22, 0))
    active_for_operations: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    write_tools_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    model_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    model_enabled_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Court(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "courts"
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("venue_id", "code", name="uq_court_venue_code"),)
