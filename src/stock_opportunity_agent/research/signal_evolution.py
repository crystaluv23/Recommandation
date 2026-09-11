"""Slow Signal evolution and finite dual-loop orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping, Protocol
from stock_opportunity_agent.artifacts import (
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    EvidenceResolver,
    RawInfoRequest,
    RawInfoResolution,
)
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    LLMSignalRunner,
    SignalExecutionStatus,
    SignalExecutionType,
    SignalExecutor,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
    default_deterministic_signal_functions,
    signal_result_model_view,
)

from stock_opportunity_agent.research.evolution_core import (
    AgentStep,
    CandidateExecutionRejected,
    DEFAULT_EVOLUTION_PRIORS,
    EvolutionCase,
    EvolutionDataset,
    EvolutionPriors,
    PlanMetaMemory,
    ProgressCallback,
    RuntimeBudgetExceeded,
    SlowLoopDataUnavailable,
    _compiled_identity_aliases,
    _MASKED_IDENTITY_VALUE,
    _assert_identity_values_masked,
    _discovery_identity_terms,
    _emit_progress,
    _exploration_case_pairs,
    _h3_ordered_content_terms,
    _h3_text_query_coverage,
    _item1_business_excerpt,
    _json_array,
    _json_string_array,
    _listing_age_bucket,
    _market_cap_bucket,
    _mask_identity_values,
    _model_evidence_view,
    _normalize_semantics,
    _ordered_unique,
    _point_in_time_profile_fields,
    _read_json,
    _require_aware_datetime,
    _sample_binary_discovery_cases,
    _sample_signal_discovery_cases,
    _select_h3_model_evidence,
    _slow_role_identity_guard_inventory,
    _usable_business_description,
    _usage_from_dict,
    _usage_to_dict,
    _validate_id,
)
from stock_opportunity_agent.research.plan_evolution import (
    EvolutionWorkspace,
    PlanEvolutionEngine,
    PlanRoundResult,
)


SIGNAL_UPDATE_MUTABLE_PATHS = (
    "spec.raw_retrieval.source_types",
    "spec.raw_retrieval.query_terms",
    "spec.raw_retrieval.lookback_days",
    "spec.raw_retrieval.comparison_requirement",
    "spec.raw_retrieval.required_source_groups",
    "spec.raw_retrieval.minimum_distinct_periods",
    "spec.raw_retrieval.minimum_period_span_days",
    "spec.raw_retrieval.minimum_observations",
    "spec.parameters",
    "spec.execution.skill_file",
    "skill",
)


@dataclass(frozen=True)
class SignalCandidateValidation:
    """Fail-closed validation result before stable Signal promotion."""

    signal_ref: str
    accepted: bool
    reasons: tuple[str, ...]
    candidate_hash: str = ""
    executed_tests: int = 0


class SignalCandidateValidator:
    """Validate schema, executability, leakage, evidence, and uniqueness."""

    def __init__(
        self,
        registry: SignalRegistry,
        *,
        llm_runner: LLMSignalRunner | None,
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        forbidden_identity_terms: Iterable[str] = (),
    ) -> None:
        self.registry = registry
        self.llm_runner = llm_runner
        self.deterministic_functions = {
            **default_deterministic_signal_functions(),
            **dict(deterministic_functions or {}),
        }
        self.forbidden_identity_terms = tuple(
            sorted(
                {
                    str(item).strip()
                    for item in forbidden_identity_terms
                    if len(str(item).strip()) >= 3
                },
                key=len,
                reverse=True,
            )
        )

    def validate(
        self,
        spec: SignalSpec,
        *,
        skill: str | None,
        tests: Iterable[Mapping[str, Any]],
    ) -> SignalCandidateValidation:
        reasons: list[str] = []
        materialized_tests = tuple(dict(item) for item in tests)
        try:
            current = self.registry.latest_spec(spec.signal_id)
        except ValidationError:
            current = None
        if current is None and spec.version != 1:
            reasons.append("new signal must start at version 1")
        if current is not None and spec.version != current.version + 1:
            reasons.append("update must use exactly the next stable version")
        if current is not None and spec.category != current.category:
            reasons.append("update must preserve the stable category")
        if current is not None and spec.execution_type is not current.execution_type:
            reasons.append("update must preserve the stable execution type")
        if (
            current is not None
            and current.execution_type is SignalExecutionType.DETERMINISTIC
            and spec.function != current.function
        ):
            reasons.append("deterministic update must preserve the registered function")
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            if spec.function not in self.deterministic_functions:
                reasons.append("deterministic function is not registered")
        elif self.llm_runner is None or not (skill or "").strip():
            reasons.append("LLM executor or skill is unavailable")
        if not all(
            (
                spec.evidence_policy.require_source,
                spec.evidence_policy.require_timestamp,
                spec.evidence_policy.require_exact_span,
            )
        ):
            reasons.append("candidate weakens required evidence traceability")
        serialized = json.dumps(spec.to_dict(), sort_keys=True)
        serialized += " " + (skill or "")
        serialized += " " + json.dumps(materialized_tests, sort_keys=True)
        for phrase in (
            "ground truth",
            "outcome label",
            "realized return",
            "future price",
            "post-outcome",
        ):
            if phrase in serialized.casefold():
                reasons.append(f"obvious leakage phrase: {phrase}")
        for identity, prose_matcher, _url_matcher in _compiled_identity_aliases(
            self.forbidden_identity_terms, expand_aliases=False
        ):
            if prose_matcher.search(serialized):
                reasons.append(f"discovery identity leaked into candidate: {identity}")
        normalized = _normalize_semantics(spec.description)
        for card in self.registry.list_signal_cards():
            if card.signal_id == spec.signal_id:
                continue
            if _normalize_semantics(card.description) == normalized:
                reasons.append(f"semantic duplicate of stable signal {card.signal_id}")
                break
        executed_tests = 0
        if not materialized_tests:
            reasons.append("candidate requires non-empty executable fixtures")
        elif not reasons:
            for index, fixture in enumerate(materialized_tests):
                try:
                    self._execute_fixture(spec, skill, fixture, index=index)
                    executed_tests += 1
                except (ValidationError, KeyError, TypeError, ValueError) as exc:
                    reasons.append(f"fixture {index + 1} failed: {exc}")
        return SignalCandidateValidation(
            signal_ref=spec.ref,
            accepted=not reasons,
            reasons=tuple(reasons),
            executed_tests=executed_tests,
        )

    def _execute_fixture(
        self,
        spec: SignalSpec,
        skill: str | None,
        fixture: Mapping[str, Any],
        *,
        index: int,
    ) -> None:
        name = str(fixture.get("name", "")).strip()
        if not name:
            raise ValidationError("fixture name is required")
        expected = SignalValue(str(fixture["expected"]))
        as_of = datetime.fromisoformat(
            str(fixture.get("as_of", "2025-01-01T00:00:00+00:00"))
        )
        _require_aware_datetime(as_of, "candidate fixture as_of")
        company_id = str(fixture.get("company_id", f"candidate_fixture_{index + 1}"))
        _validate_id(company_id, "candidate fixture company_id")
        documents_data = fixture.get("documents")
        if not isinstance(documents_data, list) or not documents_data:
            raise ValidationError("fixture requires point-in-time documents")
        documents: list[RawInfoDocument] = []
        for document_index, raw_document in enumerate(documents_data):
            if not isinstance(raw_document, Mapping):
                raise ValidationError("fixture document must be an object")
            published_at = datetime.fromisoformat(
                str(raw_document.get("published_at", as_of.isoformat()))
            )
            available_at = datetime.fromisoformat(
                str(raw_document.get("available_at", published_at.isoformat()))
            )
            source_type = str(raw_document["source_type"])
            if source_type not in spec.source_types:
                raise ValidationError("fixture source_type is outside candidate retrieval")
            documents.append(
                RawInfoDocument.create(
                    document_id=str(
                        raw_document.get(
                            "document_id",
                            f"candidate_fixture_{index + 1}_{document_index + 1}",
                        )
                    ),
                    company_id=company_id,
                    source_type=source_type,
                    published_at=published_at,
                    available_at=available_at,
                    content=str(raw_document["content"]),
                    metadata=dict(raw_document.get("metadata", {})),
                )
            )
        snapshot_payload = {
            "spec": spec.to_dict(),
            "skill": (skill or "").rstrip(),
        }
        snapshot_hash = hashlib.sha256(
            json.dumps(snapshot_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        executor = SignalExecutor(
            FrozenSignalRegistry(
                version=0,
                registry_hash=snapshot_hash,
                specs=(spec,),
                skills=({spec.ref: skill} if skill is not None else {}),
            ),
            RawInfoStore(documents=documents),
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_runner,
        )
        result = executor.execute_batch(
            (spec.ref,), company_id=company_id, as_of=as_of
        ).results[0]
        if result.value is not expected:
            raise ValidationError(
                f"expected {expected.value}, received {result.value.value}"
            )


@dataclass(frozen=True)
class SignalMiningConfig:
    """Bounded local orchestration limits for the two Mining tracks."""

    hypothesis_limit: int = 3
    selected_hypothesis_limit: int = 2
    case_pool_limit: int = 32
    ranking_case_limit: int = 12
    h2_profile_scan_limit: int = 96
    h2_min_ready_issuers: int = 16
    h2_min_ready_per_class: int = 4
    induction_cases_per_class: int = 2
    validation_cases_per_class: int = 2
    exploration_interval: int = 3
    evidence_documents_per_case: int = 4
    evidence_lookback_days: int = 365
    exploration_microbatch_size: int = 4

    def __post_init__(self) -> None:
        positive_fields = (
            "hypothesis_limit",
            "selected_hypothesis_limit",
            "case_pool_limit",
            "ranking_case_limit",
            "h2_profile_scan_limit",
            "h2_min_ready_issuers",
            "h2_min_ready_per_class",
            "induction_cases_per_class",
            "validation_cases_per_class",
            "exploration_interval",
            "evidence_documents_per_case",
            "evidence_lookback_days",
            "exploration_microbatch_size",
        )
        if any(getattr(self, name) < 1 for name in positive_fields):
            raise ValidationError("Signal Mining limits must be positive")
        if self.selected_hypothesis_limit > self.hypothesis_limit:
            raise ValidationError(
                "selected Signal Mining hypotheses cannot exceed the portfolio limit"
            )
        if self.h2_profile_scan_limit < self.case_pool_limit:
            raise ValidationError("H2 profile scan limit must cover the target pool")
        if self.h2_min_ready_issuers > self.case_pool_limit:
            raise ValidationError("H2 minimum ready issuers exceeds the target pool")
        if self.evidence_documents_per_case > 10:
            raise ValidationError(
                "Signal Mining evidence_documents_per_case cannot exceed 10"
            )

    def to_dict(self) -> dict[str, int]:
        return {
            "hypothesis_limit": self.hypothesis_limit,
            "selected_hypothesis_limit": self.selected_hypothesis_limit,
            "case_pool_limit": self.case_pool_limit,
            "ranking_case_limit": self.ranking_case_limit,
            "h2_profile_scan_limit": self.h2_profile_scan_limit,
            "h2_min_ready_issuers": self.h2_min_ready_issuers,
            "h2_min_ready_per_class": self.h2_min_ready_per_class,
            "induction_cases_per_class": self.induction_cases_per_class,
            "validation_cases_per_class": self.validation_cases_per_class,
            "exploration_interval": self.exploration_interval,
            "evidence_documents_per_case": self.evidence_documents_per_case,
            "evidence_lookback_days": self.evidence_lookback_days,
            "exploration_microbatch_size": self.exploration_microbatch_size,
        }


@dataclass(frozen=True)
class SignalMiningHypothesis:
    """One falsifiable, company-agnostic Signal Mining hypothesis."""

    hypothesis_id: str
    statement: str
    applicability: str
    expected_positive_pattern: str
    source_types: tuple[str, ...]
    query: str
    falsifiers: tuple[str, ...]
    lookback_days: int = 365
    measurement: Mapping[str, str] | None = None
    expected_direction: str | None = None
    comparison: str = "fixed_discovery_positive_vs_control"

    def __post_init__(self) -> None:
        _validate_id(self.hypothesis_id, "mining hypothesis_id")
        text_fields = (
            self.statement,
            self.applicability,
            self.expected_positive_pattern,
            self.query,
        )
        if any(not value.strip() for value in text_fields):
            raise ValidationError("Signal Mining hypothesis text cannot be empty")
        if not self.source_types or any(not item.strip() for item in self.source_types):
            raise ValidationError("Signal Mining hypothesis requires source_types")
        if len(set(self.source_types)) != len(self.source_types):
            raise ValidationError("Signal Mining hypothesis source_types must be unique")
        if not self.falsifiers or any(not item.strip() for item in self.falsifiers):
            raise ValidationError("Signal Mining hypothesis requires falsifiers")
        if self.lookback_days < 1 or self.lookback_days > 1825:
            raise ValidationError("Signal Mining lookback_days must be in [1, 1825]")
        if self.measurement is not None:
            required_measurement = {"observable", "value_kind", "normalization"}
            if set(self.measurement) != required_measurement or any(
                not str(self.measurement[key]).strip() for key in required_measurement
            ):
                raise ValidationError(
                    "Signal Mining measurement requires observable, value_kind, and "
                    "normalization"
                )
        if self.expected_direction is not None and self.expected_direction not in {
            "higher_in_positive",
            "lower_in_positive",
            "more_frequent_in_positive",
            "less_frequent_in_positive",
            "different_between_groups",
        }:
            raise ValidationError("Signal Mining expected_direction is invalid")
        if self.comparison != "fixed_discovery_positive_vs_control":
            raise ValidationError("Signal Mining comparison must use fixed groups")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "applicability": self.applicability,
            "expected_positive_pattern": self.expected_positive_pattern,
            "source_types": list(self.source_types),
            "query": self.query,
            "falsifiers": list(self.falsifiers),
            "lookback_days": self.lookback_days,
        }
        if self.measurement is not None:
            result.update(
                {
                    "measurement": dict(self.measurement),
                    "expected_direction": self.expected_direction,
                    "comparison": self.comparison,
                }
            )
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningHypothesis":
        required = {
            "hypothesis_id",
            "statement",
            "applicability",
            "expected_positive_pattern",
            "source_types",
            "query",
            "falsifiers",
            "lookback_days",
        }
        structured = {"measurement", "expected_direction", "comparison"}
        if frozenset(data) not in {
            frozenset(required),
            frozenset(required | structured),
        }:
            raise ValidationError(
                "Signal Mining hypothesis requires exactly: "
                + ", ".join(sorted(required))
                + " with optional structured v2 fields"
            )
        return cls(
            hypothesis_id=str(data["hypothesis_id"]),
            statement=str(data["statement"]),
            applicability=str(data["applicability"]),
            expected_positive_pattern=str(data["expected_positive_pattern"]),
            source_types=_json_string_array(data, "source_types"),
            query=str(data["query"]),
            falsifiers=_json_string_array(data, "falsifiers"),
            lookback_days=int(data["lookback_days"]),
            measurement=(
                {str(key): str(value) for key, value in data["measurement"].items()}
                if isinstance(data.get("measurement"), Mapping)
                else None
            ),
            expected_direction=(
                str(data["expected_direction"])
                if data.get("expected_direction") is not None
                else None
            ),
            comparison=str(
                data.get("comparison", "fixed_discovery_positive_vs_control")
            ),
        )


@dataclass(frozen=True)
class SignalMiningDecision:
    """A label-revealed contrast decision with an optional complete draft."""

    hypothesis_id: str
    disposition: str
    rationale: tuple[str, ...]
    candidate: Mapping[str, Any] | None = None
    sample_basis: Mapping[str, tuple[str, ...]] | None = None

    def __post_init__(self) -> None:
        _validate_id(self.hypothesis_id, "mining decision hypothesis_id")
        if self.disposition not in {
            "supported",
            "refine",
            "rejected",
            "inconclusive",
        }:
            raise ValidationError(
                "Mining disposition must be supported, refine, rejected, or inconclusive"
            )
        if not self.rationale or any(not item.strip() for item in self.rationale):
            raise ValidationError("Mining decision requires rationale")
        if self.disposition == "supported" and not isinstance(self.candidate, Mapping):
            raise ValidationError("supported Mining decision requires a candidate")
        if self.disposition != "supported" and self.candidate is not None:
            raise ValidationError("only a supported Mining decision may carry a candidate")
        if self.candidate is not None:
            object.__setattr__(self, "candidate", dict(self.candidate))
        if self.sample_basis is not None:
            required_basis = {"positive_refs", "control_refs"}
            if set(self.sample_basis) != required_basis:
                raise ValidationError(
                    "Mining sample_basis requires positive_refs and control_refs"
                )
            normalized_basis: dict[str, tuple[str, ...]] = {}
            for key in sorted(required_basis):
                raw_refs = self.sample_basis[key]
                if not isinstance(raw_refs, (list, tuple)) or any(
                    not isinstance(item, str) for item in raw_refs
                ):
                    raise ValidationError(
                        "Mining sample_basis values must be string arrays"
                    )
                normalized_basis[key] = tuple(raw_refs)
            if any(
                not refs or any(not ref for ref in refs) or len(set(refs)) != len(refs)
                for refs in normalized_basis.values()
            ) or set(normalized_basis["positive_refs"]) & set(
                normalized_basis["control_refs"]
            ):
                raise ValidationError(
                    "Mining sample_basis requires non-empty, unique, disjoint refs"
                )
            object.__setattr__(self, "sample_basis", normalized_basis)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "hypothesis_id": self.hypothesis_id,
            "disposition": self.disposition,
            "rationale": list(self.rationale),
            "candidate": (dict(self.candidate) if self.candidate is not None else None),
        }
        if self.sample_basis is not None:
            result["sample_basis"] = {
                key: list(refs) for key, refs in self.sample_basis.items()
            }
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningDecision":
        required = {"hypothesis_id", "disposition", "rationale", "candidate"}
        if set(data) not in (required, required | {"sample_basis"}):
            raise ValidationError(
                "Signal Mining decision requires exactly: "
                + ", ".join(sorted(required))
            )
        raw_candidate = data["candidate"]
        if raw_candidate is not None and not isinstance(raw_candidate, Mapping):
            raise ValidationError("Mining candidate must be an object or null")
        raw_sample_basis = data.get("sample_basis")
        if "sample_basis" in data and not isinstance(raw_sample_basis, Mapping):
            raise ValidationError("Mining sample_basis must be an object")
        parsed_sample_basis: dict[str, tuple[str, ...]] | None = None
        if isinstance(raw_sample_basis, Mapping):
            parsed_sample_basis = {}
            for key, value in raw_sample_basis.items():
                if not isinstance(value, list) or any(
                    not isinstance(item, str) for item in value
                ):
                    raise ValidationError(
                        "Mining sample_basis values must be string arrays"
                    )
                parsed_sample_basis[str(key)] = tuple(value)
        return cls(
            hypothesis_id=str(data["hypothesis_id"]),
            disposition=str(data["disposition"]),
            rationale=_json_string_array(data, "rationale"),
            candidate=(dict(raw_candidate) if raw_candidate is not None else None),
            sample_basis=parsed_sample_basis,
        )


@dataclass(frozen=True)
class SignalMiningObservation:
    """One locally verifiable observation over a model-visible evidence span."""

    summary: str
    document_ref: str
    exact_span: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.summary, str)
            or not self.summary.strip()
            or len(self.summary) > 500
        ):
            raise ValidationError(
                "Mining observation summary must contain 1-500 characters"
            )
        _validate_id(self.document_ref, "mining observation document_ref")
        if not 8 <= len(self.exact_span) <= 240:
            raise ValidationError(
                "Mining observation exact_span must contain 8-240 characters"
            )
        visible_tokens = re.findall(
            r"[A-Za-z0-9]+", self.exact_span.replace(_MASKED_IDENTITY_VALUE, "")
        )
        if len(visible_tokens) < 2:
            raise ValidationError(
                "Mining observation exact_span must contain at least two visible tokens"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "summary": self.summary,
            "document_ref": self.document_ref,
            "exact_span": self.exact_span,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningObservation":
        required = {"summary", "document_ref", "exact_span"}
        if set(data) != required:
            raise ValidationError(
                "Mining observation requires exactly: "
                + ", ".join(sorted(required))
            )
        return cls(
            summary=str(data["summary"]),
            document_ref=str(data["document_ref"]),
            exact_span=str(data["exact_span"]),
        )


@dataclass(frozen=True)
class SignalMiningSignature:
    """One outcome-hidden observable signature extracted from Raw Info."""

    case_ref: str
    observations: tuple[SignalMiningObservation, ...]
    evidence_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_id(self.case_ref, "mining signature case_ref")
        if any(
            not isinstance(item, SignalMiningObservation)
            for item in self.observations
        ):
            raise ValidationError("Mining signature observations must be objects")
        if len(self.observations) > 6:
            raise ValidationError("Mining signature allows at most six observations")
        if not self.observations and not self.evidence_gaps:
            raise ValidationError(
                "Mining signature without observations requires an evidence gap"
            )
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.evidence_gaps
        ):
            raise ValidationError("Mining signature evidence gaps must be non-empty")
        identities = [
            (item.document_ref, item.exact_span) for item in self.observations
        ]
        if len(set(identities)) != len(identities):
            raise ValidationError("Mining signature observations must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_ref": self.case_ref,
            "observations": [item.to_dict() for item in self.observations],
            "evidence_gaps": list(self.evidence_gaps),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningSignature":
        required = {"case_ref", "observations", "evidence_gaps"}
        if set(data) != required:
            raise ValidationError(
                "Signal Mining signature requires exactly: "
                + ", ".join(sorted(required))
            )
        observations: list[SignalMiningObservation] = []
        for item in _json_array(data, "observations"):
            if not isinstance(item, Mapping):
                raise ValidationError("Mining observation must be an object")
            observations.append(SignalMiningObservation.from_dict(item))
        return cls(
            case_ref=str(data["case_ref"]),
            observations=tuple(observations),
            evidence_gaps=_json_string_array(data, "evidence_gaps", required=False),
        )


def validate_signal_mining_signatures(
    signatures: Iterable[SignalMiningSignature],
    evidence_packets: Iterable[Mapping[str, Any]],
) -> tuple[SignalMiningSignature, ...]:
    """Bind every E1 observation to one exact supplied model-visible literal."""

    values = tuple(signatures)
    packets = tuple(evidence_packets)
    packet_by_ref: dict[str, Mapping[str, Any]] = {}
    for packet_index, packet in enumerate(packets):
        if not isinstance(packet, Mapping):
            raise ValidationError(
                f"exploration evidence packet must be an object at cases[{packet_index}]"
            )
        case_ref = packet.get("case_ref")
        if not isinstance(case_ref, str) or not case_ref:
            raise ValidationError(
                "exploration evidence packets require non-empty case_ref values"
            )
        _validate_id(case_ref, "exploration evidence case_ref")
        if case_ref in packet_by_ref:
            raise ValidationError(
                "exploration evidence packets require unique case_ref values"
            )
        packet_by_ref[case_ref] = packet
    expected_refs = set(packet_by_ref)
    actual_refs = [item.case_ref for item in values]
    if len(set(actual_refs)) != len(actual_refs) or set(actual_refs) != expected_refs:
        raise ValidationError(
            "exploration extraction must return one signature per supplied case_ref"
        )
    for signature_index, signature in enumerate(values):
        packet = packet_by_ref[signature.case_ref]
        evidence = packet.get("evidence", ())
        if not isinstance(evidence, (list, tuple)):
            raise ValidationError(
                "exploration evidence must be an array at "
                f"cases[{signature_index}].evidence"
            )
        documents: dict[str, tuple[str, ...]] = {}
        for evidence_index, item in enumerate(evidence):
            item_path = f"cases[{signature_index}].evidence[{evidence_index}]"
            if not isinstance(item, Mapping):
                raise ValidationError(
                    f"exploration evidence item must be an object at {item_path}"
                )
            document_ref = item.get("document_ref")
            content_excerpt = item.get("content_excerpt")
            if not isinstance(document_ref, str) or not document_ref:
                raise ValidationError(
                    f"exploration evidence requires document_ref at {item_path}"
                )
            _validate_id(document_ref, "exploration evidence document_ref")
            if not isinstance(content_excerpt, str):
                raise ValidationError(
                    f"exploration evidence requires content_excerpt at {item_path}"
                )
            if document_ref in documents:
                raise ValidationError(
                    f"exploration evidence document_ref must be unique at {item_path}"
                )
            allowed_spans = [content_excerpt] if content_excerpt else []
            structured = item.get("structured_context")
            if isinstance(structured, Mapping):
                for concept in structured.get("concepts", ()):
                    if not isinstance(concept, Mapping):
                        continue
                    for record in concept.get("records", ()):
                        if not isinstance(record, Mapping):
                            continue
                        exact_span = record.get("exact_span")
                        start = record.get("start")
                        end = record.get("end")
                        if (
                            isinstance(exact_span, str)
                            and exact_span
                            and type(start) is int
                            and type(end) is int
                            and 0 <= start < end
                        ):
                            allowed_spans.append(exact_span)
            documents[document_ref] = tuple(allowed_spans)
        if signature.observations and not documents:
            raise ValidationError(
                "Mining signature cannot observe an evidence-empty packet at "
                f"signatures[{signature_index}].observations"
            )
        for observation_index, observation in enumerate(signature.observations):
            path = (
                f"signatures[{signature_index}].observations[{observation_index}]"
            )
            allowed_spans = documents.get(observation.document_ref)
            if allowed_spans is None:
                raise ValidationError(
                    f"Mining observation uses an unknown document_ref at {path}.document_ref"
                )
            if not any(
                observation.exact_span in exact_span
                for exact_span in allowed_spans
            ):
                raise ValidationError(
                    "Mining observation exact_span is not a supplied literal "
                    "contained within one "
                    f"supplied record literal at {path}.exact_span"
                )
    return values


class SignalMiningModel(Protocol):
    """Four narrow structured roles used by the local Mining controller."""

    def propose_hypotheses(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningHypothesis, ...]]:
        """Return a bounded hypothesis portfolio."""

    def contrast(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningDecision, ...]]:
        """Contrast exact positive/control evidence."""

    def extract_exploration(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningSignature, ...]]:
        """Extract outcome-hidden case signatures."""

    def discover_exploration(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningDecision, ...]]:
        """Discover label-associated candidates from frozen signatures."""


@dataclass(frozen=True)
class SignalUpdateDecision:
    """One semantic decision for an exact locally selected stable Signal."""

    signal_ref: str
    disposition: str
    problem_type: str
    rationale: tuple[str, ...]
    candidate: Mapping[str, Any] | None = None
    case_diagnostics: tuple[Mapping[str, Any], ...] = ()
    changed_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if re.fullmatch(
            r"[a-z0-9][a-z0-9_.:-]*:v[1-9][0-9]*", self.signal_ref
        ) is None:
            raise ValidationError("Signal Update signal_ref is invalid")
        if self.disposition not in {"no_change", "defer", "update"}:
            raise ValidationError(
                "Signal Update disposition must be no_change, defer, or update"
            )
        if not self.problem_type.strip():
            raise ValidationError("Signal Update problem_type must not be empty")
        if not self.rationale or any(not item.strip() for item in self.rationale):
            raise ValidationError("Signal Update requires non-empty rationale")
        if self.disposition == "update" and not isinstance(self.candidate, Mapping):
            raise ValidationError("Signal Update disposition update requires candidate")
        if self.disposition != "update" and self.candidate is not None:
            raise ValidationError(
                "only Signal Update disposition update may carry candidate"
            )
        changed_paths = tuple(str(item) for item in self.changed_paths)
        if any(not item.strip() for item in changed_paths) or len(
            set(changed_paths)
        ) != len(changed_paths):
            raise ValidationError(
                "Signal Update changed_paths must be unique non-empty strings"
            )
        if self.disposition != "update" and changed_paths:
            raise ValidationError("only Signal Update disposition update may change paths")
        if self.candidate is not None:
            object.__setattr__(self, "candidate", dict(self.candidate))
        object.__setattr__(
            self,
            "case_diagnostics",
            tuple(dict(item) for item in self.case_diagnostics),
        )
        object.__setattr__(self, "changed_paths", changed_paths)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "signal_ref": self.signal_ref,
            "disposition": self.disposition,
            "problem_type": self.problem_type,
            "rationale": list(self.rationale),
            "changed_paths": list(self.changed_paths),
            "candidate": dict(self.candidate) if self.candidate is not None else None,
        }
        if self.case_diagnostics:
            result["case_diagnostics"] = [
                dict(item) for item in self.case_diagnostics
            ]
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalUpdateDecision":
        required = {
            "signal_ref",
            "disposition",
            "problem_type",
            "rationale",
            "candidate",
        }
        optional = {"case_diagnostics", "changed_paths"}
        if not required.issubset(data) or set(data) - required - optional:
            raise ValidationError(
                "Signal Update decision requires exactly: "
                + ", ".join(sorted(required))
            )
        candidate = data["candidate"]
        if candidate is not None and not isinstance(candidate, Mapping):
            raise ValidationError("Signal Update candidate must be object or null")
        return cls(
            signal_ref=str(data["signal_ref"]),
            disposition=str(data["disposition"]),
            problem_type=str(data["problem_type"]),
            rationale=_json_string_array(data, "rationale"),
            changed_paths=tuple(
                str(item) for item in data.get("changed_paths", ())
            ),
            candidate=dict(candidate) if candidate is not None else None,
            case_diagnostics=tuple(
                dict(item)
                for item in data.get("case_diagnostics", ())
                if isinstance(item, Mapping)
            ),
        )


class SignalUpdateModel(Protocol):
    """One bounded semantic Signal Update role behind local data boundaries."""

    def update(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[SignalUpdateDecision]:
        """Return no_change, defer, or a complete vNext candidate."""


_SIGNAL_UPDATE_TARGET_LIMIT = 3


@dataclass(frozen=True)
class SignalCandidateEffectiveness:
    """Paired Signal-level evidence required after contract validation."""

    signal_ref: str
    current_ref: str | None
    accepted: bool
    disposition: str
    reasons: tuple[str, ...]
    case_ids: tuple[str, ...]
    candidate_available: int
    candidate_decisive: int
    candidate_correct: int
    candidate_wrong: int
    candidate_execution_failed: int = 0
    current_available: int = 0
    current_decisive: int = 0
    current_correct: int = 0
    current_wrong: int = 0
    current_execution_failed: int = 0

    def __post_init__(self) -> None:
        if self.disposition not in {"promoted", "provisional", "rejected"}:
            raise ValidationError("invalid Signal candidate effectiveness disposition")
        if self.accepted != (self.disposition == "promoted"):
            raise ValidationError(
                "accepted Signal effectiveness must match promoted disposition"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "signal-candidate-effectiveness-v3",
            "signal_ref": self.signal_ref,
            "current_ref": self.current_ref,
            "accepted": self.accepted,
            "disposition": self.disposition,
            "reasons": list(self.reasons),
            "case_ids": list(self.case_ids),
            "candidate": {
                "available": self.candidate_available,
                "decisive": self.candidate_decisive,
                "directional_correct": self.candidate_correct,
                "directional_wrong": self.candidate_wrong,
                "execution_failed": self.candidate_execution_failed,
            },
            "current": {
                "available": self.current_available,
                "decisive": self.current_decisive,
                "directional_correct": self.current_correct,
                "directional_wrong": self.current_wrong,
                "execution_failed": self.current_execution_failed,
            },
        }


class SignalCandidateEffectivenessEvaluator:
    """Compare candidate and stable Signal behavior on one frozen sample."""

    def __init__(
        self,
        registry: SignalRegistry,
        *,
        raw_info_store: RawInfoStore,
        discovery_cases: tuple[EvolutionCase, ...],
        llm_runner: LLMSignalRunner | None,
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        case_limit: int = 8,
        minimum_cases: int = 4,
    ) -> None:
        if case_limit < 1 or minimum_cases < 1 or minimum_cases > case_limit:
            raise ValidationError("Signal effectiveness case limits are invalid")
        self.registry = registry
        self.raw_info_store = raw_info_store
        self.discovery_cases = tuple(discovery_cases)
        self.llm_runner = llm_runner
        self.deterministic_functions = dict(deterministic_functions or {})
        self.case_limit = case_limit
        self.minimum_cases = minimum_cases

    def evaluate(
        self,
        spec: SignalSpec,
        *,
        skill: str | None,
        preferred_case_ids: Iterable[str] = (),
        excluded_case_ids: Iterable[str] = (),
        induction_supported: bool = False,
    ) -> SignalCandidateEffectiveness:
        cases = self._select_cases(
            preferred_case_ids=preferred_case_ids,
            excluded_case_ids=excluded_case_ids,
        )
        case_ids = tuple(case.case_id for case in cases)
        try:
            current = self.registry.latest_spec(spec.signal_id)
        except ValidationError:
            current = None
        if len(cases) < self.minimum_cases:
            return SignalCandidateEffectiveness(
                signal_ref=spec.ref,
                current_ref=(current.ref if current is not None else None),
                accepted=False,
                disposition=("provisional" if induction_supported else "rejected"),
                reasons=(
                    "paired effectiveness requires at least "
                    f"{self.minimum_cases} Discovery cases",
                ),
                case_ids=case_ids,
                candidate_available=0,
                candidate_decisive=0,
                candidate_correct=0,
                candidate_wrong=0,
            )

        frozen_store = RawInfoStore(documents=self.raw_info_store.documents)
        candidate_hash = hashlib.sha256(
            json.dumps(
                {"spec": spec.to_dict(), "skill": skill or ""},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        candidate_executor = SignalExecutor(
            FrozenSignalRegistry(
                version=0,
                registry_hash=candidate_hash,
                specs=(spec,),
                skills=({spec.ref: skill} if skill is not None else {}),
            ),
            frozen_store,
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_runner,
        )
        current_executor = (
            SignalExecutor(
                self.registry.freeze(),
                frozen_store,
                deterministic_functions=self.deterministic_functions,
                llm_runner=self.llm_runner,
            )
            if current is not None
            else None
        )
        candidate_values: list[
            tuple[SignalValue, bool, SignalExecutionStatus]
        ] = []
        current_values: list[
            tuple[SignalValue, bool, SignalExecutionStatus]
        ] = []
        try:
            for case in cases:
                candidate_result = candidate_executor.execute_batch(
                    (spec.ref,),
                    company_id=case.company_id,
                    as_of=case.prediction_time,
                    identity=case.basic_info,
                ).results[0]
                candidate_values.append(
                    (
                        candidate_result.value,
                        case.ground_truth.is_surge,
                        candidate_result.execution_status,
                    )
                )
                if current is not None and current_executor is not None:
                    current_result = current_executor.execute_batch(
                        (current.ref,),
                        company_id=case.company_id,
                        as_of=case.prediction_time,
                        identity=case.basic_info,
                    ).results[0]
                    current_values.append(
                        (
                            current_result.value,
                            case.ground_truth.is_surge,
                            current_result.execution_status,
                        )
                    )
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            return SignalCandidateEffectiveness(
                signal_ref=spec.ref,
                current_ref=(current.ref if current is not None else None),
                accepted=False,
                disposition="rejected",
                reasons=("paired effectiveness execution failed: " + str(exc),),
                case_ids=case_ids,
                candidate_available=0,
                candidate_decisive=0,
                candidate_correct=0,
                candidate_wrong=0,
            )

        candidate_counts = _signal_effectiveness_counts(candidate_values)
        current_counts = _signal_effectiveness_counts(current_values)
        insufficient_reasons: list[str] = []
        if candidate_counts[0] < self.minimum_cases:
            insufficient_reasons.append(
                "candidate availability is below paired minimum: "
                f"{candidate_counts[0]}/{self.minimum_cases}"
            )
        decisive_floor = min(2, self.minimum_cases)
        if candidate_counts[1] < decisive_floor:
            insufficient_reasons.append(
                "candidate decisive support is below paired minimum: "
                f"{candidate_counts[1]}/{decisive_floor}"
            )
        rejection_reasons: list[str] = []
        if current is None:
            if (
                candidate_counts[1] >= decisive_floor
                and candidate_counts[2] <= candidate_counts[3]
            ):
                rejection_reasons.append(
                    "new candidate lacks positive directional evidence over controls"
                )
        else:
            labels = (
                (0, "availability"),
                (2, "directional correct count"),
            )
            for index, label in labels:
                if candidate_counts[index] < current_counts[index]:
                    rejection_reasons.append(f"candidate reduces {label}")
            if candidate_counts[3] > current_counts[3]:
                rejection_reasons.append("candidate increases directional wrong count")
            if not insufficient_reasons and not (
                candidate_counts[0] > current_counts[0]
                or candidate_counts[2] > current_counts[2]
                or candidate_counts[3] < current_counts[3]
            ):
                rejection_reasons.append(
                    "candidate shows no strict paired effectiveness gain"
                )
        if rejection_reasons:
            disposition = "rejected"
            reasons = rejection_reasons + insufficient_reasons
        elif insufficient_reasons:
            disposition = "provisional" if induction_supported else "rejected"
            reasons = insufficient_reasons
        else:
            disposition = "promoted"
            reasons = []
        return SignalCandidateEffectiveness(
            signal_ref=spec.ref,
            current_ref=(current.ref if current is not None else None),
            accepted=disposition == "promoted",
            disposition=disposition,
            reasons=tuple(reasons),
            case_ids=case_ids,
            candidate_available=candidate_counts[0],
            candidate_decisive=candidate_counts[1],
            candidate_correct=candidate_counts[2],
            candidate_wrong=candidate_counts[3],
            candidate_execution_failed=candidate_counts[4],
            current_available=current_counts[0],
            current_decisive=current_counts[1],
            current_correct=current_counts[2],
            current_wrong=current_counts[3],
            current_execution_failed=current_counts[4],
        )

    def evaluation_identity(
        self,
        spec: SignalSpec,
        *,
        candidate_hash: str,
        preferred_case_ids: Iterable[str] = (),
        excluded_case_ids: Iterable[str] = (),
        induction_supported: bool = False,
    ) -> Mapping[str, str]:
        """Return the complete stable identity used to cache one paired gate."""

        preferred_ids = tuple(str(item) for item in preferred_case_ids)
        excluded_ids = tuple(str(item) for item in excluded_case_ids)
        cases = self._select_cases(
            preferred_case_ids=preferred_ids,
            excluded_case_ids=excluded_ids,
        )
        try:
            current = self.registry.latest_spec(spec.signal_id)
            baseline = {
                "spec": current.to_dict(),
                "skill": self.registry.load_skill(current.ref),
            }
        except ValidationError:
            baseline = {"spec": None, "skill": None}
        source_manifest = []
        for case in cases:
            documents = self.raw_info_store.search(
                case.company_id,
                as_of=case.prediction_time,
            )
            source_manifest.append(
                {
                    "case_id": case.case_id,
                    "company_id": case.company_id,
                    "prediction_time": case.prediction_time.isoformat(),
                    "documents": [
                        {
                            "document_id": document.document_id,
                            "content_hash": document.content_hash,
                            "source_type": document.source_type,
                            "available_at": document.available_at.isoformat(),
                        }
                        for document in documents
                    ],
                }
            )
        runner_identity: dict[str, Any] = {
            "type": (
                None
                if self.llm_runner is None
                else f"{type(self.llm_runner).__module__}."
                f"{type(self.llm_runner).__qualname__}"
            )
        }
        caller = getattr(self.llm_runner, "caller", None)
        registration = getattr(caller, "registration", None)
        if registration is not None and callable(
            getattr(registration, "to_public_dict", None)
        ):
            runner_identity["registration"] = registration.to_public_dict()
        contract = getattr(caller, "contract", None)
        if contract is not None and getattr(contract, "contract_hash", None):
            runner_identity["contract_hash"] = str(contract.contract_hash)
        return {
            "baseline_hash": _canonical_hash(baseline),
            "cohort_hash": _canonical_hash(
                {
                    "selected": [
                        {
                            "case_id": case.case_id,
                            "company_id": case.company_id,
                            "prediction_time": case.prediction_time.isoformat(),
                        }
                        for case in cases
                    ],
                    "excluded_case_ids": list(excluded_ids),
                    "induction_supported": induction_supported,
                }
            ),
            "source_manifest_hash": _canonical_hash(
                {"source_manifest": source_manifest}
            ),
            "projection_hash": _canonical_hash(
                {
                    "schema": "signal-paired-projection-v1",
                    "executor": "SignalExecutor",
                    "point_in_time": True,
                }
            ),
            "validator_hash": _canonical_hash(
                {
                    "contract": "signal-candidate-validation-v2",
                    "effectiveness": "signal-candidate-effectiveness-v3",
                    "minimum_cases": self.minimum_cases,
                    "case_limit": self.case_limit,
                    "functions": sorted(self.deterministic_functions),
                }
            ),
            "model_hash": _canonical_hash(runner_identity),
            "sampling_hash": _canonical_hash(
                {
                    "schema": "issuer-distinct-preferred-then-stratified-v1",
                    "preferred_case_ids": list(preferred_ids),
                    "selected_case_ids": [case.case_id for case in cases],
                }
            ),
        }

    def _select_cases(
        self,
        *,
        preferred_case_ids: Iterable[str],
        excluded_case_ids: Iterable[str],
    ) -> tuple[EvolutionCase, ...]:
        case_by_id = {case.case_id: case for case in self.discovery_cases}
        excluded_companies = {
            case_by_id[case_id].company_id
            for case_id in excluded_case_ids
            if case_id in case_by_id
        }
        eligible = tuple(
            case
            for case in self.discovery_cases
            if case.company_id not in excluded_companies
        )
        preferred: list[EvolutionCase] = []
        seen_companies: set[str] = set()
        for case_id in preferred_case_ids:
            case = case_by_id.get(str(case_id))
            if (
                case is None
                or case.company_id in excluded_companies
                or case.company_id in seen_companies
            ):
                continue
            preferred.append(case)
            seen_companies.add(case.company_id)
            if len(preferred) >= self.case_limit:
                break
        for case in _sample_signal_discovery_cases(eligible, limit=self.case_limit):
            if len(preferred) >= self.case_limit:
                break
            if case.company_id in seen_companies:
                continue
            preferred.append(case)
            seen_companies.add(case.company_id)
        return tuple(preferred)


def _signal_effectiveness_counts(
    values: Iterable[tuple[SignalValue, bool, SignalExecutionStatus]],
) -> tuple[int, int, int, int, int]:
    available = decisive = correct = wrong = execution_failed = 0
    for value, is_surge, execution_status in values:
        if execution_status not in {
            SignalExecutionStatus.SUCCESS,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        }:
            execution_failed += 1
            continue
        if value is not SignalValue.UNAVAILABLE:
            available += 1
        if value not in (SignalValue.POSITIVE, SignalValue.NEGATIVE):
            continue
        decisive += 1
        if (value is SignalValue.POSITIVE) == is_surge:
            correct += 1
        else:
            wrong += 1
    return available, decisive, correct, wrong, execution_failed


def _mining_needs_exploration_fallback(audit: Mapping[str, Any]) -> bool:
    """Return whether H1/H3 ended without a substantive semantic decision."""

    stages = audit.get("stages", {})
    if not isinstance(stages, Mapping):
        return True
    h1 = stages.get("H1", {})
    if not isinstance(h1, Mapping) or not h1.get("hypotheses"):
        return True
    h3 = stages.get("H3", {})
    if not isinstance(h3, Mapping):
        return True
    decisions = h3.get("decisions", ())
    return not decisions or all(
        isinstance(item, Mapping) and item.get("disposition") == "inconclusive"
        for item in decisions
    )


def _merge_mining_fallback(
    hypothesis: Mapping[str, Any], exploration: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge two independent Mining results without changing either audit."""

    def merged_mapping(key: str) -> dict[str, Any]:
        return {**dict(hypothesis.get(key, {})), **dict(exploration.get(key, {}))}

    return {
        "candidate_refs": tuple(
            (*hypothesis.get("candidate_refs", ()), *exploration.get("candidate_refs", ()))
        ),
        "induction_case_ids": merged_mapping("induction_case_ids"),
        "validation_case_ids": merged_mapping("validation_case_ids"),
        "refined_hypotheses": merged_mapping("refined_hypotheses"),
        "failures": merged_mapping("failures"),
        "audit": {
            "schema_version": "signal-mining-audit-v2",
            "status": (
                "completed_with_hypothesis_failure"
                if hypothesis["audit"].get("status") == "failed"
                else "completed"
            ),
            "track": "hypothesis_then_exploration_fallback",
            "hypothesis": dict(hypothesis["audit"]),
            "exploration": dict(exploration["audit"]),
            "candidate_refs": list(exploration.get("candidate_refs", ())),
        },
    }


