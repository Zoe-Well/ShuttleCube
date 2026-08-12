import json
import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.access import project_followup_context
from shuttlecube.application.operations.evidence import (
    receivable_followup_context,
    renewal_followup_context,
)
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.application.operations.model_client import (
    ModelClient,
    ModelOutputInvalid,
    ModelRequest,
    ModelUnavailable,
    VenueModelClient,
)
from shuttlecube.application.operations.runtime import RunBudget, checkpoint_run, register_workflow
from shuttlecube.config import get_settings
from shuttlecube.domain.operations.models import OperationCase, OperationRun
from shuttlecube.domain.scheduling.court import Venue
from shuttlecube.infrastructure.ai.credentials import (
    configured_model_profile,
    resolve_model_provider,
)
from shuttlecube.infrastructure.ai.openai_client import model_provider_client

REVENUE_ANALYSIS_WORKFLOW_KEY = "operations.revenue_analysis.v1"
PROMPT_VERSION = 1


class RevenueCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(min_length=1, max_length=240)
    claim: str = Field(min_length=1, max_length=500)


class RevenueAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    next_actions: list[str] = Field(default_factory=list, max_length=8)
    communication_draft: str | None = Field(default=None, max_length=2000)
    citations: list[RevenueCitation] = Field(default_factory=list, max_length=20)
    abstained: bool = False
    abstention_reason: str | None = Field(default=None, max_length=500)


def _scope_for_run(run: OperationRun) -> RequestScope:
    return RequestScope(
        organization_id=run.organization_id,
        venue_id=run.venue_id,
        user_id="system",
        membership_id="system",
        capabilities=frozenset(
            {"operations.case.read", "operations.receivable.followup.read"}
        ),
    )


def _context(db: Session, scope: RequestScope, case: OperationCase) -> dict[str, object]:
    if case.case_type == "receivable_followup":
        raw = receivable_followup_context(db, scope=scope, case=case)
    else:
        raw = renewal_followup_context(db, scope=scope, case=case)
    return project_followup_context(raw, scope=scope, case_type=case.case_type)


def _allowed_source_refs(case: OperationCase) -> set[str]:
    refs = (case.evidence or {}).get("source_refs", [])
    if not isinstance(refs, list):
        return set()
    return {
        f"{item.get('kind')}:{item.get('id')}"
        for item in refs
        if isinstance(item, dict) and item.get("kind") and item.get("id")
    }


def _validate_analysis(
    output: RevenueAnalysisOutput,
    *,
    case: OperationCase,
    context: dict[str, object],
) -> RevenueAnalysisOutput:
    allowed_refs = _allowed_source_refs(case)
    if any(citation.source_ref not in allowed_refs for citation in output.citations):
        raise ValueError("analysis cites a source outside the case evidence")
    allowed_numbers = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(context, default=str)))
    generated_text = " ".join(
        [output.summary, *(output.next_actions or []), output.communication_draft or ""]
    )
    generated_numbers = set(re.findall(r"\d+(?:\.\d+)?", generated_text))
    if not generated_numbers.issubset(allowed_numbers):
        raise ValueError("analysis introduced a number not present in deterministic context")
    contact = context.get("contact")
    contact_available = isinstance(contact, dict) and contact.get("available") is True
    if not contact_available and output.communication_draft:
        raise ValueError("communication draft requires an authorized contact")
    return output


