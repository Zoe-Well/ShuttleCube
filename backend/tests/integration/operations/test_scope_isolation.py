from datetime import date, time
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.infrastructure.security.passwords import hash_password


def _principal(
    db: Session,
    *,
    suffix: str,
    role_key: str = "owner",
) -> tuple[SystemUser, Organization, Venue]:
    user = SystemUser(
        username=f"owner-{suffix}",
        display_name=f"Owner {suffix}",
        password_hash=hash_password("password123"),
    )
    organization = Organization(name=f"Organization {suffix}")
    venue = Venue(name=f"Venue {suffix}", organization_id=organization.id)
    organization_membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        status="active",
        organization_role="owner",
    )
    venue_membership = VenueMembership(
        organization_membership_id=organization_membership.id,
        organization_id=organization.id,
        venue_id=venue.id,
        role_key=role_key,
        status="active",
    )
    db.add_all([user, organization, venue, organization_membership, venue_membership])
    db.flush()
    return user, organization, venue


def _login(client: TestClient, user: SystemUser) -> None:
    response = client.post(
        "/api/v1/session/login",
        json={"username": user.username, "password": "password123"},
    )
    assert response.status_code == 200


def test_colliding_court_and_business_codes_remain_isolated_by_scope(
    client: TestClient,
    db: Session,
) -> None:
    user_a, organization_a, venue_a = _principal(db, suffix="a")
    _, organization_b, venue_b = _principal(db, suffix="b")
    court_a = Court(venue_id=venue_a.id, code="1", name="A-1")
    court_b = Court(venue_id=venue_b.id, code="1", name="B-1")
    receivable_a = Receivable(
        organization_id=organization_a.id,
        venue_id=venue_a.id,
        source_type="venue_booking",
        source_id="business-1",
        suggested_amount=Decimal("80"),
        actual_amount=Decimal("80"),
    )
    receivable_b = Receivable(
        organization_id=organization_b.id,
        venue_id=venue_b.id,
        source_type="venue_booking",
        source_id="business-1",
        suggested_amount=Decimal("100"),
        actual_amount=Decimal("100"),
    )
    db.add_all([court_a, court_b, receivable_a, receivable_b])
    db.commit()

    _login(client, user_a)

    courts = client.get("/api/v1/courts")
    assert courts.status_code == 200
    assert {item["id"] for item in courts.json()} == {court_a.id}
    receivables = client.get("/api/v1/receivables")
    assert receivables.status_code == 200
    assert {item["id"] for item in receivables.json()} == {receivable_a.id}


def test_cross_scope_student_and_session_direct_references_return_not_found(
    client: TestClient,
    db: Session,
) -> None:
    user_a, _, _ = _principal(db, suffix="a")
    _, organization_b, venue_b = _principal(db, suffix="b")
    foreign_student = Student(
        organization_id=organization_b.id,
        venue_id=venue_b.id,
        name="Foreign student",
    )
    foreign_class = FixedClass(
        organization_id=organization_b.id,
        venue_id=venue_b.id,
        name="Foreign class",
        class_type="training",
        recurrence_rule="FREQ=WEEKLY",
        start_date=date(2026, 8, 1),
        default_start_time=time(18),
        duration_minutes=60,
        session_count=1,
        capacity=8,
        default_coach_id="coach-b",
        required_court_count=1,
        student_unit_price=Decimal("100"),
    )
    db.add_all([foreign_student, foreign_class])
    db.commit()

    _login(client, user_a)

    student_response = client.get(
        f"/api/v1/students/{foreign_student.id}/entitlements"
    )
    class_response = client.get(f"/api/v1/classes/{foreign_class.id}")
    assert student_response.status_code == 404
    assert class_response.status_code == 404
