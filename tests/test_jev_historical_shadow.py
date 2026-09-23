"""Offline contract tests for the live Jev historical-shadow harness."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from stock_opportunity_agent.artifacts import atomic_write_json

from scripts.run_jev_historical_shadow import prepare_shadow, score_shadow


class JevHistoricalShadowTests(TestCase):
    def test_v139_freeze_separates_inputs_and_labels(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "shadow"
            manifest = prepare_shadow(workspace=workspace)
            inputs_text = (workspace / "inputs.json").read_text(encoding="utf-8")
            inputs = json.loads(inputs_text)
            labels = json.loads((workspace / "labels.json").read_text())

            self.assertEqual(manifest["prediction_request_count"], 21)
            self.assertEqual(manifest["routing_request_count"], 80)
            self.assertEqual(manifest["technical_exclusion_count"], 3)
            self.assertEqual(len(inputs["requests"]), 101)
            self.assertEqual(len(labels["labels"]), 24)
            self.assertNotIn('"ground_truth"', inputs_text)
            self.assertNotIn("realized_max_multiple", inputs_text)

    def test_scoring_reloads_all_durable_responses_after_freeze(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "shadow"
            manifest = prepare_shadow(workspace=workspace)
            inputs = json.loads((workspace / "inputs.json").read_text())
            for item in inputs["requests"]:
                if item["kind"] == "prediction":
                    baseline = item["analysis_metadata"]["baseline_prediction"]
                    judgment = baseline["candidate_judgment"]
                    magnitude = baseline.get("magnitude") or "not_applicable"
                    answers = {
                        "candidate_judgment": _answer(
                            judgment,
                            ("likely", "possible", "unlikely", "insufficient_information"),
                        ),
                        "magnitude": _answer(
                            magnitude,
                            ("2-3x", "3-10x", "10x+", "not_applicable"),
                        ),
                    }
                else:
                    baseline_refs = set(
                        item["analysis_metadata"]["baseline_selected_refs"]
                    )
                    answers = {}
                    for question_id, question in item["questions"].items():
                        ref = question_id.split("__", 1)[1]
                        choice = (
                            next(
                                key
                                for key in question["criteria"]
                                if key.startswith("need_")
                            )
                            if ref in baseline_refs
                            else "no_match"
                        )
                        answers[question_id] = _answer(
                            choice, tuple(question["criteria"])
                        )
                atomic_write_json(
                    workspace / "responses" / f"{item['request_id']}.json",
                    {
                        "request_id": item["request_id"],
                        "response": {
                            "id": f"recorded-{item['request_id']}",
                            "model": "typesafe/jev-1.13-test",
                            "provider": "TypeSafe",
                            "answers": answers,
                            "usage": {
                                "input_tokens": 10,
                                "output_tokens": 1,
                                "cost": 0.0,
                            },
                        },
                    },
                )
            atomic_write_json(
                workspace / "execution_summary.json",
                {
                    "completed_request_count": 101,
                    "total_cost_usd": 0.0,
                    "total_tokens": 1111,
                },
            )

            score = score_shadow(
                workspace=workspace,
                acknowledged_hash=manifest["manifest_hash"],
            )
            self.assertEqual(score["scope"]["comparable_prediction_count"], 21)
            self.assertEqual(score["scope"]["routing_round_count"], 80)
            self.assertEqual(
                score["prediction"]["jev"]["confusion"],
                score["prediction"]["historical_llm"]["confusion"],
            )
            self.assertEqual(score["routing"]["exact_set_match_rate"], 1.0)


def _answer(choice: str, options: tuple[str, ...]) -> dict:
    remaining = (1.0 - 0.7) / (len(options) - 1)
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": {
            option: 0.7 if option == choice else remaining for option in options
        },
        "confidence": 0.7,
    }
