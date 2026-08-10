from http.client import IncompleteRead
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.config import PromptConfig
from stock_opportunity_agent.llm import create, registered
from stock_opportunity_agent.llm.openai import (
    ChatMessage,
    OpenAIChatClient,
    OpenAIClientError,
    RetryableOpenAIClientError,
    UrllibTransport,
)
from stock_opportunity_agent.models import ValidationError


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append((url, headers, payload))
        return self.response


class IncompleteReadResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        raise IncompleteRead(b"{")


class OpenAIChatClientTests(TestCase):
    def test_client_uses_responses_api_payload_and_extracts_text(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp_1",
                "model": "gpt-5.4-mini",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
                    }
                ],
            }
        )
        client = OpenAIChatClient(
            "gpt-5.4-mini",
            "test-key",
            base_url="https://api.openai.com/v1/",
            temperature=0.1,
            transport=transport,
        )

        result = client.complete(
            [ChatMessage("developer", "Return JSON."), ChatMessage("user", "Analyze NVDA.")],
            max_output_tokens=200,
            response_format={"type": "json_object"},
        )

        self.assertEqual(result.output_text, "{\"ok\": true}")
        url, headers, payload = transport.calls[0]
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertEqual(headers["Authorization"], "Bearer test-key")
        self.assertEqual(payload["model"], "gpt-5.4-mini")
        self.assertEqual(payload["input"][0]["role"], "developer")
        self.assertEqual(payload["text"]["format"]["type"], "json_object")

    def test_client_passes_responses_api_tools_for_web_search(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp_1",
                "model": "gpt-5.4-mini",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
                    }
                ],
            }
        )
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=transport)

        client.complete(
            [ChatMessage("user", "Find the inflection.")],
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
        )

        payload = transport.calls[0][2]
        self.assertEqual(payload["tools"], [{"type": "web_search"}])
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["include"], ["web_search_call.action.sources"])

    def test_from_config_reads_api_key_from_named_env_var(self) -> None:
        config = PromptConfig(openai_api_key_env_var="CUSTOM_OPENAI_KEY")

        client = create(
            "openai",
            config,
            environ={"CUSTOM_OPENAI_KEY": "sk-test"},
            transport=FakeTransport({"id": "resp", "model": "gpt-5.4-mini", "output": []}),
        )

        self.assertEqual(client.api_key, "sk-test")
        self.assertIn("openai", registered())

    def test_missing_api_key_is_not_silently_accepted(self) -> None:
        with self.assertRaises(OpenAIClientError):
            OpenAIChatClient.from_config(PromptConfig(), environ={})

    def test_empty_messages_are_rejected(self) -> None:
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=FakeTransport({}))

        with self.assertRaises(ValidationError):
            client.complete([])

    def test_urllib_transport_wraps_incomplete_chunked_response(self) -> None:
        with patch("stock_opportunity_agent.llm.openai.request.urlopen", return_value=IncompleteReadResponse()):
            with self.assertRaises(RetryableOpenAIClientError) as context:
                UrllibTransport(max_attempts=1).post_json("https://api.example.test/responses", {}, {"ok": True})

        self.assertIn("incomplete or invalid", str(context.exception))
