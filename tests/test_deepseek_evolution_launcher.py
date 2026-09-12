from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "run_information_plan_evolution.sh"
COMPATIBILITY_SCRIPT = ROOT / "scripts" / "run_deepseek_evolution.sh"


class InformationPlanEvolutionLauncherTests(TestCase):
    def _run_stubbed_resume(
        self,
        root: Path,
        *,
        retryable_failures: int,
        final_status: int,
        retry_window_hours: int = 1,
    ) -> tuple[subprocess.CompletedProcess[str], int]:
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "run_contract.json").write_text(
            json.dumps(
                {
                    "contract": {"schema_version": "evolution-run-contract-v8"},
                    "contract_hash": "fixture-contract-hash",
                }
            ),
            encoding="utf-8",
        )
        approved = root / "approved.json"
        approved.write_text("{}", encoding="utf-8")
        count_path = root / "invocation-count.txt"
        stub = root / "python-stub.sh"
        stub.write_text(
            """#!/usr/bin/env bash
set -u
if [ "${1:-}" = "-c" ]; then
  if [ "$#" -ge 3 ]; then
    printf '%s\\n' 'evolution-run-contract-v8 fixture-contract-hash'
  fi
  exit 0
fi
count=0
if [ -f "$STUB_COUNT_PATH" ]; then
  count="$(<"$STUB_COUNT_PATH")"
fi
count=$((count + 1))
printf '%s' "$count" > "$STUB_COUNT_PATH"
if [ "$count" -le "$STUB_RETRYABLE_FAILURES" ]; then
  exit 75
fi
exit "$STUB_FINAL_STATUS"
""",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        result = subprocess.run(
            [
                "/bin/bash",
                str(SCRIPT),
                "resume",
                "--workspace",
                str(workspace),
                "--raw-info-root",
                str(root / "raw-info"),
                "--approved-dataset",
                str(approved),
                "--max-cycles",
                "1",
                "--retry-window-hours",
                str(retry_window_hours),
                "--retry-initial-backoff-seconds",
                "0",
                "--retry-max-backoff-seconds",
                "0",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "EVOLUTION_PYTHON": str(stub),
                "STUB_COUNT_PATH": str(count_path),
                "STUB_RETRYABLE_FAILURES": str(retryable_failures),
                "STUB_FINAL_STATUS": str(final_status),
            },
        )
        return result, int(count_path.read_text(encoding="utf-8"))

    def test_scripts_have_valid_bash_syntax(self) -> None:
        for script in (SCRIPT, COMPATIBILITY_SCRIPT):
            subprocess.run(["/bin/bash", "-n", str(script)], check=True)

    def test_help_documents_new_resume_and_external_boundary(self) -> None:
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("new [options]", result.stdout)
        self.assertIn("resume [options]", result.stdout)
        self.assertIn("new never performs LLM calls", result.stdout)
        self.assertIn("it may prepare Raw Info", result.stdout)
        self.assertIn("--acknowledge-contract-hash", result.stdout)
        self.assertIn("default: 2", result.stdout)
        self.assertIn("default: 3", result.stdout)
        self.assertIn("--data-provider", result.stdout)
        self.assertIn("--slow-bootstrap-from", result.stdout)
        self.assertIn("--retry-window-hours", result.stdout)
        self.assertIn("default: 10", result.stdout)
        self.assertIn("Locked Test stays sealed", result.stdout)
        self.assertIn("auto-promote atomically", result.stdout)
        self.assertIn("v7 contract", result.stdout)

    def test_new_rejects_any_existing_workspace_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            marker = workspace / "owner-data.txt"
            marker.write_text("keep", encoding="utf-8")
            approved = root / "approved.json"
            approved.write_text("{}", encoding="utf-8")

            result = subprocess.run(
                [
                    "/bin/bash",
                    str(SCRIPT),
                    "new",
                    "--workspace",
                    str(workspace),
                    "--raw-info-root",
                    str(root / "raw-info"),
                    "--approved-dataset",
                    str(approved),
                    "--run-id",
                    "fixture",
                    "--judge-model",
                    "judge",
                    "--evolution-model",
                    "proposer",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unused workspace", result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_new_rejects_external_authorization_before_workspace_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approved = root / "approved.json"
            approved.write_text("{}", encoding="utf-8")
            result = subprocess.run(
                [
                    "/bin/bash",
                    str(SCRIPT),
                    "new",
                    "--workspace",
                    str(root / "workspace"),
                    "--raw-info-root",
                    str(root / "raw-info"),
                    "--approved-dataset",
                    str(approved),
                    "--run-id",
                    "fixture",
                    "--judge-model",
                    "judge",
                    "--evolution-model",
                    "proposer",
                    "--external",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("new never accepts LLM external authorization", result.stderr)

    def test_new_rejects_dormant_data_policy_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approved = root / "approved.json"
            approved.write_text("{}", encoding="utf-8")
            result = subprocess.run(
                [
                    "/bin/bash",
                    str(SCRIPT),
                    "new",
                    "--workspace",
                    str(root / "workspace"),
                    "--raw-info-root",
                    str(root / "raw-info"),
                    "--approved-dataset",
                    str(approved),
                    "--run-id",
                    "fixture",
                    "--judge-model",
                    "judge",
                    "--evolution-model",
                    "proposer",
                    "--data-provider",
                    "sec_edgar",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data policy options require --data-external", result.stderr)

    def test_new_data_external_uses_broad_profile_without_manual_lists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            approved = root / "approved.json"
            approved.write_text("{}", encoding="utf-8")
            log_path = root / "commands.log"
            stub = root / "python-stub.sh"
            stub.write_text(
                """#!/usr/bin/env bash
set -eu
if [ "${1:-}" = "-c" ]; then
  if [ "$#" -ge 3 ]; then
    printf '%s\n' 'fixture-contract-hash'
  fi
  exit 0
fi
shift
command_name="$1"
shift
printf '%s' "$command_name" >> "$STUB_LOG_PATH"
printf ' %s' "$@" >> "$STUB_LOG_PATH"
printf '\n' >> "$STUB_LOG_PATH"
workspace=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--workspace" ]; then
    workspace="$2"
    shift 2
  else
    shift
  fi
done
if [ "$command_name" = "init" ]; then
  mkdir -p "$workspace"
elif [ "$command_name" = "freeze-run" ]; then
  mkdir -p "$workspace"
  printf '%s\n' '{"contract":{"schema_version":"evolution-run-contract-v8"},"contract_hash":"fixture-contract-hash"}' > "$workspace/run_contract.json"
fi
""",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            result = subprocess.run(
                [
                    "/bin/bash",
                    str(SCRIPT),
                    "new",
                    "--workspace",
                    str(workspace),
                    "--raw-info-root",
                    str(root / "raw-info"),
                    "--approved-dataset",
                    str(approved),
                    "--run-id",
                    "fixture",
                    "--judge-model",
                    "judge",
                    "--evolution-model",
                    "proposer",
                    "--data-external",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "EVOLUTION_PYTHON": str(stub),
                    "STUB_LOG_PATH": str(log_path),
                },
            )
            commands = log_path.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        freeze = next(
            line for line in commands.splitlines() if line.startswith("freeze-run ")
        )
        initial_run = next(
            line for line in commands.splitlines() if line.startswith("run-cycle ")
        )
        self.assertIn("--data-external", freeze)
        self.assertNotIn("--data-provider", freeze)
        self.assertNotIn("--max-data-requests-per-cycle", freeze)
        self.assertIn("--data-external", initial_run)

    def test_compatibility_script_only_forwards_to_stable_entry(self) -> None:
        source = COMPATIBILITY_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("run_information_plan_evolution.sh", source)
        self.assertNotIn("WORKSPACE=", source)
        self.assertNotIn("MAX_TOTAL_COST=", source)

    def test_launcher_contains_no_api_key_loading_or_secret_prompt(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("DEEPSEEK_API_KEY", source)
        self.assertNotIn("read -r -s", source)
        self.assertIn('ALLOW_EXTERNAL=0', source)
        self.assertIn('CONTRACT_SCHEMA" = "evolution-run-contract-v8', source)
        self.assertNotIn('CONTRACT_SCHEMA" = "evolution-run-contract-v4', source)

    def test_resume_automatically_relaunches_only_retryable_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, invocation_count = self._run_stubbed_resume(
                Path(directory),
                retryable_failures=2,
                final_status=0,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(invocation_count, 3)
        self.assertEqual(result.stderr.count("Temporary transport failure"), 2)
        self.assertIn("same frozen contract", result.stderr)

    def test_resume_does_not_relaunch_non_retryable_or_interrupt_exit(self) -> None:
        for final_status in (2, 130):
            with self.subTest(final_status=final_status):
                with tempfile.TemporaryDirectory() as directory:
                    result, invocation_count = self._run_stubbed_resume(
                        Path(directory),
                        retryable_failures=0,
                        final_status=final_status,
                    )

                self.assertEqual(result.returncode, final_status)
                self.assertEqual(invocation_count, 1)
                self.assertNotIn("Temporary transport failure", result.stderr)

    def test_zero_retry_window_returns_first_retryable_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, invocation_count = self._run_stubbed_resume(
                Path(directory),
                retryable_failures=100,
                final_status=0,
                retry_window_hours=0,
            )

        self.assertEqual(result.returncode, 75)
        self.assertEqual(invocation_count, 1)
        self.assertNotIn("Temporary transport failure", result.stderr)
