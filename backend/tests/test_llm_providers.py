import pytest

from app.ai.llm import (
    FakeChatModel,
    FoundryChatModel,
    OpenAIChatModel,
    build_chat_model,
    foundry_base_url,
)
from app.core.config import Settings

FOUNDRY = {
    "llm_provider": "foundry",
    "foundry_endpoint": "https://example-resource.services.ai.azure.com/openai/v1/responses",
    "foundry_api_key": "not-a-real-key",
    "foundry_model": "gpt-5.4-nano",
}


def settings_for(**overrides) -> Settings:
    # _env_file=None keeps a developer's local .env out of these assertions.
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://r.services.ai.azure.com",
        "https://r.services.ai.azure.com/",
        "https://r.services.ai.azure.com/openai/v1",
        "https://r.services.ai.azure.com/openai/v1/",
        "https://r.services.ai.azure.com/openai/v1/responses",
        "  https://r.services.ai.azure.com/openai/v1/chat/completions  ",
    ],
)
def test_every_endpoint_form_normalises_to_the_v1_base(endpoint):
    assert foundry_base_url(endpoint) == "https://r.services.ai.azure.com/openai/v1/"


def test_foundry_provider_uses_the_configured_model():
    model = build_chat_model(settings_for(**FOUNDRY))
    assert isinstance(model, FoundryChatModel)
    assert model._model == "gpt-5.4-nano"


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        ("foundry_endpoint", "MATCHIT_FOUNDRY_ENDPOINT"),
        ("foundry_api_key", "MATCHIT_FOUNDRY_API_KEY"),
        ("foundry_model", "MATCHIT_FOUNDRY_MODEL"),
    ],
)
def test_foundry_provider_names_missing_settings(missing, expected):
    with pytest.raises(ValueError, match=expected):
        build_chat_model(settings_for(**{**FOUNDRY, missing: ""}))


def test_known_providers_still_dispatch():
    assert isinstance(build_chat_model(settings_for(llm_provider="fake")), FakeChatModel)
    assert isinstance(
        build_chat_model(settings_for(llm_provider="openai", openai_api_key="x")),
        OpenAIChatModel,
    )


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="unknown llm_provider"):
        build_chat_model(settings_for(llm_provider="mystery"))
