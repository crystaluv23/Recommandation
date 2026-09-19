from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
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
    def test_freeze_uses_current_terminal_reserve_default(self) -> None:
        self.assertEqual(CLI.DEFAULT_FINALIZATION_TOKEN_RESERVE, 64_000)

    def test_preflight_validates_exact_approved_dataset_without_locked_test(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "dataset.approved.json"
            manifest.write_text('{"approval_status":"human_approved"}\n')
            inventory = SimpleNamespace(
                to_dict=lambda: {"schema_version": "inventory-v1"},
                inventory_hash="inventory_hash",
                compatible_case_count=3,
                migration_ready=False,
                blockers=("legacy labels are incompatible",),
            )
            dataset = SimpleNamespace(
                discovery=(object(), object()),
                anchor=(object(),),
                evolution_validation=(object(), object(), object()),
                locked_test_hash="f" * 64,
            )
            models = {
                "judge": {"api_key_available": True},
                "proposer": {"api_key_available": True},
            }
            manager = patch.object(CLI, "EvaluationDatasetManager")
            with (
                patch.object(CLI, "_load_local_env"),
                patch.object(
                    CLI,
                    "initialize_workspace",
                    return_value={"workspace": str(root)},
                ),
                patch.object(
                    CLI,
                    "inventory_local_evolution_inputs",
                    return_value=inventory,
                ),
                patch.object(CLI, "public_model_contract", return_value=models),
                patch.object(
                    CLI,
                    "load_approved_development_dataset",
                    return_value=dataset,
                ),
                manager as evaluation_manager,
            ):
                result = CLI.preflight_local(
                    workspace_path=root,
                    raw_info_root=root / "raw",
                    catalog_path=root / "catalog.json",
                    cases_path=root / "cases.json",
                    documents_path=root / "documents.json",
                    adjusted_prices_path=root / "prices.json",
                    judge_model="judge",
                    evolution_model="proposer",
                    approved_dataset_path=manifest,
                )

            evaluation_manager.return_value.validate_feasibility.assert_called_once()
            self.assertTrue(result["ready_for_freeze"])
            self.assertFalse(result["ready_for_external_run"])
            self.assertEqual(
                result["approved_dataset"]["evolution_validation_case_count"],
                3,
            )
            self.assertFalse(result["approved_dataset"]["locked_test_accessed"])

    def test_data_external_alone_resolves_to_broad_research_policy(self) -> None:
        policy = CLI._resolve_data_acquisition_policy(
            data_external=True,
            data_providers=(),
            data_capabilities=(),
            data_source_types=(),
            max_data_requests_per_cycle=0,
            max_data_requests_per_run=0,
        )

        self.assertEqual(policy.allowed_providers, ("*",))
        self.assertEqual(policy.allowed_capabilities, ("*",))
        self.assertEqual(policy.allowed_source_types, ("*",))
        self.assertEqual(policy.max_requests_per_cycle, 1_000)
        self.assertEqual(policy.max_requests_per_run, 10_000)

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

    def test_slow_loop_started_progress_has_no_fake_candidate_result(self) -> None:
        stream = io.StringIO()

        CLI._print_progress(
            {"event_type": "slow_loop_started", "cycle_id": 1},
            stream=stream,
        )

        self.assertIn("slow_loop_started", stream.getvalue())
        self.assertNotIn("validated=", stream.getvalue())
        self.assertNotIn("promoted=", stream.getvalue())

    def test_slow_result_staged_progress_renders_actual_candidate_result(self) -> None:
        stream = io.StringIO()

        CLI._print_progress(
            {
                "event_type": "slow_loop_result_staged",
                "cycle_id": 2,
                "validated_candidates": {"signal_a:v2": True},
                "promoted": ["signal_a:v2"],
            },
            stream=stream,
        )

        output = stream.getvalue()
        self.assertIn("validated={'signal_a:v2': True}", output)
        self.assertIn("promoted=['signal_a:v2']", output)

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
        self.assertEqual(
            args.max_consecutive_no_candidate_cycles,
            CLI.DEFAULT_MAX_CONSECUTIVE_NO_CANDIDATE_CYCLES,
        )

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

    def test_committed_no_candidate_diagnosis_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = CLI.EvolutionWorkspace(root)
            workspace.cycle_state_path.write_text(
                json.dumps({"last_completed_cycle": 3}), encoding="utf-8"
            )
            rows = (
                (
                    1,
                    "fingerprint-a",
                    {"mining_pipeline": {"status": "no_testable_hypothesis"}},
                    {},
                ),
                (
                    2,
                    "fingerprint-b",
                    {},
                    {"h1-c0002-s01": ["needs refinement"]},
                ),
                (3, "fingerprint-b", {}, {}),
            )
            for cycle_id, fingerprint, audits, refined in rows:
                path = (
                    workspace.experiments_root
                    / "cycles"
                    / f"cycle-{cycle_id:04d}"
                    / "slow_loop_validation.json"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "validation": {
                                "mined_candidates": [],
                                "updated_candidates": [],
                                "rejected": (
                                    {"slow_loop:mining_pipeline": ["invalid output"]}
                                    if cycle_id == 3
                                    else {}
                                ),
                                "refined_hypotheses": refined,
                                "agent_audits": audits,
                                "search_input_fingerprint": fingerprint,
                            }
                        }
                    ),
                    encoding="utf-8",
                )

            diagnosis = CLI._committed_no_candidate_diagnosis(root)

            self.assertEqual(diagnosis["consecutive_no_candidate_cycles"], 3)
            self.assertEqual(diagnosis["cycle_ids"], [1, 2, 3])
            self.assertTrue(diagnosis["search_input_changed_within_streak"])
            self.assertEqual(
                set(diagnosis["categories"]),
                {
                    "no_testable_hypothesis",
                    "refinement_without_candidate",
                    "technical_failure",
                },
            )

            cycle_two_path = (
                workspace.experiments_root
                / "cycles"
                / "cycle-0002"
                / "slow_loop_validation.json"
            )
            cycle_two = json.loads(cycle_two_path.read_text(encoding="utf-8"))
            cycle_two["validation"]["mined_candidates"] = ["candidate:v1"]
            cycle_two_path.write_text(json.dumps(cycle_two), encoding="utf-8")

            reset = CLI._committed_no_candidate_diagnosis(root)

            self.assertEqual(reset["consecutive_no_candidate_cycles"], 1)
            self.assertEqual(reset["cycle_ids"], [3])

    def test_committed_no_candidate_diagnosis_rejects_corrupt_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = CLI.EvolutionWorkspace(root)
            workspace.cycle_state_path.write_text(
                json.dumps({"last_completed_cycle": 1}), encoding="utf-8"
            )
            path = (
                workspace.experiments_root
                / "cycles"
                / "cycle-0001"
                / "slow_loop_validation.json"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "validation": {
                            "mined_candidates": "candidate:v1",
                            "updated_candidates": [],
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                CLI.ValidationError, "mined_candidates must be an array"
            ):
                CLI._committed_no_candidate_diagnosis(root)

    def test_run_loop_stops_after_committed_no_candidate_limit(self) -> None:
        initial = {
            "consecutive_no_candidate_cycles": 2,
            "cycle_ids": [1, 2],
            "search_input_fingerprints": ["a", "b"],
            "search_input_changed_within_streak": True,
            "categories": ["no_testable_hypothesis"],
        }
        diagnosis = {
            "consecutive_no_candidate_cycles": 3,
            "cycle_ids": [1, 2, 3],
            "search_input_fingerprints": ["a", "b", "b"],
            "search_input_changed_within_streak": True,
            "categories": ["no_testable_hypothesis"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events: list[dict[str, object]] = []
            with (
                patch.object(
                    CLI,
                    "run_cycle_command",
                    return_value={
                        "status": "cycle_completed",
                        "last_completed_cycle": 3,
                    },
                ) as run_cycle,
                patch.object(
                    CLI,
                    "_committed_no_candidate_diagnosis",
                    side_effect=(initial, diagnosis),
                ),
                patch.object(
                    CLI,
                    "workspace_status",
                    return_value={"last_completed_cycle": 3},
                ),
            ):
                result = CLI.run_loop_command(
                    workspace_path=root,
                    raw_info_root=root / "raw",
                    approved_dataset_path=root / "dataset.json",
                    external=False,
                    acknowledged_contract_hash=None,
                    max_cycles=0,
                    max_consecutive_no_candidate_cycles=3,
                    on_progress=events.append,
                )

            self.assertEqual(result["status"], "no_candidate_search_limit_reached")
            self.assertEqual(result["no_candidate_diagnosis"], diagnosis)
            self.assertEqual(run_cycle.call_count, 1)
            self.assertEqual(
                events[-1]["event_type"], "no_candidate_search_limit_reached"
            )

            events.clear()
            with (
                patch.object(CLI, "run_cycle_command") as run_cycle,
                patch.object(
                    CLI,
                    "_committed_no_candidate_diagnosis",
                    return_value=diagnosis,
                ),
                patch.object(
                    CLI,
                    "workspace_status",
                    return_value={"last_completed_cycle": 3},
                ),
            ):
                restarted = CLI.run_loop_command(
                    workspace_path=root,
                    raw_info_root=root / "raw",
                    approved_dataset_path=root / "dataset.json",
                    external=False,
                    acknowledged_contract_hash=None,
                    max_cycles=0,
                    max_consecutive_no_candidate_cycles=3,
                    on_progress=events.append,
                )

            self.assertEqual(restarted["completed_cycles_this_invocation"], [])
            run_cycle.assert_not_called()
            self.assertEqual(
                events[-1]["event_type"], "no_candidate_search_limit_reached"
            )

        with self.assertRaisesRegex(ValueError, "must be positive"):
            CLI.run_loop_command(
                workspace_path=Path("/unused"),
                raw_info_root=Path("/unused/raw"),
                approved_dataset_path=Path("/unused/dataset.json"),
                external=False,
                acknowledged_contract_hash=None,
                max_cycles=0,
                max_consecutive_no_candidate_cycles=0,
            )

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

    def test_main_returns_75_for_retryable_slow_profile_data(self) -> None:
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
            unavailable = CLI.SlowLoopDataUnavailable(
                "case-001", "provider_error"
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
            self.assertEqual(payload["status"], "slow_loop_data_unavailable")
            self.assertEqual(payload["case_ref"], "case-001")
            self.assertEqual(payload["provider_reason"], "provider_error")
            self.assertEqual(payload["last_completed_cycle"], 0)
            events = (
                workspace / "experiments" / "trajectory.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn("slow_loop_data_unavailable", events)

class CycleWatchdogTests(TestCase):
    def test_watchdog_fires_on_stall_and_stays_silent_when_disabled(self) -> None:
        import time

        cli = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(cli)

        # A disabled watchdog never fires.
        with cli._cycle_watchdog(0):
            time.sleep(1.1)

        # An armed watchdog converts a silent stall into the retryable
        # channel used for auto-resume.
        with self.assertRaises(cli.CycleWatchdogTimeout):
            with cli._cycle_watchdog(1):
                time.sleep(5)
        # The alarm is cancelled on exit: a later long sleep does not fire.
        time.sleep(1.2)
