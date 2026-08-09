from __future__ import annotations

import json
import random
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import (
    RawInfoDocument,
    RawInfoStore,
    content_sha256,
)
from stock_opportunity_agent.llm.agent import (
    AgentRequest,
    AgentTurn,
    AgentUsage,
    DomainTool,
    GenericAgent,
    ToolCall,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import (
    DEFAULT_EVOLUTION_PRIORS,
    AgentStep,
    BlindPrediction,
    ConfidenceLevel,
    DualLoopEvolutionEngine,
    EvolutionCase,
    EvolutionDataset,
    EvolutionWorkspace,
    ExecutionTrajectory,
    GroundTruth,
    HashingPlanEmbedder,
    InformationPlan,
    MagnitudeClass,
    PlanArchive,
    PlanEvolutionEngine,
    PlanMetaMemory,
    PlanMetrics,
    PlanRecord,
    PlanReflection,
    PredictionSelfReflection,
    ResearchDecision,
    ResearchState,
    RoundMetaEntry,
    RuntimeLimits,
    RuntimePlanEvaluator,
    RuntimeStopReason,
    RuntimeUsage,
    SignalCandidateValidator,
    SignalEvolutionEngine,
    SignalRound,
    default_information_plan,
    execute_information_plan,
    score_predictions,
)
from stock_opportunity_agent.signal_library import (
    SignalEvidence,
    SignalExecutionType,
    SignalExecutor,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_CATALOG = PROJECT_ROOT / "configs" / "signals_v1.json"
NOW = datetime(2025, 1, 15, 12, tzinfo=timezone.utc)


class ScriptedAgentModel:
    def __init__(self, turns: list[AgentTurn]) -> None:
        self.turns = list(turns)
        self.requests: list[AgentRequest] = []

    def respond(self, request: AgentRequest) -> AgentTurn:
        self.requests.append(request)
        if not self.turns:
            raise AssertionError("scripted agent ran out of turns")
        return self.turns.pop(0)


class OneBatchController:
    def __init__(self) -> None:
        self.reflected_batch_sizes: list[int] = []

    def initialize(
        self, plan: InformationPlan, basic_info: Mapping[str, Any]
    ) -> AgentStep[ResearchState]:
        self.initial_basic_info = dict(basic_info)
        return AgentStep(
            ResearchState(
                hypotheses=("commercial adoption may be accelerating",),
                next_information_needs=("measure revenue growth",),
            ),
            AgentUsage(llm_calls=1, tokens=20, cost=0.01),
        )

    def reflect(
        self,
        plan: InformationPlan,
        state: ResearchState,
        batch,
    ) -> AgentStep[ResearchState]:
        self.reflected_batch_sizes.append(len(batch.results))
        return AgentStep(
            ResearchState(
                hypotheses=state.hypotheses,
                current_beliefs=("growth is supported",),
                supporting_evidence=(batch.results[0].interpretation,),
                resolved_questions=("measure revenue growth",),
                decision=ResearchDecision.FINALIZE,
            ),
            AgentUsage(llm_calls=1, tokens=20, cost=0.01),
        )


class OneSignalSelector:
    def select(self, information_needs, signal_registry):
        self.needs = tuple(information_needs)
        return AgentStep(
            ("revenue_growth_yoy:v1",),
            AgentUsage(llm_calls=1, tokens=10, cost=0.005),
        )


class FixedPredictor:
    def __init__(self, *, is_surge: bool = True) -> None:
        self.is_surge = is_surge
        self.reflection_truths: list[GroundTruth] = []

    def predict(self, final_context):
        assert "ground_truth" not in final_context
        return AgentStep(
            BlindPrediction(
                is_surge=self.is_surge,
                magnitude=(MagnitudeClass.THREE_TO_TEN if self.is_surge else None),
                confidence=ConfidenceLevel.MEDIUM,
                key_reasons=("source-backed growth",),
                uncertainties=("customer concentration",),
                session_id="predictor-session-1",
            ),
            AgentUsage(llm_calls=1, tokens=30, cost=0.02),
        )

    def reflect(self, original_context, original_prediction, ground_truth):
        self.reflection_truths.append(ground_truth)
        correct = original_prediction.is_surge == ground_truth.is_surge
        return AgentStep(
            PredictionSelfReflection(
                correct=correct,
                why_prediction_failed=(() if correct else ("wrong binary class",)),
            ),
            AgentUsage(llm_calls=1, tokens=15, cost=0.01),
        )


class RawInfoStoreTests(TestCase):
    def test_append_only_store_filters_by_available_at_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RawInfoStore(directory)
            visible = RawInfoDocument.create(
                document_id="doc_visible",
                company_id="issuer_1",
                source_type="financials",
                published_at=NOW - timedelta(days=2),
                available_at=NOW - timedelta(days=1),
                content="Revenue grew 25 percent year over year.",
                metadata={"revenue_growth_yoy": 0.25},
            )
            future = RawInfoDocument.create(
                document_id="doc_future",
                company_id="issuer_1",
                source_type="financials",
                published_at=NOW + timedelta(days=1),
                available_at=NOW + timedelta(days=1),
                content="Future quarter revenue grew 80 percent.",
                metadata={"revenue_growth_yoy": 0.8},
            )
            self.assertTrue(store.append(visible))
            self.assertFalse(store.append(visible))
            store.append(future)
            self.assertEqual(
                [item.document_id for item in store.search("issuer_1", as_of=NOW)],
                ["doc_visible"],
            )
            with self.assertRaisesRegex(ValidationError, "not available"):
                store.load("doc_future", as_of=NOW)
            reloaded = RawInfoStore(directory)
            self.assertEqual(len(reloaded.documents), 2)
            self.assertEqual(reloaded.load("doc_visible"), visible)

    def test_store_rejects_conflicting_id_hash_and_path_traversal(self) -> None:
        valid = RawInfoDocument.create(
            document_id="doc_1",
            company_id="issuer_1",
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="A sourced event occurred.",
        )
        store = RawInfoStore(documents=(valid,))
        conflicting = RawInfoDocument.create(
            document_id="doc_1",
            company_id="issuer_1",
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="Different content.",
        )
        with self.assertRaisesRegex(ValidationError, "different content"):
            store.append(conflicting)
        with self.assertRaisesRegex(ValidationError, "content_hash"):
            RawInfoDocument(
                document_id="doc_2",
                company_id="issuer_1",
                source_type="news",
                published_at=NOW,
                available_at=NOW,
                content="content",
                content_hash=content_sha256("other"),
            )
        with self.assertRaisesRegex(ValidationError, "safe identifier"):
            RawInfoDocument.create(
                document_id="../escape",
                company_id="issuer_1",
                source_type="news",
                published_at=NOW,
                available_at=NOW,
                content="content",
            )

    def test_hidden_outcome_metadata_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "forbidden outcome"):
            RawInfoDocument.create(
                document_id="leaking_doc",
                company_id="issuer_1",
                source_type="financials",
                published_at=NOW,
                available_at=NOW,
                content="Contemporaneous financial statement.",
                metadata={"analysis": {"realized_max_multiple": 4.0}},
            )


class GenericAgentTests(TestCase):
    def test_agent_uses_only_granted_domain_tools_and_validates_output(self) -> None:
        model = ScriptedAgentModel(
            [
                AgentTurn(tool_call=ToolCall("lookup", {"key": "x"})),
                AgentTurn(final_output={"answer": 4}),
            ]
        )
        result = GenericAgent(model).run(
            prompt="Use the domain tool and return an integer answer.",
            tools=(DomainTool("lookup", "Look up one fixture value.", lambda key: 4),),
            workspace={"scope": "fixture"},
            output_schema=lambda value: int(value["answer"]),
            max_steps=2,
        )
        self.assertEqual(result.value, 4)
        self.assertEqual(result.observations[0].result, 4)
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertNotIn("cat", {card["name"] for card in model.requests[0].tool_cards})

    def test_agent_rejects_ungranted_or_raw_tools_and_step_exhaustion(self) -> None:
        with self.assertRaisesRegex(ValidationError, "not allowed"):
            DomainTool("rm", "Remove anything.", lambda: None)
        model = ScriptedAgentModel(
            [AgentTurn(tool_call=ToolCall("not_granted", {}))]
        )
        with self.assertRaisesRegex(ValidationError, "ungranted"):
            GenericAgent(model).run(
                prompt="test",
                tools=(),
                workspace={},
                output_schema=lambda value: value,
                max_steps=1,
            )
        looping = ScriptedAgentModel(
            [AgentTurn(tool_call=ToolCall("lookup", {}))]
        )
        with self.assertRaisesRegex(ValidationError, "exhausted"):
            GenericAgent(looping).run(
                prompt="test",
                tools=(DomainTool("lookup", "fixture lookup", lambda: 1),),
                workspace={},
                output_schema=lambda value: value,
                max_steps=1,
            )


class SignalLibraryTests(TestCase):
    def _registry(self, directory: str) -> SignalRegistry:
        registry = SignalRegistry(Path(directory) / "signals")
        self.assertEqual(registry.install_catalog(SEED_CATALOG), 12)
        return registry

    def test_seed_catalog_progressive_disclosure_and_frozen_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            self.assertEqual(len(registry.list_signal_cards()), 12)
            self.assertIn("financial", registry.list_categories())
            cards = registry.search_signal_cards("customer")
            self.assertTrue(cards)
            spec = registry.load_spec("pilot_to_volume:v1")
            self.assertEqual(spec.execution_type, SignalExecutionType.LLM)
            self.assertIn("scaled deployment", registry.load_skill(spec.ref))
            snapshot = registry.freeze()
            v2 = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Measure audited year-over-year revenue growth.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            registry.register_stable(v2)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 2)
            self.assertEqual(snapshot.load_spec("revenue_growth_yoy:v1").version, 1)
            with self.assertRaisesRegex(ValidationError, "unknown frozen"):
                snapshot.load_spec("revenue_growth_yoy:v2")

    def test_executor_uses_point_in_time_raw_info_and_tracks_observed_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="financial_1",
                        company_id="issuer_1",
                        source_type="financials",
                        published_at=NOW - timedelta(days=2),
                        available_at=NOW - timedelta(days=1),
                        content="Revenue grew 25 percent year over year.",
                        metadata={"revenue_growth_yoy": 0.25},
                    ),
                    RawInfoDocument.create(
                        document_id="financial_future",
                        company_id="issuer_1",
                        source_type="financials",
                        published_at=NOW + timedelta(days=1),
                        available_at=NOW + timedelta(days=1),
                        content="Revenue later fell.",
                        metadata={"revenue_growth_yoy": -0.5},
                    ),
                )
            )
            executor = SignalExecutor(registry.freeze(), store)
            batch = executor.execute_batch(
                ("revenue_growth_yoy:v1",),
                company_id="issuer_1",
                as_of=NOW,
            )
            result = batch.results[0]
            self.assertEqual(result.value, SignalValue.POSITIVE)
            self.assertEqual(result.supporting_evidence[0].document_id, "financial_1")
            registry.record_retrieval(result.ref)
            registry.record_result(result, is_surge=True)
            stats = registry.load_stats("revenue_growth_yoy")
            self.assertEqual(stats.retrieved, 1)
            self.assertEqual(stats.states["positive"], {"total": 1, "surge": 1})

    def test_result_evidence_must_be_from_actual_input_with_literal_span(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            document = RawInfoDocument.create(
                document_id="announcement_1",
                company_id="issuer_1",
                source_type="company_announcement",
                published_at=NOW,
                available_at=NOW,
                content="The customer entered volume deployment.",
            )

            class BadRunner:
                def execute(self, spec, documents, skill, as_of):
                    return (
                        SignalResult(
                            signal_id=spec.signal_id,
                            version=spec.version,
                            value=SignalValue.POSITIVE,
                            confidence=0.9,
                            interpretation="Volume deployment started.",
                            supporting_evidence=(
                                SignalEvidence(
                                    document_id="invented_doc",
                                    exact_span="volume deployment",
                                    timestamp=as_of,
                                ),
                            ),
                        ),
                        AgentUsage(llm_calls=1),
                    )

            executor = SignalExecutor(
                registry.freeze(),
                RawInfoStore(documents=(document,)),
                llm_runner=BadRunner(),
            )
            with self.assertRaisesRegex(ValidationError, "outside its inputs"):
                executor.execute_batch(
                    ("pilot_to_volume:v1",),
                    company_id="issuer_1",
                    as_of=NOW,
                )


class InformationPlanRuntimeTests(TestCase):
    def test_basic_info_policy_cannot_request_outcome_fields(self) -> None:
        base = default_information_plan()
        with self.assertRaisesRegex(ValidationError, "outcome fields"):
            InformationPlan(
                plan_id="leaking_plan",
                parent_ids=(),
                basic_info_policy=type(base.basic_info_policy)(
                    fields=("company_name", "hidden_ground_truth")
                ),
                initial_research_skill=base.initial_research_skill,
                reflection_skill=base.reflection_skill,
                analysis_prompt=base.analysis_prompt,
            )

    def _registry_and_store(self, directory: str):
        registry = SignalRegistry(Path(directory) / "signals")
        registry.install_catalog(SEED_CATALOG)
        document = RawInfoDocument.create(
            document_id="financial_1",
            company_id="winner_1",
            source_type="financials",
            published_at=NOW - timedelta(days=2),
            available_at=NOW - timedelta(days=1),
            content="Legacy Winner revenue grew 30 percent year over year.",
            metadata={"revenue_growth_yoy": 0.30},
        )
        return registry, RawInfoStore(documents=(document,))

    def test_runtime_reflects_over_batch_and_persists_before_label_reveal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry, store = self._registry_and_store(directory)
            controller = OneBatchController()
            selector = OneSignalSelector()
            predictor = FixedPredictor()
            persisted: list[str] = []

            def sink(company_id, prediction_time, final_context, prediction):
                serialized = json.dumps(final_context)
                self.assertNotIn("ground_truth", serialized)
                self.assertNotIn("Masked winner", serialized)
                self.assertNotIn("Legacy Winner", serialized)
                self.assertNotIn('"WIN"', serialized)
                self.assertNotIn("company_name", final_context["basic_info"])
                self.assertNotIn("ticker", final_context["basic_info"])
                persisted.append(company_id)
                return "predictions/winner_1.json"

            def truth_provider(company_id):
                self.assertEqual(persisted, [company_id])
                return GroundTruth(4.0)

            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={
                    "company_name": "Masked winner",
                    "ticker": "WIN",
                    "market_cap": 6_000_000_000,
                    "industry": "industrial",
                    "business_description": "equipment",
                    "revenue_segments": ["systems"],
                    "development_stage": "commercial",
                    "identity_aliases": ("Legacy Winner",),
                    "extra_raw_fact": "must not enter Basic Info",
                },
                prediction_time=NOW,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), store),
                controller=controller,
                signal_agent=selector,
                predictor=predictor,
                prediction_sink=sink,
                ground_truth_provider=truth_provider,
                limits=RuntimeLimits(max_llm_calls=10),
            )
            self.assertEqual(controller.reflected_batch_sizes, [1])
            self.assertNotIn("extra_raw_fact", trajectory.basic_info)
            self.assertEqual(trajectory.stop_reason, RuntimeStopReason.FINALIZED)
            self.assertEqual(trajectory.ground_truth.magnitude, MagnitudeClass.THREE_TO_TEN)
            self.assertEqual(trajectory.usage.signal_rounds, 1)
            self.assertEqual(trajectory.usage.signal_calls, 1)
            self.assertEqual(predictor.reflection_truths, [GroundTruth(4.0)])

    def test_runtime_stops_at_fixed_round_guard(self) -> None:
        class LoopingController(OneBatchController):
            def reflect(self, plan, state, batch):
                return AgentStep(
                    ResearchState(next_information_needs=("repeat",)),
                    AgentUsage(llm_calls=1),
                )

        with tempfile.TemporaryDirectory() as directory:
            registry, store = self._registry_and_store(directory)
            persisted: list[str] = []
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), store),
                controller=LoopingController(),
                signal_agent=OneSignalSelector(),
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: persisted.append("done") or "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(
                    max_signal_rounds=1,
                    max_signal_calls=5,
                    max_llm_calls=10,
                ),
            )
            self.assertEqual(trajectory.stop_reason, RuntimeStopReason.MAX_SIGNAL_ROUNDS)
            self.assertEqual(len(trajectory.signal_rounds), 1)
            self.assertEqual(persisted, ["done"])

    def test_repeated_issuer_cases_keep_distinct_truths_and_prediction_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="shared_financials",
                        company_id="shared_issuer",
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content="Revenue grew 25 percent.",
                        metadata={"revenue_growth_yoy": 0.25},
                    ),
                )
            )
            predictor = FixedPredictor()
            evaluator = RuntimePlanEvaluator(
                raw_info_store=store,
                controller=OneBatchController(),
                signal_agent=OneSignalSelector(),
                predictor=predictor,
                prediction_root=root / "predictions",
            )
            cases = (
                EvolutionCase(
                    company_id="shared_issuer",
                    prediction_time=NOW,
                    basic_info={"company_name": "Shared One"},
                    ground_truth=GroundTruth(1.2),
                ),
                EvolutionCase(
                    company_id="shared_issuer",
                    prediction_time=NOW + timedelta(days=1),
                    basic_info={"company_name": "Shared Two"},
                    ground_truth=GroundTruth(4.0),
                ),
            )
            trajectories = evaluator.evaluate(
                default_information_plan(), cases, registry.freeze()
            )
            self.assertEqual(
                [row.ground_truth.realized_max_multiple for row in trajectories],
                [1.2, 4.0],
            )
            self.assertEqual(len({row.case_id for row in trajectories}), 2)
            self.assertEqual(len({row.prediction_ref for row in trajectories}), 2)

            resumed_events = []
            resumed_predictor = FixedPredictor()
            resumed = RuntimePlanEvaluator(
                raw_info_store=store,
                controller=OneBatchController(),
                signal_agent=OneSignalSelector(),
                predictor=resumed_predictor,
                prediction_root=root / "predictions",
                on_progress=resumed_events.append,
            ).evaluate(default_information_plan(), cases, registry.freeze())
            self.assertEqual(resumed, trajectories)
            self.assertEqual(resumed_predictor.reflection_truths, [])
            self.assertEqual(
                [event["event_type"] for event in resumed_events],
                ["case_trajectory_reused", "case_trajectory_reused"],
            )

            changed_case = EvolutionCase(
                company_id="shared_issuer",
                prediction_time=NOW,
                basic_info={"company_name": "Shared One"},
                ground_truth=GroundTruth(2.2),
            )
            with self.assertRaisesRegex(ValidationError, "conflicting staged"):
                RuntimePlanEvaluator(
                    raw_info_store=store,
                    controller=OneBatchController(),
                    signal_agent=OneSignalSelector(),
                    predictor=FixedPredictor(),
                    prediction_root=root / "predictions",
                ).evaluate(
                    default_information_plan(),
                    (changed_case,),
                    registry.freeze(),
                )


