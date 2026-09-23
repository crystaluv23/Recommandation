"""Offline tests for the sequential Jev Signal-routing shadow."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.run_jev_sequential_routing_shadow import (
    STOP_OPTION,
    _read_round_record,
    _write_round_record,
    build_sequential_step,
    prepare_sequential_probe,
)
from stock_opportunity_agent.models import ValidationError


SOURCE_WORKSPACE = Path(
    "runs/cold_start/evolution/jev-signal-routing-context-parity-20260923-v3"
)
SOURCE_MANIFEST_HASH = (
    "2067bd234b01a713fa2e0ff77ffb312bbf7f86ec2be6cc8f2de490b15280e45d"
)


class JevSequentialRoutingShadowTests(TestCase):
    def test_prepare_freezes_literal_context_without_labels(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "sequential"
            manifest = prepare_sequential_probe(
                source_workspace=SOURCE_WORKSPACE,
                source_manifest_hash=SOURCE_MANIFEST_HASH,
                workspace=workspace,
            )
            text = (workspace / "inputs.json").read_text()
            inputs = json.loads(text)["requests"]

            self.assertEqual(manifest["routing_round_count"], 80)
            self.assertEqual(len(inputs), 80)
            self.assertNotIn("ground_truth", text)
            self.assertNotIn("realized_max_multiple", text)
            self.assertTrue(
                all(item["state"]["validation_feedback"] is None for item in inputs)
            )

    def test_step_appends_history_and_enforces_llm_cap(self):
        base_item = {
            "state": {
                "available_signal_cards": [
                    {"signal_ref": "a:v1", "execution_type": "llm"},
                    {"signal_ref": "b:v1", "execution_type": "llm"},
                    {"signal_ref": "c:v1", "execution_type": "llm"},
                    {"signal_ref": "d:v1", "execution_type": "deterministic"},
                ],
                "information_needs": ["need"],
                "validation_feedback": None,
            }
        }
        selected = [
            {"signal_ref": "a:v1", "choice_probability": 0.7},
            {"signal_ref": "b:v1", "choice_probability": 0.6},
        ]

        built, option_to_ref = build_sequential_step(base_item, selected, 3)

        self.assertEqual(set(option_to_ref.values()), {"d:v1"})
        self.assertEqual(
            built["state"]["available_signal_cards"],
            base_item["state"]["available_signal_cards"],
        )
        self.assertEqual(
            built["state"]["sequential_selection"]["selected_signals"], selected
        )
        self.assertEqual(
            set(built["questions"]["next_signal"]["criteria"]),
            {"candidate_000", STOP_OPTION},
        )

    def test_round_record_detects_path_changes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "round.json"
            _write_round_record(path, {"status": "completed", "selected_steps": []})
            value = json.loads(path.read_text())
            value["status"] = "in_progress"
            path.write_text(json.dumps(value))

            with self.assertRaisesRegex(ValidationError, "round record changed"):
                _read_round_record(path)
