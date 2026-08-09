from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import TestCase


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_deepseek_evolution.sh"


class DeepSeekEvolutionLauncherTests(TestCase):
    def test_script_has_valid_bash_syntax(self) -> None:
        subprocess.run(["/bin/bash", "-n", str(SCRIPT)], check=True)

    def test_help_is_non_mutating_and_documents_bounds(self) -> None:
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("DeepSeek V4 Flash", result.stdout)
        self.assertIn("10 hours", result.stdout)
        self.assertIn("USD 30", result.stdout)
        self.assertIn("one confirmation", result.stdout)
        self.assertIn("never opens Locked Test", result.stdout)