class PredictionMetricTests(TestCase):
    def test_ground_truth_thresholds_and_two_stage_metrics(self) -> None:
        self.assertFalse(GroundTruth(1.999).is_surge)
        self.assertEqual(GroundTruth(2.0).magnitude, MagnitudeClass.TWO_TO_THREE)
        self.assertEqual(GroundTruth(3.0).magnitude, MagnitudeClass.THREE_TO_TEN)
        self.assertEqual(GroundTruth(10.0).magnitude, MagnitudeClass.TEN_PLUS)
        trajectories = (
            make_trajectory("case_1", 2.5, True, MagnitudeClass.TWO_TO_THREE),
            make_trajectory("case_2", 5.0, False, None),
            make_trajectory("case_3", 1.5, True, MagnitudeClass.TWO_TO_THREE),
            make_trajectory("case_4", 1.2, False, None),
            make_trajectory("case_5", 12.0, True, MagnitudeClass.TEN_PLUS),
        )
        metrics = score_predictions(trajectories)
        self.assertEqual(
            (
                metrics.true_positive,
                metrics.false_positive,
                metrics.true_negative,
                metrics.false_negative,
            ),
            (2, 1, 1, 1),
        )
        self.assertAlmostEqual(metrics.binary_precision, 2 / 3)
        self.assertAlmostEqual(metrics.binary_recall, 2 / 3)
        self.assertAlmostEqual(metrics.binary_f1, 2 / 3)
        self.assertAlmostEqual(metrics.magnitude_accuracy, 2 / 3)
        self.assertGreater(metrics.magnitude_macro_f1, 0)

    def test_prediction_schema_requires_stage_two_only_for_positive(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires magnitude"):
            BlindPrediction(
                is_surge=True,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("reason",),
                uncertainties=(),
                session_id="s",
            )
        with self.assertRaisesRegex(ValidationError, "cannot include magnitude"):
            BlindPrediction(
                is_surge=False,
                magnitude=MagnitudeClass.TWO_TO_THREE,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("reason",),
                uncertainties=(),
                session_id="s",
            )


class PlanArchiveAndWorkspaceTests(TestCase):
    def test_quality_diverse_topk_then_random_exploration(self) -> None:
        archive = PlanArchive(
            (
                make_record("plan_a", 0.90, (1.0, 0.0)),
                make_record("plan_b", 0.80, (0.99, 0.01)),
                make_record("plan_c", 0.70, (0.0, 1.0)),
                make_record("plan_d", 0.60, (-1.0, 0.0)),
            )
        )
        selection = archive.select_parents(
            top_k=2,
            random_k=1,
            similarity_threshold=0.95,
            rng=random.Random(7),
        )
        self.assertEqual([record.plan_id for record in selection.top], ["plan_a", "plan_c"])
        self.assertEqual(len(selection.random), 1)
        self.assertNotIn(selection.random[0].plan_id, {"plan_a", "plan_c"})

    def test_workspace_restores_only_records_reachable_from_completed_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_committed", 0.8, (1.0, 0.0), round_id=1)
            meta = RoundMetaEntry(
                round_id=1,
                successful_patterns=("evidence weighting",),
                evidence_refs=("plan_committed",),
            )
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=meta,
                signal_registry_hash="registry-hash",
            )
            staged = make_record("plan_staged", 0.9, (0.0, 1.0), round_id=2)
            staged_path = Path(directory) / "plans" / "plan_staged" / "record.json"
            staged_path.parent.mkdir(parents=True)
            staged_path.write_text(json.dumps(staged.to_dict()), encoding="utf-8")
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(
                [record.plan_id for record in workspace.restore_archive().records],
                ["plan_committed"],
            )
            self.assertEqual(
                [entry.round_id for entry in workspace.restore_meta().entries],
                [1],
            )

    def test_round_commit_reuses_only_exact_crash_staged_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_recovered", 0.8, (1.0, 0.0), round_id=1)
            meta = RoundMetaEntry(round_id=1, evidence_refs=("plan_recovered",))
            staged_path = workspace.plans_root / "plan_recovered" / "record.json"
            staged_path.parent.mkdir(parents=True)
            staged_path.write_text(json.dumps(record.to_dict()), encoding="utf-8")
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=meta,
                signal_registry_hash="registry-hash",
            )
            self.assertEqual(workspace.last_completed_round, 1)

        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_conflict", 0.8, (1.0, 0.0), round_id=1)
            meta = RoundMetaEntry(round_id=1, evidence_refs=("plan_conflict",))
            staged_path = workspace.plans_root / "plan_conflict" / "record.json"
            staged_path.parent.mkdir(parents=True)
            staged_path.write_text('{"wrong": true}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "conflicting staged"):
                workspace.commit_round(
                    round_id=1,
                    records=(record,),
                    meta_entry=meta,
                    signal_registry_hash="registry-hash",
                )
            self.assertEqual(workspace.last_completed_round, 0)

    def test_meta_memory_is_fifo_and_requires_monotonic_grounded_entries(self) -> None:
        memory = PlanMetaMemory(maxlen=2)
        for round_id in (1, 2, 3):
            memory.append(
                RoundMetaEntry(
                    round_id=round_id,
                    evidence_refs=(f"plan_{round_id}",),
                )
            )
        self.assertEqual([entry.round_id for entry in memory.entries], [2, 3])
        with self.assertRaisesRegex(ValidationError, "monotonically"):
            memory.append(RoundMetaEntry(round_id=3, evidence_refs=("plan_3",)))

    def test_cycle_state_and_debug_events_resume_from_committed_round_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            started = workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=2,
            )
            self.assertFalse(started["resumed"])
            self.assertEqual(started["completed_plan_rounds"], 0)
            first_event = workspace.append_event(
                "cycle_started",
                {"cycle_id": 1, "sequence": 99, "event_type": "spoofed"},
            )
            self.assertEqual(first_event["sequence"], 1)
            self.assertEqual(first_event["event_type"], "cycle_started")
            with workspace.trajectory_events_path.open("ab") as handle:
                handle.write(b'{"truncated":')
            recovered_event = EvolutionWorkspace(directory).append_event(
                "recovered_after_truncated_log",
            )
            self.assertEqual(recovered_event["sequence"], 2)

            for round_id in (1, 2):
                plan_id = f"plan_cycle_{round_id}"
                workspace.commit_round(
                    round_id=round_id,
                    records=(
                        make_record(
                            plan_id,
                            0.5 + round_id / 10,
                            (1.0, float(round_id)),
                            round_id=round_id,
                        ),
                    ),
                    meta_entry=RoundMetaEntry(
                        round_id=round_id,
                        evidence_refs=(plan_id,),
                    ),
                    signal_registry_hash="registry-hash",
                    run_contract_hash="contract-hash",
                )
                resumed = EvolutionWorkspace(directory).start_or_resume_cycle(
                    run_contract_hash="contract-hash",
                    target_plan_rounds=2,
                )
                self.assertEqual(resumed["completed_plan_rounds"], round_id)

            workspace = EvolutionWorkspace(directory)
            self.assertEqual(
                [event["event_type"] for event in workspace.load_events()],
                ["cycle_started", "recovered_after_truncated_log"],
            )
            staged = workspace.stage_slow_result(
                cycle_id=1,
                result={"registry_version": 1},
            )
            self.assertTrue(staged.is_file())
            self.assertEqual(
                workspace.staged_slow_result(1),
                {"registry_version": 1},
            )
            workspace.complete_cycle(cycle_id=1)
            self.assertEqual(workspace.last_completed_cycle, 1)
            self.assertIsNone(
                json.loads(workspace.cycle_state_path.read_text())["active_cycle"]
            )


