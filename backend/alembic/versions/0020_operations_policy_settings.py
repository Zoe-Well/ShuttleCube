"""Add immutable operations policies and default-off write setting."""

import sqlalchemy as sa
from alembic import op

revision = "0020_operations_policy_settings"
down_revision = "0019_scope_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("venues") as batch:
        batch.add_column(
            sa.Column(
                "write_tools_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.create_index("ix_venues_write_tools_enabled", ["write_tools_enabled"])

    op.create_table(
        "operations_policies",
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("venue_id", sa.String(36), nullable=False),
        sa.Column("policy_key", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("activated_by", sa.String(36), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "venue_id",
            "policy_key",
            "policy_version",
            name="uq_operations_policy_version",
        ),
        sa.CheckConstraint(
            "state IN ('draft', 'active', 'retired')",
            name="ck_operations_policy_state",
        ),
    )
    op.create_index(
        "ix_operations_policies_organization_id", "operations_policies", ["organization_id"]
    )
    op.create_index("ix_operations_policies_venue_id", "operations_policies", ["venue_id"])
    op.create_index("ix_operations_policies_state", "operations_policies", ["state"])
    op.create_index(
        "uq_operations_policy_active",
        "operations_policies",
        ["venue_id", "policy_key"],
        unique=True,
        sqlite_where=sa.text("state = 'active'"),
        postgresql_where=sa.text("state = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_operations_policy_active", table_name="operations_policies")
    op.drop_index("ix_operations_policies_state", table_name="operations_policies")
    op.drop_index("ix_operations_policies_venue_id", table_name="operations_policies")
    op.drop_index("ix_operations_policies_organization_id", table_name="operations_policies")
    op.drop_table("operations_policies")
    with op.batch_alter_table("venues") as batch:
        batch.drop_index("ix_venues_write_tools_enabled")
        batch.drop_column("write_tools_enabled")
