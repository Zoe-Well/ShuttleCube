"""Add the scoped intelligent-operations runtime."""

import sqlalchemy as sa
from alembic import op

revision = "0021_operations_runtime"
down_revision = "0020_operations_policy_settings"
branch_labels = None
depends_on = None


def _scope_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("venue_id", sa.String(36), nullable=False),
    )


def _scope_constraints() -> tuple[sa.ForeignKeyConstraint, sa.ForeignKeyConstraint]:
    return (
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], ondelete="RESTRICT"),
    )


def _create_scope_indexes(table: str) -> None:
    op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    op.create_index(f"ix_{table}_venue_id", table, ["venue_id"])


def _create_append_only_event_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER operation_events_no_update
            BEFORE UPDATE ON operation_events
            BEGIN
                SELECT RAISE(ABORT, 'operation_events are append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER operation_events_no_delete
            BEFORE DELETE ON operation_events
            BEGIN
                SELECT RAISE(ABORT, 'operation_events are append-only');
            END
            """
        )
    elif dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_operation_event_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'operation_events are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER operation_events_no_mutation
            BEFORE UPDATE OR DELETE ON operation_events
            FOR EACH ROW EXECUTE FUNCTION reject_operation_event_mutation()
            """
        )


def _drop_append_only_event_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS operation_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS operation_events_no_delete")
    elif dialect == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS operation_events_no_mutation ON operation_events"
        )
        op.execute("DROP FUNCTION IF EXISTS reject_operation_event_mutation()")


