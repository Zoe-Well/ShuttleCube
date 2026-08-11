from pathlib import Path

from alembic.config import Config

from alembic import command


def run_migrations(database_url: str, alembic_root: Path) -> None:
    config_path = alembic_root / "alembic.ini"
    script_path = alembic_root / "alembic"
    config = Config(str(config_path) if config_path.is_file() else None)
    config.set_main_option("script_location", str(script_path))
    config.set_main_option("sqlalchemy.url", database_url)
    # Ensure env.py uses the database chosen by the desktop caller even when
    # application settings have already been cached in the current process.
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")
