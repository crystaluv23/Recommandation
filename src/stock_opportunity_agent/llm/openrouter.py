"""OpenRouter Responses API provider."""

from __future__ import annotations

import os
from typing import Any, Mapping

from stock_opportunity_agent.config import PromptConfig
from stock_opportunity_agent.llm import ModelClientSettings, register, register_model
from stock_opportunity_agent.llm.openai import (
    ChatMessage,
    ChatResponse,
    HttpTransport,
    OpenAIChatClient,
    PreparedJsonRequest,
    UrllibTransport,
    _parse_provider_response,
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

    def prepare_request(
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
    ) -> PreparedJsonRequest:
        """Build the exact secret-free OpenRouter Responses request."""

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

        return PreparedJsonRequest(f"{self.base_url}/responses", payload)

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

        prepared = self.prepare_request(
            messages,
            max_output_tokens=max_output_tokens,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            include=include,
            plugins=plugins,
            reasoning=reasoning,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.app_referer,
            "X-Title": self.app_title,
        }
        raw = self.transport.post_json(
            prepared.url,
            headers,
            prepared.payload,
        )
        return _parse_provider_response(raw)


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


@register_model(
    "openrouter-fusion",
    provider="openrouter",
    model="openrouter/fusion",
    roles=("evolution",),
    api_key_env_var=DEFAULT_OPENROUTER_API_KEY_ENV_VAR,
    description="Web-enabled Fusion Quality proposer; never used for blind judging.",
    proposal_profile="openrouter_fusion",
    web_tools_allowed=True,
    default_max_output_tokens=5000,
)
def registered_fusion_model(settings: ModelClientSettings) -> OpenRouterChatClient:
    """Build the registered OpenRouter Fusion proposal client."""

    return _registered_client(settings, model_name="openrouter/fusion")


@register_model(
    "kimi-k3-together",
    provider="openrouter",
    model="moonshotai/kimi-k3",
    roles=("judge",),
    api_key_env_var=DEFAULT_OPENROUTER_API_KEY_ENV_VAR,
    description="Anonymous no-web Kimi K3 judge pinned to the Together route.",
    provider_route="together",
    default_max_output_tokens=8000,
    default_reasoning_effort="max",
    default_input_cost_per_million_tokens=3.0,
    default_output_cost_per_million_tokens=15.0,
)
def registered_kimi_k3_model(settings: ModelClientSettings) -> OpenRouterChatClient:
    """Build the registered fixed-route Kimi K3 judge client."""

    return _registered_client(
        settings,
        model_name="moonshotai/kimi-k3",
        provider_route="together",
    )


@register_model(
    "gpt-4.1-openrouter",
    provider="openrouter",
    model="openai/gpt-4.1",
    roles=("judge",),
    api_key_env_var=DEFAULT_OPENROUTER_API_KEY_ENV_VAR,
    description="Anonymous no-web GPT-4.1 judge pinned to OpenRouter's OpenAI route.",
    provider_route="openai",
    default_max_output_tokens=2200,
    default_input_cost_per_million_tokens=2.0,
    default_output_cost_per_million_tokens=8.0,
)
def registered_gpt41_openrouter_model(
    settings: ModelClientSettings,
) -> OpenRouterChatClient:
    """Build the registered fixed-route GPT-4.1 judge client."""

    return _registered_client(
        settings,
        model_name="openai/gpt-4.1",
        provider_route="openai",
    )


def _registered_client(
    settings: ModelClientSettings,
    *,
    model_name: str,
    provider_route: str | None = None,
) -> OpenRouterChatClient:
    """Construct one catalog client with preview-safe credentials and fixed routing."""

    env = os.environ if settings.environ is None else settings.environ
    api_key = (
        "preview-only-no-network"
        if settings.preview_only
        else env.get(DEFAULT_OPENROUTER_API_KEY_ENV_VAR)
    )
    if not api_key:
        raise OpenRouterClientError(
            f"{DEFAULT_OPENROUTER_API_KEY_ENV_VAR} is not set"
        )
    return OpenRouterChatClient(
        model_name,
        api_key,
        temperature=settings.temperature,
        provider_only=(provider_route,) if provider_route else (),
        provider_require_parameters=bool(provider_route),
        provider_allow_fallbacks=not bool(provider_route),
        transport=UrllibTransport(
            timeout_seconds=settings.timeout_seconds,
            max_attempts=settings.max_http_attempts,
        ),
    )


def _openrouter_tool(tool: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(tool)
    if normalized.get("type") == "web_search":
        normalized["type"] = "openrouter:web_search"
    return normalized
