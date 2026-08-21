from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.llm.openai import RetryableOpenAIClientError


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "evolve_information_schemes.py"
SPEC = importlib.util.spec_from_file_location("evolve_information_schemes", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load evolution CLI")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class EvolutionCliTests(TestCase):
    def test_progress_printer_exposes_plan_metrics_and_top_k(self) -> None:
        stream = io.StringIO()
        events = (
            {
                "event_type": "candidate_proposed",
                "cycle_id": 1,
                "round_id": 2,
                "candidate_index": 1,
                "candidate_count": 3,
                "plan_id": "plan_child",
                "plan_summary": {
                    "basic_info_fields": ["industry", "market_cap"],
                    "initial_research": "Form a falsifiable hypothesis.",
                },
            },
            {
                "event_type": "candidate_scored",
                "cycle_id": 1,
                "round_id": 2,
                "plan_id": "plan_child",
                "metrics": {
                    "binary_f1": 0.75,
                    "binary_precision": 0.8,
                    "binary_recall": 0.7,
                },
            },
            {
                "event_type": "round_committed",
                "cycle_id": 1,
                "round_id": 2,
                "candidate_scores": [
                    {"plan_id": "plan_child", "binary_f1": 0.75}
                ],
                "top_k": [{"plan_id": "plan_child", "binary_f1": 0.75}],
            },
        )
        for event in events:
            CLI._print_progress(event, stream=stream)

        output = stream.getvalue()
        self.assertIn("采样方案 1/3：plan_child", output)
        self.assertIn("Basic Info=['industry', 'market_cap']", output)
        self.assertIn("F1=0.750", output)
        self.assertIn("当前 Top-K", output)

    def test_ctrl_c_result_is_durable_and_parser_supports_continuous_mode(self) -> None:
        args = CLI.build_parser().parse_args(
            [
                "run-loop",
                "--workspace",
                "/tmp/workspace",
                "--raw-info-root",
                "/tmp/raw-info",
                "--approved-dataset",
                "/tmp/dataset.json",
            ]
        )
        self.assertEqual(args.max_cycles, 0)

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            callback_events: list[dict[str, object]] = []
            result = CLI._interrupt_result(
                workspace,
                on_progress=callback_events.append,
            )
            self.assertEqual(result["status"], "interrupted_resumable")
            self.assertEqual(result["last_completed_round"], 0)
            trajectory = Path(str(result["trajectory_path"]))
            stored = [json.loads(line) for line in trajectory.read_text().splitlines()]
            self.assertEqual(stored[-1]["event_type"], "run_interrupted")
            self.assertEqual(callback_events[-1]["sequence"], stored[-1]["sequence"])

    def test_durable_progress_boundary_refreshes_dashboard_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stream = io.StringIO()
            progress = CLI._progress_handler(root, stream=stream)
            progress({"event_type": "candidate_proposed", "plan_id": "plan_a"})
            self.assertFalse((root / "evolution_dashboard_index.json").exists())

            progress(
                {
                    "event_type": "round_committed",
                    "round_id": 1,
                    "candidate_scores": [],
                    "top_k": [],
                }
            )
            self.assertTrue((root / "evolution_dashboard_index.json").is_file())

    def test_main_returns_130_and_resume_metadata_after_keyboard_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            dashboard = root / "dashboard"
            stdout = io.StringIO()
            argv = [
                str(SCRIPT_PATH),
                "run-loop",
                "--workspace",
                str(workspace),
                "--raw-info-root",
                str(root / "raw_info"),
                "--approved-dataset",
                str(root / "approved.json"),
                "--dashboard-root",
                str(dashboard),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    CLI,
                    "run_loop_command",
                    side_effect=KeyboardInterrupt,
                ),
                redirect_stdout(stdout),
            ):
                exit_code = CLI.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 130)
            self.assertEqual(payload["status"], "interrupted_resumable")
            self.assertEqual(payload["last_completed_round"], 0)
            self.assertTrue((dashboard / "evolution_dashboard_index.json").is_file())

    def test_main_returns_75_for_retryable_provider_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            dashboard = root / "dashboard"
            stdout = io.StringIO()
            argv = [
                str(SCRIPT_PATH),
                "run-loop",
                "--workspace",
                str(workspace),
                "--raw-info-root",
                str(root / "raw_info"),
                "--approved-dataset",
                str(root / "approved.json"),
                "--dashboard-root",
                str(dashboard),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    CLI,
                    "run_loop_command",
                    side_effect=RetryableOpenAIClientError("temporary TLS error"),
                ),
                redirect_stdout(stdout),
            ):
                exit_code = CLI.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 75)
            self.assertEqual(payload["status"], "retryable_external_error")
            self.assertFalse(payload["locked_test_accessed"])
            events = (
                workspace / "experiments" / "trajectory.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn("retryable_external_error", events)

    def test_main_returns_nonzero_for_retryable_shared_evaluation_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            stdout = io.StringIO()
            argv = [
                str(SCRIPT_PATH),
                "run-loop",
                "--workspace",
                str(workspace),
                "--raw-info-root",
                str(root / "raw_info"),
                "--approved-dataset",
                str(root / "approved.json"),
                "--dashboard-root",
                str(root / "dashboard"),
            ]
            unavailable = CLI.SharedEvaluationDataUnavailable(
                4,
                {"case_pdc": "provider_error"},
                retryable=True,
                checkpoint_ref="shared-data-pause.json",
            )
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    CLI,
                    "run_loop_command",
                    side_effect=unavailable,
                ),
                redirect_stdout(stdout),
            ):
                exit_code = CLI.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 75)
            self.assertEqual(
                payload["status"], "shared_evaluation_data_unavailable"
            )
            self.assertEqual(payload["case_reasons"], {"case_pdc": "provider_error"})
            self.assertEqual(payload["last_completed_round"], 0)
