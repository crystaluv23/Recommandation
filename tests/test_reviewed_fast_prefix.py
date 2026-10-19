"""Offline blind-prefix boundaries; fixtures are never independent role evidence."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_reviewed_fast_prefix as prefix
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, BlindPrediction, ResearchState, RuntimeBudgetExceeded, SignalSelectionDecision,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
from stock_opportunity_agent.research.local_role_exchange import (
    LocalRoleBudgetExhausted, LocalRoleExchange, LocalRoleRequestPending,
)
from stock_opportunity_agent.signal_library import SignalBatchResult


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
        text, usage = exchange.receive(request, accounting_tokens=0, allow_dispatch=False)
        atomic_write_json(root / "requests" / (digest + ".json"),
                          {"request_hash": digest, "request": request})
        atomic_write_json(root / "cache/responses" / (digest + ".json"), {
            "request_hash": digest, "response_id": "local-" + digest, "model": "independent-subagent",
            "json_output": {"unit_fixture": True}, "usage": usage,
            "raw_output": text, "decision_token_scores": None})
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

    def _assert_batch_observation(self, path, batch, request_hashes):
        # Compare canonical nested protocols, not dataclasses.asdict: a
        # resolution serializes gap as data_gap and a result has state/evidence.
        self.assertEqual(self._read(path), {
            "results": [item.to_dict() for item in batch.results],
            "signal_calls": batch.signal_calls,
            "usage": asdict(batch.usage),
            "resolutions": [item.to_dict() for item in batch.resolutions],
            "document_fingerprints": {ref: list(items) for ref, items in batch.document_fingerprints.items()},
            "skipped_unchanged_refs": list(batch.skipped_unchanged_refs),
            "request_hashes": request_hashes,
        })

    def test_real_executor_observer_preserves_resolved_missing_and_skipped_batches(self):
        # The earlier finalize-only native test never entered execute_batch.
        # This runs its real qualified snapshot, resolver and deterministic
        # functions; no model output or production role exchange is involved.
        if not prefix.SOURCE_INPUTS.is_file() or not prefix.REGISTRY.is_dir():
            self.skipTest("reviewed local source/Registry fixture unavailable")
        source = self._read(prefix.SOURCE_INPUTS)["reviewed_source_snapshot"]
        store = prefix.open_raw_info_store(source["root"], reviewed_snapshot=source)
        registry = prefix.SignalRegistry(prefix.REGISTRY).freeze()
        executor = prefix.SignalExecutor(registry, store.snapshot(),
                                        resolver=prefix.EvidenceResolver(store.snapshot()))
        native_execute = executor.execute_batch
        captured = []
        client = SimpleNamespace(request_hash_trace=["prior-unit-request"])

        def execute_and_capture(*args, **kwargs):
            batch = native_execute(*args, **kwargs)
            captured.append((batch, deepcopy(batch)))
            # Synthetic trace markers test exact slicing; they are not receipts.
            client.request_hash_trace.append(canonical_json_hash({"offline_batch": len(captured)}))
            return batch

        executor.execute_batch = execute_and_capture
        refs = ("price_momentum_126d:v2", "negative_word_count:v2")
        kwargs = {"company_id": prefix.COMPANY, "identity": prefix.IDENTITY,
                  "as_of": datetime.fromisoformat("2025-09-30T00:00:00+00:00")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix._observe(executor, "execute_batch", "signal_group", root, client)
            first = executor.execute_batch(refs, **kwargs)
            self.assertIsInstance(first, SignalBatchResult)
            self.assertIs(first, captured[0][0])
            self.assertEqual(first, captured[0][1])
            self.assertEqual(first.signal_calls, 2)
            self.assertEqual([resolution.status for resolution in first.resolutions], ["resolved", "unresolved"])
            self.assertTrue(first.results[0].supporting_evidence)
            self.assertIsNotNone(first.resolutions[1].gap)
            self.assertTrue(first.document_fingerprints[refs[0]])
            self.assertEqual(first.document_fingerprints[refs[1]], ())
            self._assert_batch_observation(root / "observations/signal_group_00.json", first,
                                           client.request_hash_trace[1:2])
            skipped = executor.execute_batch(refs, prior_fingerprints=first.document_fingerprints, **kwargs)
            self.assertIs(skipped, captured[1][0])
            self.assertEqual(skipped, captured[1][1])
            self.assertEqual(skipped.results, ())
            self.assertEqual(skipped.signal_calls, 0)
            self.assertEqual(skipped.skipped_unchanged_refs, refs)
            self.assertEqual(skipped.resolutions, first.resolutions)
            self.assertEqual(skipped.document_fingerprints, first.document_fingerprints)
            self._assert_batch_observation(root / "observations/signal_group_01.json", skipped,
                                           client.request_hash_trace[2:3])
            empty = executor.execute_batch((), **kwargs)
            self.assertIs(empty, captured[2][0])
            self.assertEqual(empty, captured[2][1])
            self.assertEqual(empty, SignalBatchResult(results=(), signal_calls=0))
            self._assert_batch_observation(root / "observations/signal_group_02.json", empty,
                                           client.request_hash_trace[3:4])

    def test_signal_batch_observer_retains_nonzero_usage_without_mutating_return(self):
        batch = SignalBatchResult(results=(), signal_calls=0,
                                  usage=AgentUsage(llm_calls=2, tokens=41, cost=0.001),
                                  document_fingerprints={"unit:v1": ("doc:hash",)},
                                  skipped_unchanged_refs=("unit:v1",))
        before = deepcopy(batch)
        producer = SimpleNamespace(execute=lambda: batch)
        client = SimpleNamespace(request_hash_trace=[])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix._observe(producer, "execute", "signal_group", root, client)
            self.assertIs(producer.execute(), batch)
            self.assertEqual(batch, before)
            self._assert_batch_observation(root / "observations/signal_group_00.json", batch, [])

    def test_agent_step_tuple_observer_retains_canonical_values_metadata_and_trace(self):
        # Offline routing fixture protects the existing family while adding
        # SignalBatchResult support; no scripted choice enters a live prefix.
        decisions = tuple(SignalSelectionDecision.legacy(ref)
                          for ref in ("price_momentum_126d:v2", "negative_word_count:v2"))
        step = AgentStep(decisions, AgentUsage(llm_calls=1, tokens=17),
                         metadata={"unit_only": True, "nested": {"values": [1, None, False]}})
        before = deepcopy(step)
        client = SimpleNamespace(request_hash_trace=["prior-unit-request"])

        def select():
            client.request_hash_trace.extend(("new-unit-request", "new-unit-correction"))
            return step

        producer = SimpleNamespace(select=select)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix._observe(producer, "select", "routing", root, client)
            self.assertIs(producer.select(), step)
            self.assertEqual(step, before)
            self.assertEqual(self._read(root / "observations/routing_00.json"), {
                "value": [decision.to_dict() for decision in decisions],
                "metadata": step.metadata, "usage": asdict(step.usage),
                "request_hashes": ["new-unit-request", "new-unit-correction"],
            })

    def test_unknown_observer_result_is_typed_rejected_without_partial_artifact(self):
        producer = SimpleNamespace(execute=lambda: SimpleNamespace(unit_only=True))
        client = SimpleNamespace(request_hash_trace=[])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix._observe(producer, "execute", "unknown", root, client)
            with self.assertRaises(ValidationError):
                producer.execute()
            self.assertFalse((root / "observations").exists())

    def _unit_exchange_answer(self, exchange, index):
        """Create synthetic receipt data only under the caller's temp root."""
        request = {"stage": "unit-only-stage", "messages": [{"role": "user", "content": f"unit fixture {index}"}],
                   "max_output_tokens": 20, "output_contract": {"type": "object"}}
        with self.assertRaises(LocalRoleRequestPending) as caught:
            exchange.receive(request, accounting_tokens=0)
        pending = caught.exception.pending
        raw = Path(pending["outbox_path"])
        raw.parent.mkdir(parents=True, exist_ok=True)
        output = {"unit_fixture": index}
        raw.write_text(json.dumps(output))
        exchange.submit(pending["request_hash"], agent_id="offline-unit-fixture-not-independent-evidence")
        reservation = len(json.dumps(request["messages"], ensure_ascii=False,
                                     sort_keys=True, separators=(",", ":")).encode("utf-8")) + request["max_output_tokens"]
        text, usage = exchange.receive(request, accounting_tokens=reservation, allow_dispatch=False)
        return request, pending["request_hash"], text, output, usage

    def _synthetic_failed_parent(self, directory):
        """Use a disposable real Git source and native receipt verification."""
        base = Path(directory).resolve()
        repository = base / "unit-source"
        code = repository / "src/unit.py"
        code.parent.mkdir(parents=True)
        code.write_text("# offline immutable source fixture\n")
        for args in (("init", "-q"), ("add", "src/unit.py"),
                     ("-c", "user.name=Offline Unit", "-c", "user.email=offline@example.invalid",
                      "-c", "commit.gpgsign=false", "commit", "-qm", "unit fixture")):
            subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True)
        commit = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                check=True, capture_output=True, text=True).stdout.strip()
        root = base / "unit-parent"
        exchange = LocalRoleExchange(root / "exchange", max_calls=32)
        request, digest, raw, output, usage = self._unit_exchange_answer(exchange, 0)
        atomic_write_json(root / "requests" / (digest + ".json"), {"request_hash": digest, "request": request})
        atomic_write_json(root / "cache/responses" / (digest + ".json"), {
            "request_hash": digest, "response_id": "local-" + digest, "model": "independent-subagent",
            "json_output": output, "usage": usage, "raw_output": raw, "decision_token_scores": None})
        atomic_write_json(root / "observations/initialize_00.json", {"unit_fixture": True, "request_hashes": [digest]})
        inputs, contract, expected, preflight = {"unit_input": True}, {"max_local_calls": 32}, {}, {}
        for name, value in (("inputs", inputs), ("contract", contract),
                            ("expectations", expected), ("preflight", preflight)):
            atomic_write_json(root / (name + ".json"), value)
        atomic_write_json(root / "failure.json", {
            "error_type": "AttributeError", "error": "'SignalBatchResult' object has no attribute 'to_dict'"})
        manifest = {"code_files": [prefix.binding(code)], "originals": [], "registry_files": [],
                    "contract_hash": canonical_json_hash(contract)}
        manifest["manifest_hash"] = canonical_json_hash(manifest)
        atomic_write_json(root / "manifest.json", manifest)
        return root, repository, commit, (inputs, contract, expected, preflight), digest

    def test_continuation_parent_verifies_git_receipt_cache_and_exact_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root, repository, commit, payloads, digest = self._synthetic_failed_parent(directory)
            before = self._files(root)
            with patch.object(prefix, "REPO", repository):
                lineage = prefix._validate_parent(root, commit, *payloads)
            self.assertEqual(before, self._files(root))
            self.assertEqual(lineage["inherited_request_hashes"], [digest])
            self.assertEqual(lineage["inherited_receipts"], 1)
            self.assertEqual(lineage["total_request_ceiling"], 32)
            self.assertEqual(lineage["maximum_new_requests"], 31)
            self.assertTrue(lineage["historical_exact_reuse_not_fresh_model_behavior"])
            self.assertEqual(lineage["parent_files"], prefix._immutable_artifacts(root))
            copied = {row["relative_path"]: row for row in lineage["copied_files"]}
            for name in (f"requests/{digest}.json", f"cache/responses/{digest}.json",
                         f"exchange/inbox/{digest}.json", f"exchange/outbox/{digest}.txt",
                         f"exchange/receipts/{digest}.json", "observations/initialize_00.json"):
                self.assertIn(name, copied)
                self.assertEqual(prefix.binding(root / name)["sha256"], copied[name]["sha256"])
            self.assertNotIn("failure.json", copied)
            self.assertNotIn("manifest.json", copied)

    def test_continuation_parent_rejects_changed_hash_cache_code_and_failure(self):
        expected_errors = {"request_hash": "request journal hash changed",
                           "cache": "parent cache differs from verified original response",
                           "code": "original artifact changed",
                           "failure": "restricted to the recorded observation failure"}
        for target, expected_error in expected_errors.items():
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root, repository, commit, payloads, digest = self._synthetic_failed_parent(directory)
                if target == "request_hash":
                    path = root / "requests" / (digest + ".json")
                    value = self._read(path)
                    value["request_hash"] = "0" * 64
                    atomic_write_json(path, value)
                elif target == "cache":
                    path = root / "cache/responses" / (digest + ".json")
                    value = self._read(path)
                    value["json_output"] = {"unit_tampered": True}
                    atomic_write_json(path, value)
                elif target == "code":
                    (repository / "src/unit.py").write_text("# changed source\n")
                else:
                    atomic_write_json(root / "failure.json", {"error_type": "OtherError", "error": "unit fixture"})
                before = self._files(root)
                with patch.object(prefix, "REPO", repository), self.assertRaisesRegex(ValidationError, expected_error):
                    prefix._validate_parent(root, commit, *payloads)
                self.assertEqual(before, self._files(root))

    def test_continuation_inherited_prefix_mismatch_and_total_call_ceiling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "continuation/exchange"
            original = LocalRoleExchange(root, max_calls=32)
            inherited = [self._unit_exchange_answer(original, index)[:2] for index in range(31)]
            exchange = prefix._ContinuationExchange(root, max_calls=32,
                                                    inherited=[digest for _request, digest in inherited])
            changed = deepcopy(inherited[0][0])
            changed["messages"][0]["content"] = "changed inherited unit request"
            before = self._files(root)
            with self.assertRaisesRegex(ValidationError, "changed an inherited production request"):
                exchange.receive(changed, accounting_tokens=0)
            self.assertEqual(before, self._files(root))
            for request, _digest in inherited:
                exchange.receive(request, accounting_tokens=0, allow_dispatch=False)
            self.assertEqual(before, self._files(root))
            next_request = deepcopy(inherited[0][0])
            next_request["messages"][0]["content"] = "new unit request at inherited total 32"
            with self.assertRaises(LocalRoleRequestPending):
                exchange.receive(next_request, accounting_tokens=0)
            self.assertEqual(len(list((root / "inbox").glob("*.json"))), 32)
            next_request["messages"][0]["content"] = "forbidden unit request 33"
            before = self._files(root)
            with self.assertRaises(LocalRoleBudgetExhausted):
                exchange.receive(next_request, accounting_tokens=0)
            self.assertEqual(before, self._files(root))

    def _native_completed_checkpoint_with_budget_journal(self, directory):
        """Produce a real completion plus native pre-dispatch budget rejection."""
        root = self._prepare(directory)
        digests = {}
        prediction = BlindPrediction(False, "insufficient_information", None, "low",
                                     ("Offline checkpoint fixture.",), (), "unit-session")

        def predict(_context):
            client = prefix.StructuredRoleClient(registration=prefix.get_model("independent-subagent"),
                contract=prefix.StageContract(self._read(root / "contract.json")), workspace=root,
                local_role_exchange=LocalRoleExchange(root / "exchange", max_calls=32),
                ledger=prefix.ExternalAttemptLedger(root / "unused_external_attempts.json",
                                                   max_attempts=1, max_total_cost=0.01),
                allow_external=False, environ={})
            kwargs = {"stage": "unit_completed_response", "system_prompt": "Offline unit fixture.",
                      "payload": {"unit_fixture": True}, "allow_outcomes": False, "max_output_tokens": 20}
            with self.assertRaises(LocalRoleRequestPending) as caught:
                client.complete_json(**kwargs)
            pending = caught.exception.pending
            raw = Path(pending["outbox_path"])
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text('{"unit_fixture":true}')
            client.local_role_exchange.submit(pending["request_hash"],
                agent_id="offline-unit-fixture-not-independent-evidence")
            output, _usage = client.complete_json(**kwargs)
            self.assertEqual(output, {"unit_fixture": True})
            digests["answered"] = pending["request_hash"]
            with self.assertRaises(RuntimeBudgetExceeded):
                client.complete_json(**{**kwargs, "stage": "unit_budget_before_dispatch"}, max_request_tokens=1)
            digests["undispatched"] = client.request_hash_trace[-1]
            self.assertNotEqual(digests["answered"], digests["undispatched"])
            return AgentStep(prediction, AgentUsage())

        with patch.object(prefix.LLMResearchController, "initialize", return_value=AgentStep(
                ResearchState(decision="finalize"), AgentUsage())), patch.object(
                LLMBlindPredictor, "predict", side_effect=predict), patch.object(
                LLMBlindPredictor, "reflect", side_effect=AssertionError("post-label role forbidden")):
            result = prefix.resume(root)
        self.assertEqual(result["status"], "prediction_persisted_before_labels_requires_independent_review")
        self.assertEqual(result["independent_receipts"], 1)
        self.assertEqual(len(list((root / "requests").glob("*.json"))), 2)
        for path in self._response_paths(root, digests["undispatched"]):
            self.assertFalse(path.exists())
        return root, digests

    def _response_paths(self, root, digest):
        return (root / "exchange/inbox" / (digest + ".json"),
                root / "exchange/outbox" / (digest + ".txt"),
                root / "exchange/receipts" / (digest + ".json"),
                root / "cache/responses" / (digest + ".json"))

    def _rebind_completion_inventory(self, root):
        completion = self._read(root / "completion.json")
        completion.pop("completion_hash")
        completion["immutable_artifacts"] = prefix._immutable_artifacts(root)
        completion["completion_hash"] = canonical_json_hash(completion)
        atomic_write_json(root / "completion.json", completion)

    def _restore_unit_files(self, root, saved):
        for path in root.rglob("*"):
            if path.is_file() and str(path.relative_to(root)) not in saved:
                path.unlink()
        for name, contents in saved.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)

    def test_completed_native_checkpoint_restores_with_undispatched_budget_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            root, digests = self._native_completed_checkpoint_with_budget_journal(directory)
            completion = self._read(root / "completion.json")
            bound = {row["path"]: row["sha256"] for row in completion["immutable_artifacts"]}
            for digest in digests.values():
                row = prefix.binding(root / "requests" / (digest + ".json"))
                self.assertEqual(bound[row["path"]], row["sha256"])
            before = self._files(root)
            received = []
            original = LocalRoleExchange.receive

            def receive(exchange, request, **kwargs):
                received.append((canonical_json_hash(request), kwargs))
                self.assertFalse(kwargs["allow_dispatch"])
                return original(exchange, request, **kwargs)

            with patch.object(LocalRoleExchange, "receive", new=receive), patch.object(
                    prefix, "execute_information_plan", side_effect=AssertionError("no native re-execution")):
                result = prefix.resume(root)
            self.assertEqual(received, [(digests["answered"], {"accounting_tokens": 0, "allow_dispatch": False})])
            self.assertEqual(result, {**completion["result"], "restored_without_execution": True,
                                      "immutable_artifacts_unchanged": True})
            self.assertEqual(before, self._files(root))

    def test_completed_budget_journal_rejects_all_partial_or_orphan_response_families(self):
        with tempfile.TemporaryDirectory() as directory:
            root, digests = self._native_completed_checkpoint_with_budget_journal(directory)
            baseline = self._files(root)
            # Single orphan on an undispatched journal; one missing member of
            # an answered set; orphan artifacts with no request journal at all.
            for family in ("undispatched_orphan", "answered_partial", "unjournaled_orphan"):
                for index in range(4):
                    with self.subTest(family=family, response_member=index):
                        try:
                            if family == "answered_partial":
                                self._response_paths(root, digests["answered"])[index].unlink()
                            else:
                                digest = digests["undispatched"] if family == "undispatched_orphan" else "f" * 64
                                destination = self._response_paths(root, digest)[index]
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                destination.write_bytes(self._response_paths(root, digests["answered"])[index].read_bytes())
                            # Deliberately rebind the outer map so this tests
                            # typed inner inventory validation, not hash alone.
                            self._rebind_completion_inventory(root)
                            before = self._files(root)
                            manifest_hash = self._read(root / "completion.json")["manifest_hash"]
                            with self.assertRaises(ValidationError):
                                prefix._completed_restore(root, manifest_hash, {"max_local_calls": 32})
                            self.assertEqual(before, self._files(root))
                        finally:
                            self._restore_unit_files(root, baseline)

    def test_completed_budget_journal_hash_and_filename_are_verified_before_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root, digests = self._native_completed_checkpoint_with_budget_journal(directory)
            baseline = self._files(root)
            for target in ("answered_content", "undispatched_content", "undispatched_hash", "undispatched_filename"):
                with self.subTest(target=target):
                    try:
                        digest = digests["answered"] if target == "answered_content" else digests["undispatched"]
                        path = root / "requests" / (digest + ".json")
                        record = self._read(path)
                        if target.endswith("content"):
                            record["request"]["messages"][0]["content"] += " unit tamper"
                            atomic_write_json(path, record)
                        elif target == "undispatched_hash":
                            record["request_hash"] = "0" * 64
                            atomic_write_json(path, record)
                        else:
                            path.rename(root / "requests" / ("0" * 64 + ".json"))
                        self._rebind_completion_inventory(root)
                        before = self._files(root)
                        manifest_hash = self._read(root / "completion.json")["manifest_hash"]
                        with self.assertRaises(ValidationError):
                            prefix._completed_restore(root, manifest_hash, {"max_local_calls": 32})
                        self.assertEqual(before, self._files(root))
                    finally:
                        self._restore_unit_files(root, baseline)

    def test_completed_budget_journal_remains_in_exact_immutable_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root, digests = self._native_completed_checkpoint_with_budget_journal(directory)
            baseline = self._files(root)
            for action in ("remove", "change", "add"):
                with self.subTest(action=action):
                    try:
                        path = root / "requests" / (digests["undispatched"] + ".json")
                        if action == "remove":
                            path.unlink()
                        elif action == "change":
                            path.write_text("{}")
                        else:
                            (root / "requests/unbound-extra.json").write_text("{}")
                        before = self._files(root)
                        manifest_hash = self._read(root / "completion.json")["manifest_hash"]
                        with self.assertRaisesRegex(ValidationError, "artifacts changed or missing"):
                            prefix._completed_restore(root, manifest_hash, {"max_local_calls": 32})
                        self.assertEqual(before, self._files(root))
                    finally:
                        self._restore_unit_files(root, baseline)
