"""DeepSeek's OpenAI-compatible Responses API provider."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from stock_opportunity_agent.llm import ModelClientSettings, register, register_model
from stock_opportunity_agent.llm.openai import (
    ChatMessage,
    ChatResponse,
    HttpTransport,
    OpenAIChatClient,
    UrllibTransport,
)


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_API_KEY_ENV_VAR = "DEEPSEEK_API_KEY"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


class DeepSeekResponsesClient(OpenAIChatClient):
    """Responses client pinned to DeepSeek's OpenAI-compatible endpoint."""

    def complete(
        self,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        """Drop OpenRouter-only reasoning fields before a DeepSeek request."""

        reasoning = kwargs.get("reasoning")
        if isinstance(reasoning, Mapping):
            effort = reasoning.get("effort")
            kwargs["reasoning"] = {"effort": effort} if effort else None
        return super().complete(messages, **kwargs)


class DeepSeekClientError(RuntimeError):
    """Raised when DeepSeek credentials are unavailable."""


@register("deepseek")
def model(
    model_name: str = DEFAULT_DEEPSEEK_MODEL,
    *,
    environ: Mapping[str, str] | None = None,
    temperature: float = 0.0,
    transport: HttpTransport | None = None,
) -> DeepSeekResponsesClient:
    """Build a direct DeepSeek client using ``DEEPSEEK_API_KEY``."""

    env = os.environ if environ is None else environ
    api_key = env.get(DEFAULT_DEEPSEEK_API_KEY_ENV_VAR)
    if not api_key:
        raise DeepSeekClientError(f"{DEFAULT_DEEPSEEK_API_KEY_ENV_VAR} is not set")
    return DeepSeekResponsesClient(
        model_name,
        api_key,
        base_url=DEFAULT_DEEPSEEK_BASE_URL,
        temperature=temperature,
        transport=transport,
    )


@register_model(
    "deepseek-v4-flash",
    provider="deepseek",
    model=DEFAULT_DEEPSEEK_MODEL,
    roles=("evolution", "judge"),
    api_key_env_var=DEFAULT_DEEPSEEK_API_KEY_ENV_VAR,
    description=(
        "Direct DeepSeek V4 Flash Responses API model for plain-JSON evolution "
        "and anonymous no-web judging."
    ),
    proposal_profile="plain_json",
    web_tools_allowed=False,
    default_max_output_tokens=8000,
    # Non-thinking mode makes the frozen temperature-zero judge setting effective.
    default_reasoning_effort="none",
    # 2026-08-02 official regular cache-miss/output prices are $0.14/$0.28.
    # DeepSeek has announced 2x peak-hour pricing, so cost gates reserve that bound.
    default_input_cost_per_million_tokens=0.28,
    default_output_cost_per_million_tokens=0.56,
)
def registered_deepseek_v4_flash_model(
    settings: ModelClientSettings,
) -> DeepSeekResponsesClient:
    """Build the catalog client without requiring credentials during preview."""

    env = os.environ if settings.environ is None else settings.environ
    api_key = (
        "preview-only-no-network"
        if settings.preview_only
        else env.get(DEFAULT_DEEPSEEK_API_KEY_ENV_VAR)
    )
    if not api_key:
        raise DeepSeekClientError(f"{DEFAULT_DEEPSEEK_API_KEY_ENV_VAR} is not set")
    return DeepSeekResponsesClient(
        DEFAULT_DEEPSEEK_MODEL,
        api_key,
        base_url=DEFAULT_DEEPSEEK_BASE_URL,
        temperature=settings.temperature,
        transport=UrllibTransport(
            timeout_seconds=settings.timeout_seconds,
            max_attempts=settings.max_http_attempts,
        ),
    )
