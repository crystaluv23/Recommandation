"""OpenRouter Responses API provider."""

from __future__ import annotations

import os
from typing import Any, Mapping

from stock_opportunity_agent.config import PromptConfig
from stock_opportunity_agent.llm import register
from stock_opportunity_agent.llm.openai import (
    ChatMessage,
    ChatResponse,
    HttpTransport,
    OpenAIChatClient,
    UrllibTransport,
    _extract_output_text,
    _require_str,
)
from stock_opportunity_agent.models import ValidationError


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_API_KEY_ENV_VAR = "OPENROUTER_API_KEY"


class OpenRouterChatClient(OpenAIChatClient):
    """OpenRouter-compatible Responses API client.

    OpenRouter mostly follows the OpenAI Responses API shape, but its web-search
    server tool and JSON-mode behavior differ enough to keep the adaptation at a
    separate provider boundary.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        base_url: str = DEFAULT_OPENROUTER_BASE_URL,
        temperature: float = 0.2,
        app_referer: str = "http://localhost",
        app_title: str = "stock-opportunity-agent",
        provider_only: tuple[str, ...] = (),
        provider_require_parameters: bool = False,
        provider_allow_fallbacks: bool = True,
        transport: HttpTransport | None = None,
    ) -> None:
        super().__init__(
            model,
            api_key,
            base_url=base_url,
            temperature=temperature,
            transport=transport,
        )
        if not app_referer.strip():
            raise ValidationError("app_referer must not be empty")
        if not app_title.strip():
            raise ValidationError("app_title must not be empty")
        if any(not provider.strip() for provider in provider_only):
            raise ValidationError("provider_only values must not be empty")
        self.app_referer = app_referer
        self.app_title = app_title
        self.provider_only = tuple(provider_only)
        self.provider_require_parameters = provider_require_parameters
        self.provider_allow_fallbacks = provider_allow_fallbacks
        self.transport = transport or UrllibTransport()

    @classmethod
    def from_config(
        cls,
        config: PromptConfig,
        environ: Mapping[str, str] | None = None,
        transport: HttpTransport | None = None,
    ) -> "OpenRouterChatClient":
        """Create a client from prompt config and ``OPENROUTER_API_KEY``."""

        env = os.environ if environ is None else environ
        api_key = env.get(DEFAULT_OPENROUTER_API_KEY_ENV_VAR)
        if not api_key:
            raise OpenRouterClientError(f"{DEFAULT_OPENROUTER_API_KEY_ENV_VAR} is not set")
        return cls(
            config.model_version,
            api_key,
            base_url=DEFAULT_OPENROUTER_BASE_URL,
            temperature=config.research_temperature,
            transport=transport,
        )

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        max_output_tokens: int | None = None,
        response_format: Mapping[str, Any] | None = None,
        tools: list[Mapping[str, Any]] | None = None,
        tool_choice: str | Mapping[str, Any] | None = None,
        include: list[str] | None = None,
        plugins: list[Mapping[str, Any]] | None = None,
        reasoning: Mapping[str, Any] | None = None,
    ) -> ChatResponse:
        """Send messages through OpenRouter and return normalized text."""

        if not messages:
            raise ValidationError("messages must not be empty")
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [message.to_response_input() for message in messages],
            "temperature": self.temperature,
        }
        if max_output_tokens is not None:
            if max_output_tokens < 1:
                raise ValidationError("max_output_tokens must be positive")
            payload["max_output_tokens"] = max_output_tokens
        if tools is not None:
            payload["tools"] = [_openrouter_tool(tool) for tool in tools]
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if response_format is not None and not tools:
            payload["text"] = {"format": dict(response_format)}
        if include is not None and not tools:
            payload["include"] = list(include)
        if plugins is not None:
            payload["plugins"] = [dict(plugin) for plugin in plugins]
        if reasoning is not None:
            payload["reasoning"] = dict(reasoning)
        if (
            self.provider_only
            or self.provider_require_parameters
            or not self.provider_allow_fallbacks
        ):
            payload["provider"] = {
                "only": list(self.provider_only),
                "require_parameters": self.provider_require_parameters,
                "allow_fallbacks": self.provider_allow_fallbacks,
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.app_referer,
            "X-Title": self.app_title,
        }
        raw = self.transport.post_json(f"{self.base_url}/responses", headers, payload)
        return ChatResponse(
            response_id=_require_str(raw, "id"),
            model=_require_str(raw, "model"),
            output_text=_extract_output_text(raw),
            raw=raw,
        )


class OpenRouterClientError(RuntimeError):
    """Raised when OpenRouter credentials or responses are invalid."""


@register("openrouter")
def model(
    config: PromptConfig,
    environ: Mapping[str, str] | None = None,
    transport: HttpTransport | None = None,
) -> OpenRouterChatClient:
    """Registered OpenRouter model provider factory."""

    return OpenRouterChatClient.from_config(config, environ=environ, transport=transport)


def _openrouter_tool(tool: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(tool)
    if normalized.get("type") == "web_search":
        normalized["type"] = "openrouter:web_search"
    return normalized
