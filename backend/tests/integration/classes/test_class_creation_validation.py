from datetime import date

from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.scheduling.court import Court, Venue


def test_class_creation_requires_registered_coach_and_courts(authenticated, db) -> None:
    client, headers = authenticated
    venue = Venue(name="校验测试场馆")
    coach = CoachProfile(name="系统教练", phone="13800000002")
    db.add_all([venue, coach])
    db.flush()
    court = Court(venue_id=venue.id, code="V-1", name="校验 1 号场")
    db.add(court)
    db.commit()
    payload = {
        "name": "周三基础班",
        "class_type": "training",
        "start_date": date(2026, 8, 5).isoformat(),
        "default_start_time": "10:00:00",
        "duration_minutes": 60,
        "session_count": 1,
        "capacity": 8,
        "default_coach_id": coach.id,
        "court_ids": ["1"],
        "required_court_count": 1,
        "student_unit_price": "100.00",
        "coach_fee_per_session": "80.00",
    }

    invalid = client.post("/api/v1/classes", json=payload, headers=headers)
    assert invalid.status_code == 422
    assert invalid.json()["title"] == "invalid_class_court"

    payload["court_ids"] = [court.id]
    created = client.post("/api/v1/classes", json=payload, headers=headers)
    assert created.status_code == 201, created.json()
