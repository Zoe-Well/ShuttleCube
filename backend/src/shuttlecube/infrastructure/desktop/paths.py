from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DesktopDataPaths:
    root: Path
    database_dir: Path
    database: Path
    attachments: Path
    backups: Path
    settings: Path
    manifest: Path
    pending_import: Path
    lock_file: Path

    @classmethod
    def from_root(cls, root: Path) -> DesktopDataPaths:
        resolved = root.expanduser().resolve()
        return cls(
            root=resolved,
            database_dir=resolved / "database",
            database=resolved / "database" / "shuttlecube.db",
            attachments=resolved / "attachments",
            backups=resolved / "backups",
            settings=resolved / "settings",
            manifest=resolved / "manifest.json",
            pending_import=resolved / "settings" / "pending-import",
            lock_file=resolved / "settings" / "desktop.lock",
        )

    def ensure(self) -> None:
        for path in (
            self.root,
            self.database_dir,
            self.attachments,
            self.backups,
            self.settings,
        ):
            path.mkdir(parents=True, exist_ok=True)


def default_desktop_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "ShuttleCube" / "Data"
    return Path.home() / ".shuttlecube" / "data"


def sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.resolve().as_posix()}"


def migrate_legacy_database(source: Path, destination: Path) -> bool:
    """Copy a legacy SQLite database using SQLite's consistent backup API."""
    if destination.exists() or not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    try:
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()
    return True
