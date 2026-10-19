"""Production bootstrap wiring; scripted replies never count as role evidence."""
from contextlib import nullcontext
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_reviewed_initial_stage import prepare, resume
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState
from tests.test_evolution_state_patch import PatchCaller


class ReviewedInitialStageTests(TestCase):
    def _prepare(self, directory):
        root = Path(directory) / "stage"
        expected = Path(directory) / "unit-only-expectations.json"
        expected.write_text(json.dumps({"unit_wiring_only": True, "samples": [{"sample_id": "s01"}, {"sample_id": "s02"}]}))
        result = prepare(root, expected)
        self.assertEqual(result["role_dispatches"], 0)
        return root

    def test_actual_projection_masked_initialize_pending_and_idempotency(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), tempfile.TemporaryDirectory() as directory:
            root = self._prepare(directory)
            first = resume(root)
            self.assertEqual(first["outcomes"], [])
            self.assertEqual(len(first["pending"]), 2)
            self.assertEqual(first["independent_receipts"], 0)
            for pending, expected_status, expected_accn in zip(first["pending"],
                    ("partial_context_budget", "complete"), ("000162828025038861", "000119312525146199")):
                inbox = json.loads(Path(pending["inbox_path"]).read_text())
                self.assertEqual(pending["stage"], "research_controller_initialize")
                wire = json.dumps(inbox["messages"])
                for forbidden in ("Bumble", "BMBL", "unit_wiring_only", "expected_semantics"):
                    self.assertNotIn(forbidden, wire)
                payload = json.loads(inbox["messages"][1]["content"])
                self.assertNotIn("evaluation_anchor", payload)
                self.assertNotIn("prediction_baseline", payload)
                rows = payload["basic_info"]["requests"]
                self.assertEqual(rows[0]["projection_status"], expected_status)
                if pending["sample_id"] == "s02":
                    # Existing F2 fulfillment gap is preserved, not certified.
                    self.assertEqual(rows[0]["status"], "resolved")
                    self.assertIsNone(rows[0]["data_gap"])
                    self.assertIn("FORM 8-K", wire)
                for req in rows[1:]:
                    self.assertEqual(req["status"], "unresolved")
                    self.assertIsNotNone(req["data_gap"])
                audit = json.loads((root / "samples" / pending["sample_id"] / "basic_info.json").read_text())
                self.assertTrue(all(expected_accn in row["document_id"] for row in audit["projection_lineage"]["entries"]))
            second = resume(root)
            self.assertEqual(first, second)
            self.assertEqual(len(list((root / "exchange/inbox").glob("*.json"))), 2)

    def test_scripted_initialize_acceptance_replay_uses_real_native_parser(self):
        class UnitCaller(PatchCaller):
            request_hash_trace = []
            def anonymous_case(self, **_kwargs):
                return nullcontext()
        # Minimal canonical state is a wiring fixture, not semantic acceptance.
        caller = UnitCaller(*[ResearchState(next_information_needs=("What customer retention trends were disclosed?",)).to_dict() for _ in range(4)])
        with tempfile.TemporaryDirectory() as directory:
            root = self._prepare(directory)
            with patch("run_reviewed_initial_stage.StructuredRoleClient", return_value=caller):
                first, second = resume(root), resume(root)
            self.assertEqual(first, second)
            self.assertEqual([row["status"] for row in first["outcomes"]], ["accepted_requires_independent_review"] * 2)
            self.assertEqual(first["independent_receipts"], 0)
            for sample_id in ("s01", "s02"):
                state = json.loads((root / "samples" / sample_id / "initial_state.json").read_text())
                self.assertEqual(state["state"], ResearchState(next_information_needs=("What customer retention trends were disclosed?",)).to_dict())
                self.assertEqual(state["usage"]["llm_calls"], 1)
            self.assertTrue(all(c["stage"] == "research_controller_initialize" for c in caller.calls))

    def test_changed_frozen_input_refused_before_role_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._prepare(directory)
            p = root / "inputs.json"
            changed = json.loads(p.read_text())
            changed["samples"][0]["prediction_time"] = "2025-10-01T00:00:00+00:00"
            p.write_text(json.dumps(changed))
            with self.assertRaises(ValidationError):
                resume(root)
            self.assertFalse((root / "exchange").exists())
