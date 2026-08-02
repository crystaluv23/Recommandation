from unittest import TestCase

from stock_opportunity_agent.llm import create, get_model, registered
from stock_opportunity_agent.llm.deepseek import (
    DeepSeekClientError,
    DeepSeekResponsesClient,
)
from stock_opportunity_agent.llm.openai import ChatMessage


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append((url, headers, payload))
        return self.response


class DeepSeekResponsesClientTests(TestCase):
    def test_provider_uses_responses_endpoint_and_json_format(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp_deepseek_1",
                "model": "deepseek-v4-flash",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"ok": true}'}
                        ],
                    }
                ],
            }
        )
        client = create(
            "deepseek",
            environ={"DEEPSEEK_API_KEY": "test-key"},
            transport=transport,
        )

        result = client.complete(
            [
                ChatMessage("developer", "Return JSON."),
                ChatMessage("user", "Evaluate this anonymous packet."),
            ],
            max_output_tokens=8000,
            response_format={"type": "json_object"},
            reasoning={"effort": "none", "exclude": True},
        )

        self.assertIsInstance(client, DeepSeekResponsesClient)
        self.assertEqual(result.output_text, '{"ok": true}')
        url, headers, payload = transport.calls[0]
        self.assertEqual(url, "https://api.deepseek.com/responses")
        self.assertEqual(headers["Authorization"], "Bearer test-key")
        self.assertEqual(payload["model"], "deepseek-v4-flash")
        self.assertEqual(payload["text"]["format"], {"type": "json_object"})
        self.assertEqual(payload["reasoning"], {"effort": "none"})
        self.assertNotIn("tools", payload)

    def test_provider_and_model_are_auto_discovered_for_both_roles(self) -> None:
        self.assertIn("deepseek", registered())
        registration = get_model("deepseek-v4-flash")

        self.assertEqual(registration.roles, ("evolution", "judge"))
        self.assertEqual(registration.api_key_env_var, "DEEPSEEK_API_KEY")
        self.assertEqual(registration.default_input_cost_per_million_tokens, 0.28)
        self.assertEqual(registration.default_output_cost_per_million_tokens, 0.56)
        self.assertEqual(registration.default_reasoning_effort, "none")

    def test_missing_api_key_fails_without_network(self) -> None:
        with self.assertRaisesRegex(DeepSeekClientError, "DEEPSEEK_API_KEY"):
            create("deepseek", environ={})
