from datetime import time
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.venue_bookings.models import VenuePriceRule


def test_default_price_settings_replace_active_rules_and_write_audit(
    authenticated: tuple[TestClient, dict[str, str]], db: Session
) -> None:
    client, headers = authenticated
    old = VenuePriceRule(
        name="旧工作日价格",
        day_type="weekday",
        time_start=time(8),
        time_end=time(22),
        price_per_court_hour=Decimal("40"),
        priority=1,
    )
    db.add(old)
    db.commit()

    response = client.put(
        "/api/v1/venue-price-rules/defaults",
        headers=headers,
        json={
            "periods": [
                {
                    "period_type": "weekday_day",
                    "time_start": "08:00:00",
                    "time_end": "18:00:00",
                    "price_per_court_hour": "50.00",
                },
                {
                    "period_type": "weekday_evening",
                    "time_start": "18:00:00",
                    "time_end": "22:00:00",
                    "price_per_court_hour": "80.00",
                },
                {
                    "period_type": "weekend",
                    "time_start": "08:00:00",
                    "time_end": "22:00:00",
                    "price_per_court_hour": "100.00",
                },
            ]
        },
    )

    assert response.status_code == 200
    assert {item["period_type"] for item in response.json()} == {
        "weekday_day",
        "weekday_evening",
        "weekend",
    }
    db.refresh(old)
    assert old.is_active is False
    audit = db.query(AuditLog).filter_by(action_type="venue.default_prices_updated").one()
    assert len(audit.after_summary["periods"]) == 3

    booking = client.post(
        "/api/v1/venue-bookings",
        headers=headers,
        json={
            "customer_name": "默认价格客户",
            "starts_at": "2099-08-03T10:00:00+08:00",
            "ends_at": "2099-08-03T12:00:00+08:00",
            "court_ids": ["court-1"],
        },
    )
    assert booking.status_code == 201
    assert booking.json()["actual_receivable"] == booking.json()["suggested_receivable"]
    assert Decimal(str(booking.json()["actual_receivable"])) > 0


def test_default_price_settings_reject_overlapping_weekday_periods(
    authenticated: tuple[TestClient, dict[str, str]],
) -> None:
    client, headers = authenticated
    response = client.put(
        "/api/v1/venue-price-rules/defaults",
        headers=headers,
        json={
            "periods": [
                {
                    "period_type": "weekday_day",
                    "time_start": "08:00:00",
                    "time_end": "19:00:00",
                    "price_per_court_hour": "50.00",
                },
                {
                    "period_type": "weekday_evening",
                    "time_start": "18:00:00",
                    "time_end": "22:00:00",
                    "price_per_court_hour": "80.00",
                },
                {
                    "period_type": "weekend",
                    "time_start": "08:00:00",
                    "time_end": "22:00:00",
                    "price_per_court_hour": "100.00",
                },
            ]
        },
    )

    assert response.status_code == 422
