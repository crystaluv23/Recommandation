"""Freeze legal priors and real routing requests without providing model answers."""
import json
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re
import shutil
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_reviewed_signal_stage import prepare, resume, samples, _save_exact
import run_reviewed_signal_stage as stage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import AgentStep, RuntimeBudgetExceeded, SignalSelectionDecision, _bounded_runtime_signal_selections
from stock_opportunity_agent.signal_library import SignalRegistry, SignalExecutor
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import ExactResponseCache
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
from stock_opportunity_agent.llm.agent import AgentUsage
from tests.test_evolution_state_patch import PatchCaller
from tests.evolution_runtime_test_support import ScriptedRoleCaller

EXPECTATIONS = ROOT / "reports/reviewed-signal-stage-expectations-20261019.json"


class ReviewedSignalStageTests(TestCase):
    def test_frozen_prior_projection_and_actual_masked_routing_pending(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "stage"
            prepared = prepare(root, EXPECTATIONS)
            self.assertEqual(prepared["role_dispatches"], 0)
            self.assertEqual(prepared["registry_refs"], 18)
            preflight = json.loads((root / "preflight.json").read_text())
            full_quote = json.loads(EXPECTATIONS.read_text())["samples"][0]["normalized_quote"]
            for name, expected_present in (("s01", True), ("s02", False)):
                row = next(row for row in preflight if row["sample_id"] == name and row["signal_ref"] == "customer_concentration:v2")
                views = [re.sub(r"\s+", " ", view["exact_text"]) for view in row["production_projection"]]
                self.assertEqual(any(full_quote in text for text in views), expected_present)
            progress = resume(root)
            self.assertEqual(len(progress["pending"]), 3)
            self.assertEqual(progress["outcomes"], [])
            self.assertEqual(progress["independent_receipts"], 0)
            for row in progress["pending"]:
                inbox = json.loads(Path(row["inbox_path"]).read_text())
                text = json.dumps(inbox["messages"])
                for forbidden in ("BMBL", "Bumble", "expected_semantics", "normalized_quote", "raw_start", "positive control"):
                    self.assertNotIn(forbidden, text)
            second = resume(root)
            self.assertEqual(progress["pending"], second["pending"])
            self.assertEqual(len(list((root / "exchange/inbox").glob("*.json"))), 3)

    def test_accepted_artifact_replay_retains_original_usage_and_refuses_changed_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage.json"
            _save_exact(path, {"state": {"decision": "continue"}, "usage": {"llm_calls": 1}})
            _save_exact(path, {"state": {"decision": "continue"}, "usage": {"llm_calls": 0}})
            self.assertEqual(json.loads(path.read_text())["usage"]["llm_calls"], 1)
            with self.assertRaises(ValidationError):
                _save_exact(path, {"state": {"decision": "finalize"}, "usage": {"llm_calls": 0}})

    def test_fact_free_priors_have_no_market_or_outcome_fields(self):
        rows = samples()
        self.assertEqual([row["sample_id"] for row in rows], ["s01", "s02", "s03"])
        for row in rows:
            self.assertEqual(row["basic_info"], {})
            self.assertNotIn("prediction_baseline", row)
            for field in ("hypotheses", "current_beliefs", "supporting_evidence", "resolved_questions"):
                self.assertEqual(row["prior_state"][field], [])

    def test_no_match_downstream_wiring_uses_real_validators_and_consumers(self):
        # Explicit scripted unit wiring only: this does not create independent
        # role receipts or establish actual routing/Signal/Reflect behavior.
        class UnitCaller(PatchCaller):
            request_hash_trace = []
            def anonymous_case(self, **_kwargs):
                return nullcontext()
        caller = UnitCaller()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "stage"
            prepare(root, EXPECTATIONS)
            with patch("run_reviewed_signal_stage.StructuredRoleClient", return_value=caller), patch(
                "run_reviewed_signal_stage.LLMSignalRetrievalAgent.select", return_value=AgentStep((), AgentUsage())):
                result = resume(root)
            self.assertEqual(result["pending"], [])
            self.assertEqual(result["independent_receipts"], 0)
            self.assertEqual([row["status"] for row in result["outcomes"]], ["accepted_requires_independent_review"] * 3)
            for name in ("s01", "s02", "s03"):
                runtime = json.loads((root / "samples" / name / "runtime.json").read_text())
                self.assertEqual(runtime["termination_trigger"], "no_signal_match")
                self.assertEqual(runtime["completed_signal_rounds"], 0)
                saved = json.loads((root / "samples" / name / "reflect.json").read_text())
                self.assertEqual(saved["metadata"], {})
                self.assertEqual(saved["execution_mode"], "not_called_due_to_no_signal_match")
            self.assertEqual(caller.calls, [])

    def test_real_signal_apply_reaches_pending_with_late_complete_disclosure(self):
        decision = SignalSelectionDecision.legacy("customer_concentration:v2")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "stage"
            prepare(root, EXPECTATIONS)
            with patch("run_reviewed_signal_stage.LLMSignalRetrievalAgent.select", return_value=AgentStep((decision,), AgentUsage())):
                result = resume(root)
            self.assertFalse(any(row["status"] == "stage_failed" for row in result["outcomes"]))
            row = next(row for row in result["pending"] if row["sample_id"] == "s01")
            inbox = json.loads(Path(row["inbox_path"]).read_text())
            text = re.sub(r"\s+", " ", json.dumps(inbox["messages"]))
            self.assertIn("there were no customers representing greater than 10% of total revenue", text)
            self.assertNotIn("BMBL", text)
            self.assertEqual(result["independent_receipts"], 0)

    def test_real_all_unavailable_finalize_has_no_reflect_call_or_authored_dispositions(self):
        class UnitCaller(PatchCaller):
            request_hash_trace = []
            def anonymous_case(self, **_kwargs):
                return nullcontext()
        caller = UnitCaller()
        decision = SignalSelectionDecision.legacy("negative_word_count:v2")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "stage"
            prepare(root, EXPECTATIONS)
            with patch("run_reviewed_signal_stage.StructuredRoleClient", return_value=caller), patch(
                "run_reviewed_signal_stage.LLMSignalRetrievalAgent.select", return_value=AgentStep((decision,), AgentUsage())):
                result = resume(root)
            self.assertEqual([row["status"] for row in result["outcomes"]], ["accepted_requires_independent_review"] * 3)
            self.assertEqual(caller.calls, [])
            for row in samples():
                saved = json.loads((root / "samples" / row["sample_id"] / "reflect.json").read_text())
                self.assertEqual(saved["metadata"], {})
                self.assertEqual(saved["execution_mode"], "not_called_due_to_production_guard")
                self.assertEqual(saved["state"]["next_information_needs"], row["prior_state"]["next_information_needs"])

    def test_shared_production_portfolio_caps_preserve_order(self):
        registry = SignalRegistry(ROOT / "runs/cold_start/minimal_rounds_v182_integrated/signals").freeze()
        refs = ["customer_concentration:v2", "guidance_acceleration:v3", "order_quality:v2", "negative_word_count:v2", "cash_reserves:v2"]
        decisions = tuple(SignalSelectionDecision.legacy(ref) for ref in refs)
        bounded = _bounded_runtime_signal_selections(decisions, registry, max_signals=4, max_llm_signals=2)
        self.assertEqual([row.signal_ref for row in bounded], [refs[0], refs[1], refs[3], refs[4]])


class ReviewedMeasurementSignalStageTests(TestCase):
    """Synthetic originals and no role answers: engineering checks only."""

    def setUp(self):
        network = patch("socket.socket", side_effect=AssertionError("network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def _read(self, path):
        return json.loads(path.read_text())

    def _fixture(self, directory):
        base = Path(directory)
        neutral = ROOT / "reports/fixtures/measurement-scope-20261020/inputs.json"
        inputs = self._read(neutral)
        for row in inputs["samples"]:
            local_paths = []
            for source in row["document_paths"]:
                target = base / Path(source).name
                shutil.copyfile(source, target)
                local_paths.append(str(target))
            row["document_paths"] = local_paths
        input_path = base / "measurement-inputs.json"
        input_path.write_text(json.dumps(inputs))
        oracle = base / "independent-oracle.json"
        expected = self._read(ROOT / "reports/reviewed-measurement-stage-expectations-20261020.json")
        expected["unit_oracle_sentinel"] = "ORACLE_MUST_NEVER_REACH_ROLE"
        oracle.write_text(json.dumps(expected))
        registry = base / "registry"
        shutil.copytree(ROOT / "runs/cold_start/minimal_rounds_v182_integrated/signals", registry)
        replacement = patch.object(stage, "REGISTRY", registry)
        replacement.start()
        self.addCleanup(replacement.stop)
        return base / "stage", input_path, oracle, registry

    def test_no_answer_preflight_preserves_actual_map_all_eligible_cards_and_repeated_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root, source, oracle, registry_path = self._fixture(directory)
            prepared = stage.prepare(root, oracle, measurement_inputs=source)
            self.assertEqual(prepared["role_dispatches"], 0)
            self.assertFalse(list(root.rglob("inbox/*.json")))
            captured = []
            select = stage.LLMSignalRetrievalAgent.select
            def observe(router, needs, frozen, context, **kwargs):
                self.assertEqual(router.request_token_budget, 512000)
                captured.append((tuple(needs), frozen, deepcopy(context), kwargs,
                                 dict(router.deterministic_functions)))
                return select(router, needs, frozen, context, **kwargs)
            with patch.object(stage.LLMSignalRetrievalAgent, "select", new=observe):
                first = stage.resume(root)
            self.assertEqual(first["outcomes"], [])
            self.assertEqual(len(first["pending"]), 3)
            self.assertEqual(first["independent_receipts"], 0)
            self.assertEqual(len(captured), 3)
            for pending, observed in zip(first["pending"], captured):
                needs, frozen, context, kwargs, functions = observed
                self.assertEqual(len(frozen.specs), 18)
                ref = "net_share_retirement_yoy:v2" if pending["sample_id"] == "m03" else "net_share_retirement_yoy:v3"
                spec = frozen.load_spec(ref)
                original_registry = SignalRegistry(registry_path)
                self.assertEqual(spec.to_dict(), original_registry.load_spec(ref).to_dict())
                self.assertEqual([item.ref for item in frozen.specs if item.signal_id == spec.signal_id], [ref])
                self.assertIsNotNone(functions[spec.function].__doc__)
                inbox = self._read(Path(pending["inbox_path"]))
                payload = json.loads(inbox["messages"][-1]["content"])
                caller = ScriptedRoleCaller([{"selections": []}])
                router = stage.LLMSignalRetrievalAgent(caller)
                router.set_evaluation_context(datetime.fromisoformat(self._read(source)["samples"][0]["prediction_time"]))
                router.set_deterministic_functions(SignalExecutor(frozen, RawInfoStore()).deterministic_functions)
                # The scripted answer is irrelevant; compare the actual outgoing
                # eligible catalog before the native response validator runs.
                try:
                    select(router, needs, frozen, context, **kwargs)
                except (ValidationError, AssertionError):
                    pass
                expected_cards = caller.calls[0]["payload"]["available_signal_cards"]
                self.assertEqual(payload["available_signal_cards"], expected_cards)
                card = next(card for card in expected_cards if card["signal_ref"] == ref)
                self.assertEqual(card.get("research_status", {}), original_registry.load_research_status(ref))
                self.assertEqual(card["measurement_scope"]["execution"]["callable_status"], "registered")
                self.assertEqual(card["measurement_scope"]["raw_retrieval"], spec.retrieval_policy.to_dict())
                self.assertNotIn("ORACLE_MUST_NEVER_REACH_ROLE", json.dumps(inbox["messages"]))
                self.assertNotIn("source_content_sha256", json.dumps(inbox["messages"]))
            inboxes = {path.name: path.read_bytes() for path in (root / "exchange/inbox").glob("*.json")}
            second = stage.resume(root)
            self.assertEqual(first["pending"], second["pending"])
            self.assertEqual(inboxes, {path.name: path.read_bytes() for path in (root / "exchange/inbox").glob("*.json")})
            self.assertFalse(list((root / "exchange/receipts").glob("*.json")))

    def test_native_correction_can_exceed_one_request_total_within_case_budget(self):
        """An explicitly scripted invalid answer is not fresh model evidence."""
        with tempfile.TemporaryDirectory() as directory:
            root, source, oracle, _registry = self._fixture(directory)
            stage.prepare(root, oracle, measurement_inputs=source)
            complete = stage.StructuredRoleClient.complete_json
            def padded(client, **kwargs):
                # Add only transport padding to this temporary offline wire;
                # keep the native role parser, correction and budget consumers.
                kwargs["payload"] = {**kwargs["payload"], "offline_budget_padding": "x" * 45000}
                return complete(client, **kwargs)
            with patch.object(stage.StructuredRoleClient, "complete_json", new=padded):
                first = stage.resume(root)
                original = next(row for row in first["pending"] if row["sample_id"] == "m01")
                raw = Path(original["outbox_path"])
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_text(json.dumps({"selections": "OFFLINE_INTENTIONALLY_INVALID_TYPE"}))
                LocalRoleExchange(root / "exchange", max_calls=24).submit(original["request_hash"],
                    agent_id="offline-scripted-invalid-answer-not-independent-model-evidence")
                corrected = stage.resume(root)
            self.assertEqual(corrected["outcomes"], [])
            retry = next(row for row in corrected["pending"] if row["sample_id"] == "m01")
            self.assertNotEqual(original["request_hash"], retry["request_hash"])
            reservations = []
            for pending in (original, retry):
                request = self._read(root / "requests" / (pending["request_hash"] + ".json"))["request"]
                reservations.append(len(json.dumps(request["messages"], ensure_ascii=False,
                    sort_keys=True, separators=(",", ":")).encode("utf-8")) + request["max_output_tokens"])
            self.assertTrue(all(value < 131072 for value in reservations), reservations)
            self.assertGreater(sum(reservations), 131072)
            self.assertLess(sum(reservations), 512000)
            self.assertEqual(len(list((root / "exchange/receipts").glob("*.json"))), 1)
            # Reuse these exact journals to distinguish the cumulative case
            # guard from the per-request ceiling, without another dispatch.
            contract = self._read(root / "contract.json")
            contract["limits"]["max_case_tokens"] = sum(reservations) - 1
            progress = stage._request_progress(root, contract, "m01")
            events = [{"event_type": "request_ready", "request_path": str(
                root / "requests" / (pending["request_hash"] + ".json"))}
                for pending in (original, retry)]
            progress(events[0])
            with self.assertRaises(RuntimeBudgetExceeded):
                progress(events[1])

    def test_measurement_source_and_exact_version_drift_fail_before_requests(self):
        for mutation in ("source", "version"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root, source, oracle, registry = self._fixture(directory)
                stage.prepare(root, oracle, measurement_inputs=source)
                if mutation == "source":
                    path = Path(self._read(source)["samples"][0]["document_paths"][0])
                else:
                    path = registry / "financial/net_share_retirement_yoy/versions/v2/spec.json"
                path.write_text(path.read_text() + "\n")
                with patch.object(stage, "StructuredRoleClient", side_effect=AssertionError("must reject before client")):
                    with self.assertRaises(ValidationError):
                        stage.resume(root)
                self.assertFalse(list((root / "requests").glob("*.json")))

    def test_unknown_source_or_version_and_implicit_measurement_mode_are_rejected(self):
        for mutation in ("source", "version", "implicit", "compatible_source"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root, source, oracle, _registry = self._fixture(directory)
                inputs = self._read(source)
                if mutation in ("source", "compatible_source"):
                    path = Path(inputs["samples"][0]["document_paths"][0])
                    document = self._read(path)
                    document["source_type"] = ("sec_company_facts" if mutation == "compatible_source"
                                               else "unreviewed_unknown_source")
                    path.write_text(json.dumps(document))
                elif mutation == "version":
                    inputs["samples"][2]["snapshot_ref"] = "net_share_retirement_yoy:v999"
                    source.write_text(json.dumps(inputs))
                kwargs = {} if mutation == "implicit" else {"measurement_inputs": source}
                if mutation == "compatible_source":
                    result = stage.prepare(root, oracle, **kwargs)
                    self.assertEqual(result["role_dispatches"], 0)
                    continue
                with self.assertRaises(ValidationError):
                    stage.prepare(root, oracle, **kwargs)
                self.assertFalse(list(root.rglob("inbox/*.json")))

    def test_request_hard_ceiling_precedes_cache_read_with_larger_case_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root, source, oracle, _registry = self._fixture(directory)
            stage.prepare(root, oracle, measurement_inputs=source)
            def oversized(router, *_args, **_kwargs):
                return router.caller.complete_json(stage="offline_measurement_hardcap",
                    system_prompt="Offline transport boundary fixture.", payload={"text": "x" * 132000},
                    allow_outcomes=False, temperature=0, max_output_tokens=20, max_request_tokens=512000)
            with patch.object(stage.LLMSignalRetrievalAgent, "select", new=oversized), patch.object(
                    ExactResponseCache, "load", side_effect=AssertionError("cache must not be read")):
                result = stage.resume(root)
            self.assertTrue(result["outcomes"])
            self.assertEqual([row["status"] for row in result["outcomes"]], ["control_budget_stopped"])
            self.assertIn("exact request/case reservation ceiling", result["outcomes"][0]["error"])
            self.assertTrue(list((root / "requests").glob("*.json")))
            self.assertFalse(list((root / "exchange/inbox").glob("*.json")))
            self.assertFalse(list((root / "exchange/receipts").glob("*.json")))
