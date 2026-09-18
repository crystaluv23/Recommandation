from http.client import IncompleteRead
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from ssl import SSLError

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


class JsonResponse(IncompleteReadResponse):
    def read(self):
        return b'{"ok":true}'


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

    def test_urllib_transport_sends_canonical_utf8_json_bytes(self) -> None:
        captured = []

        def urlopen(request, *, timeout):
            captured.append((request, timeout))
            return JsonResponse()

        with patch("stock_opportunity_agent.llm.openai.request.urlopen", urlopen):
            result = UrllibTransport(max_attempts=1).post_json(
                "https://api.example.test/responses",
                {},
                {"z": "匿名证据", "a": 1},
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            captured[0][0].data,
            '{"a":1,"z":"匿名证据"}'.encode("utf-8"),
        )

    def test_urllib_transport_retries_generic_temporary_failures(self) -> None:
        temporary_failures = (
            HTTPError(
                "https://api.example.test/responses",
                429,
                "rate limited",
                {},
                BytesIO(b'{"error":"rate limited"}'),
            ),
            HTTPError(
                "https://api.example.test/responses",
                503,
                "unavailable",
                {},
                BytesIO(b'{"error":"unavailable"}'),
            ),
            URLError("temporary DNS failure"),
            TimeoutError("socket timed out"),
            SSLError("record layer failure"),
            ConnectionResetError("connection reset"),
        )
        for failure in temporary_failures:
            with self.subTest(failure=type(failure).__name__):
                with patch(
                    "stock_opportunity_agent.llm.openai.request.urlopen",
                    side_effect=[failure, JsonResponse()],
                ) as urlopen:
                    result = UrllibTransport(
                        max_attempts=2,
                        retry_backoff_seconds=0,
                    ).post_json(
                        "https://api.example.test/responses",
                        {},
                        {"ok": True},
                    )

                self.assertEqual(result, {"ok": True})
                self.assertEqual(urlopen.call_count, 2)

    def test_urllib_transport_normalizes_tls_failure_during_response_read(self) -> None:
        from stock_opportunity_agent.llm.openai import RetryableOpenAIClientError

        class BrokenResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                raise SSLError("record layer failure")

        with patch("stock_opportunity_agent.llm.openai.request.urlopen", return_value=BrokenResponse()) as call:
            with self.assertRaises(RetryableOpenAIClientError) as raised:
                UrllibTransport(max_attempts=1).post_json("https://api.example.test/responses", {}, {})
        self.assertIsInstance(raised.exception.__cause__, SSLError)
        self.assertEqual(call.call_count, 1)

    def test_urllib_transport_does_not_retry_permanent_http_failure(self) -> None:
        failure = HTTPError(
            "https://api.example.test/responses",
            400,
            "bad request",
            {},
            BytesIO(b'{"error":"bad request"}'),
        )
        with patch(
            "stock_opportunity_agent.llm.openai.request.urlopen",
            side_effect=failure,
        ) as urlopen:
            with self.assertRaises(OpenAIClientError):
                UrllibTransport(
                    max_attempts=3,
                    retry_backoff_seconds=0,
                ).post_json(
                    "https://api.example.test/responses",
                    {},
                    {"ok": True},
                )

        self.assertEqual(urlopen.call_count, 1)

    def test_responses_envelope_ignores_unrelated_items_and_rejects_refusal(
        self,
    ) -> None:
        client = OpenAIChatClient(
            "gpt-5.4-mini",
            "test-key",
            transport=FakeTransport(
                {
                    "id": "response_with_tool",
                    "model": "gpt-5.4-mini",
                    "output": [
                        {"type": "web_search_call", "status": "completed"},
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": '{"ok":true}'},
                                {"type": "annotation", "value": "ignored"},
                            ],
                        },
                    ],
                    "usage": None,
                    "provider_extra": {"shape": "allowed"},
                }
            ),
        )
        result = client.complete([ChatMessage("user", "Return JSON.")])
        self.assertEqual(result.output_text, '{"ok":true}')

        refusing = OpenAIChatClient(
            "gpt-5.4-mini",
            "test-key",
            transport=FakeTransport(
                {
                    "id": "response_refusal",
                    "model": "gpt-5.4-mini",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "refusal", "refusal": "Cannot comply."}
                            ],
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(OpenAIClientError, "refused"):
            refusing.complete([ChatMessage("user", "Return JSON.")])

        truncated = OpenAIChatClient(
            "gpt-5.4-mini",
            "test-key",
            transport=FakeTransport(
                {
                    "id": "response_reasoning_only",
                    "model": "gpt-5.4-mini",
                    "output": [
                        {
                            "type": "reasoning",
                            "content": [
                                {"type": "reasoning_text", "text": "thinking"}
                            ],
                        }
                    ],
                }
            ),
        )
        from stock_opportunity_agent.llm.openai import (
            RetryableOpenAIClientError,
        )

        with self.assertRaisesRegex(
            RetryableOpenAIClientError, "no output_text"
        ):
            truncated.complete([ChatMessage("user", "Return JSON.")])

        missing_output = OpenAIChatClient(
            "gpt-5.4-mini",
            "test-key",
            transport=FakeTransport(
                {"id": "response_no_output", "model": "gpt-5.4-mini"}
            ),
        )
        with self.assertRaisesRegex(
            RetryableOpenAIClientError, "missing output list"
        ):
            missing_output.complete([ChatMessage("user", "Return JSON.")])
