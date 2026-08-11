from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.domain.customers.models import WalkInCustomer
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.venue_bookings.models import VenueBooking


def booking(customer_id: str, starts_at: datetime, ends_at: datetime) -> VenueBooking:
    return VenueBooking(
        customer_id=customer_id,
        starts_at=starts_at,
        ends_at=ends_at,
        court_ids_csv="court-1",
        suggested_receivable=Decimal("80.00"),
        actual_receivable=Decimal("80.00"),
        status="booked",
    )


def test_past_booking_can_be_completed_but_future_booking_cannot(
    db: Session, authenticated
) -> None:
    client, headers = authenticated
    customer = WalkInCustomer(display_name="完成状态测试客户")
    db.add(customer)
    db.flush()
    now = datetime.now(UTC)
    past = booking(customer.id, now - timedelta(hours=2), now - timedelta(hours=1))
    future = booking(customer.id, now + timedelta(hours=1), now + timedelta(hours=2))
    db.add_all([past, future])
    db.commit()

    completed = client.post(f"/api/v1/venue-bookings/{past.id}/complete", headers=headers)
    too_early = client.post(f"/api/v1/venue-bookings/{future.id}/complete", headers=headers)

    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert too_early.status_code == 409
    assert too_early.json()["title"] == "booking_not_ended"


def test_booking_list_filters_by_venue_local_start_date(db: Session, authenticated) -> None:
    client, _ = authenticated
    db.add(Venue(name="日期筛选测试场馆", timezone="Asia/Shanghai"))
    customer = WalkInCustomer(display_name="日期筛选测试客户")
    db.add(customer)
    db.flush()
    august_first = booking(
        customer.id,
        datetime(2026, 8, 1, 15, 0, tzinfo=UTC),
        datetime(2026, 8, 1, 15, 30, tzinfo=UTC),
    )
    august_second = booking(
        customer.id,
        datetime(2026, 8, 1, 17, 0, tzinfo=UTC),
        datetime(2026, 8, 1, 18, 0, tzinfo=UTC),
    )
    db.add_all([august_first, august_second])
    db.commit()

    response = client.get(
        "/api/v1/venue-bookings?from_date=2026-08-02&to_date=2026-08-02"
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [august_second.id]


def test_booking_list_rejects_reversed_date_range(authenticated) -> None:
    client, _ = authenticated

    response = client.get(
        "/api/v1/venue-bookings?from_date=2026-08-03&to_date=2026-08-02"
    )

    assert response.status_code == 422
    assert response.json()["title"] == "invalid_booking_date_range"
