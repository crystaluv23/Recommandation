"""Dual-loop evolution of adaptive Information Plans and versioned Signals."""

from __future__ import annotations

import fcntl
import hashlib
import html
import json
import math
import os
import random
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Generic, Iterable, Iterator, Mapping, Protocol, TypeVar

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    aggregate_capability_gaps,
    document_has_strong_issuer_match,
    EvidenceResolver,
    MAX_BASIC_INFO_REQUESTS,
    RawInfoRequest,
    RawInfoResolution,
)
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    LLMSignalRunner,
    SignalBatchResult,
    SignalExecutionType,
    SignalExecutor,
    SignalLearningEvent,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
    SIGNAL_CONTEXT_TAGS,
    default_deterministic_signal_functions,
    signal_result_model_view,
)


T = TypeVar("T")
ProgressCallback = Callable[[Mapping[str, Any]], None]
MAX_PREDICTOR_CONTEXT_UTF8_BYTES = 24_000
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]*$")
_IDENTITY_MASK_SENTINEL = "\ue000\ue001"
_MASKED_IDENTITY_VALUE = "[MASKED_COMPANY]"
_IDENTITY_NAME_SEPARATOR = re.compile(r"\s*(?:/|\||;|\n)\s*")
_IDENTITY_LEGAL_SUFFIX = re.compile(
    r"(?:[\s,]+(?:"
    r"inc(?:orporated)?|corp(?:oration)?|co(?:mpany)?|ltd|limited|plc|llc|"
    r"l\.?\s*p\.?|holdings?|group|n\.?\s*v\.?|s\.?\s*a\.?|"
    r"a\.?\s*g\.?|s\.?\s*e\.?)"
    r")\.?$",
    re.IGNORECASE,
)
_GENERIC_IDENTITY_LEADING_WORDS = frozenset(
    {
        "advanced",
        "american",
        "bank",
        "first",
        "general",
        "global",
        "high",
        "international",
        "national",
        "new",
        "north",
        "the",
        "united",
        "universal",
    }
)
_GENERIC_QUERY_WORDS = frozenset(
    {
        "actual",
        "and",
        "business",
        "company",
        "compare",
        "compared",
        "comparison",
        "change",
        "for",
        "from",
        "latest",
        "per",
        "recent",
        "the",
        "this",
        "versus",
        "with",
    }
)
_AMBIGUOUS_SHORT_IDENTITY_TERMS = frozenset(
    {
        "all",
        "and",
        "any",
        "are",
        "can",
        "for",
        "its",
        "new",
        "not",
        "now",
        "one",
        "our",
        "out",
        "see",
        "the",
        "two",
        "use",
        "was",
        "who",
        "you",
    }
)
_FORBIDDEN_BASIC_INFO_FIELDS = frozenset(
    {
        "ground_truth",
        "outcome",
        "outcome_label",
        "label",
        "is_surge",
        "magnitude_class",
        "realized_return",
        "realized_max_multiple",
        "future_price",
        "future_return",
        "post_outcome",
    }
)
MAX_BASIC_INFO_MODEL_CHARS = 32_000
_MODEL_VIEW_METADATA_FIELD = re.compile(
    r'"(?:retrieved_at|source|symbol)"\s*:\s*(?:"(?:\\.|[^"\\])*"|null|true|false|-?\d+(?:\.\d+)?)\s*,?',
    re.IGNORECASE,
)
_HTML_TAG = re.compile(r"<[^>]*>", re.DOTALL)
_NONVISIBLE_HTML_BLOCK = re.compile(
    r"<(?:ix:header|script|style)\b[^>]*>.*?</(?:ix:header|script|style)\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_HTML_PREFIX_FRAGMENT = re.compile(
    r"(?:\b(?:style|class|id|name|contextref|unitref|dimension|colspan|rowspan|scale)\s*=|"
    r"(?:font|background|border|padding|text-align)[-a-z]*\s*:|"
    r"(?:xbrli|xbrldi|ix|us-gaap|dei):|\b\d+(?:\.\d+)?pt\s*[\"']?)",
    re.IGNORECASE,
)
_HTML_SUFFIX_FRAGMENT = re.compile(r"^</?[A-Za-z][\w:.-]*(?:\s|$)")
_URL_VALUE = re.compile(r"https?://[^\s\"\\]+", re.IGNORECASE)
_FILING_BLOCK_TAGS = frozenset(
    {"div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th"}
)
_BUSINESS_PROFILE_TERM = re.compile(
    r"\b(?:company|business|products?|services?|customers?|markets?|operations?|"
    r"develop\w*|manufactur\w*|provid\w*|offer\w*|sell\w*|design\w*|"
    r"solutions?|technolog\w*|properties|leasing|insurance|pharmaceutical|"
    r"medicines?|drugs?|construction|airline|energy|semiconductor|resources?|"
    r"projects?|portfolio)\b",
    re.IGNORECASE,
)
_BUSINESS_PROFILE_BOILERPLATE = (
    "securities exchange commission",
    "available on our website",
    "not incorporated by reference",
    "voluntary disclosures",
    "federal securities laws",
    "annual report on form 10-k",
)


def _json_string_array(
    data: Mapping[str, Any],
    field_name: str,
    *,
    required: bool = True,
) -> tuple[str, ...]:
    """Read one JSON string array without accepting strings as iterables."""

    if field_name not in data:
        if required:
            raise ValidationError(f"{field_name} is required")
        return ()
    value = data[field_name]
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{field_name} must be an array")
    if any(not isinstance(item, str) for item in value):
        raise ValidationError(f"{field_name} must contain only strings")
    return tuple(value)


def _json_array(data: Mapping[str, Any], field_name: str) -> tuple[Any, ...]:
    """Read one JSON array while preserving typed object elements."""

    if field_name not in data:
        raise ValidationError(f"{field_name} is required")
    value = data[field_name]
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{field_name} must be an array")
    return tuple(value)


def _json_boolean(value: Any, field_name: str) -> bool:
    """Require a real JSON boolean rather than Python truthiness."""

    if type(value) is not bool:
        raise ValidationError(f"{field_name} must be a boolean")
    return value


def _normalized_projection_text(
    raw_text: str,
    *,
    raw_offset: int = 0,
    strip_market_metadata: bool = False,
) -> tuple[str, tuple[tuple[int, int, int, int], ...]]:
    """Return readable text plus compact projection-to-raw offset runs."""

    removed: list[tuple[int, int]] = list(
        (match.start(), match.end())
        for match in _NONVISIBLE_HTML_BLOCK.finditer(raw_text)
    )
    removed.extend(
        (match.start(), match.end()) for match in _HTML_TAG.finditer(raw_text)
    )
    first_close = raw_text.find(">")
    first_open = raw_text.find("<")
    if first_close >= 0 and (first_open < 0 or first_close < first_open):
        prefix = raw_text[:first_close]
        if _HTML_PREFIX_FRAGMENT.search(prefix):
            removed.append((0, first_close + 1))
    last_open = raw_text.rfind("<")
    last_close = raw_text.rfind(">")
    if last_open > last_close and _HTML_SUFFIX_FRAGMENT.match(raw_text[last_open:]):
        removed.append((last_open, len(raw_text)))
    if strip_market_metadata:
        removed.extend(
            (match.start(), match.end())
            for match in _MODEL_VIEW_METADATA_FIELD.finditer(raw_text)
        )
    removed.sort()
    merged: list[tuple[int, int]] = []
    for start, end in removed:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    chars: list[tuple[str, int, int]] = []
    cursor = 0
    for start, end in merged:
        for index in range(cursor, start):
            chars.append((raw_text[index], raw_offset + index, raw_offset + index + 1))
        chars.append((" ", raw_offset + start, raw_offset + end))
        cursor = end
    for index in range(cursor, len(raw_text)):
        chars.append((raw_text[index], raw_offset + index, raw_offset + index + 1))

    decoded_chars: list[tuple[str, int, int]] = []
    index = 0
    while index < len(chars):
        character, start, end = chars[index]
        if character == "&":
            for candidate_end in range(index + 1, min(len(chars), index + 16)):
                if chars[candidate_end][0] != ";":
                    continue
                candidate = "".join(
                    item[0] for item in chars[index : candidate_end + 1]
                )
                decoded = html.unescape(candidate)
                if len(decoded) == 1 and decoded != candidate:
                    decoded_chars.append(
                        (decoded, start, chars[candidate_end][2])
                    )
                    index = candidate_end + 1
                    break
            else:
                decoded_chars.append((character, start, end))
                index += 1
            continue
        decoded_chars.append((character, start, end))
        index += 1
    chars = decoded_chars

    normalized: list[tuple[str, int, int]] = []
    for character, start, end in chars:
        if character.isspace():
            if normalized and normalized[-1][0] == " ":
                previous = normalized[-1]
                normalized[-1] = (" ", previous[1], end)
            elif normalized:
                normalized.append((" ", start, end))
        else:
            normalized.append((character, start, end))
    while normalized and normalized[-1][0] == " ":
        normalized.pop()

    text_value = "".join(item[0] for item in normalized)
    runs: list[tuple[int, int, int, int]] = []
    for projection_index, (_character, raw_start, raw_end) in enumerate(normalized):
        if (
            runs
            and runs[-1][1] == projection_index
            and runs[-1][3] == raw_start
            and raw_end - raw_start == 1
            and runs[-1][3] - runs[-1][2] == runs[-1][1] - runs[-1][0]
        ):
            previous = runs[-1]
            runs[-1] = (previous[0], projection_index + 1, previous[2], raw_end)
        else:
            runs.append((projection_index, projection_index + 1, raw_start, raw_end))
    return text_value, tuple(runs)


def project_basic_info_bundle(
    bundle: Any,
    *,
    max_chars: int = MAX_BASIC_INFO_MODEL_CHARS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a bounded model view and durable projection lineage."""

    candidate_rows: list[list[tuple[dict[str, Any], dict[str, Any]]]] = []
    for resolution in bundle.requests:
        source_types = {item.casefold() for item in resolution.request.source_types}
        rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for span in resolution.context_spans:
            projected, runs = _normalized_projection_text(
                span.exact_text,
                raw_offset=span.start,
                strip_market_metadata=bool(
                    source_types & {"market_data", "historical_price", "price_daily", "prices"}
                ),
            )
            if not projected:
                continue
            clipped_runs = [
                (start, end, raw_start, raw_end)
                for start, end, raw_start, raw_end in runs
            ]
            projection_id = "projection_" + hashlib.sha256(
                json.dumps(
                    [span.document_id, span.content_hash, span.start, span.end, projected],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:24]
            rows.append(
                (
                    {
                        "projection_id": projection_id,
                        "document_id": span.document_id,
                        "available_at": span.available_at.isoformat(),
                        "exact_text": projected,
                    },
                    {
                        "projection_id": projection_id,
                        "document_id": span.document_id,
                        "content_hash": span.content_hash,
                        "projection_text": projected,
                        "raw_offset_runs": [list(item) for item in clipped_runs],
                    },
                )
            )
        candidate_rows.append(rows)

    selected_indices: list[list[int]] = [[] for _rows in candidate_rows]
    remaining = max_chars
    for request_index, rows in enumerate(candidate_rows):
        if rows and len(rows[0][0]["exact_text"]) <= remaining:
            selected_indices[request_index].append(0)
            remaining -= len(rows[0][0]["exact_text"])
    for request_index, rows in enumerate(candidate_rows):
        for row_index, (model_row, _audit_row) in enumerate(rows[1:], start=1):
            row_chars = len(model_row["exact_text"])
            if row_chars > remaining:
                continue
            selected_indices[request_index].append(row_index)
            remaining -= row_chars

    model_requests: list[dict[str, Any]] = []
    audit_entries: list[dict[str, Any]] = []
    for resolution, rows, indices in zip(
        bundle.requests,
        candidate_rows,
        selected_indices,
        strict=True,
    ):
        model_spans = [rows[index][0] for index in indices]
        audit_entries.extend(rows[index][1] for index in indices)
        available_count = len(rows)
        visible_count = len(model_spans)
        omitted_count = available_count - visible_count
        if resolution.status != "resolved":
            projection_status = "unavailable"
        elif available_count == 0:
            projection_status = "no_context_spans"
        elif visible_count == 0:
            projection_status = "omitted_context_budget"
        elif omitted_count:
            projection_status = "partial_context_budget"
        else:
            projection_status = "complete"
        model_requests.append(
            {
                "request": resolution.request.to_dict(),
                "status": resolution.status,
                "projections": model_spans,
                "projection_status": projection_status,
                "available_projection_count": available_count,
                "visible_projection_count": visible_count,
                "omitted_projection_count": omitted_count,
                "data_gap": resolution.gap.to_dict() if resolution.gap else None,
            }
        )
    return (
        {"requests": model_requests, "max_normalized_characters": max_chars},
        {
            "schema_version": "basic-info-model-projection-v1",
            "max_normalized_characters": max_chars,
            "entries": audit_entries,
        },
    )


def _same_artifact_path(reference: Any, expected: Path) -> bool:
    """Compare durable artifact refs by resolved target, not path spelling."""

    return isinstance(reference, str) and bool(reference) and (
        Path(reference).resolve() == expected.resolve()
    )


class ResearchDecision(str, Enum):
    """Research Controller decision after initial reasoning or batch reflection."""

    CONTINUE = "continue"
    FINALIZE = "finalize"


class MagnitudeClass(str, Enum):
    """Stage-2 class for a predicted or realized surge."""

    TWO_TO_THREE = "2-3x"
    THREE_TO_TEN = "3-10x"
    TEN_PLUS = "10x+"


class ConfidenceLevel(str, Enum):
    """Qualitative prediction confidence."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CandidateJudgment(str, Enum):
    """Fixed four-way Stage-1 opportunity judgment."""

    LIKELY = "likely"
    POSSIBLE = "possible"
    UNLIKELY = "unlikely"
    INSUFFICIENT_INFORMATION = "insufficient_information"

    @property
    def is_positive(self) -> bool:
        """Return the fixed binary projection used by Stage 2 and scoring."""

        return self in (CandidateJudgment.LIKELY, CandidateJudgment.POSSIBLE)


class RuntimeStopReason(str, Enum):
    """Why adaptive research stopped selecting more Signals."""

    FINALIZED = "finalized"
    NO_SIGNAL_MATCH = "no_signal_match"
    MAX_SIGNAL_ROUNDS = "max_signal_rounds"
    MAX_SIGNAL_CALLS = "max_signal_calls"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class AgentStep(Generic[T]):
    """One structured role result plus reported model usage."""

    value: T
    usage: AgentUsage = field(default_factory=AgentUsage)


@dataclass(frozen=True)
class BasicInfoPolicy:
    """Evolvable analyst-style requests for original point-in-time sources."""

    requests: tuple[RawInfoRequest, ...]

    def __post_init__(self) -> None:
        if not self.requests:
            raise ValidationError("basic info policy requires requests")
        if len(self.requests) > MAX_BASIC_INFO_REQUESTS:
            raise ValidationError("basic info policy cannot exceed 8 requests")
        request_ids = [item.request_id for item in self.requests]
        if len(set(request_ids)) != len(request_ids):
            raise ValidationError("basic info policy request ids must be unique")
        forbidden = [
            item.request_id
            for item in self.requests
            if any(
                _is_forbidden_basic_info_field(value)
                for value in (
                    item.request_id,
                    item.description,
                    *item.source_types,
                    item.query or "",
                )
            )
        ]
        if forbidden:
            raise ValidationError(
                "basic info policy cannot request outcome data: "
                + ", ".join(forbidden)
            )
        object.__setattr__(self, "requests", tuple(self.requests))

    def to_dict(self) -> dict[str, Any]:
        return {"requests": [item.to_dict() for item in self.requests]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BasicInfoPolicy":
        if "requests" in data:
            return cls(
                requests=tuple(
                    RawInfoRequest.from_dict(item) for item in data.get("requests", ())
                )
            )
        return cls(
            requests=tuple(
                _legacy_basic_info_request(str(item))
                for item in data.get("fields", ())
            )
        )


@dataclass(frozen=True)
class InformationPlan:
    """The four-part evolvable research strategy S=(B,H_init,H_reflect,H_analyse)."""

    plan_id: str
    parent_ids: tuple[str, ...]
    basic_info_policy: BasicInfoPolicy
    initial_research_skill: str
    reflection_skill: str
    analysis_prompt: str

    def __post_init__(self) -> None:
        _validate_id(self.plan_id, "plan_id")
        for parent_id in self.parent_ids:
            _validate_id(parent_id, "parent_id")
        if self.plan_id in self.parent_ids:
            raise ValidationError("information plan cannot be its own parent")
        for name in (
            "initial_research_skill",
            "reflection_skill",
            "analysis_prompt",
        ):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"information plan {name} must not be empty")
        object.__setattr__(self, "parent_ids", tuple(self.parent_ids))

    def canonical_dict(self) -> dict[str, Any]:
        """Return stable content for embedding and identity checks."""

        return {
            "basic_info": [
                item.to_dict() for item in self.basic_info_policy.requests
            ],
            "initial_research": " ".join(self.initial_research_skill.split()),
            "reflection": " ".join(self.reflection_skill.split()),
            "analysis": " ".join(self.analysis_prompt.split()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "parent_ids": list(self.parent_ids),
            "basic_info_policy": self.basic_info_policy.to_dict(),
            "initial_research_skill": self.initial_research_skill,
            "reflection_skill": self.reflection_skill,
            "analysis_prompt": self.analysis_prompt,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InformationPlan":
        return cls(
            plan_id=str(data["plan_id"]),
            parent_ids=tuple(str(item) for item in data.get("parent_ids", ())),
            basic_info_policy=BasicInfoPolicy.from_dict(
                dict(data["basic_info_policy"])
            ),
            initial_research_skill=str(data["initial_research_skill"]),
            reflection_skill=str(data["reflection_skill"]),
            analysis_prompt=str(data["analysis_prompt"]),
        )


@dataclass(frozen=True)
class ResearchEvidenceRef:
    """One typed, locally verifiable evidence reference in active v6 research."""

    kind: str
    claim: str
    projection_id: str | None = None
    exact_text: str | None = None
    signal_ref: str | None = None
    evidence_group: str | None = None
    evidence_index: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"basic_info", "signal"}:
            raise ValidationError("research evidence kind must be basic_info or signal")
        if not self.claim.strip() or len(self.claim) > 400:
            raise ValidationError("research evidence claim must contain 1-400 characters")
        if self.kind == "basic_info":
            if (
                not str(self.projection_id or "").strip()
                or not str(self.exact_text or "").strip()
                or self.signal_ref is not None
                or self.evidence_group is not None
                or self.evidence_index is not None
            ):
                raise ValidationError("basic_info evidence reference fields are invalid")
        elif (
            not str(self.signal_ref or "").strip()
            or self.evidence_group not in {"supporting", "counter"}
            or type(self.evidence_index) is not int
            or self.evidence_index < 0
            or self.projection_id is not None
            or self.exact_text is not None
        ):
            raise ValidationError("signal evidence reference fields are invalid")

    def to_dict(self) -> dict[str, Any]:
        if self.kind == "basic_info":
            return {
                "kind": self.kind,
                "claim": self.claim,
                "projection_id": self.projection_id,
                "exact_text": self.exact_text,
            }
        return {
            "kind": self.kind,
            "claim": self.claim,
            "signal_ref": self.signal_ref,
            "evidence_group": self.evidence_group,
            "evidence_index": self.evidence_index,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResearchEvidenceRef":
        kind = data.get("kind")
        if kind == "basic_info":
            required = {"kind", "claim", "projection_id", "exact_text"}
            if set(data) != required or any(
                not isinstance(data.get(name), str) for name in required
            ):
                raise ValidationError("basic_info evidence reference shape is invalid")
            return cls(
                kind=kind,
                claim=str(data["claim"]),
                projection_id=str(data["projection_id"]),
                exact_text=str(data["exact_text"]),
            )
        if kind == "signal":
            required = {
                "kind",
                "claim",
                "signal_ref",
                "evidence_group",
                "evidence_index",
            }
            if set(data) != required or any(
                not isinstance(data.get(name), str)
                for name in ("kind", "claim", "signal_ref", "evidence_group")
            ):
                raise ValidationError("signal evidence reference shape is invalid")
            return cls(
                kind=kind,
                claim=str(data["claim"]),
                signal_ref=str(data["signal_ref"]),
                evidence_group=str(data["evidence_group"]),
                evidence_index=data["evidence_index"],
            )
        raise ValidationError("research evidence reference has unknown kind")


@dataclass(frozen=True)
class ResearchState:
    """Complete Controller state after initial reasoning or batch reflection."""

    hypotheses: tuple[str, ...] = ()
    current_beliefs: tuple[str, ...] = ()
    supporting_evidence: tuple[ResearchEvidenceRef | str, ...] = ()
    contradictions: tuple[str, ...] = ()
    resolved_questions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    next_information_needs: tuple[str, ...] = ()
    decision: ResearchDecision = ResearchDecision.CONTINUE

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ResearchDecision):
            object.__setattr__(self, "decision", ResearchDecision(self.decision))
        for name in (
            "hypotheses",
            "current_beliefs",
            "contradictions",
            "resolved_questions",
            "open_questions",
            "next_information_needs",
        ):
            values = tuple(str(item) for item in getattr(self, name))
            if any(not item.strip() for item in values):
                raise ValidationError(f"research state {name} cannot contain blanks")
            object.__setattr__(self, name, values)
        evidence: list[ResearchEvidenceRef | str] = []
        for item in self.supporting_evidence:
            if isinstance(item, ResearchEvidenceRef):
                evidence.append(item)
            elif isinstance(item, str) and item.strip():
                evidence.append(item)
            else:
                raise ValidationError("research state supporting_evidence is invalid")
        object.__setattr__(self, "supporting_evidence", tuple(evidence))
        if self.decision is ResearchDecision.CONTINUE and not self.next_information_needs:
            raise ValidationError("continuing research requires next information needs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypotheses": list(self.hypotheses),
            "current_beliefs": list(self.current_beliefs),
            "supporting_evidence": [
                item.to_dict() if isinstance(item, ResearchEvidenceRef) else item
                for item in self.supporting_evidence
            ],
            "contradictions": list(self.contradictions),
            "resolved_questions": list(self.resolved_questions),
            "open_questions": list(self.open_questions),
            "next_information_needs": list(self.next_information_needs),
            "decision": self.decision.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResearchState":
        required = {
            "hypotheses",
            "current_beliefs",
            "supporting_evidence",
            "contradictions",
            "resolved_questions",
            "open_questions",
            "next_information_needs",
            "decision",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "ResearchState is missing fields: " + ", ".join(missing)
            )
        if not isinstance(data["decision"], str):
            raise ValidationError("ResearchState decision must be text")
        return cls(
            hypotheses=_json_string_array(data, "hypotheses"),
            current_beliefs=_json_string_array(data, "current_beliefs"),
            supporting_evidence=tuple(
                ResearchEvidenceRef.from_dict(item)
                if isinstance(item, Mapping)
                else item
                for item in _json_array(data, "supporting_evidence")
            ),
            contradictions=_json_string_array(data, "contradictions"),
            resolved_questions=_json_string_array(data, "resolved_questions"),
            open_questions=_json_string_array(data, "open_questions"),
            next_information_needs=_json_string_array(
                data, "next_information_needs"
            ),
            decision=ResearchDecision(data["decision"]),
        )


class ResearchController(Protocol):
    """Decides what information is needed before and after each Signal batch."""

    def initialize(
        self,
        plan: InformationPlan,
        basic_info: Mapping[str, Any],
    ) -> AgentStep[ResearchState]:
        """Run H_init over Basic Info."""

    def reflect(
        self,
        plan: InformationPlan,
        state: ResearchState,
        batch: SignalBatchResult,
    ) -> AgentStep[ResearchState]:
        """Run H_reflect once over the complete Signal batch."""


_SIGNAL_SELECTION_REASON_CODES = frozenset(
    {
        "answer_need",
        "confirm_hypothesis",
        "test_contradiction",
        "assess_applicability",
        "combine_evidence",
    }
)
_SIGNAL_SELECTION_ROLES = frozenset(
    {"primary", "confirmation", "contradiction", "coverage"}
)


@dataclass(frozen=True)
class SignalSelectionDecision:
    """Why one exact Signal should be applied in the current blind context."""

    signal_ref: str
    reason_code: str
    selection_reason: str
    applicability_hypothesis: str
    expected_role: str
    context_tags: tuple[str, ...] = ()
    target_need_indices: tuple[int, ...] = ()
    answer_scope: str | None = None
    residual_need: str | None = None

    def __post_init__(self) -> None:
        if self.reason_code not in _SIGNAL_SELECTION_REASON_CODES:
            raise ValidationError("unsupported Signal selection reason_code")
        if self.expected_role not in _SIGNAL_SELECTION_ROLES:
            raise ValidationError("unsupported Signal selection expected_role")
        for value, name, limit in (
            (self.selection_reason, "selection_reason", 240),
            (self.applicability_hypothesis, "applicability_hypothesis", 240),
        ):
            if not value.strip() or len(value) > limit:
                raise ValidationError(
                    f"Signal selection {name} must contain 1-{limit} characters"
                )
        if len(self.context_tags) > 4:
            raise ValidationError("Signal selection allows at most four context tags")
        normalized_tags: list[str] = []
        for item in self.context_tags:
            tag = re.sub(r"[^a-z0-9_:-]+", "_", str(item).casefold()).strip("_")
            if not tag or len(tag) > 48:
                raise ValidationError("Signal selection context tags are invalid")
            if tag not in SIGNAL_CONTEXT_TAGS:
                raise ValidationError("Signal selection context tag is not allowed")
            normalized_tags.append(tag)
        if len(set(normalized_tags)) != len(normalized_tags):
            raise ValidationError("Signal selection context tags must be unique")
        if (
            any(type(index) is not int or index < 0 for index in self.target_need_indices)
            or len(set(self.target_need_indices)) != len(self.target_need_indices)
            or len(self.target_need_indices) > 1
        ):
            raise ValidationError(
                "Signal selection target_need_indices must contain at most one "
                "unique non-negative integer"
            )
        if self.answer_scope is not None and self.answer_scope not in {
            "full",
            "partial",
        }:
            raise ValidationError(
                "Signal selection answer_scope must be full, partial, or null"
            )
        if self.reason_code != "answer_need" and (
            self.answer_scope is not None or self.residual_need is not None
        ):
            raise ValidationError(
                "non-answer Signal selection cannot carry answer scope or residual need"
            )
        if self.answer_scope == "partial":
            if (
                self.residual_need is None
                or not self.residual_need.strip()
                or len(self.residual_need) > 300
            ):
                raise ValidationError(
                    "partial Signal answer requires a 1-300 character residual need"
                )
        elif self.residual_need is not None:
            raise ValidationError(
                "Signal selection residual_need requires answer_scope=partial"
            )
        object.__setattr__(self, "context_tags", tuple(normalized_tags))
        object.__setattr__(self, "target_need_indices", tuple(self.target_need_indices))
        if self.residual_need is not None:
            object.__setattr__(self, "residual_need", self.residual_need.strip())

    def to_dict(self) -> dict[str, Any]:
        value = {
            "signal_ref": self.signal_ref,
            "reason_code": self.reason_code,
            "selection_reason": self.selection_reason,
            "applicability_hypothesis": self.applicability_hypothesis,
            "expected_role": self.expected_role,
            "context_tags": list(self.context_tags),
            "target_need_indices": list(self.target_need_indices),
        }
        if self.answer_scope is not None:
            value["answer_scope"] = self.answer_scope
            value["residual_need"] = self.residual_need
        return value

    def to_learning_dict(self) -> dict[str, Any]:
        """Project the routing decision onto the stable learning-event schema."""

        return {
            "signal_ref": self.signal_ref,
            "reason_code": self.reason_code,
            "selection_reason": self.selection_reason,
            "applicability_hypothesis": self.applicability_hypothesis,
            "expected_role": self.expected_role,
            "context_tags": list(self.context_tags),
            "target_need_indices": list(self.target_need_indices),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalSelectionDecision":
        required = {
            "signal_ref",
            "reason_code",
            "selection_reason",
            "applicability_hypothesis",
            "expected_role",
            "context_tags",
        }
        optional = {"target_need_indices", "answer_scope", "residual_need"}
        if not required.issubset(data) or set(data) - required - optional:
            raise ValidationError(
                "Signal selection requires: " + ", ".join(sorted(required))
                + "; optional target_need_indices"
            )
        raw_target_indices = data.get("target_need_indices", ())
        if not isinstance(raw_target_indices, (list, tuple)):
            raise ValidationError(
                "Signal selection target_need_indices must be an integer array"
            )
        if ("answer_scope" in data) != ("residual_need" in data):
            raise ValidationError(
                "Signal selection answer_scope and residual_need must appear together"
            )
        return cls(
            signal_ref=str(data["signal_ref"]),
            reason_code=str(data["reason_code"]),
            selection_reason=str(data["selection_reason"]),
            applicability_hypothesis=str(data["applicability_hypothesis"]),
            expected_role=str(data["expected_role"]),
            context_tags=_json_string_array(data, "context_tags"),
            target_need_indices=tuple(raw_target_indices),
            answer_scope=(
                str(data["answer_scope"])
                if data.get("answer_scope") is not None
                else None
            ),
            residual_need=(
                str(data["residual_need"])
                if data.get("residual_need") is not None
                else None
            ),
        )

    @classmethod
    def legacy(cls, signal_ref: str) -> "SignalSelectionDecision":
        """Restore pre-learning committed trajectories without inventing intent."""

        return cls(
            signal_ref=signal_ref,
            reason_code="answer_need",
            selection_reason="Legacy trajectory did not persist a selection reason.",
            applicability_hypothesis=(
                "Legacy trajectory did not persist an applicability hypothesis."
            ),
            expected_role="primary",
        )


class SignalRetrievalAgent(Protocol):
    """Maps natural-language needs to existing frozen Signal refs."""

    def select(
        self,
        information_needs: tuple[str, ...],
        signal_registry: FrozenSignalRegistry,
        prior_signal_fingerprints: Mapping[str, tuple[str, ...]],
        prior_signal_results: Mapping[str, Mapping[str, Any]],
        eligible_signal_refs: tuple[str, ...] | None = None,
        research_state: ResearchState | None = None,
        prior_context_tags: tuple[str, ...] = (),
    ) -> AgentStep[tuple[SignalSelectionDecision, ...]]:
        """Return a reasoned unique batch using needs and bounded applicability state."""


@dataclass(frozen=True)
class BlindPrediction:
    """Saved label-free two-stage Predictor output."""

    is_surge: bool
    candidate_judgment: CandidateJudgment
    magnitude: MagnitudeClass | None
    confidence: ConfidenceLevel
    key_reasons: tuple[str, ...]
    uncertainties: tuple[str, ...]
    session_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.is_surge, bool):
            raise ValidationError("BlindPrediction is_surge must be boolean")
        if not isinstance(self.candidate_judgment, CandidateJudgment):
            try:
                object.__setattr__(
                    self,
                    "candidate_judgment",
                    CandidateJudgment(self.candidate_judgment),
                )
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "BlindPrediction candidate_judgment must be likely, possible, "
                    "unlikely, or insufficient_information"
                ) from exc
        if self.is_surge is not self.candidate_judgment.is_positive:
            raise ValidationError(
                "BlindPrediction candidate_judgment does not match is_surge"
            )
        if self.is_surge and self.magnitude is None:
            raise ValidationError("surge prediction requires magnitude class")
        if not self.is_surge and self.magnitude is not None:
            raise ValidationError("non-surge prediction cannot include magnitude")
        if self.magnitude is not None and not isinstance(self.magnitude, MagnitudeClass):
            object.__setattr__(self, "magnitude", MagnitudeClass(self.magnitude))
        if not isinstance(self.confidence, ConfidenceLevel):
            object.__setattr__(self, "confidence", ConfidenceLevel(self.confidence))
        if not self.session_id.strip():
            raise ValidationError("blind prediction requires session_id")
        if not self.key_reasons:
            raise ValidationError("blind prediction requires key reasons")
        object.__setattr__(self, "key_reasons", tuple(self.key_reasons))
        object.__setattr__(self, "uncertainties", tuple(self.uncertainties))

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_surge": self.is_surge,
            "candidate_judgment": self.candidate_judgment.value,
            "magnitude": self.magnitude.value if self.magnitude else None,
            "confidence": {"level": self.confidence.value},
            "key_reasons": list(self.key_reasons),
            "uncertainties": list(self.uncertainties),
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BlindPrediction":
        required = {
            "is_surge",
            "candidate_judgment",
            "magnitude",
            "confidence",
            "key_reasons",
            "uncertainties",
            "session_id",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "BlindPrediction is missing fields: " + ", ".join(missing)
            )
        confidence = data["confidence"]
        if not isinstance(confidence, Mapping) or set(confidence) != {"level"}:
            raise ValidationError(
                "BlindPrediction confidence requires exactly a level field"
            )
        confidence_value = confidence["level"]
        if not isinstance(confidence_value, str):
            raise ValidationError("BlindPrediction confidence level must be text")
        if not isinstance(data["session_id"], str):
            raise ValidationError("BlindPrediction session_id must be text")
        if not isinstance(data["candidate_judgment"], str):
            raise ValidationError(
                "BlindPrediction candidate_judgment must be text"
            )
        magnitude = data.get("magnitude")
        if magnitude is not None and not isinstance(magnitude, str):
            raise ValidationError("BlindPrediction magnitude must be text or null")
        return cls(
            is_surge=_json_boolean(data["is_surge"], "BlindPrediction is_surge"),
            candidate_judgment=data["candidate_judgment"],
            magnitude=MagnitudeClass(str(magnitude)) if magnitude else None,
            confidence=ConfidenceLevel(confidence_value),
            key_reasons=_json_string_array(data, "key_reasons"),
            uncertainties=_json_string_array(data, "uncertainties"),
            session_id=data["session_id"],
        )


@dataclass(frozen=True)
class GroundTruth:
    """Continuous realized multiple plus deterministic two-stage labels."""

    realized_max_multiple: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.realized_max_multiple) or self.realized_max_multiple < 0:
            raise ValidationError("realized_max_multiple must be finite and non-negative")

    @property
    def is_surge(self) -> bool:
        return self.realized_max_multiple >= 2.0

    @property
    def magnitude(self) -> MagnitudeClass | None:
        if not self.is_surge:
            return None
        if self.realized_max_multiple < 3.0:
            return MagnitudeClass.TWO_TO_THREE
        if self.realized_max_multiple < 10.0:
            return MagnitudeClass.THREE_TO_TEN
        return MagnitudeClass.TEN_PLUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "realized_max_multiple": self.realized_max_multiple,
            "is_surge": self.is_surge,
            "magnitude": self.magnitude.value if self.magnitude else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GroundTruth":
        return cls(realized_max_multiple=float(data["realized_max_multiple"]))


_CANDIDATE_JUDGMENT_FEEDBACK: Mapping[
    tuple[CandidateJudgment, bool], tuple[str, str]
] = {
    (CandidateJudgment.LIKELY, True): (
        "strong_correct_positive",
        "The likely judgment was binary-correct for the realized surge; inspect "
        "which source-backed positive evidence made the strong call work.",
    ),
    (CandidateJudgment.POSSIBLE, True): (
        "correct_positive_conservative",
        "The possible judgment was binary-correct but conservative relative to "
        "the realized surge; inspect whether source-backed positive evidence was "
        "underweighted. The realized outcome alone does not prove that likely was "
        "the calibrated ex-ante category.",
    ),
    (CandidateJudgment.UNLIKELY, True): (
        "severe_false_negative",
        "The unlikely judgment missed a realized surge; identify contrary evidence "
        "that was overweighted and positive evidence that was ignored.",
    ),
    (CandidateJudgment.INSUFFICIENT_INFORMATION, True): (
        "false_negative_information_gap",
        "The insufficient-information judgment missed a realized surge; identify "
        "which point-in-time evidence was absent, not acquired, or not converted "
        "into a usable Signal.",
    ),
    (CandidateJudgment.UNLIKELY, False): (
        "strong_correct_negative",
        "The unlikely judgment was binary-correct for the realized non-surge; "
        "inspect which source-backed counter-evidence made the rejection work.",
    ),
    (CandidateJudgment.INSUFFICIENT_INFORMATION, False): (
        "correct_negative_information_gap",
        "The insufficient-information judgment was binary-correct for the realized "
        "non-surge, but still exposes an evidence-coverage gap; improve acquisition "
        "where possible without manufacturing certainty.",
    ),
    (CandidateJudgment.POSSIBLE, False): (
        "false_positive",
        "The possible judgment was a false positive; identify speculative or noisy "
        "positive evidence and counter-evidence that should have constrained it.",
    ),
    (CandidateJudgment.LIKELY, False): (
        "severe_overconfident_false_positive",
        "The likely judgment was an overconfident false positive; identify the "
        "unsupported inference or ignored counter-evidence behind the strong call.",
    ),
}


def candidate_judgment_feedback(
    prediction: BlindPrediction,
    ground_truth: GroundTruth,
) -> dict[str, Any]:
    """Derive fixed label-revealed feedback without changing binary fitness."""

    assessment, guidance = _CANDIDATE_JUDGMENT_FEEDBACK[
        (prediction.candidate_judgment, ground_truth.is_surge)
    ]
    return {
        "candidate_judgment": prediction.candidate_judgment.value,
        "predicted_binary_label": (
            "surge" if prediction.is_surge else "non_surge"
        ),
        "true_binary_label": "surge" if ground_truth.is_surge else "non_surge",
        "binary_correct": prediction.is_surge == ground_truth.is_surge,
        "assessment": assessment,
        "reflection_guidance": guidance,
    }


@dataclass(frozen=True)
class PredictionSelfReflection:
    """Post-hoc usability feedback produced only after label reveal."""

    correct: bool
    decision_drivers: tuple[str, ...] = ()
    why_prediction_failed: tuple[str, ...] = ()
    misleading_signals: tuple[str, ...] = ()
    ignored_evidence: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    plan_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "decision_drivers",
            "why_prediction_failed",
            "misleading_signals",
            "ignored_evidence",
            "missing_information",
            "plan_issues",
        ):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_outcome": {"correct": self.correct},
            "decision_drivers": list(self.decision_drivers),
            "why_prediction_failed": list(self.why_prediction_failed),
            "misleading_signals": list(self.misleading_signals),
            "ignored_evidence": list(self.ignored_evidence),
            "missing_information": list(self.missing_information),
            "plan_issues": list(self.plan_issues),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PredictionSelfReflection":
        required = {
            "prediction_outcome",
            "why_prediction_failed",
            "misleading_signals",
            "ignored_evidence",
            "missing_information",
            "plan_issues",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "PredictionSelfReflection is missing fields: "
                + ", ".join(missing)
            )
        outcome_value = data["prediction_outcome"]
        if not isinstance(outcome_value, Mapping) or set(outcome_value) != {"correct"}:
            raise ValidationError(
                "prediction_outcome requires exactly a correct field"
            )
        return cls(
            correct=_json_boolean(
                outcome_value["correct"],
                "PredictionSelfReflection correct",
            ),
            decision_drivers=(
                _json_string_array(data, "decision_drivers")
                if "decision_drivers" in data
                else ()
            ),
            why_prediction_failed=_json_string_array(
                data, "why_prediction_failed"
            ),
            misleading_signals=_json_string_array(data, "misleading_signals"),
            ignored_evidence=_json_string_array(data, "ignored_evidence"),
            missing_information=_json_string_array(data, "missing_information"),
            plan_issues=_json_string_array(data, "plan_issues"),
        )