@dataclass(frozen=True)
class SlowLoopValidation:
    """Durable Slow-loop decision staged before stable Registry mutation."""

    mined_candidates: tuple[str, ...]
    updated_candidates: tuple[str, ...]
    validated_candidates: Mapping[str, str]
    provisional_candidates: Mapping[str, tuple[str, ...]]
    rejected: Mapping[str, tuple[str, ...]]
    refined_hypotheses: Mapping[str, tuple[str, ...]]
    input_registry_version: int
    input_registry_hash: str
    input_signal_refs: tuple[str, ...]
    candidate_evaluations: Mapping[str, str] = field(default_factory=dict)
    candidate_effectiveness: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    agent_audits: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    search_input_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mined_candidates": list(self.mined_candidates),
            "updated_candidates": list(self.updated_candidates),
            "validated_candidates": dict(self.validated_candidates),
            "provisional_candidates": {
                ref: list(reasons)
                for ref, reasons in self.provisional_candidates.items()
            },
            "rejected": {
                ref: list(reasons) for ref, reasons in self.rejected.items()
            },
            "refined_hypotheses": {
                ref: list(reasons)
                for ref, reasons in self.refined_hypotheses.items()
            },
            "input_registry_version": self.input_registry_version,
            "input_registry_hash": self.input_registry_hash,
            "input_signal_refs": list(self.input_signal_refs),
            "candidate_evaluations": dict(self.candidate_evaluations),
            "candidate_effectiveness": {
                ref: dict(value)
                for ref, value in self.candidate_effectiveness.items()
            },
            "agent_audits": {
                name: dict(value) for name, value in self.agent_audits.items()
            },
            "search_input_fingerprint": self.search_input_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SlowLoopValidation":
        return cls(
            mined_candidates=tuple(
                str(item) for item in data.get("mined_candidates", ())
            ),
            updated_candidates=tuple(
                str(item) for item in data.get("updated_candidates", ())
            ),
            validated_candidates={
                str(ref): str(candidate_hash)
                for ref, candidate_hash in dict(
                    data.get("validated_candidates", {})
                ).items()
            },
            provisional_candidates={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(
                    data.get("provisional_candidates", {})
                ).items()
            },
            rejected={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("rejected", {})).items()
            },
            refined_hypotheses={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("refined_hypotheses", {})).items()
            },
            input_registry_version=int(data["input_registry_version"]),
            input_registry_hash=str(data["input_registry_hash"]),
            input_signal_refs=tuple(
                str(item) for item in data.get("input_signal_refs", ())
            ),
            candidate_evaluations={
                str(ref): str(evaluation_key)
                for ref, evaluation_key in dict(
                    data.get("candidate_evaluations", {})
                ).items()
            },
            candidate_effectiveness={
                str(ref): dict(value)
                for ref, value in dict(
                    data.get("candidate_effectiveness", {})
                ).items()
            },
            agent_audits={
                str(name): dict(value)
                for name, value in dict(data.get("agent_audits", {})).items()
            },
            search_input_fingerprint=str(
                data.get("search_input_fingerprint", "")
            ),
        )


