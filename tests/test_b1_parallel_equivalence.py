"""B1 bounded parallel Plan evaluation: concurrency-1 byte equivalence (plan C2)."""

import filecmp
import tempfile
import threading
import unittest
from pathlib import Path

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.research.plan_evolution import (
    EvaluationCancelled,
    PlanEvolutionEngine,
)


def _run_round(root: Path, *, evaluator_factory, max_parallel_plans, cancel=None):
    registry = SignalRegistry(root / "signals")
    registry.install_catalog(SEED_CATALOG)
    for stats_path in (root / "signals").rglob("stats.json"):
        stats_path.unlink()
    workspace = EvolutionWorkspace(root / "workspace")
    engine = PlanEvolutionEngine(
        archive=workspace.restore_archive(),
        meta_memory=workspace.restore_meta(),
        signal_registry=registry,
        evaluator=SyntheticPlanEvaluator(),
        proposer=CountingProposer(),
        critic=SimpleCritic(),
        round_reflector=SimpleRoundReflector(),
        workspace=workspace,
        seed_plans=(default_information_plan(),),
        candidates_per_round=2,
        evaluator_factory=evaluator_factory,
        max_parallel_plans=max_parallel_plans,
        cancel_event=cancel,
    )
    engine.run_round(
        round_id=1,
        validation_cases=make_evaluation_pool(),
        anchor_cases=make_anchor_pool(),
        signal_snapshot=registry.freeze(),
    )
    return workspace


def _artifact_bytes(workspace_root: Path) -> dict[str, bytes]:
    artifacts: dict[str, bytes] = {}
    plans_root = workspace_root / "plans"
    for record_path in sorted(plans_root.glob("*/record.json")):
        artifacts[str(record_path.relative_to(workspace_root))] = record_path.read_bytes()
    meta_path = workspace_root / "meta" / "round-0001.json"
    artifacts["meta/round-0001.json"] = meta_path.read_bytes()
    return artifacts


class B1ParallelEquivalenceTest(unittest.TestCase):
    def test_concurrency_one_matches_sequential_engine_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sequential = _run_round(
                root / "sequential",
                evaluator_factory=None,
                max_parallel_plans=1,
            )
            parallel = _run_round(
                root / "parallel1",
                evaluator_factory=lambda: SyntheticPlanEvaluator(),
                max_parallel_plans=1,
            )
            left = _artifact_bytes(Path(sequential.root))
            right = _artifact_bytes(Path(parallel.root))
            self.assertEqual(sorted(left), sorted(right))
            for key in left:
                self.assertEqual(
                    left[key],
                    right[key],
                    f"artifact differs: {key}",
                )
            self.assertEqual(parallel.last_completed_round, 1)

    def test_concurrency_two_completes_with_identical_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sequential = _run_round(
                root / "sequential",
                evaluator_factory=None,
                max_parallel_plans=1,
            )
            parallel = _run_round(
                root / "parallel2",
                evaluator_factory=lambda: SyntheticPlanEvaluator(),
                max_parallel_plans=2,
            )
            left = _artifact_bytes(Path(sequential.root))
            right = _artifact_bytes(Path(parallel.root))
            self.assertEqual(sorted(left), sorted(right))
            for key in left:
                self.assertEqual(left[key], right[key], key)
            self.assertEqual(parallel.last_completed_round, 1)

    def test_parallel_requires_factory_above_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = EvolutionWorkspace(root / "workspace")
            with self.assertRaisesRegex(
                ValidationError, "evaluator factory"
            ):
                PlanEvolutionEngine(
                    archive=workspace.restore_archive(),
                    meta_memory=workspace.restore_meta(),
                    signal_registry=SignalRegistry(root / "signals"),
                    evaluator=SyntheticPlanEvaluator(),
                    proposer=CountingProposer(),
                    critic=SimpleCritic(),
                    round_reflector=SimpleRoundReflector(),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=1,
                    max_parallel_plans=2,
                )

    def test_pre_set_cancel_stops_admission_before_any_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cancel = threading.Event()
            cancel.set()
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            engine = PlanEvolutionEngine(
                archive=workspace.restore_archive(),
                meta_memory=workspace.restore_meta(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=2,
                evaluator_factory=lambda: SyntheticPlanEvaluator(),
                max_parallel_plans=1,
                cancel_event=cancel,
            )
            with self.assertRaises(EvaluationCancelled):
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 0)
            plans_root = Path(workspace.root) / "plans"
            self.assertFalse(
                plans_root.exists() and any(plans_root.iterdir()),
                "no candidate evaluation record may exist after cancellation",
            )


if __name__ == "__main__":
    unittest.main()
