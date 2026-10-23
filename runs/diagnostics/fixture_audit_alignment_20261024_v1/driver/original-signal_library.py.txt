"""Versioned deterministic and LLM-driven Signal Registry."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from stock_opportunity_agent.artifacts import (
    atomic_write_json as _atomic_write_json,
    atomic_write_text as _atomic_write_text,
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.point_in_time import utc_day_of_instant
from stock_opportunity_agent.data.sec_company_facts import company_fact_available_at, validate_company_fact_document_issuer
from stock_opportunity_agent.data.sources.core import DataSourceError
from stock_opportunity_agent.data.resolution import (
    DataGapReason,
    EvidenceResolver,
    RawInfoRequest,
    RawInfoResolution,
    RawInfoDocumentRef,
    ResolutionEvent,
    _select_required_source_documents,
    _retrieval_contract_coverage,
    source_types_compatible,
)
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError


_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_:-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_EVALUATION_HASH_FIELDS = frozenset(
    {
        "baseline_hash",
        "cohort_hash",
        "source_manifest_hash",
        "projection_hash",
        "validator_hash",
        "model_hash",
        "sampling_hash",
    }
)
_FORBIDDEN_SOURCE_TYPES = frozenset(
    {"ground_truth", "outcome_label", "future_price", "future_return"}
)
SIGNAL_CONTEXT_TAGS = frozenset(
    {
        "general",
        "comparable_financials",
        "sparse_evidence",
        "filing_rich",
        "news_rich",
        "transcript_available",
        "market_data_only",
        "pre_revenue",
        "early_commercialization",
        "scaling",
        "mature_operations",
        "project_driven",
        "recurring_revenue",
        "customer_concentrated",
        "capital_intensive",
        "cyclical",
        "regulated",
        "biotechnology",
        "healthcare",
        "software",
        "semiconductors",
        "hardware",
        "industrial",
        "energy",
        "materials",
        "consumer",
        "financials",
        "real_estate",
        "communications",
        "small_cap",
        "mid_cap",
        "large_cap",
        "high_volatility",
        "catalyst_window",
    }
)


def _admission_identity_key(identity: Mapping[str, Any]) -> str:
    """Hash only the complete technical admission identity, never effect data."""

    return hashlib.sha256(json.dumps(dict(identity), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_admission_record(record: Mapping[str, Any], *, signal_ref: str) -> None:
    """Reject corrupt admission identities and inconsistent technical decisions."""

    identity = record.get("admission_identity")
    required = {
        "schema_version", "signal_ref", "candidate_hash", "input_registry_hash",
        "validator_hash", "research_targets", "contract_validation",
    }
    if not isinstance(identity, Mapping) or not required <= set(identity) or set(identity) - required - {"research_provenance"}:
        raise ValidationError("Signal admission identity is incomplete")
    if "research_provenance" in identity:
        _validate_research_provenance(identity["research_provenance"])
    targets = identity["research_targets"]
    contract = identity["contract_validation"]
    if (
        record.get("schema_version") != "signal-candidate-admission-v1"
        or identity["schema_version"] != "signal-candidate-admission-identity-v1"
        or identity["signal_ref"] != signal_ref
        or record.get("signal_ref") != signal_ref
        or any(not isinstance(identity[field], str) or not _SHA256.fullmatch(identity[field]) for field in ("candidate_hash", "input_registry_hash", "validator_hash"))
        or record.get("candidate_hash") != identity["candidate_hash"]
        or record.get("evaluation_key") != _admission_identity_key(identity)
        or not isinstance(targets, list) or not targets
        or any(not isinstance(item, str) or not _SAFE_ID.fullmatch(item) for item in targets)
        or targets != sorted(set(targets))
        or not isinstance(contract, Mapping)
        or type(contract.get("accepted")) is not bool
        or not isinstance(contract.get("reasons"), list)
        or any(not isinstance(reason, str) or not reason.strip() for reason in contract.get("reasons", ()))
        or type(contract.get("executed_tests")) is not int
        or contract["executed_tests"] < 0
        or record.get("contract_validation") != contract
        or record.get("accepted") is not contract["accepted"]
        or record.get("reasons") != contract["reasons"]
        or record.get("status") != ("admitted" if contract["accepted"] else "rejected")
        or (contract["accepted"] and (contract["reasons"] or contract["executed_tests"] == 0))
        or (not contract["accepted"] and not contract["reasons"])
    ):
        raise ValidationError("Signal admission record does not match its identity")


def _validate_research_provenance(value: Any) -> None:
    """Keep lineage explicit and label-free; never infer independence from absence."""

    if not isinstance(value, Mapping) or set(value) != {"generation_case_ids", "induction_case_ids", "origin", "source_input_hash"}:
        raise ValidationError("Signal research provenance is invalid")
    for name in ("generation_case_ids", "induction_case_ids"):
        refs = value[name]
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs) or refs != sorted(set(refs)):
            raise ValidationError("Signal research provenance refs are invalid")
    if value["origin"] not in {"current_cycle", "legacy_effect_records", "unknown"} or (
        value["source_input_hash"] is not None and (
            not isinstance(value["source_input_hash"], str) or not _SHA256.fullmatch(value["source_input_hash"])
        )
    ):
        raise ValidationError("Signal research provenance origin is invalid")
    if value["origin"] != "unknown" and value["source_input_hash"] is None:
        raise ValidationError("known research provenance requires its source hash")


class _FrozenDict(dict[Any, Any]):
    """JSON-compatible mapping that rejects every in-place mutation."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("frozen Signal snapshot values cannot be mutated")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


class _FrozenList(list[Any]):
    """JSON-compatible sequence that rejects every in-place mutation."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("frozen Signal snapshot values cannot be mutated")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _FrozenDict(
            {str(key): _freeze_json(nested) for key, nested in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return _FrozenList(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value
_BUILTIN_ADAPTER_SOURCE_TYPES = frozenset(
    {
        "financials",
        "financial_statements",
        "sec_company_facts",
        "company_facts",
        "filing",
        "sec_filing",
        "filing_body",
        "10-k",
        "10-q",
        "news",
        "company_news",
        "earnings_call",
        "transcript",
        "earnings_transcript",
        "market_data",
        "historical_price",
        "price_daily",
        "prices",
    }
)


class SignalExecutionType(str, Enum):
    """Supported Signal execution policies."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"


class SignalModality(str, Enum):
    """Research identity of the observable, independent of its implementation."""

    STRUCTURED = "structured"
    NARRATIVE = "narrative"


class SignalValue(str, Enum):
    """Low-dimensional canonical state used by statistics."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNAVAILABLE = "unavailable"


class SignalCoverage(str, Enum):
    """Whether available evidence was sufficient for the result."""

    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class SignalExecutionStatus(str, Enum):
    """Runtime-owned outcome of attempting one Signal execution."""

    SUCCESS = "success"
    DOMAIN_UNAVAILABLE = "domain_unavailable"
    VALIDATION_FAILED = "validation_failed"
    TRANSPORT_FAILED = "transport_failed"
    PERMANENT_FAILED = "permanent_failed"
    BUDGET_BLOCKED = "budget_blocked"
    AUTHORIZATION_BLOCKED = "authorization_blocked"


_SIGNAL_TECHNICAL_FAILURE_STATUSES = frozenset(
    {
        SignalExecutionStatus.VALIDATION_FAILED,
        SignalExecutionStatus.TRANSPORT_FAILED,
        SignalExecutionStatus.PERMANENT_FAILED,
        SignalExecutionStatus.BUDGET_BLOCKED,
        SignalExecutionStatus.AUTHORIZATION_BLOCKED,
    }
)

SIGNAL_EXECUTION_STATUS_INSTRUCTION = (
    "Interpret Signal execution.status literally. domain_unavailable is a normal "
    "domain coverage outcome: visible evidence was insufficient for a canonical "
    "conclusion. domain_unavailable is not a technical execution gap or failure, "
    "and does not prove the measured condition is absent. Only "
    + ", ".join(sorted(status.value for status in _SIGNAL_TECHNICAL_FAILURE_STATUSES))
    + " are technical execution gaps: no validated domain result was produced. "
    "Do not treat a technical failure as missing issuer data, economic absence "
    "or a valid factor prediction failure. Describe technical repair separately "
    "from completed research. An unavailable result without a recognized "
    "execution status has unknown cause; infer neither coverage insufficiency "
    "nor technical failure from its unavailable-shaped value alone. "
)


@dataclass(frozen=True)
class EvidencePolicy:
    """Traceability requirements enforced after every Signal execution."""

    require_source: bool = True
    require_timestamp: bool = True
    require_exact_span: bool = True

    def __post_init__(self) -> None:
        if any(
            type(value) is not bool
            for value in (
                self.require_source,
                self.require_timestamp,
                self.require_exact_span,
            )
        ):
            raise ValidationError("evidence policy fields must be booleans")

    def to_dict(self) -> dict[str, bool]:
        return {
            "require_source": self.require_source,
            "require_timestamp": self.require_timestamp,
            "require_exact_span": self.require_exact_span,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidencePolicy":
        required = {"require_source", "require_timestamp", "require_exact_span"}
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "evidence policy is missing fields: " + ", ".join(missing)
            )
        return cls(
            require_source=data["require_source"],
            require_timestamp=data["require_timestamp"],
            require_exact_span=data["require_exact_span"],
        )


@dataclass(frozen=True)
class SignalRetrievalPolicy:
    """Version-owned retrieval intent translated into one Raw Info request."""

    query_terms: tuple[str, ...]
    lookback_days: int | None = None
    comparison_requirement: str | None = None
    required_source_groups: tuple[tuple[str, ...], ...] = ()
    minimum_distinct_periods: int | None = None
    minimum_period_span_days: int | None = None
    minimum_observations: int | None = None

    def __post_init__(self) -> None:
        terms = tuple(" ".join(str(item).split()) for item in self.query_terms)
        if (
            not terms
            or len(terms) > 12
            or any(not item or len(item) > 80 for item in terms)
            or len({item.casefold() for item in terms}) != len(terms)
        ):
            raise ValidationError(
                "Signal retrieval query_terms require 1-12 unique bounded strings"
            )
        if self.lookback_days is not None and self.lookback_days < 1:
            raise ValidationError("Signal retrieval lookback_days must be positive")
        comparison = (
            " ".join(self.comparison_requirement.split())
            if self.comparison_requirement is not None
            else None
        )
        if comparison is not None and (not comparison or len(comparison) > 240):
            raise ValidationError(
                "Signal retrieval comparison_requirement must be bounded text"
            )
        object.__setattr__(self, "query_terms", terms)
        object.__setattr__(self, "comparison_requirement", comparison)
        groups = tuple(
            tuple(str(item) for item in group)
            for group in self.required_source_groups
        )
        if any(
            not group
            or any(not item.strip() for item in group)
            or len({item.casefold() for item in group}) != len(group)
            for group in groups
        ):
            raise ValidationError(
                "Signal retrieval source groups must be non-empty and unique"
            )
        if len(set(groups)) != len(groups):
            raise ValidationError("Signal retrieval source groups must be unique")
        for name in (
            "minimum_distinct_periods",
            "minimum_period_span_days",
            "minimum_observations",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 1):
                raise ValidationError(
                    f"Signal retrieval {name} must be a positive integer"
                )
        object.__setattr__(self, "required_source_groups", groups)

    @property
    def query(self) -> str:
        """Return the bounded lexical query passed to the data boundary."""

        return " ".join(self.query_terms)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"query_terms": list(self.query_terms)}
        if self.lookback_days is not None:
            value["lookback_days"] = self.lookback_days
        if self.comparison_requirement is not None:
            value["comparison_requirement"] = self.comparison_requirement
        if self.required_source_groups:
            value["required_source_groups"] = [
                list(group) for group in self.required_source_groups
            ]
        for name in (
            "minimum_distinct_periods",
            "minimum_period_span_days",
            "minimum_observations",
        ):
            field_value = getattr(self, name)
            if field_value is not None:
                value[name] = field_value
        return value

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        default_query_terms: tuple[str, ...],
    ) -> "SignalRetrievalPolicy":
        raw_terms = data.get("query_terms")
        if raw_terms is None and data.get("query") is not None:
            raw_terms = (str(data["query"]),)
        if raw_terms is None:
            raw_terms = default_query_terms
        if not isinstance(raw_terms, (list, tuple)):
            raise ValidationError("Signal retrieval query_terms must be an array")
        return cls(
            query_terms=tuple(str(item) for item in raw_terms),
            lookback_days=(
                int(data["lookback_days"])
                if data.get("lookback_days") is not None
                else None
            ),
            comparison_requirement=(
                str(data["comparison_requirement"])
                if data.get("comparison_requirement") is not None
                else None
            ),
            required_source_groups=tuple(
                tuple(str(item) for item in group)
                for group in data.get("required_source_groups", ())
            ),
            minimum_distinct_periods=(
                int(data["minimum_distinct_periods"])
                if data.get("minimum_distinct_periods") is not None
                else None
            ),
            minimum_period_span_days=(
                int(data["minimum_period_span_days"])
                if data.get("minimum_period_span_days") is not None
                else None
            ),
            minimum_observations=(
                int(data["minimum_observations"])
                if data.get("minimum_observations") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class SignalSpec:
    """Immutable schema, execution policy, retrieval policy, and evidence policy."""

    signal_id: str
    version: int
    category: str
    description: str
    execution_type: SignalExecutionType
    source_types: tuple[str, ...]
    modality: SignalModality | None = None
    evidence_policy: EvidencePolicy = field(default_factory=EvidencePolicy)
    function: str | None = None
    skill_file: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    retrieval_policy: SignalRetrievalPolicy | None = None

    def __post_init__(self) -> None:
        _validate_id(self.signal_id, "signal_id")
        _validate_id(self.category, "category")
        if self.version < 1:
            raise ValidationError("signal version must be positive")
        if not self.description.strip():
            raise ValidationError("signal description must not be empty")
        if not isinstance(self.execution_type, SignalExecutionType):
            object.__setattr__(
                self,
                "execution_type",
                SignalExecutionType(self.execution_type),
            )
        if self.modality is not None and not isinstance(
            self.modality, SignalModality
        ):
            object.__setattr__(self, "modality", SignalModality(self.modality))
        if (
            self.modality is SignalModality.STRUCTURED
            and self.execution_type is not SignalExecutionType.DETERMINISTIC
        ):
            raise ValidationError(
                "structured Signal modality requires deterministic execution"
            )
        if (
            self.modality is SignalModality.NARRATIVE
            and self.execution_type is not SignalExecutionType.LLM
        ):
            raise ValidationError("narrative Signal modality requires LLM execution")
        if not self.source_types:
            raise ValidationError("signal requires at least one raw source type")
        for source_type in self.source_types:
            _validate_id(source_type, "source_type")
        if set(self.source_types) & _FORBIDDEN_SOURCE_TYPES:
            raise ValidationError("signal source types cannot contain outcome data")
        if self.execution_type is SignalExecutionType.DETERMINISTIC:
            if not self.function or self.skill_file:
                raise ValidationError(
                    "deterministic signal requires function and cannot use skill_file"
                )
        elif not self.skill_file or self.function:
            raise ValidationError(
                "LLM signal requires skill_file and cannot use deterministic function"
            )
        parameters = dict(self.parameters)
        if "usage_context" in parameters:
            from stock_opportunity_agent.memory.knowledge import usage_context

            context = usage_context(parameters["usage_context"])
            if any(not ref.startswith("reflection:") for ref in context["related_refs"]):
                raise ValidationError("Signal usage context must index Experience refs")
            parameters["usage_context"] = context
        routing_phrases = parameters.get("routing_need_phrases")
        if routing_phrases is not None and (
            not isinstance(routing_phrases, list)
            or not routing_phrases
            or len(routing_phrases) > 8
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 80
                or len(re.findall(r"[a-z0-9]+", item.casefold())) < 2
                for item in routing_phrases
            )
        ):
            raise ValidationError(
                "Signal routing_need_phrases must contain 1-8 multiword strings"
            )
        required_research_phrases = parameters.get(
            "routing_required_research_phrases"
        )
        if required_research_phrases is not None and (
            not isinstance(required_research_phrases, list)
            or not required_research_phrases
            or len(required_research_phrases) > 8
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 80
                for item in required_research_phrases
            )
            or len(set(required_research_phrases))
            != len(required_research_phrases)
        ):
            raise ValidationError(
                "Signal routing_required_research_phrases must contain 1-8 "
                "unique non-empty strings"
            )
        answer_need_phrases = parameters.get("routing_answer_need_phrases")
        if answer_need_phrases is not None and (
            not isinstance(answer_need_phrases, list)
            or not answer_need_phrases
            or len(answer_need_phrases) > 16
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 80
                for item in answer_need_phrases
            )
            or len(set(answer_need_phrases)) != len(answer_need_phrases)
        ):
            raise ValidationError(
                "Signal routing_answer_need_phrases must contain 1-16 unique "
                "non-empty strings"
            )
        result_required_evidence_phrases = parameters.get(
            "result_required_evidence_phrases"
        )
        if result_required_evidence_phrases is not None and (
            not isinstance(result_required_evidence_phrases, list)
            or not result_required_evidence_phrases
            or len(result_required_evidence_phrases) > 16
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 80
                for item in result_required_evidence_phrases
            )
            or len(set(result_required_evidence_phrases))
            != len(result_required_evidence_phrases)
        ):
            raise ValidationError(
                "Signal result_required_evidence_phrases must contain 1-16 "
                "unique non-empty strings"
            )
        excluded_tags = parameters.get("routing_excluded_context_tags")
        if excluded_tags is not None and (
            not isinstance(excluded_tags, list)
            or not excluded_tags
            or len(excluded_tags) > 8
            or any(
                not isinstance(item, str) or item not in SIGNAL_CONTEXT_TAGS
                for item in excluded_tags
            )
            or len(set(excluded_tags)) != len(excluded_tags)
        ):
            raise ValidationError(
                "Signal routing_excluded_context_tags must contain 1-8 unique "
                "frozen context tags"
            )
        object.__setattr__(self, "source_types", tuple(self.source_types))
        object.__setattr__(self, "parameters", _freeze_json(parameters))
        retrieval_policy = self.retrieval_policy
        if retrieval_policy is None:
            retrieval_policy = SignalRetrievalPolicy(
                query_terms=(self.signal_id.replace("_", " "),)
            )
        elif not isinstance(retrieval_policy, SignalRetrievalPolicy):
            retrieval_policy = SignalRetrievalPolicy.from_dict(
                dict(retrieval_policy),
                default_query_terms=(self.signal_id.replace("_", " "),),
            )
        object.__setattr__(self, "retrieval_policy", retrieval_policy)
        if any(
            not source_types_compatible((item,), self.source_types)
            for group in retrieval_policy.required_source_groups
            for item in group
        ):
            raise ValidationError(
                "Signal retrieval source group is outside declared source_types"
            )

    @property
    def ref(self) -> str:
        """Return the stable version reference used in plans and trajectories."""

        return f"{self.signal_id}:v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        value = {
            "signal_id": self.signal_id,
            "version": self.version,
            "category": self.category,
            "definition": {"description": self.description},
            "schema": {
                "value": {
                    "type": "categorical",
                    "values": [value.value for value in SignalValue],
                },
                "confidence": {"type": "float"},
            },
            "execution": {
                "type": self.execution_type.value,
                **({"function": self.function} if self.function else {}),
                **({"skill_file": self.skill_file} if self.skill_file else {}),
            },
            "raw_retrieval": {
                "source_types": list(self.source_types),
                **self.retrieval_policy.to_dict(),
            },
            "evidence_policy": self.evidence_policy.to_dict(),
            "parameters": _thaw_json(self.parameters),
        }
        if self.modality is not None:
            value["modality"] = self.modality.value
        return value

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalSpec":
        execution = dict(data.get("execution", {}))
        schema = dict(data.get("schema", {}))
        value_schema = dict(schema.get("value", {}))
        declared_values = value_schema.get("values")
        expected_values = [value.value for value in SignalValue]
        if declared_values is not None and list(declared_values) != expected_values:
            raise ValidationError("SignalSpec schema must use the canonical state values")
        confidence_schema = dict(schema.get("confidence", {}))
        if confidence_schema and confidence_schema.get("type") != "float":
            raise ValidationError("SignalSpec confidence schema must be float")
        definition = data.get("definition", {})
        description = (
            definition.get("description", "")
            if isinstance(definition, Mapping)
            else str(definition)
        )
        retrieval = dict(data.get("raw_retrieval", {}))
        return cls(
            signal_id=str(data["signal_id"]),
            version=int(data["version"]),
            category=str(data["category"]),
            description=str(description),
            execution_type=SignalExecutionType(str(execution["type"])),
            modality=(
                SignalModality(str(data["modality"]))
                if data.get("modality") is not None
                else None
            ),
            function=(str(execution["function"]) if execution.get("function") else None),
            skill_file=(
                str(execution["skill_file"]) if execution.get("skill_file") else None
            ),
            source_types=tuple(str(item) for item in retrieval.get("source_types", ())),
            evidence_policy=EvidencePolicy.from_dict(
                dict(data.get("evidence_policy", {}))
            ),
            parameters=dict(data.get("parameters", {})),
            retrieval_policy=SignalRetrievalPolicy.from_dict(
                retrieval,
                default_query_terms=(
                    str(data["signal_id"]).replace("_", " "),
                ),
            ),
        )


@dataclass(frozen=True)
class SignalEvidence:
    """Literal evidence span from one actual point-in-time input document."""

    document_id: str
    exact_span: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.document_id.strip() or not self.exact_span.strip():
            raise ValidationError("signal evidence requires document_id and exact_span")

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "exact_span": self.exact_span,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalEvidence":
        timestamp = data["timestamp"]
        return cls(
            document_id=str(data["document_id"]),
            exact_span=str(data["exact_span"]),
            timestamp=(
                timestamp
                if isinstance(timestamp, datetime)
                else datetime.fromisoformat(str(timestamp))
            ),
        )


@dataclass(frozen=True)
class NumericMeasurement:
    """Meaning supplied by the deterministic function that computed a value."""

    value: float
    unit: str
    formula: str
    period_end: str | None = None
    period_start: str | None = None

    def __post_init__(self) -> None:
        if (isinstance(self.value, bool) or not isinstance(self.value, (int, float))
                or not math.isfinite(self.value)):
            raise ValidationError("numeric measurement value must be finite")
        if not isinstance(self.unit, str) or (
            self.unit not in {"fraction", "fraction_difference", "ratio", "count", "months"}
            and re.fullmatch(r"[A-Z]{3}", self.unit) is None
        ):
            raise ValidationError("numeric measurement unit is unsupported")
        if not isinstance(self.formula, str) or not self.formula.strip() or len(self.formula) > 240:
            raise ValidationError("numeric measurement formula must be bounded text")
        if self.unit == "count" and (self.value < 0 or self.value != int(self.value)):
            raise ValidationError("numeric count must be a nonnegative integer")
        if self.unit == "months" and self.value < 0:
            raise ValidationError("numeric duration cannot be negative")
        for value in (self.period_start, self.period_end):
            if value is not None:
                try:
                    if datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") != value:
                        raise ValueError("noncanonical date")
                except (TypeError, ValueError) as exc:
                    raise ValidationError("numeric measurement period must use exact ISO dates") from exc
        if self.period_start and (not self.period_end or self.period_start > self.period_end):
            raise ValidationError("numeric measurement duration is invalid")

    def to_dict(self) -> dict[str, Any]:
        """Serialize without introducing absent fields into legacy artifacts."""

        result = {"value": self.value, "unit": self.unit, "formula": self.formula}
        if self.period_end is not None:
            result["period"] = {"end": self.period_end}
            if self.period_start is not None:
                result["period"]["start"] = self.period_start
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "NumericMeasurement":
        """Restore strict runtime metadata, never inferred from Signal prose."""

        if not isinstance(value, Mapping) or set(value) - {"value", "unit", "formula", "period"} or not {"value", "unit", "formula"} <= set(value):
            raise ValidationError("numeric measurement has invalid fields")
        period = value.get("period", {})
        if not isinstance(period, Mapping) or (
            "period" in value and (not isinstance(period.get("end"), str) or set(period) - {"start", "end"})
        ):
            raise ValidationError("numeric measurement period has invalid fields")
        return cls(value["value"], value["unit"], value["formula"], period.get("end"), period.get("start"))


@dataclass(frozen=True)
class SignalResult:
    """Canonical state plus rich interpretation and evidence provenance."""

    signal_id: str
    version: int
    value: SignalValue
    confidence: float
    interpretation: str
    supporting_evidence: tuple[SignalEvidence, ...] = ()
    counter_evidence: tuple[SignalEvidence, ...] = ()
    coverage: SignalCoverage = SignalCoverage.SUFFICIENT
    execution_status: SignalExecutionStatus | None = None
    execution_error_code: str | None = None
    execution_error_message: str | None = None
    measurement: NumericMeasurement | None = None

    def __post_init__(self) -> None:
        _validate_id(self.signal_id, "signal_id")
        if self.version < 1:
            raise ValidationError("signal result version must be positive")
        if not isinstance(self.value, SignalValue):
            object.__setattr__(self, "value", SignalValue(self.value))
        if not isinstance(self.coverage, SignalCoverage):
            object.__setattr__(self, "coverage", SignalCoverage(self.coverage))
        execution_status = self.execution_status
        if execution_status is None:
            execution_status = (
                SignalExecutionStatus.DOMAIN_UNAVAILABLE
                if self.value is SignalValue.UNAVAILABLE
                else SignalExecutionStatus.SUCCESS
            )
        elif not isinstance(execution_status, SignalExecutionStatus):
            execution_status = SignalExecutionStatus(execution_status)
        object.__setattr__(self, "execution_status", execution_status)
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(float(self.confidence))
            or not 0 <= self.confidence <= 1
        ):
            raise ValidationError("signal confidence must be between 0 and 1")
        object.__setattr__(self, "confidence", float(self.confidence))
        if not self.interpretation.strip():
            raise ValidationError("signal interpretation must not be empty")
        supporting_evidence = tuple(self.supporting_evidence)
        counter_evidence = tuple(self.counter_evidence)
        object.__setattr__(self, "supporting_evidence", supporting_evidence)
        object.__setattr__(self, "counter_evidence", counter_evidence)
        if self.measurement is not None:
            if not isinstance(self.measurement, NumericMeasurement) or self.value is SignalValue.UNAVAILABLE:
                raise ValidationError("available numeric result required for measurement")
            number = self.interpretation.partition("=")[2].split(";", 1)[0]
            if number != f"{self.measurement.value:.6g}":
                raise ValidationError("numeric measurement disagrees with canonical interpretation")
        if self.value is SignalValue.UNAVAILABLE:
            if self.coverage is not SignalCoverage.UNAVAILABLE:
                raise ValidationError("unavailable signal requires unavailable coverage")
            if supporting_evidence or counter_evidence:
                raise ValidationError("unavailable signal result cannot carry evidence")
        elif self.coverage is SignalCoverage.UNAVAILABLE:
            raise ValidationError("available signal cannot use unavailable coverage")
        if execution_status is SignalExecutionStatus.SUCCESS:
            if self.value is SignalValue.UNAVAILABLE:
                raise ValidationError("successful execution requires a domain value")
        elif execution_status is SignalExecutionStatus.DOMAIN_UNAVAILABLE:
            if self.value is not SignalValue.UNAVAILABLE:
                raise ValidationError(
                    "domain-unavailable execution requires unavailable value"
                )
        elif execution_status in _SIGNAL_TECHNICAL_FAILURE_STATUSES:
            if self.value is not SignalValue.UNAVAILABLE:
                raise ValidationError(
                    "failed execution requires an unavailable-shaped value"
                )
            if not (self.execution_error_code or "").strip() or not (
                self.execution_error_message or ""
            ).strip():
                raise ValidationError(
                    "failed execution requires error code and diagnostic message"
                )
        if execution_status not in _SIGNAL_TECHNICAL_FAILURE_STATUSES and (
            self.execution_error_code is not None
            or self.execution_error_message is not None
        ):
            raise ValidationError(
                "successful/domain-unavailable execution cannot carry an error"
            )

    @property
    def ref(self) -> str:
        return f"{self.signal_id}:v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        result = {
            "signal_id": self.signal_id,
            "version": self.version,
            "state": {"value": self.value.value, "confidence": self.confidence},
            "interpretation": {"summary": self.interpretation},
            "evidence": {
                "supporting": [item.to_dict() for item in self.supporting_evidence],
                "counter": [item.to_dict() for item in self.counter_evidence],
            },
            "status": {"coverage": self.coverage.value},
            "execution": {"status": self.execution_status.value},
        }
        if self.execution_status in _SIGNAL_TECHNICAL_FAILURE_STATUSES:
            result["execution"].update(
                {
                    "error_code": self.execution_error_code,
                    "error_message": self.execution_error_message,
                }
            )
        if self.measurement is not None:
            result["measurement"] = self.measurement.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalResult":
        required = {
            "signal_id",
            "version",
            "state",
            "interpretation",
            "evidence",
            "status",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "SignalResult is missing fields: " + ", ".join(missing)
            )
        if not isinstance(data["state"], Mapping):
            raise ValidationError("SignalResult state must be an object")
        if not isinstance(data["interpretation"], Mapping):
            raise ValidationError("SignalResult interpretation must be an object")
        if not isinstance(data["evidence"], Mapping):
            raise ValidationError("SignalResult evidence must be an object")
        if not isinstance(data["status"], Mapping):
            raise ValidationError("SignalResult status must be an object")
        state = dict(data["state"])
        interpretation = dict(data["interpretation"])
        evidence = dict(data["evidence"])
        status = dict(data["status"])
        execution = dict(data.get("execution", {}))
        if set(state) != {"value", "confidence"}:
            raise ValidationError(
                "SignalResult state requires exactly value and confidence"
            )
        if "summary" not in interpretation or not isinstance(
            interpretation["summary"], str
        ):
            raise ValidationError("SignalResult interpretation.summary must be text")
        if set(evidence) != {"supporting", "counter"} or any(
            not isinstance(evidence[name], list)
            for name in ("supporting", "counter")
        ):
            raise ValidationError(
                "SignalResult evidence requires supporting/counter arrays"
            )
        if set(status) != {"coverage"}:
            raise ValidationError("SignalResult status requires exactly coverage")
        if isinstance(state["confidence"], bool) or not isinstance(
            state["confidence"], (int, float)
        ):
            raise ValidationError("SignalResult confidence must be numeric")
        if execution and set(execution) - {
            "status",
            "error_code",
            "error_message",
        }:
            raise ValidationError("SignalResult execution has unexpected fields")
        return cls(
            signal_id=str(data["signal_id"]),
            version=int(data["version"]),
            value=SignalValue(str(state["value"])),
            confidence=state["confidence"],
            interpretation=interpretation["summary"],
            measurement=(NumericMeasurement.from_dict(data["measurement"])
                         if "measurement" in data else None),
            supporting_evidence=tuple(
                SignalEvidence.from_dict(item)
                for item in evidence["supporting"]
            ),
            counter_evidence=tuple(
                SignalEvidence.from_dict(item)
                for item in evidence["counter"]
            ),
            coverage=SignalCoverage(str(status["coverage"])),
            execution_status=(
                SignalExecutionStatus(str(execution["status"]))
                if execution.get("status") is not None
                else None
            ),
            execution_error_code=(
                str(execution["error_code"])
                if execution.get("error_code") is not None
                else None
            ),
            execution_error_message=(
                str(execution["error_message"])
                if execution.get("error_message") is not None
                else None
            ),
        )


UNAVAILABLE_SIGNAL_MODEL_SUMMARY = (
    "domain_unavailable: a normal domain coverage outcome, not a technical "
    "execution gap or failure. Visible evidence was insufficient for a canonical conclusion. "
    "This is not evidence that the measured condition is absent."
)

FAILED_SIGNAL_MODEL_SUMMARY = (
    "Technical execution gap: Signal execution did not produce a validated domain result. Treat this item "
    "as unknown and do not infer that the measured condition is absent."
)

UNKNOWN_UNAVAILABLE_SIGNAL_MODEL_SUMMARY = (
    "Unavailable result with unknown execution cause. Infer neither domain "
    "coverage insufficiency nor technical failure. This is not evidence that "
    "the measured condition is absent."
)


class SignalModelInputRejected(RuntimeError):
    """An existing result is unsafe model input, not a repairable model answer."""

    def __init__(self, signal_ref: str, path: str, reason: str) -> None:
        self.reason_code = "signal_input_pit"
        self.signal_ref = signal_ref
        self.path = path
        self.reason = reason
        super().__init__(f"signal_input_pit: {signal_ref} {path}: {reason}")


def require_signal_result_pit(
    value: SignalResult | Mapping[str, Any], *, as_of: datetime,
) -> list[str]:
    """Check exact evidence times before projecting any existing result prose.

    Compact cards need runtime-copied timestamp binding; an old card without
    original evidence cannot prove this boundary and is rejected for new use.
    Canonical artifacts are never changed. F6 still owns complete evidence
    membership/literal validation and source versions require their own review.
    """
    result = value.to_dict() if isinstance(value, SignalResult) else dict(value)
    owner = str(result.get("signal_ref") or f"{result.get('signal_id')}:v{result.get('version')}")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise SignalModelInputRejected(owner, "prediction_time", "aware runtime cutoff required")
    evidence = result.get("evidence")
    if isinstance(evidence, Mapping):
        if any(group not in evidence or not isinstance(evidence[group], (list, tuple))
               for group in ("supporting", "counter")):
            raise SignalModelInputRejected(owner, "evidence", "complete supporting/counter arrays are required")
        rows = [(f"evidence.{group}[{index}].timestamp", item.get("timestamp") if isinstance(item, Mapping) else None)
                for group in ("supporting", "counter") for index, item in enumerate(evidence[group])]
    else:
        if "evidence" in result:
            raise SignalModelInputRejected(owner, "evidence", "complete supporting/counter arrays are required")
        rows = []
    canonical_count = len(rows)
    if "input_evidence_available_at" in result or not isinstance(evidence, Mapping):
        binding = result.get("input_evidence_available_at")
        if not isinstance(binding, list):
            raise SignalModelInputRejected(owner, "input_evidence_available_at", "missing original evidence or runtime time binding")
        rows.extend((f"input_evidence_available_at[{index}]", raw) for index, raw in enumerate(binding))
    times = []
    instants = []
    for path, raw in rows:
        try:
            timestamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            raise SignalModelInputRejected(owner, path, "evidence timestamp is unproven") from None
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise SignalModelInputRejected(owner, path, "evidence timestamp must be aware")
        if timestamp > as_of:
            raise SignalModelInputRejected(owner, path, "evidence timestamp exceeds prediction time")
        times.append(timestamp.isoformat())
        instants.append(timestamp)
    if isinstance(evidence, Mapping) and "input_evidence_available_at" in result:
        if instants[:canonical_count] != instants[canonical_count:]:
            raise SignalModelInputRejected(owner, "input_evidence_available_at", "runtime binding differs from canonical evidence times")
        return times[:canonical_count]
    return times


def signal_result_model_view(
    value: SignalResult | Mapping[str, Any],
    *, as_of: datetime | None = None,
    classification_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a downstream-safe view while preserving the canonical artifact."""

    result = value.to_dict() if isinstance(value, SignalResult) else dict(value)
    if as_of is not None:
        result["input_evidence_available_at"] = require_signal_result_pit(value, as_of=as_of)
    execution = result.get("execution")
    execution_status = (
        execution.get("status") if isinstance(execution, Mapping) else None
    )
    state = result.get("state")
    if isinstance(state, Mapping) and state.get("value") == SignalValue.UNAVAILABLE.value:
        result["interpretation"] = {
            "summary": (
                FAILED_SIGNAL_MODEL_SUMMARY
                if isinstance(execution_status, str) and execution_status
                in {status.value for status in _SIGNAL_TECHNICAL_FAILURE_STATUSES}
                else (
                    UNAVAILABLE_SIGNAL_MODEL_SUMMARY
                    if execution_status == SignalExecutionStatus.DOMAIN_UNAVAILABLE.value
                    else UNKNOWN_UNAVAILABLE_SIGNAL_MODEL_SUMMARY
                )
            )
        }
        result["evidence"] = {"supporting": [], "counter": []}
        result["status"] = {"coverage": SignalCoverage.UNAVAILABLE.value}
    else:
        interpretation = dict(result.get("interpretation", {}))
        measurement_context: dict[str, Any] = {
            "categorical_value_is_not_stock_direction": True,
        }
        if classification_contract is not None:
            measurement_context["classification_contract"] = validate_signal_classification_contract(
                classification_contract,
                signal_ref=f"{result['signal_id']}:v{result['version']}",
                result=value,
            )
        if result.get("measurement") is not None:
            measurement = NumericMeasurement.from_dict(result["measurement"])
            measurement_context["numeric_measurement"] = {
                **measurement.to_dict(),
                "numeric_sign": ("positive" if measurement.value > 0 else
                                 "negative" if measurement.value < 0 else "zero"),
                "categorical_state": state.get("value") if isinstance(state, Mapping) else None,
            }
            if measurement.unit in {"fraction", "fraction_difference"}:
                measurement_context["numeric_measurement"]["display"] = {
                    "value": 100 * measurement.value,
                    "unit": "%" if measurement.unit == "fraction" else "percentage_points",
                }
        if result.get("measurement") is not None or str(interpretation.get("summary", "")).startswith(
            str(result.get("signal_id", "")) + "="
        ):
            observations = _numeric_source_observations(result)
            if observations:
                measurement_context["source_observations"] = observations[:8]
                measurement_context["deferred_observation_count"] = max(
                    0, len(observations) - 8
                )
                measurement_context["period_rule"] = (
                    "Use the exact reported start/end duration; fiscal-period "
                    "labels do not turn a cumulative duration into one quarter. "
                    "Keep a computed return with its own dated price anchors."
                )
        interpretation["measurement_context"] = measurement_context
        result["interpretation"] = interpretation
    if isinstance(execution, Mapping):
        result["execution"] = {"status": execution_status}
    return result


