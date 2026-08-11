from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.domain.classes.class_models import FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.customers.models import Guardian, Student, StudentGuardian
from shuttlecube.domain.finance.models import Payment, Receivable, Refund
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.operations.models import CaseActivity, OperationCase, OperationToolCall
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.security.passwords import hash_password


def test_confirmed_followup_is_idempotent_and_has_no_finance_side_effect(
    client: TestClient,
    db: Session,
) -> None:
    user = SystemUser(
        username="followup-owner",
        display_name="Owner",
        password_hash=hash_password("password123"),
    )
    organization = Organization(name="Followup Org")
    venue = Venue(
        organization_id=organization.id,
        name="Followup Venue",
        write_tools_enabled=True,
    )
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
    student = Student(organization_id=organization.id, name="Student", phone="13800000000")
    guardian = Guardian(organization_id=organization.id, name="Guardian", phone="13900000000")
    relation = StudentGuardian(
        organization_id=organization.id,
        student_id=student.id,
        guardian_id=guardian.id,
        relationship_label="parent",
        is_primary_contact=True,
    )
    fixed_class = FixedClass(
        organization_id=organization.id,
        venue_id=venue.id,
        name="Class",
        class_type="training",
        recurrence_rule="FREQ=WEEKLY",
        start_date=date(2026, 8, 1),
        default_start_time=time(18),
        duration_minutes=60,
        session_count=8,
        capacity=8,
        default_coach_id="coach-1",
        required_court_count=1,
        student_unit_price=Decimal("100"),
        status="active",
    )
    enrollment = Enrollment(
        organization_id=organization.id,
        venue_id=venue.id,
        student_id=student.id,
        fixed_class_id=fixed_class.id,
        enrolled_on=date(2026, 8, 1),
        purchased_units=8,
        unit_price=Decimal("100"),
        suggested_receivable=Decimal("800"),
        actual_receivable=Decimal("800"),
        status="active",
    )
    receivable = Receivable(
        organization_id=organization.id,
        venue_id=venue.id,
        source_type="enrollment",
        source_id=enrollment.id,
        suggested_amount=Decimal("800"),
        actual_amount=Decimal("800"),
    )
    now = datetime.now(UTC)
    case = OperationCase(
        organization_id=organization.id,
        venue_id=venue.id,
        case_type="receivable_followup",
        subject_type="receivable",
        subject_id=receivable.id,
        case_key="case-key-followup",
        detector_key="receivable.aging_followup",
        detector_version=1,
        policy_key="default_operations",
        policy_version=1,
        occurrence_no=1,
        fingerprint="fingerprint",
        evidence_hash="evidence-hash",
        evidence={"facts": {}, "source_refs": []},
        severity="medium",
        priority_score=Decimal("50"),
        title="Receivable followup",
        state="open",
        first_detected_at=now,
        last_detected_at=now,
        queue_key="revenue",
        required_capability="operations.receivable.followup.read",
        created_by_type="detector",
    )
    db.add_all(
        [
            user,
            organization,
            venue,
            organization_membership,
            venue_membership,
            student,
            guardian,
            relation,
            fixed_class,
            enrollment,
            receivable,
            case,
        ]
    )
    db.commit()

    login = client.post(
        "/api/v1/session/login",
        json={"username": user.username, "password": "password123"},
    )
    assert login.status_code == 200
    body = {
        "activity_type": "contact_result",
        "channel": "phone",
        "contact_subject_type": "guardian",
        "contact_subject_id": guardian.id,
        "outcome_code": "follow_later",
        "summary": "Contacted; check again tomorrow.",
        "happened_at": now.isoformat(),
        "next_check_at": (now + timedelta(days=1)).isoformat(),
        "expected_case_version": case.version,
        "expected_occurrence_no": case.occurrence_no,
        "confirmed_by_user": True,
    }
    headers = {
        "X-CSRF-Token": login.json()["csrf_token"],
        "Idempotency-Key": "followup-once",
    }
    first = client.post(
        f"/api/v1/operations/cases/{case.id}/activities",
        json=body,
        headers=headers,
    )
    second = client.post(
        f"/api/v1/operations/cases/{case.id}/activities",
        json=body,
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert db.scalar(select(func.count(CaseActivity.id))) == 1
    assert db.scalar(select(func.count(OperationToolCall.id))) == 1
    assert db.scalar(select(func.count(Payment.id))) == 0
    assert db.scalar(select(func.count(Refund.id))) == 0
    db.refresh(receivable)
    assert receivable.actual_amount == Decimal("800")

