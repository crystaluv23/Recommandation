from __future__ import annotations

import hashlib
import json
import random
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import (
    RawInfoDocument,
    RawInfoStore,
    content_sha256,
)
from stock_opportunity_agent.data.resolution import RawInfoRequest
from stock_opportunity_agent.llm.agent import (
    AgentRequest,
    AgentTurn,
    AgentUsage,
    DomainTool,
    GenericAgent,
    ToolCall,
    ToolObservation,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import (
    DEFAULT_EVOLUTION_PRIORS,
    AgentStep,
    BasicInfoPolicy,
    BlindPrediction,
    CaseReflectionEvidence,
    CandidateJudgment,
    CandidateProposalRejected,
    ConfidenceLevel,
    DualLoopEvolutionEngine,
    EvaluationCaseReadiness,
    EvaluationDatasetManager,
    EvaluationDatasetInfeasible,
    EvolutionCase,
    EvolutionDataset,
    EvolutionWorkspace,
    ExecutionTrajectory,
    GroundTruth,
    HashingPlanEmbedder,
    InformationPlan,
    MagnitudeClass,
    PlanArchive,
    PlanEvaluationConfig,
    PlanEvaluationAttempt,
    PlanEvolutionEngine,
    PlanMetaMemory,
    PlanMetaReflection,
    PlanMetrics,
    ParentPlanReflectionEvidence,
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
    RoundPaused,
    SharedEvaluationDataUnavailable,
    SignalCandidateEffectivenessEvaluator,
    SignalCandidateValidator,
    SignalEvolutionEngine,
    SignalMiningDecision,
    SignalMiningHypothesis,
    SignalMiningSignature,
    SignalRound,
    candidate_judgment_feedback,
    build_parent_plan_comparison,
    default_information_plan,
    execute_information_plan,
    score_predictions,
    _mask_identity_values,
)
from stock_opportunity_agent.research.evolution_runtime import ExternalRequestPending
from stock_opportunity_agent.signal_library import (
    SignalCoverage,
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


class EmptyMiningModel:
    def __init__(self) -> None:
        self.requests: list[Mapping[str, Any]] = []

    def propose_hypotheses(self, payload):
        self.requests.append(dict(payload))
        return AgentStep((), AgentUsage(llm_calls=1))

    def rank_cases(self, payload):
        raise AssertionError("empty Mining model must stop after H1")

    def contrast(self, payload):
        raise AssertionError("empty Mining model must stop after H1")

    def extract_exploration(self, payload):
        raise AssertionError("empty Mining model is not configured for exploration")

    def discover_exploration(self, payload):
        raise AssertionError("empty Mining model is not configured for exploration")


class ScriptedMiningModel(EmptyMiningModel):
    def __init__(
        self,
        *,
        hypotheses=(),
        rankings=None,
        decisions=(),
        signatures=(),
    ) -> None:
        super().__init__()
        self.hypotheses = tuple(hypotheses)
        self.rankings = dict(rankings or {})
        self.decisions = tuple(decisions)
        self.signatures = tuple(signatures)

    def propose_hypotheses(self, payload):
        self.requests.append(dict(payload))
        return AgentStep(self.hypotheses, AgentUsage(llm_calls=1))

    def rank_cases(self, payload):
        self.requests.append(dict(payload))
        return AgentStep(self.rankings, AgentUsage(llm_calls=1))

    def contrast(self, payload):
        self.requests.append(dict(payload))
        return AgentStep(self.decisions, AgentUsage(llm_calls=1))

    def extract_exploration(self, payload):
        self.requests.append(dict(payload))
        return AgentStep(self.signatures, AgentUsage(llm_calls=1))

    def discover_exploration(self, payload):
        self.requests.append(dict(payload))
        return AgentStep(self.decisions, AgentUsage(llm_calls=1))


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

    def finalize(self, plan, state, reason):
        return AgentStep(
            ResearchState(
                hypotheses=state.hypotheses,
                current_beliefs=state.current_beliefs,
                supporting_evidence=state.supporting_evidence,
                resolved_questions=state.resolved_questions,
                decision=ResearchDecision.FINALIZE,
            ),
            AgentUsage(llm_calls=1, tokens=10, cost=0.005),
        )


class OneSignalSelector:
    def select(
        self,
        information_needs,
        signal_registry,
        prior_signal_fingerprints=None,
        prior_signal_results=None,
        eligible_signal_refs=None,
    ):
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
                candidate_judgment=(
                    CandidateJudgment.POSSIBLE
                    if self.is_surge
                    else CandidateJudgment.UNLIKELY
                ),
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
    def test_external_approval_pause_propagates_through_tool_boundary(self) -> None:
        model = ScriptedAgentModel(
            [AgentTurn(tool_call=ToolCall("lookup", {}))]
        )

        def pause() -> None:
            raise ExternalRequestPending("a" * 64, Path("request.json"))

        with self.assertRaises(ExternalRequestPending):
            GenericAgent(model).run(
                prompt="fixture",
                tools=(DomainTool("lookup", "fixture lookup", pause),),
                workspace={},
                output_schema=lambda value: value,
                max_steps=1,
            )

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

    def test_agent_exposes_tool_signature_and_returns_argument_error_for_repair(self) -> None:
        model = ScriptedAgentModel(
            [
                AgentTurn(tool_call=ToolCall("lookup", {})),
                AgentTurn(final_output={"answer": 4}),
            ]
        )

        result = GenericAgent(model).run(
            prompt="Use the domain tool and repair invalid arguments.",
            tools=(DomainTool("lookup", "Look up a value.", lambda key: 4),),
            workspace={"scope": "fixture"},
            output_schema=lambda value: int(value["answer"]),
            max_steps=2,
        )

        self.assertIn("key", model.requests[0].tool_cards[0]["arguments"])
        self.assertEqual(
            model.requests[0].tool_cards[0]["arguments_schema"]["required"],
            ["key"],
        )
        self.assertEqual(
            result.observations[0].result,
            {"error": "invalid_arguments", "expected": "(key)"},
        )
        self.assertEqual(model.requests[1].observations, result.observations)

    def test_agent_returns_domain_validation_error_for_bounded_repair(self) -> None:
        def validate_as_of(as_of: str) -> int:
            raise ValidationError("as_of must be timezone-aware")

        model = ScriptedAgentModel(
            [
                AgentTurn(
                    tool_call=ToolCall("lookup", {"as_of": "2025-01-15"})
                ),
                AgentTurn(final_output={"answer": 4}),
            ]
        )

        result = GenericAgent(model).run(
            prompt="Use the domain tool and repair invalid values.",
            tools=(DomainTool("lookup", "Look up a value.", validate_as_of),),
            workspace={"scope": "fixture"},
            output_schema=lambda value: int(value["answer"]),
            max_steps=2,
        )

        self.assertEqual(
            result.observations[0].result,
            {
                "error": "tool_validation",
                "message": "as_of must be timezone-aware",
            },
        )
        self.assertEqual(model.requests[1].observations, result.observations)

    def test_agent_returns_output_validation_error_for_bounded_repair(self) -> None:
        def parse_answer(value):
            if not isinstance(value, dict):
                raise ValidationError("final output must be an object")
            return int(value["answer"])

        model = ScriptedAgentModel(
            [
                AgentTurn(final_output='{"answer": 4}'),
                AgentTurn(final_output={"answer": 4}),
            ]
        )

        result = GenericAgent(model).run(
            prompt="Return a validated object.",
            tools=(),
            workspace={"scope": "fixture"},
            output_schema=parse_answer,
            max_steps=2,
        )

        self.assertEqual(result.value, 4)
        self.assertEqual(
            result.observations[0].result,
            {
                "error": "output_validation",
                "message": "final output must be an object",
            },
        )
        self.assertEqual(model.requests[1].observations, result.observations)

    def test_agent_returns_completion_validation_error_for_workflow_repair(self) -> None:
        model = ScriptedAgentModel(
            [
                AgentTurn(final_output={"answer": 4}),
                AgentTurn(tool_call=ToolCall("lookup", {"key": "x"})),
                AgentTurn(final_output={"answer": 4}),
            ]
        )

        def require_lookup(value, observations):
            if not any(item.name == "lookup" for item in observations):
                raise ValidationError("lookup must run before final output")

        result = GenericAgent(model).run(
            prompt="Use the required workflow.",
            tools=(DomainTool("lookup", "Look up a value.", lambda key: 4),),
            workspace={},
            output_schema=lambda value: int(value["answer"]),
            completion_validator=require_lookup,
            max_steps=3,
        )

        self.assertEqual(result.value, 4)
        self.assertEqual(
            result.observations[0].result,
            {
                "error": "output_validation",
                "message": "lookup must run before final output",
            },
        )
        self.assertEqual(result.observations[1].name, "lookup")

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
        self.assertEqual(registry.install_catalog(SEED_CATALOG), 14)
        return registry

    def test_unavailable_signal_result_rejects_placeholder_evidence(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot carry evidence"):
            SignalResult(
                signal_id="customer_concentration",
                version=1,
                value=SignalValue.UNAVAILABLE,
                confidence=0.5,
                interpretation="No relevant concentration disclosure was visible.",
                supporting_evidence=(
                    SignalEvidence(
                        document_id="filing-1",
                        exact_span="Routine filing cover-page text.",
                        timestamp=NOW,
                    ),
                ),
                coverage=SignalCoverage.UNAVAILABLE,
            )

    def test_seed_catalog_progressive_disclosure_and_frozen_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            self.assertEqual(len(registry.list_signal_cards()), 14)
            self.assertIn("financial", registry.list_categories())
            cards = registry.search_signal_cards("customer")
            self.assertTrue(cards)
            self.assertEqual(cards[0].to_dict()["signal_ref"], cards[0].ref)
            self.assertFalse(registry.search_signal_cards("market cap"))
            with self.assertRaises(ValidationError):
                registry.load_spec("pilot_to_volume:v1")
            spec = registry.load_spec("guidance_acceleration:v1")
            self.assertEqual(spec.execution_type, SignalExecutionType.LLM)
            self.assertIn("guidance", registry.load_skill(spec.ref))
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

    def test_empty_registry_cannot_be_frozen_for_an_evolution_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")

            with self.assertRaisesRegex(ValidationError, "empty stable Signal"):
                registry.freeze()

    def test_rejected_next_version_can_be_repaired_without_erasing_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self._registry(directory)
            rejected = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Rejected revenue-growth draft.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            registry.stage_candidate(
                rejected,
                tests=(candidate_growth_fixture(),),
                origin="cycle-1-update",
            )
            rejected_hash = registry.candidate_hash(rejected.ref)
            registry.record_candidate_validation(
                rejected.ref,
                candidate_hash=rejected_hash,
                accepted=False,
                reasons=("fixture failed",),
            )
            repaired = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Repaired point-in-time revenue growth.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )

            registry.stage_candidate(
                repaired,
                tests=(candidate_growth_fixture(),),
                origin="cycle-2-update",
            )

            active, _skill = registry.load_candidate(repaired.ref)
            self.assertEqual(active, repaired)
            archived = list(
                (root / "signals_candidates" / ".rejected").glob(
                    "financial/revenue_growth_yoy/v2/*/validation.json"
                )
            )
            self.assertEqual(len(archived), 1)
            self.assertEqual(
                json.loads(archived[0].read_text(encoding="utf-8"))["candidate_hash"],
                rejected_hash,
            )

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
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    ),
                    RawInfoDocument.create(
                        document_id="financial_future",
                        company_id="issuer_1",
                        source_type="financials",
                        published_at=NOW + timedelta(days=1),
                        available_at=NOW + timedelta(days=1),
                        content=sec_company_facts_content(
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                            ("2025-01-01", "2025-12-31", 50.0, "2026-01-10"),
                        ),
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
                    ("guidance_acceleration:v1",),
                    company_id="issuer_1",
                    as_of=NOW,
                )


class InformationPlanRuntimeTests(TestCase):
    def test_composite_formal_name_masks_natural_name_but_keeps_third_party(self) -> None:
        masked = _mask_identity_values(
            "UBS Boosts Kinross Gold’s (KGC) Price Target; Kinross later responded.",
            ("KGC", "Kinross Gold Corp / KINROSS GOLD CORP"),
        )

        self.assertEqual(masked.count("[MASKED_COMPANY]"), 3)
        self.assertNotIn("Kinross Gold", masked)
        self.assertNotIn("Kinross", masked)
        self.assertNotIn("KGC", masked)
        self.assertIn("UBS Boosts", masked)
        self.assertEqual(
            _mask_identity_values("Company Inc reported.", ("Company Inc",)),
            "[MASKED_COMPANY] reported.",
        )

    def test_short_ticker_masking_is_case_sensitive(self) -> None:
        masked = _mask_identity_values(
            (
                "low liquidity improved while LOW remained anonymous; "
                "https://www.low.com/LOW-news"
            ),
            ("LOW",),
        )
        self.assertEqual(
            masked,
            (
                "low liquidity improved while [MASKED_COMPANY] remained anonymous; "
                "https://www.[MASKED_COMPANY].com/[MASKED_COMPANY]-news"
            ),
        )

    def test_formal_name_masks_short_uppercase_brand_and_url_alias(self) -> None:
        masked = _mask_identity_values(
            "AAR signed an agreement at https://www.aar.com/aar-update.",
            ("AIR", "AAR Corp / AAR CORP"),
        )

        self.assertEqual(masked.count("[MASKED_COMPANY]"), 3)
        self.assertNotIn("AAR", masked)
        self.assertNotIn("aar", masked)

    def test_legacy_basic_info_fields_read_but_new_artifacts_write_requests(self) -> None:
        policy = type(default_information_plan().basic_info_policy).from_dict(
            {"fields": ["industry", "business_description"]}
        )
        self.assertEqual(
            [item.request_id for item in policy.requests],
            ["legacy_industry", "legacy_business_description"],
        )
        self.assertEqual(set(policy.to_dict()), {"requests"})

    def test_basic_info_policy_cannot_request_outcome_fields(self) -> None:
        base = default_information_plan()
        with self.assertRaisesRegex(ValidationError, "outcome data"):
            InformationPlan(
                plan_id="leaking_plan",
                parent_ids=(),
                basic_info_policy=type(base.basic_info_policy)(
                    requests=(
                        RawInfoRequest(
                            request_id="hidden_ground_truth",
                            description="Retrieve a hidden outcome.",
                            source_types=("filing",),
                        ),
                    )
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

    def test_case_readiness_prepares_broad_stable_signal_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            snapshot = registry.freeze()
            case = make_case("issuer_ready", 4.0)

            def raw(source_type: str) -> RawInfoDocument:
                return RawInfoDocument.create(
                    document_id=f"ready_{source_type}",
                    company_id=case.company_id,
                    source_type=source_type,
                    published_at=NOW,
                    available_at=NOW,
                    content=f"Point-in-time {source_type} evidence.",
                    metadata=(
                        {"prices": [100.0, 110.0]}
                        if source_type == "market_data"
                        else {}
                    ),
                )

            passing_store = RawInfoStore(
                documents=(raw("financials"), raw("market_data"), raw("filing"))
            )
            passing = RuntimePlanEvaluator(
                raw_info_store=passing_store,
                controller=OneBatchController(),
                signal_agent=OneSignalSelector(),
                predictor=FixedPredictor(),
                prediction_root=root / "passing_predictions",
                signal_readiness_snapshot=snapshot,
            ).check_case_readiness(case)

            failing_store = RawInfoStore(
                documents=(raw("financials"), raw("market_data"), raw("news"))
            )
            failing = RuntimePlanEvaluator(
                raw_info_store=failing_store,
                controller=OneBatchController(),
                signal_agent=OneSignalSelector(),
                predictor=FixedPredictor(),
                prediction_root=root / "failing_predictions",
                signal_readiness_snapshot=snapshot,
            ).check_case_readiness(case)

            self.assertTrue(passing.ready)
            self.assertFalse(failing.ready)
            self.assertEqual(
                failing.reason,
                "signal_data_readiness_below_threshold:10/14",
            )

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
                self.assertNotIn('"LOW"', serialized)
                self.assertNotIn("company_name", final_context["basic_info"])
                self.assertNotIn("ticker", final_context["basic_info"])
                self.assertNotIn("runtime_stop_reason", final_context)
                self.assertNotIn("runtime_termination_trigger", final_context)
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
                    "ticker": "LOW",
                    "market_cap": 6_000_000_000,
                    "industry": "industrial",
                    "business_description": "low liquidity equipment",
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
            self.assertNotIn(
                "usage", trajectory.final_context["signal_rounds"][0]["batch"]
            )
            self.assertIn("usage", trajectory.signal_rounds[0].to_dict()["batch"])
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
            self.assertEqual(trajectory.stop_reason, RuntimeStopReason.FINALIZED)
            self.assertEqual(
                trajectory.termination_trigger,
                RuntimeStopReason.MAX_SIGNAL_ROUNDS,
            )
            self.assertEqual(len(trajectory.signal_rounds), 1)
            self.assertEqual(persisted, ["done"])

    def test_runtime_omits_executed_refs_before_next_signal_selection(self) -> None:
        class LoopingController(OneBatchController):
            def reflect(self, plan, state, batch):
                return AgentStep(
                    ResearchState(next_information_needs=("find new evidence",)),
                    AgentUsage(llm_calls=1),
                )

        class EligibleSelector:
            def __init__(self) -> None:
                self.eligible_calls: list[tuple[str, ...]] = []

            def select(
                self,
                information_needs,
                signal_registry,
                prior_signal_fingerprints=None,
                prior_signal_results=None,
                eligible_signal_refs=None,
            ):
                eligible = tuple(eligible_signal_refs or ())
                self.eligible_calls.append(eligible)
                if "revenue_growth_yoy:v1" in eligible:
                    return AgentStep(("revenue_growth_yoy:v1",), AgentUsage())
                return AgentStep((), AgentUsage())

        with tempfile.TemporaryDirectory() as directory:
            registry, store = self._registry_and_store(directory)
            selector = EligibleSelector()
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), store),
                controller=LoopingController(),
                signal_agent=selector,
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(
                    max_signal_rounds=5,
                    max_signal_calls=5,
                    max_llm_calls=10,
                ),
            )

            self.assertEqual(len(trajectory.signal_rounds), 1)
            self.assertEqual(
                trajectory.termination_trigger,
                RuntimeStopReason.NO_SIGNAL_MATCH,
            )
            self.assertIn("revenue_growth_yoy:v1", selector.eligible_calls[0])
            self.assertNotIn("revenue_growth_yoy:v1", selector.eligible_calls[1])
            self.assertFalse(trajectory.signal_rounds[0].batch.skipped_unchanged_refs)

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
            attempt = evaluator.evaluate(
                default_information_plan(), cases, registry.freeze()
            )
            trajectories = attempt.trajectories
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
            self.assertEqual(resumed.trajectories, trajectories)
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
                candidate_judgment=CandidateJudgment.POSSIBLE,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("reason",),
                uncertainties=(),
                session_id="s",
            )
        with self.assertRaisesRegex(ValidationError, "cannot include magnitude"):
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.UNLIKELY,
                magnitude=MagnitudeClass.TWO_TO_THREE,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("reason",),
                uncertainties=(),
                session_id="s",
            )

    def test_prediction_schema_rejects_four_way_binary_mismatch(self) -> None:
        with self.assertRaisesRegex(ValidationError, "does not match is_surge"):
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.POSSIBLE,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("reason",),
                uncertainties=(),
                session_id="s",
            )

    def test_candidate_judgment_feedback_covers_all_four_way_truth_pairs(self) -> None:
        expected = {
            (CandidateJudgment.LIKELY, True): "strong_correct_positive",
            (CandidateJudgment.POSSIBLE, True): "correct_positive_conservative",
            (CandidateJudgment.UNLIKELY, True): "severe_false_negative",
            (
                CandidateJudgment.INSUFFICIENT_INFORMATION,
                True,
            ): "false_negative_information_gap",
            (CandidateJudgment.UNLIKELY, False): "strong_correct_negative",
            (
                CandidateJudgment.INSUFFICIENT_INFORMATION,
                False,
            ): "correct_negative_information_gap",
            (CandidateJudgment.POSSIBLE, False): "false_positive",
            (
                CandidateJudgment.LIKELY,
                False,
            ): "severe_overconfident_false_positive",
        }
        for (judgment, true_is_surge), assessment in expected.items():
            with self.subTest(judgment=judgment.value, truth=true_is_surge):
                prediction = BlindPrediction(
                    is_surge=judgment.is_positive,
                    candidate_judgment=judgment,
                    magnitude=(
                        MagnitudeClass.TWO_TO_THREE
                        if judgment.is_positive
                        else None
                    ),
                    confidence=ConfidenceLevel.MEDIUM,
                    key_reasons=("source-backed reason",),
                    uncertainties=(),
                    session_id="s",
                )
                feedback = candidate_judgment_feedback(
                    prediction,
                    GroundTruth(2.2 if true_is_surge else 1.2),
                )
                self.assertEqual(feedback["assessment"], assessment)
                self.assertEqual(
                    feedback["binary_correct"],
                    judgment.is_positive == true_is_surge,
                )

    def test_trajectory_persists_and_validates_candidate_judgment_feedback(self) -> None:
        trajectory = make_trajectory(
            "feedback_case",
            2.2,
            True,
            MagnitudeClass.TWO_TO_THREE,
            candidate_judgment=CandidateJudgment.POSSIBLE,
        )
        serialized = trajectory.to_dict()

        self.assertEqual(
            serialized["prediction"]["candidate_judgment"],
            "possible",
        )
        self.assertEqual(
            serialized["candidate_judgment_feedback"]["assessment"],
            "correct_positive_conservative",
        )
        self.assertEqual(
            ExecutionTrajectory.from_dict(serialized).to_dict(),
            serialized,
        )

        tampered = json.loads(json.dumps(serialized))
        tampered["candidate_judgment_feedback"]["binary_correct"] = False
        with self.assertRaisesRegex(ValidationError, "does not match"):
            ExecutionTrajectory.from_dict(tampered)

    def test_four_way_categories_do_not_change_binary_f1_semantics(self) -> None:
        trajectories = (
            make_trajectory(
                "likely_true",
                2.2,
                True,
                MagnitudeClass.TWO_TO_THREE,
                candidate_judgment=CandidateJudgment.LIKELY,
            ),
            make_trajectory(
                "possible_true",
                2.2,
                True,
                MagnitudeClass.TWO_TO_THREE,
                candidate_judgment=CandidateJudgment.POSSIBLE,
            ),
            make_trajectory(
                "unlikely_false",
                1.2,
                False,
                None,
                candidate_judgment=CandidateJudgment.UNLIKELY,
            ),
            make_trajectory(
                "insufficient_false",
                1.2,
                False,
                None,
                candidate_judgment=CandidateJudgment.INSUFFICIENT_INFORMATION,
            ),
        )

        metrics = score_predictions(trajectories)

        self.assertEqual(metrics.binary_f1, 1.0)
        self.assertEqual(
            (metrics.true_positive, metrics.true_negative),
            (2, 2),
        )

