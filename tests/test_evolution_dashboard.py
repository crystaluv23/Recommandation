from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.research.evolution_dashboard import (
    build_evolution_dashboard_bundle,
    write_evolution_dashboard_bundle,
)


class EvolutionDashboardTests(TestCase):
    def test_global_html_keeps_one_file_compatible_entry_point(self) -> None:
        html_path = (
            Path(__file__).parents[1]
            / "runs"
            / "cold_start"
            / "evolution"
            / "evolution_dashboard.html"
        )
        html = html_path.read_text(encoding="utf-8")
        self.assertIn('src="evolution_dashboard_data.js"', html)
        self.assertIn('id="run-select"', html)
        self.assertIn('id="drift-chart"', html)
        self.assertIn('id="top-k-table"', html)
        self.assertIn('id="candidate-table"', html)
        self.assertIn('id="event-table"', html)
        self.assertIn('"Binary F1"', html)
        self.assertIn('"轮次"', html)

    def test_mixed_dashboard_trusts_only_committed_v1_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "v1-workspace"
            (workspace / "plans" / "plan_one").mkdir(parents=True)
            (workspace / "experiments" / "round-0001").mkdir(parents=True)
            (workspace / "experiments" / "trajectories" / "plan_one").mkdir(
                parents=True
            )
            _write_json(workspace / "state.json", {"last_completed_round": 1})
            _write_json(
                workspace / "run_contract.json",
                {
                    "run_id": "v1-run",
                    "limits": {"top_k": 2, "similarity_threshold": 0.9},
                },
            )
            _write_json(
                workspace / "plans" / "plan_one" / "record.json",
                _record("plan_one", round_id=1, binary_f1=0.75),
            )
            _write_json(
                workspace / "experiments" / "round-0001" / "checkpoint.json",
                {"round_id": 1, "plan_ids": ["plan_one"]},
            )
            for case_id in ("case_a", "case_b"):
                _write_json(
                    workspace
                    / "experiments"
                    / "trajectories"
                    / "plan_one"
                    / f"{case_id}.json",
                    {"case_id": case_id},
                )
            _write_json(
                workspace / "cycle_state.json",
                {
                    "last_completed_cycle": 0,
                    "active_cycle": {
                        "cycle_id": 1,
                        "start_round": 0,
                        "target_plan_rounds": 2,
                        "completed_plan_rounds": 1,
                        "phase": "fast_loop",
                    },
                },
            )
            events = [
                {
                    "sequence": 1,
                    "at": "2026-08-09T00:00:00+00:00",
                    "event_type": "round_committed",
                    "round_id": 1,
                    "secret_prompt": "must not enter dashboard",
                },
                {
                    "sequence": 2,
                    "at": "2026-08-09T00:01:00+00:00",
                    "event_type": "run_interrupted",
                    "cycle_id": 1,
                },
            ]
            (workspace / "experiments" / "trajectory.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events)
                + "truncated-event\n",
                encoding="utf-8",
            )

            # This staged round must remain invisible because state.json points to 1.
            (workspace / "plans" / "plan_staged").mkdir(parents=True)
            _write_json(
                workspace / "plans" / "plan_staged" / "record.json",
                _record("plan_staged", round_id=2, binary_f1=1.0),
            )
            (workspace / "experiments" / "round-0002").mkdir(parents=True)
            _write_json(
                workspace / "experiments" / "round-0002" / "checkpoint.json",
                {"round_id": 2, "plan_ids": ["plan_staged"]},
            )

            legacy = root / "legacy-run"
            legacy.mkdir()
            _write_json(
                legacy / "evolution_history.json",
                {
                    "run_id": "legacy-run",
                    "schema_version": "scheme-evolution-history-v1",
                    "rounds": [],
                },
            )
            malformed = root / "malformed-run"
            malformed.mkdir()
            (malformed / "evolution_history.json").write_text("[]", encoding="utf-8")

            bundle = build_evolution_dashboard_bundle(root, recent_event_limit=10)
            self.assertEqual(len(bundle["runs"]), 2)
            v1 = next(run for run in bundle["runs"] if run["run_id"] == "v1-run")
            self.assertEqual(v1["architecture"], "information_plan_signal_v1")
            self.assertEqual(v1["last_completed_round"], 1)
            self.assertEqual(len(v1["rounds"]), 1)
            self.assertEqual(v1["rounds"][0]["candidates"][0]["plan_id"], "plan_one")
            self.assertEqual(v1["committed_trajectory_count"], 2)
            self.assertEqual(v1["staged_trajectory_file_count"], 2)
            self.assertEqual(v1["interruption_count"], 1)
            self.assertEqual(v1["trajectory_event_corrupt_line_count"], 1)
            self.assertEqual(v1["current_top_k"][0]["binary_f1"], 0.75)
            self.assertNotIn("secret_prompt", json.dumps(v1["recent_events"]))
            self.assertEqual(bundle["skipped_runs"][0]["run_id"], "malformed-run")

            written = write_evolution_dashboard_bundle(root)
            self.assertEqual(written["schema_version"], bundle["schema_version"])
            index = json.loads(
                (root / "evolution_dashboard_index.json").read_text(encoding="utf-8")
            )
            self.assertFalse(index["contains_final_test_metrics"])
            script = (root / "evolution_dashboard_data.js").read_text(
                encoding="utf-8"
            )
            self.assertTrue(
                script.startswith("window.__SCHEME_EVOLUTION_DASHBOARD__ = ")
            )
            self.assertNotIn("must not enter dashboard", script)


def _record(plan_id: str, *, round_id: int, binary_f1: float) -> dict:
    return {
        "plan_id": plan_id,
        "parent_ids": ["plan_parent"],
        "round_id": round_id,
        "plan": {
            "plan_id": plan_id,
            "parent_ids": ["plan_parent"],
            "basic_info_policy": {"fields": ["industry", "market_cap"]},
            "initial_research_skill": "Form a falsifiable hypothesis.",
            "reflection_skill": "Resolve contradictions before finalizing.",
            "analysis_prompt": "Weigh source-backed evidence.",
        },
        "embedding": [1.0, 0.0],
        "metrics": {
            "binary_precision": 0.8,
            "binary_recall": 0.7,
            "binary_f1": binary_f1,
            "magnitude_accuracy": 0.5,
            "magnitude_macro_f1": 0.4,
            "confusion": {
                "true_positive": 1,
                "false_positive": 0,
                "true_negative": 1,
                "false_negative": 1,
            },
            "sample_count": 2,
        },
        "reflection": {},
        "signal_usage": {},
        "trajectories": [
            {
                "case_id": "case_a",
                "stop_reason": "finalized",
                "usage": {
                    "signal_calls": 1,
                    "model": {"llm_calls": 4, "tokens": 100, "cost": 0.1},
                },
            },
            {
                "case_id": "case_b",
                "stop_reason": "max_signal_rounds",
                "usage": {
                    "signal_calls": 2,
                    "model": {"llm_calls": 5, "tokens": 120, "cost": 0.2},
                },
            },
        ],
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
