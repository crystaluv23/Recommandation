"""Local role dispatch must preserve production boundaries without network I/O."""
import json
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.llm import get_model, RegisteredModel
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_transport import (
    StructuredRoleClient, ExternalAttemptLedger, StructuredOutputInvalid,
)
from stock_opportunity_agent.research.local_role_exchange import (
    LocalRoleExchange, LocalRoleRequestPending, LocalRoleBudgetExhausted,
)
from stock_opportunity_agent.research.scheme_evolution import EvolutionControlFlow, RuntimeBudgetExceeded


class LocalRoleExchangeTests(TestCase):
    def client(self, root, *, calls=3):
        contract = SimpleNamespace(contract_hash="a" * 64,
                                   limits={"max_structured_corrections": 1, "max_local_role_calls": calls})
        return StructuredRoleClient(registration=get_model("independent-subagent"), contract=contract,
            workspace=root, ledger=ExternalAttemptLedger(root / "attempts.json", max_attempts=1, max_total_cost=1),
            allow_external=False, environ={})

    def kwargs(self):
        return dict(stage="research_controller_initialize", system_prompt="Inspect only supplied facts.",
                    payload={"initial_research_skill": "Read source", "basic_info": {"fact": "Issuer Alpha revenue is 40."}},
                    allow_outcomes=False, max_output_tokens=400)

    def submit(self, exchange, pending, raw):
        output = Path(pending["outbox_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(raw)
        exchange.submit(pending["request_hash"], agent_id="independent-test-role")

    def test_masked_dispatch_receipt_restore_and_cache_resume(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("network forbidden")):
            root = Path(directory)
            client = self.client(root)
            with client.anonymous_case(aliases=("Issuer Alpha",), company_id="issuer-alpha"):
                with self.assertRaises(LocalRoleRequestPending) as raised:
                    client.complete_json(**self.kwargs())
                pending = raised.exception.pending
                inbox = json.loads(Path(pending["inbox_path"]).read_text())
                self.assertNotIn("Issuer Alpha", json.dumps(inbox))
                self.assertNotIn("expectations", inbox)
                self.assertEqual(inbox["backend"], "independent-subagent")
                quoted = json.loads(inbox["messages"][1]["content"])["basic_info"]["fact"]
                self.submit(client.local_role_exchange, pending, json.dumps({"quote": quoted}))
                output, usage = client.complete_json(**self.kwargs())
                self.assertEqual(output["quote"], "Issuer Alpha revenue is 40.")
                self.assertEqual(usage.llm_calls, 1)
                self.assertEqual(usage.cost, 0)
            restarted = self.client(root)
            with restarted.anonymous_case(aliases=("Issuer Alpha",), company_id="issuer-alpha"):
                output2, usage2 = restarted.complete_json(**self.kwargs())
            self.assertEqual(output2, output)
            self.assertEqual(usage2.llm_calls, 0)
            self.assertEqual(len(list((root / "local_roles/inbox").glob("*.json"))), 1)
            self.assertEqual(client.ledger.summary["attempt_count"], 0)
            cached = next((root / "cache/responses").glob("*.json"))
            cache = json.loads(cached.read_text())
            self.assertIsNone(cache["usage"]["token_usage"])
            self.assertIsNone(cache["usage"]["internal_agent_cost"])

    def test_budget_is_checked_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.client(root)
            with self.assertRaises(RuntimeBudgetExceeded):
                client.complete_json(**self.kwargs(), max_request_tokens=1)
            self.assertFalse((root / "local_roles/inbox").exists())

    def test_missing_response_and_call_ceiling_are_control_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.client(root, calls=1)
            with self.assertRaises(LocalRoleRequestPending) as raised:
                client.complete_json(**self.kwargs())
            self.assertIsInstance(raised.exception, EvolutionControlFlow)
            self.assertNotIsInstance(raised.exception, ValidationError)
            changed = self.kwargs()
            changed["system_prompt"] = "A different request"
            with self.assertRaises(LocalRoleBudgetExhausted) as exhausted:
                client.complete_json(**changed)
            self.assertIsInstance(exhausted.exception, EvolutionControlFlow)
            with self.assertRaises(ValidationError):
                self.client(root, calls=2)

    def test_raw_tamper_and_wrong_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(Path(directory))
            with self.assertRaises(LocalRoleRequestPending) as raised:
                client.complete_json(**self.kwargs())
            pending = raised.exception.pending
            self.submit(client.local_role_exchange, pending, '{"answer":true}')
            Path(pending["outbox_path"]).write_text('{"answer":false}')
            with self.assertRaisesRegex(ValidationError, "receipt"):
                client.complete_json(**self.kwargs())

    def test_malformed_raw_preserved_and_enters_native_parser_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(Path(directory))
            with self.assertRaises(LocalRoleRequestPending) as raised:
                client.complete_json(**self.kwargs())
            pending = raised.exception.pending
            self.submit(client.local_role_exchange, pending, "This is not JSON")
            with self.assertRaises(StructuredOutputInvalid) as malformed:
                client.complete_json(**self.kwargs())
            self.assertEqual(malformed.exception.raw_output, "This is not JSON")
            self.assertEqual(Path(pending["outbox_path"]).read_text(), "This is not JSON")
            self.assertFalse(list((Path(directory) / "cache/responses").glob("*.json")))

    def test_repeated_correction_hash_keeps_no_progress_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(Path(directory))
            kwargs = self.kwargs()
            with client.correction_chain(stage=kwargs["stage"]):
                with self.assertRaises(LocalRoleRequestPending):
                    client.complete_json(**kwargs)
                with self.assertRaisesRegex(Exception, "no-progress"):
                    client.complete_json(**kwargs)
            self.assertEqual(len(list((Path(directory) / "local_roles/inbox").glob("*.json"))), 1)

    def test_external_mode_and_registration_impersonation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(Path(directory))
            with self.assertRaisesRegex(ValidationError, "disallows external"):
                StructuredRoleClient(registration=get_model("independent-subagent"), contract=client.contract,
                    workspace=directory, ledger=client.ledger, allow_external=True)
            with self.assertRaisesRegex(ValidationError, "requires independent"):
                StructuredRoleClient(registration=get_model("deepseek-v4-flash"), contract=client.contract,
                    workspace=directory, ledger=client.ledger, local_role_exchange=client.local_role_exchange)
            with self.assertRaisesRegex(ValidationError, "requires local"):
                replace(get_model("independent-subagent"), provider="remote")

    def test_binary_logprobs_are_absent_without_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(Path(directory))
            token, usage, scores = client.complete_binary_token_with_scores(
                stage="blind_predictor_predict", system_prompt="Decide", payload={"final_context": {}},
                allow_outcomes=False, decision_field="decision", decision_tokens=("yes", "no"))
            self.assertEqual(token, "")
            self.assertEqual(usage.llm_calls, 0)
            self.assertIsNone(scores)
            self.assertFalse((Path(directory) / "local_roles/inbox").exists())

    def test_atomic_publish_failure_leaves_no_partial_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "exchange"
            with patch("stock_opportunity_agent.research.local_role_exchange.os.link", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    LocalRoleExchange(root, max_calls=1)
            self.assertFalse((root / "contract.json").exists())
            self.assertEqual(list(root.iterdir()), [])
            LocalRoleExchange(root, max_calls=1)
