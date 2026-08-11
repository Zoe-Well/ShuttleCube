import pytest
from pydantic import ValidationError

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.access import capabilities_for_role
from shuttlecube.application.operations.tools import (
    CapabilityDenied,
    ToolDisabled,
    ToolRegistry,
    UnknownTool,
)

MVP_TOOL_KEYS = {
    "get_case_evidence",
    "get_receivable_followup_context",
    "get_renewal_followup_context",
    "list_replacement_candidates",
    "get_reconciliation_result",
    "get_operations_report_snapshot",
    "record_followup_outcome",
    "dismiss_operation_case",
    "schedule_cancelled_class_replacement",
}


def _scope(role_key: str) -> RequestScope:
    return RequestScope(
        organization_id="organization-1",
        venue_id="venue-1",
        user_id="user-1",
        membership_id="membership-1",
        capabilities=capabilities_for_role(role_key),
    )


def test_static_registry_contains_only_the_frozen_mvp_business_tools() -> None:
    registry = ToolRegistry.default()

    assert set(registry.keys()) == MVP_TOOL_KEYS
    assert not any(
        fragment in key
        for key in registry.keys()
        for fragment in ("sql", "http", "file", "shell", "python", "repair")
    )


def test_registry_rejects_unknown_and_arbitrary_capability_tools() -> None:
    registry = ToolRegistry.default()

    for key in ("execute_sql", "fetch_url", "write_file", "repair_receivable"):
        with pytest.raises(UnknownTool):
            registry.get(key)


def test_tool_input_schema_is_strict_and_scope_cannot_be_browser_supplied() -> None:
    registry = ToolRegistry.default()

    validated = registry.validate_input(
        "get_case_evidence",
        {"case_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert validated.model_dump() == {
        "case_id": "00000000-0000-0000-0000-000000000001"
    }

    with pytest.raises(ValidationError):
        registry.validate_input(
            "get_case_evidence",
            {
                "case_id": "00000000-0000-0000-0000-000000000001",
                "organization_id": "organization-2",
                "venue_id": "venue-2",
            },
        )


def test_capability_and_write_enablement_are_checked_before_handler_execution() -> None:
    registry = ToolRegistry.default()

    registry.authorize(
        "get_receivable_followup_context",
        scope=_scope("operator"),
        write_tools_enabled=False,
    )
    with pytest.raises(CapabilityDenied):
        registry.authorize(
            "get_operations_report_snapshot",
            scope=_scope("operator"),
            write_tools_enabled=False,
        )
    with pytest.raises(ToolDisabled):
        registry.authorize(
            "record_followup_outcome",
            scope=_scope("operator"),
            write_tools_enabled=False,
        )


def test_risk_approval_and_idempotency_metadata_are_not_model_controlled() -> None:
    registry = ToolRegistry.default()

    followup = registry.get("record_followup_outcome")
    dismiss = registry.get("dismiss_operation_case")
    replacement = registry.get("schedule_cancelled_class_replacement")

    assert (followup.risk_level, followup.approval_policy) == (
        "low",
        "explicit_confirmation",
    )
    assert followup.idempotency_scope == "venue_tool_key"
    assert dismiss.approval_policy == "human_only"
    assert (replacement.risk_level, replacement.approval_policy) == (
        "medium",
        "mandatory_approval",
    )
    assert replacement.required_capability == "operations.schedule.execute"


def test_tool_result_redaction_removes_contacts_secrets_and_disallowed_money() -> None:
    registry = ToolRegistry.default()
    result = {
        "case_id": "case-1",
        "phone": "13800000000",
        "wechat": "private-id",
        "api_key": "secret",
        "venue_total_outstanding": "10000.00",
        "outstanding_amount": "500.00",
    }

    redacted = registry.redact_result(
        "get_receivable_followup_context",
        result,
        capabilities=_scope("operator").capabilities,
    )
    assert redacted == {
        "case_id": "case-1",
        "phone": "[REDACTED]",
        "wechat": "[REDACTED]",
        "api_key": "[REDACTED]",
        "venue_total_outstanding": "[REDACTED]",
        "outstanding_amount": "500.00",
    }
