"""Magnitude learning tasks in the Slow source view (action-plan P5 phase 1)."""

import inspect
import unittest

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.artifacts import canonical_json_hash as _canonical_hash
from stock_opportunity_agent.research.scheme_evolution import (
    FitnessEligibility,
    PlanEvaluationSummary,
    PlanMetaReflection,
    PlanRecord,
    PlanReflection,
    RoundMetaEntry,
    score_predictions,
)
from stock_opportunity_agent.research.signal_evolution import (
    _SLOW_FEEDBACK_KINDS,
    _SLOW_SOURCE_ROLES,
    SlowLoopResult,
    SignalEvolutionEngine,
    magnitude_feedback_rows,
    validate_slow_input,
)


def _plan_record(plan_id: str, rows):
    base = default_information_plan()
    plan = InformationPlan(
        plan_id=plan_id,
        parent_ids=(),
        basic_info_policy=base.basic_info_policy,
        initial_research_skill=base.initial_research_skill,
        reflection_skill=base.reflection_skill,
        analysis_prompt=base.analysis_prompt,
    )
    return PlanRecord(
        plan=plan,
        round_id=1,
        embedding=(1.0, 0.0),
        metrics=score_predictions(rows),
        reflection=PlanReflection(),
        signal_usage={},
        trajectories=rows,
        evaluation=PlanEvaluationSummary(
            evaluation_stage="round",
            n_cases=len(rows),
            case_ids=tuple(item.case_id for item in rows),
            dataset_snapshot_ids=("snapshot-test",),
            metrics_by_cohort={},
        ),
        fitness=FitnessEligibility(
            eligible=True,
            reasons=(),
            expected_case_count=len(rows),
            valid_case_count=len(rows),
            evidence_covered_count=len(rows),
            predicted_positive_count=sum(
                1 for item in rows if item.prediction.is_surge
            ),
            true_positive_count=sum(
                1
                for item in rows
                if item.prediction.is_surge and item.ground_truth.is_surge
            ),
        ),
    )


def _meta_entry(round_id: int, plan_ids):
    rows = _v130_rows()
    reflections = []
    for plan_id in plan_ids:
        record = _plan_record(plan_id, rows)
        reflections.append(PlanMetaReflection.from_record(record))
    return RoundMetaEntry(
        round_id=round_id,
        evidence_refs=tuple(plan_ids),
    ).append_plan_reflections(reflections)


def _legacy_meta_entry(round_id: int, plan_ids):
    """Rebuild an entry whose Plan reflections lack magnitude artifacts."""

    current = _meta_entry(round_id, plan_ids)
    legacy_reflections = []
    for reflection in current.plan_reflections:
        serialized = reflection.to_dict()
        serialized.pop("magnitude_diagnostics", None)
        legacy_reflections.append(PlanMetaReflection.from_dict(serialized))
    return RoundMetaEntry(
        round_id=round_id,
        evidence_refs=tuple(plan_ids),
    ).append_plan_reflections(legacy_reflections)


def _v130_rows():
    rows = []

    def add(multiple, predicted_surge, predicted_magnitude):
        rows.append(
            make_trajectory(
                f"case_slow_{len(rows) + 1:02d}",
                multiple,
                predicted_surge,
                predicted_magnitude,
            )
        )

    for _ in range(3):
        add(1.5, False, None)
    for _ in range(2):
        add(1.2, True, MagnitudeClass.TWO_TO_THREE)
    add(2.5, True, MagnitudeClass.TWO_TO_THREE)
    add(2.8, False, None)
    add(5.0, True, MagnitudeClass.TWO_TO_THREE)
    add(15.0, True, MagnitudeClass.TWO_TO_THREE)
    return tuple(rows)


