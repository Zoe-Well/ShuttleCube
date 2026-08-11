"""add effective-dated coach rate standards

Revision ID: 0013_coach_rates
Revises: 0012_monthly_payroll
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_coach_rates"
down_revision: str | None = "0012_monthly_payroll"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("coach_rates"):
        expected_columns = {
            "coach_id",
            "business_type",
            "amount",
            "effective_from",
            "effective_to",
            "id",
            "created_at",
            "updated_at",
            "version",
        }
        actual_columns = {column["name"] for column in inspector.get_columns("coach_rates")}
        if actual_columns != expected_columns:
            raise RuntimeError(
                "coach_rates exists but does not match migration 0013; manual repair required"
            )
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("coach_rates") if index["name"]
        }
        for name, columns in (
            ("ix_coach_rates_coach_id", ["coach_id"]),
            ("ix_coach_rates_business_type", ["business_type"]),
            ("ix_coach_rates_effective_from", ["effective_from"]),
        ):
            if name not in existing_indexes:
                op.create_index(name, "coach_rates", columns)
        return
    op.create_table(
        "coach_rates",
        sa.Column("coach_id", sa.String(36), sa.ForeignKey("coach_profiles.id"), nullable=False),
        sa.Column("business_type", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "coach_id", "business_type", "effective_from", name="uq_coach_rate_effective"
        ),
    )
    op.create_index("ix_coach_rates_coach_id", "coach_rates", ["coach_id"])
    op.create_index("ix_coach_rates_business_type", "coach_rates", ["business_type"])
    op.create_index("ix_coach_rates_effective_from", "coach_rates", ["effective_from"])


def downgrade() -> None:
    op.drop_table("coach_rates")
