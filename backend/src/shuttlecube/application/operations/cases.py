from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.operations.access import AccessDenied, require_capability
from shuttlecube.application.operations.detectors import DetectorDefinition
from shuttlecube.application.operations.state_machine import transition_case
from shuttlecube.domain.operations.models import OperationCase
from shuttlecube.domain.operations.schemas import EvidenceEnvelope

_PRIORITY = {
    "info": Decimal("10"),
    "low": Decimal("25"),
    "medium": Decimal("50"),
    "high": Decimal("75"),
    "critical": Decimal("100"),
}


def _fact_int(value: object, default: int = 0) -> int:
    if isinstance(value, (int, str)):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _case_title(definition: DetectorDefinition, evidence: EvidenceEnvelope) -> str:
    if (
        definition.case_type == "attendance_overdue"
        and _fact_int(evidence.facts.get("active_enrollment_count"), -1) == 0
    ):
        return "零学员课程尚未标记为未开课"
    return definition.title


def upsert_detected_case(
    db: Session,
    *,
    scope: RequestScope,
    definition: DetectorDefinition,
    evidence: EvidenceEnvelope,
    case_sla_days: int,
    detected_at: datetime | None = None,
) -> tuple[OperationCase, bool]:
    now = detected_at or datetime.now(UTC)
    item = db.scalar(
        select(OperationCase).where(
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
            OperationCase.detector_key == definition.detector_key,
            OperationCase.subject_type == evidence.subject_type,
            OperationCase.subject_id == evidence.subject_id,
        )
    )
    created = item is None
    if item is None:
        item = OperationCase(
            organization_id=scope.organization_id,
            venue_id=scope.venue_id,
            case_type=definition.case_type,
            subject_type=evidence.subject_type,
            subject_id=evidence.subject_id,
            case_key=evidence.case_key,
            detector_key=definition.detector_key,
            detector_version=definition.version,
            policy_key="default_operations",
            policy_version=evidence.policy_version,
            occurrence_no=1,
            fingerprint=evidence.fingerprint,
            evidence_hash=evidence.evidence_hash,
            evidence=evidence.model_dump(mode="json"),
            severity=evidence.severity_baseline,
            priority_score=_PRIORITY[evidence.severity_baseline],
            title=_case_title(definition, evidence),
            state="open",
            first_detected_at=now,
            last_detected_at=now,
            due_at=now + timedelta(days=case_sla_days),
            queue_key=definition.queue_key,
            required_capability=definition.required_capability,
            created_by_type="detector",
        )
        db.add(item)
    else:
        if item.state in {"resolved", "dismissed"}:
            transition_case(item, "open", now=now)
            item.first_detected_at = now
            item.due_at = now + timedelta(days=case_sla_days)
        item.detector_version = definition.version
        item.policy_version = evidence.policy_version
        item.fingerprint = evidence.fingerprint
        item.evidence_hash = evidence.evidence_hash
        item.evidence = evidence.model_dump(mode="json")
        item.severity = evidence.severity_baseline
        item.priority_score = _PRIORITY[evidence.severity_baseline]
        item.last_detected_at = now
        item.queue_key = definition.queue_key
        item.required_capability = definition.required_capability
        item.title = _case_title(definition, evidence)
    db.flush()
    facts = evidence.facts
    if (
        definition.case_type == "reconciliation_failure"
        and _fact_int(facts.get("failure_count")) >= 3
        and item.state not in {"escalated", "resolved", "dismissed"}
    ):
        transition_case(item, "escalated", now=now)
        db.flush()
    return item, created


def dismiss_case(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    reason: str,
    expected_version: int,
    request_id: str,
) -> OperationCase:
    try:
        require_capability(scope, "operations.case.manage")
    except AccessDenied as exc:
        raise BusinessError(403, "capability_denied", "没有关闭运营案件的权限") from exc
    if (
        case.organization_id != scope.organization_id
        or case.venue_id != scope.venue_id
    ):
        raise BusinessError(404, "scope_not_found", "运营案件不存在")
    if case.version != expected_version:
        raise BusinessError(409, "concurrent_change", "案件已被其他人员更新")
    if case.state in {"resolved", "dismissed"}:
        return case
    transition_case(case, "dismissed", reason=reason)
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operation_case.dismissed",
        entity_type="operation_case",
        entity_id=case.id,
        request_id=request_id,
        before={"state": "active", "occurrence_no": case.occurrence_no},
        after={"state": "dismissed"},
        reason=reason,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.flush()
    return case
