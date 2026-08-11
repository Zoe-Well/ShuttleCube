from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from shuttlecube.infrastructure.database.base import (
    Base,
    IdMixin,
    TimestampMixin,
    VersionMixin,
    utc_now,
)


class OperationCase(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "operation_cases"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    case_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_type: Mapped[str] = mapped_column(String(80))
    subject_id: Mapped[str] = mapped_column(String(36))
    case_key: Mapped[str] = mapped_column(String(64), unique=True)
    detector_key: Mapped[str] = mapped_column(String(80))
    detector_version: Mapped[int] = mapped_column(Integer)
    policy_key: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[int] = mapped_column(Integer)
    occurrence_no: Mapped[int] = mapped_column(Integer, default=1)
    fingerprint: Mapped[str] = mapped_column(String(64))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    title: Mapped[str] = mapped_column(String(240))
    business_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="open", index=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queue_key: Mapped[str] = mapped_column(String(80), index=True)
    required_capability: Mapped[str] = mapped_column(String(120))
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_type: Mapped[str] = mapped_column(String(20), default="system")
    current_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "detector_key",
            "subject_type",
            "subject_id",
            name="uq_operation_case_subject",
        ),
        CheckConstraint("occurrence_no >= 1", name="ck_operation_case_occurrence"),
        Index(
            "ix_operation_case_queue",
            "venue_id",
            "queue_key",
            "state",
            "severity",
            "due_at",
        ),
    )


class CaseActivity(IdMixin, Base):
    __tablename__ = "case_activities"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("operation_cases.id", ondelete="RESTRICT"), index=True
    )
    case_occurrence_no: Mapped[int] = mapped_column(Integer)
    activity_type: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(24))
    contact_subject_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    contact_subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome_code: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(String(2000))
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operated_by: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(20))
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_case_activity_timeline", "case_id", "created_at"),
        Index("ix_case_activity_operator", "venue_id", "operated_by", "happened_at"),
    )


class OperationRun(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "operation_runs"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("operation_cases.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("operation_runs.id", ondelete="RESTRICT"), nullable=True
    )
    run_type: Mapped[str] = mapped_column(String(40), index=True)
    trigger_type: Mapped[str] = mapped_column(String(24))
    workflow_key: Mapped[str] = mapped_column(String(100))
    workflow_version: Mapped[int] = mapped_column(Integer)
    policy_key: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[int] = mapped_column(Integer)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    toolset_version: Mapped[int] = mapped_column(Integer)
    model_profile: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_refs: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64))
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    max_steps: Mapped[int] = mapped_column(Integer)
    max_model_calls: Mapped[int] = mapped_column(Integer)
    max_tool_calls: Mapped[int] = mapped_column(Integer)
    max_write_calls: Mapped[int] = mapped_column(Integer)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    model_call_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    write_call_count: Mapped[int] = mapped_column(Integer, default=0)
    token_usage_summary: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index(
            "ix_operation_run_claim",
            "state",
            "next_attempt_at",
            "lease_expires_at",
            "venue_id",
        ),
    )


class OperationEvent(IdMixin, Base):
    __tablename__ = "operation_events"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("operation_cases.id", ondelete="RESTRICT"), nullable=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("operation_runs.id", ondelete="RESTRICT"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_redacted: Mapped[dict[str, object]] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_operation_event_sequence"),
    )


class OperationToolCall(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "operation_tool_calls"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("operation_runs.id", ondelete="RESTRICT"), index=True
    )
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("operation_cases.id", ondelete="RESTRICT"), nullable=True
    )
    policy_key: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[int] = mapped_column(Integer)
    tool_key: Mapped[str] = mapped_column(String(100), index=True)
    tool_version: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20))
    normalized_input: Mapped[dict[str, object]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64))
    impact_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    subject_versions: Mapped[dict[str, int]] = mapped_column(JSON)
    required_capability: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    result_reference: Mapped[str | None] = mapped_column(String(240), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "tool_key",
            "idempotency_key",
            name="uq_operation_tool_idempotency",
        ),
    )


class OperationApproval(IdMixin, VersionMixin, Base):
    __tablename__ = "operation_approvals"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    tool_call_id: Mapped[str] = mapped_column(
        ForeignKey("operation_tool_calls.id", ondelete="RESTRICT"), index=True
    )
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("operation_cases.id", ondelete="RESTRICT"), nullable=True
    )
    policy_key: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[int] = mapped_column(Integer)
    requested_by: Mapped[str] = mapped_column(String(36))
    approval_policy: Mapped[str] = mapped_column(String(40))
    risk_level: Mapped[str] = mapped_column(String(20))
    action_summary: Mapped[str] = mapped_column(String(1000))
    impact_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64))
    subject_versions: Mapped[dict[str, int]] = mapped_column(JSON)
    required_capability: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index(
            "uq_operation_approval_pending",
            "tool_call_id",
            unique=True,
            sqlite_where=sa_text("state = 'pending'"),
            postgresql_where=sa_text("state = 'pending'"),
        ),
    )


class OperationsReportSnapshot(IdMixin, Base):
    __tablename__ = "operations_report_snapshots"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    venue_id: Mapped[str] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("operation_runs.id", ondelete="RESTRICT"), index=True
    )
    period_type: Mapped[str] = mapped_column(String(16), index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date)
    effective_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    business_timezone: Mapped[str] = mapped_column(String(64))
    period_state: Mapped[str] = mapped_column(String(20))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    generated_by: Mapped[str] = mapped_column(String(36))
    comparison_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    comparison_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    comparison_status: Mapped[str] = mapped_column(String(32))
    policy_key: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[int] = mapped_column(Integer)
    metric_version: Mapped[int] = mapped_column(Integer)
    anomaly_rule_version: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    breakdowns: Mapped[dict[str, object]] = mapped_column(JSON)
    anomalies: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    source_refs: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    narrative_state: Mapped[str] = mapped_column(String(24), default="not_requested")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    anomaly_explanations: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON, nullable=True
    )
    recommendations: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    caveats: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    narrative_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model_profile: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index(
            "ix_operations_report_period",
            "venue_id",
            "period_type",
            "period_start",
            "generated_at",
        ),
    )
