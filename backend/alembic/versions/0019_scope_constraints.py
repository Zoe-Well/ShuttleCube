"""Enforce non-null Scope and scoped business uniqueness."""

import sqlalchemy as sa
from alembic import op

from alembic.util import CommandError

revision = "0019_scope_constraints"
down_revision = "0018_scope_backfill"
branch_labels = None
depends_on = None

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

SQLITE_NAMING_CONVENTION = {
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}

SCOPE_RELATIONSHIPS = (
    ("class_sessions", "fixed_class_id", "fixed_classes", True),
    ("enrollments", "fixed_class_id", "fixed_classes", True),
    ("attendance_records", "class_session_id", "class_sessions", True),
    ("makeup_records", "origin_attendance_id", "attendance_records", True),
    ("private_lessons", "package_id", "private_lesson_packages", True),
    ("event_participants", "event_id", "temporary_events", True),
    ("payments", "receivable_id", "receivables", True),
    ("refunds", "receivable_id", "receivables", True),
    ("payroll_settlements", "expense_id", "expenses", True),
    ("schedule_allocations", "schedule_entry_id", "schedule_entries", True),
)


def _scalar(connection: sa.Connection, statement: str) -> int:
    return int(connection.execute(sa.text(statement)).scalar_one())


def _validate_backfill(connection: sa.Connection) -> None:
    open_issues = _scalar(
        connection,
        "SELECT count(*) FROM migration_issues WHERE resolved_at IS NULL",
    )
    if open_issues:
        raise CommandError(
            f"Scope migration has {open_issues} unresolved migration issue(s); "
            "resolve them before enabling constraints."
        )

    nulls: list[str] = []
    if _scalar(connection, "SELECT count(*) FROM venues WHERE organization_id IS NULL"):
        nulls.append("venues.organization_id")
    for table_name in ORGANIZATION_SCOPED_TABLES:
        if _scalar(
            connection,
            f'SELECT count(*) FROM "{table_name}" WHERE organization_id IS NULL',
        ):
            nulls.append(f"{table_name}.organization_id")
    for table_name in VENUE_SCOPED_TABLES:
        if _scalar(
            connection,
            f"""
            SELECT count(*) FROM "{table_name}"
            WHERE organization_id IS NULL OR venue_id IS NULL
            """,
        ):
            nulls.append(f"{table_name}.scope")
    if nulls:
        raise CommandError("Scope backfill left null ownership in: " + ", ".join(nulls))

    mismatches: list[str] = []
    for child, foreign_key, parent, venue_scoped in SCOPE_RELATIONSHIPS:
        venue_clause = " OR child.venue_id <> parent.venue_id" if venue_scoped else ""
        count = _scalar(
            connection,
            f"""
            SELECT count(*)
            FROM "{child}" child
            JOIN "{parent}" parent ON parent.id = child."{foreign_key}"
            WHERE child.organization_id <> parent.organization_id{venue_clause}
            """,
        )
        if count:
            mismatches.append(f"{child}.{foreign_key}->{parent} ({count})")
    if mismatches:
        raise CommandError("Cross-Scope relationships found: " + ", ".join(mismatches))


def _set_scope_nullable(table_name: str, *, venue_scoped: bool, nullable: bool) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.alter_column(
            "organization_id",
            existing_type=sa.String(36),
            nullable=nullable,
        )
        if venue_scoped:
            batch.alter_column(
                "venue_id",
                existing_type=sa.String(36),
                nullable=nullable,
            )


def upgrade() -> None:
    connection = op.get_bind()
    _validate_backfill(connection)

    with op.batch_alter_table("venues") as batch:
        batch.alter_column(
            "organization_id",
            existing_type=sa.String(36),
            nullable=False,
        )
    for table_name in ORGANIZATION_SCOPED_TABLES:
        _set_scope_nullable(table_name, venue_scoped=False, nullable=False)
    for table_name in VENUE_SCOPED_TABLES:
        _set_scope_nullable(table_name, venue_scoped=True, nullable=False)

    with op.batch_alter_table(
        "courts", naming_convention=SQLITE_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("uq_courts_code", type_="unique")
        batch.create_unique_constraint("uq_court_venue_code", ["venue_id", "code"])

    with op.batch_alter_table("receivables") as batch:
        batch.drop_constraint("uq_receivable_source", type_="unique")
        batch.create_unique_constraint(
            "uq_receivable_scope_source",
            ["venue_id", "source_type", "source_id"],
        )

    with op.batch_alter_table("coach_fees") as batch:
        batch.drop_constraint("uq_coach_fee_source", type_="unique")
        batch.create_unique_constraint(
            "uq_coach_fee_scope_source",
            ["venue_id", "source_type", "source_id", "coach_id"],
        )

    with op.batch_alter_table("class_sessions") as batch:
        batch.drop_constraint("uq_class_session_sequence", type_="unique")
        batch.create_unique_constraint(
            "uq_class_session_scope_sequence",
            ["venue_id", "fixed_class_id", "sequence_number"],
        )

    with op.batch_alter_table("attendance_records") as batch:
        batch.drop_constraint("uq_session_student_attendance", type_="unique")
        batch.create_unique_constraint(
            "uq_attendance_scope_session_student",
            ["venue_id", "class_session_id", "student_id"],
        )

    with op.batch_alter_table("schedule_allocations") as batch:
        batch.drop_constraint("uq_schedule_resource", type_="unique")
        batch.create_unique_constraint(
            "uq_schedule_scope_resource",
            ["venue_id", "schedule_entry_id", "resource_type", "resource_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("schedule_allocations") as batch:
        batch.drop_constraint("uq_schedule_scope_resource", type_="unique")
        batch.create_unique_constraint(
            "uq_schedule_resource",
            ["schedule_entry_id", "resource_type", "resource_id"],
        )
    with op.batch_alter_table("attendance_records") as batch:
        batch.drop_constraint("uq_attendance_scope_session_student", type_="unique")
        batch.create_unique_constraint(
            "uq_session_student_attendance", ["class_session_id", "student_id"]
        )
    with op.batch_alter_table("class_sessions") as batch:
        batch.drop_constraint("uq_class_session_scope_sequence", type_="unique")
        batch.create_unique_constraint(
            "uq_class_session_sequence", ["fixed_class_id", "sequence_number"]
        )
    with op.batch_alter_table("coach_fees") as batch:
        batch.drop_constraint("uq_coach_fee_scope_source", type_="unique")
        batch.create_unique_constraint(
            "uq_coach_fee_source", ["source_type", "source_id", "coach_id"]
        )
    with op.batch_alter_table("receivables") as batch:
        batch.drop_constraint("uq_receivable_scope_source", type_="unique")
        batch.create_unique_constraint("uq_receivable_source", ["source_type", "source_id"])
    with op.batch_alter_table("courts") as batch:
        batch.drop_constraint("uq_court_venue_code", type_="unique")
        batch.create_unique_constraint("uq_courts_code", ["code"])

    for table_name in reversed(VENUE_SCOPED_TABLES):
        _set_scope_nullable(table_name, venue_scoped=True, nullable=True)
    for table_name in reversed(ORGANIZATION_SCOPED_TABLES):
        _set_scope_nullable(table_name, venue_scoped=False, nullable=True)
    with op.batch_alter_table("venues") as batch:
        batch.alter_column(
            "organization_id",
            existing_type=sa.String(36),
            nullable=True,
        )
