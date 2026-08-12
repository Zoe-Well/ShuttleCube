import sqlite3
from contextlib import closing
from pathlib import Path

from alembic.config import Config

from alembic import command
from shuttlecube.infrastructure.desktop.paths import sqlite_url

BACKEND_ROOT = Path(__file__).parents[3]
ORGANIZATION_SCOPED_TABLES = {
    "students",
    "guardians",
    "student_guardians",
    "walk_in_customers",
    "coach_profiles",
    "coach_rates",
    "attachments",
}
VENUE_SCOPED_TABLES = {
    "fixed_classes",
    "class_sessions",
    "enrollments",
    "attendance_records",
    "lesson_unit_ledgers",
    "makeup_records",
    "private_lesson_packages",
    "private_lessons",
    "venue_bookings",
    "venue_price_rules",
    "temporary_events",
    "event_participants",
    "receivables",
    "payments",
    "refunds",
    "expenses",
    "other_incomes",
    "coach_fees",
    "payroll_settlements",
    "schedule_entries",
    "schedule_allocations",
    "court_blocks",
    "audit_logs",
}


def _config(database: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["database_url"] = sqlite_url(database)
    return config


def _columns(connection: sqlite3.Connection, table: str) -> dict[str, tuple[object, ...]]:
    return {row[1]: row for row in connection.execute(f'PRAGMA table_info("{table}")')}


def test_existing_single_venue_data_is_backfilled_without_row_loss(tmp_path: Path) -> None:
    database = tmp_path / "scope.db"
    config = _config(database)
    command.upgrade(config, "0016_backfill_missing_receivables")

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            """
            INSERT INTO venues (
                id, name, timezone, weekday_open_time, weekday_close_time,
                weekend_open_time, weekend_close_time, created_at, updated_at, version
            ) VALUES (
                'venue-1', 'Legacy venue', 'Asia/Shanghai', '14:00', '22:00',
                '08:00', '22:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
            )
            """
        )
        connection.execute(
            """
            INSERT INTO courts (
                id, venue_id, code, name, is_active, created_at, updated_at, version
            ) VALUES (
                'court-1', 'venue-1', '1', 'Court 1', 1,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
            )
            """
        )
        connection.execute(
            """
            INSERT INTO students (
                id, name, is_active, created_at, updated_at, version
            ) VALUES (
                'student-1', 'Legacy student', 1,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
            )
            """
        )
        connection.execute(
            """
            INSERT INTO system_users (
                id, username, display_name, password_hash, is_active,
                created_at, updated_at, version
            ) VALUES (
                'user-1', 'legacy-owner', 'Legacy owner', 'hash', 1,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
            )
            """
        )
        before = {
            table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in ("venues", "courts", "students", "system_users")
        }

    command.upgrade(config, "0019_scope_constraints")

    with closing(sqlite3.connect(database)) as connection:
        after = {
            table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in before
        }
        assert after == before
        organization_id = connection.execute(
            "SELECT organization_id FROM venues WHERE id = 'venue-1'"
        ).fetchone()[0]
        assert organization_id
        assert connection.execute(
            "SELECT organization_id FROM students WHERE id = 'student-1'"
        ).fetchone() == (organization_id,)
        assert connection.execute(
            "SELECT count(*) FROM organization_memberships WHERE status = 'pending_review'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM venue_memberships WHERE status = 'pending_review'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM migration_issues").fetchone() == (0,)


def test_all_scoped_tables_are_non_null_after_backfill_and_scope_downgrades_cleanly(
    tmp_path: Path,
) -> None:
    database = tmp_path / "scope-schema.db"
    config = _config(database)
    command.upgrade(config, "0019_scope_constraints")

    with closing(sqlite3.connect(database)) as connection:
        existing_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert ORGANIZATION_SCOPED_TABLES | VENUE_SCOPED_TABLES <= existing_tables
        for table in ORGANIZATION_SCOPED_TABLES:
            columns = _columns(connection, table)
            assert columns["organization_id"][3] == 1, table
            assert "venue_id" not in columns, table
        for table in VENUE_SCOPED_TABLES:
            columns = _columns(connection, table)
            assert columns["organization_id"][3] == 1, table
            assert columns["venue_id"][3] == 1, table

    command.downgrade(config, "0016_backfill_missing_receivables")

    with closing(sqlite3.connect(database)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "organizations" not in tables
        assert "organization_memberships" not in tables
        assert "venue_memberships" not in tables
        assert "migration_issues" not in tables
        assert "organization_id" not in _columns(connection, "students")
        assert "venue_id" not in _columns(connection, "students")
