"""Deterministic magnitude feedback and diagnostics (action-plan P2)."""

import unittest

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import (
    CaseReflectionEvidence,
    FitnessEligibility,
    PlanEvaluationSummary,
    PlanMetaReflection,
    PlanRecord,
    magnitude_diagnostics,
    magnitude_feedback,
    score_predictions,
)


def _feedback(multiple, predicted_surge, predicted_magnitude):
    trajectory = make_trajectory(
        "case_fb", multiple, predicted_surge, predicted_magnitude
    )
    return magnitude_feedback(trajectory.prediction, trajectory.ground_truth)


class MagnitudeFeedbackTest(unittest.TestCase):
    def test_correct_positive_prediction(self):
        block = _feedback(2.5, True, MagnitudeClass.TWO_TO_THREE)
        self.assertEqual(
            block,
            {
                "magnitude_applicable": True,
                "predicted_magnitude": "2-3x",
                "true_magnitude": "2-3x",
                "magnitude_correct": True,
                "error_kind": "correct",
                "ordinal_distance": 0,
            },
        )

    def test_underestimate_distances(self):
        near = _feedback(5.0, True, MagnitudeClass.TWO_TO_THREE)
        far = _feedback(15.0, True, MagnitudeClass.TWO_TO_THREE)
        self.assertEqual(
            (near["error_kind"], near["ordinal_distance"]),
            ("underestimate", 1),
        )
        self.assertEqual(
            (far["error_kind"], far["ordinal_distance"]),
            ("underestimate", 2),
        )

    def test_overestimate(self):
        block = _feedback(2.5, True, MagnitudeClass.TEN_PLUS)
        self.assertEqual(block["error_kind"], "overestimate")
        self.assertEqual(block["ordinal_distance"], 2)
        self.assertFalse(block["magnitude_correct"])

    def test_missed_surge_never_fabricates_class_or_distance(self):
        block = _feedback(2.5, False, None)
        self.assertEqual(block["error_kind"], "missed_surge")
        self.assertIsNone(block["predicted_magnitude"])
        self.assertIsNone(block["ordinal_distance"])
        self.assertFalse(block["magnitude_correct"])

    def test_false_positive_is_not_applicable_and_keeps_predicted_class(self):
        block = _feedback(1.5, True, MagnitudeClass.TWO_TO_THREE)
        self.assertFalse(block["magnitude_applicable"])
        self.assertEqual(block["error_kind"], "not_applicable")
        self.assertIsNone(block["true_magnitude"])
        self.assertEqual(block["predicted_magnitude"], "2-3x")

    def test_true_negative_is_not_applicable(self):
        block = _feedback(1.5, False, None)
        self.assertEqual(block["error_kind"], "not_applicable")
        self.assertIsNone(block["predicted_magnitude"])
        self.assertIsNone(block["true_magnitude"])

    def test_boundary_multiples(self):
        self.assertEqual(_feedback(2.0, True, MagnitudeClass.TWO_TO_THREE)["true_magnitude"], "2-3x")
        self.assertEqual(_feedback(3.0, True, MagnitudeClass.THREE_TO_TEN)["true_magnitude"], "3-10x")
        self.assertEqual(_feedback(10.0, True, MagnitudeClass.TEN_PLUS)["true_magnitude"], "10x+")


def _v130_shaped_trajectories():
    rows = []
    index = 0

    def add(multiple, predicted_surge, predicted_magnitude):
        nonlocal index
        index += 1
        rows.append(
            make_trajectory(
                f"case_{index:02d}",
                multiple,
                predicted_surge,
                predicted_magnitude,
            )
        )

    for _ in range(6):
        add(1.5, False, None)
    for _ in range(4):
        add(1.2, True, MagnitudeClass.TWO_TO_THREE)
    for _ in range(5):
        add(2.5, True, MagnitudeClass.TWO_TO_THREE)
    for _ in range(2):
        add(2.8, False, None)
    for _ in range(5):
        add(5.0, True, MagnitudeClass.TWO_TO_THREE)
    for _ in range(2):
        add(15.0, True, MagnitudeClass.TWO_TO_THREE)
    return tuple(rows)