class MagnitudeFeedbackRowsTest(unittest.TestCase):
    def test_committed_round_projects_one_row_per_plan(self):
        rows, manifest = magnitude_feedback_rows(
            (_meta_entry(1, ("plan_a", "plan_b")),),
            last_completed_round=1,
        )
        self.assertEqual(
            [row["feedback_ref"] for row in rows],
            ["magnitude:plan_a", "magnitude:plan_b"],
        )
        for row in rows:
            self.assertEqual(row["kind"], "magnitude_feedback")
            self.assertEqual(row["subject_ref"], row["feedback_ref"].split(":", 1)[1])
            self.assertEqual(row["source_refs"], [row["feedback_ref"]])
            self.assertIn("not a promotion gate", row["limitations"][0])
            self.assertEqual(row["event"]["round_id"], 1)
        for entry in manifest:
            self.assertEqual(
                entry["content_hash"],
                _canonical_hash(
                    next(
                        row["event"]
                        for row in rows
                        if row["feedback_ref"] == entry["ref"]
                    )
                ),
            )
            self.assertEqual(entry["visible_to"], sorted(_SLOW_SOURCE_ROLES))

    def test_carries_underestimate_evidence_for_h1(self):
        rows, _ = magnitude_feedback_rows(
            (_meta_entry(1, ("plan_a",)),),
            last_completed_round=1,
        )
        diagnostics = rows[0]["event"]["magnitude_diagnostics"]
        self.assertEqual(diagnostics["underestimate_count"], 2)
        self.assertEqual(diagnostics["missed_surge_count"], 1)

    def test_legacy_reflection_without_diagnostics_yields_no_row(self):
        rows, manifest = magnitude_feedback_rows(
            (_legacy_meta_entry(1, ("plan_legacy",)),),
            last_completed_round=1,
        )
        self.assertEqual(rows, [])
        self.assertEqual(manifest, [])

    def test_uncommitted_and_imported_rounds_are_excluded(self):
        entries = (
            _meta_entry(2, ("plan_future",)),
            _meta_entry(-1, ("plan_imported",)),
        )
        rows, _ = magnitude_feedback_rows(
            entries,
            last_completed_round=1,
        )
        self.assertEqual(rows, [])

    def test_kind_registered_for_slow_input_validation(self):
        self.assertIn("magnitude_feedback", _SLOW_FEEDBACK_KINDS)


class SlowInputSchemaTest(unittest.TestCase):
    def test_magnitude_row_passes_validate_slow_input(self):
        rows, manifest = magnitude_feedback_rows(
            (_meta_entry(1, ("plan_a",)),),
            last_completed_round=1,
        )
        payload = {
            "schema_version": "slow-input-v1",
            "cycle_id": 1,
            "contract_hash": "contract-hash",
            "registry_hash": "registry-hash",
            "source_cutoff": {"committed_fast_round": 1},
            "source_manifest": manifest,
            "feedback_rows": rows,
            "sampling_manifest": {
                "schema_version": "slow-sampling-manifest-v1",
                "dev_case_ids": ["case_dev_1"],
                "check_case_ids": ["case_check_1"],
                "issuer_groups": {
                    "case_dev_1": "issuer_a",
                    "case_check_1": "issuer_b",
                },
            },
            "previous_memory_head": None,
            "previous_memory_hash": "",
            "feedback_hash": _canonical_hash({"feedback_rows": rows}),
        }
        validated = validate_slow_input(payload)
        self.assertEqual(validated["feedback_rows"][0]["kind"], "magnitude_feedback")


class EngineWiringTest(unittest.TestCase):
    def test_committed_slow_feedback_consumes_magnitude_rows(self):
        source = inspect.getsource(SignalEvolutionEngine._committed_slow_feedback)
        self.assertIn("magnitude_feedback_rows(", source)
        self.assertIn("self.meta_memory.entries", source)


class SlowLoopResultMagnitudeTest(unittest.TestCase):
    def test_default_result_states_magnitude_unassessed(self):
        result = SlowLoopResult(
            mined_candidates=(),
            updated_candidates=(),
            validated_candidates={},
            promoted=(),
            provisional_candidates={},
            rejected={},
            refined_hypotheses={},
            input_registry_version=6,
            input_registry_hash="hash",
            output_registry_version=6,
            output_registry_hash="hash",
        )
        self.assertFalse(result.magnitude_contribution["assessed"])
        self.assertIn("Fast-consumption", result.magnitude_contribution["reason"])
        self.assertNotIn("directional only", result.magnitude_contribution["reason"])

    def test_roundtrip_preserves_default_and_custom(self):
        result = SlowLoopResult(
            mined_candidates=(),
            updated_candidates=(),
            validated_candidates={},
            promoted=(),
            provisional_candidates={},
            rejected={},
            refined_hypotheses={},
            input_registry_version=6,
            input_registry_hash="hash",
            output_registry_version=6,
            output_registry_hash="hash",
        )
        restored = SlowLoopResult.from_dict(result.to_dict())
        self.assertFalse(restored.magnitude_contribution["assessed"])
        custom = dict(result.to_dict())
        custom["magnitude_contribution"] = {
            "assessed": True,
            "experiment": "plan-consumption",
        }
        restored_custom = SlowLoopResult.from_dict(custom)
        self.assertTrue(restored_custom.magnitude_contribution["assessed"])
        historical = dict(result.to_dict())
        historical["magnitude_contribution"] = {
            "assessed": False,
            "reason": "historical directional-only promotion policy",
        }
        self.assertEqual(SlowLoopResult.from_dict(historical).magnitude_contribution,
                         historical["magnitude_contribution"])
        historical.pop("magnitude_contribution")
        self.assertEqual(SlowLoopResult.from_dict(historical).magnitude_contribution,
                         result.magnitude_contribution)


if __name__ == "__main__":
    unittest.main()
