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


class OpenAIChatModel:
    """Structured output via JSON mode; also covers Azure OpenAI deployments."""

    def __init__(self, api_key: str, model: str):
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

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
    if settings.llm_provider == "fake":
        return FakeChatModel()
    raise ValueError(f"unknown llm_provider: {settings.llm_provider}")