class MagnitudeDiagnosticsTest(unittest.TestCase):
    def test_v130_shape_reproduces_audit_matrix(self):
        rows = _v130_shaped_trajectories()
        diagnostics = magnitude_diagnostics(rows)
        self.assertEqual(
            diagnostics["confusion_matrix"],
            {
                "non_surge": {
                    "predicted_negative": 6,
                    "predicted_2-3x": 4,
                    "predicted_3-10x": 0,
                    "predicted_10x+": 0,
                },
                "2-3x": {
                    "predicted_negative": 2,
                    "predicted_2-3x": 5,
                    "predicted_3-10x": 0,
                    "predicted_10x+": 0,
                },
                "3-10x": {
                    "predicted_negative": 0,
                    "predicted_2-3x": 5,
                    "predicted_3-10x": 0,
                    "predicted_10x+": 0,
                },
                "10x+": {
                    "predicted_negative": 0,
                    "predicted_2-3x": 2,
                    "predicted_3-10x": 0,
                    "predicted_10x+": 0,
                },
            },
        )
        self.assertEqual(
            diagnostics["per_class_support"],
            {"2-3x": 7, "3-10x": 5, "10x+": 2},
        )
        self.assertEqual(diagnostics["underestimate_count"], 7)
        self.assertEqual(diagnostics["overestimate_count"], 0)
        self.assertEqual(diagnostics["missed_surge_count"], 2)
        self.assertEqual(diagnostics["surge_case_count"], 14)
        self.assertEqual(diagnostics["magnitude_correct_count"], 5)
        self.assertAlmostEqual(
            diagnostics["conditional_accuracy_on_tp"],
            5 / 12,
        )
        self.assertEqual(diagnostics["tp_denominator"], 12)
        self.assertIsNone(diagnostics["undefined_reason"])

    def test_aggregates_stay_consistent_with_score_predictions(self):
        rows = _v130_shaped_trajectories()
        metrics = score_predictions(rows)
        diagnostics = magnitude_diagnostics(rows)
        self.assertAlmostEqual(
            metrics.magnitude_accuracy,
            diagnostics["magnitude_correct_count"] / diagnostics["surge_case_count"],
        )
        self.assertAlmostEqual(metrics.false_negative, diagnostics["missed_surge_count"])

    def test_conditional_accuracy_undefined_without_true_positives(self):
        rows = (
            make_trajectory("case_a", 1.5, False, None),
            make_trajectory("case_b", 1.5, True, MagnitudeClass.TWO_TO_THREE),
            make_trajectory("case_c", 2.5, False, None),
        )
        diagnostics = magnitude_diagnostics(rows)
        self.assertEqual(diagnostics["tp_denominator"], 0)
        self.assertIsNone(diagnostics["conditional_accuracy_on_tp"])
        self.assertEqual(diagnostics["undefined_reason"], "no_true_positive_predictions")
        self.assertEqual(diagnostics["missed_surge_count"], 1)


class CaseReflectionEvidenceMagnitudeTest(unittest.TestCase):
    def test_from_trajectory_carries_validated_block(self):
        trajectory = make_trajectory(
            "case_ev", 15.0, True, MagnitudeClass.TWO_TO_THREE
        )
        evidence = CaseReflectionEvidence.from_trajectory(trajectory, case_index=1)
        self.assertEqual(
            evidence.magnitude_feedback["error_kind"],
            "underestimate",
        )
        serialized = evidence.to_dict()
        self.assertIn("magnitude_feedback", serialized)
        restored = CaseReflectionEvidence.from_dict(serialized)
        self.assertEqual(restored.magnitude_feedback, evidence.magnitude_feedback)

    def test_legacy_dict_without_block_loads_as_none(self):
        trajectory = make_trajectory("case_lg", 2.5, True, MagnitudeClass.TWO_TO_THREE)
        serialized = CaseReflectionEvidence.from_trajectory(
            trajectory, case_index=2
        ).to_dict()
        legacy = {
            key: value
            for key, value in serialized.items()
            if key != "magnitude_feedback"
        }
        restored = CaseReflectionEvidence.from_dict(legacy)
        self.assertIsNone(restored.magnitude_feedback)
        self.assertNotIn("magnitude_feedback", restored.to_dict())

    def test_tampered_block_is_rejected(self):
        trajectory = make_trajectory("case_tp", 2.5, True, MagnitudeClass.TWO_TO_THREE)
        serialized = CaseReflectionEvidence.from_trajectory(
            trajectory, case_index=3
        ).to_dict()
        serialized["magnitude_feedback"]["error_kind"] = "overestimate"
        with self.assertRaises(ValidationError):
            CaseReflectionEvidence.from_dict(serialized)

    def test_block_disagreeing_with_binary_labels_is_rejected(self):
        trajectory = make_trajectory("case_bl", 1.5, True, MagnitudeClass.TWO_TO_THREE)
        serialized = CaseReflectionEvidence.from_trajectory(
            trajectory, case_index=4
        ).to_dict()
        serialized["magnitude_feedback"]["magnitude_applicable"] = True
        serialized["magnitude_feedback"]["true_magnitude"] = "2-3x"
        with self.assertRaises(ValidationError):
            CaseReflectionEvidence.from_dict(serialized)


