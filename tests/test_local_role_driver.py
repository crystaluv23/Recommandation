"""Preflight actual stage inputs before dispatch, and exercise real CLI assembly."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_local_role_acceptance import preflight_samples, _variants, stage_consumer_checks
from diagnose_executed_answer_scope import _source_inputs
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState


class LocalRoleDriverTests(TestCase):
    def test_old_illegal_prior_is_rejected_by_real_preflight(self):
        old = json.loads((ROOT / "runs/diagnostics/local_roles_mvp_20261019_v2/inputs.json").read_text())
        with self.assertRaises(ValidationError):
            preflight_samples(old)

    def test_new_all_seven_priors_pass_actual_production_validators(self):
        inputs, _ = _source_inputs()
        variants, _ = _variants(inputs["samples"][0])
        inputs["samples"].extend(variants)
        result = preflight_samples(inputs)
        self.assertEqual(result["fixed_denominator"], 7)
        self.assertTrue(all(row["legal_prior_and_routing"] for row in result["samples"]))

    def test_driver_branch_consumes_actual_accepted_positive_shape(self):
        batch = ROOT / "runs/diagnostics/local_roles_mvp_20261019_v2"
        inputs = json.loads((batch / "inputs.json").read_text())
        sample = next(row for row in inputs["samples"] if row["sample_id"] == "future_forecast")
        expectation = next(row for row in json.loads((batch / "expectations.json").read_text()) if row["sample_id"] == sample["sample_id"])
        accepted = json.loads((batch / "samples/future_forecast/initial_reflect.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            checks = stage_consumer_checks(batch, sample, ResearchState.from_dict(accepted["state"]), expectation, output=Path(directory))
            self.assertTrue(all(checks.values()))
            proof = json.loads((Path(directory) / "future_forecast.json").read_text())
            self.assertTrue(proof["state_deltas"][0]["need_dispositions"]["items"])

    def test_real_cli_dispatches_valid_priors_and_rejects_fault_before_role(self):
        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory) / "batch"
            script = str(ROOT / "scripts/run_local_role_acceptance.py")
            subprocess.run([sys.executable, script, "prepare", "--root", str(batch)],
                           cwd=ROOT, check=True, capture_output=True, text=True)
            run = subprocess.run([sys.executable, script, "resume", "--root", str(batch)],
                                 cwd=ROOT, check=True, capture_output=True, text=True)
            result = json.loads(run.stdout)
            self.assertEqual(len(result["pending"]), 6)
            self.assertEqual(len(result["outcomes"]), 1)
            self.assertEqual(result["outcomes"][0]["sample_id"], "future_actual")
            self.assertEqual(result["outcomes"][0]["failure_type"], "SignalModelInputRejected")
            self.assertEqual(result["outcomes"][0]["request_hashes"], [])
            self.assertEqual(result["external_api_calls"], 0)
            self.assertEqual(json.loads((batch / "unused_external_attempts.json").read_text())["attempts"], [])
