from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.queries.receivables import receivable_for_source, receivable_summary
from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.private_lessons.models import PrivateLessonPackage
from shuttlecube.infrastructure.database.base import utc_now

ACTIVE_ENTITLEMENT_STATUSES = {"active"}


def _finance(db: Session, source_type: str, source_id: str) -> dict[str, object] | None:
    item = receivable_for_source(db, source_type, source_id)
    if item is None:
        return None
    summary = receivable_summary(db, item)
    return {
        "receivable_id": summary.receivable_id,
        "actual_amount": float(summary.actual_amount),
        "received_amount": float(summary.received_amount),
        "refunded_amount": float(summary.refunded_amount),
        "outstanding_amount": float(summary.outstanding_amount),
        "payment_status": summary.payment_status,
    }


def get_student_entitlements(db: Session, student_id: str) -> dict[str, object]:
    enrollments = list(
        db.scalars(
            select(Enrollment)
            .where(Enrollment.student_id == student_id)
            .order_by(Enrollment.created_at.desc())
        ).all()
    )
    packages = list(
        db.scalars(
            select(PrivateLessonPackage)
            .where(PrivateLessonPackage.student_id == student_id)
            .order_by(PrivateLessonPackage.created_at.desc())
        ).all()
    )
    classes = (
        {
            item.id: item
            for item in db.scalars(
                select(FixedClass).where(
                    FixedClass.id.in_([entry.fixed_class_id for entry in enrollments])
                )
            ).all()
        }
        if enrollments
        else {}
    )
    coaches = (
        {
            item.id: item
            for item in db.scalars(
                select(CoachProfile).where(
                    CoachProfile.id.in_([package.bound_coach_id for package in packages])
                )
            ).all()
        }
        if packages
        else {}
    )
    return {
        "student_id": student_id,
        "fixed_classes": [
            {
                "id": item.id,
                "fixed_class_id": item.fixed_class_id,
                "name": classes[item.fixed_class_id].name
                if item.fixed_class_id in classes
                else item.fixed_class_id,
                "purchased_units": item.purchased_units,
                "remaining_units": balance(db, item.id),
                "status": item.status,
                "acquisition_type": item.acquisition_type,
                "source_enrollment_id": item.source_enrollment_id,
                "transferred_to_enrollment_id": item.transferred_to_enrollment_id,
                "finance": _finance(db, "enrollment", item.id),
                "version": item.version,
            }
            for item in enrollments
        ],
        "private_packages": [
            {
                "id": item.id,
                "coach_id": item.bound_coach_id,
                "coach_name": coaches[item.bound_coach_id].name
                if item.bound_coach_id in coaches
                else item.bound_coach_id,
                "purchased_units": item.purchased_units,
                "remaining_units": balance(db, item.id),
                "valid_until": item.valid_until,
                "status": item.status,
                "finance": _finance(db, "private_package", item.id),
                "version": item.version,
            }
            for item in packages
        ],
    }


def student_entitlement_summary(db: Session, student_id: str) -> dict[str, object]:
    enrollments = list(
        db.scalars(select(Enrollment).where(Enrollment.student_id == student_id)).all()
    )
    packages = list(
        db.scalars(
            select(PrivateLessonPackage).where(PrivateLessonPackage.student_id == student_id)
        ).all()
    )
    labels: list[str] = []
    has_invalid = False
    for enrollment in enrollments:
        fixed_class = db.get(FixedClass, enrollment.fixed_class_id)
        if (
            enrollment.status not in ACTIVE_ENTITLEMENT_STATUSES
            or fixed_class is None
            or fixed_class.status != "active"
        ):
            has_invalid = True
            continue
        if fixed_class and fixed_class.status == "active":
            labels.append(f"固定班：{fixed_class.name}")
    for package in packages:
        valid_until = package.valid_until
        if valid_until is not None and valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=utc_now().tzinfo)
        if package.status not in ACTIVE_ENTITLEMENT_STATUSES or (
            valid_until is not None and valid_until < utc_now()
        ):
            has_invalid = True
            continue
        coach = db.get(CoachProfile, package.bound_coach_id)
        labels.append(f"私教课包：{coach.name if coach else package.bound_coach_id}")
    return {
        "active_labels": labels,
        "has_history": bool(enrollments or packages),
        "has_invalid": has_invalid,
    }
