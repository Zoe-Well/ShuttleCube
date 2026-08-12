from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.security.passwords import hash_password
from tests.unit.operations.test_policies import valid_policy_config


def _owner(db: Session) -> SystemUser:
    user = SystemUser(
        username="policy-version-owner",
        display_name="Policy Version Owner",
        password_hash=hash_password("password123"),
    )
    organization = Organization(name="Policy Version Organization")
    venue = Venue(name="Policy Version Venue", organization_id=organization.id)
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
    db.add_all([user, organization, venue, organization_membership, venue_membership])
    db.commit()
    return user


def test_policy_versions_can_be_named_viewed_edited_copied_activated_and_deleted(
    client: TestClient,
    db: Session,
) -> None:
    user = _owner(db)
    login = client.post(
        "/api/v1/session/login",
        json={"username": user.username, "password": "password123"},
    )
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}

    created = client.post(
        "/api/v1/operations/policies",
        headers={**headers, "Idempotency-Key": "create-policy-v1"},
        json={"name": "日常运营规则", "schema_version": "1", "config": valid_policy_config()},
    )
    assert created.status_code == 201
    first = created.json()
    assert first["name"] == "日常运营规则"

    activated = client.post(
        f"/api/v1/operations/policies/{first['id']}:activate",
        headers={**headers, "Idempotency-Key": "activate-policy-v1"},
        json={"expected_version": first["version"]},
    )
    assert activated.status_code == 200

    copied = client.post(
        f"/api/v1/operations/policies/{first['id']}:copy",
        headers={**headers, "Idempotency-Key": "copy-policy-v2"},
        json={"name": "暑期运营规则"},
    )
    assert copied.status_code == 201
    second = copied.json()
    assert second["policy_version"] == 2
    assert second["state"] == "draft"

    changed_config = valid_policy_config()
    changed_config["attendance"] = {"grace_hours": 12}
    updated = client.patch(
        f"/api/v1/operations/policies/{second['id']}",
        headers={**headers, "Idempotency-Key": "update-policy-v2"},
        json={
            "name": "暑期运营规则（确认版）",
            "config": changed_config,
            "expected_version": second["version"],
        },
    )
    assert updated.status_code == 200
    second = updated.json()
    assert second["name"] == "暑期运营规则（确认版）"
    assert second["config"]["attendance"]["grace_hours"] == 12

    # This exercises the migrated-database partial unique index: the prior
    # active version must be retired before the new draft becomes active.
    activated = client.post(
        f"/api/v1/operations/policies/{second['id']}:activate",
        headers={**headers, "Idempotency-Key": "activate-policy-v2"},
        json={"expected_version": second["version"]},
    )
    assert activated.status_code == 200
    assert activated.json()["state"] == "active"

    detail = client.get(f"/api/v1/operations/policies/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["state"] == "retired"

    disposable = client.post(
        f"/api/v1/operations/policies/{second['id']}:copy",
        headers={**headers, "Idempotency-Key": "copy-policy-v3"},
        json={"name": "待删除草稿"},
    ).json()
    deleted = client.delete(
        f"/api/v1/operations/policies/{disposable['id']}",
        params={"expected_version": disposable["version"]},
        headers={**headers, "Idempotency-Key": "delete-policy-v3"},
    )
    assert deleted.status_code == 204

    active_delete = client.delete(
        f"/api/v1/operations/policies/{second['id']}",
        params={"expected_version": activated.json()["version"]},
        headers={**headers, "Idempotency-Key": "delete-active-policy"},
    )
    assert active_delete.status_code == 409
    assert active_delete.json()["title"] == "policy_not_draft"

    actions = set(db.scalars(select(AuditLog.action_type)).all())
    assert {
        "operations.policy_draft_created",
        "operations.policy_draft_updated",
        "operations.policy_draft_copied",
        "operations.policy_draft_deleted",
        "operations.policy_activated",
    }.issubset(actions)
