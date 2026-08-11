from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.evidence import build_evidence
from shuttlecube.application.operations.reconciliation import (
    ReconciliationRegistry,
    reconciliation_payload,
)
from shuttlecube.application.queries.receivables import receivable_summary
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment, LessonUnitLedger
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.operations.models import OperationCase
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.operations.schemas import (
    EvidenceEnvelope,
    OperationsPolicyConfig,
    SourceReference,
)
from shuttlecube.domain.private_lessons.models import PrivateLessonPackage
from shuttlecube.domain.scheduling.models import ScheduleAllocation

Detector = Callable[
    [Session, RequestScope, OperationsPolicy, datetime], list[EvidenceEnvelope]
]


@dataclass(frozen=True)
class DetectorDefinition:
    detector_key: str
    version: int
    case_type: str
    queue_key: str
    required_capability: str
    title: str
    implementation: Detector | None = None


class DetectorRegistry:
    def __init__(self, definitions: Iterable[DetectorDefinition]) -> None:
        items = list(definitions)
        self._items = {item.detector_key: item for item in items}
        if len(items) != len(self._items):
            raise ValueError("duplicate detector key")

    @classmethod
    def default(cls) -> DetectorRegistry:
        return cls(
            (
                DetectorDefinition(
                    "attendance.overdue",
                    1,
                    "attendance_overdue",
                    "operations",
                    "operations.case.manage",
                    "课程逾期未完成考勤",
                    detect_overdue_attendance,
                ),
                DetectorDefinition(
                    "class.replacement_pending",
                    1,
                    "class_replacement_pending",
                    "training",
                    "operations.case.manage",
                    "取消课程等待补排",
                    detect_replacement_pending,
                ),
                DetectorDefinition(
                    "receivable.aging_followup",
                    1,
                    "receivable_followup",
                    "revenue",
                    "operations.receivable.followup.read",
                    "应收款持续未结清",
                    detect_receivable_aging,
                ),
                DetectorDefinition(
                    "reconciliation.failed",
                    1,
                    "reconciliation_failure",
                    "control",
                    "operations.case.manage",
                    "业务数据一致性异常",
                    detect_reconciliation_failures,
                ),
                DetectorDefinition(
                    "class.renewal_opportunity",
                    1,
                    "fixed_class_renewal",
                    "revenue",
                    "operations.case.manage",
                    "固定班进入续费窗口",
                    detect_fixed_class_renewal,
                ),
                DetectorDefinition(
                    "private_package.renewal_opportunity",
                    1,
                    "private_package_renewal",
                    "revenue",
                    "operations.case.manage",
                    "私教课包进入续费窗口",
                    detect_private_package_renewal,
                ),
            )
        )

    def get(self, detector_key: str) -> DetectorDefinition:
        try:
            return self._items[detector_key]
        except KeyError as exc:
            raise KeyError(f"unknown detector: {detector_key}") from exc

    def enabled(self) -> tuple[DetectorDefinition, ...]:
        return tuple(item for item in self._items.values() if item.implementation is not None)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def detect_reconciliation_failures(
    db: Session,
    scope: RequestScope,
    policy: OperationsPolicy,
    now: datetime,
) -> list[EvidenceEnvelope]:
    results = ReconciliationRegistry.default().run(db, scope)
    evidence_items: list[EvidenceEnvelope] = []
    for result in results:
        previous = db.scalar(
            select(OperationCase).where(
                OperationCase.organization_id == scope.organization_id,
                OperationCase.venue_id == scope.venue_id,
                OperationCase.detector_key == "reconciliation.failed",
                OperationCase.subject_type == "reconciliation_issue",
                OperationCase.subject_id == result.issue_id,
            )
        )
        previous_facts = (previous.evidence or {}).get("facts", {}) if previous else {}
        prior_count = (
            int(previous_facts.get("failure_count", 0))
            if previous is not None
            and previous.state not in {"resolved", "dismissed"}
            and isinstance(previous_facts, dict)
            else 0
        )
        failure_count = prior_count + 1
        severity = "critical" if failure_count >= 3 else result.severity
        payload = reconciliation_payload(result)
        evidence_items.append(
            build_evidence(
                scope=scope,
                detector_key="reconciliation.failed",
                detector_version=1,
                policy_version=policy.policy_version,
                subject_type="reconciliation_issue",
                subject_id=result.issue_id,
                severity=severity,
                facts={
                    "reconciliation": payload,
                    "failure_count": failure_count,
                    "automatic_repair_available": False,
                },
                source_refs=tuple(
                    SourceReference(kind=item.kind, id=item.id, version=item.version)
                    for item in result.affected_refs
                ),
                business_links=tuple(item.route for item in result.repair_entry_points),
                generated_at=now,
            )
        )
    return evidence_items


