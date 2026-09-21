"""Per-case technical-exclusion carry-over (user-approved 2026-09-21).

A CandidateExecutionRejected case records its failure, abstains as a real
finalized negative prediction (insufficient_information), stays in the
label-blind confusion matrix, and never blocks the candidate while at most
MAX_TECHNICAL_CASE_EXCLUSIONS cases are excluded. Control-plane errors and
cap overflow keep the previous rejection semantics.
"""

import tempfile
import unittest
from pathlib import Path

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    CandidateExecutionRejected,
    assess_fitness_eligibility,
    score_predictions,
)
from stock_opportunity_agent.research.plan_evolution import (
    MAX_TECHNICAL_CASE_EXCLUSIONS,
    CaseEvaluationFailure,
    PlanEvaluationAttempt,
)


def _attempt(expected, trajectories, failures):
    return PlanEvaluationAttempt(
        plan=default_information_plan(),
        expected_case_ids=tuple(expected),
        trajectories=tuple(trajectories),
        failures=tuple(failures),
    )


def _abstain_trajectory(case):
    """A finalized insufficient_information abstain with a persisted ref."""

    from dataclasses import replace

    base = make_trajectory(
        case.company_id,
        float(case.ground_truth.realized_max_multiple),
        False,
        None,
        case_id=case.case_id,
    )
    prediction = BlindPrediction(
        is_surge=False,
        candidate_judgment=CandidateJudgment.INSUFFICIENT_INFORMATION,
        magnitude=None,
        confidence=ConfidenceLevel.LOW,
        key_reasons=("Technical exclusion abstention.",),
        uncertainties=(),
        session_id=f"exclusion_{case.case_id}",
    )
    return replace(
        base,
        prediction=prediction,
        prediction_ref=f"predictions/abstain_{case.case_id}.json",
    )


class CarryOverAttemptTest(unittest.TestCase):
    def _cases(self):
        return (
            make_case("carry_pos", 4.0),
            make_case("carry_neg", 1.2),
            make_case("carry_pos2", 5.0),
        )

    def _trajectories_with_abstain(self, cases, abstain_index):
        rows = []
        for index, case in enumerate(cases):
            if index == abstain_index:
                rows.append(_abstain_trajectory(case))
            else:
                rows.append(
                    make_trajectory(
                        case.company_id,
                        float(case.ground_truth.realized_max_multiple),
                        case.ground_truth.is_surge,
                        case.ground_truth.magnitude if case.ground_truth.is_surge else None,
                        case_id=case.case_id,
                    )
                )
        return tuple(rows)

    def test_within_cap_exclusion_scores_and_stays_eligible(self):
        cases = self._cases()
        failing_case = cases[0]
        trajectories = self._trajectories_with_abstain(cases, abstain_index=0)
        failure = CaseEvaluationFailure(
            case_id=failing_case.case_id,
            stage="research_controller_initialize_correction",
            error_type="CandidateExecutionRejected",
            message="no-progress identical correction request",
            artifact_ref="experiments/trajectories/x/failure.json",
        )
        attempt = _attempt(
            [case.case_id for case in cases], trajectories, [failure]
        )
        self.assertEqual(
            attempt.technical_exclusion_case_ids, (failing_case.case_id,)
        )
        metrics = attempt.metrics
        self.assertIsNotNone(metrics)
        # Abstain on a surge truth counts as FN; the other surge is 1 TP.
        self.assertEqual(metrics.false_negative, 1)
        self.assertEqual(metrics.true_positive, 1)
        fitness = attempt.fitness
        self.assertTrue(fitness.eligible, fitness.reasons)
        serialized = attempt.to_dict()
        self.assertEqual(
            serialized["technical_exclusion_case_ids"],
            [failing_case.case_id],
        )

    def test_over_cap_stays_rejected_with_metrics_none(self):
        cases = (
            self._cases()
            + (make_case("carry_x1", 6.0), make_case("carry_x2", 7.0))
        )
        trajectories = self._trajectories_with_abstain(cases, abstain_index=0)
        # Three distinct fresh failures (plus one replayed abstain) exceed
        # the cumulative per-candidate cap.
        failures = tuple(
            CaseEvaluationFailure(
                case_id=case.case_id,
                stage="s",
                error_type="CandidateExecutionRejected",
                message="m",
                artifact_ref="a",
            )
            for case in cases[2:5]
        )
        attempt = _attempt(
            [case.case_id for case in cases], trajectories, failures
        )
        self.assertEqual(attempt.technical_exclusion_case_ids, ())
        self.assertIsNone(attempt.metrics)

    def test_fitness_assessor_skips_source_evidence_only_for_exclusions(self):
        cases = self._cases()
        rows = self._trajectories_with_abstain(cases, abstain_index=0)
        with_skip = assess_fitness_eligibility(
            rows,
            expected_case_ids=[case.case_id for case in cases],
            technical_exclusion_case_ids=[cases[0].case_id],
        )
        self.assertTrue(with_skip.eligible, with_skip.reasons)
        # The abstain row carries no source evidence; without the exclusion
        # marker that gap must still block eligibility.
        from dataclasses import replace as _replace

        evidence_free = _replace(
            rows[0],
            basic_info={"requests": []},
            signal_rounds=(),
        )
        blocked = assess_fitness_eligibility(
            (evidence_free, *rows[1:]),
            expected_case_ids=[case.case_id for case in cases],
        )
        self.assertIn("missing_source_evidence", blocked.reasons)


