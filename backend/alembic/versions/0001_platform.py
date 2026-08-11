"""platform base tables"""
from alembic import op
import sqlalchemy as sa

revision = "0001_platform"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("system_users", sa.Column("username", sa.String(80), nullable=False), sa.Column("display_name", sa.String(120), nullable=False), sa.Column("password_hash", sa.Text(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.UniqueConstraint("username"))
    op.create_table("user_sessions", sa.Column("user_id", sa.String(36), sa.ForeignKey("system_users.id", ondelete="CASCADE"), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("csrf_token", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("audit_logs", sa.Column("actor_user_id", sa.String(36), nullable=False), sa.Column("action_type", sa.String(80), nullable=False), sa.Column("entity_type", sa.String(80), nullable=False), sa.Column("entity_id", sa.String(36), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("before_summary", sa.JSON(), nullable=True), sa.Column("after_summary", sa.JSON(), nullable=True), sa.Column("reason", sa.Text(), nullable=True), sa.Column("request_id", sa.String(64), nullable=False), sa.Column("id", sa.String(36), primary_key=True))
    op.create_table("idempotency_records", sa.Column("scope", sa.String(100), nullable=False), sa.Column("key", sa.String(128), nullable=False), sa.Column("response", sa.JSON(), nullable=False), sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"))

def downgrade() -> None:
    for name in ["idempotency_records", "audit_logs", "user_sessions", "system_users"]: op.drop_table(name)
