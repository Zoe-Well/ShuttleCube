import json
import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.application.operations.model_client import (
    ModelOutputInvalid,
    ModelRequest,
    ModelUnavailable,
    VenueModelClient,
)
from shuttlecube.application.operations.runtime import RunBudget, checkpoint_run, register_workflow
from shuttlecube.config import get_settings
from shuttlecube.domain.operations.models import OperationCase, OperationRun
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.ai.openai_client import OpenAIResponsesClient

RECONCILIATION_EXPLANATION_WORKFLOW_KEY = "operations.reconciliation_explanation.v1"
PROMPT_VERSION = 1


class ReconciliationCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(min_length=1, max_length=240)
    claim: str = Field(min_length=1, max_length=500)


class ReconciliationExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    hypotheses: list[str] = Field(default_factory=list, max_length=6)
    repair_order: list[str] = Field(default_factory=list, max_length=8)
    citations: list[ReconciliationCitation] = Field(default_factory=list, max_length=20)
    abstained: bool = False
    abstention_reason: str | None = Field(default=None, max_length=500)


def reconciliation_case_context(case: OperationCase) -> dict[str, object]:
    facts = (case.evidence or {}).get("facts", {})
    if not isinstance(facts, dict) or not isinstance(facts.get("reconciliation"), dict):
        raise ValueError("reconciliation result is missing")
    result = dict(facts["reconciliation"])
    impact = result.get("impact", {})
    impact_values = impact if isinstance(impact, dict) else {}
    order = [
        {"key": key, "value": impact_values[key]}
        for key in (
            "affected_amount",
            "affected_lesson_units",
            "affected_schedules",
            "downstream_records",
        )
        if key in impact_values and str(impact_values[key]) not in {"0", "0.00", "0.0"}
    ]
    return {
        "case_id": case.id,
        "case_state": case.state,
        "failure_count": int(facts.get("failure_count", 1)),
        "result": result,
        "deterministic_impact_order": order,
        "automatic_repair_available": False,
    }


def _source_refs(context: dict[str, object]) -> set[str]:
    result = context.get("result", {})
    refs = result.get("affected_refs", []) if isinstance(result, dict) else []
    return {
        f"{item.get('kind')}:{item.get('id')}"
        for item in refs
        if isinstance(item, dict) and item.get("kind") and item.get("id")
    }


def _validate_explanation(
    output: ReconciliationExplanation,
    *,
    context: dict[str, object],
) -> ReconciliationExplanation:
    allowed_refs = _source_refs(context)
    if any(item.source_ref not in allowed_refs for item in output.citations):
        raise ValueError("explanation cites a source outside deterministic evidence")
    text = " ".join([output.summary, *output.hypotheses, *output.repair_order])
    forbidden = (
        "执行 SQL",
        "运行 SQL",
        "自动修复",
        "直接修改数据库",
        "自动冲正",
        "自动补账",
    )
    if any(fragment in text for fragment in forbidden):
        raise ValueError("explanation crossed the no-auto-repair boundary")
    allowed_numbers = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(context, default=str)))
    generated_numbers = set(re.findall(r"\d+(?:\.\d+)?", text))
    if not generated_numbers.issubset(allowed_numbers):
        raise ValueError("explanation introduced a number outside deterministic evidence")
    return output


