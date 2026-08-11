"""coach fees and payroll settlements"""

import sqlalchemy as sa
from alembic import op

revision = "0011_payroll"
down_revision = "0010_finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_settlements",
        sa.Column("coach_id", sa.String(36), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("calculated_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("adjustment_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("adjustment_reason", sa.Text()),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expense_id", sa.String(36), sa.ForeignKey("expenses.id"), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_payroll_settlements_coach_id", "payroll_settlements", ["coach_id"])
    op.create_index("ix_payroll_settlements_paid_at", "payroll_settlements", ["paid_at"])
    op.create_index("ix_payroll_settlements_status", "payroll_settlements", ["status"])
    op.create_table(
        "coach_fees",
        sa.Column("coach_id", sa.String(36), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("adjustment_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("adjustment_reason", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("settlement_id", sa.String(36), sa.ForeignKey("payroll_settlements.id")),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("source_type", "source_id", "coach_id", name="uq_coach_fee_source"),
    )
    op.create_index("ix_coach_fees_coach_id", "coach_fees", ["coach_id"])
    op.create_index("ix_coach_fees_occurred_at", "coach_fees", ["occurred_at"])
    op.create_index("ix_coach_fees_status", "coach_fees", ["status"])
    op.create_index("ix_coach_fees_settlement_id", "coach_fees", ["settlement_id"])


def downgrade() -> None:
    op.drop_table("coach_fees")
    op.drop_table("payroll_settlements")
