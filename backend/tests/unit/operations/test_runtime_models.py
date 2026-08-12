from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shuttlecube.application.operations.state_machine import (
    InvalidTransition,
    transition_case,
    transition_run,
)
from shuttlecube.domain.operations.models import (
    CaseActivity,
    OperationApproval,
    OperationCase,
    OperationEvent,
    OperationRun,
    OperationsReportSnapshot,
    OperationToolCall,
)

NOW = datetime(2026, 8, 9, 8, tzinfo=UTC)


def _case() -> OperationCase:
    return OperationCase(
        organization_id="organization-1",
        venue_id="venue-1",
        case_type="overdue_attendance",
        subject_type="class_session",
        subject_id="session-1",
        case_key="case-key-1",
        detector_key="overdue_attendance",
        detector_version=1,
        policy_key="default_operations",
        policy_version=1,
        fingerprint="fingerprint-1",
        evidence_hash="evidence-1",
        severity="medium",
        priority_score=50,
        title="Attendance is overdue",
        business_summary="Attendance is not finalized after the grace period.",
        queue_key="training_operations",
        required_capability="operations.case.manage",
        first_detected_at=NOW,
        last_detected_at=NOW,
    )


def _run(case: OperationCase) -> OperationRun:
    return OperationRun(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        case_id=case.id,
        run_type="case_analysis",
        trigger_type="manual",
        workflow_key="case_analysis",
        workflow_version=1,
        policy_key="default_operations",
        policy_version=1,
        toolset_version=1,
        input_refs=[{"kind": "class_session", "id": "session-1"}],
        input_hash="input-1",
        checkpoint={"step": "queued"},
        max_steps=8,
        max_model_calls=1,
        max_tool_calls=4,
        max_write_calls=0,
        deadline_at=NOW + timedelta(minutes=2),
    )


def test_runtime_aggregate_models_persist_with_safe_initial_states(db: Session) -> None:
    case = _case()
    db.add(case)
    db.flush()
    run = _run(case)
    db.add(run)
    db.flush()
    activity = CaseActivity(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        case_id=case.id,
        case_occurrence_no=1,
        activity_type="note",
        channel="none",
        outcome_code="other",
        summary="Owner reviewed the deterministic evidence.",
        happened_at=NOW,
        operated_by="user-1",
        source="manual",
    )
    event = OperationEvent(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        case_id=case.id,
        run_id=run.id,
        sequence=1,
        event_type="run.queued",
        actor_type="user",
        actor_id="user-1",
        trace_id="trace-1",
        payload_redacted={"case_id": case.id},
        payload_hash="payload-1",
        occurred_at=NOW,
    )
    tool_call = OperationToolCall(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        run_id=run.id,
        case_id=case.id,
        policy_key="default_operations",
        policy_version=1,
        tool_key="record_followup_outcome",
        tool_version=1,
        risk_level="low",
        normalized_input={"outcome_code": "no_answer"},
        input_hash="tool-input-1",
        impact_snapshot={"case_id": case.id},
        subject_versions={"case": 1},
        required_capability="operations.receivable.followup.write",
        idempotency_key="followup-1",
    )
    db.add(tool_call)
    db.flush()
    approval = OperationApproval(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        tool_call_id=tool_call.id,
        case_id=case.id,
        policy_key="default_operations",
        policy_version=1,
        requested_by="user-1",
        approval_policy="explicit_confirmation",
        risk_level="low",
        action_summary="Record the confirmed follow-up outcome",
        impact_snapshot={"case_id": case.id},
        input_hash=tool_call.input_hash,
        subject_versions={"case": 1},
        required_capability="operations.receivable.followup.write",
        expires_at=NOW + timedelta(hours=1),
    )
    snapshot = OperationsReportSnapshot(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        run_id=run.id,
        period_type="day",
        period_start=date(2026, 8, 8),
        period_end=date(2026, 8, 8),
        effective_end=NOW,
        business_timezone="Asia/Shanghai",
        period_state="complete",
        generated_at=NOW,
        generated_by="user-1",
        comparison_status="available",
        policy_key="default_operations",
        policy_version=1,
        metric_version=1,
        anomaly_rule_version=1,
        metrics=[],
        breakdowns={},
        anomalies=[],
        source_refs=[],
        evidence_hash="report-evidence-1",
    )
    db.add_all([activity, event, approval, snapshot])
    db.commit()

    assert case.state == "open"
    assert case.occurrence_no == 1
    assert run.state == "queued"
    assert tool_call.state == "proposed"
    assert approval.state == "pending"
    assert snapshot.narrative_state == "not_requested"
    assert db.get(OperationCase, case.id) is case
    assert db.get(OperationRun, run.id) is run
    assert db.query(CaseActivity).filter_by(case_id=case.id).count() == 1
    assert db.query(OperationEvent).filter_by(run_id=run.id).count() == 1


def test_runtime_uniqueness_prevents_duplicate_event_and_tool_result(db: Session) -> None:
    case = _case()
    db.add(case)
    db.flush()
    run = _run(case)
    db.add(run)
    db.flush()
    first = OperationEvent(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        case_id=case.id,
        run_id=run.id,
        sequence=1,
        event_type="run.queued",
        actor_type="system",
        trace_id="trace-1",
        payload_redacted={},
        payload_hash="event-1",
        occurred_at=NOW,
    )
    duplicate = OperationEvent(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        case_id=case.id,
        run_id=run.id,
        sequence=1,
        event_type="run.started",
        actor_type="system",
        trace_id="trace-1",
        payload_redacted={},
        payload_hash="event-2",
        occurred_at=NOW,
    )
    db.add_all([first, duplicate])
    with pytest.raises(IntegrityError):
        db.commit()


def test_case_and_run_states_only_change_through_deterministic_guards() -> None:
    case = _case()
    run = _run(case)

    transition_case(case, "analyzing")
    transition_run(run, "running")
    assert case.state == "analyzing"
    assert run.state == "running"

    with pytest.raises(InvalidTransition):
        transition_case(case, "resolved")
    with pytest.raises(InvalidTransition):
        transition_run(run, "queued")
