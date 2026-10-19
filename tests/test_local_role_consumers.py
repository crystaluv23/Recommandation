"""Exercise actual CLI consumers against accepted independent-role production shapes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase


class LocalRoleConsumersTests(TestCase):
    def test_saved_positive_control_survives_real_cli_consumers(self):
        root = Path(__file__).resolve().parents[1]
        batch = root / "runs/diagnostics/local_roles_mvp_20261019_v2"
        original = (batch / "samples/future_forecast/outcome.json").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([
                sys.executable, str(root / "scripts/verify_local_role_consumers.py"),
                "--root", str(batch), "--output", directory, "--sample-id", "future_forecast",
            ], cwd=root, capture_output=True, text=True, check=True)
            envelope = json.loads(result.stdout)
            self.assertTrue(envelope["all_selected_consumers_verified"])
            proof = json.loads((Path(directory) / "future_forecast.json").read_text())
            self.assertTrue(all(proof["checks"].values()))
            self.assertTrue(proof["state_deltas"][0]["need_dispositions"]["items"])
            self.assertEqual(proof["state_deltas"][0]["need_dispositions"]["items"][0]["answer_scope"], "full")
            self.assertTrue(proof["original_stage_outcome_unchanged"])
            self.assertFalse(proof["new_prediction_or_posthoc_or_critic_executed"])
        self.assertEqual((batch / "samples/future_forecast/outcome.json").read_bytes(), original)

    def test_missing_accepted_state_is_not_promoted_by_cli(self):
        root = Path(__file__).resolve().parents[1]
        batch = root / "runs/diagnostics/local_roles_mvp_20261019_v2"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([
                sys.executable, str(root / "scripts/verify_local_role_consumers.py"),
                "--root", str(batch), "--output", directory, "--sample-id", "q2_only",
            ], cwd=root, capture_output=True, text=True, check=True)
            envelope = json.loads(result.stdout)
            self.assertFalse(envelope["all_selected_consumers_verified"])
            self.assertEqual(envelope["outcomes"][0]["status"], "missing_accepted_stage")
