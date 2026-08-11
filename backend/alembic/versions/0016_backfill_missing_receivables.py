"""backfill receivables missing from legacy business records"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0016_backfill_missing_receivables"
down_revision = "0015_other_income"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)
    target = sa.table(
        "receivables",
        sa.column("source_type"),
        sa.column("source_id"),
        sa.column("suggested_amount"),
        sa.column("actual_amount"),
        sa.column("adjustment_reason"),
        sa.column("status"),
        sa.column("id"),
        sa.column("created_at"),
        sa.column("updated_at"),
        sa.column("version"),
    )
    sources = [
        ("enrollment", "enrollments", "suggested_receivable", "actual_receivable", None),
        (
            "private_package",
            "private_lesson_packages",
            "actual_receivable",
            "actual_receivable",
            None,
        ),
        (
            "private_lesson",
            "private_lessons",
            "actual_receivable",
            "actual_receivable",
            "billing_mode = 'single'",
        ),
        (
            "venue_booking",
            "venue_bookings",
            "suggested_receivable",
            "actual_receivable",
            None,
        ),
        ("event", "temporary_events", "suggested_receivable", "actual_receivable", None),
    ]
    for source_type, table_name, suggested_column, actual_column, condition in sources:
        statement = (
            f"SELECT source.id, source.{suggested_column}, source.{actual_column} "
            f"FROM {table_name} AS source "
            "LEFT JOIN receivables AS receivable "
            "ON receivable.source_type = :source_type "
            "AND receivable.source_id = source.id "
            "WHERE receivable.id IS NULL"
        )
        if condition:
            statement += f" AND {condition}"
        for source_id, suggested_amount, actual_amount in bind.execute(
            sa.text(statement), {"source_type": source_type}
        ):
            actual_value = actual_amount or 0
            bind.execute(
                target.insert().values(
                    source_type=source_type,
                    source_id=source_id,
                    suggested_amount=(
                        suggested_amount if suggested_amount is not None else actual_value
                    ),
                    actual_amount=actual_value,
                    adjustment_reason=None,
                    status="settled" if actual_value == 0 else "open",
                    id=str(uuid4()),
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )


def downgrade() -> None:
    # The inserted rows are valid business facts and cannot be safely distinguished
    # from receivables subsequently used by payments, so downgrade preserves them.
    pass
