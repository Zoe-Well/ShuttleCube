"""Add nullable Scope ownership and deterministically backfill legacy data."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0018_scope_backfill"
down_revision = "0017_organization_venue_membership"
branch_labels = None
depends_on = None

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"

ORGANIZATION_SCOPED_TABLES = (
    "students",
    "guardians",
    "student_guardians",
    "walk_in_customers",
    "coach_profiles",
    "coach_rates",
    "attachments",
)

VENUE_SCOPED_TABLES = (
    "fixed_classes",
    "class_sessions",
    "enrollments",
    "attendance_records",
    "lesson_unit_ledgers",
    "makeup_records",
    "private_lesson_packages",
    "private_lessons",
    "venue_bookings",
    "venue_price_rules",
    "temporary_events",
    "event_participants",
    "receivables",
    "payments",
    "refunds",
    "expenses",
    "other_incomes",
    "coach_fees",
    "payroll_settlements",
    "schedule_entries",
    "schedule_allocations",
    "court_blocks",
    "audit_logs",
)


def _issue_id(table_name: str, record_id: str, issue_code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"shuttlecube:migration:{table_name}:{record_id}:{issue_code}"))


def _add_scope_columns(table_name: str, *, venue_scoped: bool) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
        batch.create_index(f"ix_{table_name}_organization_id", ["organization_id"])
        batch.create_foreign_key(
            f"fk_{table_name}_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        if venue_scoped:
            batch.add_column(sa.Column("venue_id", sa.String(36), nullable=True))
            batch.create_index(f"ix_{table_name}_venue_id", ["venue_id"])
            batch.create_foreign_key(
                f"fk_{table_name}_venue_id",
                "venues",
                ["venue_id"],
                ["id"],
                ondelete="RESTRICT",
            )


def _record_unresolved_venue_rows(
    connection: sa.Connection,
    *,
    table_name: str,
    venue_count: int,
) -> None:
    inspector = sa.inspect(connection)
    primary_key = inspector.get_pk_constraint(table_name).get("constrained_columns") or []
    if not primary_key:
        primary_key = ["rowid"]
    id_expression = " || ':' || ".join(f"CAST({column} AS TEXT)" for column in primary_key)
    rows = connection.execute(
        sa.text(f'SELECT {id_expression} AS record_id FROM "{table_name}"')
    )
    issue_code = "venue_missing" if venue_count == 0 else "venue_ambiguous"
    detail = (
        "No legacy Venue exists for this venue-scoped record."
        if venue_count == 0
        else "More than one legacy Venue exists and this record has no deterministic owner."
    )
    now = datetime.now(UTC)
    for (record_id,) in rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO migration_issues (
                    id, migration_key, table_name, record_id, issue_code,
                    detail, resolved_at, created_at
                ) VALUES (
                    :id, '0018_scope_backfill', :table_name, :record_id, :issue_code,
                    :detail, NULL, :created_at
                )
                """
            ),
            {
                "id": _issue_id(table_name, str(record_id), issue_code),
                "table_name": table_name,
                "record_id": str(record_id),
                "issue_code": issue_code,
                "detail": detail,
                "created_at": now,
            },
        )


def upgrade() -> None:
    op.create_table(
        "migration_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("migration_key", sa.String(80), nullable=False),
        sa.Column("table_name", sa.String(80), nullable=False),
        sa.Column("record_id", sa.String(160), nullable=False),
        sa.Column("issue_code", sa.String(80), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "migration_key", "table_name", "record_id", "issue_code", name="uq_migration_issue"
        ),
    )
    op.create_index(
        "ix_migration_issues_open", "migration_issues", ["migration_key", "resolved_at"]
    )

    for table_name in ORGANIZATION_SCOPED_TABLES:
        _add_scope_columns(table_name, venue_scoped=False)
    for table_name in VENUE_SCOPED_TABLES:
        _add_scope_columns(table_name, venue_scoped=True)

    connection = op.get_bind()
    for table_name in (*ORGANIZATION_SCOPED_TABLES, *VENUE_SCOPED_TABLES):
        connection.execute(
            sa.text(f'UPDATE "{table_name}" SET organization_id = :organization_id'),
            {"organization_id": DEFAULT_ORGANIZATION_ID},
        )

    venue_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM venues"))]
    if len(venue_ids) == 1:
        for table_name in VENUE_SCOPED_TABLES:
            connection.execute(
                sa.text(f'UPDATE "{table_name}" SET venue_id = :venue_id'),
                {"venue_id": venue_ids[0]},
            )
    else:
        for table_name in VENUE_SCOPED_TABLES:
            _record_unresolved_venue_rows(
                connection,
                table_name=table_name,
                venue_count=len(venue_ids),
            )


def downgrade() -> None:
    for table_name in reversed(VENUE_SCOPED_TABLES):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(f"fk_{table_name}_venue_id", type_="foreignkey")
            batch.drop_constraint(f"fk_{table_name}_organization_id", type_="foreignkey")
            batch.drop_index(f"ix_{table_name}_venue_id")
            batch.drop_index(f"ix_{table_name}_organization_id")
            batch.drop_column("venue_id")
            batch.drop_column("organization_id")
    for table_name in reversed(ORGANIZATION_SCOPED_TABLES):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(f"fk_{table_name}_organization_id", type_="foreignkey")
            batch.drop_index(f"ix_{table_name}_organization_id")
            batch.drop_column("organization_id")
    op.drop_index("ix_migration_issues_open", table_name="migration_issues")
    op.drop_table("migration_issues")
