from __future__ import annotations

import re
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
        self.assertIn("exported environment", result.stdout)
        self.assertIn("git-ignored .env.local", result.stdout)
        self.assertIn("opens Locked Test", result.stdout)
        self.assertIn("resume automatically", result.stdout)

    def test_key_and_reviewer_do_not_require_interactive_input(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("read -r -s", source)
        self.assertIn('REVIEWER="local-operator"', source)
        self.assertIn('KEY_SOURCE="git-ignored .env.local"', source)

    def test_only_temporary_failure_status_is_restarted(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('if [ "$RUN_STATUS" -ne 75 ]; then', source)
        self.assertIn("临时网络/服务故障", source)

    def test_strict_mode_variables_are_braced_before_non_ascii_text(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        unbraced_before_non_ascii = re.compile(
            r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]"
        )
        self.assertIsNone(unbraced_before_non_ascii.search(source))
