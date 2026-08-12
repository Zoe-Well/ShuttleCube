from __future__ import annotations

import ctypes
import json
import os
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlparse

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import SecretStr

from shuttlecube.config import Settings


class CredentialStorageUnavailable(RuntimeError):
    pass


class CredentialValidationFailed(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return (
        _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))),
        buffer,
    )


def protect_for_current_windows_user(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStorageUnavailable("Windows credential encryption is unavailable")
    source, source_buffer = _blob(data)
    protected = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        "ShuttleCube OpenAI API Key",
        None,
        None,
        None,
        0x01,
        ctypes.byref(protected),
    ):
        raise CredentialStorageUnavailable("Unable to encrypt credential")
    del source_buffer
    try:
        return ctypes.string_at(protected.pbData, protected.cbData)
    finally:
        kernel32.LocalFree(protected.pbData)


def unprotect_for_current_windows_user(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStorageUnavailable("Windows credential encryption is unavailable")
    source, source_buffer = _blob(data)
    clear = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x01, ctypes.byref(clear)
    ):
        raise CredentialStorageUnavailable("Unable to decrypt credential")
    del source_buffer
    try:
        return ctypes.string_at(clear.pbData, clear.cbData)
    finally:
        kernel32.LocalFree(clear.pbData)


@dataclass(frozen=True)
class CredentialMetadata:
    verified_at: datetime
    provider: Literal["openai", "deepseek", "custom"]
    base_url: str
    api_mode: Literal["responses", "chat_completions"]
    model_profile: str


@dataclass(frozen=True)
class ModelProviderConfiguration:
    api_key: SecretStr
    provider: Literal["openai", "deepseek", "custom"]
    base_url: str
    api_mode: Literal["responses", "chat_completions"]
    model_profile: str


PROVIDER_DEFAULTS: dict[str, tuple[str, str, str]] = {
    "openai": ("https://api.openai.com/v1", "responses", "gpt-5.6"),
    "deepseek": ("https://api.deepseek.com", "chat_completions", "deepseek-chat"),
}


def normalize_provider_configuration(
    *, provider: str, base_url: str, api_mode: str, model_profile: str
) -> tuple[
    Literal["openai", "deepseek", "custom"],
    str,
    Literal["responses", "chat_completions"],
    str,
]:
    if provider not in {"openai", "deepseek", "custom"}:
        raise ValueError("不支持的 AI 服务商")
    defaults = PROVIDER_DEFAULTS.get(provider)
    if defaults is not None:
        base_url, api_mode, default_model = defaults
        model_profile = model_profile.strip() or default_model
    normalized_url = base_url.strip().rstrip("/")
    parsed = urlparse(normalized_url)
    is_local_http = parsed.scheme == "http" and parsed.hostname in {
        "localhost", "127.0.0.1", "::1"
    }
    if parsed.scheme != "https" and not is_local_http:
        raise ValueError("AI 服务地址必须使用 HTTPS；本机地址可使用 HTTP")
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("AI 服务地址格式不正确")
    if api_mode not in {"responses", "chat_completions"}:
        raise ValueError("不支持的 API 协议")
    normalized_model = model_profile.strip()
    if not normalized_model or len(normalized_model) > 120:
        raise ValueError("模型名称不能为空且不能超过 120 个字符")
    return (
        cast(Literal["openai", "deepseek", "custom"], provider),
        normalized_url,
        cast(Literal["responses", "chat_completions"], api_mode),
        normalized_model,
    )


