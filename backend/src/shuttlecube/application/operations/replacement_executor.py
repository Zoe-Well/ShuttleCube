from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.commands.class_cancellation import (
    schedule_cancelled_session_replacement,
)
from shuttlecube.application.operations.access import capabilities_for_role
from shuttlecube.application.operations.idempotency import (
    canonical_hash,
    persist_tool_result,
    reconcile_replacement_outcome,
    reconcile_uncertain_outcome,
)
from shuttlecube.application.operations.policies import get_active_policy
from shuttlecube.application.operations.replacement_workflow import (
    REPLACEMENT_EXECUTION_WORKFLOW_KEY,
)
from shuttlecube.application.operations.runtime import RunBudget, checkpoint_run, register_workflow
from shuttlecube.application.operations.state_machine import transition_case
from shuttlecube.application.operations.tools import ToolRegistry
from shuttlecube.application.operations.verifiers import VerifierRegistry
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.identity.organization_models import (
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.operations.models import (
    OperationApproval,
    OperationCase,
    OperationRun,
    OperationToolCall,
)
from shuttlecube.domain.scheduling.conflicts import Resource, find_conflicts
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _actor_capabilities(
    db: Session,
    *,
    organization_id: str,
    venue_id: str,
    user_id: str,
) -> frozenset[str]:
    membership = db.scalar(
        select(VenueMembership)
        .join(
            OrganizationMembership,
            OrganizationMembership.id == VenueMembership.organization_membership_id,
        )
        .where(
            VenueMembership.organization_id == organization_id,
            VenueMembership.venue_id == venue_id,
            VenueMembership.status == "active",
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
    )
    return capabilities_for_role(membership.role_key) if membership else frozenset()


def execute_replacement_workflow(
    db: Session,
    run: OperationRun,
    budget: RunBudget,
) -> None:
    scope = RequestScope(
        organization_id=run.organization_id,
        venue_id=run.venue_id,
        user_id="system",
        membership_id="system",
        capabilities=frozenset(),
    )
    tool_call = db.scalar(
        select(OperationToolCall).where(
            OperationToolCall.run_id == run.id,
            OperationToolCall.organization_id == scope.organization_id,
            OperationToolCall.venue_id == scope.venue_id,
            OperationToolCall.tool_key == "schedule_cancelled_class_replacement",
        )
    )
    if tool_call is None:
        raise RuntimeError("replacement_execution_context_missing")
    approval = db.scalar(
        select(OperationApproval).where(
            OperationApproval.organization_id == scope.organization_id,
            OperationApproval.venue_id == scope.venue_id,
            OperationApproval.tool_call_id == tool_call.id,
        )
    )
    case = db.scalar(
        select(OperationCase).where(
            OperationCase.id == run.case_id,
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
        )
    )
    if approval is None or case is None:
        raise RuntimeError("replacement_execution_context_missing")
    if tool_call.state == "succeeded" and tool_call.result_reference:
        checkpoint_run(
            run,
            {
                "workflow_step": "replacement_complete",
                "completed_steps": ["reconciled_existing_result"],
                "state": {"result_reference": tool_call.result_reference},
            },
        )
        return
    if tool_call.state in {"executing", "uncertain"}:
        reconciled = reconcile_uncertain_outcome(
            tool_call,
            probe=lambda current: reconcile_replacement_outcome(
                db,
                scope=scope,
                tool_call=current,
            ),
        )
        if reconciled.outcome == "succeeded":
            checkpoint_run(
                run,
                {
                    "workflow_step": "replacement_complete",
                    "completed_steps": ["outcome_reconciliation"],
                    "state": {"result_reference": reconciled.result_reference},
                },
            )
            return
        if reconciled.outcome == "uncertain":
            raise RuntimeError("replacement_outcome_uncertain")
    if tool_call.state != "approved" or approval.state != "approved":
        raise RuntimeError("replacement_not_approved")
    if not approval.decided_by:
        raise RuntimeError("approval_actor_missing")
    capabilities = _actor_capabilities(
        db,
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        user_id=approval.decided_by,
    )
    if not {
        "operations.approval.decide",
        "operations.schedule.execute",
    }.issubset(capabilities):
        tool_call.state = "stale"
        tool_call.error_code = "actor_capability_changed"
        if case.state == "waiting_approval":
            transition_case(case, "waiting_human")
        raise RuntimeError("actor_capability_changed")
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if venue is None or venue.write_tools_enabled is not True:
        raise RuntimeError("write_tool_disabled")
    active_policy = get_active_policy(db, scope=scope, policy_key=tool_call.policy_key)
    definition = ToolRegistry.default().get(tool_call.tool_key)
    normalized = dict(tool_call.normalized_input)
    if (
        active_policy.policy_version != tool_call.policy_version
        or definition.tool_version != tool_call.tool_version
        or canonical_hash(normalized) != tool_call.input_hash
        or approval.input_hash != tool_call.input_hash
    ):
        tool_call.state = "stale"
        tool_call.error_code = "policy_tool_or_input_changed"
        raise RuntimeError("replacement_stale")
    expires_at = _aware(datetime.fromisoformat(str(normalized["expires_at"])))
    if expires_at <= datetime.now(UTC):
        tool_call.state = "stale"
        tool_call.error_code = "resource_plan_expired"
        raise RuntimeError("resource_plan_expired")
    session = db.scalar(
        select(ClassSession).where(
            ClassSession.id == str(normalized["cancelled_session_id"]),
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
        )
    )
    if (
        session is None
        or session.version != int(normalized["cancelled_session_version"])
        or session.status != "cancelled"
        or session.replacement_decision != "pending"
    ):
        tool_call.state = "stale"
        tool_call.error_code = "session_changed"
        raise RuntimeError("replacement_stale")
    starts_at = _aware(datetime.fromisoformat(str(normalized["starts_at"])))
    ends_at = _aware(datetime.fromisoformat(str(normalized["ends_at"])))
    local_start = starts_at.astimezone(ZoneInfo(venue.timezone))
    local_end = ends_at.astimezone(ZoneInfo(venue.timezone))
    weekend = local_start.weekday() >= 5
    opening = venue.weekend_open_time if weekend else venue.weekday_open_time
    closing = venue.weekend_close_time if weekend else venue.weekday_close_time
    if (
        local_start.date() != local_end.date()
        or local_start.minute != 0
        or local_start.time().replace(tzinfo=None) < opening
        or local_end.time().replace(tzinfo=None) > closing
    ):
        tool_call.state = "stale"
        tool_call.error_code = "business_hours_changed"
        raise RuntimeError("replacement_stale")
    original_allocations = db.scalars(
        select(ScheduleAllocation).where(
            ScheduleAllocation.organization_id == scope.organization_id,
            ScheduleAllocation.venue_id == scope.venue_id,
            ScheduleAllocation.schedule_entry_id == session.schedule_entry_id,
        )
    ).all()
    expected_coaches = set(normalized["coach_ids"])
    expected_courts = set(normalized["court_ids"])
    original_coaches = {
        item.resource_id for item in original_allocations if item.resource_type == "coach"
    } or {session.actual_coach_id}
    original_courts = {
        item.resource_id for item in original_allocations if item.resource_type == "court"
    }
    if expected_coaches != original_coaches or expected_courts != original_courts:
        tool_call.state = "stale"
        tool_call.error_code = "original_resources_changed"
        raise RuntimeError("replacement_stale")
    resources = [
        *(Resource("coach", item) for item in sorted(expected_coaches)),
        *(Resource("court", item) for item in sorted(expected_courts)),
    ]
    if find_conflicts(db, resources, starts_at, ends_at):
        tool_call.state = "stale"
        tool_call.error_code = "resource_conflict"
        raise RuntimeError("replacement_stale")
    budget.consume_step()
    budget.consume_tool_call(is_write=True)
    try:
        # The business facts, business audit, Tool result mapping and verifier outcome
        # either survive together or are all rolled back to the approved proposal.
        with db.begin_nested():
            tool_call.state = "executing"
            tool_call.started_at = datetime.now(UTC)
            if case.state == "waiting_approval":
                transition_case(case, "executing")
            replacement = schedule_cancelled_session_replacement(
                db,
                session,
                replacement_start=starts_at,
                replacement_end=ends_at,
                actor_id=approval.decided_by,
                request_id=f"operation-run:{run.id}",
                version=session.version,
                scope=RequestScope(
                    organization_id=scope.organization_id,
                    venue_id=scope.venue_id,
                    user_id=approval.decided_by,
                    membership_id="approval-execution",
                    capabilities=capabilities,
                ),
                commit=False,
            )
            persist_tool_result(
                tool_call,
                result_reference=f"class_session:{replacement.id}",
                result_summary=f"replacement session {replacement.id} created",
            )
            tool_call.finished_at = datetime.now(UTC)
            transition_case(case, "verifying")
            verification = VerifierRegistry.default().verify(db, scope, case)
            if verification.outcome != "resolved":
                raise RuntimeError(
                    f"replacement_verification_failed:{verification.reason_code}"
                )
            checkpoint_run(
                run,
                {
                    "workflow_step": "replacement_complete",
                    "completed_steps": ["revalidate", "execute", "audit", "verify"],
                    "state": {
                        "cancelled_session_id": session.id,
                        "replacement_session_id": replacement.id,
                        "result_reference": tool_call.result_reference,
                        "verification": {
                            "outcome": verification.outcome,
                            "reason_code": verification.reason_code,
                            "facts": verification.facts,
                        },
                    },
                },
            )
    except Exception as exc:
        tool_call.state = "failed"
        tool_call.error_code = type(exc).__name__
        tool_call.finished_at = datetime.now(UTC)
        if case.state in {"waiting_approval", "executing", "verifying"}:
            transition_case(case, "waiting_human")
        raise


register_workflow(REPLACEMENT_EXECUTION_WORKFLOW_KEY, execute_replacement_workflow)
