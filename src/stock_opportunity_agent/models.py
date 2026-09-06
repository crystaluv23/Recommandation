"""Shared serializable domain records for the stock opportunity agent.

The records in this module are intentionally dependency-free so every other
module can import them without pulling in data vendors, LLM clients, or storage
drivers.
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import re
from types import UnionType
from typing import Any, ClassVar, Literal, Mapping, TypeVar, Union, get_args, get_origin, get_type_hints


class ValidationError(ValueError):
    """Raised when a domain record violates its contract."""


@dataclass(frozen=True)
class ValidationIssue:
    """Machine-readable repair boundary for one validation obligation."""

    code: str
    message: str
    paths: tuple[str, ...] = ()
    item_id: str | None = None
    item_id_field: str | None = None
    severity: str = "error"
    retryability: str = "correctable"
    path_policy: str = "all"
    allowed_repairs: tuple[str, ...] = ("replace",)
    dependent_paths: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.code or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
            for character in self.code
        ):
            raise ValueError("validation issue code must be lowercase snake_case")
        if not self.message.strip():
            raise ValueError("validation issue message must not be empty")
        if self.severity not in {"error", "warning"}:
            raise ValueError("validation issue severity is invalid")
        if self.retryability not in {"correctable", "terminal"}:
            raise ValueError("validation issue retryability is invalid")
        if self.path_policy not in {"all", "any"}:
            raise ValueError("validation issue path_policy is invalid")
        if not self.allowed_repairs or any(
            repair not in {"replace", "remove", "quarantine"}
            for repair in self.allowed_repairs
        ):
            raise ValueError("validation issue allowed repairs are invalid")
        for values, name in (
            (self.paths, "paths"),
            (self.dependent_paths, "dependent_paths"),
            (self.source_refs, "source_refs"),
        ):
            normalized = tuple(str(value) for value in values)
            if any(not value for value in normalized) or len(set(normalized)) != len(
                normalized
            ):
                raise ValueError(f"validation issue {name} must be unique and non-empty")
            object.__setattr__(self, name, normalized)
        if not self.paths:
            raise ValueError("validation issue requires at least one path")
        object.__setattr__(
            self,
            "allowed_repairs",
            tuple(dict.fromkeys(str(value) for value in self.allowed_repairs)),
        )
        if self.item_id is not None and not self.item_id.strip():
            raise ValueError("validation issue item_id must be omitted or non-empty")
        if (self.item_id is None) != (self.item_id_field is None):
            raise ValueError(
                "validation issue item_id and item_id_field must be set together"
            )
        if self.item_id_field is not None and (
            not self.item_id_field
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.item_id_field) is None
        ):
            raise ValueError("validation issue item_id_field is invalid")

    def to_dict(self) -> dict[str, Any]:
        """Return the exact correction-facing issue record."""

        value: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "paths": list(self.paths),
            "severity": self.severity,
            "retryability": self.retryability,
            "path_policy": self.path_policy,
            "allowed_repairs": list(self.allowed_repairs),
            "dependent_paths": list(self.dependent_paths),
            "source_refs": list(self.source_refs),
        }
        if self.item_id is not None:
            value["item_id"] = self.item_id
            value["item_id_field"] = self.item_id_field
        return value


class StructuredValidationError(ValidationError):
    """Validation failure whose repair authority is carried by typed issues."""

    def __init__(self, issues: tuple[ValidationIssue, ...] | list[ValidationIssue]):
        materialized = tuple(issues)
        if not materialized:
            raise ValueError("structured validation requires at least one issue")
        super().__init__("; ".join(issue.message for issue in materialized))
        self.issues = materialized


class DataQuality(str, Enum):
    """Point-in-time data quality state."""

    MISSING = "missing"
    STALE = "stale"
    ESTIMATED = "estimated"
    CONFIRMED = "confirmed"


class EvidenceKind(str, Enum):
    """Evidence provenance category."""

    FILING = "filing"
    TRANSCRIPT = "transcript"
    NEWS = "news"
    RESEARCH_REPORT = "research_report"
    THEME_CONTEXT = "theme_context"
    PRICE_VOLUME = "price_volume"
    FINANCIAL = "financial"
    VALUATION = "valuation"
    MEMORY = "memory"
    INFERENCE = "inference"


class CatalystStatus(str, Enum):
    """Lifecycle status for a catalyst."""

    EXPECTED = "expected"
    CONFIRMED = "confirmed"
    DELAYED = "delayed"
    MISSED = "missed"


class ThesisStatus(str, Enum):
    """Lifecycle status for a thesis."""

    DRAFT = "draft"
    ACTIVE = "active"
    CHALLENGED = "challenged"
    RETIRED = "retired"


class RecommendationState(str, Enum):
    """Watchlist state, deliberately separate from trading states."""

    IGNORE = "ignore"
    MONITOR = "monitor"
    HIGH_PRIORITY_WATCHLIST = "high_priority_watchlist"
    ACTION_CANDIDATE = "action_candidate"


class ReviewOutcome(str, Enum):
    """Outcome label for later thesis review."""

    TOO_EARLY = "too_early"
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    DISCONFIRMED = "disconfirmed"


class ExperimentStatus(str, Enum):
    """Status for meta-learning experiments and proposals."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    REJECTED = "rejected"
    COMPLETED = "completed"


