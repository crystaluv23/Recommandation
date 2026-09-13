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
    PreparedJsonRequest,
    UrllibTransport,
    _require_str,
)
from stock_opportunity_agent.models import ValidationError


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_API_KEY_ENV_VAR = "DEEPSEEK_API_KEY"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


class DeepSeekResponsesClient(OpenAIChatClient):
    """Responses client pinned to DeepSeek's OpenAI-compatible endpoint."""

    supports_token_logprobs = True

    def prepare_request(
        self,
        messages: list[ChatMessage],
        *,
        logprobs: bool = False,
        top_logprobs: int | None = None,
        **kwargs: Any,
    ) -> PreparedJsonRequest:
        """Build the exact Responses or Chat request selected by this adapter."""

        reasoning = kwargs.get("reasoning")
        if isinstance(reasoning, Mapping):
            effort = reasoning.get("effort")
            kwargs["reasoning"] = {"effort": effort} if effort else None
        if logprobs:
            return self._prepare_chat_with_logprobs(
                messages,
                top_logprobs=top_logprobs,
                **kwargs,
            )
        return super().prepare_request(messages, **kwargs)

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        logprobs: bool = False,
        top_logprobs: int | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Use Responses normally and Chat Completions when logprobs are requested."""

        reasoning = kwargs.get("reasoning")
        if isinstance(reasoning, Mapping):
            effort = reasoning.get("effort")
            kwargs["reasoning"] = {"effort": effort} if effort else None
        if logprobs:
            return self._complete_chat_with_logprobs(
                messages,
                top_logprobs=top_logprobs,
                **kwargs,
            )
        return super().complete(messages, **kwargs)

    def _complete_chat_with_logprobs(
        self,
        messages: list[ChatMessage],
        *,
        top_logprobs: int | None,
        max_output_tokens: int | None = None,
        response_format: Mapping[str, Any] | None = None,
        reasoning: Mapping[str, Any] | None = None,
        **_unused: Any,
    ) -> ChatResponse:
        """Call DeepSeek's documented Chat Completions logprob boundary."""

        prepared = self._prepare_chat_with_logprobs(
            messages,
            top_logprobs=top_logprobs,
            max_output_tokens=max_output_tokens,
            response_format=response_format,
            reasoning=reasoning,
        )
        headers = {"Authorization": f"Bearer {self.api_key}"}
        raw = self.transport.post_json(
            prepared.url,
            headers,
            prepared.payload,
        )
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValidationError("DeepSeek chat response requires choices")
        first = choices[0]
        if not isinstance(first, Mapping) or not isinstance(first.get("message"), Mapping):
            raise ValidationError("DeepSeek chat response requires a message")
        output_text = _require_str(first["message"], "content")
        return ChatResponse(
            response_id=_require_str(raw, "id"),
            model=_require_str(raw, "model"),
            output_text=output_text,
            raw=dict(raw),
        )

    def _prepare_chat_with_logprobs(
        self,
        messages: list[ChatMessage],
        *,
        top_logprobs: int | None,
        max_output_tokens: int | None = None,
        response_format: Mapping[str, Any] | None = None,
        reasoning: Mapping[str, Any] | None = None,
        **_unused: Any,
    ) -> PreparedJsonRequest:
        """Build DeepSeek's exact Chat Completions logprob request."""

        if not messages:
            raise ValidationError("messages must not be empty")
        if top_logprobs is None or not 1 <= top_logprobs <= 20:
            raise ValidationError("top_logprobs must be between 1 and 20")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "temperature": self.temperature,
            "logprobs": True,
            "top_logprobs": top_logprobs,
        }
        if max_output_tokens is not None:
            if max_output_tokens < 1:
                raise ValidationError("max_output_tokens must be positive")
            payload["max_tokens"] = max_output_tokens
        if response_format is not None:
            payload["response_format"] = dict(response_format)
        if isinstance(reasoning, Mapping) and reasoning.get("effort") == "none":
            payload["thinking"] = {"type": "disabled"}

        return PreparedJsonRequest(
            f"{self.base_url}/chat/completions",
            payload,
        )


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
    "deepseek-v4-flash-thinking",
    provider="deepseek",
    model=DEFAULT_DEEPSEEK_MODEL,
    roles=("evolution",),
    api_key_env_var=DEFAULT_DEEPSEEK_API_KEY_ENV_VAR,
    description="DeepSeek V4 Flash with high reasoning for structured research roles.",
    proposal_profile="plain_json",
    web_tools_allowed=False,
    default_max_output_tokens=8000,
    default_reasoning_effort="high",
    default_input_cost_per_million_tokens=0.28,
    default_output_cost_per_million_tokens=0.56,
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