class EvaluationDatasetSamplingTests(TestCase):
    def test_snapshots_freeze_anchor_and_rotate_exact_random_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evaluation"
            pool = make_evaluation_pool()
            anchors = make_anchor_pool()
            config = PlanEvaluationConfig()
            manager = EvaluationDatasetManager(root, pool, anchors, config)

            round_one = manager.get_or_create_round_dataset(1)
            round_two = manager.get_or_create_round_dataset(2)

            self.assertEqual(round_one.actual_counts, {
                "non_surge": 10,
                "2_3x": 7,
                "3_10x": 5,
                "10x_plus": 2,
            })
            self.assertEqual(round_two.actual_counts, round_one.actual_counts)
            self.assertEqual(round_one.anchor_case_ids, round_two.anchor_case_ids)
            self.assertFalse(
                set(round_one.random_case_ids) & set(round_two.random_case_ids)
            )
            all_round_cases = manager.resolve_cases(round_one.case_ids)
            self.assertEqual(
                len({case.company_id for case in all_round_cases}),
                len(all_round_cases),
            )
            self.assertEqual(round_one.random_seed, 43)
            self.assertTrue((root / "round_001" / "snapshot.json").is_file())
            self.assertTrue((root / "anchor.json").is_file())

            restarted = EvaluationDatasetManager(
                root, tuple(reversed(pool)), anchors, config
            )
            reused = restarted.get_or_create_round_dataset(1)
            self.assertEqual(reused.snapshot_id, round_one.snapshot_id)
            self.assertEqual(reused.case_ids, round_one.case_ids)

    def test_new_random_snapshot_skips_unready_case_without_changing_quotas(self) -> None:
        pool = make_evaluation_pool()
        anchors = make_anchor_pool()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = EvaluationDatasetManager(
                root / "baseline", pool, anchors
            ).get_or_create_round_dataset(1)
            blocked_case_id = baseline.random_case_ids[0]
            checked: list[str] = []

            def readiness(case: EvolutionCase) -> EvaluationCaseReadiness:
                checked.append(case.case_id)
                if case.case_id == blocked_case_id:
                    return EvaluationCaseReadiness(
                        case.case_id, False, "provider_no_data"
                    )
                return EvaluationCaseReadiness(case.case_id, True)

            snapshot = EvaluationDatasetManager(
                root / "ready",
                pool,
                anchors,
                case_readiness=readiness,
            ).get_or_create_round_dataset(1)

            self.assertNotIn(blocked_case_id, snapshot.random_case_ids)
            self.assertIn(blocked_case_id, checked)
            self.assertEqual(
                dict(snapshot.random_actual_counts),
                dict(PlanEvaluationConfig().random_label_counts),
            )
            self.assertEqual(len(snapshot.case_ids), 24)

    def test_hash_valid_snapshot_cannot_reuse_one_company(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evaluation"
            pool = make_evaluation_pool()
            anchors = make_anchor_pool()
            manager = EvaluationDatasetManager(root, pool, anchors)
            snapshot = manager.get_or_create_round_dataset(1)
            original = manager.resolve_cases((snapshot.random_case_ids[0],))[0]
            duplicate_company = EvolutionCase(
                company_id=original.company_id,
                prediction_time=NOW + timedelta(days=1),
                basic_info=original.basic_info,
                ground_truth=original.ground_truth,
            )
            path = root / "round_001" / "snapshot.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["random_case_ids"][1] = duplicate_company.case_id
            payload["case_ids"][len(snapshot.anchor_case_ids) + 1] = (
                duplicate_company.case_id
            )
            unhashed = {key: value for key, value in payload.items() if key != "snapshot_id"}
            payload["snapshot_id"] = hashlib.sha256(
                json.dumps(
                    unhashed,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            path.write_text(json.dumps(payload), encoding="utf-8")

            restarted = EvaluationDatasetManager(
                root, (*pool, duplicate_company), anchors
            )
            with self.assertRaisesRegex(ValidationError, "sampling contract"):
                restarted.get_or_create_round_dataset(1)

    def test_sampling_shortage_fails_closed(self) -> None:
        shared_one = EvolutionCase(
            company_id="shared",
            prediction_time=NOW,
            basic_info={"company_name": "shared"},
            ground_truth=GroundTruth(1.1),
            case_id="shared:first",
        )
        shared_two = EvolutionCase(
            company_id="shared",
            prediction_time=NOW + timedelta(days=1),
            basic_info={"company_name": "shared"},
            ground_truth=GroundTruth(1.2),
            case_id="shared:second",
        )
        positive = make_case("only_positive", 2.2)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EvaluationDatasetInfeasible):
                EvaluationDatasetManager(
                    Path(directory),
                    (shared_one, shared_two, positive),
                    make_anchor_pool(),
                    PlanEvaluationConfig(),
                )


class PlanArchiveAndWorkspaceTests(TestCase):
    def test_durable_attempt_trajectories_feed_capability_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            trajectory = replace(
                make_trajectory("issuer_gap", 1.2, False, None),
                basic_info={
                    "requests": [
                        {
                            "data_gap": {
                                "request_id": "recent_news",
                                "reason": "adapter_missing",
                                "message": "missing",
                                "source_types": ["news"],
                                "provider": None,
                            }
                        }
                    ]
                },
            )
            attempt = PlanEvaluationAttempt(
                plan=default_information_plan(),
                expected_case_ids=(trajectory.case_id,),
                trajectories=(trajectory,),
            )

            path = workspace.stage_evaluation_attempt(
                round_id=1,
                attempt=attempt,
                available_source_types=("news",),
            )

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["trajectories"][0]["case_id"], trajectory.case_id)
            backlog = json.loads(
                (workspace.root / "capability_backlog.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(backlog["items"][0]["request_id"], "recent_news")
            self.assertEqual(backlog["items"][0]["status"], "resolved")

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
                signal_registry_version=1,
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

    def test_workspace_rejects_checkpoint_record_cross_link_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_committed", 0.8, (1.0, 0.0), round_id=1)
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=("plan_committed",),
                ),
                signal_registry_version=1,
                signal_registry_hash="registry-hash",
            )
            record_path = workspace.plans_root / "plan_committed" / "record.json"
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            payload["round_id"] = 2
            record_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValidationError, "cross-links"):
                workspace.restore_archive()

    def test_workspace_accepts_equivalent_checkpoint_path_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_committed", 0.8, (1.0, 0.0), round_id=1)
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=("plan_committed",),
                ),
                signal_registry_version=1,
                signal_registry_hash="registry-hash",
            )
            state = json.loads(workspace.state_path.read_text(encoding="utf-8"))
            checkpoint_path = Path(state["checkpoint_ref"])
            state["checkpoint_ref"] = str(
                checkpoint_path.parent
                / ".."
                / checkpoint_path.parent.name
                / checkpoint_path.name
            )
            workspace.state_path.write_text(json.dumps(state), encoding="utf-8")

            self.assertEqual(
                [item.plan_id for item in workspace.restore_archive().records],
                ["plan_committed"],
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
                signal_registry_version=1,
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
                    signal_registry_version=1,
                    signal_registry_hash="registry-hash",
                )
            self.assertEqual(workspace.last_completed_round, 0)

    def test_meta_memory_is_fifo_and_requires_monotonic_grounded_entries(self) -> None:
        memory = PlanMetaMemory(maxlen=2)
        plan_reflection = PlanMetaReflection.from_record(
            make_record("plan_meta_fifo", 0.8, (1.0, 0.0))
        )
        for round_id in (1, 2, 3):
            memory.append(
                RoundMetaEntry(
                    round_id=round_id,
                    plan_reflections=(plan_reflection,),
                    evidence_refs=(plan_reflection.plan_id,),
                )
            )
        self.assertEqual([entry.round_id for entry in memory.entries], [2, 3])
        self.assertTrue(
            all(
                entry.plan_reflections == (plan_reflection,)
                for entry in memory.entries
            )
        )
        with self.assertRaisesRegex(ValidationError, "monotonically"):
            memory.append(
                RoundMetaEntry(
                    round_id=3,
                    evidence_refs=("plan_meta_fifo",),
                )
            )

    def test_additive_round_meta_round_trips_and_reads_legacy_horizontal_only(
        self,
    ) -> None:
        record = make_record("plan_meta_roundtrip", 0.8, (1.0, 0.0))
        plan_reflection = PlanMetaReflection.from_record(record)
        entry = RoundMetaEntry(
            round_id=1,
            successful_patterns=("preserve exact evidence",),
            search_implications=("restore annual filings",),
            evidence_refs=(record.plan_id,),
        ).append_plan_reflections((plan_reflection,))

        serialized = entry.to_dict()
        restored = RoundMetaEntry.from_dict(serialized)

        self.assertEqual(restored, entry)
        self.assertEqual(
            restored.plan_reflections[0].original_case_reflections[0].self_reflection,
            record.trajectories[0].self_reflection,
        )
        self.assertEqual(
            restored.plan_reflections[0].vertical_plan_reflection,
            record.reflection,
        )
        rendered = json.dumps(serialized)
        self.assertNotIn('"case_id"', rendered)
        self.assertNotIn('"company_id"', rendered)
        self.assertNotIn('"final_context"', rendered)
        legacy = dict(serialized)
        legacy.pop("plan_reflections")
        self.assertEqual(
            RoundMetaEntry.from_dict(legacy).plan_reflections,
            (),
        )

        unsafe_case = plan_reflection.original_case_reflections[0].to_dict()
        unsafe_case["company_id"] = "must-not-persist"
        with self.assertRaisesRegex(ValidationError, "fields are invalid"):
            CaseReflectionEvidence.from_dict(unsafe_case)

    def test_cycle_state_and_debug_events_resume_from_committed_round_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            started = workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=2,
                initial_signal_registry_version=1,
                initial_signal_registry_hash="registry-hash-v1",
                observed_signal_registry_version=1,
                observed_signal_registry_hash="registry-hash-v1",
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
                    signal_registry_version=1,
                    signal_registry_hash="registry-hash",
                    run_contract_hash="contract-hash",
                )
                resumed = EvolutionWorkspace(directory).start_or_resume_cycle(
                    run_contract_hash="contract-hash",
                    target_plan_rounds=2,
                    initial_signal_registry_version=1,
                    initial_signal_registry_hash="registry-hash-v1",
                    observed_signal_registry_version=1,
                    observed_signal_registry_hash="registry-hash-v1",
                )
                self.assertEqual(resumed["completed_plan_rounds"], round_id)

            workspace = EvolutionWorkspace(directory)
            self.assertEqual(
                [event["event_type"] for event in workspace.load_events()],
                ["cycle_started", "recovered_after_truncated_log"],
            )
            validation = {
                "mined_candidates": [],
                "updated_candidates": [],
                "validated_candidates": {},
                "rejected": {},
                "input_registry_version": 1,
                "input_registry_hash": "registry-hash-v1",
                "input_signal_refs": ["fixture:v1"],
            }
            workspace.stage_slow_validation(cycle_id=1, validation=validation)
            result = {
                **validation,
                "promoted": [],
                "output_registry_version": 1,
                "output_registry_hash": "registry-hash-v1",
            }
            staged = workspace.stage_slow_result(
                cycle_id=1,
                result=result,
            )
            self.assertTrue(staged.is_file())
            self.assertEqual(
                workspace.staged_slow_result(1),
                result,
            )
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=1,
                observed_signal_registry_hash="registry-hash-v1",
            )
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
        proposal_attempt,
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
                "proposal_attempt": proposal_attempt,
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
        self.seen_registry_refs: list[tuple[str, ...]] = []

    def evaluate(self, plan, cases, signal_registry):
        self.seen_registry_refs.append(
            tuple(spec.ref for spec in signal_registry.specs)
        )
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
                    case_id=case.case_id,
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
    def __init__(self) -> None:
        self.parent_comparisons: list[tuple[Mapping[str, Any], ...]] = []

    def critique(self, *, plan, trajectories, metrics, parent_comparisons=()):
        self.parent_comparisons.append(parent_comparisons)
        return PlanReflection(
            successful_patterns=("correct binary separation",),
            next_explorations=("test contradiction-first reflection",),
        )