class EvaluatorCarryOverTest(unittest.TestCase):
    """The inline abstain path through RuntimePlanEvaluator.evaluate."""

    def test_first_case_rejection_carries_over_and_scores(self):
        import tempfile

        from stock_opportunity_agent.research.plan_evolution import (
            RuntimePlanEvaluator,
        )

        class StubPredictor:
            def predict(self, final_context):
                return AgentStep(
                    BlindPrediction(
                        is_surge=False,
                        candidate_judgment=CandidateJudgment.UNLIKELY,
                        magnitude=None,
                        confidence=ConfidenceLevel.LOW,
                        key_reasons=("stub",),
                        uncertainties=(),
                        session_id="s",
                    ),
                    AgentUsage(),
                )

            def reflect(self, ctx, prediction, truth):
                return AgentStep(
                    PredictionSelfReflection(correct=not truth.is_surge),
                    AgentUsage(),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)

            class FailingOnceController:
                def __init__(self) -> None:
                    self.calls = 0

                def initialize(self, plan, basic_info):
                    self.calls += 1
                    if self.calls == 1:
                        raise CandidateExecutionRejected(
                            "research_controller_initialize",
                            "simulated guard rejection",
                        )
                    return AgentStep(
                        ResearchState(decision=ResearchDecision.FINALIZE),
                        AgentUsage(),
                    )

                def reflect(self, *args, **kwargs):
                    return AgentStep(
                        ResearchState(decision=ResearchDecision.FINALIZE),
                        AgentUsage(),
                    )

            evaluator = RuntimePlanEvaluator(
                raw_info_store=RawInfoStore(documents=()),
                controller=FailingOnceController(),
                signal_agent=None,
                predictor=StubPredictor(),
                prediction_root=root / "predictions",
            )
            cases = (make_case("c1", 4.0), make_case("c2", 1.2))
            attempt = evaluator.evaluate(
                default_information_plan(), cases, registry.freeze()
            )
            self.assertEqual(len(attempt.failures), 1)
            self.assertEqual(len(attempt.trajectories), 2)
            self.assertEqual(len(attempt.technical_exclusion_case_ids), 1)
            metrics = attempt.metrics
            self.assertIsNotNone(metrics)
            self.assertEqual(metrics.false_negative, 1)


