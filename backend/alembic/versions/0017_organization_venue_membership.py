"""Add Organization ownership and review-gated memberships."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0017_organization_venue_membership"
down_revision = "0016_backfill_missing_receivables"
branch_labels = None
depends_on = None

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def _stable_id(kind: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, ":".join(("shuttlecube", kind, *parts))))


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_organization_status"),
    )
    op.create_index("ix_organizations_status", "organizations", ["status"])

    with op.batch_alter_table("venues") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column(
                "active_for_operations", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(
            sa.Column("model_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("model_enabled_by", sa.String(36), nullable=True))
        batch.add_column(sa.Column("model_enabled_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_venues_organization_id", ["organization_id"])
        batch.create_index("ix_venues_active_for_operations", ["active_for_operations"])
        batch.create_index("ix_venues_model_enabled", ["model_enabled"])
        batch.create_foreign_key(
            "fk_venues_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "organization_memberships",
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_review"),
        sa.Column("organization_role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["system_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["system_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_membership_user"
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'active', 'disabled')",
            name="ck_organization_membership_status",
        ),
        sa.CheckConstraint(
            "organization_role IN ('owner', 'admin', 'member')",
            name="ck_organization_membership_role",
        ),
    )
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_memberships_user_id", "organization_memberships", ["user_id"]
    )
    op.create_index(
        "ix_organization_memberships_status", "organization_memberships", ["status"]
    )

    op.create_table(
        "venue_memberships",
        sa.Column("organization_membership_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("venue_id", sa.String(36), nullable=False),
        sa.Column("role_key", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_review"),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["organization_membership_id"],
            ["organization_memberships.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "organization_membership_id", "venue_id", name="uq_venue_membership_member"
        ),
        sa.CheckConstraint(
            "role_key IN ('owner', 'operations_manager', 'operator', 'finance_viewer')",
            name="ck_venue_membership_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'active', 'disabled')",
            name="ck_venue_membership_status",
        ),
    )
    for column in ("organization_membership_id", "organization_id", "venue_id", "status"):
        op.create_index(f"ix_venue_memberships_{column}", "venue_memberships", [column])

    connection = op.get_bind()
    now = datetime.now(UTC)
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
        sa.column("version", sa.Integer),
    )
    connection.execute(
        organizations.insert().values(
            id=DEFAULT_ORGANIZATION_ID,
            name="ShuttleCube",
            status="active",
            created_at=now,
            updated_at=now,
            version=1,
        )
    )
    connection.execute(
        sa.text("UPDATE venues SET organization_id = :organization_id"),
        {"organization_id": DEFAULT_ORGANIZATION_ID},
    )

    users = list(connection.execute(sa.text("SELECT id FROM system_users ORDER BY id")))
    venues = list(connection.execute(sa.text("SELECT id FROM venues ORDER BY id")))
    for (user_id,) in users:
        organization_membership_id = _stable_id(
            "organization-membership", DEFAULT_ORGANIZATION_ID, user_id
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO organization_memberships (
                    id, organization_id, user_id, status, organization_role,
                    created_at, updated_at, version
                ) VALUES (
                    :id, :organization_id, :user_id, 'pending_review', 'member',
                    :created_at, :updated_at, 1
                )
                """
            ),
            {
                "id": organization_membership_id,
                "organization_id": DEFAULT_ORGANIZATION_ID,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        for (venue_id,) in venues:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO venue_memberships (
                        id, organization_membership_id, organization_id, venue_id,
                        role_key, status, created_at, updated_at, version
                    ) VALUES (
                        :id, :organization_membership_id, :organization_id, :venue_id,
                        'operator', 'pending_review', :created_at, :updated_at, 1
                    )
                    """
                ),
                {
                    "id": _stable_id("venue-membership", organization_membership_id, venue_id),
                    "organization_membership_id": organization_membership_id,
                    "organization_id": DEFAULT_ORGANIZATION_ID,
                    "venue_id": venue_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )


def downgrade() -> None:
    op.drop_table("venue_memberships")
    op.drop_table("organization_memberships")
    with op.batch_alter_table("venues") as batch:
        batch.drop_constraint("fk_venues_organization_id", type_="foreignkey")
        batch.drop_index("ix_venues_model_enabled")
        batch.drop_index("ix_venues_active_for_operations")
        batch.drop_index("ix_venues_organization_id")
        batch.drop_column("model_enabled_at")
        batch.drop_column("model_enabled_by")
        batch.drop_column("model_enabled")
        batch.drop_column("active_for_operations")
        batch.drop_column("organization_id")
    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_table("organizations")
