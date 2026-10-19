"""Local role dispatch must preserve production boundaries without network I/O."""
import json
import tempfile
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError

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
                self.assertTrue(Path(pending["outbox_path"]).parent.is_dir())
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
            self.assertEqual(usage2.llm_calls, 1)
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

    def test_separate_clients_cannot_exceed_shared_ceiling_concurrently(self):
        import stock_opportunity_agent.research.local_role_exchange as module
        original = module._immutable
        barrier = Barrier(2)

        def delayed_publish(path, record):
            if path.parent.name == "inbox":
                try:
                    barrier.wait(timeout=0.2)
                except BrokenBarrierError:
                    pass
            return original(path, record)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clients = [self.client(root, calls=1), self.client(root, calls=1)]

            def dispatch(index):
                kwargs = self.kwargs()
                kwargs["system_prompt"] += str(index)
                try:
                    clients[index].complete_json(**kwargs)
                except EvolutionControlFlow as exc:
                    return type(exc).__name__

            with patch.object(module, "_immutable", side_effect=delayed_publish), ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(dispatch, (0, 1)))
            self.assertEqual(sorted(results), ["LocalRoleBudgetExhausted", "LocalRoleRequestPending"])
            self.assertEqual(len(list((root / "local_roles/inbox").glob("*.json"))), 1)

    def test_cache_resume_revalidates_raw_receipt_and_parsed_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.client(root)
            with self.assertRaises(LocalRoleRequestPending) as raised:
                client.complete_json(**self.kwargs())
            pending = raised.exception.pending
            self.submit(client.local_role_exchange, pending, '{"answer":true}')
            self.assertTrue(client.complete_json(**self.kwargs())[0]["answer"])
            cache_path = root / "cache/responses" / f"{pending['request_hash']}.json"
            original_cache = cache_path.read_bytes()
            cache = json.loads(original_cache)
            cache["json_output"] = {"answer": False}
            cache_path.write_text(json.dumps(cache))
            with self.assertRaisesRegex(ValidationError, "cache"):
                self.client(root).complete_json(**self.kwargs())
            cache_path.write_bytes(original_cache)
            Path(pending["outbox_path"]).write_text('{"answer":false}')
            with self.assertRaisesRegex(ValidationError, "receipt"):
                self.client(root).complete_json(**self.kwargs())
            self.assertEqual(len(list((root / "local_roles/inbox").glob("*.json"))), 1)

    def test_shared_ceiling_is_serialized_between_processes(self):
        code = '''
import sys, time
from pathlib import Path
import stock_opportunity_agent.research.local_role_exchange as m
root = Path(sys.argv[1])
x = m.LocalRoleExchange(root, max_calls=1)
original = m._immutable
def slow(path, record):
    if path.parent.name == "inbox": time.sleep(0.15)
    return original(path, record)
m._immutable = slow
try:
    x.receive({"stage": "test", "messages": [{"role": "user", "content": sys.argv[2]}], "max_output_tokens": 1}, accounting_tokens=1)
except m.EvolutionControlFlow as e:
    print(type(e).__name__)
'''
        with tempfile.TemporaryDirectory() as directory:
            children = [subprocess.Popen([sys.executable, "-c", code, directory, str(i)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(2)]
            results = []
            for child in children:
                out, err = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, err)
                results.append(out.strip())
            self.assertEqual(sorted(results), ["LocalRoleBudgetExhausted", "LocalRoleRequestPending"])
            self.assertEqual(len(list((Path(directory) / "inbox").glob("*.json"))), 1)

    def test_cache_cannot_adopt_replaced_receipt_or_recreate_missing_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.client(root)
            with self.assertRaises(LocalRoleRequestPending) as raised:
                client.complete_json(**self.kwargs())
            pending = raised.exception.pending
            self.submit(client.local_role_exchange, pending, '{"answer":true}')
            client.complete_json(**self.kwargs())
            receipt_path = root / "local_roles/receipts" / f"{pending['request_hash']}.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["agent_id"] = "a-different-agent"
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValidationError, "cache"):
                self.client(root).complete_json(**self.kwargs())
            inbox = Path(pending["inbox_path"])
            inbox.unlink()
            with self.assertRaisesRegex(ValidationError, "missing its original inbox"):
                self.client(root).complete_json(**self.kwargs())
            self.assertFalse(inbox.exists())

    def test_receipt_hash_and_return_use_one_raw_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.client(root)
            with self.assertRaises(LocalRoleRequestPending) as raised:
                client.complete_json(**self.kwargs())
            pending = raised.exception.pending
            self.submit(client.local_role_exchange, pending, '{"answer":true}')
            request = json.loads((root / "requests" / f"{pending['request_hash']}.json").read_text())["request"]
            raw = Path(pending["outbox_path"])
            original = Path.read_bytes
            count = []

            def change_after_read(path):
                data = original(path)
                if path == raw:
                    count.append(True)
                    path.write_text('{"answer":false}')
                return data

            with patch.object(Path, "read_bytes", change_after_read):
                text, _usage = client.local_role_exchange.receive(request, accounting_tokens=1)
            self.assertEqual(text, '{"answer":true}')
            self.assertEqual(len(count), 1)

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