@dataclass(frozen=True)
class SlowLoopResult:
    """Validated and automatically promoted Signal slow-loop outcome."""

    mined_candidates: tuple[str, ...]
    updated_candidates: tuple[str, ...]
    validated_candidates: Mapping[str, str]
    promoted: tuple[str, ...]
    provisional_candidates: Mapping[str, tuple[str, ...]]
    rejected: Mapping[str, tuple[str, ...]]
    refined_hypotheses: Mapping[str, tuple[str, ...]]
    input_registry_version: int
    input_registry_hash: str
    output_registry_version: int
    output_registry_hash: str
    candidate_evaluations: Mapping[str, str] = field(default_factory=dict)
    candidate_effectiveness: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    agent_audits: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    search_input_fingerprint: str = ""

    @property
    def registry_version(self) -> int:
        """Compatibility alias for the committed output Registry version."""

        return self.output_registry_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "mined_candidates": list(self.mined_candidates),
            "updated_candidates": list(self.updated_candidates),
            "validated_candidates": dict(self.validated_candidates),
            "promoted": list(self.promoted),
            "provisional_candidates": {
                ref: list(reasons)
                for ref, reasons in self.provisional_candidates.items()
            },
            "rejected": {
                ref: list(reasons) for ref, reasons in self.rejected.items()
            },
            "refined_hypotheses": {
                ref: list(reasons)
                for ref, reasons in self.refined_hypotheses.items()
            },
            "input_registry_version": self.input_registry_version,
            "input_registry_hash": self.input_registry_hash,
            "output_registry_version": self.output_registry_version,
            "output_registry_hash": self.output_registry_hash,
            "candidate_evaluations": dict(self.candidate_evaluations),
            "candidate_effectiveness": {
                ref: dict(value)
                for ref, value in self.candidate_effectiveness.items()
            },
            "agent_audits": {
                name: dict(value) for name, value in self.agent_audits.items()
            },
            "search_input_fingerprint": self.search_input_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SlowLoopResult":
        return cls(
            mined_candidates=tuple(
                str(item) for item in data.get("mined_candidates", ())
            ),
            updated_candidates=tuple(
                str(item) for item in data.get("updated_candidates", ())
            ),
            validated_candidates={
                str(ref): str(candidate_hash)
                for ref, candidate_hash in dict(
                    data.get(
                        "validated_candidates",
                        data.get("validated_pending_approval", {}),
                    )
                ).items()
            },
            promoted=tuple(str(item) for item in data.get("promoted", ())),
            provisional_candidates={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(
                    data.get("provisional_candidates", {})
                ).items()
            },
            rejected={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("rejected", {})).items()
            },
            refined_hypotheses={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("refined_hypotheses", {})).items()
            },
            input_registry_version=int(
                data.get("input_registry_version", data.get("registry_version", 0))
            ),
            input_registry_hash=str(data.get("input_registry_hash", "")),
            output_registry_version=int(
                data.get("output_registry_version", data.get("registry_version", 0))
            ),
            output_registry_hash=str(data.get("output_registry_hash", "")),
            candidate_evaluations={
                str(ref): str(evaluation_key)
                for ref, evaluation_key in dict(
                    data.get("candidate_evaluations", {})
                ).items()
            },
            candidate_effectiveness={
                str(ref): dict(value)
                for ref, value in dict(
                    data.get("candidate_effectiveness", {})
                ).items()
            },
            agent_audits={
                str(name): dict(value)
                for name, value in dict(data.get("agent_audits", {})).items()
            },
            search_input_fingerprint=str(
                data.get("search_input_fingerprint", "")
            ),
        )


def candidate_signal_spec_from_dict(spec: Mapping[str, Any]) -> SignalSpec:
    """Parse a candidate with the same strict evidence contract at every boundary."""

    evidence_policy = spec.get("evidence_policy")
    if not isinstance(evidence_policy, Mapping):
        raise ValidationError(
            "candidate SignalSpec evidence_policy must be an object"
        )
    required_policy = {
        "require_source",
        "require_timestamp",
        "require_exact_span",
    }
    if set(evidence_policy) != required_policy:
        raise ValidationError(
            "candidate SignalSpec evidence_policy requires source, timestamp, "
            "and exact-span fields"
        )
    try:
        return SignalSpec.from_dict(dict(spec))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(
            f"candidate SignalSpec JSON is invalid: {type(exc).__name__}: {exc}"
        ) from exc


def validate_signal_update_candidate(
    signal_ref: str,
    candidate: Mapping[str, Any],
    stable: SignalSpec,
    *,
    stable_skill: str | None = None,
    changed_paths: Iterable[str] | None = None,
) -> tuple[SignalSpec, str | None, list[Any]]:
    """Validate and baseline-overlay an update without mutating the Registry."""

    if set(candidate) not in (
        {"signal_ref", "spec", "tests"},
        {"signal_ref", "spec", "skill", "tests"},
    ):
        raise ValidationError(
            "Signal Update candidate requires signal_ref, spec, tests and optional skill"
        )
    if str(candidate["signal_ref"]) != signal_ref:
        raise ValidationError("Signal Update candidate changed target signal_ref")
    raw_spec = candidate["spec"]
    raw_tests = candidate["tests"]
    if not isinstance(raw_spec, Mapping) or not isinstance(raw_tests, list):
        raise ValidationError("Signal Update candidate spec/tests shape is invalid")
    candidate_spec = dict(raw_spec)
    candidate_retrieval = candidate_spec.get("raw_retrieval")
    if not isinstance(candidate_retrieval, Mapping):
        raise ValidationError("Signal Update candidate raw_retrieval must be an object")
    retrieval = dict(stable.to_dict()["raw_retrieval"])
    retrieval.update(dict(candidate_retrieval))
    candidate_spec["raw_retrieval"] = retrieval
    updated = candidate_signal_spec_from_dict(candidate_spec)
    if updated.signal_id != stable.signal_id or updated.version != stable.version + 1:
        raise ValidationError("Signal Update candidate must preserve id and use vNext")
    if updated.category != stable.category:
        raise ValidationError("Signal Update candidate must preserve category")
    if updated.description != stable.description:
        raise ValidationError("Signal Update candidate must preserve description")
    if updated.execution_type is not stable.execution_type:
        raise ValidationError("Signal Update candidate must preserve execution type")
    if updated.evidence_policy != stable.evidence_policy:
        raise ValidationError("Signal Update candidate must preserve evidence policy")
    if (
        stable.execution_type is SignalExecutionType.DETERMINISTIC
        and updated.function != stable.function
    ):
        raise ValidationError(
            "Signal Update deterministic candidate must preserve function"
        )
    skill_value = candidate.get("skill", stable_skill)
    if skill_value is not None and not isinstance(skill_value, str):
        raise ValidationError("Signal Update skill must be string or null")
    if updated.execution_type is SignalExecutionType.DETERMINISTIC and (
        skill_value is not None
    ):
        raise ValidationError("deterministic Signal Update skill must be null")
    if updated.execution_type is SignalExecutionType.LLM and not (
        isinstance(skill_value, str) and skill_value.strip()
    ):
        raise ValidationError("LLM Signal Update requires a complete skill")

    stable_dict = stable.to_dict()
    updated_dict = updated.to_dict()
    retrieval_fields = tuple(
        path.removeprefix("spec.raw_retrieval.")
        for path in SIGNAL_UPDATE_MUTABLE_PATHS
        if path.startswith("spec.raw_retrieval.")
    )
    actual_paths = {
        f"spec.raw_retrieval.{name}"
        for name in retrieval_fields
        if stable_dict["raw_retrieval"].get(name)
        != updated_dict["raw_retrieval"].get(name)
    }
    if stable_dict["parameters"] != updated_dict["parameters"]:
        actual_paths.add("spec.parameters")
    if stable_dict["execution"].get("skill_file") != updated_dict[
        "execution"
    ].get("skill_file"):
        actual_paths.add("spec.execution.skill_file")
    if stable_skill != skill_value:
        actual_paths.add("skill")
    if not actual_paths:
        raise ValidationError(
            "Signal Update candidate has no effective change; use no_change"
        )
    if changed_paths is not None:
        declared = tuple(str(item) for item in changed_paths)
        allowed_paths = set(SIGNAL_UPDATE_MUTABLE_PATHS)
        unknown = sorted(set(declared) - allowed_paths)
        if unknown:
            raise ValidationError(
                "Signal Update changed_paths contains unknown path: "
                + ", ".join(unknown)
            )
        if len(set(declared)) != len(declared):
            raise ValidationError("Signal Update changed_paths must be unique")
        missing = sorted(actual_paths - set(declared))
        surplus = sorted(set(declared) - actual_paths)
        if missing or surplus:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if surplus:
                details.append("surplus " + ", ".join(surplus))
            raise ValidationError(
                "Signal Update changed_paths does not match effective diff: "
                + "; ".join(details)
            )
    return updated, skill_value, raw_tests


