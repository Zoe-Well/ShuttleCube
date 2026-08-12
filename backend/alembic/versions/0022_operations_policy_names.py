"""Add user-facing names to operations policy versions."""

import sqlalchemy as sa

from alembic import op

revision = "0022_operations_policy_names"
down_revision = "0021_operations_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operations_policies",
        sa.Column("name", sa.String(length=80), nullable=True),
    )
    policy = sa.table(
        "operations_policies",
        sa.column("id", sa.String(length=36)),
        sa.column("policy_version", sa.Integer()),
        sa.column("name", sa.String(length=80)),
    )
    connection = op.get_bind()
    for policy_id, policy_version in connection.execute(
        sa.select(policy.c.id, policy.c.policy_version)
    ):
        connection.execute(
            policy.update()
            .where(policy.c.id == policy_id)
            .values(name=f"运营规则 v{policy_version}")
        )
    with op.batch_alter_table("operations_policies") as batch:
        batch.alter_column("name", existing_type=sa.String(length=80), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("operations_policies") as batch:
        batch.drop_column("name")
