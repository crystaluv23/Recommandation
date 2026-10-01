"""Provider envelope classification and durable attempt recovery, without network."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.llm import RegisteredModel
from stock_opportunity_agent.llm.deepseek import DeepSeekResponsesClient
from stock_opportunity_agent.llm.openai import ChatMessage, OpenAIChatClient, OpenAIClientError, RetryableOpenAIClientError
from stock_opportunity_agent.llm.openrouter import OpenRouterChatClient
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_output_validation import _complete_parsed_role
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from tests.evolution_runtime_test_support import make_contract


def completion(**extra):
    """One complete Responses envelope with known measured usage."""
    return {"id": "response", "model": "fixture-model", "usage": {"input_tokens": 3, "output_tokens": 2},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]}], **extra}


class SequenceTransport:
    """Return physical responses once; no retry hidden inside the fixture."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append((url, payload))
        return self.responses.pop(0)


class ProviderEnvelopeTests(TestCase):
    def test_missing_metadata_and_nonobject_envelopes_are_retryable_for_all_adapters(self):
        for adapter in (OpenAIChatClient, OpenRouterChatClient, DeepSeekResponsesClient):
            for raw in (completion(id=None), completion(id=""), completion(id=" "), completion(model=None), completion(id="\ud800"), [], None):
                with self.subTest(adapter=adapter.__name__, raw_type=type(raw).__name__):
                    transport = SequenceTransport(raw)
                    with self.assertRaises(RetryableOpenAIClientError) as caught:
                        adapter("fixture-model", "fixture-key", transport=transport).complete([ChatMessage("user", "Return JSON.")])
                    self.assertFalse(isinstance(caught.exception, ValidationError))
                    self.assertEqual(len(transport.calls), 1)
                    self.assertIn("decoded_response_hash", caught.exception.response_diagnostic)

    def test_explicit_error_refusal_and_cancellation_take_precedence_over_missing_id(self):
        permanent = (
            {"error": {"type": "invalid_request_error", "code": "server_error", "message": "secret-message"}},
            {"error": {"code": 400, "type": "server_error"}},
            {"error": {"code": "unknown_code"}},
            {"status": "cancelled", "error": {"code": 500}},
            {"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "Cannot comply."}]}]},
        )
        for raw in permanent:
            with self.subTest(raw=raw):
                with self.assertRaises(OpenAIClientError) as caught:
                    OpenAIChatClient("model", "key", transport=SequenceTransport(raw)).complete([ChatMessage("user", "Return JSON.")])
                self.assertNotIsInstance(caught.exception, RetryableOpenAIClientError)
        for raw in ({"error": {"code": 429}}, {"error": {"type": "timeout"}},
                    {"error": {"code": 503}}, completion(status="failed"), completion(status="in_progress")):
            with self.assertRaises(RetryableOpenAIClientError):
                OpenAIChatClient("model", "key", transport=SequenceTransport(raw)).complete([ChatMessage("user", "Return JSON.")])

    def test_chat_choices_and_refusal_share_the_same_provider_boundary(self):
        for raw in ({}, {"choices": [{}]}, {"choices": [{"message": {"content": None}}]}):
            with self.assertRaises(RetryableOpenAIClientError):
                DeepSeekResponsesClient("model", "key", transport=SequenceTransport(raw)).complete(
                    [ChatMessage("user", "Return JSON.")], logprobs=True, top_logprobs=2,
                )
        with self.assertRaises(OpenAIClientError) as caught:
            DeepSeekResponsesClient("model", "key", transport=SequenceTransport(
                {"choices": [{"message": {"refusal": "Cannot comply."}}]},
            )).complete([ChatMessage("user", "Return JSON.")], logprobs=True, top_logprobs=2)
        self.assertNotIsInstance(caught.exception, RetryableOpenAIClientError)


class DurableProviderRecoveryTests(TestCase):
    def role_client(self, root, transport, *, max_cost=1.0):
        """Build the real durable caller around an offline provider transport."""
        contract = make_contract()
        registration = RegisteredModel(
            alias="fixture-provider", provider="fixture", model="fixture-model", roles=("evolution",),
            api_key_env_var="FIXTURE_KEY", description="offline provider envelope", proposal_profile="plain_json",
            client_factory=lambda _settings: OpenAIChatClient("fixture-model", "fixture-credential", transport=transport),
            default_input_cost_per_million_tokens=1.0, default_output_cost_per_million_tokens=1.0,
        )
        ledger = ExternalAttemptLedger(root / "attempts.json", max_attempts=4, max_total_cost=max_cost)
        return StructuredRoleClient(registration=registration, contract=contract, workspace=root, ledger=ledger,
                                    allow_external=True, acknowledged_contract_hash=contract.contract_hash,
                                    environ={"FIXTURE_KEY": "fixture-credential"})

    def call(self, client, key):
        return client.complete_json(stage="provider_boundary", system_prompt="Return JSON.",
                                    payload={"context": key}, allow_outcomes=False, max_output_tokens=20)

    def test_failure_diagnostic_cost_and_restart_preserve_completed_cache(self):
        bad = completion(id=None, provider_extra="fixture-credential")
        transport = SequenceTransport(completion(), bad, completion())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            caller = self.role_client(root, transport)
            self.call(caller, "completed")
            with self.assertRaises(RetryableOpenAIClientError):
                self.call(caller, "pending")
            initial = json.loads((root / "attempts.json").read_text())["attempts"]
            self.assertEqual([x["status"] for x in initial], ["completed", "failed"])
            failure_path = next((root / "failed_responses").glob("*.json"))
            failure = json.loads(failure_path.read_text())
            self.assertEqual(initial[-1]["response_hash"], canonical_json_hash(failure))
            self.assertEqual(failure["usage"]["cost_basis"], "provider_usage")
            self.assertAlmostEqual(initial[-1]["actual_cost"], 5 / 1_000_000)
            self.assertEqual(failure["provider_response_diagnostic"]["fields"]["id"]["type"], "NoneType")
            for path in root.rglob("*.json"):
                self.assertNotIn("fixture-credential", path.read_text())
            resumed = self.role_client(root, transport)
            _value, cached_usage = self.call(resumed, "completed")
            self.assertEqual(cached_usage.llm_calls, 0)
            self.assertEqual(len(transport.calls), 2)
            self.call(resumed, "pending")
            final = json.loads((root / "attempts.json").read_text())["attempts"]
            self.assertEqual([x["status"] for x in final], ["completed", "failed", "completed"])
            self.assertEqual(final[1]["request_hash"], final[2]["request_hash"])
            self.assertEqual(len(list((root / "cache/responses").glob("*.json"))), 2)

    def test_unknown_usage_is_conservative_on_both_failure_and_valid_completion(self):
        for usage in (None, {}, {"input_tokens": 3}, {"input_tokens": True, "output_tokens": 2},
                      {"input_tokens": -1, "output_tokens": 2}):
            transport = SequenceTransport(completion(id=None, usage=usage), completion(usage=usage))
            with self.subTest(usage=usage), TemporaryDirectory() as directory:
                root = Path(directory); caller = self.role_client(root, transport)
                with self.assertRaises(RetryableOpenAIClientError):
                    self.call(caller, "pending")
                _value, paid_usage = self.call(caller, "pending")
                rows = json.loads((root / "attempts.json").read_text())["attempts"]
                self.assertTrue(all(x["actual_cost"] == x["reserved_cost"] > 0 for x in rows))
                record = json.loads(next((root / "cache/responses").glob("*.json")).read_text())
                self.assertEqual(record["usage"]["cost_basis"], "reservation_unknown_usage")
                self.assertNotIn("input_tokens", record["usage"])
                _value, cached_usage = self.call(caller, "pending")
                self.assertEqual(cached_usage.cost, 0)
                self.assertEqual(cached_usage.tokens, paid_usage.tokens)
                self.assertEqual(len(transport.calls), 2)

    def test_provider_failure_bypasses_role_correction(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); transport = SequenceTransport(completion(id=None))
            caller = self.role_client(root, transport)
            with self.assertRaises(RetryableOpenAIClientError):
                _complete_parsed_role(caller, stage="provider_boundary", system_prompt="Return JSON.",
                                      payload={"context": "anonymous"}, parser=lambda value: value,
                                      allow_outcomes=False, patch_corrections=True, max_output_tokens=20)
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(len(list((root / "requests").glob("*.json"))), 1)
            self.assertEqual(list((root / "cache/responses").glob("*.json")), [])
