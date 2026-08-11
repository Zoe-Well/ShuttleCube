from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.attendance import (
    AttendanceDecision,
    balance,
    finalize_attendance,
)
from shuttlecube.application.commands.class_cancellation import (
    cancel_and_replace,
    schedule_cancelled_session_replacement,
)
from shuttlecube.application.commands.classes import create_fixed_class, enroll_student
from shuttlecube.application.commands.fixed_class_management import (
    EnrollmentRenewal,
    archive_fixed_class,
    renew_fixed_class,
    reschedule_class_session,
    transfer_fixed_class_entitlement,
    update_class_capacity,
)
from shuttlecube.application.queries.receivables import receivable_for_source
from shuttlecube.application.queries.schedule import list_schedule
from shuttlecube.application.queries.student_entitlements import student_entitlement_summary
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import MakeupRecord
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import ScheduleEntry


def create_class(db: Session, name: str, court_id: str, start_day: date) -> FixedClass:
    fixed_class = FixedClass(
        name=name,
        class_type="training",
        start_date=start_day,
        default_start_time=time(10),
        duration_minutes=60,
        session_count=2,
        capacity=4,
        default_coach_id=f"coach-{name}",
        required_court_count=1,
        student_unit_price=Decimal("100.00"),
        coach_fee_per_session=Decimal("50.00"),
    )
    return create_fixed_class(db, fixed_class, [court_id])[0]


@pytest.fixture
def venue_and_courts(db: Session) -> tuple[Court, Court]:
    venue = Venue(name="生命周期测试场馆")
    db.add(venue)
    db.flush()
    courts = [
        Court(venue_id=venue.id, code="LC-1", name="生命周期 1 号场"),
        Court(venue_id=venue.id, code="LC-2", name="生命周期 2 号场"),
    ]
    db.add_all(courts)
    db.commit()
    return courts[0], courts[1]


def test_session_reschedule_cancel_and_later_replacement(
    db: Session, admin, venue_and_courts: tuple[Court, Court]
) -> None:
    fixed_class = create_class(db, "周末改期班", venue_and_courts[0].id, date(2026, 8, 8))
    sessions = list(
        db.scalars(
            select(ClassSession)
            .where(ClassSession.fixed_class_id == fixed_class.id)
            .order_by(ClassSession.sequence_number)
        ).all()
    )
    first, second = sessions
    old_entry_id = first.schedule_entry_id
    reschedule_class_session(
        db,
        first,
        starts_at=datetime(2026, 8, 8, 4, tzinfo=UTC),
        ends_at=datetime(2026, 8, 8, 5, tzinfo=UTC),
        reason="临时调整",
        actor_id=admin.id,
        request_id="reschedule-class-session",
        version=first.version,
    )
    old_entry = db.get(ScheduleEntry, old_entry_id)
    assert old_entry is not None and old_entry.status == "rescheduled"
    assert first.schedule_entry_id != old_entry_id
    visible_entries = list_schedule(
        db,
        datetime(2026, 8, 8, tzinfo=UTC),
        datetime(2026, 8, 9, tzinfo=UTC),
    )
    assert old_entry_id not in {entry.id for entry, _ in visible_entries}

    cancel_and_replace(
        db,
        second,
        reason="场馆维护",
        replacement_decision="pending",
        replacement_start=None,
        replacement_end=None,
        actor_id=admin.id,
        request_id="cancel-pending",
        version=second.version,
    )
    assert second.status == "cancelled" and second.replacement_decision == "pending"
    replacement = schedule_cancelled_session_replacement(
        db,
        second,
        replacement_start=datetime(2026, 8, 22, 2, tzinfo=UTC),
        replacement_end=datetime(2026, 8, 22, 3, tzinfo=UTC),
        actor_id=admin.id,
        request_id="schedule-replacement",
        version=second.version,
    )
    assert replacement.replacement_for_session_id == second.id
    assert second.replacement_decision == "scheduled"