def execute_reconciliation_explanation_workflow(
    db: Session,
    run: OperationRun,
    budget: RunBudget,
) -> None:
    scope = RequestScope(
        organization_id=run.organization_id,
        venue_id=run.venue_id,
        user_id="system",
        membership_id="system",
        capabilities=frozenset({"operations.case.read"}),
    )
    case = db.scalar(
        select(OperationCase).where(
            OperationCase.id == run.case_id,
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
            OperationCase.case_type == "reconciliation_failure",
        )
    )
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if case is None or venue is None:
        raise RuntimeError("reconciliation_context_missing")
    context = reconciliation_case_context(case)
    settings = get_settings()
    if venue.model_enabled is not True or settings.openai_api_key is None:
        checkpoint_run(
            run,
            {
                "workflow_step": "explanation_unavailable",
                "completed_steps": ["deterministic_context", "model_gate"],
                "state": {
                    "context": context,
                    "explanation": None,
                    "reason": (
                        "model_disabled"
                        if venue.model_enabled is not True
                        else "provider_not_configured"
                    ),
                },
            },
        )
        return
    request = ModelRequest(
        workflow_key=RECONCILIATION_EXPLANATION_WORKFLOW_KEY,
        prompt_version=PROMPT_VERSION,
        system_instruction=(
            "你是羽毛球馆数据一致性解释助手。只能解释输入中的确定性规则结果，"
            "不得改变 result、severity、invariants 或影响排序。可能原因必须明确写成假设；"
            "只能建议人工打开给定业务入口核对，不得提供 SQL 或自动修账、冲正、改排期方案。"
            "所有事实结论必须引用允许的 source_ref。"
        ),
        input_data={
            "context": context,
            "allowed_source_refs": sorted(_source_refs(context)),
        },
        output_schema=ReconciliationExplanation,
        model_profile=run.model_profile or settings.operations_model_profile,
    )
    try:
        response = VenueModelClient(
            db,
            scope,
            OpenAIResponsesClient(settings),
        ).generate(request)
        budget.consume_model_call(tokens=response.usage)
        output = _validate_explanation(
            ReconciliationExplanation.model_validate(response.output),
            context=context,
        )
        checkpoint_run(
            run,
            {
                "workflow_step": "explanation_complete",
                "completed_steps": ["deterministic_context", "model", "validate"],
                "state": {
                    "context": context,
                    "explanation": output.model_dump(mode="json"),
                    "provider": response.provider_metadata,
                },
            },
        )
    except (ModelUnavailable, ModelOutputInvalid, ValueError) as exc:
        checkpoint_run(
            run,
            {
                "workflow_step": "explanation_unavailable",
                "completed_steps": ["deterministic_context", "model_attempt"],
                "state": {
                    "context": context,
                    "explanation": None,
                    "reason": type(exc).__name__,
                },
            },
        )


def enqueue_reconciliation_explanation(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    trigger_key: str,
) -> OperationRun:
    if case.case_type != "reconciliation_failure":
        raise ValueError("case is not a reconciliation failure")
    input_hash = canonical_hash(
        {
            "workflow_key": RECONCILIATION_EXPLANATION_WORKFLOW_KEY,
            "case_id": case.id,
            "occurrence_no": case.occurrence_no,
            "evidence_hash": case.evidence_hash,
            "trigger_key": trigger_key,
        }
    )
    existing = db.scalar(
        select(OperationRun).where(
            OperationRun.organization_id == scope.organization_id,
            OperationRun.venue_id == scope.venue_id,
            OperationRun.workflow_key == RECONCILIATION_EXPLANATION_WORKFLOW_KEY,
            OperationRun.input_hash == input_hash,
        )
    )
    if existing is not None:
        return existing
    now = datetime.now(UTC)
    run = OperationRun(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        case_id=case.id,
        parent_run_id=case.current_run_id,
        run_type="case_analysis",
        trigger_type="manual",
        workflow_key=RECONCILIATION_EXPLANATION_WORKFLOW_KEY,
        workflow_version=1,
        policy_key=case.policy_key,
        policy_version=case.policy_version,
        prompt_version=PROMPT_VERSION,
        toolset_version=1,
        model_profile=get_settings().operations_model_profile,
        input_refs=[{"kind": "operation_case", "id": case.id, "version": case.version}],
        input_hash=input_hash,
        checkpoint={"workflow_step": "queued", "state": {}},
        state="queued",
        max_steps=3,
        max_model_calls=1,
        max_tool_calls=0,
        max_write_calls=0,
        deadline_at=now + timedelta(minutes=2),
    )
    db.add(run)
    db.flush()
    case.current_run_id = run.id
    return run


register_workflow(
    RECONCILIATION_EXPLANATION_WORKFLOW_KEY,
    execute_reconciliation_explanation_workflow,
)
