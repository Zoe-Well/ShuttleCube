import json
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from shuttlecube.application.operations.state_machine import transition_run
from shuttlecube.domain.operations.models import OperationRun


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class RunBudget:
    max_steps: int
    max_model_calls: int
    max_tool_calls: int
    max_write_calls: int
    step_count: int = 0
    model_call_count: int = 0
    tool_call_count: int = 0
    write_call_count: int = 0
    token_usage_summary: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_run(cls, run: OperationRun) -> RunBudget:
        return cls(
            max_steps=run.max_steps,
            max_model_calls=run.max_model_calls,
            max_tool_calls=run.max_tool_calls,
            max_write_calls=run.max_write_calls,
            step_count=run.step_count or 0,
            model_call_count=run.model_call_count or 0,
            tool_call_count=run.tool_call_count or 0,
            write_call_count=run.write_call_count or 0,
            token_usage_summary=dict(run.token_usage_summary or {}),
        )

    def consume_step(self) -> None:
        if self.step_count >= self.max_steps:
            raise BudgetExceeded("max_steps")
        self.step_count += 1

    def consume_model_call(self, *, tokens: dict[str, int]) -> None:
        if self.model_call_count >= self.max_model_calls:
            raise BudgetExceeded("max_model_calls")
        self.model_call_count += 1
        for key, value in tokens.items():
            self.token_usage_summary[key] = self.token_usage_summary.get(key, 0) + value

    def consume_tool_call(self, *, is_write: bool) -> None:
        if is_write and self.write_call_count >= self.max_write_calls:
            raise BudgetExceeded("max_write_calls")
        if self.tool_call_count >= self.max_tool_calls:
            raise BudgetExceeded("max_tool_calls")
        self.tool_call_count += 1
        if is_write:
            self.write_call_count += 1

    def persist_to(self, run: OperationRun) -> None:
        run.step_count = self.step_count
        run.model_call_count = self.model_call_count
        run.tool_call_count = self.tool_call_count
        run.write_call_count = self.write_call_count
        run.token_usage_summary = dict(self.token_usage_summary)


def checkpoint_run(run: OperationRun, checkpoint: dict[str, object]) -> None:
    json.dumps(checkpoint, ensure_ascii=False, allow_nan=False)
    run.checkpoint = checkpoint


def retryable_error(error: Exception) -> bool:
    return isinstance(error, (TimeoutError, ConnectionError))


class OperationsExecutor:
    def execute(
        self,
        run: OperationRun,
        workflow: Callable[[OperationRun, RunBudget], None],
    ) -> str:
        budget = RunBudget.from_run(run)
        if run.state == "queued":
            transition_run(run, "running")
        try:
            workflow(run, budget)
            budget.persist_to(run)
            transition_run(run, "succeeded")
        except BudgetExceeded as exc:
            budget.persist_to(run)
            run.error_code = "budget_exceeded"
            run.error_summary = str(exc)
            transition_run(run, "escalated")
        except Exception as exc:
            budget.persist_to(run)
            run.error_code = type(exc).__name__
            run.error_summary = str(exc)[:1000]
            transition_run(run, "retry_scheduled" if retryable_error(exc) else "failed")
        return run.state


RegisteredWorkflow = Callable[[Session, OperationRun, RunBudget], None]
_WORKFLOWS: dict[str, RegisteredWorkflow] = {}


def register_workflow(workflow_key: str, workflow: RegisteredWorkflow) -> None:
    if workflow_key in _WORKFLOWS:
        raise ValueError(f"Workflow already registered: {workflow_key}")
    _WORKFLOWS[workflow_key] = workflow


def execute_persisted_run(
    session_factory: Callable[[], Session],
    run_id: str,
) -> None:
    """Execute a claimed run in a unit of work separate from lease claiming."""
    with session_factory() as db:
        run = db.get(OperationRun, run_id)
        if run is None or run.state != "running":
            return
        workflow = _WORKFLOWS.get(run.workflow_key)
        if workflow is None:
            run.error_code = "workflow_not_registered"
            run.error_summary = f"No runtime workflow registered for {run.workflow_key}"[:1000]
            transition_run(run, "failed")
        else:
            OperationsExecutor().execute(run, lambda current, budget: workflow(db, current, budget))
        db.commit()
