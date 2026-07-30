"""OpenAI Responses API provider."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any, Mapping, Protocol
from urllib import request
from urllib.error import HTTPError, URLError

from stock_opportunity_agent.config import PromptConfig
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.llm import register


class HttpTransport(Protocol):
    """Small transport boundary used to keep API tests offline."""

    def post_json(self, url: str, headers: Mapping[str, str], payload: Mapping[str, Any]) -> dict[str, Any]:
        """Send JSON and return decoded JSON."""


class UrllibTransport:
    """Standard-library HTTP transport."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValidationError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValidationError("max_attempts must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValidationError("retry_backoff_seconds cannot be negative")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds

    def post_json(self, url: str, headers: Mapping[str, str], payload: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(1, self.max_attempts + 1):
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if attempt < self.max_attempts and (
                    exc.code in {408, 429} or 500 <= exc.code < 600
                ):
                    self._backoff(attempt)
                    continue
                raise OpenAIClientError(f"OpenAI API returned HTTP {exc.code}: {detail}") from exc
            except URLError as exc:
                if attempt >= self.max_attempts:
                    raise OpenAIClientError(f"OpenAI API request failed: {exc.reason}") from exc
                self._backoff(attempt)
            except TimeoutError as exc:
                if attempt >= self.max_attempts:
                    raise OpenAIClientError(f"OpenAI API request timed out: {exc}") from exc
                self._backoff(attempt)
            except (HTTPException, json.JSONDecodeError) as exc:
                if attempt >= self.max_attempts:
                    raise OpenAIClientError(f"OpenAI API response was incomplete or invalid: {exc}") from exc
                self._backoff(attempt)
        raise OpenAIClientError("OpenAI API request failed")

    def _backoff(self, attempt: int) -> None:
        delay = self.retry_backoff_seconds * (2 ** (attempt - 1))
        if delay > 0:
            time.sleep(delay)


class OpenAIClientError(RuntimeError):
    """Raised when the OpenAI API request or response is invalid."""


@dataclass(frozen=True)
class ChatMessage:
    """Minimal chat-style message accepted by the Responses API adapter."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"developer", "system", "user", "assistant"}:
            raise ValidationError("role must be developer, system, user, or assistant")
        if not self.content.strip():
            raise ValidationError("message content must not be empty")

    def to_response_input(self) -> dict[str, Any]:
        """Return a Responses API message item."""

        return {
            "role": self.role,
            "content": [{"type": "input_text", "text": self.content}],
        }


@dataclass(frozen=True)
class ChatResponse:
    """Normalized text response from OpenAI."""

    response_id: str
    model: str
    output_text: str
    raw: dict[str, Any]


class OpenAIChatClient:
    """Tiny ChatGPT/OpenAI Responses API client.

    Example:
        ``OpenAIChatClient.from_config(config.prompts).complete([ChatMessage("user", "Hi")])``.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.2,
        transport: HttpTransport | None = None,
    ) -> None:
        if not model.strip():
            raise ValidationError("model must not be empty")
        if not api_key.strip():
            raise ValidationError("api_key must not be empty")
        if not base_url.strip():
            raise ValidationError("base_url must not be empty")
        if not 0 <= temperature <= 1:
            raise ValidationError("temperature must be between 0 and 1")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.transport = transport or UrllibTransport()

    @classmethod
    def from_config(
        cls,
        config: PromptConfig,
        environ: Mapping[str, str] | None = None,
        transport: HttpTransport | None = None,
    ) -> "OpenAIChatClient":
        """Create a client using the API key environment variable named by config."""

        env = os.environ if environ is None else environ
        api_key = env.get(config.openai_api_key_env_var)
        if not api_key:
            raise OpenAIClientError(f"{config.openai_api_key_env_var} is not set")
        return cls(
            config.model_version,
            api_key,
            base_url=config.openai_base_url,
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
    ) -> ChatResponse:
        """Send messages to the OpenAI Responses API and return assistant text."""

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
        if response_format is not None:
            payload["text"] = {"format": dict(response_format)}
        if tools is not None:
            payload["tools"] = [dict(tool) for tool in tools]
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if include is not None:
            payload["include"] = list(include)

        headers = {"Authorization": f"Bearer {self.api_key}"}
        raw = self.transport.post_json(f"{self.base_url}/responses", headers, payload)
        return ChatResponse(
            response_id=_require_str(raw, "id"),
            model=_require_str(raw, "model"),
            output_text=_extract_output_text(raw),
            raw=raw,
        )


@register("openai")
def model(
    config: PromptConfig,
    environ: Mapping[str, str] | None = None,
    transport: HttpTransport | None = None,
) -> OpenAIChatClient:
    """Registered OpenAI model provider factory."""

    return OpenAIChatClient.from_config(config, environ=environ, transport=transport)


def _extract_output_text(raw: Mapping[str, Any]) -> str:
    output = raw.get("output")
    if not isinstance(output, list):
        raise OpenAIClientError("OpenAI response missing output list")
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    if not chunks:
        raise OpenAIClientError("OpenAI response contained no output_text")
    return "".join(chunks)


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise OpenAIClientError(f"OpenAI response missing {key}")
    return value
