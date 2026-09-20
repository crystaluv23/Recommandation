"""P6 fault-injection matrix: real engines, scripted roles, magnitude context.

One test per scenario row of the action-plan P6 table
(reports/fast-slow-magnitude-evolution-action-plan-20260920.md §P6). Real
PlanEvolutionEngine / SignalEvolutionEngine / adapters run against durable
workspaces; only LLM roles are scripted. Crashes are injected by one-shot
monkeypatched raises, then engines are reconstructed from durable state to
verify idempotent recovery without false commits or promotions.
"""

import json
import unittest
from dataclasses import replace
from pathlib import Path

from tests.scheme_evolution_test_support import *  # noqa: F403
from tests.evolution_runtime_test_support import *  # noqa: F403

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMRoundReflector,
)
from stock_opportunity_agent.research.scheme_evolution import (
    CaseReflectionEvidence,
    PlanMetaReflection,
    PlanMetaMemory,
    RoundMetaEntry,
    magnitude_feedback_rows,
)
from stock_opportunity_agent.research.signal_evolution import (
    SlowLoopResult,
    validate_slow_input,
)
from stock_opportunity_agent.research.evolution_dashboard import (
    _dashboard_selection_key,
)
from stock_opportunity_agent.research.scheme_evolution import binary_f1_fraction


def _committed_magnitude_round(workspace, registry, *, plan_id="plan_mag_r1"):
    """Commit one fast round whose meta carries magnitude diagnostics."""

    record = make_record(plan_id, 1.0, (1.0, 0.0))
    snapshot = registry.freeze()
    workspace.start_or_resume_cycle(
        run_contract_hash="contract-hash",
        target_plan_rounds=1,
        initial_signal_registry_version=snapshot.version,
        initial_signal_registry_hash=snapshot.registry_hash,
        observed_signal_registry_version=snapshot.version,
        observed_signal_registry_hash=snapshot.registry_hash,
    )
    meta_entry = RoundMetaEntry(
        round_id=1,
        evidence_refs=(plan_id,),
    ).append_plan_reflections((PlanMetaReflection.from_record(record),))
    workspace.commit_round(
        round_id=1,
        records=(record,),
        meta_entry=meta_entry,
        signal_registry_version=snapshot.version,
        signal_registry_hash=snapshot.registry_hash,
        run_contract_hash="contract-hash",
    )
    return record, snapshot