class CountingProposer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def propose(
        self,
        *,
        round_id,
        candidate_index,
        candidate_count,
        forbidden_plan_ids,
        parents,
        meta_info,
        prior,
    ):
        self.calls.append(
            {
                "round_id": round_id,
                "candidate_index": candidate_index,
                "candidate_count": candidate_count,
                "forbidden_plan_ids": forbidden_plan_ids,
                "parents": tuple(plan.plan_id for plan in parents),
                "meta_rounds": tuple(entry.round_id for entry in meta_info),
                "prior": prior,
            }
        )
        index = len(self.calls)
        base = default_information_plan()
        return InformationPlan(
            plan_id=f"plan_child_{index}",
            parent_ids=tuple(plan.plan_id for plan in parents),
            basic_info_policy=base.basic_info_policy,
            initial_research_skill=f"{base.initial_research_skill} Variant {index}.",
            reflection_skill=base.reflection_skill,
            analysis_prompt=base.analysis_prompt,
        )


class SyntheticPlanEvaluator:
    def __init__(self, *, include_signal: bool = True) -> None:
        self.include_signal = include_signal
        self.seen_company_ids: list[str] = []

    def evaluate(self, plan, cases, signal_registry):
        rows = []
        for case in cases:
            self.seen_company_ids.append(case.company_id)
            predicted = case.ground_truth.is_surge
            rows.append(
                make_trajectory(
                    case.company_id,
                    case.ground_truth.realized_max_multiple,
                    predicted,
                    case.ground_truth.magnitude if predicted else None,
                    signal_result=(
                        SignalResult(
                            signal_id="revenue_growth_yoy",
                            version=1,
                            value=(
                                SignalValue.POSITIVE
                                if case.ground_truth.is_surge
                                else SignalValue.NEGATIVE
                            ),
                            confidence=1.0,
                            interpretation="synthetic observed state",
                        )
                        if self.include_signal
                        else None
                    ),
                )
            )
        return tuple(rows)


