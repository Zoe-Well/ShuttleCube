import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from shuttlecube.infrastructure.database.migrations import run_migrations
from shuttlecube.infrastructure.desktop.paths import (
    DesktopDataPaths,
    migrate_legacy_database,
    sqlite_url,
)
from shuttlecube.infrastructure.desktop.transfer import (
    SUPPORTED_SCHEMA_VERSIONS,
    TransferError,
    apply_pending_import,
    export_transfer,
    stage_import,
    validate_transfer,
)

BACKEND_ROOT = Path(__file__).parents[3]


def _database(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.executescript(
                """
            CREATE TABLE alembic_version (version_num TEXT NOT NULL);
            INSERT INTO alembic_version VALUES ('0009_hard_delete_cancelled');
            CREATE TABLE system_users (id TEXT PRIMARY KEY, display_name TEXT NOT NULL);
            CREATE TABLE user_sessions (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL);
            """
            )
            connection.execute("INSERT INTO system_users VALUES ('user-1', ?)", (value,))
            connection.execute("INSERT INTO user_sessions VALUES ('session-1', 'secret-token')")


def _display_name(database: Path) -> str:
    with closing(sqlite3.connect(database)) as connection:
        return str(connection.execute("SELECT display_name FROM system_users").fetchone()[0])


def test_legacy_database_uses_consistent_sqlite_copy(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    destination = tmp_path / "Data" / "database" / "shuttlecube.db"
    _database(source, "旧设备")

    assert migrate_legacy_database(source, destination)
    assert _display_name(destination) == "旧设备"
    assert not migrate_legacy_database(source, destination)


def test_transfer_round_trip_restores_data_and_clears_sessions(tmp_path: Path) -> None:
    paths = DesktopDataPaths.from_root(tmp_path / "Data")
    paths.ensure()
    _database(paths.database, "导出版本")
    (paths.attachments / "receipt.bin").write_bytes(b"receipt")
    package = export_transfer(paths, tmp_path / "exports")

    manifest = validate_transfer(package)
    assert manifest.schema_version == "0009_hard_delete_cancelled"
    with closing(sqlite3.connect(package / "database" / "shuttlecube.db")) as connection:
        assert connection.execute("SELECT count(*) FROM user_sessions").fetchone()[0] == 0

    with closing(sqlite3.connect(paths.database)) as connection:
        with connection:
            connection.execute("UPDATE system_users SET display_name = '当前版本'")
    stage_import(paths, package)
    assert apply_pending_import(paths)
    assert _display_name(paths.database) == "导出版本"
    assert (paths.attachments / "receipt.bin").read_bytes() == b"receipt"
    assert list(paths.backups.glob("Before-Import-*"))


def test_transfer_rejects_modified_files(tmp_path: Path) -> None:
    paths = DesktopDataPaths.from_root(tmp_path / "Data")
    paths.ensure()
    _database(paths.database, "完整版本")
    package = export_transfer(paths, tmp_path / "exports")
    (package / "database" / "shuttlecube.db").write_bytes(b"damaged")

    with pytest.raises(TransferError, match="损坏"):
        validate_transfer(package)


def test_transfer_rejects_newer_schema(tmp_path: Path) -> None:
    paths = DesktopDataPaths.from_root(tmp_path / "Data")
    paths.ensure()
    _database(paths.database, "新版本")
    package = export_transfer(paths, tmp_path / "exports")
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "9999_future"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(TransferError, match="不受当前应用支持"):
        validate_transfer(package)


def test_current_schema_transfer_round_trip_restores_data_and_clears_sessions(
    tmp_path: Path,
) -> None:
    paths = DesktopDataPaths.from_root(tmp_path / "Data")
    paths.ensure()
    run_migrations(sqlite_url(paths.database), BACKEND_ROOT)
    with closing(sqlite3.connect(paths.database)) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO system_users (
                    username, display_name, password_hash, is_active, id,
                    created_at, updated_at, version
                ) VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                """,
                ("owner", "导出版本", "test-password-hash", "user-current"),
            )
            connection.execute(
                """
                INSERT INTO user_sessions (
                    user_id, token_hash, csrf_token, expires_at, id, created_at, updated_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                ("user-current", "current-token", "current-csrf", "session-current"),
            )
    (paths.attachments / "receipt.bin").write_bytes(b"current-receipt")

    package = export_transfer(paths, tmp_path / "exports")
    manifest = validate_transfer(package)

    assert manifest.schema_version == "0022_operations_policy_names"
    with closing(sqlite3.connect(package / "database" / "shuttlecube.db")) as connection:
        assert connection.execute("SELECT count(*) FROM user_sessions").fetchone() == (0,)

    with closing(sqlite3.connect(paths.database)) as connection:
        with connection:
            connection.execute("UPDATE system_users SET display_name = '导入前版本'")
    stage_import(paths, package)
    assert apply_pending_import(paths)
    assert _display_name(paths.database) == "导出版本"
    assert (paths.attachments / "receipt.bin").read_bytes() == b"current-receipt"
    assert list(paths.backups.glob("Before-Import-*"))


def test_every_repository_migration_is_accepted_for_transfer() -> None:
    migration_versions = {
        path.stem
        for path in (BACKEND_ROOT / "alembic" / "versions").glob("[0-9][0-9][0-9][0-9]_*.py")
    }
    assert migration_versions <= SUPPORTED_SCHEMA_VERSIONS
