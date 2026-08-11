"""other cash income"""

import sqlalchemy as sa
from alembic import op

revision = "0015_other_income"
down_revision = "0014_fixed_class_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "other_incomes" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "other_incomes",
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payer", sa.String(160), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("operated_by", sa.String(36), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="effective"),
        sa.Column("void_reason", sa.Text()),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_other_incomes_category", "other_incomes", ["category"])
    op.create_index("ix_other_incomes_received_at", "other_incomes", ["received_at"])
    op.create_index("ix_other_incomes_status", "other_incomes", ["status"])
    op.create_index("ix_other_incomes_operated_by", "other_incomes", ["operated_by"])


def downgrade() -> None:
    op.drop_table("other_incomes")
