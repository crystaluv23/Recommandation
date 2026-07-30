"""Data contracts and protocols for information-scheme evolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Protocol

from stock_opportunity_agent.models import SerializableRecord, ValidationError


SCHEME_EVOLUTION_SCHEMA_VERSION = "scheme-evolution-v0.1"
_BLIND_FORBIDDEN_VARIABLES = {
    "label",
    "outcome",
    "outcome_return",
    "forward_return",
    "winner",
    "control",
    "sealed_test",
}


class MutationOperator(str, Enum):
    """Supported ways to produce a child information-scheme genome."""

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
    """Evolvable signal recipe kept distinct from extracted facts."""

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
    """Versioned prompt contract with a content-derived hash."""

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
    """Evolvable information recipe; fixed evaluation rules are excluded."""

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
        if not self.data_source_specs:
            raise ValidationError("genome requires at least one data source")
        for key in ("max_sources", "max_signals", "max_context_tokens", "max_estimated_cost_usd"):
            if key not in self.complexity_budget:
                raise ValidationError(f"genome complexity_budget missing {key}")
            if float(self.complexity_budget[key]) < 0:
                raise ValidationError(f"genome complexity_budget.{key} cannot be negative")


@dataclass(frozen=True)
class MaterializedScheme(SerializableRecord):
    """One genome learned only from one discovery fold."""

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
class PredictionRecord(SerializableRecord):
    """Persisted blind prediction written before labels are evaluated."""

    genome_id: str
    materialized_scheme_id: str
    fold_id: str
    sample_id: str
    prediction_time: datetime
    probability_of_surge: float
    binary_decision: str
    confidence: str
    supporting_signals: list[str]
    contradicting_signals: list[str]
    missing_information: list[str]
    difficulty_codes: list[str]
    evidence_source_ids: list[str]
    model_metadata: dict[str, Any]
    raw_response_location: str | None

    def __post_init__(self) -> None:
        for name in (
            "genome_id",
            "materialized_scheme_id",
            "fold_id",
            "sample_id",
            "binary_decision",
            "confidence",
        ):
            _require_text(getattr(self, name), name)
        if not 0 <= self.probability_of_surge <= 1:
            raise ValidationError("probability_of_surge must be between 0 and 1")
        if self.binary_decision not in {"positive", "negative", "abstain"}:
            raise ValidationError("binary_decision must be positive, negative, or abstain")
        if self.confidence not in {"low", "medium", "high"}:
            raise ValidationError("confidence must be low, medium, or high")


@dataclass(frozen=True)
class SchemeEvaluationResult(SerializableRecord):
    """Deterministic metrics for one genome on label-hidden predictions."""

    genome_id: str
    sample_count: int
    confusion_matrix: dict[str, int]
    precision: float
    recall: float
    f1: float
    pr_auc: float
    roc_auc: float
    brier_score: float
    log_loss: float
    precision_at_k: float
    recall_at_k: float
    coverage_rate: float
    abstention_rate: float
    metrics_by_time_period: dict[str, dict[str, float]]
    metrics_by_sector: dict[str, dict[str, float]]
    metrics_by_market_cap_bucket: dict[str, dict[str, float]]
    model_provider_sensitivity: dict[str, float]
    data_cost_usd: float
    token_cost_usd: float
    latency_ms: float
    confidence_intervals: dict[str, list[float]]
    worst_period_f1: float
    primary_utility: float


@dataclass(frozen=True)
class AdmissionDecision(SerializableRecord):
    """Paired statistical admission decision against the incumbent."""

    status: str
    admitted: bool
    utility_difference: float
    confidence_interval: list[float]
    paired_block_count: int
    reasons: list[str]


@dataclass(frozen=True)
class SchemeExperimentRecord(SerializableRecord):
    """Detailed candidate experiment beneath the canonical meta-learning record."""

    experiment_id: str
    parent_genome_ids: list[str]
    candidate_genome_id: str
    mutation_operator: MutationOperator
    data_split_version: str
    label_spec_version: str
    configuration_hashes: dict[str, str]
    evaluation_result: SchemeEvaluationResult
    admission_decision: AdmissionDecision
    failure_reason: str | None
    started_at: datetime
    completed_at: datetime
    git_commit: str | None


@dataclass(frozen=True)
class MetaLesson(SerializableRecord):
    """Bounded, structured evidence for future proposal rounds."""

    lesson: str
    scope: str
    supporting_experiment_ids: list[str]
    positive_cases_count: int
    counterexamples_count: int
    estimated_effect: float
    confidence: float
    suggested_mutation_operators: list[MutationOperator]
    created_at: datetime
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.lesson, "meta lesson")
        _require_text(self.scope, "meta lesson scope")
        if self.positive_cases_count < 0 or self.counterexamples_count < 0:
            raise ValidationError("meta lesson case counts cannot be negative")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("meta lesson confidence must be between 0 and 1")


@dataclass(frozen=True)
class MutationRequest(SerializableRecord):
    """A bounded request routed from failure attribution to the proposer."""

    operator: MutationOperator
    target_fields: list[str]
    reason: str


@dataclass(frozen=True)
class LabelSpec(SerializableRecord):
    """Fixed surge-label observation contract."""

    version: str
    horizon_days: int
    positive_label: int = 1

    def __post_init__(self) -> None:
        _require_text(self.version, "label spec version")
        if self.horizon_days < 1:
            raise ValidationError("label horizon_days must be positive")
        if self.positive_label != 1:
            raise ValidationError("the initial binary evaluator requires positive_label=1")


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
    """Fixed metrics and admission policy excluded from every genome."""

    version: str
    positive_threshold: float = 0.5
    top_k: int = 5
    bootstrap_replicates: int = 400
    confidence_level: float = 0.9
    minimum_paired_blocks: int = 4
    minimum_coverage: float = 0.75
    maximum_worst_period_degradation: float = 0.1
    maximum_cost_usd: float = 20.0
    utility_weights: dict[str, float] = field(
        default_factory=lambda: {
            "pr_auc": 0.35,
            "precision_at_k": 0.2,
            "recall_at_k": 0.15,
            "brier_score": -0.15,
            "worst_period_f1": 0.15,
            "cost_usd": -0.02,
            "complexity": -0.01,
        }
    )
    bootstrap_seed: int = 20260731

    def __post_init__(self) -> None:
        _require_text(self.version, "evaluation spec version")
        if not 0 < self.positive_threshold < 1:
            raise ValidationError("positive_threshold must be between 0 and 1")
        if self.top_k < 1 or self.bootstrap_replicates < 20:
            raise ValidationError("top_k must be positive and bootstrap_replicates at least 20")
        if not 0 < self.confidence_level < 1:
            raise ValidationError("confidence_level must be between 0 and 1")
        if self.minimum_paired_blocks < 2:
            raise ValidationError("minimum_paired_blocks must be at least two")
        if not 0 <= self.minimum_coverage <= 1:
            raise ValidationError("minimum_coverage must be between 0 and 1")


@dataclass(frozen=True)
class FixedEvolutionSpec(SerializableRecord):
    """All non-evolvable rules supplied to the engine."""

    label_spec: LabelSpec
    split_spec: DataSplitSpec
    evaluation_spec: EvaluationSpec

    @property
    def content_hash(self) -> str:
        """Return one deterministic hash covering every fixed rule."""

        return _hash_json(self.to_dict())


@dataclass(frozen=True)
class LabeledSample(SerializableRecord):
    """Internal sample whose label is never exposed through :meth:`blind_view`."""

    sample_id: str
    company_key: str
    prediction_time: datetime
    label: int
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
        if self.label not in {0, 1}:
            raise ValidationError("evolution sample label must be binary")
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
    """Admission input with no label, outcome, ticker, or company name."""

    sample_id: str
    company_key: str
    prediction_time: datetime
    sector: str
    market_cap_bucket: str
    period: str
    features: dict[str, float]
    evidence_source_ids: list[str]


@dataclass(frozen=True)
class EvolutionFold(SerializableRecord):
    """One expanding-window discovery/admission fold."""

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
    """Candidate source independent of any interactive model session."""

    def propose(
        self,
        parents: list[SchemeGenome],
        meta_memory: list[MetaLesson],
        mutation_requests: list[MutationRequest],
        count: int,
    ) -> list[SchemeGenome]:
        """Return at most ``count`` candidate genomes."""


class SchemeFoldEvaluator(Protocol):
    """Adapter from genomes into existing materialization and blind analysis."""

    @property
    def evaluator_fingerprint(self) -> str:
        """Return the version/provider/settings hash used by resume checks."""

    def materialize(self, genome: SchemeGenome, fold: EvolutionFold) -> MaterializedScheme:
        """Learn a concrete scheme using discovery labels from this fold only."""

    def predict(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> PredictionRecord:
        """Predict from one label-free admission sample."""




def _hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_anonymous_id(value: str) -> str:
    return "anon_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be non-empty")
