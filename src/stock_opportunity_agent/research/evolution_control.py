"""Frozen contracts, recovery inputs, and bounded-cycle composition."""

from __future__ import annotations

import math
import os
import platform
import re
import shutil
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from stock_opportunity_agent.research.signal_tracking import imported_learning_events, record_committed_signal_use

from stock_opportunity_agent.artifacts import canonical_json_hash as _canonical_hash
from stock_opportunity_agent.research.evolution_dataset import LocalEvolutionInventory
from stock_opportunity_agent.config import load_config
from stock_opportunity_agent.data.acquisition import (
    AlphaVantageNewsAdapter,
    AlphaVantageTranscriptAdapter,
    FinnhubNewsAdapter,
    HistoricalPriceAdapter,
    HistoricalUnavailableAdapter,
    SecCompanyFactsAdapter,
    SecFilingAdapter,
    UnavailableProviderAdapter,
)
from stock_opportunity_agent.data.raw_info import RawInfoOracle, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    aggregate_capability_gaps,
    DataAcquisitionBudget,
    DataAcquisitionPolicy,
    EvidenceResolver,
    extract_unresolved_signal_needs,
)
from stock_opportunity_agent.data.sources.alpha_vantage import (
    AlphaVantageClient,
    alpha_vantage_json_error,
)
from stock_opportunity_agent.data.sources.finnhub import FinnhubClient
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import UrllibJsonTransport
from stock_opportunity_agent.data.sources.massive import MassiveClient
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.data.sources.state import (
    ManagedHttpTransport,
    RawDataCache,
    RequestLedger,
    SourceBudget,
)
from stock_opportunity_agent.data.sources.stooq import StooqClient
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.llm.openrouter_jev import (
    DEFAULT_JEV_MODEL,
    DEFAULT_JEV_URL,
    DEFAULT_OPENROUTER_API_KEY_ENV_VAR,
    OpenRouterJevClient,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import (
    DEFAULT_EVOLUTION_PRIORS,
    DualLoopEvolutionEngine,
    DualLoopResult,
    EvolutionCase,
    EvolutionWorkspace,
    EvaluationDatasetManager,
    FitnessEligibility,
    GroundTruth,
    HashingPlanEmbedder,
    InformationPlan,
    PlanMetrics,
    PlanEvaluationConfig,
    PlanEvolutionEngine,
    PlanMetaMemory,
    ParentPlanReflectionEvidence,
    ProgressCallback,
    RoundMetaEntry,
    RuntimeLimits,
    RuntimePlanEvaluator,
    SlowLoopResult,
    SignalEvolutionEngine,
    cosine_similarity,
    binary_f1_fraction,
    default_information_plan,
    _mask_identity_values,
    _signal_learning_events_from_record,
)
from stock_opportunity_agent.research.research_targets import (
    active_research_targets,
    build_target_group_manifest,
    build_target_sampling_manifest,
)
from stock_opportunity_agent.research.plan_evolution import (
    install_stop_handler,
)
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    SignalRegistry,
    SignalLearningEvent,
)
from stock_opportunity_agent.research.evolution_settings import (
    FIXED_PREDICTOR_SEMANTICS_HASH,
    HISTORICAL_PLAN_SEED_CAPACITY,
    HISTORICAL_PLAN_SEED_QUALITY_RATIO,
    HISTORICAL_PLAN_SEED_SCHEMA_VERSION,
    HISTORICAL_PLAN_SEED_SIMILARITY_THRESHOLD,
    REGISTERED_SOURCE_TYPE_CATALOG,
    REGISTERED_SOURCE_TYPE_CATALOG_HASH,
    ROLE_OUTPUT_TOKEN_LIMITS,
    _model_available_source_types,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _validate_plan_for_proposer_context,
)
from stock_opportunity_agent.research.evolution_transport import (
    ExternalAttemptLedger,
    ExternalExecutionNotReady,
    StructuredRoleClient,
    _read_json,
    _sha256_file,
    _write_or_verify_json,
    current_code_revision,
    public_model_contract,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMBlindPredictor,
    LLMInformationPlanProposer,
    LLMPlanCritic,
    LLMResearchController,
    LLMRoundReflector,
    LLMSignalRetrievalAgent,
)
from stock_opportunity_agent.research.evolution_jev_roles import (
    JevBlindPredictor,
    JevSignalRetrievalAgent,
)
from stock_opportunity_agent.research.evolution_signal_roles import (
    LLMSignalMiningModel,
    LLMSignalUpdateModel,
    StructuredLLMSignalRunner,
)


