from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.report_workflow import (
    enqueue_report_run,
    execute_report_workflow,
)
from shuttlecube.application.operations.runtime import RunBudget
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.classes.enrollment_models import AttendanceRecord, LessonUnitLedger
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.identity.organization_models import Organization
from shuttlecube.domain.operations.models import OperationsReportSnapshot
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.payroll.models import CoachFee
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import CourtBlock, ScheduleAllocation, ScheduleEntry
from shuttlecube.domain.venue_bookings.models import VenueBooking


def _policy_config() -> dict[str, object]:
    return {
        "receivable_followup": {"aging_days": 7, "escalation_days": 30, "max_attempts": 4},
        "renewal": {
            "fixed_class_days": 30,
            "private_package_expiry_days": 30,
            "private_package_remaining_units": 3,
            "cadence_days": 7,
        },
        "attendance": {"grace_hours": 24},
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


def test_report_snapshot_is_repeatable_and_court_block_reduces_capacity(db: Session) -> None:
    organization = Organization(name="Report Org")
    venue = Venue(
        organization_id=organization.id,
        name="Report Venue",
        timezone="UTC",
        weekday_open_time=time(8),
        weekday_close_time=time(12),
        weekend_open_time=time(8),
        weekend_close_time=time(12),
    )
    court = Court(venue_id=venue.id, code="1", name="Court 1")
    policy = OperationsPolicy(
        organization_id=organization.id,
        venue_id=venue.id,
        policy_key="default_operations",
        policy_version=1,
        schema_version=1,
        config=_policy_config(),
        config_hash="policy-hash",
        state="active",
        effective_from=datetime.now(UTC) - timedelta(days=30),
        created_by="owner",
    )
    anchor = date.today() - timedelta(days=1)
    block = CourtBlock(
        organization_id=organization.id,
        venue_id=venue.id,
        reason="Maintenance",
        starts_at=datetime.combine(anchor, time(9), UTC),
        ends_at=datetime.combine(anchor, time(10), UTC),
        status="confirmed",
    )
    block_entry = ScheduleEntry(
        organization_id=organization.id,
        venue_id=venue.id,
        source_type="court_block",
        source_id=block.id,
        title="Maintenance",
        starts_at=block.starts_at,
        ends_at=block.ends_at,
        status="confirmed",
    )
    usage_entry = ScheduleEntry(
        organization_id=organization.id,
        venue_id=venue.id,
        source_type="venue_booking",
        source_id="booking-1",
        title="Booking",
        starts_at=datetime.combine(anchor, time(10), UTC),
        ends_at=datetime.combine(anchor, time(12), UTC),
        status="confirmed",
    )
    block_allocation = ScheduleAllocation(
        organization_id=organization.id,
        venue_id=venue.id,
        schedule_entry_id=block_entry.id,
        resource_type="court",
        resource_id=court.id,
        starts_at=block_entry.starts_at,
        ends_at=block_entry.ends_at,
        active=True,
    )
    usage_allocation = ScheduleAllocation(
        organization_id=organization.id,
        venue_id=venue.id,
        schedule_entry_id=usage_entry.id,
        resource_type="court",
        resource_id=court.id,
        starts_at=usage_entry.starts_at,
        ends_at=usage_entry.ends_at,
        active=True,
    )
    overdue_session = ClassSession(
        organization_id=organization.id,
        venue_id=venue.id,
        fixed_class_id="fixed-class-report",
        sequence_number=1,
        scheduled_start=datetime.combine(anchor, time(8), UTC),
        scheduled_end=datetime.combine(anchor, time(9), UTC),
        actual_coach_id="coach-report",
        status="scheduled",
    )
    completed_session = ClassSession(
        organization_id=organization.id,
        venue_id=venue.id,
        fixed_class_id="fixed-class-report",
        sequence_number=2,
        scheduled_start=datetime.combine(anchor, time(9), UTC),
        scheduled_end=datetime.combine(anchor, time(10), UTC),
        actual_coach_id="coach-report",
        status="completed",
        attendance_finalized_at=datetime.combine(anchor, time(10), UTC),
    )
    attendance = AttendanceRecord(
        organization_id=organization.id,
        venue_id=venue.id,
        class_session_id=completed_session.id,
        student_id="student-report",
        enrollment_id="enrollment-report",
        status="present",
        deduct_units=1,
    )
    private_lesson = PrivateLesson(
        organization_id=organization.id,
        venue_id=venue.id,
        student_id="student-report",
        coach_id="coach-report",
        billing_mode="package",
        starts_at=datetime.combine(anchor, time(8), UTC),
        ends_at=datetime.combine(anchor, time(9), UTC),
        actual_receivable=0,
        coach_fee=100,
        status="completed",
    )
    booking = VenueBooking(
        organization_id=organization.id,
        venue_id=venue.id,
        customer_id="customer-report",
        starts_at=datetime.combine(anchor, time(8), UTC),
        ends_at=datetime.combine(anchor, time(9), UTC),
        court_ids_csv=court.id,
        suggested_receivable=200,
        actual_receivable=200,
        status="cancelled",
    )
    event = TemporaryEvent(
        organization_id=organization.id,
        venue_id=venue.id,
        event_type="training",
        name="Report Event",
        starts_at=datetime.combine(anchor, time(10), UTC),
        ends_at=datetime.combine(anchor, time(11), UTC),
        court_ids_csv=court.id,
        status="completed",
    )
    receivable = Receivable(
        organization_id=organization.id,
        venue_id=venue.id,
        source_type="venue_booking",
        source_id=booking.id,
        suggested_amount=300,
        actual_amount=300,
    )
    coach_fee = CoachFee(
        organization_id=organization.id,
        venue_id=venue.id,
        coach_id="coach-report",
        source_type="event",
        source_id=event.id,
        occurred_at=datetime.combine(anchor, time(11), UTC),
        base_amount=100,
        adjustment_amount=0,
        status="pending",
    )
    ledgers = [
        LessonUnitLedger(
            organization_id=organization.id,
            venue_id=venue.id,
            owner_type=owner_type,
            owner_id=owner_id,
            change_type="attendance",
            delta=-1,
            balance_before=2,
            balance_after=1,
            source_type=source_type,
            source_id=source_id,
            operated_by="owner",
            operated_at=datetime.combine(anchor, time(10), UTC),
            idempotency_key=f"report-ledger:{owner_type}",
        )
        for owner_type, owner_id, source_type, source_id in (
            ("enrollment", "enrollment-report", "attendance", attendance.id),
            ("private_package", "package-report", "private_lesson", private_lesson.id),
        )
    ]
    db.add_all(
        [
            organization,
            venue,
            court,
            policy,
            block,
            block_entry,
            usage_entry,
            block_allocation,
            usage_allocation,
            overdue_session,
            completed_session,
            attendance,
            private_lesson,
            booking,
            event,
            receivable,
            coach_fee,
            *ledgers,
        ]
    )
    db.commit()
    scope = RequestScope(
        organization_id=organization.id,
        venue_id=venue.id,
        user_id="owner",
        membership_id="membership",
        capabilities=frozenset({"operations.report.read"}),
    )
    run = enqueue_report_run(
        db,
        scope=scope,
        period_type="day",
        anchor_date=anchor,
        include_narrative=True,
        trigger_key="report-once",
    )
    execute_report_workflow(db, run, RunBudget.from_run(run))
    db.flush()
    snapshot = db.scalar(select(OperationsReportSnapshot).where(OperationsReportSnapshot.run_id == run.id))
    assert snapshot is not None
    assert snapshot.narrative_state == "queued"
    assert snapshot.narrative_run_id is not None
    capacity = snapshot.breakdowns["court_capacity"]
    assert capacity["totals"]["base_business_hours"] == "4.00"
    assert capacity["totals"]["court_block_unavailable_hours"] == "1.00"
    assert capacity["totals"]["available_hours"] == "3.00"
    assert capacity["totals"]["commercial_usage_hours"] == "2.00"
    assert capacity["totals"]["raw_utilization"] == "0.6667"
    metrics = {item["metric_key"]: item for item in snapshot.metrics}
    assert metrics["outstanding_as_of"]["value"] == "300.00"
    assert metrics["outstanding_as_of"]["scope"] == "as_of"
    assert metrics["outstanding_receivables_as_of"]["value"] == 1
    assert metrics["coach_fee_current_pending_as_of"]["value"] == "100.00"
    assert metrics["private_lessons_completed"]["value"] == 1
    assert metrics["venue_bookings_cancelled"]["value"] == 1
    assert metrics["temporary_events_completed"]["value"] == 1
    assert metrics["attendance_overdue_sessions"]["value"] == 1
    assert metrics["attendance_present"]["value"] == 1
    assert metrics["fixed_class_lesson_units_consumed"]["value"] == 1
    assert metrics["private_lesson_units_consumed"]["value"] == 1
    assert all(item["source_refs"] for item in snapshot.metrics)
    anomaly_keys = {item["rule_key"] for item in snapshot.anomalies}
    assert "attendance_overdue" in anomaly_keys
    evidence_hash = snapshot.evidence_hash

    execute_report_workflow(db, run, RunBudget.from_run(run))
    db.flush()
    assert db.scalar(select(func.count(OperationsReportSnapshot.id))) == 1
    db.refresh(snapshot)
    assert snapshot.evidence_hash == evidence_hash