class BlindPredictor(Protocol):
    """Same adapter performs label-free prediction and label-revealed reflection."""

    def predict(self, final_context: Mapping[str, Any]) -> AgentStep[BlindPrediction]:
        """Predict without label, identity leakage, or web tools."""

    def reflect(
        self,
        original_context: Mapping[str, Any],
        original_prediction: BlindPrediction,
        ground_truth: GroundTruth,
    ) -> AgentStep[PredictionSelfReflection]:
        """Reflect in the saved prediction session after truth is revealed."""


@dataclass(frozen=True)
class SignalRound:
    """One need-selection-execution batch in a research trajectory."""

    information_needs: tuple[str, ...]
    selections: tuple[SignalSelectionDecision, ...]
    batch: SignalBatchResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "selections", tuple(self.selections))
        selected = self.selected_signals
        executed = tuple(result.ref for result in self.batch.results)
        if len(set(selected)) != len(selected):
            raise ValidationError("Signal round selections must be unique")
        if executed != selected:
            raise ValidationError(
                "Signal round must preserve one selection decision per result"
            )

    @property
    def selected_signals(self) -> tuple[str, ...]:
        return tuple(item.signal_ref for item in self.selections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "information_needs": list(self.information_needs),
            "selected_signals": list(self.selected_signals),
            "selections": [item.to_dict() for item in self.selections],
            "batch": {
                "results": [result.to_dict() for result in self.batch.results],
                "signal_calls": self.batch.signal_calls,
                "usage": _usage_to_dict(self.batch.usage),
                "resolutions": [
                    item.to_dict() for item in self.batch.resolutions
                ],
                "document_fingerprints": {
                    ref: list(value)
                    for ref, value in self.batch.document_fingerprints.items()
                },
                "skipped_unchanged_refs": list(
                    self.batch.skipped_unchanged_refs
                ),
            },
        }

    def to_model_context_dict(self) -> dict[str, Any]:
        """Return semantic Signal evidence without cache-variant usage metadata."""

        return {
            "information_needs": list(self.information_needs),
            "selected_signals": list(self.selected_signals),
            "selections": [item.to_dict() for item in self.selections],
            "batch": {
                "results": [result.to_dict() for result in self.batch.results],
                "signal_calls": self.batch.signal_calls,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalRound":
        batch = dict(data["batch"])
        return cls(
            information_needs=tuple(
                str(item) for item in data.get("information_needs", ())
            ),
            selections=(
                tuple(
                    SignalSelectionDecision.from_dict(item)
                    for item in data.get("selections", ())
                )
                if "selections" in data
                else tuple(
                    SignalSelectionDecision.legacy(str(item))
                    for item in data.get("selected_signals", ())
                )
            ),
            batch=SignalBatchResult(
                results=tuple(
                    SignalResult.from_dict(item) for item in batch.get("results", ())
                ),
                signal_calls=int(batch.get("signal_calls", 0)),
                usage=_usage_from_dict(dict(batch.get("usage", {}))),
                resolutions=tuple(
                    RawInfoResolution.from_dict(item)
                    for item in batch.get("resolutions", ())
                ),
                document_fingerprints={
                    str(ref): tuple(str(item) for item in value)
                    for ref, value in dict(
                        batch.get("document_fingerprints", {})
                    ).items()
                },
                skipped_unchanged_refs=tuple(
                    str(item)
                    for item in batch.get("skipped_unchanged_refs", ())
                ),
            ),
        )


@dataclass(frozen=True)
class RuntimeLimits:
    """Fixed engineering guards, not evolvable research logic."""

    max_signal_rounds: int = 8
    max_signal_calls: int = 20
    max_llm_calls: int = 30
    max_tokens: int = 160_000
    max_cost: float = 20.0
    max_signals_per_round: int = 4
    max_llm_signals_per_round: int = 2
    finalization_token_reserve: int = 64_000

    def __post_init__(self) -> None:
        if min(
            self.max_signal_rounds,
            self.max_signal_calls,
            self.max_llm_calls,
            self.max_tokens,
            self.max_signals_per_round,
            self.max_llm_signals_per_round,
            self.finalization_token_reserve,
        ) < 1:
            raise ValidationError("runtime count and token limits must be positive")
        if self.max_llm_calls < 3:
            raise ValidationError("runtime requires at least three LLM calls")
        if self.max_llm_signals_per_round > self.max_signals_per_round:
            raise ValidationError("LLM Signal round cap cannot exceed total Signal cap")
        if self.finalization_token_reserve >= self.max_tokens:
            raise ValidationError("finalization token reserve must be below max_tokens")
        if self.max_cost <= 0:
            raise ValidationError("runtime max_cost must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_signal_rounds": self.max_signal_rounds,
            "max_signal_calls": self.max_signal_calls,
            "max_llm_calls": self.max_llm_calls,
            "max_tokens": self.max_tokens,
            "max_cost": self.max_cost,
            "max_signals_per_round": self.max_signals_per_round,
            "max_llm_signals_per_round": self.max_llm_signals_per_round,
            "finalization_token_reserve": self.finalization_token_reserve,
        }


@dataclass(frozen=True)
class RuntimeUsage:
    """Complete usage accumulated by one Information Plan execution."""

    signal_rounds: int
    signal_calls: int
    model: AgentUsage

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_rounds": self.signal_rounds,
            "signal_calls": self.signal_calls,
            "model": _usage_to_dict(self.model),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimeUsage":
        return cls(
            signal_rounds=int(data["signal_rounds"]),
            signal_calls=int(data["signal_calls"]),
            model=_usage_from_dict(dict(data["model"])),
        )


@dataclass(frozen=True)
class ExecutionTrajectory:
    """Complete auditable Plan execution for one company."""

    company_id: str
    prediction_time: datetime
    basic_info: Mapping[str, Any]
    initial_state: ResearchState
    signal_rounds: tuple[SignalRound, ...]
    final_state: ResearchState
    final_context: Mapping[str, Any]
    prediction: BlindPrediction
    prediction_ref: str
    ground_truth: GroundTruth
    self_reflection: PredictionSelfReflection
    stop_reason: RuntimeStopReason
    usage: RuntimeUsage
    case_id: str = ""
    termination_trigger: RuntimeStopReason | None = None
    basic_info_projection: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_id(self.company_id, "company_id")
        resolved_case_id = self.case_id or _default_case_id(
            self.company_id, self.prediction_time
        )
        _validate_id(resolved_case_id, "case_id")
        object.__setattr__(self, "case_id", resolved_case_id)
        if not self.prediction_ref.strip():
            raise ValidationError("execution trajectory requires persisted prediction ref")
        object.__setattr__(self, "basic_info", dict(self.basic_info))
        object.__setattr__(self, "basic_info_projection", dict(self.basic_info_projection))
        object.__setattr__(self, "signal_rounds", tuple(self.signal_rounds))
        object.__setattr__(self, "final_context", dict(self.final_context))
        if not isinstance(self.stop_reason, RuntimeStopReason):
            object.__setattr__(self, "stop_reason", RuntimeStopReason(self.stop_reason))
        if self.termination_trigger is not None and not isinstance(
            self.termination_trigger, RuntimeStopReason
        ):
            object.__setattr__(
                self,
                "termination_trigger",
                RuntimeStopReason(self.termination_trigger),
            )

    def to_dict(self) -> dict[str, Any]:
        value = {
            "case_id": self.case_id,
            "company_id": self.company_id,
            "prediction_time": self.prediction_time.isoformat(),
            "basic_info_bundle": dict(self.basic_info),
            "basic_info_projection": dict(self.basic_info_projection),
            "initial_state": self.initial_state.to_dict(),
            "signal_rounds": [item.to_dict() for item in self.signal_rounds],
            "final_state": self.final_state.to_dict(),
            "final_context": dict(self.final_context),
            "prediction": self.prediction.to_dict(),
            "prediction_ref": self.prediction_ref,
            "ground_truth": self.ground_truth.to_dict(),
            "candidate_judgment_feedback": candidate_judgment_feedback(
                self.prediction,
                self.ground_truth,
            ),
            "self_reflection": self.self_reflection.to_dict(),
            "stop_reason": self.stop_reason.value,
            "termination_trigger": (
                self.termination_trigger.value if self.termination_trigger else None
            ),
            "usage": self.usage.to_dict(),
        }
        return value

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionTrajectory":
        trajectory = cls(
            case_id=str(data.get("case_id", "")),
            company_id=str(data["company_id"]),
            prediction_time=datetime.fromisoformat(str(data["prediction_time"])),
            basic_info=dict(
                data.get("basic_info_bundle", data.get("basic_info", {}))
            ),
            basic_info_projection=dict(data.get("basic_info_projection", {})),
            initial_state=ResearchState.from_dict(dict(data["initial_state"])),
            signal_rounds=tuple(
                SignalRound.from_dict(item) for item in data.get("signal_rounds", ())
            ),
            final_state=ResearchState.from_dict(dict(data["final_state"])),
            final_context=dict(data.get("final_context", {})),
            prediction=BlindPrediction.from_dict(dict(data["prediction"])),
            prediction_ref=str(data["prediction_ref"]),
            ground_truth=GroundTruth.from_dict(dict(data["ground_truth"])),
            self_reflection=PredictionSelfReflection.from_dict(
                dict(data["self_reflection"])
            ),
            stop_reason=RuntimeStopReason(str(data["stop_reason"])),
            usage=RuntimeUsage.from_dict(dict(data["usage"])),
            termination_trigger=(
                RuntimeStopReason(str(data["termination_trigger"]))
                if data.get("termination_trigger")
                else None
            ),
        )
        serialized_feedback = data.get("candidate_judgment_feedback")
        if serialized_feedback is not None:
            if not isinstance(serialized_feedback, Mapping):
                raise ValidationError(
                    "candidate_judgment_feedback must be an object"
                )
            expected_feedback = candidate_judgment_feedback(
                trajectory.prediction,
                trajectory.ground_truth,
            )
            if dict(serialized_feedback) != expected_feedback:
                raise ValidationError(
                    "candidate_judgment_feedback does not match prediction and truth"
                )
        return trajectory


@dataclass(frozen=True)
class CaseReflectionEvidence:
    """Anonymous original post-hoc reflection retained in round meta-info."""

    case_index: int
    stop_reason: RuntimeStopReason
    termination_trigger: RuntimeStopReason | None
    candidate_judgment_feedback: Mapping[str, Any]
    self_reflection: PredictionSelfReflection

    def __post_init__(self) -> None:
        if self.case_index < 1:
            raise ValidationError("case reflection index must be positive")
        if not isinstance(self.stop_reason, RuntimeStopReason):
            object.__setattr__(
                self,
                "stop_reason",
                RuntimeStopReason(self.stop_reason),
            )
        if self.termination_trigger is not None and not isinstance(
            self.termination_trigger, RuntimeStopReason
        ):
            object.__setattr__(
                self,
                "termination_trigger",
                RuntimeStopReason(self.termination_trigger),
            )
        feedback = dict(self.candidate_judgment_feedback)
        expected_fields = {
            "candidate_judgment",
            "predicted_binary_label",
            "true_binary_label",
            "binary_correct",
            "assessment",
            "reflection_guidance",
        }
        if set(feedback) != expected_fields:
            raise ValidationError(
                "case reflection candidate-judgment feedback fields are invalid"
            )
        try:
            judgment = CandidateJudgment(str(feedback["candidate_judgment"]))
        except ValueError:
            raise ValidationError("case reflection candidate judgment is invalid")
        predicted_is_surge = judgment in {
            CandidateJudgment.LIKELY,
            CandidateJudgment.POSSIBLE,
        }
        if feedback["predicted_binary_label"] not in {"surge", "non_surge"}:
            raise ValidationError("case reflection predicted binary label is invalid")
        if feedback["true_binary_label"] not in {"surge", "non_surge"}:
            raise ValidationError("case reflection true binary label is invalid")
        _json_boolean(feedback["binary_correct"], "case reflection binary_correct")
        for field_name in ("assessment", "reflection_guidance"):
            if not isinstance(feedback[field_name], str):
                raise ValidationError(
                    f"case reflection {field_name} must be a string"
                )
        true_is_surge = feedback["true_binary_label"] == "surge"
        assessment, guidance = _CANDIDATE_JUDGMENT_FEEDBACK[
            (judgment, true_is_surge)
        ]
        expected_feedback = {
            "candidate_judgment": judgment.value,
            "predicted_binary_label": (
                "surge" if predicted_is_surge else "non_surge"
            ),
            "true_binary_label": "surge" if true_is_surge else "non_surge",
            "binary_correct": predicted_is_surge == true_is_surge,
            "assessment": assessment,
            "reflection_guidance": guidance,
        }
        if feedback != expected_feedback:
            raise ValidationError(
                "case reflection feedback is not the deterministic four-way record"
            )
        object.__setattr__(self, "candidate_judgment_feedback", feedback)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_index": self.case_index,
            "stop_reason": self.stop_reason.value,
            "termination_trigger": (
                self.termination_trigger.value if self.termination_trigger else None
            ),
            "candidate_judgment_feedback": dict(
                self.candidate_judgment_feedback
            ),
            "self_reflection": self.self_reflection.to_dict(),
        }

    @classmethod
    def from_trajectory(
        cls,
        trajectory: ExecutionTrajectory,
        *,
        case_index: int,
    ) -> "CaseReflectionEvidence":
        """Build the identity-free layer from one immutable trajectory."""

        return cls(
            case_index=case_index,
            stop_reason=trajectory.stop_reason,
            termination_trigger=trajectory.termination_trigger,
            candidate_judgment_feedback=candidate_judgment_feedback(
                trajectory.prediction,
                trajectory.ground_truth,
            ),
            self_reflection=trajectory.self_reflection,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CaseReflectionEvidence":
        required = {
            "case_index",
            "stop_reason",
            "termination_trigger",
            "candidate_judgment_feedback",
            "self_reflection",
        }
        if set(data) != required:
            raise ValidationError("case reflection evidence fields are invalid")
        feedback = data["candidate_judgment_feedback"]
        reflection = data["self_reflection"]
        if not isinstance(feedback, Mapping) or not isinstance(reflection, Mapping):
            raise ValidationError("case reflection evidence objects are invalid")
        return cls(
            case_index=int(data["case_index"]),
            stop_reason=RuntimeStopReason(str(data["stop_reason"])),
            termination_trigger=(
                RuntimeStopReason(str(data["termination_trigger"]))
                if data["termination_trigger"] is not None
                else None
            ),
            candidate_judgment_feedback=dict(feedback),
            self_reflection=PredictionSelfReflection.from_dict(dict(reflection)),
        )


class RuntimeBudgetExceeded(ValidationError):
    """Raised when request preflight or completed usage reaches a hard limit."""

    def __init__(
        self,
        message: str,
        usage: AgentUsage = AgentUsage(),
    ) -> None:
        self.usage = usage
        super().__init__(message)


class EvolutionControlFlow(RuntimeError):
    """Base for pauses that must propagate beyond candidate diagnostics."""


class CandidateExecutionRejected(ValidationError):
    """One candidate cannot continue after bounded structured correction."""

    def __init__(
        self,
        stage: str,
        message: str,
        usage: AgentUsage = AgentUsage(),
    ) -> None:
        self.stage = str(stage)
        self.usage = usage
        super().__init__(message)


class RoundPaused(EvolutionControlFlow):
    """No valid evolutionary progress is possible under the frozen inputs."""

    def __init__(self, round_id: int, reason: str, checkpoint_ref: str) -> None:
        self.round_id = int(round_id)
        self.reason = str(reason)
        self.checkpoint_ref = str(checkpoint_ref)
        super().__init__(f"round {round_id} paused: {reason}")


class SharedEvaluationDataUnavailable(EvolutionControlFlow):
    """Shared point-in-time inputs cannot currently support one exact round."""

    def __init__(
        self,
        round_id: int,
        case_reasons: Mapping[str, str],
        *,
        retryable: bool,
        checkpoint_ref: str = "",
    ) -> None:
        self.round_id = int(round_id)
        self.case_reasons = {
            str(case_id): str(reason)
            for case_id, reason in case_reasons.items()
        }
        self.retryable = bool(retryable)
        self.checkpoint_ref = str(checkpoint_ref)
        super().__init__(
            f"round {round_id} shared evaluation data unavailable: "
            + ", ".join(
                f"{case_id}={reason}"
                for case_id, reason in self.case_reasons.items()
            )
        )


    def to_dict(self) -> dict[str, Any]:
        """Return the secret-free process-control payload."""

        return {
            "status": "shared_evaluation_data_unavailable",
            "round_id": self.round_id,
            "case_reasons": dict(self.case_reasons),
            "retryable": self.retryable,
            "checkpoint_ref": self.checkpoint_ref,
        }


class SlowLoopDataUnavailable(EvolutionControlFlow):
    """A retryable source failure interrupted Slow case preparation."""

    def __init__(self, case_ref: str, reason: str) -> None:
        self.case_ref = str(case_ref)
        self.reason = str(reason)
        self.retryable = True
        super().__init__(f"Slow profile data unavailable: {case_ref}={reason}")


def execute_information_plan(
    *,
    plan: InformationPlan,
    company_id: str,
    case_id: str | None = None,
    company_basic_source: Mapping[str, Any],
    prediction_time: datetime,
    signal_registry: FrozenSignalRegistry,
    signal_executor: SignalExecutor,
    controller: ResearchController,
    signal_agent: SignalRetrievalAgent,
    predictor: BlindPredictor,
    prediction_sink: Callable[
        [str, datetime, Mapping[str, Any], BlindPrediction], str
    ],
    ground_truth_provider: Callable[[str], GroundTruth],
    limits: RuntimeLimits = RuntimeLimits(),
) -> ExecutionTrajectory:
    """Execute one adaptive Plan and persist its prediction before label reveal."""

    _validate_id(company_id, "company_id")
    _require_aware_datetime(prediction_time, "prediction_time")
    resolved_case_id = case_id or _default_case_id(company_id, prediction_time)
    _validate_id(resolved_case_id, "case_id")
    basic_info_bundle = signal_executor.resolver.resolve_basic_info(
        plan.basic_info_policy.requests,
        company_id=company_id,
        identity=company_basic_source,
        as_of=prediction_time,
    )
    basic_info, basic_info_projection = project_basic_info_bundle(basic_info_bundle)
    source_aliases = company_basic_source.get("identity_aliases", ())
    if isinstance(source_aliases, str):
        source_aliases = (source_aliases,)
    source_aliases = (
        *source_aliases,
        *(
            str(company_basic_source[key])
            for key in ("company_name", "ticker", "symbol")
            if company_basic_source.get(key)
        ),
    )
    model_usage = AgentUsage()
    _set_request_token_budget(controller, limits.max_tokens)
    _set_evaluation_context(controller, prediction_time)
    initial_step = controller.initialize(plan, basic_info)
    model_usage = _consume_model_step(model_usage, initial_step.usage, limits)
    initial_state = initial_step.value
    state = initial_state
    rounds: list[SignalRound] = []
    signal_calls = 0
    stop_reason = RuntimeStopReason.FINALIZED
    termination_trigger: RuntimeStopReason | None = None
    signal_fingerprints: dict[str, tuple[str, ...]] = {}
    prior_signal_results: dict[str, Mapping[str, Any]] = {}

    while state.decision is ResearchDecision.CONTINUE:
        if len(rounds) >= limits.max_signal_rounds:
            termination_trigger = RuntimeStopReason.MAX_SIGNAL_ROUNDS
            break
        if signal_calls >= limits.max_signal_calls:
            termination_trigger = RuntimeStopReason.MAX_SIGNAL_CALLS
            break
        if model_usage.llm_calls + 4 > limits.max_llm_calls:
            termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
            break
        if model_usage.tokens >= limits.max_tokens - limits.finalization_token_reserve:
            termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
            break

        eligible_signal_refs = tuple(
            spec.ref
            for spec in signal_registry.specs
            if spec.ref not in signal_fingerprints
        )
        if not eligible_signal_refs:
            termination_trigger = RuntimeStopReason.NO_SIGNAL_MATCH
            break

        _set_request_token_budget(
            signal_agent,
            limits.max_tokens - model_usage.tokens - limits.finalization_token_reserve,
        )
        try:
            selection_step = signal_agent.select(
                state.next_information_needs,
                signal_registry,
                signal_fingerprints,
                prior_signal_results,
                eligible_signal_refs=eligible_signal_refs,
                research_state=state,
                prior_context_tags=tuple(
                    dict.fromkeys(
                        tag
                        for round_row in rounds
                        for selection in round_row.selections
                        for tag in selection.context_tags
                    )
                ),
            )
        except RuntimeBudgetExceeded as exc:
            model_usage = _consume_usage(model_usage, exc.usage, limits)
            termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
            break
        model_usage = _consume_model_step(model_usage, selection_step.usage, limits)
        selections = tuple(selection_step.value)
        bounded_selections: list[SignalSelectionDecision] = []
        llm_count = 0
        specs_by_ref = {spec.ref: spec for spec in signal_registry.specs}
        for selection in selections:
            spec = specs_by_ref.get(selection.signal_ref)
            if spec is None:
                bounded_selections.append(selection)
                continue
            if spec.execution_type is SignalExecutionType.LLM:
                if llm_count >= limits.max_llm_signals_per_round:
                    continue
                llm_count += 1
            bounded_selections.append(selection)
            if len(bounded_selections) >= limits.max_signals_per_round:
                break
        selections = tuple(bounded_selections)
        selected = tuple(item.signal_ref for item in selections)
        _assert_identity_values_masked(
            [list(item.context_tags) for item in selections],
            (company_id, *(str(item) for item in source_aliases)),
        )
        if len(set(selected)) != len(selected):
            raise ValidationError("Signal Retrieval Agent returned duplicate refs")
        if not set(selected).issubset(eligible_signal_refs):
            raise ValidationError(
                "Signal Retrieval Agent returned an already executed or unknown ref"
            )
        if not selected:
            termination_trigger = RuntimeStopReason.NO_SIGNAL_MATCH
            break
        remaining_calls = limits.max_signal_calls - signal_calls
        selected = selected[:remaining_calls]
        selections = selections[:remaining_calls]
        _set_request_token_budget(
            signal_executor.llm_runner,
            limits.max_tokens - model_usage.tokens - limits.finalization_token_reserve,
        )
        deterministic_refs = tuple(
            ref
            for ref in selected
            if specs_by_ref[ref].execution_type
            is SignalExecutionType.DETERMINISTIC
        )
        llm_refs = tuple(
            ref
            for ref in selected
            if specs_by_ref[ref].execution_type is SignalExecutionType.LLM
        )
        completed_batches: list[SignalBatchResult] = []
        if deterministic_refs:
            completed_batches.append(
                signal_executor.execute_batch(
                    deterministic_refs,
                    company_id=company_id,
                    as_of=prediction_time,
                    identity=company_basic_source,
                    prior_fingerprints=signal_fingerprints,
                )
            )
        soft_budget_exhausted = False
        if llm_refs:
            completed_fingerprints = {
                ref: fingerprint
                for completed in completed_batches
                for ref, fingerprint in completed.document_fingerprints.items()
            }
            try:
                completed_batches.append(
                    signal_executor.execute_batch(
                        llm_refs,
                        company_id=company_id,
                        as_of=prediction_time,
                        identity=company_basic_source,
                        prior_fingerprints={
                            **signal_fingerprints,
                            **completed_fingerprints,
                        },
                    )
                )
            except RuntimeBudgetExceeded as exc:
                model_usage = _consume_usage(model_usage, exc.usage, limits)
                soft_budget_exhausted = True
        batch = _merge_runtime_signal_batches(selected, completed_batches)
        if not batch.results:
            termination_trigger = (
                RuntimeStopReason.BUDGET_EXHAUSTED
                if soft_budget_exhausted
                else RuntimeStopReason.NO_SIGNAL_MATCH
            )
            break
        signal_fingerprints.update(batch.document_fingerprints)
        prior_signal_results.update(
            {result.ref: result.to_dict() for result in batch.results}
        )
        model_usage = _consume_usage(model_usage, batch.usage, limits)
        signal_calls += batch.signal_calls
        executed = tuple(result.ref for result in batch.results)
        rounds.append(
            SignalRound(
                information_needs=state.next_information_needs,
                selections=tuple(
                    item for item in selections if item.signal_ref in executed
                ),
                batch=batch,
            )
        )
        reflection_termination_trigger: RuntimeStopReason | None = None
        if soft_budget_exhausted:
            reflection_termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
        elif len(rounds) >= limits.max_signal_rounds:
            reflection_termination_trigger = RuntimeStopReason.MAX_SIGNAL_ROUNDS
        elif signal_calls >= limits.max_signal_calls:
            reflection_termination_trigger = RuntimeStopReason.MAX_SIGNAL_CALLS
        elif model_usage.llm_calls + 5 > limits.max_llm_calls:
            reflection_termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
        elif model_usage.tokens >= (
            limits.max_tokens - limits.finalization_token_reserve
        ):
            reflection_termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
        if all(
            result.value is SignalValue.UNAVAILABLE
            for result in batch.results
        ) and reflection_termination_trigger is None:
            continue
        _set_reflection_runtime_context(
            controller,
            selections=rounds[-1].selections,
            must_finalize=reflection_termination_trigger is not None,
            termination_trigger=reflection_termination_trigger,
        )
        reflection_budget = limits.max_tokens - model_usage.tokens
        if reflection_termination_trigger is None:
            reflection_budget -= limits.finalization_token_reserve
        _set_request_token_budget(controller, reflection_budget)
        try:
            reflection_step = controller.reflect(plan, state, batch)
        except RuntimeBudgetExceeded as exc:
            model_usage = _consume_usage(model_usage, exc.usage, limits)
            termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
            break
        model_usage = _consume_model_step(model_usage, reflection_step.usage, limits)
        state = reflection_step.value
        if reflection_termination_trigger is not None:
            termination_trigger = reflection_termination_trigger
        if soft_budget_exhausted:
            stop_reason = (
                RuntimeStopReason.FINALIZED
                if state.decision is ResearchDecision.FINALIZE
                else RuntimeStopReason.BUDGET_EXHAUSTED
            )
            break
        if state.decision is ResearchDecision.FINALIZE:
            stop_reason = RuntimeStopReason.FINALIZED

    if state.decision is ResearchDecision.CONTINUE:
        if termination_trigger is None:
            termination_trigger = RuntimeStopReason.NO_SIGNAL_MATCH
        if termination_trigger is RuntimeStopReason.NO_SIGNAL_MATCH:
            state = _finalize_exhausted_research_collection(state)
            stop_reason = RuntimeStopReason.FINALIZED
        else:
            stop_reason = termination_trigger

    final_context = _assemble_final_context(
        plan=plan,
        company_id=company_id,
        additional_identity_aliases=tuple(str(item) for item in source_aliases),
        basic_info=basic_info,
        state=state,
        rounds=rounds,
        prediction_time=prediction_time,
    )
    _set_request_token_budget(predictor, limits.max_tokens - model_usage.tokens)
    prediction_step = predictor.predict(final_context)
    model_usage = _consume_model_step(model_usage, prediction_step.usage, limits)
    prediction = prediction_step.value
    prediction_ref = prediction_sink(
        company_id,
        prediction_time,
        final_context,
        prediction,
    )
    if not prediction_ref.strip():
        raise ValidationError("prediction sink must return a durable reference")

    ground_truth = ground_truth_provider(company_id)
    _set_request_token_budget(predictor, limits.max_tokens - model_usage.tokens)
    try:
        reflection_step = predictor.reflect(final_context, prediction, ground_truth)
        model_usage = _consume_model_step(model_usage, reflection_step.usage, limits)
    except RuntimeBudgetExceeded:
        reflection_step = AgentStep(
            PredictionSelfReflection(
                correct=(
                    prediction.is_surge == ground_truth.is_surge
                    and (
                        not ground_truth.is_surge
                        or prediction.magnitude is ground_truth.magnitude
                    )
                ),
                plan_issues=("budget_skipped",),
            ),
            AgentUsage(),
        )

    return ExecutionTrajectory(
        case_id=resolved_case_id,
        company_id=company_id,
        prediction_time=prediction_time,
        basic_info=basic_info_bundle.to_dict(),
        initial_state=initial_state,
        signal_rounds=tuple(rounds),
        final_state=state,
        final_context=final_context,
        prediction=prediction,
        prediction_ref=prediction_ref,
        ground_truth=ground_truth,
        self_reflection=reflection_step.value,
        stop_reason=stop_reason,
        termination_trigger=termination_trigger,
        basic_info_projection=basic_info_projection,
        usage=RuntimeUsage(
            signal_rounds=len(rounds),
            signal_calls=signal_calls,
            model=model_usage,
        ),
    )


def _set_request_token_budget(component: Any, remaining: int) -> None:
    """Set an optional exact-request preflight budget on concrete v6 adapters."""

    setter = getattr(component, "set_request_token_budget", None)
    if callable(setter):
        setter(max(0, int(remaining)))


def _set_evaluation_context(component: Any, prediction_time: datetime) -> None:
    """Expose the fixed point-in-time horizon to capable H_init adapters."""

    setter = getattr(component, "set_evaluation_context", None)
    if callable(setter):
        setter(prediction_time)


def _set_reflection_runtime_context(
    component: Any,
    *,
    selections: tuple[SignalSelectionDecision, ...],
    must_finalize: bool,
    termination_trigger: RuntimeStopReason | None,
) -> None:
    """Expose exact selection intent and a terminal boundary to capable controllers."""

    setter = getattr(component, "set_reflection_runtime_context", None)
    if callable(setter):
        setter(
            selections=selections,
            must_finalize=must_finalize,
            termination_trigger=termination_trigger,
        )


def _finalize_exhausted_research_collection(state: ResearchState) -> ResearchState:
    """End natural no-match collection without changing research content."""

    value = state.to_dict()
    value["decision"] = ResearchDecision.FINALIZE.value
    finalized = ResearchState.from_dict(value)
    original_content = state.to_dict()
    finalized_content = finalized.to_dict()
    original_content.pop("decision")
    finalized_content.pop("decision")
    if finalized_content != original_content:
        raise ValidationError("no_signal_match finalization changed research content")
    return finalized


def _merge_runtime_signal_batches(
    selected: tuple[str, ...],
    batches: Iterable[SignalBatchResult],
) -> SignalBatchResult:
    """Merge successful deterministic/LLM subgroups back into selector order."""

    rows = tuple(batches)
    results_by_ref: dict[str, SignalResult] = {}
    usage = AgentUsage()
    resolutions: list[RawInfoResolution] = []
    fingerprints: dict[str, tuple[str, ...]] = {}
    skipped: list[str] = []
    for batch in rows:
        usage = usage + batch.usage
        resolutions.extend(batch.resolutions)
        fingerprints.update(batch.document_fingerprints)
        skipped.extend(batch.skipped_unchanged_refs)
        for result in batch.results:
            if result.ref in results_by_ref:
                raise ValidationError("runtime Signal subgroups returned duplicate refs")
            results_by_ref[result.ref] = result
    unexpected = set(results_by_ref) - set(selected)
    if unexpected:
        raise ValidationError(
            f"runtime Signal subgroups returned unselected refs: {sorted(unexpected)}"
        )
    results = tuple(results_by_ref[ref] for ref in selected if ref in results_by_ref)
    return SignalBatchResult(
        results=results,
        signal_calls=len(results),
        usage=usage,
        resolutions=tuple(resolutions),
        document_fingerprints=fingerprints,
        skipped_unchanged_refs=tuple(dict.fromkeys(skipped)),
    )


def _case_identity_alias_inventory(cases: Iterable[EvolutionCase]) -> tuple[str, ...]:
    """Collect every explicit identity alias for one local evaluation batch."""

    aliases: list[str] = []
    for case in cases:
        aliases.extend((case.case_id, case.company_id))
        for key in ("company_name", "ticker", "symbol", "name"):
            value = case.basic_info.get(key)
            if isinstance(value, str) and value.strip():
                aliases.append(value)
        raw_aliases = case.basic_info.get("identity_aliases", ())
        if isinstance(raw_aliases, str):
            raw_aliases = (raw_aliases,)
        if isinstance(raw_aliases, (list, tuple)):
            aliases.extend(
                item for item in raw_aliases if isinstance(item, str) and item.strip()
            )
    return tuple(dict.fromkeys(aliases))


def _slow_role_identity_guard_inventory(
    cases: Iterable[EvolutionCase],
) -> tuple[str, ...]:
    """Build exact, non-ambiguous identity guards for aggregate Slow roles.

    Complete local case masking deliberately expands formal names to brands. An
    aggregate role cannot use that expansion because ordinary brands such as
    ``News`` or ``Open`` are also protocol vocabulary. Keep only opaque ids,
    exact ticker-like aliases, and multi-token formal-name components here.
    """

    guards: list[str] = []
    for case in cases:
        guards.extend((case.case_id, case.company_id))
        for key in ("ticker", "symbol"):
            value = case.basic_info.get(key)
            if isinstance(value, str) and value.strip():
                guards.append(value.strip())
        raw_names: list[str] = []
        for key in ("company_name", "name"):
            value = case.basic_info.get(key)
            if isinstance(value, str) and value.strip():
                raw_names.append(value)
        raw_aliases = case.basic_info.get("identity_aliases", ())
        if isinstance(raw_aliases, str):
            raw_aliases = (raw_aliases,)
        if isinstance(raw_aliases, (list, tuple)):
            raw_names.extend(
                item for item in raw_aliases if isinstance(item, str) and item.strip()
            )
        for raw_name in raw_names:
            for component in _IDENTITY_NAME_SEPARATOR.split(raw_name):
                component = " ".join(component.split()).strip(" ,")
                if _is_strong_slow_identity_term(component):
                    guards.append(component)
                natural_name = _IDENTITY_LEGAL_SUFFIX.sub("", component).strip(" ,")
                if len(re.findall(r"[A-Za-z0-9]+", natural_name)) >= 2:
                    guards.append(natural_name)
    return tuple(dict.fromkeys(guards))


def _is_strong_slow_identity_term(value: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9]+", value)
    return len(tokens) >= 2 or (
        len(tokens) == 1
        and value.isalnum()
        and value.isupper()
        and 2 <= len(value) <= 5
    )


def _prediction_baseline_from_basic_info(
    basic_info: Mapping[str, Any],
    prediction_time: datetime,
) -> dict[str, Any]:
    """Compute the fixed point-in-time Predictor baseline from visible market bars."""

    market_source_types = {
        "historical_price",
        "market_data",
        "price_daily",
        "prices",
    }
    bars: dict[str, float] = {}
    for row in basic_info.get("requests", ()):
        if not isinstance(row, Mapping):
            continue
        request = row.get("request", {})
        source_types = (
            set(request.get("source_types", ()))
            if isinstance(request, Mapping)
            else set()
        )
        if not source_types.intersection(market_source_types):
            continue
        for projection in row.get("projections", ()):
            if not isinstance(projection, Mapping):
                continue
            exact_text = projection.get("exact_text")
            if not isinstance(exact_text, str):
                continue
            for match in re.finditer(r"\{[^{}]*\}", exact_text):
                try:
                    value = json.loads(match.group(0))
                except json.JSONDecodeError:
                    continue
                if not isinstance(value, Mapping):
                    continue
                raw_date = value.get("as_of_date")
                raw_close = value.get("adjusted_close")
                if (
                    not isinstance(raw_date, str)
                    or isinstance(raw_close, bool)
                    or not isinstance(raw_close, (int, float))
                    or not math.isfinite(float(raw_close))
                    or float(raw_close) <= 0
                ):
                    continue
                try:
                    bar_date = datetime.fromisoformat(raw_date).date()
                except ValueError:
                    continue
                if bar_date >= prediction_time.date():
                    continue
                existing = bars.get(raw_date)
                close = float(raw_close)
                if existing is not None and not math.isclose(
                    existing, close, rel_tol=0.0, abs_tol=1e-12
                ):
                    raise ValidationError(
                        "conflicting adjusted-close values in Predictor baseline "
                        f"for {raw_date}"
                    )
                bars[raw_date] = close
    method = "mean_last_5_complete_adjusted_closes_strictly_before_prediction_time"
    recent = sorted(bars.items())[-5:]
    if len(recent) < 5:
        return {
            "status": "unavailable",
            "method": method,
            "reason": "fewer_than_5_visible_market_bars",
        }
    return {
        "status": "available",
        "method": method,
        "mean_adjusted_close": sum(close for _date, close in recent) / 5,
        "trading_dates": [bar_date for bar_date, _close in recent],
    }


def _assemble_final_context(
    *,
    plan: InformationPlan,
    company_id: str,
    additional_identity_aliases: tuple[str, ...],
    basic_info: Mapping[str, Any],
    state: ResearchState,
    rounds: Iterable[SignalRound],
    prediction_time: datetime,
) -> dict[str, Any]:
    identity_keys = {"company_id", "company_name", "ticker", "symbol"}
    identity_aliases = [
        company_id,
        *additional_identity_aliases,
        *(
            str(value)
            for key, value in basic_info.items()
            if key in identity_keys and value is not None
        ),
    ]
    source_index: list[dict[str, Any]] = []
    data_gaps: list[dict[str, Any]] = []
    for row in basic_info.get("requests", ()):
        if not isinstance(row, Mapping):
            continue
        request = row.get("request", {})
        projections = row.get("projections", ())
        source_row = {
            "request_id": (
                request.get("request_id")
                if isinstance(request, Mapping)
                else None
            ),
            "source_types": (
                list(request.get("source_types", ()))
                if isinstance(request, Mapping)
                else []
            ),
            "status": row.get("status"),
            "projection_ids": [
                item.get("projection_id")
                for item in projections
                if isinstance(item, Mapping)
                and isinstance(item.get("projection_id"), str)
            ],
        }
        for field_name in (
            "projection_status",
            "available_projection_count",
            "visible_projection_count",
            "omitted_projection_count",
        ):
            if field_name in row:
                source_row[field_name] = row[field_name]
        source_index.append(source_row)
        if isinstance(row.get("data_gap"), Mapping):
            data_gaps.append(dict(row["data_gap"]))

    round_rows = tuple(rounds)
    signal_results = {
        result.ref: result
        for round_row in round_rows
        for result in round_row.batch.results
    }
    model_signal_results = {
        ref: signal_result_model_view(result)
        for ref, result in signal_results.items()
    }
    signal_rounds = [
        {
            "selected_signals": list(round_row.selected_signals),
            "batch": {
                "results": [
                    {
                        "signal_ref": result.ref,
                        "state": model_signal_results[result.ref]["state"],
                        "interpretation": model_signal_results[result.ref][
                            "interpretation"
                        ],
                        "status": model_signal_results[result.ref]["status"],
                    }
                    for result in round_row.batch.results
                ],
                "signal_calls": round_row.batch.signal_calls,
            },
        }
        for round_row in round_rows
    ]
    cited_signal_evidence: list[dict[str, Any]] = []
    seen_signal_evidence: set[tuple[str, str, int]] = set()
    for evidence_ref in state.supporting_evidence:
        if (
            not isinstance(evidence_ref, ResearchEvidenceRef)
            or evidence_ref.kind != "signal"
        ):
            continue
        key = (
            str(evidence_ref.signal_ref),
            str(evidence_ref.evidence_group),
            int(evidence_ref.evidence_index or 0),
        )
        if key in seen_signal_evidence:
            continue
        result = signal_results.get(key[0])
        if result is None:
            raise RuntimeBudgetExceeded(
                f"Predictor projection cannot resolve cited Signal {key[0]!r}"
            )
        evidence_rows = (
            result.supporting_evidence
            if key[1] == "supporting"
            else result.counter_evidence
        )
        if key[2] >= len(evidence_rows):
            raise RuntimeBudgetExceeded(
                "Predictor projection cannot resolve cited Signal evidence index"
            )
        cited_signal_evidence.append(
            {
                "signal_ref": key[0],
                "evidence_group": key[1],
                "evidence_index": key[2],
                "evidence": evidence_rows[key[2]].to_dict(),
            }
        )
        seen_signal_evidence.add(key)

    context = {
        "context_contract": {
            "kind": "bounded_prediction_projection",
            "max_utf8_bytes": MAX_PREDICTOR_CONTEXT_UTF8_BYTES,
            "complete_trajectory_retained_locally": True,
        },
        "basic_info": {
            "source_index": source_index,
            "data_gaps": data_gaps,
        },
        "prediction_baseline": _prediction_baseline_from_basic_info(
            basic_info, prediction_time
        ),
        "signal_rounds": signal_rounds,
        "cited_signal_evidence": cited_signal_evidence,
        "final_research_state": state.to_dict(),
        "analysis_prompt": plan.analysis_prompt,
    }
    masked_context = _mask_identity_values(context, identity_aliases)
    _assert_identity_values_masked(masked_context, identity_aliases)
    context_bytes = len(
        json.dumps(
            masked_context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if context_bytes > MAX_PREDICTOR_CONTEXT_UTF8_BYTES:
        raise RuntimeBudgetExceeded(
            "compact Predictor context exceeds frozen UTF-8 byte ceiling: "
            f"required={context_bytes}, limit={MAX_PREDICTOR_CONTEXT_UTF8_BYTES}"
        )
    return masked_context


def _consume_model_step(
    current: AgentUsage,
    reported: AgentUsage,
    limits: RuntimeLimits,
) -> AgentUsage:
    if reported.llm_calls == 0:
        reported = AgentUsage(llm_calls=1, tokens=reported.tokens, cost=reported.cost)
    return _consume_usage(current, reported, limits)


def _consume_usage(
    current: AgentUsage,
    additional: AgentUsage,
    limits: RuntimeLimits,
) -> AgentUsage:
    result = current + additional
    if result.llm_calls > limits.max_llm_calls:
        raise RuntimeBudgetExceeded("runtime exceeded max_llm_calls")
    if result.tokens > limits.max_tokens:
        raise RuntimeBudgetExceeded("runtime exceeded max_tokens")
    if result.cost > limits.max_cost:
        raise RuntimeBudgetExceeded("runtime exceeded max_cost")
    return result


@dataclass(frozen=True)
class PlanMetrics:
    """Binary fitness plus Stage-2 diagnostics."""

    binary_precision: float
    binary_recall: float
    binary_f1: float
    magnitude_accuracy: float
    magnitude_macro_f1: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    sample_count: int
    predicted_positive_count: int | None = None
    precision_defined: bool | None = None
    valid_case_count: int | None = None

    def __post_init__(self) -> None:
        metric_values = (
            self.binary_precision,
            self.binary_recall,
            self.binary_f1,
            self.magnitude_accuracy,
            self.magnitude_macro_f1,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= value <= 1
            for value in metric_values
        ):
            raise ValidationError("Plan metric values must be finite and in [0, 1]")
        counts = (
            self.true_positive,
            self.false_positive,
            self.true_negative,
            self.false_negative,
            self.sample_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValidationError("Plan metric counts must be non-negative integers")
        if sum(counts[:4]) != self.sample_count:
            raise ValidationError("Plan confusion counts must sum to sample_count")
        predicted = self.true_positive + self.false_positive
        if self.predicted_positive_count is None:
            object.__setattr__(self, "predicted_positive_count", predicted)
        elif self.predicted_positive_count != predicted:
            raise ValidationError("predicted-positive count differs from confusion")
        if self.precision_defined is None:
            object.__setattr__(self, "precision_defined", predicted > 0)
        elif self.precision_defined != (predicted > 0):
            raise ValidationError("precision-defined flag differs from confusion")
        if self.valid_case_count is None:
            object.__setattr__(self, "valid_case_count", self.sample_count)
        if self.valid_case_count < 0 or self.valid_case_count > self.sample_count:
            raise ValidationError("valid case count is outside the metric sample")

    def to_dict(self) -> dict[str, Any]:
        return {
            "binary_precision": self.binary_precision,
            "binary_recall": self.binary_recall,
            "binary_f1": self.binary_f1,
            "magnitude_accuracy": self.magnitude_accuracy,
            "magnitude_macro_f1": self.magnitude_macro_f1,
            "confusion": {
                "true_positive": self.true_positive,
                "false_positive": self.false_positive,
                "true_negative": self.true_negative,
                "false_negative": self.false_negative,
            },
            "sample_count": self.sample_count,
            "predicted_positive_count": self.predicted_positive_count,
            "precision_defined": self.precision_defined,
            "valid_case_count": self.valid_case_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanMetrics":
        confusion = dict(data.get("confusion", {}))
        return cls(
            binary_precision=float(data["binary_precision"]),
            binary_recall=float(data["binary_recall"]),
            binary_f1=float(data["binary_f1"]),
            magnitude_accuracy=float(data["magnitude_accuracy"]),
            magnitude_macro_f1=float(data["magnitude_macro_f1"]),
            true_positive=int(confusion.get("true_positive", 0)),
            false_positive=int(confusion.get("false_positive", 0)),
            true_negative=int(confusion.get("true_negative", 0)),
            false_negative=int(confusion.get("false_negative", 0)),
            sample_count=int(data["sample_count"]),
            predicted_positive_count=int(
                data.get(
                    "predicted_positive_count",
                    int(confusion.get("true_positive", 0))
                    + int(confusion.get("false_positive", 0)),
                )
            ),
            precision_defined=_json_boolean(
                data.get(
                    "precision_defined",
                    int(confusion.get("true_positive", 0))
                    + int(confusion.get("false_positive", 0))
                    > 0,
                ),
                "PlanMetrics precision_defined",
            ),
            valid_case_count=int(data.get("valid_case_count", data["sample_count"])),
        )


def score_predictions(trajectories: Iterable[ExecutionTrajectory]) -> PlanMetrics:
    """Compute binary metrics and three-class magnitude diagnostics."""

    rows = tuple(trajectories)
    if not rows:
        raise ValidationError("cannot score an empty trajectory set")
    true_positive = sum(
        row.prediction.is_surge and row.ground_truth.is_surge for row in rows
    )
    false_positive = sum(
        row.prediction.is_surge and not row.ground_truth.is_surge for row in rows
    )
    true_negative = sum(
        not row.prediction.is_surge and not row.ground_truth.is_surge for row in rows
    )
    false_negative = sum(
        not row.prediction.is_surge and row.ground_truth.is_surge for row in rows
    )
    predicted_positive_count = true_positive + false_positive
    precision = _safe_ratio(true_positive, predicted_positive_count)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    binary_f1 = _safe_ratio(2 * precision * recall, precision + recall)

    surge_rows = tuple(row for row in rows if row.ground_truth.is_surge)
    magnitude_correct = sum(
        row.prediction.magnitude == row.ground_truth.magnitude for row in surge_rows
    )
    magnitude_accuracy = _safe_ratio(magnitude_correct, len(surge_rows))
    per_class_f1: list[float] = []
    for magnitude in MagnitudeClass:
        class_tp = sum(
            row.ground_truth.magnitude is magnitude
            and row.prediction.magnitude is magnitude
            for row in surge_rows
        )
        class_fp = sum(
            row.ground_truth.magnitude is not magnitude
            and row.prediction.magnitude is magnitude
            for row in surge_rows
        )
        class_fn = sum(
            row.ground_truth.magnitude is magnitude
            and row.prediction.magnitude is not magnitude
            for row in surge_rows
        )
        class_precision = _safe_ratio(class_tp, class_tp + class_fp)
        class_recall = _safe_ratio(class_tp, class_tp + class_fn)
        per_class_f1.append(
            _safe_ratio(
                2 * class_precision * class_recall,
                class_precision + class_recall,
            )
        )
    return PlanMetrics(
        binary_precision=precision,
        binary_recall=recall,
        binary_f1=binary_f1,
        magnitude_accuracy=magnitude_accuracy,
        magnitude_macro_f1=sum(per_class_f1) / len(per_class_f1),
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        sample_count=len(rows),
        predicted_positive_count=predicted_positive_count,
        precision_defined=predicted_positive_count > 0,
        valid_case_count=len(rows),
    )


@dataclass(frozen=True)
class FitnessEligibility:
    """Explicit separation between durable diagnostics and selectable fitness."""

    eligible: bool
    reasons: tuple[str, ...]
    expected_case_count: int
    valid_case_count: int
    evidence_covered_count: int
    predicted_positive_count: int
    true_positive_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(str(item) for item in self.reasons))
        if self.eligible != (not self.reasons):
            raise ValidationError("fitness eligibility must match its reasons")

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "status": "eligible" if self.eligible else "diagnostic_only",
            "reasons": list(self.reasons),
            "expected_case_count": self.expected_case_count,
            "valid_case_count": self.valid_case_count,
            "evidence_covered_count": self.evidence_covered_count,
            "predicted_positive_count": self.predicted_positive_count,
            "true_positive_count": self.true_positive_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FitnessEligibility":
        reasons = tuple(str(item) for item in data.get("reasons", ()))
        return cls(
            eligible=_json_boolean(
                data.get("eligible", not reasons), "fitness eligible"
            ),
            reasons=reasons,
            expected_case_count=int(data.get("expected_case_count", 0)),
            valid_case_count=int(data.get("valid_case_count", 0)),
            evidence_covered_count=int(data.get("evidence_covered_count", 0)),
            predicted_positive_count=int(data.get("predicted_positive_count", 0)),
            true_positive_count=int(data.get("true_positive_count", 0)),
        )


def assess_fitness_eligibility(
    trajectories: Iterable[ExecutionTrajectory],
    *,
    expected_case_ids: Iterable[str],
) -> FitnessEligibility:
    """Assess completeness, finalization, evidence, and non-degenerate fitness."""

    rows = tuple(trajectories)
    expected = tuple(str(item) for item in expected_case_ids)
    actual = tuple(row.case_id for row in rows)
    valid_rows = tuple(
        row for row in rows if _trajectory_is_fitness_finalized(row)
    )
    evidence_covered = sum(_trajectory_has_source_evidence(row) for row in rows)
    predicted_positive = sum(row.prediction.is_surge for row in rows)
    true_positive = sum(
        row.prediction.is_surge and row.ground_truth.is_surge for row in rows
    )
    reasons: list[str] = []
    if len(expected) != len(rows) or set(expected) != set(actual):
        reasons.append("incomplete_case_set")
    if len(valid_rows) != len(rows):
        reasons.append("unfinalized_case")
    if evidence_covered != len(rows):
        reasons.append("missing_source_evidence")
    if predicted_positive == 0:
        reasons.append("no_positive_prediction")
    if true_positive == 0:
        reasons.append("no_true_positive")
    return FitnessEligibility(
        eligible=not reasons,
        reasons=tuple(reasons),
        expected_case_count=len(expected),
        valid_case_count=len(valid_rows),
        evidence_covered_count=evidence_covered,
        predicted_positive_count=predicted_positive,
        true_positive_count=true_positive,
    )


def _trajectory_is_fitness_finalized(trajectory: ExecutionTrajectory) -> bool:
    return (
        trajectory.stop_reason is RuntimeStopReason.FINALIZED
        and trajectory.final_state.decision is ResearchDecision.FINALIZE
        and bool(trajectory.prediction_ref.strip())
    )


def _trajectory_has_source_evidence(trajectory: ExecutionTrajectory) -> bool:
    requests = trajectory.basic_info.get("requests", ())
    if isinstance(requests, list) and any(
        isinstance(item, Mapping) and bool(item.get("context_spans"))
        for item in requests
    ):
        return True
    return any(
        result.value is not SignalValue.UNAVAILABLE
        and bool(result.supporting_evidence or result.counter_evidence)
        for signal_round in trajectory.signal_rounds
        for result in signal_round.batch.results
    )


def _shared_missing_source_case_ids(
    attempts: Iterable[PlanEvaluationAttempt],
) -> tuple[str, ...]:
    """Find evidence-free cases shared by every complete candidate attempt."""

    values = tuple(attempts)
    if not values or any(
        attempt.metrics is None
        or "missing_source_evidence" not in attempt.fitness.reasons
        for attempt in values
    ):
        return ()
    missing_sets = [
        {
            trajectory.case_id
            for trajectory in attempt.trajectories
            if not _trajectory_has_source_evidence(trajectory)
        }
        for attempt in values
    ]
    return tuple(sorted(set.intersection(*missing_sets)))


def _safe_ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


@dataclass(frozen=True)
class EvolutionCase:
    """One dataset case whose label owner is outside Plan execution."""

    company_id: str
    prediction_time: datetime
    basic_info: Mapping[str, Any]
    ground_truth: GroundTruth
    case_id: str = ""

    def __post_init__(self) -> None:
        _validate_id(self.company_id, "company_id")
        _require_aware_datetime(self.prediction_time, "prediction_time")
        resolved_case_id = self.case_id or _default_case_id(
            self.company_id, self.prediction_time
        )
        _validate_id(resolved_case_id, "case_id")
        object.__setattr__(self, "case_id", resolved_case_id)
        object.__setattr__(self, "basic_info", dict(self.basic_info))

    def to_discovery_dict(self) -> dict[str, Any]:
        """Return label-visible data only for the Discovery workspace."""

        return {
            "case_id": self.case_id,
            "company_id": self.company_id,
            "prediction_time": self.prediction_time.isoformat(),
            "basic_info": dict(self.basic_info),
            "ground_truth": self.ground_truth.to_dict(),
        }


@dataclass(frozen=True)
class EvaluationCaseReadiness:
    """Label-free readiness result for one prospective evaluation case."""

    case_id: str
    ready: bool
    reason: str = ""
    retryable: bool = False

    def __post_init__(self) -> None:
        _validate_id(self.case_id, "readiness case_id")
        if type(self.ready) is not bool or type(self.retryable) is not bool:
            raise ValidationError("evaluation readiness flags must be booleans")
        if self.ready and (self.reason or self.retryable):
            raise ValidationError("ready evaluation case cannot carry a failure")
        if not self.ready and not self.reason.strip():
            raise ValidationError("unready evaluation case requires a reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "ready": self.ready,
            "reason": self.reason,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class EvolutionDataset:
    """Issuer-disjoint Discovery, Anchor, Validation, and Locked Test sets."""

    discovery: tuple[EvolutionCase, ...]
    anchor: tuple[EvolutionCase, ...]
    evolution_validation: tuple[EvolutionCase, ...]
    locked_test: tuple[EvolutionCase, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "discovery", tuple(self.discovery))
        object.__setattr__(self, "anchor", tuple(self.anchor))
        object.__setattr__(
            self, "evolution_validation", tuple(self.evolution_validation)
        )
        object.__setattr__(self, "locked_test", tuple(self.locked_test))
        owners: dict[str, str] = {}
        seen_case_ids: set[str] = set()
        for split_name, cases in (
            ("discovery", self.discovery),
            ("anchor", self.anchor),
            ("evolution_validation", self.evolution_validation),
            ("locked_test", self.locked_test),
        ):
            if not cases:
                raise ValidationError(f"dataset split {split_name} must not be empty")
            for case in cases:
                if case.case_id in seen_case_ids:
                    raise ValidationError(f"duplicate evolution case_id: {case.case_id}")
                seen_case_ids.add(case.case_id)
                prior = owners.setdefault(case.company_id, split_name)
                if prior != split_name:
                    raise ValidationError(
                        f"company {case.company_id} crosses dataset ownership boundaries"
                    )


EVALUATION_LABELS = ("non_surge", "2_3x", "3_10x", "10x_plus")
DEFAULT_ANCHOR_LABEL_COUNTS = {
    "non_surge": 7,
    "2_3x": 5,
    "3_10x": 3,
    "10x_plus": 1,
}
DEFAULT_RANDOM_LABEL_COUNTS = {
    "non_surge": 3,
    "2_3x": 2,
    "3_10x": 2,
    "10x_plus": 1,
}
DEFAULT_EVALUATION_LABEL_COUNTS = {
    "non_surge": 10,
    "2_3x": 7,
    "3_10x": 5,
    "10x_plus": 2,
}
DEFAULT_EVALUATION_SECONDARY_METRICS = (
    "binary_precision",
    "binary_recall",
    "magnitude_macro_f1",
    "magnitude_accuracy",
)


@dataclass(frozen=True)
class PlanEvaluationConfig:
    """Fixed-Anchor plus round-Random Fast-loop evaluation contract."""

    cases_per_round: int = 24
    label_counts: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_EVALUATION_LABEL_COUNTS)
    )
    anchor_cases: int = 16
    anchor_label_counts: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_ANCHOR_LABEL_COUNTS)
    )
    random_cases: int = 8
    random_label_counts: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_RANDOM_LABEL_COUNTS)
    )
    primary_metric: str = "binary_f1"
    secondary_metrics: tuple[str, ...] = DEFAULT_EVALUATION_SECONDARY_METRICS
    max_cases_per_company_per_round: int = 1
    base_seed: int = 42
    require_finalized: bool = True
    require_source_evidence: bool = True
    max_proposal_attempts_per_slot: int = 3
    max_structured_corrections: int = 1

    def __post_init__(self) -> None:
        counts = {str(key): int(value) for key, value in self.label_counts.items()}
        anchor_counts = {
            str(key): int(value) for key, value in self.anchor_label_counts.items()
        }
        random_counts = {
            str(key): int(value) for key, value in self.random_label_counts.items()
        }
        if any(
            set(group) != set(EVALUATION_LABELS)
            for group in (counts, anchor_counts, random_counts)
        ):
            raise ValidationError("evaluation counts must name all four labels")
        if any(
            value < 1
            for group in (counts, anchor_counts, random_counts)
            for value in group.values()
        ):
            raise ValidationError("evaluation counts must be positive")
        if self.cases_per_round < 1 or sum(counts.values()) != self.cases_per_round:
            raise ValidationError(
                "evaluation label counts must sum to cases_per_round"
            )
        if self.anchor_cases < 1 or sum(anchor_counts.values()) != self.anchor_cases:
            raise ValidationError("Anchor counts must sum to anchor_cases")
        if self.random_cases < 1 or sum(random_counts.values()) != self.random_cases:
            raise ValidationError("Random counts must sum to random_cases")
        if self.anchor_cases + self.random_cases != self.cases_per_round:
            raise ValidationError("Anchor and Random sizes must sum to cases_per_round")
        combined = {
            label: anchor_counts[label] + random_counts[label]
            for label in EVALUATION_LABELS
        }
        if counts != combined:
            raise ValidationError(
                "combined evaluation counts must equal Anchor plus Random counts"
            )
        if self.primary_metric != "binary_f1":
            raise ValidationError("Plan evolution primary metric must be binary_f1")
        if self.max_cases_per_company_per_round < 1:
            raise ValidationError("max cases per company per round must be positive")
        if self.max_proposal_attempts_per_slot < 1:
            raise ValidationError("proposal attempts per slot must be positive")
        if self.max_structured_corrections != 1:
            raise ValidationError("v5 requires exactly one structured correction")
        if not self.require_finalized:
            raise ValidationError("v5 fitness requires finalized trajectories")
        object.__setattr__(self, "label_counts", counts)
        object.__setattr__(self, "anchor_label_counts", anchor_counts)
        object.__setattr__(self, "random_label_counts", random_counts)
        object.__setattr__(
            self,
            "secondary_metrics",
            tuple(str(item) for item in self.secondary_metrics),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases_per_round": self.cases_per_round,
            "label_counts": dict(self.label_counts),
            "anchor": {
                "case_count": self.anchor_cases,
                "label_counts": dict(self.anchor_label_counts),
            },
            "random": {
                "case_count": self.random_cases,
                "label_counts": dict(self.random_label_counts),
            },
            "primary_metric": self.primary_metric,
            "secondary_metrics": list(self.secondary_metrics),
            "max_cases_per_company_per_round": (
                self.max_cases_per_company_per_round
            ),
            "base_seed": self.base_seed,
            "fitness_gate": {
                "require_finalized": self.require_finalized,
                "require_source_evidence": self.require_source_evidence,
                "require_predicted_positive": True,
                "require_true_positive": True,
            },
            "proposal": {
                "max_attempts_per_slot": self.max_proposal_attempts_per_slot,
                "max_structured_corrections": self.max_structured_corrections,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanEvaluationConfig":
        required = {
            "cases_per_round",
            "label_counts",
            "anchor",
            "random",
            "fitness_gate",
            "proposal",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "v5 evaluation contract is missing: " + ", ".join(missing)
            )
        gate = dict(data["fitness_gate"])
        proposal = dict(data["proposal"])
        anchor = dict(data["anchor"])
        random_group = dict(data["random"])
        if not _json_boolean(
            gate.get("require_predicted_positive", False),
            "fitness require_predicted_positive",
        ):
            raise ValidationError("v5 fitness requires at least one positive prediction")
        if not _json_boolean(
            gate.get("require_true_positive", False),
            "fitness require_true_positive",
        ):
            raise ValidationError("v5 fitness requires at least one true positive")
        return cls(
            cases_per_round=int(data["cases_per_round"]),
            label_counts=dict(data["label_counts"]),
            anchor_cases=int(anchor["case_count"]),
            anchor_label_counts=dict(anchor["label_counts"]),
            random_cases=int(random_group["case_count"]),
            random_label_counts=dict(random_group["label_counts"]),
            primary_metric=str(data.get("primary_metric", "binary_f1")),
            secondary_metrics=tuple(
                str(item)
                for item in data.get(
                    "secondary_metrics", DEFAULT_EVALUATION_SECONDARY_METRICS
                )
            ),
            max_cases_per_company_per_round=int(
                data.get("max_cases_per_company_per_round", 1)
            ),
            base_seed=int(data.get("base_seed", 42)),
            require_finalized=_json_boolean(
                gate.get("require_finalized", True),
                "fitness require_finalized",
            ),
            require_source_evidence=_json_boolean(
                gate.get("require_source_evidence", True),
                "fitness require_source_evidence",
            ),
            max_proposal_attempts_per_slot=int(
                proposal.get("max_attempts_per_slot", 3)
            ),
            max_structured_corrections=int(
                proposal.get("max_structured_corrections", 1)
            ),
        )


def evaluation_label(case: EvolutionCase) -> str:
    """Map one four-class outcome to the persisted evaluation label."""

    if not case.ground_truth.is_surge:
        return "non_surge"
    return {
        MagnitudeClass.TWO_TO_THREE: "2_3x",
        MagnitudeClass.THREE_TO_TEN: "3_10x",
        MagnitudeClass.TEN_PLUS: "10x_plus",
    }[case.ground_truth.magnitude]


class EvaluationDatasetInfeasible(ValidationError):
    """Raised before external work when an exact round cannot be assembled."""

    def __init__(
        self,
        *,
        expected_counts: Mapping[str, int],
        available_counts: Mapping[str, int],
        available_companies: int,
    ) -> None:
        self.expected_counts = dict(expected_counts)
        self.available_counts = dict(available_counts)
        self.available_companies = int(available_companies)
        super().__init__(
            "evaluation_dataset_infeasible: expected "
            f"{self.expected_counts}, available {self.available_counts}, "
            f"distinct_companies={self.available_companies}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "evaluation_dataset_infeasible",
            "expected_counts": dict(self.expected_counts),
            "available_counts": dict(self.available_counts),
            "available_companies": self.available_companies,
        }


@dataclass(frozen=True)
class EvaluationDatasetSnapshot:
    """Immutable Anchor plus Random case-id snapshot shared by one round."""

    snapshot_id: str
    round_id: int
    random_seed: int
    anchor_snapshot_id: str
    target_counts: Mapping[str, int]
    actual_counts: Mapping[str, int]
    anchor_target_counts: Mapping[str, int]
    anchor_actual_counts: Mapping[str, int]
    random_target_counts: Mapping[str, int]
    random_actual_counts: Mapping[str, int]
    anchor_case_ids: tuple[str, ...]
    random_case_ids: tuple[str, ...]
    case_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "plan-evaluation-dataset-v3",
            "snapshot_id": self.snapshot_id,
            "stage": "round",
            "round_id": self.round_id,
            "random_seed": self.random_seed,
            "anchor_snapshot_id": self.anchor_snapshot_id,
            "target_counts": dict(self.target_counts),
            "actual_counts": dict(self.actual_counts),
            "anchor_target_counts": dict(self.anchor_target_counts),
            "anchor_actual_counts": dict(self.anchor_actual_counts),
            "random_target_counts": dict(self.random_target_counts),
            "random_actual_counts": dict(self.random_actual_counts),
            "anchor_case_ids": list(self.anchor_case_ids),
            "random_case_ids": list(self.random_case_ids),
            "case_ids": list(self.case_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvaluationDatasetSnapshot":
        if data.get("schema_version") != "plan-evaluation-dataset-v3":
            raise ValidationError("unsupported evaluation dataset snapshot schema")
        payload = dict(data)
        snapshot_id = str(payload.pop("snapshot_id", ""))
        if not snapshot_id or _canonical_hash(payload) != snapshot_id:
            raise ValidationError("evaluation dataset snapshot hash mismatch")
        return cls(
            snapshot_id=snapshot_id,
            round_id=int(data["round_id"]),
            random_seed=int(data["random_seed"]),
            anchor_snapshot_id=str(data["anchor_snapshot_id"]),
            target_counts={
                str(key): int(value)
                for key, value in dict(data.get("target_counts", {})).items()
            },
            actual_counts={
                str(key): int(value)
                for key, value in dict(data.get("actual_counts", {})).items()
            },
            anchor_target_counts={
                str(key): int(value)
                for key, value in dict(data.get("anchor_target_counts", {})).items()
            },
            anchor_actual_counts={
                str(key): int(value)
                for key, value in dict(data.get("anchor_actual_counts", {})).items()
            },
            random_target_counts={
                str(key): int(value)
                for key, value in dict(data.get("random_target_counts", {})).items()
            },
            random_actual_counts={
                str(key): int(value)
                for key, value in dict(data.get("random_actual_counts", {})).items()
            },
            anchor_case_ids=tuple(
                str(item) for item in data.get("anchor_case_ids", ())
            ),
            random_case_ids=tuple(
                str(item) for item in data.get("random_case_ids", ())
            ),
            case_ids=tuple(str(item) for item in data.get("case_ids", ())),
        )


class EvaluationDatasetManager:
    """Freeze Anchor and create exact rotating Random round snapshots."""

    def __init__(
        self,
        root: str | Path,
        pool: Iterable[EvolutionCase],
        anchor_cases: Iterable[EvolutionCase],
        config: PlanEvaluationConfig = PlanEvaluationConfig(),
        case_readiness: Callable[[EvolutionCase], EvaluationCaseReadiness]
        | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.pool = tuple(pool)
        self.anchor_cases = tuple(anchor_cases)
        self.config = config
        self.case_readiness = case_readiness
        self._readiness_cache: dict[str, EvaluationCaseReadiness] = {}
        all_cases = (*self.anchor_cases, *self.pool)
        self._cases_by_id = {case.case_id: case for case in all_cases}
        if len(self._cases_by_id) != len(all_cases):
            raise ValidationError("evaluation pool contains duplicate case ids")
        anchor_companies = {case.company_id for case in self.anchor_cases}
        if anchor_companies & {case.company_id for case in self.pool}:
            raise ValidationError("Anchor issuers must be absent from Random pool")
        if self.config.max_cases_per_company_per_round != 1:
            raise ValidationError("v5 evaluation requires one case per company")
        self.anchor_snapshot_id = self._write_or_load_anchor()
        self.validate_feasibility()

    def validate_feasibility(self) -> None:
        """Prove the exact quotas can be assigned to distinct companies."""

        self._validate_anchor_cases()
        self._select_exact_cases(round_id=1, history={}, require_ready=False)

    def get_or_create_round_dataset(
        self, round_id: int
    ) -> EvaluationDatasetSnapshot:
        path = self._round_root(round_id) / "snapshot.json"
        if path.exists():
            snapshot = self._load_snapshot(path, round_id=round_id)
            self._require_cases_ready(
                self.resolve_cases(snapshot.case_ids), round_id=round_id
            )
            return snapshot
        self._require_cases_ready(self.anchor_cases, round_id=round_id)
        seed = self.config.base_seed + round_id
        random_cases = self._select_exact_cases(
            round_id=round_id,
            history=self._selection_history(before_round=round_id),
            require_ready=True,
        )
        return self._write_snapshot(
            path,
            round_id=round_id,
            seed=seed,
            random_cases=random_cases,
        )

    def _selection_history(
        self, *, before_round: int
    ) -> dict[str, tuple[int, int]]:
        history: dict[str, tuple[int, int]] = {}
        for path in sorted(self.root.glob("round_*/snapshot.json")):
            snapshot_round = int(path.parent.name.removeprefix("round_"))
            if snapshot_round >= before_round:
                continue
            snapshot = self._load_snapshot(path, round_id=snapshot_round)
            for case_id in snapshot.random_case_ids:
                count, _last = history.get(case_id, (0, 0))
                history[case_id] = (count + 1, snapshot.round_id)
        return history

    def _select_exact_cases(
        self,
        *,
        round_id: int,
        history: Mapping[str, tuple[int, int]],
        require_ready: bool,
    ) -> tuple[EvolutionCase, ...]:
        by_label_company: dict[str, dict[str, list[EvolutionCase]]] = {
            label: {} for label in EVALUATION_LABELS
        }
        for case in self.pool:
            by_label_company[evaluation_label(case)].setdefault(
                case.company_id, []
            ).append(case)

        def case_key(case: EvolutionCase) -> tuple[int, int, str]:
            count, last_round = history.get(case.case_id, (0, 0))
            tie = hashlib.sha256(
                f"{self.config.base_seed}:{round_id}:{case.case_id}".encode(
                    "utf-8"
                )
            ).hexdigest()
            return count, last_round, tie

        company_order: dict[str, list[str]] = {}
        best_case: dict[tuple[str, str], EvolutionCase] = {}
        ordered_cases: dict[tuple[str, str], tuple[EvolutionCase, ...]] = {}
        for label, companies in by_label_company.items():
            for company_id, cases in companies.items():
                ordered = tuple(sorted(cases, key=case_key))
                ordered_cases[(label, company_id)] = ordered
                best_case[(label, company_id)] = ordered[0]
            company_order[label] = sorted(
                companies,
                key=lambda company_id: (
                    case_key(best_case[(label, company_id)]),
                    company_id,
                ),
            )

        def selected_case(
            label: str, company_id: str
        ) -> EvolutionCase | None:
            if not require_ready or self.case_readiness is None:
                return best_case[(label, company_id)]
            for case in ordered_cases[(label, company_id)]:
                if self._readiness_for(case).ready:
                    return case
            return None

        slots = [
            (label, index)
            for label in EVALUATION_LABELS
            for index in range(int(self.config.random_label_counts[label]))
        ]
        slots.sort(
            key=lambda slot: (
                len(company_order[slot[0]]),
                EVALUATION_LABELS.index(slot[0]),
                slot[1],
            )
        )
        matched_company: dict[str, tuple[str, int]] = {}

        def assign(slot: tuple[str, int], seen: set[str]) -> bool:
            label, _index = slot
            for company_id in company_order[label]:
                if company_id in seen:
                    continue
                if selected_case(label, company_id) is None:
                    continue
                seen.add(company_id)
                prior = matched_company.get(company_id)
                if prior is None or assign(prior, seen):
                    matched_company[company_id] = slot
                    return True
            return False

        if any(not assign(slot, set()) for slot in slots):
            failed_readiness = tuple(
                result
                for result in self._readiness_cache.values()
                if not result.ready
            )
            if require_ready and failed_readiness:
                self._raise_shared_unavailable(round_id, failed_readiness)
            raise EvaluationDatasetInfeasible(
                expected_counts=self.config.random_label_counts,
                available_counts=_count_evaluation_labels(self.pool),
                available_companies=len({case.company_id for case in self.pool}),
            )
        slot_company = {slot: company for company, slot in matched_company.items()}
        selected = tuple(
            selected_case(label, slot_company[(label, index)])
            for label in EVALUATION_LABELS
            for index in range(int(self.config.random_label_counts[label]))
        )
        if any(case is None for case in selected):
            raise ValidationError(
                "exact Random evaluation matching selected an unready case"
            )
        selected_cases = tuple(case for case in selected if case is not None)
        if (
            len(selected_cases) != self.config.random_cases
            or _count_evaluation_labels(selected_cases)
            != dict(self.config.random_label_counts)
            or len({case.company_id for case in selected_cases})
            != len(selected_cases)
        ):
            raise ValidationError("exact Random evaluation matching produced invalid output")
        return selected_cases

    def _readiness_for(self, case: EvolutionCase) -> EvaluationCaseReadiness:
        cached = self._readiness_cache.get(case.case_id)
        if cached is not None:
            return cached
        if self.case_readiness is None:
            result = EvaluationCaseReadiness(case.case_id, True)
        else:
            result = self.case_readiness(case)
            if result.case_id != case.case_id:
                raise ValidationError("evaluation readiness case identity mismatch")
        self._readiness_cache[case.case_id] = result
        return result

    def _require_cases_ready(
        self, cases: Iterable[EvolutionCase], *, round_id: int
    ) -> None:
        failures = tuple(
            result
            for result in (self._readiness_for(case) for case in cases)
            if not result.ready
        )
        if failures:
            self._raise_shared_unavailable(round_id, failures)

    @staticmethod
    def _raise_shared_unavailable(
        round_id: int, failures: Iterable[EvaluationCaseReadiness]
    ) -> None:
        values = tuple(failures)
        raise SharedEvaluationDataUnavailable(
            round_id,
            {item.case_id: item.reason for item in values},
            retryable=any(item.retryable for item in values),
        )

    def _validate_anchor_cases(self) -> None:
        if (
            len(self.anchor_cases) != self.config.anchor_cases
            or _count_evaluation_labels(self.anchor_cases)
            != dict(self.config.anchor_label_counts)
            or len({case.company_id for case in self.anchor_cases})
            != len(self.anchor_cases)
        ):
            raise ValidationError("Anchor cases violate the fixed evaluation contract")

    def _write_or_load_anchor(self) -> str:
        self._validate_anchor_cases()
        payload = {
            "schema_version": "plan-evaluation-anchor-v1",
            "stage": "anchor",
            "target_counts": dict(self.config.anchor_label_counts),
            "actual_counts": _count_evaluation_labels(self.anchor_cases),
            "case_ids": [case.case_id for case in self.anchor_cases],
        }
        envelope = {**payload, "snapshot_id": _canonical_hash(payload)}
        path = self.root / "anchor.json"
        _write_or_verify_json(path, envelope)
        stored = _read_json(path)
        stored_id = str(stored.get("snapshot_id", ""))
        unhashed = dict(stored)
        unhashed.pop("snapshot_id", None)
        if stored_id != _canonical_hash(unhashed) or stored != envelope:
            raise ValidationError("Anchor snapshot identity mismatch")
        return stored_id

    def resolve_cases(self, case_ids: Iterable[str]) -> tuple[EvolutionCase, ...]:
        resolved: list[EvolutionCase] = []
        for case_id in case_ids:
            if case_id not in self._cases_by_id:
                raise ValidationError(
                    f"evaluation snapshot case is missing from approved pool: {case_id}"
                )
            resolved.append(self._cases_by_id[case_id])
        return tuple(resolved)

    def _round_root(self, round_id: int) -> Path:
        if round_id < 1:
            raise ValidationError("evaluation round id must be positive")
        return self.root / f"round_{round_id:03d}"

    def _load_snapshot(
        self,
        path: Path,
        *,
        round_id: int,
    ) -> EvaluationDatasetSnapshot:
        snapshot = EvaluationDatasetSnapshot.from_dict(_read_json(path))
        if snapshot.round_id != round_id:
            raise ValidationError("evaluation dataset snapshot identity mismatch")
        cases = self.resolve_cases(snapshot.case_ids)
        expected_counts = {
            label: int(self.config.label_counts[label])
            for label in EVALUATION_LABELS
        }
        if (
            snapshot.random_seed != self.config.base_seed + round_id
            or snapshot.anchor_snapshot_id != self.anchor_snapshot_id
            or dict(snapshot.target_counts) != expected_counts
            or _count_evaluation_labels(cases) != dict(snapshot.actual_counts)
            or dict(snapshot.actual_counts) != expected_counts
            or len(cases) != self.config.cases_per_round
            or tuple(snapshot.anchor_case_ids)
            != tuple(case.case_id for case in self.anchor_cases)
            or dict(snapshot.anchor_target_counts)
            != dict(self.config.anchor_label_counts)
            or dict(snapshot.anchor_actual_counts)
            != dict(self.config.anchor_label_counts)
            or len(snapshot.random_case_ids) != self.config.random_cases
            or dict(snapshot.random_target_counts)
            != dict(self.config.random_label_counts)
            or dict(snapshot.random_actual_counts)
            != dict(self.config.random_label_counts)
            or tuple(snapshot.case_ids)
            != (*snapshot.anchor_case_ids, *snapshot.random_case_ids)
            or len(set(snapshot.case_ids)) != len(snapshot.case_ids)
            or len({case.company_id for case in cases}) != len(cases)
        ):
            raise ValidationError(
                "evaluation snapshot violates the frozen round sampling contract"
            )
        return snapshot

    def _write_snapshot(
        self,
        path: Path,
        *,
        round_id: int,
        seed: int,
        random_cases: tuple[EvolutionCase, ...],
    ) -> EvaluationDatasetSnapshot:
        cases = (*self.anchor_cases, *random_cases)
        payload = {
            "schema_version": "plan-evaluation-dataset-v3",
            "stage": "round",
            "round_id": round_id,
            "random_seed": seed,
            "anchor_snapshot_id": self.anchor_snapshot_id,
            "target_counts": {
                label: int(self.config.label_counts[label])
                for label in EVALUATION_LABELS
            },
            "actual_counts": _count_evaluation_labels(cases),
            "anchor_target_counts": dict(self.config.anchor_label_counts),
            "anchor_actual_counts": _count_evaluation_labels(self.anchor_cases),
            "random_target_counts": dict(self.config.random_label_counts),
            "random_actual_counts": _count_evaluation_labels(random_cases),
            "anchor_case_ids": [case.case_id for case in self.anchor_cases],
            "random_case_ids": [case.case_id for case in random_cases],
            "case_ids": [case.case_id for case in cases],
        }
        snapshot = EvaluationDatasetSnapshot.from_dict(
            {**payload, "snapshot_id": _canonical_hash(payload)}
        )
        _write_or_verify_json(path, snapshot.to_dict())
        return snapshot


def _count_evaluation_labels(
    cases: Iterable[EvolutionCase],
) -> dict[str, int]:
    counts = {label: 0 for label in EVALUATION_LABELS}
    for case in cases:
        counts[evaluation_label(case)] += 1
    return counts


@dataclass(frozen=True)
class PlanReflection:
    """Plan-level Critic output over all trajectories and metrics."""

    successful_patterns: tuple[str, ...] = ()
    failed_patterns: tuple[str, ...] = ()
    repeated_failure_modes: tuple[str, ...] = ()
    misleading_signals: tuple[str, ...] = ()
    missing_information_needs: tuple[str, ...] = ()
    next_explorations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "successful_patterns",
            "failed_patterns",
            "repeated_failure_modes",
            "misleading_signals",
            "missing_information_needs",
            "next_explorations",
        ):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "successful_patterns": list(self.successful_patterns),
            "failed_patterns": list(self.failed_patterns),
            "repeated_failure_modes": list(self.repeated_failure_modes),
            "misleading_signals": list(self.misleading_signals),
            "missing_information_needs": list(self.missing_information_needs),
            "next_explorations": list(self.next_explorations),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanReflection":
        required = {
            "successful_patterns",
            "failed_patterns",
            "repeated_failure_modes",
            "misleading_signals",
            "missing_information_needs",
            "next_explorations",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "PlanReflection is missing fields: " + ", ".join(missing)
            )
        return cls(
            successful_patterns=_json_string_array(data, "successful_patterns"),
            failed_patterns=_json_string_array(data, "failed_patterns"),
            repeated_failure_modes=_json_string_array(
                data, "repeated_failure_modes"
            ),
            misleading_signals=_json_string_array(data, "misleading_signals"),
            missing_information_needs=_json_string_array(
                data, "missing_information_needs"
            ),
            next_explorations=_json_string_array(data, "next_explorations"),
        )


@dataclass(frozen=True)
class PlanEvaluationSummary:
    """Dataset lineage for one comparable round evaluation."""

    evaluation_stage: str
    n_cases: int
    case_ids: tuple[str, ...]
    dataset_snapshot_ids: tuple[str, ...] = ()
    metrics_by_cohort: Mapping[str, PlanMetrics] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.evaluation_stage not in {"round", "legacy"}:
            raise ValidationError("Plan evaluation stage must be round or legacy")
        if self.n_cases < 1 or self.n_cases != len(self.case_ids):
            raise ValidationError("Plan evaluation case count does not match case ids")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValidationError("Plan evaluation case ids must be unique")
        cohorts = {str(key): value for key, value in self.metrics_by_cohort.items()}
        if cohorts and set(cohorts) != {"anchor", "random", "combined"}:
            raise ValidationError(
                "round cohort metrics must contain anchor, random, and combined"
            )
        object.__setattr__(self, "metrics_by_cohort", cohorts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_stage": self.evaluation_stage,
            "n_cases": self.n_cases,
            "case_ids": list(self.case_ids),
            "dataset_snapshot_ids": list(self.dataset_snapshot_ids),
            "metrics_by_cohort": {
                cohort: metrics.to_dict()
                for cohort, metrics in self.metrics_by_cohort.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanEvaluationSummary":
        case_ids = tuple(str(item) for item in data.get("case_ids", ()))
        raw_stage = str(data.get("evaluation_stage", "legacy"))
        return cls(
            evaluation_stage="round" if raw_stage == "round" else "legacy",
            n_cases=int(data.get("n_cases", len(case_ids))),
            case_ids=case_ids,
            dataset_snapshot_ids=tuple(
                str(item) for item in data.get("dataset_snapshot_ids", ())
            ),
            metrics_by_cohort={
                str(cohort): PlanMetrics.from_dict(dict(metrics))
                for cohort, metrics in dict(
                    data.get("metrics_by_cohort", {})
                ).items()
            },
        )


@dataclass(frozen=True)
class PlanRecord:
    """Durable Plan Archive record P=(S,E,J,R,U,T)."""

    plan: InformationPlan
    round_id: int
    embedding: tuple[float, ...]
    metrics: PlanMetrics
    reflection: PlanReflection
    signal_usage: Mapping[str, Mapping[str, int]]
    trajectories: tuple[ExecutionTrajectory, ...]
    evaluation: PlanEvaluationSummary | None = None
    fitness: FitnessEligibility | None = None

    def __post_init__(self) -> None:
        if self.round_id < 1:
            raise ValidationError("plan record round_id must be positive")
        if not self.embedding or not all(math.isfinite(item) for item in self.embedding):
            raise ValidationError("plan embedding must contain finite values")
        if not self.trajectories:
            raise ValidationError("plan record requires complete trajectories")
        object.__setattr__(self, "embedding", tuple(float(item) for item in self.embedding))
        object.__setattr__(
            self,
            "signal_usage",
            {
                ref: {str(key): int(value) for key, value in counts.items()}
                for ref, counts in self.signal_usage.items()
            },
        )
        object.__setattr__(self, "trajectories", tuple(self.trajectories))
        if self.evaluation is None:
            object.__setattr__(
                self,
                "evaluation",
                PlanEvaluationSummary(
                    evaluation_stage="legacy",
                    n_cases=len(self.trajectories),
                    case_ids=tuple(item.case_id for item in self.trajectories),
                ),
            )
        elif self.evaluation.n_cases != len(self.trajectories):
            raise ValidationError(
                "Plan evaluation metadata must cover every saved trajectory"
            )
        trajectory_case_ids = tuple(item.case_id for item in self.trajectories)
        if set(self.evaluation.case_ids) != set(trajectory_case_ids):
            raise ValidationError(
                "Plan evaluation case ids differ from saved trajectories"
            )
        if self.metrics.sample_count != len(self.trajectories):
            raise ValidationError(
                "Plan metrics sample_count differs from saved trajectories"
            )
        cohort_metrics = self.evaluation.metrics_by_cohort
        if cohort_metrics and cohort_metrics["combined"] != self.metrics:
            raise ValidationError("combined cohort metrics differ from Plan metrics")
        if self.fitness is None:
            object.__setattr__(
                self,
                "fitness",
                assess_fitness_eligibility(
                    self.trajectories,
                    expected_case_ids=self.evaluation.case_ids,
                ),
            )
        if self.metrics.predicted_positive_count != self.fitness.predicted_positive_count:
            raise ValidationError("Plan metrics and fitness predicted positives differ")
        if self.fitness.expected_case_count != len(self.evaluation.case_ids):
            raise ValidationError("Plan fitness expected case count is inconsistent")

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "parent_ids": list(self.plan.parent_ids),
            "round_id": self.round_id,
            "plan": self.plan.to_dict(),
            "embedding": list(self.embedding),
            "metrics": self.metrics.to_dict(),
            "reflection": self.reflection.to_dict(),
            "signal_usage": {
                ref: dict(counts) for ref, counts in self.signal_usage.items()
            },
            "trajectories": [item.to_dict() for item in self.trajectories],
            "fitness": self.fitness.to_dict(),
            **self.evaluation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanRecord":
        return cls(
            plan=InformationPlan.from_dict(dict(data["plan"])),
            round_id=int(data["round_id"]),
            embedding=tuple(float(item) for item in data.get("embedding", ())),
            metrics=PlanMetrics.from_dict(dict(data["metrics"])),
            reflection=PlanReflection.from_dict(dict(data["reflection"])),
            signal_usage={
                str(ref): {str(key): int(value) for key, value in dict(counts).items()}
                for ref, counts in dict(data.get("signal_usage", {})).items()
            },
            trajectories=tuple(
                ExecutionTrajectory.from_dict(item)
                for item in data.get("trajectories", ())
            ),
            evaluation=(
                PlanEvaluationSummary.from_dict(data)
                if data.get("case_ids")
                else None
            ),
            fitness=(
                FitnessEligibility.from_dict(dict(data["fitness"]))
                if isinstance(data.get("fitness"), Mapping)
                else None
            ),
        )


_FORBIDDEN_PLAN_META_KEYS = frozenset(
    {
        "basic_info_bundle",
        "case_id",
        "company_id",
        "final_context",
        "final_state",
        "identity_aliases",
        "initial_state",
        "prediction_ref",
        "raw_info",
        "trajectories",
    }
)


def _assert_plan_meta_context_free(value: Any, *, path: str = "plan_meta") -> None:
    """Reject source/context-bearing fields from proposer-visible reflection."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = re.sub(
                r"[^a-z0-9]+", "_", str(key).casefold()
            ).strip("_")
            if normalized in _FORBIDDEN_PLAN_META_KEYS:
                raise ValidationError(
                    f"forbidden context field in Plan meta reflection: {path}.{key}"
                )
            _assert_plan_meta_context_free(nested, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_plan_meta_context_free(nested, path=f"{path}[{index}]")


@dataclass(frozen=True)
class PlanMetaReflection:
    """Original case reflections plus the exact vertical Plan-critic layer."""

    plan: InformationPlan
    metrics: PlanMetrics
    metrics_by_cohort: Mapping[str, PlanMetrics]
    evaluation_snapshot_ids: tuple[str, ...]
    fitness: FitnessEligibility
    signal_usage: Mapping[str, Mapping[str, int]]
    original_case_reflections: tuple[CaseReflectionEvidence, ...]
    vertical_plan_reflection: PlanReflection
    parent_comparisons: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        cohorts = {
            str(cohort): metrics
            for cohort, metrics in self.metrics_by_cohort.items()
        }
        if cohorts and set(cohorts) != {"anchor", "random", "combined"}:
            raise ValidationError(
                "Plan meta reflection cohort metrics must contain all cohorts"
            )
        if cohorts and cohorts["combined"] != self.metrics:
            raise ValidationError(
                "Plan meta reflection combined metrics differ from metrics"
            )
        snapshot_ids = tuple(str(item) for item in self.evaluation_snapshot_ids)
        if any(not item for item in snapshot_ids) or len(set(snapshot_ids)) != len(
            snapshot_ids
        ):
            raise ValidationError("Plan meta reflection snapshot ids are invalid")
        case_reflections = tuple(self.original_case_reflections)
        if len(case_reflections) != self.metrics.sample_count:
            raise ValidationError(
                "Plan meta reflection must retain every original case reflection"
            )
        if tuple(item.case_index for item in case_reflections) != tuple(
            range(1, len(case_reflections) + 1)
        ):
            raise ValidationError(
                "Plan meta reflection case indexes must be consecutive and opaque"
            )
        if self.fitness.expected_case_count != len(case_reflections):
            raise ValidationError(
                "Plan meta reflection fitness count is inconsistent"
            )
        usage = {
            str(ref): {str(key): int(value) for key, value in counts.items()}
            for ref, counts in self.signal_usage.items()
        }
        comparisons = tuple(dict(item) for item in self.parent_comparisons)
        for comparison in comparisons:
            if comparison.get("child_plan_id") != self.plan.plan_id:
                raise ValidationError(
                    "Plan meta reflection parent comparison cites another child"
                )
            _assert_plan_meta_context_free(comparison)
        object.__setattr__(self, "metrics_by_cohort", cohorts)
        object.__setattr__(self, "evaluation_snapshot_ids", snapshot_ids)
        object.__setattr__(self, "signal_usage", usage)
        object.__setattr__(self, "original_case_reflections", case_reflections)
        object.__setattr__(self, "parent_comparisons", comparisons)

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan": self.plan.to_dict(),
            "metrics": self.metrics.to_dict(),
            "evaluation": {
                "n_cases": len(self.original_case_reflections),
                "dataset_snapshot_ids": list(self.evaluation_snapshot_ids),
                "metrics_by_cohort": {
                    cohort: metrics.to_dict()
                    for cohort, metrics in self.metrics_by_cohort.items()
                },
            },
            "fitness": self.fitness.to_dict(),
            "signal_usage": {
                ref: dict(counts) for ref, counts in self.signal_usage.items()
            },
            "original_case_reflections": [
                item.to_dict() for item in self.original_case_reflections
            ],
            "vertical_plan_reflection": self.vertical_plan_reflection.to_dict(),
            "parent_comparisons": [
                dict(item) for item in self.parent_comparisons
            ],
        }

    @classmethod
    def from_record(
        cls,
        record: PlanRecord,
        *,
        parent_comparisons: tuple[Mapping[str, Any], ...] = (),
    ) -> "PlanMetaReflection":
        """Compose the immutable original and vertical layers for one Plan."""

        return cls(
            plan=record.plan,
            metrics=record.metrics,
            metrics_by_cohort=record.evaluation.metrics_by_cohort,
            evaluation_snapshot_ids=record.evaluation.dataset_snapshot_ids,
            fitness=record.fitness,
            signal_usage=record.signal_usage,
            original_case_reflections=tuple(
                CaseReflectionEvidence.from_trajectory(
                    trajectory,
                    case_index=index,
                )
                for index, trajectory in enumerate(record.trajectories, start=1)
            ),
            vertical_plan_reflection=record.reflection,
            parent_comparisons=parent_comparisons,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanMetaReflection":
        required = {
            "plan_id",
            "plan",
            "metrics",
            "evaluation",
            "fitness",
            "signal_usage",
            "original_case_reflections",
            "vertical_plan_reflection",
            "parent_comparisons",
        }
        if set(data) != required:
            raise ValidationError("PlanMetaReflection fields are invalid")
        for field_name in (
            "plan",
            "metrics",
            "evaluation",
            "fitness",
            "signal_usage",
            "vertical_plan_reflection",
        ):
            if not isinstance(data[field_name], Mapping):
                raise ValidationError(
                    f"PlanMetaReflection {field_name} must be an object"
                )
        plan = InformationPlan.from_dict(dict(data["plan"]))
        if str(data["plan_id"]) != plan.plan_id:
            raise ValidationError("PlanMetaReflection plan id is inconsistent")
        evaluation = dict(data["evaluation"])
        if set(evaluation) != {
            "n_cases",
            "dataset_snapshot_ids",
            "metrics_by_cohort",
        }:
            raise ValidationError("PlanMetaReflection evaluation fields are invalid")
        raw_cases = data["original_case_reflections"]
        raw_comparisons = data["parent_comparisons"]
        if not isinstance(raw_cases, (list, tuple)) or not isinstance(
            raw_comparisons, (list, tuple)
        ):
            raise ValidationError("PlanMetaReflection arrays are invalid")
        if any(not isinstance(item, Mapping) for item in raw_cases) or any(
            not isinstance(item, Mapping) for item in raw_comparisons
        ):
            raise ValidationError("PlanMetaReflection arrays must contain objects")
        if not isinstance(evaluation["metrics_by_cohort"], Mapping):
            raise ValidationError(
                "PlanMetaReflection cohort metrics must be an object"
            )
        signal_usage = dict(data["signal_usage"])
        if any(not isinstance(value, Mapping) for value in signal_usage.values()):
            raise ValidationError("PlanMetaReflection Signal usage is invalid")
        result = cls(
            plan=plan,
            metrics=PlanMetrics.from_dict(dict(data["metrics"])),
            metrics_by_cohort={
                str(cohort): PlanMetrics.from_dict(dict(metrics))
                for cohort, metrics in dict(
                    evaluation["metrics_by_cohort"]
                ).items()
            },
            evaluation_snapshot_ids=_json_string_array(
                evaluation,
                "dataset_snapshot_ids",
            ),
            fitness=FitnessEligibility.from_dict(dict(data["fitness"])),
            signal_usage={
                str(ref): {
                    str(key): int(value) for key, value in dict(counts).items()
                }
                for ref, counts in signal_usage.items()
            },
            original_case_reflections=tuple(
                CaseReflectionEvidence.from_dict(dict(item))
                for item in raw_cases
            ),
            vertical_plan_reflection=PlanReflection.from_dict(
                dict(data["vertical_plan_reflection"])
            ),
            parent_comparisons=tuple(dict(item) for item in raw_comparisons),
        )
        if int(evaluation["n_cases"]) != len(result.original_case_reflections):
            raise ValidationError("PlanMetaReflection case count is inconsistent")
        return result


@dataclass(frozen=True)
class ParentPlanReflectionEvidence:
    """Anonymous aggregate evidence for comparing one actual parent to a child."""

    plan: InformationPlan
    source_scope: str
    evaluation_snapshot_ids: tuple[str, ...] = ()
    metrics_by_cohort: Mapping[str, PlanMetrics] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source_scope not in {
            "current_archive",
            "historical_seed",
            "manual_seed",
        }:
            raise ValidationError("parent reflection source scope is invalid")
        snapshot_ids = tuple(str(item) for item in self.evaluation_snapshot_ids)
        if any(not item for item in snapshot_ids) or len(set(snapshot_ids)) != len(
            snapshot_ids
        ):
            raise ValidationError("parent reflection snapshot ids are invalid")
        cohorts = {
            str(cohort): metrics for cohort, metrics in self.metrics_by_cohort.items()
        }
        if cohorts and set(cohorts) != {"anchor", "random", "combined"}:
            raise ValidationError(
                "parent reflection metrics must contain every evaluation cohort"
            )
        object.__setattr__(self, "evaluation_snapshot_ids", snapshot_ids)
        object.__setattr__(self, "metrics_by_cohort", cohorts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_scope": self.source_scope,
            "parent_plan": self.plan.to_dict(),
            "evaluation_snapshot_ids": list(self.evaluation_snapshot_ids),
            "metrics_by_cohort": {
                cohort: metrics.to_dict()
                for cohort, metrics in self.metrics_by_cohort.items()
            },
        }


def build_parent_plan_comparison(
    *,
    parent: ParentPlanReflectionEvidence,
    child_plan: InformationPlan,
    child_metrics: PlanMetrics,
    child_snapshot_id: str,
) -> dict[str, Any]:
    """Build a label-free Plan diff and only exactly comparable metric deltas."""

    if parent.plan.plan_id not in child_plan.parent_ids:
        raise ValidationError("parent comparison is outside child Plan lineage")
    if not child_snapshot_id:
        raise ValidationError("child evaluation snapshot id is required")
    parent_requests = {
        request.request_id: request
        for request in parent.plan.basic_info_policy.requests
    }
    child_requests = {
        request.request_id: request
        for request in child_plan.basic_info_policy.requests
    }
    added = [
        child_requests[request_id].to_dict()
        for request_id in sorted(set(child_requests) - set(parent_requests))
    ]
    removed = [
        parent_requests[request_id].to_dict()
        for request_id in sorted(set(parent_requests) - set(child_requests))
    ]
    modified = [
        {
            "request_id": request_id,
            "before": parent_requests[request_id].to_dict(),
            "after": child_requests[request_id].to_dict(),
        }
        for request_id in sorted(set(parent_requests).intersection(child_requests))
        if parent_requests[request_id].to_dict()
        != child_requests[request_id].to_dict()
    ]
    text_changes = {
        field_name: {
            "before": str(getattr(parent.plan, field_name)),
            "after": str(getattr(child_plan, field_name)),
        }
        for field_name in (
            "initial_research_skill",
            "reflection_skill",
            "analysis_prompt",
        )
        if str(getattr(parent.plan, field_name))
        != str(getattr(child_plan, field_name))
    }
    same_snapshot = parent.evaluation_snapshot_ids == (child_snapshot_id,)
    parent_combined = parent.metrics_by_cohort.get("combined")
    metric_delta: dict[str, Any] | None = None
    if same_snapshot and parent_combined is not None:
        metric_delta = {
            "binary_f1": child_metrics.binary_f1 - parent_combined.binary_f1,
            "binary_precision": (
                child_metrics.binary_precision - parent_combined.binary_precision
            ),
            "binary_recall": (
                child_metrics.binary_recall - parent_combined.binary_recall
            ),
            "confusion": {
                "true_positive": (
                    child_metrics.true_positive - parent_combined.true_positive
                ),
                "false_positive": (
                    child_metrics.false_positive - parent_combined.false_positive
                ),
                "true_negative": (
                    child_metrics.true_negative - parent_combined.true_negative
                ),
                "false_negative": (
                    child_metrics.false_negative - parent_combined.false_negative
                ),
            },
        }
    return {
        **parent.to_dict(),
        "child_plan_id": child_plan.plan_id,
        "child_evaluation_snapshot_id": child_snapshot_id,
        "same_evaluation_snapshot": same_snapshot,
        "plan_diff": {
            "basic_info_requests_added": added,
            "basic_info_requests_removed": removed,
            "basic_info_requests_modified": modified,
            "text_fields_changed": text_changes,
        },
        "metric_delta": metric_delta,
    }


class PlanEmbedder(Protocol):
    """Embeds a canonicalized Plan for diversity selection."""

    def embed(self, plan: InformationPlan) -> tuple[float, ...]:
        """Return a finite fixed-length vector."""


class HashingPlanEmbedder:
    """Dependency-free deterministic bag-of-token Plan embedder."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions < 8:
            raise ValidationError("plan embedding dimensions must be at least 8")
        self.dimensions = dimensions

    def embed(self, plan: InformationPlan) -> tuple[float, ...]:
        canonical = json.dumps(plan.canonical_dict(), sort_keys=True)
        vector = [0.0] * self.dimensions
        normalized = " ".join(canonical.casefold().split())
        tokens = re.findall(r"\w+", normalized, flags=re.UNICODE)
        compact = "".join(character for character in normalized if not character.isspace())
        tokens.extend(
            f"char3:{compact[index:index + 3]}"
            for index in range(max(0, len(compact) - 2))
        )
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0:
            raise ValidationError("canonicalized plan produced empty embedding")
        return tuple(item / norm for item in vector)


@dataclass(frozen=True)
class ParentSelection:
    """Quality-diverse Top-K records plus random exploration records."""

    top: tuple[PlanRecord, ...]
    random: tuple[PlanRecord, ...]

    @property
    def records(self) -> tuple[PlanRecord, ...]:
        return self.top + self.random

    @property
    def plans(self) -> tuple[InformationPlan, ...]:
        return tuple(record.plan for record in self.records)


class PlanArchive:
    """Committed in-memory Plan records with quality-diverse parent selection."""

    def __init__(self, records: Iterable[PlanRecord] = ()) -> None:
        self._records: dict[str, PlanRecord] = {}
        for record in records:
            self.add(record)

    @property
    def records(self) -> tuple[PlanRecord, ...]:
        return tuple(
            sorted(
                self._records.values(),
                key=lambda record: (record.round_id, record.plan_id),
            )
        )

    def add(self, record: PlanRecord) -> None:
        if record.plan_id in self._records:
            raise ValidationError(f"duplicate plan archive id: {record.plan_id}")
        self._records[record.plan_id] = record

    def select_parents(
        self,
        *,
        top_k: int,
        random_k: int = 2,
        similarity_threshold: float = 0.9,
        rng: random.Random | None = None,
    ) -> ParentSelection:
        """Select by binary F1, then remove embedding-near duplicates."""

        if top_k < 1 or random_k < 0:
            raise ValidationError("parent selection counts are invalid")
        if not -1 < similarity_threshold <= 1:
            raise ValidationError("similarity threshold must be in (-1, 1]")
        ranked = sorted(
            (
                record
                for record in self._records.values()
                if record.fitness is not None and record.fitness.eligible
            ),
            key=lambda record: (-record.metrics.binary_f1, record.plan_id),
        )
        selected: list[PlanRecord] = []
        for record in ranked:
            if all(
                cosine_similarity(record.embedding, kept.embedding)
                < similarity_threshold
                for kept in selected
            ):
                selected.append(record)
            if len(selected) == top_k:
                break
        selected_ids = {record.plan_id for record in selected}
        exploration_pool = [
            record for record in ranked if record.plan_id not in selected_ids
        ]
        generator = rng or random.Random()
        random_records = tuple(
            generator.sample(exploration_pool, min(random_k, len(exploration_pool)))
        )
        return ParentSelection(top=tuple(selected), random=random_records)


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    """Return cosine similarity for equal finite vectors."""

    left_values = tuple(float(item) for item in left)
    right_values = tuple(float(item) for item in right)
    if not left_values or len(left_values) != len(right_values):
        raise ValidationError("cosine vectors must be non-empty and equal length")
    left_norm = math.sqrt(sum(item * item for item in left_values))
    right_norm = math.sqrt(sum(item * item for item in right_values))
    if left_norm == 0 or right_norm == 0:
        raise ValidationError("cosine vectors cannot have zero norm")
    return sum(a * b for a, b in zip(left_values, right_values)) / (
        left_norm * right_norm
    )


@dataclass(frozen=True)
class RoundMetaEntry:
    """One additive original/vertical/horizontal reflection FIFO entry."""

    round_id: int
    plan_reflections: tuple[PlanMetaReflection, ...] = ()
    successful_patterns: tuple[str, ...] = ()
    failed_patterns: tuple[str, ...] = ()
    false_positive_patterns: tuple[str, ...] = ()
    false_negative_patterns: tuple[str, ...] = ()
    useful_signals: tuple[str, ...] = ()
    suspicious_signals: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    search_implications: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.round_id < 1:
            raise ValidationError("meta entry round_id must be positive")
        plan_reflections = tuple(self.plan_reflections)
        plan_ids = tuple(item.plan_id for item in plan_reflections)
        if len(set(plan_ids)) != len(plan_ids):
            raise ValidationError("round meta Plan reflections must be unique")
        object.__setattr__(self, "plan_reflections", plan_reflections)
        for name in (
            "successful_patterns",
            "failed_patterns",
            "false_positive_patterns",
            "false_negative_patterns",
            "useful_signals",
            "suspicious_signals",
            "missing_capabilities",
            "search_implications",
            "evidence_refs",
        ):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))
        if not self.evidence_refs:
            raise ValidationError("round meta entry requires experiment evidence refs")
        if plan_ids and not set(self.evidence_refs).issubset(set(plan_ids)):
            raise ValidationError(
                "round meta entry cites evidence outside new experiments"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "plan_reflections": [
                item.to_dict() for item in self.plan_reflections
            ],
            "plan_level": {
                "successful_patterns": list(self.successful_patterns),
                "failed_patterns": list(self.failed_patterns),
            },
            "prediction_errors": {
                "false_positive": list(self.false_positive_patterns),
                "false_negative": list(self.false_negative_patterns),
            },
            "signal_observations": {
                "useful": list(self.useful_signals),
                "suspicious": list(self.suspicious_signals),
                "missing_capabilities": list(self.missing_capabilities),
            },
            "search_implications": list(self.search_implications),
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RoundMetaEntry":
        required = {
            "round_id",
            "plan_level",
            "prediction_errors",
            "signal_observations",
            "search_implications",
            "evidence_refs",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "RoundMetaEntry is missing fields: " + ", ".join(missing)
            )
        allowed = required | {"plan_reflections"}
        if set(data) - allowed:
            raise ValidationError("RoundMetaEntry contains unknown fields")
        for field_name in (
            "plan_level",
            "prediction_errors",
            "signal_observations",
        ):
            if not isinstance(data[field_name], Mapping):
                raise ValidationError(f"RoundMetaEntry {field_name} must be an object")
        plan_level = dict(data["plan_level"])
        prediction_errors = dict(data["prediction_errors"])
        observations = dict(data["signal_observations"])
        if set(plan_level) != {"successful_patterns", "failed_patterns"}:
            raise ValidationError("RoundMetaEntry plan_level fields are invalid")
        if set(prediction_errors) != {"false_positive", "false_negative"}:
            raise ValidationError("RoundMetaEntry prediction_errors fields are invalid")
        if set(observations) != {"useful", "suspicious", "missing_capabilities"}:
            raise ValidationError("RoundMetaEntry signal_observations fields are invalid")
        raw_plan_reflections = data.get("plan_reflections", ())
        if not isinstance(raw_plan_reflections, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in raw_plan_reflections
        ):
            raise ValidationError("RoundMetaEntry plan_reflections must be objects")
        return cls(
            round_id=int(data["round_id"]),
            plan_reflections=tuple(
                PlanMetaReflection.from_dict(dict(item))
                for item in raw_plan_reflections
            ),
            successful_patterns=_json_string_array(
                plan_level, "successful_patterns"
            ),
            failed_patterns=_json_string_array(plan_level, "failed_patterns"),
            false_positive_patterns=_json_string_array(
                prediction_errors, "false_positive"
            ),
            false_negative_patterns=_json_string_array(
                prediction_errors, "false_negative"
            ),
            useful_signals=_json_string_array(observations, "useful"),
            suspicious_signals=_json_string_array(observations, "suspicious"),
            missing_capabilities=_json_string_array(
                observations, "missing_capabilities"
            ),
            search_implications=_json_string_array(data, "search_implications"),
            evidence_refs=_json_string_array(data, "evidence_refs"),
        )

    def append_plan_reflections(
        self,
        plan_reflections: Iterable[PlanMetaReflection],
    ) -> "RoundMetaEntry":
        """Return the completed entry without rewriting horizontal reflection."""

        if self.plan_reflections:
            raise ValidationError("round meta Plan reflections are already appended")
        appended = tuple(plan_reflections)
        if not appended:
            raise ValidationError("round meta requires additive Plan reflections")
        return RoundMetaEntry(
            round_id=self.round_id,
            plan_reflections=appended,
            successful_patterns=self.successful_patterns,
            failed_patterns=self.failed_patterns,
            false_positive_patterns=self.false_positive_patterns,
            false_negative_patterns=self.false_negative_patterns,
            useful_signals=self.useful_signals,
            suspicious_signals=self.suspicious_signals,
            missing_capabilities=self.missing_capabilities,
            search_implications=self.search_implications,
            evidence_refs=self.evidence_refs,
        )


class PlanMetaMemory:
    """One fixed-length FIFO of recent experiment-grounded round reflections."""

    def __init__(
        self,
        maxlen: int = 10,
        entries: Iterable[RoundMetaEntry] = (),
    ) -> None:
        if maxlen < 1:
            raise ValidationError("meta memory maxlen must be positive")
        self.maxlen = maxlen
        self._entries: list[RoundMetaEntry] = []
        for entry in entries:
            self.append(entry)

    @property
    def entries(self) -> tuple[RoundMetaEntry, ...]:
        return tuple(self._entries)

    def append(self, entry: RoundMetaEntry) -> None:
        if self._entries and entry.round_id <= self._entries[-1].round_id:
            raise ValidationError("round meta entries must advance monotonically")
        self._entries.append(entry)
        self._entries = self._entries[-self.maxlen :]

    def model_view(self, *, max_chars: int = 48_000) -> tuple[Mapping[str, Any], ...]:
        """Derive a bounded FIFO view while retaining one aggregate per round."""

        def compact_strings(
            values: Iterable[Any], *, count: int = 3, chars: int = 160
        ) -> list[str]:
            return [str(item)[:chars] for item in tuple(values)[:count]]

        def compact_reflection(value: Mapping[str, Any]) -> dict[str, Any]:
            return {
                str(key): compact_strings(items, chars=240)
                if isinstance(items, (list, tuple))
                else items
                for key, items in value.items()
            }

        def reflection_detail_score(case: CaseReflectionEvidence) -> int:
            value = case.self_reflection.to_dict()
            return sum(
                len(str(item))
                for field_value in value.values()
                if isinstance(field_value, (list, tuple))
                for item in field_value
            )

        bases: list[dict[str, Any]] = []
        for entry in self._entries:
            assessment_counts: dict[str, int] = {}
            for plan in entry.plan_reflections:
                for case in plan.original_case_reflections:
                    assessment = str(
                        case.candidate_judgment_feedback.get("assessment", "unknown")
                    )
                    assessment_counts[assessment] = assessment_counts.get(assessment, 0) + 1
            bases.append(
                {
                    "round_id": entry.round_id,
                    "aggregate": {
                        "plan_count": len(entry.plan_reflections),
                        "evidence_refs": compact_strings(entry.evidence_refs, chars=80),
                        "assessment_counts": dict(sorted(assessment_counts.items())),
                        "successful_patterns": compact_strings(entry.successful_patterns),
                        "failed_patterns": compact_strings(entry.failed_patterns),
                        "false_positive_patterns": compact_strings(entry.false_positive_patterns),
                        "false_negative_patterns": compact_strings(entry.false_negative_patterns),
                        "useful_signals": compact_strings(entry.useful_signals),
                        "suspicious_signals": compact_strings(entry.suspicious_signals),
                        "missing_capabilities": compact_strings(entry.missing_capabilities),
                        "search_implications": compact_strings(entry.search_implications),
                    },
                    "representative_details": [],
                }
            )
        if len(json.dumps(bases, ensure_ascii=False, sort_keys=True)) > max_chars:
            raise ValidationError("round aggregate meta view exceeds fixed context limit")

        by_round = {int(item["round_id"]): item for item in bases}
        for entry in reversed(self._entries):
            details = by_round[entry.round_id]["representative_details"]
            for plan in reversed(entry.plan_reflections):
                best_by_assessment: dict[
                    str, tuple[int, int, CaseReflectionEvidence]
                ] = {}
                for case in plan.original_case_reflections:
                    assessment = str(
                        case.candidate_judgment_feedback.get("assessment", "unknown")
                    )
                    candidate = (
                        reflection_detail_score(case),
                        case.case_index,
                        case,
                    )
                    current = best_by_assessment.get(assessment)
                    if current is None or candidate[0] > current[0] or (
                        candidate[0] == current[0] and candidate[1] < current[1]
                    ):
                        best_by_assessment[assessment] = candidate
                representatives = [
                    {
                        "case_index": case.case_index,
                        "assessment": assessment,
                        "stop_reason": case.stop_reason.value,
                        "self_reflection": compact_reflection(
                            case.self_reflection.to_dict()
                        ),
                    }
                    for assessment, (_score, _case_index, case) in sorted(
                        best_by_assessment.items(),
                        key=lambda item: (-item[1][0], item[1][1], item[0]),
                    )[:6]
                ]
                candidate = {
                    "plan_id": plan.plan_id,
                    "metrics": plan.metrics.to_dict(),
                    "fitness": plan.fitness.to_dict(),
                    "vertical": compact_reflection(
                        plan.vertical_plan_reflection.to_dict()
                    ),
                    "representative_cases": representatives,
                }
                details.append(candidate)
                if len(json.dumps(bases, ensure_ascii=False, sort_keys=True)) > max_chars:
                    details.pop()
                    break
        return tuple(bases)


@dataclass(frozen=True)
class EvolutionPriors:
    """Fixed framework prompts H_R, H_P, H_E, and H_U."""

    reflect_round: str
    propose_plan: str
    mine_signal: str
    update_signal: str

    def __post_init__(self) -> None:
        for name in (
            "reflect_round",
            "propose_plan",
            "mine_signal",
            "update_signal",
        ):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"evolution prior {name} must not be empty")


DEFAULT_EVOLUTION_PRIORS = EvolutionPriors(
    reflect_round=(
        "Reflect only on the supplied completed Information Plan experiments. "
        "Add horizontal cross-Plan patterns, prediction errors, Signal observations, "
        "missing capabilities, and testable search implications with evidence refs. "
        "Do not rewrite the preserved original case or vertical Plan layers."
    ),
    propose_plan=(
        "Propose one complete Information Plan S=(B,H_init,H_reflect,H_analyse). "
        "Use the quality-diverse parents and every layer of the additive FIFO "
        "experiment lessons, make an attributable change, and never change labels, "
        "datasets, metrics, priors, runtime guards, or the stable Signal Registry."
    ),
    mine_signal=(
        "Follow this workflow exactly: sample issuer-distinct label-stratified "
        "Discovery cases; inspect point-in-time Raw Info for positive cases and "
        "matched controls; check Signal cards and exact stable specs for duplicates; "
        "stage one complete evidence-traceable candidate with non-empty executable "
        "fixtures; run its contract tests; then return only successfully staged and "
        "tested candidate refs. Use only registered deterministic functions. If no "
        "candidate passes, return an empty candidate_refs list."
    ),
    update_signal=(
        "Follow this workflow exactly: load one exact stable SignalSpec; inspect its "
        "observed-policy statistics and structured committed failure cases; sample "
        "label-stratified Discovery cases and inspect their point-in-time Raw Info; "
        "clone exactly vNext while preserving signal_id, "
        "category, execution type, and deterministic function; provide non-empty "
        "executable fixtures; run its contract tests; then return only successfully "
        "staged and tested candidate refs. Never invent a deterministic function. "
        "If no candidate passes, return an empty candidate_refs list."
    ),
)


class InformationPlanProposer(Protocol):
    """Conditional candidate sampler called independently for every child."""

    def propose(
        self,
        *,
        round_id: int,
        candidate_index: int,
        candidate_count: int,
        proposal_attempt: int,
        forbidden_plan_ids: tuple[str, ...],
        parents: tuple[InformationPlan, ...],
        meta_info: tuple[RoundMetaEntry, ...],
        prior: str,
    ) -> InformationPlan:
        """Return one complete candidate Plan."""


class CandidateProposalRejected(ValidationError):
    """Raised only after model Plan content exhausts bounded correction."""


class PlanCritic(Protocol):
    """Summarizes Plan behavior over its full validation batch."""

    def critique(
        self,
        *,
        plan: InformationPlan,
        trajectories: tuple[ExecutionTrajectory, ...],
        metrics: PlanMetrics,
        parent_comparisons: tuple[Mapping[str, Any], ...] = (),
    ) -> PlanReflection:
        """Return repeated strengths, failures, and next explorations."""


class RoundReflector(Protocol):
    """Applies fixed H_R to new round experiments, never to old meta alone."""

    def reflect(
        self,
        *,
        round_id: int,
        records: tuple[PlanRecord, ...],
        prior: str,
        parent_comparisons_by_plan_id: Mapping[
            str, tuple[Mapping[str, Any], ...]
        ] | None = None,
    ) -> RoundMetaEntry:
        """Return one grounded FIFO entry with record evidence refs."""


class PlanEvaluator(Protocol):
    """Evaluates one Plan on label-hidden evolution-validation cases."""

    def evaluate(
        self,
        plan: InformationPlan,
        cases: tuple[EvolutionCase, ...],
        signal_registry: FrozenSignalRegistry,
    ) -> PlanEvaluationAttempt | tuple[ExecutionTrajectory, ...]:
        """Return one bounded attempt after the persistence/reveal boundary."""


class RuntimePlanEvaluator:
    """Concrete Plan evaluator using the adaptive runtime and a durable sink."""

    def __init__(
        self,
        *,
        raw_info_store: RawInfoStore,
        evidence_resolver: EvidenceResolver | None = None,
        controller: ResearchController,
        signal_agent: SignalRetrievalAgent,
        predictor: BlindPredictor,
        prediction_root: str | Path,
        trajectory_root: str | Path | None = None,
        limits: RuntimeLimits = RuntimeLimits(),
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        llm_signal_runner: LLMSignalRunner | None = None,
        signal_readiness_snapshot: FrozenSignalRegistry | None = None,
        minimum_signal_readiness: float = 0.8,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        if not 0 < minimum_signal_readiness <= 1:
            raise ValidationError("minimum Signal readiness must be in (0, 1]")
        self.raw_info_store = raw_info_store
        self.evidence_resolver = evidence_resolver or EvidenceResolver(raw_info_store)
        self.controller = controller
        self.signal_agent = signal_agent
        self.predictor = predictor
        self.prediction_root = Path(prediction_root)
        self.prediction_root.mkdir(parents=True, exist_ok=True)
        self.trajectory_root = (
            Path(trajectory_root)
            if trajectory_root is not None
            else self.prediction_root.parent / "trajectories"
        )
        self.trajectory_root.mkdir(parents=True, exist_ok=True)
        self.limits = limits
        self.deterministic_functions = deterministic_functions
        self.llm_signal_runner = llm_signal_runner
        self.signal_readiness_snapshot = signal_readiness_snapshot
        self.minimum_signal_readiness = minimum_signal_readiness
        self.on_progress = on_progress

    def check_case_readiness(
        self, case: EvolutionCase
    ) -> EvaluationCaseReadiness:
        """Materialize the fixed label-free market backbone before Plan work."""

        resolution = self.evidence_resolver.resolve(
            RawInfoRequest(
                request_id="fixed_evaluation_market_backbone",
                description=(
                    "Read the point-in-time daily market backbone required by "
                    "the fixed evaluation evidence gate."
                ),
                source_types=("market_data",),
                lookback_days=60,
                max_documents=1,
            ),
            company_id=case.company_id,
            identity=case.basic_info,
            as_of=case.prediction_time,
        )
        if resolution.status == "resolved":
            signal_resolutions: tuple[RawInfoResolution, ...] = ()
            if self.signal_readiness_snapshot is not None:
                executor = SignalExecutor(
                    self.signal_readiness_snapshot,
                    self.raw_info_store,
                    resolver=self.evidence_resolver,
                    deterministic_functions=self.deterministic_functions,
                    llm_runner=self.llm_signal_runner,
                )
                signal_resolutions = executor.prepare_inputs(
                    (
                        spec.ref
                        for spec in self.signal_readiness_snapshot.specs
                    ),
                    company_id=case.company_id,
                    as_of=case.prediction_time,
                    identity=case.basic_info,
                )
                ready_count = sum(
                    item.status == "resolved" for item in signal_resolutions
                )
                total_count = len(signal_resolutions)
                ready_fraction = (
                    ready_count / total_count if total_count else 1.0
                )
                if ready_fraction < self.minimum_signal_readiness:
                    failed = tuple(
                        item for item in signal_resolutions
                        if item.status != "resolved"
                    )
                    failed_reasons = {
                        str(event.details.get("reason", ""))
                        for item in failed
                        for event in item.events
                        if event.kind == "acquisition_failed"
                    }
                    result = EvaluationCaseReadiness(
                        case.case_id,
                        False,
                        (
                            "signal_data_readiness_below_threshold:"
                            f"{ready_count}/{total_count}"
                        ),
                        retryable="provider_error" in failed_reasons,
                    )
                    _emit_progress(
                        self.on_progress,
                        "evaluation_case_signal_data_unavailable",
                        **result.to_dict(),
                        minimum_signal_readiness=self.minimum_signal_readiness,
                        ready_signal_count=ready_count,
                        total_signal_count=total_count,
                        unready_signals={
                            item.request.request_id.removeprefix("signal:"): (
                                item.gap.reason.value
                                if item.gap is not None
                                else "no_matching_documents"
                            )
                            for item in failed
                        },
                    )
                    return result
            result = EvaluationCaseReadiness(case.case_id, True)
            _emit_progress(
                self.on_progress,
                "evaluation_case_data_ready",
                case_id=case.case_id,
                document_count=len(resolution.documents),
                appended_document_count=len(resolution.appended_documents),
                ready_signal_count=sum(
                    item.status == "resolved" for item in signal_resolutions
                ),
                total_signal_count=len(signal_resolutions),
            )
            return result
        failed_reasons = {
            str(event.details.get("reason", ""))
            for event in resolution.events
            if event.kind == "acquisition_failed"
        }
        reason = (
            resolution.gap.reason.value
            if resolution.gap is not None
            else "no_matching_documents"
        )
        result = EvaluationCaseReadiness(
            case.case_id,
            False,
            reason,
            retryable="provider_error" in failed_reasons,
        )
        _emit_progress(
            self.on_progress,
            "evaluation_case_data_unavailable",
            **result.to_dict(),
            provider=(resolution.gap.provider if resolution.gap else None),
            attempted_providers=[
                str(event.details.get("provider", ""))
                for event in resolution.events
                if event.kind == "acquisition_started"
            ],
        )
        return result

    def evaluate(
        self,
        plan: InformationPlan,
        cases: tuple[EvolutionCase, ...],
        signal_registry: FrozenSignalRegistry,
    ) -> PlanEvaluationAttempt:
        if not cases:
            raise ValidationError("evolution validation cases must not be empty")
        expected_case_ids = tuple(item.case_id for item in cases)
        executor = SignalExecutor(
            signal_registry,
            self.raw_info_store,
            resolver=self.evidence_resolver,
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_signal_runner,
        )
        trajectories: list[ExecutionTrajectory] = []

        def stop_after_unfinalized(
            trajectory: ExecutionTrajectory,
        ) -> PlanEvaluationAttempt | None:
            if _trajectory_is_fitness_finalized(trajectory):
                return None
            _emit_progress(
                self.on_progress,
                "candidate_evaluation_stopped",
                plan_id=plan.plan_id,
                case_id=trajectory.case_id,
                reason="unfinalized_case",
                stop_reason=trajectory.stop_reason.value,
                completed_case_count=len(trajectories),
                expected_case_count=len(cases),
            )
            return PlanEvaluationAttempt(
                plan=plan,
                expected_case_ids=expected_case_ids,
                trajectories=tuple(trajectories),
            )

        for case_index, case in enumerate(cases, start=1):
            case_path = self.prediction_root / plan.plan_id / f"{case.case_id}.json"
            trajectory_path = (
                self.trajectory_root / plan.plan_id / f"{case.case_id}.json"
            )
            input_hash = _canonical_hash(
                {
                    "schema_version": "execution-trajectory-input-v1",
                    "plan": plan.to_dict(),
                    "case": {
                        "case_id": case.case_id,
                        "company_id": case.company_id,
                        "prediction_time": case.prediction_time.isoformat(),
                        "basic_info": dict(case.basic_info),
                        "ground_truth": case.ground_truth.to_dict(),
                    },
                    "signal_registry_hash": signal_registry.registry_hash,
                    "signal_learning_hash": signal_registry.learning_hash,
                    "runtime_limits": self.limits.to_dict(),
                }
            )
            if trajectory_path.exists():
                staged = _read_json(trajectory_path)
                if (
                    staged.get("schema_version")
                    != "execution-trajectory-checkpoint-v1"
                    or staged.get("input_hash") != input_hash
                ):
                    raise ValidationError(
                        f"conflicting staged execution trajectory: {trajectory_path}"
                    )
                trajectory = ExecutionTrajectory.from_dict(
                    dict(staged.get("trajectory", {}))
                )
                if trajectory.case_id != case.case_id:
                    raise ValidationError("staged execution trajectory case mismatch")
                trajectories.append(trajectory)
                _emit_progress(
                    self.on_progress,
                    "case_trajectory_reused",
                    plan_id=plan.plan_id,
                    case_id=case.case_id,
                    case_index=case_index,
                    case_count=len(cases),
                    trajectory_path=str(trajectory_path),
                )
                stopped_attempt = stop_after_unfinalized(trajectory)
                if stopped_attempt is not None:
                    return stopped_attempt
                continue

            _emit_progress(
                self.on_progress,
                "case_started",
                plan_id=plan.plan_id,
                case_id=case.case_id,
                case_index=case_index,
                case_count=len(cases),
            )

            def sink(
                company_id: str,
                prediction_time: datetime,
                final_context: Mapping[str, Any],
                prediction: BlindPrediction,
                *,
                path: Path = case_path,
                expected_case_id: str = case.case_id,
            ) -> str:
                _write_or_verify_json(
                    path,
                    {
                        "case_id": expected_case_id,
                        "company_id": company_id,
                        "prediction_time": prediction_time.isoformat(),
                        "final_context": dict(final_context),
                        "prediction": prediction.to_dict(),
                    },
                )
                return str(path)

            def truth_provider(
                company_id: str,
                *,
                path: Path = case_path,
                expected_company_id: str = case.company_id,
                truth: GroundTruth = case.ground_truth,
            ) -> GroundTruth:
                if not path.exists():
                    raise ValidationError("ground truth requested before prediction persistence")
                if company_id != expected_company_id:
                    raise ValidationError("ground truth requested for the wrong case")
                return truth

            try:
                trajectory = execute_information_plan(
                    plan=plan,
                    company_id=case.company_id,
                    case_id=case.case_id,
                    company_basic_source=case.basic_info,
                    prediction_time=case.prediction_time,
                    signal_registry=signal_registry,
                    signal_executor=executor,
                    controller=self.controller,
                    signal_agent=self.signal_agent,
                    predictor=self.predictor,
                    prediction_sink=sink,
                    ground_truth_provider=truth_provider,
                    limits=self.limits,
                )
            except ValidationError as exc:
                stage = (
                    exc.stage
                    if isinstance(exc, CandidateExecutionRejected)
                    else "case_execution"
                )
                failure_path = (
                    self.trajectory_root
                    / plan.plan_id
                    / f"{case.case_id}.failure.json"
                )
                failure = CaseEvaluationFailure(
                    case_id=case.case_id,
                    stage=stage,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    artifact_ref=str(failure_path),
                )
                _write_or_verify_json(
                    failure_path,
                    {
                        "schema_version": "case-evaluation-failure-v1",
                        "input_hash": input_hash,
                        **failure.to_dict(),
                    },
                )
                _emit_progress(
                    self.on_progress,
                    "case_evaluation_failed",
                    plan_id=plan.plan_id,
                    case_id=case.case_id,
                    stage=stage,
                    error_type=type(exc).__name__,
                    failure_path=str(failure_path),
                )
                return PlanEvaluationAttempt(
                    plan=plan,
                    expected_case_ids=expected_case_ids,
                    trajectories=tuple(trajectories),
                    failures=(failure,),
                )
            _write_or_verify_json(
                trajectory_path,
                {
                    "schema_version": "execution-trajectory-checkpoint-v1",
                    "input_hash": input_hash,
                    "plan_id": plan.plan_id,
                    "case_id": case.case_id,
                    "trajectory": trajectory.to_dict(),
                },
            )
            trajectories.append(trajectory)
            _emit_progress(
                self.on_progress,
                "case_completed",
                plan_id=plan.plan_id,
                case_id=case.case_id,
                case_index=case_index,
                case_count=len(cases),
                stop_reason=trajectory.stop_reason.value,
                signal_rounds=trajectory.usage.signal_rounds,
                signal_calls=trajectory.usage.signal_calls,
                llm_calls=trajectory.usage.model.llm_calls,
                tokens=trajectory.usage.model.tokens,
                cost=trajectory.usage.model.cost,
                trajectory_path=str(trajectory_path),
            )
            stopped_attempt = stop_after_unfinalized(trajectory)
            if stopped_attempt is not None:
                return stopped_attempt
        return PlanEvaluationAttempt(
            plan=plan,
            expected_case_ids=expected_case_ids,
            trajectories=tuple(trajectories),
        )


class EvolutionWorkspace:
    """Atomic committed-round persistence and recovery boundary."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.plans_root = self.root / "plans"
        self.experiments_root = self.root / "experiments"
        self.meta_root = self.root / "meta"
        self.cache_root = self.root / "cache"
        self.evaluation_root = self.root / "evaluation"
        self.trajectory_root = self.experiments_root / "trajectories"
        for path in (
            self.plans_root,
            self.experiments_root,
            self.meta_root,
            self.cache_root,
            self.evaluation_root,
            self.trajectory_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            _atomic_write_json(self.state_path, {"last_completed_round": 0})
        self._event_sequence = _last_event_sequence(self.trajectory_events_path)

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def cycle_state_path(self) -> Path:
        return self.root / "cycle_state.json"

    @property
    def trajectory_events_path(self) -> Path:
        return self.experiments_root / "trajectory.jsonl"

    @property
    def last_completed_round(self) -> int:
        return int(_read_json(self.state_path).get("last_completed_round", 0))

    @property
    def last_completed_cycle(self) -> int:
        if not self.cycle_state_path.exists():
            return 0
        return int(_read_json(self.cycle_state_path).get("last_completed_cycle", 0))

    @contextmanager
    def execution_lock(self) -> Iterator[None]:
        """Prevent concurrent cycle executors from mutating one workspace."""

        with self.execution_lock_at(self.root):
            yield

    @staticmethod
    @contextmanager
    def execution_lock_at(root: str | Path) -> Iterator[None]:
        """Lock an existing workspace without materializing runtime directories."""

        lock_path = Path(root) / ".evolution-run.lock"
        with lock_path.open("a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValidationError(
                    "evolution workspace already has an active cycle executor"
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def staged_candidate_plan(
        self,
        *,
        round_id: int,
        candidate_index: int,
        candidate_count: int,
        selected_parent_ids: tuple[str, ...],
        run_contract_hash: str,
    ) -> tuple[InformationPlan, int] | None:
        """Load one exact accepted candidate checkpoint for restart recovery."""

        path = self._candidate_plan_path(round_id, candidate_index)
        if not path.exists():
            return None
        payload = _read_json(path)
        expected_identity = {
            "schema_version": "information-plan-candidate-checkpoint-v1",
            "round_id": round_id,
            "candidate_index": candidate_index,
            "candidate_count": candidate_count,
            "selected_parent_ids": list(selected_parent_ids),
            "run_contract_hash": run_contract_hash,
        }
        if any(payload.get(key) != value for key, value in expected_identity.items()):
            raise ValidationError("staged candidate Plan identity mismatch")
        raw_plan = payload.get("plan")
        proposal_attempt = payload.get("proposal_attempt")
        if not isinstance(raw_plan, Mapping) or (
            isinstance(proposal_attempt, bool)
            or not isinstance(proposal_attempt, int)
            or proposal_attempt < 1
        ):
            raise ValidationError("staged candidate Plan payload is invalid")
        plan = InformationPlan.from_dict(raw_plan)
        if tuple(plan.parent_ids) != selected_parent_ids:
            raise ValidationError("staged candidate Plan lineage mismatch")
        return plan, proposal_attempt

    def stage_candidate_plan(
        self,
        *,
        round_id: int,
        candidate_index: int,
        candidate_count: int,
        selected_parent_ids: tuple[str, ...],
        proposal_attempt: int,
        run_contract_hash: str,
        plan: InformationPlan,
    ) -> Path:
        """Persist one accepted candidate before its first evaluation case."""

        if round_id < 1 or candidate_index < 1 or candidate_index > candidate_count:
            raise ValidationError("candidate Plan checkpoint slot is invalid")
        if proposal_attempt < 1 or tuple(plan.parent_ids) != selected_parent_ids:
            raise ValidationError("candidate Plan checkpoint lineage is invalid")
        path = self._candidate_plan_path(round_id, candidate_index)
        _write_or_verify_json(
            path,
            {
                "schema_version": "information-plan-candidate-checkpoint-v1",
                "round_id": round_id,
                "candidate_index": candidate_index,
                "candidate_count": candidate_count,
                "selected_parent_ids": list(selected_parent_ids),
                "proposal_attempt": proposal_attempt,
                "run_contract_hash": run_contract_hash,
                "plan": plan.to_dict(),
            },
        )
        return path

    def _candidate_plan_path(self, round_id: int, candidate_index: int) -> Path:
        if round_id < 1 or candidate_index < 1:
            raise ValidationError("candidate Plan checkpoint identity is invalid")
        return (
            self.experiments_root
            / f"round-{round_id:04d}"
            / "candidates"
            / f"slot-{candidate_index:02d}.json"
        )

    def append_event(
        self,
        event_type: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one diagnostic event; never use it as completion authority."""

        normalized_type = str(event_type).strip()
        if not normalized_type:
            raise ValidationError("evolution event type must not be empty")
        self._event_sequence += 1
        event = {
            **dict(details or {}),
            "schema_version": "evolution-trajectory-event-v1",
            "sequence": self._event_sequence,
            "at": datetime.now(timezone.utc).isoformat(),
            "event_type": normalized_type,
        }
        self.trajectory_events_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with self.trajectory_events_path.open("a+b") as handle:
            if handle.tell() > 0:
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    handle.write(b"\n")
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def load_events(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Load valid append-only debug events, optionally retaining the tail."""

        if limit is not None and limit < 1:
            raise ValidationError("evolution event limit must be positive")
        if not self.trajectory_events_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.trajectory_events_path.read_text(
            encoding="utf-8"
        ).splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(value, dict):
                continue
            events.append(value)
        return events[-limit:] if limit is not None else events

    def start_or_resume_cycle(
        self,
        *,
        run_contract_hash: str,
        target_plan_rounds: int,
        cycle_mode: str = "fast_then_slow",
        initial_signal_registry_version: int,
        initial_signal_registry_hash: str,
        observed_signal_registry_version: int,
        observed_signal_registry_hash: str,
    ) -> dict[str, Any]:
        """Freeze or recover one Fast/Slow cycle and its Registry boundary."""

        if cycle_mode not in {"fast_then_slow", "slow_bootstrap"}:
            raise ValidationError("cycle mode is invalid")
        if (
            not run_contract_hash
            or target_plan_rounds < 0
            or initial_signal_registry_version < 1
            or observed_signal_registry_version < 1
        ):
            raise ValidationError("cycle contract hash and round target are required")
        if (
            (cycle_mode == "fast_then_slow" and target_plan_rounds < 1)
            or (cycle_mode == "slow_bootstrap" and target_plan_rounds != 0)
        ):
            raise ValidationError("cycle mode and Fast-round target conflict")
        if self.cycle_state_path.exists():
            state = _read_json(self.cycle_state_path)
            if state.get("schema_version") != "dual-loop-cycle-state-v2":
                raise ValidationError("unsupported dual-loop cycle state schema")
            if state.get("run_contract_hash") != run_contract_hash:
                raise ValidationError("cycle state run contract mismatch")
            if (
                int(state.get("initial_signal_registry_version", 0))
                != initial_signal_registry_version
                or state.get("initial_signal_registry_hash")
                != initial_signal_registry_hash
            ):
                raise ValidationError("cycle state initial Signal Registry mismatch")
        else:
            state = {
                "schema_version": "dual-loop-cycle-state-v2",
                "run_contract_hash": run_contract_hash,
                "initial_signal_registry_version": initial_signal_registry_version,
                "initial_signal_registry_hash": initial_signal_registry_hash,
                "current_signal_registry_version": initial_signal_registry_version,
                "current_signal_registry_hash": initial_signal_registry_hash,
                "last_completed_cycle": 0,
                "active_cycle": None,
            }
        active = state.get("active_cycle")
        resumed = isinstance(active, Mapping)
        if not resumed:
            if (
                cycle_mode == "slow_bootstrap"
                and int(state.get("last_completed_cycle", 0)) != 0
            ):
                raise ValidationError("slow_bootstrap contract is single-cycle")
            if (
                int(state.get("current_signal_registry_version", 0))
                != observed_signal_registry_version
                or state.get("current_signal_registry_hash")
                != observed_signal_registry_hash
            ):
                raise ValidationError(
                    "stable Signal Registry differs from last committed cycle output"
                )
            active = {
                "cycle_id": int(state.get("last_completed_cycle", 0)) + 1,
                "start_round": self.last_completed_round,
                "target_plan_rounds": target_plan_rounds,
                "cycle_mode": cycle_mode,
                "completed_plan_rounds": 0,
                "phase": "fast_loop",
                "input_signal_registry_version": observed_signal_registry_version,
                "input_signal_registry_hash": observed_signal_registry_hash,
            }
        else:
            active = dict(active)
            if int(active.get("target_plan_rounds", 0)) != target_plan_rounds:
                raise ValidationError("active cycle round target mismatch")
            if active.get("cycle_mode", "fast_then_slow") != cycle_mode:
                raise ValidationError("active cycle mode mismatch")
            if (
                int(active.get("input_signal_registry_version", 0))
                != int(state.get("current_signal_registry_version", 0))
                or active.get("input_signal_registry_hash")
                != state.get("current_signal_registry_hash")
            ):
                raise ValidationError("active cycle Signal input is not committed state")
        start_round = int(active.get("start_round", -1))
        completed = self.last_completed_round - start_round
        if completed < 0 or completed > target_plan_rounds:
            raise ValidationError("committed round pointer conflicts with active cycle")
        active["completed_plan_rounds"] = completed
        active["phase"] = (
            "slow_loop" if completed == target_plan_rounds else "fast_loop"
        )
        state["active_cycle"] = active
        _atomic_write_json(self.cycle_state_path, state)
        return {**active, "resumed": resumed}

    def mark_cycle_phase(self, phase: str) -> None:
        if phase not in {"fast_loop", "slow_loop", "signal_transition"}:
            raise ValidationError("invalid dual-loop cycle phase")
        state = _read_json(self.cycle_state_path)
        active = state.get("active_cycle")
        if not isinstance(active, Mapping):
            raise ValidationError("no active dual-loop cycle")
        active = dict(active)
        active["completed_plan_rounds"] = (
            self.last_completed_round - int(active["start_round"])
        )
        active["phase"] = phase
        state["active_cycle"] = active
        _atomic_write_json(self.cycle_state_path, state)

    def staged_slow_validation(self, cycle_id: int) -> dict[str, Any] | None:
        path = self._slow_validation_path(cycle_id)
        if not path.exists():
            return None
        payload = _read_json(path)
        cycle_state = _read_json(self.cycle_state_path)
        if (
            payload.get("schema_version") != "dual-loop-slow-validation-v1"
            or int(payload.get("cycle_id", 0)) != cycle_id
            or payload.get("run_contract_hash")
            != cycle_state.get("run_contract_hash")
        ):
            raise ValidationError("staged Slow-loop validation identity mismatch")
        active = cycle_state.get("active_cycle")
        validation = dict(payload.get("validation", {}))
        if not isinstance(active, Mapping) or (
            int(validation.get("input_registry_version", 0))
            != int(active.get("input_signal_registry_version", 0))
            or validation.get("input_registry_hash")
            != active.get("input_signal_registry_hash")
        ):
            raise ValidationError("staged Slow validation Registry input mismatch")
        return validation

    def stage_slow_validation(
        self,
        *,
        cycle_id: int,
        validation: Mapping[str, Any],
    ) -> Path:
        path = self._slow_validation_path(cycle_id)
        cycle_state = _read_json(self.cycle_state_path)
        active = cycle_state.get("active_cycle")
        if not isinstance(active, Mapping) or int(active.get("cycle_id", 0)) != cycle_id:
            raise ValidationError("active dual-loop cycle identity mismatch")
        if self.last_completed_round != (
            int(active.get("start_round", -1))
            + int(active.get("target_plan_rounds", 0))
        ):
            raise ValidationError("cannot stage Slow validation before all Fast rounds")
        if (
            int(validation.get("input_registry_version", 0))
            != int(active.get("input_signal_registry_version", 0))
            or validation.get("input_registry_hash")
            != active.get("input_signal_registry_hash")
        ):
            raise ValidationError("Slow validation differs from cycle Registry input")
        _write_or_verify_json(
            path,
            {
                "schema_version": "dual-loop-slow-validation-v1",
                "cycle_id": cycle_id,
                "run_contract_hash": cycle_state.get("run_contract_hash"),
                "validation": dict(validation),
            },
        )
        self.mark_cycle_phase("signal_transition")
        return path

    def staged_slow_result(self, cycle_id: int) -> dict[str, Any] | None:
        path = self._slow_result_path(cycle_id)
        if not path.exists():
            return None
        payload = _read_json(path)
        cycle_state = _read_json(self.cycle_state_path)
        if (
            payload.get("schema_version") != "dual-loop-slow-result-v2"
            or int(payload.get("cycle_id", 0)) != cycle_id
            or payload.get("run_contract_hash")
            != cycle_state.get("run_contract_hash")
        ):
            raise ValidationError("staged Slow-loop result identity mismatch")
        return dict(payload.get("result", {}))

    def stage_slow_result(
        self,
        *,
        cycle_id: int,
        result: Mapping[str, Any],
    ) -> Path:
        path = self._slow_result_path(cycle_id)
        cycle_state = _read_json(self.cycle_state_path)
        active = cycle_state.get("active_cycle")
        if not isinstance(active, Mapping) or int(active.get("cycle_id", 0)) != cycle_id:
            raise ValidationError("active dual-loop cycle identity mismatch")
        if (
            int(result.get("input_registry_version", 0))
            != int(active.get("input_signal_registry_version", 0))
            or result.get("input_registry_hash")
            != active.get("input_signal_registry_hash")
        ):
            raise ValidationError("Slow result differs from cycle Registry input")
        _write_or_verify_json(
            path,
            {
                "schema_version": "dual-loop-slow-result-v2",
                "cycle_id": cycle_id,
                "run_contract_hash": cycle_state.get("run_contract_hash"),
                "result": dict(result),
            },
        )
        return path

    def complete_cycle(
        self,
        *,
        cycle_id: int,
        observed_signal_registry_version: int,
        observed_signal_registry_hash: str,
    ) -> None:
        """Advance the cycle pointer only after Fast rounds and Slow result exist."""

        state = _read_json(self.cycle_state_path)
        active = state.get("active_cycle")
        if not isinstance(active, Mapping) or int(active.get("cycle_id", 0)) != cycle_id:
            raise ValidationError("active dual-loop cycle identity mismatch")
        target = int(active["target_plan_rounds"])
        expected_round = int(active["start_round"]) + target
        if self.last_completed_round != expected_round:
            raise ValidationError("cannot complete cycle before all Fast rounds")
        slow_path = self._slow_result_path(cycle_id)
        if not slow_path.exists():
            raise ValidationError("cannot complete cycle without staged Slow result")
        slow_result = self.staged_slow_result(cycle_id)
        if slow_result is None:
            raise ValidationError("cannot complete cycle without staged Slow result")
        if (
            int(slow_result.get("output_registry_version", 0))
            != observed_signal_registry_version
            or slow_result.get("output_registry_hash")
            != observed_signal_registry_hash
        ):
            raise ValidationError("stable Registry differs from staged Slow output")
        state.update(
            {
                "last_completed_cycle": cycle_id,
                "last_completed_round": self.last_completed_round,
                "last_cycle_ref": str(slow_path),
                "current_signal_registry_version": observed_signal_registry_version,
                "current_signal_registry_hash": observed_signal_registry_hash,
                "active_cycle": None,
            }
        )
        _atomic_write_json(self.cycle_state_path, state)

    def _slow_validation_path(self, cycle_id: int) -> Path:
        if cycle_id < 1:
            raise ValidationError("cycle id must be positive")
        return (
            self.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_validation.json"
        )

    def _slow_result_path(self, cycle_id: int) -> Path:
        if cycle_id < 1:
            raise ValidationError("cycle id must be positive")
        return (
            self.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_result.json"
        )

    def commit_round(
        self,
        *,
        round_id: int,
        records: tuple[PlanRecord, ...],
        meta_entry: RoundMetaEntry,
        signal_registry_version: int,
        signal_registry_hash: str,
        signal_learning_hash: str = "",
        run_contract_hash: str = "",
    ) -> None:
        """Write or verify exact staged artifacts, then advance one pointer last."""

        expected = self.last_completed_round + 1
        if round_id != expected:
            raise ValidationError(
                f"round commit must advance from {expected - 1} to {expected}"
            )
        if not records or any(record.round_id != round_id for record in records):
            raise ValidationError("round commit requires records from the same round")
        if signal_registry_version < 1:
            raise ValidationError("round Signal Registry version must be positive")
        if meta_entry.round_id != round_id:
            raise ValidationError("round meta entry does not match committed round")
        plan_ids = [record.plan_id for record in records]
        if len(set(plan_ids)) != len(plan_ids):
            raise ValidationError("round cannot commit duplicate plan ids")

        for record in records:
            path = self.plans_root / record.plan_id / "record.json"
            _write_or_verify_json(path, record.to_dict())
        _write_or_verify_json(
            self.meta_root / f"round-{round_id:04d}.json",
            meta_entry.to_dict(),
        )
        checkpoint_path = (
            self.experiments_root / f"round-{round_id:04d}" / "checkpoint.json"
        )
        _write_or_verify_json(
            checkpoint_path,
            {
                "round_id": round_id,
                "plan_ids": plan_ids,
                "meta_ref": str(
                    self.meta_root / f"round-{round_id:04d}.json"
                ),
                "signal_registry_version": signal_registry_version,
                "signal_registry_hash": signal_registry_hash,
                "signal_learning_hash": signal_learning_hash,
                "run_contract_hash": run_contract_hash,
            },
        )
        _atomic_write_json(
            self.state_path,
            {
                "last_completed_round": round_id,
                "checkpoint_ref": str(checkpoint_path),
            },
        )

    def stage_evaluation_attempt(
        self,
        *,
        round_id: int,
        attempt: PlanEvaluationAttempt,
        available_source_types: Iterable[str] = (),
    ) -> Path:
        """Persist one candidate attempt whether or not it is fitness-eligible."""

        if round_id < 1:
            raise ValidationError("evaluation attempt round must be positive")
        path = (
            self.experiments_root
            / f"round-{round_id:04d}"
            / "attempts"
            / f"{attempt.plan.plan_id}.json"
        )
        _write_or_verify_json(path, attempt.to_dict())
        self.refresh_capability_backlog(
            available_source_types=available_source_types
        )
        return path

    def refresh_capability_backlog(
        self, *, available_source_types: Iterable[str] = ()
    ) -> Path:
        """Rebuild the derived capability backlog from durable attempts."""

        trajectories: list[Mapping[str, Any]] = []
        for path in sorted(
            self.experiments_root.glob("round-*/attempts/*.json")
        ):
            attempt = _read_json(path)
            trajectories.extend(
                item
                for item in attempt.get("trajectories", ())
                if isinstance(item, Mapping)
            )
        bootstrap_manifest_path = self.root / "slow_bootstrap" / "manifest.json"
        signal_need_items: Iterable[Mapping[str, Any]] = ()
        committed_fast_backlog: Mapping[str, Any] | None = None
        if bootstrap_manifest_path.exists():
            envelope = _read_json(bootstrap_manifest_path)
            manifest = envelope.get("manifest", {})
            if isinstance(manifest, Mapping):
                backlog_seed = manifest.get("capability_backlog_seed", {})
                if isinstance(backlog_seed, Mapping):
                    if manifest.get("source_kind") == "committed_fast":
                        committed_fast_backlog = dict(backlog_seed)
                    else:
                        raw_items = backlog_seed.get("signal_need_items", ())
                        if isinstance(raw_items, list):
                            signal_need_items = tuple(
                                item
                                for item in raw_items
                                if isinstance(item, Mapping)
                            )
        report = (
            dict(committed_fast_backlog)
            if committed_fast_backlog is not None and not trajectories
            else aggregate_capability_gaps(
                trajectories,
                available_source_types=available_source_types,
                signal_need_items=signal_need_items,
            )
        )
        _atomic_write_json(
            self.experiments_root / "capability_gap_report.json",
            report,
        )
        path = self.root / "capability_backlog.json"
        _atomic_write_json(path, report)
        return path

    def reject_round(
        self,
        *,
        round_id: int,
        reason: str,
        attempts: Iterable[PlanEvaluationAttempt],
    ) -> Path:
        """Persist one immutable pause checkpoint without advancing state."""

        if round_id != self.last_completed_round + 1:
            raise ValidationError("round rejection does not follow committed state")
        path = self.experiments_root / f"round-{round_id:04d}" / "rejected.json"
        payload = {
            "schema_version": "plan-round-rejected-v1",
            "round_id": round_id,
            "reason": str(reason),
            "attempts": [attempt.to_dict() for attempt in attempts],
            "last_completed_round": self.last_completed_round,
        }
        _write_or_verify_json(path, payload)
        return path

    def stage_shared_data_pause(
        self,
        *,
        round_id: int,
        case_reasons: Mapping[str, str],
        retryable: bool,
    ) -> Path:
        """Persist a replaceable diagnostic without committing or rejecting."""

        if round_id != self.last_completed_round + 1:
            raise ValidationError("shared-data pause does not follow committed state")
        path = (
            self.experiments_root
            / f"round-{round_id:04d}"
            / "shared-data-pause.json"
        )
        _atomic_write_json(
            path,
            {
                "schema_version": "plan-round-shared-data-pause-v1",
                "round_id": round_id,
                "case_reasons": {
                    str(case_id): str(reason)
                    for case_id, reason in case_reasons.items()
                },
                "retryable": bool(retryable),
                "last_completed_round": self.last_completed_round,
            },
        )
        return path

    def load_round_rejection(self, round_id: int) -> dict[str, Any] | None:
        path = self.experiments_root / f"round-{round_id:04d}" / "rejected.json"
        return _read_json(path) if path.exists() else None

    def restore_archive(self, *, expected_run_contract_hash: str | None = None) -> PlanArchive:
        """Load only Plans reachable from authoritative completed checkpoints."""

        state = _read_json(self.state_path)
        last_completed_round = int(state.get("last_completed_round", 0))
        if last_completed_round < 0:
            raise ValidationError("completed round pointer cannot be negative")
        if last_completed_round:
            expected_last_checkpoint = (
                self.experiments_root
                / f"round-{last_completed_round:04d}"
                / "checkpoint.json"
            )
            if not _same_artifact_path(
                state.get("checkpoint_ref"), expected_last_checkpoint
            ):
                raise ValidationError(
                    "state pointer checkpoint_ref differs from its completed round"
                )
        records: list[PlanRecord] = []
        for round_id in range(1, last_completed_round + 1):
            checkpoint = _read_json(
                self.experiments_root
                / f"round-{round_id:04d}"
                / "checkpoint.json"
            )
            if int(checkpoint["round_id"]) != round_id:
                raise ValidationError("round checkpoint identity mismatch")
            if (
                expected_run_contract_hash is not None
                and checkpoint.get("run_contract_hash") != expected_run_contract_hash
            ):
                raise ValidationError("round checkpoint run contract mismatch")
            plan_ids = checkpoint.get("plan_ids")
            if (
                not isinstance(plan_ids, list)
                or not plan_ids
                or any(not isinstance(item, str) or not item for item in plan_ids)
                or len(set(plan_ids)) != len(plan_ids)
            ):
                raise ValidationError("round checkpoint Plan ids are invalid")
            expected_meta_ref = self.meta_root / f"round-{round_id:04d}.json"
            if not _same_artifact_path(checkpoint.get("meta_ref"), expected_meta_ref):
                raise ValidationError("round checkpoint meta reference mismatch")
            for plan_id in plan_ids:
                record = PlanRecord.from_dict(
                    _read_json(self.plans_root / plan_id / "record.json")
                )
                if record.plan_id != plan_id or record.round_id != round_id:
                    raise ValidationError(
                        "round checkpoint cross-links a different Plan record"
                    )
                records.append(record)
        return PlanArchive(records)

    def restore_meta(self, *, maxlen: int = 10) -> PlanMetaMemory:
        entries = [
            RoundMetaEntry.from_dict(
                _read_json(self.meta_root / f"round-{round_id:04d}.json")
            )
            for round_id in range(1, self.last_completed_round + 1)
        ]
        return PlanMetaMemory(maxlen=maxlen, entries=entries)

    def load_experiment_records(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return committed summaries for the Signal Update Agent."""

        if limit < 1:
            raise ValidationError("experiment record limit must be positive")
        records = self.restore_archive().records[-limit:]
        return [
            {
                "plan_id": record.plan_id,
                "round_id": record.round_id,
                "metrics": record.metrics.to_dict(),
                "reflection": record.reflection.to_dict(),
                "signal_usage": {
                    ref: dict(counts) for ref, counts in record.signal_usage.items()
                },
            }
            for record in records
        ]


@dataclass(frozen=True)
class PlanRoundResult:
    """One fully committed fast-loop round."""

    round_id: int
    parents: tuple[InformationPlan, ...]
    records: tuple[PlanRecord, ...]
    meta_entry: RoundMetaEntry


@dataclass(frozen=True)
class CaseEvaluationFailure:
    """Durable reason one case could not cross the prediction boundary."""

    case_id: str
    stage: str
    error_type: str
    message: str
    artifact_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "stage": self.stage,
            "error_type": self.error_type,
            "message": self.message,
            "artifact_ref": self.artifact_ref,
        }


@dataclass(frozen=True)
class PlanEvaluationAttempt:
    """Complete or stopped candidate evaluation before archive admission."""

    plan: InformationPlan
    expected_case_ids: tuple[str, ...]
    trajectories: tuple[ExecutionTrajectory, ...]
    failures: tuple[CaseEvaluationFailure, ...] = ()

    @property
    def metrics(self) -> PlanMetrics | None:
        if self.failures or len(self.trajectories) != len(self.expected_case_ids):
            return None
        return score_predictions(self.trajectories)

    @property
    def fitness(self) -> FitnessEligibility:
        return assess_fitness_eligibility(
            self.trajectories,
            expected_case_ids=self.expected_case_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        metrics = self.metrics
        return {
            "schema_version": "plan-evaluation-attempt-v1",
            "plan_id": self.plan.plan_id,
            "expected_case_ids": list(self.expected_case_ids),
            "completed_case_ids": [item.case_id for item in self.trajectories],
            "trajectories": [item.to_dict() for item in self.trajectories],
            "failures": [item.to_dict() for item in self.failures],
            "metrics": metrics.to_dict() if metrics is not None else None,
            "fitness": self.fitness.to_dict(),
        }


@dataclass(frozen=True)
class PlanEvaluationResult:
    """In-round predictions and metrics before durable PlanRecord creation."""

    plan: InformationPlan
    trajectories: tuple[ExecutionTrajectory, ...]
    metrics: PlanMetrics
    metrics_by_cohort: Mapping[str, PlanMetrics]
    fitness: FitnessEligibility


class PlanEvolutionEngine:
    """Bounded Information Plan Fast Loop under a frozen Signal Registry."""

    def __init__(
        self,
        *,
        archive: PlanArchive,
        meta_memory: PlanMetaMemory,
        signal_registry: SignalRegistry,
        evaluator: PlanEvaluator,
        proposer: InformationPlanProposer,
        critic: PlanCritic,
        round_reflector: RoundReflector,
        workspace: EvolutionWorkspace,
        seed_plans: tuple[InformationPlan, ...],
        warm_start_plans: tuple[InformationPlan, ...] = (),
        warm_start_parent_evidence: tuple[
            ParentPlanReflectionEvidence, ...
        ] = (),
        priors: EvolutionPriors = DEFAULT_EVOLUTION_PRIORS,
        embedder: PlanEmbedder | None = None,
        candidates_per_round: int = 3,
        top_k: int = 3,
        random_k: int = 2,
        similarity_threshold: float = 0.9,
        rng: random.Random | None = None,
        parent_selection_seed: int | None = None,
        capability_source_types: Iterable[str] = (),
        evaluation_config: PlanEvaluationConfig = PlanEvaluationConfig(),
        case_readiness: Callable[[EvolutionCase], EvaluationCaseReadiness]
        | None = None,
        run_contract_hash: str = "",
        on_progress: ProgressCallback | None = None,
    ) -> None:
        if candidates_per_round < 1:
            raise ValidationError("candidates_per_round must be positive")
        if not seed_plans:
            raise ValidationError("plan evolution requires at least one seed Plan")
        self.archive = archive
        self.meta_memory = meta_memory
        self.signal_registry = signal_registry
        self.evaluator = evaluator
        self.proposer = proposer
        self.critic = critic
        self.round_reflector = round_reflector
        self.workspace = workspace
        self.seed_plans = tuple(seed_plans)
        self.warm_start_plans = tuple(warm_start_plans)
        self.warm_start_parent_evidence = {
            item.plan.plan_id: item for item in warm_start_parent_evidence
        }
        parent_seed_ids = [
            plan.plan_id for plan in (*self.seed_plans, *self.warm_start_plans)
        ]
        if len(parent_seed_ids) != len(set(parent_seed_ids)):
            raise ValidationError("plan evolution seed ids must be unique")
        if len(self.warm_start_parent_evidence) != len(
            tuple(warm_start_parent_evidence)
        ) or set(self.warm_start_parent_evidence) - {
            plan.plan_id for plan in self.warm_start_plans
        }:
            raise ValidationError("warm-start reflection evidence is inconsistent")
        warm_plans_by_id = {
            plan.plan_id: plan for plan in self.warm_start_plans
        }
        if any(
            evidence.plan != warm_plans_by_id[plan_id]
            for plan_id, evidence in self.warm_start_parent_evidence.items()
        ):
            raise ValidationError("warm-start reflection Plan content differs")
        self.priors = priors
        self.embedder = embedder or HashingPlanEmbedder()
        self.candidates_per_round = candidates_per_round
        self.top_k = top_k
        self.random_k = random_k
        self.similarity_threshold = similarity_threshold
        self.rng = rng or random.Random()
        self.parent_selection_seed = parent_selection_seed
        self.capability_source_types = tuple(capability_source_types)
        self.evaluation_config = evaluation_config
        self.case_readiness = case_readiness
        self.run_contract_hash = run_contract_hash
        self.on_progress = on_progress
        for committed_record in self.archive.records:
            self._record_signal_statistics(committed_record)

    def run_round(
        self,
        *,
        round_id: int,
        validation_cases: tuple[EvolutionCase, ...],
        anchor_cases: tuple[EvolutionCase, ...],
        signal_snapshot: FrozenSignalRegistry,
    ) -> PlanRoundResult:
        """Sample N independent Plans, evaluate, critique, archive, and reflect."""

        if round_id != self.workspace.last_completed_round + 1:
            raise ValidationError("fast-loop round id does not follow committed state")
        rejected = self.workspace.load_round_rejection(round_id)
        if rejected is not None:
            checkpoint = (
                self.workspace.experiments_root
                / f"round-{round_id:04d}"
                / "rejected.json"
            )
            raise RoundPaused(round_id, str(rejected["reason"]), str(checkpoint))
        dataset_manager = EvaluationDatasetManager(
            self.workspace.evaluation_root,
            validation_cases,
            anchor_cases,
            self.evaluation_config,
            case_readiness=self.case_readiness,
        )
        try:
            round_snapshot = dataset_manager.get_or_create_round_dataset(round_id)
        except SharedEvaluationDataUnavailable as unavailable:
            checkpoint = self.workspace.stage_shared_data_pause(
                round_id=round_id,
                case_reasons=unavailable.case_reasons,
                retryable=unavailable.retryable,
            )
            _emit_progress(
                self.on_progress,
                "shared_evaluation_data_unavailable",
                round_id=round_id,
                case_reasons=dict(unavailable.case_reasons),
                retryable=unavailable.retryable,
                checkpoint_ref=str(checkpoint),
            )
            raise SharedEvaluationDataUnavailable(
                round_id,
                unavailable.case_reasons,
                retryable=unavailable.retryable,
                checkpoint_ref=str(checkpoint),
            ) from unavailable
        round_cases = dataset_manager.resolve_cases(round_snapshot.case_ids)
        round_aliases = _case_identity_alias_inventory(round_cases)
        for role in (self.proposer, self.critic, self.round_reflector):
            setter = getattr(role, "set_anonymous_aliases", None)
            if callable(setter):
                setter(round_aliases)
        _emit_progress(
            self.on_progress,
            "round_started",
            round_id=round_id,
            candidate_count=self.candidates_per_round,
            validation_case_count=len(validation_cases),
            evaluation_case_count=len(round_cases),
            evaluation_snapshot_id=round_snapshot.snapshot_id,
        )
        selection = self.archive.select_parents(
            top_k=self.top_k,
            random_k=self.random_k,
            similarity_threshold=self.similarity_threshold,
            rng=(
                random.Random(f"{self.parent_selection_seed}:{round_id}")
                if self.parent_selection_seed is not None
                else self.rng
            ),
        )
        quality_parents = [record.plan for record in selection.top]
        quality_embeddings = [record.embedding for record in selection.top]
        parent_evidence_by_id = {
            record.plan_id: ParentPlanReflectionEvidence(
                plan=record.plan,
                source_scope="current_archive",
                evaluation_snapshot_ids=record.evaluation.dataset_snapshot_ids,
                metrics_by_cohort=record.evaluation.metrics_by_cohort,
            )
            for record in selection.records
        }
        selected_warm_start_plans: list[InformationPlan] = []
        for plan in self.warm_start_plans:
            if len(quality_parents) >= self.top_k:
                break
            embedding = self.embedder.embed(plan)
            if all(
                cosine_similarity(embedding, kept) < self.similarity_threshold
                for kept in quality_embeddings
            ):
                quality_parents.append(plan)
                quality_embeddings.append(embedding)
                selected_warm_start_plans.append(plan)
                parent_evidence_by_id[plan.plan_id] = (
                    self.warm_start_parent_evidence.get(plan.plan_id)
                    or ParentPlanReflectionEvidence(
                        plan=plan,
                        source_scope="historical_seed",
                    )
                )
        if not quality_parents:
            quality_parents.extend(self.seed_plans)
            parent_evidence_by_id.update(
                {
                    plan.plan_id: ParentPlanReflectionEvidence(
                        plan=plan,
                        source_scope="manual_seed",
                    )
                    for plan in self.seed_plans
                }
            )
        parents = tuple(quality_parents) + tuple(
            record.plan for record in selection.random
        )
        selected_parent_ids = tuple(plan.plan_id for plan in parents)
        _emit_progress(
            self.on_progress,
            "parents_selected",
            round_id=round_id,
            top_parent_ids=[record.plan_id for record in selection.top],
            random_parent_ids=[record.plan_id for record in selection.random],
            seed_parent_ids=[plan.plan_id for plan in selected_warm_start_plans]
            or (
                [plan.plan_id for plan in self.seed_plans]
                if not selection.top
                else []
            ),
        )
        allowed_parent_ids = {plan.plan_id for plan in parents}
        candidate_plans: list[InformationPlan] = []
        forbidden_content_hashes = {
            _canonical_hash(record.plan.canonical_dict())
            for record in self.archive.records
        } | {_canonical_hash(plan.canonical_dict()) for plan in parents}
        for candidate_index in range(1, self.candidates_per_round + 1):
            accepted: InformationPlan | None = None
            accepted_proposal_attempt: int | None = None
            staged_candidate = self.workspace.staged_candidate_plan(
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=self.candidates_per_round,
                selected_parent_ids=selected_parent_ids,
                run_contract_hash=self.run_contract_hash,
            )
            if staged_candidate is not None:
                accepted, accepted_proposal_attempt = staged_candidate
                content_hash = _canonical_hash(accepted.canonical_dict())
                if content_hash in forbidden_content_hashes:
                    raise ValidationError(
                        "staged candidate Plan duplicates prior or sibling content"
                    )
                forbidden_content_hashes.add(content_hash)
                _emit_progress(
                    self.on_progress,
                    "candidate_proposal_reused",
                    round_id=round_id,
                    candidate_index=candidate_index,
                    candidate_count=self.candidates_per_round,
                    proposal_attempt=accepted_proposal_attempt,
                    plan_id=accepted.plan_id,
                )
            else:
                for proposal_attempt in range(
                    1, self.evaluation_config.max_proposal_attempts_per_slot + 1
                ):
                    _emit_progress(
                        self.on_progress,
                        "candidate_proposal_started",
                        round_id=round_id,
                        candidate_index=candidate_index,
                        candidate_count=self.candidates_per_round,
                        proposal_attempt=proposal_attempt,
                    )
                    try:
                        candidate = self.proposer.propose(
                            round_id=round_id,
                            candidate_index=candidate_index,
                            candidate_count=self.candidates_per_round,
                            proposal_attempt=proposal_attempt,
                            forbidden_plan_ids=tuple(
                                sorted(
                                    {
                                        *(
                                            record.plan_id
                                            for record in self.archive.records
                                        ),
                                        *(plan.plan_id for plan in candidate_plans),
                                    }
                                )
                            ),
                            parents=parents,
                            meta_info=self.meta_memory.entries,
                            prior=self.priors.propose_plan,
                        )
                        if (
                            not candidate.parent_ids
                            or set(candidate.parent_ids) != allowed_parent_ids
                        ):
                            raise CandidateProposalRejected(
                                "runtime lineage differs from selected parents"
                            )
                        content_hash = _canonical_hash(candidate.canonical_dict())
                        if content_hash in forbidden_content_hashes:
                            raise CandidateProposalRejected(
                                "candidate Plan content duplicates an existing Plan"
                            )
                    except CandidateProposalRejected as exc:
                        _emit_progress(
                            self.on_progress,
                            "candidate_proposal_rejected",
                            round_id=round_id,
                            candidate_index=candidate_index,
                            candidate_count=self.candidates_per_round,
                            proposal_attempt=proposal_attempt,
                            reason=str(exc),
                        )
                        continue
                    accepted = candidate
                    accepted_proposal_attempt = proposal_attempt
                    forbidden_content_hashes.add(content_hash)
                    self.workspace.stage_candidate_plan(
                        round_id=round_id,
                        candidate_index=candidate_index,
                        candidate_count=self.candidates_per_round,
                        selected_parent_ids=selected_parent_ids,
                        proposal_attempt=proposal_attempt,
                        run_contract_hash=self.run_contract_hash,
                        plan=accepted,
                    )
                    break
            if accepted is None:
                continue
            candidate_plans.append(accepted)
            _emit_progress(
                self.on_progress,
                "candidate_proposed",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=self.candidates_per_round,
                plan_id=accepted.plan_id,
                parent_ids=list(accepted.parent_ids),
                plan_summary=summarize_information_plan(accepted),
            )

        if not candidate_plans:
            checkpoint = self.workspace.reject_round(
                round_id=round_id,
                reason="all_candidate_proposals_rejected",
                attempts=(),
            )
            raise RoundPaused(
                round_id,
                "all_candidate_proposals_rejected",
                str(checkpoint),
            )

        attempts: list[PlanEvaluationAttempt] = []
        evaluation_results: list[PlanEvaluationResult] = []
        for candidate_index, plan in enumerate(candidate_plans, start=1):
            _emit_progress(
                self.on_progress,
                "candidate_evaluation_started",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=len(candidate_plans),
                plan_id=plan.plan_id,
            )
            raw_attempt = self.evaluator.evaluate(
                plan,
                round_cases,
                signal_snapshot,
            )
            attempt = (
                raw_attempt
                if isinstance(raw_attempt, PlanEvaluationAttempt)
                else PlanEvaluationAttempt(
                    plan=plan,
                    expected_case_ids=round_snapshot.case_ids,
                    trajectories=tuple(raw_attempt),
                )
            )
            attempts.append(attempt)
            attempt_path = self.workspace.stage_evaluation_attempt(
                round_id=round_id,
                attempt=attempt,
                available_source_types=self.capability_source_types,
            )
            metrics = attempt.metrics
            fitness = attempt.fitness
            if metrics is None:
                _emit_progress(
                    self.on_progress,
                    "candidate_evaluation_rejected",
                    round_id=round_id,
                    candidate_index=candidate_index,
                    plan_id=plan.plan_id,
                    reasons=list(fitness.reasons),
                    attempt_ref=str(attempt_path),
                )
                continue
            trajectories_by_id = {
                trajectory.case_id: trajectory for trajectory in attempt.trajectories
            }
            if set(trajectories_by_id) != set(round_snapshot.case_ids):
                _emit_progress(
                    self.on_progress,
                    "candidate_evaluation_rejected",
                    round_id=round_id,
                    candidate_index=candidate_index,
                    plan_id=plan.plan_id,
                    reasons=list(fitness.reasons),
                    attempt_ref=str(attempt_path),
                )
                continue
            anchor_trajectories = tuple(
                trajectories_by_id[case_id]
                for case_id in round_snapshot.anchor_case_ids
            )
            random_trajectories = tuple(
                trajectories_by_id[case_id]
                for case_id in round_snapshot.random_case_ids
            )
            metrics_by_cohort = {
                "anchor": score_predictions(anchor_trajectories),
                "random": score_predictions(random_trajectories),
                "combined": metrics,
            }
            _emit_progress(
                self.on_progress,
                "candidate_scored" if fitness.eligible else "candidate_diagnostic_only",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=len(candidate_plans),
                plan_id=plan.plan_id,
                metrics=metrics.to_dict(),
                metrics_by_cohort={
                    cohort: cohort_metrics.to_dict()
                    for cohort, cohort_metrics in metrics_by_cohort.items()
                },
                fitness=fitness.to_dict(),
                trajectory_count=len(attempt.trajectories),
                evaluation_stage="round",
                case_ids=list(round_snapshot.case_ids),
                attempt_ref=str(attempt_path),
            )
            evaluation_results.append(
                PlanEvaluationResult(
                    plan=plan,
                    trajectories=attempt.trajectories,
                    metrics=metrics,
                    metrics_by_cohort=metrics_by_cohort,
                    fitness=fitness,
                )
            )

        shared_missing_case_ids = _shared_missing_source_case_ids(attempts)
        if shared_missing_case_ids:
            case_reasons = {
                case_id: "missing_source_evidence_after_readiness"
                for case_id in shared_missing_case_ids
            }
            checkpoint = self.workspace.stage_shared_data_pause(
                round_id=round_id,
                case_reasons=case_reasons,
                retryable=False,
            )
            _emit_progress(
                self.on_progress,
                "shared_evaluation_data_unavailable",
                round_id=round_id,
                case_reasons=case_reasons,
                retryable=False,
                checkpoint_ref=str(checkpoint),
            )
            raise SharedEvaluationDataUnavailable(
                round_id,
                case_reasons,
                retryable=False,
                checkpoint_ref=str(checkpoint),
            )

        records: list[PlanRecord] = []
        parent_comparisons_by_plan_id: dict[
            str, tuple[Mapping[str, Any], ...]
        ] = {}
        for result in evaluation_results:
            trajectories = result.trajectories
            metrics = result.metrics
            try:
                comparisons = tuple(
                    build_parent_plan_comparison(
                        parent=parent_evidence_by_id[parent_id],
                        child_plan=result.plan,
                        child_metrics=metrics,
                        child_snapshot_id=round_snapshot.snapshot_id,
                    )
                    for parent_id in result.plan.parent_ids
                )
            except KeyError as exc:
                raise ValidationError(
                    "candidate parent reflection evidence is missing"
                ) from exc
            parent_comparisons_by_plan_id[result.plan.plan_id] = comparisons
            reflection = self.critic.critique(
                plan=result.plan,
                trajectories=trajectories,
                metrics=metrics,
                parent_comparisons=comparisons,
            )
            records.append(
                PlanRecord(
                    plan=result.plan,
                    round_id=round_id,
                    embedding=self.embedder.embed(result.plan),
                    metrics=metrics,
                    reflection=reflection,
                    signal_usage=collect_signal_usage(trajectories),
                    trajectories=trajectories,
                    evaluation=PlanEvaluationSummary(
                        evaluation_stage="round",
                        n_cases=len(trajectories),
                        case_ids=round_snapshot.case_ids,
                        dataset_snapshot_ids=(round_snapshot.snapshot_id,),
                        metrics_by_cohort=result.metrics_by_cohort,
                    ),
                    fitness=result.fitness,
                )
            )

        record_tuple = tuple(records)
        if not any(record.fitness.eligible for record in record_tuple):
            checkpoint = self.workspace.reject_round(
                round_id=round_id,
                reason="no_fitness_eligible_candidates",
                attempts=attempts,
            )
            _emit_progress(
                self.on_progress,
                "round_rejected",
                round_id=round_id,
                reason="no_fitness_eligible_candidates",
                checkpoint_ref=str(checkpoint),
            )
            raise RoundPaused(
                round_id,
                "no_fitness_eligible_candidates",
                str(checkpoint),
            )
        horizontal_meta_entry = self.round_reflector.reflect(
            round_id=round_id,
            records=record_tuple,
            prior=self.priors.reflect_round,
            parent_comparisons_by_plan_id=parent_comparisons_by_plan_id,
        )
        if horizontal_meta_entry.round_id != round_id:
            raise ValidationError("round reflector returned a different round id")
        meta_entry = horizontal_meta_entry.append_plan_reflections(
            PlanMetaReflection.from_record(
                record,
                parent_comparisons=parent_comparisons_by_plan_id[record.plan_id],
            )
            for record in record_tuple
        )
        expected_refs = {record.plan_id for record in record_tuple}
        if tuple(
            item.plan_id for item in meta_entry.plan_reflections
        ) != tuple(record.plan_id for record in record_tuple):
            raise ValidationError(
                "round meta entry must retain every new Plan reflection in order"
            )
        if not set(meta_entry.evidence_refs).issubset(expected_refs):
            raise ValidationError("round meta entry cites evidence outside new experiments")
        _emit_progress(
            self.on_progress,
            "round_commit_started",
            round_id=round_id,
            plan_ids=[record.plan_id for record in record_tuple],
        )
        self.workspace.commit_round(
            round_id=round_id,
            records=record_tuple,
            meta_entry=meta_entry,
            signal_registry_version=signal_snapshot.version,
            signal_registry_hash=signal_snapshot.registry_hash,
            signal_learning_hash=signal_snapshot.learning_hash,
            run_contract_hash=self.run_contract_hash,
        )
        for record in record_tuple:
            self.archive.add(record)
            self._record_signal_statistics(record)
        self.meta_memory.append(meta_entry)
        current_top = self.archive.select_parents(
            top_k=self.top_k,
            random_k=0,
            similarity_threshold=self.similarity_threshold,
            rng=self.rng,
        ).top
        _emit_progress(
            self.on_progress,
            "round_committed",
            round_id=round_id,
            plan_ids=[record.plan_id for record in record_tuple],
            candidate_scores=[
                {
                    "plan_id": record.plan_id,
                    "binary_f1": record.metrics.binary_f1,
                    "binary_precision": record.metrics.binary_precision,
                    "binary_recall": record.metrics.binary_recall,
                }
                for record in record_tuple
            ],
            top_k=[
                {
                    "plan_id": record.plan_id,
                    "binary_f1": record.metrics.binary_f1,
                }
                for record in current_top
            ],
            checkpoint_ref=str(
                self.workspace.experiments_root
                / f"round-{round_id:04d}"
                / "checkpoint.json"
            ),
        )
        return PlanRoundResult(
            round_id=round_id,
            parents=parents,
            records=record_tuple,
            meta_entry=meta_entry,
        )

    def _record_signal_statistics(self, record: PlanRecord) -> None:
        for trajectory in record.trajectories:
            for round_index, signal_round in enumerate(trajectory.signal_rounds):
                for result_index, result in enumerate(signal_round.batch.results):
                    observation_id = ":".join(
                        (
                            record.plan_id,
                            trajectory.case_id,
                            str(round_index),
                            str(result_index),
                            result.ref,
                        )
                    )
                    self.signal_registry.record_observation(
                        observation_id,
                        result,
                        is_surge=trajectory.ground_truth.is_surge,
                    )
        self.signal_registry.record_learning_events(
            _signal_learning_events_from_record(record)
        )


def _signal_learning_events_from_record(
    record: PlanRecord,
) -> tuple[SignalLearningEvent, ...]:
    """Derive stable learning events from one authoritative Plan record."""

    learning_events: list[SignalLearningEvent] = []
    for trajectory in record.trajectories:
        for round_index, signal_round in enumerate(trajectory.signal_rounds):
            for result_index, result in enumerate(signal_round.batch.results):
                selection = next(
                    item
                    for item in signal_round.selections
                    if item.signal_ref == result.ref
                )
                fingerprint = tuple(
                    signal_round.batch.document_fingerprints.get(result.ref, ())
                )
                observation_key = _canonical_hash(
                    {
                        "case_id": trajectory.case_id,
                        "signal_ref": result.ref,
                        "document_fingerprint": list(fingerprint),
                    }
                )
                event_id = _canonical_hash(
                    {
                        "round_id": record.round_id,
                        "plan_id": record.plan_id,
                        "case_id": trajectory.case_id,
                        "signal_round": round_index,
                        "result_index": result_index,
                        "signal_ref": result.ref,
                    }
                )
                learning_events.append(
                    SignalLearningEvent(
                        event_id=event_id,
                        observation_key=observation_key,
                        signal_ref=result.ref,
                        round_id=record.round_id,
                        plan_id=record.plan_id,
                        case_id=trajectory.case_id,
                        company_id=trajectory.company_id,
                        prediction_time=trajectory.prediction_time.isoformat(),
                        selection=selection.to_learning_dict(),
                        result_value=result.value,
                        coverage=result.coverage,
                        document_fingerprint=fingerprint,
                        is_surge=trajectory.ground_truth.is_surge,
                        realized_max_multiple=(
                            trajectory.ground_truth.realized_max_multiple
                        ),
                        prediction_correct=trajectory.self_reflection.correct,
                        reflection_attribution=_signal_reflection_attribution(
                            result.ref, trajectory.self_reflection
                        ),
                    )
                )
    return tuple(learning_events)


def _signal_reflection_attribution(
    signal_ref: str,
    reflection: PredictionSelfReflection,
) -> tuple[str, ...]:
    signal_id = signal_ref.split(":v", 1)[0].casefold()

    def mentions(values: Iterable[str]) -> bool:
        return any(
            signal_ref.casefold() in value.casefold()
            or signal_id in value.casefold()
            for value in values
        )

    attribution: list[str] = []
    if mentions(reflection.misleading_signals):
        attribution.append("misleading")
    if mentions(reflection.ignored_evidence):
        attribution.append("ignored")
    if mentions(
        (
            *reflection.why_prediction_failed,
            *reflection.missing_information,
            *reflection.plan_issues,
        )
    ):
        attribution.append("other")
    return tuple(attribution)


def collect_signal_usage(
    trajectories: Iterable[ExecutionTrajectory],
) -> dict[str, dict[str, int]]:
    """Count actual selected canonical states, not mere Plan membership."""

    usage: dict[str, dict[str, int]] = {}
    for trajectory in trajectories:
        for signal_round in trajectory.signal_rounds:
            for result in signal_round.batch.results:
                counts = usage.setdefault(
                    result.ref,
                    {value.value: 0 for value in SignalValue},
                )
                counts[result.value.value] += 1
    return usage


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
        serialized = json.dumps(spec.to_dict(), sort_keys=True).casefold()
        serialized += " " + (skill or "").casefold()
        serialized += " " + json.dumps(materialized_tests, sort_keys=True).casefold()
        for phrase in (
            "ground truth",
            "outcome label",
            "realized return",
            "future price",
            "post-outcome",
        ):
            if phrase in serialized:
                reasons.append(f"obvious leakage phrase: {phrase}")
        for identity in self.forbidden_identity_terms:
            normalized_identity = identity.casefold()
            if (
                len(normalized_identity) == 3
                and normalized_identity.isalpha()
                and normalized_identity in _AMBIGUOUS_SHORT_IDENTITY_TERMS
            ):
                continue
            if re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_identity)}(?![a-z0-9])",
                serialized,
            ):
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "applicability": self.applicability,
            "expected_positive_pattern": self.expected_positive_pattern,
            "source_types": list(self.source_types),
            "query": self.query,
            "falsifiers": list(self.falsifiers),
            "lookback_days": self.lookback_days,
        }

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
        if set(data) != required:
            raise ValidationError(
                "Signal Mining hypothesis requires exactly: "
                + ", ".join(sorted(required))
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
        )


@dataclass(frozen=True)
class SignalMiningDecision:
    """A label-revealed contrast decision with an optional complete draft."""

    hypothesis_id: str
    disposition: str
    rationale: tuple[str, ...]
    candidate: Mapping[str, Any] | None = None

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "disposition": self.disposition,
            "rationale": list(self.rationale),
            "candidate": (dict(self.candidate) if self.candidate is not None else None),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningDecision":
        required = {"hypothesis_id", "disposition", "rationale", "candidate"}
        if set(data) != required:
            raise ValidationError(
                "Signal Mining decision requires exactly: "
                + ", ".join(sorted(required))
            )
        raw_candidate = data["candidate"]
        if raw_candidate is not None and not isinstance(raw_candidate, Mapping):
            raise ValidationError("Mining candidate must be an object or null")
        return cls(
            hypothesis_id=str(data["hypothesis_id"]),
            disposition=str(data["disposition"]),
            rationale=_json_string_array(data, "rationale"),
            candidate=(dict(raw_candidate) if raw_candidate is not None else None),
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
        documents: dict[str, str] = {}
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
            documents[document_ref] = content_excerpt
        if signature.observations and not documents:
            raise ValidationError(
                "Mining signature cannot observe an evidence-empty packet at "
                f"signatures[{signature_index}].observations"
            )
        for observation_index, observation in enumerate(signature.observations):
            path = (
                f"signatures[{signature_index}].observations[{observation_index}]"
            )
            excerpt = documents.get(observation.document_ref)
            if excerpt is None:
                raise ValidationError(
                    f"Mining observation uses an unknown document_ref at {path}.document_ref"
                )
            if observation.exact_span not in excerpt:
                raise ValidationError(
                    f"Mining observation exact_span is not a supplied literal at {path}.exact_span"
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
        if self.candidate is not None:
            object.__setattr__(self, "candidate", dict(self.candidate))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_ref": self.signal_ref,
            "disposition": self.disposition,
            "problem_type": self.problem_type,
            "rationale": list(self.rationale),
            "candidate": dict(self.candidate) if self.candidate is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalUpdateDecision":
        required = {
            "signal_ref",
            "disposition",
            "problem_type",
            "rationale",
            "candidate",
        }
        if set(data) != required:
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
            candidate=dict(candidate) if candidate is not None else None,
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
    current_available: int = 0
    current_decisive: int = 0
    current_correct: int = 0
    current_wrong: int = 0

    def __post_init__(self) -> None:
        if self.disposition not in {"promoted", "provisional", "rejected"}:
            raise ValidationError("invalid Signal candidate effectiveness disposition")
        if self.accepted != (self.disposition == "promoted"):
            raise ValidationError(
                "accepted Signal effectiveness must match promoted disposition"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "signal-candidate-effectiveness-v2",
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
            },
            "current": {
                "available": self.current_available,
                "decisive": self.current_decisive,
                "directional_correct": self.current_correct,
                "directional_wrong": self.current_wrong,
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
        for case in _sample_signal_discovery_cases(
            eligible,
            limit=self.case_limit,
        ):
            if len(preferred) >= self.case_limit:
                break
            if case.company_id in seen_companies:
                continue
            preferred.append(case)
            seen_companies.add(case.company_id)
        cases = tuple(preferred)
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
        candidate_values: list[tuple[SignalValue, bool]] = []
        current_values: list[tuple[SignalValue, bool]] = []
        try:
            for case in cases:
                candidate_result = candidate_executor.execute_batch(
                    (spec.ref,),
                    company_id=case.company_id,
                    as_of=case.prediction_time,
                    identity=case.basic_info,
                ).results[0]
                candidate_values.append(
                    (candidate_result.value, case.ground_truth.is_surge)
                )
                if current is not None and current_executor is not None:
                    current_result = current_executor.execute_batch(
                        (current.ref,),
                        company_id=case.company_id,
                        as_of=case.prediction_time,
                        identity=case.basic_info,
                    ).results[0]
                    current_values.append(
                        (current_result.value, case.ground_truth.is_surge)
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
            current_available=current_counts[0],
            current_decisive=current_counts[1],
            current_correct=current_counts[2],
            current_wrong=current_counts[3],
        )


def _signal_effectiveness_counts(
    values: Iterable[tuple[SignalValue, bool]],
) -> tuple[int, int, int, int]:
    available = decisive = correct = wrong = 0
    for value, is_surge in values:
        if value is not SignalValue.UNAVAILABLE:
            available += 1
        if value not in (SignalValue.POSITIVE, SignalValue.NEGATIVE):
            continue
        decisive += 1
        if (value is SignalValue.POSITIVE) == is_surge:
            correct += 1
        else:
            wrong += 1
    return available, decisive, correct, wrong


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
    candidate_effectiveness: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    agent_audits: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

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
            "candidate_effectiveness": {
                ref: dict(value)
                for ref, value in self.candidate_effectiveness.items()
            },
            "agent_audits": {
                name: dict(value) for name, value in self.agent_audits.items()
            },
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
    candidate_effectiveness: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    agent_audits: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

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
            "candidate_effectiveness": {
                ref: dict(value)
                for ref, value in self.candidate_effectiveness.items()
            },
            "agent_audits": {
                name: dict(value) for name, value in self.agent_audits.items()
            },
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
        )


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
            validation = self._validate_cycle(input_snapshot, cycle_id=cycle_id)
            self.workspace.stage_slow_validation(
                cycle_id=cycle_id,
                validation=validation.to_dict(),
            )
        else:
            validation = SlowLoopValidation.from_dict(staged)
        transition = self.registry.promote_validated_batch(
            validation.validated_candidates,
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
            candidate_effectiveness=validation.candidate_effectiveness,
            agent_audits=validation.agent_audits,
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
            prior_validation = self.registry.load_candidate_validation(signal_ref)
            reusable_prior = (
                prior_validation is not None
                and prior_validation.get("schema_version")
                == "signal-candidate-validation-v2"
                and isinstance(prior_validation.get("effectiveness"), Mapping)
                and dict(prior_validation["effectiveness"]).get("disposition")
                != "provisional"
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
                        "schema_version": "signal-candidate-effectiveness-v2",
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
            effectiveness_by_ref[signal_ref] = effectiveness
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
            if validation.accepted:
                semantic_seen[semantic] = signal_ref
                accepted_hashes[signal_ref] = candidate_hash
            validations[signal_ref] = validation
            if not reusable_prior and stable_ref != signal_ref:
                self.registry.record_candidate_validation(
                    signal_ref,
                    candidate_hash=candidate_hash,
                    accepted=validation.accepted,
                    reasons=validation.reasons,
                    contract_validation=contract_validation,
                    effectiveness=effectiveness,
                )
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
            candidate_effectiveness=effectiveness_by_ref,
            agent_audits=agent_audits,
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
        prior = self._prior_signal_update(issue_fingerprint)
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
                    local = dict(prior.get("local_selection", {}))
                    return self._signal_update_output(
                        candidate_refs=(staged_ref,),
                        induction_case_ids={
                            staged_ref: tuple(local.get("induction_case_ids", ()))
                        },
                        validation_case_ids={
                            staged_ref: tuple(local.get("holdout_case_ids", ()))
                        },
                        audit={
                            **base_audit,
                            "disposition": "reused_provisional",
                            "staged_ref": staged_ref,
                            "local_selection": local,
                        },
                    )
            return self._signal_update_output(
                audit={
                    **base_audit,
                    "disposition": "unchanged_issue_suppressed",
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
            if result.value is SignalValue.UNAVAILABLE:
                bucket = "unavailable"
            elif result.value is SignalValue.NEUTRAL:
                bucket = "neutral"
            elif (result.value is SignalValue.POSITIVE) == case.ground_truth.is_surge:
                bucket = "correct"
            else:
                bucket = "wrong"
            classified[bucket].append((case, result, resolution))

        primary_name = (
            "unavailable"
            if target["problem_type"] == "repeated_unavailable"
            else "wrong"
        )
        primary = classified[primary_name][:2]
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
            "available_bucket_counts": {
                name: len(values) for name, values in classified.items()
            },
            "induction_case_ids": [
                case.case_id for case, _result, _resolution in induction
            ],
            "holdout_case_ids": [case.case_id for case in holdout],
            "issuer_disjoint": not (
                induction_companies & {case.company_id for case in holdout}
            ),
        }
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
            "decision": decision.to_dict(),
            "disposition": decision.disposition,
        }
        if decision.disposition != "update":
            return self._signal_update_output(audit=audit)
        assert decision.candidate is not None
        try:
            staged_ref = self._stage_update_candidate(
                signal_ref=signal_ref,
                candidate=decision.candidate,
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
        self, issue_fingerprint: str
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
                if candidate.get("issue_fingerprint") == issue_fingerprint:
                    return candidate
        return None

    def _stage_update_candidate(
        self,
        *,
        signal_ref: str,
        candidate: Mapping[str, Any],
    ) -> str:
        if set(candidate) != {"signal_ref", "spec", "skill", "tests"}:
            raise ValidationError(
                "Signal Update candidate requires exactly signal_ref, spec, skill, tests"
            )
        if str(candidate["signal_ref"]) != signal_ref:
            raise ValidationError("Signal Update candidate changed target signal_ref")
        raw_spec = candidate["spec"]
        raw_tests = candidate["tests"]
        if not isinstance(raw_spec, Mapping) or not isinstance(raw_tests, list):
            raise ValidationError("Signal Update candidate spec/tests shape is invalid")
        stable = self.registry.load_spec(signal_ref)
        updated = self._candidate_spec_from_tool(raw_spec)
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
        skill_value = candidate["skill"]
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
        hypotheses_step = self.mining_model.propose_hypotheses(
            {
                "track": "hypothesis",
                "limits": config.to_dict(),
                "h2_applicability_contract": self._h2_applicability_contract(
                    briefs_by_ref.values()
                ),
                **context,
            }
        )
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
            "hypotheses": [item.to_dict() for item in hypotheses_step.value],
            "usage": _usage_to_dict(hypotheses_step.usage),
        }
        if not hypotheses:
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
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
                evidence_unavailable[hypothesis.hypothesis_id] = (
                    "fewer than the configured issuer-distinct cases had usable "
                    "hypothesis-relevant point-in-time evidence; attempted refs: "
                    + ", ".join(attempted_case_refs),
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
            }
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
            audit["stages"]["H3"] = {
                "status": "not_called_evidence_unavailable",
                "decisions": [],
                "resolutions": resolution_audit,
                "usage": _usage_to_dict(AgentUsage()),
            }
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
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
        selection_by_id = {
            item["hypothesis"].hypothesis_id: item
            for item in evaluable_selections
        }
        staged = self._stage_mining_decisions(
            decisions,
            selection_by_id=selection_by_id,
            case_by_ref=case_by_ref,
            refined=refined,
        )
        audit["candidate_refs"] = list(staged["candidate_refs"])
        audit["staging"] = list(staged["staging"])
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
        case_pairs = tuple(
            (f"case-{index:03d}", case)
            for index, case in enumerate(cases, start=1)
        )
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
        selected = {
            "e1_refs": tuple((*e1_by_class[True], *e1_by_class[False])),
            "validation_refs": tuple(
                (*validation_by_class[True], *validation_by_class[False])
            ),
        }
        priority = ("news", "filings", "financials", "transcripts", "market_data")
        available = set(self.evidence_resolver.available_source_types)
        source_types = tuple(item for item in priority if item in available)
        if not source_types:
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
        extraction_step = self.mining_model.extract_exploration(
            {
                "track": "exploration",
                "cases": evidence_packets,
                "rules": {
                    "labels_hidden": True,
                    "identities_hidden": True,
                    "describe_only_observable_patterns": True,
                },
            }
        )
        signatures = validate_signal_mining_signatures(
            extraction_step.value,
            evidence_packets,
        )
        signature_by_ref = {item.case_ref: item for item in signatures}
        grounded_signatures = tuple(
            signature_by_ref[case_ref]
            for case_ref in selected["e1_refs"]
            if signature_by_ref[case_ref].observations
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
        selected_grounded_signatures = tuple(
            (
                *grounded_by_class[True][: config.induction_cases_per_class],
                *grounded_by_class[False][: config.induction_cases_per_class],
            )
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
                        "usage": _usage_to_dict(extraction_step.usage),
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
                    "usage": _usage_to_dict(extraction_step.usage),
                },
                "E2": {
                    "decisions": [item.to_dict() for item in decisions],
                    "usage": _usage_to_dict(discovery_step.usage),
                },
            },
            "candidate_refs": list(staged["candidate_refs"]),
            "staging": list(staged["staging"]),
            "refined_hypotheses": {
                key: list(value) for key, value in refined.items()
            },
        }
        return self._mining_output(
            audit=audit,
            refined=refined,
            **staged,
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
                "schema_version": "capability-gap-report-v2",
                "items": [],
                "signal_need_items": [],
                "open_count": 0,
                "resolved_count": 0,
            }
        )
        return {
            "cycle_id": cycle_id,
            "meta_info": list(self.meta_memory.model_view()),
            "capability_backlog": capability_backlog,
            "stable_signal_cards": cards,
            "prior_slow_work": prior_work,
            "available_raw_source_types": list(
                self.evidence_resolver.available_source_types
            ),
            "registered_deterministic_functions": sorted(
                self.validator.deterministic_functions
            ),
            "locked_test_available": False,
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
        aliases = _discovery_identity_terms((case,))
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
        masked_info = dict(_mask_identity_values(safe_info, aliases))
        _assert_identity_values_masked(masked_info, aliases)
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
        aliases = _discovery_identity_terms((case,))
        evidence = [
            _model_evidence_view(
                document,
                index=index,
                aliases=aliases,
                query=spec.description,
            )
            for index, document in enumerate(documents, start=1)
        ]
        masked_result = _mask_identity_values(signal_result_model_view(result), aliases)
        _assert_identity_values_masked(evidence, aliases)
        _assert_identity_values_masked(masked_result, aliases)
        packet = {
            "case_ref": case_ref,
            "prediction_time": case.prediction_time.isoformat(),
            "label": "positive" if case.ground_truth.is_surge else "control",
            "evidence": evidence,
            "evidence_scope": (
                "bounded excerpts from every exact Signal execution input; "
                "an excerpt cannot prove that an absent fact is absent from the source"
            ),
            "resolution_status": resolution.status,
            "current_signal_result": masked_result,
        }
        return packet, {
            "case_ref": case_ref,
            "status": resolution.status,
            "input_request": resolution.request.to_dict(),
            "document_count": len(documents),
            "document_ids": [item.document_id for item in documents],
            "document_hashes": [item.content_hash for item in documents],
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
                            "required": ["source_types"],
                            "properties": {
                                "source_types": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"type": "string"},
                                }
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
            schema["constraints"] = [
                *schema["constraints"],
                "spec must preserve signal_id, category, execution type, and deterministic function",
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


def default_information_plan() -> InformationPlan:
    """Return the first manual Plan used to bring up the adaptive runtime."""

    return InformationPlan(
        plan_id="plan_manual_v1",
        parent_ids=(),
        basic_info_policy=BasicInfoPolicy(
            requests=(
                RawInfoRequest(
                    request_id="recent_annual_filing",
                    description=(
                        "Read the latest annual filing available before the prediction "
                        "time for the business model, risks, and segment economics."
                    ),
                    source_types=("10-k",),
                    lookback_days=730,
                    max_documents=1,
                ),
                RawInfoRequest(
                    request_id="recent_company_news",
                    description=(
                        "Retrieve recent company-specific news that may change market "
                        "expectations, financing, customers, regulation, or products."
                    ),
                    source_types=("news",),
                    lookback_days=180,
                    max_documents=5,
                    query="regulatory customer financing product order",
                ),
                RawInfoRequest(
                    request_id="reported_financial_facts",
                    description=(
                        "Inspect reported financial facts available at the prediction "
                        "time for growth, margins, cash, and capital structure."
                    ),
                    source_types=("sec_company_facts",),
                    lookback_days=730,
                    max_documents=2,
                ),
                RawInfoRequest(
                    request_id="recent_market_backbone",
                    description=(
                        "Inspect the latest 45 days of point-in-time price and volume "
                        "for early market confirmation or contradiction."
                    ),
                    source_types=("market_data",),
                    lookback_days=45,
                    max_documents=1,
                ),
            )
        ),
        initial_research_skill=(
            "Form an initial commercialization and expectation-gap hypothesis from "
            "Basic Info only, then state the most decision-relevant information needs."
        ),
        reflection_skill=(
            "Reflect over the entire Signal batch. Track support, contradiction, "
            "resolved questions, concentration risk, and the next smallest set of "
            "information needs; finalize only when the surge thesis is decidable."
        ),
        analysis_prompt=(
            "Organize and weight source-backed supporting and counter evidence for the "
            "fixed six-calendar-month adjusted-share-price 2x Predictor. Distinguish "
            "real commercial adoption from narrative and expose uncertainty; do not "
            "calculate probabilities, classify the final answer, alter the four-way "
            "judgment, or generate the prediction."
        ),
    )


def _agent_raw_document_view(
    document: RawInfoDocument,
    *,
    max_content_chars: int,
    query: str | None = None,
) -> dict[str, Any]:
    """Return a bounded prompt view while the executor keeps the full document."""

    if max_content_chars < 200:
        raise ValidationError("Agent Raw Info preview bound is too small")
    excerpt, truncated = _query_relevant_excerpt(
        document,
        query=query,
        max_chars=max_content_chars,
    )
    compact_metadata = {
        str(key): (value[:500] if isinstance(value, str) else value)
        for key, value in document.metadata.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
    return {
        "document_id": document.document_id,
        "company_id": document.company_id,
        "source_type": document.source_type,
        "published_at": document.published_at.isoformat(),
        "available_at": document.available_at.isoformat(),
        "content_hash": document.content_hash,
        "content_length": len(document.content),
        "content_excerpt": excerpt,
        "content_truncated": truncated,
        "content_projection": "normalized_query_window_v1",
        "metadata": compact_metadata,
        "metadata_keys": sorted(document.metadata),
    }


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _normalize_semantics(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _is_forbidden_basic_info_field(value: str) -> bool:
    normalized = _normalize_field_name(value)
    return normalized in _FORBIDDEN_BASIC_INFO_FIELDS or any(
        normalized.startswith(f"{field}_") or normalized.endswith(f"_{field}")
        for field in _FORBIDDEN_BASIC_INFO_FIELDS
    )


def _legacy_basic_info_request(field_name: str) -> RawInfoRequest:
    """Map a legacy bootstrap field to one fixed source request."""

    normalized = _normalize_field_name(field_name)
    mappings: dict[str, tuple[tuple[str, ...], int | None]] = {
        "company_name": (("company_identity",), None),
        "ticker": (("company_identity",), None),
        "symbol": (("company_identity",), None),
        "market_cap": (("historical_price", "financial_statements"), 365),
        "industry": (("10-k", "filing"), 730),
        "business_description": (("10-k", "filing"), 730),
        "revenue_segments": (("10-k", "financial_statements"), 730),
        "development_stage": (("10-k", "news"), 730),
    }
    source_types, lookback_days = mappings.get(
        normalized, (("legacy_basic_info",), None)
    )
    return RawInfoRequest(
        request_id=f"legacy_{normalized}",
        description=f"Legacy request for source evidence about {field_name}.",
        source_types=source_types,
        lookback_days=lookback_days,
        max_documents=5,
    )


def _discovery_identity_terms(cases: Iterable[EvolutionCase]) -> tuple[str, ...]:
    identity_keys = {
        "company_id",
        "company_name",
        "ticker",
        "symbol",
        "identity_aliases",
    }
    terms: set[str] = set()
    for case in cases:
        terms.add(case.company_id)
        for key, value in case.basic_info.items():
            if key not in identity_keys:
                continue
            if isinstance(value, str):
                terms.add(value)
            elif isinstance(value, Iterable) and not isinstance(value, Mapping):
                terms.update(str(item) for item in value)
    return tuple(sorted((item for item in terms if item.strip()), key=len, reverse=True))


def _sample_signal_discovery_cases(
    cases: Iterable[EvolutionCase], *, limit: int
) -> tuple[EvolutionCase, ...]:
    """Return a deterministic issuer-distinct four-label round-robin sample."""

    if limit < 1:
        raise ValidationError("Discovery sample limit must be positive")
    buckets = {
        label: sorted(
            (case for case in cases if evaluation_label(case) == label),
            key=lambda case: case.case_id,
        )
        for label in EVALUATION_LABELS
    }
    selected: list[EvolutionCase] = []
    seen_companies: set[str] = set()
    offsets = {label: 0 for label in EVALUATION_LABELS}
    while len(selected) < limit:
        advanced = False
        for label in EVALUATION_LABELS:
            bucket = buckets[label]
            while offsets[label] < len(bucket):
                case = bucket[offsets[label]]
                offsets[label] += 1
                if case.company_id in seen_companies:
                    continue
                selected.append(case)
                seen_companies.add(case.company_id)
                advanced = True
                break
            if len(selected) >= limit:
                break
        if not advanced:
            break
    return tuple(selected)


def _sample_binary_discovery_cases(
    cases: Iterable[EvolutionCase], *, per_class: int
) -> tuple[EvolutionCase, ...]:
    """Return deterministic issuer-distinct positive/control cases in equal counts."""

    if per_class < 1:
        raise ValidationError("binary Discovery sample size must be positive")
    positives = sorted(
        (case for case in cases if case.ground_truth.is_surge),
        key=lambda case: case.case_id,
    )
    controls = sorted(
        (case for case in cases if not case.ground_truth.is_surge),
        key=lambda case: case.case_id,
    )
    selected: list[EvolutionCase] = []
    seen_companies: set[str] = set()
    for bucket in (positives, controls):
        count = 0
        for case in bucket:
            if case.company_id in seen_companies:
                continue
            selected.append(case)
            seen_companies.add(case.company_id)
            count += 1
            if count >= per_class:
                break
    return tuple(selected)


def _market_cap_bucket(value: Any) -> str:
    """Coarsen optional market cap without fabricating missing precision."""

    try:
        market_cap = float(value)
    except (TypeError, ValueError):
        return "unavailable"
    if not math.isfinite(market_cap) or market_cap < 0:
        return "unavailable"
    if market_cap < 300_000_000:
        return "micro"
    if market_cap < 2_000_000_000:
        return "small"
    if market_cap < 10_000_000_000:
        return "mid"
    return "large"


def _point_in_time_profile_fields(
    basic_info: Mapping[str, Any],
    documents: Iterable[RawInfoDocument],
) -> dict[str, Any]:
    """Extract a small outcome-free company profile from already local as-of data."""

    aliases = {
        "business_description": (
            "business_description",
            "company_description",
            "description",
            "long_business_summary",
            "business_summary",
        ),
        "industry": ("industry", "industry_name"),
        "sector": ("sector", "sector_name"),
        "exchange": ("exchange", "primary_exchange", "exchange_name"),
        "market_cap": ("market_cap", "market_capitalization", "marketcap"),
        "listing_date": ("ipo_date", "listing_date", "list_date"),
    }
    sources: list[Mapping[str, Any]] = [basic_info]
    for document in documents:
        sources.append(document.metadata)
        stripped = document.content.lstrip()
        if len(document.content) > 100_000 or not stripped.startswith(("{", "[")):
            continue
        try:
            parsed = json.loads(document.content)
        except (json.JSONDecodeError, TypeError):
            continue
        sources.extend(_nested_profile_mappings(parsed, depth=0))
    output: dict[str, Any] = {}
    for canonical, accepted_keys in aliases.items():
        for source in sources:
            normalized = {str(key).casefold(): value for key, value in source.items()}
            value = next(
                (
                    normalized[key]
                    for key in accepted_keys
                    if key in normalized and normalized[key] not in (None, "")
                ),
                None,
            )
            if value is None:
                continue
            if canonical == "business_description" and isinstance(value, str):
                output[canonical] = " ".join(value.split())[:800]
            elif isinstance(value, (str, int, float)):
                output[canonical] = value
            if canonical in output:
                break
    return output


class _FilingLeafBlockParser(HTMLParser):
    """Project filing HTML into non-duplicated leaf text blocks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[list[Any]] = []
        self._anchor_depth = 0
        self.blocks: list[tuple[str, bool]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        normalized = tag.casefold()
        if normalized == "a":
            self._anchor_depth += 1
        if normalized in _FILING_BLOCK_TAGS:
            if self._stack:
                self._stack[-1][3] += 1
            self._stack.append(
                [normalized, [], self._anchor_depth > 0, 0]
            )
        elif normalized == "br":
            for frame in self._stack:
                frame[1].append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in _FILING_BLOCK_TAGS and self._stack:
            match = next(
                (
                    index
                    for index in range(len(self._stack) - 1, -1, -1)
                    if self._stack[index][0] == normalized
                ),
                None,
            )
            if match is not None:
                closing = self._stack[match:]
                self._stack = self._stack[:match]
                for _tag, parts, has_anchor, nested_blocks in reversed(closing):
                    text = " ".join("".join(parts).split())
                    if text and nested_blocks == 0:
                        self.blocks.append((text, bool(has_anchor)))
        if normalized == "a" and self._anchor_depth:
            self._anchor_depth -= 1

    def handle_data(self, data: str) -> None:
        for frame in self._stack:
            frame[1].append(data)
            if self._anchor_depth:
                frame[2] = True


def _filing_heading_key(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _is_item1_start_heading(value: str) -> bool:
    tokens = _filing_heading_key(value).split()
    return (
        tokens[:3] == ["item", "1", "business"]
        or tokens[:5] == ["item", "1", "description", "of", "business"]
    ) and len(tokens) <= 7


def _is_item1_end_heading(value: str) -> bool:
    tokens = _filing_heading_key(value).split()
    return (
        tokens[:4] == ["item", "1a", "risk", "factors"]
        or tokens[:3] == ["item", "2", "properties"]
    ) and len(tokens) <= 7


def _usable_business_description(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = " ".join(value.split())
    return (
        len(normalized) >= 60
        and sum(character.isalpha() for character in normalized) >= 40
        and len(re.findall(r"[A-Za-z]{2,}", normalized)) >= 8
    )


def _html_item1_business_excerpt(raw_text: str) -> str | None:
    parser = _FilingLeafBlockParser()
    try:
        parser.feed(raw_text)
        parser.close()
    except (AssertionError, ValueError):
        return None
    blocks = parser.blocks
    start_indexes = [
        index
        for index, (text, linked) in enumerate(blocks)
        if not linked and _is_item1_start_heading(text)
    ]
    for start in start_indexes:
        section: list[str] = []
        for text, linked in blocks[start + 1 :]:
            if not linked and _is_item1_end_heading(text):
                break
            heading = _filing_heading_key(text)
            if linked or heading in {"table of contents", "part i"}:
                continue
            if len(re.findall(r"[A-Za-z]{2,}", text)) < 15:
                continue
            if "forward-looking" in text.casefold():
                continue
            section.append(text)
        for position, text in enumerate(section):
            terms = {
                match.group(0).casefold()
                for match in _BUSINESS_PROFILE_TERM.finditer(text)
            }
            boilerplate_count = sum(
                phrase in text.casefold()
                for phrase in _BUSINESS_PROFILE_BOILERPLATE
            )
            if len(terms) < 3 or boilerplate_count >= 2:
                continue
            excerpt = " ".join(section[position:])[:800]
            if _usable_business_description(excerpt):
                return excerpt
    return None


def _plain_item1_business_excerpt(raw_text: str) -> str | None:
    text_value, _runs = _normalized_projection_text(raw_text)
    matches = re.finditer(
        r"\bitem\s+1[.\s:-]+business\b(?P<body>.*?)(?="
        r"\bitem\s+1a[.\s:-]+risk\s+factors\b|"
        r"\bitem\s+2[.\s:-]+properties\b|$)",
        text_value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in matches:
        excerpt = " ".join(match.group("body").split())[:800]
        if _usable_business_description(excerpt):
            return excerpt
    return None


def _item1_business_excerpt(
    documents: Iterable[RawInfoDocument],
) -> str | None:
    """Extract a substantive bounded Item 1 business excerpt from an as-of filing."""

    for document in sorted(
        documents,
        key=lambda item: (item.available_at, item.document_id),
        reverse=True,
    ):
        if document.source_type.casefold() not in {
            "10-k",
            "filing",
            "filing_body",
            "sec_filing",
        }:
            continue
        excerpt = (
            _html_item1_business_excerpt(document.content)
            if _HTML_TAG.search(document.content)
            else _plain_item1_business_excerpt(document.content)
        )
        if excerpt is not None:
            return excerpt
    return None


def _model_evidence_view(
    document: RawInfoDocument,
    *,
    index: int,
    aliases: tuple[str, ...],
    query: str | None,
) -> dict[str, Any]:
    """Return one bounded, masked model view with immutable source lineage."""

    view = _agent_raw_document_view(
        document, max_content_chars=1_200, query=query
    )
    return {
        "document_ref": f"document-{index:02d}",
        "source_type": view["source_type"],
        "published_at": view["published_at"],
        "available_at": view["available_at"],
        "content_hash": view["content_hash"],
        "content_excerpt": _mask_identity_values(view["content_excerpt"], aliases),
        "content_truncated": view["content_truncated"],
        "content_projection": view["content_projection"],
    }


def _select_h3_model_evidence(
    documents: tuple[RawInfoDocument, ...],
    *,
    case: EvolutionCase,
    query: str | None,
    limit: int,
) -> tuple[tuple[RawInfoDocument, ...], list[dict[str, Any]], dict[str, Any]]:
    """Select a bounded complementary H3 packet from an eligible ranked pool."""

    aliases = _discovery_identity_terms((case,))
    eligible: list[RawInfoDocument] = []
    filtered: list[dict[str, str]] = []
    for document in documents:
        if (
            "news" in document.source_type.casefold()
            and not document_has_strong_issuer_match(document, case.basic_info)
        ):
            filtered.append(
                {
                    "document_id": document.document_id,
                    "reason": "missing_strong_issuer_match",
                }
            )
        else:
            eligible.append(document)
    full_coverage = _h3_packet_query_coverage(eligible, query=query)
    indexed_views = [
        (
            index,
            document,
            _model_evidence_view(
                document, index=1, aliases=aliases, query=query
            ),
        )
        for index, document in enumerate(eligible)
    ]
    selected: list[RawInfoDocument] = []
    evidence: list[dict[str, Any]] = []
    remaining = list(indexed_views)
    while remaining and len(selected) < limit:
        best = max(
            remaining,
            key=lambda item: _h3_selection_score(
                (*evidence, item[2]), query=query, rank=item[0]
            ),
        )
        remaining.remove(best)
        selected.append(best[1])
        evidence.append(
            {**best[2], "document_ref": f"document-{len(evidence) + 1:02d}"}
        )
    query_coverage = _h3_text_query_coverage(
        (str(item["content_excerpt"]) for item in evidence), query=query
    )
    query_coverage["scope"] = "model_visible_excerpts"
    query_coverage["full_document_coverage"] = full_coverage
    selected_ids = {item.document_id for item in selected}
    filtered.extend(
        {
            "document_id": document.document_id,
            "reason": "document_limit_not_selected",
        }
        for document in eligible
        if document.document_id not in selected_ids
    )
    return tuple(selected), evidence, {
        "filtered_documents": filtered,
        "query_coverage": query_coverage,
        "query_match_status": (
            "matched"
            if query_coverage["sufficient"]
            else (
                "unmatched_comparator_context"
                if selected
                else "no_exact_source"
            )
        ),
    }


def _h3_selection_score(
    evidence: tuple[dict[str, Any], ...],
    *,
    query: str | None,
    rank: int,
) -> tuple[int, int, int, int]:
    """Prefer sufficient, term-diverse, ordered evidence with stable rank ties."""

    coverage = _h3_text_query_coverage(
        (str(item["content_excerpt"]) for item in evidence), query=query
    )
    return (
        int(coverage["sufficient"]),
        len(coverage["matched_terms"]),
        len(coverage["matched_ordered_pairs"]),
        -rank,
    )


def _h3_ordered_content_terms(
    value: str,
    *,
    exclude_generic: bool,
) -> tuple[str, ...]:
    """Normalize ordered query/content terms without substring matching."""

    result: list[str] = []
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    for raw in re.findall(r"[A-Za-z0-9]+", separated.casefold()):
        if len(raw) < 3 or (exclude_generic and raw in _GENERIC_QUERY_WORDS):
            continue
        term = raw[:-3] + "y" if raw.endswith("ies") else raw
        if term.endswith("s") and len(term) > 4 and not term.endswith("ss"):
            term = term[:-1]
        if exclude_generic and term in _GENERIC_QUERY_WORDS:
            continue
        result.append(term)
    return tuple(result)


def _h3_matched_query_pairs(
    query_terms: tuple[str, ...],
    visible_terms: tuple[str, ...],
    *,
    max_gap: int = 4,
) -> set[tuple[str, str]]:
    """Return consecutive query pairs found in order within a short term gap."""

    pairs = set(zip(query_terms, query_terms[1:]))
    matched: set[tuple[str, str]] = set()
    for first, second in pairs:
        for index, term in enumerate(visible_terms):
            if term != first:
                continue
            if second in visible_terms[index + 1 : index + 1 + max_gap]:
                matched.add((first, second))
                break
    return matched


def _h3_packet_query_coverage(
    documents: Iterable[RawInfoDocument],
    *,
    query: str | None,
) -> dict[str, Any]:
    """Audit distinct-term and short-range ordered-pair packet coverage."""

    return _h3_text_query_coverage(
        (_h3_document_visible_text(document) for document in documents),
        query=query,
    )


def _h3_text_query_coverage(
    visible_texts: Iterable[str],
    *,
    query: str | None,
) -> dict[str, Any]:
    """Audit query coverage over the exact visible text supplied by a caller."""

    ordered_query_terms = tuple(
        dict.fromkeys(_h3_ordered_content_terms(query or "", exclude_generic=True))
    )
    query_terms = set(ordered_query_terms)
    matched_terms: set[str] = set()
    matched_pairs: set[tuple[str, str]] = set()
    for visible_text in visible_texts:
        visible_terms = _h3_ordered_content_terms(
            visible_text,
            exclude_generic=True,
        )
        matched_terms.update(query_terms & set(visible_terms))
        matched_pairs.update(
            _h3_matched_query_pairs(ordered_query_terms, visible_terms)
        )
    required_match_count = (
        len(query_terms)
        if len(query_terms) <= 2
        else math.ceil(len(query_terms) * 0.75)
    )
    required_pair_count = (
        0 if len(query_terms) <= 2 else math.ceil((len(query_terms) - 1) * 0.5)
    )
    sufficient = (
        not query_terms
        or (
            len(matched_terms) >= required_match_count
            and len(matched_pairs) >= required_pair_count
        )
    )
    return {
        "query_terms": list(ordered_query_terms),
        "matched_terms": sorted(matched_terms),
        "required_match_count": required_match_count,
        "required_ordered_pair_count": required_pair_count,
        "matched_ordered_pairs": [
            f"{first} {second}" for first, second in sorted(matched_pairs)
        ],
        "sufficient": sufficient,
    }


def _h3_content_terms(value: str, *, exclude_generic: bool) -> set[str]:
    """Normalize bounded query/content terms without substring matching."""

    return set(_h3_ordered_content_terms(value, exclude_generic=exclude_generic))


def _h3_document_visible_text(document: RawInfoDocument) -> str:
    """Return deterministic reader-visible text for H3 relevance and excerpts."""

    title = str(document.metadata.get("title", ""))
    if "news" in document.source_type.casefold():
        try:
            payload = json.loads(document.content)
        except (json.JSONDecodeError, TypeError):
            payload = None
        if isinstance(payload, Mapping):
            fields = [
                str(payload.get(key) or "")
                for key in ("title", "summary", "body", "content")
            ]
            return " ".join("\n".join((title, *fields)).split())
    projected, _runs = _normalized_projection_text(document.content)
    return " ".join(f"{title}\n{projected}".split())


def _query_relevant_excerpt(
    document: RawInfoDocument,
    *,
    query: str | None,
    max_chars: int,
) -> tuple[str, bool]:
    """Select one bounded visible window around the strongest query match."""

    text_value = _h3_document_visible_text(document)
    if len(text_value) <= max_chars:
        return text_value, False
    query_terms = _h3_content_terms(query or "", exclude_generic=True)
    anchors = (
        [
            match.start()
            for match in re.finditer(r"[A-Za-z0-9]+", text_value)
            if query_terms.intersection(
                _h3_content_terms(match.group(0), exclude_generic=True)
            )
        ]
        if query_terms else []
    )
    starts = {0}
    starts.update(
        max(0, min(len(text_value) - max_chars, anchor - max_chars // 3))
        for anchor in anchors
    )

    # Score exactly the boundary-adjusted window that will leave the controller.
    adjusted_starts = set()
    for start in starts:
        boundary = text_value.find(" ", start, start + 80) if start else -1
        adjusted_starts.add(boundary + 1 if boundary >= 0 else start)

    def score(start: int) -> tuple[int, int, int, int]:
        coverage = _h3_text_query_coverage(
            (text_value[start : start + max_chars],), query=query
        )
        return (
            int(coverage["sufficient"]),
            len(coverage["matched_terms"]),
            len(coverage["matched_ordered_pairs"]),
            -start,
        )

    start = max(adjusted_starts, key=score)
    return text_value[start : start + max_chars], True


def _nested_profile_mappings(value: Any, *, depth: int) -> list[Mapping[str, Any]]:
    """Bound traversal of common JSON profile wrappers without schema guessing."""

    if depth > 3:
        return []
    if isinstance(value, Mapping):
        rows: list[Mapping[str, Any]] = [value]
        for child in value.values():
            if isinstance(child, (Mapping, list)):
                rows.extend(_nested_profile_mappings(child, depth=depth + 1))
        return rows
    if isinstance(value, list):
        rows = []
        for child in value[:10]:
            if isinstance(child, (Mapping, list)):
                rows.extend(_nested_profile_mappings(child, depth=depth + 1))
        return rows
    return []


def _listing_age_bucket(value: Any, *, as_of: datetime) -> str:
    """Coarsen optional listing date into a label-free applicability feature."""

    if not isinstance(value, str) or not value.strip():
        return "unavailable"
    try:
        listed = datetime.fromisoformat(value).date()
    except ValueError:
        try:
            listed = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return "unavailable"
    years = max(0.0, (as_of.date() - listed).days / 365.25)
    if years < 1:
        return "under_1y"
    if years < 5:
        return "1_5y"
    if years < 10:
        return "5_10y"
    return "over_10y"


def _default_case_id(company_id: str, prediction_time: datetime) -> str:
    _require_aware_datetime(prediction_time, "prediction_time")
    timestamp = prediction_time.astimezone(timezone.utc).strftime("%Y%m%dt%H%M%sz")
    return f"{company_id}:{timestamp}"


def _compiled_identity_aliases(
    aliases: Iterable[str],
) -> tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...]:
    """Compile exact prose and URL identity matchers once per payload traversal."""

    compiled: list[tuple[str, re.Pattern[str], re.Pattern[str]]] = []
    for alias in _identity_alias_variants(aliases):
        escaped = _identity_alias_pattern(alias)
        pattern = (
            rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
            if alias[0].isalnum() and alias[-1].isalnum()
            else escaped
        )
        prose_flags = (
            0
            if alias.isalnum() and alias.isupper() and len(alias) <= 5
            else re.IGNORECASE
        )
        compiled.append(
            (
                alias,
                re.compile(pattern, flags=prose_flags),
                re.compile(pattern, flags=re.IGNORECASE),
            )
        )
    return tuple(compiled)


def _identity_alias_pattern(alias: str) -> str:
    """Allow common filing punctuation variants without broad fuzzy matching."""

    ticker_like = alias.isalnum() and alias.isupper() and len(alias) <= 5
    if ticker_like:
        return re.escape(alias)
    tokens = re.findall(r"[A-Za-z0-9]+", alias.replace("&", " and "))
    if len(tokens) >= 2:
        token_patterns = [
            r"(?:and|&)" if token.casefold() == "and" else re.escape(token)
            for token in tokens
        ]
        return r"[^A-Za-z0-9]+".join(token_patterns)
    if len(tokens) == 1 and len(tokens[0]) >= 6 and tokens[0].casefold().endswith("s"):
        return re.escape(tokens[0][:-1]) + r"[’']?s"
    return re.escape(alias)


def _mask_identity_values(value: Any, aliases: Iterable[str]) -> Any:
    matchers = _compiled_identity_aliases(aliases)

    def mask_url(match: re.Match[str]) -> str:
        result = match.group(0)
        for _alias, _prose_matcher, url_matcher in matchers:
            result = url_matcher.sub(_IDENTITY_MASK_SENTINEL, result)
        return result

    def mask(item: Any) -> Any:
        if isinstance(item, str):
            result = item
            for _alias, prose_matcher, _url_matcher in matchers:
                result = prose_matcher.sub(_IDENTITY_MASK_SENTINEL, result)
            result = _URL_VALUE.sub(mask_url, result)
            return result.replace(_IDENTITY_MASK_SENTINEL, _MASKED_IDENTITY_VALUE)
        if isinstance(item, list):
            return [mask(child) for child in item]
        if isinstance(item, tuple):
            return tuple(mask(child) for child in item)
        if isinstance(item, Mapping):
            return {key: mask(child) for key, child in item.items()}
        return item

    return mask(value)


def _identity_alias_variants(aliases: Iterable[str]) -> tuple[str, ...]:
    """Expand formal target identities into the names used by ordinary prose."""

    variants: set[str] = set()
    for raw_alias in aliases:
        alias = " ".join(str(raw_alias or "").split()).strip()
        if not alias:
            continue
        variants.add(alias)
        for component in _IDENTITY_NAME_SEPARATOR.split(alias):
            component = " ".join(component.split()).strip(" ,")
            if not _is_meaningful_derived_identity_alias(component):
                continue
            variants.add(component)
            natural_name = component
            while True:
                stripped = _IDENTITY_LEGAL_SUFFIX.sub("", natural_name).strip(" ,")
                if stripped == natural_name:
                    break
                natural_name = stripped
            if _is_meaningful_derived_identity_alias(natural_name):
                variants.add(natural_name)
            brand = natural_name.split(maxsplit=1)[0].strip(".,'\"")
            brand_length = sum(character.isalnum() for character in brand)
            if (
                (brand_length >= 4 or (brand_length >= 3 and brand.isupper()))
                and brand.casefold() not in _GENERIC_IDENTITY_LEADING_WORDS
            ):
                variants.add(brand)
    return tuple(sorted(variants, key=lambda item: (-len(item), item.casefold(), item)))


def _is_meaningful_derived_identity_alias(value: str) -> bool:
    compact = "".join(character for character in value if character.isalnum())
    if len(compact) >= 4:
        return True
    return len(compact) >= 2 and any(character.isdigit() for character in compact)


def _assert_identity_values_masked(value: Any, aliases: Iterable[str]) -> None:
    """Fail closed if the assembled Predictor context still names its target."""

    matchers = _compiled_identity_aliases(aliases)

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                visit(child, f"{path}.{key}")
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")
            return
        if not isinstance(item, str):
            return
        anonymous_item = item.replace(_MASKED_IDENTITY_VALUE, "")
        urls = tuple(match.group(0) for match in _URL_VALUE.finditer(anonymous_item))
        for _alias, prose_matcher, url_matcher in matchers:
            if prose_matcher.search(anonymous_item):
                raise ValidationError(
                    f"target identity remained in anonymous context: {path}"
                )
            for url in urls:
                if url_matcher.search(url):
                    raise ValidationError(
                        f"target identity remained in anonymous context URL: {path}"
                    )

    visit(value, "final_context")


def _validate_id(value: str, name: str) -> None:
    if not _SAFE_ID.fullmatch(value):
        raise ValidationError(f"{name} must use lowercase safe identifier characters")


def _require_aware_datetime(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} must be timezone-aware")


def _usage_to_dict(usage: AgentUsage) -> dict[str, Any]:
    return {
        "llm_calls": usage.llm_calls,
        "tokens": usage.tokens,
        "cost": usage.cost,
    }


def _usage_from_dict(data: Mapping[str, Any]) -> AgentUsage:
    return AgentUsage(
        llm_calls=int(data.get("llm_calls", 0)),
        tokens=int(data.get("tokens", 0)),
        cost=float(data.get("cost", 0.0)),
    )


def summarize_information_plan(
    plan: InformationPlan,
    *,
    max_text_chars: int = 180,
) -> dict[str, Any]:
    """Return a concise, terminal/dashboard-safe summary of one sampled Plan."""

    if max_text_chars < 20:
        raise ValidationError("Plan summary text limit is too small")

    def clip(value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= max_text_chars:
            return normalized
        return normalized[: max_text_chars - 1].rstrip() + "…"

    return {
        "plan_id": plan.plan_id,
        "parent_ids": list(plan.parent_ids),
        "basic_info_requests": [
            {
                "request_id": item.request_id,
                "source_types": list(item.source_types),
                "lookback_days": item.lookback_days,
                "max_documents": item.max_documents,
            }
            for item in plan.basic_info_policy.requests
        ],
        "initial_research": clip(plan.initial_research_skill),
        "reflection": clip(plan.reflection_skill),
        "analysis": clip(plan.analysis_prompt),
    }


def _emit_progress(
    callback: ProgressCallback | None,
    event_type: str,
    **details: Any,
) -> None:
    if callback is not None:
        callback({"event_type": event_type, **details})


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _last_event_sequence(path: Path) -> int:
    if not path.exists():
        return 0
    latest = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            latest = max(latest, int(value.get("sequence", 0)))
    return latest


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"required evolution artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"evolution artifact must be an object: {path}")
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    """Reuse a crash-staged JSON object only when its canonical value is exact."""

    expected = json.loads(json.dumps(dict(value), sort_keys=True))
    if path.exists():
        actual = _read_json(path)
        if actual != expected:
            raise ValidationError(f"conflicting staged evolution artifact: {path}")
        return
    _atomic_write_json(path, expected)
