from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.coach_fees import ensure_class_session_fee
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.classes.enrollment_models import (
    AttendanceRecord,
    Enrollment,
    LessonUnitLedger,
)
from shuttlecube.infrastructure.database.base import utc_now


@dataclass(frozen=True)
class AttendanceDecision:
    student_id: str
    enrollment_id: str
    status: str
    deduct_units: int
    note: str | None = None


def balance(db: Session, enrollment_id: str) -> int:
    last = db.scalars(
        select(LessonUnitLedger)
        .where(LessonUnitLedger.owner_id == enrollment_id, LessonUnitLedger.status == "effective")
        .order_by(LessonUnitLedger.operated_at.desc())
    ).first()
    return last.balance_after if last else 0


def finalize_attendance(
    db: Session,
    class_session: ClassSession,
    decisions: list[AttendanceDecision],
    actor_id: str,
    idempotency_key: str,
) -> list[AttendanceRecord]:
    if class_session.status == "completed":
        return list(
            db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.class_session_id == class_session.id
                )
            ).all()
        )
    if class_session.status != "scheduled":
        raise BusinessError(409, "invalid_session_state", "只有待上课课程可以完成考勤")
    records = []
    seen_students: set[str] = set()
    seen_enrollments: set[str] = set()
    for item in decisions:
        if item.student_id in seen_students or item.enrollment_id in seen_enrollments:
            raise BusinessError(422, "duplicate_attendance_decision", "同一学员不能重复提交考勤")
        enrollment = db.get(Enrollment, item.enrollment_id)
        if (
            enrollment is None
            or enrollment.fixed_class_id != class_session.fixed_class_id
            or enrollment.student_id != item.student_id
            or enrollment.status != "active"
        ):
            raise BusinessError(422, "invalid_attendance_enrollment", "考勤学员不属于当前班级")
        seen_students.add(item.student_id)
        seen_enrollments.add(item.enrollment_id)
        before = balance(db, item.enrollment_id)
        after = before - item.deduct_units
        if after < 0:
            raise BusinessError(422, "insufficient_units", "学员课时不足")
        ledger = None
        if item.deduct_units:
            ledger = LessonUnitLedger(
                owner_type="enrollment",
                owner_id=item.enrollment_id,
                change_type="attendance",
                delta=-item.deduct_units,
                balance_before=before,
                balance_after=after,
                source_type="class_session",
                source_id=class_session.id,
                reason=item.note,
                operated_by=actor_id,
                operated_at=utc_now(),
                idempotency_key=f"{idempotency_key}:{item.enrollment_id}",
            )
            db.add(ledger)
            db.flush()
        record = AttendanceRecord(
            class_session_id=class_session.id,
            student_id=item.student_id,
            enrollment_id=item.enrollment_id,
            status=item.status,
            deduct_units=item.deduct_units,
            grants_makeup=False,
            lesson_ledger_id=ledger.id if ledger else None,
            decision_note=item.note,
        )
        db.add(record)
        db.flush()
        records.append(record)
    class_session.status = "completed"
    class_session.attendance_finalized_at = utc_now()
    ensure_class_session_fee(db, class_session)
    db.commit()
    return records
