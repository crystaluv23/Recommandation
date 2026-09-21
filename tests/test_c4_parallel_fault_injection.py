"""C4 fault-injection matrix on the parallel evaluate path (concurrency 2).

Extends the P6 matrix to plan B: reverse completion order, worker exception,
pre-commit crash, and coordinator-only event emission. All scenarios use the
real PlanEvolutionEngine with scripted roles; no external calls.
"""

import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.research.plan_evolution import (
    EvaluationCancelled,
    PlanEvolutionEngine,
)


class _TimedEvaluator:
    """Slot-dependent timing to force completion-order inversion."""

    def __init__(self, delays: dict[str, float]) -> None:
        self.delays = delays

    def evaluate(self, plan, cases, signal_registry):
        time.sleep(self.delays.get(plan.plan_id, 0.0))
        return SyntheticPlanEvaluator().evaluate(plan, cases, signal_registry)


class _FailingSlotEvaluator:
    def __init__(self, failing_plan_id: str) -> None:
        self.failing_plan_id = failing_plan_id

    def evaluate(self, plan, cases, signal_registry):
        if plan.plan_id == self.failing_plan_id:
            raise RuntimeError("simulated worker exception during evaluation")
        return SyntheticPlanEvaluator().evaluate(plan, cases, signal_registry)


def _build(root: Path, *, factory, parallel=2, events=None, on_progress=None):
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
        evaluator_factory=factory,
        max_parallel_plans=parallel,
        on_progress=on_progress,
    )
    return engine, workspace, registry


def _run_round(engine, registry):
    engine.run_round(
        round_id=1,
        validation_cases=make_evaluation_pool(),
        anchor_cases=make_anchor_pool(),
        signal_snapshot=registry.freeze(),
    )


def _artifact_bytes(workspace_root: Path) -> dict[str, bytes]:
    root = Path(workspace_root)
    artifacts = {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted((root / "plans").glob("*/record.json"))
    }
    artifacts["meta/round-0001.json"] = (root / "meta" / "round-0001.json").read_bytes()
    return artifacts


class C4ReverseCompletionOrderTest(unittest.TestCase):
    """Completion order inversion must not change slot-ordered results."""

    def test_slow_first_slot_keeps_slot_order_artifacts_and_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events: list[dict] = []
            guard = threading.Lock()

            def on_progress(event):
                with guard:
                    events.append(
                        {
                            "event_type": event.get("event_type"),
                            "candidate_index": event.get("candidate_index"),
                            "thread": threading.current_thread().name,
                        }
                    )

            delays = {"plan_child_1": 0.25, "plan_child_2": 0.0}
            engine, workspace, registry = _build(
                root,
                factory=lambda: _TimedEvaluator(delays),
                on_progress=on_progress,
            )
            _run_round(engine, registry)
            self.assertEqual(workspace.last_completed_round, 1)

            sequential_root = root / "sequential"
            seq_engine, seq_workspace, seq_registry = _build(
                sequential_root, factory=None, parallel=1
            )
            _run_round(seq_engine, seq_registry)
            self.assertEqual(
                _artifact_bytes(Path(workspace.root)),
                _artifact_bytes(Path(seq_workspace.root)),
            )

            started = [
                event["candidate_index"]
                for event in events
                if event["event_type"] == "candidate_evaluation_started"
            ]
            self.assertEqual(started, [1, 2])
            scored = [
                event["candidate_index"]
                for event in events
                if event["event_type"] == "candidate_scored"
            ]
            self.assertEqual(scored, [1, 2])
            self.assertTrue(all(event["thread"] == "MainThread" for event in events))


class C4WorkerExceptionTest(unittest.TestCase):
    """A worker exception crashes the round without false commits; recovery works."""

    def test_failing_slot_preserves_sibling_staging_and_recovers_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine, workspace, registry = _build(
                root, factory=lambda: _FailingSlotEvaluator("plan_child_2")
            )
            with self.assertRaisesRegex(RuntimeError, "simulated worker exception"):
                _run_round(engine, registry)
            self.assertEqual(workspace.last_completed_round, 0)
            plans_root = Path(workspace.root) / "plans"
            self.assertFalse(plans_root.exists() and any(plans_root.iterdir()))
            experiments_root = Path(workspace.root) / "experiments"
            staged_attempts = list(experiments_root.rglob("*.json"))
            self.assertTrue(staged_attempts, "sibling attempt staging is preserved")

            recovered, workspace2, registry2 = _build(
                root, factory=lambda: SyntheticPlanEvaluator()
            )
            _run_round(recovered, registry2)
            self.assertEqual(workspace2.last_completed_round, 1)
            restored_meta = workspace2.restore_meta()
            self.assertEqual(
                [entry.round_id for entry in restored_meta.entries], [1]
            )
            all_events = registry2.load_learning_events("revenue_growth_yoy:v1")
            event_ids = [event.event_id for event in all_events]
            self.assertEqual(len(event_ids), len(set(event_ids)))


class C4PreCommitCrashTest(unittest.TestCase):
    """Crash after evaluation, before the commit barrier, commits exactly once."""

    def test_commit_barrier_crash_recovers_with_single_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine, workspace, registry = _build(
                root, factory=lambda: SyntheticPlanEvaluator()
            )
            original = type(workspace).commit_round

            def crash_once(self_workspace, **kwargs):
                type(self_workspace).commit_round = original
                raise RuntimeError("simulated crash before round commit")

            type(workspace).commit_round = crash_once
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                _run_round(engine, registry)
            self.assertEqual(workspace.last_completed_round, 0)
            self.assertTrue(
                list((Path(workspace.root) / "experiments").rglob("*.json"))
            )

            recovered, workspace2, registry2 = _build(
                root, factory=lambda: SyntheticPlanEvaluator()
            )
            _run_round(recovered, registry2)
            self.assertEqual(workspace2.last_completed_round, 1)
            restored_meta = workspace2.restore_meta()
            self.assertEqual(
                [entry.round_id for entry in restored_meta.entries], [1]
            )
            self.assertEqual(len(workspace2.restore_archive().records), 2)
            all_events = registry2.load_learning_events("revenue_growth_yoy:v1")
            event_ids = [event.event_id for event in all_events]
            self.assertEqual(len(event_ids), len(set(event_ids)))


class C4StopUnderConcurrencyTest(unittest.TestCase):
    """Stop during in-flight candidate work at concurrency 2."""

    def test_stop_mid_round_leaves_staged_work_and_clean_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cancel = threading.Event()

            class CancellingSlowEvaluator:
                def evaluate(self, plan, cases, signal_registry):
                    cancel.set()
                    time.sleep(0.05)
                    return SyntheticPlanEvaluator().evaluate(
                        plan, cases, signal_registry
                    )

            engine, workspace, registry = _build(
                root, factory=lambda: CancellingSlowEvaluator()
            )
            engine.cancel_event = cancel
            with self.assertRaises(EvaluationCancelled):
                _run_round(engine, registry)
            self.assertEqual(workspace.last_completed_round, 0)
            plans_root = Path(workspace.root) / "plans"
            self.assertFalse(plans_root.exists() and any(plans_root.iterdir()))


if __name__ == "__main__":
    unittest.main()
