"""Immutable contracts for resumable information-scheme evolution.

The fixed evaluation contract is deliberately separate from ``SchemeGenome``:
candidate generation may change information collection, signal discovery, and
analysis instructions, but it cannot change labels, splits, or scoring rules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Protocol

from stock_opportunity_agent.models import SerializableRecord, ValidationError


SCHEME_EVOLUTION_SCHEMA_VERSION = "scheme-evolution-v0.2"
OUTCOME_CLASSES = ("A", "B", "C")
POSITIVE_CLASSES = ("B", "C")
_BLIND_FORBIDDEN_VARIABLES = {
    "label",
    "outcome",
    "outcome_return",
    "forward_return",
    "future_price",
    "realized_max_multiple",
    "true_class",
    "is_surge",
    "winner",
    "control",
    "sealed_test",
    "final_test",
}


class MutationOperator(str, Enum):
    """Supported bounded mutations of an information-scheme genome."""

    LOCAL_REFINE = "local_refine"
    ABLATION = "ablation"
    SOURCE_EXPAND = "source_expand"
    SOURCE_REPLACE = "source_replace"
    SIGNAL_SPLIT = "signal_split"
    SIGNAL_MERGE = "signal_merge"
    COUNTEREXAMPLE_REPAIR = "counterexample_repair"
    CROSSOVER = "crossover"
    ORTHOGONAL_REDESIGN = "orthogonal_redesign"
    COST_COMPRESS = "cost_compress"
    ROBUSTNESS_MUTATION = "robustness_mutation"
    RANDOM_RESTART = "random_restart"


@dataclass(frozen=True)
class DataSourceSpec(SerializableRecord):
    """One source family and its point-in-time retrieval contract."""

    source_id: str
    source_family: str
    retrieval_rule: str
    cutoff_rule: str
    required: bool
    freshness_days: int | None
    estimated_cost_usd: float
    failure_policy: str

    def __post_init__(self) -> None:
        for name in (
            "source_id",
            "source_family",
            "retrieval_rule",
            "cutoff_rule",
            "failure_policy",
        ):
            _require_text(getattr(self, name), name)
        if self.freshness_days is not None and self.freshness_days < 0:
            raise ValidationError("freshness_days cannot be negative")
        if self.estimated_cost_usd < 0:
            raise ValidationError("estimated_cost_usd cannot be negative")


@dataclass(frozen=True)
class SignalSpec(SerializableRecord):
    """Executable, falsifiable signal recipe kept separate from source facts."""

    signal_id: str
    name: str
    hypothesis: str
    required_sources: list[str]
    observation_cutoff_rule: str
    extraction_rule: str
    value_type: str
    direction: str
    horizon_days: int
    decay_days: int
    minimum_evidence: int
    contradictory_evidence_rule: str
    confounders: list[str]
    missing_value_policy: str
    evidence_schema: dict[str, Any]
    version: str

    def __post_init__(self) -> None:
        for name in (
            "signal_id",
            "name",
            "hypothesis",
            "observation_cutoff_rule",
            "extraction_rule",
            "value_type",
            "direction",
            "contradictory_evidence_rule",
            "missing_value_policy",
            "version",
        ):
            _require_text(getattr(self, name), name)
        if self.horizon_days < 1 or self.decay_days < 0:
            raise ValidationError("signal horizon_days must be positive and decay_days non-negative")
        if self.minimum_evidence < 1:
            raise ValidationError("signal minimum_evidence must be positive")
        if not self.required_sources:
            raise ValidationError("signal requires at least one source")
        if not self.evidence_schema:
            raise ValidationError("signal evidence_schema must not be empty")


@dataclass(frozen=True)
class PromptSpec(SerializableRecord):
    """Versioned prompt contract with a deterministic content hash."""

    template: str
    variables: list[str]
    output_json_schema: dict[str, Any]
    model_constraints: dict[str, Any]
    version: str
    content_hash: str = ""

    def __post_init__(self) -> None:
        _require_text(self.template, "prompt template")
        _require_text(self.version, "prompt version")
        if not self.output_json_schema:
            raise ValidationError("prompt output_json_schema must not be empty")
        expected = _hash_json(
            {
                "template": self.template,
                "variables": self.variables,
                "output_json_schema": self.output_json_schema,
                "model_constraints": self.model_constraints,
                "version": self.version,
            }
        )
        if self.content_hash and self.content_hash != expected:
            raise ValidationError("prompt content_hash does not match prompt content")
        object.__setattr__(self, "content_hash", expected)


@dataclass(frozen=True)
class SchemeGenome(SerializableRecord):
    """Evolvable ``(data, signal, analysis)`` recipe with fixed rules excluded."""

    genome_id: str
    parent_ids: list[str]
    generation: int
    mutation_operator: MutationOperator
    hypothesis_of_change: str
    changed_fields: list[str]
    expected_benefit: str
    possible_side_effects: list[str]
    falsification_test: str
    data_source_specs: list[DataSourceSpec]
    contrastive_discovery_prompt: PromptSpec
    seed_signal_specs: list[SignalSpec]
    signal_merge_prompt: PromptSpec
    blind_analysis_prompt: PromptSpec
    complexity_budget: dict[str, float | int]
    metadata: dict[str, Any]
    target_failure_type: str = "general"
    schema_version: str = SCHEME_EVOLUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "genome_id",
            "hypothesis_of_change",
            "expected_benefit",
            "falsification_test",
            "schema_version",
        ):
            _require_text(getattr(self, name), name)
        if self.generation < 0:
            raise ValidationError("genome generation cannot be negative")
        if self.target_failure_type not in {
            "false_positive",
            "false_negative",
            "class_c_miss",
            "general",
        }:
            raise ValidationError("invalid target_failure_type")
        if not self.data_source_specs:
            raise ValidationError("genome requires at least one data source")
        for key in (
            "max_sources",
            "max_signals",
            "max_context_tokens",
            "max_estimated_cost_usd",
        ):
            if key not in self.complexity_budget:
                raise ValidationError(f"genome complexity_budget missing {key}")
            if float(self.complexity_budget[key]) < 0:
                raise ValidationError(f"genome complexity_budget.{key} cannot be negative")


@dataclass(frozen=True)
class MaterializedScheme(SerializableRecord):
    """Signals discovered on one training fold and frozen before validation."""

    materialized_scheme_id: str
    genome_id: str
    fold_id: str
    discovered_signals: list[SignalSpec]
    retained_signals: list[SignalSpec]
    rejected_signals: list[dict[str, str]]
    materialization_inputs_hash: str
    output_hash: str

    def __post_init__(self) -> None:
        for name in (
            "materialized_scheme_id",
            "genome_id",
            "fold_id",
            "materialization_inputs_hash",
            "output_hash",
        ):
            _require_text(getattr(self, name), name)


@dataclass(frozen=True)
class EvaluationContract(SerializableRecord):
    """Frozen six-month A/B/C exam that candidate schemes cannot mutate."""

    version: str = "six-month-max-multiple-v1"
    horizon_months: int = 6
    price_field: str = "adjusted_close"
    multiple_calculation_type: str = "max_future_price_ratio"
    smoothing_window_days: int = 5
    class_boundaries: dict[str, dict[str, float | None]] | None = None
    positive_classes: list[str] | None = None
    primary_metric: str = "binary_f1"
    diagnostic_metrics: list[str] | None = None

    def __post_init__(self) -> None:
        boundaries = self.class_boundaries or {
            "A": {"min_inclusive": 0.0, "max_exclusive": 2.0},
            "B": {"min_inclusive": 2.0, "max_exclusive": 3.0},
            "C": {"min_inclusive": 3.0, "max_exclusive": None},
        }
        diagnostics = self.diagnostic_metrics or [
            "binary_precision",
            "binary_recall",
            "multiclass_macro_f1",
            "class_c_recall",
            "ordinal_distance",
        ]
        positives = self.positive_classes or list(POSITIVE_CLASSES)
        object.__setattr__(self, "class_boundaries", boundaries)
        object.__setattr__(self, "positive_classes", positives)
        object.__setattr__(self, "diagnostic_metrics", diagnostics)
        _require_text(self.version, "evaluation contract version")
        if self.horizon_months != 6:
            raise ValidationError("v1 evaluation contract requires horizon_months=6")
        if self.price_field != "adjusted_close":
            raise ValidationError("v1 evaluation contract requires adjusted_close")
        if self.multiple_calculation_type != "max_future_price_ratio":
            raise ValidationError("invalid multiple calculation type")
        if self.smoothing_window_days != 5:
            raise ValidationError("v1 evaluation contract requires five-day smoothing")
        expected_boundaries = {
            "A": {"min_inclusive": 0.0, "max_exclusive": 2.0},
            "B": {"min_inclusive": 2.0, "max_exclusive": 3.0},
            "C": {"min_inclusive": 3.0, "max_exclusive": None},
        }
        if boundaries != expected_boundaries:
            raise ValidationError("v1 A/B/C class boundaries are fixed")
        if positives != list(POSITIVE_CLASSES):
            raise ValidationError("v1 positive classes are fixed to B and C")
        if self.primary_metric != "binary_f1":
            raise ValidationError("v1 primary metric is fixed to binary_f1")

    @property
    def content_hash(self) -> str:
        """Return a deterministic hash of every fixed exam field."""

        return _hash_json(self.to_dict())

    def classify(self, realized_max_multiple: float) -> str:
        """Map a continuous realized multiple into the fixed ordinal class."""

        if realized_max_multiple < 0:
            raise ValidationError("realized_max_multiple cannot be negative")
        if realized_max_multiple < 2.0:
            return "A"
        if realized_max_multiple < 3.0:
            return "B"
        return "C"

    def is_positive(self, outcome_class: str) -> bool:
        """Return the fixed binary interpretation of an A/B/C class."""

        if outcome_class not in OUTCOME_CLASSES:
            raise ValidationError("outcome class must be A, B, or C")
        return outcome_class in POSITIVE_CLASSES


@dataclass(frozen=True)
class DataSplitSpec(SerializableRecord):
    """Fixed walk-forward, purge, and embargo contract."""

    version: str
    purge_days: int
    embargo_days: int
    block_field: str = "period"

    def __post_init__(self) -> None:
        _require_text(self.version, "data split version")
        if self.purge_days < 0 or self.embargo_days < 0:
            raise ValidationError("purge and embargo days cannot be negative")


@dataclass(frozen=True)
class EvaluationSpec(SerializableRecord):
    """Fixed Top-K and cost controls outside every candidate genome."""

    version: str
    top_k: int = 5
    prediction_similarity_threshold: float = 0.95
    maximum_cost_usd: float = 20.0

    def __post_init__(self) -> None:
        _require_text(self.version, "evaluation spec version")
        if self.top_k < 1:
            raise ValidationError("top_k must be positive")
        if not 0 <= self.prediction_similarity_threshold <= 1:
            raise ValidationError("prediction_similarity_threshold must be between zero and one")
        if self.maximum_cost_usd < 0:
            raise ValidationError("maximum_cost_usd cannot be negative")


@dataclass(frozen=True)
class FixedEvolutionSpec(SerializableRecord):
    """All non-evolvable rules supplied to the engine."""

    evaluation_contract: EvaluationContract
    split_spec: DataSplitSpec
    evaluation_spec: EvaluationSpec

    @property
    def content_hash(self) -> str:
        """Return one deterministic hash covering every fixed rule."""

        return _hash_json(self.to_dict())


@dataclass(frozen=True)
class LabeledSample(SerializableRecord):
    """Internal labeled sample; only :meth:`blind_view` enters prediction."""

    sample_id: str
    company_key: str
    prediction_time: datetime
    realized_max_multiple: float
    true_class: str
    is_surge: bool
    sector: str
    market_cap_bucket: str
    period: str
    features: dict[str, float]
    evidence_source_ids: list[str]
    document_available_dates: list[date]

    def __post_init__(self) -> None:
        for name in (
            "sample_id",
            "company_key",
            "sector",
            "market_cap_bucket",
            "period",
        ):
            _require_text(getattr(self, name), name)
        contract = EvaluationContract()
        if self.true_class != contract.classify(self.realized_max_multiple):
            raise ValidationError("true_class does not match realized_max_multiple")
        if self.is_surge != contract.is_positive(self.true_class):
            raise ValidationError("is_surge does not match true_class")
        future_dates = [
            available
            for available in self.document_available_dates
            if available > self.prediction_time.date()
        ]
        if future_dates:
            raise ValidationError("sample contains a document available after prediction_time")

    def blind_view(self) -> "BlindSample":
        """Return the only sample shape allowed into a blind evaluator."""

        return BlindSample(
            sample_id=self.sample_id,
            company_key=_stable_anonymous_id(self.company_key),
            prediction_time=self.prediction_time,
            sector=self.sector,
            market_cap_bucket=self.market_cap_bucket,
            period=self.period,
            features=dict(self.features),
            evidence_source_ids=list(self.evidence_source_ids),
        )


@dataclass(frozen=True)
class BlindSample(SerializableRecord):
    """Validation input with no labels, outcomes, ticker, or company name."""

    sample_id: str
    company_key: str
    prediction_time: datetime
    sector: str
    market_cap_bucket: str
    period: str
    features: dict[str, float]
    evidence_source_ids: list[str]


@dataclass(frozen=True)
class PredictionRecord(SerializableRecord):
    """One persisted A/B/C prediction written before labels are revealed."""

    genome_id: str
    materialized_scheme_id: str
    fold_id: str
    sample_id: str
    prediction_time: datetime
    predicted_class: str
    is_surge: bool
    confidence_level: str
    difficulty_level: str
    difficulty_reasons: list[str]
    decisive_signals: list[str]
    conflicting_signals: list[str]
    missing_information: list[str]
    flip_conditions: list[str]
    evidence_source_ids: list[str]
    model_metadata: dict[str, Any]
    input_hash: str
    raw_response_location: str | None

    def __post_init__(self) -> None:
        for name in (
            "genome_id",
            "materialized_scheme_id",
            "fold_id",
            "sample_id",
            "input_hash",
        ):
            _require_text(getattr(self, name), name)
        contract = EvaluationContract()
        if self.predicted_class not in OUTCOME_CLASSES:
            raise ValidationError("predicted_class must be A, B, or C")
        if self.is_surge != contract.is_positive(self.predicted_class):
            raise ValidationError("predicted is_surge must be derived from predicted_class")
        if self.confidence_level not in {"low", "medium", "high"}:
            raise ValidationError("invalid confidence_level")
        if self.difficulty_level not in {"low", "medium", "high"}:
            raise ValidationError("invalid difficulty_level")


@dataclass(frozen=True)
class SchemeEvaluationResult(SerializableRecord):
    """Deterministic A/B/C metrics and structured validation diagnostics."""

    genome_id: str
    sample_count: int
    confusion_matrix: dict[str, int]
    binary_precision: float
    binary_recall: float
    binary_f1: float
    multiclass_confusion_matrix: dict[str, dict[str, int]]
    per_class_recall: dict[str, float]
    multiclass_macro_f1: float
    class_c_recall: float
    ordinal_distance: float
    error_cases: list[dict[str, Any]]
    reflection_summary: dict[str, Any]
    predictions_by_sample: dict[str, str]
    binary_predictions_by_sample: dict[str, bool]
    metrics_by_time_period: dict[str, dict[str, float]]
    metrics_by_sector: dict[str, dict[str, float]]
    metrics_by_market_cap_bucket: dict[str, dict[str, float]]
    data_cost_usd: float
    token_cost_usd: float
    latency_ms: float
    primary_metric: str = "binary_f1"

    @property
    def primary_score(self) -> float:
        """Return the only v1 Top-K score."""

        return self.binary_f1


@dataclass(frozen=True)
class AdmissionDecision(SerializableRecord):
    """Top-K retention decision; all retained schemes remain proposals."""

    status: str
    admitted: bool
    primary_metric_delta: float
    diagnostic_metric_deltas: dict[str, float]
    reasons: list[str]


@dataclass(frozen=True)
class SchemeExperimentRecord(SerializableRecord):
    """Detailed child-versus-parent experiment record."""

    experiment_id: str
    parent_genome_ids: list[str]
    candidate_genome_id: str
    mutation_operator: MutationOperator
    data_split_version: str
    evaluation_contract_hash: str
    configuration_hashes: dict[str, str]
    evaluation_result: SchemeEvaluationResult
    admission_decision: AdmissionDecision
    failure_reason: str | None
    started_at: datetime
    completed_at: datetime
    git_commit: str | None


@dataclass(frozen=True)
class MetaLesson(SerializableRecord):
    """Structured cross-iteration hypothesis with explicit experiment status."""

    observation: str
    evidence: dict[str, Any]
    diagnosed_issue: str
    tested_change: str
    metric_delta: dict[str, float]
    status: str
    confidence: float
    supporting_experiment_ids: list[str]
    suggested_mutation_operators: list[MutationOperator]
    created_at: datetime
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        for name in ("observation", "diagnosed_issue", "tested_change"):
            _require_text(getattr(self, name), name)
        if self.status not in {"hypothesis", "validated", "rejected"}:
            raise ValidationError("meta lesson status must be hypothesis, validated, or rejected")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("meta lesson confidence must be between 0 and 1")


@dataclass(frozen=True)
class MutationRequest(SerializableRecord):
    """A bounded request routed from an observed failure to the proposer."""

    operator: MutationOperator
    target_fields: list[str]
    reason: str


@dataclass(frozen=True)
class EvolutionFold(SerializableRecord):
    """One expanding-window signal-train/validation fold."""

    fold_id: str
    discovery_samples: list[LabeledSample]
    admission_samples: list[LabeledSample]
    admission_start: datetime

    def __post_init__(self) -> None:
        _require_text(self.fold_id, "fold id")
        if not self.discovery_samples or not self.admission_samples:
            raise ValidationError("evolution fold requires discovery and admission samples")
        discovery_companies = {sample.company_key for sample in self.discovery_samples}
        admission_companies = {sample.company_key for sample in self.admission_samples}
        if discovery_companies & admission_companies:
            raise ValidationError("discovery and admission companies must be disjoint")


class SchemeProposer(Protocol):
    """Candidate source independent of any one model provider."""

    def propose(
        self,
        parents: list[SchemeGenome],
        meta_memory: list[MetaLesson],
        mutation_requests: list[MutationRequest],
        count: int,
    ) -> list[SchemeGenome]:
        """Return at most ``count`` candidate genomes."""


class SchemeFoldEvaluator(Protocol):
    """Adapter from genomes to discovery, extraction, and blind analysis."""

    @property
    def evaluator_fingerprint(self) -> str:
        """Return the provider/model/settings hash used by resume checks."""

    def materialize(self, genome: SchemeGenome, fold: EvolutionFold) -> MaterializedScheme:
        """Discover and freeze signals using signal-train labels only."""

    def restore(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        fold: EvolutionFold,
    ) -> None:
        """Restore transient packet state without rediscovering frozen signals."""

    def extract(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> dict[str, Any]:
        """Return label-free frozen-signal extraction input for one sample."""

    def predict(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> PredictionRecord:
        """Predict from one label-free validation sample."""


def _hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_anonymous_id(value: str) -> str:
    return "anon_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be non-empty")