class SimpleCritic:
    def critique(self, *, plan, trajectories, metrics):
        return PlanReflection(
            successful_patterns=("correct binary separation",),
            next_explorations=("test contradiction-first reflection",),
        )


class SimpleRoundReflector:
    def __init__(self) -> None:
        self.calls: list[tuple[int, tuple[str, ...], str]] = []

    def reflect(self, *, round_id, records, prior):
        self.calls.append((round_id, tuple(record.plan_id for record in records), prior))
        return RoundMetaEntry(
            round_id=round_id,
            successful_patterns=("correct binary separation",),
            useful_signals=("revenue_growth_yoy",),
            search_implications=("try contradiction-first",),
            evidence_refs=tuple(record.plan_id for record in records),
        )


class PlanEvolutionEngineTests(TestCase):
    def test_fast_loop_calls_proposer_independently_and_commits_s_e_j_r_u_t(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            proposer = CountingProposer()
            reflector = SimpleRoundReflector()
            evaluator = SyntheticPlanEvaluator()
            archive = PlanArchive()
            meta = PlanMetaMemory()
            progress_events = []
            engine = PlanEvolutionEngine(
                archive=archive,
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=reflector,
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=2,
                top_k=2,
                random_k=1,
                rng=random.Random(3),
                on_progress=progress_events.append,
            )
            cases = (
                make_case("validation_positive", 4.0),
                make_case("validation_control", 1.2),
            )
            result = engine.run_round(
                round_id=1,
                validation_cases=cases,
                signal_snapshot=registry.freeze(),
            )
            self.assertEqual(len(proposer.calls), 2)
            self.assertEqual(proposer.calls[0]["parents"], ("plan_manual_v1",))
            self.assertEqual(proposer.calls[0]["prior"], DEFAULT_EVOLUTION_PRIORS.propose_plan)
            self.assertEqual(proposer.calls[0]["candidate_index"], 1)
            self.assertEqual(proposer.calls[0]["candidate_count"], 2)
            self.assertEqual(proposer.calls[0]["forbidden_plan_ids"], ())
            self.assertEqual(proposer.calls[1]["candidate_index"], 2)
            self.assertEqual(
                proposer.calls[1]["forbidden_plan_ids"], ("plan_child_1",)
            )
            self.assertEqual(len(result.records), 2)
            for record in result.records:
                self.assertTrue(record.embedding)
                self.assertEqual(record.metrics.binary_f1, 1.0)
                self.assertTrue(record.reflection.successful_patterns)
                self.assertIn("revenue_growth_yoy:v1", record.signal_usage)
                self.assertEqual(len(record.trajectories), 2)
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(len(workspace.restore_archive().records), 2)
            self.assertEqual(meta.entries[0].evidence_refs, ("plan_child_1", "plan_child_2"))
            event_types = [event["event_type"] for event in progress_events]
            self.assertIn("candidate_proposed", event_types)
            self.assertIn("candidate_scored", event_types)
            self.assertEqual(event_types[-1], "round_committed")
            committed_event = progress_events[-1]
            self.assertEqual(committed_event["round_id"], 1)
            self.assertEqual(len(committed_event["top_k"]), 1)
            proposed = next(
                event
                for event in progress_events
                if event["event_type"] == "candidate_proposed"
            )
            self.assertIn("basic_info_fields", proposed["plan_summary"])
            stats = registry.load_stats("revenue_growth_yoy")
            self.assertEqual(stats.retrieved, 4)
            self.assertEqual(stats.executed, 4)
            PlanEvolutionEngine(
                archive=workspace.restore_archive(),
                meta_memory=workspace.restore_meta(),
                signal_registry=registry,
                evaluator=evaluator,
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            reconciled = registry.load_stats("revenue_growth_yoy")
            self.assertEqual(reconciled.retrieved, 4)
            self.assertEqual(reconciled.executed, 4)

    def test_round_meta_cannot_cite_old_or_unrelated_experiment(self) -> None:
        class BadReflector(SimpleRoundReflector):
            def reflect(self, *, round_id, records, prior):
                return RoundMetaEntry(round_id=round_id, evidence_refs=("old_plan",))

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(include_signal=False),
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=BadReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            with self.assertRaisesRegex(ValidationError, "outside new experiments"):
                engine.run_round(
                    round_id=1,
                    validation_cases=(make_case("validation_1", 1.2),),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 0)


class SignalEvolutionTests(TestCase):
    def test_candidate_validation_rejects_leakage_duplicate_and_bad_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            validator = SignalCandidateValidator(registry, llm_runner=None)
            leaking = SignalSpec(
                signal_id="future_outcome_hint",
                version=1,
                category="risks",
                description="Use future price to infer the outcome label.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            finding = validator.validate(leaking, skill=None, tests=())
            self.assertFalse(finding.accepted)
            self.assertTrue(any("leakage" in reason for reason in finding.reasons))
            duplicate = SignalSpec(
                signal_id="duplicate_growth",
                version=1,
                category="financial",
                description=registry.latest_spec("revenue_growth_yoy").description,
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertFalse(
                validator.validate(duplicate, skill=None, tests=()).accepted
            )
            bad_update = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=3,
                category="financial",
                description="Updated growth measure.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertFalse(
                validator.validate(bad_update, skill=None, tests=()).accepted
            )

    def test_slow_loop_validates_then_requires_exact_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            new_spec = SignalSpec(
                signal_id="discovery_growth_quality",
                version=1,
                category="financial",
                description="Measure whether growth is broad-based across disclosed segments.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            updated_spec = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Measure point-in-time revenue growth with explicit comparable-period checks.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            mining_model = ScriptedAgentModel(
                [
                    AgentTurn(
                        tool_call=ToolCall(
                            "create_candidate_signal",
                            {
                                "spec": new_spec.to_dict(),
                                "tests": [candidate_growth_fixture()],
                            },
                        )
                    ),
                    AgentTurn(final_output={"candidate_refs": []}),
                ]
            )
            update_model = ScriptedAgentModel(
                [
                    AgentTurn(
                        tool_call=ToolCall(
                            "clone_signal_version",
                            {
                                "signal_ref": "revenue_growth_yoy:v1",
                                "spec": updated_spec.to_dict(),
                                "tests": [candidate_growth_fixture()],
                            },
                        )
                    ),
                    AgentTurn(final_output={"candidate_refs": []}),
                ]
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_positive", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_agent=GenericAgent(mining_model),
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
            )
            result = engine.run_cycle()
            self.assertEqual(
                set(result.validated_pending_approval),
                {"discovery_growth_quality:v1", "revenue_growth_yoy:v2"},
            )
            self.assertEqual(result.promoted, ())
            self.assertEqual(result.registry_version, 1)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 1)
            with self.assertRaisesRegex(ValidationError, "approval"):
                registry.promote_candidate("revenue_growth_yoy:v2")
            promoted = engine.promote_approved(
                result,
                approvals=result.validated_pending_approval,
                approved_by="human-reviewer",
            )
            self.assertEqual(
                set(promoted.promoted),
                {"discovery_growth_quality:v1", "revenue_growth_yoy:v2"},
            )
            self.assertEqual(promoted.registry_version, 2)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 2)
            self.assertEqual(registry.latest_spec("discovery_growth_quality").version, 1)
            self.assertTrue(
                (root / "signals_candidates" / "financial" / "revenue_growth_yoy" / "v2").exists()
            )

    def test_slow_loop_agents_cannot_access_locked_test(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            mining_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            update_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            raw_store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="discovery_doc",
                        company_id="discovery_only",
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Discovery evidence.",
                    ),
                    RawInfoDocument.create(
                        document_id="locked_doc",
                        company_id="locked_company",
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Locked evidence.",
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(make_case("discovery_only", 3.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_agent=GenericAgent(mining_model),
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
            )
            engine.run_cycle()
            for model in (mining_model, update_model):
                serialized = json.dumps(model.requests[0].workspace)
                self.assertNotIn("locked_company", serialized)
                self.assertFalse(model.requests[0].workspace["locked_test_available"])
            with self.assertRaisesRegex(ValidationError, "after the Discovery"):
                engine._search_raw_info_tool(
                    make_case("discovery_only", 3.0).case_id,
                    (NOW + timedelta(days=1)).isoformat(),
                )
            with self.assertRaisesRegex(ValidationError, "Discovery case"):
                engine._load_discovery_raw_document(
                    make_case("discovery_only", 3.0).case_id,
                    "locked_doc",
                )


class DualLoopTests(TestCase):
    def test_offline_dual_loop_freezes_signals_then_runs_one_slow_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            meta = PlanMetaMemory()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            mining_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            update_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_agent=GenericAgent(mining_model),
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                evolution_validation=(make_case("validation_case", 1.5),),
                locked_test=(make_case("locked_company", 12.0),),
            )
            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle()
            self.assertEqual(len(result.plan_rounds), 1)
            self.assertEqual(result.signal_evolution.promoted, ())
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(evaluator.seen_company_ids, ["validation_case"])
            self.assertNotIn("locked_company", json.dumps(mining_model.requests[0].workspace))

    def test_dual_loop_resume_runs_only_remaining_fast_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            committed = make_record(
                "plan_committed",
                0.75,
                HashingPlanEmbedder().embed(default_information_plan()),
                round_id=1,
            )
            workspace.commit_round(
                round_id=1,
                records=(committed,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(committed.plan_id,),
                ),
                signal_registry_hash=registry.freeze().registry_hash,
            )
            meta = workspace.restore_meta()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=workspace.restore_archive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            mining_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            update_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_agent=GenericAgent(mining_model),
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                evolution_validation=(make_case("validation_case", 1.5),),
                locked_test=(make_case("locked_company", 12.0),),
            )

            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=2,
            ).run_cycle(completed_plan_rounds=1)

            self.assertEqual([item.round_id for item in result.plan_rounds], [2])
            self.assertEqual(workspace.last_completed_round, 2)
            self.assertEqual(len(proposer.calls), 1)
            self.assertEqual(evaluator.seen_company_ids, ["validation_case"])


