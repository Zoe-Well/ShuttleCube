from shuttlecube.config import DEFAULT_DATABASE_PATH, Settings


def test_current_settings_have_no_agent_runtime() -> None:
    assert "redis" not in Settings.model_fields
    assert "model_api_key" not in Settings.model_fields
    assert "agent" not in Settings.model_fields


def test_default_database_path_does_not_depend_on_working_directory() -> None:
    assert DEFAULT_DATABASE_PATH.as_posix().endswith("/backend/shuttlecube.db")
