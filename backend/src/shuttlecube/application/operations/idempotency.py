import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.operations.models import OperationToolCall


class IdempotencyConflict(RuntimeError):
    pass


class OutcomeNotReconciled(RuntimeError):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def find_tool_call(
    db: Session,
    *,
    scope: RequestScope,
    tool_key: str,
    idempotency_key: str,
) -> OperationToolCall | None:
    return db.scalar(
        select(OperationToolCall).where(
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
            OperationToolCall.tool_key == tool_key,
            OperationToolCall.idempotency_key == idempotency_key,
        )
    )


def resolve_idempotent_result(
    db: Session,
    *,
    scope: RequestScope,
    tool_key: str,
    idempotency_key: str,
    normalized_input: Mapping[str, object],
) -> OperationToolCall | None:
    existing = find_tool_call(
        db,
        scope=scope,
        tool_key=tool_key,
        idempotency_key=idempotency_key,
    )
    if existing is None:
        return None
    if existing.input_hash != canonical_hash(normalized_input):
        raise IdempotencyConflict("same idempotency key was used with different input")
    return existing


def persist_tool_result(
    tool_call: OperationToolCall,
    *,
    result_reference: str,
    result_summary: str,
) -> None:
    if tool_call.state == "succeeded":
        if tool_call.result_reference != result_reference:
            raise IdempotencyConflict("successful tool result cannot be replaced")
        return
    tool_call.state = "succeeded"
    tool_call.result_reference = result_reference
    tool_call.result_summary = result_summary[:1000]
    tool_call.error_code = None


@dataclass(frozen=True)
class ReconciliationResult:
    outcome: Literal["succeeded", "not_committed", "uncertain"]
    result_reference: str | None = None
    result_summary: str | None = None
    evidence: dict[str, object] | None = None


OutcomeProbe = Callable[[OperationToolCall], ReconciliationResult]


def reconcile_uncertain_outcome(
    tool_call: OperationToolCall,
    *,
    probe: OutcomeProbe,
) -> ReconciliationResult:
    if tool_call.state not in {"executing", "uncertain"}:
        raise OutcomeNotReconciled("only interrupted execution can be reconciled")
    result = probe(tool_call)
    if result.outcome == "succeeded":
        if not result.result_reference:
            raise OutcomeNotReconciled("successful reconciliation needs a business reference")
        persist_tool_result(
            tool_call,
            result_reference=result.result_reference,
            result_summary=result.result_summary or "reconciled from business facts",
        )
    elif result.outcome == "not_committed":
        tool_call.state = "approved"
        tool_call.error_code = "not_committed"
    else:
        tool_call.state = "uncertain"
        tool_call.error_code = "outcome_uncertain"
    return result


def reconcile_replacement_outcome(
    db: Session,
    *,
    scope: RequestScope,
    tool_call: OperationToolCall,
) -> ReconciliationResult:
    if tool_call.tool_key != "schedule_cancelled_class_replacement":
        raise OutcomeNotReconciled("tool call is not a replacement execution")
    cancelled_session_id = str(tool_call.normalized_input.get("cancelled_session_id", ""))
    replacements = list(
        db.scalars(
            select(ClassSession).where(
                ClassSession.organization_id == scope.organization_id,
                ClassSession.venue_id == scope.venue_id,
                ClassSession.replacement_for_session_id == cancelled_session_id,
            )
        ).all()
    )
    if not replacements:
        return ReconciliationResult("not_committed", evidence={"replacement_count": 0})
    if len(replacements) != 1:
        return ReconciliationResult(
            "uncertain",
            evidence={"replacement_ids": [item.id for item in replacements]},
        )
    replacement = replacements[0]
    audit_id = db.scalar(
        select(AuditLog.id).where(
            AuditLog.organization_id == scope.organization_id,
            AuditLog.venue_id == scope.venue_id,
            AuditLog.entity_type == "class_session",
            AuditLog.entity_id == cancelled_session_id,
            AuditLog.action_type == "class_session.replacement_scheduled",
        )
    )
    if audit_id is None:
        return ReconciliationResult(
            "uncertain",
            evidence={"replacement_session_id": replacement.id, "audit_missing": True},
        )
    expected_start = datetime.fromisoformat(
        str(tool_call.normalized_input.get("starts_at", ""))
    )
    expected_end = datetime.fromisoformat(
        str(tool_call.normalized_input.get("ends_at", ""))
    )
    if (
        _aware(replacement.scheduled_start) != _aware(expected_start)
        or _aware(replacement.scheduled_end) != _aware(expected_end)
    ):
        return ReconciliationResult(
            "uncertain",
            evidence={"replacement_session_id": replacement.id, "schedule_mismatch": True},
        )
    return ReconciliationResult(
        "succeeded",
        result_reference=f"class_session:{replacement.id}",
        result_summary=f"reconciled replacement session {replacement.id}",
        evidence={"replacement_session_id": replacement.id, "audit_log_id": audit_id},
    )
