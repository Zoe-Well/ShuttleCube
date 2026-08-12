import pytest

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.access import (
    AccessDenied,
    capabilities_for_role,
    project_receivable_case,
    project_report_payload,
    require_capability,
)
from shuttlecube.application.operations.tracing import redact_trace_payload


def _scope(role_key: str) -> RequestScope:
    return RequestScope(
        organization_id="organization-1",
        venue_id="venue-1",
        user_id=f"user-{role_key}",
        membership_id=f"membership-{role_key}",
        capabilities=capabilities_for_role(role_key),
    )


def test_versioned_role_bundles_keep_finance_and_assignment_boundaries_explicit() -> None:
    owner = capabilities_for_role("owner")
    manager = capabilities_for_role("operations_manager")
    operator = capabilities_for_role("operator")
    finance = capabilities_for_role("finance_viewer")

    assert "operations.case.assign" in owner
    assert "operations.case.assign" in manager
    assert "operations.case.assign" not in operator
    assert "operations.model.manage" not in operator
    assert "operations.receivable.followup.read" in operator
    assert "operations.report.financial.read" not in operator
    assert "operations.payroll.read" not in operator
    assert "operations.report.financial.read" in finance
    assert "operations.payroll.read" in finance


def test_capability_guard_denies_missing_capability_without_role_inference() -> None:
    scope = _scope("operator")

    require_capability(scope, "operations.receivable.followup.read")
    with pytest.raises(AccessDenied):
        require_capability(scope, "operations.payroll.read")


def test_operator_sees_only_the_amount_for_the_authorized_receivable_case() -> None:
    scope = _scope("operator")
    payload = {
        "id": "receivable-1",
        "source_type": "fixed_class",
        "source_id": "class-1",
        "actual_amount": "800.00",
        "paid_amount": "300.00",
        "refunded_amount": "0.00",
        "outstanding_amount": "500.00",
        "venue_total_outstanding": "12000.00",
        "gross_margin": "400.00",
        "student_name": "Student A",
        "phone": "13800000000",
    }

    visible = project_receivable_case(
        payload,
        scope=scope,
        authorized_receivable_id="receivable-1",
    )
    assert visible == {
        "id": "receivable-1",
        "source_type": "fixed_class",
        "source_id": "class-1",
        "outstanding_amount": "500.00",
        "student_name": "Student A",
    }

    with pytest.raises(AccessDenied):
        project_receivable_case(
            payload,
            scope=scope,
            authorized_receivable_id="receivable-2",
        )


def test_report_projection_removes_finance_payroll_and_linked_source_refs() -> None:
    payload = {
        "metrics": [
            {"metric_key": "attendance_count", "value": "20"},
            {"metric_key": "cash_received", "value": "5000.00"},
            {"metric_key": "coach_fee", "value": "800.00"},
        ],
        "breakdowns": {
            "attendance": [{"label": "Class A", "value": "20"}],
            "finance": [{"label": "Training", "value": "5000.00"}],
            "payroll": [{"label": "Coach A", "value": "800.00"}],
        },
        "source_refs": [
            {"kind": "attendance", "id": "attendance-1"},
            {"kind": "payment", "id": "payment-1"},
            {"kind": "payroll_settlement", "id": "payroll-1"},
        ],
    }

    projected = project_report_payload(payload, scope=_scope("operator"))
    assert [metric["metric_key"] for metric in projected["metrics"]] == [
        "attendance_count"
    ]
    assert set(projected["breakdowns"]) == {"attendance"}
    assert projected["source_refs"] == [{"kind": "attendance", "id": "attendance-1"}]

    finance_projected = project_report_payload(payload, scope=_scope("finance_viewer"))
    assert {metric["metric_key"] for metric in finance_projected["metrics"]} == {
        "attendance_count",
        "cash_received",
        "coach_fee",
    }


def test_trace_redaction_removes_credentials_contacts_and_unauthorized_finance() -> None:
    payload = {
        "authorization": "Bearer secret",
        "cookie": "session=secret",
        "api_key": "sk-secret",
        "phone": "13800000000",
        "attachment_url": "https://private.example/file",
        "outstanding_amount": "500.00",
        "event": "case.analyzed",
    }

    redacted = redact_trace_payload(payload, capabilities=_scope("operator").capabilities)
    assert redacted["event"] == "case.analyzed"
    assert redacted["outstanding_amount"] == "[REDACTED]"
    for key in ("authorization", "cookie", "api_key", "phone", "attachment_url"):
        assert redacted[key] == "[REDACTED]"
