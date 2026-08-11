from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReceivableFollowupPolicy(StrictSchema):
    aging_days: int = Field(ge=0, le=3650)
    escalation_days: int = Field(ge=1, le=3650)
    max_attempts: int = Field(ge=1, le=100)


class RenewalPolicy(StrictSchema):
    fixed_class_days: int = Field(ge=1, le=365)
    private_package_expiry_days: int = Field(ge=1, le=365)
    private_package_remaining_units: int = Field(ge=0, le=1000)
    cadence_days: int = Field(ge=1, le=365)


class AttendancePolicy(StrictSchema):
    grace_hours: int = Field(ge=0, le=720)


class ReplacementPolicy(StrictSchema):
    window_days: int = Field(ge=1, le=90)
    slot_minutes: Literal[15, 30, 60]
    resource_mode: Literal["original_only"]


class ReportPolicy(StrictSchema):
    min_sample_size: int = Field(ge=1)
    income_decline: Decimal
    refund_ratio: Decimal
    expense_growth: Decimal
    outstanding: Decimal
    cancellation_rate: Decimal
    low_utilization: Decimal
    coach_pending: Decimal


class RuntimePolicy(StrictSchema):
    case_sla_days: int = Field(ge=1, le=365)
    approval_expiry_minutes: int = Field(ge=1, le=10080)
    retry_limit: int = Field(ge=0, le=10)


class OperationsPolicyConfig(StrictSchema):
    receivable_followup: ReceivableFollowupPolicy
    renewal: RenewalPolicy
    attendance: AttendancePolicy
    replacement: ReplacementPolicy
    reports: ReportPolicy
    runtime: RuntimePolicy


class SourceReference(StrictSchema):
    kind: str = Field(min_length=1, max_length=80)
    id: str = Field(min_length=1, max_length=160)
    version: int | None = Field(default=None, ge=1)


class EvidenceEnvelope(StrictSchema):
    schema_version: int = Field(ge=1)
    organization_id: str
    venue_id: str
    detector_key: str
    detector_version: int = Field(ge=1)
    policy_version: int = Field(ge=1)
    subject_type: str
    subject_id: str
    case_key: str
    severity_baseline: Literal["info", "low", "medium", "high", "critical"]
    facts: dict[str, object]
    source_refs: list[SourceReference]
    business_links: list[str] = Field(default_factory=list)
    generated_at: datetime
    evidence_hash: str
    fingerprint: str


class ModelCitation(StrictSchema):
    source_ref: str
    claim: str = Field(max_length=500)


class ModelOutput(StrictSchema):
    summary: str = Field(max_length=4000)
    anomaly_explanations: list[str] = Field(default_factory=list, max_length=20)
    recommendations: list[str] = Field(default_factory=list, max_length=20)
    citations: list[ModelCitation] = Field(default_factory=list, max_length=50)
    abstained: bool = False
    abstention_reason: str | None = Field(default=None, max_length=500)


class RunCheckpoint(StrictSchema):
    workflow_step: str
    cursor: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    state: dict[str, object] = Field(default_factory=dict)


class ToolResultEnvelope(StrictSchema):
    schema_version: int = 1
    tool_key: str
    tool_version: int = Field(ge=1)
    ok: bool
    result: dict[str, object] | None = None
    error_code: str | None = None
    retryable: bool = False
    source_refs: list[SourceReference] = Field(default_factory=list)


class ReportMetric(StrictSchema):
    metric_ref: str
    metric_key: str
    scope: Literal["period", "as_of"]
    unit: Literal["cny", "count", "lesson_unit", "hour", "ratio"]
    value: Decimal | int
    display_precision: int = Field(ge=0, le=6)
    calculated_at: datetime
    source_refs: list[SourceReference] = Field(default_factory=list)
    data_status: Literal["complete", "partial", "insufficient", "data_quality_issue"] = (
        "complete"
    )


class ReportAnomaly(StrictSchema):
    anomaly_id: str
    rule_key: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    metric_refs: list[str]
    threshold: dict[str, object]
    comparison: dict[str, object]
    evidence: dict[str, object]
    data_sufficiency: Literal["sufficient", "insufficient"]


class OperationsError(StrictSchema):
    code: str
    detail: str
    retryable: bool = False
    safe_context: dict[str, object] = Field(default_factory=dict)