def run_revenue_analysis(
    db: Session,
    *,
    run: OperationRun,
    case: OperationCase,
    model_client: ModelClient,
    budget: RunBudget,
) -> None:
    scope = _scope_for_run(run)
    context = _context(db, scope, case)
    contact = context.get("contact")
    if not isinstance(contact, dict) or contact.get("available") is not True:
        checkpoint_run(
            run,
            {
                "workflow_step": "analysis_complete",
                "completed_steps": ["context", "contact_guard"],
                "state": {
                    "analysis": RevenueAnalysisOutput(
                        summary="当前没有可用且已授权的联系人，系统未生成沟通草稿。",
                        abstained=True,
                        abstention_reason="contact_unavailable",
                    ).model_dump(mode="json"),
                    "context": context,
                },
            },
        )
        return
    request = ModelRequest(
        workflow_key=REVENUE_ANALYSIS_WORKFLOW_KEY,
        prompt_version=PROMPT_VERSION,
        system_instruction=(
            "你是羽毛球馆运营分析助手。只解释输入中的确定性事实，"
            "不得重新计算金额、声称已付款或已续费，不得提出自动修改资金、课时或价格。"
            "所有事实性结论必须引用给定 source_ref；沟通内容只是可编辑草稿。"
        ),
        input_data={
            "case_type": case.case_type,
            "context": context,
            "allowed_source_refs": sorted(_allowed_source_refs(case)),
        },
        output_schema=RevenueAnalysisOutput,
        model_profile=configured_model_profile(get_settings()),
    )
    response = model_client.generate(request)
    budget.consume_model_call(tokens=response.usage)
    output = _validate_analysis(
        RevenueAnalysisOutput.model_validate(response.output),
        case=case,
        context=context,
    )
    checkpoint_run(
        run,
        {
            "workflow_step": "analysis_complete",
            "completed_steps": ["context", "model", "validate"],
            "state": {
                "analysis": output.model_dump(mode="json"),
                "context": context,
                "provider": response.provider_metadata,
            },
        },
    )


def execute_revenue_analysis_workflow(
    db: Session,
    run: OperationRun,
    budget: RunBudget,
) -> None:
    scope = _scope_for_run(run)
    case = db.scalar(
        select(OperationCase).where(
            OperationCase.id == run.case_id,
            OperationCase.organization_id == scope.organization_id,
            OperationCase.venue_id == scope.venue_id,
        )
    )
    if case is None:
        raise RuntimeError("case_not_found")
    venue = db.scalar(
        select(Venue).where(
            Venue.id == scope.venue_id,
            Venue.organization_id == scope.organization_id,
        )
    )
    if venue is None:
        raise RuntimeError("venue_not_found")
    settings = get_settings()
    configuration = resolve_model_provider(settings)
    if venue.model_enabled is not True or configuration is None:
        checkpoint_run(
            run,
            {
                "workflow_step": "analysis_unavailable",
                "completed_steps": ["model_gate"],
                "state": {
                    "analysis": None,
                    "reason": "model_disabled"
                    if venue.model_enabled is not True
                    else "provider_not_configured",
                },
            },
        )
        return
    try:
        provider = model_provider_client(settings)
        run_revenue_analysis(
            db,
            run=run,
            case=case,
            model_client=VenueModelClient(db, scope, provider),
            budget=budget,
        )
    except (ModelUnavailable, ModelOutputInvalid, ValueError) as exc:
        checkpoint_run(
            run,
            {
                "workflow_step": "analysis_unavailable",
                "completed_steps": ["context", "model_attempt"],
                "state": {"analysis": None, "reason": type(exc).__name__},
            },
        )


def enqueue_revenue_analysis(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    policy_version: int,
    trigger_key: str,
) -> OperationRun:
    input_hash = canonical_hash(
        {
            "workflow_key": REVENUE_ANALYSIS_WORKFLOW_KEY,
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
            OperationRun.workflow_key == REVENUE_ANALYSIS_WORKFLOW_KEY,
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
        workflow_key=REVENUE_ANALYSIS_WORKFLOW_KEY,
        workflow_version=1,
        policy_key="default_operations",
        policy_version=policy_version,
        prompt_version=PROMPT_VERSION,
        toolset_version=1,
        model_profile=configured_model_profile(get_settings()),
        input_refs=[{"kind": "operation_case", "id": case.id, "version": case.version}],
        input_hash=input_hash,
        checkpoint={"workflow_step": "queued", "state": {}},
        state="queued",
        max_steps=4,
        max_model_calls=1,
        max_tool_calls=0,
        max_write_calls=0,
        deadline_at=now + timedelta(minutes=2),
    )
    db.add(run)
    db.flush()
    case.current_run_id = run.id
    return run


register_workflow(REVENUE_ANALYSIS_WORKFLOW_KEY, execute_revenue_analysis_workflow)