class DesktopOpenAICredentialStore:
    def __init__(
        self,
        settings: Settings,
        *,
        protect: Callable[[bytes], bytes] = protect_for_current_windows_user,
        unprotect: Callable[[bytes], bytes] = unprotect_for_current_windows_user,
    ) -> None:
        if not settings.desktop_mode or settings.data_dir is None:
            raise CredentialStorageUnavailable("Credential editing is desktop-only")
        directory = Path(settings.data_dir) / "settings"
        self._secret_path = directory / "openai-api-key.dpapi"
        self._metadata_path = directory / "openai-api-key.json"
        self._protect = protect
        self._unprotect = unprotect

    def exists(self) -> bool:
        return self._secret_path.is_file()

    def read(self) -> SecretStr | None:
        if not self.exists():
            return None
        clear = self._unprotect(self._secret_path.read_bytes()).decode("utf-8")
        return SecretStr(clear)

    def metadata(self) -> CredentialMetadata | None:
        if not self._metadata_path.is_file():
            return None
        try:
            value = json.loads(self._metadata_path.read_text(encoding="utf-8"))
            provider = str(value.get("provider", "openai"))
            api_mode = str(value.get("api_mode", "responses"))
            if provider not in {"openai", "deepseek", "custom"}:
                return None
            if api_mode not in {"responses", "chat_completions"}:
                return None
            return CredentialMetadata(
                verified_at=datetime.fromisoformat(str(value["verified_at"])),
                provider=cast(Literal["openai", "deepseek", "custom"], provider),
                base_url=str(value.get("base_url", PROVIDER_DEFAULTS["openai"][0])),
                api_mode=cast(Literal["responses", "chat_completions"], api_mode),
                model_profile=str(value["model_profile"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def save(
        self,
        api_key: SecretStr,
        *,
        model_profile: str,
        verified_at: datetime,
        provider: Literal["openai", "deepseek", "custom"] = "openai",
        base_url: str = "https://api.openai.com/v1",
        api_mode: Literal["responses", "chat_completions"] = "responses",
    ) -> None:
        self._secret_path.parent.mkdir(parents=True, exist_ok=True)
        protected = self._protect(api_key.get_secret_value().encode("utf-8"))
        secret_temp = self._secret_path.with_name(f"{self._secret_path.name}.tmp")
        metadata_temp = self._metadata_path.with_name(f"{self._metadata_path.name}.tmp")
        secret_temp.write_bytes(protected)
        metadata_temp.write_text(
            json.dumps(
                {
                    "verified_at": verified_at.astimezone(UTC).isoformat(),
                    "provider": provider,
                    "base_url": base_url,
                    "api_mode": api_mode,
                    "model_profile": model_profile,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        secret_temp.replace(self._secret_path)
        metadata_temp.replace(self._metadata_path)

    def delete(self) -> None:
        for path in (self._secret_path, self._metadata_path):
            path.unlink(missing_ok=True)


def credential_store(settings: Settings) -> DesktopOpenAICredentialStore | None:
    if not settings.desktop_mode or settings.data_dir is None:
        return None
    return DesktopOpenAICredentialStore(settings)


def resolve_openai_api_key(settings: Settings) -> SecretStr | None:
    store = credential_store(settings)
    if store is not None:
        saved = store.read()
        if saved is not None:
            return saved
    return settings.openai_api_key


def resolve_model_provider(settings: Settings) -> ModelProviderConfiguration | None:
    api_key = resolve_openai_api_key(settings)
    if api_key is None:
        return None
    store = credential_store(settings)
    metadata = store.metadata() if store is not None and store.exists() else None
    if metadata is not None:
        return ModelProviderConfiguration(
            api_key=api_key,
            provider=metadata.provider,
            base_url=metadata.base_url,
            api_mode=metadata.api_mode,
            model_profile=metadata.model_profile,
        )
    defaults = PROVIDER_DEFAULTS.get(settings.operations_model_provider)
    base_url = settings.operations_model_base_url or (defaults[0] if defaults else "")
    api_mode = defaults[1] if defaults else settings.operations_model_api_mode
    provider, base_url, api_mode, model_profile = normalize_provider_configuration(
        provider=settings.operations_model_provider,
        base_url=base_url,
        api_mode=api_mode,
        model_profile=settings.operations_model_profile,
    )
    return ModelProviderConfiguration(
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        api_mode=api_mode,
        model_profile=model_profile,
    )


def configured_model_profile(settings: Settings) -> str:
    configuration = resolve_model_provider(settings)
    return configuration.model_profile if configuration else settings.operations_model_profile


def validate_model_provider(
    configuration: ModelProviderConfiguration, settings: Settings
) -> datetime:
    try:
        client = OpenAI(
            api_key=configuration.api_key.get_secret_value(),
            base_url=configuration.base_url,
            timeout=min(settings.operations_model_timeout_seconds, 20),
            max_retries=0,
        )
        models = client.models.list()
        model_ids = {str(item.id) for item in models.data}
        if model_ids and configuration.model_profile not in model_ids:
            raise CredentialValidationFailed(
                "model_not_available",
                f"当前 API Key 无法使用模型 {configuration.model_profile}",
            )
    except CredentialValidationFailed:
        raise
    except AuthenticationError as exc:
        raise CredentialValidationFailed("invalid_api_key", "API Key 无效，请重新检查") from exc
    except PermissionDeniedError as exc:
        raise CredentialValidationFailed(
            "model_access_denied", "API Key 无权使用当前 AI 模型"
        ) from exc
    except NotFoundError as exc:
        raise CredentialValidationFailed(
            "model_not_available", "当前账号无法使用配置的 AI 模型"
        ) from exc
    except (APIConnectionError, APITimeoutError) as exc:
        raise CredentialValidationFailed(
            "provider_unreachable", "暂时无法连接 AI 服务，请检查网络后重试"
        ) from exc
    except RateLimitError as exc:
        raise CredentialValidationFailed(
            "provider_rate_limited", "AI 服务当前请求过多，请稍后重试"
        ) from exc
    except Exception as exc:
        raise CredentialValidationFailed(
            "credential_validation_failed", "API Key 验证失败，请稍后重试"
        ) from exc
    return datetime.now(UTC)


def validate_openai_api_key(api_key: SecretStr, settings: Settings) -> datetime:
    return validate_model_provider(
        ModelProviderConfiguration(
            api_key=api_key,
            provider="openai",
            base_url=PROVIDER_DEFAULTS["openai"][0],
            api_mode="responses",
            model_profile=settings.operations_model_profile,
        ),
        settings,
    )
