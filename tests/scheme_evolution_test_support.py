from __future__ import annotations

import hashlib
import json
import random
import re
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from unittest import TestCase, mock

from stock_opportunity_agent.data.raw_info import (
    RawInfoDocument,
    RawInfoStore,
    content_sha256,
)
from stock_opportunity_agent.data.acquisition import UnavailableProviderAdapter
from stock_opportunity_agent.data.resolution import (
    DataAcquisitionPolicy,
    EvidenceResolver,
    RawInfoRequest,
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
    BasicInfoPolicy,
    BlindPrediction,
    CaseReflectionEvidence,
    CandidateJudgment,
    CandidateProposalRejected,
    CandidateExecutionRejected,
    ConfidenceLevel,
    DualLoopEvolutionEngine,
    EvaluationCaseReadiness,
    EvaluationDatasetManager,
    EvaluationDatasetInfeasible,
    EvolutionCase,
    EvolutionDataset,
    EvolutionWorkspace,
    ExecutionTrajectory,
    FitnessEligibility,
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
    ResearchEvidenceRef,
    ResearchState,
    RoundMetaEntry,
    RuntimeBudgetExceeded,
    RuntimeLimits,
    RuntimePlanEvaluator,
    RuntimeStopReason,
    RuntimeUsage,
    RoundPaused,
    SharedEvaluationDataUnavailable,
    SlowLoopDataUnavailable,
    SignalCandidateEffectivenessEvaluator,
    SignalCandidateValidator,
    SignalEvolutionEngine,
    SignalMiningDecision,
    SignalMiningHypothesis,
    SignalMiningConfig,
    SignalMiningObservation,
    SignalMiningSignature,
    SignalRound,
    SignalSelectionDecision,
    SignalUpdateDecision,
    candidate_judgment_feedback,
    build_parent_plan_comparison,
    default_information_plan,
    execute_information_plan,
    score_predictions,
    MAX_PREDICTOR_CONTEXT_UTF8_BYTES,
    _assemble_final_context,
    _agent_raw_document_view,
    _exploration_case_pairs,
    _h3_text_query_coverage,
    _item1_business_excerpt,
    _mask_identity_values,
    _slow_role_identity_guard_inventory,
    _select_h3_model_evidence,
    validate_signal_mining_signatures,
)
from stock_opportunity_agent.research.evolution_runtime import ExternalRequestPending
from stock_opportunity_agent.signal_library import (
    SignalBatchResult,
    SignalCoverage,
    SignalEvidence,
    SignalExecutionStatus,
    SignalExecutionType,
    SignalExecutor,
    SignalLearningEvent,
    SignalRetrievalPolicy,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
    signal_execution_failure_result,
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
        requested = {
            str(item["case_ref"])
            for item in payload.get("cases", ())
            if isinstance(item, Mapping) and item.get("case_ref")
        }
        return AgentStep(
            tuple(item for item in self.signatures if item.case_ref in requested),
            AgentUsage(llm_calls=1),
        )

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


class OneSignalSelector:
    def select(
        self,
        information_needs,
        signal_registry,
        prior_signal_fingerprints=None,
        prior_signal_results=None,
        eligible_signal_refs=None,
        research_state=None,
        prior_context_tags=(),
    ):
        self.needs = tuple(information_needs)
        return AgentStep(
            (
                SignalSelectionDecision(
                    signal_ref="revenue_growth_yoy:v1",
                    reason_code="answer_need",
                    selection_reason="Measure the requested revenue growth.",
                    applicability_hypothesis="Comparable annual financial periods exist.",
                    expected_role="primary",
                    context_tags=("comparable_financials",),
                ),
            ),
            AgentUsage(llm_calls=1, tokens=10, cost=0.005),
        )


class NoChangeUpdateModel:
    def __init__(self) -> None:
        self.requests: list[Mapping[str, Any]] = []

    def update(self, payload):
        self.requests.append(payload)
        return AgentStep(
            SignalUpdateDecision(
                signal_ref=str(payload["target"]["signal_ref"]),
                disposition="no_change",
                problem_type="routing_applicability",
                rationale=("The induction evidence does not isolate a defect.",),
            ),
            AgentUsage(llm_calls=1),
        )


class ScriptedUpdateModel:
    def __init__(self, decision: SignalUpdateDecision) -> None:
        self.decision = decision
        self.requests: list[Mapping[str, Any]] = []

    def update(self, payload):
        self.requests.append(payload)
        return AgentStep(self.decision, AgentUsage(llm_calls=1))


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
    def __init__(
        self,
        *,
        include_signal: bool = True,
        signal_selection: SignalSelectionDecision | None = None,
    ) -> None:
        self.include_signal = include_signal
        self.signal_selection = signal_selection
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
                    signal_selection=self.signal_selection,
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


def fixture_mining_config(case_count: int) -> SignalMiningConfig:
    """Use production logic with fixture-sized H2 readiness thresholds."""

    per_class = max(1, case_count // 2)
    return SignalMiningConfig(
        case_pool_limit=case_count,
        h2_profile_scan_limit=case_count,
        h2_min_ready_issuers=case_count,
        h2_min_ready_per_class=per_class,
        induction_cases_per_class=min(2, per_class),
        validation_cases_per_class=min(2, max(1, per_class - 1)),
        exploration_microbatch_size=max(1, case_count),
    )


def exploration_selection(
    cases: tuple[EvolutionCase, ...],
    *,
    cycle_id: int,
    induction_per_class: int,
    validation_per_class: int,
) -> dict[str, Any]:
    """Mirror local label-aware sampling while keeping presentation globally ordered."""

    case_pairs = _exploration_case_pairs(cases, cycle_id=cycle_id)
    refs_by_class = {
        label: tuple(
            case_ref
            for case_ref, case in case_pairs
            if case.ground_truth.is_surge == label
        )
        for label in (True, False)
    }
    e1_by_class: dict[bool, tuple[str, ...]] = {}
    validation_by_class: dict[bool, tuple[str, ...]] = {}
    for label, refs in refs_by_class.items():
        candidate_count = min(
            2 * induction_per_class,
            len(refs) - validation_per_class,
        )
        e1_by_class[label] = refs[:candidate_count]
        validation_by_class[label] = refs[
            candidate_count : candidate_count + validation_per_class
        ]
    all_refs = tuple(case_ref for case_ref, _case in case_pairs)
    e1_set = {*e1_by_class[True], *e1_by_class[False]}
    validation_set = {
        *validation_by_class[True],
        *validation_by_class[False],
    }
    return {
        "all_refs": all_refs,
        "e1_by_class": e1_by_class,
        "e1_refs": tuple(ref for ref in all_refs if ref in e1_set),
        "validation_refs": tuple(ref for ref in all_refs if ref in validation_set),
    }


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
    signal_selection: SignalSelectionDecision | None = None,
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
                selections=(
                    signal_selection
                    or SignalSelectionDecision(
                        signal_ref=signal_result.ref,
                        reason_code="answer_need",
                        selection_reason="Exercise the fixture Signal.",
                        applicability_hypothesis="The fixture supplies compatible inputs.",
                        expected_role="primary",
                        context_tags=("general",),
                    ),
                ),
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


__all__ = [name for name in globals() if not name.startswith("__")]
