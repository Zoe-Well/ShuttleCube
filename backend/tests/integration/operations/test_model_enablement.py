import pytest
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.operations.access import capabilities_for_role
from shuttlecube.application.operations.memberships import (
    set_venue_model_enabled,
    set_venue_runtime_settings,
)
from shuttlecube.application.operations.model_client import (
    DisabledModelClient,
    ModelDisabled,
    StubModelClient,
    model_client_for_venue,
)
from shuttlecube.domain.identity.organization_models import Organization
from shuttlecube.domain.scheduling.court import Venue


def _scope(role_key: str, *, organization_id: str, venue_id: str) -> RequestScope:
    return RequestScope(
        organization_id=organization_id,
        venue_id=venue_id,
        user_id=f"user-{role_key}",
        membership_id=f"membership-{role_key}",
        capabilities=capabilities_for_role(role_key),
    )


def test_new_venue_model_is_off_even_when_provider_credentials_exist(db: Session) -> None:
    organization = Organization(name="Organization")
    venue = Venue(name="Venue", organization_id=organization.id)
    db.add_all([organization, venue])
    db.commit()

    client = model_client_for_venue(
        venue=venue,
        provider_configured=True,
        enabled_client=StubModelClient(),
    )
    assert venue.model_enabled is False
    assert isinstance(client, DisabledModelClient)
    with pytest.raises(ModelDisabled):
        client.generate({"task": "summary"})


def test_authorized_explicit_enable_and_disable_are_per_venue(db: Session) -> None:
    organization = Organization(name="Organization")
    first = Venue(name="First", organization_id=organization.id)
    second = Venue(name="Second", organization_id=organization.id)
    db.add_all([organization, first, second])
    db.commit()
    owner = _scope("owner", organization_id=organization.id, venue_id=first.id)

    set_venue_model_enabled(
        db,
        scope=owner,
        venue=first,
        enabled=True,
        reason="Enable controlled narrative runs",
        expected_version=first.version,
    )
    db.commit()

    assert first.model_enabled is True
    assert first.model_enabled_by == owner.user_id
    assert first.model_enabled_at is not None
    assert second.model_enabled is False

    enabled_client = StubModelClient()
    assert (
        model_client_for_venue(
            venue=first,
            provider_configured=True,
            enabled_client=enabled_client,
        )
        is enabled_client
    )

    set_venue_model_enabled(
        db,
        scope=owner,
        venue=first,
        enabled=False,
        reason="Incident stop",
        expected_version=first.version,
    )
    db.commit()
    assert isinstance(
        model_client_for_venue(
            venue=first,
            provider_configured=True,
            enabled_client=enabled_client,
        ),
        DisabledModelClient,
    )


def test_operator_cannot_enable_model_and_provider_configuration_is_not_consent(
    db: Session,
) -> None:
    organization = Organization(name="Organization")
    venue = Venue(name="Venue", organization_id=organization.id)
    db.add_all([organization, venue])
    db.commit()
    operator = _scope("operator", organization_id=organization.id, venue_id=venue.id)

    with pytest.raises(PermissionError):
        set_venue_model_enabled(
            db,
            scope=operator,
            venue=venue,
            enabled=True,
            reason="Not authorized",
            expected_version=venue.version,
        )

    assert venue.model_enabled is False
    assert isinstance(
        model_client_for_venue(
            venue=venue,
            provider_configured=True,
            enabled_client=StubModelClient(),
        ),
        DisabledModelClient,
    )


def test_owner_controls_runtime_flags_and_operator_cannot_enable_write_tools(
    db: Session,
) -> None:
    organization = Organization(name="Organization")
    venue = Venue(name="Venue", organization_id=organization.id)
    db.add_all([organization, venue])
    db.commit()
    owner = _scope("owner", organization_id=organization.id, venue_id=venue.id)

    set_venue_runtime_settings(
        db,
        scope=owner,
        venue=venue,
        operations_enabled=True,
        write_tools_enabled=False,
        reason="Enable deterministic operations",
        expected_version=venue.version,
    )
    db.commit()
    assert venue.active_for_operations is True
    assert venue.write_tools_enabled is False

    operator = _scope("operator", organization_id=organization.id, venue_id=venue.id)
    with pytest.raises(PermissionError):
        set_venue_runtime_settings(
            db,
            scope=operator,
            venue=venue,
            operations_enabled=True,
            write_tools_enabled=True,
            reason="Not authorized",
            expected_version=venue.version,
        )


def test_write_tools_cannot_be_enabled_while_operations_are_off(db: Session) -> None:
    organization = Organization(name="Organization")
    venue = Venue(name="Venue", organization_id=organization.id)
    db.add_all([organization, venue])
    db.commit()
    owner = _scope("owner", organization_id=organization.id, venue_id=venue.id)

    with pytest.raises(BusinessError) as error:
        set_venue_runtime_settings(
            db,
            scope=owner,
            venue=venue,
            operations_enabled=False,
            write_tools_enabled=True,
            reason="Invalid combination",
            expected_version=venue.version,
        )
    assert getattr(error.value, "code", None) == "operations_required_for_write_tools"
