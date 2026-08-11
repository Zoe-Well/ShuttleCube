from decimal import Decimal

import pytest
from pydantic import ValidationError

from shuttlecube.domain.operations.schemas import OperationsPolicyConfig


def valid_policy_config() -> dict[str, object]:
    return {
        "receivable_followup": {
            "aging_days": 7,
            "escalation_days": 30,
            "max_attempts": 4,
        },
        "renewal": {
            "fixed_class_days": 30,
            "private_package_expiry_days": 30,
            "private_package_remaining_units": 3,
            "cadence_days": 7,
        },
        "attendance": {"grace_hours": 24},
        "replacement": {
            "window_days": 14,
            "slot_minutes": 30,
            "resource_mode": "original_only",
        },
        "reports": {
            "min_sample_size": 5,
            "income_decline": "0.20",
            "refund_ratio": "0.10",
            "expense_growth": "0.20",
            "outstanding": "1000.00",
            "cancellation_rate": "0.10",
            "low_utilization": "0.30",
            "coach_pending": "1000.00",
        },
        "runtime": {
            "case_sla_days": 3,
            "approval_expiry_minutes": 60,
            "retry_limit": 2,
        },
    }


def test_policy_config_is_strict_typed_and_decimal_safe() -> None:
    config = OperationsPolicyConfig.model_validate(valid_policy_config())
    assert config.replacement.resource_mode == "original_only"
    assert config.reports.income_decline == Decimal("0.20")
    assert config.runtime.retry_limit == 2

    with pytest.raises(ValidationError):
        OperationsPolicyConfig.model_validate(
            {**valid_policy_config(), "arbitrary_sql": "delete from payments"}
        )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("replacement", "resource_mode", "any_coach"),
        ("replacement", "slot_minutes", 20),
        ("runtime", "retry_limit", 11),
        ("receivable_followup", "max_attempts", 0),
    ],
)
def test_policy_config_rejects_unsupported_or_out_of_range_values(
    section: str,
    field: str,
    value: object,
) -> None:
    raw = valid_policy_config()
    raw[section] = {**raw[section], field: value}  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        OperationsPolicyConfig.model_validate(raw)