def test_renew_archive_and_transfer_preserve_history_and_money(
    db: Session, admin, venue_and_courts: tuple[Court, Court]
) -> None:
    source_class = create_class(db, "续期来源班", venue_and_courts[0].id, date(2026, 8, 8))
    target_class = create_class(db, "权益目标班", venue_and_courts[1].id, date(2026, 8, 9))
    student = Student(name="权益转移学员")
    db.add(student)
    db.commit()
    enrollment = enroll_student(
        db,
        student_id=student.id,
        fixed_class=source_class,
        enrolled_on=date(2026, 8, 8),
        purchased_units=2,
        actual_receivable=Decimal("200.00"),
        reason=None,
        actor_id=admin.id,
    )
    first_session = db.scalars(
        select(ClassSession)
        .where(ClassSession.fixed_class_id == source_class.id)
        .order_by(ClassSession.sequence_number)
    ).first()
    assert first_session is not None
    leave_records = finalize_attendance(
        db,
        first_session,
        [AttendanceDecision(student.id, enrollment.id, "leave", 0, "请假保留课时")],
        admin.id,
        "lifecycle-attendance",
    )
    assert leave_records[0].deduct_units == 0 and leave_records[0].grants_makeup is False
    assert balance(db, enrollment.id) == 2
    assert db.query(MakeupRecord).count() == 0

    created, renewed = renew_fixed_class(
        db,
        source_class,
        additional_sessions=2,
        enrollment_renewals=[],
        actor_id=admin.id,
        request_id="renew-fixed-class",
        version=source_class.version,
    )
    receivable = receivable_for_source(db, "enrollment", enrollment.id)
    assert len(created) == 2 and renewed == []
    assert balance(db, enrollment.id) == 2
    assert receivable is not None and receivable.actual_amount == Decimal("200.00")

    with pytest.raises(BusinessError) as capacity_error:
        update_class_capacity(
            db,
            source_class,
            capacity=0,
            actor_id=admin.id,
            request_id="invalid-capacity",
            version=source_class.version,
        )
    assert capacity_error.value.code == "capacity_below_active_enrollments"

    archive_fixed_class(
        db,
        source_class,
        reason="学期结束",
        actor_id=admin.id,
        request_id="archive-fixed-class",
        version=source_class.version,
    )
    assert source_class.status == "archived" and enrollment.status == "expired"
    assert balance(db, enrollment.id) == 2
    visible_schedule = list_schedule(
        db,
        datetime(2026, 8, 1, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC),
    )
    source_session_ids = set(
        db.scalars(
            select(ClassSession.id).where(ClassSession.fixed_class_id == source_class.id)
        ).all()
    )
    assert not any(entry.source_id in source_session_ids for entry, _ in visible_schedule)

    target = transfer_fixed_class_entitlement(
        db,
        student_id=student.id,
        source_enrollment=enrollment,
        target_class=target_class,
        target_units=2,
        reason="按目标班价格折算",
        actor_id=admin.id,
        request_id="transfer-entitlement",
        version=enrollment.version,
    )
    assert enrollment.status == "transferred" and balance(db, enrollment.id) == 0
    assert target.acquisition_type == "transfer" and balance(db, target.id) == 2
    assert receivable_for_source(db, "enrollment", target.id) is None
    renew_fixed_class(
        db,
        target_class,
        additional_sessions=1,
        enrollment_renewals=[EnrollmentRenewal(target.id, 1, None, None)],
        actor_id=admin.id,
        request_id="renew-transferred-entitlement",
        version=target_class.version,
    )
    target_receivable = receivable_for_source(db, "enrollment", target.id)
    assert balance(db, target.id) == 3
    assert target_receivable is not None and target_receivable.actual_amount == Decimal("100.00")
    summary = student_entitlement_summary(db, student.id)
    assert summary["has_invalid"] is True
    assert any("权益目标班" in label for label in summary["active_labels"])
