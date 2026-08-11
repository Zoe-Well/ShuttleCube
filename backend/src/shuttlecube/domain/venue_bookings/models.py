from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.domain.scope import VenueScopeMixin
from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin, VersionMixin


class VenuePriceRule(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "venue_price_rules"
    name: Mapped[str] = mapped_column(String(120))
    day_type: Mapped[str] = mapped_column(String(20), default="weekday")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    time_start: Mapped[time] = mapped_column(Time)
    time_end: Mapped[time] = mapped_column(Time)
    price_per_court_hour: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class VenueBooking(VenueScopeMixin, IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "venue_bookings"
    customer_id: Mapped[str] = mapped_column(ForeignKey("walk_in_customers.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    court_ids_csv: Mapped[str] = mapped_column(Text)
    price_rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("venue_price_rules.id"), nullable=True
    )
    suggested_receivable: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    actual_receivable: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_status: Mapped[str] = mapped_column(String(30), default="unpaid")
    status: Mapped[str] = mapped_column(String(30), default="booked", index=True)
    schedule_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("schedule_entries.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
