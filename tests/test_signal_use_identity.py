"""Source-bound use identity across reused run names, exact imports and restart."""

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import _signal_learning_events_from_record
from stock_opportunity_agent.research.signal_tracking import record_committed_signal_use, target_use_profiles
from stock_opportunity_agent.signal_library import SignalLearningEvent
from tests.scheme_evolution_test_support import (
    CountingProposer, EvolutionWorkspace, MagnitudeClass, PlanArchive, PlanEvolutionEngine,
    PlanMetaMemory, PlanRecord, SEED_CATALOG, SignalRegistry, SignalResult, SignalValue,
    SimpleCritic, SimpleRoundReflector, SyntheticPlanEvaluator, default_information_plan,
    make_record, make_trajectory,
)


class SignalUseIdentityTests(TestCase):
    def record(self):
        record = make_record("plan_r0001_c02", 1.0, (1.0,))
        trajectory = make_trajectory("issuer-1", 2.5, True, MagnitudeClass.TWO_TO_THREE,
            case_id=record.trajectories[0].case_id,
            signal_result=SignalResult(signal_id="revenue_growth_yoy", version=1,
                value=SignalValue.POSITIVE, confidence=1.0, interpretation="Reported growth."))
        return replace(record, trajectories=(trajectory,))

    def registry(self, root):
        registry = SignalRegistry(root / "signals")
        registry.install_catalog(SEED_CATALOG)
        return registry

    def engine(self, root, registry, records):
        return PlanEvolutionEngine(archive=PlanArchive(records=records), meta_memory=PlanMetaMemory(),
            signal_registry=registry, evaluator=SyntheticPlanEvaluator(), proposer=CountingProposer(),
            critic=SimpleCritic(), round_reflector=SimpleRoundReflector(),
            workspace=EvolutionWorkspace(root / "workspace"), seed_plans=(default_information_plan(),))

    def test_reused_names_retain_source_history_and_one_physical_observation(self):
        first = self.record()
        second = replace(first, plan=replace(first.plan,
            analysis_prompt=first.plan.analysis_prompt + " Review contrary evidence."))
        original = _signal_learning_events_from_record(first)[0]
        other = _signal_learning_events_from_record(second)[0]
        self.assertNotEqual(original.event_id, other.event_id)
        self.assertEqual(original.observation_key, other.observation_key)
        self.assertEqual(original.source_record_hash, canonical_json_hash(first.to_dict()))
        self.assertEqual(other.source_position, (0, 0))
        with tempfile.TemporaryDirectory() as directory:
            registry = self.registry(Path(directory))
            record_committed_signal_use(registry, (original, other))
            profile = target_use_profiles(registry, original.signal_ref, round_cutoff=1)["surge_direction"]
            self.assertEqual((profile["selection_events"], profile["physical_observations"]), (2, 1))
            self.assertEqual(profile["effect_status"], "unverified")
            events = registry._learning_dir(original.signal_ref) / "events.jsonl"
            before = events.read_bytes()
            restored = PlanRecord.from_dict(json.loads(json.dumps(first.to_dict(), indent=4)))
            self.assertEqual(_signal_learning_events_from_record(restored), (original,))
            self.assertEqual(record_committed_signal_use(registry, (original, other)), 0)
            self.assertEqual(events.read_bytes(), before)

    def test_legacy_import_is_exact_and_does_not_collide_with_new_source(self):
        new = _signal_learning_events_from_record(self.record())[0]
        legacy_value = new.to_dict()
        legacy_value.pop("source")
        legacy_value["schema_version"] = "signal-learning-event-v1"
        legacy_value["event_id"] = canonical_json_hash({"round_id": new.round_id,
            "plan_id": new.plan_id, "case_id": new.case_id, "signal_round": 0,
            "result_index": 0, "signal_ref": new.signal_ref})
        legacy = SignalLearningEvent.from_dict(legacy_value)
        self.assertEqual(legacy.to_dict(), legacy_value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self.registry(root)
            record_committed_signal_use(registry, (legacy,))
            record_committed_signal_use(registry, (new,))
            reopened = SignalRegistry(root / "signals")
            self.assertEqual(record_committed_signal_use(reopened, (legacy, new)), 0)
            self.assertEqual(reopened.load_learning_events(new.signal_ref), (legacy, new))
            self.assertEqual(len(reopened.load_target_evaluations(new.signal_ref)), 1)

    def test_source_binding_tampering_and_exact_content_collision_are_rejected(self):
        event = _signal_learning_events_from_record(self.record())[0]
        for source in ({}, {"record_hash": None, "signal_round": 0, "result_index": 0},
                       {"record_hash": "a" * 64, "signal_round": True, "result_index": 0},
                       {"record_hash": event.source_record_hash, "signal_round": 1, "result_index": 0}):
            with self.subTest(source=source), self.assertRaises(ValidationError):
                SignalLearningEvent.from_dict({**event.to_dict(), "source": source})
        with tempfile.TemporaryDirectory() as directory:
            registry = self.registry(Path(directory))
            registry.record_learning_events((event,))
            before = (registry._learning_dir(event.signal_ref) / "events.jsonl").read_bytes()
            changed = replace(event, selection={**event.selection, "selection_reason": "Different intent."})
            with self.assertRaisesRegex(ValidationError, "conflicting Signal learning event id"):
                registry.record_learning_events((changed,))
            self.assertEqual((registry._learning_dir(event.signal_ref) / "events.jsonl").read_bytes(), before)

    def test_statistics_and_learning_restore_after_derivative_interruption(self):
        first = self.record()
        second = replace(first, plan=replace(first.plan,
            reflection_skill=first.plan.reflection_skill + " Preserve unresolved needs."))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self.registry(root)
            with patch.object(registry, "record_target_evaluations", side_effect=OSError("interrupted")):
                with self.assertRaisesRegex(OSError, "interrupted"):
                    self.engine(root / "first-source", registry, (first,))
            self.assertEqual(len(registry.load_learning_events("revenue_growth_yoy:v1")), 1)
            self.assertEqual(registry.load_target_evaluations("revenue_growth_yoy:v1"), ())
            for _ in range(2):
                self.engine(root / "first-source", registry, (first,))
                self.engine(root / "second-source", registry, (second,))
            stats = registry.load_stats("revenue_growth_yoy")
            self.assertEqual((stats.retrieved, stats.executed), (2, 2))
            self.assertEqual(len(registry.load_learning_events("revenue_growth_yoy:v1")), 2)
            self.assertEqual(len(registry.load_target_evaluations("revenue_growth_yoy:v1")), 1)