@dataclass(frozen=True)
class EvolutionRunContract:
    """Secret-free immutable identity for one bounded evolution run."""

    run_id: str
    created_at: str
    dataset_manifest_hash: str
    raw_info_oracle_id: str
    raw_info_inventory_hash: str
    initial_signal_registry_version: int
    initial_signal_registry_hash: str
    priors_hash: str
    models: Mapping[str, Mapping[str, Any]]
    code_revision: str
    python_runtime: str
    limits: Mapping[str, Any]
    max_external_attempts: int
    max_total_cost: float
    predictor_semantics_hash: str = FIXED_PREDICTOR_SEMANTICS_HASH
    source_type_catalog_hash: str = REGISTERED_SOURCE_TYPE_CATALOG_HASH
    seed_pool_manifest_hash: str | None = None
    cycle_mode: str = "fast_then_slow"
    slow_bootstrap_manifest_hash: str | None = None
    slow_history_manifest_hash: str | None = None
    max_slow_cycles: int = 1
    min_new_signals_per_cycle: int = 1
    locked_test_accessed: bool = False
    parallel_jev_decisions: bool = False
    data_acquisition: DataAcquisitionPolicy = DataAcquisitionPolicy()
    schema_version: str = "evolution-run-contract-v8"

    def __post_init__(self) -> None:
        reasoning_reserve = self.limits.get("structured_reasoning_token_reserve", 0)
        if (
            isinstance(reasoning_reserve, bool)
            or not isinstance(reasoning_reserve, int)
            or reasoning_reserve < 0
        ):
            raise ValidationError("structured reasoning token reserve must be a nonnegative integer")
        if not self.run_id.strip():
            raise ValidationError("evolution run_id is required")
        for name in (
            "dataset_manifest_hash",
            "raw_info_inventory_hash",
            "initial_signal_registry_hash",
            "priors_hash",
        ):
            value = str(getattr(self, name))
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValidationError(f"{name} must be a SHA-256 hex digest")
        if self.seed_pool_manifest_hash is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.seed_pool_manifest_hash
        ):
            raise ValidationError(
                "seed_pool_manifest_hash must be a SHA-256 hex digest"
            )
        if self.slow_bootstrap_manifest_hash is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.slow_bootstrap_manifest_hash
        ):
            raise ValidationError(
                "slow_bootstrap_manifest_hash must be a SHA-256 hex digest"
            )
        if self.slow_history_manifest_hash is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.slow_history_manifest_hash
        ):
            raise ValidationError(
                "slow_history_manifest_hash must be a SHA-256 hex digest"
            )
        if self.max_slow_cycles < 1 or self.min_new_signals_per_cycle < 1:
            raise ValidationError("Slow cycle and new-Signal limits must be positive")
        if self.initial_signal_registry_version < 1:
            raise ValidationError("initial signal registry version must be positive")
        if not self.raw_info_oracle_id.strip():
            raise ValidationError("raw_info_oracle_id is required")
        if (
            type(self.max_external_attempts) is not int
            or self.max_external_attempts < 1
            or isinstance(self.max_total_cost, bool)
            or not isinstance(self.max_total_cost, (int, float))
            or not math.isfinite(self.max_total_cost)
            or self.max_total_cost <= 0
        ):
            raise ValidationError("external attempt and cost ceilings must be positive")
        if self.locked_test_accessed:
            raise ValidationError("ordinary evolution contract cannot open Locked Test")
        if self.parallel_jev_decisions and "jev" not in self.models:
            raise ValidationError(
                "parallel Jev decisions require a frozen Jev model identity"
            )
        object.__setattr__(
            self,
            "models",
            {str(role): dict(metadata) for role, metadata in self.models.items()},
        )
        object.__setattr__(self, "limits", dict(self.limits))
        if "h1_request_budget" in self.limits and int(self.limits["h1_request_budget"]) < 1:
            raise ValidationError("H1 request budget must be positive")
        if self.schema_version not in {
            "evolution-run-contract-v1",
            "evolution-run-contract-v2",
            "evolution-run-contract-v3",
            "evolution-run-contract-v4",
            "evolution-run-contract-v5",
            "evolution-run-contract-v6",
            "evolution-run-contract-v7",
            "evolution-run-contract-v8",
        }:
            raise ValidationError("unsupported evolution run contract schema")
        if self.schema_version in {
            "evolution-run-contract-v5",
            "evolution-run-contract-v6",
            "evolution-run-contract-v7",
            "evolution-run-contract-v8",
        }:
            schema_label = self.schema_version.rsplit("v", 1)[-1]
            required_roles = {"judge", "proposer"}
            missing_roles = sorted(required_roles - set(self.models))
            if missing_roles:
                raise ValidationError(
                    f"{schema_label} contract is missing model roles: "
                    + ", ".join(missing_roles)
                )
            for role in sorted(required_roles):
                metadata = self.models[role]
                for field in ("alias", "provider", "model"):
                    if not str(metadata.get(field, "")).strip():
                        raise ValidationError(
                            f"{schema_label} contract model role {role} is missing {field}"
                        )
            if not self.code_revision.strip() or not self.python_runtime.strip():
                raise ValidationError(
                    f"{schema_label} contract requires code revision and Python runtime"
                )
            required_limits = {
                "plan_rounds_per_signal_cycle",
                "candidates_per_round",
                "top_k",
                "random_k",
                "similarity_threshold",
                "parent_selection_seed",
                "plan_proposal_temperature",
                "judge_temperature",
                "max_signal_rounds",
                "max_signal_calls",
                "max_llm_calls",
                "max_tokens",
                "max_case_cost",
                "max_agent_steps",
                "evaluation",
            }
            missing_limits = sorted(required_limits - set(self.limits))
            if missing_limits:
                raise ValidationError(
                    f"{schema_label} contract is missing runtime limits: "
                    + ", ".join(missing_limits)
                )

            def require_integer(name: str, *, minimum: int | None = None) -> int:
                value = self.limits[name]
                if type(value) is not int or (
                    minimum is not None and value < minimum
                ):
                    qualifier = (
                        f"at least {minimum}" if minimum is not None else "an integer"
                    )
                    raise ValidationError(
                        f"{schema_label} contract limit {name} must be {qualifier}"
                    )
                return value

            def require_number(name: str) -> float:
                value = self.limits[name]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise ValidationError(
                        f"{schema_label} contract limit {name} must be finite numeric"
                    )
                return float(value)

            max_parallel_plans = self.limits.get("max_parallel_plans", 1)
            if (
                type(max_parallel_plans) is not int
                or max_parallel_plans < 1
                or max_parallel_plans > require_integer(
                    "candidates_per_round", minimum=1
                )
            ):
                raise ValidationError(
                    f"{schema_label} contract limit max_parallel_plans must be "
                    "an integer from 1 through candidates_per_round"
                )

            for name in (
                "candidates_per_round",
                "top_k",
                "max_signal_rounds",
                "max_signal_calls",
                "max_llm_calls",
                "max_tokens",
                "max_agent_steps",
            ):
                require_integer(name, minimum=1)
            plan_rounds = require_integer(
                "plan_rounds_per_signal_cycle", minimum=0
            )
            if self.schema_version in {
                "evolution-run-contract-v7",
                "evolution-run-contract-v8",
            }:
                allowed_modes = {"fast_then_slow", "slow_bootstrap"}
                if self.schema_version == "evolution-run-contract-v8":
                    allowed_modes.add("slow_only")
                if self.cycle_mode not in allowed_modes:
                    raise ValidationError(
                        f"{schema_label} contract cycle_mode is invalid"
                    )
                if self.cycle_mode == "fast_then_slow":
                    if (
                        plan_rounds < 1
                        or self.slow_bootstrap_manifest_hash is not None
                    ):
                        raise ValidationError(
                            f"{schema_label} fast_then_slow requires positive Fast rounds and no Slow bootstrap manifest"
                        )
                elif self.cycle_mode == "slow_bootstrap" and (
                    plan_rounds != 0
                    or self.slow_bootstrap_manifest_hash is None
                    or self.slow_history_manifest_hash is not None
                ):
                    raise ValidationError(
                        f"{schema_label} slow_bootstrap requires zero Fast rounds and a bootstrap manifest"
                    )
                elif self.cycle_mode == "slow_only" and (
                    plan_rounds != 0
                    or self.slow_history_manifest_hash is None
                    or self.slow_bootstrap_manifest_hash is not None
                ):
                    raise ValidationError(
                        "v8 slow_only requires zero Fast rounds and one history manifest"
                    )
            elif plan_rounds < 1:
                raise ValidationError(
                    f"{schema_label} contract limit plan_rounds_per_signal_cycle must be at least 1"
                )
            require_integer("random_k", minimum=0)
            require_integer("parent_selection_seed")
            similarity = require_number("similarity_threshold")
            if not -1 < similarity <= 1:
                raise ValidationError(
                    f"{schema_label} contract similarity_threshold must be in (-1, 1]"
                )
            if require_number("plan_proposal_temperature") != 1.0:
                raise ValidationError(
                    f"{schema_label} contract proposer temperature must be 1.0"
                )
            if require_number("judge_temperature") != 0.0:
                raise ValidationError(
                    f"{schema_label} contract judge temperature must be 0.0"
                )
            if require_number("max_case_cost") <= 0:
                raise ValidationError(
                    f"{schema_label} contract max_case_cost must be positive"
                )
            structured_corrections = self.limits.get(
                "max_structured_corrections", 1
            )
            if (
                type(structured_corrections) is not int
                or not 1 <= structured_corrections <= 2
            ):
                raise ValidationError(
                    f"{schema_label} contract max_structured_corrections must "
                    "be 1 or 2"
                )
            evaluation = self.limits["evaluation"]
            if not isinstance(evaluation, Mapping):
                raise ValidationError(
                    f"{schema_label} contract requires evaluation limits"
                )
            evaluation_config = PlanEvaluationConfig.from_dict(evaluation)
            if (
                evaluation_config.cases_per_round != 24
                or dict(evaluation_config.label_counts)
                != {"non_surge": 10, "2_3x": 7, "3_10x": 5, "10x_plus": 2}
                or dict(evaluation_config.anchor_label_counts)
                != {"non_surge": 7, "2_3x": 5, "3_10x": 3, "10x_plus": 1}
                or dict(evaluation_config.random_label_counts)
                != {"non_surge": 3, "2_3x": 2, "3_10x": 2, "10x_plus": 1}
                or evaluation_config.max_cases_per_company_per_round != 1
            ):
                raise ValidationError(
                    f"{schema_label} contract requires exact 16-Anchor plus 8-Random evaluation"
                )
            if dict(evaluation) != evaluation_config.to_dict():
                raise ValidationError(
                    f"{schema_label} contract evaluation limits must be complete and canonical"
                )
            if self.schema_version in {
                "evolution-run-contract-v6",
                "evolution-run-contract-v7",
                "evolution-run-contract-v8",
            }:
                for name, expected in (
                    ("predictor_semantics_hash", FIXED_PREDICTOR_SEMANTICS_HASH),
                    ("source_type_catalog_hash", REGISTERED_SOURCE_TYPE_CATALOG_HASH),
                ):
                    if getattr(self, name) != expected:
                        raise ValidationError(f"{schema_label} contract {name} changed")
                required_v6_limits = {
                    "max_signals_per_round": 4,
                    "max_llm_signals_per_round": 2,
                    "basic_info_context_chars": 32_000,
                    "signal_batch_context_chars": 32_000,
                    "predictor_context_bytes": 24_000,
                    "posthoc_context_chars": 24_000,
                    "meta_context_chars": 48_000,
                    "role_output_tokens": ROLE_OUTPUT_TOKEN_LIMITS,
                }
                for name, expected in required_v6_limits.items():
                    if name == "role_output_tokens":
                        actual_role_limits = self.limits.get(name)
                        if isinstance(actual_role_limits, Mapping) and set(
                            actual_role_limits
                        ) == set(ROLE_OUTPUT_TOKEN_LIMITS):
                            compatible = all(
                                actual_role_limits[role] == value
                                or (
                                    role in {"controller", "h1"}
                                    and actual_role_limits[role] == 2_000
                                )
                                for role, value in ROLE_OUTPUT_TOKEN_LIMITS.items()
                            )
                            if compatible:
                                continue
                    if self.limits.get(name) != expected:
                        raise ValidationError(
                            f"{schema_label} contract limit {name} must equal the frozen value"
                        )
                reserve = self.limits.get("finalization_token_reserve")
                supported_reserves = (
                    {36_000}
                    if self.schema_version == "evolution-run-contract-v6"
                    else {36_000, 64_000}
                )
                if reserve not in supported_reserves:
                    raise ValidationError(
                        f"{schema_label} contract finalization reserve is unsupported"
                    )
                if int(self.limits["max_tokens"]) <= int(reserve):
                    raise ValidationError(
                        f"{schema_label} max_tokens must exceed finalization reserve"
                    )

    def to_dict(self) -> dict[str, Any]:
        value = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "raw_info_inventory_hash": self.raw_info_inventory_hash,
            "priors_hash": self.priors_hash,
            "models": {role: dict(value) for role, value in self.models.items()},
            "code_revision": self.code_revision,
            "python_runtime": self.python_runtime,
            "limits": dict(self.limits),
            "max_external_attempts": self.max_external_attempts,
            "max_total_cost": self.max_total_cost,
            "locked_test_accessed": False,
        }
        if self.schema_version in {
            "evolution-run-contract-v4",
            "evolution-run-contract-v5",
            "evolution-run-contract-v6",
            "evolution-run-contract-v7",
            "evolution-run-contract-v8",
        }:
            value["initial_signal_registry_version"] = (
                self.initial_signal_registry_version
            )
            value["initial_signal_registry_hash"] = self.initial_signal_registry_hash
        else:
            value["signal_registry_version"] = self.initial_signal_registry_version
            value["signal_registry_hash"] = self.initial_signal_registry_hash
        if self.schema_version != "evolution-run-contract-v1":
            value["data_acquisition"] = self.data_acquisition.to_dict()
        if self.schema_version in {
            "evolution-run-contract-v3",
            "evolution-run-contract-v4",
            "evolution-run-contract-v5",
            "evolution-run-contract-v6",
            "evolution-run-contract-v7",
            "evolution-run-contract-v8",
        }:
            value["raw_info_oracle_id"] = self.raw_info_oracle_id
        if self.schema_version in {
            "evolution-run-contract-v6",
            "evolution-run-contract-v7",
            "evolution-run-contract-v8",
        }:
            value["predictor_semantics_hash"] = self.predictor_semantics_hash
            value["source_type_catalog_hash"] = self.source_type_catalog_hash
        if self.schema_version in {
            "evolution-run-contract-v7",
            "evolution-run-contract-v8",
        }:
            value["cycle_mode"] = self.cycle_mode
            if self.slow_bootstrap_manifest_hash is not None:
                value["slow_bootstrap_manifest_hash"] = (
                    self.slow_bootstrap_manifest_hash
                )
        if self.schema_version == "evolution-run-contract-v8":
            value["max_slow_cycles"] = self.max_slow_cycles
            value["min_new_signals_per_cycle"] = self.min_new_signals_per_cycle
            value["slow_history_manifest_hash"] = self.slow_history_manifest_hash
        if self.seed_pool_manifest_hash is not None:
            value["seed_pool_manifest_hash"] = self.seed_pool_manifest_hash
        if self.parallel_jev_decisions:
            value["parallel_jev_decisions"] = True
        return value

    @property
    def contract_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    @property
    def executable(self) -> bool:
        """Only v8 contracts may advance the current dual-loop state."""

        return self.schema_version == "evolution-run-contract-v8"

    def freeze(self, path: str | Path) -> None:
        _write_or_verify_json(
            Path(path),
            {"contract_hash": self.contract_hash, "contract": self.to_dict()},
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvolutionRunContract":
        if value.get("schema_version") == "evolution-run-contract-v8":
            required_v8 = {
                "cycle_mode",
                "slow_history_manifest_hash",
                "max_slow_cycles",
                "min_new_signals_per_cycle",
            }
            missing_v8 = sorted(required_v8 - set(value))
            if missing_v8:
                raise ValidationError(
                    "v8 contract is missing frozen Slow fields: "
                    + ", ".join(missing_v8)
                )
        return cls(
            run_id=str(value["run_id"]),
            created_at=str(value["created_at"]),
            dataset_manifest_hash=str(value["dataset_manifest_hash"]),
            raw_info_oracle_id=str(
                value.get("raw_info_oracle_id", "legacy-workspace-raw-info")
            ),
            raw_info_inventory_hash=str(value["raw_info_inventory_hash"]),
            initial_signal_registry_version=int(
                value.get(
                    "initial_signal_registry_version",
                    value.get("signal_registry_version", 0),
                )
            ),
            initial_signal_registry_hash=str(
                value.get(
                    "initial_signal_registry_hash",
                    value.get("signal_registry_hash", ""),
                )
            ),
            priors_hash=str(value["priors_hash"]),
            models={
                str(role): dict(metadata)
                for role, metadata in dict(value["models"]).items()
            },
            code_revision=str(value["code_revision"]),
            python_runtime=str(value["python_runtime"]),
            limits=dict(value["limits"]),
            max_external_attempts=int(value["max_external_attempts"]),
            max_total_cost=value["max_total_cost"],
            predictor_semantics_hash=str(
                value.get("predictor_semantics_hash", FIXED_PREDICTOR_SEMANTICS_HASH)
            ),
            source_type_catalog_hash=str(
                value.get("source_type_catalog_hash", REGISTERED_SOURCE_TYPE_CATALOG_HASH)
            ),
            seed_pool_manifest_hash=(
                str(value["seed_pool_manifest_hash"])
                if value.get("seed_pool_manifest_hash") is not None
                else None
            ),
            cycle_mode=str(value.get("cycle_mode", "fast_then_slow")),
            slow_bootstrap_manifest_hash=(
                str(value["slow_bootstrap_manifest_hash"])
                if value.get("slow_bootstrap_manifest_hash") is not None
                else None
            ),
            slow_history_manifest_hash=(
                str(value["slow_history_manifest_hash"])
                if value.get("slow_history_manifest_hash") is not None
                else None
            ),
            max_slow_cycles=int(value.get("max_slow_cycles", 1)),
            min_new_signals_per_cycle=int(
                value.get("min_new_signals_per_cycle", 1)
            ),
            locked_test_accessed=bool(value.get("locked_test_accessed", False)),
            parallel_jev_decisions=bool(
                value.get("parallel_jev_decisions", False)
            ),
            data_acquisition=DataAcquisitionPolicy.from_dict(
                dict(value.get("data_acquisition", {}))
            ),
            schema_version=str(
                value.get("schema_version", "evolution-run-contract-v1")
            ),
        )

    @classmethod
    def load_frozen(cls, path: str | Path) -> "EvolutionRunContract":
        envelope = _read_json(Path(path))
        contract = cls.from_dict(dict(envelope["contract"]))
        if envelope.get("contract_hash") != contract.contract_hash:
            raise ValidationError("frozen evolution run contract hash mismatch")
        return contract


def historical_plan_seed_selection_policy() -> dict[str, Any]:
    """Return the fixed, non-evolvable cross-workspace seed policy."""

    return {
        "capacity": HISTORICAL_PLAN_SEED_CAPACITY,
        "max_per_source_run_family": 1,
        "quality_ratio": HISTORICAL_PLAN_SEED_QUALITY_RATIO,
        "similarity_threshold": HISTORICAL_PLAN_SEED_SIMILARITY_THRESHOLD,
        "coverage_scope": "unique_random_case_ids",
        "fitness_metric": "combined_binary_f1",
    }


@dataclass(frozen=True)
class HistoricalPlanSeed:
    """One content-addressed historical Plan used only as parent input."""

    source_workspace: str
    source_run_id: str
    source_run_family_id: str
    source_contract_hash: str
    source_checkpoint_ref: str
    source_record_hash: str
    source_round_id: int
    source_plan_id: str
    plan_content_hash: str
    plan: InformationPlan
    embedding: tuple[float, ...]
    metrics_by_cohort: Mapping[str, PlanMetrics]
    random_case_ids: tuple[str, ...]
    source_dataset_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "source_workspace",
            "source_run_id",
            "source_run_family_id",
            "source_checkpoint_ref",
            "source_plan_id",
        ):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"historical Plan seed {name} is required")
        for name in (
            "source_contract_hash",
            "source_record_hash",
            "plan_content_hash",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(getattr(self, name))):
                raise ValidationError(f"historical Plan seed {name} is invalid")
        if self.source_round_id < 1:
            raise ValidationError("historical Plan seed source round must be positive")
        if self.plan.plan_id != self.source_plan_id:
            raise ValidationError(
                "historical Plan seed source Plan identity is inconsistent"
            )
        if _canonical_hash(self.plan.canonical_dict()) != self.plan_content_hash:
            raise ValidationError("historical Plan seed content hash mismatch")
        if not self.embedding or not all(math.isfinite(item) for item in self.embedding):
            raise ValidationError("historical Plan seed embedding is invalid")
        object.__setattr__(self, "embedding", tuple(float(item) for item in self.embedding))
        cohort_metrics = {
            str(name): metrics for name, metrics in self.metrics_by_cohort.items()
        }
        if set(cohort_metrics) != {"anchor", "random", "combined"}:
            raise ValidationError("historical Plan seed cohort metrics are incomplete")
        if (
            cohort_metrics["anchor"].sample_count != 16
            or cohort_metrics["random"].sample_count != 8
            or cohort_metrics["combined"].sample_count != 24
        ):
            raise ValidationError("historical Plan seed cohort sizes are invalid")
        object.__setattr__(self, "metrics_by_cohort", cohort_metrics)
        random_case_ids = tuple(str(item) for item in self.random_case_ids)
        if len(random_case_ids) != 8 or len(set(random_case_ids)) != 8:
            raise ValidationError("historical Plan seed Random case ids are invalid")
        object.__setattr__(self, "random_case_ids", random_case_ids)
        if self.source_dataset_snapshot_id is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.source_dataset_snapshot_id
        ):
            raise ValidationError(
                "historical Plan seed evaluation snapshot id is invalid"
            )

    @property
    def seed_id(self) -> str:
        return f"historical_seed_{self.plan_content_hash}"

    @property
    def binary_f1(self) -> float:
        return self.metrics_by_cohort["combined"].binary_f1

    @property
    def minimum_cohort_f1(self) -> float:
        return min(
            self.metrics_by_cohort["anchor"].binary_f1,
            self.metrics_by_cohort["random"].binary_f1,
        )

    @property
    def parent_plan(self) -> InformationPlan:
        return InformationPlan(
            plan_id=self.seed_id,
            parent_ids=(),
            basic_info_policy=self.plan.basic_info_policy,
            initial_research_skill=self.plan.initial_research_skill,
            reflection_skill=self.plan.reflection_skill,
            analysis_prompt=self.plan.analysis_prompt,
        )

    def to_dict(self) -> dict[str, Any]:
        value = {
            "seed_id": self.seed_id,
            "source_workspace": self.source_workspace,
            "source_run_id": self.source_run_id,
            "source_run_family_id": self.source_run_family_id,
            "source_contract_hash": self.source_contract_hash,
            "source_checkpoint_ref": self.source_checkpoint_ref,
            "source_record_hash": self.source_record_hash,
            "source_round_id": self.source_round_id,
            "source_plan_id": self.source_plan_id,
            "plan_content_hash": self.plan_content_hash,
            "plan": self.plan.to_dict(),
            "embedding": list(self.embedding),
            "metrics_by_cohort": {
                cohort: metrics.to_dict()
                for cohort, metrics in self.metrics_by_cohort.items()
            },
            "random_case_ids": list(self.random_case_ids),
        }
        if self.source_dataset_snapshot_id is not None:
            value["source_dataset_snapshot_id"] = self.source_dataset_snapshot_id
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HistoricalPlanSeed":
        seed = cls(
            source_workspace=str(value["source_workspace"]),
            source_run_id=str(value["source_run_id"]),
            source_run_family_id=str(value["source_run_family_id"]),
            source_contract_hash=str(value["source_contract_hash"]),
            source_checkpoint_ref=str(value["source_checkpoint_ref"]),
            source_record_hash=str(value["source_record_hash"]),
            source_round_id=int(value["source_round_id"]),
            source_plan_id=str(value["source_plan_id"]),
            plan_content_hash=str(value["plan_content_hash"]),
            plan=InformationPlan.from_dict(dict(value["plan"])),
            embedding=tuple(float(item) for item in value.get("embedding", ())),
            metrics_by_cohort={
                str(cohort): PlanMetrics.from_dict(dict(metrics))
                for cohort, metrics in dict(value["metrics_by_cohort"]).items()
            },
            random_case_ids=tuple(str(item) for item in value["random_case_ids"]),
            source_dataset_snapshot_id=(
                str(value["source_dataset_snapshot_id"])
                if value.get("source_dataset_snapshot_id") is not None
                else None
            ),
        )
        if str(value.get("seed_id", "")) != seed.seed_id:
            raise ValidationError("historical Plan seed id is invalid")
        return seed


