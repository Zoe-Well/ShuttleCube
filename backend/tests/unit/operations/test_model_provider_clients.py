import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import BaseModel, SecretStr

from shuttlecube.application.operations.model_client import ModelOutputInvalid, ModelRequest
from shuttlecube.config import Settings
from shuttlecube.infrastructure.ai.credentials import ModelProviderConfiguration
from shuttlecube.infrastructure.ai.openai_client import (
    OpenAIChatCompletionsClient,
    OpenAIResponsesClient,
)


class ExampleOutput(BaseModel):
    summary: str


def _request() -> ModelRequest:
    return ModelRequest(
        workflow_key="test.workflow",
        prompt_version=1,
        system_instruction="Summarize the evidence.",
        input_data={"case": "example"},
        output_schema=ExampleOutput,
        model_profile="test-model",
    )


class _ResponsesEndpoint:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    def parse(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            id="response-1",
            model="test-model",
            status="completed",
            output_parsed=ExampleOutput(summary="responses result"),
            usage=None,
        )


class _ChatEndpoint:
    def __init__(self, content: str) -> None:
        self.content = content
        self.kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            id="chat-1",
            model="deepseek-chat",
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4),
        )


def test_responses_provider_uses_responses_parse() -> None:
    endpoint = _ResponsesEndpoint()
    fake_client = SimpleNamespace(responses=endpoint)
    client = OpenAIResponsesClient(Settings(), client=cast(Any, fake_client))

    result = client.generate(_request())

    assert result.output == ExampleOutput(summary="responses result")
    assert result.provider_metadata["provider"] == "openai"
    assert endpoint.kwargs is not None
    assert endpoint.kwargs["model"] == "test-model"
    assert endpoint.kwargs["text_format"] is ExampleOutput


def test_deepseek_provider_uses_chat_completions_and_validates_json() -> None:
    endpoint = _ChatEndpoint(json.dumps({"summary": "deepseek result"}))
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=endpoint))
    configuration = ModelProviderConfiguration(
        api_key=SecretStr("sk-test-key"),
        provider="deepseek",
        base_url="https://api.deepseek.com",
        api_mode="chat_completions",
        model_profile="deepseek-chat",
    )
    client = OpenAIChatCompletionsClient(
        Settings(), configuration=configuration, client=cast(Any, fake_client)
    )

    result = client.generate(_request())

    assert result.output == ExampleOutput(summary="deepseek result")
    assert result.provider_metadata["provider"] == "deepseek"
    assert endpoint.kwargs is not None
    assert endpoint.kwargs["response_format"] == {"type": "json_object"}
    assert endpoint.kwargs["messages"][1]["content"] == '{"case":"example"}'


def test_chat_completions_rejects_invalid_json() -> None:
    endpoint = _ChatEndpoint("not-json")
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=endpoint))
    configuration = ModelProviderConfiguration(
        api_key=SecretStr("sk-test-key"),
        provider="deepseek",
        base_url="https://api.deepseek.com",
        api_mode="chat_completions",
        model_profile="deepseek-chat",
    )
    client = OpenAIChatCompletionsClient(
        Settings(), configuration=configuration, client=cast(Any, fake_client)
    )

    with pytest.raises(ModelOutputInvalid):
        client.generate(_request())