class SimpleRoundReflector:
    def __init__(self) -> None:
        self.calls: list[tuple[int, tuple[str, ...], str]] = []
        self.parent_comparisons_by_plan_id: list[Mapping[str, Any]] = []

    def reflect(
        self,
        *,
        round_id,
        records,
        prior,
        parent_comparisons_by_plan_id=None,
    ):
        self.calls.append((round_id, tuple(record.plan_id for record in records), prior))
        self.parent_comparisons_by_plan_id.append(
            parent_comparisons_by_plan_id or {}
        )
        return RoundMetaEntry(
            round_id=round_id,
            successful_patterns=("correct binary separation",),
            useful_signals=("revenue_growth_yoy",),
            search_implications=("try contradiction-first",),
            evidence_refs=tuple(record.plan_id for record in records),
        )


class PlanEvolutionEngineTests(TestCase):
    def test_parent_comparison_only_deltas_metrics_on_exact_snapshot(self) -> None:
        def metrics(tp: int, fp: int, tn: int, fn: int) -> PlanMetrics:
            precision = tp / (tp + fp)
            recall = tp / (tp + fn)
            return PlanMetrics(
                binary_precision=precision,
                binary_recall=recall,
                binary_f1=2 * precision * recall / (precision + recall),
                magnitude_accuracy=0.0,
                magnitude_macro_f1=0.0,
                true_positive=tp,
                false_positive=fp,
                true_negative=tn,
                false_negative=fn,
                sample_count=tp + fp + tn + fn,
            )

        base = default_information_plan()
        parent_plan = replace(base, plan_id="parent_plan")
        child_plan = replace(
            base,
            plan_id="child_plan",
            parent_ids=(parent_plan.plan_id,),
            basic_info_policy=BasicInfoPolicy(
                requests=tuple(
                    request
                    for request in base.basic_info_policy.requests
                    if request.request_id
                    in {"recent_company_news", "recent_market_backbone"}
                )
            ),
        )
        parent_metrics = metrics(8, 1, 9, 6)
        child_metrics = metrics(5, 1, 9, 9)
        snapshot_id = "a" * 64
        evidence = ParentPlanReflectionEvidence(
            plan=parent_plan,
            source_scope="historical_seed",
            evaluation_snapshot_ids=(snapshot_id,),
            metrics_by_cohort={
                "anchor": parent_metrics,
                "random": parent_metrics,
                "combined": parent_metrics,
            },
        )

        comparison = build_parent_plan_comparison(
            parent=evidence,
            child_plan=child_plan,
            child_metrics=child_metrics,
            child_snapshot_id=snapshot_id,
        )

        self.assertTrue(comparison["same_evaluation_snapshot"])
        self.assertEqual(comparison["metric_delta"]["confusion"]["true_positive"], -3)
        self.assertEqual(comparison["metric_delta"]["confusion"]["false_negative"], 3)
        removed_ids = {
            item["request_id"]
            for item in comparison["plan_diff"]["basic_info_requests_removed"]
        }
        self.assertEqual(
            removed_ids,
            {"recent_annual_filing", "reported_financial_facts"},
        )

        cross_snapshot = build_parent_plan_comparison(
            parent=evidence,
            child_plan=child_plan,
            child_metrics=child_metrics,
            child_snapshot_id="b" * 64,
        )
        self.assertFalse(cross_snapshot["same_evaluation_snapshot"])
        self.assertIsNone(cross_snapshot["metric_delta"])

    def test_historical_warm_start_replaces_manual_cold_start_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            proposer = CountingProposer()
            base = default_information_plan()
            historical = InformationPlan(
                plan_id="historical_seed_fixture",
                parent_ids=(),
                basic_info_policy=base.basic_info_policy,
                initial_research_skill=(
                    f"{base.initial_research_skill} Historical warm start."
                ),
                reflection_skill=base.reflection_skill,
                analysis_prompt=base.analysis_prompt,
            )
            events: list[Mapping[str, Any]] = []
            critic = SimpleCritic()
            round_reflector = SimpleRoundReflector()
            dataset_manager = EvaluationDatasetManager(
                workspace.evaluation_root,
                make_evaluation_pool(),
                make_anchor_pool(),
            )
            snapshot = dataset_manager.get_or_create_round_dataset(1)
            parent_trajectories = SyntheticPlanEvaluator().evaluate(
                historical,
                dataset_manager.resolve_cases(snapshot.case_ids),
                registry.freeze(),
            )
            anchor_ids = set(snapshot.anchor_case_ids)
            parent_metrics_by_cohort = {
                "anchor": score_predictions(
                    tuple(
                        item
                        for item in parent_trajectories
                        if item.case_id in anchor_ids
                    )
                ),
                "random": score_predictions(
                    tuple(
                        item
                        for item in parent_trajectories
                        if item.case_id not in anchor_ids
                    )
                ),
                "combined": score_predictions(parent_trajectories),
            }
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=proposer,
                critic=critic,
                round_reflector=round_reflector,
                workspace=workspace,
                seed_plans=(base,),
                warm_start_plans=(historical,),
                warm_start_parent_evidence=(
                    ParentPlanReflectionEvidence(
                        plan=historical,
                        source_scope="historical_seed",
                        evaluation_snapshot_ids=(snapshot.snapshot_id,),
                        metrics_by_cohort=parent_metrics_by_cohort,
                    ),
                ),
                candidates_per_round=1,
                on_progress=events.append,
            )

            engine.run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )

            self.assertEqual(proposer.calls[0]["parents"], (historical.plan_id,))
            parent_event = next(
                item for item in events if item["event_type"] == "parents_selected"
            )
            self.assertEqual(parent_event["seed_parent_ids"], [historical.plan_id])
            comparison = critic.parent_comparisons[0][0]
            self.assertTrue(comparison["same_evaluation_snapshot"])
            self.assertIsNotNone(comparison["metric_delta"])
            self.assertEqual(
                round_reflector.parent_comparisons_by_plan_id[0][
                    "plan_child_1"
                ],
                critic.parent_comparisons[0],
            )
            committed_meta = workspace.restore_meta().entries[0]
            self.assertEqual(
                committed_meta.plan_reflections[0].parent_comparisons,
                critic.parent_comparisons[0],
            )
            self.assertEqual(
                committed_meta.plan_reflections[
                    0
                ].vertical_plan_reflection.successful_patterns,
                ("correct binary separation",),
            )

    def test_current_top_k_displaces_historical_warm_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            current = make_record("current_plan", 1.0, (1.0, 0.0))
            base = default_information_plan()
            historical = InformationPlan(
                plan_id="historical_seed_fixture",
                parent_ids=(),
                basic_info_policy=base.basic_info_policy,
                initial_research_skill=(
                    f"{base.initial_research_skill} Historical warm start."
                ),
                reflection_skill=base.reflection_skill,
                analysis_prompt=base.analysis_prompt,
            )
            proposer = CountingProposer()
            engine = PlanEvolutionEngine(
                archive=PlanArchive((current,)),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(base,),
                warm_start_plans=(historical,),
                candidates_per_round=1,
                top_k=1,
            )

            engine.run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )

            self.assertEqual(proposer.calls[0]["parents"], (current.plan_id,))

    def test_one_stage_shares_exact_round_snapshot_and_keeps_diagnostics(self) -> None:
        class StageAwareEvaluator:
            def __init__(self) -> None:
                self.calls: dict[str, list[tuple[str, ...]]] = {}

            def evaluate(self, plan, cases, signal_registry):
                prior_calls = self.calls.setdefault(plan.plan_id, [])
                prior_calls.append(tuple(case.case_id for case in cases))
                rows = []
                for case in cases:
                    if plan.plan_id == "plan_child_1":
                        predicted = True
                    elif plan.plan_id == "plan_child_2":
                        predicted = case.ground_truth.is_surge
                    else:
                        predicted = False
                    rows.append(
                        make_trajectory(
                            case.company_id,
                            case.ground_truth.realized_max_multiple,
                            predicted,
                            (
                                case.ground_truth.magnitude
                                if predicted and case.ground_truth.is_surge
                                else (
                                    MagnitudeClass.TWO_TO_THREE
                                    if predicted
                                    else None
                                )
                            ),
                            case_id=case.case_id,
                        )
                    )
                return tuple(rows)

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            evaluator = StageAwareEvaluator()
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=evaluator,
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=3,
            )
            result = engine.run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )

            round_ids = evaluator.calls["plan_child_1"][0]
            self.assertEqual(evaluator.calls["plan_child_2"][0], round_ids)
            self.assertEqual(evaluator.calls["plan_child_3"][0], round_ids)
            self.assertTrue(all(len(calls) == 1 for calls in evaluator.calls.values()))

            records = {record.plan_id: record for record in result.records}
            self.assertEqual(
                records["plan_child_3"].evaluation.evaluation_stage,
                "round",
            )
            self.assertEqual(records["plan_child_3"].evaluation.n_cases, 24)
            self.assertFalse(records["plan_child_3"].fitness.eligible)
            self.assertIn("no_positive_prediction", records["plan_child_3"].fitness.reasons)
            self.assertEqual(records["plan_child_3"].metrics.predicted_positive_count, 0)
            self.assertFalse(records["plan_child_3"].metrics.precision_defined)
            evaluated = records["plan_child_1"]
            self.assertEqual(evaluated.evaluation.evaluation_stage, "round")
            self.assertEqual(evaluated.evaluation.n_cases, 24)
            self.assertEqual(evaluated.metrics, score_predictions(evaluated.trajectories))
            self.assertEqual(
                set(evaluated.evaluation.metrics_by_cohort),
                {"anchor", "random", "combined"},
            )
            self.assertEqual(
                evaluated.evaluation.metrics_by_cohort["combined"],
                evaluated.metrics,
            )
            anchor_metrics = score_predictions(evaluated.trajectories[:16])
            random_metrics = score_predictions(evaluated.trajectories[16:])
            self.assertEqual(
                evaluated.evaluation.metrics_by_cohort["anchor"],
                anchor_metrics,
            )
            self.assertEqual(
                evaluated.evaluation.metrics_by_cohort["random"],
                random_metrics,
            )
            self.assertNotEqual(
                evaluated.metrics.binary_f1,
                (anchor_metrics.binary_f1 + random_metrics.binary_f1) / 2,
            )
            saved = json.loads(
                (
                    workspace.plans_root
                    / "plan_child_1"
                    / "record.json"
                ).read_text()
            )
            self.assertEqual(saved["evaluation_stage"], "round")
            self.assertEqual(saved["n_cases"], 24)
            self.assertEqual(len(saved["dataset_snapshot_ids"]), 1)

    def test_non_content_pause_is_not_converted_to_candidate_rejection(self) -> None:
        class PendingApproval(ValidationError):
            pass

        class PausingProposer:
            def propose(self, **kwargs):
                raise PendingApproval("external approval pending")

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            events = []
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=PausingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
                on_progress=events.append,
            )
            with self.assertRaisesRegex(PendingApproval, "approval pending"):
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 0)
            self.assertNotIn(
                "candidate_proposal_rejected",
                [item["event_type"] for item in events],
            )

    def test_all_rejected_candidates_leave_round_uncommitted(self) -> None:
        class RejectingProposer:
            def propose(self, **kwargs):
                raise CandidateProposalRejected(
                    "invalid Plan content after correction"
                )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            events = []
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=RejectingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=2,
                on_progress=events.append,
            )
            with self.assertRaisesRegex(RoundPaused, "all_candidate"):
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 0)
            self.assertEqual(
                [item["event_type"] for item in events].count(
                    "candidate_proposal_rejected"
                ),
                6,
            )

    def test_shared_anchor_data_pause_precedes_plan_calls_and_is_not_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            proposer = CountingProposer()
            anchors = make_anchor_pool()
            blocked_case_id = anchors[0].case_id

            def readiness(case: EvolutionCase) -> EvaluationCaseReadiness:
                if case.case_id == blocked_case_id:
                    return EvaluationCaseReadiness(
                        case.case_id,
                        False,
                        "provider_error",
                        retryable=True,
                    )
                return EvaluationCaseReadiness(case.case_id, True)

            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
                case_readiness=readiness,
            )

            with self.assertRaises(SharedEvaluationDataUnavailable) as context:
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=anchors,
                    signal_snapshot=registry.freeze(),
                )

            self.assertTrue(context.exception.retryable)
            self.assertEqual(proposer.calls, [])
            round_root = workspace.experiments_root / "round-0001"
            self.assertTrue((round_root / "shared-data-pause.json").is_file())
            self.assertFalse((round_root / "rejected.json").exists())
            self.assertEqual(workspace.last_completed_round, 0)

    def test_common_post_evaluation_evidence_gap_is_not_plan_rejection(self) -> None:
        class OneSharedGapEvaluator(SyntheticPlanEvaluator):
            def evaluate(self, plan, cases, signal_registry):
                rows = super().evaluate(plan, cases, signal_registry)
                return (
                    *rows[:-1],
                    replace(
                        rows[-1],
                        basic_info={"requests": []},
                        signal_rounds=(),
                    ),
                )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            critic = SimpleCritic()
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=OneSharedGapEvaluator(),
                proposer=CountingProposer(),
                critic=critic,
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=2,
            )

            with self.assertRaises(SharedEvaluationDataUnavailable) as context:
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )

            self.assertFalse(context.exception.retryable)
            self.assertEqual(len(context.exception.case_reasons), 1)
            self.assertEqual(critic.parent_comparisons, [])
            round_root = workspace.experiments_root / "round-0001"
            self.assertTrue((round_root / "shared-data-pause.json").is_file())
            self.assertFalse((round_root / "rejected.json").exists())
            self.assertEqual(workspace.last_completed_round, 0)

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
            cases = make_evaluation_pool()
            result = engine.run_round(
                round_id=1,
                validation_cases=cases,
                anchor_cases=make_anchor_pool(),
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
                self.assertEqual(len(record.trajectories), 24)
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(len(workspace.restore_archive().records), 2)
            self.assertEqual(meta.entries[0].evidence_refs, ("plan_child_1", "plan_child_2"))
            self.assertEqual(
                tuple(
                    item.plan_id for item in meta.entries[0].plan_reflections
                ),
                ("plan_child_1", "plan_child_2"),
            )
            for plan_reflection, record in zip(
                meta.entries[0].plan_reflections,
                result.records,
            ):
                self.assertEqual(len(plan_reflection.original_case_reflections), 24)
                self.assertEqual(
                    plan_reflection.vertical_plan_reflection,
                    record.reflection,
                )
            self.assertEqual(workspace.restore_meta().entries, meta.entries)
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
            self.assertIn("basic_info_requests", proposed["plan_summary"])
            stats = registry.load_stats("revenue_growth_yoy")
            self.assertEqual(stats.retrieved, 48)
            self.assertEqual(stats.executed, 48)
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
            self.assertEqual(reconciled.retrieved, 48)
            self.assertEqual(reconciled.executed, 48)

    def test_round_meta_cannot_cite_old_or_unrelated_experiment(self) -> None:
        class BadReflector(SimpleRoundReflector):
            def reflect(
                self,
                *,
                round_id,
                records,
                prior,
                parent_comparisons_by_plan_id=None,
            ):
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
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 0)


