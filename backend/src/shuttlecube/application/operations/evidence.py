import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.queries.receivables import receivable_summary
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment, LessonUnitLedger
from shuttlecube.domain.customers.models import Guardian, Student, StudentGuardian
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.operations.models import CaseActivity, OperationCase
from shuttlecube.domain.operations.schemas import EvidenceEnvelope, SourceReference
from shuttlecube.domain.private_lessons.models import PrivateLessonPackage

EVIDENCE_SCHEMA_VERSION = 1


def _hash(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_business_link(route: str) -> str:
    if not route.startswith("/") or route.startswith("//") or "://" in route:
        raise ValueError("business links must be application-relative routes")
    return route


def build_evidence(
    *,
    scope: RequestScope,
    detector_key: str,
    detector_version: int,
    policy_version: int,
    subject_type: str,
    subject_id: str,
    severity: str,
    facts: dict[str, object],
    source_refs: Iterable[SourceReference],
    business_links: Iterable[str] = (),
    generated_at: datetime | None = None,
) -> EvidenceEnvelope:
    refs = sorted(
        source_refs,
        key=lambda ref: (ref.kind, ref.id, ref.version or 0),
    )
    stable_identity = {
        "organization_id": scope.organization_id,
        "venue_id": scope.venue_id,
        "detector_key": detector_key,
        "subject_type": subject_type,
        "subject_id": subject_id,
    }
    case_key = _hash(stable_identity)
    evidence_body = {
        **stable_identity,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "detector_version": detector_version,
        "policy_version": policy_version,
        "severity": severity,
        "facts": facts,
        "source_refs": [ref.model_dump(mode="json") for ref in refs],
    }
    return EvidenceEnvelope(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        detector_key=detector_key,
        detector_version=detector_version,
        policy_version=policy_version,
        subject_type=subject_type,
        subject_id=subject_id,
        case_key=case_key,
        severity_baseline=severity,
        facts=facts,
        source_refs=refs,
        business_links=[safe_business_link(route) for route in business_links],
        generated_at=generated_at or datetime.now(UTC),
        evidence_hash=_hash(evidence_body),
        fingerprint=_hash(
            {
                "case_key": case_key,
                "detector_version": detector_version,
                "policy_version": policy_version,
                "facts": facts,
                "source_refs": [ref.model_dump(mode="json") for ref in refs],
            }
        ),
    )


def _masked_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "未命名联系人"
    return f"{stripped[0]}*" if len(stripped) > 1 else "*"


def _student_contact(
    db: Session,
    *,
    scope: RequestScope,
    student_id: str,
) -> dict[str, object]:
    student = db.scalar(
        select(Student).where(
            Student.id == student_id,
            Student.organization_id == scope.organization_id,
        )
    )
    if student is None:
        return {"available": False, "reason": "student_not_found"}
    guardian = db.scalar(
        select(Guardian)
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .where(
            StudentGuardian.organization_id == scope.organization_id,
            StudentGuardian.student_id == student.id,
            Guardian.organization_id == scope.organization_id,
        )
        .order_by(StudentGuardian.is_primary_contact.desc(), Guardian.id)
    )
    if guardian is not None:
        return {
            "available": bool(guardian.phone or guardian.wechat_note),
            "subject_type": "guardian",
            "subject_id": guardian.id,
            "display_name": _masked_name(guardian.name),
        }
    return {
        "available": bool(student.phone),
        "subject_type": "student",
        "subject_id": student.id,
        "display_name": _masked_name(student.name),
    }


def _activity_timeline(
    db: Session,
    *,
    scope: RequestScope,
    case_id: str,
) -> list[dict[str, object]]:
    rows = db.scalars(
        select(CaseActivity)
        .where(
            CaseActivity.organization_id == scope.organization_id,
            CaseActivity.venue_id == scope.venue_id,
            CaseActivity.case_id == case_id,
        )
        .order_by(CaseActivity.happened_at.desc(), CaseActivity.created_at.desc())
        .limit(50)
    ).all()
    return [
        {
            "id": row.id,
            "activity_type": row.activity_type,
            "channel": row.channel,
            "outcome_code": row.outcome_code,
            "summary": row.summary,
            "happened_at": row.happened_at.isoformat(),
            "next_check_at": row.next_check_at.isoformat() if row.next_check_at else None,
            "operated_by": row.operated_by,
            "source": row.source,
        }
        for row in rows
    ]


def _case_subject_or_404(
    case: OperationCase,
    *,
    scope: RequestScope,
    allowed_types: set[str],
) -> None:
    if (
        case.organization_id != scope.organization_id
        or case.venue_id != scope.venue_id
        or case.case_type not in allowed_types
    ):
        raise BusinessError(404, "scope_not_found", "运营案件不存在")


def receivable_followup_context(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    now: datetime | None = None,
) -> dict[str, object]:
    _case_subject_or_404(case, scope=scope, allowed_types={"receivable_followup"})
    item = db.scalar(
        select(Receivable).where(
            Receivable.id == case.subject_id,
            Receivable.organization_id == scope.organization_id,
            Receivable.venue_id == scope.venue_id,
        )
    )
    if item is None:
        raise BusinessError(404, "scope_not_found", "应收记录不存在")
    summary = receivable_summary(db, item)
    student_id: str | None = None
    if item.source_type == "enrollment":
        source = db.scalar(
            select(Enrollment).where(
                Enrollment.id == item.source_id,
                Enrollment.organization_id == scope.organization_id,
                Enrollment.venue_id == scope.venue_id,
            )
        )
        student_id = source.student_id if source else None
    elif item.source_type == "private_package":
        source = db.scalar(
            select(PrivateLessonPackage).where(
                PrivateLessonPackage.id == item.source_id,
                PrivateLessonPackage.organization_id == scope.organization_id,
                PrivateLessonPackage.venue_id == scope.venue_id,
            )
        )
        student_id = source.student_id if source else None
    current = now or datetime.now(UTC)
    created_at = item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=UTC)
    return {
        "receivable_id": item.id,
        "business_source": {
            "source_type": item.source_type,
            "source_id": item.source_id,
            "display_name": f"{item.source_type}:{item.source_id[:8]}",
        },
        "amounts": {
            "actual_receivable": str(summary.actual_amount),
            "received": str(summary.received_amount),
            "refunded": str(summary.refunded_amount),
            "net_received": str(summary.net_received),
            "outstanding": str(summary.outstanding_amount),
            "payment_status": summary.payment_status,
        },
        "aging_days": max((current - created_at).days, 0),
        "contact": (
            _student_contact(db, scope=scope, student_id=student_id)
            if student_id
            else {"available": False, "reason": "contact_not_supported_for_source"}
        ),
        "activities": _activity_timeline(db, scope=scope, case_id=case.id),
        "next_allowed_followup_at": case.next_check_at.isoformat()
        if case.next_check_at
        else None,
    }


