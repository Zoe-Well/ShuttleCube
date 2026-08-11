import sqlite3
from contextlib import closing
from pathlib import Path

from alembic.config import Config

from alembic import command
from shuttlecube.infrastructure.database.migrations import run_migrations
from shuttlecube.infrastructure.desktop.paths import sqlite_url

BACKEND_ROOT = Path(__file__).parents[3]


def _upgrade_to(database: Path, revision: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["database_url"] = sqlite_url(database)
    command.upgrade(config, revision)


def test_recent_desktop_database_upgrades_to_head_without_losing_user(tmp_path: Path) -> None:
    database = tmp_path / "shuttlecube.db"
    _upgrade_to(database, "0009_hard_delete_cancelled")
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO system_users (
                    username, display_name, password_hash, is_active, id,
                    created_at, updated_at, version
                ) VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                """,
                ("owner", "升级前用户", "test-password-hash", "user-1"),
            )

    run_migrations(sqlite_url(database), BACKEND_ROOT)

    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0016_backfill_missing_receivables",
        )
        assert connection.execute(
            "SELECT display_name FROM system_users WHERE id = 'user-1'"
        ).fetchone() == ("升级前用户",)
        enrollment_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(enrollments)")
        }
        assert {
            "acquisition_type",
            "source_enrollment_id",
            "transferred_to_enrollment_id",
        } <= enrollment_columns


def test_legacy_business_records_receive_only_missing_receivables(tmp_path: Path) -> None:
    database = tmp_path / "shuttlecube.db"
    _upgrade_to(database, "0015_other_income")
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO walk_in_customers (
                    display_name, id, created_at, updated_at, version
                ) VALUES ('历史散客', 'customer-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                """
            )
            connection.execute(
                """
                INSERT INTO venue_bookings (
                    customer_id, starts_at, ends_at, court_ids_csv,
                    suggested_receivable, actual_receivable, payment_status, status,
                    id, created_at, updated_at, version
                ) VALUES (
                    'customer-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'court-1',
                    0, 40, 'unpaid', 'booked',
                    'booking-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
                )
                """
            )
            connection.execute(
                """
                INSERT INTO temporary_events (
                    event_type, name, starts_at, ends_at, court_ids_csv, coach_fee,
                    suggested_receivable, actual_receivable, expense_amount,
                    track_participants, requires_attendance, status,
                    id, created_at, updated_at, version
                ) VALUES (
                    'other', '历史免费活动', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'court-1', 0,
                    0, 0, 0, 0, 0, 'confirmed',
                    'event-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
                )
                """
            )
            connection.execute(
                """
                INSERT INTO receivables (
                    source_type, source_id, suggested_amount, actual_amount,
                    status, id, created_at, updated_at, version
                ) VALUES (
                    'event', 'existing-event', 0, 0,
                    'settled', 'receivable-existing', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
                )
                """
            )

    run_migrations(sqlite_url(database), BACKEND_ROOT)

    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            """
            SELECT source_type, source_id, suggested_amount, actual_amount, status
            FROM receivables
            ORDER BY source_type, source_id
            """
        ).fetchall()
        assert rows == [
            ("event", "event-1", 0, 0, "settled"),
            ("event", "existing-event", 0, 0, "settled"),
            ("venue_booking", "booking-1", 0, 40, "open"),
        ]
