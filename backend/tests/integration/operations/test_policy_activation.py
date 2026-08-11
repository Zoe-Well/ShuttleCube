import pytest
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.access import capabilities_for_role
from shuttlecube.application.operations.policies import (
    PolicyNotConfigured,
    StalePolicy,
    activate_policy,
    assert_policy_current,
    create_policy_draft,
    get_active_policy,
)
from shuttlecube.domain.identity.organization_models import Organization
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.scheduling.court import Venue
from tests.unit.operations.test_policies import valid_policy_config


def _scope(organization_id: str, venue_id: str) -> RequestScope:
    return RequestScope(
        organization_id=organization_id,
        venue_id=venue_id,
        user_id="owner-1",
        membership_id="membership-1",
        capabilities=capabilities_for_role("owner"),
    )


def test_policy_activation_retires_previous_version_and_preserves_immutability(
    db: Session,
) -> None:
    organization = Organization(name="Organization")
    db.add(organization)
    db.flush()
    venue = Venue(name="Venue", organization_id=organization.id)
    db.add(venue)
    db.flush()
    scope = _scope(organization.id, venue.id)

    first = create_policy_draft(
        db,
        scope=scope,
        schema_version=1,
        config=valid_policy_config(),
    )
    activate_policy(db, scope=scope, policy_id=first.id, expected_version=first.version)
    db.commit()
    first_hash = first.config_hash

    second_config = valid_policy_config()
    second_config["attendance"] = {"grace_hours": 12}
    second = create_policy_draft(
        db,
        scope=scope,
        schema_version=1,
        config=second_config,
    )
    activate_policy(db, scope=scope, policy_id=second.id, expected_version=second.version)
    db.commit()

    assert first.state == "retired"
    assert first.config_hash == first_hash
    assert second.state == "active"
    assert second.policy_version == first.policy_version + 1
    assert get_active_policy(db, scope=scope).id == second.id
    assert (
        db.query(OperationsPolicy)
        .filter_by(venue_id=venue.id, policy_key="default_operations", state="active")
        .count()
        == 1
    )


def test_missing_and_stale_policy_are_explicit_stop_conditions(db: Session) -> None:
    organization = Organization(name="Organization")
    db.add(organization)
    db.flush()
    venue = Venue(name="Venue", organization_id=organization.id)
    db.add(venue)
    db.flush()
    scope = _scope(organization.id, venue.id)

    with pytest.raises(PolicyNotConfigured):
        get_active_policy(db, scope=scope)

    policy = create_policy_draft(
        db,
        scope=scope,
        schema_version=1,
        config=valid_policy_config(),
    )
    activate_policy(db, scope=scope, policy_id=policy.id, expected_version=policy.version)
    db.commit()

    assert_policy_current(
        db,
        scope=scope,
        policy_key=policy.policy_key,
        policy_version=policy.policy_version,
        config_hash=policy.config_hash,
    )
    with pytest.raises(StalePolicy):
        assert_policy_current(
            db,
            scope=scope,
            policy_key=policy.policy_key,
            policy_version=policy.policy_version,
            config_hash="stale-hash",
        )
