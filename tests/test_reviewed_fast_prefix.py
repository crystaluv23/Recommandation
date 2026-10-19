"""Offline blind-prefix boundaries; fixtures are never independent role evidence."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_reviewed_fast_prefix as prefix
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, BlindPrediction, ResearchState,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
from stock_opportunity_agent.research.local_role_exchange import (
    LocalRoleExchange, LocalRoleRequestPending,
)


class ReviewedFastPrefixTests(TestCase):
    def setUp(self):
        self.network = patch("socket.socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def _prepare(self, directory):
        if not prefix.SOURCE_INPUTS.is_file() or not prefix.REGISTRY.is_dir():
            self.skipTest("reviewed local source/Registry fixture unavailable")
        base = Path(directory)
        expected = base / "unit-only-oracle.json"
        expected.write_text(json.dumps({"fixed_denominator": 1, "sample": {"sample_id": "s01"},
                                        "unit_only_sentinel": "NEVER_PASS_THIS_TO_A_ROLE"}))
        code = base / "unit-frozen-code.py"
        code.write_text("# isolated binding prevents concurrent implementation edits affecting this fixture\n")
        root = base / "prefix"
        with patch.object(prefix, "_code_bindings", return_value=[prefix.binding(code)]):
            result = prefix.prepare(root, expected)
        self.assertEqual(result["role_answers"], 0)
        return root

    def _read(self, path):
        return json.loads(path.read_text())

    def _files(self, root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def _completion(self, root, *, manifest_hash="unit-manifest"):
        """Build a checkpoint entirely in TemporaryDirectory, without a model."""
        result = {"status": "unit_fixture", "completed_fast_round": False,
                  "completed_trajectory": False, "independent_receipts": 1}
        completion = {"manifest_hash": manifest_hash, "result": result,
                      "immutable_artifacts": prefix._immutable_artifacts(root)}
        completion["completion_hash"] = canonical_json_hash(completion)
        atomic_write_json(root / "completion.json", completion)
        return result

    def _receipt_fixture(self, root):
        """Write only synthetic temporary exchange data; never read a live outbox."""
        exchange = LocalRoleExchange(root / "exchange", max_calls=32)
        request = {"stage": "unit-only-stage", "messages": [{"role": "user", "content": "unit fixture"}],
                   "max_output_tokens": 20, "output_contract": {"type": "object"}}
        digest = canonical_json_hash(request)
        with self.assertRaises(LocalRoleRequestPending) as caught:
            exchange.receive(request, accounting_tokens=0)
        raw = Path(caught.exception.pending["outbox_path"])
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text('{"unit_fixture":true}')
        exchange.submit(digest, agent_id="offline-unit-fixture-not-independent-evidence")
        atomic_write_json(root / "requests" / (digest + ".json"),
                          {"request_hash": digest, "request": request})
        atomic_write_json(root / "prediction.json", {"unit_fixture": True})
        self._completion(root)
        return digest

    def test_frozen_limits_and_real_pending_anonymous_request_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._prepare(directory)
            contract = self._read(root / "contract.json")
            self.assertEqual(contract["max_local_calls"], 32)
            self.assertFalse(contract["parallel_jev_decisions"])
            self.assertEqual(contract["runtime_limits"], {
                "max_signal_rounds": 2, "max_signal_calls": 4, "max_llm_calls": 24,
                "max_tokens": 256000, "max_cost": 20.0, "max_signals_per_round": 4,
                "max_llm_signals_per_round": 2, "finalization_token_reserve": 64000})
            self.assertEqual(contract["limits"]["max_structured_corrections"], 1)
            self.assertEqual(contract["external_llm_calls_authorized"], 0)
            self.assertEqual(contract["readonly_data_requests_authorized"], 0)
            first = prefix.resume(root)
            self.assertEqual(first["status"], "pending_independent_role")
            self.assertEqual(first["independent_receipts"], 0)
            self.assertEqual(first["pending"][0]["stage"], "research_controller_initialize")
            wire = Path(first["pending"][0]["inbox_path"]).read_text()
            for forbidden in ("BMBL", "Bumble", "cik_0001830043", "NEVER_PASS_THIS_TO_A_ROLE"):
                self.assertNotIn(forbidden, wire)
            self.assertFalse((root / "prediction.json").exists())
            self.assertFalse((root / "completion.json").exists())
            before = self._files(root)
            second = prefix.resume(root)
            self.assertEqual(first, second)
            self.assertEqual(before, self._files(root))
            self.assertEqual(len(list((root / "exchange/inbox").glob("*.json"))), 1)

    def test_frozen_input_contract_and_code_drift_reject_before_dispatch(self):
        for target in ("inputs.json", "contract.json", "unit-frozen-code.py"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = self._prepare(directory)
                path = root / target if target.endswith(".json") else Path(directory) / target
                if target == "inputs.json":
                    value = self._read(path)
                    value["sample"]["prediction_time"] = "2025-10-01T00:00:00+00:00"
                    atomic_write_json(path, value)
                elif target == "contract.json":
                    value = self._read(path)
                    value["max_local_calls"] += 1
                    atomic_write_json(path, value)
                else:
                    path.write_text("# changed frozen implementation\n")
                with patch.object(prefix, "StructuredRoleClient") as client:
                    with self.assertRaises(ValidationError):
                        prefix.resume(root)
                    client.assert_not_called()
                self.assertFalse((root / "exchange").exists())

    def test_registry_learning_identity_is_checked_beyond_envelope_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._prepare(directory)
            inputs = self._read(root / "inputs.json")
            inputs["learning_hash"] = "0" * 64
            contract = self._read(root / "contract.json")
            contract["input_hash"] = canonical_json_hash(inputs)
            manifest = self._read(root / "manifest.json")
            manifest.pop("manifest_hash")
            manifest["contract_hash"] = canonical_json_hash(contract)
            manifest["manifest_hash"] = canonical_json_hash(manifest)
            for name, value in (("inputs", inputs), ("contract", contract), ("manifest", manifest)):
                atomic_write_json(root / (name + ".json"), value)
            with patch.object(prefix, "StructuredRoleClient") as client:
                with self.assertRaisesRegex(ValidationError, "Registry specs/learning identity changed"):
                    prefix.resume(root)
                client.assert_not_called()
            self.assertFalse((root / "exchange").exists())

    def test_native_sink_persists_and_reads_back_before_dedicated_boundary(self):
        # Only model answers are fixtures. Native execute_information_plan,
        # projection, observers, sink, durable readback and boundary are real.
        state = ResearchState(decision="finalize")
        prediction = BlindPrediction(False, "insufficient_information", None, "low",
                                     ("Offline boundary fixture.",), ("No model evidence.",), "unit-session")
        initial = AgentStep(state, AgentUsage(llm_calls=1, tokens=3))
        predicted = AgentStep(prediction, AgentUsage(llm_calls=4, tokens=7))
        original_state = deepcopy(state.to_dict())
        with tempfile.TemporaryDirectory() as directory:
            root = self._prepare(directory)
            seen = []
            original_read = prefix.read_json

            def read(path):
                value = original_read(path)
                if Path(path) == root / "prediction.json":
                    seen.append(deepcopy(value))
                return value

            def predict(context):
                self.assertEqual(context["runtime_termination"], {
                    "phase": "prediction_ready", "stop_reason": "finalized", "termination_trigger": None})
                self.assertFalse((root / "prediction.json").exists())
                return predicted

            with patch.object(prefix.LLMResearchController, "initialize", return_value=initial), patch.object(
                    LLMBlindPredictor, "predict", side_effect=predict), patch.object(
                    LLMBlindPredictor, "reflect", side_effect=AssertionError("post-label role forbidden")), patch.object(
                    prefix, "read_json", side_effect=read):
                result = prefix.resume(root)
            self.assertEqual(result["status"], "prediction_persisted_before_labels_requires_independent_review")
            self.assertEqual(result["ground_truth_reads"], 0)
            self.assertFalse(result["completed_trajectory"])
            self.assertFalse(result["completed_fast_round"])
            self.assertEqual(result["independent_receipts"], 0)
            self.assertEqual(len(seen), 2)  # sink readback, then ground-truth boundary verification
            self.assertEqual(seen[0], seen[1])
            self.assertEqual(seen[0]["prediction"], prediction.to_dict())
            self.assertEqual(state.to_dict(), original_state)
            saved = self._read(root / "observations/initialize_00.json")
            self.assertEqual(saved["value"], original_state)
            self.assertEqual(saved["usage"], asdict(initial.usage))
            self.assertEqual(self._read(root / "completion.json")["result"],
                             {k: v for k, v in result.items()})
            before = self._files(root)
            with patch.object(prefix, "execute_information_plan", side_effect=AssertionError("no re-execution")):
                restored = prefix.resume(root)
            self.assertTrue(restored["restored_without_execution"])
            self.assertEqual(before, self._files(root))

    def test_sink_readback_mismatch_never_creates_completed_checkpoint(self):
        prediction = BlindPrediction(False, "insufficient_information", None, "low",
                                     ("Offline fixture.",), (), "unit-session")
        with tempfile.TemporaryDirectory() as directory:
            root = self._prepare(directory)
            original_read = prefix.read_json

            def read(path):
                if Path(path) == root / "prediction.json":
                    return {"unit_corrupted_readback": True}
                return original_read(path)

            with patch.object(prefix.LLMResearchController, "initialize", return_value=AgentStep(
                    ResearchState(decision="finalize"), AgentUsage())), patch.object(
                    LLMBlindPredictor, "predict", return_value=AgentStep(prediction, AgentUsage())), patch.object(
                    prefix, "read_json", side_effect=read):
                result = prefix.resume(root)
            self.assertEqual(result["status"], "prefix_failed")
            self.assertEqual(result["error_type"], "ValidationError")
            self.assertIn("sink readback mismatch", result["error"])
            self.assertFalse((root / "completion.json").exists())

    def test_completed_restore_validates_receipts_with_dispatch_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._receipt_fixture(root)
            before = self._files(root)
            original = LocalRoleExchange.receive
            calls = []

            def receive(exchange, request, **kwargs):
                calls.append(kwargs)
                return original(exchange, request, **kwargs)

            with patch.object(LocalRoleExchange, "receive", new=receive):
                result = prefix._completed_restore(root, "unit-manifest", {"max_local_calls": 32})
            self.assertTrue(result["restored_without_execution"])
            self.assertEqual(calls, [{"accounting_tokens": 0, "allow_dispatch": False}])
            self.assertEqual(before, self._files(root))

    def test_completed_checkpoint_rejects_changed_missing_and_extra_artifacts(self):
        for target in ("prediction", "raw", "receipt", "missing", "extra"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                digest = self._receipt_fixture(root)
                if target == "prediction":
                    atomic_write_json(root / "prediction.json", {"changed": True})
                elif target == "raw":
                    (root / "exchange/outbox" / (digest + ".txt")).write_text('{"changed":true}')
                elif target == "receipt":
                    atomic_write_json(root / "exchange/receipts" / (digest + ".json"), {"changed": True})
                elif target == "missing":
                    (root / "prediction.json").unlink()
                else:
                    (root / "unbound-extra.json").write_text("{}")
                before = self._files(root)
                with patch.object(LocalRoleExchange, "receive") as receive:
                    with self.assertRaisesRegex(ValidationError, "artifacts changed or missing"):
                        prefix._completed_restore(root, "unit-manifest", {"max_local_calls": 32})
                    receive.assert_not_called()
                self.assertEqual(before, self._files(root))

    def test_completed_restore_rechecks_native_receipt_even_with_rebound_inventory(self):
        for target in ("raw", "receipt", "missing_inbox", "missing_receipt"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                digest = self._receipt_fixture(root)
                if target == "raw":
                    (root / "exchange/outbox" / (digest + ".txt")).write_text('{"changed":true}')
                elif target == "receipt":
                    path = root / "exchange/receipts" / (digest + ".json")
                    receipt = self._read(path)
                    receipt["agent_id"] = ""
                    atomic_write_json(path, receipt)
                elif target == "missing_inbox":
                    (root / "exchange/inbox" / (digest + ".json")).unlink()
                else:
                    (root / "exchange/receipts" / (digest + ".json")).unlink()
                self._completion(root)
                before = self._files(root)
                with self.assertRaises(ValidationError):
                    prefix._completed_restore(root, "unit-manifest", {"max_local_calls": 32})
                self.assertEqual(before, self._files(root))