class SignalEvolutionEngine:
    """Locally orchestrated Signal Mining and one-call Signal Update."""

    def __init__(
        self,
        *,
        registry: SignalRegistry,
        raw_info_store: RawInfoStore,
        discovery_cases: tuple[EvolutionCase, ...],
        meta_memory: PlanMetaMemory,
        workspace: EvolutionWorkspace,
        mining_model: SignalMiningModel,
        update_model: SignalUpdateModel,
        llm_signal_runner: LLMSignalRunner | None,
        evidence_resolver: EvidenceResolver | None = None,
        priors: EvolutionPriors = DEFAULT_EVOLUTION_PRIORS,
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        effectiveness_case_limit: int = 8,
        effectiveness_minimum_cases: int = 4,
        mining_config: SignalMiningConfig = SignalMiningConfig(),
    ) -> None:
        if not discovery_cases:
            raise ValidationError("Signal evolution requires label-visible Discovery cases")
        self.registry = registry
        self.raw_info_store = raw_info_store
        self.discovery_cases = discovery_cases
        self.meta_memory = meta_memory
        self.workspace = workspace
        self.mining_model = mining_model
        self.update_model = update_model
        discovery_aliases = _slow_role_identity_guard_inventory(discovery_cases)
        self.slow_role_identity_guards = discovery_aliases
        for role in (self.mining_model, self.update_model):
            setter = getattr(role, "set_identity_guard_aliases", None)
            if callable(setter):
                setter(discovery_aliases)
        self.llm_signal_runner = llm_signal_runner
        self.evidence_resolver = evidence_resolver or EvidenceResolver(raw_info_store)
        self.priors = priors
        self.mining_config = mining_config
        self.validator = SignalCandidateValidator(
            registry,
            llm_runner=llm_signal_runner,
            deterministic_functions=deterministic_functions,
            forbidden_identity_terms=_discovery_identity_terms(discovery_cases),
        )
        self.effectiveness_evaluator = SignalCandidateEffectivenessEvaluator(
            registry,
            raw_info_store=raw_info_store,
            discovery_cases=discovery_cases,
            llm_runner=llm_signal_runner,
            deterministic_functions=deterministic_functions,
            case_limit=effectiveness_case_limit,
            minimum_cases=effectiveness_minimum_cases,
        )

    @staticmethod
    def _role_work_identity(role: Any) -> Any:
        identity = getattr(role, "work_identity", None)
        if isinstance(identity, Mapping):
            return dict(identity)
        return f"{type(role).__module__}.{type(role).__qualname__}"

    def _search_input_fingerprint(
        self, input_snapshot: FrozenSignalRegistry
    ) -> str:
        """Hash the committed inputs that can change Slow candidate search."""

        relevant_documents = self._relevant_search_documents()
        backlog_path = self.workspace.root / "capability_backlog.json"
        backlog = _read_json(backlog_path) if backlog_path.exists() else {}

        return _canonical_hash(
            {
                "schema_version": "slow-search-input-v1",
                "input_registry_hash": input_snapshot.registry_hash,
                "discovery_cases": [
                    {
                        "case_id": case.case_id,
                        "company_id": case.company_id,
                        "prediction_time": case.prediction_time.isoformat(),
                    }
                    for case in self.discovery_cases
                ],
                "relevant_raw_info": relevant_documents,
                "capability_backlog": backlog,
                "meta_info": list(self.meta_memory.model_view()),
                "mining_config": self.mining_config.to_dict(),
                "mining_model": self._role_work_identity(self.mining_model),
                "update_model": self._role_work_identity(self.update_model),
            }
        )

    def _relevant_search_documents(self) -> list[dict[str, Any]]:
        """Return exact PIT Raw Info identities relevant to Discovery cases."""

        cutoff_by_company: dict[str, datetime] = {}
        for case in self.discovery_cases:
            prior = cutoff_by_company.get(case.company_id)
            if prior is None or case.prediction_time > prior:
                cutoff_by_company[case.company_id] = case.prediction_time
        return sorted(
            (
                {
                    "document_id": document.document_id,
                    "content_hash": document.content_hash,
                    "company_id": document.company_id,
                    "source_type": document.source_type,
                    "available_at": document.available_at.isoformat(),
                }
                for document in self.raw_info_store.documents
                if document.company_id in cutoff_by_company
                and document.available_at <= cutoff_by_company[document.company_id]
            ),
            key=lambda item: (
                item["company_id"],
                item["available_at"],
                item["document_id"],
            ),
        )

    def _hypothesis_work_fingerprint(
        self,
        hypothesis: SignalMiningHypothesis,
        *,
        packets: Iterable[Mapping[str, Any]],
        validation_refs: Iterable[str],
        case_by_ref: Mapping[str, EvolutionCase],
    ) -> str:
        """Hash one H3 comparison without its cycle-owned proposal id."""

        hypothesis_definition = hypothesis.to_dict()
        hypothesis_definition.pop("hypothesis_id", None)
        validation_cases = [
            {
                "case_id": case_by_ref[case_ref].case_id,
                "company_id": case_by_ref[case_ref].company_id,
                "prediction_time": case_by_ref[case_ref].prediction_time.isoformat(),
            }
            for case_ref in validation_refs
        ]
        return _canonical_hash(
            {
                "schema_version": "signal-mining-h3-work-v1",
                "hypothesis": hypothesis_definition,
                "induction_packets": [dict(packet) for packet in packets],
                "validation_cases": validation_cases,
                "input_registry_hash": self.registry.freeze().registry_hash,
                "mining_config": self.mining_config.to_dict(),
                "mining_model": self._role_work_identity(self.mining_model),
                "projection_protocol": "signal-mining-h3-evidence-v2",
            }
        )

    def _prior_terminal_hypothesis_work(self) -> dict[str, Mapping[str, Any]]:
        """Load exact committed H3 work that must not be retried unchanged."""

        terminal_statuses = {
            "candidate_rejected",
            "evidence_unavailable",
            "inconclusive",
            "refine",
            "rejected",
            "unchanged_work_suppressed",
        }
        prior: dict[str, Mapping[str, Any]] = {}
        paths = tuple(
            self.workspace.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_validation.json"
            for cycle_id in range(1, self.workspace.last_completed_cycle + 1)
        )
        for path in reversed(paths):
            if not path.is_file():
                continue
            payload = _read_json(path)
            validation = payload.get("validation", {})
            if not isinstance(validation, Mapping):
                continue
            audits = validation.get("agent_audits", {})
            if not isinstance(audits, Mapping):
                continue
            audit = audits.get("mining_pipeline", {})
            if (
                isinstance(audit, Mapping)
                and audit.get("track") == "hypothesis_then_exploration_fallback"
                and isinstance(audit.get("hypothesis"), Mapping)
            ):
                audit = audit["hypothesis"]
            if not isinstance(audit, Mapping):
                continue
            rows = audit.get("hypothesis_work", ())
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                fingerprint = str(row.get("work_fingerprint", ""))
                if (
                    fingerprint
                    and row.get("status") in terminal_statuses
                    and fingerprint not in prior
                ):
                    prior[fingerprint] = row
        return prior

    @staticmethod
    def _with_runtime_sample_basis(
        decisions: Iterable[SignalMiningDecision],
        *,
        positive_refs: Iterable[str],
        control_refs: Iterable[str],
    ) -> tuple[SignalMiningDecision, ...]:
        """Replace model sample claims with the exact runtime-owned groups."""

        basis = {
            "positive_refs": tuple(positive_refs),
            "control_refs": tuple(control_refs),
        }
        if not basis["positive_refs"] or not basis["control_refs"]:
            raise ValidationError(
                "Signal Mining association requires positive and control sample refs"
            )
        return tuple(replace(item, sample_basis=basis) for item in decisions)

    def run_cycle(
        self,
        *,
        cycle_id: int,
        input_snapshot: FrozenSignalRegistry | None = None,
    ) -> SlowLoopResult:
        """Validate, durably stage, and automatically promote one Slow batch."""

        staged = self.workspace.staged_slow_validation(cycle_id)
        if staged is None:
            if input_snapshot is None:
                raise ValidationError("new Slow loop requires its input Signal snapshot")
            self.workspace.refresh_capability_backlog(
                available_source_types=self.evidence_resolver.available_source_types
            )
            validation = self._validate_cycle(input_snapshot, cycle_id=cycle_id)
            self.workspace.stage_slow_validation(
                cycle_id=cycle_id,
                validation=validation.to_dict(),
            )
        else:
            validation = SlowLoopValidation.from_dict(staged)
        transition = self.registry.promote_validated_batch(
            validation.validated_candidates,
            validated_evaluations=(
                validation.candidate_evaluations
                if validation.candidate_evaluations
                else None
            ),
            transition_id=f"cycle-{cycle_id:04d}",
            input_version=validation.input_registry_version,
            input_hash=validation.input_registry_hash,
            input_refs=validation.input_signal_refs,
        )
        return SlowLoopResult(
            mined_candidates=validation.mined_candidates,
            updated_candidates=validation.updated_candidates,
            validated_candidates=validation.validated_candidates,
            promoted=transition.promoted,
            provisional_candidates=validation.provisional_candidates,
            rejected=validation.rejected,
            refined_hypotheses=validation.refined_hypotheses,
            input_registry_version=transition.input_version,
            input_registry_hash=transition.input_hash,
            output_registry_version=transition.output_version,
            output_registry_hash=transition.output_hash,
            candidate_evaluations=validation.candidate_evaluations,
            candidate_effectiveness=validation.candidate_effectiveness,
            agent_audits=validation.agent_audits,
            search_input_fingerprint=validation.search_input_fingerprint,
        )

    def _validate_cycle(
        self,
        input_snapshot: FrozenSignalRegistry,
        *,
        cycle_id: int = 1,
    ) -> SlowLoopValidation:
        """Stage all candidates and return the exact pre-promotion decision."""

        current = self.registry.freeze()
        if (
            current.version != input_snapshot.version
            or current.registry_hash != input_snapshot.registry_hash
        ):
            raise ValidationError("Slow-loop input Signal snapshot changed")

        mined: list[str] = []
        updated: list[str] = []
        agent_failures: dict[str, tuple[str, ...]] = {}
        agent_audits: dict[str, Mapping[str, Any]] = {}
        induction_case_ids: dict[str, tuple[str, ...]] = {}
        validation_case_ids: dict[str, tuple[str, ...]] = {}
        refined_hypotheses: dict[str, tuple[str, ...]] = {}
        try:
            mining_output = self._run_signal_mining(cycle_id=cycle_id)
            mined = list(mining_output["candidate_refs"])
            induction_case_ids = dict(mining_output["induction_case_ids"])
            validation_case_ids = dict(mining_output["validation_case_ids"])
            refined_hypotheses = dict(mining_output["refined_hypotheses"])
            agent_failures.update(dict(mining_output["failures"]))
            agent_audits["mining_pipeline"] = dict(mining_output["audit"])
        except ValidationError as exc:
            agent_failures["slow_loop:mining_pipeline"] = (
                "structured_output_failed: " + str(exc),
            )
            agent_audits["mining_pipeline"] = {
                "status": "failed",
                "error": str(exc),
                "usage": _usage_to_dict(getattr(exc, "usage", AgentUsage())),
            }
        try:
            update_output = self._run_signal_update(cycle_id=cycle_id)
            updated = list(update_output["candidate_refs"])
            induction_case_ids.update(update_output["induction_case_ids"])
            validation_case_ids.update(update_output["validation_case_ids"])
            agent_failures.update(update_output["failures"])
            agent_audits["update_pipeline"] = dict(update_output["audit"])
        except ValidationError as exc:
            agent_failures["slow_loop:update_pipeline"] = (
                "structured_output_failed: " + str(exc),
            )
            agent_audits["update_pipeline"] = {
                "schema_version": "signal-update-audit-v2",
                "cycle_id": cycle_id,
                "status": "failed",
                "error": str(exc),
                "usage": _usage_to_dict(
                    getattr(exc, "usage", AgentUsage())
                ),
            }
        all_refs = _ordered_unique([*mined, *updated])

        validations: dict[str, SignalCandidateValidation] = {}
        accepted_hashes: dict[str, str] = {}
        accepted_evaluations: dict[str, str] = {}
        semantic_seen: dict[str, str] = {}
        effectiveness_by_ref: dict[str, Mapping[str, Any]] = {}
        for signal_ref in all_refs:
            spec, skill = self.registry.load_candidate(signal_ref)
            tests = self.registry.load_candidate_tests(signal_ref)
            candidate_hash = self.registry.candidate_hash(signal_ref)
            try:
                stable_ref = self.registry.latest_spec(spec.signal_id).ref
            except ValidationError:
                stable_ref = None
            evaluation_identity = self.effectiveness_evaluator.evaluation_identity(
                spec,
                candidate_hash=candidate_hash,
                preferred_case_ids=validation_case_ids.get(signal_ref, ()),
                excluded_case_ids=induction_case_ids.get(signal_ref, ()),
                induction_supported=signal_ref in induction_case_ids,
            )
            evaluation_key, _identity = self.registry.candidate_evaluation_key(
                signal_ref,
                candidate_hash=candidate_hash,
                evaluation_identity=evaluation_identity,
            )
            prior_validation = self.registry.load_candidate_validation(
                signal_ref,
                evaluation_key=evaluation_key,
            )
            reusable_prior = (
                prior_validation is not None
                and prior_validation.get("schema_version")
                == "signal-candidate-evaluation-v3"
                and isinstance(prior_validation.get("effectiveness"), Mapping)
            )
            contract_validation: Mapping[str, Any]
            if stable_ref == signal_ref:
                validation = SignalCandidateValidation(
                    signal_ref=signal_ref,
                    accepted=False,
                    reasons=("candidate version is already stable",),
                    candidate_hash=candidate_hash,
                )
                effectiveness = {
                    "accepted": False,
                    "disposition": "rejected",
                    "status": "not_run",
                    "reasons": ["candidate version is already stable"],
                }
                contract_validation = {
                    "accepted": False,
                    "reasons": ["candidate version is already stable"],
                    "executed_tests": 0,
                }
            elif reusable_prior:
                assert prior_validation is not None
                validation = SignalCandidateValidation(
                    signal_ref=signal_ref,
                    accepted=bool(prior_validation.get("accepted")),
                    reasons=tuple(
                        str(item) for item in prior_validation.get("reasons", ())
                    ),
                    candidate_hash=candidate_hash,
                )
                effectiveness = dict(prior_validation["effectiveness"])
                contract_validation = dict(
                    prior_validation.get("contract_validation", {})
                )
            else:
                checked = self.validator.validate(spec, skill=skill, tests=tests)
                contract_validation = {
                    "accepted": checked.accepted,
                    "reasons": list(checked.reasons),
                    "executed_tests": checked.executed_tests,
                }
                if checked.accepted:
                    paired = self.effectiveness_evaluator.evaluate(
                        spec,
                        skill=skill,
                        preferred_case_ids=validation_case_ids.get(signal_ref, ()),
                        excluded_case_ids=induction_case_ids.get(signal_ref, ()),
                        induction_supported=signal_ref in induction_case_ids,
                    )
                    effectiveness = paired.to_dict()
                    reasons = paired.reasons
                    accepted = paired.accepted
                else:
                    effectiveness = {
                        "schema_version": "signal-candidate-effectiveness-v3",
                        "signal_ref": signal_ref,
                        "accepted": False,
                        "disposition": "rejected",
                        "status": "not_run",
                        "reasons": ["contract validation failed"],
                    }
                    reasons = checked.reasons
                    accepted = False
                validation = SignalCandidateValidation(
                    signal_ref=checked.signal_ref,
                    accepted=accepted,
                    reasons=tuple(reasons),
                    candidate_hash=candidate_hash,
                    executed_tests=checked.executed_tests,
                )
            semantic = _normalize_semantics(spec.description)
            prior_ref = semantic_seen.get(semantic)
            if validation.accepted and prior_ref is not None:
                duplicate_reason = f"semantic duplicate of candidate {prior_ref}"
                validation = SignalCandidateValidation(
                    signal_ref=signal_ref,
                    accepted=False,
                    reasons=(duplicate_reason,),
                    candidate_hash=candidate_hash,
                    executed_tests=validation.executed_tests,
                )
                contract_validation = {
                    **dict(contract_validation),
                    "accepted": False,
                    "reasons": [
                        *list(contract_validation.get("reasons", ())),
                        duplicate_reason,
                    ],
                }
                effectiveness = {
                    **dict(effectiveness),
                    "accepted": False,
                    "disposition": "rejected",
                    "reasons": [
                        *list(effectiveness.get("reasons", ())),
                        duplicate_reason,
                    ],
                }
            effectiveness_by_ref[signal_ref] = effectiveness
            if validation.accepted:
                semantic_seen[semantic] = signal_ref
                accepted_hashes[signal_ref] = candidate_hash
                accepted_evaluations[signal_ref] = evaluation_key
            validations[signal_ref] = validation
            if not reusable_prior and stable_ref != signal_ref:
                recorded_key = self.registry.record_candidate_validation(
                    signal_ref,
                    candidate_hash=candidate_hash,
                    evaluation_identity=evaluation_identity,
                    accepted=validation.accepted,
                    reasons=validation.reasons,
                    contract_validation=contract_validation,
                    effectiveness=effectiveness,
                )
                if validation.accepted:
                    accepted_evaluations[signal_ref] = recorded_key
        rejected = dict(agent_failures)
        provisional = {
            signal_ref: tuple(
                str(reason) for reason in effectiveness.get("reasons", ())
            )
            for signal_ref, effectiveness in effectiveness_by_ref.items()
            if effectiveness.get("disposition") == "provisional"
        }
        rejected.update(
            {
                signal_ref: validation.reasons
                for signal_ref, validation in validations.items()
                if not validation.accepted and signal_ref not in provisional
            }
        )
        return SlowLoopValidation(
            mined_candidates=tuple(mined),
            updated_candidates=tuple(updated),
            validated_candidates=accepted_hashes,
            provisional_candidates=provisional,
            rejected=rejected,
            refined_hypotheses=refined_hypotheses,
            input_registry_version=input_snapshot.version,
            input_registry_hash=input_snapshot.registry_hash,
            input_signal_refs=tuple(spec.ref for spec in input_snapshot.specs),
            candidate_evaluations=accepted_evaluations,
            candidate_effectiveness=effectiveness_by_ref,
            agent_audits=agent_audits,
            search_input_fingerprint=self._search_input_fingerprint(
                input_snapshot
            ),
        )

    def _run_signal_update(self, *, cycle_id: int) -> dict[str, Any]:
        """Run a bounded portfolio of independent single-target Updates."""

        targets = self._select_signal_update_targets()
        base_audit: dict[str, Any] = {
            "schema_version": "signal-update-audit-v2",
            "cycle_id": cycle_id,
            "status": "completed",
            "model_called": False,
            "model_target_count": 0,
            "model_usage": _usage_to_dict(AgentUsage()),
            "target_limit": _SIGNAL_UPDATE_TARGET_LIMIT,
            "target_count": len(targets),
            "candidate_refs": [],
            "targets": [],
        }
        if not targets:
            return self._signal_update_output(
                audit={**base_audit, "disposition": "no_actionable_target"}
            )

        cases = _sample_signal_discovery_cases(
            self.discovery_cases,
            limit=self.effectiveness_evaluator.case_limit + 4,
        )
        executor = SignalExecutor(
            self.registry.freeze(),
            self.raw_info_store,
            resolver=self.evidence_resolver,
            deterministic_functions=self.validator.deterministic_functions,
            llm_runner=self.llm_signal_runner,
        )
        candidate_refs: list[str] = []
        induction_case_ids: dict[str, tuple[str, ...]] = {}
        validation_case_ids: dict[str, tuple[str, ...]] = {}
        failures: dict[str, tuple[str, ...]] = {}
        target_audits: list[dict[str, Any]] = []
        for target in targets:
            signal_ref = str(target["signal_ref"])
            try:
                output = self._run_one_signal_update(
                    cycle_id=cycle_id,
                    target=target,
                    cases=cases,
                    executor=executor,
                )
            except ValidationError as exc:
                failures[f"update:{signal_ref}"] = (
                    "structured_output_failed: " + str(exc),
                )
                target_audits.append(
                    {
                        "schema_version": "signal-update-target-audit-v1",
                        "cycle_id": cycle_id,
                        "status": "failed",
                        "model_called": bool(
                            getattr(exc, "usage", AgentUsage()).llm_calls
                        ),
                        "target": dict(target),
                        "issue_fingerprint": _canonical_hash(target),
                        "error": str(exc),
                        "usage": _usage_to_dict(
                            getattr(exc, "usage", AgentUsage())
                        ),
                    }
                )
                continue
            candidate_refs.extend(output["candidate_refs"])
            induction_case_ids.update(output["induction_case_ids"])
            validation_case_ids.update(output["validation_case_ids"])
            failures.update(output["failures"])
            target_audits.append(dict(output["audit"]))

        model_usage = AgentUsage()
        for item in target_audits:
            raw_usage = item.get("model_usage", item.get("usage", {}))
            if isinstance(raw_usage, Mapping):
                model_usage = model_usage + _usage_from_dict(dict(raw_usage))
        model_target_count = sum(
            bool(item.get("model_called")) for item in target_audits
        )
        aggregate_audit = {
            **base_audit,
            "disposition": "portfolio_completed",
            "model_called": model_target_count > 0,
            "model_target_count": model_target_count,
            "model_usage": _usage_to_dict(model_usage),
            "candidate_refs": list(candidate_refs),
            "targets": target_audits,
        }
        return self._signal_update_output(
            candidate_refs=candidate_refs,
            induction_case_ids=induction_case_ids,
            validation_case_ids=validation_case_ids,
            failures=failures,
            audit=aggregate_audit,
        )

    def _run_one_signal_update(
        self,
        *,
        cycle_id: int,
        target: Mapping[str, Any],
        cases: tuple[EvolutionCase, ...],
        executor: SignalExecutor,
    ) -> dict[str, Any]:
        """Run one issuer-split Update without affecting sibling targets."""

        base_audit: dict[str, Any] = {
            "schema_version": "signal-update-target-audit-v1",
            "cycle_id": cycle_id,
            "status": "completed",
            "model_called": False,
            "candidate_refs": [],
        }
        signal_ref = str(target["signal_ref"])
        issue_fingerprint = _canonical_hash(target)
        base_audit.update(
            {
                "target": dict(target),
                "issue_fingerprint": issue_fingerprint,
            }
        )
        spec = self.registry.load_spec(signal_ref)
        skill = self.registry.load_skill(signal_ref)
        classified: dict[
            str, list[tuple[EvolutionCase, SignalResult, RawInfoResolution]]
        ] = {
            "wrong": [],
            "correct": [],
            "unavailable": [],
            "neutral": [],
        }
        technical_failures: list[dict[str, Any]] = []
        execution_usage = AgentUsage()
        for case in cases:
            batch = executor.execute_batch(
                (signal_ref,),
                company_id=case.company_id,
                as_of=case.prediction_time,
                identity=case.basic_info,
            )
            execution_usage = execution_usage + batch.usage
            result = batch.results[0]
            resolution = batch.resolutions[0]
            if result.execution_status not in {
                SignalExecutionStatus.SUCCESS,
                SignalExecutionStatus.DOMAIN_UNAVAILABLE,
            }:
                technical_failures.append(
                    {
                        "case_id": case.case_id,
                        "company_id": case.company_id,
                        "execution_status": result.execution_status.value,
                        "error_code": result.execution_error_code,
                        "error_message": result.execution_error_message,
                        "resolution": resolution.to_dict(),
                    }
                )
                continue
            if result.value is SignalValue.UNAVAILABLE:
                bucket = "unavailable"
            elif result.value is SignalValue.NEUTRAL:
                bucket = "neutral"
            elif (result.value is SignalValue.POSITIVE) == case.ground_truth.is_surge:
                bucket = "correct"
            else:
                bucket = "wrong"
            classified[bucket].append((case, result, resolution))

        problem_type = str(target["problem_type"])
        primary_name = (
            "unavailable" if problem_type == "repeated_unavailable" else "wrong"
        )
        primary = list(classified[primary_name][:2])
        primary_sources = [primary_name] * len(primary)
        if problem_type == "repeated_explicit_misleading" and len(primary) < 2:
            sourced_unavailable = [
                item for item in classified["unavailable"] if item[2].documents
            ]
            supplement = sourced_unavailable[: 2 - len(primary)]
            primary.extend(supplement)
            primary_sources.extend(["domain_unavailable"] * len(supplement))
        boundary_pool = [
            *classified["correct"],
            *classified["neutral"],
        ]
        boundary = boundary_pool[:2]
        induction = tuple([*primary, *boundary])
        induction_companies = {
            case.company_id for case, _result, _resolution in induction
        }
        holdout = tuple(
            case
            for case in cases
            if case.company_id not in induction_companies
        )[: self.effectiveness_evaluator.case_limit]
        local_selection = {
            "problem_bucket": primary_name,
            "primary_sources": primary_sources,
            "available_bucket_counts": {
                name: len(values) for name, values in classified.items()
            },
            "technical_failure_count": len(technical_failures),
            "induction_case_ids": [
                case.case_id for case, _result, _resolution in induction
            ],
            "holdout_case_ids": [case.case_id for case in holdout],
            "issuer_disjoint": not (
                induction_companies & {case.company_id for case in holdout}
            ),
        }
        execution_inputs = sorted(
            (
                {
                    "case_id": case.case_id,
                    "company_id": case.company_id,
                    "prediction_time": case.prediction_time.isoformat(),
                    "resolution": resolution.to_dict(),
                }
                for values in classified.values()
                for case, _result, resolution in values
            ),
            key=lambda item: item["case_id"],
        )
        work_fingerprint = _canonical_hash(
            {
                "schema_version": "signal-update-work-v1",
                "issue_fingerprint": issue_fingerprint,
                "local_selection": local_selection,
                "execution_inputs": execution_inputs,
                "update_model": self._role_work_identity(self.update_model),
                "projection_protocol": "signal-update-evidence-packet-v2",
            }
        )
        base_audit["work_fingerprint"] = work_fingerprint
        prior = self._prior_signal_update(work_fingerprint)
        if prior is not None:
            staged_ref = str(prior.get("staged_ref", ""))
            if staged_ref:
                validation = self.registry.load_candidate_validation(staged_ref)
                effectiveness = (
                    dict(validation.get("effectiveness", {}))
                    if validation is not None
                    else {}
                )
                if effectiveness.get("disposition") == "provisional":
                    return self._signal_update_output(
                        candidate_refs=(staged_ref,),
                        induction_case_ids={
                            staged_ref: tuple(local_selection["induction_case_ids"])
                        },
                        validation_case_ids={
                            staged_ref: tuple(local_selection["holdout_case_ids"])
                        },
                        audit={
                            **base_audit,
                            "disposition": "reused_provisional",
                            "staged_ref": staged_ref,
                            "local_selection": local_selection,
                        },
                    )
            return self._signal_update_output(
                audit={
                    **base_audit,
                    "disposition": "unchanged_work_suppressed",
                    "local_selection": local_selection,
                }
            )
        if (
            not primary
            or not boundary
            or len(holdout) < self.effectiveness_evaluator.minimum_cases
        ):
            return self._signal_update_output(
                audit={
                    **base_audit,
                    "disposition": "defer",
                    "defer_reason": "insufficient_local_induction_or_holdout",
                    "local_selection": local_selection,
                    "execution_usage": _usage_to_dict(execution_usage),
                    "technical_failures": technical_failures,
                }
            )

        induction_packets: list[dict[str, Any]] = []
        resolutions: list[dict[str, Any]] = []
        for index, (case, result, resolution) in enumerate(induction, start=1):
            case_ref = f"update-case-{index:03d}"
            packet, resolution_audit = self._signal_update_evidence_packet(
                case_ref,
                case,
                spec=spec,
                result=result,
                resolution=resolution,
            )
            induction_packets.append(packet)
            resolutions.append(resolution_audit)

        payload = {
            "update_contract_version": "signal-update-decision-v2",
            "fixed_prior": self.priors.update_signal,
            "target": {
                "signal_ref": signal_ref,
                "problem_type": target["problem_type"],
                "stable_spec": spec.to_dict(),
                "stable_skill": skill,
                "learned_profile": self.registry.load_learning_profile(signal_ref),
            },
            "induction_cases": induction_packets,
            "candidate_contract": {
                "arguments_schema": self._candidate_arguments_schema(clone=True),
                "changed_paths_allowed": list(SIGNAL_UPDATE_MUTABLE_PATHS),
                "changed_paths_excluded": [
                    "spec.version",
                    "spec.definition",
                    "tests",
                    "whole-section aliases",
                ],
                "vnext_template": {
                    "signal_ref": signal_ref,
                    "spec": {**spec.to_dict(), "version": spec.version + 1},
                    "skill": skill,
                    "tests": [],
                },
            },
            "rules": {
                "dispositions": ["no_change", "defer", "update"],
                "distinguish_routing_applicability_from_signal_defect": True,
                "holdout_hidden": True,
                "candidate_only_when_update": True,
            },
        }
        step = self.update_model.update(payload)
        decision = step.value
        if decision.signal_ref != signal_ref:
            raise CandidateExecutionRejected(
                "signal_update_decision",
                "Signal Update decision changed the local target ref",
                step.usage,
            )
        audit = {
            **base_audit,
            "model_called": True,
            "model_usage": _usage_to_dict(step.usage),
            "execution_usage": _usage_to_dict(execution_usage),
            "local_selection": local_selection,
            "resolutions": resolutions,
            "technical_failures": technical_failures,
            "decision": decision.to_dict(),
            "disposition": decision.disposition,
        }
        audit["diagnostic_counts"] = {
            "evidence_verdict": {
                name: sum(
                    str(item.get("evidence_verdict", "")) == name
                    for item in decision.case_diagnostics
                )
                for name in ("supported", "contradicted", "insufficient")
            },
            "outcome_relation": {
                name: sum(
                    str(item.get("outcome_relation", "")) == name
                    for item in decision.case_diagnostics
                )
                for name in ("aligned", "misaligned", "not_assessable")
            },
        }
        if decision.disposition != "update":
            return self._signal_update_output(audit=audit)
        assert decision.candidate is not None
        try:
            staged_ref = self._stage_update_candidate(
                signal_ref=signal_ref,
                candidate=decision.candidate,
                changed_paths=decision.changed_paths,
            )
        except ValidationError as exc:
            raise CandidateExecutionRejected(
                "signal_update_candidate",
                str(exc),
                step.usage,
            ) from exc
        audit["candidate_refs"] = [staged_ref]
        audit["staged_ref"] = staged_ref
        return self._signal_update_output(
            candidate_refs=(staged_ref,),
            induction_case_ids={
                staged_ref: tuple(
                    case.case_id for case, _result, _resolution in induction
                )
            },
            validation_case_ids={
                staged_ref: tuple(case.case_id for case in holdout)
            },
            audit=audit,
        )

    def _select_signal_update_targets(
        self,
        *,
        limit: int = _SIGNAL_UPDATE_TARGET_LIMIT,
    ) -> tuple[dict[str, Any], ...]:
        if limit < 1:
            raise ValidationError("Signal Update target limit must be positive")
        targets: list[tuple[int, str, dict[str, Any]]] = []
        for card in self.registry.list_signal_cards():
            profile = dict(card.learned_profile)
            unique = int(profile.get("unique_observations", 0))
            if unique < 2:
                continue
            directional = dict(profile.get("directional", {}))
            attribution = dict(profile.get("reflection_attribution", {}))
            misleading = int(attribution.get("misleading", 0))
            wrong = int(directional.get("wrong", 0))
            unavailable = int(directional.get("unavailable", 0))
            unavailable_with_inputs = int(
                directional.get("unavailable_with_inputs", 0)
            )
            if misleading >= 2:
                problem_type = "repeated_explicit_misleading"
                score = 300 + misleading
            elif wrong >= 2:
                problem_type = "repeated_directional_wrong"
                score = 200 + wrong
            elif unavailable_with_inputs >= 2 and unavailable * 2 >= unique:
                problem_type = "repeated_unavailable"
                score = 100 + unavailable_with_inputs
            else:
                continue
            target = {
                "signal_ref": card.ref,
                "problem_type": problem_type,
                "support": {
                    "unique_observations": unique,
                    "misleading_attributions": misleading,
                    "directional_wrong": wrong,
                    "unavailable": unavailable,
                    "unavailable_with_inputs": unavailable_with_inputs,
                },
                "recurring_contexts": list(
                    profile.get("recurring_contexts", ())
                )[:3],
            }
            targets.append((score, card.ref, target))
        ranked = sorted(targets, key=lambda item: (-item[0], item[1]))
        return tuple(item[2] for item in ranked[:limit])

    def _prior_signal_update(
        self, work_fingerprint: str
    ) -> Mapping[str, Any] | None:
        for path in reversed(
            sorted(
                (self.workspace.experiments_root / "cycles").glob(
                    "cycle-*/slow_loop_validation.json"
                )
            )
        ):
            payload = _read_json(path)
            validation = payload.get("validation", {})
            if not isinstance(validation, Mapping):
                continue
            audits = validation.get("agent_audits", {})
            if not isinstance(audits, Mapping):
                continue
            audit = audits.get("update_pipeline", {})
            if not isinstance(audit, Mapping):
                continue
            candidates = [audit]
            target_audits = audit.get("targets", ())
            if isinstance(target_audits, list):
                candidates.extend(
                    item for item in target_audits if isinstance(item, Mapping)
                )
            for candidate in candidates:
                if (
                    candidate.get("work_fingerprint") == work_fingerprint
                    and (
                        candidate.get("disposition") == "no_change"
                        or bool(candidate.get("staged_ref"))
                    )
                ):
                    return candidate
        return None

    def _stage_update_candidate(
        self,
        *,
        signal_ref: str,
        candidate: Mapping[str, Any],
        changed_paths: Iterable[str],
    ) -> str:
        stable = self.registry.load_spec(signal_ref)
        updated, skill_value, raw_tests = validate_signal_update_candidate(
            signal_ref,
            candidate,
            stable,
            stable_skill=self.registry.load_skill(signal_ref),
            changed_paths=changed_paths,
        )
        return self.registry.stage_candidate(
            updated,
            skill=skill_value,
            tests=raw_tests,
            origin=f"update:{signal_ref}",
        )

    @staticmethod
    def _signal_update_output(
        *,
        audit: Mapping[str, Any],
        candidate_refs: Iterable[str] = (),
        induction_case_ids: Mapping[str, tuple[str, ...]] | None = None,
        validation_case_ids: Mapping[str, tuple[str, ...]] | None = None,
        failures: Mapping[str, tuple[str, ...]] | None = None,
    ) -> dict[str, Any]:
        return {
            "candidate_refs": tuple(candidate_refs),
            "induction_case_ids": dict(induction_case_ids or {}),
            "validation_case_ids": dict(validation_case_ids or {}),
            "failures": dict(failures or {}),
            "audit": dict(audit),
        }

    def _run_signal_mining(self, *, cycle_id: int) -> dict[str, Any]:
        """Run one bounded Mining track while local code owns every data boundary."""

        if cycle_id < 1:
            raise ValidationError("Signal Mining cycle id must be positive")
        mode = (
            "exploration"
            if cycle_id % self.mining_config.exploration_interval == 0
            else "hypothesis"
        )
        if mode == "exploration":
            return self._run_exploration_mining(cycle_id=cycle_id)
        fallback_supported = bool(
            getattr(self.mining_model, "supports_exploration_fallback", False)
        )
        hypothesis_failure: CandidateExecutionRejected | None = None
        try:
            hypothesis_result = self._run_hypothesis_mining(cycle_id=cycle_id)
        except CandidateExecutionRejected as exc:
            if not fallback_supported:
                raise
            hypothesis_failure = exc
            hypothesis_result = self._mining_output(
                audit={
                    "schema_version": "signal-mining-audit-v1",
                    "status": "failed",
                    "cycle_id": cycle_id,
                    "track": "hypothesis",
                    "limits": self.mining_config.to_dict(),
                    "stages": {},
                    "failure_stage": exc.stage,
                    "error": str(exc),
                    "failure_details": dict(exc.details),
                    "usage": _usage_to_dict(exc.usage),
                    "candidate_refs": [],
                    "refined_hypotheses": {},
                },
                refined={},
            )
        if (
            hypothesis_result["candidate_refs"]
            or not fallback_supported
            or (
                hypothesis_failure is None
                and not _mining_needs_exploration_fallback(
                    hypothesis_result["audit"]
                )
            )
        ):
            return hypothesis_result
        try:
            exploration_result = self._run_exploration_mining(cycle_id=cycle_id)
        except ValidationError as exc:
            if hypothesis_failure is None:
                raise
            combined_usage = hypothesis_failure.usage + getattr(
                exc, "usage", AgentUsage()
            )
            raise CandidateExecutionRejected(
                "signal_mining_pipeline",
                "hypothesis track failed before same-cycle Exploration fallback: "
                f"{hypothesis_failure}; Exploration track also failed: {exc}",
                combined_usage,
            ) from exc
        return _merge_mining_fallback(hypothesis_result, exploration_result)

    def _run_hypothesis_mining(self, *, cycle_id: int) -> dict[str, Any]:
        config = self.mining_config
        scanned_pairs = self._mining_case_universe(
            limit=config.h2_profile_scan_limit
        )
        self._preflight_h2_profiles(scanned_pairs)
        refined: dict[str, tuple[str, ...]] = {}
        audit: dict[str, Any] = {
            "schema_version": "signal-mining-audit-v1",
            "status": "completed",
            "cycle_id": cycle_id,
            "track": "hypothesis",
            "limits": config.to_dict(),
            "stages": {},
        }
        ready_rows: list[tuple[str, EvolutionCase, dict[str, Any]]] = []
        profile_audit: list[dict[str, Any]] = []
        positive_ready_count = 0
        control_ready_count = 0
        for case_ref, case in scanned_pairs:
            brief = self._mining_case_brief(case_ref, case)
            profile_audit.append(
                {
                    "case_ref": case_ref,
                    "ready": bool(brief.pop("_profile_ready", False)),
                    "profile_resolution": brief.pop("_profile_resolution", None),
                }
            )
            if profile_audit[-1]["ready"]:
                ready_rows.append((case_ref, case, brief))
                if case.ground_truth.is_surge:
                    positive_ready_count += 1
                else:
                    control_ready_count += 1
                if (
                    len(ready_rows) >= config.case_pool_limit
                    and positive_ready_count >= config.h2_min_ready_per_class
                    and control_ready_count >= config.h2_min_ready_per_class
                ):
                    break
        positives = [item for item in ready_rows if item[1].ground_truth.is_surge]
        controls = [item for item in ready_rows if not item[1].ground_truth.is_surge]
        if (
            len(ready_rows) < config.h2_min_ready_issuers
            or len(positives) < config.h2_min_ready_per_class
            or len(controls) < config.h2_min_ready_per_class
        ):
            reason = "insufficient_h2_profile_readiness"
            audit["status"] = reason
            audit["h2_profile_readiness"] = {
                "scanned": len(profile_audit),
                "ready": len(ready_rows),
                "positive_ready": len(positives),
                "control_ready": len(controls),
                "minimum_ready": config.h2_min_ready_issuers,
                "minimum_per_class": config.h2_min_ready_per_class,
                "cases": profile_audit,
            }
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
            return self._mining_output(audit=audit, refined=refined)
        mandatory_refs = {
            item[0]
            for item in (
                *positives[: config.h2_min_ready_per_class],
                *controls[: config.h2_min_ready_per_class],
            )
        }
        selected_ready = [item for item in ready_rows if item[0] in mandatory_refs]
        selected_ready.extend(
            item
            for item in ready_rows
            if item[0] not in mandatory_refs
        )
        selected_ready = selected_ready[: config.case_pool_limit]
        case_pairs = tuple((ref, case) for ref, case, _brief in selected_ready)
        briefs_by_ref = {ref: brief for ref, _case, brief in selected_ready}
        context = self._mining_context(cycle_id=cycle_id)
        prior_terminal_work = self._prior_terminal_hypothesis_work()
        hypothesis_work: list[dict[str, Any]] = []
        applicability_contract = self._h2_applicability_contract(
            briefs_by_ref.values()
        )
        h1_payload = {
            "track": "hypothesis",
            "h1_contract_version": "signal-mining-hypothesis-v3",
            "hypothesis_slots": [
                f"h1-c{cycle_id:04d}-s{index:02d}"
                for index in range(1, config.hypothesis_limit + 1)
            ],
            "fixed_comparison": "fixed_discovery_positive_vs_control",
            "limits": config.to_dict(),
            "h2_applicability_contract": applicability_contract,
            **context,
        }
        h1_input_fingerprint = _canonical_hash(
            {
                "schema_version": "signal-mining-h1-input-v3",
                "contract": h1_payload["h1_contract_version"],
                "limits": h1_payload["limits"],
                "h2_applicability_contract": applicability_contract,
                "capability_backlog": context["capability_backlog"],
                "meta_info": context["meta_info"],
                "stable_signal_cards": context["stable_signal_cards"],
                "available_raw_source_types": context[
                    "available_raw_source_types"
                ],
                "registered_deterministic_functions": context[
                    "registered_deterministic_functions"
                ],
                "relevant_raw_info": self._relevant_search_documents(),
                "mining_model": self._role_work_identity(self.mining_model),
            }
        )
        prior_h1 = next(
            (
                item
                for item in reversed(context["prior_slow_work"])
                if item.get("h1_input_fingerprint") == h1_input_fingerprint
                and dict(item.get("h1_conclusion", {})).get("conclusion")
                == "no_testable_hypothesis"
            ),
            None,
        )
        if prior_h1 is not None:
            prior_conclusion = dict(prior_h1["h1_conclusion"])
            audit["status"] = "unchanged_h1_work_suppressed"
            audit["stages"]["H1"] = {
                "contract_version": "signal-mining-hypothesis-v3",
                "input_fingerprint": h1_input_fingerprint,
                "conclusion": prior_conclusion,
                "hypotheses": [],
                "reused_from_prior_cycle": True,
                "usage": _usage_to_dict(AgentUsage()),
            }
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {}
            audit["hypothesis_work"] = []
            return self._mining_output(audit=audit, refined={})
        try:
            hypotheses_step = self.mining_model.propose_hypotheses(h1_payload)
        except CandidateExecutionRejected as exc:
            raise CandidateExecutionRejected(
                exc.stage,
                str(exc),
                exc.usage,
                details={
                    **dict(exc.details),
                    "contract_version": "signal-mining-hypothesis-v3",
                    "input_fingerprint": h1_input_fingerprint,
                    "conclusion": {
                        "conclusion": "technical_failure",
                        "reason_code": "structured_recovery_exhausted",
                    },
                },
            ) from exc
        if len(hypotheses_step.value) > config.hypothesis_limit:
            raise ValidationError(
                "Signal Mining hypothesis portfolio exceeds the configured limit"
            )
        hypotheses: list[SignalMiningHypothesis] = []
        available_sources = set(self.evidence_resolver.available_source_types)
        seen_ids: set[str] = set()
        for hypothesis in hypotheses_step.value:
            if hypothesis.hypothesis_id in seen_ids:
                raise ValidationError("Signal Mining hypothesis ids must be unique")
            seen_ids.add(hypothesis.hypothesis_id)
            unsupported = sorted(set(hypothesis.source_types) - available_sources)
            if unsupported:
                refined[hypothesis.hypothesis_id] = (
                    "required source types are unavailable: " + ", ".join(unsupported),
                )
                continue
            hypotheses.append(hypothesis)
        audit["stages"]["H1"] = {
            "contract_version": "signal-mining-hypothesis-v3",
            "input_fingerprint": h1_input_fingerprint,
            "conclusion": dict(hypotheses_step.metadata),
            "hypotheses": [item.to_dict() for item in hypotheses_step.value],
            "usage": _usage_to_dict(hypotheses_step.usage),
        }
        if not hypotheses:
            if hypotheses_step.metadata.get("conclusion") == "no_testable_hypothesis":
                audit["status"] = "no_testable_hypothesis"
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
            audit["hypothesis_work"] = []
            return self._mining_output(audit=audit, refined=refined)
        case_by_ref = dict(case_pairs)
        ranking_limit = min(config.ranking_case_limit, len(case_pairs))
        rankings = {
            hypothesis.hypothesis_id: tuple(
                case_ref
                for case_ref, _case in case_pairs
                if self._h2_applicability_matches(
                    hypothesis.applicability,
                    briefs_by_ref[case_ref],
                )
            )[:ranking_limit]
            for hypothesis in hypotheses
        }
        audit["stages"]["H2"] = {
            "mode": "deterministic_canonical_applicability",
            "rankings": {key: list(value) for key, value in rankings.items()},
            "case_briefs": [
                briefs_by_ref[case_ref] for case_ref, _case in case_pairs
            ],
            "profile_readiness": {
                "scanned": len(profile_audit),
                "ready": len(ready_rows),
                "selected": len(case_pairs),
                "cases": profile_audit,
            },
            "usage": _usage_to_dict(AgentUsage()),
        }

        selections: list[dict[str, Any]] = []
        for hypothesis in hypotheses:
            selected = self._select_mining_cases(
                rankings[hypothesis.hypothesis_id],
                case_by_ref=case_by_ref,
            )
            if selected is None:
                refined[hypothesis.hypothesis_id] = (
                    "label-hidden ranking did not contain both positive and control cases",
                )
                continue
            selections.append(
                {
                    "hypothesis": hypothesis,
                    **selected,
                }
            )
        if not selections:
            audit["local_selection"] = []
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
            audit["hypothesis_work"] = []
            return self._mining_output(audit=audit, refined=refined)

        contrast_packets: list[dict[str, Any]] = []
        evidence_packets_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        resolution_audit: list[dict[str, Any]] = []
        evidence_unavailable: dict[str, tuple[str, ...]] = {}
        evaluable_selections: list[dict[str, Any]] = []
        for selection in selections:
            hypothesis = selection["hypothesis"]
            if len(evaluable_selections) >= config.selected_hypothesis_limit:
                refined[hypothesis.hypothesis_id] = (
                    "deferred because the per-cycle evidence contrast budget was reached",
                )
                continue
            usable_by_class: dict[bool, list[str]] = {True: [], False: []}
            comparator_by_class: dict[bool, list[str]] = {True: [], False: []}
            attempted_case_refs: list[str] = []
            attempted_packet_refs: list[str] = []
            packet_ref_by_case: dict[str, str] = {}
            for case_ref in rankings[hypothesis.hypothesis_id]:
                case = case_by_ref[case_ref]
                case_class = bool(case.ground_truth.is_surge)
                if (
                    len(usable_by_class[case_class])
                    >= config.induction_cases_per_class
                ):
                    continue
                packet_key = (
                    case_ref,
                    tuple(hypothesis.source_types),
                    hypothesis.query,
                    hypothesis.lookback_days,
                )
                if packet_key not in evidence_packets_by_key:
                    packet, resolution = self._mining_evidence_packet(
                        case_ref,
                        case,
                        source_types=hypothesis.source_types,
                        query=hypothesis.query,
                        lookback_days=hypothesis.lookback_days,
                        reveal_label=True,
                    )
                    packet_ref = "packet_" + hashlib.sha256(
                        json.dumps(packet_key, sort_keys=True).encode("utf-8")
                    ).hexdigest()[:20]
                    evidence_packets_by_key[packet_key] = {
                        "packet_ref": packet_ref,
                        **packet,
                    }
                    resolution_audit.append({"packet_ref": packet_ref, **resolution})
                stored_packet = evidence_packets_by_key[packet_key]
                attempted_case_refs.append(case_ref)
                attempted_packet_refs.append(stored_packet["packet_ref"])
                if stored_packet["evidence"]:
                    packet_ref_by_case[case_ref] = stored_packet["packet_ref"]
                    target = (
                        usable_by_class
                        if stored_packet.get("query_match_status") == "matched"
                        else comparator_by_class
                    )
                    target[case_class].append(case_ref)
                if all(
                    len(refs) >= config.induction_cases_per_class
                    for refs in usable_by_class.values()
                ):
                    break
            for case_class in (True, False):
                needed = (
                    config.induction_cases_per_class
                    - len(usable_by_class[case_class])
                )
                usable_by_class[case_class].extend(
                    comparator_by_class[case_class][:needed]
                )
            if not all(
                len(refs) >= config.induction_cases_per_class
                for refs in usable_by_class.values()
            ):
                reasons = (
                    "fewer than the configured issuer-distinct cases had usable "
                    "hypothesis-relevant point-in-time evidence; attempted refs: "
                    + ", ".join(attempted_case_refs),
                )
                attempted_ref_set = set(attempted_packet_refs)
                work_fingerprint = self._hypothesis_work_fingerprint(
                    hypothesis,
                    packets=(
                        packet
                        for packet in evidence_packets_by_key.values()
                        if packet["packet_ref"] in attempted_ref_set
                    ),
                    validation_refs=selection["validation_refs"],
                    case_by_ref=case_by_ref,
                )
                prior_work = prior_terminal_work.get(work_fingerprint)
                if prior_work is not None:
                    reasons = (
                        "unchanged hypothesis work suppressed until evidence or "
                        "strategy changes",
                    )
                    status = "unchanged_work_suppressed"
                    refined[hypothesis.hypothesis_id] = reasons
                else:
                    status = "evidence_unavailable"
                    evidence_unavailable[hypothesis.hypothesis_id] = reasons
                hypothesis_work.append(
                    {
                        "hypothesis_id": hypothesis.hypothesis_id,
                        "work_fingerprint": work_fingerprint,
                        "status": status,
                        "reasons": list(reasons),
                    }
                )
                continue
            induction_refs = tuple(
                (*usable_by_class[True], *usable_by_class[False])
            )
            validation_by_class: dict[bool, list[str]] = {True: [], False: []}
            used_companies = {
                case_by_ref[case_ref].company_id for case_ref in induction_refs
            }
            for case_ref in rankings[hypothesis.hypothesis_id]:
                case = case_by_ref[case_ref]
                case_class = bool(case.ground_truth.is_surge)
                if (
                    case.company_id in used_companies
                    or len(validation_by_class[case_class])
                    >= config.validation_cases_per_class
                ):
                    continue
                used_companies.add(case.company_id)
                validation_by_class[case_class].append(case_ref)
            actual_selection = {
                **selection,
                "induction_refs": induction_refs,
                "validation_refs": tuple(
                    (*validation_by_class[True], *validation_by_class[False])
                ),
                "sample_basis": {
                    "positive_refs": tuple(
                        packet_ref_by_case[case_ref]
                        for case_ref in usable_by_class[True]
                    ),
                    "control_refs": tuple(
                        packet_ref_by_case[case_ref]
                        for case_ref in usable_by_class[False]
                    ),
                },
            }
            active_refs = {
                packet_ref_by_case[case_ref] for case_ref in induction_refs
            }
            work_fingerprint = self._hypothesis_work_fingerprint(
                hypothesis,
                packets=(
                    packet
                    for packet in evidence_packets_by_key.values()
                    if packet["packet_ref"] in active_refs
                ),
                validation_refs=actual_selection["validation_refs"],
                case_by_ref=case_by_ref,
            )
            prior_work = prior_terminal_work.get(work_fingerprint)
            if prior_work is not None:
                reasons = (
                    "unchanged hypothesis work suppressed until evidence or "
                    "strategy changes",
                )
                refined[hypothesis.hypothesis_id] = reasons
                hypothesis_work.append(
                    {
                        "hypothesis_id": hypothesis.hypothesis_id,
                        "work_fingerprint": work_fingerprint,
                        "status": "unchanged_work_suppressed",
                        "reasons": list(reasons),
                        "prior_status": str(prior_work.get("status", "")),
                    }
                )
                continue
            actual_selection["work_fingerprint"] = work_fingerprint
            evaluable_selections.append(actual_selection)
            contrast_packets.append(
                {
                    "hypothesis": hypothesis.to_dict(),
                    "evidence_packet_refs": [
                        packet_ref_by_case[case_ref]
                        for case_ref in induction_refs
                    ],
                }
            )
        audit["local_selection"] = [
            {
                "hypothesis_id": item["hypothesis"].hypothesis_id,
                "induction_case_refs": list(item["induction_refs"]),
                "validation_case_refs": list(item["validation_refs"]),
            }
            for item in evaluable_selections
        ]
        audit["evidence_unavailable"] = {
            key: list(value) for key, value in evidence_unavailable.items()
        }
        if not contrast_packets:
            suppressed = any(
                item.get("status") == "unchanged_work_suppressed"
                for item in hypothesis_work
            )
            h3_status = "not_called_evidence_unavailable"
            if suppressed and not evidence_unavailable:
                h3_status = "not_called_unchanged_work"
            elif suppressed:
                h3_status = "not_called_no_evaluable_work"
            audit["stages"]["H3"] = {
                "status": h3_status,
                "decisions": [],
                "resolutions": resolution_audit,
                "usage": _usage_to_dict(AgentUsage()),
            }
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
            audit["hypothesis_work"] = hypothesis_work
            return self._mining_output(audit=audit, refined=refined)
        active_packet_refs = {
            packet_ref
            for comparison in contrast_packets
            for packet_ref in comparison["evidence_packet_refs"]
        }
        decisions_step = self.mining_model.contrast(
            {
                "track": "hypothesis",
                "evidence_packets": [
                    packet
                    for packet in evidence_packets_by_key.values()
                    if packet["packet_ref"] in active_packet_refs
                ],
                "comparisons": contrast_packets,
                "candidate_contract": self._mining_candidate_contract(),
                "rules": {
                    "decisions": [
                        "supported",
                        "refine",
                        "rejected",
                        "inconclusive",
                    ],
                    "candidate_only_when_supported": True,
                },
            }
        )
        allowed_hypotheses = {
            item["hypothesis"].hypothesis_id for item in evaluable_selections
        }
        decisions = self._validate_mining_decisions(
            decisions_step.value,
            allowed_hypothesis_ids=allowed_hypotheses,
        )
        selection_by_id = {
            item["hypothesis"].hypothesis_id: item
            for item in evaluable_selections
        }
        decisions = tuple(
            self._with_runtime_sample_basis(
                (decision,),
                **selection_by_id[decision.hypothesis_id]["sample_basis"],
            )[0]
            for decision in decisions
        )
        for decision in decisions:
            if decision.disposition == "inconclusive":
                evidence_unavailable[decision.hypothesis_id] = tuple(
                    "H3 judged the model-facing evidence semantically insufficient: "
                    + reason
                    for reason in decision.rationale
                )
        audit["stages"]["H3"] = {
            "status": (
                "completed_with_inconclusive"
                if any(item.disposition == "inconclusive" for item in decisions)
                else "completed"
            ),
            "decisions": [item.to_dict() for item in decisions],
            "resolutions": resolution_audit,
            "usage": _usage_to_dict(decisions_step.usage),
        }
        audit["evidence_unavailable"] = {
            key: list(value) for key, value in evidence_unavailable.items()
        }
        staged = self._stage_mining_decisions(
            decisions,
            selection_by_id=selection_by_id,
            case_by_ref=case_by_ref,
            refined=refined,
        )
        staging_by_id = {
            str(item.get("hypothesis_id", "")): item
            for item in staged["staging"]
            if isinstance(item, Mapping)
        }
        for decision in decisions:
            selection = selection_by_id[decision.hypothesis_id]
            status = decision.disposition
            reasons = decision.rationale
            if decision.disposition == "supported":
                staging = staging_by_id.get(decision.hypothesis_id, {})
                if staging.get("status") == "contract_accepted":
                    status = "candidate_staged"
                    reasons = ()
                else:
                    status = "candidate_rejected"
                    reasons = tuple(
                        str(reason)
                        for reason in staging.get(
                            "reasons",
                            ("candidate staging did not produce an accepted draft",),
                        )
                    )
            hypothesis_work.append(
                {
                    "hypothesis_id": decision.hypothesis_id,
                    "work_fingerprint": selection["work_fingerprint"],
                    "status": status,
                    "reasons": list(reasons),
                }
            )
        audit["candidate_refs"] = list(staged["candidate_refs"])
        audit["staging"] = list(staged["staging"])
        audit["hypothesis_work"] = hypothesis_work
        audit["refined_hypotheses"] = {
            key: list(value) for key, value in refined.items()
        }
        return self._mining_output(
            audit=audit,
            refined=refined,
            **staged,
        )

    def _run_exploration_mining(self, *, cycle_id: int) -> dict[str, Any]:
        config = self.mining_config
        required_per_class = (
            (2 * config.induction_cases_per_class)
            + config.validation_cases_per_class
        )
        cases = _sample_binary_discovery_cases(
            self.discovery_cases,
            per_class=required_per_class,
        )
        case_pairs = _exploration_case_pairs(cases, cycle_id=cycle_id)
        case_by_ref = dict(case_pairs)
        refs_by_class = {
            case_class: tuple(
                case_ref
                for case_ref, case in case_pairs
                if bool(case.ground_truth.is_surge) == case_class
            )
            for case_class in (True, False)
        }
        minimum_per_class = (
            config.induction_cases_per_class
            + config.validation_cases_per_class
        )
        if any(
            len(refs) < minimum_per_class for refs in refs_by_class.values()
        ):
            audit = {
                "schema_version": "signal-mining-audit-v1",
                "status": "completed",
                "cycle_id": cycle_id,
                "track": "exploration",
                "limits": config.to_dict(),
                "stages": {},
                "candidate_refs": [],
                "refined_hypotheses": {
                    "exploration_sampling": [
                        "Discovery pool lacks the configured issuer-distinct "
                        "induction and validation cases in one or both groups"
                    ]
                },
            }
            return self._mining_output(
                audit=audit,
                refined={
                    "exploration_sampling": (
                        "Discovery pool lacks the configured issuer-distinct "
                        "induction and validation cases in one or both groups",
                    )
                },
            )
        e1_by_class: dict[bool, tuple[str, ...]] = {}
        validation_by_class: dict[bool, tuple[str, ...]] = {}
        for case_class, refs in refs_by_class.items():
            candidate_count = min(
                2 * config.induction_cases_per_class,
                len(refs) - config.validation_cases_per_class,
            )
            e1_by_class[case_class] = refs[:candidate_count]
            validation_by_class[case_class] = refs[
                candidate_count : candidate_count
                + config.validation_cases_per_class
            ]
        e1_ref_set = {*e1_by_class[True], *e1_by_class[False]}
        validation_ref_set = {
            *validation_by_class[True],
            *validation_by_class[False],
        }
        selected = {
            "e1_refs": tuple(
                case_ref for case_ref, _case in case_pairs if case_ref in e1_ref_set
            ),
            "validation_refs": tuple(
                case_ref
                for case_ref, _case in case_pairs
                if case_ref in validation_ref_set
            ),
        }
        available = set(self.evidence_resolver.available_source_types)
        source_types = tuple(sorted(available))
        evidence_packets: list[dict[str, Any]] = []
        resolution_audit: list[dict[str, Any]] = []
        for case_ref in selected["e1_refs"]:
            packet, resolution = self._mining_evidence_packet(
                case_ref,
                case_by_ref[case_ref],
                source_types=source_types,
                query=None,
                lookback_days=config.evidence_lookback_days,
                reveal_label=False,
            )
            evidence_packets.append(packet)
            resolution_audit.append(resolution)
        signatures_list: list[SignalMiningSignature] = []
        extraction_usage = AgentUsage()
        extraction_failures: dict[str, tuple[str, ...]] = {}
        microbatches: list[dict[str, Any]] = []
        for start in range(0, len(evidence_packets), config.exploration_microbatch_size):
            batch_packets = evidence_packets[
                start : start + config.exploration_microbatch_size
            ]
            batch_refs = tuple(str(item["case_ref"]) for item in batch_packets)
            try:
                extraction_step = self.mining_model.extract_exploration(
                    {
                        "track": "exploration",
                        "microbatch_ref": f"e1-batch-{start // config.exploration_microbatch_size + 1:03d}",
                        "cases": batch_packets,
                        "rules": {
                            "labels_hidden": True,
                            "identities_hidden": True,
                            "describe_only_observable_patterns": True,
                        },
                    }
                )
                extraction_usage = extraction_usage + extraction_step.usage
                batch_signatures = validate_signal_mining_signatures(
                    extraction_step.value,
                    batch_packets,
                )
            except CandidateExecutionRejected as exc:
                extraction_usage = extraction_usage + exc.usage
                reason = (
                    "Exploration E1 microbatch exhausted structured recovery: "
                    + str(exc),
                )
                for case_ref in batch_refs:
                    extraction_failures[case_ref] = reason
                microbatches.append(
                    {
                        "case_refs": list(batch_refs),
                        "status": "technical_failure",
                        "error": str(exc),
                    }
                )
                continue
            except RuntimeBudgetExceeded:
                raise
            except ValidationError as exc:
                reason = (
                    "Exploration E1 microbatch failed local result validation: "
                    + str(exc),
                )
                for case_ref in batch_refs:
                    extraction_failures[case_ref] = reason
                microbatches.append(
                    {
                        "case_refs": list(batch_refs),
                        "status": "validation_failure",
                        "error": str(exc),
                    }
                )
                continue
            signatures_list.extend(batch_signatures)
            quarantined = extraction_step.metadata.get("quarantined_observations", {})
            for case_ref, reasons in quarantined.items():
                extraction_failures[case_ref] = tuple(
                    "Exploration E1 observation quarantined: " + str(reason)
                    for reason in reasons
                )
            microbatches.append(
                {
                    "case_refs": list(batch_refs),
                    "status": "partial_technical_failure" if quarantined else "completed",
                    "quarantined_observations": quarantined,
                }
            )
        signatures = tuple(signatures_list)
        signature_by_ref = {item.case_ref: item for item in signatures}
        grounded_signatures = tuple(
            signature_by_ref[case_ref]
            for case_ref in selected["e1_refs"]
            if case_ref in signature_by_ref
            and signature_by_ref[case_ref].observations
        )
        grounded_by_class = {
            case_class: tuple(
                item
                for item in grounded_signatures
                if bool(case_by_ref[item.case_ref].ground_truth.is_surge)
                == case_class
            )
            for case_class in (True, False)
        }
        selected_grounded_refs = {
            item.case_ref
            for item in (
                *grounded_by_class[True][: config.induction_cases_per_class],
                *grounded_by_class[False][: config.induction_cases_per_class],
            )
        }
        selected_grounded_signatures = tuple(
            signature_by_ref[case_ref]
            for case_ref, _case in case_pairs
            if case_ref in selected_grounded_refs
        )
        if any(
            len(items) < config.induction_cases_per_class
            for items in grounded_by_class.values()
        ):
            reason = (
                "Exploration E1 produced fewer than the configured grounded "
                "signatures in one or both fixed groups"
            )
            audit = {
                "schema_version": "signal-mining-audit-v1",
                "status": "completed",
                "cycle_id": cycle_id,
                "track": "exploration",
                "limits": config.to_dict(),
                "local_selection": {
                    "e1_candidate_case_refs": list(selected["e1_refs"]),
                    "induction_case_refs": [
                        item.case_ref for item in selected_grounded_signatures
                    ],
                    "validation_case_refs": list(selected["validation_refs"]),
                    "grounded_case_refs": [
                        item.case_ref for item in grounded_signatures
                    ],
                },
                "stages": {
                    "E1": {
                        "signatures": [item.to_dict() for item in signatures],
                        "resolutions": resolution_audit,
                        "microbatches": microbatches,
                        "failures": {
                            key: list(value)
                            for key, value in extraction_failures.items()
                        },
                        "usage": _usage_to_dict(extraction_usage),
                    },
                    "E2": {
                        "status": "not_called_evidence_unavailable",
                        "decisions": [],
                        "usage": _usage_to_dict(AgentUsage()),
                    },
                },
                "candidate_refs": [],
                "refined_hypotheses": {"exploration_evidence": [reason]},
            }
            return self._mining_output(
                audit=audit,
                refined={"exploration_evidence": (reason,)},
                failures={
                    f"slow_loop:exploration_e1:{case_ref}": reasons
                    for case_ref, reasons in extraction_failures.items()
                },
            )
        revealed = [
            {
                **signature.to_dict(),
                "label": (
                    "positive"
                    if case_by_ref[signature.case_ref].ground_truth.is_surge
                    else "control"
                ),
            }
            for signature in selected_grounded_signatures
        ]
        discovery_step = self.mining_model.discover_exploration(
            {
                "track": "exploration",
                "signatures": revealed,
                "candidate_contract": self._mining_candidate_contract(),
                "rules": {
                    "candidate_only_for_repeated_observable_pattern": True,
                    "exact_spans_authoritative_over_summaries": True,
                    "decisions": [
                        "supported",
                        "refine",
                        "rejected",
                        "inconclusive",
                    ],
                },
            }
        )
        decisions = self._validate_mining_decisions(
            discovery_step.value,
            allowed_hypothesis_ids=None,
        )
        decisions = self._with_runtime_sample_basis(
            decisions,
            positive_refs=(
                signature.case_ref
                for signature in selected_grounded_signatures
                if case_by_ref[signature.case_ref].ground_truth.is_surge
            ),
            control_refs=(
                signature.case_ref
                for signature in selected_grounded_signatures
                if not case_by_ref[signature.case_ref].ground_truth.is_surge
            ),
        )
        refined: dict[str, tuple[str, ...]] = {}
        selection_by_id = {
            item.hypothesis_id: {
                "induction_refs": tuple(
                    signature.case_ref for signature in selected_grounded_signatures
                ),
                "validation_refs": selected["validation_refs"],
            }
            for item in decisions
        }
        staged = self._stage_mining_decisions(
            decisions,
            selection_by_id=selection_by_id,
            case_by_ref=case_by_ref,
            refined=refined,
        )
        audit = {
            "schema_version": "signal-mining-audit-v1",
            "status": "completed",
            "cycle_id": cycle_id,
            "track": "exploration",
            "limits": config.to_dict(),
            "local_selection": {
                "e1_candidate_case_refs": list(selected["e1_refs"]),
                "induction_case_refs": [
                    item.case_ref for item in selected_grounded_signatures
                ],
                "validation_case_refs": list(selected["validation_refs"]),
                "grounded_case_refs": [
                    item.case_ref for item in grounded_signatures
                ],
            },
            "stages": {
                "E1": {
                    "signatures": [item.to_dict() for item in signatures],
                    "resolutions": resolution_audit,
                    "microbatches": microbatches,
                    "failures": {
                        key: list(value) for key, value in extraction_failures.items()
                    },
                    "usage": _usage_to_dict(extraction_usage),
                },
                "E2": {
                    "decisions": [item.to_dict() for item in decisions],
                    "no_candidate": discovery_step.metadata.get("no_candidate"),
                    "considered_case_count": len(selected_grounded_signatures),
                    "usage": _usage_to_dict(discovery_step.usage),
                },
            },
            "candidate_refs": list(staged["candidate_refs"]),
            "staging": list(staged["staging"]),
            "refined_hypotheses": {
                key: list(value) for key, value in refined.items()
            },
        }
        staged_with_failures = dict(staged)
        staged_with_failures["failures"] = {
            **dict(staged["failures"]),
            **{
                f"slow_loop:exploration_e1:{case_ref}": reasons
                for case_ref, reasons in extraction_failures.items()
            },
        }
        return self._mining_output(
            audit=audit,
            refined=refined,
            **staged_with_failures,
        )

    def _mining_output(
        self,
        *,
        audit: Mapping[str, Any],
        refined: Mapping[str, tuple[str, ...]],
        candidate_refs: Iterable[str] = (),
        induction_case_ids: Mapping[str, tuple[str, ...]] | None = None,
        validation_case_ids: Mapping[str, tuple[str, ...]] | None = None,
        failures: Mapping[str, tuple[str, ...]] | None = None,
        staging: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        del staging
        return {
            "candidate_refs": tuple(candidate_refs),
            "induction_case_ids": dict(induction_case_ids or {}),
            "validation_case_ids": dict(validation_case_ids or {}),
            "refined_hypotheses": dict(refined),
            "failures": dict(failures or {}),
            "audit": dict(audit),
        }

    def _mining_context(self, *, cycle_id: int) -> dict[str, Any]:
        prior_work: list[dict[str, Any]] = []
        for path in sorted(
            (self.workspace.experiments_root / "cycles").glob(
                "cycle-*/slow_loop_validation.json"
            )
        )[-3:]:
            payload = _read_json(path)
            validation = payload.get("validation", {})
            if not isinstance(validation, Mapping):
                continue
            provisional_rows = []
            for signal_ref, reasons in dict(
                validation.get("provisional_candidates", {})
            ).items():
                try:
                    spec, _skill = self.registry.load_candidate(str(signal_ref))
                except ValidationError:
                    continue
                provisional_rows.append(
                    {
                        "signal_ref": str(signal_ref),
                        "description": spec.description,
                        "source_types": list(spec.source_types),
                        "reasons": list(reasons),
                    }
                )
            audit = dict(validation.get("agent_audits", {})).get(
                "mining_pipeline", {}
            )
            if (
                isinstance(audit, Mapping)
                and audit.get("track") == "hypothesis_then_exploration_fallback"
                and isinstance(audit.get("hypothesis"), Mapping)
            ):
                audit = dict(audit["hypothesis"])
            h1_rows = (
                dict(dict(audit).get("stages", {}))
                .get("H1", {})
                .get("hypotheses", [])
                if isinstance(audit, Mapping)
                else []
            )
            h1_stage = (
                dict(dict(audit).get("stages", {})).get("H1", {})
                if isinstance(audit, Mapping)
                else {}
            )
            failure_details = (
                dict(audit.get("failure_details", {}))
                if isinstance(audit, Mapping)
                and isinstance(audit.get("failure_details"), Mapping)
                else {}
            )
            refined_ids = set(
                dict(validation.get("refined_hypotheses", {}))
            )
            refined_reasons = dict(
                validation.get("refined_hypotheses", {})
            )
            evidence_unavailable = (
                dict(audit.get("evidence_unavailable", {}))
                if isinstance(audit, Mapping)
                else {}
            )
            prior_work.append(
                {
                    "provisional_candidates": provisional_rows,
                    "refined_hypotheses": [
                        {
                            "hypothesis": dict(item),
                            "reasons": list(
                                refined_reasons.get(
                                    str(item.get("hypothesis_id")), ()
                                )
                            ),
                        }
                        for item in h1_rows
                        if isinstance(item, Mapping)
                        and item.get("hypothesis_id") in refined_ids
                    ],
                    "evidence_unavailable": [
                        {
                            "hypothesis": dict(item),
                            "reasons": list(
                                evidence_unavailable.get(
                                    str(item.get("hypothesis_id")), ()
                                )
                            ),
                        }
                        for item in h1_rows
                        if isinstance(item, Mapping)
                        and item.get("hypothesis_id") in evidence_unavailable
                    ],
                    "h1_conclusion": (
                        dict(
                            h1_stage.get(
                                "conclusion", failure_details.get("conclusion", {})
                            )
                        )
                        if isinstance(h1_stage, Mapping)
                        and isinstance(h1_stage.get("conclusion"), Mapping)
                        else {}
                    ),
                    "h1_input_fingerprint": (
                        str(
                            h1_stage.get(
                                "input_fingerprint",
                                failure_details.get("input_fingerprint", ""),
                            )
                        )
                        if isinstance(h1_stage, Mapping)
                        else ""
                    ),
                }
            )
        cards = [
            self._mining_signal_card_view(card.to_dict())
            for category in self.registry.list_categories()
            for card in self.registry.list_signal_cards(category)
        ]
        backlog_path = self.workspace.root / "capability_backlog.json"
        capability_backlog = (
            _read_json(backlog_path)
            if backlog_path.exists()
            else {
                "schema_version": "capability-gap-report-v3",
                "items": [],
                "signal_need_items": [],
                "open_count": 0,
                "resolved_count": 0,
            }
        )
        capability_backlog = dict(capability_backlog)
        capability_backlog["signal_need_items"] = [
            {
                **dict(item),
                "need_ref": str(item.get("need_ref") or "need-" + _canonical_hash(item)[:16]),
            }
            for item in capability_backlog.get("signal_need_items", ())
            if isinstance(item, Mapping)
        ]
        capability_backlog = self._mining_capability_backlog_view(
            capability_backlog
        )
        meta_view = _mask_identity_values(
            list(self.meta_memory.model_view()),
            self.slow_role_identity_guards,
            expand_aliases=False,
        )
        return {
            "cycle_id": cycle_id,
            "meta_info": meta_view,
            "meta_context_audit": {
                "content_hash": _canonical_hash(meta_view),
                "round_ids": [int(item["round_id"]) for item in meta_view],
                "case_count": sum(
                    len(plan.original_case_reflections)
                    for entry in self.meta_memory.entries
                    for plan in entry.plan_reflections
                ),
            },
            "capability_backlog": _mask_identity_values(
                capability_backlog, self.slow_role_identity_guards, expand_aliases=False
            ),
            "stable_signal_cards": cards,
            "prior_slow_work": _mask_identity_values(
                prior_work, self.slow_role_identity_guards, expand_aliases=False
            ),
            "available_raw_source_types": list(
                self.evidence_resolver.available_source_types
            ),
            "registered_deterministic_functions": sorted(
                self.validator.deterministic_functions
            ),
            "locked_test_available": False,
        }

    @staticmethod
    def _mining_capability_backlog_view(
        backlog: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Remove local identities and paths from the H1-only backlog view."""

        needs = []
        for raw_item in backlog.get("signal_need_items", ()):
            if not isinstance(raw_item, Mapping):
                continue
            item = dict(raw_item)
            item["sources"] = [
                {
                    "source_ref": "source-" + _canonical_hash(
                        str(source.get("source_ref", ""))
                    )[:16],
                    "source_round": source.get("source_round"),
                    "source_fingerprint": source.get("source_fingerprint"),
                    "original_need": source.get("original_need"),
                    "stop_reason": source.get("stop_reason"),
                }
                for source in item.get("sources", ())
                if isinstance(source, Mapping)
            ]
            needs.append(item)
        items = []
        for raw_item in backlog.get("items", ()):
            if not isinstance(raw_item, Mapping):
                continue
            item = {
                key: value
                for key, value in raw_item.items()
                if key != "affected_case_ids"
            }
            item["affected_source_count"] = len(
                raw_item.get("affected_case_ids", ())
            )
            items.append(item)
        technical = []
        for raw_item in backlog.get("technical_failures", ()):
            if not isinstance(raw_item, Mapping):
                continue
            technical.append(
                {
                    key: value
                    for key, value in raw_item.items()
                    if key != "case_id"
                }
            )
        return {
            "schema_version": backlog.get("schema_version"),
            "items": items,
            "signal_need_items": needs,
            "technical_failures": technical,
            "diagnostic_attempt_count": len(backlog.get("diagnostic_attempts", ())),
            "open_count": backlog.get("open_count", 0),
            "resolved_count": backlog.get("resolved_count", 0),
        }

    @staticmethod
    def _mining_signal_card_view(card: Mapping[str, Any]) -> dict[str, Any]:
        """Omit an all-zero learned profile from the H1-only card projection."""

        result = dict(card)
        profile = result.get("learned_profile")
        if not isinstance(profile, Mapping):
            return result
        if (
            int(profile.get("selection_events", 0)) == 0
            and int(profile.get("unique_observations", 0)) == 0
        ):
            result.pop("learned_profile", None)
        return result

    def _mining_case_universe(
        self, *, limit: int
    ) -> tuple[tuple[str, EvolutionCase], ...]:
        return tuple(
            (f"case-{index:03d}", case)
            for index, case in enumerate(
                _sample_signal_discovery_cases(self.discovery_cases, limit=limit),
                start=1,
            )
        )

    def _preflight_h2_profiles(
        self, case_pairs: Iterable[tuple[str, EvolutionCase]]
    ) -> None:
        """Pause before H1 when mandatory H2 profiles cannot be obtained."""

        pairs = tuple(case_pairs)
        config = self.mining_config
        potential_positive = sum(case.ground_truth.is_surge for _, case in pairs)
        potential_control = len(pairs) - potential_positive
        if (
            len(pairs) < config.h2_min_ready_issuers
            or potential_positive < config.h2_min_ready_per_class
            or potential_control < config.h2_min_ready_per_class
        ):
            return
        ready = 0
        positive_ready = 0
        control_ready = 0
        first_case_ref = "profile-preflight"
        for case_ref, case in pairs:
            if first_case_ref == "profile-preflight":
                first_case_ref = case_ref
            _documents, profile = self._mining_local_profile(case)
            if not self._mining_profile_ready(profile):
                continue
            ready += 1
            if case.ground_truth.is_surge:
                positive_ready += 1
            else:
                control_ready += 1
        if (
            ready >= config.h2_min_ready_issuers
            and positive_ready >= config.h2_min_ready_per_class
            and control_ready >= config.h2_min_ready_per_class
        ):
            return
        request = self._mining_profile_request(first_case_ref)
        can_acquire = getattr(self.evidence_resolver, "can_acquire", None)
        if can_acquire is None or can_acquire(request):
            return
        reason_resolver = getattr(
            self.evidence_resolver,
            "acquisition_unavailability_reason",
            None,
        )
        reason = (
            reason_resolver(request)
            if reason_resolver is not None
            else "profile_adapter_unavailable"
        )
        raise SlowLoopDataUnavailable(
            "profile-preflight",
            reason or "profile_adapter_unavailable",
        )

    @staticmethod
    def _mining_profile_request(case_ref: str) -> RawInfoRequest:
        return RawInfoRequest(
            request_id=f"signal_mining_profile:{case_ref}",
            description="Latest point-in-time annual filing business profile.",
            source_types=("10-k", "filing", "sec_filing"),
            lookback_days=730,
            max_documents=1,
            query="item 1 business",
        )

    def _mining_local_profile(
        self, case: EvolutionCase
    ) -> tuple[tuple[RawInfoDocument, ...], dict[str, Any]]:
        documents = tuple(
            document
            for document in self.raw_info_store.documents
            if document.company_id == case.company_id
            and document.available_at <= case.prediction_time
        )
        profile = _point_in_time_profile_fields(case.basic_info, documents)
        if not _usable_business_description(profile.get("business_description")):
            profile.pop("business_description", None)
            excerpt = _item1_business_excerpt(documents)
            if excerpt:
                profile["business_description"] = excerpt
        return documents, profile

    @staticmethod
    def _mining_profile_ready(profile: Mapping[str, Any]) -> bool:
        return bool(
            _usable_business_description(profile.get("business_description"))
            or profile.get("industry")
            or profile.get("sector")
        )

    @staticmethod
    def _h2_applicability_contract(
        briefs: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Describe only fields and categorical values visible in this H2 pool."""

        rows = tuple(briefs)
        field_by_rule = {
            "industry_values": "industry",
            "sector_values": "sector",
            "exchange_values": "exchange",
            "market_cap_bucket_values": "market_cap_bucket",
            "listing_age_bucket_values": "listing_age_bucket",
        }
        observed_values = {
            rule_name: sorted(
                {
                    str(brief[field_name])
                    for brief in rows
                    if field_name in brief and str(brief[field_name]).strip()
                }
            )
            for rule_name, field_name in field_by_rule.items()
        }
        observed_values["raw_info_source_type_values"] = sorted(
            {
                str(source_type)
                for brief in rows
                for source_type in (
                    brief.get("raw_info_coverage", {}).get("source_types", ())
                    if isinstance(brief.get("raw_info_coverage"), Mapping)
                    else ()
                )
            }
        )
        return {
            "schema_version": "h2-applicability-contract-v1",
            "canonical_rule_names": [
                "all_ready_issuers",
                "business_description_topics",
                *[
                    rule_name
                    for rule_name, values in observed_values.items()
                    if values
                ],
            ],
            "observed_values": observed_values,
            "business_description_topic_limits": {
                "max_values": 6,
                "max_terms_per_value": 4,
                "max_total_terms": 8,
            },
        }

    @staticmethod
    def _h2_applicability_matches(
        applicability: str,
        brief: Mapping[str, Any],
    ) -> bool:
        """Apply an H1 canonical rule without model judgment or label access."""

        if applicability == "all_ready_issuers":
            return True
        rule_name, separator, raw_values = applicability.partition(":")
        if not separator:
            return False
        values = tuple(item.casefold() for item in raw_values.split("|") if item)
        if not values:
            return False
        if rule_name == "business_description_topics":
            description_terms = set(
                _h3_ordered_content_terms(
                    str(brief.get("business_description", "")),
                    exclude_generic=False,
                )
            )
            return any(
                set(
                    _h3_ordered_content_terms(value, exclude_generic=False)
                ).issubset(description_terms)
                for value in values
            )
        if rule_name == "raw_info_source_type_values":
            coverage = brief.get("raw_info_coverage", {})
            visible = (
                coverage.get("source_types", ())
                if isinstance(coverage, Mapping)
                else ()
            )
        else:
            field_by_rule = {
                "industry_values": "industry",
                "sector_values": "sector",
                "exchange_values": "exchange",
                "market_cap_bucket_values": "market_cap_bucket",
                "listing_age_bucket_values": "listing_age_bucket",
            }
            field_name = field_by_rule.get(rule_name)
            if field_name is None:
                return False
            visible = (brief.get(field_name),)
        visible_values = {
            str(item).casefold() for item in visible if item is not None and str(item)
        }
        return any(value in visible_values for value in values)

    def _mining_case_brief(
        self, case_ref: str, case: EvolutionCase
    ) -> dict[str, Any]:
        aliases = self.slow_role_identity_guards
        documents, profile = self._mining_local_profile(case)
        profile_resolution: dict[str, Any] | None = None
        if not self._mining_profile_ready(profile):
            request = self._mining_profile_request(case_ref)
            can_acquire = getattr(self.evidence_resolver, "can_acquire", None)
            acquisition_available = can_acquire is None or can_acquire(request)
            if not acquisition_available:
                profile_resolution = {
                    "status": "unavailable",
                    "data_gap": {"reason": "profile_adapter_unavailable"},
                    "document_count": 0,
                }
            else:
                resolution = self.evidence_resolver.resolve(
                    request,
                    company_id=case.company_id,
                    identity=case.basic_info,
                    as_of=case.prediction_time,
                )
                if resolution.gap is not None and resolution.gap.reason.value in {
                    "provider_error",
                    "quota_deferred",
                    "materialization_failed",
                }:
                    raise SlowLoopDataUnavailable(
                        case_ref,
                        resolution.gap.reason.value,
                    )
                acquired = self.evidence_resolver.load_documents(
                    resolution, as_of=case.prediction_time
                )
                documents = tuple(
                    {
                        item.document_id: item
                        for item in (*documents, *acquired)
                    }.values()
                )
                profile = _point_in_time_profile_fields(case.basic_info, documents)
                if not _usable_business_description(
                    profile.get("business_description")
                ):
                    profile.pop("business_description", None)
                profile_resolution = {
                    "status": resolution.status,
                    "data_gap": resolution.gap.to_dict() if resolution.gap else None,
                    "document_count": len(acquired),
                }
        if not _usable_business_description(profile.get("business_description")):
            profile.pop("business_description", None)
            excerpt = _item1_business_excerpt(documents)
            if excerpt:
                profile["business_description"] = excerpt
        profile_ready = self._mining_profile_ready(profile)
        description = str(
            profile.get("business_description") or "unavailable"
        )[:600]
        safe_info = {
            "business_description": description,
            "industry": profile.get("industry") or "unavailable",
            "sector": profile.get("sector") or "unavailable",
            "exchange": profile.get("exchange") or "unavailable",
            "market_cap_bucket": _market_cap_bucket(profile.get("market_cap")),
            "listing_age_bucket": _listing_age_bucket(
                profile.get("listing_date"),
                as_of=case.prediction_time,
            ),
        }
        safe_info = {
            key: value
            for key, value in safe_info.items()
            if key == "business_description" or value != "unavailable"
        }
        masked_info = dict(_mask_identity_values(safe_info, aliases, expand_aliases=False))
        _assert_identity_values_masked(masked_info, aliases, expand_aliases=False)
        return {
            "case_ref": case_ref,
            "prediction_year": case.prediction_time.year,
            **masked_info,
            "raw_info_coverage": {
                "document_count": len(documents),
                "source_types": sorted({item.source_type for item in documents}),
            },
            "_profile_ready": profile_ready,
            "_profile_resolution": profile_resolution,
        }

    def _select_mining_cases(
        self,
        ranked_refs: Iterable[str],
        *,
        case_by_ref: Mapping[str, EvolutionCase],
    ) -> dict[str, tuple[str, ...]] | None:
        positives: list[str] = []
        controls: list[str] = []
        seen_companies: set[str] = set()
        for case_ref in ranked_refs:
            case = case_by_ref[case_ref]
            if case.company_id in seen_companies:
                continue
            seen_companies.add(case.company_id)
            target = positives if case.ground_truth.is_surge else controls
            target.append(case_ref)
        induction_count = self.mining_config.induction_cases_per_class
        validation_count = self.mining_config.validation_cases_per_class
        if not positives or not controls:
            return None
        induction = tuple(
            [*positives[:induction_count], *controls[:induction_count]]
        )
        validation = tuple(
            [
                *positives[induction_count : induction_count + validation_count],
                *controls[induction_count : induction_count + validation_count],
            ]
        )
        return {"induction_refs": induction, "validation_refs": validation}

    def _signal_update_evidence_packet(
        self,
        case_ref: str,
        case: EvolutionCase,
        *,
        spec: SignalSpec,
        result: SignalResult,
        resolution: RawInfoResolution,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Project the exact documents already consumed by one Signal execution."""

        documents = self.evidence_resolver.load_documents(
            resolution, as_of=case.prediction_time
        )
        aliases = self.slow_role_identity_guards
        cited_evidence = (
            ("supporting", result.supporting_evidence),
            ("counter", result.counter_evidence),
        )
        cited_document_ids = {
            item.document_id
            for _group, items in cited_evidence
            for item in items
        }
        documents = tuple(
            sorted(
                documents,
                key=lambda item: (
                    item.document_id not in cited_document_ids,
                    item.document_id,
                ),
            )
        )
        document_ref_by_id = {
            document.document_id: f"document-{index:02d}"
            for index, document in enumerate(documents, start=1)
        }
        evidence = [
            _model_evidence_view(
                document,
                index=index,
                aliases=aliases,
                query=spec.retrieval_policy.query,
                expand_aliases=False,
            )
            for index, document in enumerate(documents, start=1)
        ]
        result_view = signal_result_model_view(result)
        for group in ("supporting", "counter"):
            for item in result_view["evidence"][group]:
                item["document_id"] = document_ref_by_id.get(
                    item["document_id"], "missing-document"
                )
        masked_result = _mask_identity_values(result_view, aliases, expand_aliases=False)
        executed_evidence = [
            {
                "role": group,
                "document_ref": document_ref_by_id.get(
                    item.document_id, "missing-document"
                ),
                "exact_span": _mask_identity_values(
                    item.exact_span, aliases, expand_aliases=False
                ),
                "timestamp": item.timestamp.isoformat(),
            }
            for group, items in cited_evidence
            for item in items
        ]
        _assert_identity_values_masked(evidence, aliases, expand_aliases=False)
        _assert_identity_values_masked(masked_result, aliases, expand_aliases=False)
        _assert_identity_values_masked(executed_evidence, aliases, expand_aliases=False)
        packet = {
            "case_ref": case_ref,
            "evidence_observation": {
                "prediction_time": case.prediction_time.isoformat(),
                "executed_evidence": executed_evidence,
                "evidence": evidence,
                "evidence_scope": (
                    "executed_evidence is the Signal's exact cited projection; evidence "
                    "adds bounded context from every exact Signal execution input; "
                    "an excerpt cannot prove that an absent fact is absent from the source"
                ),
                "resolution_status": resolution.status,
                "resolution_coverage": resolution.coverage.to_dict(),
                "current_signal_result": masked_result,
            },
            "outcome_relation": {
                "label": "positive" if case.ground_truth.is_surge else "control",
                "current_signal_relation": (
                    "not_assessable"
                    if result.value in {SignalValue.UNAVAILABLE, SignalValue.NEUTRAL}
                    else (
                        "aligned"
                        if (result.value is SignalValue.POSITIVE)
                        == case.ground_truth.is_surge
                        else "misaligned"
                    )
                ),
                "rule": (
                    "The label may assess directional association only after source "
                    "support is judged; it is not evidence that a fact or event exists."
                ),
            },
        }
        return packet, {
            "case_ref": case_ref,
            "status": resolution.status,
            "input_request": resolution.request.to_dict(),
            "document_count": len(documents),
            "document_ids": [item.document_id for item in documents],
            "document_hashes": [item.content_hash for item in documents],
            "cited_document_refs": [
                item["document_ref"] for item in executed_evidence
            ],
            "as_of": case.prediction_time.isoformat(),
            "reused_signal_execution_input": True,
        }

    def _mining_evidence_packet(
        self,
        case_ref: str,
        case: EvolutionCase,
        *,
        source_types: tuple[str, ...],
        query: str | None,
        lookback_days: int,
        reveal_label: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        selection: dict[str, Any] = {}

        def select_documents(
            candidates: tuple[RawInfoDocument, ...],
            request: RawInfoRequest,
        ) -> tuple[RawInfoDocument, ...]:
            selected, evidence, audit = _select_h3_model_evidence(
                candidates,
                case=case,
                query=query,
                limit=request.max_documents,
                aliases=self.slow_role_identity_guards,
                expand_aliases=False,
                prefer_source_diversity=True,
            )
            selection.clear()
            selection.update(audit)
            selection["evidence"] = evidence
            return selected

        resolution = self.evidence_resolver.resolve(
            RawInfoRequest(
                request_id=f"signal_mining:{case_ref}",
                description="Exact point-in-time evidence for Signal Mining comparison.",
                source_types=source_types,
                lookback_days=lookback_days,
                max_documents=self.mining_config.evidence_documents_per_case,
                query=query,
            ),
            company_id=case.company_id,
            identity=case.basic_info,
            as_of=case.prediction_time,
            select_documents=select_documents,
        )
        if resolution.gap is not None and resolution.gap.reason.value in {
            "provider_error",
            "quota_deferred",
            "materialization_failed",
        }:
            raise SlowLoopDataUnavailable(case_ref, resolution.gap.reason.value)
        documents = self.evidence_resolver.load_documents(
            resolution,
            as_of=case.prediction_time,
        )
        evidence = list(selection.pop("evidence", ())) if documents else []
        filtered_documents = list(selection.get("filtered_documents", ()))
        query_coverage = dict(
            selection.get(
                "query_coverage",
                _h3_text_query_coverage((), query=query),
            )
        )
        packet: dict[str, Any] = {
            "case_ref": case_ref,
            "prediction_time": case.prediction_time.isoformat(),
            "evidence": evidence,
            "query_match_status": selection.get(
                "query_match_status", "no_exact_source"
            ),
            "resolution_status": (
                resolution.status
                if documents
                else "unresolved_after_relevance_filter"
            ),
        }
        if reveal_label:
            packet["label"] = (
                "positive" if case.ground_truth.is_surge else "control"
            )
        return packet, {
            "case_ref": case_ref,
            "status": (
                resolution.status
                if documents
                else "unresolved_after_relevance_filter"
            ),
            "requested_source_types": list(source_types),
            "document_count": len(documents),
            "usable": bool(documents),
            "document_hashes": [item.content_hash for item in documents],
            "filtered_documents": filtered_documents,
            "query_coverage": query_coverage,
            "as_of": case.prediction_time.isoformat(),
        }

    def _mining_candidate_contract(self) -> dict[str, Any]:
        return {
            "arguments_schema": self._candidate_arguments_schema(clone=False),
            "constraints": [
                "new signal_id only; existing stable identities belong to Update",
                "non-empty point-in-time fixtures required",
                "candidate text and fixtures must not contain Discovery identities or labels",
            ],
        }

    @staticmethod
    def _validate_mining_decisions(
        decisions: Iterable[SignalMiningDecision],
        *,
        allowed_hypothesis_ids: set[str] | None,
    ) -> tuple[SignalMiningDecision, ...]:
        values = tuple(decisions)
        ids = [item.hypothesis_id for item in values]
        if len(set(ids)) != len(ids):
            raise ValidationError("Signal Mining decisions must have unique hypothesis ids")
        if allowed_hypothesis_ids is not None:
            if set(ids) != allowed_hypothesis_ids:
                raise ValidationError(
                    "Signal Mining decisions must cover every supplied comparison"
                )
        return values

    def _stage_mining_decisions(
        self,
        decisions: Iterable[SignalMiningDecision],
        *,
        selection_by_id: Mapping[str, Mapping[str, Any]],
        case_by_ref: Mapping[str, EvolutionCase],
        refined: dict[str, tuple[str, ...]],
    ) -> dict[str, Any]:
        candidate_refs: list[str] = []
        induction_case_ids: dict[str, tuple[str, ...]] = {}
        validation_case_ids: dict[str, tuple[str, ...]] = {}
        failures: dict[str, tuple[str, ...]] = {}
        staging: list[dict[str, Any]] = []
        for decision in decisions:
            if decision.disposition != "supported":
                if decision.disposition == "refine":
                    refined[decision.hypothesis_id] = decision.rationale
                staging.append(
                    {
                        "hypothesis_id": decision.hypothesis_id,
                        "status": decision.disposition,
                        "reasons": list(decision.rationale),
                    }
                )
                continue
            candidate = dict(decision.candidate or {})
            if set(candidate) != {"spec", "skill", "tests"}:
                failures[f"slow_loop:mining_stage:{decision.hypothesis_id}"] = (
                    "supported candidate requires exactly spec, skill, and tests",
                )
                continue
            tests = candidate["tests"]
            if not isinstance(tests, list):
                failures[f"slow_loop:mining_stage:{decision.hypothesis_id}"] = (
                    "candidate tests must be an array",
                )
                continue
            try:
                signal_ref = self._stage_from_tool(
                    spec=candidate["spec"],
                    skill=(
                        str(candidate["skill"])
                        if candidate["skill"] is not None
                        else None
                    ),
                    tests=tests,
                    origin=f"mining:{decision.hypothesis_id}",
                    collected=candidate_refs,
                )
                contract = self._run_signal_tests_tool(signal_ref)
                if not contract["accepted"]:
                    candidate_refs.remove(signal_ref)
                    failures[signal_ref] = tuple(
                        str(reason) for reason in contract["reasons"]
                    )
                    staging.append(
                        {
                            "hypothesis_id": decision.hypothesis_id,
                            "signal_ref": signal_ref,
                            "status": "contract_rejected",
                            "reasons": list(contract["reasons"]),
                        }
                    )
                    continue
                selection = selection_by_id[decision.hypothesis_id]
                induction_case_ids[signal_ref] = tuple(
                    case_by_ref[case_ref].case_id
                    for case_ref in selection["induction_refs"]
                )
                validation_case_ids[signal_ref] = tuple(
                    case_by_ref[case_ref].case_id
                    for case_ref in selection["validation_refs"]
                )
                staging.append(
                    {
                        "hypothesis_id": decision.hypothesis_id,
                        "signal_ref": signal_ref,
                        "status": "contract_accepted",
                    }
                )
            except ValidationError as exc:
                failures[f"slow_loop:mining_stage:{decision.hypothesis_id}"] = (
                    str(exc),
                )
                staging.append(
                    {
                        "hypothesis_id": decision.hypothesis_id,
                        "status": "staging_failed",
                        "reasons": [str(exc)],
                    }
                )
        return {
            "candidate_refs": tuple(candidate_refs),
            "induction_case_ids": induction_case_ids,
            "validation_case_ids": validation_case_ids,
            "failures": failures,
            "staging": tuple(staging),
        }

    def _candidate_arguments_schema(self, *, clone: bool) -> dict[str, Any]:
        registered_functions = sorted(self.validator.deterministic_functions)
        schema: dict[str, Any] = {
            "type": "object",
            "required": ["spec", "tests"],
            "additionalProperties": False,
            "properties": {
                "spec": {
                    "type": "object",
                    "required": [
                        "signal_id",
                        "version",
                        "category",
                        "definition",
                        "schema",
                        "execution",
                        "raw_retrieval",
                        "evidence_policy",
                        "parameters",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "signal_id": {"type": "string"},
                        "version": {"type": "integer", "minimum": 1},
                        "category": {"type": "string"},
                        "definition": {
                            "type": "object",
                            "required": ["description"],
                            "properties": {"description": {"type": "string"}},
                            "additionalProperties": False,
                        },
                        "schema": {
                            "const": {
                                "value": {
                                    "type": "categorical",
                                    "values": [
                                        "positive",
                                        "neutral",
                                        "negative",
                                        "unavailable",
                                    ],
                                },
                                "confidence": {"type": "float"},
                            }
                        },
                        "execution": {
                            "oneOf": [
                                {
                                    "type": "object",
                                    "required": ["type", "function"],
                                    "properties": {
                                        "type": {"const": "deterministic"},
                                        "function": {
                                            "enum": registered_functions,
                                        },
                                    },
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "required": ["type", "skill_file"],
                                    "properties": {
                                        "type": {"const": "llm"},
                                        "skill_file": {"type": "string"},
                                    },
                                    "additionalProperties": False,
                                },
                            ]
                        },
                        "raw_retrieval": {
                            "type": "object",
                            "required": ["source_types", "query_terms"],
                            "properties": {
                                "source_types": {
                                    "type": "array",
                                    "minItems": 1,
                                    "uniqueItems": True,
                                    "items": {"type": "string"},
                                },
                                "query_terms": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": 12,
                                    "uniqueItems": True,
                                    "items": {
                                        "type": "string",
                                        "minLength": 1,
                                        "maxLength": 80,
                                    },
                                },
                                "lookback_days": {
                                    "type": ["integer", "null"],
                                    "minimum": 1,
                                },
                                "comparison_requirement": {
                                    "type": ["string", "null"],
                                    "minLength": 1,
                                    "maxLength": 240,
                                },
                                "required_source_groups": {
                                    "type": "array",
                                    "uniqueItems": True,
                                    "items": {
                                        "type": "array",
                                        "minItems": 1,
                                        "uniqueItems": True,
                                        "items": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                    },
                                },
                                "minimum_distinct_periods": {
                                    "type": ["integer", "null"],
                                    "minimum": 1,
                                },
                                "minimum_period_span_days": {
                                    "type": ["integer", "null"],
                                    "minimum": 1,
                                },
                                "minimum_observations": {
                                    "type": ["integer", "null"],
                                    "minimum": 1,
                                },
                            },
                            "additionalProperties": False,
                        },
                        "evidence_policy": {
                            "const": {
                                "require_source": True,
                                "require_timestamp": True,
                                "require_exact_span": True,
                            }
                        },
                        "parameters": {"type": "object"},
                    },
                },
                "skill": {"type": ["string", "null"]},
                "tests": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["name", "as_of", "expected", "documents"],
                        "properties": {
                            "name": {"type": "string"},
                            "as_of": {
                                "type": "string",
                                "description": "timezone-aware ISO-8601 timestamp",
                            },
                            "company_id": {"type": "string"},
                            "expected": {
                                "enum": [
                                    "positive",
                                    "neutral",
                                    "negative",
                                    "unavailable",
                                ]
                            },
                            "documents": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "required": [
                                        "document_id",
                                        "source_type",
                                        "published_at",
                                        "available_at",
                                        "content",
                                    ],
                                },
                            },
                        },
                    },
                },
            },
            "constraints": [
                "deterministic execution cannot include skill",
                "LLM execution requires non-empty skill",
                "fixture source_type must be declared by raw_retrieval",
            ],
        }
        if clone:
            schema["required"] = ["signal_ref", "spec", "tests"]
            schema["properties"] = {
                "signal_ref": {"type": "string", "description": "exact stable ref"},
                **schema["properties"],
            }
            schema["properties"]["spec"]["properties"]["raw_retrieval"].pop(
                "required"
            )
            schema["constraints"] = [
                *schema["constraints"],
                "spec must preserve signal_id, category, description, evidence policy, execution type, and deterministic function",
                "spec.version must equal stable version plus one",
            ]
        return schema

    def _stage_from_tool(
        self,
        *,
        spec: Mapping[str, Any],
        skill: str | None,
        tests: Iterable[Mapping[str, Any]],
        origin: str,
        collected: list[str],
    ) -> str:
        candidate = self._candidate_spec_from_tool(spec)
        if origin == "mining" or origin.startswith("mining:"):
            try:
                stable = self.registry.latest_spec(candidate.signal_id)
            except ValidationError:
                stable = None
            if stable is not None:
                raise ValidationError(
                    "mined candidate duplicates stable Signal identity "
                    f"{stable.ref}; use the Update Agent for vNext"
                )
        signal_ref = self.registry.stage_candidate(
            candidate,
            skill=skill,
            tests=tests,
            origin=origin,
        )
        collected.append(signal_ref)
        return signal_ref

    @staticmethod
    def _candidate_spec_from_tool(spec: Mapping[str, Any]) -> SignalSpec:
        return candidate_signal_spec_from_dict(spec)

    def _run_signal_tests_tool(self, signal_ref: str) -> dict[str, Any]:
        spec, skill = self.registry.load_candidate(str(signal_ref))
        validation = self.validator.validate(
            spec,
            skill=skill,
            tests=self.registry.load_candidate_tests(str(signal_ref)),
        )
        return {
            "signal_ref": signal_ref,
            "accepted": validation.accepted,
            "reasons": list(validation.reasons),
        }


@dataclass(frozen=True)
class DualLoopResult:
    """One finite fast-loop group followed by one Signal slow loop."""

    plan_rounds: tuple[PlanRoundResult, ...]
    signal_evolution: SlowLoopResult


class DualLoopEvolutionEngine:
    """Run a finite Plan group, then commit one validated Signal transition."""

    def __init__(
        self,
        *,
        plan_engine: PlanEvolutionEngine,
        signal_engine: SignalEvolutionEngine,
        signal_registry: SignalRegistry,
        dataset: EvolutionDataset,
        plan_rounds_per_signal_cycle: int = 5,
        cycle_mode: str = "fast_then_slow",
        on_progress: ProgressCallback | None = None,
    ) -> None:
        if cycle_mode not in {"fast_then_slow", "slow_bootstrap"}:
            raise ValidationError("dual-loop cycle mode is invalid")
        if (
            (cycle_mode == "fast_then_slow" and plan_rounds_per_signal_cycle < 1)
            or (cycle_mode == "slow_bootstrap" and plan_rounds_per_signal_cycle != 0)
        ):
            raise ValidationError("dual-loop mode and Fast-round target conflict")
        self.plan_engine = plan_engine
        self.signal_engine = signal_engine
        self.signal_registry = signal_registry
        self.dataset = dataset
        self.plan_rounds_per_signal_cycle = plan_rounds_per_signal_cycle
        self.cycle_mode = cycle_mode
        self.on_progress = on_progress

    def run_cycle(
        self,
        *,
        cycle_id: int,
        completed_plan_rounds: int = 0,
    ) -> DualLoopResult:
        """Resume remaining Fast rounds, then automatically promote Slow output."""

        if not 0 <= completed_plan_rounds <= self.plan_rounds_per_signal_cycle:
            raise ValidationError("completed Fast-round count is outside cycle target")

        staged_validation = self.signal_engine.workspace.staged_slow_validation(cycle_id)
        if staged_validation is not None and (
            completed_plan_rounds != self.plan_rounds_per_signal_cycle
        ):
            raise ValidationError("staged Slow validation exists before Fast completion")
        learning_round_cutoff = (
            self.plan_engine.workspace.last_completed_round - completed_plan_rounds
        )
        if learning_round_cutoff < 0:
            raise ValidationError("Fast-loop learning cutoff cannot be negative")
        snapshot = (
            None
            if staged_validation is not None
            else self.signal_registry.freeze(
                learning_round_cutoff=learning_round_cutoff
            )
        )
        rounds: list[PlanRoundResult] = []
        if self.cycle_mode == "fast_then_slow":
            _emit_progress(
                self.on_progress,
                "fast_loop_started",
                cycle_mode=self.cycle_mode,
                completed_plan_rounds=completed_plan_rounds,
                target_plan_rounds=self.plan_rounds_per_signal_cycle,
                signal_registry_hash=(
                    str(staged_validation["input_registry_hash"])
                    if staged_validation is not None
                    else snapshot.registry_hash
                ),
            )
        if snapshot is None and completed_plan_rounds < self.plan_rounds_per_signal_cycle:
            raise ValidationError("Fast-loop resume requires an input Signal snapshot")
        for _ in range(
            completed_plan_rounds,
            self.plan_rounds_per_signal_cycle,
        ):
            round_id = self.plan_engine.workspace.last_completed_round + 1
            rounds.append(
                self.plan_engine.run_round(
                    round_id=round_id,
                    validation_cases=self.dataset.evolution_validation,
                    anchor_cases=self.dataset.anchor,
                    signal_snapshot=snapshot,  # type: ignore[arg-type]
                )
            )
        if snapshot is not None and self.signal_registry.version != snapshot.version:
            raise ValidationError("stable Signal definitions changed during fast loop")
        _emit_progress(
            self.on_progress,
            "slow_loop_started",
            cycle_mode=self.cycle_mode,
            completed_plan_rounds=self.plan_rounds_per_signal_cycle,
            target_plan_rounds=self.plan_rounds_per_signal_cycle,
        )
        signal_result = self.signal_engine.run_cycle(
            cycle_id=cycle_id,
            input_snapshot=snapshot,
        )
        _emit_progress(
            self.on_progress,
            "slow_loop_completed",
            mined_candidates=list(signal_result.mined_candidates),
            updated_candidates=list(signal_result.updated_candidates),
            validated_candidates=dict(signal_result.validated_candidates),
            promoted=list(signal_result.promoted),
            rejected={
                ref: list(reasons)
                for ref, reasons in signal_result.rejected.items()
            },
            input_registry_version=signal_result.input_registry_version,
            input_registry_hash=signal_result.input_registry_hash,
            output_registry_version=signal_result.output_registry_version,
            output_registry_hash=signal_result.output_registry_hash,
        )
        return DualLoopResult(
            plan_rounds=tuple(rounds),
            signal_evolution=signal_result,
        )