def upgrade() -> None:
    op.create_table(
        "operation_cases",
        *_scope_columns(),
        sa.Column("case_type", sa.String(80), nullable=False),
        sa.Column("subject_type", sa.String(80), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("case_key", sa.String(64), nullable=False),
        sa.Column("detector_key", sa.String(80), nullable=False),
        sa.Column("detector_version", sa.Integer(), nullable=False),
        sa.Column("policy_key", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("occurrence_no", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("priority_score", sa.Numeric(10, 2), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("business_summary", sa.Text(), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queue_key", sa.String(80), nullable=False),
        sa.Column("required_capability", sa.String(120), nullable=False),
        sa.Column("assigned_to", sa.String(36), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by", sa.String(36), nullable=True),
        sa.Column("created_by_type", sa.String(20), nullable=False),
        sa.Column("current_run_id", sa.String(36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_reason", sa.Text(), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_scope_constraints(),
        sa.CheckConstraint(
            "occurrence_no >= 1", name="ck_operation_case_occurrence"
        ),
        sa.UniqueConstraint("case_key", name="uq_operation_cases_case_key"),
        sa.UniqueConstraint(
            "venue_id",
            "detector_key",
            "subject_type",
            "subject_id",
            name="uq_operation_case_subject",
        ),
    )
    _create_scope_indexes("operation_cases")
    for column in (
        "case_type",
        "severity",
        "state",
        "queue_key",
        "assigned_to",
        "first_detected_at",
        "last_detected_at",
        "next_check_at",
    ):
        op.create_index(f"ix_operation_cases_{column}", "operation_cases", [column])
    op.create_index(
        "ix_operation_case_queue",
        "operation_cases",
        ["venue_id", "queue_key", "state", "severity", "due_at"],
    )

    op.create_table(
        "case_activities",
        *_scope_columns(),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("case_occurrence_no", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("contact_subject_type", sa.String(80), nullable=True),
        sa.Column("contact_subject_id", sa.String(36), nullable=True),
        sa.Column("outcome_code", sa.String(40), nullable=False),
        sa.Column("summary", sa.String(2000), nullable=False),
        sa.Column("happened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operated_by", sa.String(36), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_constraints(),
        sa.ForeignKeyConstraint(
            ["case_id"], ["operation_cases.id"], ondelete="RESTRICT"
        ),
    )
    _create_scope_indexes("case_activities")
    for column in ("case_id", "happened_at", "operated_by"):
        op.create_index(f"ix_case_activities_{column}", "case_activities", [column])
    op.create_index(
        "ix_case_activity_timeline", "case_activities", ["case_id", "created_at"]
    )
    op.create_index(
        "ix_case_activity_operator",
        "case_activities",
        ["venue_id", "operated_by", "happened_at"],
    )

    op.create_table(
        "operation_runs",
        *_scope_columns(),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("parent_run_id", sa.String(36), nullable=True),
        sa.Column("run_type", sa.String(40), nullable=False),
        sa.Column("trigger_type", sa.String(24), nullable=False),
        sa.Column("workflow_key", sa.String(100), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("policy_key", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("toolset_version", sa.Integer(), nullable=False),
        sa.Column("model_profile", sa.String(80), nullable=True),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_steps", sa.Integer(), nullable=False),
        sa.Column("max_model_calls", sa.Integer(), nullable=False),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False),
        sa.Column("max_write_calls", sa.Integer(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("model_call_count", sa.Integer(), nullable=False),
        sa.Column("tool_call_count", sa.Integer(), nullable=False),
        sa.Column("write_call_count", sa.Integer(), nullable=False),
        sa.Column("token_usage_summary", sa.JSON(), nullable=False),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_summary", sa.String(1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_scope_constraints(),
        sa.ForeignKeyConstraint(
            ["case_id"], ["operation_cases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"], ["operation_runs.id"], ondelete="RESTRICT"
        ),
    )
    _create_scope_indexes("operation_runs")
    for column in (
        "case_id",
        "run_type",
        "state",
        "next_attempt_at",
        "lease_owner",
        "lease_expires_at",
    ):
        op.create_index(f"ix_operation_runs_{column}", "operation_runs", [column])
    op.create_index(
        "ix_operation_run_claim",
        "operation_runs",
        ["state", "next_attempt_at", "lease_expires_at", "venue_id"],
    )

    op.create_table(
        "operation_events",
        *_scope_columns(),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("payload_redacted", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_constraints(),
        sa.ForeignKeyConstraint(
            ["case_id"], ["operation_cases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["operation_runs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("run_id", "sequence", name="uq_operation_event_sequence"),
    )
    _create_scope_indexes("operation_events")
    for column in ("run_id", "event_type", "trace_id", "occurred_at"):
        op.create_index(f"ix_operation_events_{column}", "operation_events", [column])
    _create_append_only_event_guards()

    op.create_table(
        "operation_tool_calls",
        *_scope_columns(),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("policy_key", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("tool_key", sa.String(100), nullable=False),
        sa.Column("tool_version", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("normalized_input", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("impact_snapshot", sa.JSON(), nullable=False),
        sa.Column("subject_versions", sa.JSON(), nullable=False),
        sa.Column("required_capability", sa.String(120), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("result_reference", sa.String(240), nullable=True),
        sa.Column("result_summary", sa.String(1000), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_scope_constraints(),
        sa.ForeignKeyConstraint(
            ["run_id"], ["operation_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["operation_cases.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "venue_id",
            "tool_key",
            "idempotency_key",
            name="uq_operation_tool_idempotency",
        ),
    )
    _create_scope_indexes("operation_tool_calls")
    for column in ("run_id", "tool_key", "state"):
        op.create_index(
            f"ix_operation_tool_calls_{column}", "operation_tool_calls", [column]
        )

    op.create_table(
        "operations_report_snapshots",
        *_scope_columns(),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_timezone", sa.String(64), nullable=False),
        sa.Column("period_state", sa.String(20), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by", sa.String(36), nullable=False),
        sa.Column("comparison_start", sa.Date(), nullable=True),
        sa.Column("comparison_end", sa.Date(), nullable=True),
        sa.Column("comparison_status", sa.String(32), nullable=False),
        sa.Column("policy_key", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("metric_version", sa.Integer(), nullable=False),
        sa.Column("anomaly_rule_version", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("breakdowns", sa.JSON(), nullable=False),
        sa.Column("anomalies", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("narrative_state", sa.String(24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("anomaly_explanations", sa.JSON(), nullable=True),
        sa.Column("recommendations", sa.JSON(), nullable=True),
        sa.Column("caveats", sa.JSON(), nullable=True),
        sa.Column("narrative_run_id", sa.String(36), nullable=True),
        sa.Column("model_profile", sa.String(80), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_constraints(),
        sa.ForeignKeyConstraint(
            ["run_id"], ["operation_runs.id"], ondelete="RESTRICT"
        ),
    )
    _create_scope_indexes("operations_report_snapshots")
    for column in ("run_id", "period_type", "period_start", "generated_at"):
        op.create_index(
            f"ix_operations_report_snapshots_{column}",
            "operations_report_snapshots",
            [column],
        )
    op.create_index(
        "ix_operations_report_period",
        "operations_report_snapshots",
        ["venue_id", "period_type", "period_start", "generated_at"],
    )

    op.create_table(
        "operation_approvals",
        *_scope_columns(),
        sa.Column("tool_call_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("policy_key", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("approval_policy", sa.String(40), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("action_summary", sa.String(1000), nullable=False),
        sa.Column("impact_snapshot", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("subject_versions", sa.JSON(), nullable=False),
        sa.Column("required_capability", sa.String(120), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(36), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *_scope_constraints(),
        sa.ForeignKeyConstraint(
            ["tool_call_id"], ["operation_tool_calls.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["operation_cases.id"], ondelete="RESTRICT"
        ),
    )
    _create_scope_indexes("operation_approvals")
    for column in ("tool_call_id", "state", "expires_at"):
        op.create_index(
            f"ix_operation_approvals_{column}", "operation_approvals", [column]
        )
    op.create_index(
        "uq_operation_approval_pending",
        "operation_approvals",
        ["tool_call_id"],
        unique=True,
        sqlite_where=sa.text("state = 'pending'"),
        postgresql_where=sa.text("state = 'pending'"),
    )


def downgrade() -> None:
    _drop_append_only_event_guards()
    for table in (
        "operation_approvals",
        "operations_report_snapshots",
        "operation_tool_calls",
        "operation_events",
        "operation_runs",
        "case_activities",
        "operation_cases",
    ):
        op.drop_table(table)
