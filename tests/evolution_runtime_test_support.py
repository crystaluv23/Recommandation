from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
from unittest import TestCase, mock

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm import RegisteredModel, get_model
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    DataAcquisitionPolicy,
    EvidenceResolver,
    RawInfoRequest,
)
from stock_opportunity_agent.models import (
    StructuredValidationError,
    ValidationError,
    ValidationIssue,
)
from stock_opportunity_agent.research import evolution_runtime as evolution_runtime_module
from stock_opportunity_agent.research.evolution_runtime import (
    DecisionTokenScores,
    EvolutionRunContract,
    ExactResponseCache,
    ExternalAttemptLedger,
    ExternalBudgetExhausted,
    ExternalExecutionNotReady,
    ExternalRequestPending,
    HistoricalPlanSeedPool,
    LLMBlindPredictor,
    LLMInformationPlanProposer,
    LLMSignalMiningModel,
    LLMPlanCritic,
    LLMRoundReflector,
    LLMResearchController,
    LLMSignalRetrievalAgent,
    LLMSignalUpdateModel,
    StructuredLLMSignalRunner,
    StructuredOutputInvalid,
    StructuredRoleClient,
    approve_dataset_proposal,
    filter_case_price_history,
    inventory_local_evolution_inputs,
    build_historical_plan_seed_pool,
    load_approved_development_dataset,
    load_or_create_historical_plan_seed_pool,
    migrate_legacy_raw_info,
    prepare_dataset_proposal,
    prepare_expanded_dataset_proposal,
)
from stock_opportunity_agent.research.scheme_evolution import (
    BlindPrediction,
    CaseReflectionEvidence,
    CandidateExecutionRejected,
    CandidateProposalRejected,
    CandidateJudgment,
    ConfidenceLevel,
    EvaluationDatasetInfeasible,
    EvaluationDatasetManager,
    EvolutionWorkspace,
    ExecutionTrajectory,
    FitnessEligibility,
    GroundTruth,
    InformationPlan,
    MagnitudeClass,
    PlanMetaReflection,
    PlanMetrics,
    PlanEvaluationConfig,
    PlanRecord,
    PlanReflection,
    PredictionSelfReflection,
    ResearchDecision,
    ResearchEvidenceRef,
    ResearchState,
    RoundMetaEntry,
    RuntimeStopReason,
    RuntimeBudgetExceeded,
    RuntimeUsage,
    SignalRound,
    SignalSelectionDecision,
    _normalized_projection_text,
    project_basic_info_bundle,
    candidate_judgment_feedback,
    default_information_plan,
)
from stock_opportunity_agent.signal_library import (
    LLMSignalBatchInput,
    SignalBatchResult,
    SignalCoverage,
    SignalEvidence,
    SignalExecutor,
    SignalExecutionStatus,
    SignalExecutionType,
    SignalModality,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def signal_selection(signal_ref: str) -> dict[str, Any]:
    return {
        "selections": [
            {
                "signal_ref": signal_ref,
                "reason_code": "answer_need",
                "selection_reason": "Answer the current information need.",
                "applicability_hypothesis": "The supplied evidence is applicable.",
                "expected_role": "primary",
                "context_tags": ["general"],
                "target_need_indices": [0],
                "answer_scope": "full",
                "residual_need": None,
            }
        ]
    }


def validation_error(call: Mapping[str, Any]) -> str:
    """Read validation feedback from stable-prefix and legacy role requests."""

    payload = call["payload"]
    feedback = payload.get("validation_feedback")
    if isinstance(feedback, Mapping):
        return str(feedback["validation_error"])
    return str(payload["validation_error"])


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _label_bars(
    multiple: float,
    *,
    volume: int = 100_000,
    complete_horizon: bool = True,
) -> list[dict[str, object]]:
    bars = [
        {
            "as_of_date": f"2024-12-{day:02d}",
            "adjusted_close": 10.0,
            "volume": volume,
        }
        for day in range(10, 30)
    ]
    future_multiples = [
        min(multiple, 3.0),
        min(multiple, 9.0),
        multiple,
        multiple,
        multiple,
        multiple,
        multiple,
    ]
    bars.extend(
        {
            "as_of_date": f"2025-01-{day:02d}",
            "adjusted_close": 10.0 * future_multiple,
            "volume": volume,
        }
        for day, future_multiple in zip(range(10, 17), future_multiples)
    )
    if complete_horizon:
        bars.append(
            {
                "as_of_date": "2025-07-10",
                "adjusted_close": 10.0 * multiple,
                "volume": volume,
            }
        )
    return bars


def write_anchor_spec(
    path: Path, positive_cases: list[tuple[str, str]]
) -> None:
    payload = {
        "schema_version": "information-plan-anchor-spec-v1",
        "anchor_id": "fixture-anchor-v1",
        "review_basis": "fixture",
        "positive_cases": [
            {
                "symbol": symbol,
                "prediction_date": "2025-01-10",
                "expected_label": label,
                "match_control": index < 7,
                "rationale": "fixture",
            }
            for index, (symbol, label) in enumerate(positive_cases)
        ],
    }
    payload["spec_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(path, payload)


def make_contract() -> EvolutionRunContract:
    return EvolutionRunContract(
        run_id="fixture-run",
        created_at="2026-08-09T00:00:00+00:00",
        dataset_manifest_hash=SHA_A,
        raw_info_oracle_id="raw-info-fixture",
        raw_info_inventory_hash=SHA_B,
        initial_signal_registry_version=1,
        initial_signal_registry_hash=SHA_C,
        priors_hash=SHA_D,
        models={
            "judge": {
                "alias": "fixture-judge",
                "provider": "fixture",
                "model": "fixture-judge-model",
            },
            "proposer": {
                "alias": "fixture-proposer",
                "provider": "fixture",
                "model": "fixture-proposer-model",
            },
        },
        code_revision="deadbeef",
        python_runtime="3.12.0",
        limits={
            "plan_rounds_per_signal_cycle": 1,
            "candidates_per_round": 1,
            "top_k": 3,
            "random_k": 2,
            "similarity_threshold": 0.9,
            "parent_selection_seed": 42,
            "plan_proposal_temperature": 1.0,
            "judge_temperature": 0.0,
            "max_signal_rounds": 5,
            "max_signal_calls": 20,
            "max_signals_per_round": 4,
            "max_llm_signals_per_round": 2,
            "max_llm_calls": 40,
            "max_tokens": 120_000,
            "finalization_token_reserve": 36_000,
            "basic_info_context_chars": 32_000,
            "signal_batch_context_chars": 32_000,
            "predictor_context_bytes": 24_000,
            "posthoc_context_chars": 24_000,
            "meta_context_chars": 48_000,
            "role_output_tokens": {
                "controller": 8_000,
                "routing": 2_000,
                "predictor": 2_000,
                "posthoc": 2_000,
                "h1": 8_000,
                "h2": 2_000,
                "proposer": 4_000,
                "critic": 4_000,
                "signal_batch": 4_000,
                "h3": 8_000,
                "update": 8_000,
            },
            "max_case_cost": 5.0,
            "max_agent_steps": 20,
            "evaluation": PlanEvaluationConfig().to_dict(),
        },
        max_external_attempts=2,
        max_total_cost=1.0,
    )


class ScriptedRoleCaller:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = list(outputs)
        self.stages: list[str] = []
        self.calls: list[dict[str, object]] = []

    def complete_json(self, **kwargs):
        self.stages.append(str(kwargs["stage"]))
        self.calls.append(dict(kwargs))
        return self.outputs.pop(0), AgentUsage(llm_calls=1, tokens=5, cost=0.01)


__all__ = [name for name in globals() if not name.startswith("__")]
