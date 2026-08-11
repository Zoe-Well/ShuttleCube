from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.application.commands.coach_rates import set_coach_rate
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.domain.scheduling.court import Court, Venue


def test_coach_directory_manages_effective_dated_rates_and_audits_changes(
    db: Session, authenticated: tuple[TestClient, dict[str, str]]
) -> None:
    client, headers = authenticated
    created = client.post(
        "/api/v1/coaches",
        headers=headers,
        json={
            "name": "陈教练",
            "fixed_class_fee": 180,
            "private_lesson_fee": 220,
            "rate_effective_from": "2026-08-01",
        },
    )

    assert created.status_code == 201
    coach = created.json()
    assert coach["fixed_class_fee"] == 180
    assert coach["private_lesson_fee"] == 220
    assert coach["fixed_class_fee_effective_from"] == "2026-08-01"
    assert db.scalar(
        select(AuditLog).where(
            AuditLog.action_type == "coach.created", AuditLog.entity_id == coach["id"]
        )
    ) is not None

    updated = client.put(
        f"/api/v1/coaches/{coach['id']}",
        headers=headers,
        json={
            "name": "陈教练",
            "fixed_class_fee": 200,
            "rate_effective_from": "2026-09-01",
            "version": coach["version"],
        },
    )
    assert updated.status_code == 200

    history = client.get(f"/api/v1/coaches/{coach['id']}/rates")
    assert history.status_code == 200
    fixed_rates = [
        item for item in history.json() if item["business_type"] == "fixed_class"
    ]
    assert fixed_rates == [
        {
            "id": fixed_rates[0]["id"],
            "business_type": "fixed_class",
            "amount": 200.0,
            "effective_from": "2026-09-01",
            "effective_to": None,
            "version": fixed_rates[0]["version"],
        },
        {
            "id": fixed_rates[1]["id"],
            "business_type": "fixed_class",
            "amount": 180.0,
            "effective_from": "2026-08-01",
            "effective_to": "2026-08-31",
            "version": fixed_rates[1]["version"],
        },
    ]


def test_class_and_private_lesson_freeze_the_effective_default_rate(
    db: Session, authenticated: tuple[TestClient, dict[str, str]]
) -> None:
    client, headers = authenticated
    coach = CoachProfile(name="费率教练")
    student = Student(name="胡东东")
    venue = Venue(name="费率测试场馆")
    db.add_all([coach, student, venue])
    db.flush()
    court = Court(venue_id=venue.id, code="RATE-1", name="费率测试场地")
    db.add(court)
    set_coach_rate(
        db,
        coach_id=coach.id,
        business_type="fixed_class",
        amount=Decimal("180.00"),
        effective_from=date(2026, 8, 1),
    )
    set_coach_rate(
        db,
        coach_id=coach.id,
        business_type="private_lesson",
        amount=Decimal("220.00"),
        effective_from=date(2026, 8, 1),
    )
    set_coach_rate(
        db,
        coach_id=coach.id,
        business_type="private_lesson",
        amount=Decimal("260.00"),
        effective_from=date(2026, 9, 1),
    )
    db.commit()

    fixed_class_response = client.post(
        "/api/v1/classes",
        headers=headers,
        json={
            "name": "周末提高班",
            "class_type": "training",
            "start_date": "2026-08-08",
            "default_start_time": "18:00:00",
            "duration_minutes": 60,
            "session_count": 1,
            "capacity": 8,
            "default_coach_id": coach.id,
            "court_ids": [court.id],
            "required_court_count": 1,
            "student_unit_price": 100,
        },
    )
    assert fixed_class_response.status_code == 201
    fixed_class = db.get(FixedClass, fixed_class_response.json()["class_id"])
    assert fixed_class is not None
    assert fixed_class.coach_fee_per_session == Decimal("180.00")

    lesson_response = client.post(
        "/api/v1/private-lessons",
        headers=headers,
        json={
            "student_id": student.id,
            "coach_id": coach.id,
            "billing_mode": "single",
            "starts_at": "2026-08-31T16:00:00Z",
            "ends_at": "2026-08-31T17:00:00Z",
            "court_ids": ["court-2"],
            "actual_receivable": 300,
            "warning_acknowledgements": ["outside_business_hours"],
        },
    )
    assert lesson_response.status_code == 201
    lesson = db.get(PrivateLesson, lesson_response.json()["id"])
    assert lesson is not None
    assert lesson.coach_fee == Decimal("260.00")
