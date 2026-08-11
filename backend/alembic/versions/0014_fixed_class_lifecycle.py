"""fixed class lifecycle and entitlement transfers

Revision ID: 0014_fixed_class_lifecycle
Revises: 0013_coach_rates
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_fixed_class_lifecycle"
down_revision: str | None = "0013_coach_rates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "class_sessions", sa.Column("replacement_decision", sa.String(length=30), nullable=True)
    )
    with op.batch_alter_table("enrollments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "acquisition_type",
                sa.String(length=30),
                nullable=False,
                server_default="purchase",
            )
        )
        batch_op.add_column(
            sa.Column("source_enrollment_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("transferred_to_enrollment_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_enrollment_source_enrollment",
            "enrollments",
            ["source_enrollment_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_enrollment_transferred_to",
            "enrollments",
            ["transferred_to_enrollment_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("enrollments") as batch_op:
        batch_op.drop_constraint("fk_enrollment_transferred_to", type_="foreignkey")
        batch_op.drop_constraint("fk_enrollment_source_enrollment", type_="foreignkey")
        batch_op.drop_column("transferred_to_enrollment_id")
        batch_op.drop_column("source_enrollment_id")
        batch_op.drop_column("acquisition_type")
    op.drop_column("class_sessions", "replacement_decision")
