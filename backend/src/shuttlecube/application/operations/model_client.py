from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.domain.scheduling.court import Venue


class ModelUnavailable(RuntimeError):
    pass


class ModelDisabled(ModelUnavailable):
    pass


class ModelOutputInvalid(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelRequest:
    workflow_key: str
    prompt_version: int
    system_instruction: str
    input_data: Mapping[str, object]
    output_schema: type[BaseModel]
    model_profile: str
    tools: Sequence[Mapping[str, object]] = field(default_factory=tuple)


@dataclass(frozen=True)
class ModelResponse:
    output: BaseModel
    usage: dict[str, int]
    provider_metadata: dict[str, object]


class ModelClient(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse: ...


class DisabledModelClient:
    def __init__(self, reason: str = "model use is disabled for this venue") -> None:
        self.reason = reason

    def generate(self, request: ModelRequest | Mapping[str, object]) -> ModelResponse:
        del request
        raise ModelDisabled(self.reason)


class StubModelClient:
    def __init__(self, outputs: Sequence[Mapping[str, object] | BaseModel] = ()) -> None:
        self._outputs = deque(outputs)
        self.requests: list[ModelRequest] = []

    def queue(self, output: Mapping[str, object] | BaseModel) -> None:
        self._outputs.append(output)

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._outputs:
            raise ModelUnavailable("stub has no queued response")
        raw = self._outputs.popleft()
        try:
            output = (
                raw
                if isinstance(raw, request.output_schema)
                else request.output_schema.model_validate(raw)
            )
        except Exception as exc:
            raise ModelOutputInvalid("stub response failed the output schema") from exc
        return ModelResponse(
            output=output,
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
            },
            provider_metadata={"provider": "stub"},
        )


class VenueModelClient:
    """Enforces the per-Venue opt-in immediately before every provider call."""

    def __init__(self, db: Session, scope: RequestScope, provider: ModelClient) -> None:
        self._db = db
        self._scope = scope
        self._provider = provider

    def generate(self, request: ModelRequest) -> ModelResponse:
        enabled = self._db.scalar(
            select(Venue.model_enabled).where(
                Venue.id == self._scope.venue_id,
                Venue.organization_id == self._scope.organization_id,
            )
        )
        if enabled is not True:
            raise ModelDisabled("model use is disabled for this venue")
        return self._provider.generate(request)


def model_client_for_venue(
    *,
    venue: Venue,
    provider_configured: bool,
    enabled_client: ModelClient,
) -> ModelClient:
    if venue.model_enabled is not True:
        return DisabledModelClient()
    if not provider_configured:
        return DisabledModelClient("model provider credentials are not configured")
    return enabled_client
