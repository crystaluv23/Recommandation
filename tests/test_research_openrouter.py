from unittest import TestCase

from stock_opportunity_agent.config import PromptConfig
from stock_opportunity_agent.llm import create, registered
from stock_opportunity_agent.llm.openai import ChatMessage
from stock_opportunity_agent.llm.openrouter import OpenRouterChatClient, OpenRouterClientError


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append((url, headers, payload))
        return self.response


class OpenRouterChatClientTests(TestCase):
    def test_web_search_payload_uses_openrouter_tool_without_json_mode(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp_1",
                "model": "openai/gpt-5.5",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
                    }
                ],
            }
        )
        client = OpenRouterChatClient("openai/gpt-5.5", "test-key", transport=transport)

        result = client.complete(
            [ChatMessage("user", "Find the inflection.")],
            response_format={"type": "json_object"},
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
        )

        self.assertEqual(result.output_text, "{\"ok\": true}")
        url, headers, payload = transport.calls[0]
        self.assertEqual(url, "https://openrouter.ai/api/v1/responses")
        self.assertEqual(headers["Authorization"], "Bearer test-key")
        self.assertEqual(headers["HTTP-Referer"], "http://localhost")
        self.assertEqual(headers["X-Title"], "stock-opportunity-agent")
        self.assertEqual(payload["tools"], [{"type": "openrouter:web_search"}])
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertNotIn("text", payload)
        self.assertNotIn("include", payload)

    def test_non_tool_json_mode_is_preserved(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp_1",
                "model": "openai/gpt-5.5",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
                    }
                ],
            }
        )
        client = OpenRouterChatClient("openai/gpt-5.5", "test-key", transport=transport)

        client.complete(
            [ChatMessage("user", "Analyze this packet.")],
            response_format={"type": "json_object"},
        )

        payload = transport.calls[0][2]
        self.assertEqual(payload["text"]["format"]["type"], "json_object")

    def test_from_config_reads_openrouter_api_key(self) -> None:
        client = create(
            "openrouter",
            PromptConfig(model_version="openai/gpt-5.5"),
            environ={"OPENROUTER_API_KEY": "sk-or-test"},
            transport=FakeTransport({"id": "resp", "model": "openai/gpt-5.5", "output": []}),
        )

        self.assertEqual(client.api_key, "sk-or-test")
        self.assertIn("openrouter", registered())

    def test_missing_openrouter_api_key_is_not_silently_accepted(self) -> None:
        with self.assertRaises(OpenRouterClientError):
            OpenRouterChatClient.from_config(PromptConfig(model_version="openai/gpt-5.5"), environ={})