@dataclass(frozen=True)
class HistoricalPlanSeedPool:
    """Immutable automatic warm-start snapshot for one new workspace."""

    dataset_manifest_hash: str
    evaluation_contract: Mapping[str, Any]
    predictor_semantics_hash: str = FIXED_PREDICTOR_SEMANTICS_HASH
    entries: tuple[HistoricalPlanSeed, ...] = ()
    scanned_workspace_count: int = 0
    compatible_workspace_count: int = 0
    eligible_plan_count: int = 0
    schema_version: str = HISTORICAL_PLAN_SEED_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != HISTORICAL_PLAN_SEED_SCHEMA_VERSION:
            raise ValidationError("unsupported historical Plan seed-pool schema")
        if not re.fullmatch(r"[0-9a-f]{64}", self.dataset_manifest_hash):
            raise ValidationError("historical Plan seed dataset hash is invalid")
        if self.predictor_semantics_hash != FIXED_PREDICTOR_SEMANTICS_HASH:
            raise ValidationError("historical Plan seed Predictor semantics changed")
        evaluation = PlanEvaluationConfig.from_dict(self.evaluation_contract)
        if dict(self.evaluation_contract) != evaluation.to_dict():
            raise ValidationError(
                "historical Plan seed evaluation contract is not canonical"
            )
        object.__setattr__(self, "evaluation_contract", evaluation.to_dict())
        for name in (
            "scanned_workspace_count",
            "compatible_workspace_count",
            "eligible_plan_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValidationError(f"historical Plan seed {name} is invalid")
        entries = tuple(self.entries)
        if len(entries) > HISTORICAL_PLAN_SEED_CAPACITY:
            raise ValidationError("historical Plan seed pool exceeds capacity")
        if len({entry.seed_id for entry in entries}) != len(entries):
            raise ValidationError("historical Plan seed ids are not unique")
        if len({entry.plan_content_hash for entry in entries}) != len(entries):
            raise ValidationError("historical Plan seed content is duplicated")
        if len({entry.source_run_family_id for entry in entries}) != len(entries):
            raise ValidationError("historical Plan seed run families are duplicated")
        if len(entries) == 2:
            first, second = entries
            if second.binary_f1 < (
                first.binary_f1 * HISTORICAL_PLAN_SEED_QUALITY_RATIO
            ):
                raise ValidationError("historical Plan second seed is below quality floor")
            if (
                cosine_similarity(first.embedding, second.embedding)
                >= HISTORICAL_PLAN_SEED_SIMILARITY_THRESHOLD
            ):
                raise ValidationError("historical Plan seeds are too similar")
        object.__setattr__(self, "entries", entries)

    @property
    def plans(self) -> tuple[InformationPlan, ...]:
        return tuple(entry.parent_plan for entry in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "evaluation_contract": dict(self.evaluation_contract),
            "predictor_semantics_hash": self.predictor_semantics_hash,
            "selection_policy": historical_plan_seed_selection_policy(),
            "scan_summary": {
                "scanned_workspace_count": self.scanned_workspace_count,
                "compatible_workspace_count": self.compatible_workspace_count,
                "eligible_plan_count": self.eligible_plan_count,
            },
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @property
    def manifest_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def freeze(self, path: str | Path) -> None:
        _write_or_verify_json(
            Path(path),
            {"manifest_hash": self.manifest_hash, "manifest": self.to_dict()},
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HistoricalPlanSeedPool":
        selection_policy = value.get("selection_policy")
        evaluation_contract = value.get("evaluation_contract")
        scan_summary = value.get("scan_summary")
        entries = value.get("entries")
        if not isinstance(selection_policy, Mapping) or dict(selection_policy) != (
            historical_plan_seed_selection_policy()
        ):
            raise ValidationError("historical Plan seed selection policy changed")
        if not isinstance(evaluation_contract, Mapping):
            raise ValidationError("historical Plan seed evaluation contract is invalid")
        if not isinstance(scan_summary, Mapping):
            raise ValidationError("historical Plan seed scan summary is invalid")
        if not isinstance(entries, list):
            raise ValidationError("historical Plan seed entries must be an array")
        if any(not isinstance(item, Mapping) for item in entries):
            raise ValidationError("historical Plan seed entry is invalid")
        scan = dict(scan_summary)
        return cls(
            dataset_manifest_hash=str(value["dataset_manifest_hash"]),
            evaluation_contract=dict(evaluation_contract),
            predictor_semantics_hash=str(value["predictor_semantics_hash"]),
            entries=tuple(
                HistoricalPlanSeed.from_dict(dict(item))
                for item in entries
            ),
            scanned_workspace_count=int(scan.get("scanned_workspace_count", 0)),
            compatible_workspace_count=int(
                scan.get("compatible_workspace_count", 0)
            ),
            eligible_plan_count=int(scan.get("eligible_plan_count", 0)),
            schema_version=str(value["schema_version"]),
        )

    @classmethod
    def load_frozen(cls, path: str | Path) -> "HistoricalPlanSeedPool":
        envelope = _read_json(Path(path))
        pool = cls.from_dict(dict(envelope["manifest"]))
        if envelope.get("manifest_hash") != pool.manifest_hash:
            raise ValidationError("historical Plan seed-pool hash mismatch")
        return pool


def _seed_candidate_quality_key(
    candidate: HistoricalPlanSeed,
) -> tuple[Any, ...]:
    return (
        -binary_f1_fraction(candidate.metrics_by_cohort["combined"]),
        -candidate.metrics_by_cohort["combined"].magnitude_macro_f1,
        -candidate.minimum_cohort_f1,
        -len(candidate.random_case_ids),
        candidate.source_run_family_id,
        candidate.plan_content_hash,
    )


def _serialized_binary_confusion(
    trajectories: Iterable[Mapping[str, Any]],
    case_ids: Iterable[str],
) -> tuple[int, int, int, int]:
    wanted = set(case_ids)
    rows = [item for item in trajectories if str(item.get("case_id", "")) in wanted]
    if len(rows) != len(wanted) or len({str(item["case_id"]) for item in rows}) != len(
        wanted
    ):
        raise ValidationError("historical Plan seed trajectories are incomplete")
    confusion = [0, 0, 0, 0]
    for row in rows:
        prediction = row.get("prediction")
        ground_truth = row.get("ground_truth")
        if not isinstance(prediction, Mapping) or not isinstance(
            ground_truth, Mapping
        ):
            raise ValidationError("historical Plan seed prediction rows are invalid")
        predicted = prediction.get("is_surge")
        truth = ground_truth.get("is_surge")
        if type(predicted) is not bool or type(truth) is not bool:
            raise ValidationError("historical Plan seed binary labels are invalid")
        if any(
            name in prediction
            for name in (
                "yes_token_probability",
                "no_token_probability",
                "decision_margin",
            )
        ):
            raise ValidationError(
                "superseded token-threshold predictions cannot seed current runs"
            )
        judgment = prediction.get("candidate_judgment")
        if judgment is not None:
            if judgment not in {
                "likely",
                "possible",
                "unlikely",
                "insufficient_information",
            } or predicted != (judgment in {"likely", "possible"}):
                raise ValidationError(
                    "historical Plan seed four-way prediction mapping is invalid"
                )
        if predicted and truth:
            confusion[0] += 1
        elif predicted and not truth:
            confusion[1] += 1
        elif not predicted and not truth:
            confusion[2] += 1
        else:
            confusion[3] += 1
    return confusion[0], confusion[1], confusion[2], confusion[3]


def _metrics_match_serialized_predictions(
    metrics: PlanMetrics,
    trajectories: Iterable[Mapping[str, Any]],
    case_ids: Iterable[str],
) -> bool:
    confusion = _serialized_binary_confusion(trajectories, case_ids)
    if confusion != (
        metrics.true_positive,
        metrics.false_positive,
        metrics.true_negative,
        metrics.false_negative,
    ):
        return False
    true_positive, false_positive, _true_negative, false_negative = confusion
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    binary_f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return (
        math.isclose(metrics.binary_precision, precision, abs_tol=1e-12)
        and math.isclose(metrics.binary_recall, recall, abs_tol=1e-12)
        and math.isclose(metrics.binary_f1, binary_f1, abs_tol=1e-12)
    )


def _select_historical_plan_seed_candidates(
    candidates: Iterable[HistoricalPlanSeed],
) -> tuple[HistoricalPlanSeed, ...]:
    """Select one quality seed and one source/semantic/coverage-diverse seed."""

    best_by_family: dict[str, HistoricalPlanSeed] = {}
    for candidate in candidates:
        current = best_by_family.get(candidate.source_run_family_id)
        if current is None or _seed_candidate_quality_key(candidate) < (
            _seed_candidate_quality_key(current)
        ):
            best_by_family[candidate.source_run_family_id] = candidate
    best_by_content: dict[str, HistoricalPlanSeed] = {}
    for candidate in best_by_family.values():
        current = best_by_content.get(candidate.plan_content_hash)
        if current is None or _seed_candidate_quality_key(candidate) < (
            _seed_candidate_quality_key(current)
        ):
            best_by_content[candidate.plan_content_hash] = candidate
    ranked = sorted(best_by_content.values(), key=_seed_candidate_quality_key)
    if not ranked:
        return ()
    first = ranked[0]
    second_candidates: list[tuple[tuple[Any, ...], HistoricalPlanSeed]] = []
    first_random_ids = set(first.random_case_ids)
    for candidate in ranked[1:]:
        if candidate.source_run_family_id == first.source_run_family_id:
            continue
        if candidate.binary_f1 < (
            first.binary_f1 * HISTORICAL_PLAN_SEED_QUALITY_RATIO
        ):
            continue
        similarity = cosine_similarity(first.embedding, candidate.embedding)
        if similarity >= HISTORICAL_PLAN_SEED_SIMILARITY_THRESHOLD:
            continue
        marginal_coverage = len(set(candidate.random_case_ids) - first_random_ids)
        second_candidates.append(
            (
                (
                    -marginal_coverage,
                    similarity,
                    -binary_f1_fraction(
                        candidate.metrics_by_cohort["combined"]
                    ),
                    -candidate.metrics_by_cohort["combined"].magnitude_macro_f1,
                    candidate.source_run_family_id,
                    candidate.plan_content_hash,
                ),
                candidate,
            )
        )
    if not second_candidates:
        return (first,)
    second_candidates.sort(key=lambda item: item[0])
    return (first, second_candidates[0][1])


def _committed_seed_candidates_from_workspace(
    source_root: Path,
    *,
    search_root: Path,
    dataset_manifest_hash: str,
    evaluation_contract: Mapping[str, Any],
) -> tuple[HistoricalPlanSeed, ...]:
    contract = EvolutionRunContract.load_frozen(source_root / "run_contract.json")
    if (
        contract.schema_version
        not in {
            "evolution-run-contract-v6",
            "evolution-run-contract-v7",
            "evolution-run-contract-v8",
        }
        or contract.locked_test_accessed
        or contract.predictor_semantics_hash != FIXED_PREDICTOR_SEMANTICS_HASH
        or contract.dataset_manifest_hash != dataset_manifest_hash
        or dict(contract.limits.get("evaluation", {})) != dict(evaluation_contract)
    ):
        raise ValidationError("historical workspace is seed-incompatible")
    state = _read_json(source_root / "state.json")
    last_completed_round = int(state.get("last_completed_round", 0))
    if last_completed_round < 1:
        return ()
    expected_last_checkpoint = (
        source_root / "experiments" / f"round-{last_completed_round:04d}" / "checkpoint.json"
    )
    checkpoint_ref = state.get("checkpoint_ref")
    if (
        not isinstance(checkpoint_ref, str)
        or Path(checkpoint_ref).resolve() != expected_last_checkpoint.resolve()
    ):
        raise ValidationError("historical workspace completed pointer is invalid")
    candidates: list[HistoricalPlanSeed] = []
    embedder = HashingPlanEmbedder()
    for round_id in range(1, last_completed_round + 1):
        checkpoint_path = (
            source_root / "experiments" / f"round-{round_id:04d}" / "checkpoint.json"
        )
        checkpoint = _read_json(checkpoint_path)
        if (
            int(checkpoint.get("round_id", 0)) != round_id
            or checkpoint.get("run_contract_hash") != contract.contract_hash
        ):
            raise ValidationError("historical workspace checkpoint is invalid")
        plan_ids = checkpoint.get("plan_ids")
        if (
            not isinstance(plan_ids, list)
            or not plan_ids
            or any(not isinstance(item, str) or not item for item in plan_ids)
            or len(set(plan_ids)) != len(plan_ids)
        ):
            raise ValidationError("historical workspace checkpoint Plan ids are invalid")
        snapshot_path = source_root / "evaluation" / f"round_{round_id:03d}" / "snapshot.json"
        snapshot = _read_json(snapshot_path)
        case_ids = tuple(str(item) for item in snapshot.get("case_ids", ()))
        anchor_case_ids = tuple(
            str(item) for item in snapshot.get("anchor_case_ids", ())
        )
        random_case_ids = tuple(
            str(item) for item in snapshot.get("random_case_ids", ())
        )
        if (
            int(snapshot.get("round_id", 0)) != round_id
            or len(case_ids) != 24
            or len(set(case_ids)) != 24
            or len(anchor_case_ids) != 16
            or len(set(anchor_case_ids)) != 16
            or len(random_case_ids) != 8
            or len(set(random_case_ids)) != 8
            or set(anchor_case_ids).intersection(random_case_ids)
            or set(case_ids) != set(anchor_case_ids).union(random_case_ids)
        ):
            raise ValidationError("historical workspace evaluation snapshot is invalid")
        snapshot_id = str(snapshot.get("snapshot_id", ""))
        for plan_id in plan_ids:
            record_path = source_root / "plans" / plan_id / "record.json"
            raw_record = _read_json(record_path)
            plan = InformationPlan.from_dict(dict(raw_record["plan"]))
            metrics = PlanMetrics.from_dict(dict(raw_record["metrics"]))
            cohort_metrics = {
                str(cohort): PlanMetrics.from_dict(dict(value))
                for cohort, value in dict(
                    raw_record.get("metrics_by_cohort", {})
                ).items()
            }
            fitness = FitnessEligibility.from_dict(dict(raw_record["fitness"]))
            evaluation_case_ids = tuple(
                str(item) for item in raw_record.get("case_ids", ())
            )
            dataset_snapshot_ids = tuple(
                str(item) for item in raw_record.get("dataset_snapshot_ids", ())
            )
            serialized_trajectories = raw_record.get("trajectories", ())
            if not isinstance(serialized_trajectories, list):
                continue
            trajectory_rows = tuple(
                item for item in serialized_trajectories if isinstance(item, Mapping)
            )
            trajectory_case_ids = tuple(
                str(item.get("case_id", ""))
                for item in trajectory_rows
            )
            if (
                str(raw_record.get("plan_id")) != plan_id
                or plan.plan_id != plan_id
                or int(raw_record.get("round_id", 0)) != round_id
                or raw_record.get("evaluation_stage") != "round"
                or int(raw_record.get("n_cases", 0)) != 24
                or len(evaluation_case_ids) != 24
                or set(evaluation_case_ids) != set(case_ids)
                or len(trajectory_case_ids) != 24
                or set(trajectory_case_ids) != set(case_ids)
                or snapshot_id not in dataset_snapshot_ids
                or set(cohort_metrics) != {"anchor", "random", "combined"}
                or cohort_metrics["combined"] != metrics
                or not _metrics_match_serialized_predictions(
                    cohort_metrics["anchor"], trajectory_rows, anchor_case_ids
                )
                or not _metrics_match_serialized_predictions(
                    cohort_metrics["random"], trajectory_rows, random_case_ids
                )
                or not _metrics_match_serialized_predictions(
                    cohort_metrics["combined"], trajectory_rows, case_ids
                )
                or not fitness.eligible
                or fitness.true_positive_count < 1
            ):
                continue
            try:
                _validate_plan_for_proposer_context(
                    plan,
                    available_source_types=REGISTERED_SOURCE_TYPE_CATALOG,
                )
            except ValidationError:
                continue
            plan_content_hash = _canonical_hash(plan.canonical_dict())
            try:
                relative_workspace = str(source_root.relative_to(search_root))
            except ValueError:
                relative_workspace = source_root.name
            candidates.append(
                HistoricalPlanSeed(
                    source_workspace=relative_workspace,
                    source_run_id=contract.run_id,
                    source_run_family_id=contract.run_id,
                    source_contract_hash=contract.contract_hash,
                    source_checkpoint_ref=str(checkpoint_path),
                    source_record_hash=_canonical_hash(raw_record),
                    source_round_id=round_id,
                    source_plan_id=plan.plan_id,
                    plan_content_hash=plan_content_hash,
                    plan=plan,
                    embedding=embedder.embed(plan),
                    metrics_by_cohort=cohort_metrics,
                    random_case_ids=random_case_ids,
                    source_dataset_snapshot_id=snapshot_id,
                )
            )
    return tuple(candidates)


def build_historical_plan_seed_pool(
    *,
    search_root: str | Path,
    target_workspace: str | Path,
    dataset_manifest_hash: str,
    evaluation_contract: Mapping[str, Any],
) -> HistoricalPlanSeedPool:
    """Discover eligible committed Plans without performing external calls."""

    root = Path(search_root)
    target = Path(target_workspace).resolve()
    scanned = 0
    compatible = 0
    candidates: list[HistoricalPlanSeed] = []
    if root.is_dir():
        for contract_path in sorted(root.glob("*/run_contract.json")):
            source_root = contract_path.parent
            if source_root.resolve() == target:
                continue
            scanned += 1
            try:
                source_candidates = _committed_seed_candidates_from_workspace(
                    source_root,
                    search_root=root,
                    dataset_manifest_hash=dataset_manifest_hash,
                    evaluation_contract=evaluation_contract,
                )
            except (KeyError, OSError, TypeError, ValueError, ValidationError):
                continue
            compatible += 1
            candidates.extend(source_candidates)
    selected = _select_historical_plan_seed_candidates(candidates)
    return HistoricalPlanSeedPool(
        dataset_manifest_hash=dataset_manifest_hash,
        evaluation_contract=dict(evaluation_contract),
        entries=selected,
        scanned_workspace_count=scanned,
        compatible_workspace_count=compatible,
        eligible_plan_count=len(candidates),
    )


def load_or_create_historical_plan_seed_pool(
    *,
    workspace: str | Path,
    dataset_manifest_hash: str,
    evaluation_contract: Mapping[str, Any],
) -> HistoricalPlanSeedPool:
    """Reuse an exact staged pool or deterministically discover and freeze one."""

    workspace_root = Path(workspace)
    manifest_path = workspace_root / "seed_pool" / "manifest.json"
    if manifest_path.is_file():
        pool = HistoricalPlanSeedPool.load_frozen(manifest_path)
        if (
            pool.dataset_manifest_hash != dataset_manifest_hash
            or dict(pool.evaluation_contract) != dict(evaluation_contract)
        ):
            raise ValidationError("historical Plan seed pool conflicts with freeze scope")
        for entry in pool.entries:
            try:
                _validate_plan_for_proposer_context(
                    entry.plan,
                    available_source_types=REGISTERED_SOURCE_TYPE_CATALOG,
                )
            except ValidationError as exc:
                raise ValidationError(
                    "historical Plan seed pool contains content incompatible with "
                    f"the current proposer contract, seed_id={entry.seed_id!r}: {exc}"
                ) from exc
        return pool
    pool = build_historical_plan_seed_pool(
        search_root=workspace_root.parent,
        target_workspace=workspace_root,
        dataset_manifest_hash=dataset_manifest_hash,
        evaluation_contract=evaluation_contract,
    )
    pool.freeze(manifest_path)
    return pool


@dataclass(frozen=True)
class ApprovedDevelopmentDataset:
    """Ordinary loop inputs with Locked Test represented only by a sealed hash."""

    discovery: tuple[EvolutionCase, ...]
    anchor: tuple[EvolutionCase, ...]
    evolution_validation: tuple[EvolutionCase, ...]
    locked_test_hash: str
    approved_manifest_hash: str


def load_approved_development_dataset(
    manifest_path: str | Path,
) -> ApprovedDevelopmentDataset:
    """Load Discovery/Validation only; never deserialize Locked Test cases."""

    path = Path(manifest_path)
    manifest = _read_json(path)
    if manifest.get("approval_status") != "human_approved":
        raise ValidationError("development dataset manifest is not human-approved")
    if manifest.get("locked_test_sealed") is not True:
        raise ValidationError("development dataset does not seal Locked Test")
    artifacts = dict(manifest.get("artifacts", {}))
    loaded: dict[str, tuple[EvolutionCase, ...]] = {}
    for split_name in ("discovery", "anchor", "evolution_validation"):
        if split_name not in artifacts:
            raise ValidationError(
                f"approved development dataset is missing {split_name} split"
            )
        metadata = dict(artifacts[split_name])
        split_path = Path(str(metadata["path"]))
        if not split_path.is_file() or _sha256_file(split_path) != metadata.get(
            "sha256"
        ):
            raise ValidationError(f"dataset split hash mismatch: {split_name}")
        split = _read_json(split_path)
        if split.get("split") != split_name:
            raise ValidationError(f"dataset split identity mismatch: {split_name}")
        rows = split.get("cases", ())
        if not isinstance(rows, list) or int(
            metadata.get("case_count", -1)
        ) != len(rows):
            raise ValidationError(f"dataset split case count mismatch: {split_name}")
        loaded[split_name] = tuple(
            EvolutionCase(
                case_id=str(row["case_id"]),
                company_id=str(row["company_id"]),
                prediction_time=datetime.fromisoformat(str(row["prediction_time"])),
                basic_info=dict(row["basic_info"]),
                ground_truth=GroundTruth.from_dict(dict(row["ground_truth"])),
            )
            for row in rows
        )
    company_sets = {
        split_name: {case.company_id for case in cases}
        for split_name, cases in loaded.items()
    }
    if (
        company_sets["discovery"] & company_sets["anchor"]
        or company_sets["discovery"] & company_sets["evolution_validation"]
        or company_sets["anchor"] & company_sets["evolution_validation"]
    ):
        raise ValidationError("development dataset splits share issuer identities")
    locked_metadata = dict(artifacts["locked_test"])
    if not re.fullmatch(r"[0-9a-f]{64}", str(locked_metadata.get("sha256", ""))):
        raise ValidationError("Locked Test artifact hash is invalid")
    return ApprovedDevelopmentDataset(
        discovery=loaded["discovery"],
        anchor=loaded["anchor"],
        evolution_validation=loaded["evolution_validation"],
        locked_test_hash=str(locked_metadata["sha256"]),
        approved_manifest_hash=_sha256_file(path),
    )


def _contract_bound_import_learning_events(
    *,
    source_root: Path,
    contract: EvolutionRunContract,
) -> dict[str, SignalLearningEvent]:
    """Load learning events explicitly inherited by the source contract."""

    return {event.event_id: event for event in imported_learning_events(
        source_root, contract=contract.to_dict())}


def _validate_slow_fast_context(value: Any) -> Mapping[str, Any]:
    """Validate a self-contained, source-bound Fast context snapshot."""

    if (
        not isinstance(value, Mapping)
        or value.get("schema_version") != "slow-fast-context-v1"
        or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("origin_contract_hash", "")))
        or not isinstance(value.get("meta_entries"), list)
        or not isinstance(value.get("capability_backlog_seed"), Mapping)
    ):
        raise ValidationError("Slow history Fast context is invalid")
    try:
        entries = tuple(RoundMetaEntry.from_dict(dict(row)) for row in value["meta_entries"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("Slow history Fast meta entries are invalid") from exc
    if len({entry.round_id for entry in entries}) != len(entries):
        raise ValidationError("Slow history Fast meta rounds conflict")
    from stock_opportunity_agent.research.cross_round_reflection import validate_prediction_observation
    observations = value.get("prediction_observations", [])
    if not isinstance(observations, list):
        raise ValidationError("Slow history prediction observations must be an array")
    for row in observations:
        validate_prediction_observation(row)
    return value


def _load_slow_fast_context(
    source_root: Path, contract: EvolutionRunContract, *, seen: frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    """Recover Fast input through verified legacy imports, then freeze it once."""

    if contract.contract_hash in seen or contract.locked_test_accessed:
        raise ValidationError("Slow history Fast context lineage is cyclic or incompatible")
    seen = seen | {contract.contract_hash}
    if contract.cycle_mode in {"slow_bootstrap", "slow_only"}:
        relative = "slow_bootstrap" if contract.cycle_mode == "slow_bootstrap" else "slow_history"
        expected_hash = (
            contract.slow_bootstrap_manifest_hash
            if relative == "slow_bootstrap" else contract.slow_history_manifest_hash
        )
        envelope = _read_json(source_root / relative / "manifest.json")
        manifest = envelope.get("manifest")
        if (
            not isinstance(manifest, Mapping)
            or envelope.get("manifest_hash") != expected_hash
            or _canonical_hash(manifest) != expected_hash
        ):
            raise ValidationError("Slow history Fast context source manifest changed")
        schema = manifest.get("schema_version")
        if relative == "slow_history":
            if schema == "slow-history-manifest-v2":
                return _validate_slow_fast_context(manifest.get("fast_context"))
            if schema != "slow-history-manifest-v1":
                raise ValidationError("Slow history Fast context source schema is invalid")
            ancestor_root = Path(str(manifest.get("source_workspace", "")))
            ancestor = EvolutionRunContract.load_frozen(ancestor_root / "run_contract.json")
            if (
                ancestor.contract_hash != manifest.get("source_contract_hash")
                or ancestor.dataset_manifest_hash != contract.dataset_manifest_hash
                or int(manifest.get("committed_slow_cycle", 0)) < 1
            ):
                raise ValidationError("Slow history Fast context ancestor identity differs")
            return _load_slow_fast_context(ancestor_root, ancestor, seen=seen)
        if schema not in {"slow-bootstrap-manifest-v1", "slow-bootstrap-manifest-v2"}:
            raise ValidationError("Slow history Fast bootstrap schema is invalid")
        if schema == "slow-bootstrap-manifest-v2" and (
            manifest.get("source_kind") != "committed_fast"
            or not manifest.get("meta_entries")
        ):
            raise ValidationError("Slow history committed Fast context is missing")
        return _validate_slow_fast_context({
            "schema_version": "slow-fast-context-v1",
            "origin_contract_hash": contract.contract_hash,
            "origin_manifest_hash": expected_hash,
            "meta_entries": manifest.get("meta_entries", []),
            "capability_backlog_seed": manifest.get("capability_backlog_seed", {}),
            "prediction_observations": manifest.get("prediction_observations", []),
        })

    workspace = EvolutionWorkspace(source_root)
    archive = workspace.restore_archive(expected_run_contract_hash=contract.contract_hash)
    meta = workspace.restore_meta()
    trajectories = []
    need_sources = []
    for record in archive.records:
        for trajectory in record.trajectories:
            serialized = trajectory.to_dict()
            trajectories.append(serialized)
            need_sources.append({
                "source_ref": f"{record.plan_id}:{trajectory.case_id}",
                "source_round": record.round_id,
                "source_fingerprint": _canonical_hash(serialized),
                "trajectory": serialized,
            })
    return _validate_slow_fast_context({
        "schema_version": "slow-fast-context-v1",
        "origin_contract_hash": contract.contract_hash,
        "origin_manifest_hash": None,
        "meta_entries": [entry.to_dict() for entry in meta.entries],
        "prediction_observations": [*workspace.imported_prediction_observations(),
                                    *workspace.committed_prediction_observations()],
        "capability_backlog_seed": aggregate_capability_gaps(
            trajectories, signal_need_items=extract_unresolved_signal_needs(need_sources),
        ),
    })


def build_slow_history_manifest(
    *,
    workspace: str | Path,
    source_workspace: str | Path,
    dataset_manifest_hash: str,
) -> str:
    """Freeze one committed source workspace for a new slow-only workspace."""

    target_root = Path(workspace)
    source_root = Path(source_workspace).resolve()
    source_contract = EvolutionRunContract.load_frozen(
        source_root / "run_contract.json"
    )
    if (
        source_contract.locked_test_accessed
        or source_contract.dataset_manifest_hash != dataset_manifest_hash
    ):
        raise ValidationError("Slow history source workspace is incompatible")
    state = _read_json(source_root / "state.json")
    cycle_state = _read_json(source_root / "cycle_state.json")
    completed_fast = int(state.get("last_completed_round", 0))
    completed_slow = int(cycle_state.get("last_completed_cycle", 0))
    active_cycle = cycle_state.get("active_cycle")
    if completed_slow < 1:
        raise ValidationError("Slow history requires a fully committed source cycle")
    if active_cycle is not None and (
        not isinstance(active_cycle, Mapping)
        or int(active_cycle.get("cycle_id", 0)) <= completed_slow
    ):
        raise ValidationError("Slow history active cycle does not follow its pointer")
    registry = SignalRegistry(
        source_root / "signals",
        candidate_root=source_root / "signals_candidates",
    )
    snapshot = registry.freeze()
    if (
        snapshot.version
        != int(cycle_state.get("current_signal_registry_version", 0))
        or snapshot.registry_hash
        != str(cycle_state.get("current_signal_registry_hash", ""))
    ):
        raise ValidationError(
            "Slow history Registry is ahead of its committed cycle pointer"
        )
    definition_files: list[dict[str, str]] = []
    for path in sorted((source_root / "signals").rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root / "signals")
        if (
            relative.name in {"events.jsonl", "profile.json", "stats.json"}
            or "learning" in relative.parts
            or relative.parts[0] == ".transitions"
        ):
            continue
        definition_files.append(
            {"path": str(relative), "sha256": _sha256_file(path)}
        )
    registry_events: dict[str, SignalLearningEvent] = {}
    version_refs = registry.list_version_refs()
    for signal_ref in version_refs:
        for event in registry.load_learning_events(signal_ref):
            prior = registry_events.get(event.event_id)
            if prior is not None and prior.to_dict() != event.to_dict():
                raise ValidationError("source Registry learning event id conflicts")
            registry_events[event.event_id] = event
    imported_events = _contract_bound_import_learning_events(
        source_root=source_root,
        contract=source_contract,
    )
    for event_id, event in imported_events.items():
        observed = registry_events.get(event_id)
        if observed is None or observed.to_dict() != event.to_dict():
            raise ValidationError(
                "source Registry differs from contract-bound imported learning events"
            )
    committed_event_ids = {
        event.event_id
        for event in registry_events.values()
        if event.round_id <= completed_fast
    } | set(imported_events)
    learning_events = [
        event.to_dict()
        for signal_ref in version_refs
        for event in registry.load_learning_events(signal_ref)
        if event.event_id in committed_event_ids
    ]
    cycle_artifacts: list[dict[str, str]] = []
    required_cycle_artifacts = (
        "slow_input.json",
        "slow_memory.json",
        "slow_experiments.json",
        "slow_loop_validation.json",
        "slow_loop_result.json",
    )
    for cycle_id in range(1, completed_slow + 1):
        cycle_root = (
            source_root / "experiments" / "cycles" / f"cycle-{cycle_id:04d}"
        )
        for name in required_cycle_artifacts:
            path = cycle_root / name
            if not path.is_file():
                raise ValidationError("Slow history committed artifact is missing")
            cycle_artifacts.append(
                {
                    "cycle_id": str(cycle_id),
                    "path": str(path.relative_to(source_root)),
                    "sha256": _sha256_file(path),
                }
            )
    # Provisional residents and their pooled evaluation history are workspace
    # state, not stable Registry content: without carrying them, every
    # successor workspace would restart pooled accumulation from zero. Only
    # candidates referenced by committed cycle attempts are pointer-reachable;
    # staged work from an unfinished active cycle stays behind.
    committed_candidate_ids: set[str] = set()

    def _note_candidate_ref(candidate_ref: str) -> None:
        if ":" in candidate_ref:
            committed_candidate_ids.add(candidate_ref.rsplit(":", 1)[0])

    for cycle_id in range(1, completed_slow + 1):
        cycle_root = (
            source_root / "experiments" / "cycles" / f"cycle-{cycle_id:04d}"
        )
        for attempt in dict(
            _read_json(cycle_root / "slow_experiments.json")
        ).get("attempts", ()):
            if isinstance(attempt, Mapping):
                _note_candidate_ref(str(attempt.get("candidate_ref") or ""))
        # Revisited provisional residents never appear in the attempts list:
        # their committed evaluations (the rows pooled continuation needs)
        # live in the validation payload's candidate_effectiveness map.
        validation = dict(
            _read_json(cycle_root / "slow_loop_validation.json")
        )
        effectiveness = dict(
            dict(validation.get("validation", {})).get(
                "candidate_effectiveness", {}
            )
        )
        for candidate_ref in effectiveness:
            _note_candidate_ref(str(candidate_ref))
    candidate_files: list[dict[str, str]] = []
    candidates_root = source_root / "signals_candidates"
    candidate_paths: tuple[Path, ...] = (
        sorted(candidates_root.rglob("*")) if candidates_root.is_dir() else ()
    )
    for path in candidate_paths:
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if ".rejected" in relative.parts:
            continue
        parts = relative.parts
        if (
            len(parts) < 4
            or parts[0] != "signals_candidates"
            or parts[2] not in committed_candidate_ids
        ):
            continue
        candidate_files.append(
            {"path": str(relative), "sha256": _sha256_file(path)}
        )
    manifest = {
        "schema_version": "slow-history-manifest-v2",
        "fast_context": dict(_load_slow_fast_context(source_root, source_contract)),
        "source_namespace": "source-" + source_contract.contract_hash[:16],
        "source_workspace": str(source_root),
        "source_contract_hash": source_contract.contract_hash,
        "dataset_manifest_hash": dataset_manifest_hash,
        "committed_fast_round": completed_fast,
        "committed_slow_cycle": completed_slow,
        "registry_version": snapshot.version,
        "registry_hash": snapshot.registry_hash,
        "registry_definition_files": definition_files,
        "learning_events": learning_events,
        "cycle_artifacts": cycle_artifacts,
        "candidate_files": candidate_files,
    }
    envelope = {"manifest_hash": _canonical_hash(manifest), "manifest": manifest}
    _write_or_verify_json(
        target_root / "slow_history" / "manifest.json", envelope
    )
    return str(envelope["manifest_hash"])


def validate_slow_history_manifest(
    *,
    workspace: str | Path,
    contract: EvolutionRunContract,
) -> Mapping[str, Any]:
    """Validate the frozen source pointer, hashes, and imported Registry identity."""

    envelope = _read_json(Path(workspace) / "slow_history" / "manifest.json")
    manifest = dict(envelope.get("manifest", {}))
    if (
        manifest.get("schema_version") not in {"slow-history-manifest-v1", "slow-history-manifest-v2"}
        or envelope.get("manifest_hash") != _canonical_hash(manifest)
        or envelope.get("manifest_hash") != contract.slow_history_manifest_hash
        or manifest.get("dataset_manifest_hash") != contract.dataset_manifest_hash
    ):
        raise ValidationError("Slow history manifest identity mismatch")
    if manifest.get("schema_version") == "slow-history-manifest-v2":
        _validate_slow_fast_context(manifest.get("fast_context"))
    source_root = Path(str(manifest.get("source_workspace", "")))
    for row in manifest.get("registry_definition_files", ()):
        source_path = source_root / "signals" / str(row["path"])
        if not source_path.is_file() or _sha256_file(source_path) != row.get("sha256"):
            raise ValidationError("Slow history source Registry file changed")
    for row in manifest.get("cycle_artifacts", ()):
        source_path = source_root / str(row["path"])
        if not source_path.is_file() or _sha256_file(source_path) != row.get("sha256"):
            raise ValidationError("Slow history committed artifact changed")
    for row in manifest.get("candidate_files", ()):
        source_path = source_root / str(row["path"])
        if not source_path.is_file() or _sha256_file(source_path) != row.get("sha256"):
            raise ValidationError("Slow history candidate file changed")
    return manifest


def _registry_matches_committed_history(
    *,
    snapshot_version: int,
    snapshot_hash: str,
    history_registry_version: int,
    history_registry_hash: str,
    workspace_root: Path,
) -> bool:
    """Whether the live Registry is explained by the committed cycle chain.

    The baseline is the imported history manifest. Each committed cycle must
    record exactly the expected input Registry and a well-formed output, and
    the live Registry must equal the last committed cycle's output. A
    promotion committed by an own cycle therefore resumes; unexplained drift
    (an uncommitted transition, a gap, or a rewritten cycle) still fails
    closed exactly as before.
    """

    expected_version = history_registry_version
    expected_hash = history_registry_hash
    workspace = EvolutionWorkspace(workspace_root)
    for cycle_id in range(1, workspace.last_completed_cycle + 1):
        result_path = (
            workspace_root
            / "experiments"
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_result.json"
        )
        if not result_path.is_file():
            return False
        result = dict(_read_json(result_path).get("result", {}))
        input_version = result.get("input_registry_version")
        input_hash = str(result.get("input_registry_hash", ""))
        output_version = result.get("output_registry_version")
        output_hash = str(result.get("output_registry_hash", ""))
        if (
            input_version != expected_version
            or input_hash != expected_hash
            or not isinstance(output_version, int)
            or not output_hash.strip()
        ):
            return False
        expected_version = output_version
        expected_hash = output_hash
    return (
        snapshot_version == expected_version and snapshot_hash == expected_hash
    )


def apply_slow_history_manifest(
    *,
    workspace: str | Path,
    manifest: Mapping[str, Any],
) -> None:
    """Materialize the exact committed Registry and namespaced history once."""

    target_root = Path(workspace)
    source_root = Path(str(manifest["source_workspace"]))
    signals_root = target_root / "signals"
    existing_manifests = tuple(signals_root.glob("*/*/manifest.json"))
    if existing_manifests:
        snapshot = SignalRegistry(
            signals_root,
            candidate_root=target_root / "signals_candidates",
        ).freeze()
        if snapshot.registry_hash != manifest.get("registry_hash"):
            raise ValidationError("target Registry conflicts with Slow history")
    else:
        for row in manifest.get("registry_definition_files", ()):
            source_path = source_root / "signals" / str(row["path"])
            target_path = signals_root / str(row["path"])
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
    registry = SignalRegistry(
        signals_root,
        candidate_root=target_root / "signals_candidates",
    )
    events = tuple(
        SignalLearningEvent.from_dict(dict(item))
        for item in manifest.get("learning_events", ())
    )
    record_committed_signal_use(registry, events)
    snapshot = registry.freeze()
    if (
        snapshot.version != int(manifest["registry_version"])
        or snapshot.registry_hash != manifest["registry_hash"]
    ):
        raise ValidationError("imported Slow history Registry identity mismatch")
    namespace = str(manifest["source_namespace"])
    for row in manifest.get("cycle_artifacts", ()):
        source_path = source_root / str(row["path"])
        target_path = target_root / "slow_history" / namespace / str(row["path"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() and _sha256_file(target_path) != row["sha256"]:
            raise ValidationError("imported Slow history artifact conflicts")
        if not target_path.exists():
            shutil.copy2(source_path, target_path)
    for row in manifest.get("candidate_files", ()):
        source_path = source_root / str(row["path"])
        target_path = target_root / str(row["path"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() and _sha256_file(target_path) != row["sha256"]:
            raise ValidationError("imported Slow history candidate conflicts")
        if not target_path.exists():
            shutil.copy2(source_path, target_path)
    # Carry the source's own imported namespaces forward so multi-hop
    # successor chains keep the full namespaced history (resident
    # enumeration and reflection footprints read every namespace). Namespaces
    # are immutable once written: byte conflicts fail closed.
    for namespace_dir in sorted(
        path
        for path in (source_root / "slow_history").glob("*")
        if path.is_dir()
    ):
        for file_path in sorted(namespace_dir.rglob("*")):
            if not file_path.is_file():
                continue
            target_path = target_root / file_path.relative_to(source_root)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                if target_path.read_bytes() != file_path.read_bytes():
                    raise ValidationError(
                        "imported Slow history namespace conflicts"
                    )
            else:
                shutil.copy2(file_path, target_path)


def build_slow_bootstrap_manifest(
    *,
    workspace: str | Path,
    source_workspaces: Iterable[str | Path],
    dataset: ApprovedDevelopmentDataset,
    signal_snapshot: FrozenSignalRegistry,
    evaluation_contract: Mapping[str, Any],
) -> str:
    """Freeze one explicit rejected-gap or committed-Fast Slow seed."""

    workspace_root = Path(workspace)
    manifest_path = workspace_root / "slow_bootstrap" / "manifest.json"
    sources = tuple(Path(item) for item in source_workspaces)
    if not sources:
        raise ValidationError("slow_bootstrap requires at least one source workspace")
    source_kinds = tuple(_slow_bootstrap_source_kind(item) for item in sources)
    if all(kind == "committed_fast" for kind in source_kinds):
        return _build_committed_fast_bootstrap_manifest(
            manifest_path=manifest_path,
            source_workspaces=sources,
            dataset=dataset,
            signal_snapshot=signal_snapshot,
            evaluation_contract=evaluation_contract,
        )
    if any(kind != "rejected_no_match" for kind in source_kinds):
        raise ValidationError(
            "slow_bootstrap cannot merge rejected and committed Fast sources"
        )
    cases = {
        case.case_id: case
        for case in (
            *dataset.discovery,
            *dataset.anchor,
            *dataset.evolution_validation,
        )
    }
    grouped: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    for source_root in sources:
        contract = EvolutionRunContract.load_frozen(source_root / "run_contract.json")
        if (
            contract.schema_version not in {
                "evolution-run-contract-v6",
                "evolution-run-contract-v7",
                "evolution-run-contract-v8",
            }
            or contract.cycle_mode != "fast_then_slow"
            or contract.locked_test_accessed
            or contract.dataset_manifest_hash != dataset.approved_manifest_hash
            or contract.predictor_semantics_hash != FIXED_PREDICTOR_SEMANTICS_HASH
            or dict(contract.limits.get("evaluation", {}))
            != dict(evaluation_contract)
        ):
            raise ValidationError("slow-bootstrap source workspace is incompatible")
        source_snapshot = SignalRegistry(
            source_root / "signals",
            candidate_root=source_root / "signals_candidates",
        ).freeze()
        if (
            source_snapshot.version != signal_snapshot.version
            or source_snapshot.registry_hash != signal_snapshot.registry_hash
        ):
            raise ValidationError(
                "slow-bootstrap source Signal Registry differs from target input"
            )
        state = _read_json(source_root / "state.json")
        last_completed_round = int(state.get("last_completed_round", 0))
        rejected_round = last_completed_round + 1
        rejected_path = (
            source_root
            / "experiments"
            / f"round-{rejected_round:04d}"
            / "rejected.json"
        )
        rejected = _read_json(rejected_path)
        if (
            rejected.get("schema_version") != "plan-round-rejected-v1"
            or int(rejected.get("round_id", 0)) != rejected_round
            or int(rejected.get("last_completed_round", -1))
            != last_completed_round
        ):
            raise ValidationError("slow-bootstrap source rejection is not authoritative")
        source_key = contract.contract_hash
        extracted = 0
        for attempt in rejected.get("attempts", ()):
            if not isinstance(attempt, Mapping):
                continue
            for trajectory in attempt.get("trajectories", ()):
                if not isinstance(trajectory, Mapping):
                    continue
                if (
                    trajectory.get("stop_reason") != "no_signal_match"
                    or trajectory.get("termination_trigger") != "no_signal_match"
                ):
                    continue
                state_payload = trajectory.get("final_state", {})
                if (
                    not isinstance(state_payload, Mapping)
                    or state_payload.get("decision") != "continue"
                ):
                    continue
                case = cases.get(str(trajectory.get("case_id", "")))
                if case is None:
                    raise ValidationError(
                        "slow-bootstrap trajectory case is outside the approved dataset"
                    )
                aliases: list[str] = [case.case_id, case.company_id]
                for key in ("company_name", "ticker", "symbol", "name"):
                    value = case.basic_info.get(key)
                    if isinstance(value, str) and value.strip():
                        aliases.append(value)
                raw_aliases = case.basic_info.get("identity_aliases", ())
                if isinstance(raw_aliases, str):
                    raw_aliases = (raw_aliases,)
                if isinstance(raw_aliases, (list, tuple)):
                    aliases.extend(
                        item
                        for item in raw_aliases
                        if isinstance(item, str) and item.strip()
                    )
                needs = state_payload.get("next_information_needs", ())
                if not isinstance(needs, list):
                    raise ValidationError(
                        "slow-bootstrap next_information_needs must be an array"
                    )
                for raw_need in needs:
                    if not isinstance(raw_need, str):
                        raise ValidationError(
                            "slow-bootstrap information need must be a string"
                        )
                    masked = str(_mask_identity_values(raw_need, aliases))
                    need = " ".join(masked.split())
                    if not need:
                        continue
                    normalized = need.casefold()
                    row = grouped.setdefault(
                        normalized,
                        {
                            "need": need,
                            "occurrences": 0,
                            "source_contract_hashes": set(),
                        },
                    )
                    row["occurrences"] += 1
                    row["source_contract_hashes"].add(source_key)
                    extracted += 1
        source_rows.append(
            {
                "run_id": contract.run_id,
                "contract_hash": contract.contract_hash,
                "rejected_round": rejected_round,
                "rejected_hash": _sha256_file(rejected_path),
                "extracted_need_count": extracted,
            }
        )
    signal_need_items = [
        {
            "need": row["need"],
            "occurrences": row["occurrences"],
            "source_count": len(row["source_contract_hashes"]),
        }
        for _key, row in sorted(grouped.items())
    ]
    if not signal_need_items:
        raise ValidationError(
            "slow_bootstrap sources contain no eligible no_signal_match need"
        )
    backlog = aggregate_capability_gaps((), signal_need_items=signal_need_items)
    manifest = {
        "schema_version": "slow-bootstrap-manifest-v1",
        "source_kind": "rejected_no_match",
        "dataset_manifest_hash": dataset.approved_manifest_hash,
        "predictor_semantics_hash": FIXED_PREDICTOR_SEMANTICS_HASH,
        "evaluation_contract": dict(evaluation_contract),
        "input_signal_registry_version": signal_snapshot.version,
        "input_signal_registry_hash": signal_snapshot.registry_hash,
        "sources": source_rows,
        "capability_backlog_seed": backlog,
    }
    manifest_hash = _canonical_hash(manifest)
    _write_or_verify_json(
        manifest_path,
        {"manifest_hash": manifest_hash, "manifest": manifest},
    )
    return manifest_hash


def _slow_bootstrap_source_kind(source_root: Path) -> str:
    """Classify one source by its next authoritative Slow input boundary."""

    state = _read_json(source_root / "state.json")
    last_completed_round = int(state.get("last_completed_round", 0))
    rejected_path = (
        source_root
        / "experiments"
        / f"round-{last_completed_round + 1:04d}"
        / "rejected.json"
    )
    if rejected_path.exists():
        return "rejected_no_match"
    if last_completed_round > 0:
        return "committed_fast"
    raise ValidationError("slow-bootstrap source has no authoritative seed boundary")


def _build_committed_fast_bootstrap_manifest(
    *,
    manifest_path: Path,
    source_workspaces: tuple[Path, ...],
    dataset: ApprovedDevelopmentDataset,
    signal_snapshot: FrozenSignalRegistry,
    evaluation_contract: Mapping[str, Any],
) -> str:
    """Freeze derivatives from one committed Fast range whose Slow has not run."""

    if len(source_workspaces) != 1:
        raise ValidationError(
            "committed Fast bootstrap requires exactly one source workspace"
        )
    source_root = source_workspaces[0]
    contract = EvolutionRunContract.load_frozen(source_root / "run_contract.json")
    if (
        contract.schema_version not in {
            "evolution-run-contract-v7",
            "evolution-run-contract-v8",
        }
        or contract.cycle_mode != "fast_then_slow"
        or contract.locked_test_accessed
        or contract.dataset_manifest_hash != dataset.approved_manifest_hash
        or contract.predictor_semantics_hash != FIXED_PREDICTOR_SEMANTICS_HASH
        or dict(contract.limits.get("evaluation", {}))
        != dict(evaluation_contract)
    ):
        raise ValidationError("committed Fast bootstrap source is incompatible")
    source_snapshot = SignalRegistry(
        source_root / "signals",
        candidate_root=source_root / "signals_candidates",
    ).freeze()
    if (
        source_snapshot.version != signal_snapshot.version
        or source_snapshot.registry_hash != signal_snapshot.registry_hash
    ):
        raise ValidationError(
            "committed Fast bootstrap source Signal Registry differs from target input"
        )

    state_path = source_root / "state.json"
    cycle_state_path = source_root / "cycle_state.json"
    state = _read_json(state_path)
    cycle_state = _read_json(cycle_state_path)
    active = cycle_state.get("active_cycle")
    if not isinstance(active, Mapping):
        raise ValidationError("committed Fast bootstrap requires an active source cycle")
    cycle_id = int(active.get("cycle_id", 0))
    start_round = int(active.get("start_round", -1))
    target_rounds = int(active.get("target_plan_rounds", 0))
    final_round = int(state.get("last_completed_round", 0))
    if (
        cycle_id < 1
        or active.get("cycle_mode") != "fast_then_slow"
        or cycle_state.get("run_contract_hash") != contract.contract_hash
        or active.get("phase") not in {"fast_loop", "slow_loop"}
        or int(active.get("input_signal_registry_version", 0))
        != signal_snapshot.version
        or active.get("input_signal_registry_hash")
        != signal_snapshot.registry_hash
        or target_rounds < 1
        or final_round != start_round + target_rounds
        or int(cycle_state.get("last_completed_cycle", -1)) != cycle_id - 1
    ):
        raise ValidationError(
            "committed Fast bootstrap source is not at the pre-Slow boundary"
        )
    source_workspace = EvolutionWorkspace(source_root)
    if (
        source_workspace.staged_slow_validation(cycle_id) is not None
        or source_workspace.staged_slow_result(cycle_id) is not None
    ):
        raise ValidationError(
            "committed Fast bootstrap source already contains Slow output"
        )
    archive = source_workspace.restore_archive(
        expected_run_contract_hash=contract.contract_hash
    )
    records = tuple(
        record
        for record in archive.records
        if start_round < record.round_id <= final_round
    )
    expected_round_ids = tuple(range(start_round + 1, final_round + 1))
    if tuple(sorted({record.round_id for record in records})) != expected_round_ids:
        raise ValidationError("committed Fast bootstrap record range is incomplete")
    meta_entries = tuple(
        entry
        for entry in source_workspace.restore_meta().entries
        if start_round < entry.round_id <= final_round
    )
    if tuple(entry.round_id for entry in meta_entries) != expected_round_ids:
        raise ValidationError("committed Fast bootstrap meta range is incomplete")
    learning_events = tuple(
        event
        for record in records
        for event in _signal_learning_events_from_record(record)
    )
    if len({event.event_id for event in learning_events}) != len(learning_events):
        raise ValidationError("committed Fast bootstrap learning events are duplicated")
    trajectories: list[dict[str, Any]] = []
    need_sources: list[dict[str, Any]] = []
    for record in records:
        for trajectory in record.trajectories:
            serialized = trajectory.to_dict()
            trajectories.append(serialized)
            need_sources.append(
                {
                    "source_ref": f"{record.plan_id}:{trajectory.case_id}",
                    "source_round": record.round_id,
                    "source_fingerprint": _canonical_hash(serialized),
                    "trajectory": serialized,
                }
            )
    signal_need_items = extract_unresolved_signal_needs(need_sources)
    artifacts: list[dict[str, Any]] = []
    for round_id in expected_round_ids:
        checkpoint_path = (
            source_root / "experiments" / f"round-{round_id:04d}" / "checkpoint.json"
        )
        meta_path = source_root / "meta" / f"round-{round_id:04d}.json"
        checkpoint = _read_json(checkpoint_path)
        artifacts.extend(
            (
                {
                    "kind": "checkpoint",
                    "round_id": round_id,
                    "sha256": _sha256_file(checkpoint_path),
                },
                {
                    "kind": "meta",
                    "round_id": round_id,
                    "sha256": _sha256_file(meta_path),
                },
            )
        )
        for plan_id in checkpoint["plan_ids"]:
            plan_path = source_root / "plans" / str(plan_id) / "record.json"
            artifacts.append(
                {
                    "kind": "plan_record",
                    "round_id": round_id,
                    "plan_id": str(plan_id),
                    "sha256": _sha256_file(plan_path),
                }
            )
    manifest = {
        "schema_version": "slow-bootstrap-manifest-v2",
        "source_kind": "committed_fast",
        "dataset_manifest_hash": dataset.approved_manifest_hash,
        "predictor_semantics_hash": FIXED_PREDICTOR_SEMANTICS_HASH,
        "evaluation_contract": dict(evaluation_contract),
        "input_signal_registry_version": signal_snapshot.version,
        "input_signal_registry_hash": signal_snapshot.registry_hash,
        "sources": [
            {
                "run_id": contract.run_id,
                "contract_hash": contract.contract_hash,
                "cycle_id": cycle_id,
                "start_round": start_round,
                "final_round": final_round,
                "state_hash": _sha256_file(state_path),
                "cycle_state_hash": _sha256_file(cycle_state_path),
                "artifacts": artifacts,
            }
        ],
        "meta_entries": [entry.to_dict() for entry in meta_entries],
        "prediction_observations": [*source_workspace.imported_prediction_observations(),
                                    *source_workspace.committed_prediction_observations(round_ids=expected_round_ids)],
        "signal_learning_events": [event.to_dict() for event in learning_events],
        "capability_backlog_seed": aggregate_capability_gaps(
            trajectories,
            signal_need_items=signal_need_items,
        ),
    }
    manifest_hash = _canonical_hash(manifest)
    _write_or_verify_json(
        manifest_path,
        {"manifest_hash": manifest_hash, "manifest": manifest},
    )
    return manifest_hash


def validate_slow_bootstrap_manifest(
    *,
    workspace: str | Path,
    contract: EvolutionRunContract,
    signal_snapshot: FrozenSignalRegistry,
) -> Mapping[str, Any]:
    """Verify the immutable Slow-bootstrap seed before cycle creation."""

    path = Path(workspace) / "slow_bootstrap" / "manifest.json"
    envelope = _read_json(path)
    manifest = envelope.get("manifest", {})
    if not isinstance(manifest, Mapping):
        raise ValidationError("slow-bootstrap manifest body is invalid")
    manifest_hash = _canonical_hash(manifest)
    backlog = manifest.get("capability_backlog_seed", {})
    if (
        envelope.get("manifest_hash") != manifest_hash
        or contract.slow_bootstrap_manifest_hash != manifest_hash
        or manifest.get("schema_version")
        not in {"slow-bootstrap-manifest-v1", "slow-bootstrap-manifest-v2"}
        or manifest.get("dataset_manifest_hash") != contract.dataset_manifest_hash
        or manifest.get("predictor_semantics_hash")
        != contract.predictor_semantics_hash
        or dict(manifest.get("evaluation_contract", {}))
        != dict(contract.limits.get("evaluation", {}))
        or int(manifest.get("input_signal_registry_version", 0))
        != signal_snapshot.version
        or manifest.get("input_signal_registry_hash")
        != signal_snapshot.registry_hash
        or not isinstance(backlog, Mapping)
        or backlog.get("schema_version")
        not in {"capability-gap-report-v2", "capability-gap-report-v3"}
    ):
        raise ValidationError("slow-bootstrap manifest differs from frozen contract")
    schema_version = str(manifest["schema_version"])
    if schema_version == "slow-bootstrap-manifest-v1":
        if (
            manifest.get("source_kind") not in {None, "rejected_no_match"}
            or not backlog.get("signal_need_items")
        ):
            raise ValidationError(
                "rejected Slow-bootstrap manifest has no diagnostic seed"
            )
        return manifest

    sources = manifest.get("sources")
    meta_values = manifest.get("meta_entries")
    event_values = manifest.get("signal_learning_events")
    if (
        manifest.get("source_kind") != "committed_fast"
        or not isinstance(sources, list)
        or len(sources) != 1
        or not isinstance(sources[0], Mapping)
        or not isinstance(meta_values, list)
        or not meta_values
        or not isinstance(event_values, list)
    ):
        raise ValidationError("committed Fast bootstrap manifest shape is invalid")
    source = sources[0]
    start_round = int(source.get("start_round", -1))
    final_round = int(source.get("final_round", 0))
    expected_round_ids = tuple(range(start_round + 1, final_round + 1))
    try:
        meta_entries = tuple(
            RoundMetaEntry.from_dict(dict(value)) for value in meta_values
        )
        learning_events = tuple(
            SignalLearningEvent.from_dict(dict(value)) for value in event_values
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(
            "committed Fast bootstrap contains invalid learning derivatives"
        ) from exc
    known_signal_refs = {spec.ref for spec in signal_snapshot.specs}
    artifacts = source.get("artifacts")
    if (
        start_round < 0
        or final_round <= start_round
        or tuple(entry.round_id for entry in meta_entries) != expected_round_ids
        or any(event.round_id not in expected_round_ids for event in learning_events)
        or len({event.event_id for event in learning_events})
        != len(learning_events)
        or any(event.signal_ref not in known_signal_refs for event in learning_events)
        or not isinstance(artifacts, list)
        or not artifacts
        or any(
            not isinstance(item, Mapping)
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
            for item in artifacts
        )
    ):
        raise ValidationError(
            "committed Fast bootstrap derivatives differ from their source range"
        )
    return manifest


def apply_slow_bootstrap_derivatives(
    manifest: Mapping[str, Any],
    *,
    registry: SignalRegistry,
) -> tuple[RoundMetaEntry, ...]:
    """Idempotently restore manifest-bound committed-Fast learning derivatives."""

    if manifest.get("schema_version") != "slow-bootstrap-manifest-v2":
        return ()
    events = tuple(
        SignalLearningEvent.from_dict(dict(value))
        for value in manifest.get("signal_learning_events", ())
    )
    record_committed_signal_use(registry, events)
    return tuple(
        RoundMetaEntry.from_dict(dict(value))
        for value in manifest.get("meta_entries", ())
    )


def _validate_cycle_execution_request(
    contract: EvolutionRunContract,
    *,
    allow_data_external: bool,
) -> None:
    """Reject non-executable or mismatched source-data execution requests."""

    if not contract.executable:
        raise ValidationError("legacy_contract_read_only")
    if allow_data_external and not contract.data_acquisition.enabled:
        raise ExternalExecutionNotReady(
            "data_acquisition_not_in_contract",
            "source-data execution was requested but the frozen contract disabled it",
        )
    if contract.data_acquisition.enabled and not allow_data_external:
        raise ExternalExecutionNotReady(
            "data_external_approval_required",
            (
                "the frozen contract enables source-data acquisition; rerun with "
                "--data-external before any cycle or evaluation snapshot can start"
            ),
        )


def _rebased_history_meta_entries(
    entries: Iterable[RoundMetaEntry],
) -> tuple[RoundMetaEntry, ...]:
    """Move imported round reflections into a reserved negative round range.

    A successor run imports committed Fast history while numbering its own
    rounds from one; PlanMetaMemory requires strictly increasing round ids,
    so unrebased imported entries would make the first local commit raise a
    monotonicity violation. The rebased prefix keeps source order and stays
    strictly below every local round id.
    """

    ordered = tuple(entries)
    if not ordered:
        return ()
    offset = max(entry.round_id for entry in ordered) + 1
    return tuple(
        replace(entry, round_id=entry.round_id - offset) for entry in ordered
    )


def _parallel_decision_roles(
    judge_caller: Any,
    *,
    parallel_jev_decisions: bool,
    environ: Mapping[str, str] | None,
) -> tuple[Any, Any]:
    """Return (signal_agent, predictor) honoring the parallel Jev decision path.

    Default production keeps the LLM roles; an explicit frozen-contract flag
    swaps only the two closed-choice decisions to Jev while the same caller
    keeps prose explanation and post-label reflection.
    """

    if not parallel_jev_decisions:
        return LLMSignalRetrievalAgent(judge_caller), LLMBlindPredictor(judge_caller)
    client = OpenRouterJevClient.from_environ(environ)
    return JevSignalRetrievalAgent(client), JevBlindPredictor(client, judge_caller)


def _run_bounded_evolution_cycle_unlocked(
    *,
    workspace_path: str | Path,
    raw_info_root: str | Path,
    approved_dataset_manifest: str | Path,
    contract: EvolutionRunContract,
    allow_external: bool,
    acknowledged_contract_hash: str | None = None,
    allow_data_external: bool = False,
    environ: Mapping[str, str] | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> DualLoopResult:
    """Run one finite cycle while the caller holds the workspace lock."""

    workspace_root = Path(workspace_path)
    _validate_cycle_execution_request(
        contract, allow_data_external=allow_data_external
    )
    dataset = load_approved_development_dataset(approved_dataset_manifest)
    if dataset.approved_manifest_hash != contract.dataset_manifest_hash:
        raise ValidationError("approved dataset differs from frozen run contract")
    if contract.python_runtime != platform.python_version():
        raise ValidationError("Python runtime differs from frozen run contract")
    project_root = Path(__file__).resolve().parents[3]
    if contract.code_revision != current_code_revision(project_root):
        raise ValidationError("Git revision differs from frozen run contract")
    oracle = RawInfoOracle.load_or_create(raw_info_root)
    if oracle.oracle_id != contract.raw_info_oracle_id:
        raise ValidationError("Raw Info oracle differs from frozen run contract")
    evaluation_limits = contract.limits["evaluation"]
    if not isinstance(evaluation_limits, Mapping):
        raise ValidationError("run contract evaluation limits must be an object")
    evaluation_config = PlanEvaluationConfig.from_dict(evaluation_limits)
    EvaluationDatasetManager(
        workspace_root / "evaluation",
        dataset.evolution_validation,
        dataset.anchor,
        evaluation_config,
    ).validate_feasibility()
    historical_seed_plans: tuple[InformationPlan, ...] = ()
    historical_seed_parent_evidence: tuple[
        ParentPlanReflectionEvidence, ...
    ] = ()
    if contract.seed_pool_manifest_hash is not None:
        seed_pool = HistoricalPlanSeedPool.load_frozen(
            workspace_root / "seed_pool" / "manifest.json"
        )
        if (
            seed_pool.manifest_hash != contract.seed_pool_manifest_hash
            or seed_pool.dataset_manifest_hash != contract.dataset_manifest_hash
            or dict(seed_pool.evaluation_contract) != evaluation_config.to_dict()
        ):
            raise ValidationError(
                "historical Plan seed pool differs from frozen run contract"
            )
        historical_seed_plans = seed_pool.plans
        historical_seed_parent_evidence = tuple(
            ParentPlanReflectionEvidence(
                plan=entry.parent_plan,
                source_scope="historical_seed",
                evaluation_snapshot_ids=(
                    (entry.source_dataset_snapshot_id,)
                    if entry.source_dataset_snapshot_id is not None
                    else ()
                ),
                metrics_by_cohort=entry.metrics_by_cohort,
            )
            for entry in seed_pool.entries
        )
    registry = SignalRegistry(
        workspace_root / "signals",
        candidate_root=workspace_root / "signals_candidates",
    )
    snapshot = registry.freeze()
    bootstrap_meta_entries: tuple[RoundMetaEntry, ...] = ()
    if contract.cycle_mode == "slow_bootstrap":
        bootstrap_manifest = validate_slow_bootstrap_manifest(
            workspace=workspace_root,
            contract=contract,
            signal_snapshot=snapshot,
        )
        bootstrap_meta_entries = _rebased_history_meta_entries(
            apply_slow_bootstrap_derivatives(
                bootstrap_manifest,
                registry=registry,
            )
        )
    elif contract.slow_history_manifest_hash is not None:
        # slow_only succession and fast_then_slow dual-loop continuation share
        # the same committed-history validation and chain-continuity rules.
        history_manifest = validate_slow_history_manifest(
            workspace=workspace_root,
            contract=contract,
        )
        if history_manifest.get("schema_version") == "slow-history-manifest-v2":
            bootstrap_meta_entries = _rebased_history_meta_entries(
                RoundMetaEntry.from_dict(dict(row))
                for row in history_manifest["fast_context"]["meta_entries"]
            )
        if not _registry_matches_committed_history(
            snapshot_version=snapshot.version,
            snapshot_hash=snapshot.registry_hash,
            history_registry_version=int(history_manifest["registry_version"]),
            history_registry_hash=str(history_manifest["registry_hash"]),
            workspace_root=workspace_root,
        ):
            raise ValidationError(
                "imported-history Registry differs from frozen committed history"
            )
    if _canonical_hash(_default_priors_dict()) != contract.priors_hash:
        raise ValidationError("fixed evolution priors differ from frozen run contract")

    limits = dict(contract.limits)
    target_plan_rounds = int(limits["plan_rounds_per_signal_cycle"])
    evolution_workspace = EvolutionWorkspace(workspace_root)
    cycle = evolution_workspace.start_or_resume_cycle(
        run_contract_hash=contract.contract_hash,
        target_plan_rounds=target_plan_rounds,
        cycle_mode=contract.cycle_mode,
        initial_signal_registry_version=contract.initial_signal_registry_version,
        initial_signal_registry_hash=contract.initial_signal_registry_hash,
        observed_signal_registry_version=snapshot.version,
        observed_signal_registry_hash=snapshot.registry_hash,
        max_slow_cycles=contract.max_slow_cycles,
    )
    cycle_id = int(cycle["cycle_id"])

    emit_lock = threading.Lock()

    def emit(event: Mapping[str, Any]) -> None:
        with emit_lock:
            event_type = str(event.get("event_type") or "runtime_progress")
            details = {
                key: value for key, value in event.items() if key != "event_type"
            }
            details.setdefault("cycle_id", cycle_id)
            if event_type == "round_committed":
                evolution_workspace.mark_cycle_phase("fast_loop")
            elif event_type == "slow_loop_started":
                evolution_workspace.mark_cycle_phase("slow_loop")
            stored = evolution_workspace.append_event(event_type, details)
            if on_progress is not None:
                on_progress(stored)

    emit(
        {
            "event_type": "cycle_resumed" if cycle["resumed"] else "cycle_started",
            "start_round": int(cycle["start_round"]),
            "completed_plan_rounds": int(cycle["completed_plan_rounds"]),
            "target_plan_rounds": target_plan_rounds,
            "cycle_mode": contract.cycle_mode,
            "phase": str(cycle["phase"]),
            "max_parallel_plans": int(limits.get("max_parallel_plans", 1)),
        }
    )
    completed_plan_rounds = int(cycle["completed_plan_rounds"])
    staged_slow = evolution_workspace.staged_slow_result(cycle_id)
    if staged_slow is not None:
        if completed_plan_rounds != target_plan_rounds:
            raise ValidationError("staged Slow result exists before Fast loop completion")
        signal_result = SlowLoopResult.from_dict(staged_slow)
        emit(
            {
                "event_type": "slow_loop_result_reused",
                "validated_candidates": dict(signal_result.validated_candidates),
                "promoted": list(signal_result.promoted),
                "output_registry_version": signal_result.output_registry_version,
                "output_registry_hash": signal_result.output_registry_hash,
            }
        )
        current_snapshot = registry.freeze()
        evolution_workspace.complete_cycle(
            cycle_id=cycle_id,
            observed_signal_registry_version=current_snapshot.version,
            observed_signal_registry_hash=current_snapshot.registry_hash,
        )
        emit(
            {
                "event_type": "cycle_committed",
                "last_completed_round": evolution_workspace.last_completed_round,
                "last_completed_cycle": evolution_workspace.last_completed_cycle,
            }
        )
        return DualLoopResult(plan_rounds=(), signal_evolution=signal_result)

    staged_validation = evolution_workspace.staged_slow_validation(cycle_id)
    if staged_validation is None and (
        snapshot.version != int(cycle["input_signal_registry_version"])
        or snapshot.registry_hash != cycle["input_signal_registry_hash"]
    ):
        raise ValidationError("stable Signal Registry differs from active cycle input")

    ledger = ExternalAttemptLedger(
        workspace_root / "attempts.json",
        max_attempts=contract.max_external_attempts,
        max_total_cost=contract.max_total_cost,
    )
    reconciled_attempts = ledger.reconcile_interrupted()
    if reconciled_attempts:
        emit(
            {
                "event_type": "external_attempts_reconciled",
                "interrupted_attempt_count": reconciled_attempts,
            }
        )
    judge_alias = str(contract.models["judge"]["alias"])
    evolution_alias = str(contract.models["proposer"]["alias"])
    judge_caller = StructuredRoleClient(
        registration=get_model(judge_alias, role="judge"),
        contract=contract,
        workspace=workspace_root,
        ledger=ledger,
        allow_external=allow_external,
        acknowledged_contract_hash=acknowledged_contract_hash,
        environ=environ,
        on_progress=emit,
    )
    evolution_caller = StructuredRoleClient(
        registration=get_model(evolution_alias, role="evolution"),
        contract=contract,
        workspace=workspace_root,
        ledger=ledger,
        allow_external=allow_external,
        acknowledged_contract_hash=acknowledged_contract_hash,
        environ=environ,
        on_progress=emit,
    )
    raw_info_store = RawInfoStore(raw_info_root)
    evidence_resolver = _build_evidence_resolver(
        workspace_root,
        raw_info_store,
        contract=contract,
        allow_data_external=allow_data_external,
        environ=environ,
        cycle_id=cycle_id,
    )
    available_source_types = _model_available_source_types(
        evidence_resolver.available_source_types
    )
    evolution_workspace.refresh_capability_backlog(
        available_source_types=available_source_types
    )
    runtime_limits = RuntimeLimits(
        max_signal_rounds=int(limits["max_signal_rounds"]),
        max_signal_calls=int(limits["max_signal_calls"]),
        max_llm_calls=int(limits["max_llm_calls"]),
        max_tokens=int(limits["max_tokens"]),
        max_cost=float(limits["max_case_cost"]),
        max_signals_per_round=int(limits["max_signals_per_round"]),
        max_llm_signals_per_round=int(limits["max_llm_signals_per_round"]),
        finalization_token_reserve=int(limits["finalization_token_reserve"]),
    )
    archive = evolution_workspace.restore_archive(
        expected_run_contract_hash=contract.contract_hash
    )
    meta_memory = evolution_workspace.restore_meta()
    if contract.cycle_mode == "slow_bootstrap":
        if evolution_workspace.last_completed_round != 0 or meta_memory.entries:
            raise ValidationError(
                "committed Fast bootstrap target must keep an empty Fast pointer"
            )
        meta_memory = PlanMetaMemory(entries=bootstrap_meta_entries)
    elif bootstrap_meta_entries:
        # Imported-history reflections are rebased below the local round
        # range, so they prefix the FIFO and never collide with locally
        # committed rounds on first commit or on resume.
        meta_memory = PlanMetaMemory(
            entries=(*bootstrap_meta_entries, *meta_memory.entries)
        )
    signal_runner = StructuredLLMSignalRunner(judge_caller)
    coordinator_signal_agent, coordinator_predictor = _parallel_decision_roles(
        judge_caller,
        parallel_jev_decisions=contract.parallel_jev_decisions,
        environ=environ,
    )
    evaluator = RuntimePlanEvaluator(
        raw_info_store=raw_info_store,
        evidence_resolver=evidence_resolver,
        controller=LLMResearchController(judge_caller),
        signal_agent=coordinator_signal_agent,
        predictor=coordinator_predictor,
        prediction_root=workspace_root / "predictions",
        trajectory_root=evolution_workspace.trajectory_root,
        limits=runtime_limits,
        llm_signal_runner=signal_runner,
        signal_readiness_snapshot=snapshot,
        on_progress=emit,
        cancel_event=cancel_event,
    )
    max_parallel_plans = int(limits.get("max_parallel_plans", 1))

    def build_parallel_evaluator() -> RuntimePlanEvaluator:
        worker_caller = StructuredRoleClient(
            registration=get_model(judge_alias, role="judge"),
            contract=contract,
            workspace=workspace_root,
            ledger=ledger,
            allow_external=allow_external,
            acknowledged_contract_hash=acknowledged_contract_hash,
            environ=environ,
            on_progress=emit,
        )
        worker_store = RawInfoStore(raw_info_root)
        worker_resolver = _build_evidence_resolver(
            workspace_root,
            worker_store,
            contract=contract,
            allow_data_external=allow_data_external,
            environ=environ,
            cycle_id=cycle_id,
        )
        worker_source_types = _model_available_source_types(
            worker_resolver.available_source_types
        )
        if worker_source_types != available_source_types:
            raise ValidationError(
                "parallel evaluator source catalog differs from coordinator"
            )
        worker_signal_agent, worker_predictor = _parallel_decision_roles(
            worker_caller,
            parallel_jev_decisions=contract.parallel_jev_decisions,
            environ=environ,
        )
        return RuntimePlanEvaluator(
            raw_info_store=worker_store,
            evidence_resolver=worker_resolver,
            controller=LLMResearchController(worker_caller),
            signal_agent=worker_signal_agent,
            predictor=worker_predictor,
            prediction_root=workspace_root / "predictions",
            trajectory_root=evolution_workspace.trajectory_root,
            limits=runtime_limits,
            llm_signal_runner=StructuredLLMSignalRunner(worker_caller),
            signal_readiness_snapshot=snapshot,
            on_progress=emit,
            cancel_event=cancel_event,
        )
    plan_proposer = LLMInformationPlanProposer(
        evolution_caller,
        temperature=float(limits["plan_proposal_temperature"]),
        available_source_types=available_source_types,
    )
    plan_proposer.set_request_token_budget(int(limits["max_tokens"]))
    plan_engine = PlanEvolutionEngine(
        archive=archive,
        meta_memory=meta_memory,
        signal_registry=registry,
        evaluator=evaluator,
        proposer=plan_proposer,
        critic=LLMPlanCritic(judge_caller),
        round_reflector=LLMRoundReflector(judge_caller),
        workspace=evolution_workspace,
        seed_plans=(default_information_plan(),),
        warm_start_plans=historical_seed_plans,
        warm_start_parent_evidence=historical_seed_parent_evidence,
        candidates_per_round=int(limits["candidates_per_round"]),
        top_k=int(limits["top_k"]),
        random_k=int(limits["random_k"]),
        similarity_threshold=float(limits["similarity_threshold"]),
        parent_selection_seed=int(limits["parent_selection_seed"]),
        capability_source_types=available_source_types,
        evaluation_config=evaluation_config,
        case_readiness=evaluator.check_case_readiness,
        run_contract_hash=contract.contract_hash,
        on_progress=emit,
        evaluator_factory=(
            build_parallel_evaluator if max_parallel_plans > 1 else None
        ),
        max_parallel_plans=max_parallel_plans,
        cancel_event=cancel_event,
    )
    mining_model = LLMSignalMiningModel(
        evolution_caller,
        creative_temperature=float(limits["plan_proposal_temperature"]),
        h1_max_output_tokens=int(limits["role_output_tokens"]["h1"]),
    )
    mining_model.set_request_token_budget(
        int(limits.get("h1_request_budget", limits["max_tokens"]))
    )
    active_targets = active_research_targets()
    if len(active_targets) > 1:
        raise ValidationError(
            "production Slow currently requires one active magnitude target "
            "per cycle so every candidate has an unambiguous owning axis"
        )
    target_reveal = None
    target_sampling = None
    if active_targets:
        target_contract = active_targets[0]
        target_reveal = build_target_group_manifest(
            dataset.discovery,
            target_contract,
        )
        target_sampling = build_target_sampling_manifest(
            dataset.discovery,
            target_contract,
            cycle_id=cycle_id,
            base_seed=contract.contract_hash,
            dev_limit=max(32, int(limits.get("effectiveness_case_limit", 16))),
            check_limit=int(limits.get("effectiveness_case_limit", 16)),
        )
    signal_engine = SignalEvolutionEngine(
        registry=registry,
        raw_info_store=raw_info_store,
        discovery_cases=dataset.discovery,
        meta_memory=meta_memory,
        workspace=evolution_workspace,
        mining_model=mining_model,
        update_model=LLMSignalUpdateModel(evolution_caller),
        llm_signal_runner=signal_runner,
        identity_cases=(
            *dataset.discovery,
            *dataset.anchor,
            *dataset.evolution_validation,
        ),
        evidence_resolver=evidence_resolver,
        on_progress=emit,
        min_new_signals_per_cycle=contract.min_new_signals_per_cycle,
        research_target_reveal=target_reveal,
        research_target_sampling=target_sampling,
    )
    result = DualLoopEvolutionEngine(
        plan_engine=plan_engine,
        signal_engine=signal_engine,
        signal_registry=registry,
        dataset=dataset,  # type: ignore[arg-type]
        plan_rounds_per_signal_cycle=int(limits["plan_rounds_per_signal_cycle"]),
        cycle_mode=contract.cycle_mode,
        on_progress=emit,
    ).run_cycle(
        cycle_id=cycle_id,
        completed_plan_rounds=completed_plan_rounds,
    )
    slow_result_path = evolution_workspace.stage_slow_result(
        cycle_id=cycle_id,
        result=result.signal_evolution.to_dict(),
    )
    emit(
        {
            "event_type": "slow_loop_result_staged",
            "slow_result_path": str(slow_result_path),
            "validated_candidates": dict(
                result.signal_evolution.validated_candidates
            ),
            "promoted": list(result.signal_evolution.promoted),
        }
    )
    current_snapshot = registry.freeze()
    evolution_workspace.complete_cycle(
        cycle_id=cycle_id,
        observed_signal_registry_version=current_snapshot.version,
        observed_signal_registry_hash=current_snapshot.registry_hash,
    )
    emit(
        {
            "event_type": "cycle_committed",
            "last_completed_round": evolution_workspace.last_completed_round,
            "last_completed_cycle": evolution_workspace.last_completed_cycle,
        }
    )
    return result


def run_bounded_evolution_cycle(
    *,
    workspace_path: str | Path,
    raw_info_root: str | Path,
    approved_dataset_manifest: str | Path,
    contract: EvolutionRunContract,
    allow_external: bool,
    acknowledged_contract_hash: str | None = None,
    allow_data_external: bool = False,
    environ: Mapping[str, str] | None = None,
    on_progress: ProgressCallback | None = None,
) -> DualLoopResult:
    """Run/resume one finite Fast group under an exclusive workspace lock."""

    _validate_cycle_execution_request(
        contract, allow_data_external=allow_data_external
    )
    Path(workspace_path).mkdir(parents=True, exist_ok=True)
    cancel_event = threading.Event()
    restore_stop_handler = (
        install_stop_handler(cancel_event)
        if threading.current_thread() is threading.main_thread()
        else lambda: None
    )
    try:
        with EvolutionWorkspace.execution_lock_at(workspace_path):
            return _run_bounded_evolution_cycle_unlocked(
                workspace_path=workspace_path,
                raw_info_root=raw_info_root,
                approved_dataset_manifest=approved_dataset_manifest,
                contract=contract,
                allow_external=allow_external,
                acknowledged_contract_hash=acknowledged_contract_hash,
                allow_data_external=allow_data_external,
                environ=environ,
                on_progress=on_progress,
                cancel_event=cancel_event,
            )
    finally:
        restore_stop_handler()


def build_run_contract(
    *,
    run_id: str,
    dataset_manifest_path: str | Path,
    inventory: LocalEvolutionInventory,
    raw_info_oracle: RawInfoOracle,
    raw_info_inventory_hash: str,
    initial_signal_registry_version: int,
    initial_signal_registry_hash: str,
    priors: Mapping[str, str],
    role_aliases: Mapping[str, str],
    project_root: str | Path,
    limits: Mapping[str, Any],
    max_external_attempts: int,
    max_total_cost: float,
    seed_pool_manifest_hash: str | None = None,
    cycle_mode: str = "fast_then_slow",
    slow_bootstrap_manifest_hash: str | None = None,
    slow_history_manifest_hash: str | None = None,
    max_slow_cycles: int = 1,
    min_new_signals_per_cycle: int = 1,
    data_acquisition: DataAcquisitionPolicy = DataAcquisitionPolicy(),
    environ: Mapping[str, str] | None = None,
    parallel_jev_decisions: bool = False,
) -> EvolutionRunContract:
    """Build one bounded contract from reviewed, hashed local inputs."""

    manifest_path = Path(dataset_manifest_path)
    manifest = _read_json(manifest_path)
    if manifest.get("approval_status") != "human_approved":
        raise ValidationError("dataset split manifest is not human-approved")
    if manifest.get("locked_test_sealed") is not True:
        raise ValidationError("dataset split manifest must seal Locked Test")
    models = public_model_contract(role_aliases, environ=environ)
    if parallel_jev_decisions:
        env = os.environ if environ is None else environ
        models["jev"] = {
            "alias": "openrouter-jev",
            "provider": "openrouter",
            "provider_identity": "openrouter-decisions",
            "model": DEFAULT_JEV_MODEL,
            "endpoint": DEFAULT_JEV_URL,
            "api_key_env_var": DEFAULT_OPENROUTER_API_KEY_ENV_VAR,
            "api_key_available": bool(env.get(DEFAULT_OPENROUTER_API_KEY_ENV_VAR)),
            "roles": ["parallel_decisions"],
            "web_tools_allowed": False,
        }
    return EvolutionRunContract(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        dataset_manifest_hash=_sha256_file(manifest_path),
        raw_info_oracle_id=raw_info_oracle.oracle_id,
        raw_info_inventory_hash=raw_info_inventory_hash,
        initial_signal_registry_version=initial_signal_registry_version,
        initial_signal_registry_hash=initial_signal_registry_hash,
        priors_hash=_canonical_hash(dict(priors)),
        models=models,
        code_revision=current_code_revision(project_root),
        python_runtime=platform.python_version(),
        limits=dict(limits),
        max_external_attempts=max_external_attempts,
        max_total_cost=max_total_cost,
        seed_pool_manifest_hash=seed_pool_manifest_hash,
        cycle_mode=cycle_mode,
        slow_bootstrap_manifest_hash=slow_bootstrap_manifest_hash,
        slow_history_manifest_hash=slow_history_manifest_hash,
        max_slow_cycles=max_slow_cycles,
        min_new_signals_per_cycle=min_new_signals_per_cycle,
        parallel_jev_decisions=parallel_jev_decisions,
        data_acquisition=data_acquisition,
    )


def _build_evidence_resolver(
    workspace_root: Path,
    store: RawInfoStore,
    *,
    contract: EvolutionRunContract,
    allow_data_external: bool,
    environ: Mapping[str, str] | None,
    cycle_id: int,
) -> EvidenceResolver:
    """Build production adapters over the existing cache/ledger/quota boundary."""

    configured = contract.data_acquisition
    effective_policy = (
        configured
        if configured.enabled and allow_data_external
        else DataAcquisitionPolicy()
    )
    adapters: list[Any] = []
    env = os.environ if environ is None else environ
    config = load_config(environ=env).data_sources
    if effective_policy.enabled:
        cache = RawDataCache(workspace_root / "cache" / "data")
        ledger = RequestLedger(workspace_root / "data_requests.jsonl")
        source_budget = SourceBudget(ledger)

        def managed(source: str, capability: DataCapability) -> ManagedHttpTransport:
            return ManagedHttpTransport(
                source,
                capability,
                UrllibJsonTransport(),
                cache,
                ledger,
                source_budget,
                json_error_detector=(
                    alpha_vantage_json_error
                    if source == "alpha_vantage"
                    else None
                ),
            )

        sec_user_agent = str(env.get("SOA_SEC_USER_AGENT", "")).strip()
        if sec_user_agent:
            sec_facts_client = SecEdgarClient(
                sec_user_agent,
                transport=managed(
                    "sec_edgar", DataCapability.FINANCIAL_STATEMENTS
                ),
            )
            sec_filing_client = SecEdgarClient(
                sec_user_agent,
                transport=managed("sec_edgar", DataCapability.FILING_DOCUMENTS),
            )
            adapters.extend(
                [
                    SecCompanyFactsAdapter(sec_facts_client),
                    SecFilingAdapter(sec_filing_client),
                ]
            )
        else:
            adapters.extend(
                [
                    UnavailableProviderAdapter(
                        "sec_edgar",
                        SecCompanyFactsAdapter.source_types,
                        SecCompanyFactsAdapter.capabilities,
                        "SOA_SEC_USER_AGENT is not configured.",
                        unavailability_reason="sec_user_agent_unconfigured",
                    ),
                    UnavailableProviderAdapter(
                        "sec_edgar",
                        SecFilingAdapter.source_types,
                        SecFilingAdapter.capabilities,
                        "SOA_SEC_USER_AGENT is not configured.",
                        unavailability_reason="sec_user_agent_unconfigured",
                    ),
                ]
            )
        alpha_key = env.get(config.alpha_vantage_api_key_env_var)
        alpha_price_adapter: Any
        if alpha_key:
            alpha_news = AlphaVantageClient(
                alpha_key,
                transport=managed("alpha_vantage", DataCapability.NEWS),
            )
            alpha_prices = AlphaVantageClient(
                alpha_key,
                transport=managed("alpha_vantage", DataCapability.PRICE_DAILY),
            )
            alpha_transcripts = AlphaVantageClient(
                alpha_key,
                transport=managed("alpha_vantage", DataCapability.TRANSCRIPTS),
            )
            adapters.extend(
                [
                    AlphaVantageNewsAdapter(alpha_news),
                    AlphaVantageTranscriptAdapter(alpha_transcripts),
                ]
            )
            alpha_price_adapter = HistoricalPriceAdapter(
                "alpha_vantage",
                lambda symbol, _start, _end: alpha_prices.daily_prices(
                    symbol, outputsize="full"
                ),
                event_source=alpha_prices,
            )
        else:
            adapters.append(
                UnavailableProviderAdapter(
                    "alpha_vantage",
                    ("news", "company_news"),
                    ("news",),
                    f"{config.alpha_vantage_api_key_env_var} is not configured.",
                )
            )
            adapters.append(
                UnavailableProviderAdapter(
                    "alpha_vantage",
                    AlphaVantageTranscriptAdapter.source_types,
                    AlphaVantageTranscriptAdapter.capabilities,
                    f"{config.alpha_vantage_api_key_env_var} is not configured.",
                )
            )
            alpha_price_adapter = UnavailableProviderAdapter(
                "alpha_vantage",
                HistoricalPriceAdapter.source_types,
                ("price_daily",),
                f"{config.alpha_vantage_api_key_env_var} is not configured.",
            )
        finnhub_key = env.get(config.finnhub_api_key_env_var)
        if finnhub_key:
            adapters.append(FinnhubNewsAdapter(FinnhubClient(
                finnhub_key, transport=managed("finnhub", DataCapability.NEWS),
            )))
        massive_key = env.get(config.massive_api_key_env_var)
        massive_price_adapter: Any
        if massive_key:
            massive = MassiveClient(
                massive_key,
                transport=managed("massive", DataCapability.PRICE_DAILY),
            )
            massive_price_adapter = HistoricalPriceAdapter(
                "massive",
                lambda symbol, start, end: massive.daily_prices(
                    symbol, start_date=start, end_date=end
                ),
                event_source=massive,
            )
        else:
            massive_price_adapter = UnavailableProviderAdapter(
                "massive",
                HistoricalPriceAdapter.source_types,
                ("price_daily",),
                f"{config.massive_api_key_env_var} is not configured.",
            )
        adapters.append(massive_price_adapter)
        stooq = StooqClient(
            api_key=env.get(config.stooq_api_key_env_var),
            transport=managed("stooq", DataCapability.PRICE_DAILY),
        )
        adapters.append(
            HistoricalPriceAdapter(
                "stooq",
                lambda symbol, start, end: stooq.daily_prices(
                    symbol, start_date=start, end_date=end
                ),
                event_source=stooq,
            )
        )
        adapters.append(alpha_price_adapter)
    else:
        # Adapter descriptors are still present so a local miss is correctly
        # classified as unauthorized rather than as an unknown capability.
        adapters.extend(
            [
                SecCompanyFactsAdapter(None),
                SecFilingAdapter(None),
                AlphaVantageNewsAdapter(None),
                FinnhubNewsAdapter(None),
                AlphaVantageTranscriptAdapter(None),
                HistoricalPriceAdapter("massive", lambda *_: ()),
            ]
        )
    adapters.append(
        HistoricalUnavailableAdapter(
            "alpha_vantage",
            ("company_profile", "company_overview"),
        )
    )
    return EvidenceResolver(
        store,
        adapters=adapters,
        policy=effective_policy,
        budget=DataAcquisitionBudget(
            ledger_path=workspace_root / "data_acquisition_requests.jsonl",
            cycle_id=cycle_id,
        ),
    )


def _default_priors_dict() -> dict[str, str]:
    return {
        "reflect_round": DEFAULT_EVOLUTION_PRIORS.reflect_round,
        "propose_plan": DEFAULT_EVOLUTION_PRIORS.propose_plan,
        "mine_signal": DEFAULT_EVOLUTION_PRIORS.mine_signal,
        "update_signal": DEFAULT_EVOLUTION_PRIORS.update_signal,
    }
