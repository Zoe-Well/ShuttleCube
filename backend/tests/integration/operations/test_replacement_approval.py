from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.api.v1.operations import ApprovalDecisionInput, _decide_operation_approval
from shuttlecube.application.operations.access import capabilities_for_role
from shuttlecube.application.operations.approvals import decide_approval
from shuttlecube.application.operations.candidates import generate_replacement_candidates
from shuttlecube.application.operations.replacement_executor import (
    execute_replacement_workflow,
)
from shuttlecube.application.operations.replacement_workflow import (
    create_replacement_proposal,
)
from shuttlecube.application.operations.runtime import OperationsExecutor, RunBudget
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import LessonUnitLedger
from shuttlecube.domain.finance.models import Payment, Refund
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.operations.models import (
    OperationApproval,
    OperationCase,
    OperationRun,
    OperationToolCall,
)
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry
from shuttlecube.infrastructure.security.passwords import hash_password


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
        "replacement": {"window_days": 14, "slot_minutes": 60, "resource_mode": "original_only"},
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


def test_approved_replacement_is_atomic_idempotent_and_schedule_only(db: Session) -> None:
    now = datetime.now(UTC)
    user = SystemUser(
        username="replacement-owner",
        display_name="Replacement Owner",
        password_hash=hash_password("password123"),
    )
    organization = Organization(name="Replacement Org")
    venue = Venue(
        organization_id=organization.id,
        name="Replacement Venue",
        timezone="UTC",
        weekday_open_time=time(0),
        weekday_close_time=time(23, 59),
        weekend_open_time=time(0),
        weekend_close_time=time(23, 59),
        active_for_operations=True,
        write_tools_enabled=True,
    )
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        status="active",
        organization_role="owner",
    )
    venue_membership = VenueMembership(
        organization_membership_id=membership.id,
        organization_id=organization.id,
        venue_id=venue.id,
        role_key="owner",
        status="active",
    )
    court = Court(venue_id=venue.id, code="R-1", name="Replacement Court")
    fixed_class = FixedClass(
        organization_id=organization.id,
        venue_id=venue.id,
        name="Replacement Class",
        class_type="training",
        start_date=date.today(),
        default_start_time=time(10),
        duration_minutes=60,
        session_count=1,
        capacity=6,
        default_coach_id="coach-replacement",
        required_court_count=1,
        student_unit_price=Decimal("100.00"),
        coach_fee_per_session=Decimal("50.00"),
        status="active",
    )
    original_start = now - timedelta(days=1)
    original_start = original_start.replace(minute=0, second=0, microsecond=0)
    original = ClassSession(
        organization_id=organization.id,
        venue_id=venue.id,
        fixed_class_id=fixed_class.id,
        sequence_number=1,
        scheduled_start=original_start,
        scheduled_end=original_start + timedelta(hours=1),
        actual_coach_id=fixed_class.default_coach_id,
        status="cancelled",
        replacement_decision="pending",
        cancellation_reason="maintenance",
    )
    entry = ScheduleEntry(
        organization_id=organization.id,
        venue_id=venue.id,
        source_type="class_session",
        source_id=original.id,
        title="Cancelled class",
        starts_at=original.scheduled_start,
        ends_at=original.scheduled_end,
        status="cancelled",
    )
    original.schedule_entry_id = entry.id
    allocations = [
        ScheduleAllocation(
            organization_id=organization.id,
            venue_id=venue.id,
            schedule_entry_id=entry.id,
            resource_type=resource_type,
            resource_id=resource_id,
            starts_at=entry.starts_at,
            ends_at=entry.ends_at,
            active=False,
        )
        for resource_type, resource_id in (
            ("coach", fixed_class.default_coach_id),
            ("court", court.id),
        )
    ]
    policy = OperationsPolicy(
        organization_id=organization.id,
        venue_id=venue.id,
        policy_key="default_operations",
        policy_version=1,
        schema_version=1,
        config=_policy_config(),
        config_hash="replacement-policy-hash",
        state="active",
        effective_from=now - timedelta(days=1),
        created_by=user.id,
    )
    case = OperationCase(
        organization_id=organization.id,
        venue_id=venue.id,
        case_type="class_replacement_pending",
        subject_type="class_session",
        subject_id=original.id,
        case_key="replacement-case-key",
        detector_key="class.replacement_pending",
        detector_version=1,
        policy_key=policy.policy_key,
        policy_version=policy.policy_version,
        occurrence_no=1,
        fingerprint="replacement-fingerprint",
        evidence_hash="replacement-evidence-hash",
        evidence={"facts": {}, "source_refs": []},
        severity="high",
        priority_score=Decimal("90"),
        title="Cancelled class needs replacement",
        state="open",
        first_detected_at=now,
        last_detected_at=now,
        queue_key="training",
        required_capability="operations.case.manage",
        created_by_type="detector",
    )
    db.add_all(
        [
            user,
            organization,
            venue,
            membership,
            venue_membership,
            court,
            fixed_class,
            original,
            entry,
            *allocations,
            policy,
            case,
        ]
    )
    db.commit()
    scope = RequestScope(
        organization_id=organization.id,
        venue_id=venue.id,
        user_id=user.id,
        membership_id=venue_membership.id,
        capabilities=capabilities_for_role("owner"),
    )
    window_start = (now + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    _, candidate_result = generate_replacement_candidates(
        db,
        scope=scope,
        case=case,
        policy=policy,
        window_start=window_start,
        window_end=window_start + timedelta(hours=3),
        expected_case_version=case.version,
        max_candidates=3,
    )
    plan = candidate_result["candidates"][0]
    assert isinstance(plan, dict)
    tool_call, approval, run = create_replacement_proposal(
        db,
        scope=scope,
        case=case,
        policy=policy,
        resource_plan_id=str(plan["resource_plan_id"]),
        coordination_confirmed=True,
        expected_case_version=case.version,
        idempotency_key="replacement-once",
    )
    db.commit()

    first_decision, queued_run = decide_approval(
        db,
        scope=scope,
        approval=approval,
        approve=True,
        expected_version=approval.version,
        expected_input_hash=approval.input_hash,
        reason="Student and coach confirmed",
        request_id="approve-replacement",
    )
    duplicate_decision, duplicate_run = decide_approval(
        db,
        scope=scope,
        approval=approval,
        approve=True,
        expected_version=approval.version,
        expected_input_hash=approval.input_hash,
        reason="Student and coach confirmed",
        request_id="approve-replacement-retry",
    )
    assert duplicate_decision.id == first_decision.id
    assert queued_run is not None and duplicate_run is not None
    assert duplicate_run.id == queued_run.id

    state = OperationsExecutor().execute(
        run,
        lambda current, budget: execute_replacement_workflow(db, current, budget),
    )
    db.flush()
    assert state == "succeeded"
    execute_replacement_workflow(db, run, RunBudget.from_run(run))
    db.flush()

    replacements = list(
        db.scalars(
            select(ClassSession).where(
                ClassSession.organization_id == organization.id,
                ClassSession.venue_id == venue.id,
                ClassSession.replacement_for_session_id == original.id,
            )
        ).all()
    )
    assert len(replacements) == 1
    replacement = replacements[0]
    replacement_entry = db.get(ScheduleEntry, replacement.schedule_entry_id)
    assert replacement_entry is not None
    assert replacement_entry.organization_id == organization.id
    assert replacement_entry.venue_id == venue.id
    assert db.scalar(
        select(func.count(ScheduleAllocation.id)).where(
            ScheduleAllocation.schedule_entry_id == replacement_entry.id,
            ScheduleAllocation.organization_id == organization.id,
            ScheduleAllocation.venue_id == venue.id,
        )
    ) == 2
    db.refresh(original)
    db.refresh(case)
    db.refresh(tool_call)
    assert original.replacement_decision == "scheduled"
    assert case.state == "resolved"
    assert tool_call.state == "succeeded"
    assert tool_call.result_reference == f"class_session:{replacement.id}"
    assert db.scalar(select(func.count(Payment.id))) == 0
    assert db.scalar(select(func.count(Refund.id))) == 0
    assert db.scalar(select(func.count(LessonUnitLedger.id))) == 0
    assert db.scalar(
        select(func.count(OperationToolCall.id)).where(
            OperationToolCall.tool_key == "schedule_cancelled_class_replacement"
        )
    ) == 1


@pytest.mark.parametrize("conflict", ["stale", "expired"])
def test_approval_conflict_persists_terminal_states_without_business_writes(
    db: Session,
    conflict: str,
) -> None:
    now = datetime.now(UTC)
    expected_hash = "a" * 64
    case = OperationCase(
        organization_id="approval-org",
        venue_id="approval-venue",
        case_type="class_replacement_pending",
        subject_type="class_session",
        subject_id="cancelled-session",
        case_key=f"approval-{conflict}-case",
        detector_key="class.replacement_pending",
        detector_version=1,
        policy_key="default_operations",
        policy_version=1,
        occurrence_no=1,
        fingerprint="approval-fingerprint",
        evidence_hash="approval-evidence",
        evidence={},
        severity="high",
        priority_score=Decimal("75"),
        title="Replacement approval",
        state="waiting_approval",
        first_detected_at=now,
        last_detected_at=now,
        queue_key="training",
        required_capability="operations.case.manage",
        created_by_type="detector",
    )
    db.add(case)
    db.flush()
    run = OperationRun(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        case_id=case.id,
        run_type="tool_execution",
        trigger_type="approval",
        workflow_key="operations.replacement_execute.v1",
        workflow_version=1,
        policy_key="default_operations",
        policy_version=1,
        prompt_version=None,
        toolset_version=1,
        model_profile=None,
        input_refs=[],
        input_hash=expected_hash,
        checkpoint={},
        state="waiting_approval",
        max_steps=4,
        max_model_calls=0,
        max_tool_calls=1,
        max_write_calls=1,
        deadline_at=now + timedelta(minutes=30),
    )
    db.add(run)
    db.flush()
    tool_call = OperationToolCall(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        run_id=run.id,
        case_id=case.id,
        policy_key="default_operations",
        policy_version=1,
        tool_key="schedule_cancelled_class_replacement",
        tool_version=1,
        risk_level="medium",
        normalized_input={},
        input_hash=expected_hash,
        impact_snapshot={},
        subject_versions={},
        required_capability="operations.schedule.execute",
        state="awaiting_approval",
        idempotency_key=f"approval-{conflict}-once",
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
        requested_by="approval-owner",
        approval_policy="mandatory_approval",
        risk_level="medium",
        action_summary="Create one replacement session",
        impact_snapshot={},
        input_hash=expected_hash,
        subject_versions={},
        required_capability="operations.approval.decide",
        state="pending",
        expires_at=(
            now - timedelta(minutes=1)
            if conflict == "expired"
            else now + timedelta(minutes=30)
        ),
    )
    db.add(approval)
    db.commit()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/api/v1/operations/approvals/{approval.id}:approve",
            "headers": [],
        }
    )
    request.state.request_id = f"approval-{conflict}-request"
    scope = RequestScope(
        organization_id=case.organization_id,
        venue_id=case.venue_id,
        user_id="approval-owner",
        membership_id="approval-membership",
        capabilities=frozenset(
            {"operations.approval.decide", "operations.case.manage"}
        ),
    )

    with pytest.raises(BusinessError) as raised:
        _decide_operation_approval(
            approval_id=approval.id,
            payload=ApprovalDecisionInput(
                expected_approval_version=approval.version,
                expected_input_hash=(expected_hash if conflict == "expired" else "b" * 64),
                reason="Approve current proposal",
            ),
            approve=True,
            request=request,
            scope=scope,
            db=db,
        )

    expected_error = "approval_expired" if conflict == "expired" else "approval_stale"
    expected_approval_state = "expired" if conflict == "expired" else "stale"
    assert raised.value.code == expected_error
    db.expire_all()
    assert db.get(OperationApproval, approval.id).state == expected_approval_state
    assert db.get(OperationToolCall, tool_call.id).state == "stale"
    assert db.get(OperationRun, run.id).state == "cancelled"
    assert db.get(OperationCase, case.id).state == "waiting_human"
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "operation_approval",
            AuditLog.entity_id == approval.id,
            AuditLog.action_type == f"operation_approval.{expected_approval_state}",
        )
    )
    assert audit is not None
    assert audit.request_id == f"approval-{conflict}-request"
    assert db.scalar(select(func.count(Payment.id))) == 0
    assert db.scalar(select(func.count(Refund.id))) == 0
    assert db.scalar(select(func.count(LessonUnitLedger.id))) == 0
    assert db.scalar(select(func.count(ClassSession.id))) == 0