class SignalEvolutionTests(TestCase):
    def test_mining_ranks_identity_and_label_hidden_briefs_then_overlays_labels(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            positive = replace(
                make_case("workflow_positive", 4.0),
                basic_info={
                    "ticker": "WINR",
                    "company_name": "Winner Corp",
                    "business_description": "Winner Corp builds optical systems.",
                    "industry": "Hardware",
                },
            )
            control = replace(
                make_case("workflow_control", 1.1),
                basic_info={
                    "ticker": "CTRL",
                    "company_name": "Control Corp",
                    "business_description": "Control Corp builds optical systems.",
                    "industry": "Hardware",
                },
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="order_confirmation",
                statement="Material order confirmation precedes repricing.",
                applicability="Project-driven hardware companies.",
                expected_positive_pattern="Positive cases disclose confirmed orders.",
                source_types=("news",),
                query="material order",
                falsifiers=("Controls disclose the same pattern.",),
            )
            second_hypothesis = replace(
                hypothesis,
                hypothesis_id="commercialization_confirmation",
            )
            deferred_hypothesis = replace(
                hypothesis,
                hypothesis_id="guidance_confirmation",
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(
                    hypothesis,
                    second_hypothesis,
                    deferred_hypothesis,
                ),
                rankings={
                    item.hypothesis_id: ("case-001", "case-002")
                    for item in (
                        hypothesis,
                        second_hypothesis,
                        deferred_hypothesis,
                    )
                },
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="order_confirmation",
                        disposition="refine",
                        rationale=("Two cases are not enough to draft a Signal.",),
                    ),
                ),
            )
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"workflow_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=f"{case.basic_info['company_name']} reported a material order.",
                    )
                    for index, case in enumerate((positive, control))
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_agent=GenericAgent(
                    ScriptedAgentModel(
                        [AgentTurn(final_output={"candidate_refs": []})]
                    )
                ),
                llm_signal_runner=None,
            )
            result = engine._run_signal_mining(cycle_id=1)

            ranking_payload = mining_model.requests[1]
            ranking_json = json.dumps(ranking_payload)
            self.assertNotIn("Winner Corp", ranking_json)
            self.assertNotIn("Control Corp", ranking_json)
            self.assertNotIn("WINR", ranking_json)
            self.assertNotIn("CTRL", ranking_json)
            self.assertNotIn("ground_truth", ranking_json)
            self.assertNotIn('"label"', ranking_json)
            contrast_cases = mining_model.requests[2]["comparisons"][0]["cases"]
            self.assertEqual(
                {item["label"] for item in contrast_cases},
                {"positive", "control"},
            )
            self.assertNotIn("Winner Corp", json.dumps(contrast_cases))
            self.assertEqual(result["candidate_refs"], ())
            self.assertIn("order_confirmation", result["refined_hypotheses"])
            self.assertEqual(
                result["refined_hypotheses"]["guidance_confirmation"],
                (
                    "deferred because the per-cycle evidence contrast budget was reached",
                ),
            )

    def test_signal_agent_completion_matches_test_order_to_each_returned_ref(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_agent=GenericAgent(
                    ScriptedAgentModel(
                        [AgentTurn(final_output={"candidate_refs": []})]
                    )
                ),
                llm_signal_runner=None,
            )
            signal_ref = "revenue_growth_yoy:v2"
            observations = (
                ToolObservation("load_signal_spec", {}, {}),
                ToolObservation("query_signal_usage", {}, {}),
                ToolObservation("query_signal_failure_cases", {}, {}),
                ToolObservation("sample_discovery_cases", {}, []),
                ToolObservation("search_raw_info", {}, {}),
                ToolObservation(
                    "run_signal_tests",
                    {},
                    {"signal_ref": signal_ref, "accepted": True},
                ),
                ToolObservation("clone_signal_version", {}, signal_ref),
                ToolObservation(
                    "run_signal_tests",
                    {},
                    {"signal_ref": "other_signal:v2", "accepted": True},
                ),
            )

            with self.assertRaisesRegex(
                ValidationError, "after staging that exact ref"
            ):
                engine._validate_agent_completion(
                    "update", (signal_ref,), observations
                )

    def test_mining_tool_rejects_existing_stable_signal_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_agent=GenericAgent(
                    ScriptedAgentModel(
                        [AgentTurn(final_output={"candidate_refs": []})]
                    )
                ),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
            )

            with self.assertRaisesRegex(
                ValidationError, "duplicates stable Signal identity"
            ):
                engine._stage_from_tool(
                    spec=registry.load_spec("price_momentum_126d:v1").to_dict(),
                    skill=None,
                    tests=(candidate_growth_fixture(),),
                    origin="mining",
                    collected=[],
                )

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

            common_word_validator = SignalCandidateValidator(
                registry,
                llm_runner=None,
                forbidden_identity_terms=("FOR",),
            )
            prose_candidate = SignalSpec(
                signal_id="catalyst_handling_quality",
                version=1,
                category="catalysts",
                description="Check handling for positive catalyst evidence.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertTrue(
                common_word_validator.validate(
                    prose_candidate,
                    skill=None,
                    tests=(candidate_growth_fixture(),),
                ).accepted
            )

    def test_paired_effectiveness_rejects_an_identical_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"paired_positive_{index}", 4.0)
                for index in range(4)
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"paired_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            current = registry.latest_spec("revenue_growth_yoy")
            candidate = SignalSpec(
                **{
                    **current.__dict__,
                    "version": current.version + 1,
                    "description": "Equivalent revenue-growth wording.",
                }
            )

            result = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=cases,
                llm_runner=None,
            ).evaluate(candidate, skill=None)

            self.assertFalse(result.accepted)
            self.assertIn(
                "no strict paired effectiveness gain",
                " ".join(result.reasons),
            )

    def test_effectiveness_excludes_induction_and_marks_sparse_support_provisional(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            induction = (
                make_case("induction_positive", 4.0),
                make_case("induction_control", 1.1),
            )
            validation = (
                make_case("validation_positive", 4.0),
                make_case("validation_control", 1.1),
            )
            cases = (*induction, *validation)
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"independent_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                125.0 if case.ground_truth.is_surge else 90.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            candidate = SignalSpec(
                signal_id="independent_growth_direction",
                version=1,
                category="financial",
                description="Classify comparable revenue growth direction.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            evaluator = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=cases,
                llm_runner=None,
                case_limit=2,
                minimum_cases=2,
            )

            accepted = evaluator.evaluate(
                candidate,
                skill=None,
                preferred_case_ids=tuple(case.case_id for case in validation),
                excluded_case_ids=tuple(case.case_id for case in induction),
                induction_supported=True,
            )
            provisional = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=induction,
                llm_runner=None,
                case_limit=2,
                minimum_cases=2,
            ).evaluate(
                candidate,
                skill=None,
                excluded_case_ids=tuple(case.case_id for case in induction),
                induction_supported=True,
            )

            self.assertTrue(accepted.accepted)
            self.assertEqual(accepted.disposition, "promoted")
            self.assertEqual(set(accepted.case_ids), {case.case_id for case in validation})
            self.assertEqual(provisional.disposition, "provisional")
            self.assertFalse(provisional.accepted)

    def test_slow_loop_validates_and_auto_promotes_exact_batch_idempotently(self) -> None:
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
                parameters={"positive_min": 0.10, "negative_max": 0.0},
            )
            updated_spec = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Measure point-in-time revenue growth with explicit comparable-period checks.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
                parameters={"positive_min": 0.10, "negative_max": 0.0},
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="broad_growth",
                statement="Point-in-time revenue acceleration separates winners.",
                applicability="Companies with comparable financial periods.",
                expected_positive_pattern="Positive cases show stronger growth.",
                source_types=("financials",),
                query="revenue",
                falsifiers=("Controls show the same growth.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                rankings={
                    "broad_growth": tuple(
                        f"case-{index:03d}" for index in range(1, 9)
                    )
                },
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
            discovery_cases = tuple(
                [
                    make_case(f"discovery_positive_{index}", 4.0)
                    for index in range(4)
                ]
                + [
                    make_case(f"discovery_control_{index}", 1.1)
                    for index in range(4)
                ]
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
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=mining_model,
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
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
            committed = make_record(
                "plan_before_signal_promotion",
                0.8,
                (1.0, 0.0),
                round_id=1,
            )
            workspace.commit_round(
                round_id=1,
                records=(committed,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(committed.plan_id,),
                ),
                signal_registry_version=snapshot.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
            )
            original_bump_version = registry.bump_version

            def interrupt_before_version_commit():
                registry.bump_version = original_bump_version
                raise RuntimeError("simulated interruption before Registry version commit")

            registry.bump_version = interrupt_before_version_commit
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                engine.run_cycle(cycle_id=1, input_snapshot=snapshot)
            self.assertEqual(registry.version, 1)
            mining_request_count = len(mining_model.requests)
            update_request_count = len(update_model.requests)

            result = engine.run_cycle(cycle_id=1)
            self.assertEqual(
                set(result.validated_candidates),
                {"discovery_growth_quality:v1", "revenue_growth_yoy:v2"},
            )
            self.assertEqual(set(result.promoted), set(result.validated_candidates))
            self.assertEqual(
                result.agent_audits["mining_pipeline"]["track"],
                "hypothesis",
            )
            self.assertTrue(
                result.candidate_effectiveness[
                    "revenue_growth_yoy:v2"
                ]["accepted"]
            )
            self.assertEqual(result.input_registry_version, 1)
            self.assertEqual(result.output_registry_version, 2)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 2)
            self.assertFalse(
                (
                    root
                    / "signals_candidates"
                    / "financial"
                    / "discovery_growth_quality"
                    / "v1"
                    / "approval.json"
                ).exists()
            )
            promoted = engine.run_cycle(cycle_id=1)
            self.assertEqual(
                set(promoted.promoted),
                {"discovery_growth_quality:v1", "revenue_growth_yoy:v2"},
            )
            self.assertEqual(promoted.registry_version, 2)
            self.assertEqual(len(mining_model.requests), mining_request_count)
            self.assertEqual(len(update_model.requests), update_request_count)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 2)
            self.assertEqual(registry.latest_spec("discovery_growth_quality").version, 1)
            self.assertTrue(
                (root / "signals_candidates" / "financial" / "revenue_growth_yoy" / "v2").exists()
            )

    def test_mining_controller_rejects_malformed_candidate_spec_locally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            invalid_spec = registry.load_spec("guidance_acceleration:v1").to_dict()
            invalid_spec["execution"].pop("type")
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="guidance_change",
                statement="Explicit guidance changes separate winners.",
                applicability="Companies issuing guidance.",
                expected_positive_pattern="Positive cases raise guidance.",
                source_types=("news",),
                query="guidance",
                falsifiers=("Controls raise guidance equally often.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                rankings={"guidance_change": ("case-001", "case-002")},
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="guidance_change",
                        disposition="supported",
                        rationale=("The small sample separates.",),
                        candidate={
                            "spec": invalid_spec,
                            "skill": None,
                            "tests": [],
                        },
                    ),
                ),
            )
            update_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            positive = make_case("discovery_positive", 4.0)
            control = make_case("discovery_control", 1.1)
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"guidance_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Management changed guidance.",
                    )
                    for index, case in enumerate((positive, control))
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
            )

            result = engine._validate_cycle(registry.freeze())

            self.assertEqual(result.validated_candidates, {})
            self.assertIn(
                "candidate SignalSpec JSON is invalid",
                str(result.rejected["slow_loop:mining_stage:guidance_change"]),
            )

    def test_exploration_freezes_label_hidden_signatures_before_reveal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"explore_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"explore_control_{index}", 1.1) for index in range(4)]
            )
            induction_refs = ("case-001", "case-002", "case-005", "case-006")
            mining_model = ScriptedMiningModel(
                signatures=tuple(
                    SignalMiningSignature(
                        case_ref=case_ref,
                        observations=("A bounded observable event is present.",),
                    )
                    for case_ref in induction_refs
                ),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_pattern",
                        disposition="refine",
                        rationale=("The extracted pattern needs more cases.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"exploration_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="A bounded observable event was reported.",
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_agent=GenericAgent(
                    ScriptedAgentModel(
                        [AgentTurn(final_output={"candidate_refs": []})]
                    )
                ),
                llm_signal_runner=None,
            )

            result = engine._run_signal_mining(cycle_id=3)

            e1_payload, e2_payload = mining_model.requests
            self.assertNotIn('"label"', json.dumps(e1_payload))
            self.assertEqual(
                {item["label"] for item in e2_payload["signatures"]},
                {"positive", "control"},
            )
            self.assertEqual(
                result["refined_hypotheses"]["exploration_pattern"],
                ("The extracted pattern needs more cases.",),
            )

    def test_signal_failure_query_uses_executed_refs_not_free_form_prose(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            signal_result = SignalResult(
                signal_id="revenue_growth_yoy",
                version=1,
                value=SignalValue.POSITIVE,
                confidence=1.0,
                interpretation="fixture",
            )
            trajectory = make_trajectory(
                "failure_case",
                4.0,
                False,
                None,
                signal_result=signal_result,
            )
            record = replace(
                make_record("failure_plan", 0.0, (1.0, 0.0)),
                trajectories=(trajectory,),
                metrics=score_predictions((trajectory,)),
                evaluation=None,
                fitness=None,
            )
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(record.plan_id,),
                ),
                signal_registry_version=snapshot.version,
                signal_registry_hash=snapshot.registry_hash,
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_agent=GenericAgent(
                    ScriptedAgentModel(
                        [AgentTurn(final_output={"candidate_refs": []})]
                    )
                ),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
            )

            failures = engine._query_signal_failure_cases(
                "revenue_growth_yoy:v1"
            )

            self.assertEqual(len(failures), 1)
            self.assertEqual(
                failures[0]["matched_signal_refs"],
                ["revenue_growth_yoy:v1"],
            )
            self.assertEqual(
                failures[0]["match_reason"],
                "incorrect_prediction_with_signal_used",
            )

    def test_slow_loop_agents_cannot_access_locked_test(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            mining_model = EmptyMiningModel()
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
                        content="start " + ("evidence " * 2_000) + "end",
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
                mining_model=mining_model,
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
            )
            engine._validate_cycle(registry.freeze())
            mining_workspace = mining_model.requests[0]
            update_workspace = update_model.requests[0].workspace
            for workspace_view in (mining_workspace, update_workspace):
                serialized = json.dumps(workspace_view)
                self.assertNotIn("locked_company", serialized)
                self.assertFalse(workspace_view["locked_test_available"])
                self.assertIn("capability_backlog", workspace_view)
            search_view = engine._search_raw_info_tool(
                make_case("discovery_only", 3.0).case_id,
                NOW.isoformat(),
                source_types=["news"],
            )["documents"][0]
            self.assertNotIn("content", search_view)
            self.assertTrue(search_view["content_truncated"])
            self.assertLess(len(search_view["content_excerpt"]), 1_300)
            loaded_view = engine._load_discovery_raw_document(
                make_case("discovery_only", 3.0).case_id,
                "discovery_doc",
            )
            self.assertLess(len(loaded_view["content_excerpt"]), 6_100)
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
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
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
            mining_model = EmptyMiningModel()
            update_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=mining_model,
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )
            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=1)
            self.assertEqual(len(result.plan_rounds), 1)
            self.assertEqual(result.signal_evolution.promoted, ())
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(len(evaluator.seen_company_ids), 24)
            self.assertEqual(len(set(evaluator.seen_company_ids)), 24)
            self.assertNotIn("locked_company", json.dumps(mining_model.requests[0]))

    def test_next_cycle_uses_promoted_registry_without_reevaluating_old_plans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            initial = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=initial.version,
                initial_signal_registry_hash=initial.registry_hash,
                observed_signal_registry_version=initial.version,
                observed_signal_registry_hash=initial.registry_hash,
            )
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
                run_contract_hash="contract-hash",
            )
            new_spec = SignalSpec(
                signal_id="cross_cycle_growth_quality",
                version=1,
                category="financial",
                description="Measure whether revenue growth spans disclosed segments.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            discovery_cases = tuple(
                [
                    make_case(f"discovery_positive_{index}", 4.0)
                    for index in range(4)
                ]
                + [
                    make_case(f"discovery_control_{index}", 1.1)
                    for index in range(4)
                ]
            )
            signal_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"cross_cycle_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                125.0 if case.ground_truth.is_surge else 90.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(discovery_cases)
                )
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="cross_cycle_growth",
                statement="Revenue growth direction separates winners.",
                applicability="Companies with comparable financial periods.",
                expected_positive_pattern="Positive cases have stronger growth.",
                source_types=("financials",),
                query="revenue",
                falsifiers=("Controls have indistinguishable growth.",),
            )
            first_signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=signal_store,
                discovery_cases=discovery_cases,
                meta_memory=meta,
                workspace=workspace,
                mining_model=ScriptedMiningModel(
                    hypotheses=(hypothesis,),
                    rankings={
                        "cross_cycle_growth": tuple(
                            f"case-{index:03d}" for index in range(1, 9)
                        )
                    },
                    decisions=(
                        SignalMiningDecision(
                            hypothesis_id="cross_cycle_growth",
                            disposition="supported",
                            rationale=("Positive and control cases separate.",),
                            candidate={
                                "spec": new_spec.to_dict(),
                                "skill": None,
                                "tests": [candidate_growth_fixture()],
                            },
                        ),
                    ),
                ),
                update_agent=GenericAgent(
                    ScriptedAgentModel(
                        [AgentTurn(final_output={"candidate_refs": []})]
                    )
                ),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
            )
            dataset = EvolutionDataset(
                discovery=discovery_cases,
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )
            first = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=first_signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=1)
            self.assertEqual(first.signal_evolution.promoted, (new_spec.ref,))
            workspace.stage_slow_result(
                cycle_id=1,
                result=first.signal_evolution.to_dict(),
            )
            promoted_snapshot = registry.freeze()
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=promoted_snapshot.version,
                observed_signal_registry_hash=promoted_snapshot.registry_hash,
            )
            old_record = plan_engine.archive.records[0]
            old_f1 = old_record.metrics.binary_f1

            second_cycle = workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=initial.version,
                initial_signal_registry_hash=initial.registry_hash,
                observed_signal_registry_version=promoted_snapshot.version,
                observed_signal_registry_hash=promoted_snapshot.registry_hash,
            )
            second_signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_agent=GenericAgent(
                    ScriptedAgentModel(
                        [AgentTurn(final_output={"candidate_refs": []})]
                    )
                ),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
            )
            second = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=second_signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=int(second_cycle["cycle_id"]))

            self.assertNotIn(new_spec.ref, evaluator.seen_registry_refs[0])
            self.assertIn(new_spec.ref, evaluator.seen_registry_refs[1])
            self.assertEqual(len(evaluator.seen_registry_refs), 2)
            self.assertEqual(len(evaluator.seen_company_ids), 48)
            self.assertEqual(len(plan_engine.archive.records), 2)
            self.assertEqual(old_record.metrics.binary_f1, old_f1)
            self.assertIn(old_record.plan_id, proposer.calls[1]["parents"])
            round_one_checkpoint = json.loads(
                (
                    workspace.experiments_root
                    / "round-0001"
                    / "checkpoint.json"
                ).read_text(encoding="utf-8")
            )
            round_two_checkpoint = json.loads(
                (
                    workspace.experiments_root
                    / "round-0002"
                    / "checkpoint.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(round_one_checkpoint["signal_registry_version"], 1)
            self.assertEqual(round_two_checkpoint["signal_registry_version"], 2)
            self.assertEqual(second.signal_evolution.output_registry_version, 2)

    def test_dual_loop_resume_runs_only_remaining_fast_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=2,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
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
                signal_registry_version=registry.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
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
            mining_model = EmptyMiningModel()
            update_model = ScriptedAgentModel(
                [AgentTurn(final_output={"candidate_refs": []})]
            )
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=mining_model,
                update_agent=GenericAgent(update_model),
                llm_signal_runner=None,
                enforce_agent_workflow=False,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )

            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=2,
            ).run_cycle(cycle_id=1, completed_plan_rounds=1)

            self.assertEqual([item.round_id for item in result.plan_rounds], [2])
            self.assertEqual(workspace.last_completed_round, 2)
            self.assertEqual(len(proposer.calls), 1)
            self.assertEqual(len(result.plan_rounds[0].records), 1)
            self.assertFalse(
                (workspace.evaluation_root / "round_002" / "champion.json").exists()
            )
            self.assertEqual(len(evaluator.seen_company_ids), 24)


