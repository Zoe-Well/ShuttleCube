from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shuttlecube.infrastructure.desktop.paths import DesktopDataPaths

TRANSFER_FORMAT_VERSION = 1
APP_VERSION = "0.1.0"
SUPPORTED_SCHEMA_VERSIONS = {
    "0001_platform",
    "0002_identity_audit",
    "0003_directory",
    "0004_scheduling",
    "0005_fixed_classes",
    "0006_enrollment_ledger",
    "0007_private_lessons",
    "0008_bookings_events",
    "0009_hard_delete_cancelled",
    "0010_finance",
    "0011_payroll",
    "0012_monthly_payroll",
    "0013_coach_rates",
    "0014_fixed_class_lifecycle",
    "0015_other_income",
    "0016_backfill_missing_receivables",
    "0017_organization_venue_membership",
    "0018_scope_backfill",
    "0019_scope_constraints",
    "0020_operations_policy_settings",
    "0021_operations_runtime",
    "0022_operations_policy_names",
}


class TransferError(ValueError):
    pass


@dataclass(frozen=True)
class TransferManifest:
    format_version: int
    app_version: str
    schema_version: str
    exported_at: str
    files: dict[str, str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_version(database: Path) -> str:
    with closing(
        sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    ) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "alembic_version" not in tables:
            return "unversioned"
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        return str(row[0]) if row else "unversioned"


def _backup_database(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    try:
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()


def _sanitize_exported_database(database: Path) -> None:
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            if "user_sessions" in tables:
                connection.execute("DELETE FROM user_sessions")
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise TransferError("数据库完整性检查失败")


def _manifest_files(package: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for base in (package / "database", package / "attachments"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_symlink():
                raise TransferError("迁移文件夹不能包含符号链接")
            if path.is_file():
                files[path.relative_to(package).as_posix()] = _sha256(path)
    return files


def export_transfer(
    paths: DesktopDataPaths,
    destination_parent: Path,
    *,
    prefix: str = "ShuttleCube-Transfer",
    allow_inside_data: bool = False,
) -> Path:
    if not paths.database.is_file():
        raise TransferError("尚未找到可导出的业务数据库")
    parent = destination_parent.expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    if not allow_inside_data and (parent == paths.root or paths.root in parent.parents):
        raise TransferError("请选择 ShuttleCube 数据目录以外的位置")
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S")
    destination = parent / f"{prefix}-{timestamp}"
    suffix = 1
    while destination.exists():
        destination = parent / f"{prefix}-{timestamp}-{suffix}"
        suffix += 1
    destination.mkdir(parents=False)
    try:
        database_dir = destination / "database"
        database_dir.mkdir()
        database = database_dir / "shuttlecube.db"
        _backup_database(paths.database, database)
        _sanitize_exported_database(database)
        if paths.attachments.is_dir():
            shutil.copytree(paths.attachments, destination / "attachments")
        else:
            (destination / "attachments").mkdir()
        manifest = TransferManifest(
            format_version=TRANSFER_FORMAT_VERSION,
            app_version=APP_VERSION,
            schema_version=_schema_version(database),
            exported_at=datetime.now(UTC).isoformat(),
            files=_manifest_files(destination),
        )
        # The manifest is the completion marker and is deliberately written last.
        (destination / "manifest.json").write_text(
            json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination


def validate_transfer(package: Path) -> TransferManifest:
    source = package.expanduser().resolve()
    manifest_path = source / "manifest.json"
    database = source / "database" / "shuttlecube.db"
    if not manifest_path.is_file() or not database.is_file():
        raise TransferError("所选文件夹不是有效的 ShuttleCube 迁移文件夹")
    try:
        raw: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = TransferManifest(
            format_version=int(raw["format_version"]),
            app_version=str(raw["app_version"]),
            schema_version=str(raw["schema_version"]),
            exported_at=str(raw["exported_at"]),
            files={str(key): str(value) for key, value in dict(raw["files"]).items()},
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TransferError("迁移清单格式不正确") from exc
    if manifest.format_version > TRANSFER_FORMAT_VERSION:
        raise TransferError("该迁移文件夹由更高版本的 ShuttleCube 创建，请先升级应用")
    if manifest.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise TransferError("该迁移文件夹的数据版本不受当前应用支持")
    actual_files = _manifest_files(source)
    if actual_files != manifest.files:
        raise TransferError("迁移文件缺失、损坏或已被修改")
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    if not result or result[0] != "ok" or "system_users" not in tables:
        raise TransferError("迁移文件夹中的数据库无效")
    return manifest


def stage_import(paths: DesktopDataPaths, package: Path) -> TransferManifest:
    manifest = validate_transfer(package)
    source = package.expanduser().resolve()
    temporary = paths.settings / "pending-import.partial"
    if temporary.exists():
        shutil.rmtree(temporary)
    if paths.pending_import.exists():
        shutil.rmtree(paths.pending_import)
    temporary.mkdir(parents=True)
    try:
        shutil.copytree(source / "database", temporary / "database")
        shutil.copytree(source / "attachments", temporary / "attachments")
        shutil.copy2(source / "manifest.json", temporary / "manifest.json")
        validate_transfer(temporary)
        shutil.copytree(temporary, paths.pending_import)
        shutil.rmtree(temporary)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(paths.pending_import, ignore_errors=True)
        raise
    return manifest


def apply_pending_import(paths: DesktopDataPaths) -> bool:
    if not paths.pending_import.is_dir():
        return False
    validate_transfer(paths.pending_import)
    if paths.database.is_file():
        export_transfer(
            paths,
            paths.backups,
            prefix="Before-Import",
            allow_inside_data=True,
        )
    incoming_database = paths.pending_import / "database" / "shuttlecube.db"
    incoming_attachments = paths.pending_import / "attachments"
    replacement_database = paths.database_dir / "shuttlecube.importing.db"
    replacement_attachments = paths.root / "attachments.importing"
    shutil.copy2(incoming_database, replacement_database)
    if replacement_attachments.exists():
        shutil.rmtree(replacement_attachments)
    shutil.copytree(incoming_attachments, replacement_attachments)
    old_database = paths.database_dir / "shuttlecube.before-import.db"
    old_attachments = paths.root / "attachments.before-import"
    for old in (old_database, old_attachments):
        if old.is_dir():
            shutil.rmtree(old)
        elif old.exists():
            old.unlink()
    try:
        if paths.database.exists():
            os.replace(paths.database, old_database)
        if paths.attachments.exists():
            os.replace(paths.attachments, old_attachments)
        os.replace(replacement_database, paths.database)
        os.replace(replacement_attachments, paths.attachments)
    except Exception:
        if old_database.exists():
            if paths.database.exists():
                paths.database.unlink()
            os.replace(old_database, paths.database)
        elif paths.database.exists():
            paths.database.unlink()
        if old_attachments.exists():
            if paths.attachments.exists():
                shutil.rmtree(paths.attachments)
            os.replace(old_attachments, paths.attachments)
        elif paths.attachments.exists():
            shutil.rmtree(paths.attachments)
        raise
    else:
        if old_database.exists():
            old_database.unlink()
        if old_attachments.exists():
            shutil.rmtree(old_attachments)
        shutil.rmtree(paths.pending_import)
    return True


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
