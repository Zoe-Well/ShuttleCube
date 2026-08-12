from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.operations.models import OperationCase
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.security.passwords import hash_password


def _case(
    organization: Organization,
    venue: Venue,
    *,
    suffix: str,
    state: str,
    now: datetime,
) -> OperationCase:
    return OperationCase(
        organization_id=organization.id,
        venue_id=venue.id,
        case_type="attendance_overdue",
        subject_type="class_session",
        subject_id=f"session-{suffix}",
        case_key=f"case-history-{suffix}",
        detector_key="attendance.overdue",
        detector_version=1,
        policy_key="default_operations",
        policy_version=1,
        fingerprint=f"fingerprint-{suffix}",
        evidence_hash=f"evidence-{suffix}",
        evidence={"facts": {"sequence_number": 1}},
        severity="medium",
        priority_score=Decimal("50"),
        title=f"Case {suffix}",
        state=state,
        first_detected_at=now - timedelta(days=2),
        last_detected_at=now - timedelta(days=1),
        queue_key="training",
        required_capability="operations.case.read",
        resolved_at=now if state == "resolved" else None,
        dismissed_reason="无需继续处理" if state == "dismissed" else None,
    )


def test_case_list_defaults_to_active_and_history_remains_queryable(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(UTC)
    user = SystemUser(
        username="case-history-owner",
        display_name="Owner",
        password_hash=hash_password("password123"),
    )
    organization = Organization(name="Case History Org")
    venue = Venue(organization_id=organization.id, name="Case History Venue")
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
        role_key="owner",
        status="active",
    )
    active = _case(organization, venue, suffix="active", state="open", now=now)
    resolved = _case(organization, venue, suffix="resolved", state="resolved", now=now)
    dismissed = _case(organization, venue, suffix="dismissed", state="dismissed", now=now)
    db.add_all(
        [user, organization, venue, organization_membership, venue_membership, active, resolved, dismissed]
    )
    db.commit()

    login = client.post(
        "/api/v1/session/login",
        json={"username": user.username, "password": "password123"},
    )
    assert login.status_code == 200

    current = client.get("/api/v1/operations/cases")
    assert current.status_code == 200
    assert [item["id"] for item in current.json()["items"]] == [active.id]

    history = client.get(
        "/api/v1/operations/cases",
        params=[("state", "resolved"), ("state", "dismissed")],
    )
    assert history.status_code == 200
    assert {item["id"] for item in history.json()["items"]} == {resolved.id, dismissed.id}

    detail = client.get(f"/api/v1/operations/cases/{resolved.id}")
    assert detail.status_code == 200
    assert detail.json()["state"] == "resolved"
