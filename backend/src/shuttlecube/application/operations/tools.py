from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.access import AccessDenied, require_capability
from shuttlecube.domain.operations.models import OperationCase


class ToolError(RuntimeError):
    pass


class UnknownTool(ToolError):
    pass


class CapabilityDenied(ToolError):
    pass


class ToolDisabled(ToolError):
    pass


class StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def model_dump(self, **kwargs: Any) -> dict[str, object]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


class CaseInput(StrictToolInput):
    case_id: str = Field(min_length=1, max_length=36)


class CaseEvidenceInput(CaseInput):
    occurrence_no: int | None = Field(default=None, ge=1)


class ReplacementCandidatesInput(CaseInput):
    resource_plan_version: int | None = Field(default=None, ge=1)


class ReportSnapshotInput(StrictToolInput):
    snapshot_id: str = Field(min_length=1, max_length=36)


class FollowupOutcomeInput(CaseInput):
    expected_case_version: int = Field(ge=1)
    expected_occurrence_no: int = Field(ge=1)
    activity_type: Literal[
        "contact_attempt", "contact_result", "promise", "note", "status_decision"
    ]
    channel: Literal["phone", "wechat", "in_person", "other", "none"]
    contact_subject_type: Literal["student", "guardian"] | None = None
    contact_subject_id: str | None = Field(default=None, max_length=36)
    outcome_code: Literal[
        "reached",
        "no_answer",
        "promised_payment",
        "paid_elsewhere",
        "renewed",
        "no_intent",
        "follow_later",
        "disputed",
        "invalid_contact",
        "other",
    ]
    summary: str = Field(min_length=1, max_length=2000)
    happened_at: datetime
    next_check_at: datetime | None = None
    confirmed_by_user: bool


class DismissCaseInput(CaseInput):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class ScheduleReplacementInput(CaseInput):
    resource_plan_id: str = Field(min_length=1, max_length=36)
    resource_plan_version: int = Field(ge=1)
    expected_case_version: int = Field(ge=1)


class ToolOutput(StrictToolInput):
    data: dict[str, object] = Field(default_factory=dict)


ToolHandler = Callable[[object, BaseModel], Mapping[str, object]]


@dataclass(frozen=True)
class ToolExecutionContext:
    db: Session
    scope: RequestScope
    request_id: str
    run_id: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    tool_key: str
    tool_version: int
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    risk_level: Literal["read", "low", "medium", "high"]
    required_capability: str
    approval_policy: Literal[
        "none", "explicit_confirmation", "mandatory_approval", "human_only"
    ]
    idempotency_scope: Literal["none", "venue_tool_key"]
    timeout_seconds: float
    redaction_policy: str
    verifier: str
    enabled_flag: str | None
    model_selectable: bool = False
    implementation: ToolHandler | None = None

    @property
    def is_write(self) -> bool:
        return self.risk_level != "read"


def _definition(
    tool_key: str,
    description: str,
    input_schema: type[BaseModel],
    capability: str,
    *,
    risk: Literal["read", "low", "medium", "high"] = "read",
    approval: Literal[
        "none", "explicit_confirmation", "mandatory_approval", "human_only"
    ] = "none",
    model_selectable: bool = False,
    implementation: ToolHandler | None = None,
) -> ToolDefinition:
    is_write = risk != "read"
    return ToolDefinition(
        tool_key=tool_key,
        tool_version=1,
        description=description,
        input_schema=input_schema,
        output_schema=ToolOutput,
        risk_level=risk,
        required_capability=capability,
        approval_policy=approval,
        idempotency_scope="venue_tool_key" if is_write else "none",
        timeout_seconds=15.0 if is_write else 10.0,
        redaction_policy="operations-tool-v1",
        verifier=f"{tool_key}:v1",
        enabled_flag="write_tools_enabled" if is_write else None,
        model_selectable=model_selectable,
        implementation=implementation,
    )