class CumulativeCapAcrossRestartTest(unittest.TestCase):
    """The exclusion cap counts replayed abstains after a restart."""

    def test_replayed_abstains_plus_fresh_failure_exceeds_cap(self):
        import tempfile

        from stock_opportunity_agent.research.plan_evolution import (
            RuntimePlanEvaluator,
        )

        class StubPredictor:
            def predict(self, final_context):
                return AgentStep(
                    BlindPrediction(
                        is_surge=False,
                        candidate_judgment=CandidateJudgment.UNLIKELY,
                        magnitude=None,
                        confidence=ConfidenceLevel.LOW,
                        key_reasons=("stub",),
                        uncertainties=(),
                        session_id="s",
                    ),
                    AgentUsage(),
                )

            def reflect(self, ctx, prediction, truth):
                return AgentStep(
                    PredictionSelfReflection(correct=not truth.is_surge),
                    AgentUsage(),
                )

        class ControlledController:
            def __init__(self, fail_on):
                self.fail_on = set(fail_on)
                self.calls = 0

            def initialize(self, plan, basic_info):
                self.calls += 1
                if self.calls in self.fail_on:
                    raise CandidateExecutionRejected(
                        "research_controller_initialize",
                        "simulated rejection",
                    )
                return AgentStep(
                    ResearchState(decision=ResearchDecision.FINALIZE),
                    AgentUsage(),
                )

            def reflect(self, *args, **kwargs):
                return AgentStep(
                    ResearchState(decision=ResearchDecision.FINALIZE),
                    AgentUsage(),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(make_case(f"c{i}", m) for i, m in enumerate((4.0, 1.2, 5.0, 1.1, 6.0)))

            def build(fail_on):
                return RuntimePlanEvaluator(
                    raw_info_store=RawInfoStore(documents=()),
                    controller=ControlledController(fail_on),
                    signal_agent=None,
                    predictor=StubPredictor(),
                    prediction_root=root / "predictions",
                )

            first = build({1, 2}).evaluate(
                default_information_plan(), cases, registry.freeze()
            )
            self.assertEqual(len(first.technical_exclusion_case_ids), 2)
            self.assertIsNotNone(first.metrics)
            checkpoint_files = list(
                (root / "trajectories").glob("*/*.json")
            )
            self.assertTrue(checkpoint_files, "abstain checkpoints persisted")

            # Simulate the crash point: only the two abstain checkpoints
            # existed when the process died; later cases restart fresh.
            for case in cases[2:]:
                for path in (root / "trajectories").glob(
                    f"*/{case.case_id}.json"
                ):
                    path.unlink()
            restarted = build({1}).evaluate(
                default_information_plan(), cases, registry.freeze()
            )
            # Two abstains replay from disk (the controller never re-runs
            # them); a third fresh failure pushes the cumulative total to
            # 3 > 2, so metrics stay None (rejection semantics preserved
            # across restart).
            self.assertEqual(len(restarted.failures), 1)
            self.assertEqual(len(restarted.technical_exclusion_case_ids), 0)
            self.assertIsNone(restarted.metrics)


class InitializeCombinedConstraintTest(unittest.TestCase):
    def test_initialize_prompt_names_simultaneous_obligations(self):
        import inspect

        from stock_opportunity_agent.research.evolution_plan_roles import (
            LLMResearchController,
        )

        source = inspect.getsource(LLMResearchController)
        self.assertIn(
            "satisfy every prior obligation simultaneously", source
        )
        self.assertIn("out-of-horizon condition", source)


if __name__ == "__main__":
    unittest.main()


class StagedAttemptSupersessionTest(unittest.TestCase):
    """A diagnostic staged attempt may be superseded after restart."""

    def _workspace(self, root):
        return EvolutionWorkspace(root / "workspace")

    def _attempt(self, plan_id, expected, trajectories, failures):
        from stock_opportunity_agent.research.plan_evolution import (
            PlanEvaluationAttempt,
        )

        base = default_information_plan()
        plan = InformationPlan(
            plan_id=plan_id,
            parent_ids=(),
            basic_info_policy=base.basic_info_policy,
            initial_research_skill=f"{base.initial_research_skill} {plan_id}",
            reflection_skill=base.reflection_skill,
            analysis_prompt=base.analysis_prompt,
        )
        return PlanEvaluationAttempt(
            plan=plan,
            expected_case_ids=tuple(expected),
            trajectories=tuple(trajectories),
            failures=tuple(failures),
        )

    def test_diagnostic_attempt_superseded_eligible_stays_frozen(self):
        import tempfile

        from stock_opportunity_agent.research.plan_evolution import (
            CaseEvaluationFailure,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._workspace(root)
            case = make_case("sup", 4.0)
            good = make_trajectory(
                case.company_id, 4.0, True, MagnitudeClass.THREE_TO_TEN
            )
            expected = (case.case_id,)
            failure = CaseEvaluationFailure(
                case_id=case.case_id,
                stage="s",
                error_type="CandidateExecutionRejected",
                message="m",
                artifact_ref="a",
            )
            # 1) diagnostic attempt (abstain row, failure) staged
            abstain = good.__class__(
                **{
                    **good.__dict__,
                    "prediction": BlindPrediction(
                        is_surge=False,
                        candidate_judgment=CandidateJudgment.INSUFFICIENT_INFORMATION,
                        magnitude=None,
                        confidence=ConfidenceLevel.LOW,
                        key_reasons=("exclusion",),
                        uncertainties=(),
                        session_id=f"exclusion_{case.case_id}",
                    ),
                }
            )
            first = self._attempt(
                "plan_r0001_c01", expected, (abstain,), [failure]
            )
            workspace.stage_evaluation_attempt(round_id=1, attempt=first)

            # 2) retry with different content supersedes it
            second = self._attempt("plan_r0001_c01", expected, (good,), ())
            path = workspace.stage_evaluation_attempt(round_id=1, attempt=second)
            self.assertTrue(
                (path.parent / "superseded" / "plan_r0001_c01-001.json").exists()
            )
            staged = json.loads(path.read_text())
            self.assertEqual(len(staged["failures"]), 0)

            # 3) an eligible attempt is verify-only: differing content fails
            with self.assertRaises(ValidationError):
                workspace.stage_evaluation_attempt(
                    round_id=1, attempt=first
                )
