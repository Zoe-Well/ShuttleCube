import os
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from shuttlecube.config import Settings
from shuttlecube.infrastructure.ai.credentials import (
    DesktopOpenAICredentialStore,
    normalize_provider_configuration,
    protect_for_current_windows_user,
    unprotect_for_current_windows_user,
)


def test_desktop_credential_store_round_trips_without_plaintext_file(tmp_path) -> None:
    settings = Settings(desktop_mode=True, data_dir=tmp_path)
    store = DesktopOpenAICredentialStore(
        settings,
        protect=lambda value: b"encrypted:" + value[::-1],
        unprotect=lambda value: value.removeprefix(b"encrypted:")[::-1],
    )
    verified_at = datetime(2026, 8, 11, 8, 30, tzinfo=UTC)

    store.save(
        SecretStr("sk-test-not-a-real-credential"),
        provider="deepseek",
        base_url="https://api.deepseek.com",
        api_mode="chat_completions",
        model_profile="deepseek-chat",
        verified_at=verified_at,
    )

    saved = store.read()
    metadata = store.metadata()
    assert saved is not None
    assert saved.get_secret_value() == "sk-test-not-a-real-credential"
    assert b"sk-test" not in (tmp_path / "settings" / "openai-api-key.dpapi").read_bytes()
    assert metadata is not None
    assert metadata.verified_at == verified_at
    assert metadata.provider == "deepseek"
    assert metadata.base_url == "https://api.deepseek.com"
    assert metadata.api_mode == "chat_completions"
    assert metadata.model_profile == "deepseek-chat"

    store.delete()
    assert store.read() is None
    assert store.metadata() is None


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is desktop-only")
def test_windows_user_encryption_round_trip() -> None:
    clear = b"sk-test-dpapi-round-trip"
    protected = protect_for_current_windows_user(clear)

    assert protected != clear
    assert unprotect_for_current_windows_user(protected) == clear


def test_official_deepseek_configuration_uses_safe_preset() -> None:
    provider, base_url, api_mode, model = normalize_provider_configuration(
        provider="deepseek",
        base_url="https://untrusted.example",
        api_mode="responses",
        model_profile="deepseek-chat",
    )

    assert provider == "deepseek"
    assert base_url == "https://api.deepseek.com"
    assert api_mode == "chat_completions"
    assert model == "deepseek-chat"


def test_custom_provider_rejects_insecure_remote_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        normalize_provider_configuration(
            provider="custom",
            base_url="http://models.example.com/v1",
            api_mode="chat_completions",
            model_profile="custom-model",
        )