class PlanMetaReflectionMagnitudeTest(unittest.TestCase):
    def _record(self):
        rows = _v130_shaped_trajectories()
        base = default_information_plan()
        plan = InformationPlan(
            plan_id="plan_r0001_c01",
            parent_ids=(),
            basic_info_policy=base.basic_info_policy,
            initial_research_skill=base.initial_research_skill,
            reflection_skill=base.reflection_skill,
            analysis_prompt=base.analysis_prompt,
        )
        metrics = score_predictions(rows)
        return PlanRecord(
            plan=plan,
            round_id=1,
            embedding=(1.0, 0.0),
            metrics=metrics,
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
                predicted_positive_count=16,
                true_positive_count=12,
            ),
        )

    def test_from_record_persists_diagnostics_and_case_blocks(self):
        meta = PlanMetaReflection.from_record(self._record())
        self.assertEqual(
            meta.magnitude_diagnostics["underestimate_count"], 7
        )
        serialized = meta.to_dict()
        self.assertIn("magnitude_diagnostics", serialized)
        self.assertTrue(
            all(
                item.magnitude_feedback is not None
                for item in meta.original_case_reflections
            )
        )

    def test_legacy_serialization_without_diagnostics_loads(self):
        serialized = PlanMetaReflection.from_record(self._record()).to_dict()
        legacy = {
            key: value
            for key, value in serialized.items()
            if key != "magnitude_diagnostics"
        }
        restored = PlanMetaReflection.from_dict(legacy)
        self.assertIsNone(restored.magnitude_diagnostics)

    def test_roundtrip_preserves_diagnostics(self):
        serialized = PlanMetaReflection.from_record(self._record()).to_dict()
        restored = PlanMetaReflection.from_dict(serialized)
        self.assertEqual(
            restored.magnitude_diagnostics,
            PlanMetaReflection.from_record(self._record()).magnitude_diagnostics,
        )


class ParentComparisonMagnitudeDeltaTest(unittest.TestCase):
    def test_same_snapshot_includes_magnitude_delta(self):
        child = make_record("plan_child", 0.8, (1.0, 0.0))
        parent_evidence = ParentPlanReflectionEvidence(
            plan=InformationPlan(
                plan_id="plan_parent",
                parent_ids=(),
                basic_info_policy=child.plan.basic_info_policy,
                initial_research_skill="parent skill",
                reflection_skill="parent reflect",
                analysis_prompt="parent analyse",
            ),
            source_scope="current_archive",
            evaluation_snapshot_ids=("snapshot-x",),
            metrics_by_cohort={
                "anchor": child.metrics,
                "random": child.metrics,
                "combined": child.metrics,
            },
        )
        child_plan = InformationPlan(
            plan_id="plan_child",
            parent_ids=("plan_parent",),
            basic_info_policy=child.plan.basic_info_policy,
            initial_research_skill="child skill",
            reflection_skill="child reflect",
            analysis_prompt="child analyse",
        )
        comparison = build_parent_plan_comparison(
            parent=parent_evidence,
            child_plan=child_plan,
            child_metrics=child.metrics,
            child_snapshot_id="snapshot-x",
        )
        self.assertTrue(comparison["same_evaluation_snapshot"])
        self.assertIn("magnitude_metric_delta", comparison)
        self.assertEqual(
            set(comparison["magnitude_metric_delta"]),
            {"magnitude_accuracy", "magnitude_macro_f1"},
        )

    def test_cross_snapshot_magnitude_delta_is_null(self):
        child = make_record("plan_child2", 0.8, (1.0, 0.0))
        parent_evidence = ParentPlanReflectionEvidence(
            plan=InformationPlan(
                plan_id="plan_parent2",
                parent_ids=(),
                basic_info_policy=child.plan.basic_info_policy,
                initial_research_skill="parent skill",
                reflection_skill="parent reflect",
                analysis_prompt="parent analyse",
            ),
            source_scope="current_archive",
            evaluation_snapshot_ids=("snapshot-other",),
            metrics_by_cohort={},
        )
        child_plan = InformationPlan(
            plan_id="plan_child2",
            parent_ids=("plan_parent2",),
            basic_info_policy=child.plan.basic_info_policy,
            initial_research_skill="child skill",
            reflection_skill="child reflect",
            analysis_prompt="child analyse",
        )
        comparison = build_parent_plan_comparison(
            parent=parent_evidence,
            child_plan=child_plan,
            child_metrics=child.metrics,
            child_snapshot_id="snapshot-x",
        )
        self.assertFalse(comparison["same_evaluation_snapshot"])
        self.assertIsNone(comparison["metric_delta"])
        self.assertIsNone(comparison["magnitude_metric_delta"])


if __name__ == "__main__":
    unittest.main()
