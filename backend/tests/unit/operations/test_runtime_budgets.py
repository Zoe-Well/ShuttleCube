from datetime import UTC, datetime, timedelta

import pytest

from shuttlecube.application.operations.runner import claim_next_run
from shuttlecube.application.operations.runtime import (
    BudgetExceeded,
    RunBudget,
    checkpoint_run,
)
from shuttlecube.domain.operations.models import OperationRun

NOW = datetime(2026, 8, 9, 8, tzinfo=UTC)


def _run() -> OperationRun:
    return OperationRun(
        organization_id="organization-1",
        venue_id="venue-1",
        run_type="scan",
        trigger_type="scheduled",
        workflow_key="overdue_attendance_scan",
        workflow_version=1,
        policy_key="default_operations",
        policy_version=1,
        toolset_version=1,
        input_refs=[],
        input_hash="input-1",
        checkpoint={"cursor": None},
        max_steps=2,
        max_model_calls=1,
        max_tool_calls=1,
        max_write_calls=0,
        deadline_at=NOW + timedelta(minutes=5),
        attempt=1,
        step_count=0,
        model_call_count=0,
        tool_call_count=0,
        write_call_count=0,
        token_usage_summary={},
    )


def test_run_budget_stops_before_exceeding_each_persisted_limit() -> None:
    run = _run()
    budget = RunBudget.from_run(run)

    budget.consume_step()
    budget.consume_step()
    budget.consume_model_call(tokens={"input": 20, "output": 5})
    budget.consume_tool_call(is_write=False)

    with pytest.raises(BudgetExceeded, match="max_steps"):
        budget.consume_step()
    with pytest.raises(BudgetExceeded, match="max_model_calls"):
        budget.consume_model_call(tokens={"input": 1, "output": 1})
    with pytest.raises(BudgetExceeded, match="max_tool_calls"):
        budget.consume_tool_call(is_write=False)
    with pytest.raises(BudgetExceeded, match="max_write_calls"):
        budget.consume_tool_call(is_write=True)

    budget.persist_to(run)
    assert run.step_count == 2
    assert run.model_call_count == 1
    assert run.tool_call_count == 1
    assert run.write_call_count == 0
    assert run.token_usage_summary == {"input": 20, "output": 5}


def test_checkpoint_replaces_only_valid_json_state_and_survives_retry() -> None:
    run = _run()
    checkpoint_run(run, {"cursor": "student-20", "completed_steps": ["query"]})
    run.state = "retry_scheduled"
    run.attempt += 1

    assert run.checkpoint == {
        "cursor": "student-20",
        "completed_steps": ["query"],
    }
    assert run.attempt == 2


def test_expired_lease_can_be_taken_over_but_live_lease_cannot(db) -> None:
    run = _run()
    run.state = "running"
    run.lease_owner = "dead-worker"
    run.lease_expires_at = NOW - timedelta(seconds=1)
    db.add(run)
    db.commit()

    claimed = claim_next_run(
        db,
        worker_id="replacement-worker",
        now=NOW,
        lease_duration=timedelta(seconds=30),
    )
    assert claimed is not None
    assert claimed.id == run.id
    assert claimed.lease_owner == "replacement-worker"

    db.commit()
    assert (
        claim_next_run(
            db,
            worker_id="third-worker",
            now=NOW + timedelta(seconds=1),
            lease_duration=timedelta(seconds=30),
        )
        is None
    )