def detect_overdue_attendance(
    db: Session,
    scope: RequestScope,
    policy: OperationsPolicy,
    now: datetime,
) -> list[EvidenceEnvelope]:
    config = OperationsPolicyConfig.model_validate(policy.config)
    cutoff = _aware(now) - timedelta(hours=config.attendance.grace_hours)
    rows = db.execute(
        select(ClassSession, FixedClass)
        .join(FixedClass, FixedClass.id == ClassSession.fixed_class_id)
        .where(
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
            FixedClass.organization_id == scope.organization_id,
            FixedClass.venue_id == scope.venue_id,
            FixedClass.status == "active",
            ClassSession.status == "scheduled",
            ClassSession.attendance_finalized_at.is_(None),
            ClassSession.scheduled_end <= cutoff,
        )
        .order_by(ClassSession.scheduled_end, ClassSession.id)
    ).all()
    result: list[EvidenceEnvelope] = []
    for session, fixed_class in rows:
        ended_at = _aware(session.scheduled_end)
        overdue_hours = max(int((_aware(now) - ended_at).total_seconds() // 3600), 0)
        result.append(
            build_evidence(
                scope=scope,
                detector_key="attendance.overdue",
                detector_version=1,
                policy_version=policy.policy_version,
                subject_type="class_session",
                subject_id=session.id,
                severity="high" if overdue_hours >= 48 else "medium",
                facts={
                    "class_session_id": session.id,
                    "fixed_class_id": fixed_class.id,
                    "fixed_class_name": fixed_class.name,
                    "sequence_number": session.sequence_number,
                    "scheduled_end": ended_at.isoformat(),
                    "grace_hours": config.attendance.grace_hours,
                    "overdue_hours": overdue_hours,
                    "attendance_finalized": False,
                },
                source_refs=(
                    SourceReference(kind="class_session", id=session.id, version=session.version),
                    SourceReference(kind="fixed_class", id=fixed_class.id, version=fixed_class.version),
                ),
                business_links=(f"/classes/{fixed_class.id}",),
                generated_at=now,
            )
        )
    return result


def detect_replacement_pending(
    db: Session,
    scope: RequestScope,
    policy: OperationsPolicy,
    now: datetime,
) -> list[EvidenceEnvelope]:
    rows = db.execute(
        select(ClassSession, FixedClass)
        .join(FixedClass, FixedClass.id == ClassSession.fixed_class_id)
        .where(
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
            ClassSession.status == "cancelled",
            ClassSession.replacement_decision == "pending",
            FixedClass.organization_id == scope.organization_id,
            FixedClass.venue_id == scope.venue_id,
        )
        .order_by(ClassSession.scheduled_start, ClassSession.id)
    ).all()
    result: list[EvidenceEnvelope] = []
    for session, fixed_class in rows:
        allocations = db.scalars(
            select(ScheduleAllocation).where(
                ScheduleAllocation.organization_id == scope.organization_id,
                ScheduleAllocation.venue_id == scope.venue_id,
                ScheduleAllocation.schedule_entry_id == session.schedule_entry_id,
            )
        ).all()
        coach_ids = sorted(
            {
                row.resource_id
                for row in allocations
                if row.resource_type == "coach"
            }
            or {session.actual_coach_id}
        )
        court_ids = sorted(
            {row.resource_id for row in allocations if row.resource_type == "court"}
        )
        result.append(
            build_evidence(
                scope=scope,
                detector_key="class.replacement_pending",
                detector_version=1,
                policy_version=policy.policy_version,
                subject_type="class_session",
                subject_id=session.id,
                severity="high",
                facts={
                    "cancelled_session_id": session.id,
                    "fixed_class_id": fixed_class.id,
                    "fixed_class_name": fixed_class.name,
                    "original_start": _aware(session.scheduled_start).isoformat(),
                    "original_end": _aware(session.scheduled_end).isoformat(),
                    "duration_minutes": int(
                        (_aware(session.scheduled_end) - _aware(session.scheduled_start)).total_seconds()
                        // 60
                    ),
                    "coach_ids": coach_ids,
                    "court_ids": court_ids,
                    "required_court_count": fixed_class.required_court_count,
                    "student_availability_verified": False,
                },
                source_refs=(
                    SourceReference(kind="class_session", id=session.id, version=session.version),
                    SourceReference(
                        kind="fixed_class", id=fixed_class.id, version=fixed_class.version
                    ),
                ),
                business_links=(f"/classes/{fixed_class.id}",),
                generated_at=now,
            )
        )
    return result


def detect_receivable_aging(
    db: Session,
    scope: RequestScope,
    policy: OperationsPolicy,
    now: datetime,
) -> list[EvidenceEnvelope]:
    config = OperationsPolicyConfig.model_validate(policy.config)
    current = _aware(now)
    cutoff = current - timedelta(days=config.receivable_followup.aging_days)
    rows = db.scalars(
        select(Receivable)
        .where(
            Receivable.organization_id == scope.organization_id,
            Receivable.venue_id == scope.venue_id,
            Receivable.status.not_in(("void", "refunded", "settled")),
            Receivable.created_at <= cutoff,
        )
        .order_by(Receivable.created_at, Receivable.id)
    ).all()
    result: list[EvidenceEnvelope] = []
    for item in rows:
        summary = receivable_summary(db, item)
        if summary.outstanding_amount <= 0:
            continue
        aging_days = max((current - _aware(item.created_at)).days, 0)
        severity = (
            "high"
            if aging_days >= config.receivable_followup.escalation_days
            else "medium"
        )
        result.append(
            build_evidence(
                scope=scope,
                detector_key="receivable.aging_followup",
                detector_version=1,
                policy_version=policy.policy_version,
                subject_type="receivable",
                subject_id=item.id,
                severity=severity,
                facts={
                    "receivable_id": item.id,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "aging_days": aging_days,
                    "actual_receivable": str(summary.actual_amount),
                    "received": str(summary.received_amount),
                    "refunded": str(summary.refunded_amount),
                    "outstanding": str(summary.outstanding_amount),
                    "payment_status": summary.payment_status,
                },
                source_refs=(
                    SourceReference(kind="receivable", id=item.id, version=item.version),
                ),
                business_links=(f"/finance/receivables/{item.id}",),
                generated_at=now,
            )
        )
    return result


def detect_fixed_class_renewal(
    db: Session,
    scope: RequestScope,
    policy: OperationsPolicy,
    now: datetime,
) -> list[EvidenceEnvelope]:
    config = OperationsPolicyConfig.model_validate(policy.config)
    current = _aware(now)
    window_end = current + timedelta(days=config.renewal.fixed_class_days)
    rows = db.execute(
        select(FixedClass, func.max(ClassSession.scheduled_end))
        .join(ClassSession, ClassSession.fixed_class_id == FixedClass.id)
        .where(
            FixedClass.organization_id == scope.organization_id,
            FixedClass.venue_id == scope.venue_id,
            FixedClass.status == "active",
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
        )
        .group_by(FixedClass.id)
        .having(func.max(ClassSession.scheduled_end) <= window_end)
        .order_by(func.max(ClassSession.scheduled_end), FixedClass.id)
    ).all()
    result: list[EvidenceEnvelope] = []
    for fixed_class, latest_end in rows:
        active_enrollments = int(
            db.scalar(
                select(func.count(Enrollment.id)).where(
                    Enrollment.organization_id == scope.organization_id,
                    Enrollment.venue_id == scope.venue_id,
                    Enrollment.fixed_class_id == fixed_class.id,
                    Enrollment.status == "active",
                )
            )
            or 0
        )
        if active_enrollments == 0 or latest_end is None:
            continue
        remaining_sessions = int(
            db.scalar(
                select(func.count(ClassSession.id)).where(
                    ClassSession.organization_id == scope.organization_id,
                    ClassSession.venue_id == scope.venue_id,
                    ClassSession.fixed_class_id == fixed_class.id,
                    ClassSession.status == "scheduled",
                    ClassSession.scheduled_end >= current,
                )
            )
            or 0
        )
        result.append(
            build_evidence(
                scope=scope,
                detector_key="class.renewal_opportunity",
                detector_version=1,
                policy_version=policy.policy_version,
                subject_type="fixed_class",
                subject_id=fixed_class.id,
                severity="medium" if remaining_sessions <= 1 else "low",
                facts={
                    "fixed_class_id": fixed_class.id,
                    "class_name": fixed_class.name,
                    "latest_session_end": _aware(latest_end).isoformat(),
                    "remaining_scheduled_sessions": remaining_sessions,
                    "active_enrollments": active_enrollments,
                    "session_count": fixed_class.session_count,
                },
                source_refs=(
                    SourceReference(
                        kind="fixed_class", id=fixed_class.id, version=fixed_class.version
                    ),
                ),
                business_links=(f"/classes/{fixed_class.id}",),
                generated_at=now,
            )
        )
    return result


def detect_private_package_renewal(
    db: Session,
    scope: RequestScope,
    policy: OperationsPolicy,
    now: datetime,
) -> list[EvidenceEnvelope]:
    config = OperationsPolicyConfig.model_validate(policy.config)
    current = _aware(now)
    expiry_cutoff = current + timedelta(days=config.renewal.private_package_expiry_days)
    packages = db.scalars(
        select(PrivateLessonPackage)
        .where(
            PrivateLessonPackage.organization_id == scope.organization_id,
            PrivateLessonPackage.venue_id == scope.venue_id,
            PrivateLessonPackage.status == "active",
        )
        .order_by(PrivateLessonPackage.valid_until, PrivateLessonPackage.id)
    ).all()
    result: list[EvidenceEnvelope] = []
    for package in packages:
        remaining_units = int(
            db.scalar(
                select(func.coalesce(func.sum(LessonUnitLedger.delta), 0)).where(
                    LessonUnitLedger.organization_id == scope.organization_id,
                    LessonUnitLedger.venue_id == scope.venue_id,
                    LessonUnitLedger.owner_type == "private_package",
                    LessonUnitLedger.owner_id == package.id,
                    LessonUnitLedger.status == "effective",
                )
            )
            or 0
        )
        valid_until = _aware(package.valid_until) if package.valid_until else None
        expiry_due = valid_until is not None and valid_until <= expiry_cutoff
        units_due = remaining_units <= config.renewal.private_package_remaining_units
        if not expiry_due and not units_due:
            continue
        result.append(
            build_evidence(
                scope=scope,
                detector_key="private_package.renewal_opportunity",
                detector_version=1,
                policy_version=policy.policy_version,
                subject_type="private_package",
                subject_id=package.id,
                severity="medium" if remaining_units <= 0 else "low",
                facts={
                    "private_package_id": package.id,
                    "student_id": package.student_id,
                    "coach_id": package.bound_coach_id,
                    "valid_until": valid_until.isoformat() if valid_until else None,
                    "remaining_units": remaining_units,
                    "expiry_due": expiry_due,
                    "units_due": units_due,
                },
                source_refs=(
                    SourceReference(
                        kind="private_package", id=package.id, version=package.version
                    ),
                ),
                business_links=(f"/private-lessons/packages/{package.id}",),
                generated_at=now,
            )
        )
    return result