def _record_followup_outcome(
    raw_context: object,
    raw_input: BaseModel,
) -> Mapping[str, object]:
    from shuttlecube.application.operations.activities import (
        FollowupActivityInput,
        activity_payload,
        record_followup_activity,
    )

    if not isinstance(raw_context, ToolExecutionContext):
        raise ToolError("record_followup_outcome requires ToolExecutionContext")
    payload = FollowupOutcomeInput.model_validate(raw_input)
    case = raw_context.db.scalar(
        select(OperationCase).where(
            OperationCase.id == payload.case_id,
            OperationCase.organization_id == raw_context.scope.organization_id,
            OperationCase.venue_id == raw_context.scope.venue_id,
        )
    )
    if case is None:
        raise ToolError("scope_not_found")
    activity = record_followup_activity(
        raw_context.db,
        scope=raw_context.scope,
        case=case,
        payload=FollowupActivityInput.model_validate(
            payload.model_dump(exclude={"case_id"})
        ),
        request_id=raw_context.request_id,
        source="tool",
        run_id=raw_context.run_id,
    )
    return {"data": activity_payload(activity)}


def _get_reconciliation_result(
    raw_context: object,
    raw_input: BaseModel,
) -> Mapping[str, object]:
    if not isinstance(raw_context, ToolExecutionContext):
        raise ToolError("get_reconciliation_result requires ToolExecutionContext")
    payload = CaseInput.model_validate(raw_input)
    case = raw_context.db.scalar(
        select(OperationCase).where(
            OperationCase.id == payload.case_id,
            OperationCase.organization_id == raw_context.scope.organization_id,
            OperationCase.venue_id == raw_context.scope.venue_id,
            OperationCase.case_type == "reconciliation_failure",
        )
    )
    if case is None:
        raise ToolError("scope_not_found")
    facts = (case.evidence or {}).get("facts", {})
    result = facts.get("reconciliation") if isinstance(facts, dict) else None
    if not isinstance(result, dict):
        raise ToolError("reconciliation_result_missing")
    return {
        "data": {
            **result,
            "failure_count": int(facts.get("failure_count", 1)),
            "automatic_repair_available": False,
        }
    }


