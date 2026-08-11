from datetime import time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.scheduling.court import Venue


def test_admin_updates_business_hours_and_records_audit(
    authenticated: tuple[TestClient, dict[str, str]], db: Session
) -> None:
    client, headers = authenticated
    venue = Venue(
        name="测试羽毛球馆",
        timezone="Asia/Shanghai",
        weekday_open_time=time(14, 0),
        weekday_close_time=time(22, 0),
        weekend_open_time=time(8, 0),
        weekend_close_time=time(22, 0),
    )
    db.add(venue)
    db.commit()
    db.refresh(venue)

    response = client.put(
        "/api/v1/venue/settings",
        headers=headers,
        json={
            "name": venue.name,
            "timezone": venue.timezone,
            "weekday_open_time": "13:30:00",
            "weekday_close_time": "23:00:00",
            "weekend_open_time": "07:30:00",
            "weekend_close_time": "23:30:00",
            "version": venue.version,
        },
    )

    assert response.status_code == 200
    db.refresh(venue)
    assert venue.weekday_open_time == time(13, 30)
    assert venue.weekend_close_time == time(23, 30)
    audit = db.query(AuditLog).filter_by(action_type="venue.business_hours_updated").one()
    assert audit.entity_id == venue.id
    assert audit.before_summary == {
        "weekday_open_time": "14:00:00",
        "weekday_close_time": "22:00:00",
        "weekend_open_time": "08:00:00",
        "weekend_close_time": "22:00:00",
    }
    assert audit.after_summary == {
        "weekday_open_time": "13:30:00",
        "weekday_close_time": "23:00:00",
        "weekend_open_time": "07:30:00",
        "weekend_close_time": "23:30:00",
    }


def test_business_hours_reject_close_before_open(
    authenticated: tuple[TestClient, dict[str, str]], db: Session
) -> None:
    client, headers = authenticated
    venue = Venue(
        name="测试羽毛球馆",
        timezone="Asia/Shanghai",
        weekday_open_time=time(14, 0),
        weekday_close_time=time(22, 0),
        weekend_open_time=time(8, 0),
        weekend_close_time=time(22, 0),
    )
    db.add(venue)
    db.commit()
    db.refresh(venue)

    response = client.put(
        "/api/v1/venue/settings",
        headers=headers,
        json={
            "name": venue.name,
            "timezone": venue.timezone,
            "weekday_open_time": "22:00:00",
            "weekday_close_time": "14:00:00",
            "weekend_open_time": "08:00:00",
            "weekend_close_time": "22:00:00",
            "version": venue.version,
        },
    )

    assert response.status_code == 422
    db.refresh(venue)
    assert venue.weekday_open_time == time(14, 0)
    assert venue.weekday_close_time == time(22, 0)