def make_evaluation_pool() -> tuple[EvolutionCase, ...]:
    cases = []
    label_inputs = (
        ("non_surge", 32, 1.2),
        ("2_3x", 24, 2.5),
        ("3_10x", 16, 5.0),
        ("10x_plus", 8, 12.0),
    )
    for label, count, multiple in label_inputs:
        for index in range(count):
            cases.append(make_case(f"{label}_{index:02d}", multiple))
    return tuple(cases)


def make_anchor_pool() -> tuple[EvolutionCase, ...]:
    cases = []
    label_inputs = (
        ("non_surge", 7, 1.2),
        ("2_3x", 5, 2.5),
        ("3_10x", 3, 5.0),
        ("10x_plus", 1, 12.0),
    )
    for label, count, multiple in label_inputs:
        for index in range(count):
            cases.append(make_case(f"anchor_{label}_{index:02d}", multiple))
    return tuple(cases)


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
                "content": sec_company_facts_content(
                    ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                    ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                ),
            }
        ],
    }


def sec_company_facts_content(
    *periods: tuple[str, str, float, str],
) -> str:
    rows = [
        {
            "accn": f"fixture-{index}",
            "end": end,
            "filed": filed,
            "form": "10-K",
            "start": start,
            "val": value,
        }
        for index, (start, end, value, filed) in enumerate(periods, start=1)
    ]
    return json.dumps(
        {
            "cik": 1,
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": rows}
                    }
                }
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def make_trajectory(
    company_id: str,
    multiple: float,
    predicted_surge: bool,
    predicted_magnitude: MagnitudeClass | None,
    *,
    signal_result: SignalResult | None = None,
    case_id: str | None = None,
    candidate_judgment: CandidateJudgment | None = None,
) -> ExecutionTrajectory:
    truth = GroundTruth(multiple)
    prediction = BlindPrediction(
        is_surge=predicted_surge,
        candidate_judgment=candidate_judgment
        or (
            CandidateJudgment.POSSIBLE
            if predicted_surge
            else CandidateJudgment.UNLIKELY
        ),
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
        case_id=case_id or f"case_{company_id}",
        company_id=company_id,
        prediction_time=NOW,
        basic_info={
            "requests": [
                {
                    "status": "resolved",
                    "context_spans": [{"exact_text": "fixture source text"}],
                }
            ]
        },
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
            true_positive=1,
            false_positive=0,
            true_negative=0,
            false_negative=0,
            sample_count=1,
        ),
        reflection=PlanReflection(),
        signal_usage={},
        trajectories=(
            make_trajectory(
                f"case_{plan_id}",
                2.5,
                True,
                MagnitudeClass.TWO_TO_THREE,
            ),
        ),
    )
