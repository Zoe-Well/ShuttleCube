"""enforce one confirmed payroll settlement per coach month

Revision ID: 0012_monthly_payroll
Revises: 0011_payroll
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_monthly_payroll"
down_revision: str | None = "0011_payroll"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_payroll_confirmed_coach_month",
        "payroll_settlements",
        ["coach_id", "period_start"],
        unique=True,
        sqlite_where=sa.text("status = 'confirmed'"),
        postgresql_where=sa.text("status = 'confirmed'"),
    )


def downgrade() -> None:
    op.drop_index("uq_payroll_confirmed_coach_month", table_name="payroll_settlements")
