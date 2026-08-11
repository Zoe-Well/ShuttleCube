"""Permanently remove legacy soft-cancelled operation records."""

from alembic import op

revision = "0009_hard_delete_cancelled"
down_revision = "0008_bookings_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM event_participants WHERE event_id IN "
        "(SELECT id FROM temporary_events WHERE status = 'cancelled')"
    )
    op.execute("DELETE FROM temporary_events WHERE status = 'cancelled'")
    op.execute("DELETE FROM venue_bookings WHERE status = 'cancelled'")
    op.execute("DELETE FROM private_lessons WHERE status = 'cancelled'")
    op.execute(
        "UPDATE schedule_entries SET original_entry_id = NULL WHERE original_entry_id IN "
        "(SELECT id FROM schedule_entries WHERE status = 'cancelled')"
    )
    # Audit records are append-only business facts. They intentionally survive
    # cleanup of the operational rows they describe.
    op.execute(
        "DELETE FROM schedule_allocations WHERE schedule_entry_id IN "
        "(SELECT id FROM schedule_entries WHERE status = 'cancelled')"
    )
    op.execute("DELETE FROM schedule_entries WHERE status = 'cancelled'")


def downgrade() -> None:
    # Physical deletion is intentionally irreversible.
    pass
