from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.reconciliation import ReconciliationRegistry
from shuttlecube.application.operations.state_machine import transition_case
from shuttlecube.application.queries.receivables import receivable_summary
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.operations.models import OperationCase, OperationToolCall
from shuttlecube.domain.private_lessons.models import PrivateLessonPackage
from shuttlecube.domain.scheduling.conflicts import Resource, find_conflicts
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry


@dataclass(frozen=True)
class VerificationResult:
    outcome: str
    reason_code: str
    facts: dict[str, object]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


Verifier = Callable[[Session, RequestScope, OperationCase], VerificationResult]


class VerifierRegistry:
    def __init__(self, items: Iterable[tuple[str, Verifier]]) -> None:
        self._items = dict(items)

    @classmethod
    def default(cls) -> VerifierRegistry:
        return cls(
            (
                ("attendance_overdue", verify_overdue_attendance),
                ("receivable_followup", verify_receivable_followup),
                ("fixed_class_renewal", verify_fixed_class_renewal),
                ("private_package_renewal", verify_private_package_renewal),
                ("class_replacement_pending", verify_class_replacement),
                ("reconciliation_failure", verify_reconciliation_failure),
            )
        )

    def verify(
        self,
        db: Session,
        scope: RequestScope,
        case: OperationCase,
    ) -> VerificationResult:
        verifier = self._items.get(case.case_type)
        if verifier is None:
            return VerificationResult("unsupported", "verifier_not_registered", {})
        return verifier(db, scope, case)


def verify_reconciliation_failure(
    db: Session,
    scope: RequestScope,
    case: OperationCase,
) -> VerificationResult:
    facts = (case.evidence or {}).get("facts", {})
    recorded = facts.get("reconciliation", {}) if isinstance(facts, dict) else {}
    if not isinstance(recorded, dict):
        return VerificationResult("escalate", "reconciliation_evidence_invalid", {})
    rule_key = str(recorded.get("rule_key", ""))
    issue_id = str(recorded.get("issue_id", case.subject_id))
    recorded_version = int(recorded.get("rule_version", 0))
    try:
        rule = ReconciliationRegistry.default().get(rule_key)
    except KeyError:
        if case.state != "escalated":
            transition_case(case, "escalated")
        return VerificationResult(
            "escalate",
            "reconciliation_rule_missing",
            {"rule_key": rule_key, "recorded_version": recorded_version},
        )
    compatible = (
        rule.version >= recorded_version >= rule.compatible_from_version
    )
    if not compatible:
        if case.state != "escalated":
            transition_case(case, "escalated")
        return VerificationResult(
            "escalate",
            "reconciliation_rule_incompatible",
            {
                "rule_key": rule_key,
                "recorded_version": recorded_version,
                "current_version": rule.version,
                "compatible_from_version": rule.compatible_from_version,
            },
        )
    current = {item.issue_id: item for item in rule.implementation(db, scope)}.get(issue_id)
    if current is None:
        if case.state not in {"resolved", "dismissed"}:
            transition_case(case, "resolved")
        return VerificationResult(
            "resolved",
            "reconciliation_passed",
            {"rule_key": rule_key, "rule_version": rule.version, "issue_id": issue_id},
        )
    failure_count = int(facts.get("failure_count", 1)) if isinstance(facts, dict) else 1
    if failure_count >= 3 and case.state != "escalated":
        transition_case(case, "escalated")
        outcome = "escalate"
    else:
        if case.state == "open":
            transition_case(case, "monitoring")
        outcome = "monitoring"
    return VerificationResult(
        outcome,
        "reconciliation_still_failed",
        {
            "rule_key": rule_key,
            "rule_version": rule.version,
            "issue_id": issue_id,
            "failure_count": failure_count,
            "invariants": [item.model_dump(mode="json") for item in current.invariants],
        },
    )