def _scoped_lesson_balance(
    db: Session,
    *,
    scope: RequestScope,
    owner_type: str,
    owner_id: str,
) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(LessonUnitLedger.delta), 0)).where(
                LessonUnitLedger.organization_id == scope.organization_id,
                LessonUnitLedger.venue_id == scope.venue_id,
                LessonUnitLedger.owner_type == owner_type,
                LessonUnitLedger.owner_id == owner_id,
                LessonUnitLedger.status == "effective",
            )
        )
        or 0
    )


def renewal_followup_context(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
) -> dict[str, object]:
    _case_subject_or_404(
        case,
        scope=scope,
        allowed_types={"fixed_class_renewal", "private_package_renewal"},
    )
    if case.case_type == "fixed_class_renewal":
        fixed_class = db.scalar(
            select(FixedClass).where(
                FixedClass.id == case.subject_id,
                FixedClass.organization_id == scope.organization_id,
                FixedClass.venue_id == scope.venue_id,
            )
        )
        if fixed_class is None:
            raise BusinessError(404, "scope_not_found", "固定班不存在")
        latest_end = db.scalar(
            select(func.max(ClassSession.scheduled_end)).where(
                ClassSession.organization_id == scope.organization_id,
                ClassSession.venue_id == scope.venue_id,
                ClassSession.fixed_class_id == fixed_class.id,
            )
        )
        enrollment = db.scalar(
            select(Enrollment).where(
                Enrollment.organization_id == scope.organization_id,
                Enrollment.venue_id == scope.venue_id,
                Enrollment.fixed_class_id == fixed_class.id,
                Enrollment.status == "active",
            )
        )
        return {
            "renewal_type": "fixed_class",
            "subject_id": fixed_class.id,
            "end_at": latest_end.isoformat() if latest_end else None,
            "remaining_scheduled_sessions": int(
                db.scalar(
                    select(func.count(ClassSession.id)).where(
                        ClassSession.organization_id == scope.organization_id,
                        ClassSession.venue_id == scope.venue_id,
                        ClassSession.fixed_class_id == fixed_class.id,
                        ClassSession.status == "scheduled",
                    )
                )
                or 0
            ),
            "contact": _student_contact(db, scope=scope, student_id=enrollment.student_id)
            if enrollment
            else {"available": False, "reason": "no_active_enrollment"},
            "activities": _activity_timeline(db, scope=scope, case_id=case.id),
            "renewal_facts": {
                "session_count": fixed_class.session_count,
                "source_version": fixed_class.version,
            },
        }
    package = db.scalar(
        select(PrivateLessonPackage).where(
            PrivateLessonPackage.id == case.subject_id,
            PrivateLessonPackage.organization_id == scope.organization_id,
            PrivateLessonPackage.venue_id == scope.venue_id,
        )
    )
    if package is None:
        raise BusinessError(404, "scope_not_found", "私教课包不存在")
    return {
        "renewal_type": "private_package",
        "subject_id": package.id,
        "expires_on": package.valid_until.date().isoformat() if package.valid_until else None,
        "remaining_units": _scoped_lesson_balance(
            db,
            scope=scope,
            owner_type="private_package",
            owner_id=package.id,
        ),
        "contact": _student_contact(db, scope=scope, student_id=package.student_id),
        "activities": _activity_timeline(db, scope=scope, case_id=case.id),
        "renewal_facts": {
            "source_version": package.version,
            "replacement_package_ids": [
                item_id
                for item_id in db.scalars(
                    select(PrivateLessonPackage.id).where(
                        PrivateLessonPackage.organization_id == scope.organization_id,
                        PrivateLessonPackage.venue_id == scope.venue_id,
                        PrivateLessonPackage.student_id == package.student_id,
                        PrivateLessonPackage.bound_coach_id == package.bound_coach_id,
                        PrivateLessonPackage.id != package.id,
                        PrivateLessonPackage.created_at > case.first_detected_at,
                    )
                ).all()
            ],
        },
    }
