from sqlalchemy.orm import Session

from shuttlecube.cli import bootstrap_operations_owner, bootstrap_venue
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.infrastructure.security.passwords import hash_password


def test_venue_can_seed_four_courts(db: Session) -> None:
    organization = Organization(name="Organization")
    venue = Venue(organization_id=organization.id)
    db.add_all([organization, venue])
    db.flush()
    db.add_all([Court(venue_id=venue.id, code=str(i), name=f"{i} 号场地") for i in range(1, 5)])
    db.commit()
    assert db.query(Court).count() == 4


def test_bootstrap_venue_is_idempotent(monkeypatch, db: Session) -> None:
    organization = Organization(name="Organization")
    db.add(organization)
    db.commit()
    monkeypatch.setattr("shuttlecube.cli.SessionLocal", lambda: db)
    bootstrap_venue()
    bootstrap_venue()
    assert db.query(Venue).count() == 1
    assert [court.code for court in db.query(Court).order_by(Court.code)] == ["1", "2", "3", "4"]


def test_bootstrap_operations_owner_is_audited_and_keeps_risky_features_off(
    monkeypatch, db: Session
) -> None:
    user = SystemUser(
        username="owner1",
        display_name="Owner",
        password_hash=hash_password("password123"),
    )
    organization = Organization(name="Organization")
    venue = Venue(organization_id=organization.id)
    organization_membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
    )
    venue_membership = VenueMembership(
        organization_membership_id=organization_membership.id,
        organization_id=organization.id,
        venue_id=venue.id,
        role_key="operator",
    )
    db.add_all(
        [user, organization, venue, organization_membership, venue_membership]
    )
    db.commit()
    monkeypatch.setattr("shuttlecube.cli.SessionLocal", lambda: db)

    bootstrap_operations_owner(user.username, venue.id)

    assert organization_membership.status == "active"
    assert organization_membership.organization_role == "owner"
    assert venue_membership.status == "active"
    assert venue_membership.role_key == "owner"
    assert venue.active_for_operations is True
    assert venue.model_enabled is False
    assert venue.write_tools_enabled is False
    assert db.query(AuditLog).filter_by(action_type="operations.owner_bootstrapped").count() == 1
