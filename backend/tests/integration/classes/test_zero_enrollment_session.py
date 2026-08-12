from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.class_cancellation import mark_not_held_no_enrollment
from shuttlecube.application.operations.cases import upsert_detected_case
from shuttlecube.application.operations.detectors import DetectorRegistry, detect_overdue_attendance
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.organization_models import Organization
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.payroll.models import CoachFee
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry


def _policy_config() -> dict[str, object]:
    return {
        "receivable_followup": {"aging_days": 7, "escalation_days": 30, "max_attempts": 4},
        "renewal": {
            "fixed_class_days": 30,
            "private_package_expiry_days": 30,
            "private_package_remaining_units": 3,
            "cadence_days": 7,
        },
        "attendance": {"grace_hours": 1},
        "replacement": {"window_days": 14, "slot_minutes": 30, "resource_mode": "original_only"},
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
        "runtime": {"case_sla_days": 3, "approval_expiry_minutes": 60, "retry_limit": 2},
    }


def _zero_enrollment_session(db: Session) -> tuple[ClassSession, ScheduleEntry, ScheduleAllocation, OperationsPolicy, RequestScope]:
    now = datetime.now(UTC)
    organization = Organization(name="零学员课程测试机构")
    venue = Venue(organization_id=organization.id, name="零学员课程测试场馆")
    fixed_class = FixedClass(
        organization_id=organization.id,
        venue_id=venue.id,
        name="测试周五固定班",
        class_type="training",
        start_date=date.today(),
        default_start_time=time(18),
        duration_minutes=60,
        session_count=1,
        capacity=10,
        default_coach_id="coach-1",
        required_court_count=1,
        student_unit_price=Decimal("100"),
        coach_fee_per_session=Decimal("80"),
        status="active",
    )
    session = ClassSession(
        organization_id=organization.id,
        venue_id=venue.id,
        fixed_class_id=fixed_class.id,
        sequence_number=1,
        scheduled_start=now - timedelta(hours=3),
        scheduled_end=now - timedelta(hours=2),
        actual_coach_id="coach-1",
        status="scheduled",
    )
    db.add_all([organization, venue, fixed_class, session])
    db.flush()
    entry = ScheduleEntry(
        organization_id=organization.id,
        venue_id=venue.id,
        source_type="class_session",
        source_id=session.id,
        title=fixed_class.name,
        starts_at=session.scheduled_start,
        ends_at=session.scheduled_end,
        status="confirmed",
    )
    db.add(entry)
    db.flush()
    allocation = ScheduleAllocation(
        organization_id=organization.id,
        venue_id=venue.id,
        schedule_entry_id=entry.id,
        resource_type="coach",
        resource_id="coach-1",
        starts_at=entry.starts_at,
        ends_at=entry.ends_at,
        active=True,
    )
    session.schedule_entry_id = entry.id
    policy = OperationsPolicy(
        organization_id=organization.id,
        venue_id=venue.id,
        policy_version=1,
        schema_version=1,
        config=_policy_config(),
        config_hash="zero-enrollment-policy",
        state="active",
        effective_from=now - timedelta(days=1),
        created_by="owner-1",
    )
    db.add_all([allocation, policy])
    db.commit()
    scope = RequestScope(
        organization_id=organization.id,
        venue_id=venue.id,
        user_id="owner-1",
        membership_id="membership-1",
        capabilities=frozenset({"operations.case.manage"}),
    )
    return session, entry, allocation, policy, scope


def test_zero_enrollment_session_is_cancelled_without_attendance_or_coach_fee(db: Session, admin) -> None:
    session, entry, allocation, _, _ = _zero_enrollment_session(db)

    mark_not_held_no_enrollment(
        db,
        session,
        actor_id=admin.id,
        request_id="zero-enrollment-not-held",
        version=session.version,
    )

    assert session.status == "cancelled"
    assert session.replacement_decision == "waived"
    assert session.attendance_finalized_at is None
    assert entry.status == "cancelled"
    assert entry.cancellation_reason == "本节无报名学员，未实际开课"
    assert allocation.active is False
    assert db.scalar(select(CoachFee).where(CoachFee.source_id == session.id)) is None


def test_zero_enrollment_session_endpoint_returns_the_cancelled_state(db: Session, authenticated) -> None:
    client, headers = authenticated
    session, entry, allocation, _, _ = _zero_enrollment_session(db)

    response = client.post(
        f"/api/v1/class-sessions/{session.id}/no-enrollment:mark-not-held",
        json={"version": session.version},
        headers=headers,
    )

    assert response.status_code == 200, response.json()
    assert response.json() | {"version": None} == {
        "session_id": session.id,
        "status": "cancelled",
        "replacement_decision": "waived",
        "version": None,
    }
    assert entry.status == "cancelled"
    assert allocation.active is False


def test_no_enrollment_action_rejects_a_class_that_now_has_an_active_student(db: Session, admin) -> None:
    session, _, _, _, scope = _zero_enrollment_session(db)
    student = Student(organization_id=scope.organization_id, name="新报名学员")
    enrollment = Enrollment(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        student_id=student.id,
        fixed_class_id=session.fixed_class_id,
        enrolled_on=date.today(),
        purchased_units=1,
        unit_price=Decimal("100"),
        suggested_receivable=Decimal("100"),
        actual_receivable=Decimal("100"),
        status="active",
    )
    db.add_all([student, enrollment])
    db.commit()

    with pytest.raises(BusinessError) as exc:
        mark_not_held_no_enrollment(
            db,
            session,
            actor_id=admin.id,
            request_id="zero-enrollment-stale-page",
            version=session.version,
        )

    assert exc.value.code == "session_has_active_enrollments"
    assert session.status == "scheduled"


def test_operations_marks_zero_enrollment_as_not_held_work_instead_of_attendance(db: Session) -> None:
    session, _, _, policy, scope = _zero_enrollment_session(db)
    now = datetime.now(UTC)

    evidence = detect_overdue_attendance(db, scope, policy, now)

    assert len(evidence) == 1
    assert evidence[0].subject_id == session.id
    assert evidence[0].facts["active_enrollment_count"] == 0
    assert evidence[0].facts["recommended_action"] == "mark_not_held_no_enrollment"
    definition = DetectorRegistry.default().get("attendance.overdue")
    case, _ = upsert_detected_case(
        db,
        scope=scope,
        definition=definition,
        evidence=evidence[0],
        case_sla_days=3,
        detected_at=now,
    )
    assert case.title == "零学员课程尚未标记为未开课"