def _slow_engine_fixture(root, registry, workspace, mining_model):
    discovery_cases = tuple(
        [make_case(f"discovery_positive_{index}", 4.0) for index in range(4)]
        + [make_case(f"discovery_control_{index}", 1.1) for index in range(4)]
    )
    raw_store = RawInfoStore(
        documents=tuple(
            RawInfoDocument.create(
                document_id=f"matrix-financial-{index}",
                company_id=case.company_id,
                source_type="financials",
                published_at=NOW,
                available_at=NOW,
                content=sec_company_facts_content(
                    ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                    ("2024-01-01", "2024-12-31", 120.0, "2025-01-10"),
                ),
            )
            for index, case in enumerate(discovery_cases)
        )
    )
    return SignalEvolutionEngine(
        registry=registry,
        raw_info_store=raw_store,
        discovery_cases=discovery_cases,
        meta_memory=workspace.restore_meta(),
        workspace=workspace,
        mining_model=mining_model,
        update_model=NoChangeUpdateModel(),
        llm_signal_runner=None,
        mining_config=fixture_mining_config(len(discovery_cases) // 2),
    )


class UniqueIdProposer(CountingProposer):
    """Proposer whose plan ids never repeat across engine rebuilds."""

    counter = 0

    def propose(self, **kwargs):
        call = dict(kwargs)
        UniqueIdProposer.counter += 1
        index = UniqueIdProposer.counter
        self.calls.append(
            {
                "round_id": call["round_id"],
                "meta_rounds": tuple(
                    entry.round_id for entry in call["meta_info"]
                ),
                "meta_infos": tuple(call["meta_info"]),
            }
        )
        base = default_information_plan()
        return InformationPlan(
            plan_id=f"plan_child_{index}",
            parent_ids=tuple(plan.plan_id for plan in call["parents"]),
            basic_info_policy=base.basic_info_policy,
            initial_research_skill=(
                f"{base.initial_research_skill} Variant {index}."
            ),
            reflection_skill=base.reflection_skill,
            analysis_prompt=base.analysis_prompt,
        )


class S1LabelRevealOrderingTest(unittest.TestCase):
    """Scenario 1: magnitude feedback exists only after prediction persistence."""

    def test_blind_call_has_no_truth_and_posthoc_carries_magnitude(self):
        caller = ScriptedRoleCaller(
            [
                {
                    "candidate_judgment": "unlikely",
                    "magnitude": None,
                    "confidence": {"level": "medium"},
                    "key_reasons": ["no doubling catalyst supplied"],
                    "uncertainties": [],
                    "session_id": "anonymous-session",
                },
                {
                    "prediction_outcome": {"correct": False},
                    "decision_drivers": [],
                    "why_prediction_failed": [
                        "The supplied evidence never connected to a 2x path."
                    ],
                    "misleading_signals": [],
                    "ignored_evidence": [],
                    "missing_information": [],
                    "plan_issues": [],
                },
            ]
        )
        predictor = LLMBlindPredictor(caller)
        step = predictor.predict({"summary": "Only steady-state operations."})
        self.assertFalse(step.value.is_surge)
        blind_payload = json.dumps(caller.calls[0]["payload"])
        self.assertNotIn("magnitude_feedback", blind_payload)
        self.assertNotIn("revealed_ground_truth", blind_payload)
        self.assertNotIn("realized_max_multiple", blind_payload)

        predictor.reflect(
            {"summary": "Only steady-state operations."},
            step.value,
            GroundTruth(12.0),
        )
        posthoc = caller.calls[1]["payload"]
        self.assertIn("revealed_ground_truth", posthoc)
        self.assertEqual(
            posthoc["magnitude_feedback"]["error_kind"], "missed_surge"
        )


class S2SingleValidCandidateTest(unittest.TestCase):
    """Scenario 2: single valid Plan keeps magnitude tasks without Round LLM."""

    def test_no_round_llm_and_next_proposer_consumes_magnitude(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            for stats_path in (root / "signals").rglob("stats.json"):
                stats_path.unlink()
            workspace = EvolutionWorkspace(root / "workspace")
            caller = ScriptedRoleCaller([])
            proposers: list[CountingProposer] = []

            def build_engine() -> PlanEvolutionEngine:
                proposers.append(UniqueIdProposer())
                return PlanEvolutionEngine(
                    archive=workspace.restore_archive(),
                    meta_memory=workspace.restore_meta(),
                    signal_registry=registry,
                    evaluator=SyntheticPlanEvaluator(),
                    proposer=proposers[-1],
                    critic=SimpleCritic(),
                    round_reflector=LLMRoundReflector(caller),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=1,
                )

            build_engine().run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            self.assertEqual(caller.calls, [])
            entry = workspace.restore_meta().entries[-1]
            reflection = entry.plan_reflections[0]
            self.assertIsNotNone(reflection.magnitude_diagnostics)
            self.assertIsNotNone(
                reflection.original_case_reflections[0].magnitude_feedback
            )

            build_engine().run_round(
                round_id=2,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            seen_rounds = proposers[1].calls[0]["meta_rounds"]
            self.assertIn(1, seen_rounds)
            restored = workspace.restore_meta()
            local = [item for item in restored.entries if item.plan_reflections]
            self.assertIsNotNone(local[0].plan_reflections[0].magnitude_diagnostics)


class S3DifferentSnapshotTest(unittest.TestCase):
    """Scenario 3: cross-snapshot parents never get paired metric deltas."""

    def test_changed_pool_disables_binary_and_magnitude_deltas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            critic = SimpleCritic()

            def build_engine() -> PlanEvolutionEngine:
                return PlanEvolutionEngine(
                    archive=workspace.restore_archive(),
                    meta_memory=workspace.restore_meta(),
                    signal_registry=registry,
                    evaluator=SyntheticPlanEvaluator(),
                    proposer=UniqueIdProposer(),
                    critic=critic,
                    round_reflector=SimpleRoundReflector(),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=1,
                )

            build_engine().run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            shifted_pool = list(make_evaluation_pool())
            shifted_pool[0] = make_case("non_surge_alt_00", 1.3)
            build_engine().run_round(
                round_id=2,
                validation_cases=tuple(shifted_pool),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            comparisons = [
                comparison
                for group in critic.parent_comparisons
                for comparison in group
            ]
            self.assertTrue(comparisons)
            for comparison in comparisons:
                if comparison.get("child_plan_id", "").startswith("plan_child_"):
                    continue
            round_two = critic.parent_comparisons[1]
            self.assertTrue(round_two)
            for comparison in round_two:
                self.assertFalse(comparison["same_evaluation_snapshot"])
                self.assertIsNone(comparison["metric_delta"])
                self.assertIsNone(comparison["magnitude_metric_delta"])


class S4ImportedPrefixThreeLocalRoundsTest(unittest.TestCase):
    """Scenario 4: imported negative prefix plus local rounds never collide."""

    def test_magnitude_tasks_survive_import_prefix_and_local_commits(self):
        from stock_opportunity_agent.research.evolution_control import (
            _rebased_history_meta_entries,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            for stats_path in (root / "signals").rglob("stats.json"):
                stats_path.unlink()
            workspace = EvolutionWorkspace(root / "workspace")
            imported = RoundMetaEntry(
                round_id=1,
                evidence_refs=("imported-plan",),
                missing_capabilities=("Imported unresolved Fast need.",),
            )
            proposers: list[CountingProposer] = []
            counter = [0]

            class UniqueProposer(CountingProposer):
                def propose(self, **kwargs):
                    counter[0] += 1
                    call = dict(kwargs)
                    self.calls.append(
                        {
                            "round_id": call["round_id"],
                            "meta_rounds": tuple(
                                entry.round_id for entry in call["meta_info"]
                            ),
                            "meta_infos": tuple(call["meta_info"]),
                        }
                    )
                    base = default_information_plan()
                    return InformationPlan(
                        plan_id=f"plan_child_{counter[0]}",
                        parent_ids=tuple(
                            plan.plan_id for plan in call["parents"]
                        ),
                        basic_info_policy=base.basic_info_policy,
                        initial_research_skill=(
                            f"{base.initial_research_skill} Variant {counter[0]}."
                        ),
                        reflection_skill=base.reflection_skill,
                        analysis_prompt=base.analysis_prompt,
                    )

            def build_engine() -> PlanEvolutionEngine:
                proposers.append(UniqueProposer())
                imports = _rebased_history_meta_entries((imported,))
                local = workspace.restore_meta()
                return PlanEvolutionEngine(
                    archive=workspace.restore_archive(),
                    meta_memory=PlanMetaMemory(
                        entries=(*imports, *local.entries)
                    ),
                    signal_registry=registry,
                    evaluator=SyntheticPlanEvaluator(),
                    proposer=proposers[-1],
                    critic=SimpleCritic(),
                    round_reflector=SimpleRoundReflector(),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=1,
                )

            for round_id in (1, 2, 3):
                build_engine().run_round(
                    round_id=round_id,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(
                proposers[0].calls[0]["meta_rounds"], (-1,)
            )
            self.assertEqual(
                proposers[2].calls[0]["meta_rounds"], (-1, 1, 2)
            )
            self.assertEqual(
                [entry.round_id for entry in workspace.restore_meta().entries],
                [1, 2, 3],
            )
            for entry in workspace.restore_meta().entries:
                self.assertIsNotNone(
                    entry.plan_reflections[0].magnitude_diagnostics
                )


class S5PostCommitCrashTest(unittest.TestCase):
    """Scenario 5: crash after durable round commit recovers idempotently."""

    def test_stats_learning_meta_recover_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            for stats_path in (root / "signals").rglob("stats.json"):
                stats_path.unlink()
            workspace = EvolutionWorkspace(root / "workspace")

            def build_engine() -> PlanEvolutionEngine:
                return PlanEvolutionEngine(
                    archive=workspace.restore_archive(),
                    meta_memory=workspace.restore_meta(),
                    signal_registry=registry,
                    evaluator=SyntheticPlanEvaluator(),
                    proposer=UniqueIdProposer(),
                    critic=SimpleCritic(),
                    round_reflector=SimpleRoundReflector(),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=1,
                )

            crashing = build_engine()
            original = PlanEvolutionEngine._record_signal_statistics

            def crash_once(self_engine, record):
                PlanEvolutionEngine._record_signal_statistics = original
                raise RuntimeError("simulated crash after durable round commit")

            PlanEvolutionEngine._record_signal_statistics = crash_once
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                crashing.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 1)

            build_engine()
            events_after_first_restore = len(
                registry.load_learning_events("revenue_growth_yoy:v1")
            )
            build_engine()
            events_after_second_restore = len(
                registry.load_learning_events("revenue_growth_yoy:v1")
            )
            self.assertEqual(events_after_first_restore, events_after_second_restore)
            all_events = registry.load_learning_events("revenue_growth_yoy:v1")
            event_ids = [event.event_id for event in all_events]
            self.assertEqual(len(event_ids), len(set(event_ids)))

            build_engine().run_round(
                round_id=2,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            self.assertEqual(workspace.last_completed_round, 2)
            restored_meta = workspace.restore_meta()
            self.assertEqual(
                [entry.round_id for entry in restored_meta.entries], [1, 2]
            )
            for entry in restored_meta.entries:
                self.assertIsNotNone(
                    entry.plan_reflections[0].magnitude_diagnostics
                )


class S6SlowStagedValidationCrashTest(unittest.TestCase):
    """Scenario 6: crash while staging Slow validation promotes nothing early."""

    def test_recovery_completes_once_and_keeps_single_magnitude_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            _committed_magnitude_round(workspace, registry)
            mining_model = EmptyMiningModel()
            engine = _slow_engine_fixture(root, registry, workspace, mining_model)
            snapshot = registry.freeze()

            original = EvolutionWorkspace.stage_slow_validation

            def crash_once(self_workspace, **kwargs):
                EvolutionWorkspace.stage_slow_validation = original
                raise RuntimeError("simulated crash staging slow validation")

            EvolutionWorkspace.stage_slow_validation = crash_once
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                engine.run_cycle(cycle_id=1, input_snapshot=snapshot)
            self.assertEqual(registry.version, snapshot.version)
            self.assertEqual(workspace.last_completed_cycle, 0)

            recovered = _slow_engine_fixture(root, registry, workspace, mining_model)
            result = recovered.run_cycle(cycle_id=1, input_snapshot=snapshot)
            self.assertEqual(result.promoted, ())
            workspace.stage_slow_result(
                cycle_id=1, result=result.to_dict()
            )
            current = registry.freeze()
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=current.version,
                observed_signal_registry_hash=current.registry_hash,
            )
            self.assertEqual(workspace.last_completed_cycle, 1)
            slow_input = validate_slow_input(
                json.loads(
                    (
                        workspace.experiments_root
                        / "cycles"
                        / "cycle-0001"
                        / "slow_input.json"
                    ).read_text()
                )
            )
            magnitude_rows = [
                row
                for row in slow_input["feedback_rows"]
                if row["kind"] == "magnitude_feedback"
            ]
            self.assertEqual(len(magnitude_rows), 1)
            self.assertEqual(magnitude_rows[0]["feedback_ref"], "magnitude:plan_mag_r1")
            self.assertFalse(result.magnitude_contribution["assessed"])


class S7PromotionCycleCommitCrashTest(unittest.TestCase):
    """Scenario 7: crash after promotion, before cycle commit, recovers once."""

    def _promoting_fixture(self, root, workspace):
        registry = SignalRegistry(root / "signals")
        registry.install_catalog(SEED_CATALOG)
        new_spec = SignalSpec(
            signal_id="discovery_growth_quality",
            version=1,
            category="financial",
            description=(
                "Measure the latest point-in-time year-over-year revenue growth "
                "with a stricter positive threshold."
            ),
            execution_type=SignalExecutionType.DETERMINISTIC,
            function="financial.revenue_growth_yoy",
            source_types=("financials",),
            parameters={"positive_min": 0.10, "negative_max": 0.0},
        )
        hypothesis = SignalMiningHypothesis(
            hypothesis_id="broad_growth",
            statement="Point-in-time revenue acceleration separates winners.",
            applicability="all_ready_issuers",
            expected_positive_pattern="Positive cases show stronger growth.",
            source_types=("financials",),
            query="revenue",
            falsifiers=("Controls show the same growth.",),
        )
        mining_model = ScriptedMiningModel(
            hypotheses=(hypothesis,),
            rankings={"broad_growth": tuple(f"case-{index:03d}" for index in range(1, 9))},
            decisions=(
                SignalMiningDecision(
                    hypothesis_id="broad_growth",
                    disposition="supported",
                    rationale=("Positive and control cases separate consistently.",),
                    candidate={
                        "spec": new_spec.to_dict(),
                        "skill": None,
                        "tests": [candidate_growth_fixture()],
                    },
                ),
            ),
        )
        discovery_cases = tuple(
            [make_case(f"discovery_positive_{index}", 4.0) for index in range(8)]
            + [make_case(f"discovery_control_{index}", 1.1) for index in range(8)]
        )
        raw_store = RawInfoStore(
            documents=tuple(
                RawInfoDocument.create(
                    document_id=f"effectiveness_financial_{index}",
                    company_id=case.company_id,
                    source_type="financials",
                    published_at=NOW,
                    available_at=NOW,
                    content=sec_company_facts_content(
                        ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                        (
                            "2024-01-01",
                            "2024-12-31",
                            115.0 if case.ground_truth.is_surge else 90.0,
                            "2025-01-10",
                        ),
                    ),
                )
                for index, case in enumerate(discovery_cases)
            )
        )
        engine = SignalEvolutionEngine(
            registry=registry,
            raw_info_store=raw_store,
            discovery_cases=discovery_cases,
            meta_memory=workspace.restore_meta(),
            workspace=workspace,
            mining_model=mining_model,
            update_model=NoChangeUpdateModel(),
            llm_signal_runner=None,
            mining_config=fixture_mining_config(len(discovery_cases) // 2),
        )
        return registry, mining_model, engine

    def test_transition_and_pointer_recover_coherently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = EvolutionWorkspace(root / "workspace")
            registry, mining_model, engine = self._promoting_fixture(root, workspace)
            _committed_magnitude_round(workspace, registry, plan_id="plan_mag_r1")
            snapshot = registry.freeze()

            # Crash point: the registry transition and staged Slow result are
            # durable inside run_cycle, but the control layer has not yet
            # called complete_cycle — exactly the post-promotion,
            # pre-cycle-commit interrupted state.
            promoted_result = engine.run_cycle(cycle_id=1, input_snapshot=snapshot)
            self.assertEqual(
                set(promoted_result.promoted), {"discovery_growth_quality:v1"}
            )
            self.assertEqual(registry.version, snapshot.version + 1)
            self.assertEqual(workspace.last_completed_cycle, 0)
            self.assertTrue(
                (
                    workspace.experiments_root
                    / "cycles"
                    / "cycle-0001"
                    / "slow_loop_validation.json"
                ).is_file()
            )

            # Pre-commit recovery rerun must be idempotent: the already
            # applied transition is not promoted a second time.
            rerun = engine.run_cycle(cycle_id=1)
            self.assertEqual(set(rerun.promoted), set(promoted_result.promoted))
            self.assertEqual(registry.version, snapshot.version + 1)
            self.assertEqual(
                registry.latest_spec("discovery_growth_quality").version, 1
            )

            # Completion mirrors the control layer: stage the Slow result and
            # complete the cycle pointer with the observed registry.
            workspace.stage_slow_result(
                cycle_id=1, result=promoted_result.to_dict()
            )
            current = registry.freeze()
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=current.version,
                observed_signal_registry_hash=current.registry_hash,
            )
            self.assertEqual(workspace.last_completed_cycle, 1)


class S8MalformedBoundedCorrectionTest(unittest.TestCase):
    """Scenario 8: malformed reflection gets bounded correction, blocks rejected."""

    def test_empty_posthoc_corrects_once_with_magnitude_payload(self):
        empty = {
            "prediction_outcome": {"correct": False},
            "decision_drivers": [],
            "why_prediction_failed": [],
            "misleading_signals": [],
            "ignored_evidence": [],
            "missing_information": [],
            "plan_issues": [],
        }
        corrected = json.loads(json.dumps(empty))
        corrected["why_prediction_failed"] = [
            "No source-backed path to the realized class was supplied."
        ]
        caller = ScriptedRoleCaller([empty, corrected])
        predictor = LLMBlindPredictor(caller)

        reflection = predictor.reflect(
            {"summary": "Growth was steady but not accelerating."},
            BlindPrediction(
                is_surge=True,
                candidate_judgment=CandidateJudgment.POSSIBLE,
                magnitude=MagnitudeClass.TWO_TO_THREE,
                confidence=ConfidenceLevel.MEDIUM,
                key_reasons=("backlog",),
                uncertainties=(),
                session_id="anonymous-session",
            ),
            GroundTruth(12.0),
        )

        self.assertEqual(caller.stages[-1], "blind_predictor_posthoc_reflect_correction")
        self.assertIn("magnitude_feedback", caller.calls[0]["payload"])
        self.assertEqual(
            reflection.value.why_prediction_failed,
            tuple(corrected["why_prediction_failed"]),
        )

    def test_tampered_magnitude_block_fails_closed(self):
        trajectory = make_trajectory(
            "case_tamper", 2.5, True, MagnitudeClass.TWO_TO_THREE
        )
        serialized = CaseReflectionEvidence.from_trajectory(
            trajectory, case_index=1
        ).to_dict()
        serialized["magnitude_feedback"]["ordinal_distance"] = 2
        with self.assertRaises(ValidationError):
            CaseReflectionEvidence.from_dict(serialized)


class S9LegacyMissingMagnitudeTest(unittest.TestCase):
    """Scenario 9: absent magnitude is never zero-filled or read as improvement."""

    def test_dashboard_key_ranks_present_metric_first_at_equal_f1(self):
        present = {
            "plan_id": "plan_present",
            "metrics": {
                "binary_f1": 0.8,
                "magnitude_macro_f1": 0.2,
                "confusion": {
                    "true_positive": 12,
                    "false_positive": 4,
                    "false_negative": 2,
                    "true_negative": 6,
                },
            },
        }
        legacy = {
            "plan_id": "plan_legacy",
            "metrics": {
                "binary_f1": 0.8,
                "confusion": {
                    "true_positive": 12,
                    "false_positive": 4,
                    "false_negative": 2,
                    "true_negative": 6,
                },
            },
        }
        self.assertLess(
            _dashboard_selection_key(present), _dashboard_selection_key(legacy)
        )

    def test_zero_denominator_fraction_scores_zero(self):
        metrics = PlanMetrics(
            binary_precision=0.0,
            binary_recall=0.0,
            binary_f1=0.0,
            magnitude_accuracy=0.0,
            magnitude_macro_f1=0.0,
            true_positive=0,
            false_positive=0,
            false_negative=0,
            true_negative=24,
            sample_count=24,
        )
        self.assertEqual(binary_f1_fraction(metrics), 0)
        self.assertEqual(float(binary_f1_fraction(metrics)), 0.0)


class S10FailurePropagationTest(unittest.TestCase):
    """Scenario 10: reflection failure stays a failure, never fake content."""

    def test_rejected_posthoc_fallback_keeps_framework_truth(self):
        class RejectingCaller(ScriptedRoleCaller):
            def complete_json(self, **kwargs):
                raise CandidateExecutionRejected(
                    "blind_predictor_posthoc_reflect",
                    "transport unavailable after bounded retries",
                )

        predictor = LLMBlindPredictor(RejectingCaller([]))
        prediction = BlindPrediction(
            is_surge=True,
            candidate_judgment=CandidateJudgment.POSSIBLE,
            magnitude=MagnitudeClass.TWO_TO_THREE,
            confidence=ConfidenceLevel.MEDIUM,
            key_reasons=("backlog",),
            uncertainties=(),
            session_id="anonymous-session",
        )
        step = predictor.reflect({"summary": "context"}, prediction, GroundTruth(12.0))
        self.assertFalse(step.value.correct)
        self.assertTrue(
            any(
                "posthoc_reflection_validation_failed" in issue
                for issue in step.value.plan_issues
            )
        )


class S11EmptyMiningNoOpCycleTest(unittest.TestCase):
    """Scenario 11: legal no-op Slow cycle commits and keeps learning inputs."""

    def test_no_op_cycle_commits_with_magnitude_row_and_honest_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            _committed_magnitude_round(workspace, registry)
            engine = _slow_engine_fixture(
                root, registry, workspace, EmptyMiningModel()
            )
            result = engine.run_cycle(
                cycle_id=1, input_snapshot=registry.freeze()
            )
            self.assertEqual(result.promoted, ())
            workspace.stage_slow_result(
                cycle_id=1, result=result.to_dict()
            )
            current = registry.freeze()
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=current.version,
                observed_signal_registry_hash=current.registry_hash,
            )
            self.assertEqual(workspace.last_completed_cycle, 1)
            self.assertFalse(result.magnitude_contribution["assessed"])
            restored = workspace.restore_meta()
            self.assertEqual(
                [entry.round_id for entry in restored.entries], [1]
            )
            self.assertIsNotNone(
                restored.entries[0].plan_reflections[0].magnitude_diagnostics
            )


class S12PromotionVisibleToNextFastTest(unittest.TestCase):
    """Scenario 12: promotion reaches the next Fast without rewriting history."""

    def test_next_fast_round_sees_promoted_version_and_old_records_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = EvolutionWorkspace(root / "workspace")
            s7 = S7PromotionCycleCommitCrashTest()
            registry, mining_model, slow_engine = s7._promoting_fixture(
                root, workspace
            )

            def fast_engine() -> PlanEvolutionEngine:
                return PlanEvolutionEngine(
                    archive=workspace.restore_archive(),
                    meta_memory=workspace.restore_meta(),
                    signal_registry=registry,
                    evaluator=SyntheticPlanEvaluator(),
                    proposer=UniqueIdProposer(),
                    critic=SimpleCritic(),
                    round_reflector=SimpleRoundReflector(),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=1,
                )

            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            fast_engine().run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            record_id = workspace.restore_archive().records[0].plan_id
            record_path = workspace.plans_root / record_id / "record.json"
            original_record_bytes = record_path.read_bytes()

            result = slow_engine.run_cycle(cycle_id=1, input_snapshot=snapshot)
            self.assertEqual(set(result.promoted), {"discovery_growth_quality:v1"})
            promoted_version = registry.version
            workspace.stage_slow_result(
                cycle_id=1, result=result.to_dict()
            )
            current = registry.freeze()
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=current.version,
                observed_signal_registry_hash=current.registry_hash,
            )

            evaluator = SyntheticPlanEvaluator()
            round_two_engine = PlanEvolutionEngine(
                archive=workspace.restore_archive(),
                meta_memory=workspace.restore_meta(),
                signal_registry=registry,
                evaluator=evaluator,
                proposer=UniqueIdProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            round_two_engine.run_round(
                round_id=2,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            self.assertGreater(registry.freeze().version, promoted_version - 1)
            self.assertTrue(
                any(
                    "discovery_growth_quality" in ref
                    for refs in evaluator.seen_registry_refs
                    for ref in refs
                )
            )
            self.assertEqual(
                record_path.read_bytes(), original_record_bytes
            )


if __name__ == "__main__":
    unittest.main()