T = TypeVar("T", bound="SerializableRecord")


class SerializableRecord:
    """Mixin for JSON-compatible dataclass records."""

    _hints_cache: ClassVar[dict[type[Any], dict[str, Any]]] = {}

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dictionary using enum values and ISO dates."""

        return {field.name: _to_wire(getattr(self, field.name)) for field in fields(self)}

    @classmethod
    def from_dict(cls: type[T], data: Mapping[str, Any]) -> T:
        """Build a record from a dictionary produced by :meth:`to_dict`.

        Example:
            ``TickerRef.from_dict({"symbol": "NVDA"})``.
        """

        hints = cls._hints_cache.setdefault(cls, get_type_hints(cls))
        kwargs: dict[str, Any] = {}
        for field in fields(cls):
            if field.name in data:
                kwargs[field.name] = _from_wire(data[field.name], hints[field.name])
            elif field.default is not MISSING or field.default_factory is not MISSING:
                continue
            else:
                raise ValidationError(f"{cls.__name__}.{field.name} is required")
        return cls(**kwargs)


def _to_wire(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, SerializableRecord):
        return value.to_dict()
    if isinstance(value, list):
        return [_to_wire(item) for item in value]
    if isinstance(value, tuple):
        return [_to_wire(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_wire(item) for key, item in value.items()}
    return value


def _from_wire(value: Any, annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in {Union, UnionType}:
        non_none = [arg for arg in args if arg is not type(None)]
        if value is None:
            return None
        if len(non_none) == 1:
            return _from_wire(value, non_none[0])

    if origin is Literal:
        if value not in args:
            raise ValidationError(f"{value!r} is not one of {args!r}")
        return value

    if origin is list:
        return [_from_wire(item, args[0]) for item in value]

    if origin is dict:
        key_type, value_type = args
        return {
            _from_wire(key, key_type): _from_wire(item, value_type)
            for key, item in value.items()
        }

    if annotation is datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    if annotation is date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)

    if isinstance(annotation, type) and is_dataclass(annotation) and issubclass(annotation, SerializableRecord):
        if isinstance(value, annotation):
            return value
        return annotation.from_dict(value)

    return value


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValidationError(f"{name} must not be empty")


def _require_score(value: float, name: str) -> None:
    if not 0 <= value <= 1:
        raise ValidationError(f"{name} must be between 0 and 1")


def _require_ordered_dates(start: date, end: date, start_name: str, end_name: str) -> None:
    if end < start:
        raise ValidationError(f"{end_name} must be on or after {start_name}")


@dataclass(frozen=True)
class TickerRef(SerializableRecord):
    """Stable reference to a US-listed company security."""

    symbol: str
    exchange: str | None = None
    company_name: str | None = None
    figi: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.symbol, "symbol")
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class AsOfContext(SerializableRecord):
    """Point-in-time context for data, research, scores, and decisions."""

    as_of_date: date
    data_cutoff: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class VersionStamp(SerializableRecord):
    """Versions that make generated artifacts auditable."""

    prompt_version: str
    scoring_version: str
    signal_version: str
    model_version: str
    data_pipeline_version: str
    config_version: str

    def __post_init__(self) -> None:
        for field in fields(self):
            _require_non_empty(getattr(self, field.name), field.name)


@dataclass(frozen=True)
class EvidenceItem(SerializableRecord):
    """Source-backed evidence or an explicitly marked inference."""

    kind: EvidenceKind
    summary: str
    as_of_date: date
    source_id: str | None = None
    source_url: str | None = None
    published_date: date | None = None
    data_quality: DataQuality = DataQuality.CONFIRMED
    inference: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.summary, "summary")
        if self.kind is not EvidenceKind.INFERENCE and not self.inference and not (self.source_id or self.source_url):
            raise ValidationError("non-inference evidence requires source_id or source_url")
        if self.published_date and self.published_date > self.as_of_date:
            raise ValidationError("published_date cannot be after as_of_date")


@dataclass(frozen=True)
class Catalyst(SerializableRecord):
    """Potential repricing event with expected and observed timing."""

    name: str
    expected_date: date
    status: CatalystStatus
    evidence: list[EvidenceItem]
    actual_date: date | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")
        if not self.evidence:
            raise ValidationError("catalyst requires at least one evidence item")
        if self.actual_date:
            _require_ordered_dates(self.expected_date, self.actual_date, "expected_date", "actual_date")


@dataclass(frozen=True)
class CompanyProfile(SerializableRecord):
    """Point-in-time company descriptors used by packets and scanners."""

    ticker: TickerRef
    sector: str
    industry: str
    market_cap_usd: float | None
    average_daily_dollar_volume: float | None
    data_quality: DataQuality = DataQuality.CONFIRMED

    def __post_init__(self) -> None:
        _require_non_empty(self.sector, "sector")
        _require_non_empty(self.industry, "industry")
        if self.market_cap_usd is not None and self.market_cap_usd < 0:
            raise ValidationError("market_cap_usd cannot be negative")
        if self.average_daily_dollar_volume is not None and self.average_daily_dollar_volume < 0:
            raise ValidationError("average_daily_dollar_volume cannot be negative")


@dataclass(frozen=True)
class FeatureRecord(SerializableRecord):
    """Point-in-time structured feature with source and availability metadata."""

    name: str
    value: float | int | str | bool | None
    as_of_date: date
    source: str
    retrieved_at: datetime
    data_quality: DataQuality = DataQuality.CONFIRMED
    source_id: str | None = None
    source_url: str | None = None
    period_end_date: date | None = None
    window_days: int | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "feature name")
        _require_non_empty(self.source, "feature source")
        if self.data_quality is DataQuality.MISSING:
            if self.value is not None:
                raise ValidationError("missing feature value must be None")
            if not self.unavailable_reason or not self.unavailable_reason.strip():
                raise ValidationError("missing feature requires unavailable_reason")
        elif self.value is None:
            raise ValidationError("available feature value cannot be None")
        if self.window_days is not None and self.window_days < 1:
            raise ValidationError("window_days must be positive when set")


@dataclass(frozen=True)
class SegmentAssessment(SerializableRecord):
    """Assessment of an industry-chain segment inside a theme."""

    segment_name: str
    timing_score: float
    transmission_score: float
    evidence: list[EvidenceItem]
    risks: list[str]
    transmission_stage: int = 0
    candidate_symbols: list[str] = field(default_factory=list)
    leading_indicators: list[str] = field(default_factory=list)
    crowdedness_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_non_empty(self.segment_name, "segment_name")
        _require_score(self.timing_score, "timing_score")
        _require_score(self.transmission_score, "transmission_score")
        if not 0 <= self.transmission_stage <= 7:
            raise ValidationError("transmission_stage must be between 0 and 7")
        if not self.evidence:
            raise ValidationError("segment assessment requires evidence")


@dataclass(frozen=True)
class ThemeMap(SerializableRecord):
    """Theme, industry-chain segments, leading indicators, and risks."""

    theme_id: str
    name: str
    as_of_date: date
    segments: list[SegmentAssessment]
    leading_indicators: list[str]
    evidence: list[EvidenceItem]
    risks: list[str]
    stage_scale_version: str = "theme-stage-v0.1"
    candidate_symbols: list[str] = field(default_factory=list)
    validation_state: dict[str, bool] = field(default_factory=dict)
    crowdedness_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_non_empty(self.theme_id, "theme_id")
        _require_non_empty(self.name, "name")
        _require_non_empty(self.stage_scale_version, "stage_scale_version")
        if not self.segments:
            raise ValidationError("theme map requires at least one segment")
        if not self.evidence:
            raise ValidationError("theme map requires evidence")


@dataclass(frozen=True)
class ResearchPacket(SerializableRecord):
    """Prepared point-in-time input for LLM and non-LLM research."""

    packet_id: str
    as_of: AsOfContext
    company: CompanyProfile
    features: list[FeatureRecord]
    evidence: list[EvidenceItem]
    catalysts: list[Catalyst]
    theme_ids: list[str]
    memory_refs: list[str]
    version: VersionStamp

    def __post_init__(self) -> None:
        _require_non_empty(self.packet_id, "packet_id")
        if not self.features:
            raise ValidationError("research packet requires structured features")
        if not self.evidence:
            raise ValidationError("research packet requires evidence")


@dataclass(frozen=True)
class Thesis(SerializableRecord):
    """Versioned research claim with support, opposition, and review dates."""

    thesis_id: str
    ticker: TickerRef
    as_of_date: date
    claim: str
    status: ThesisStatus
    supporting_evidence: list[EvidenceItem]
    contrary_evidence: list[EvidenceItem]
    catalysts: list[Catalyst]
    disconfirming_conditions: list[str]
    review_dates: list[date]
    version: VersionStamp

    def __post_init__(self) -> None:
        _require_non_empty(self.thesis_id, "thesis_id")
        _require_non_empty(self.claim, "claim")
        if not self.supporting_evidence:
            raise ValidationError("thesis requires supporting evidence")
        if not self.contrary_evidence:
            raise ValidationError("thesis requires contrary evidence")
        if not self.disconfirming_conditions:
            raise ValidationError("thesis requires disconfirming conditions")
        if not self.review_dates:
            raise ValidationError("thesis requires review dates")


@dataclass(frozen=True)
class SignalDefinition(SerializableRecord):
    """Measurable signal with applicability and false-positive notes."""

    signal_id: str
    name: str
    description: str
    version: str
    applicable_sectors: list[str]
    false_positive_patterns: list[str]
    evidence: list[EvidenceItem]

    def __post_init__(self) -> None:
        _require_non_empty(self.signal_id, "signal_id")
        _require_non_empty(self.name, "name")
        _require_non_empty(self.description, "description")
        _require_non_empty(self.version, "version")
        if not self.evidence:
            raise ValidationError("signal definition requires evidence")


@dataclass(frozen=True)
class ScoreCard(SerializableRecord):
    """Component scores and final opportunity score."""

    score_id: str
    ticker: TickerRef
    as_of_date: date
    theme_transmission_score: float
    segment_timing_score: float
    company_rocket_score: float
    risk_adjustment: float
    upside_potential: float
    launch_probability: float
    final_opportunity_score: float
    component_scores: dict[str, float]
    evidence: list[EvidenceItem]
    version: VersionStamp

    def __post_init__(self) -> None:
        _require_non_empty(self.score_id, "score_id")
        for name in (
            "theme_transmission_score",
            "segment_timing_score",
            "company_rocket_score",
            "risk_adjustment",
            "upside_potential",
            "launch_probability",
            "final_opportunity_score",
        ):
            _require_score(getattr(self, name), name)
        for name, value in self.component_scores.items():
            _require_non_empty(name, "component score name")
            _require_score(value, f"component_scores.{name}")
        if not self.component_scores:
            raise ValidationError("score card requires component scores")
        if not self.evidence:
            raise ValidationError("score card requires evidence")


@dataclass(frozen=True)
class WatchlistEntry(SerializableRecord):
    """Ranked watchlist output with recommendation state and reason."""

    entry_id: str
    ticker: TickerRef
    as_of_date: date
    rank: int
    state: RecommendationState
    score: ScoreCard
    reason: str
    thesis_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.entry_id, "entry_id")
        _require_non_empty(self.reason, "reason")
        _require_non_empty(self.thesis_id, "thesis_id")
        if self.rank < 1:
            raise ValidationError("rank must be at least 1")


@dataclass(frozen=True)
class DecisionRecord(SerializableRecord):
    """Immutable record of what the system recommended and why."""

    decision_id: str
    as_of_date: date
    entry: WatchlistEntry
    thesis: Thesis
    evidence: list[EvidenceItem]
    version: VersionStamp

    def __post_init__(self) -> None:
        _require_non_empty(self.decision_id, "decision_id")
        if not self.evidence:
            raise ValidationError("decision record requires evidence")


@dataclass(frozen=True)
class ReviewRecord(SerializableRecord):
    """Outcome review after time has passed."""

    review_id: str
    decision_id: str
    as_of_date: date
    review_date: date
    outcome: ReviewOutcome
    error_labels: list[str]
    lessons: list[str]
    evidence: list[EvidenceItem]
    version: VersionStamp

    def __post_init__(self) -> None:
        _require_non_empty(self.review_id, "review_id")
        _require_non_empty(self.decision_id, "decision_id")
        _require_ordered_dates(self.as_of_date, self.review_date, "as_of_date", "review_date")
        if not self.evidence:
            raise ValidationError("review record requires evidence")


@dataclass(frozen=True)
class ExperimentRecord(SerializableRecord):
    """Meta-learning proposal, test design, result, and approval state."""

    experiment_id: str
    as_of_date: date
    hypothesis: str
    status: ExperimentStatus
    risk_level: Literal["low", "medium", "high"]
    test_design: str
    proposed_change: str
    requires_human_approval: bool
    result_summary: str | None = None
    approval_record_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.hypothesis, "hypothesis")
        _require_non_empty(self.test_design, "test_design")
        _require_non_empty(self.proposed_change, "proposed_change")
        if self.risk_level in {"medium", "high"} and not self.requires_human_approval:
            raise ValidationError("medium and high risk experiments require human approval")