def verify_overdue_attendance(
    db: Session,
    scope: RequestScope,
    case: OperationCase,
) -> VerificationResult:
    session = db.scalar(
        select(ClassSession).where(
            ClassSession.id == case.subject_id,
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
        )
    )
    if session is None:
        return VerificationResult("escalate", "subject_missing", {})
    resolved = session.status != "scheduled" or session.attendance_finalized_at is not None
    facts = {
        "class_session_id": session.id,
        "status": session.status,
        "attendance_finalized_at": session.attendance_finalized_at,
        "source_version": session.version,
    }
    if resolved:
        if case.state not in {"resolved", "dismissed"}:
            transition_case(case, "resolved", now=datetime.now(UTC))
        return VerificationResult("resolved", "attendance_finalized", facts)
    if case.state == "open":
        transition_case(case, "monitoring")
    return VerificationResult("monitoring", "attendance_still_pending", facts)


def _resolve_or_monitor(
    case: OperationCase,
    *,
    resolved: bool,
    resolved_reason: str,
    monitoring_reason: str,
    facts: dict[str, object],
) -> VerificationResult:
    if resolved:
        if case.state not in {"resolved", "dismissed"}:
            transition_case(case, "resolved", now=datetime.now(UTC))
        return VerificationResult("resolved", resolved_reason, facts)
    if case.state == "open":
        transition_case(case, "monitoring")
    return VerificationResult("monitoring", monitoring_reason, facts)


def verify_receivable_followup(
    db: Session,
    scope: RequestScope,
    case: OperationCase,
) -> VerificationResult:
    item = db.scalar(
        select(Receivable).where(
            Receivable.id == case.subject_id,
            Receivable.organization_id == scope.organization_id,
            Receivable.venue_id == scope.venue_id,
        )
    )
    if item is None:
        return VerificationResult("escalate", "subject_missing", {})
    summary = receivable_summary(db, item)
    facts = {
        "receivable_id": item.id,
        "status": item.status,
        "payment_status": summary.payment_status,
        "outstanding": str(summary.outstanding_amount),
        "source_version": item.version,
    }
    return _resolve_or_monitor(
        case,
        resolved=summary.outstanding_amount <= 0 or item.status in {"void", "refunded"},
        resolved_reason="receivable_settled",
        monitoring_reason="receivable_still_outstanding",
        facts=facts,
    )


def verify_fixed_class_renewal(
    db: Session,
    scope: RequestScope,
    case: OperationCase,
) -> VerificationResult:
    from shuttlecube.domain.classes.class_models import FixedClass

    item = db.scalar(
        select(FixedClass).where(
            FixedClass.id == case.subject_id,
            FixedClass.organization_id == scope.organization_id,
            FixedClass.venue_id == scope.venue_id,
        )
    )
    if item is None:
        return VerificationResult("escalate", "subject_missing", {})
    original_count = int((case.evidence or {}).get("facts", {}).get("session_count", 0))
    current_last_end = db.scalar(
        select(func.max(ClassSession.scheduled_end)).where(
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
            ClassSession.fixed_class_id == item.id,
        )
    )
    facts = {
        "fixed_class_id": item.id,
        "session_count": item.session_count,
        "original_session_count": original_count,
        "latest_session_end": current_last_end,
        "source_version": item.version,
    }
    return _resolve_or_monitor(
        case,
        resolved=item.session_count > original_count,
        resolved_reason="fixed_class_renewed",
        monitoring_reason="fixed_class_not_renewed",
        facts=facts,
    )


def verify_private_package_renewal(
    db: Session,
    scope: RequestScope,
    case: OperationCase,
) -> VerificationResult:
    item = db.scalar(
        select(PrivateLessonPackage).where(
            PrivateLessonPackage.id == case.subject_id,
            PrivateLessonPackage.organization_id == scope.organization_id,
            PrivateLessonPackage.venue_id == scope.venue_id,
        )
    )
    if item is None:
        return VerificationResult("escalate", "subject_missing", {})
    replacement_ids = list(
        db.scalars(
            select(PrivateLessonPackage.id).where(
                PrivateLessonPackage.organization_id == scope.organization_id,
                PrivateLessonPackage.venue_id == scope.venue_id,
                PrivateLessonPackage.student_id == item.student_id,
                PrivateLessonPackage.bound_coach_id == item.bound_coach_id,
                PrivateLessonPackage.id != item.id,
                PrivateLessonPackage.created_at > case.first_detected_at,
            )
        ).all()
    )
    facts = {
        "private_package_id": item.id,
        "replacement_package_ids": replacement_ids,
        "source_version": item.version,
    }
    return _resolve_or_monitor(
        case,
        resolved=bool(replacement_ids),
        resolved_reason="private_package_renewed",
        monitoring_reason="private_package_not_renewed",
        facts=facts,
    )


