"""finance facts and receivable backfill"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0010_finance"
down_revision = "0009_hard_delete_cancelled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receivables",
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("suggested_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("adjustment_reason", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("source_type", "source_id", name="uq_receivable_source"),
        sa.CheckConstraint("suggested_amount >= 0", name="ck_receivable_suggested_nonnegative"),
        sa.CheckConstraint("actual_amount >= 0", name="ck_receivable_actual_nonnegative"),
    )
    op.create_index("ix_receivables_source_type", "receivables", ["source_type"])
    op.create_index("ix_receivables_source_id", "receivables", ["source_id"])
    op.create_index("ix_receivables_status", "receivables", ["status"])
    op.create_table(
        "payments",
        sa.Column("receivable_id", sa.String(36), sa.ForeignKey("receivables.id"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("payer_name", sa.String(160)),
        sa.Column("received_by", sa.String(120)),
        sa.Column("operated_by", sa.String(36), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("void_reason", sa.Text()),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
    )
    op.create_index("ix_payments_receivable_id", "payments", ["receivable_id"])
    op.create_index("ix_payments_paid_at", "payments", ["paid_at"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_table(
        "refunds",
        sa.Column("receivable_id", sa.String(36), sa.ForeignKey("receivables.id"), nullable=False),
        sa.Column("payment_id", sa.String(36), sa.ForeignKey("payments.id")),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("suggested_amount", sa.Numeric(12, 2)),
        sa.Column("actual_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operated_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("void_reason", sa.Text()),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.CheckConstraint("actual_amount > 0", name="ck_refund_amount_positive"),
    )
    op.create_index("ix_refunds_receivable_id", "refunds", ["receivable_id"])
    op.create_index("ix_refunds_refunded_at", "refunds", ["refunded_at"])
    op.create_index("ix_refunds_status", "refunds", ["status"])
    op.create_table(
        "expenses",
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("spent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payee", sa.String(160), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("source_type", sa.String(40)),
        sa.Column("source_id", sa.String(36)),
        sa.Column("operated_by", sa.String(36), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("void_reason", sa.Text()),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
    )
    op.create_index("ix_expense_source", "expenses", ["source_type", "source_id"])
    op.create_index("ix_expenses_spent_at", "expenses", ["spent_at"])
    op.create_index("ix_expenses_status", "expenses", ["status"])
    op.create_table(
        "attachments",
        sa.Column("owner_type", sa.String(40), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("storage_key", sa.String(240), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(36), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("deleted_by", sa.String(36)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.String(36), primary_key=True),
    )
    op.create_index("ix_attachment_owner", "attachments", ["owner_type", "owner_id"])
    op.create_index("ix_attachments_status", "attachments", ["status"])
    _backfill_receivables()


def _backfill_receivables() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)
    sources = [
        ("enrollment", "enrollments", "suggested_receivable", "actual_receivable", None),
        ("private_package", "private_lesson_packages", "actual_receivable", "actual_receivable", None),
        ("private_lesson", "private_lessons", "actual_receivable", "actual_receivable", "billing_mode = 'single'"),
        ("venue_booking", "venue_bookings", "suggested_receivable", "actual_receivable", None),
        ("event", "temporary_events", "suggested_receivable", "actual_receivable", None),
    ]
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
    for source_type, table, suggested, actual, condition in sources:
        sql = f"SELECT id, {suggested}, {actual} FROM {table}"
        if condition:
            sql += f" WHERE {condition}"
        for source_id, suggested_amount, actual_amount in bind.execute(sa.text(sql)):
            value = actual_amount or 0
            bind.execute(
                target.insert().values(
                    source_type=source_type,
                    source_id=source_id,
                    suggested_amount=suggested_amount or value,
                    actual_amount=value,
                    adjustment_reason=None,
                    status="settled" if value == 0 else "open",
                    id=str(uuid4()),
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )


def downgrade() -> None:
    for name in ["attachments", "expenses", "refunds", "payments", "receivables"]:
        op.drop_table(name)