def _numeric_source_observations(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project dated numeric literals without inferring missing periods or units."""

    observations: list[dict[str, Any]] = []
    evidence = result.get("evidence", {})
    if not isinstance(evidence, Mapping):
        return observations
    for group in ("supporting", "counter"):
        for index, item in enumerate(evidence.get(group, ())):
            if not isinstance(item, Mapping):
                continue
            try:
                raw = json.loads(item.get("exact_span", ""))
            except (TypeError, ValueError):
                continue
            for row in (raw if isinstance(raw, list) else [raw]):
                if not isinstance(row, Mapping):
                    continue
                date_key, value_key = (
                    ("end", "val" if "val" in row else "value") if "end" in row
                    else ("as_of_date", "adjusted_close")
                )
                number = row.get(value_key)
                if (
                    isinstance(number, bool)
                    or not isinstance(number, (int, float))
                    or not math.isfinite(number)
                ):
                    continue
                dates = {key: row[key] for key in ("start", date_key)
                         if key in row and row[key] is not None}
                try:
                    if date_key not in dates:
                        continue
                    for date in dates.values():
                        datetime.strptime(date, "%Y-%m-%d")
                except (TypeError, ValueError):
                    continue
                observations.append({
                    "evidence_group": group, "evidence_index": index,
                    **dates, value_key: number,
                    **{key: row[key] for key in ("tag", "unit")
                       if isinstance(row.get(key), str)},
                })
    return observations


def signal_execution_failure_result(
    spec: SignalSpec,
    *,
    status: SignalExecutionStatus,
    error_code: str,
    error_message: str,
) -> SignalResult:
    """Build a canonical technical failure without claiming domain unavailability."""

    if status not in _SIGNAL_TECHNICAL_FAILURE_STATUSES:
        raise ValidationError("Signal execution failure requires a technical status")
    return SignalResult(
        signal_id=spec.signal_id,
        version=spec.version,
        value=SignalValue.UNAVAILABLE,
        confidence=0.0,
        interpretation=(
            "Signal execution failed strict validation or execution: "
            + error_message
        ),
        coverage=SignalCoverage.UNAVAILABLE,
        execution_status=status,
        execution_error_code=error_code,
        execution_error_message=error_message,
    )


@dataclass(frozen=True)
class SignalBatchResult:
    """One complete Signal batch returned to whole-batch reflection."""

    results: tuple[SignalResult, ...]
    signal_calls: int
    usage: AgentUsage = field(default_factory=AgentUsage)
    resolutions: tuple[RawInfoResolution, ...] = ()
    document_fingerprints: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    skipped_unchanged_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.signal_calls != len(self.results):
            raise ValidationError("signal_calls must match batch result count")
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "resolutions", tuple(self.resolutions))
        object.__setattr__(
            self,
            "document_fingerprints",
            {
                str(ref): tuple(str(item) for item in fingerprint)
                for ref, fingerprint in self.document_fingerprints.items()
            },
        )
        object.__setattr__(
            self,
            "skipped_unchanged_refs",
            tuple(str(item) for item in self.skipped_unchanged_refs),
        )


@dataclass(frozen=True)
class SignalCard:
    """Compact progressive-disclosure view of one stable Signal."""

    signal_id: str
    version: int
    category: str
    description: str
    execution_type: SignalExecutionType
    learned_profile: Mapping[str, Any] = field(default_factory=dict)
    research_status: Mapping[str, Any] = field(default_factory=dict)
    usage_context: Mapping[str, Any] | None = None
    measurement_scope: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "learned_profile", dict(self.learned_profile))
        object.__setattr__(self, "research_status", _freeze_json(self.research_status))
        object.__setattr__(self, "measurement_scope", _freeze_json(self.measurement_scope))

    @property
    def ref(self) -> str:
        return f"{self.signal_id}:v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        from stock_opportunity_agent.memory.knowledge import empty_performance, usage_context

        return {
            "signal_ref": self.ref,
            "signal_id": self.signal_id,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "execution_type": self.execution_type.value,
            "measurement_scope": _thaw_json(self.measurement_scope),
            "learned_profile": _thaw_json(self.learned_profile),
            "usage_context": usage_context(_thaw_json(self.usage_context)),
            "performance": _thaw_json(self.learned_profile.get("performance", empty_performance())),
            **({"research_status": _thaw_json(self.research_status)} if self.research_status else {}),
        }


@dataclass
class SignalStats:
    """Observed-policy state counts, not causal Signal credit."""

    retrieved: int = 0
    executed: int = 0
    unavailable: int = 0
    states: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            value.value: {"total": 0, "surge": 0}
            for value in SignalValue
        }
    )
    total_tokens: int = 0
    total_cost: float = 0.0
    processed_observation_ids: set[str] = field(default_factory=set)

    def record_retrieval(self) -> None:
        self.retrieved += 1

    def record_result(
        self,
        result: SignalResult,
        *,
        is_surge: bool,
        usage: AgentUsage = AgentUsage(),
    ) -> None:
        if result.execution_status in _SIGNAL_TECHNICAL_FAILURE_STATUSES:
            return
        self.executed += 1
        if result.value is SignalValue.UNAVAILABLE:
            self.unavailable += 1
        bucket = self.states[result.value.value]
        bucket["total"] += 1
        bucket["surge"] += int(is_surge)
        self.total_tokens += usage.tokens
        self.total_cost += usage.cost

    def record_observation(
        self,
        observation_id: str,
        result: SignalResult,
        *,
        is_surge: bool,
        usage: AgentUsage = AgentUsage(),
    ) -> bool:
        """Record one actual occurrence exactly once across restore/reconcile."""

        if not observation_id.strip():
            raise ValidationError("signal observation_id must not be empty")
        if result.execution_status in _SIGNAL_TECHNICAL_FAILURE_STATUSES:
            return False
        if observation_id in self.processed_observation_ids:
            return False
        self.processed_observation_ids.add(observation_id)
        self.record_retrieval()
        self.record_result(result, is_surge=is_surge, usage=usage)
        return True

    def surge_rate(self, value: SignalValue) -> float | None:
        bucket = self.states[value.value]
        if bucket["total"] == 0:
            return None
        return bucket["surge"] / bucket["total"]

    def to_dict(self) -> dict[str, Any]:
        state_statistics: dict[str, Any] = {}
        for value in SignalValue:
            bucket = self.states[value.value]
            state_statistics[value.value] = {
                **bucket,
                "surge_rate": self.surge_rate(value),
            }
        return {
            "usage": {
                "retrieved": self.retrieved,
                "executed": self.executed,
                "unavailable": self.unavailable,
            },
            "state_statistics": state_statistics,
            "cost": {
                "total_tokens": self.total_tokens,
                "total_cost": self.total_cost,
            },
            "processed_observation_ids": sorted(self.processed_observation_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalStats":
        usage = dict(data.get("usage", {}))
        states = {
            value.value: {
                "total": int(
                    dict(data.get("state_statistics", {}))
                    .get(value.value, {})
                    .get("total", 0)
                ),
                "surge": int(
                    dict(data.get("state_statistics", {}))
                    .get(value.value, {})
                    .get("surge", 0)
                ),
            }
            for value in SignalValue
        }
        cost = dict(data.get("cost", {}))
        return cls(
            retrieved=int(usage.get("retrieved", 0)),
            executed=int(usage.get("executed", 0)),
            unavailable=int(usage.get("unavailable", 0)),
            states=states,
            total_tokens=int(cost.get("total_tokens", 0)),
            total_cost=float(cost.get("total_cost", 0.0)),
            processed_observation_ids={
                str(item) for item in data.get("processed_observation_ids", ())
            },
        )


def signal_use_event_id(*, source_record_hash: str, case_id: str, signal_ref: str,
                        signal_round: int, result_index: int) -> str:
    """Bind one use slot to its immutable Plan execution, independent of run names."""

    return _canonical_hash({"source_record_hash": source_record_hash, "case_id": case_id,
        "signal_ref": signal_ref, "signal_round": signal_round, "result_index": result_index})


@dataclass(frozen=True)
class SignalLearningEvent:
    """One committed Plan selection joined to result and revealed outcome."""

    event_id: str
    observation_key: str
    signal_ref: str
    round_id: int
    plan_id: str
    case_id: str
    company_id: str
    prediction_time: str
    selection: Mapping[str, Any]
    result_value: SignalValue
    coverage: SignalCoverage
    document_fingerprint: tuple[str, ...]
    is_surge: bool
    realized_max_multiple: float
    prediction_correct: bool
    reflection_attribution: tuple[str, ...] = ()
    source_record_hash: str = ""
    source_position: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.source_record_hash or self.source_position:
            if (not isinstance(self.source_record_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", self.source_record_hash) is None
                or not isinstance(self.source_position, (list, tuple))
                or len(self.source_position) != 2
                or any(type(index) is not int or index < 0 for index in self.source_position)):
                raise ValidationError("Signal learning source binding is invalid")
            expected_id = signal_use_event_id(source_record_hash=self.source_record_hash,
                case_id=self.case_id, signal_ref=self.signal_ref,
                signal_round=self.source_position[0], result_index=self.source_position[1])
            if self.event_id != expected_id:
                raise ValidationError("Signal learning event id differs from source binding")
            object.__setattr__(self, "source_position", tuple(self.source_position))
        for value, name in (
            (self.event_id, "event_id"),
            (self.observation_key, "observation_key"),
            (self.plan_id, "plan_id"),
            (self.case_id, "case_id"),
            (self.company_id, "company_id"),
        ):
            if not str(value).strip():
                raise ValidationError(f"Signal learning {name} must not be empty")
        _parse_ref(self.signal_ref)
        if self.round_id < 1:
            raise ValidationError("Signal learning round_id must be positive")
        if not math.isfinite(self.realized_max_multiple):
            raise ValidationError(
                "Signal learning realized_max_multiple must be finite"
            )
        selection = dict(self.selection)
        required_selection = {
            "signal_ref",
            "reason_code",
            "selection_reason",
            "applicability_hypothesis",
            "expected_role",
            "context_tags",
        }
        optional_selection = {"target_need_indices"}
        if not required_selection.issubset(selection) or (
            set(selection) - required_selection - optional_selection
        ):
            raise ValidationError("Signal learning selection shape is invalid")
        if selection["signal_ref"] != self.signal_ref:
            raise ValidationError("Signal learning selection ref mismatch")
        if not isinstance(selection["context_tags"], (list, tuple)) or isinstance(
            selection["context_tags"], str
        ):
            raise ValidationError("Signal learning context_tags must be an array")
        if any(
            str(item) not in SIGNAL_CONTEXT_TAGS
            for item in selection["context_tags"]
        ):
            raise ValidationError("Signal learning context tag is not allowed")
        if "target_need_indices" in selection:
            target_need_indices = selection["target_need_indices"]
            if (
                not isinstance(target_need_indices, (list, tuple))
                or isinstance(target_need_indices, str)
                or any(
                    type(index) is not int or index < 0
                    for index in target_need_indices
                )
                or len(set(target_need_indices)) != len(target_need_indices)
                or len(target_need_indices) > 1
            ):
                raise ValidationError(
                    "Signal learning target_need_indices must contain at most "
                    "one unique non-negative integer"
                )
        object.__setattr__(self, "selection", selection)
        object.__setattr__(
            self,
            "document_fingerprint",
            tuple(str(item) for item in self.document_fingerprint),
        )
        object.__setattr__(
            self,
            "reflection_attribution",
            tuple(str(item) for item in self.reflection_attribution),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ("signal-learning-event-v2" if self.source_record_hash
                               else "signal-learning-event-v1"),
            **({"source": {"record_hash": self.source_record_hash,
                "signal_round": self.source_position[0], "result_index": self.source_position[1]}}
               if self.source_record_hash else {}),
            "event_id": self.event_id,
            "observation_key": self.observation_key,
            "signal_ref": self.signal_ref,
            "round_id": self.round_id,
            "plan_id": self.plan_id,
            "case_id": self.case_id,
            "company_id": self.company_id,
            "prediction_time": self.prediction_time,
            "selection": dict(self.selection),
            "result": {
                "value": self.result_value.value,
                "coverage": self.coverage.value,
                "document_fingerprint": list(self.document_fingerprint),
            },
            "outcome": {
                "is_surge": self.is_surge,
                "realized_max_multiple": self.realized_max_multiple,
                "prediction_correct": self.prediction_correct,
            },
            "reflection_attribution": list(self.reflection_attribution),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalLearningEvent":
        schema = data.get("schema_version")
        if schema not in {"signal-learning-event-v1", "signal-learning-event-v2"}:
            raise ValidationError("unsupported Signal learning event schema")
        source = data.get("source")
        if schema == "signal-learning-event-v2":
            if not isinstance(source, Mapping) or set(source) != {"record_hash", "signal_round", "result_index"}:
                raise ValidationError("Signal learning source binding is missing or malformed")
        elif "source" in data:
            raise ValidationError("legacy Signal learning event cannot carry a v2 source")
        result = dict(data.get("result", {}))
        outcome = dict(data.get("outcome", {}))
        if type(outcome.get("is_surge")) is not bool or type(
            outcome.get("prediction_correct")
        ) is not bool:
            raise ValidationError("Signal learning outcome booleans are invalid")
        return cls(
            event_id=str(data["event_id"]),
            observation_key=str(data["observation_key"]),
            signal_ref=str(data["signal_ref"]),
            round_id=int(data["round_id"]),
            plan_id=str(data["plan_id"]),
            case_id=str(data["case_id"]),
            company_id=str(data["company_id"]),
            prediction_time=str(data["prediction_time"]),
            selection=dict(data.get("selection", {})),
            result_value=SignalValue(str(result["value"])),
            coverage=SignalCoverage(str(result["coverage"])),
            document_fingerprint=tuple(
                str(item) for item in result.get("document_fingerprint", ())
            ),
            is_surge=outcome["is_surge"],
            realized_max_multiple=float(outcome["realized_max_multiple"]),
            prediction_correct=outcome["prediction_correct"],
            reflection_attribution=tuple(
                str(item) for item in data.get("reflection_attribution", ())
            ),
            source_record_hash=source["record_hash"] if schema == "signal-learning-event-v2" else "",
            source_position=(source["signal_round"], source["result_index"])
                if schema == "signal-learning-event-v2" else (),
        )


@dataclass(frozen=True)
class FrozenSignalRegistry:
    """Immutable definitions and skills used throughout one fast-loop group."""

    version: int
    registry_hash: str
    specs: tuple[SignalSpec, ...]
    skills: Mapping[str, str]
    learned_profiles: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    learning_hash: str = ""
    research_status: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "specs", tuple(self.specs))
        object.__setattr__(self, "skills", _freeze_json(self.skills))
        object.__setattr__(
            self,
            "learned_profiles",
            _freeze_json({
                str(ref): dict(profile)
                for ref, profile in self.learned_profiles.items()
            }),
        )
        object.__setattr__(self, "research_status", _freeze_json(self.research_status))

    def load_spec(self, signal_ref: str) -> SignalSpec:
        for spec in self.specs:
            if spec.ref == signal_ref:
                return spec
        raise ValidationError(f"unknown frozen signal ref: {signal_ref}")


@dataclass(frozen=True)
class SignalCapabilityAudit:
    """Fail-closed executable-surface audit for one frozen Signal snapshot."""

    enabled_refs: tuple[str, ...]
    disabled: Mapping[str, tuple[str, ...]]

    @property
    def passed(self) -> bool:
        return not self.disabled

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "signal-capability-audit-v1",
            "enabled_refs": list(self.enabled_refs),
            "disabled": {
                ref: list(reasons) for ref, reasons in self.disabled.items()
            },
            "passed": self.passed,
        }


@dataclass(frozen=True)
class SignalRegistryTransition:
    """One exact, recoverable stable-Registry transition."""

    transition_id: str
    input_version: int
    input_hash: str
    output_version: int
    output_hash: str
    promoted: tuple[str, ...]


@dataclass(frozen=True)
class SignalTargetEvaluation:
    """One target-scoped evaluation record referencing a physical observation.

    Direction statistics (SignalStats, surge_rate, learning events) are
    unchanged; these records live in their own namespace keyed by Signal
    version x target x evaluation protocol. Several targets may reference the
    same observation without re-counting the physical execution. A Signal with
    no records for a target is unknown for it -- never zero-filled support.
    """

    evaluation_id: str
    signal_ref: str
    target_id: str
    evaluation_protocol: str
    observation_key: str
    result: str
    created_at: str

    def __post_init__(self) -> None:
        for name in (
            "evaluation_id",
            "signal_ref",
            "target_id",
            "evaluation_protocol",
            "observation_key",
            "result",
            "created_at",
        ):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"Signal target evaluation {name} is required")
        if self.result not in {
            "supported",
            "contradicted",
            "inconclusive",
            "insufficient_evidence",
        }:
            raise ValidationError("Signal target evaluation result is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "signal_ref": self.signal_ref,
            "target_id": self.target_id,
            "evaluation_protocol": self.evaluation_protocol,
            "observation_key": self.observation_key,
            "result": self.result,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalTargetEvaluation":
        required = {
            "evaluation_id",
            "signal_ref",
            "target_id",
            "evaluation_protocol",
            "observation_key",
            "result",
            "created_at",
        }
        if set(data) != required:
            raise ValidationError("Signal target evaluation fields are invalid")
        return cls(
            evaluation_id=str(data["evaluation_id"]),
            signal_ref=str(data["signal_ref"]),
            target_id=str(data["target_id"]),
            evaluation_protocol=str(data["evaluation_protocol"]),
            observation_key=str(data["observation_key"]),
            result=str(data["result"]),
            created_at=str(data["created_at"]),
        )


class SignalRegistry:
    """File-backed progressive-disclosure Signal Registry."""

    def __init__(
        self,
        root: str | Path,
        *,
        candidate_root: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.knowledge_workspace_root = self.root.parent
        self.candidate_root = (
            Path(candidate_root)
            if candidate_root is not None
            else self.root.parent / "signals_candidates"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.candidate_root.mkdir(parents=True, exist_ok=True)
        self._transition_recovery_active = False
        self._fault_injector: Callable[[str, str | None], None] | None = None
        if not self._registry_path.exists():
            _atomic_write_json(self._registry_path, {"version": 1})

    @property
    def version(self) -> int:
        return int(_read_json(self._registry_path).get("version", 1))

    @property
    def _registry_path(self) -> Path:
        return self.root / "registry.json"

    def bump_version(self) -> int:
        """Advance the stable Registry version once after a promotion batch."""

        next_version = self.version + 1
        _atomic_write_json(self._registry_path, {"version": next_version})
        return next_version

    def register_stable(
        self,
        spec: SignalSpec,
        *,
        skill: str | None = None,
        tests: Iterable[Mapping[str, Any]] = (),
    ) -> None:
        """Register one immutable stable version without overwriting history."""

        current = self._latest_spec_or_none(spec.signal_id)
        if current is None and spec.version != 1:
            raise ValidationError("new signal must start at version 1")
        if current is not None and spec.version != current.version + 1:
            raise ValidationError("signal update must create exactly the next version")
        if spec.execution_type is SignalExecutionType.LLM and not (skill or "").strip():
            raise ValidationError("LLM signal requires non-empty skill content")
        if spec.execution_type is SignalExecutionType.DETERMINISTIC and (skill or "").strip():
            raise ValidationError("deterministic signal cannot include LLM skill content")

        signal_dir = self.root / spec.category / spec.signal_id
        version_dir = signal_dir / "versions" / f"v{spec.version}"
        if version_dir.exists():
            raise ValidationError(f"stable signal version already exists: {spec.ref}")
        version_dir.mkdir(parents=True)
        _atomic_write_json(version_dir / "spec.json", spec.to_dict())
        _atomic_write_json(version_dir / "tests.json", {"tests": list(tests)})
        if skill is not None:
            (version_dir / "skill.md").write_text(skill.rstrip() + "\n", encoding="utf-8")
        if not (signal_dir / "stats.json").exists():
            _atomic_write_json(signal_dir / "stats.json", SignalStats().to_dict())
        _atomic_write_json(
            signal_dir / "manifest.json",
            {
                "signal_id": spec.signal_id,
                "category": spec.category,
                "stable_version": spec.version,
            },
        )

    def install_catalog(self, path: str | Path) -> int:
        """Materialize a compact source-controlled seed catalog."""

        catalog = _read_json(Path(path))
        installed = 0
        for item in catalog.get("signals", ()):
            if item.get("enabled", True) is not True:
                continue
            spec = SignalSpec.from_dict(item["spec"])
            if self._latest_spec_or_none(spec.signal_id) is not None:
                continue
            self.register_stable(
                spec,
                skill=item.get("skill"),
                tests=item.get("tests", ()),
            )
            installed += 1
        return installed

    def audit_capabilities(
        self,
        *,
        available_source_types: Iterable[str] = _BUILTIN_ADAPTER_SOURCE_TYPES,
    ) -> SignalCapabilityAudit:
        """Verify that every exposed stable Signal has an executable implementation."""

        functions = default_deterministic_signal_functions()
        available = {item.casefold() for item in available_source_types}
        enabled: list[str] = []
        disabled: dict[str, tuple[str, ...]] = {}
        for card in self.list_signal_cards():
            spec = self.load_spec(card.ref)
            reasons: list[str] = []
            tests_path = (
                self._manifest_for(spec.signal_id).parent
                / "versions"
                / f"v{spec.version}"
                / "tests.json"
            )
            fixtures = tuple(_read_json(tests_path).get("tests", ()))
            if not source_types_compatible(spec.source_types, available):
                reasons.append("acquisition_adapter_missing")
            if not fixtures or any(
                not isinstance(fixture, Mapping)
                or not fixture.get("documents")
                for fixture in fixtures
            ):
                reasons.append("real_schema_fixture_missing")
            if spec.execution_type is SignalExecutionType.DETERMINISTIC:
                if spec.function not in functions:
                    reasons.append("deterministic_function_missing")
                elif not reasons:
                    for index, fixture in enumerate(fixtures):
                        try:
                            _audit_deterministic_fixture(
                                spec, fixture, index=index
                            )
                        except (ValidationError, KeyError, TypeError, ValueError) as exc:
                            reasons.append("schema_fixture_failed: " + str(exc))
                            break
            elif not (self.load_skill(spec.ref) or "").strip():
                reasons.append("llm_skill_missing")
            if reasons:
                disabled[spec.ref] = tuple(reasons)
            else:
                enabled.append(spec.ref)
        return SignalCapabilityAudit(tuple(enabled), disabled)

    def list_categories(self) -> tuple[str, ...]:
        """Return category names without exposing full Signal specs."""

        return tuple(sorted({card.category for card in self.list_signal_cards()}))

    def list_signal_cards(
        self, category: str | None = None, *,
        deterministic_functions: Mapping[str, DeterministicSignalFunction] | None = None,
    ) -> tuple[SignalCard, ...]:
        """Return compact cards for the current stable versions."""

        self._assert_registry_readable()
        from stock_opportunity_agent.memory.knowledge import KnowledgeUseStore

        performance = KnowledgeUseStore(self.knowledge_workspace_root).profiles(publish=False)
        cards: list[SignalCard] = []
        for manifest_path in sorted(self.root.glob("*/*/manifest.json")):
            manifest = _read_json(manifest_path)
            if category is not None and manifest["category"] != category:
                continue
            spec = self.load_spec(
                f"{manifest['signal_id']}:v{int(manifest['stable_version'])}"
            )
            cards.append(
                SignalCard(
                    signal_id=spec.signal_id,
                    version=spec.version,
                    category=spec.category,
                    description=spec.description,
                    execution_type=spec.execution_type,
                    learned_profile={**self.load_learning_profile(spec.ref),
                        **({"performance": performance[spec.ref]} if spec.ref in performance else {})},
                    research_status=self.load_research_status(spec.ref),
                    usage_context=_thaw_json(spec.parameters.get("usage_context")),
                    measurement_scope=signal_measurement_scope(
                        spec, deterministic_functions=deterministic_functions),
                )
            )
        return tuple(sorted(cards, key=lambda card: (card.category, card.signal_id)))

    def search_signal_cards(self, query: str) -> tuple[SignalCard, ...]:
        """Search compact cards without loading full specs."""

        needle = query.casefold()
        return tuple(
            card
            for card in self.list_signal_cards()
            if needle
            in " ".join((card.signal_id, card.category, card.description)).casefold()
        )

    def load_spec(self, signal_ref: str) -> SignalSpec:
        """Load one exact stable version after progressive disclosure."""

        self._assert_registry_readable()
        signal_id, version = _parse_ref(signal_ref)
        manifest_path = self._manifest_for(signal_id)
        manifest = _read_json(manifest_path)
        path = (
            manifest_path.parent
            / "versions"
            / f"v{version}"
            / "spec.json"
        )
        if not path.exists():
            raise ValidationError(f"unknown stable signal ref: {signal_ref}")
        spec = SignalSpec.from_dict(_read_json(path))
        if spec.signal_id != signal_id or spec.version != version:
            raise ValidationError("signal path and spec identity disagree")
        return spec

    def list_version_refs(self) -> tuple[str, ...]:
        """Enumerate immutable versions for history, not current routing eligibility."""

        refs: list[str] = []
        for path in sorted(self.root.glob("*/*/versions/v*/spec.json")):
            relative = path.relative_to(self.root)
            if re.fullmatch(r"v[1-9][0-9]*", relative.parts[3]) is None:
                raise ValidationError("Registry version path is invalid")
            ref = f"{relative.parts[1]}:{relative.parts[3]}"
            if self.load_spec(ref).category != relative.parts[0]:
                raise ValidationError("Registry version category differs from path")
            refs.append(ref)
        if len(refs) != len(set(refs)):
            raise ValidationError("Registry contains duplicate Signal versions")
        return tuple(refs)

    def load_skill(self, signal_ref: str) -> str | None:
        spec = self.load_spec(signal_ref)
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            return None
        manifest_path = self._manifest_for(spec.signal_id)
        path = manifest_path.parent / "versions" / f"v{spec.version}" / "skill.md"
        if not path.exists():
            raise ValidationError(f"LLM signal skill is missing: {signal_ref}")
        return path.read_text(encoding="utf-8")

    def load_tests(self, signal_ref: str) -> tuple[Mapping[str, Any], ...]:
        """Load immutable executable fixtures for one exact stable Signal ref."""

        spec = self.load_spec(signal_ref)
        manifest_path = self._manifest_for(spec.signal_id)
        tests = _read_json(
            manifest_path.parent / "versions" / f"v{spec.version}" / "tests.json"
        ).get("tests", ())
        if not isinstance(tests, list) or any(
            not isinstance(item, Mapping) for item in tests
        ):
            raise ValidationError(
                f"stable signal tests must be a list of objects: {signal_ref}"
            )
        return tuple(dict(item) for item in tests)

    def load_stats(self, signal_id: str) -> SignalStats:
        manifest_path = self._manifest_for(signal_id)
        path = manifest_path.parent / "stats.json"
        if not path.exists():
            # A Registry materialized from definition files only (Slow-history
            # import) has not observed anything in this workspace yet; stats
            # start empty exactly as register_stable initializes them.
            return SignalStats()
        return SignalStats.from_dict(_read_json(path))

    def record_retrieval(self, signal_ref: str) -> None:
        spec = self.load_spec(signal_ref)
        stats = self.load_stats(spec.signal_id)
        stats.record_retrieval()
        self._save_stats(spec.signal_id, stats)

    def record_result(
        self,
        result: SignalResult,
        *,
        is_surge: bool,
        usage: AgentUsage = AgentUsage(),
    ) -> None:
        self.load_spec(result.ref)
        stats = self.load_stats(result.signal_id)
        stats.record_result(result, is_surge=is_surge, usage=usage)
        self._save_stats(result.signal_id, stats)

    def record_observation(
        self,
        observation_id: str,
        result: SignalResult,
        *,
        is_surge: bool,
        usage: AgentUsage = AgentUsage(),
    ) -> bool:
        """Idempotently persist one actual Signal state occurrence."""

        self.load_spec(result.ref)
        stats = self.load_stats(result.signal_id)
        recorded = stats.record_observation(
            observation_id,
            result,
            is_surge=is_surge,
            usage=usage,
        )
        if recorded:
            self._save_stats(result.signal_id, stats)
        return recorded

    def load_learning_events(
        self, signal_ref: str
    ) -> tuple[SignalLearningEvent, ...]:
        """Load the append-only committed learning stream for one exact version."""

        self.load_spec(signal_ref)
        path = self._learning_dir(signal_ref) / "events.jsonl"
        if not path.exists():
            return ()
        events: list[SignalLearningEvent] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                event = SignalLearningEvent.from_dict(json.loads(line))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValidationError(
                    f"invalid Signal learning event at {path}:{line_number}"
                ) from exc
            if event.signal_ref != signal_ref:
                raise ValidationError("Signal learning event path/ref mismatch")
            events.append(event)
        if len({event.event_id for event in events}) != len(events):
            raise ValidationError("duplicate Signal learning event ids on disk")
        return tuple(events)

    def record_target_evaluations(
        self,
        evaluations: Iterable[SignalTargetEvaluation],
    ) -> int:
        """Append target evaluations idempotently by exact evaluation id."""

        records = list(self._load_target_evaluation_rows())
        existing = {record.evaluation_id: record for record in records}
        missing = []
        materialized = tuple(evaluations)
        if any(not isinstance(item, SignalTargetEvaluation) for item in materialized):
            raise ValidationError("target evaluation must be a SignalTargetEvaluation")
        for ref in sorted({item.signal_ref for item in materialized}):
            self.load_spec(ref)
        for evaluation in materialized:
            if evaluation.evaluation_id in existing:
                if existing[evaluation.evaluation_id] != evaluation:
                    raise ValidationError("conflicting Signal target evaluation id")
                continue
            existing[evaluation.evaluation_id] = evaluation
            missing.append(evaluation)
        if missing:
            _atomic_write_text(self._target_evaluations_path(), "".join(
                json.dumps(row.to_dict(), sort_keys=True) + "\n" for row in (*records, *missing)
            ))
        return len(missing)

    def load_target_evaluations(
        self,
        signal_ref: str,
        *,
        target_id: str | None = None,
    ) -> tuple[SignalTargetEvaluation, ...]:
        """Load committed target evaluations for one exact Signal version."""

        self.load_spec(signal_ref)
        records = []
        for evaluation in self._load_target_evaluation_rows():
            if evaluation.signal_ref != signal_ref:
                continue
            if target_id is not None and evaluation.target_id != target_id:
                continue
            records.append(evaluation)
        return tuple(records)

    def target_support(self, signal_ref: str, target_id: str) -> dict[str, Any] | None:
        """Summarize target support; None means unknown, never zero support."""

        records = self.load_target_evaluations(signal_ref, target_id=target_id)
        if not records:
            return None
        counts: dict[str, int] = {}
        for evaluation in records:
            counts[evaluation.result] = counts.get(evaluation.result, 0) + 1
        return {
            "target_id": target_id,
            "signal_ref": signal_ref,
            "evaluation_count": len(records),
            "results": dict(sorted(counts.items())),
            "protocols": sorted(
                {evaluation.evaluation_protocol for evaluation in records}
            ),
        }

    def _target_evaluations_path(self) -> Path:
        return self.root / "target_evaluations.jsonl"

    def _load_target_evaluation_rows(self) -> tuple[SignalTargetEvaluation, ...]:
        path = self._target_evaluations_path()
        if not path.exists():
            return ()
        rows: list[SignalTargetEvaluation] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                rows.append(SignalTargetEvaluation.from_dict(json.loads(line)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValidationError(
                    f"invalid Signal target evaluation at {path}:{line_number}"
                ) from exc
        if len({row.evaluation_id for row in rows}) != len(rows):
            raise ValidationError("duplicate Signal target evaluation ids on disk")
        return tuple(rows)


    def load_learning_profile(self, signal_ref: str) -> dict[str, Any]:
        """Load the rebuildable identity-free profile for one exact version."""

        self.load_spec(signal_ref)
        path = self._learning_dir(signal_ref) / "profile.json"
        if not path.exists():
            return _build_signal_learning_profile(signal_ref, ())
        profile = _read_json(path)
        if (
            profile.get("schema_version") != "signal-learning-profile-v1"
            or profile.get("signal_ref") != signal_ref
        ):
            raise ValidationError("Signal learning profile path/ref mismatch")
        return profile

    def record_learning_event(self, event: SignalLearningEvent) -> bool:
        """Append one event idempotently and atomically rebuild its compact profile."""

        return self.record_learning_events((event,)) == 1

    def record_learning_events(
        self, events: Iterable[SignalLearningEvent]
    ) -> int:
        """Append a committed batch, rebuilding each affected profile only once."""

        grouped: dict[str, list[SignalLearningEvent]] = {}
        for event in events:
            self.load_spec(event.signal_ref)
            grouped.setdefault(event.signal_ref, []).append(event)
        recorded = 0
        for signal_ref, new_events in grouped.items():
            learning_dir = self._learning_dir(signal_ref)
            learning_dir.mkdir(parents=True, exist_ok=True)
            existing = list(self.load_learning_events(signal_ref))
            known_ids = {item.event_id: item for item in existing}
            missing: list[SignalLearningEvent] = []
            for event in new_events:
                if event.event_id in known_ids:
                    if known_ids[event.event_id] != event:
                        raise ValidationError("conflicting Signal learning event id")
                    continue
                known_ids[event.event_id] = event
                missing.append(event)
            profile = _build_signal_learning_profile(signal_ref, (*existing, *missing))
            path = learning_dir / "events.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                for event in missing:
                    handle.write(
                        json.dumps(
                            event.to_dict(),
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                handle.flush()
                os.fsync(handle.fileno())
            _atomic_write_json(
                learning_dir / "profile.json",
                profile,
            )
            recorded += len(missing)
        return recorded

    def committed_learning_events(
        self, signal_ref: str, *, round_cutoff: int,
        imported_events: Iterable[SignalLearningEvent] = (),
    ) -> tuple[SignalLearningEvent, ...]:
        """Select local committed uses plus exact authorized imported uses.

        Source rounds retain their identity and never enlarge the local cutoff.
        Missing or changed copies of authorized imports fail closed.
        """

        if round_cutoff < 0:
            raise ValidationError("Signal learning round cutoff cannot be negative")
        events = self.load_learning_events(signal_ref)
        known = {event.event_id: event for event in events}
        imported_ids = set()
        for imported in imported_events:
            if imported.signal_ref != signal_ref:
                continue
            stored = known.get(imported.event_id)
            if stored is None or stored.to_dict() != imported.to_dict():
                raise ValidationError("imported learning event differs from its Registry copy")
            imported_ids.add(imported.event_id)
        return tuple(event for event in events
            if event.round_id <= round_cutoff or event.event_id in imported_ids)

    def load_committed_learning_profile(
        self, signal_ref: str, *, round_cutoff: int,
        imported_events: Iterable[SignalLearningEvent] = (),
    ) -> dict[str, Any]:
        """Build a routing profile using the same committed use selection."""

        return _build_signal_learning_profile(signal_ref,
            self.committed_learning_events(signal_ref, round_cutoff=round_cutoff,
                imported_events=imported_events))

    def freeze(
        self, *, learning_round_cutoff: int | None = None,
        imported_events: Iterable[SignalLearningEvent] = (),
    ) -> FrozenSignalRegistry:
        """Freeze definitions plus profiles committed by an optional round cutoff."""

        if learning_round_cutoff is not None and learning_round_cutoff < 0:
            raise ValidationError("Signal learning round cutoff cannot be negative")
        imported_events = tuple(imported_events)
        if imported_events and learning_round_cutoff is None:
            raise ValidationError("explicit Signal imports require a local learning cutoff")

        cards = self.list_signal_cards()
        if not cards:
            raise ValidationError("cannot freeze an empty stable Signal Registry")
        audit = self.audit_capabilities()
        if not audit.passed:
            raise ValidationError(
                "Signal capability audit failed: "
                + json.dumps(audit.to_dict(), sort_keys=True)
            )
        specs = tuple(self.load_spec(card.ref) for card in cards)
        for ref in {event.signal_ref for event in imported_events}:
            self.committed_learning_events(ref, round_cutoff=learning_round_cutoff,
                imported_events=imported_events)
        skills = {
            spec.ref: skill
            for spec in specs
            if (skill := self.load_skill(spec.ref)) is not None
        }
        canonical = json.dumps(
            {
                "version": self.version,
                "specs": [spec.to_dict() for spec in specs],
                "skills": skills,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        learned_profiles = {}
        from stock_opportunity_agent.memory.knowledge import KnowledgeUseStore, empty_performance

        performance = KnowledgeUseStore(self.knowledge_workspace_root).profiles(
            round_cutoff=learning_round_cutoff, publish=False)
        for spec in specs:
            if learning_round_cutoff is None:
                profile = self.load_learning_profile(spec.ref)
            else:
                profile = self.load_committed_learning_profile(spec.ref,
                    round_cutoff=learning_round_cutoff, imported_events=imported_events)
            profile["performance"] = performance.get(spec.ref, empty_performance())
            learned_profiles[spec.ref] = profile
        research_status = {card.ref: dict(card.research_status) for card in cards if card.research_status}
        learning_canonical = json.dumps(
            {"profiles": learned_profiles, "research_status": research_status} if research_status else learned_profiles,
            sort_keys=True,
            separators=(",", ":"),
        )
        return FrozenSignalRegistry(
            version=self.version,
            registry_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            specs=specs,
            skills=skills,
            learned_profiles=learned_profiles,
            research_status=research_status,
            learning_hash=hashlib.sha256(
                learning_canonical.encode("utf-8")
            ).hexdigest(),
        )

    def stage_candidate(
        self,
        spec: SignalSpec,
        *,
        skill: str | None = None,
        tests: Iterable[Mapping[str, Any]] = (),
        origin: str,
    ) -> str:
        """Write a candidate outside the stable registry."""

        if not origin.strip():
            raise ValidationError("signal candidate origin is required")
        if spec.execution_type is SignalExecutionType.LLM and not (skill or "").strip():
            raise ValidationError("LLM signal candidate requires skill content")
        if spec.execution_type is SignalExecutionType.DETERMINISTIC and (skill or "").strip():
            raise ValidationError(
                "deterministic signal candidate cannot include LLM skill content"
            )
        materialized_tests = [dict(item) for item in tests]
        version_dir = (
            self.candidate_root
            / spec.category
            / spec.signal_id
            / f"v{spec.version}"
        )
        sibling_category = next(
            (
                sibling.parent.name
                for sibling in self.candidate_root.glob(f"*/{spec.signal_id}")
                if sibling.parent.name not in (spec.category, ".rejected")
            ),
            None,
        )
        if sibling_category is not None:
            # Candidate refs resolve by signal_id across categories, so one
            # signal_id staged under two categories makes every later load
            # ambiguous; reject at the write instead of corrupting the cycle.
            raise ValidationError(
                f"conflicting signal candidate: {spec.signal_id} is already "
                f"staged under category {sibling_category}; choose a "
                "distinct signal_id"
            )
        if version_dir.exists():
            existing = SignalSpec.from_dict(_read_json(version_dir / "spec.json"))
            existing_skill_path = version_dir / "skill.md"
            existing_skill = (
                existing_skill_path.read_text(encoding="utf-8").strip()
                if existing_skill_path.exists()
                else None
            )
            existing_origin = str(
                _read_json(version_dir / "candidate.json").get("origin", "")
            )
            exact_replay = (
                existing == spec
                and existing_skill == ((skill or "").strip() or None)
                and self.load_candidate_tests(spec.ref) == tuple(materialized_tests)
                and existing_origin == origin
            )
            if exact_replay:
                return spec.ref
            validation_path = version_dir / "validation.json"
            validation = (
                _read_json(validation_path) if validation_path.exists() else {}
            )
            if validation.get("status") != "rejected":
                raise ValidationError(f"conflicting signal candidate: {spec.ref}")
            candidate_hash = self.candidate_hash(spec.ref)
            archive_identity = hashlib.sha256(
                json.dumps(
                    {
                        "candidate_hash": candidate_hash,
                        "origin": existing_origin,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            archive_dir = (
                self.candidate_root
                / ".rejected"
                / existing.category
                / existing.signal_id
                / f"v{existing.version}"
                / archive_identity
            )
            duplicate_index = 2
            while archive_dir.exists():
                archive_dir = archive_dir.with_name(
                    f"{archive_identity}-{duplicate_index}"
                )
                duplicate_index += 1
            archive_dir.parent.mkdir(parents=True, exist_ok=True)
            os.replace(version_dir, archive_dir)
        version_dir.mkdir(parents=True)
        _atomic_write_json(version_dir / "spec.json", spec.to_dict())
        _atomic_write_json(version_dir / "tests.json", {"tests": materialized_tests})
        _atomic_write_json(version_dir / "candidate.json", {"origin": origin})
        if skill is not None:
            _write_or_verify_text(version_dir / "skill.md", skill.rstrip() + "\n")
        return spec.ref

    def load_candidate(self, signal_ref: str) -> tuple[SignalSpec, str | None]:
        spec_path = self._candidate_spec_path(signal_ref)
        spec = SignalSpec.from_dict(_read_json(spec_path))
        skill_path = spec_path.parent / "skill.md"
        return spec, (
            skill_path.read_text(encoding="utf-8") if skill_path.exists() else None
        )

    def load_candidate_tests(
        self, signal_ref: str
    ) -> tuple[Mapping[str, Any], ...]:
        """Load immutable candidate fixtures used by executable validation."""

        tests = _read_json(
            self._candidate_spec_path(signal_ref).parent / "tests.json"
        ).get("tests", ())
        if not isinstance(tests, list) or any(not isinstance(item, Mapping) for item in tests):
            raise ValidationError(f"candidate tests must be a list of objects: {signal_ref}")
        return tuple(dict(item) for item in tests)

    def candidate_hash(self, signal_ref: str) -> str:
        """Hash the exact staged spec, skill, and executable fixtures."""

        spec, skill = self.load_candidate(signal_ref)
        payload = {
            "spec": spec.to_dict(),
            "skill": (skill.rstrip() if skill is not None else None),
            "tests": list(self.load_candidate_tests(signal_ref)),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def record_candidate_admission(
        self,
        signal_ref: str,
        *,
        input_registry_hash: str,
        validator_hash: str,
        research_targets: Iterable[str],
        contract_validation: Mapping[str, Any],
        research_provenance: Mapping[str, Any] | None = None,
    ) -> str:
        """Bind a technical decision to content without claiming predictive effect."""

        candidate_hash = self.candidate_hash(signal_ref)
        supplied_targets = tuple(research_targets)
        contract = dict(contract_validation)
        if not supplied_targets or any(not isinstance(item, str) or not _SAFE_ID.fullmatch(item) for item in supplied_targets):
            raise ValidationError("admission research targets must be non-empty safe ids")
        targets = tuple(sorted(set(supplied_targets)))
        if any(not isinstance(value, str) or not _SHA256.fullmatch(value) for value in (input_registry_hash, validator_hash)):
            raise ValidationError("admission Registry and validator hashes are invalid")
        accepted = contract.get("accepted")
        reasons = contract.get("reasons")
        executed_tests = contract.get("executed_tests")
        fixture_count = len(self.load_candidate_tests(signal_ref))
        if (
            type(accepted) is not bool
            or not isinstance(reasons, list)
            or any(not isinstance(reason, str) or not reason.strip() for reason in reasons)
            or type(executed_tests) is not int
            or not 0 <= executed_tests <= fixture_count
            or (accepted and (reasons or fixture_count == 0 or executed_tests != fixture_count))
            or (not accepted and not reasons)
        ):
            raise ValidationError("admission requires a complete technical validation result")
        identity = {
            "schema_version": "signal-candidate-admission-identity-v1",
            "signal_ref": signal_ref,
            "candidate_hash": candidate_hash,
            "input_registry_hash": input_registry_hash,
            "validator_hash": validator_hash,
            "research_targets": list(targets),
            "contract_validation": contract,
        }
        if research_provenance is not None:
            _validate_research_provenance(research_provenance)
            identity["research_provenance"] = dict(research_provenance)
        key = _admission_identity_key(identity)
        record = {
            "schema_version": "signal-candidate-admission-v1",
            "evaluation_key": key,
            "admission_identity": identity,
            "signal_ref": signal_ref,
            "candidate_hash": candidate_hash,
            "accepted": accepted,
            "status": "admitted" if accepted else "rejected",
            "reasons": reasons,
            "contract_validation": contract,
        }
        candidate_dir = self._candidate_spec_path(signal_ref).parent
        _write_or_verify_json(candidate_dir / "evaluations" / f"{key}.json", record)
        _atomic_write_json(candidate_dir / "validation.json", {
            "schema_version": "signal-candidate-validation-pointer-v1",
            "signal_ref": signal_ref,
            "candidate_hash": candidate_hash,
            "latest_evaluation_key": key,
            "status": record["status"],
        })
        return key

    def load_research_status(self, signal_ref: str) -> dict[str, Any]:
        """Read published version-bound admission; legacy versions have no new status."""

        spec = self.load_spec(signal_ref)
        version_dir = self._manifest_for(spec.signal_id).parent / "versions" / f"v{spec.version}"
        manifest = _read_json(version_dir.parent.parent / "manifest.json")
        admission_keys = manifest.get("admission_keys", {})
        if not isinstance(admission_keys, Mapping) or any(
            not isinstance(version, str) or not re.fullmatch(r"[1-9][0-9]*", version)
            or not isinstance(key, str) or not _SHA256.fullmatch(key)
            for version, key in admission_keys.items()
        ):
            raise ValidationError("published Signal admission key map is invalid")
        path = version_dir / "admission.json"
        if not path.exists():
            # A manifest explicitly declaring admission cannot silently lose its proof.
            if str(spec.version) in admission_keys:
                raise ValidationError("published Signal admission record is missing")
            return {}
        record = _read_json(path)
        _validate_admission_record(record, signal_ref=signal_ref)
        if admission_keys.get(str(spec.version)) != record["evaluation_key"]:
            raise ValidationError("published Signal admission key differs from manifest")
        skill = self.load_skill(signal_ref)
        stable_hash = hashlib.sha256(json.dumps({
            "spec": spec.to_dict(),
            "skill": skill.rstrip() if skill is not None else None,
            "tests": list(self.load_tests(signal_ref)),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if record["candidate_hash"] != stable_hash or record["accepted"] is not True:
            raise ValidationError("published Signal admission differs from version content")
        return {
            "technical_status": "admitted",
            "effect_status": "unverified",
            "research_targets": list(record["admission_identity"]["research_targets"]),
            "admission_key": record["evaluation_key"],
        }

    def record_candidate_effectiveness(
        self,
        signal_ref: str,
        *,
        admission_key: str,
        evaluation_identity: Mapping[str, Any] | None,
        effectiveness: Mapping[str, Any],
        observation_status: str = "completed",
    ) -> str:
        """Save independent effect evidence or a failure without changing admission."""

        admission = self.load_candidate_validation(signal_ref, evaluation_key=admission_key)
        if admission is None or admission.get("schema_version") != "signal-candidate-admission-v1" or admission.get("accepted") is not True:
            raise ValidationError("effect observation requires exact successful technical admission")
        if observation_status not in {"completed", "failed"} or (
            evaluation_identity is None and observation_status != "failed"
        ):
            raise ValidationError("effect observation status/identity is invalid")
        if evaluation_identity is None:
            evaluation_key, identity = None, None
        else:
            evaluation_key, identity = self.candidate_evaluation_key(
                signal_ref, candidate_hash=self.candidate_hash(signal_ref), evaluation_identity=evaluation_identity,
            )
        record = {
            "schema_version": "signal-candidate-effect-observation-v1",
            "signal_ref": signal_ref,
            "candidate_hash": self.candidate_hash(signal_ref),
            "admission_key": admission_key,
            "evaluation_key": evaluation_key,
            "evaluation_identity": identity,
            "observation_status": observation_status,
            "effectiveness": dict(effectiveness),
        }
        key = _canonical_hash(record)
        _write_or_verify_json(self._candidate_spec_path(signal_ref).parent / "effects" / f"{key}.json", {**record, "effect_key": key})
        return key

    def list_candidate_effectiveness(self, signal_ref: str) -> tuple[Mapping[str, Any], ...]:
        """Load independently hash-bound effect observations, including failures."""

        rows = []
        candidate_hash = self.candidate_hash(signal_ref)
        for path in sorted((self._candidate_spec_path(signal_ref).parent / "effects").glob("*.json")):
            row = _read_json(path)
            key = row.get("effect_key")
            identity = row.get("evaluation_identity")
            if (
                row.get("schema_version") != "signal-candidate-effect-observation-v1"
                or row.get("signal_ref") != signal_ref or row.get("candidate_hash") != candidate_hash
                or key != path.stem or key != _canonical_hash({name: value for name, value in row.items() if name != "effect_key"})
                or row.get("observation_status") not in {"completed", "failed"}
            ):
                raise ValidationError("candidate effect observation identity is invalid")
            if identity is None:
                if row["observation_status"] != "failed" or row.get("evaluation_key") is not None:
                    raise ValidationError("effect observation lacks its evaluation identity")
            else:
                if not isinstance(identity, Mapping) or not set(_CANDIDATE_EVALUATION_HASH_FIELDS).issubset(identity):
                    raise ValidationError("candidate effect evaluation identity is invalid")
                evaluation_key, expected_identity = self.candidate_evaluation_key(
                    signal_ref, candidate_hash=candidate_hash,
                    evaluation_identity={name: identity[name] for name in _CANDIDATE_EVALUATION_HASH_FIELDS},
                )
                if identity != expected_identity or row.get("evaluation_key") != evaluation_key:
                    raise ValidationError("candidate effect evaluation identity is invalid")
            admission = self.load_candidate_validation(signal_ref, evaluation_key=str(row.get("admission_key", "")))
            if admission is None or admission.get("schema_version") != "signal-candidate-admission-v1" or admission.get("accepted") is not True:
                raise ValidationError("effect observation admission is invalid")
            rows.append(row)
        return tuple(rows)

    def record_candidate_validation(
        self,
        signal_ref: str,
        *,
        candidate_hash: str,
        evaluation_identity: Mapping[str, Any],
        accepted: bool,
        reasons: Iterable[str],
        contract_validation: Mapping[str, Any] | None = None,
        effectiveness: Mapping[str, Any] | None = None,
    ) -> str:
        """Persist one immutable evaluation without changing the stable Registry."""

        if candidate_hash != self.candidate_hash(signal_ref):
            raise ValidationError("candidate changed before validation was recorded")
        evaluation_key, identity = self.candidate_evaluation_key(
            signal_ref,
            candidate_hash=candidate_hash,
            evaluation_identity=evaluation_identity,
        )
        candidate_dir = self._candidate_spec_path(signal_ref).parent
        path = candidate_dir / "evaluations" / f"{evaluation_key}.json"
        effectiveness_value = dict(effectiveness or {})
        disposition = str(effectiveness_value.get("disposition", "rejected"))
        if disposition not in {"promoted", "provisional", "rejected"}:
            raise ValidationError("candidate evaluation disposition is invalid")
        if accepted != (
            disposition == "promoted"
            and effectiveness_value.get("accepted") is True
        ):
            raise ValidationError(
                "candidate accepted state must match promoted effectiveness"
            )
        _write_or_verify_json(
            path,
            {
                "schema_version": "signal-candidate-evaluation-v3",
                "evaluation_key": evaluation_key,
                "evaluation_identity": identity,
                "signal_ref": signal_ref,
                "candidate_hash": candidate_hash,
                "accepted": bool(accepted),
                "status": disposition,
                "reasons": [str(item) for item in reasons],
                "contract_validation": dict(contract_validation or {}),
                "effectiveness": effectiveness_value,
            },
        )
        _atomic_write_json(
            candidate_dir / "validation.json",
            {
                "schema_version": "signal-candidate-validation-pointer-v1",
                "signal_ref": signal_ref,
                "candidate_hash": candidate_hash,
                "latest_evaluation_key": evaluation_key,
                "status": disposition,
            },
        )
        return evaluation_key

    def candidate_evaluation_key(
        self,
        signal_ref: str,
        *,
        candidate_hash: str,
        evaluation_identity: Mapping[str, Any],
    ) -> tuple[str, dict[str, str]]:
        """Validate and hash the complete identity of one candidate evaluation."""

        if candidate_hash != self.candidate_hash(signal_ref):
            raise ValidationError("candidate evaluation hash differs from staged content")
        if set(evaluation_identity) != _CANDIDATE_EVALUATION_HASH_FIELDS:
            raise ValidationError(
                "candidate evaluation identity requires exactly: "
                + ", ".join(sorted(_CANDIDATE_EVALUATION_HASH_FIELDS))
            )
        identity = {
            "candidate_hash": candidate_hash,
            **{
                field: str(evaluation_identity[field])
                for field in sorted(_CANDIDATE_EVALUATION_HASH_FIELDS)
            },
        }
        if any(not _SHA256.fullmatch(value) for value in identity.values()):
            raise ValidationError("candidate evaluation identity hashes are invalid")
        canonical = json.dumps(
            {
                "schema_version": "signal-candidate-evaluation-identity-v1",
                **identity,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), identity

    def load_candidate_validation(
        self,
        signal_ref: str,
        *,
        evaluation_key: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Return one immutable evaluation, defaulting to the latest pointer."""

        candidate_dir = self._candidate_spec_path(signal_ref).parent
        pointer_path = candidate_dir / "validation.json"
        if evaluation_key is not None:
            if not _SHA256.fullmatch(evaluation_key):
                raise ValidationError("candidate evaluation key is invalid")
            path = candidate_dir / "evaluations" / f"{evaluation_key}.json"
        else:
            path = pointer_path
        if not path.exists():
            return None
        validation = _read_json(path)
        if (
            evaluation_key is None
            and validation.get("schema_version")
            == "signal-candidate-validation-pointer-v1"
        ):
            pointed_key = str(validation.get("latest_evaluation_key", ""))
            if not _SHA256.fullmatch(pointed_key):
                raise ValidationError("candidate validation pointer is invalid")
            validation = _read_json(
                candidate_dir / "evaluations" / f"{pointed_key}.json"
            )
            evaluation_key = pointed_key
        if validation.get("candidate_hash") != self.candidate_hash(signal_ref):
            raise ValidationError("candidate validation hash differs from staged content")
        if validation.get("schema_version") == "signal-candidate-admission-v1":
            _validate_admission_record(validation, signal_ref=signal_ref)
        if validation.get("schema_version") in {"signal-candidate-evaluation-v3", "signal-candidate-admission-v1"}:
            stored_key = str(validation.get("evaluation_key", ""))
            if evaluation_key is not None and stored_key != evaluation_key:
                raise ValidationError("candidate evaluation path and identity differ")
        return validation

    def list_candidate_evaluations(
        self,
        signal_ref: str,
    ) -> tuple[Mapping[str, Any], ...]:
        """Return every immutable v3 evaluation in key order."""

        candidate_dir = self._candidate_spec_path(signal_ref).parent
        return tuple(
            _read_json(path)
            for path in sorted((candidate_dir / "evaluations").glob("*.json"))
        )

    def promote_validated_batch(
        self,
        validated_candidates: Mapping[str, str],
        *,
        validated_evaluations: Mapping[str, str] | None = None,
        transition_id: str,
        input_version: int,
        input_hash: str,
        input_refs: Iterable[str],
    ) -> SignalRegistryTransition:
        """Idempotently promote one durably staged machine-validated batch."""

        _validate_id(transition_id, "Signal transition id")
        ordered_candidates = tuple(sorted(validated_candidates.items()))
        ordered_evaluations = tuple(sorted((validated_evaluations or {}).items()))
        if validated_evaluations is not None and (
            set(validated_evaluations) != set(validated_candidates)
            or any(not _SHA256.fullmatch(key) for key in validated_evaluations.values())
        ):
            raise ValidationError(
                "validated candidate evaluations must bind every candidate to one key"
            )
        ordered_input_refs = tuple(str(item) for item in input_refs)
        if len(set(ordered_input_refs)) != len(ordered_input_refs):
            raise ValidationError("Signal transition input refs must be unique")
        if input_version < 1 or not re.fullmatch(r"[0-9a-f]{64}", input_hash):
            raise ValidationError("Signal transition input identity is invalid")
        transition_path = self.root / ".transitions" / f"{transition_id}.json"
        intent = {
            "schema_version": (
                "signal-registry-transition-v2"
                if validated_evaluations is not None
                else "signal-registry-transition-v1"
            ),
            "transition_id": transition_id,
            "input_registry_version": input_version,
            "input_registry_hash": input_hash,
            "input_signal_refs": list(ordered_input_refs),
            "validated_candidates": dict(ordered_candidates),
            **(
                {"validated_evaluations": dict(ordered_evaluations)}
                if validated_evaluations is not None
                else {}
            ),
        }
        if transition_path.exists():
            stored_transition = _read_json(transition_path)
            for field, expected in intent.items():
                if stored_transition.get(field) != expected:
                    raise ValidationError("Signal transition replay identity mismatch")
        else:
            current = self.freeze()
            if current.version != input_version or current.registry_hash != input_hash:
                raise ValidationError(
                    "stable Signal Registry differs before automatic promotion"
                )
            if tuple(spec.ref for spec in current.specs) != ordered_input_refs:
                raise ValidationError("Signal transition input refs differ from snapshot")
            self._validate_promotion_candidates(
                ordered_candidates,
                input_refs=ordered_input_refs,
                input_hash=input_hash,
                validated_evaluations=(
                    dict(ordered_evaluations)
                    if validated_evaluations is not None
                    else None
                ),
            )
            _atomic_write_json(transition_path, {**intent, "status": "prepared"})
            self._fault_checkpoint("after_transition_prepared")

        self._transition_recovery_active = True
        try:
            return self._apply_prepared_transition(
                transition_path=transition_path,
                intent=intent,
                transition_id=transition_id,
                input_version=input_version,
                input_hash=input_hash,
                input_refs=ordered_input_refs,
                ordered_candidates=ordered_candidates,
                validated_evaluations=(
                    dict(ordered_evaluations)
                    if validated_evaluations is not None
                    else None
                ),
            )
        finally:
            self._transition_recovery_active = False

    def _apply_prepared_transition(
        self,
        *,
        transition_path: Path,
        intent: Mapping[str, Any],
        transition_id: str,
        input_version: int,
        input_hash: str,
        input_refs: tuple[str, ...],
        ordered_candidates: tuple[tuple[str, str], ...],
        validated_evaluations: Mapping[str, str] | None,
    ) -> SignalRegistryTransition:
        self._verify_transition_base(
            input_version=input_version,
            input_hash=input_hash,
            input_refs=input_refs,
            validated_candidates=ordered_candidates,
            validated_evaluations=validated_evaluations,
        )
        promoted_specs: list[SignalSpec] = []
        for signal_ref, candidate_hash in ordered_candidates:
            spec, skill = self.load_candidate(signal_ref)
            if self.candidate_hash(signal_ref) != candidate_hash:
                raise ValidationError(
                    f"validated candidate changed before promotion: {signal_ref}"
                )
            self._materialize_candidate_version(spec, skill=skill)
            validation = self.load_candidate_validation(
                signal_ref,
                evaluation_key=validated_evaluations[signal_ref] if validated_evaluations is not None else None,
            )
            if validation is not None and validation.get("schema_version") == "signal-candidate-admission-v1":
                version_dir = self.root / spec.category / spec.signal_id / "versions" / f"v{spec.version}"
                _write_or_verify_json(version_dir / "admission.json", validation)
                manifest_path = version_dir.parent.parent / "manifest.json"
                manifest = _read_json(manifest_path)
                _atomic_write_json(manifest_path, {**manifest, "admission_keys": {
                    **manifest.get("admission_keys", {}), str(spec.version): validation["evaluation_key"],
                }})
                self._fault_checkpoint("after_stable_admission", signal_ref)
            promoted_specs.append(spec)

        if ordered_candidates:
            if self.version == input_version:
                self.bump_version()
                self._fault_checkpoint("after_registry_version")
            elif self.version != input_version + 1:
                raise ValidationError("Signal Registry version advanced unexpectedly")
        elif self.version != input_version:
            raise ValidationError("empty Signal transition changed Registry version")
        self._fault_checkpoint("before_output_snapshot")
        output = self.freeze()
        self._fault_checkpoint("after_output_snapshot")
        for spec in promoted_specs:
            candidate_dir = self._candidate_spec_path(spec.ref).parent
            _write_or_verify_json(
                candidate_dir / "promotion.json",
                {
                    "promoted": True,
                    "mode": "automatic_after_machine_validation",
                    "transition_id": transition_id,
                    **(
                        {"evaluation_key": validated_evaluations[spec.ref]}
                        if validated_evaluations is not None
                        else {}
                    ),
                    "output_registry_version": output.version,
                    "output_registry_hash": output.registry_hash,
                },
            )
            self._fault_checkpoint("after_promotion_record", spec.ref)
        completed = {
            **dict(intent),
            "status": "applied",
            "output_registry_version": output.version,
            "output_registry_hash": output.registry_hash,
            "promoted": [spec.ref for spec in promoted_specs],
        }
        self._fault_checkpoint("before_transition_applied")
        _atomic_write_json(transition_path, completed)
        return SignalRegistryTransition(
            transition_id=transition_id,
            input_version=input_version,
            input_hash=input_hash,
            output_version=output.version,
            output_hash=output.registry_hash,
            promoted=tuple(spec.ref for spec in promoted_specs),
        )

    def _assert_registry_readable(self) -> None:
        if self._transition_recovery_active:
            return
        for path in sorted((self.root / ".transitions").glob("*.json")):
            if _read_json(path).get("status") == "prepared":
                raise ValidationError(
                    "Signal Registry has a prepared transition requiring recovery"
                )

    def _fault_checkpoint(self, stage: str, signal_ref: str | None = None) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage, signal_ref)

    def _validate_promotion_candidates(
        self,
        candidates: tuple[tuple[str, str], ...],
        *,
        input_refs: tuple[str, ...],
        input_hash: str,
        validated_evaluations: Mapping[str, str] | None = None,
    ) -> None:
        input_by_id = {
            _parse_ref(signal_ref)[0]: signal_ref for signal_ref in input_refs
        }
        seen_signal_ids: set[str] = set()
        for signal_ref, expected_hash in candidates:
            spec, _skill = self.load_candidate(signal_ref)
            if spec.ref != signal_ref:
                raise ValidationError("candidate ref differs from staged SignalSpec")
            if spec.signal_id in seen_signal_ids:
                raise ValidationError(
                    "promotion batch cannot contain multiple versions of one Signal"
                )
            seen_signal_ids.add(spec.signal_id)
            if self.candidate_hash(signal_ref) != expected_hash:
                raise ValidationError(
                    f"validated candidate hash does not match staged content: {signal_ref}"
                )
            validation = self.load_candidate_validation(
                signal_ref,
                evaluation_key=(
                    validated_evaluations[signal_ref]
                    if validated_evaluations is not None
                    else None
                ),
            )
            if validation is None:
                raise ValidationError(
                    f"candidate requires matching successful validation: {signal_ref}"
                )
            is_admission = validation.get("schema_version") == "signal-candidate-admission-v1"
            if is_admission:
                _validate_admission_record(validation, signal_ref=signal_ref)
            if (
                not validation.get("accepted")
                or validation.get("candidate_hash") != expected_hash
                or validation.get("schema_version")
                not in {
                    "signal-candidate-validation-v2",
                    "signal-candidate-evaluation-v3",
                    "signal-candidate-admission-v1",
                }
                or (not is_admission and dict(validation.get("effectiveness", {})).get("accepted") is not True)
                or (is_admission and (
                    validation["admission_identity"]["input_registry_hash"] != input_hash
                    or validation["contract_validation"]["executed_tests"] != len(self.load_candidate_tests(signal_ref))
                ))
            ):
                raise ValidationError(
                    f"candidate requires matching successful validation: {signal_ref}"
                )
            self._audit_candidate_for_stable(spec, signal_ref=signal_ref)
            prior_ref = input_by_id.get(spec.signal_id)
            if prior_ref is None and spec.version != 1:
                raise ValidationError("new signal must start at version 1")
            if prior_ref is not None:
                prior = self.load_spec(prior_ref)
                if spec.category != prior.category or spec.version != prior.version + 1:
                    raise ValidationError(
                        "signal update must preserve category and create exactly the next version"
                    )

    def _audit_candidate_for_stable(
        self,
        spec: SignalSpec,
        *,
        signal_ref: str,
    ) -> None:
        tests = self.load_candidate_tests(signal_ref)
        if not set(spec.source_types).intersection(_BUILTIN_ADAPTER_SOURCE_TYPES):
            raise ValidationError(
                f"candidate has no stable acquisition adapter: {signal_ref}"
            )
        if not tests or any(not fixture.get("documents") for fixture in tests):
            raise ValidationError(
                f"candidate lacks a real-schema stable fixture: {signal_ref}"
            )
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            functions = default_deterministic_signal_functions()
            if spec.function not in functions:
                raise ValidationError(
                    f"candidate deterministic function is not stable: {signal_ref}"
                )
            for index, fixture in enumerate(tests):
                try:
                    _audit_deterministic_fixture(spec, fixture, index=index)
                except (ValidationError, KeyError, TypeError, ValueError) as exc:
                    raise ValidationError(
                        f"candidate stable fixture failed: {signal_ref}: {exc}"
                    ) from exc

    def _verify_transition_base(
        self,
        *,
        input_version: int,
        input_hash: str,
        input_refs: tuple[str, ...],
        validated_candidates: tuple[tuple[str, str], ...],
        validated_evaluations: Mapping[str, str] | None = None,
    ) -> None:
        if self.version not in {input_version, input_version + 1}:
            raise ValidationError("Signal transition Registry version is inconsistent")
        if self.snapshot_from_refs(input_version, input_refs).registry_hash != input_hash:
            raise ValidationError("Signal transition input snapshot changed")
        input_by_id = {_parse_ref(ref)[0]: ref for ref in input_refs}
        candidate_by_id = {
            _parse_ref(ref)[0]: ref for ref, _candidate_hash in validated_candidates
        }
        current_by_id = {
            card.signal_id: card.ref for card in self.list_signal_cards()
        }
        current_ids = set(current_by_id)
        input_ids = set(input_by_id)
        allowed_ids = input_ids | set(candidate_by_id)
        if not input_ids.issubset(current_ids) or not current_ids.issubset(allowed_ids):
            raise ValidationError("unrelated stable Signal mutation during transition")
        for signal_id, current_ref in current_by_id.items():
            allowed = {input_by_id.get(signal_id), candidate_by_id.get(signal_id)}
            if current_ref not in allowed:
                raise ValidationError("stable Signal changed outside transition batch")
        self._validate_promotion_candidates(
            validated_candidates,
            input_refs=input_refs,
            input_hash=input_hash,
            validated_evaluations=validated_evaluations,
        )

    def snapshot_from_refs(
        self,
        version: int,
        signal_refs: tuple[str, ...],
    ) -> FrozenSignalRegistry:
        """Recompute an ordered immutable definition snapshot for lineage checks.

        Callers compare the returned hash with their frozen input authority.
        This reconstructs definitions only, never committed learned profiles.
        """
        specs = tuple(self.load_spec(signal_ref) for signal_ref in signal_refs)
        skills = {
            spec.ref: skill
            for spec in specs
            if (skill := self.load_skill(spec.ref)) is not None
        }
        canonical = json.dumps(
            {
                "version": version,
                "specs": [spec.to_dict() for spec in specs],
                "skills": skills,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return FrozenSignalRegistry(
            version=version,
            registry_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            specs=specs,
            skills=skills,
        )

    def _materialize_candidate_version(
        self,
        spec: SignalSpec,
        *,
        skill: str | None,
    ) -> None:
        candidate_dir = self._candidate_spec_path(spec.ref).parent
        tests = _read_json(candidate_dir / "tests.json").get("tests", ())
        signal_dir = self.root / spec.category / spec.signal_id
        version_dir = signal_dir / "versions" / f"v{spec.version}"
        version_dir.mkdir(parents=True, exist_ok=True)
        _write_or_verify_json(version_dir / "spec.json", spec.to_dict())
        self._fault_checkpoint("after_stable_spec", spec.ref)
        _write_or_verify_json(version_dir / "tests.json", {"tests": list(tests)})
        self._fault_checkpoint("after_stable_tests", spec.ref)
        if skill is not None:
            _write_or_verify_text(version_dir / "skill.md", skill.rstrip() + "\n")
            self._fault_checkpoint("after_stable_skill", spec.ref)
        if not (signal_dir / "stats.json").exists():
            _atomic_write_json(signal_dir / "stats.json", SignalStats().to_dict())
        self._fault_checkpoint("after_stable_stats", spec.ref)
        manifest_path = signal_dir / "manifest.json"
        expected_manifest = {
            "signal_id": spec.signal_id,
            "category": spec.category,
            "stable_version": spec.version,
        }
        if manifest_path.exists():
            manifest = _read_json(manifest_path)
            stable_version = int(manifest["stable_version"])
            if "admission_keys" in manifest:
                expected_manifest["admission_keys"] = dict(manifest["admission_keys"])
            if stable_version not in {spec.version - 1, spec.version}:
                raise ValidationError("stable Signal manifest changed during promotion")
            if manifest.get("signal_id") != spec.signal_id or manifest.get("category") != spec.category:
                raise ValidationError("stable Signal manifest identity mismatch")
        _atomic_write_json(manifest_path, expected_manifest)
        self._fault_checkpoint("after_stable_manifest", spec.ref)

    def _candidate_spec_path(self, signal_ref: str) -> Path:
        signal_id, version = _parse_ref(signal_ref)
        matches = list(
            self.candidate_root.glob(f"*/{signal_id}/v{version}/spec.json")
        )
        if len(matches) != 1:
            raise ValidationError(f"unknown or ambiguous signal candidate: {signal_ref}")
        return matches[0]

    def latest_spec(self, signal_id: str) -> SignalSpec:
        spec = self._latest_spec_or_none(signal_id)
        if spec is None:
            raise ValidationError(f"unknown signal: {signal_id}")
        return spec

    def _latest_spec_or_none(self, signal_id: str) -> SignalSpec | None:
        try:
            manifest_path = self._manifest_for(signal_id)
        except ValidationError:
            return None
        manifest = _read_json(manifest_path)
        return self.load_spec(
            f"{signal_id}:v{int(manifest['stable_version'])}"
        )

    def _manifest_for(self, signal_id: str) -> Path:
        _validate_id(signal_id, "signal_id")
        matches = list(self.root.glob(f"*/{signal_id}/manifest.json"))
        if len(matches) != 1:
            raise ValidationError(f"unknown or ambiguous signal id: {signal_id}")
        return matches[0]

    def _learning_dir(self, signal_ref: str) -> Path:
        signal_id, version = _parse_ref(signal_ref)
        return (
            self._manifest_for(signal_id).parent
            / "versions"
            / f"v{version}"
            / "learning"
        )

    def _save_stats(self, signal_id: str, stats: SignalStats) -> None:
        manifest_path = self._manifest_for(signal_id)
        _atomic_write_json(manifest_path.parent / "stats.json", stats.to_dict())


DeterministicSignalFunction = Callable[
    [SignalSpec, tuple[RawInfoDocument, ...], datetime], SignalResult
]


@dataclass(frozen=True)
class LLMSignalBatchInput:
    """One independently versioned Signal inside a shared model call."""

    spec: SignalSpec
    documents: tuple[RawInfoDocument, ...]
    skill: str
    eligible_documents: tuple[RawInfoDocument, ...] | None = None


@dataclass(frozen=True)
class LLMSignalReadingOutcome:
    """Runtime reading dependencies, separate from the unchanged SignalResult."""

    results: Mapping[str, SignalResult]
    usage: AgentUsage
    documents: Mapping[str, tuple[RawInfoDocument, ...]]
    visible_documents: Mapping[str, tuple[RawInfoDocument, ...]]
    traces: Mapping[str, Mapping[str, Any]]


class LLMSignalRunner(Protocol):
    """No-label adapter for one versioned extraction skill."""

    def execute(
        self,
        spec: SignalSpec,
        documents: tuple[RawInfoDocument, ...],
        skill: str,
        as_of: datetime,
    ) -> tuple[SignalResult, AgentUsage]:
        """Return a structured evidence-backed result and usage."""

    def execute_many(
        self,
        inputs: tuple[LLMSignalBatchInput, ...],
        as_of: datetime,
    ) -> tuple[Mapping[str, SignalResult], AgentUsage]:
        """Return independently keyed results from one shared bounded call."""


class SignalExecutor:
    """Execute a selected Signal batch against one frozen Registry snapshot."""

    def __init__(
        self,
        snapshot: FrozenSignalRegistry,
        raw_info_store: RawInfoStore,
        *,
        resolver: EvidenceResolver | None = None,
        deterministic_functions: Mapping[str, DeterministicSignalFunction] | None = None,
        llm_runner: LLMSignalRunner | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.raw_info_store = raw_info_store
        self.resolver = resolver or EvidenceResolver(raw_info_store)
        self.deterministic_functions = {
            **default_deterministic_signal_functions(),
            **dict(deterministic_functions or {}),
        }
        self.llm_runner = llm_runner
        self._classification_products: dict[str, tuple[SignalResult, dict[str, Any]]] = {}

    def classification_contracts_for(self, results: Iterable[SignalResult]) -> dict[str, dict[str, Any]]:
        """Return declarations only for result objects actually produced here."""

        return {
            result.ref: _thaw_json(record[1])
            for result in results
            if (record := self._classification_products.get(result.ref)) is not None
            and record[0] is result
        }

    def can_execute(self, spec: SignalSpec, *, skill: str | None = None) -> bool:
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            return bool(spec.function in self.deterministic_functions)
        return self.llm_runner is not None and bool((skill or "").strip())

    def prepare_inputs(
        self,
        signal_refs: Iterable[str],
        *,
        company_id: str,
        as_of: datetime,
        identity: Mapping[str, Any] | None = None,
    ) -> tuple[RawInfoResolution, ...]:
        """Materialize exact Raw Info inputs for stable Signal refs."""

        refs = tuple(signal_refs)
        if len(set(refs)) != len(refs):
            raise ValidationError("signal input preparation cannot contain duplicate refs")
        return tuple(
            self._resolve_input(
                self.snapshot.load_spec(signal_ref),
                company_id=company_id,
                as_of=as_of,
                identity=identity,
            )
            for signal_ref in refs
        )

    def execute_batch(
        self,
        signal_refs: Iterable[str],
        *,
        company_id: str,
        as_of: datetime,
        identity: Mapping[str, Any] | None = None,
        prior_fingerprints: Mapping[str, tuple[str, ...]] | None = None,
    ) -> SignalBatchResult:
        """Execute every selected Signal and validate literal evidence."""

        results_by_ref: dict[str, SignalResult] = {}
        declarations: dict[str, dict[str, Any]] = {}
        resolutions: list[RawInfoResolution] = []
        fingerprints: dict[str, tuple[str, ...]] = {}
        skipped: list[str] = []
        usage = AgentUsage()
        llm_inputs: list[LLMSignalBatchInput] = []
        source_reader = getattr(self.llm_runner, "execute_with_source_reading", None)
        reading_inputs: dict[str, LLMSignalBatchInput] = {}
        refs = tuple(signal_refs)
        if len(set(refs)) != len(refs):
            raise ValidationError("signal batch cannot contain duplicate refs")
        for signal_ref in refs:
            self._classification_products.pop(signal_ref, None)
            spec = self.snapshot.load_spec(signal_ref)
            resolution = self._resolve_input(
                spec,
                company_id=company_id,
                as_of=as_of,
                identity=identity,
            )
            resolutions.append(resolution)
            documents = self.resolver.load_documents(resolution, as_of=as_of)
            fingerprint = tuple(
                sorted(
                    f"{document.document_id}:{document.content_hash}"
                    for document in documents
                )
            )
            fingerprints[spec.ref] = fingerprint
            uses_reading = spec.execution_type is SignalExecutionType.LLM and callable(source_reader)
            if uses_reading:
                from stock_opportunity_agent.research.signal_source_reading import catalog_signature

                pool = self.resolver.eligible_documents(resolution.request,
                    company_id=company_id, identity=dict(identity or {}), as_of=as_of)
                reading = LLMSignalBatchInput(spec, documents, self.snapshot.skills.get(spec.ref, ""), pool)
                reading_inputs[spec.ref] = reading
                signature = catalog_signature(reading, as_of)
                previous = (prior_fingerprints or {}).get(spec.ref, ())
                available = {f"{d.document_id}:{d.content_hash}": d for d in pool}
                # Legacy fingerprints cannot establish that the full catalog
                # and actual read dependencies were unchanged.
                prior_documents = tuple(available[p] for p in previous[1:] if p in available)
                unchanged = (bool(previous) and previous[0] == signature
                             and len(prior_documents) == len(previous) - 1
                             and bool(prior_documents))
                fingerprints[spec.ref] = (signature,)
                if unchanged:
                    resolutions[-1] = _signal_read_resolution(resolution, prior_documents,
                        (), {"mode": "unchanged_read_dependencies", "catalog_signature": signature,
                             "coverage_not_recomputed_from_unread_text": True})
                    fingerprints[spec.ref] = tuple(previous)
                    skipped.append(spec.ref)
                    continue
            if not uses_reading and (prior_fingerprints or {}).get(spec.ref) == fingerprint:
                skipped.append(spec.ref)
                continue
            if resolution.status != "resolved":
                result = _unresolved_signal_result(spec, resolution)
            elif spec.execution_type is SignalExecutionType.DETERMINISTIC:
                try:
                    function = self.deterministic_functions[str(spec.function)]
                except KeyError:
                    result = signal_execution_failure_result(
                        spec,
                        status=SignalExecutionStatus.PERMANENT_FAILED,
                        error_code="deterministic_function_unregistered",
                        error_message=(
                            "unregistered deterministic signal function: "
                            f"{spec.function}"
                        ),
                    )
                else:
                    try:
                        declarations[spec.ref] = signal_classification_contract(
                            spec, deterministic_functions={str(spec.function): function})
                        result = function(spec, documents, as_of)
                        validate_signal_result(
                            spec, result, documents, as_of=as_of
                        )
                    except (ValidationError, KeyError, TypeError, ValueError) as exc:
                        result = signal_execution_failure_result(
                            spec,
                            status=SignalExecutionStatus.VALIDATION_FAILED,
                            error_code="deterministic_result_validation_failed",
                            error_message=f"{type(exc).__name__}: {exc}",
                        )
            else:
                if self.llm_runner is None:
                    results_by_ref[spec.ref] = signal_execution_failure_result(
                        spec,
                        status=SignalExecutionStatus.PERMANENT_FAILED,
                        error_code="llm_signal_runner_missing",
                        error_message="LLM signal runner is not configured",
                    )
                    continue
                skill = self.snapshot.skills.get(spec.ref, "")
                if not skill.strip():
                    results_by_ref[spec.ref] = signal_execution_failure_result(
                        spec,
                        status=SignalExecutionStatus.PERMANENT_FAILED,
                        error_code="llm_signal_skill_missing",
                        error_message=f"frozen LLM skill is missing: {spec.ref}",
                    )
                    continue
                declarations[spec.ref] = signal_classification_contract(spec, skill=skill)
                llm_inputs.append(reading_inputs.get(spec.ref) or LLMSignalBatchInput(spec, documents, skill))
                continue
            if result.execution_status in {
                SignalExecutionStatus.SUCCESS,
                SignalExecutionStatus.DOMAIN_UNAVAILABLE,
            }:
                validate_signal_result(spec, result, documents, as_of=as_of)
            results_by_ref[spec.ref] = result
        if llm_inputs:
            execute_many = getattr(self.llm_runner, "execute_many", None)
            if callable(source_reader) or callable(execute_many):
                outcome = source_reader(tuple(llm_inputs), as_of) if callable(source_reader) else None
                if outcome is not None:
                    llm_results, signal_usage = outcome.results, outcome.usage
                else:
                    llm_results, signal_usage = execute_many(tuple(llm_inputs), as_of)
                usage = usage + signal_usage
                for item in llm_inputs:
                    validation_documents = item.documents
                    if outcome is not None:
                        pool = item.eligible_documents or ()
                        validation_documents = outcome.documents.get(item.spec.ref, ())
                        pool_records = {_canonical_hash(d.to_dict()) for d in pool}
                        if len({d.document_id for d in validation_documents}) != len(validation_documents) or any(
                            _canonical_hash(d.to_dict()) not in pool_records for d in validation_documents
                        ):
                            raise ValidationError("Signal reader returned changed or ineligible source versions")
                        index = next(i for i, r in enumerate(resolutions) if r.request.request_id == f"signal:{item.spec.ref}")
                        resolution = _signal_read_resolution(resolutions[index], validation_documents,
                            outcome.visible_documents.get(item.spec.ref, ()), outcome.traces.get(item.spec.ref, {}))
                        resolutions[index] = resolution
                        from stock_opportunity_agent.research.signal_source_reading import catalog_signature

                        fingerprints[item.spec.ref] = (catalog_signature(item, as_of), *sorted(
                            f"{d.document_id}:{d.content_hash}" for d in validation_documents))
                    result = llm_results.get(item.spec.ref)
                    if result is None:
                        result = signal_execution_failure_result(
                            item.spec,
                            status=SignalExecutionStatus.VALIDATION_FAILED,
                            error_code="signal_batch_result_missing",
                            error_message="LLM Signal batch omitted this result.",
                        )
                    try:
                        validate_signal_result(
                            item.spec, result, validation_documents, as_of=as_of
                        )
                    except (ValidationError, KeyError, TypeError, ValueError) as exc:
                        result = signal_execution_failure_result(
                            item.spec,
                            status=SignalExecutionStatus.VALIDATION_FAILED,
                            error_code="llm_result_validation_failed",
                            error_message=f"{type(exc).__name__}: {exc}",
                        )
                    if outcome is not None and not resolution.coverage.contract_satisfied and result.execution_status is SignalExecutionStatus.SUCCESS:
                        result = _unresolved_signal_result(item.spec, resolution)
                    results_by_ref[item.spec.ref] = result
            else:
                for item in llm_inputs:
                    result, signal_usage = self.llm_runner.execute(
                        item.spec, item.documents, item.skill, as_of
                    )
                    usage = usage + signal_usage
                    try:
                        validate_signal_result(
                            item.spec, result, item.documents, as_of=as_of
                        )
                    except (ValidationError, KeyError, TypeError, ValueError) as exc:
                        result = signal_execution_failure_result(
                            item.spec,
                            status=SignalExecutionStatus.VALIDATION_FAILED,
                            error_code="llm_result_validation_failed",
                            error_message=f"{type(exc).__name__}: {exc}",
                        )
                    results_by_ref[item.spec.ref] = result
        results = tuple(results_by_ref[ref] for ref in refs if ref in results_by_ref)
        for result in results:
            if result.execution_status is SignalExecutionStatus.SUCCESS and result.ref in declarations:
                declaration = dict(declarations[result.ref])
                declaration.pop("contract_hash")
                declaration["result_hash"] = _canonical_hash(result.to_dict())
                self._classification_products[result.ref] = (result,
                    {**declaration, "contract_hash": _canonical_hash(declaration)})
        return SignalBatchResult(
            results=results,
            signal_calls=len(results),
            usage=usage,
            resolutions=tuple(resolutions),
            document_fingerprints=fingerprints,
            skipped_unchanged_refs=tuple(skipped),
        )

    def _resolve_input(
        self,
        spec: SignalSpec,
        *,
        company_id: str,
        as_of: datetime,
        identity: Mapping[str, Any] | None,
    ) -> RawInfoResolution:
        selection = {}
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            function = self.deterministic_functions.get(str(spec.function))
            selector = _measurement_input_selector(spec, function, as_of)
            if selector is not None:
                selection["select_documents"] = selector
        return self.resolver.resolve(
            RawInfoRequest(
                request_id=f"signal:{spec.ref}",
                description=spec.description,
                source_types=spec.source_types,
                lookback_days=spec.retrieval_policy.lookback_days,
                max_documents=10,
                query=spec.retrieval_policy.query,
                required_source_groups=spec.retrieval_policy.required_source_groups,
                minimum_distinct_periods=(
                    spec.retrieval_policy.minimum_distinct_periods
                ),
                minimum_period_span_days=(
                    spec.retrieval_policy.minimum_period_span_days
                ),
                minimum_observations=spec.retrieval_policy.minimum_observations,
            ),
            company_id=company_id,
            identity=dict(identity or {}),
            as_of=as_of,
            **selection,
        )


def _signal_read_resolution(
    original: RawInfoResolution, documents: tuple[RawInfoDocument, ...],
    visible_documents: tuple[RawInfoDocument, ...], trace: Mapping[str, Any],
) -> RawInfoResolution:
    """Replace selected-source claims with actual reading and visible coverage."""

    from stock_opportunity_agent.data.resolution import DataGap

    coverage = replace(original.coverage,
        selected_document_count=len(documents),
        context_truncated=trace.get("mode") != "complete_small_input",
        visible_span_count=sum(len(h.get("result", {}).get("source_projection", ())) for h in trace.get("history", ())),
        selection_truncated=len(documents) < original.coverage.eligible_document_count,
        **_retrieval_contract_coverage(visible_documents, original.request))
    gap = None if coverage.contract_satisfied else DataGap(original.request.request_id,
        DataGapReason.REQUIRED_COVERAGE_INCOMPLETE, "Actual source reading did not satisfy retrieval coverage",
        original.request.source_types)
    return replace(original, documents=tuple(RawInfoDocumentRef.from_document(d) for d in documents),
        status="resolved" if coverage.contract_satisfied else "unresolved",
        gap=gap, coverage=coverage, context_spans=(), omitted_context_markers=(),
        events=(*original.events, ResolutionEvent("llm_signal_source_reading", dict(trace))))


def _unresolved_signal_result(
    spec: SignalSpec, resolution: RawInfoResolution
) -> SignalResult:
    """Map data-boundary control failures without inventing a domain observation."""

    reason = resolution.gap.reason if resolution.gap is not None else None
    status_by_reason = {
        DataGapReason.ADAPTER_MISSING: SignalExecutionStatus.PERMANENT_FAILED,
        DataGapReason.MISSING_IDENTIFIER: SignalExecutionStatus.PERMANENT_FAILED,
        DataGapReason.EXTERNAL_NOT_AUTHORIZED: (
            SignalExecutionStatus.AUTHORIZATION_BLOCKED
        ),
        DataGapReason.QUOTA_DEFERRED: SignalExecutionStatus.BUDGET_BLOCKED,
        DataGapReason.PROVIDER_ERROR: SignalExecutionStatus.TRANSPORT_FAILED,
        DataGapReason.MATERIALIZATION_FAILED: SignalExecutionStatus.PERMANENT_FAILED,
    }
    status = status_by_reason.get(reason)
    if status is not None:
        code = reason.value if reason is not None else "raw_info_resolution_failed"
        message = (
            resolution.gap.message
            if resolution.gap is not None
            else "Raw Info resolution failed without a structured gap."
        )
        return signal_execution_failure_result(
            spec,
            status=status,
            error_code=code,
            error_message=message,
        )
    return SignalResult(
        signal_id=spec.signal_id,
        version=spec.version,
        value=SignalValue.UNAVAILABLE,
        confidence=0.0,
        interpretation=(
            "Point-in-time inputs did not satisfy the Signal retrieval contract."
        ),
        coverage=SignalCoverage.UNAVAILABLE,
    )


def validate_signal_result(
    spec: SignalSpec,
    result: SignalResult,
    documents: Iterable[RawInfoDocument],
    *,
    as_of: datetime,
) -> None:
    """Fail closed on identity, future time, source, or exact-span mismatch."""

    if result.signal_id != spec.signal_id or result.version != spec.version:
        raise ValidationError("signal result identity does not match SignalSpec")
    if result.value is SignalValue.UNAVAILABLE:
        return
    evidence_groups = (
        ("supporting", result.supporting_evidence),
        ("counter", result.counter_evidence),
    )
    evidence = result.supporting_evidence + result.counter_evidence
    if spec.evidence_policy.require_source and not evidence:
        raise ValidationError(
            f"available signal result ({result.value.value}) requires source evidence; "
            "cite the examined non-qualifying spans as counter evidence for "
            "neutral or negative conclusions only when all mandatory measured-object "
            "requirements hold, or return unavailable with empty "
            "evidence when the visible text cannot support applying the skill"
        )
    if result.measurement is not None:
        if spec.execution_type is not SignalExecutionType.DETERMINISTIC:
            raise ValidationError("numeric measurement is deterministic runtime-owned metadata")
        measurement = result.measurement
        if measurement.period_end is not None and not any(
            row.get("end") == measurement.period_end
            and row.get("start") == measurement.period_start
            for row in _numeric_source_observations(result.to_dict())
        ):
            raise ValidationError("numeric measurement period is not in its cited source facts")
    documents_by_id = {document.document_id: document for document in documents}
    for group, group_evidence in evidence_groups:
        for index, item in enumerate(group_evidence):
            location = f"signal {group} evidence[{index}]"
            try:
                document = documents_by_id[item.document_id]
            except KeyError as exc:
                raise ValidationError(
                    f"{location} cites a document outside its inputs: {item.document_id}"
                ) from exc
            if document.available_at > as_of or item.timestamp > as_of:
                raise ValidationError(
                    f"{location} timestamp exceeds prediction time: {item.document_id}"
                )
            if (
                spec.evidence_policy.require_exact_span
                and item.exact_span not in document.content
            ):
                raise ValidationError(
                    f"{location} exact span is not in cited document: {item.document_id}"
                )
    required_phrases = spec.parameters.get("result_required_evidence_phrases")
    if required_phrases:
        cited_texts = tuple(
            " "
            + re.sub(
                r"[^a-z0-9]+",
                " ",
                item.exact_span.casefold(),
            ).strip()
            + " "
            for item in evidence
        )
        normalized_phrases = tuple(
            " "
            + re.sub(r"[^a-z0-9]+", " ", str(phrase).casefold()).strip()
            + " "
            for phrase in required_phrases
        )
        if not any(
            phrase in cited_text
            for cited_text in cited_texts
            for phrase in normalized_phrases
        ):
            raise ValidationError(
                f"signal {spec.ref} available result requires cited evidence "
                "containing at least one version-owned "
                "result_required_evidence_phrases value: "
                f"{list(required_phrases)} within one exact supporting or counter "
                "span; do not assemble a phrase across separate citations. "
                "Return unavailable with empty evidence "
                "when visible evidence does not name the measured object"
            )


def default_deterministic_signal_functions() -> dict[str, DeterministicSignalFunction]:
    """Return executable functions used by the manually seeded v1 Signals."""

    return {
        "financial.revenue_growth_yoy": _revenue_growth_signal,
        "financial.revenue_acceleration": _revenue_acceleration_signal,
        "financial.gross_margin_change": _gross_margin_change_signal,
        "financial.revenue_acceleration_adjacent": _revenue_acceleration_adjacent_signal,
        "financial.gross_margin_change_yoy": _gross_margin_change_yoy_signal,
        "financial.operating_cash_flow_margin": _operating_cash_flow_margin_signal,
        "financial.net_share_retirement_yoy": _net_share_retirement_yoy_signal,
        "financial.cash_to_current_liabilities_ratio": (
            _cash_to_current_liabilities_ratio_signal
        ),
        "financial.cash_burn_rate_elevated": _cash_burn_rate_elevated_signal,
        "financial.liquidity_runway_months": _liquidity_runway_months_signal,
        "market.max_drawdown_1y": _max_drawdown_signal,
        "market.price_momentum_126d": _price_momentum_signal,
        "financial.cash_reserves": _cash_reserves_signal,
        "news.negative_word_count": _negative_word_count_signal,
    }


def signal_parameter_names(*names: str) -> Callable[[DeterministicSignalFunction], DeterministicSignalFunction]:
    """Declare consumed parameter keys for disclosure without wrapping execution."""

    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise ValidationError("Signal parameter names must be unique nonempty strings")

    def declare(function: DeterministicSignalFunction) -> DeterministicSignalFunction:
        function.__signal_parameter_names__ = tuple(names)
        return function

    return declare


def signal_input_facts(helper: Callable[..., Any]) -> Callable[[DeterministicSignalFunction], DeterministicSignalFunction]:
    """Declare the pure operand helper also used by this actual numeric callable."""
    if not callable(helper):
        raise ValidationError("Signal input facts helper must be callable")

    def declare(function: DeterministicSignalFunction) -> DeterministicSignalFunction:
        function.__signal_input_facts__ = helper
        return function

    return declare


def _measurement_input_selector(spec, function, as_of):
    helper = getattr(function, "__signal_input_facts__", None)
    if helper is None:
        return None
    def select(ranked, request):
        if not callable(helper):
            raise ValidationError("Signal input facts helper must be callable")
        # No information is discarded below the limit. Keep the original consumer
        # validation/technical failure path instead of parsing facts prematurely.
        if len(ranked) <= request.max_documents:
            return _select_required_source_documents(list(ranked), request)
        basis = helper(spec, ranked, as_of)
        if not isinstance(basis, _SecInputBasis):
            raise ValidationError("Signal input facts helper returned an invalid basis")
        needed = {fact.document.document_id for fact in basis.facts}
        eligible = {document.document_id for document in ranked}
        if not needed <= eligible:
            raise ValidationError("Signal input facts helper referenced an ineligible source")
        if len(needed) > request.max_documents:
            return ()
        prioritized = [d for d in ranked if d.document_id in needed]
        prioritized.extend(d for d in ranked if d.document_id not in needed)
        selected = _select_required_source_documents(prioritized, request)
        selected_ids = {d.document_id for d in selected}
        # Return/reparse in original ranked order, preserving tie/context order.
        selected = [d for d in ranked if d.document_id in selected_ids]
        def preserves(values):
            subset = helper(spec, tuple(values), as_of)
            if not isinstance(subset, _SecInputBasis):
                raise ValidationError("Signal input facts helper returned an invalid basis")
            return _input_basis_identity(basis) == _input_basis_identity(subset)

        if needed <= selected_ids and preserves(selected):
            return selected
        minimal = [d for d in ranked if d.document_id in needed]
        if preserves(minimal) and _retrieval_contract_coverage(minimal, request)["contract_satisfied"]:
            # A harmful filler is optional; never throw away a feasible basis
            # merely because ordinary relevance filling would alter it.
            safe = list(minimal)
            for document in ranked:
                if len(safe) >= request.max_documents:
                    break
                if document.document_id not in needed:
                    ids = {d.document_id for d in safe} | {document.document_id}
                    candidate = [d for d in ranked if d.document_id in ids]
                    if preserves(candidate):
                        safe = candidate
            return safe
        # Context outside the operands can establish dominance/currency/basis.
        # One deterministic deletion pass retains such witnesses; no search tree.
        reduced = list(ranked)
        for document in reversed(ranked):
            if len(reduced) <= request.max_documents:
                break
            if document.document_id in needed:
                continue
            candidate = [d for d in reduced if d.document_id != document.document_id]
            if _retrieval_contract_coverage(candidate, request)["contract_satisfied"] and preserves(candidate):
                reduced = candidate
        if len(reduced) <= request.max_documents:
            return reduced
        # Reuse the resolver's existing empty-selection acquisition/gap path.
        return ()

    return select


def signal_measurement_scope(
    spec: SignalSpec, *,
    deterministic_functions: Mapping[str, DeterministicSignalFunction] | None = None,
) -> dict[str, Any]:
    """Copy version-owned scope and the actual callable's declared measurement contract."""

    execution: dict[str, Any] = {"type": spec.execution_type.value}
    if spec.execution_type is SignalExecutionType.DETERMINISTIC:
        function = (deterministic_functions.get(spec.function)
                    if deterministic_functions is not None else None)
        names = getattr(function, "__signal_parameter_names__", None)
        if (not isinstance(names, (tuple, list))
                or any(not isinstance(name, str) or not name for name in names)
                or len(set(names)) != len(names)):
            names = None
        execution.update(
            function=spec.function,
            callable_status=("unknown" if deterministic_functions is None
                             else "registered" if function is not None else "missing"),
            contract=(function.__doc__ or None) if function is not None else None,
            parameter_names=list(names) if names is not None else None,
            configured_parameters=({name: _thaw_json(spec.parameters[name])
                                    for name in names if name in spec.parameters}
                                   if names is not None else None),
        )
    return {"signal_ref": spec.ref, "source_types": list(spec.source_types),
            "raw_retrieval": spec.retrieval_policy.to_dict(), "execution": execution}


def signal_classification_contract(
    spec: SignalSpec, *,
    deterministic_functions: Mapping[str, DeterministicSignalFunction] | None = None,
    skill: str | None = None,
    result: SignalResult | None = None,
) -> dict[str, Any]:
    """Copy the actual version declaration without inferring its category meaning."""

    execution = signal_measurement_scope(
        spec, deterministic_functions=deterministic_functions,
    )["execution"]
    if spec.execution_type is SignalExecutionType.LLM:
        if skill is not None and not isinstance(skill, str):
            raise ValidationError("classification skill must be text")
        execution.update(contract=skill, configured_parameters=_thaw_json(spec.parameters))
    contract = {
        "signal_ref": spec.ref,
        "spec_hash": _canonical_hash(spec.to_dict()),
        "definition": spec.description,
        "execution": execution,
        "declaration_available": bool((execution.get("contract") or "").strip()),
    }
    if result is not None:
        if result.ref != spec.ref:
            raise ValidationError("classification result differs from spec")
        contract["result_hash"] = _canonical_hash(result.to_dict())
    return {**contract, "contract_hash": _canonical_hash(contract)}


def validate_signal_classification_contract(
    value: Mapping[str, Any], *, signal_ref: str,
    result: SignalResult | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Check identity/integrity of runtime control data, never semantic truth."""

    fields = {
        "signal_ref", "spec_hash", "definition", "execution",
        "declaration_available", "contract_hash", "result_hash",
    }
    if not isinstance(value, Mapping) or set(value) not in (fields, fields | {"source_contract_hash"}):
        raise ValidationError("classification contract has invalid fields")
    envelope = _thaw_json(value)
    digest = envelope.pop("contract_hash")
    if (envelope["signal_ref"] != signal_ref
            or not isinstance(envelope["spec_hash"], str)
            or _SHA256.fullmatch(envelope["spec_hash"]) is None
            or not isinstance(envelope["definition"], str)
            or not isinstance(envelope["execution"], Mapping)
            or type(envelope["declaration_available"]) is not bool
            or digest != _canonical_hash(envelope)):
        raise ValidationError("classification contract identity/integrity mismatch")
    result_hash = value.get("result_hash")
    if not isinstance(result_hash, str) or _SHA256.fullmatch(result_hash) is None:
        raise ValidationError("classification contract result hash is invalid")
    source_hash = value.get("source_contract_hash")
    if source_hash is not None and (not isinstance(source_hash, str) or _SHA256.fullmatch(source_hash) is None):
        raise ValidationError("classification source binding is invalid")
    if result is not None:
        canonical = result if isinstance(result, SignalResult) else SignalResult.from_dict(result)
        if value.get("result_hash") != _canonical_hash(canonical.to_dict()):
            raise ValidationError("classification contract result binding mismatch")
    return {**envelope, "contract_hash": digest}


def project_signal_classification_contract(
    original: Mapping[str, Any], projected: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a deterministic anonymous view while retaining the original source hash."""

    source = validate_signal_classification_contract(original, signal_ref=original.get("signal_ref", ""))
    if source == projected:
        return _thaw_json(projected)
    result = _thaw_json(projected)
    result.pop("contract_hash")
    result["source_contract_hash"] = source.get("source_contract_hash", source["contract_hash"])
    return {**result, "contract_hash": _canonical_hash(result)}


def saved_signal_classification_contracts(
    context: Mapping[str, Any], *, round_index: int,
) -> dict[str, dict[str, Any]]:
    """Reuse only declarations in an accepted saved context; never query a Registry."""

    contracts: dict[str, dict[str, Any]] = {}
    rounds = context.get("signal_rounds", ())
    if type(round_index) is not int or not 0 <= round_index < len(rounds):
        return {}
    round_row = rounds[round_index]
    cards = round_row.get("batch", {}).get("results", ()) if isinstance(round_row, Mapping) else ()
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        interpretation = card.get("interpretation", {})
        measurement_context = interpretation.get("measurement_context", {}) if isinstance(interpretation, Mapping) else {}
        contract = measurement_context.get("classification_contract") if isinstance(measurement_context, Mapping) else None
        if contract is None:
            continue
        if not isinstance(contract.get("result_hash"), str):
            raise ValidationError("saved classification requires a produced result binding")
        ref = card.get("signal_ref") or f"{card.get('signal_id')}:v{card.get('version')}"
        _parse_ref(ref)
        checked = validate_signal_classification_contract(contract, signal_ref=ref)
        if ref in contracts and contracts[ref] != checked:
            raise ValidationError("conflicting saved classification contracts")
        contracts[ref] = checked
    return contracts


def deterministic_signal_function_contracts(
    functions: Mapping[str, DeterministicSignalFunction],
) -> dict[str, str]:
    """Describe actual registered callables for candidate authors, including overrides."""

    return {
        name: " ".join((function.__doc__ or "No measurement description supplied.").split())
        for name, function in sorted(functions.items())
    }


def _audit_deterministic_fixture(
    spec: SignalSpec,
    fixture: Mapping[str, Any],
    *,
    index: int,
) -> None:
    """Execute one source-backed fixture without an LLM or external call."""

    expected = SignalValue(str(fixture["expected"]))
    as_of = datetime.fromisoformat(
        str(fixture.get("as_of", "2025-01-01T00:00:00+00:00"))
    )
    documents: list[RawInfoDocument] = []
    for document_index, raw in enumerate(fixture.get("documents", ())):
        if not isinstance(raw, Mapping):
            raise ValidationError("capability fixture document must be an object")
        source_type = str(raw["source_type"])
        if source_type not in spec.source_types:
            raise ValidationError("capability fixture source_type is outside SignalSpec")
        published_at = datetime.fromisoformat(
            str(raw.get("published_at", raw.get("available_at", as_of.isoformat())))
        )
        available_at = datetime.fromisoformat(
            str(raw.get("available_at", published_at.isoformat()))
        )
        documents.append(
            RawInfoDocument.create(
                document_id=str(
                    raw.get(
                        "document_id",
                        f"capability_{spec.signal_id}_{index}_{document_index}",
                    )
                ),
                company_id="capability_fixture",
                source_type=source_type,
                published_at=published_at,
                available_at=available_at,
                content=str(raw["content"]),
                metadata=dict(raw.get("metadata", {})),
            )
        )
    snapshot_hash = hashlib.sha256(
        json.dumps(spec.to_dict(), sort_keys=True).encode("utf-8")
    ).hexdigest()
    result = SignalExecutor(
        FrozenSignalRegistry(1, snapshot_hash, (spec,), {}),
        RawInfoStore(documents=documents),
    ).execute_batch(
        (spec.ref,),
        company_id="capability_fixture",
        as_of=as_of,
    ).results[0]
    if result.value is not expected:
        raise ValidationError(
            f"expected {expected.value}, received {result.value.value}"
        )


@dataclass(frozen=True)
class _SecFact:
    tag: str
    value: float
    unit: str
    start: str | None
    end: str
    filed: str
    form: str
    document: RawInfoDocument
    exact_span: str


_REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "Revenue",
    "RevenueFromContractsWithCustomers",
    "RevenueFromSaleOfGoods",
)
_MAX_SEC_CURRENT_PERIOD_AGE_DAYS = 550
# A same-period value at least this many times smaller than the canonical total
# marks its whole tag as a disaggregation partial (FEIM's $89K/$0 beside a $40M+
# total is 447x; Hertz's $19M beside $3.2B is 168x; AMD's ASC 606 restatement
# crossover stays within 1.11x and must NOT count as partial).
_PARTIAL_VALUE_RATIO = 3.0
_CASH_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashAndCashEquivalents",
)
_CURRENT_LIABILITIES_TAGS = (
    "LiabilitiesCurrent",
    "CurrentLiabilities",
)
_OPERATING_CASH_FLOW_TAGS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    "CashFlowsFromUsedInOperatingActivities",
)
_SHARE_COUNT_TAGS = (
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstanding",
    "WeightedAverageShares",
    "AdjustedWeightedAverageShares",
)


@dataclass(frozen=True)
class _SecInputBasis:
    """Local pure operand/failure context, never a serialized Signal contract."""

    facts: tuple[_SecFact, ...] = ()
    unavailable_reason: str | None = None


def _input_basis_identity(basis):
    return (basis.unavailable_reason, tuple((fact.document.document_id,
        fact.document.content_hash, fact.exact_span, fact.tag, fact.unit,
        fact.start, fact.end, fact.filed, fact.form, fact.value) for fact in basis.facts))


def _revenue_growth_input_facts(spec, documents, as_of):
    series = _canonical_series(_sec_facts(documents, as_of), _REVENUE_TAGS)
    pair = _latest_yoy_pair(series)
    if pair is None or pair[1].value == 0:
        return _SecInputBasis(tuple(pair or ()), "Comparable SEC revenue periods were unavailable.")
    if not _current_sec_fact_is_fresh(spec, pair[0], as_of):
        return _SecInputBasis(tuple(pair), f"Latest supported SEC revenue period ended {pair[0].end} and is stale.")
    return _SecInputBasis(tuple(pair))


def _revenue_acceleration_input_facts(spec, documents, as_of):
    if "period_policy" in spec.parameters:
        if spec.parameters["period_policy"] == "adjacent_yoy":
            return _revenue_acceleration_adjacent_input_facts(spec, documents, as_of)
        return _SecInputBasis((), "Unsupported revenue acceleration period_policy.")
    series = _canonical_series(_sec_facts(documents, as_of), _REVENUE_TAGS)
    pairs = _yoy_pairs(series)
    if len(pairs) < 2:
        return _SecInputBasis(tuple(f for pair in pairs for f in pair), "Two comparable SEC revenue growth periods were unavailable.")
    current = pairs[0]
    if not _current_sec_fact_is_fresh(spec, current[0], as_of):
        return _SecInputBasis(tuple(current), f"Latest supported SEC revenue period ended {current[0].end} and is stale.")
    prior = next((pair for pair in pairs[1:] if pair[0].end < current[0].end
                  and pair[0].unit.casefold() == current[0].unit.casefold()), None)
    facts = (*current, *(prior or ()))
    if prior is None or current[1].value == 0 or prior[1].value == 0:
        return _SecInputBasis(facts, "Revenue acceleration history was incomplete.")
    return _SecInputBasis(facts)


def _gross_margin_input_facts(spec, documents, as_of):
    if "period_policy" in spec.parameters:
        if spec.parameters["period_policy"] == "same_window_yoy":
            return _gross_margin_yoy_input_facts(spec, documents, as_of)
        return _SecInputBasis((), "Unsupported gross-margin period_policy.")
    facts = _sec_facts(documents, as_of)
    revenues = _canonical_series(facts, _REVENUE_TAGS)
    gross = _canonical_series(facts, ("GrossProfit",))
    by_period = {(f.start, f.end, f.unit.casefold()): f for f in gross}
    margins = [(r, by_period[(r.start, r.end, r.unit.casefold())]) for r in revenues
               if (r.start, r.end, r.unit.casefold()) in by_period and r.value != 0]
    margins.sort(key=lambda pair: pair[0].end, reverse=True)
    if len(margins) < 2:
        return _SecInputBasis(tuple(f for pair in margins for f in pair), "Comparable SEC gross-margin periods were unavailable.")
    current = margins[0]
    if not _current_sec_fact_is_fresh(spec, current[0], as_of):
        return _SecInputBasis(current, f"Latest matched SEC gross-margin period ended {current[0].end} and is stale.")
    prior = next((pair for pair in margins[1:] if _comparable_duration(current[0], pair[0])), None)
    if prior is None:
        return _SecInputBasis(current, "Comparable SEC gross-margin periods were unavailable.")
    return _SecInputBasis((*current, *prior))


def _shift_month_start(value: date, months: int) -> date:
    ordinal = value.year * 12 + value.month - 1 + months
    return value.replace(year=ordinal // 12, month=ordinal % 12 + 1)


def _reported_window_months(fact: _SecFact) -> int | None:
    try:
        start, end = date.fromisoformat(fact.start or ""), date.fromisoformat(fact.end)
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        if start.day == 1 and months in (3, 6, 9, 12) and _shift_month_start(start, months) - timedelta(days=1) == end:
            return months
    except ValueError:
        pass
    return None


def _reported_fraction(fact: _SecFact) -> Fraction:
    raw = json.loads(fact.exact_span, parse_float=str)
    return Fraction(raw["value"] if "value" in raw else raw["val"])


def _checked_window_basis(all_facts, selected, reason=None):
    selected = tuple(fact for fact in selected if fact is not None)
    witnesses = []
    for fact in selected:
        same = [other for other in all_facts if (other.tag, other.start, other.end, other.unit.casefold())
                == (fact.tag, fact.start, fact.end, fact.unit.casefold())]
        if len({_reported_fraction(other) for other in same}) > 1:
            witnesses.extend(same)
    if witnesses:
        unique = {(fact.document.document_id, fact.exact_span): fact for fact in (*selected, *witnesses)}
        return _SecInputBasis(tuple(unique.values()), "Conflicting SEC values for a required reported window; revision authority is unresolved.")
    return _SecInputBasis(selected, reason)


def _strict_revenue_windows(spec, facts, as_of, *, adjacent):
    series = _canonical_series(facts, _REVENUE_TAGS)
    if not series:
        return _SecInputBasis((), "SEC revenue duration windows were unavailable.")
    current = max(series, key=lambda fact: (fact.end, fact.start or ""))
    if not _current_sec_fact_is_fresh(spec, current, as_of):
        return _SecInputBasis((current,), f"Latest SEC revenue window ended {current.end} and is stale.")
    months = _reported_window_months(current)
    if months is None or (adjacent and months not in (3, 12)):
        return _checked_window_basis(facts, (current,), "Latest reported window lacks a supported calendar proof; acceleration requires a standalone quarter or annual window, never cumulative YTD.")
    try:
        start = date.fromisoformat(current.start)
        stop = date.fromisoformat(current.end) + timedelta(days=1)
        keys = [(_shift_month_start(start, -12), _shift_month_start(stop, -12) - timedelta(days=1))]
        if adjacent:
            keys.extend(((_shift_month_start(start, -months), start - timedelta(days=1)),
                         (_shift_month_start(start, -months-12), _shift_month_start(start, -12) - timedelta(days=1))))
    except ValueError:
        return _SecInputBasis((current,), "Required fiscal comparison boundaries are unsupported.")
    selected = [current]
    for left, right in keys:
        selected.append(next((fact for fact in series if fact.start == left.isoformat()
                              and fact.end == right.isoformat() and fact.unit.casefold() == current.unit.casefold()), None))
    reason = "Required same-window YoY or immediately adjacent comparison was unavailable; no older-pair fallback." if None in selected else None
    if reason is None and (selected[1].value == 0 or (adjacent and selected[3].value == 0)):
        reason = "Required prior-year revenue denominator is zero."
    return _checked_window_basis(facts, selected, reason)


def _revenue_acceleration_adjacent_input_facts(spec, documents, as_of):
    facts = _sec_facts(documents, as_of)
    return _strict_revenue_windows(spec, facts, as_of, adjacent=True)


def _gross_margin_yoy_input_facts(spec, documents, as_of):
    facts = _sec_facts(documents, as_of)
    basis = _strict_revenue_windows(spec, facts, as_of, adjacent=False)
    if basis.unavailable_reason is not None:
        return basis
    current, previous = basis.facts
    gross = _canonical_series((fact for fact in facts if fact.unit.casefold() == current.unit.casefold()), ("GrossProfit",))
    selected = []
    for revenue in (current, previous):
        selected.extend((revenue, next((fact for fact in gross if fact.start == revenue.start
            and fact.end == revenue.end and fact.unit.casefold() == revenue.unit.casefold()), None)))
    reason = "GrossProfit for an exact required revenue window was unavailable; no older-pair fallback." if None in selected else None
    if current.value == 0 or previous.value == 0:
        reason = "Required revenue denominator is zero."
    return _checked_window_basis(facts, selected, reason)


def _operating_margin_input_facts(spec, documents, as_of):
    facts = _sec_facts(documents, as_of)
    revenues = _canonical_series(facts, _REVENUE_TAGS)
    cash_flows = _canonical_series(facts, _OPERATING_CASH_FLOW_TAGS, dominance=False)
    by_period = {(f.start, f.end, f.unit.casefold()): f for f in cash_flows}
    pairs = [(r, by_period[(r.start, r.end, r.unit.casefold())]) for r in revenues
             if (r.start, r.end, r.unit.casefold()) in by_period and r.value > 0]
    pairs.sort(key=lambda pair: pair[0].end, reverse=True)
    if not pairs:
        return _SecInputBasis((), "Matching SEC operating-cash-flow and positive-revenue periods were unavailable.")
    latest = pairs[0]
    if not _current_sec_fact_is_fresh(spec, latest[0], as_of):
        return _SecInputBasis(latest, f"Latest matched SEC operating-cash-flow period ended {latest[0].end} and is stale.")
    return _SecInputBasis(latest)


def _share_input_facts(spec, documents, as_of):
    pair = _latest_share_yoy_pair(_share_duration_series(_sec_facts(documents, as_of)))
    if pair is None:
        return _SecInputBasis((), "Comparable point-in-time SEC weighted-average share periods were unavailable.")
    if not _current_sec_fact_is_fresh(spec, pair[0], as_of):
        return _SecInputBasis(pair, f"Latest comparable SEC share period ended {pair[0].end} and is stale.")
    return _SecInputBasis(pair)


def _cash_input_facts(spec, documents, as_of):
    facts = [f for f in _sec_facts(documents, as_of) if f.tag in _CASH_TAGS and f.start is None]
    if not facts:
        return _SecInputBasis((), "Point-in-time SEC cash balance was unavailable.")
    latest = max(facts, key=lambda f: (f.end, f.filed, f.document.document_id))
    if not _current_sec_fact_is_fresh(spec, latest, as_of):
        return _SecInputBasis((latest,), f"Latest SEC cash balance ended {latest.end} and is stale.")
    return _SecInputBasis((latest,))


def _cash_liability_input_facts(spec, documents, as_of):
    facts = _sec_facts(documents, as_of)
    cash = _instant_series(facts, _CASH_TAGS)
    liabilities = _instant_series(facts, _CURRENT_LIABILITIES_TAGS)
    by_period = {(f.end, f.unit.casefold()): f for f in liabilities}
    pairs = [(f, by_period[(f.end, f.unit.casefold())]) for f in cash
             if (f.end, f.unit.casefold()) in by_period and by_period[(f.end, f.unit.casefold())].value > 0]
    if not pairs:
        return _SecInputBasis((), "Matching SEC cash and positive current-liabilities instant facts were unavailable.")
    pair = max(pairs, key=lambda pair: (pair[0].end, pair[0].unit.casefold() == "usd",
                                       pair[0].filed, pair[0].document.document_id))
    if not _current_sec_fact_is_fresh(spec, pair[0], as_of):
        return _SecInputBasis(pair, f"Latest matched SEC liquidity period ended {pair[0].end} and is stale.")
    return _SecInputBasis(pair)


def _cash_flow_cash_input_facts(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> _SecInputBasis:
    """Match latest operating cash flow with the closest prior cash instant."""

    facts = _sec_facts(documents, as_of)
    tag_priority = {
        tag: index for index, tag in enumerate(_OPERATING_CASH_FLOW_TAGS)
    }
    cash_flows = [
        fact
        for fact in facts
        if fact.tag in tag_priority
        and fact.start is not None
        and re.fullmatch(r"[A-Za-z]{3}", fact.unit) is not None
    ]
    if not cash_flows:
        return _SecInputBasis((), "SEC operating-cash-flow duration facts were unavailable.")
    cash_flow = max(
        cash_flows,
        key=lambda fact: (
            fact.end,
            fact.unit.casefold() == "usd",
            -tag_priority[fact.tag],
            fact.filed,
            fact.document.document_id,
        ),
    )
    if not _current_sec_fact_is_fresh(spec, cash_flow, as_of):
        return _SecInputBasis((cash_flow,), f"Latest SEC operating-cash-flow period ended {cash_flow.end} and is stale.")
    cash_candidates = [
        fact
        for fact in _instant_series(facts, _CASH_TAGS)
        if fact.end <= cash_flow.end
        and fact.unit.casefold() == cash_flow.unit.casefold()
        and fact.value > 0
    ]
    if not cash_candidates:
        return _SecInputBasis((cash_flow,), "A positive same-currency SEC cash instant at or before the latest operating-cash-flow period end was unavailable.")
    cash = max(
        cash_candidates,
        key=lambda fact: (fact.end, fact.filed, fact.document.document_id),
    )
    if not _current_sec_fact_is_fresh(spec, cash, as_of):
        return _SecInputBasis((cash_flow, cash), f"Latest matched SEC cash balance ended {cash.end} and is stale.")
    return _SecInputBasis((cash_flow, cash))


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days")
@signal_input_facts(_revenue_growth_input_facts)
def _revenue_growth_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure revenue_growth_yoy as current / comparable prior-year revenue - 1. Requires
    SEC duration facts from the per-issuer canonical total series (dominance-resolved;
    partial or zero same-period tag values never displace the total), matching units
    and comparable year-over-year periods; zero prior revenue or missing/stale
    current facts yields unavailable. Numeric states use
    positive_min (default 0) and negative_max (default positive_min): value >=
    positive_min is positive, otherwise value <= negative_max is negative, otherwise
    neutral. Thresholds do not change the measurement. Values beyond
    plausible_abs_max (default 5) are downgraded to partial coverage at 0.5
    confidence with an implausible_value marker. max_period_age_days (default 550)
    bounds current SEC period age; older comparative periods remain allowed.
    """

    basis = _revenue_growth_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    current, previous = basis.facts
    value = current.value / previous.value - 1.0
    return _numeric_result(
        spec,
        value,
        current.document,
        as_of,
        label="revenue_growth_yoy",
        measurement_unit='fraction',
        measurement_formula='current / comparable prior-year revenue - 1',
        measurement_period=current,
        evidence=_fact_evidence((current, previous), as_of),
        plausible_abs_max=5.0,
    )


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days", "period_policy")
@signal_input_facts(_revenue_acceleration_input_facts)
def _revenue_acceleration_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """With period_policy=adjacent_yoy, measure current standalone quarter YoY growth
    minus immediately previous quarter YoY growth (four reported windows); annual
    uses adjacent annual YoY growth (three windows). Require exact month-aligned
    boundaries, currency and latest anchor; no skipped quarter, YTD derivation,
    mixed cadence, older complete fallback or unresolved conflicts. Missing inputs
    are unavailable. An unknown explicit policy is unavailable. Without period_policy,
    preserve legacy behavior: latest year-over-year revenue growth minus an earlier
    comparable growth rate. Requires two supported revenue year-over-year pairs from the
    per-issuer canonical total series (dominance-resolved; never mixed-basis), with
    matching units and nonzero denominators; incomplete/stale current facts yield
    unavailable. Numeric states use positive_min (default 0) and negative_max (default
    positive_min): value >= positive_min is positive, otherwise value <= negative_max is
    negative, otherwise neutral. Thresholds do not change the measurement. Values beyond
    plausible_abs_max (default 5) are downgraded to partial coverage at 0.5 confidence
    with an implausible_value marker. max_period_age_days (default 550) bounds current
    SEC period age; older comparative periods remain allowed.
    """

    if spec.parameters.get("period_policy") == "adjacent_yoy":
        return _revenue_acceleration_adjacent_signal(spec, documents, as_of)
    basis = _revenue_acceleration_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    current_pair, prior_pair = basis.facts[:2], basis.facts[2:]
    current_growth = current_pair[0].value / current_pair[1].value - 1.0
    prior_growth = prior_pair[0].value / prior_pair[1].value - 1.0
    facts = (*current_pair, *prior_pair)
    return _numeric_result(
        spec,
        current_growth - prior_growth,
        current_pair[0].document,
        as_of,
        label="revenue_acceleration",
        measurement_unit='fraction_difference',
        measurement_formula='latest year-over-year growth - earlier year-over-year growth',
        measurement_period=current_pair[0],
        evidence=_fact_evidence(facts, as_of),
        plausible_abs_max=5.0,
    )


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days", "period_policy")
@signal_input_facts(_gross_margin_input_facts)
def _gross_margin_change_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """With period_policy=same_window_yoy, measure latest GrossProfit/revenue minus
    the same reported fiscal window's margin one year earlier. Require exact
    month-aligned 3/6/9/12-month windows, matching currency and latest revenue anchor;
    no older complete fallback or unresolved conflicts. Missing current profit or
    any comparator is unavailable. Unknown explicit policies are unavailable.
    Without period_policy preserve legacy behavior: latest margin minus the previous
    comparable-duration margin. GrossProfit and revenue must match start, end and units
    within each period, and revenue comes from the per-issuer canonical total series
    (dominance-resolved; partial or zero same-period tag values never displace the
    total). Missing matched periods, zero revenue or stale current facts yield
    unavailable. Numeric states use positive_min (default 0) and negative_max (default
    positive_min): value >= positive_min is positive, otherwise value <= negative_max is
    negative, otherwise neutral. Thresholds do not change the measurement. Values beyond
    plausible_abs_max (default 2) are downgraded to partial coverage at 0.5 confidence
    with an implausible_value marker. max_period_age_days (default 550) bounds current
    SEC period age; older comparative periods remain allowed.
    """

    if spec.parameters.get("period_policy") == "same_window_yoy":
        return _gross_margin_change_yoy_signal(spec, documents, as_of)
    basis = _gross_margin_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    r, g, prior_r, prior_g = basis.facts
    current = (r.end, g.value / r.value, r, g)
    previous = (prior_r.end, prior_g.value / prior_r.value, prior_r, prior_g)
    return _numeric_result(
        spec,
        current[1] - previous[1],
        current[2].document,
        as_of,
        label="gross_margin_change",
        measurement_unit='fraction_difference',
        measurement_formula='current gross profit / revenue - previous gross profit / revenue',
        measurement_period=current[2],
        evidence=_fact_evidence(
            (current[2], current[3], previous[2], previous[3]), as_of
        ),
        plausible_abs_max=2.0,
    )


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days")
@signal_input_facts(_revenue_acceleration_adjacent_input_facts)
def _revenue_acceleration_adjacent_signal(spec, documents, as_of):
    """Measure current standalone quarter YoY revenue growth minus immediately previous
    standalone quarter YoY growth (four reported windows); annual uses adjacent annual
    YoY growth (three windows). Anchor to latest canonical revenue end, shortest reported
    duration on ties. Require exact month-aligned calendar/fiscal boundaries and currency;
    no skipped quarter, YTD subtraction, annual/quarter mixing, older-pair fallback or
    unresolved conflicting values. Missing/stale/zero-denominator/unsupported-calendar
    inputs are unavailable. Thresholds preserve positive_min/negative_max: >= positive_min
    is positive, else <= negative_max negative, else neutral (defaults 0/positive_min).
    max_period_age_days defaults to 550; plausible_abs_max defaults to 5 and downgrades
    extreme observations to partial/0.5 without changing their measurement or state.
    """
    basis = _revenue_acceleration_adjacent_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    current, year_ago, previous, previous_year_ago = basis.facts
    value = float(_reported_fraction(current) / _reported_fraction(year_ago)
                  - _reported_fraction(previous) / _reported_fraction(previous_year_ago))
    return _numeric_result(spec, value, current.document, as_of, label="revenue_acceleration",
        measurement_unit="fraction_difference",
        measurement_formula="current window YoY growth - immediately previous same-cadence window YoY growth",
        measurement_period=current, evidence=_fact_evidence(basis.facts, as_of), plausible_abs_max=5.0)


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days")
@signal_input_facts(_gross_margin_yoy_input_facts)
def _gross_margin_change_yoy_signal(spec, documents, as_of):
    """Measure latest GrossProfit/revenue minus the same reported fiscal window's margin
    one year earlier. Anchor to latest canonical revenue end, shortest reported duration
    on ties, before matching profit. Require exact 3/6/9/12-month aligned reported windows,
    matching currencies and exact calendar-year shifts of both boundaries; YTD compares
    identical YTD windows. Missing/stale/zero-revenue/unsupported-calendar or unresolved
    conflicting facts are unavailable, never replaced by an older complete pair.
    Thresholds preserve positive_min/negative_max: >= positive_min positive, else
    <= negative_max negative, else neutral (defaults 0/positive_min).
    max_period_age_days defaults to 550; plausible_abs_max defaults to 2 and downgrades
    extremes to partial/0.5 without changing their measurement or state.
    """
    basis = _gross_margin_yoy_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    current, gross, previous, previous_gross = basis.facts
    value = float(_reported_fraction(gross)/_reported_fraction(current)
                  - _reported_fraction(previous_gross)/_reported_fraction(previous))
    return _numeric_result(spec, value,
        current.document, as_of, label="gross_margin_change", measurement_unit="fraction_difference",
        measurement_formula="current gross profit / revenue - same fiscal window prior-year gross profit / revenue",
        measurement_period=current, evidence=_fact_evidence(basis.facts, as_of), plausible_abs_max=2.0)


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days")
@signal_input_facts(_operating_margin_input_facts)
def _operating_cash_flow_margin_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure operating cash flow margin as operating cash flow / positive revenue for the
    latest matching SEC duration period (same start, end and units). Revenue comes from
    the per-issuer canonical total series (dominance-resolved; partial or zero
    same-period tag values never displace the total). Requires both revenue
    and operating-cash-flow facts. This does not measure operating-income alignment or
    cash runway. Missing/mismatched/stale facts yield unavailable. Numeric states use
    positive_min (default 0) and negative_max (default positive_min): value >=
    positive_min is positive, otherwise value <= negative_max is negative, otherwise
    neutral. Thresholds do not change the measurement. Values beyond plausible_abs_max
    (default 1.5) are downgraded to partial coverage at 0.5 confidence with an
    implausible_value marker. max_period_age_days (default 550) bounds current SEC
    period age; older comparative periods remain allowed.
    """

    basis = _operating_margin_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    revenue, cash_flow = basis.facts
    latest = (revenue.end, cash_flow.value / revenue.value, revenue, cash_flow)
    return _numeric_result(
        spec,
        latest[1],
        latest[2].document,
        as_of,
        label="operating_cash_flow_margin",
        measurement_unit='fraction',
        measurement_formula='operating cash flow / same-period revenue',
        measurement_period=latest[2],
        evidence=_fact_evidence((latest[2], latest[3]), as_of),
        plausible_abs_max=1.5,
    )


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days")
@signal_input_facts(_share_input_facts)
def _net_share_retirement_yoy_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure net share retirement as 1 - current / prior-year weighted-average shares over
    comparable periods. Positive means net retirement and negative means dilution; this is
    not a cash buyback amount. Missing comparable or stale current facts yield
    unavailable. Numeric states use positive_min (default 0) and negative_max (default
    positive_min): value >= positive_min is positive, otherwise value <= negative_max is
    negative, otherwise neutral. Thresholds do not change the measurement.
    Values beyond plausible_abs_max (default 1) retain their measurement and categorical
    state, but are downgraded to partial coverage at 0.5 confidence with an
    implausible_value marker; this is not an unavailable guard or numeric clamp.
    max_period_age_days (default 550) bounds current SEC period age; older comparative
    periods remain allowed.
    """

    basis = _share_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    current, previous = basis.facts
    value = 1.0 - (current.value / previous.value)
    return _numeric_result(
        spec,
        value,
        current.document,
        as_of,
        label="net_share_retirement_yoy",
        measurement_unit='fraction',
        measurement_formula='1 - current weighted-average shares / prior-year shares',
        measurement_period=current,
        evidence=_fact_evidence((current, previous), as_of),
        plausible_abs_max=1.0,
    )


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days")
@signal_input_facts(_cash_input_facts)
def _cash_reserves_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure the latest SEC instant cash and equivalents balance, in its reported currency
    units, without normalizing by burn, revenue or company size. Missing or stale current
    cash facts yield unavailable. Numeric states use positive_min (default 0) and
    negative_max (default positive_min): value >= positive_min is positive, otherwise
    value <= negative_max is negative, otherwise neutral. Thresholds do not change the
    measurement. max_period_age_days (default 550) bounds current SEC period age; older
    comparative periods remain allowed.
    Optional plausible_abs_max has no default bound; when configured and exceeded,
    the shared numeric builder retains value/state with partial coverage, 0.5
    confidence and implausible_value. It is not an unavailable guard or clamp.
    """

    basis = _cash_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    latest = basis.facts[0]
    return _numeric_result(
        spec,
        latest.value,
        latest.document,
        as_of,
        label="cash_reserves",
        measurement_unit=latest.unit.upper(),
        measurement_formula='latest reported instant cash balance',
        measurement_period=latest,
        evidence=_fact_evidence((latest,), as_of),
    )


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "max_period_age_days")
@signal_input_facts(_cash_liability_input_facts)
def _cash_to_current_liabilities_ratio_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure latest cash and equivalents / current liabilities for the same SEC
    instant period and reported currency. Non-positive liabilities and missing,
    mismatched, or stale facts yield unavailable. Numeric states use positive_min
    (default 0) and negative_max (default positive_min).
    Optional plausible_abs_max has no default bound; when configured and exceeded,
    the shared numeric builder retains value/state with partial coverage, 0.5
    confidence and implausible_value. It is not an unavailable guard or clamp.
    """

    basis = _cash_liability_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    cash_fact, liabilities_fact = basis.facts
    return _numeric_result(
        spec,
        cash_fact.value / liabilities_fact.value,
        cash_fact.document,
        as_of,
        label="cash_to_current_liabilities_ratio",
        measurement_unit='ratio',
        measurement_formula='cash / same-date current liabilities',
        measurement_period=cash_fact,
        evidence=_fact_evidence((cash_fact, liabilities_fact), as_of),
    )


@signal_parameter_names("burn_threshold", "max_period_age_days")
@signal_input_facts(_cash_flow_cash_input_facts)
def _cash_burn_rate_elevated_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure cash burn as absolute negative operating cash flow / cash for the latest
    SEC duration, using the closest same-currency cash instant at or before period end.
    Non-negative operating cash flow is a zero burn ratio. Missing, non-positive cash,
    mismatched, or stale facts yield unavailable. burn_threshold defaults to 0.10;
    qualifying burn is positive, observed zero burn is negative, and an observed
    below-threshold positive burn is neutral.
    """

    match = _latest_cash_flow_and_cash(spec, documents, as_of)
    if isinstance(match, SignalResult):
        return match
    cash_flow, cash = match
    threshold = _finite_nonnegative_parameter(spec, "burn_threshold", 0.10)
    ratio = abs(min(cash_flow.value, 0.0)) / cash.value
    if cash_flow.value >= 0:
        state = SignalValue.NEGATIVE
    elif ratio >= threshold:
        state = SignalValue.POSITIVE
    else:
        state = SignalValue.NEUTRAL
    return _explicit_numeric_result(
        spec,
        state,
        ratio,
        label="cash_burn_rate_elevated",
        measurement_unit='ratio',
        measurement_formula='absolute negative operating cash flow / cash',
        measurement_period=cash_flow,
        evidence=_fact_evidence((cash_flow, cash), as_of),
    )


@signal_parameter_names("positive_runway_max_months", "negative_runway_min_months", "max_period_age_days")
@signal_input_facts(_cash_flow_cash_input_facts)
def _liquidity_runway_months_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure cash runway in months from the latest SEC operating cash flow
    duration and the closest same-currency cash instant at or before its end. Monthly
    burn is absolute cash flow divided by the rounded reported duration in months.
    Missing, non-positive, mismatched, or stale facts yield unavailable. Runway <=
    positive_runway_max_months (default 6) is positive,
    runway >= negative_runway_min_months (default 12) is negative, and values between
    are neutral. The positive branch is checked first, so an equal pair of
    thresholds assigns the shared boundary to positive. Non-negative operating cash flow is negative evidence of a
    low-runway condition (an effectively unbounded burn runway).
    """

    match = _latest_cash_flow_and_cash(spec, documents, as_of)
    if isinstance(match, SignalResult):
        return match
    cash_flow, cash = match
    if cash_flow.value >= 0:
        return SignalResult(
            signal_id=spec.signal_id,
            version=spec.version,
            value=SignalValue.NEGATIVE,
            confidence=1.0,
            interpretation=(
                "liquidity_runway_months=unbounded_nonnegative_operating_cash_flow"
            ),
            supporting_evidence=_fact_evidence((cash_flow, cash), as_of),
            coverage=SignalCoverage.SUFFICIENT,
        )
    assert cash_flow.start is not None
    days = (
        datetime.fromisoformat(cash_flow.end)
        - datetime.fromisoformat(cash_flow.start)
    ).days + 1
    months = max(1, round(days / (365.2425 / 12.0)))
    runway = cash.value / (abs(cash_flow.value) / months)
    positive_max = _finite_nonnegative_parameter(
        spec, "positive_runway_max_months", 6.0
    )
    negative_min = _finite_nonnegative_parameter(
        spec, "negative_runway_min_months", 12.0
    )
    if negative_min < positive_max:
        raise ValidationError(
            "negative_runway_min_months cannot be below positive_runway_max_months"
        )
    if runway <= positive_max:
        state = SignalValue.POSITIVE
    elif runway >= negative_min:
        state = SignalValue.NEGATIVE
    else:
        state = SignalValue.NEUTRAL
    return _explicit_numeric_result(
        spec,
        state,
        runway,
        label="liquidity_runway_months",
        measurement_unit='months',
        measurement_formula='cash / (absolute negative operating cash flow / reported months)',
        measurement_period=cash_flow,
        evidence=_fact_evidence((cash_flow, cash), as_of),
    )


def _sec_facts(
    documents: tuple[RawInfoDocument, ...], as_of: datetime
) -> tuple[_SecFact, ...]:
    """Parse only the two supported SEC Company Facts source schemas."""

    facts: list[_SecFact] = []
    for document in documents:
        try:
            payload = json.loads(document.content)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, Mapping):
            continue
        canonical_spans = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
            == document.content
        )
        namespaces = payload.get("facts")
        recognized = payload.get("schema_version") == "sec-company-facts-document-v1" or (
            isinstance(namespaces, Mapping) and any(isinstance(namespaces.get(key), Mapping)
                                                   for key in ("us-gaap", "ifrs-full")))
        if recognized:
            try:
                validate_company_fact_document_issuer(document, payload)
            except DataSourceError as error:
                raise ValidationError(str(error)) from None
        if payload.get("schema_version") == "sec-company-facts-document-v1":
            filing_date = str(payload.get("filing_date", ""))
            form = str(payload.get("form", ""))
            for raw in payload.get("facts", ()):
                if not isinstance(raw, Mapping):
                    continue
                fact = _make_sec_fact(
                    raw,
                    tag=str(raw.get("tag", "")),
                    value=raw.get("value"),
                    unit=str(raw.get("unit", "")),
                    filed=filing_date,
                    form=form,
                    document=document,
                    as_of=as_of,
                    canonical_spans=canonical_spans,
                )
                if fact is not None:
                    facts.append(fact)
            continue
        if not isinstance(namespaces, Mapping):
            continue
        reporting_facts = namespaces.get("us-gaap")
        if not isinstance(reporting_facts, Mapping):
            reporting_facts = namespaces.get("ifrs-full")
        if not isinstance(reporting_facts, Mapping):
            continue
        for tag, definition in reporting_facts.items():
            if not isinstance(definition, Mapping):
                continue
            units = definition.get("units")
            if not isinstance(units, Mapping):
                continue
            for unit, rows in units.items():
                if not isinstance(rows, list):
                    continue
                for raw in rows:
                    if not isinstance(raw, Mapping):
                        continue
                    fact = _make_sec_fact(
                        raw,
                        tag=str(tag),
                        value=raw.get("val"),
                        unit=str(unit),
                        filed=str(raw.get("filed", "")),
                        form=str(raw.get("form", "")),
                        document=document,
                        as_of=as_of,
                        canonical_spans=canonical_spans,
                    )
                    if fact is not None:
                        facts.append(fact)
    return tuple(facts)


def _make_sec_fact(
    raw: Mapping[str, Any],
    *,
    tag: str,
    value: Any,
    unit: str,
    filed: str,
    form: str,
    document: RawInfoDocument,
    as_of: datetime,
    canonical_spans: bool = False,
) -> _SecFact | None:
    if not tag or not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    end = str(raw.get("end", ""))
    start_value = raw.get("start")
    start = str(start_value) if start_value else None
    try:
        end_date = datetime.fromisoformat(end).date()
        filed_date = datetime.fromisoformat(filed).date()
        if start is not None:
            datetime.fromisoformat(start)
    except ValueError:
        return None
    if company_fact_available_at(filed_date) > as_of or end_date > utc_day_of_instant(as_of):
        return None
    exact_span = json.dumps(dict(raw), sort_keys=True, separators=(",", ":"))
    if not canonical_spans and exact_span not in document.content:
        return None
    return _SecFact(
        tag=tag,
        value=float(value),
        unit=unit,
        start=start,
        end=end,
        filed=filed,
        form=form,
        document=document,
        exact_span=exact_span,
    )


def _canonical_series(
    facts: Iterable[_SecFact],
    tags: tuple[str, ...],
    *,
    dominance: bool = True,
) -> list[_SecFact]:
    """Resolve one canonical per-currency series for an issuer's concept total.

    A tag whose same-period value is at least _PARTIAL_VALUE_RATIO times
    smaller than a co-occurring value (or zero beside a nonzero value) is a
    disaggregation partial and is excluded entirely, including periods no other
    tag covers; detection is direction-free and runs before ranking so a
    coverage tie can never promote a partial tag. Among remaining total tags
    the canonical basis is the coverage-ranked one: latest period end, then
    distinct period count, then the declared tag order. A period key covered by
    the canonical tag keeps the canonical fact; remaining trusted tags fill only
    uncovered keys, so a tag switch or a percent-level restatement crossover
    stitches into one series while a partial slice never enters it. When no
    fact is eligible, or every present tag is partial, the series is empty and
    callers fail closed. With dominance disabled the legacy priority order
    stands per key, except a zero-valued preferred tag cannot displace a
    nonzero same-period value. Returns one currency's series (USD preferred,
    else latest period end, else unit name), latest end first.
    """

    tag_priority = {tag: index for index, tag in enumerate(tags)}
    eligible = [
        fact
        for fact in facts
        if fact.tag in tag_priority
        and fact.start is not None
        and re.fullmatch(r"[A-Za-z]{3}", fact.unit) is not None
    ]
    by_key: dict[tuple[str, str, str], dict[str, _SecFact]] = {}
    for fact in sorted(
        eligible,
        key=lambda item: (item.start or "", item.end, item.filed, item.document.document_id),
    ):
        key = (fact.start or "", fact.end, fact.unit.casefold())
        by_key.setdefault(key, {}).setdefault(fact.tag, fact)

    present = {fact.tag for fact in eligible}
    if not present:
        return []
    # Direction-free partial detection: a tag at least _PARTIAL_VALUE_RATIO
    # times smaller than a co-occurring same-period value is a disaggregation
    # slice and is excluded entirely, before any canonical ranking can prefer
    # it through a coverage tie.
    partial_tags: set[str] = set()
    if dominance:
        for tag_map in by_key.values():
            for tag, fact in tag_map.items():
                if tag in partial_tags:
                    continue
                for other_tag, other in tag_map.items():
                    if other_tag == tag:
                        continue
                    if abs(other.value) >= _PARTIAL_VALUE_RATIO * max(
                        abs(fact.value), 1e-9
                    ) or (other.value != 0 and fact.value == 0):
                        partial_tags.add(tag)
                        break
    total_tags = present - partial_tags
    if not total_tags:
        return []
    coverage = {
        tag: (
            max(fact.end for fact in eligible if fact.tag == tag),
            sum(1 for key in by_key if tag in by_key[key]),
        )
        for tag in total_tags
    }
    canonical = max(
        total_tags,
        key=lambda tag: (coverage[tag][0], coverage[tag][1], -tag_priority[tag], tag),
    )

    selected: dict[tuple[str, str, str], _SecFact] = {}
    for key, tag_map in by_key.items():
        trusted = sorted(
            (
                (tag_priority[tag], fact)
                for tag, fact in tag_map.items()
                if tag not in partial_tags
            ),
            key=lambda row: (row[0], row[1].filed, row[1].document.document_id),
        )
        if not trusted:
            continue
        chosen = tag_map[canonical] if canonical in tag_map else trusted[0][1]
        if chosen.value == 0:
            nonzero = [row[1] for row in trusted if row[1].value != 0]
            if nonzero:
                chosen = nonzero[0]
        selected[key] = chosen

    by_unit: dict[str, list[_SecFact]] = {}
    for fact in selected.values():
        by_unit.setdefault(fact.unit.casefold(), []).append(fact)
    unit = min(
        by_unit,
        key=lambda name: (
            name != "usd",
            max(fact.end for fact in by_unit[name]),
            name,
        ),
    )
    return sorted(by_unit[unit], key=lambda fact: fact.end, reverse=True)


def _instant_series(
    facts: Iterable[_SecFact], tags: tuple[str, ...]
) -> list[_SecFact]:
    """Return one preferred monetary instant fact per end date and currency."""

    tag_priority = {tag: index for index, tag in enumerate(tags)}
    eligible = [
        fact
        for fact in facts
        if fact.tag in tag_priority
        and fact.start is None
        and re.fullmatch(r"[A-Za-z]{3}", fact.unit) is not None
    ]
    by_period: dict[tuple[str, str], _SecFact] = {}
    for fact in eligible:
        key = (fact.end, fact.unit.casefold())
        current = by_period.get(key)
        if current is None or (
            (
                -tag_priority[fact.tag],
                fact.filed,
                fact.document.document_id,
            )
            > (
                -tag_priority[current.tag],
                current.filed,
                current.document.document_id,
            )
            and (fact.value != 0 or current.value == 0)
        ):
            by_period[key] = fact
    return sorted(
        by_period.values(),
        key=lambda fact: (fact.end, fact.unit.casefold() == "usd", fact.unit),
        reverse=True,
    )


def _latest_cash_flow_and_cash(spec, documents, as_of):
    """Keep the prior matching API while sharing the pure operand basis."""
    basis = _cash_flow_cash_input_facts(spec, documents, as_of)
    if basis.unavailable_reason is not None:
        return _unavailable_result(spec, basis.unavailable_reason)
    return basis.facts



def _share_duration_series(facts: Iterable[_SecFact]) -> list[_SecFact]:
    """Keep filing-scoped share contexts so split-restated pairs can be preferred."""

    tag_priority = {tag: index for index, tag in enumerate(_SHARE_COUNT_TAGS)}
    eligible = [
        fact
        for fact in facts
        if fact.tag in tag_priority
        and fact.start is not None
        and fact.unit.casefold() == "shares"
        and fact.value > 0
    ]
    by_context: dict[tuple[str, str, str, str], _SecFact] = {}
    for fact in eligible:
        key = (
            fact.start or "",
            fact.end,
            fact.filed,
            fact.document.document_id,
        )
        current = by_context.get(key)
        if current is None or tag_priority[fact.tag] < tag_priority[current.tag]:
            by_context[key] = fact
    return sorted(
        by_context.values(),
        key=lambda fact: (fact.end, fact.filed, fact.document.document_id),
        reverse=True,
    )


def _current_sec_fact_is_fresh(
    spec: SignalSpec, fact: _SecFact, as_of: datetime
) -> bool:
    """Require a bounded current SEC period while allowing older comparatives."""

    raw_limit = spec.parameters.get(
        "max_period_age_days", _MAX_SEC_CURRENT_PERIOD_AGE_DAYS
    )
    if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or raw_limit < 1:
        raise ValidationError("max_period_age_days must be a positive integer")
    period_end = datetime.fromisoformat(fact.end).date()
    return (as_of.date() - period_end).days <= raw_limit


def _latest_share_yoy_pair(
    series: list[_SecFact],
) -> tuple[_SecFact, _SecFact] | None:
    for current in series:
        current_end = datetime.fromisoformat(current.end).date()
        candidates = [
            previous
            for previous in series
            if previous.tag == current.tag
            and previous.end < current.end
            and 330
            <= (current_end - datetime.fromisoformat(previous.end).date()).days
            <= 400
            and _comparable_duration(current, previous)
        ]
        if not candidates:
            continue
        previous = max(
            candidates,
            key=lambda fact: (
                fact.document.document_id == current.document.document_id,
                fact.filed == current.filed,
                fact.end,
                fact.filed,
                fact.document.document_id,
            ),
        )
        return current, previous
    return None


def _comparable_duration(left: _SecFact, right: _SecFact) -> bool:
    if (left.start is None or right.start is None
            or left.unit.casefold() != right.unit.casefold()):
        return False
    left_days = (
        datetime.fromisoformat(left.end) - datetime.fromisoformat(left.start)
    ).days
    right_days = (
        datetime.fromisoformat(right.end) - datetime.fromisoformat(right.start)
    ).days
    return abs(left_days - right_days) <= 45


def _yoy_pairs(series: list[_SecFact]) -> list[tuple[_SecFact, _SecFact]]:
    pairs: list[tuple[_SecFact, _SecFact]] = []
    for current in series:
        current_end = datetime.fromisoformat(current.end).date()
        candidates = [
            previous
            for previous in series
            if previous.end < current.end
            and 330 <= (current_end - datetime.fromisoformat(previous.end).date()).days <= 400
            and _comparable_duration(current, previous)
        ]
        if candidates:
            pairs.append((current, max(candidates, key=lambda fact: fact.end)))
    return pairs


def _latest_yoy_pair(
    series: list[_SecFact],
) -> tuple[_SecFact, _SecFact] | None:
    pairs = _yoy_pairs(series)
    return pairs[0] if pairs else None


def _fact_evidence(
    facts: Iterable[_SecFact], as_of: datetime
) -> tuple[SignalEvidence, ...]:
    seen: set[tuple[str, str]] = set()
    evidence: list[SignalEvidence] = []
    for fact in facts:
        key = (fact.document.document_id, fact.exact_span)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            SignalEvidence(
                document_id=fact.document.document_id,
                exact_span=fact.exact_span,
                timestamp=min(fact.document.available_at, as_of),
            )
        )
    return tuple(evidence)


def _price_series_evidence(
    document: RawInfoDocument,
    values: list[Any],
    indices: Iterable[int],
    as_of: datetime,
) -> tuple[SignalEvidence, ...] | None:
    """Cite complete calculation anchors after verifying raw/metadata alignment."""

    try:
        rows = json.loads(document.content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(rows, list) or not rows or not all(
        isinstance(row, Mapping) and "close" in row for row in rows
    ):
        return None
    raw_prices = [
        row["adjusted_close"] if row.get("adjusted_close") is not None else row["close"]
        for row in rows
    ]
    if raw_prices != values:
        raise ValidationError("raw price bars do not match metadata.prices")
    decoder = json.JSONDecoder()
    offset = document.content.index("[") + 1
    spans: list[str] = []
    for _row in rows:
        while document.content[offset].isspace() or document.content[offset] == ",":
            offset += 1
        _value, end = decoder.raw_decode(document.content, offset)
        spans.append(document.content[offset:end])
        offset = end
    return tuple(
        SignalEvidence(
            document_id=document.document_id, exact_span=spans[index],
            timestamp=min(document.available_at, as_of),
        )
        for index in sorted(set(indices))
    )


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max")
def _max_drawdown_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure the minimum price / preceding running peak - 1 over all observations in the
    latest supplied metadata.prices series. This function does not itself restrict dates
    to one year; retrieval owns the point-in-time series window. Missing prices yield
    unavailable; invalid or nonpositive prices fail validation. Numeric states use
    positive_min (default 0) and negative_max (default positive_min): value >=
    positive_min is positive, otherwise value <= negative_max is negative, otherwise
    neutral. Thresholds do not change the measurement.
    Optional plausible_abs_max has no default bound; when configured and exceeded,
    the shared numeric builder retains value/state with partial coverage, 0.5
    confidence and implausible_value. It is not an unavailable guard or clamp.
    """

    found = _latest_metadata_value(documents, "prices")
    if found is None:
        return _unavailable_result(spec, "Raw Info did not contain a price series.")
    values, document = found
    if not isinstance(values, list) or not values:
        raise ValidationError("market price metadata must be a non-empty list")
    peak = -math.inf
    drawdown = 0.0
    peak_index = 0
    drawdown_peak = 0
    drawdown_trough = 0
    for index, raw in enumerate(values):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValidationError("market price metadata must be numeric")
        price = float(raw)
        if not math.isfinite(price) or price <= 0:
            raise ValidationError("market price metadata must be finite and positive")
        if price > peak:
            peak, peak_index = price, index
        current = (price / peak) - 1
        if current < drawdown:
            drawdown, drawdown_peak, drawdown_trough = current, peak_index, index
    return _numeric_result(
        spec, drawdown, document, as_of, label="max_drawdown_1y",
        measurement_unit="fraction",
        measurement_formula="minimum price / preceding running peak - 1",
        evidence=_price_series_evidence(
            document, values, (0, drawdown_peak, drawdown_trough, len(values) - 1), as_of,
        ),
    )


@signal_parameter_names("positive_min", "negative_max", "plausible_abs_max", "lookback_observations")
def _price_momentum_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Measure last / first price - 1 over the final lookback_observations + 1 supplied
    metadata.prices values (default lookback_observations=126, positive integer). Fewer
    observations yield unavailable; prices must be finite positive numbers. Retrieval owns
    dates and adjustment convention. Numeric states use positive_min (default 0) and
    negative_max (default positive_min): value >= positive_min is positive, otherwise
    value <= negative_max is negative, otherwise neutral. Thresholds do not change the
    measurement. Values beyond plausible_abs_max (default 50) retain their measurement
    and categorical state, but are downgraded to partial coverage at 0.5 confidence
    with an implausible_value marker; this is not an unavailable guard or numeric clamp.
    """

    found = _latest_metadata_value(documents, "prices")
    if found is None:
        return _unavailable_result(spec, "Raw Info did not contain a price series.")
    values, document = found
    if not isinstance(values, list) or not values:
        raise ValidationError("market price metadata must be a non-empty list")
    raw_lookback = spec.parameters.get("lookback_observations", 126)
    if isinstance(raw_lookback, bool) or not isinstance(raw_lookback, int):
        raise ValidationError("price momentum lookback_observations must be an integer")
    if raw_lookback < 1:
        raise ValidationError("price momentum lookback_observations must be positive")
    if len(values) <= raw_lookback:
        return _unavailable_result(
            spec,
            f"Price history requires {raw_lookback + 1} observations; received {len(values)}.",
        )
    window: list[float] = []
    for raw in values[-(raw_lookback + 1) :]:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValidationError("market price metadata must be numeric")
        price = float(raw)
        if not math.isfinite(price) or price <= 0:
            raise ValidationError("market price metadata must be finite and positive")
        window.append(price)
    momentum = window[-1] / window[0] - 1.0
    return _numeric_result(
        spec,
        momentum,
        document,
        as_of,
        label=f"price_momentum_{raw_lookback}d",
        measurement_unit="fraction",
        measurement_formula="last / first supplied price - 1 in the supplied lookback",
        evidence=_price_series_evidence(
            document, values, (len(values) - raw_lookback - 1, len(values) - 1), as_of,
        ),
        plausible_abs_max=50.0,
    )


@signal_parameter_names("terms", "negative_count_min")
def _negative_word_count_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Count case-insensitive literal substring occurrences across input documents.

    terms defaults to decline, loss, risk, delay, investigation, default.
    Count >= negative_count_min (default 1) is negative; otherwise neutral.
    This measures lexical frequency, not semantic sentiment or event severity.
    """

    raw_terms = spec.parameters.get(
        "terms",
        ("decline", "loss", "risk", "delay", "investigation", "default"),
    )
    if not isinstance(raw_terms, (list, tuple)):
        raise ValidationError("negative word count terms must be a list")
    terms = tuple(str(item).casefold() for item in raw_terms if str(item).strip())
    count = 0
    evidence: list[SignalEvidence] = []
    for document in documents:
        content = document.content.casefold()
        document_count = sum(content.count(term) for term in terms)
        count += document_count
        if document_count == 0:
            continue
        first_match = min(
            position
            for term in terms
            if (position := content.find(term)) >= 0
        )
        start = max(0, first_match - 80)
        span = document.content[start : min(len(document.content), start + 240)]
        evidence.append(
            SignalEvidence(
                document_id=document.document_id,
                exact_span=span,
                timestamp=min(document.available_at, as_of),
            )
        )
    threshold = int(spec.parameters.get("negative_count_min", 1))
    if not evidence:
        document = documents[0]
        evidence.append(
            SignalEvidence(
                document_id=document.document_id,
                exact_span=document.content[: min(240, len(document.content))],
                timestamp=min(document.available_at, as_of),
            )
        )
    return SignalResult(
        signal_id=spec.signal_id,
        version=spec.version,
        value=(SignalValue.NEGATIVE if count >= threshold else SignalValue.NEUTRAL),
        confidence=1.0,
        interpretation=f"negative_word_count={count}",
        measurement=NumericMeasurement(count, "count", "literal substring occurrences across input documents"),
        supporting_evidence=tuple(evidence),
        coverage=SignalCoverage.SUFFICIENT,
    )


def _numeric_result(
    spec: SignalSpec,
    numeric_value: float,
    document: RawInfoDocument,
    as_of: datetime,
    *,
    label: str,
    measurement_unit: str,
    measurement_formula: str,
    measurement_period: _SecFact | None = None,
    evidence: tuple[SignalEvidence, ...] | None = None,
    plausible_abs_max: float | None = None,
) -> SignalResult:
    positive_min = float(spec.parameters.get("positive_min", 0.0))
    negative_max = float(spec.parameters.get("negative_max", positive_min))
    if negative_max > positive_min:
        raise ValidationError("negative_max cannot exceed positive_min")
    if numeric_value >= positive_min:
        value = SignalValue.POSITIVE
    elif numeric_value <= negative_max:
        value = SignalValue.NEGATIVE
    else:
        value = SignalValue.NEUTRAL
    raw_bound = spec.parameters.get("plausible_abs_max", plausible_abs_max)
    gated = (
        isinstance(raw_bound, (int, float))
        and not isinstance(raw_bound, bool)
        and math.isfinite(float(raw_bound))
        and abs(numeric_value) > float(raw_bound)
    )
    span = document.content[: min(240, len(document.content))]
    supporting = evidence or (
        SignalEvidence(
            document_id=document.document_id,
            exact_span=span,
            timestamp=min(document.available_at, as_of),
        ),
    )
    return SignalResult(
        measurement=NumericMeasurement(
            numeric_value, measurement_unit, measurement_formula,
            measurement_period.end if measurement_period else None,
            measurement_period.start if measurement_period else None,
        ),
        signal_id=spec.signal_id,
        version=spec.version,
        value=value,
        confidence=0.5 if gated else 1.0,
        interpretation=(
            f"{label}={numeric_value:.6g}"
            + ("; implausible_value" if gated else "")
        ),
        supporting_evidence=supporting,
        coverage=SignalCoverage.PARTIAL if gated else SignalCoverage.SUFFICIENT,
    )


def _finite_nonnegative_parameter(
    spec: SignalSpec, name: str, default: float
) -> float:
    raw = spec.parameters.get(name, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValidationError(f"{name} must be numeric")
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise ValidationError(f"{name} must be finite and non-negative")
    return value


def _explicit_numeric_result(
    spec: SignalSpec,
    value: SignalValue,
    numeric_value: float,
    *,
    label: str,
    measurement_unit: str,
    measurement_formula: str,
    measurement_period: _SecFact | None = None,
    evidence: tuple[SignalEvidence, ...],
) -> SignalResult:
    if not math.isfinite(numeric_value):
        raise ValidationError(f"{label} must be finite")
    return SignalResult(
        measurement=NumericMeasurement(
            numeric_value, measurement_unit, measurement_formula,
            measurement_period.end if measurement_period else None,
            measurement_period.start if measurement_period else None,
        ),
        signal_id=spec.signal_id,
        version=spec.version,
        value=value,
        confidence=1.0,
        interpretation=f"{label}={numeric_value:.6g}",
        supporting_evidence=evidence,
        coverage=SignalCoverage.SUFFICIENT,
    )


def _unavailable_result(spec: SignalSpec, interpretation: str) -> SignalResult:
    return SignalResult(
        signal_id=spec.signal_id,
        version=spec.version,
        value=SignalValue.UNAVAILABLE,
        confidence=0.0,
        interpretation=interpretation,
        coverage=SignalCoverage.UNAVAILABLE,
    )


def _latest_metadata_value(
    documents: tuple[RawInfoDocument, ...], key: str
) -> tuple[Any, RawInfoDocument] | None:
    """Choose complete compatible metadata independently of resolver ordering."""

    candidates = [document for document in documents if key in document.metadata]
    if not candidates:
        return None
    def endpoint(document: RawInfoDocument) -> str:
        return str(document.metadata.get("end") or document.available_at.date().isoformat())

    latest = max(endpoint(document) for document in candidates)
    candidates = [document for document in candidates if endpoint(document) == latest]
    if any(not isinstance(document.metadata[key], list) for document in candidates):
        raise ValidationError("market price metadata must be a list")
    selected = max(
        candidates,
        key=lambda document: (len(document.metadata[key]), document.available_at, document.document_id),
    )
    values = selected.metadata[key]
    for document in candidates:
        other = document.metadata[key]
        if other and values[-len(other):] != other:
            raise ValidationError("conflicting market series at the same endpoint")
    return values, selected


def _build_signal_learning_profile(
    signal_ref: str,
    events: Iterable[SignalLearningEvent],
) -> dict[str, Any]:
    """Derive one bounded identity-free observational profile."""

    materialized = tuple(events)
    observations: dict[str, SignalLearningEvent] = {}
    disputed: set[str] = set()
    for event in materialized:
        if event.signal_ref != signal_ref:
            raise ValidationError("cannot mix Signal refs in one learning profile")
        prior = observations.get(event.observation_key)
        if prior is not None and (
            prior.is_surge != event.is_surge
            or prior.realized_max_multiple != event.realized_max_multiple
            or prior.company_id != event.company_id
            or prior.case_id != event.case_id
            or prior.prediction_time != event.prediction_time
            or prior.document_fingerprint != event.document_fingerprint
        ):
            raise ValidationError("conflicting duplicate Signal learning observation")
        if prior is not None and (
            prior.result_value is not event.result_value
            or prior.coverage is not event.coverage
        ):
            disputed.add(event.observation_key)
        observations.setdefault(event.observation_key, event)
    observations = {
        key: event for key, event in observations.items() if key not in disputed
    }

    matrix = {
        value.value: {"surge": 0, "non_surge": 0}
        for value in SignalValue
    }
    directional_correct = 0
    directional_wrong = 0
    unavailable = 0
    unavailable_with_inputs = 0
    for event in observations.values():
        outcome = "surge" if event.is_surge else "non_surge"
        matrix[event.result_value.value][outcome] += 1
        unavailable += int(event.result_value is SignalValue.UNAVAILABLE)
        unavailable_with_inputs += int(
            event.result_value is SignalValue.UNAVAILABLE
            and bool(event.document_fingerprint)
        )
        if event.result_value is SignalValue.POSITIVE:
            directional_correct += int(event.is_surge)
            directional_wrong += int(not event.is_surge)
        elif event.result_value is SignalValue.NEGATIVE:
            directional_correct += int(not event.is_surge)
            directional_wrong += int(event.is_surge)

    tag_observations: dict[str, set[str]] = {}
    tag_issuers: dict[str, set[str]] = {}
    tag_positive_surge: dict[str, list[int]] = {}
    reason_counts: dict[str, int] = {}
    for event in materialized:
        reason_code = str(event.selection.get("reason_code", "unspecified"))[:40]
        reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1
        if event.observation_key in disputed:
            continue
        for raw_tag in event.selection.get("context_tags", ()):
            tag = _learning_token(str(raw_tag))
            if not tag:
                continue
            tag_observations.setdefault(tag, set()).add(event.observation_key)
            tag_issuers.setdefault(tag, set()).add(event.company_id)
    for tag, observation_ids in tag_observations.items():
        positive = 0
        positive_surge = 0
        for observation_id in observation_ids:
            event = observations[observation_id]
            if event.result_value is SignalValue.POSITIVE:
                positive += 1
                positive_surge += int(event.is_surge)
        tag_positive_surge[tag] = [positive, positive_surge]

    patterns: list[dict[str, Any]] = []
    ordered_tags = sorted(
        tag_observations,
        key=lambda tag: (-len(tag_observations[tag]), tag),
    )
    for tag in ordered_tags:
        observation_count = len(tag_observations[tag])
        issuer_count = len(tag_issuers[tag])
        if observation_count < 2 or issuer_count < 2:
            continue
        positive, positive_surge = tag_positive_surge[tag]
        patterns.append(
            {
                "context_tag": tag,
                "observations": observation_count,
                "issuers": issuer_count,
                "positive_surge_rate": (
                    positive_surge / positive if positive else None
                ),
            }
        )
        if len(patterns) == 3:
            break

    unique_count = len(observations)
    if unique_count < 2:
        confidence = "insufficient"
    elif unique_count < 4:
        confidence = "sparse"
    elif unique_count < 8:
        confidence = "emerging"
    else:
        confidence = "repeated"
    attribution_observations = {
        "misleading": set(),
        "ignored": set(),
        "other": set(),
    }
    for event in materialized:
        for item in event.reflection_attribution:
            key = item if item in attribution_observations else "other"
            attribution_observations[key].add(event.observation_key)
    attribution = {
        key: len(observation_ids)
        for key, observation_ids in attribution_observations.items()
    }

    return {
        "schema_version": "signal-learning-profile-v1",
        "signal_ref": signal_ref,
        "confidence": confidence,
        "selection_events": len(materialized),
        "unique_observations": unique_count,
        "disputed_observations": len(disputed),
        "unique_issuers": len({event.company_id for event in observations.values()}),
        "state_outcome_matrix": matrix,
        "directional": {
            "correct": directional_correct,
            "wrong": directional_wrong,
            "unavailable": unavailable,
            "unavailable_with_inputs": unavailable_with_inputs,
            "unavailable_without_inputs": unavailable - unavailable_with_inputs,
        },
        "reflection_attribution": attribution,
        "selection_reason_codes": [
            {"reason_code": reason, "count": count}
            for reason, count in sorted(
                reason_counts.items(), key=lambda item: (-item[1], item[0])
            )[:3]
        ],
        "recurring_contexts": patterns,
    }


def _learning_token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_:-]+", "_", value.casefold()).strip("_")
    return normalized[:48]


def _parse_ref(signal_ref: str) -> tuple[str, int]:
    match = re.fullmatch(r"([a-z0-9][a-z0-9_:-]*):v([1-9][0-9]*)", signal_ref)
    if match is None:
        raise ValidationError(f"invalid signal ref: {signal_ref}")
    return match.group(1), int(match.group(2))


def _validate_id(value: str, name: str) -> None:
    if not _SAFE_ID.fullmatch(value):
        raise ValidationError(f"{name} must use lowercase safe identifier characters")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"required JSON artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON artifact must contain an object: {path}")
    return value


def _write_or_verify_text(path: Path, value: str) -> None:
    """Write immutable UTF-8 text atomically or verify an exact replay."""

    if path.exists():
        if path.read_text(encoding="utf-8") != value:
            raise ValidationError(f"conflicting immutable text artifact: {path}")
        return
    _atomic_write_text(path, value)


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    """Preserve an immutable governance artifact or verify an exact replay."""

    expected = json.loads(json.dumps(dict(value), sort_keys=True))
    if path.exists():
        if _read_json(path) != expected:
            raise ValidationError(f"conflicting immutable JSON artifact: {path}")
        return
    _atomic_write_json(path, expected)
