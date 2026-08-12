from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "shuttlecube.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHUTTLECUBE_", env_file=".env", extra="ignore")

    app_name: str = "ShuttleCube"
    environment: str = "development"
    database_url: str = f"sqlite+pysqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    secret_key: str = Field(default="development-only-change-me", min_length=16)
    timezone: str = "Asia/Shanghai"
    session_cookie: str = "shuttlecube_session"
    session_ttl_hours: int = 12
    secure_cookies: bool = False
    desktop_mode: bool = False
    data_dir: Path | None = None
    static_dir: Path | None = None
    artifact_storage: Literal["s3", "local"] = "s3"
    local_artifact_dir: Path | None = None
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "shuttlecube"
    s3_access_key: str = "shuttlecube"
    s3_secret_key: str = "shuttlecube-local-secret"
    openai_api_key: SecretStr | None = None
    operations_model_provider: Literal["openai", "deepseek", "custom"] = "openai"
    operations_model_base_url: str | None = None
    operations_model_api_mode: Literal["responses", "chat_completions"] = "responses"
    operations_model_profile: str = "gpt-5.6"
    operations_model_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    operations_model_max_retries: int = Field(default=2, ge=0, le=5)
    operations_runner_enabled: bool = True
    operations_runner_poll_seconds: float = Field(default=1.0, gt=0, le=60)
    operations_runner_lease_seconds: int = Field(default=60, ge=10, le=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
