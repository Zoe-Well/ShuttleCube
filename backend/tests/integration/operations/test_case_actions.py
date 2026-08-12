from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.operations.models import OperationCase
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.security.passwords import hash_password


def test_attendance_case_action_context_and_immediate_verification(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(UTC)
    user = SystemUser(
        username="case-action-owner",
        display_name="Owner",
        password_hash=hash_password("password123"),
    )
    organization = Organization(name="Case Action Org")
    venue = Venue(organization_id=organization.id, name="Case Action Venue")
    organization_membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        status="active",
        organization_role="owner",
    )
    venue_membership = VenueMembership(
        organization_membership_id=organization_membership.id,
        organization_id=organization.id,
        venue_id=venue.id,
        role_key="owner",
        status="active",
    )
    student = Student(organization_id=organization.id, name="测试学员")
    fixed_class = FixedClass(
        organization_id=organization.id,
        venue_id=venue.id,
        name="测试周五固定班",
        class_type="training",
        recurrence_rule="FREQ=WEEKLY",
        start_date=date.today(),
        default_start_time=time(18),
        duration_minutes=60,
        session_count=8,
        capacity=10,
        default_coach_id="coach-1",
        required_court_count=1,
        student_unit_price=Decimal("100"),
        status="active",
    )
    session = ClassSession(
        organization_id=organization.id,
        venue_id=venue.id,
        fixed_class_id=fixed_class.id,
        sequence_number=6,
        scheduled_start=now - timedelta(days=1, hours=1),
        scheduled_end=now - timedelta(days=1),
        actual_coach_id="coach-1",
        status="scheduled",
    )
    enrollment = Enrollment(
        organization_id=organization.id,
        venue_id=venue.id,
        student_id=student.id,
        fixed_class_id=fixed_class.id,
        enrolled_on=date.today(),
        purchased_units=8,
        unit_price=Decimal("100"),
        suggested_receivable=Decimal("800"),
        actual_receivable=Decimal("800"),
        status="active",
    )
    case = OperationCase(
        organization_id=organization.id,
        venue_id=venue.id,
        case_type="attendance_overdue",
        subject_type="class_session",
        subject_id=session.id,
        case_key="case-action-attendance",
        detector_key="attendance.overdue",
        detector_version=1,
        policy_key="default_operations",
        policy_version=1,
        fingerprint="case-action-fingerprint",
        evidence_hash="case-action-evidence",
        evidence={
            "facts": {
                "class_session_id": session.id,
                "fixed_class_id": fixed_class.id,
                "fixed_class_name": fixed_class.name,
                "sequence_number": 6,
            }
        },
        severity="medium",
        priority_score=Decimal("50"),
        title="课程逾期未完成考勤",
        state="open",
        first_detected_at=now - timedelta(days=1),
        last_detected_at=now,
        queue_key="training",
        required_capability="operations.case.read",
    )
    db.add_all(
        [
            user,
            organization,
            venue,
            organization_membership,
            venue_membership,
            student,
            fixed_class,
            session,
            enrollment,
            case,
        ]
    )
    db.commit()

    login = client.post(
        "/api/v1/session/login",
        json={"username": user.username, "password": "password123"},
    )
    assert login.status_code == 200
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}

    context = client.get(f"/api/v1/operations/cases/{case.id}/action-context")
    assert context.status_code == 200
    assert context.json()["session"] | {
        "scheduled_start": None,
        "scheduled_end": None,
    } == {
        "id": session.id,
        "fixed_class_id": fixed_class.id,
        "fixed_class_name": "测试周五固定班",
        "sequence_number": 6,
        "scheduled_start": None,
        "scheduled_end": None,
        "status": "scheduled",
        "attendance_finalized_at": None,
        "version": session.version,
    }
    assert context.json()["enrollments"] == [
        {"id": enrollment.id, "student_id": student.id, "student_name": "测试学员"}
    ]

    session.attendance_finalized_at = now
    session.status = "completed"
    db.commit()
    verification = client.post(
        f"/api/v1/operations/cases/{case.id}:verify",
        headers=headers,
    )
    assert verification.status_code == 200
    assert verification.json()["state"] == "resolved"
    db.refresh(case)
    assert case.state == "resolved"

    closed_context = client.get(f"/api/v1/operations/cases/{case.id}/action-context")
    assert closed_context.status_code == 409
    assert closed_context.json()["title"] == "case_closed"