def verify_class_replacement(
    db: Session,
    scope: RequestScope,
    case: OperationCase,
) -> VerificationResult:
    original = db.scalar(
        select(ClassSession).where(
            ClassSession.id == case.subject_id,
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
        )
    )
    if original is None:
        return VerificationResult("escalate", "subject_missing", {})
    replacements = list(
        db.scalars(
            select(ClassSession).where(
                ClassSession.organization_id == scope.organization_id,
                ClassSession.venue_id == scope.venue_id,
                ClassSession.replacement_for_session_id == original.id,
                ClassSession.status != "cancelled",
            )
        ).all()
    )
    if len(replacements) != 1:
        return VerificationResult(
            "monitoring" if not replacements else "escalate",
            "replacement_missing" if not replacements else "replacement_not_unique",
            {"replacement_ids": [item.id for item in replacements]},
        )
    replacement = replacements[0]
    entry = db.scalar(
        select(ScheduleEntry).where(
            ScheduleEntry.id == replacement.schedule_entry_id,
            ScheduleEntry.organization_id == scope.organization_id,
            ScheduleEntry.venue_id == scope.venue_id,
            ScheduleEntry.status == "confirmed",
        )
    )
    if entry is None:
        return VerificationResult("escalate", "replacement_schedule_missing", {})
    allocations = list(
        db.scalars(
            select(ScheduleAllocation).where(
                ScheduleAllocation.organization_id == scope.organization_id,
                ScheduleAllocation.venue_id == scope.venue_id,
                ScheduleAllocation.schedule_entry_id == entry.id,
                ScheduleAllocation.active.is_(True),
            )
        ).all()
    )
    resources = [Resource(item.resource_type, item.resource_id) for item in allocations]
    conflicts = find_conflicts(
        db,
        resources,
        replacement.scheduled_start,
        replacement.scheduled_end,
        exclude_entry_id=entry.id,
    )
    tool_call = db.scalar(
        select(OperationToolCall).where(
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
            OperationToolCall.case_id == case.id,
            OperationToolCall.tool_key == "schedule_cancelled_class_replacement",
            OperationToolCall.state == "succeeded",
            OperationToolCall.result_reference == f"class_session:{replacement.id}",
        )
    )
    audit_exists = db.scalar(
        select(AuditLog.id).where(
            AuditLog.organization_id == scope.organization_id,
            AuditLog.venue_id == scope.venue_id,
            AuditLog.entity_type == "class_session",
            AuditLog.entity_id == original.id,
            AuditLog.action_type == "class_session.replacement_scheduled",
        )
    )
    expected_coaches = set(tool_call.normalized_input.get("coach_ids", [])) if tool_call else set()
    expected_courts = set(tool_call.normalized_input.get("court_ids", [])) if tool_call else set()
    actual_coaches = {item.resource_id for item in allocations if item.resource_type == "coach"}
    actual_courts = {item.resource_id for item in allocations if item.resource_type == "court"}
    valid = (
        original.replacement_decision == "scheduled"
        and not conflicts
        and tool_call is not None
        and audit_exists is not None
        and actual_coaches == expected_coaches
        and actual_courts == expected_courts
        and _aware(replacement.scheduled_start)
        == _aware(datetime.fromisoformat(str(tool_call.normalized_input.get("starts_at"))))
        and _aware(replacement.scheduled_end)
        == _aware(datetime.fromisoformat(str(tool_call.normalized_input.get("ends_at"))))
    )
    facts = {
        "cancelled_session_id": original.id,
        "replacement_session_id": replacement.id,
        "schedule_entry_id": entry.id,
        "allocation_ids": [item.id for item in allocations],
        "conflict_count": len(conflicts),
        "tool_call_id": tool_call.id if tool_call else None,
        "audit_log_id": audit_exists,
    }
    return _resolve_or_monitor(
        case,
        resolved=valid,
        resolved_reason="replacement_verified",
        monitoring_reason="replacement_verification_failed",
        facts=facts,
    )
