"""Offline contract tests for the live Jev historical-shadow harness."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.llm.openrouter_jev import JevDecisionResponse

from scripts.run_jev_historical_shadow import (
    _selected_routing_refs,
    _routing_history_matches,
    prepare_direction_probe,
    prepare_magnitude_followup,
    prepare_routing_context_parity_probe,
    prepare_shadow,
    score_combined_shadow,
    score_routing_context_parity_probe,
    score_shadow,
)


class JevHistoricalShadowTests(TestCase):
    def test_historical_unavailable_matching_preserves_canonical_fields(self):
        row = {
            "signal_id": "fixture_signal", "version": 1,
            "state": {"value": "unavailable", "confidence": 0.5},
            "interpretation": {"summary": "Current explicit domain coverage summary."},
            "status": {"coverage": "unavailable"},
            "execution": {"status": "domain_unavailable"},
        }
        expected = {"fixture_signal:v1": row}
        archived = deepcopy(expected)
        archived["fixture_signal:v1"]["interpretation"]["summary"] = "Old coverage summary."
        original = deepcopy(archived)
        self.assertTrue(_routing_history_matches(archived, expected))
        self.assertEqual(archived, original)
        legacy = deepcopy(archived)
        legacy["fixture_signal:v1"].pop("execution")
        self.assertTrue(_routing_history_matches(legacy, expected))
        self.assertNotIn("execution", legacy["fixture_signal:v1"])
        for key, value in (
            ("version", 2), ("state", {"value": "unavailable", "confidence": 0.8}),
            ("status", {"coverage": "partial"}),
            ("execution", {"status": "validation_failed"}),
            ("unowned", "extra"),
        ):
            changed = deepcopy(archived)
            changed["fixture_signal:v1"][key] = value
            with self.subTest(key=key):
                self.assertFalse(_routing_history_matches(changed, expected))
        self.assertFalse(_routing_history_matches({}, expected))

    def test_historical_available_summaries_remain_exact(self):
        row = {
            "signal_id": "fixture_signal", "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "Accepted available measurement."},
            "status": {"coverage": "sufficient"},
        }
        expected = {"fixture_signal:v1": row}
        self.assertTrue(_routing_history_matches(expected, expected))
        altered = deepcopy(expected)
        altered["fixture_signal:v1"]["interpretation"]["summary"] = "Different available measurement."
        self.assertFalse(_routing_history_matches(altered, expected))

    def test_routing_cap_ranks_by_total_selection_probability(self):
        cards = [
            {"signal_ref": f"signal_{index}:v1", "execution_type": "deterministic"}
            for index in range(5)
        ]
        selection_probabilities = (0.9, 0.8, 0.7, 0.6, 0.5)
        answers = {}
        for index, (card, selection_probability) in enumerate(
            zip(cards, selection_probabilities, strict=True)
        ):
            need_probability = 0.4 if index == 0 else selection_probability
            answers[f"signal_{index:03d}__{card['signal_ref']}"] = {
                "type": "choice",
                "choice": "need_0",
                "probabilities": {
                    "need_0": need_probability,
                    "context_only": selection_probability - need_probability,
                    "no_match": 1.0 - selection_probability,
                },
                "confidence": need_probability,
            }
        response = JevDecisionResponse.from_dict(
            {
                "id": "routing-rank-test",
                "model": "typesafe/jev-test",
                "provider": "test",
                "answers": answers,
            }
        )

        selected = _selected_routing_refs(
            {"state": {"available_signal_cards": cards}}, response
        )

        self.assertEqual(
            selected,
            ["signal_0:v1", "signal_1:v1", "signal_2:v1", "signal_3:v1"],
        )

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
            prediction = next(
                item for item in inputs["requests"] if item["kind"] == "prediction"
            )
            self.assertNotIn("final_context", prediction["state"])
            self.assertNotIn(
                "analysis_prompt", prediction["state"]["evidence_context"]
            )
            self.assertNotIn(
                "context_contract", prediction["state"]["evidence_context"]
            )
            self.assertIn("decision_contract", prediction["state"])

    def test_scoring_reloads_all_durable_responses_after_freeze(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "shadow"
            manifest = prepare_shadow(workspace=workspace)
            inputs = json.loads((workspace / "inputs.json").read_text())
            for item in inputs["requests"]:
                if item["kind"] == "prediction":
                    baseline = item["analysis_metadata"]["baseline_prediction"]
                    judgment = baseline["candidate_judgment"]
                    answers = {
                        "candidate_judgment": _answer(
                            judgment,
                            ("likely", "possible", "unlikely", "insufficient_information"),
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

    def test_magnitude_followup_uses_only_durable_positive_choices(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            followup = root / "followup"
            manifest = prepare_shadow(workspace=source)
            inputs = json.loads((source / "inputs.json").read_text())
            positive_cases = set()
            prediction_index = 0
            for item in inputs["requests"]:
                if item["kind"] == "prediction":
                    prediction_index += 1
                    is_positive = prediction_index <= 2
                    choice = "possible" if is_positive else "unlikely"
                    if is_positive:
                        positive_cases.add(item["case_key"])
                    answers = {
                        "candidate_judgment": _answer(
                            choice,
                            (
                                "likely",
                                "possible",
                                "unlikely",
                                "insufficient_information",
                            ),
                        )
                    }
                else:
                    answers = {
                        question_id: _answer("no_match", tuple(question["criteria"]))
                        for question_id, question in item["questions"].items()
                    }
                atomic_write_json(
                    source / "responses" / f"{item['request_id']}.json",
                    {
                        "request_id": item["request_id"],
                        "response": {
                            "id": f"recorded-{item['request_id']}",
                            "model": "typesafe/jev-1.13-test",
                            "provider": "TypeSafe",
                            "answers": answers,
                            "usage": {"input_tokens": 10, "output_tokens": 1, "cost": 0.0},
                        },
                    },
                )

            followup_manifest = prepare_magnitude_followup(
                source_workspace=source,
                source_manifest_hash=manifest["manifest_hash"],
                workspace=followup,
            )
            followup_inputs_text = (followup / "inputs.json").read_text()
            followup_inputs = json.loads(followup_inputs_text)
            self.assertEqual(followup_manifest["magnitude_request_count"], 2)
            self.assertEqual(
                {item["case_key"] for item in followup_inputs["requests"]},
                positive_cases,
            )
            self.assertNotIn("ground_truth", followup_inputs_text)
            self.assertNotIn("labels.json", followup_inputs_text)
            for item in followup_inputs["requests"]:
                self.assertIn("immutable_candidate_judgment", item["state"])
                self.assertEqual(set(item["questions"]), {"magnitude"})
                self.assertNotIn(
                    "not_applicable", item["questions"]["magnitude"]["criteria"]
                )
                atomic_write_json(
                    followup / "responses" / f"{item['request_id']}.json",
                    {
                        "request_id": item["request_id"],
                        "response": {
                            "id": f"recorded-{item['request_id']}",
                            "model": "typesafe/jev-1.13-test",
                            "provider": "TypeSafe",
                            "answers": {
                                "magnitude": _answer(
                                    "2-3x", ("2-3x", "3-10x", "10x+")
                                )
                            },
                            "usage": {"input_tokens": 10, "output_tokens": 1, "cost": 0.0},
                        },
                    },
                )
            atomic_write_json(
                source / "execution_summary.json",
                {"completed_request_count": len(inputs["requests"]), "actual_cost_usd": 0.0},
            )
            atomic_write_json(
                followup / "execution_summary.json",
                {"completed_request_count": 2, "actual_cost_usd": 0.0},
            )
            combined = score_combined_shadow(
                source_workspace=source,
                source_manifest_hash=manifest["manifest_hash"],
                magnitude_workspace=followup,
                magnitude_manifest_hash=followup_manifest["manifest_hash"],
            )
            self.assertEqual(combined["prediction"]["adapter_valid_count"], 21)
            self.assertEqual(combined["conditional_magnitude_followup"]["request_count"], 2)

    def test_direction_probe_freezes_one_question_without_labels(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            raw_probe = root / "raw"
            parity_probe = root / "parity"
            source_manifest = prepare_shadow(workspace=source)
            raw_manifest = prepare_direction_probe(
                source_workspace=source,
                source_manifest_hash=source_manifest["manifest_hash"],
                workspace=raw_probe,
                variant="raw_context",
            )
            parity_manifest = prepare_direction_probe(
                source_workspace=source,
                source_manifest_hash=source_manifest["manifest_hash"],
                workspace=parity_probe,
                variant="parity_context",
            )
            self.assertEqual(raw_manifest["prediction_request_count"], 21)
            self.assertEqual(parity_manifest["prediction_request_count"], 21)
            for probe in (raw_probe, parity_probe):
                text = (probe / "inputs.json").read_text()
                inputs = json.loads(text)["requests"]
                self.assertNotIn("ground_truth", text)
                self.assertTrue(
                    all(set(item["questions"]) == {"candidate_judgment"} for item in inputs)
                )

    def test_routing_parity_uses_exact_llm_context_and_scores_portfolios(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            parity = root / "parity"
            source_manifest = prepare_shadow(workspace=source)
            parity_manifest = prepare_routing_context_parity_probe(
                source_workspace=source,
                source_manifest_hash=source_manifest["manifest_hash"],
                workspace=parity,
            )
            source_inputs = json.loads((source / "inputs.json").read_text())
            parity_text = (parity / "inputs.json").read_text()
            parity_inputs = json.loads(parity_text)
            source_routing = {
                item["request_id"]: item
                for item in source_inputs["requests"]
                if item["kind"] == "routing"
            }
            self.assertEqual(parity_manifest["routing_request_count"], 80)
            self.assertEqual(parity_manifest["routing_question_count"], 992)
            self.assertNotIn("ground_truth", parity_text)
            self.assertNotIn("realized_max_multiple", parity_text)
            for item in parity_inputs["requests"]:
                expected_state = dict(source_routing[item["request_id"]]["state"])
                expected_state["validation_feedback"] = None
                self.assertEqual(item["state"], expected_state)
                self.assertIn("validation_feedback", item["state"])
                self.assertTrue(
                    all(
                        "smallest nonredundant portfolio"
                        in question["instructions"]
                        for question in item["questions"].values()
                    )
                )
                self.assertTrue(
                    all(
                        "routing_answer_need_phrases"
                        in question["instructions"]
                        for question in item["questions"].values()
                    )
                )
                baseline_refs = set(
                    item["analysis_metadata"]["baseline_selected_refs"]
                )
                parity_answers = {}
                source_answers = {}
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
                    parity_answers[question_id] = _answer(
                        choice, tuple(question["criteria"])
                    )
                    source_question = source_routing[item["request_id"]]["questions"][
                        question_id
                    ]
                    source_answers[question_id] = _answer(
                        "no_match", tuple(source_question["criteria"])
                    )
                for workspace, answers in (
                    (parity, parity_answers),
                    (source, source_answers),
                ):
                    atomic_write_json(
                        workspace / "responses" / f"{item['request_id']}.json",
                        {
                            "request_id": item["request_id"],
                            "response": {
                                "id": f"recorded-{workspace.name}-{item['request_id']}",
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
                parity / "execution_summary.json",
                {
                    "completed_request_count": 80,
                    "actual_cost_usd": 0.0,
                    "total_tokens": 800,
                },
            )
            score = score_routing_context_parity_probe(
                source_workspace=source,
                source_manifest_hash=source_manifest["manifest_hash"],
                workspace=parity,
                acknowledged_hash=parity_manifest["manifest_hash"],
            )
            self.assertEqual(score["context_audit"]["object_equal_round_count"], 80)
            self.assertEqual(score["parity_jev"]["exact_set_match_rate"], 1.0)


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
