import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from shuttlecube.application.operations.repositories import OperationsRepository
from shuttlecube.domain.operations.models import OperationEvent, OperationRun

_SECRET_FRAGMENTS = (
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "api_key",
    "credential",
)
_CONTACT_KEYS = {"phone", "wechat", "email", "mobile"}
_BINARY_KEYS = {"attachment_body", "voucher_body", "file_content"}
_PRIVATE_LINK_KEYS = {"attachment_url", "voucher_url", "file_url"}


def redact_payload(value: object, *, key: str | None = None) -> object:
    normalized = (key or "").lower()
    if normalized in _CONTACT_KEYS or normalized in _BINARY_KEYS or normalized in _PRIVATE_LINK_KEYS or any(
        fragment in normalized for fragment in _SECRET_FRAGMENTS
    ):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(item_key): redact_payload(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item) for item in value]
    return value


def redact_trace_payload(
    payload: Mapping[str, object],
    *,
    capabilities: frozenset[str],
) -> dict[str, object]:
    redacted = redact_payload(payload)
    assert isinstance(redacted, dict)
    can_finance = "operations.report.financial.read" in capabilities
    can_payroll = "operations.payroll.read" in capabilities
    for key in tuple(redacted):
        normalized = key.lower()
        if normalized.startswith(("coach_fee", "payroll")) and not can_payroll:
            redacted[key] = "[REDACTED]"
        elif normalized.startswith(
            ("cash_", "income", "refund", "expense", "profit", "outstanding")
        ) and not can_finance:
            redacted[key] = "[REDACTED]"
    return redacted


def payload_hash(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def model_usage_summary(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> dict[str, int]:
    values = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "reasoning_tokens": reasoning_tokens,
    }
    return {key: max(0, int(value)) for key, value in values.items()}


@dataclass
class TraceRecorder:
    repository: OperationsRepository
    trace_id: str
    request_id: str | None = None

    def record(
        self,
        run: OperationRun,
        *,
        event_type: str,
        actor_type: str,
        payload: Mapping[str, object],
        actor_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> OperationEvent:
        redacted = redact_payload(payload)
        assert isinstance(redacted, dict)
        return self.repository.append_event(
            run,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            trace_id=self.trace_id,
            request_id=self.request_id,
            payload_redacted=redacted,
            payload_hash=payload_hash(redacted),
            occurred_at=occurred_at or datetime.now(UTC),
        )

    def link_business_audit(
        self,
        run: OperationRun,
        *,
        audit_log_id: str,
        business_reference: str,
        actor_id: str,
    ) -> OperationEvent:
        return self.record(
            run,
            event_type="business_audit_linked",
            actor_type="user",
            actor_id=actor_id,
            payload={
                "audit_log_id": audit_log_id,
                "business_reference": business_reference,
            },
        )
