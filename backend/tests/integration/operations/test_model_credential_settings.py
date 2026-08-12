from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.v1 import operations_settings
from shuttlecube.config import Settings, get_settings
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.security.passwords import hash_password


def _owner(db: Session) -> tuple[SystemUser, Venue]:
    user = SystemUser(
        username="credential-owner",
        display_name="Credential Owner",
        password_hash=hash_password("password123"),
    )
    organization = Organization(name="Credential Organization")
    venue = Venue(name="Credential Venue", organization_id=organization.id)
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
    return user, venue


def test_desktop_owner_can_validate_save_enable_and_remove_credential(
    client: TestClient,
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, venue = _owner(db)
    settings = Settings(desktop_mode=True, data_dir=tmp_path, operations_model_profile="gpt-test")
    client.app.dependency_overrides[get_settings] = lambda: settings
    verified_at = datetime(2026, 8, 11, 9, 15, tzinfo=UTC)
    monkeypatch.setattr(
        operations_settings,
        "validate_model_provider",
        lambda _configuration, _settings: verified_at,
    )
    login = client.post(
        "/api/v1/session/login",
        json={"username": user.username, "password": "password123"},
    )
    headers = {
        "X-CSRF-Token": login.json()["csrf_token"],
        "Idempotency-Key": "credential-test",
    }
    secret = "sk-test-not-a-real-credential-value"

    configured = client.put(
        "/api/v1/operations/settings/model/credential",
        json={
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "api_mode": "chat_completions",
            "model_profile": "deepseek-chat",
            "api_key": secret,
        },
        headers=headers,
    )

    assert configured.status_code == 200
    assert configured.json()["provider_configured"] is True
    assert configured.json()["provider_source"] == "desktop"
    assert configured.json()["provider_key"] == "deepseek"
    assert configured.json()["provider_base_url"] == "https://api.deepseek.com"
    assert configured.json()["provider_api_mode"] == "chat_completions"
    assert configured.json()["provider_model_profile"] == "deepseek-chat"
    assert configured.json()["provider_verified_at"] == verified_at.isoformat().replace("+00:00", "Z")
    assert secret not in configured.text
    encrypted = (tmp_path / "settings" / "openai-api-key.dpapi").read_bytes()
    assert secret.encode() not in encrypted

    enabled = client.patch(
        "/api/v1/operations/settings/model",
        json={"model_enabled": True, "expected_version": configured.json()["version"]},
        headers={**headers, "Idempotency-Key": "enable-model-test"},
    )
    assert enabled.status_code == 200
    assert enabled.json()["model_enabled"] is True

    removed = client.delete(
        "/api/v1/operations/settings/model/credential",
        headers={**headers, "Idempotency-Key": "remove-credential-test"},
    )
    assert removed.status_code == 200
    assert removed.json()["provider_configured"] is False
    assert removed.json()["model_enabled"] is False
    assert not (tmp_path / "settings" / "openai-api-key.dpapi").exists()

    audit_text = " ".join(
        str(item)
        for row in db.scalars(select(AuditLog)).all()
        for item in (row.before_summary, row.after_summary, row.reason)
    )
    assert secret not in audit_text
    refreshed_venue = db.get(Venue, venue.id)
    assert refreshed_venue is not None
    assert refreshed_venue.model_enabled is False
