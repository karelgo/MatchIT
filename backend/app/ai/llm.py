"""Provider-agnostic structured LLM access.

Every AI feature talks to `ChatModel.complete_structured`, which returns a
validated Pydantic model. Vendor SDKs are confined to this module.
"""

import json
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.core.config import Settings

T = TypeVar("T", bound=BaseModel)


class ChatModel(Protocol):
    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T: ...


class AnthropicChatModel:
    """Structured output via forced tool use."""

    def __init__(self, api_key: str, model: str):
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T:
        tool_name = "emit_" + schema.__name__.lower()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": tool_name,
                    "description": f"Emit the {schema.__name__} result",
                    "input_schema": schema.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in response.content:
            if block.type == "tool_use":
                return schema.model_validate(block.input)
        raise RuntimeError("model returned no tool_use block")


class _JSONModeChatModel:
    """Structured output via JSON mode.

    Shared by every OpenAI-compatible endpoint. Subclasses build `_client` (an
    `openai.AsyncOpenAI` or a subclass of it) and set `_model` to the model id or,
    for a deployment-addressed endpoint, the deployment name.
    """

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{system}\n\nRespond with a single JSON object matching this "
                        f"JSON schema:\n{json.dumps(schema.model_json_schema())}"
                    ),
                },
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return schema.model_validate_json(content)


class OpenAIChatModel(_JSONModeChatModel):
    def __init__(self, api_key: str, model: str):
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model


def foundry_base_url(endpoint: str) -> str:
    """Normalise a Foundry endpoint to its OpenAI-compatible v1 base URL.

    The portal hands out both the resource root and full operation URLs such as
    `https://<resource>.services.ai.azure.com/openai/v1/responses`, so accept
    either and let the SDK append the operation path itself.
    """
    trimmed = endpoint.strip().rstrip("/")
    marker = "/openai/v1"
    if marker in trimmed:
        return trimmed[: trimmed.index(marker) + len(marker)] + "/"
    return f"{trimmed}{marker}/"


class FoundryChatModel:
    """A model deployed on Microsoft Foundry (Azure AI Foundry).

    Foundry's v1 surface is OpenAI-compatible, so the stock client works once it is
    pointed at the resource. It serves the Responses API, which reports a refusal or
    a truncated generation instead of raising, so both are turned into errors here.
    """

    def __init__(self, endpoint: str, api_key: str, model: str):
        import openai

        missing = [
            name
            for name, value in (
                ("MATCHIT_FOUNDRY_ENDPOINT", endpoint),
                ("MATCHIT_FOUNDRY_API_KEY", api_key),
                ("MATCHIT_FOUNDRY_MODEL", model),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"foundry llm_provider requires {', '.join(missing)}")

        self._client = openai.AsyncOpenAI(
            base_url=foundry_base_url(endpoint), api_key=api_key
        )
        self._model = model

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T:
        response = await self._client.responses.create(
            model=self._model,
            instructions=system,
            # The schema goes in the input, not the instructions: json_object format
            # is rejected unless the input messages themselves ask for JSON.
            input=[
                {
                    "role": "user",
                    "content": (
                        f"{user}\n\nRespond with a single JSON object matching this "
                        f"JSON schema:\n{json.dumps(schema.model_json_schema())}"
                    ),
                }
            ],
            text={"format": {"type": "json_object"}},
            # Reasoning models spend part of this budget before emitting anything,
            # so the cap has to cover the thinking as well as the JSON.
            max_output_tokens=max(max_tokens, 4096),
        )
        content = (response.output_text or "").strip()
        if not content:
            raise RuntimeError(
                f"foundry model {self._model} returned no output "
                f"(status={response.status!r})"
            )
        return schema.model_validate_json(content)


class FakeChatModel:
    """Deterministic model for tests: returns queued responses in order."""

    def __init__(self, responses: list[BaseModel] | None = None):
        self.responses: list[BaseModel] = list(responses or [])
        self.calls: list[dict] = []

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T:
        self.calls.append({"system": system, "user": user, "schema": schema.__name__})
        if not self.responses:
            raise RuntimeError("FakeChatModel has no queued responses")
        response = self.responses.pop(0)
        if not isinstance(response, schema):
            raise TypeError(f"queued {type(response).__name__}, expected {schema.__name__}")
        return response


def build_chat_model(settings: Settings) -> ChatModel:
    if settings.llm_provider == "anthropic":
        return AnthropicChatModel(settings.anthropic_api_key, settings.anthropic_model)
    if settings.llm_provider == "openai":
        return OpenAIChatModel(settings.openai_api_key, settings.openai_model)
    if settings.llm_provider == "foundry":
        return FoundryChatModel(
            settings.foundry_endpoint, settings.foundry_api_key, settings.foundry_model
        )
    if settings.llm_provider == "fake":
        return FakeChatModel()
    raise ValueError(f"unknown llm_provider: {settings.llm_provider}")