class ToolRegistry:
    def __init__(self, definitions: Iterable[ToolDefinition]) -> None:
        items = list(definitions)
        self._definitions = {item.tool_key: item for item in items}
        if len(self._definitions) != len(items):
            raise ValueError("Duplicate operation tool key")

    @classmethod
    def default(cls) -> ToolRegistry:
        return cls(
            (
                _definition(
                    "get_case_evidence",
                    "Read normalized deterministic evidence for one operation case.",
                    CaseEvidenceInput,
                    "operations.case.read",
                    model_selectable=True,
                ),
                _definition(
                    "get_receivable_followup_context",
                    "Read the authorized case-level receivable follow-up context.",
                    CaseInput,
                    "operations.receivable.followup.read",
                    model_selectable=True,
                ),
                _definition(
                    "get_renewal_followup_context",
                    "Read deterministic renewal facts for one operation case.",
                    CaseInput,
                    "operations.case.read",
                    model_selectable=True,
                ),
                _definition(
                    "list_replacement_candidates",
                    "Read server-generated legal replacement resource plans.",
                    ReplacementCandidatesInput,
                    "operations.case.read",
                ),
                _definition(
                    "get_reconciliation_result",
                    "Read deterministic reconciliation results for one case.",
                    CaseInput,
                    "operations.case.read",
                    model_selectable=True,
                    implementation=_get_reconciliation_result,
                ),
                _definition(
                    "get_operations_report_snapshot",
                    "Read an immutable deterministic operations report snapshot.",
                    ReportSnapshotInput,
                    "operations.report.financial.read",
                ),
                _definition(
                    "record_followup_outcome",
                    "Record a user-confirmed structured follow-up activity.",
                    FollowupOutcomeInput,
                    "operations.case.manage",
                    risk="low",
                    approval="explicit_confirmation",
                    implementation=_record_followup_outcome,
                ),
                _definition(
                    "dismiss_operation_case",
                    "Dismiss one case as an explicit human decision.",
                    DismissCaseInput,
                    "operations.case.manage",
                    risk="low",
                    approval="human_only",
                ),
                _definition(
                    "schedule_cancelled_class_replacement",
                    "Execute an approved server-generated replacement resource plan.",
                    ScheduleReplacementInput,
                    "operations.schedule.execute",
                    risk="medium",
                    approval="mandatory_approval",
                ),
            )
        )

    def keys(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def get(self, tool_key: str) -> ToolDefinition:
        try:
            return self._definitions[tool_key]
        except KeyError as exc:
            raise UnknownTool(tool_key) from exc

    def validate_input(self, tool_key: str, value: Mapping[str, object]) -> BaseModel:
        return self.get(tool_key).input_schema.model_validate(value)

    def validate_output(self, tool_key: str, value: Mapping[str, object]) -> BaseModel:
        return self.get(tool_key).output_schema.model_validate(value)

    def execute(
        self,
        tool_key: str,
        *,
        context: ToolExecutionContext,
        value: Mapping[str, object],
        write_tools_enabled: bool,
    ) -> BaseModel:
        definition = self.authorize(
            tool_key,
            scope=context.scope,
            write_tools_enabled=write_tools_enabled,
        )
        if definition.implementation is None:
            raise ToolDisabled(f"{tool_key} has no registered handler")
        normalized = definition.input_schema.model_validate(value)
        result = definition.implementation(context, normalized)
        return definition.output_schema.model_validate(result)

    def authorize(
        self,
        tool_key: str,
        *,
        scope: RequestScope,
        write_tools_enabled: bool,
    ) -> ToolDefinition:
        definition = self.get(tool_key)
        try:
            require_capability(scope, definition.required_capability)
        except AccessDenied as exc:
            raise CapabilityDenied(definition.required_capability) from exc
        if definition.is_write and not write_tools_enabled:
            raise ToolDisabled(tool_key)
        return definition

    def model_projection(
        self,
        allowed_tool_keys: Iterable[str],
        *,
        scope: RequestScope,
    ) -> list[dict[str, object]]:
        projected: list[dict[str, object]] = []
        for tool_key in allowed_tool_keys:
            definition = self.get(tool_key)
            if not definition.model_selectable or definition.is_write:
                continue
            try:
                require_capability(scope, definition.required_capability)
            except AccessDenied:
                continue
            projected.append(
                {
                    "type": "function",
                    "name": definition.tool_key,
                    "description": definition.description,
                    "parameters": definition.input_schema.model_json_schema(),
                    "strict": True,
                }
            )
        return projected

    def redact_result(
        self,
        tool_key: str,
        result: Mapping[str, object],
        *,
        capabilities: frozenset[str],
    ) -> dict[str, object]:
        self.get(tool_key)
        sensitive_keys = {
            "phone",
            "wechat",
            "cookie",
            "authorization",
            "api_key",
            "secret",
            "credential",
            "attachment_body",
            "voucher_url",
        }
        venue_money_keys = {
            "venue_total_outstanding",
            "venue_income",
            "venue_expense",
            "venue_profit",
            "payroll_total",
            "coach_salary",
        }

        def redact(value: object, key: str | None = None) -> object:
            normalized = (key or "").lower()
            if normalized in sensitive_keys or any(
                fragment in normalized
                for fragment in ("password", "token", "secret", "credential")
            ):
                return "[REDACTED]"
            if normalized in venue_money_keys:
                financial = "operations.report.financial.read" in capabilities
                payroll = "operations.payroll.read" in capabilities
                if (normalized.startswith(("payroll", "coach_")) and not payroll) or (
                    not normalized.startswith(("payroll", "coach_")) and not financial
                ):
                    return "[REDACTED]"
            if isinstance(value, Mapping):
                return {str(k): redact(v, str(k)) for k, v in value.items()}
            if isinstance(value, list):
                return [redact(item) for item in value]
            return value

        return {str(key): redact(value, str(key)) for key, value in result.items()}