def make_case(company_id: str, multiple: float) -> EvolutionCase:
    return EvolutionCase(
        company_id=company_id,
        prediction_time=NOW,
        basic_info={
            "company_name": company_id,
            "ticker": company_id.upper(),
            "industry": "fixture",
        },
        ground_truth=GroundTruth(multiple),
    )


def candidate_growth_fixture() -> dict[str, Any]:
    return {
        "name": "point-in-time positive growth",
        "as_of": NOW.isoformat(),
        "expected": "positive",
        "documents": [
            {
                "document_id": "candidate_growth_fixture",
                "source_type": "financials",
                "published_at": NOW.isoformat(),
                "available_at": NOW.isoformat(),
                "content": "Revenue grew 25 percent year over year.",
                "metadata": {"revenue_growth_yoy": 0.25},
            }
        ],
    }


def make_trajectory(
    company_id: str,
    multiple: float,
    predicted_surge: bool,
    predicted_magnitude: MagnitudeClass | None,
    *,
    signal_result: SignalResult | None = None,
) -> ExecutionTrajectory:
    truth = GroundTruth(multiple)
    prediction = BlindPrediction(
        is_surge=predicted_surge,
        magnitude=predicted_magnitude,
        confidence=ConfidenceLevel.MEDIUM,
        key_reasons=("fixture reason",),
        uncertainties=(),
        session_id=f"session_{company_id}",
    )
    final_state = ResearchState(decision=ResearchDecision.FINALIZE)
    signal_rounds = ()
    if signal_result is not None:
        from stock_opportunity_agent.signal_library import SignalBatchResult

        signal_rounds = (
            SignalRound(
                information_needs=("fixture need",),
                selected_signals=(signal_result.ref,),
                batch=SignalBatchResult(
                    results=(signal_result,),
                    signal_calls=1,
                ),
            ),
        )
    return ExecutionTrajectory(
        company_id=company_id,
        prediction_time=NOW,
        basic_info={"ticker": company_id.upper()},
        initial_state=final_state,
        signal_rounds=signal_rounds,
        final_state=final_state,
        final_context={"fixture": True},
        prediction=prediction,
        prediction_ref=f"predictions/{company_id}.json",
        ground_truth=truth,
        self_reflection=PredictionSelfReflection(
            correct=(predicted_surge == truth.is_surge),
        ),
        stop_reason=RuntimeStopReason.FINALIZED,
        usage=RuntimeUsage(
            signal_rounds=len(signal_rounds),
            signal_calls=len(signal_rounds),
            model=AgentUsage(),
        ),
    )


def make_record(
    plan_id: str,
    binary_f1: float,
    embedding: tuple[float, ...],
    *,
    round_id: int = 1,
) -> PlanRecord:
    base = default_information_plan()
    plan = InformationPlan(
        plan_id=plan_id,
        parent_ids=(),
        basic_info_policy=base.basic_info_policy,
        initial_research_skill=f"{base.initial_research_skill} {plan_id}",
        reflection_skill=base.reflection_skill,
        analysis_prompt=base.analysis_prompt,
    )
    return PlanRecord(
        plan=plan,
        round_id=round_id,
        embedding=embedding,
        metrics=PlanMetrics(
            binary_precision=binary_f1,
            binary_recall=binary_f1,
            binary_f1=binary_f1,
            magnitude_accuracy=0.0,
            magnitude_macro_f1=0.0,
            true_positive=0,
            false_positive=0,
            true_negative=1,
            false_negative=0,
            sample_count=1,
        ),
        reflection=PlanReflection(),
        signal_usage={},
        trajectories=(make_trajectory(f"case_{plan_id}", 1.0, False, None),),
    )
