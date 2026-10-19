"""Freeze legal priors and real routing requests without providing model answers."""
import json
from contextlib import nullcontext
from pathlib import Path
import re
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_reviewed_signal_stage import prepare, resume, samples, _save_exact
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import AgentStep, SignalSelectionDecision, _bounded_runtime_signal_selections
from stock_opportunity_agent.signal_library import SignalRegistry
from stock_opportunity_agent.llm.agent import AgentUsage
from tests.test_evolution_state_patch import PatchCaller

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
