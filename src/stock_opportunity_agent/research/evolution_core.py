"""Immutable records, pure rules, and shared helpers for evolution."""

from __future__ import annotations

import hashlib
import html
import json
import math
import random
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from fractions import Fraction
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Generic, Iterable, Mapping, Protocol, TypeVar
from stock_opportunity_agent.artifacts import (
    atomic_write_json as _atomic_write_json,
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.data.markup import nonvisible_html_ranges
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import (
    document_has_strong_issuer_match,
    MAX_BASIC_INFO_REQUESTS,
    RawInfoRequest,
    RawInfoResolution,
)
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_reflection_memory import (
    ReflectionItem,
    ReflectionMemoryIndex,
    reflection_items_from_dict,
    validate_source_snapshot,
)
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    SignalBatchResult,
    SignalExecutionStatus,
    SignalExecutionType,
    SignalExecutor,
    SignalLearningEvent,
    SignalResult,
    SignalValue,
    SIGNAL_CONTEXT_TAGS,
    signal_result_model_view,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stock_opportunity_agent.research.plan_evolution import PlanEvaluationAttempt


T = TypeVar("T")


ProgressCallback = Callable[[Mapping[str, Any]], None]


MAX_PREDICTOR_CONTEXT_UTF8_BYTES = 24_000


_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]*$")


_IDENTITY_MASK_SENTINEL = "\ue000\ue001"


_MASKED_IDENTITY_VALUE = "[MASKED_COMPANY]"


_TARGET_AFFILIATE_RELATION = re.compile(
    r"(?P<name>\b[A-Z][A-Za-z0-9&.'’+-]*"
    r"(?:\s+(?:[A-Z][A-Za-z0-9&.'’+-]*|of|the|and|&)){0,5})"
    r"(?P<relation>\s*,?\s+(?:an?\s+)?(?:division|subsidiary|brand|business|"
    r"unit|segment)\s+of\s+\[MASKED_COMPANY\])"
)


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
        "critical",
        "energy",
        "first",
        "general",
        "global",
        "green",
        "high",
        "international",
        "life",
        "national",
        "new",
        "north",
        "the",
        "travel",
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


_GENERIC_AGGREGATE_IDENTITY_WORDS = (
    _GENERIC_IDENTITY_LEADING_WORDS
    | _GENERIC_QUERY_WORDS
    | {
        "age",
        "all",
        "alpha",
        "bucket",
        "data",
        "description",
        "exchange",
        "facts",
        "filing",
        "financials",
        "future",
        "historical",
        "info",
        "issuers",
        "listing",
        "market",
        "match",
        "news",
        "open",
        "price",
        "raw",
        "ready",
        "signal",
        "source",
        "topics",
        "type",
        "values",
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

    removed: list[tuple[int, int]] = list(nonvisible_html_ranges(raw_text))
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
        # Disclose what the budgets omitted: resolver-level markers arrive on
        # the resolution; projection-level omissions preview their normalized
        # text here. Ranked-but-unfunded content stays addressable instead of
        # silently vanishing behind a green structural status.
        chosen_indices = set(indices)
        omitted_markers = list(resolution.omitted_context_markers)
        for row_index, (model_row, _audit_row) in enumerate(rows):
            if row_index in chosen_indices or len(omitted_markers) >= 8:
                continue
            preview = " ".join(str(model_row["exact_text"]).split())
            omitted_markers.append(preview[:110])
        model_requests.append(
            {
                "request": resolution.request.to_dict(),
                "status": resolution.status,
                "projections": model_spans,
                "projection_status": projection_status,
                "available_projection_count": available_count,
                "visible_projection_count": visible_count,
                "omitted_projection_count": omitted_count,
                "omitted_context_markers": omitted_markers[:8],
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
    metadata: Mapping[str, Any] = field(default_factory=dict)


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
        if not isinstance(self.claim, str) or not self.claim.strip():
            raise ValidationError("research evidence claim must be nonempty text")
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
class JevDecisionSignal:
    """One persisted Jev choice used as diagnostic evolution feedback."""

    provider: str
    model: str
    response_id: str
    question_id: str
    choice: str
    probabilities: Mapping[str, float]
    confidence: float

    def __post_init__(self) -> None:
        for name in (
            "provider",
            "model",
            "response_id",
            "question_id",
            "choice",
        ):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"Jev decision {name} must not be empty")
        probabilities = {
            str(key): float(value) for key, value in self.probabilities.items()
        }
        if self.choice not in probabilities:
            raise ValidationError("Jev choice must be present in probabilities")
        if not probabilities or any(
            not math.isfinite(value) or value < 0 or value > 1
            for value in probabilities.values()
        ):
            raise ValidationError("Jev probabilities must be finite values in [0, 1]")
        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.001):
            raise ValidationError("Jev probabilities must sum to one")
        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValidationError("Jev confidence must be in [0, 1]")
        object.__setattr__(self, "probabilities", probabilities)
        object.__setattr__(self, "confidence", confidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "response_id": self.response_id,
            "question_id": self.question_id,
            "choice": self.choice,
            "probabilities": dict(self.probabilities),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JevDecisionSignal":
        required = {
            "provider",
            "model",
            "response_id",
            "question_id",
            "choice",
            "probabilities",
            "confidence",
        }
        if set(data) != required or not isinstance(data["probabilities"], Mapping):
            raise ValidationError("Jev decision fields are invalid")
        return cls(
            provider=str(data["provider"]),
            model=str(data["model"]),
            response_id=str(data["response_id"]),
            question_id=str(data["question_id"]),
            choice=str(data["choice"]),
            probabilities={
                str(key): float(value)
                for key, value in data["probabilities"].items()
            },
            confidence=float(data["confidence"]),
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
    jev_decision: JevDecisionSignal | None = None

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
        if self.jev_decision is not None and not isinstance(
            self.jev_decision, JevDecisionSignal
        ):
            object.__setattr__(
                self,
                "jev_decision",
                JevDecisionSignal.from_dict(self.jev_decision),
            )

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
        if self.jev_decision is not None:
            value["jev_decision"] = self.jev_decision.to_dict()
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
        optional = {
            "target_need_indices",
            "answer_scope",
            "residual_need",
            "jev_decision",
        }
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
        raw_jev_decision = data.get("jev_decision")
        if raw_jev_decision is not None and not isinstance(
            raw_jev_decision, Mapping
        ):
            raise ValidationError("Signal selection Jev decision must be an object")
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
            jev_decision=(
                JevDecisionSignal.from_dict(dict(raw_jev_decision))
                if raw_jev_decision is not None
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
    jev_decisions: tuple[JevDecisionSignal, ...] = ()

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
        decisions = tuple(self.jev_decisions)
        if any(not isinstance(item, JevDecisionSignal) for item in decisions):
            decisions = tuple(
                item
                if isinstance(item, JevDecisionSignal)
                else JevDecisionSignal.from_dict(item)
                for item in decisions
            )
        if len({item.question_id for item in decisions}) != len(decisions):
            raise ValidationError("BlindPrediction Jev question ids must be unique")
        object.__setattr__(self, "jev_decisions", decisions)

    def to_dict(self) -> dict[str, Any]:
        value = {
            "is_surge": self.is_surge,
            "candidate_judgment": self.candidate_judgment.value,
            "magnitude": self.magnitude.value if self.magnitude else None,
            "confidence": {"level": self.confidence.value},
            "key_reasons": list(self.key_reasons),
            "uncertainties": list(self.uncertainties),
            "session_id": self.session_id,
        }
        if self.jev_decisions:
            value["jev_decisions"] = [item.to_dict() for item in self.jev_decisions]
        return value

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
        raw_jev_decisions = data.get("jev_decisions", ())
        if not isinstance(raw_jev_decisions, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in raw_jev_decisions
        ):
            raise ValidationError("BlindPrediction Jev decisions must be objects")
        return cls(
            is_surge=_json_boolean(data["is_surge"], "BlindPrediction is_surge"),
            candidate_judgment=data["candidate_judgment"],
            magnitude=MagnitudeClass(str(magnitude)) if magnitude else None,
            confidence=ConfidenceLevel(confidence_value),
            key_reasons=_json_string_array(data, "key_reasons"),
            uncertainties=_json_string_array(data, "uncertainties"),
            session_id=data["session_id"],
            jev_decisions=tuple(
                JevDecisionSignal.from_dict(item)
                for item in raw_jev_decisions
            ),
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


_MAGNITUDE_CLASS_ORDER: tuple[MagnitudeClass, ...] = (
    MagnitudeClass.TWO_TO_THREE,
    MagnitudeClass.THREE_TO_TEN,
    MagnitudeClass.TEN_PLUS,
)

_MAGNITUDE_DIAGNOSTICS_REQUIRED_KEYS = frozenset(
    {
        "confusion_matrix",
        "per_class_support",
        "prediction_distribution",
        "truth_distribution",
        "surge_case_count",
        "magnitude_correct_count",
        "underestimate_count",
        "overestimate_count",
        "missed_surge_count",
        "conditional_accuracy_on_tp",
        "tp_denominator",
        "undefined_reason",
    }
)


def magnitude_feedback(
    prediction: BlindPrediction,
    ground_truth: GroundTruth,
) -> dict[str, Any]:
    """Derive the deterministic per-case magnitude diagnostic block.

    This is a sibling of ``candidate_judgment_feedback`` in consumer payloads,
    never a member of it: the legacy six-field record and its strict
    reload-equality validations stay byte-compatible. A false negative keeps
    its full-set magnitude miss in the aggregate metrics but carries no
    fabricated predicted class or ordinal distance here.
    """

    applicable = ground_truth.is_surge
    predicted = prediction.magnitude
    truth = ground_truth.magnitude
    correct = applicable and predicted is truth
    if not applicable:
        error_kind = "not_applicable"
    elif predicted is None:
        error_kind = "missed_surge"
    elif predicted is truth:
        error_kind = "correct"
    elif _MAGNITUDE_CLASS_ORDER.index(predicted) < _MAGNITUDE_CLASS_ORDER.index(
        truth
    ):
        error_kind = "underestimate"
    else:
        error_kind = "overestimate"
    ordinal_distance = None
    if applicable and predicted is not None:
        ordinal_distance = abs(
            _MAGNITUDE_CLASS_ORDER.index(predicted)
            - _MAGNITUDE_CLASS_ORDER.index(truth)
        )
    return {
        "magnitude_applicable": applicable,
        "predicted_magnitude": predicted.value if predicted else None,
        "true_magnitude": truth.value if truth else None,
        "magnitude_correct": correct,
        "error_kind": error_kind,
        "ordinal_distance": ordinal_distance,
    }


def jev_decision_feedback(
    prediction: BlindPrediction,
    ground_truth: GroundTruth,
) -> dict[str, Any] | None:
    """Project persisted Jev distributions onto realized labels for reflection.

    The values remain provider decision signals rather than calibrated
    live-market probabilities and never participate in fitness.
    """

    if not prediction.jev_decisions:
        return None
    by_question = {item.question_id: item for item in prediction.jev_decisions}
    judgment = by_question.get("candidate_judgment")
    magnitude = by_question.get("magnitude")
    expected_questions = (
        {"candidate_judgment", "magnitude"}
        if prediction.is_surge
        else {"candidate_judgment"}
    )
    if judgment is None or set(by_question) != expected_questions:
        raise ValidationError(
            "Jev BlindPrediction requires one direction decision and a magnitude "
            "decision only for positive judgments"
        )
    positive_probability = sum(
        judgment.probabilities.get(value, 0.0)
        for value in (
            CandidateJudgment.LIKELY.value,
            CandidateJudgment.POSSIBLE.value,
        )
    )
    negative_probability = sum(
        judgment.probabilities.get(value, 0.0)
        for value in (
            CandidateJudgment.UNLIKELY.value,
            CandidateJudgment.INSUFFICIENT_INFORMATION.value,
        )
    )
    true_binary_probability = (
        positive_probability if ground_truth.is_surge else negative_probability
    )
    true_magnitude = ground_truth.magnitude.value if ground_truth.magnitude else None
    binary_brier = (positive_probability - float(ground_truth.is_surge)) ** 2
    binary_log_loss = -math.log(max(true_binary_probability, 1e-12))
    binary_entropy = -sum(
        probability * math.log(probability)
        for probability in (positive_probability, negative_probability)
        if probability > 0
    ) / math.log(2)
    binary_correct = prediction.is_surge == ground_truth.is_surge
    if binary_correct and true_binary_probability < 0.60:
        binary_assessment = "correct_low_support"
    elif not binary_correct and true_binary_probability <= 0.20:
        binary_assessment = "high_confidence_error"
    elif binary_correct:
        binary_assessment = "correct_supported"
    else:
        binary_assessment = "error_uncertain"

    magnitude_calibration: dict[str, Any] | None = None
    if magnitude is not None and true_magnitude is not None:
        magnitude_probabilities = tuple(
            magnitude.probabilities.get(label.value, 0.0)
            for label in _MAGNITUDE_CLASS_ORDER
        )
        truth_index = next(
            index
            for index, label in enumerate(_MAGNITUDE_CLASS_ORDER)
            if label.value == true_magnitude
        )
        magnitude_brier = sum(
            (probability - float(index == truth_index)) ** 2
            for index, probability in enumerate(magnitude_probabilities)
        )
        cumulative_prediction = 0.0
        cumulative_truth = 0.0
        ranked_probability_score = 0.0
        for index in range(len(magnitude_probabilities) - 1):
            cumulative_prediction += magnitude_probabilities[index]
            cumulative_truth += float(truth_index <= index)
            ranked_probability_score += (
                cumulative_prediction - cumulative_truth
            ) ** 2
        true_probability = magnitude_probabilities[truth_index]
        magnitude_correct = magnitude.choice == true_magnitude
        if magnitude_correct and true_probability < 0.60:
            magnitude_assessment = "correct_low_support"
        elif not magnitude_correct and true_probability <= 0.20:
            magnitude_assessment = "high_confidence_class_error"
        elif magnitude_correct:
            magnitude_assessment = "correct_supported"
        else:
            magnitude_assessment = "class_error_uncertain"
        magnitude_calibration = {
            "brier_score": magnitude_brier,
            "log_loss": -math.log(max(true_probability, 1e-12)),
            "ranked_probability_score": ranked_probability_score,
            "normalized_entropy": (
                -sum(
                    probability * math.log(probability)
                    for probability in magnitude_probabilities
                    if probability > 0
                )
                / math.log(len(magnitude_probabilities))
            ),
            "top_class_probability": max(magnitude_probabilities),
            "assessment": magnitude_assessment,
        }

    return {
        "interpretation": (
            "provider decision signal only; probabilities are not calibrated "
            "live-market probabilities and confidence is distribution concentration, "
            "not correctness probability"
        ),
        "candidate_judgment": {
            **judgment.to_dict(),
            "positive_probability": positive_probability,
            "negative_probability": negative_probability,
            "probability_assigned_to_realized_binary": true_binary_probability,
            "calibration": {
                "brier_score": binary_brier,
                "log_loss": binary_log_loss,
                "normalized_entropy": binary_entropy,
                "binary_margin": abs(positive_probability - negative_probability),
                "assessment": binary_assessment,
            },
        },
        "magnitude": (
            {
                **magnitude.to_dict(),
                "requested": True,
                "true_magnitude": true_magnitude,
                "probability_assigned_to_true_magnitude": (
                    magnitude.probabilities.get(true_magnitude, 0.0)
                    if true_magnitude is not None
                    else None
                ),
                "calibration": magnitude_calibration,
            }
            if magnitude is not None
            else {
                "requested": False,
                "reason": "negative candidate_judgment",
                "true_magnitude": true_magnitude,
                "probability_assigned_to_true_magnitude": None,
            }
        ),
    }


def _legacy_jev_decision_feedback(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project current deterministic feedback to the pre-calibration schema."""

    legacy = deepcopy(dict(value))
    candidate = legacy.get("candidate_judgment")
    if isinstance(candidate, dict):
        candidate.pop("calibration", None)
    magnitude = legacy.get("magnitude")
    if isinstance(magnitude, dict):
        magnitude.pop("calibration", None)
    return legacy


def _jev_calibration_summary(
    feedback_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Aggregate deterministic Jev diagnostics without changing fitness."""

    rows = tuple(dict(row) for row in feedback_rows)
    if not rows:
        return None
    direction_blocks = [
        dict(row["candidate_judgment"])
        for row in rows
        if isinstance(row.get("candidate_judgment"), Mapping)
    ]
    direction_rows = [
        dict(block["calibration"])
        for block in direction_blocks
        if isinstance(block.get("calibration"), Mapping)
    ]
    if not direction_rows:
        return None
    magnitude_blocks = [
        dict(row["magnitude"])
        for row in rows
        if isinstance(row.get("magnitude"), Mapping)
        and row["magnitude"].get("requested") is True
    ]
    magnitude_rows = [
        dict(block["calibration"])
        for block in magnitude_blocks
        if isinstance(block.get("calibration"), Mapping)
    ]

    def mean(items: Iterable[float]) -> float | None:
        values = tuple(float(item) for item in items)
        return sum(values) / len(values) if values else None

    choice_counts = Counter(
        str(block["choice"])
        for block in magnitude_blocks
        if isinstance(block.get("choice"), str)
    )
    total_magnitude_choices = sum(choice_counts.values())
    return {
        "interpretation": (
            "descriptive provider-signal calibration only; excluded from fitness"
        ),
        "direction": {
            "case_count": len(direction_rows),
            "mean_brier_score": mean(
                row["brier_score"] for row in direction_rows
            ),
            "mean_log_loss": mean(row["log_loss"] for row in direction_rows),
            "mean_probability_assigned_to_realized_binary": mean(
                block["probability_assigned_to_realized_binary"]
                for block in direction_blocks
            ),
            "mean_provider_confidence": mean(
                block["confidence"] for block in direction_blocks
            ),
            "mean_normalized_entropy": mean(
                row["normalized_entropy"] for row in direction_rows
            ),
            "assessment_counts": dict(
                sorted(Counter(str(row["assessment"]) for row in direction_rows).items())
            ),
        },
        "magnitude": {
            "scored_case_count": len(magnitude_rows),
            "requested_case_count": len(magnitude_blocks),
            "mean_brier_score": mean(
                row["brier_score"] for row in magnitude_rows
            ),
            "mean_log_loss": mean(row["log_loss"] for row in magnitude_rows),
            "mean_probability_assigned_to_true_magnitude": mean(
                block["probability_assigned_to_true_magnitude"]
                for block in magnitude_blocks
                if block.get("probability_assigned_to_true_magnitude") is not None
            ),
            "mean_provider_confidence": mean(
                block["confidence"] for block in magnitude_blocks
            ),
            "mean_ranked_probability_score": mean(
                row["ranked_probability_score"] for row in magnitude_rows
            ),
            "mean_normalized_entropy": mean(
                row["normalized_entropy"] for row in magnitude_rows
            ),
            "choice_counts": dict(sorted(choice_counts.items())),
            "top_choice_share": (
                max(choice_counts.values()) / total_magnitude_choices
                if total_magnitude_choices
                else None
            ),
            "assessment_counts": dict(
                sorted(Counter(str(row["assessment"]) for row in magnitude_rows).items())
            ),
        },
    }


def research_jev_calibration_diagnostics(
    trajectories: Iterable[Any],
) -> dict[str, Any] | None:
    """Summarize Jev signal quality over research-completed trajectories."""

    rows = tuple(trajectories)
    completed = tuple(row for row in rows if not is_technical_exclusion_trajectory(row))
    feedback = tuple(
        value
        for row in completed
        for value in (jev_decision_feedback(row.prediction, row.ground_truth),)
        if value is not None
    )
    summary = _jev_calibration_summary(feedback)
    if summary is not None:
        summary["scored_case_count"] = len(rows)
        summary["research_completed_case_count"] = len(completed)
        summary["excluded_technical_case_count"] = len(rows) - len(completed)
    return summary


def _validated_magnitude_feedback_block(
    block: Mapping[str, Any],
    *,
    predicted_is_surge: bool,
    true_is_surge: bool,
) -> dict[str, Any]:
    """Validate a persisted magnitude block against its binary labels."""

    expected_keys = {
        "magnitude_applicable",
        "predicted_magnitude",
        "true_magnitude",
        "magnitude_correct",
        "error_kind",
        "ordinal_distance",
    }
    if set(block) != expected_keys:
        raise ValidationError("magnitude feedback fields are invalid")
    if block["magnitude_applicable"] is not true_is_surge:
        raise ValidationError("magnitude feedback applicability differs from truth")
    predicted = block["predicted_magnitude"]
    truth = block["true_magnitude"]
    if true_is_surge:
        if not isinstance(truth, str) or truth not in {
            magnitude.value for magnitude in _MAGNITUDE_CLASS_ORDER
        }:
            raise ValidationError("magnitude feedback true class is invalid")
    elif truth is not None:
        raise ValidationError("magnitude feedback true class must be null")
    if predicted_is_surge:
        if not isinstance(predicted, str) or predicted not in {
            magnitude.value for magnitude in _MAGNITUDE_CLASS_ORDER
        }:
            raise ValidationError("magnitude feedback predicted class is invalid")
    elif predicted is not None:
        raise ValidationError("magnitude feedback predicted class must be null")
    if not isinstance(block["magnitude_correct"], bool):
        raise ValidationError("magnitude feedback correctness must be boolean")
    distance = block["ordinal_distance"]
    if not true_is_surge:
        consistent = (
            block["error_kind"] == "not_applicable"
            and block["magnitude_correct"] is False
            and distance is None
        )
    elif predicted is None:
        consistent = (
            block["error_kind"] == "missed_surge"
            and block["magnitude_correct"] is False
            and distance is None
        )
    else:
        predicted_index = _MAGNITUDE_CLASS_ORDER.index(MagnitudeClass(predicted))
        truth_index = _MAGNITUDE_CLASS_ORDER.index(MagnitudeClass(truth))
        if predicted_index == truth_index:
            consistent = (
                block["error_kind"] == "correct"
                and block["magnitude_correct"] is True
                and distance == 0
            )
        else:
            expected_kind = (
                "underestimate" if predicted_index < truth_index else "overestimate"
            )
            consistent = (
                block["error_kind"] == expected_kind
                and block["magnitude_correct"] is False
                and distance == abs(predicted_index - truth_index)
            )
    if not consistent:
        raise ValidationError("magnitude feedback internals are inconsistent")
    return dict(block)


def binary_f1_fraction(metrics: PlanMetrics) -> Fraction:
    """Exact rational Binary F1 from confusion counts for tie-safe ordering.

    Floating storage of Binary F1 can render equal scores as 0.7999999999999999
    versus 0.8; selection comparisons therefore use the confusion counts
    directly. An all-negative sample (zero denominator) scores as zero,
    matching ``score_predictions``.
    """

    denominator = (
        2 * metrics.true_positive + metrics.false_positive + metrics.false_negative
    )
    if denominator == 0:
        return Fraction(0)
    return Fraction(2 * metrics.true_positive, denominator)


def _magnitude_diagnostics_from_classes(
    rows: Iterable[tuple[str, str | None]],
) -> dict[str, Any]:
    """Aggregate canonical diagnostics from true/predicted class pairs."""

    rows = tuple(rows)
    columns = ("predicted_negative",) + tuple(
        f"predicted_{magnitude.value}" for magnitude in _MAGNITUDE_CLASS_ORDER
    )
    matrix: dict[str, dict[str, int]] = {}
    truth_distribution: dict[str, int] = {}
    prediction_distribution: dict[str, int] = {}
    row_classes: tuple[str, ...] = ("non_surge",) + tuple(
        magnitude.value for magnitude in _MAGNITUDE_CLASS_ORDER
    )
    for true_class in row_classes:
        matrix[true_class] = {column: 0 for column in columns}
        truth_distribution[true_class] = 0
    for column in columns[1:]:
        prediction_distribution[column] = 0
    underestimate = 0
    overestimate = 0
    missed_surge = 0
    for truth_class, predicted_class in rows:
        matrix[truth_class][
            "predicted_negative" if predicted_class is None else f"predicted_{predicted_class}"
        ] += 1
        truth_distribution[truth_class] += 1
        if predicted_class is not None:
            prediction_distribution[f"predicted_{predicted_class}"] += 1
        if truth_class == "non_surge":
            continue
        if predicted_class is None:
            missed_surge += 1
        elif predicted_class != truth_class:
            predicted_index = _MAGNITUDE_CLASS_ORDER.index(
                MagnitudeClass(predicted_class)
            )
            truth_index = _MAGNITUDE_CLASS_ORDER.index(MagnitudeClass(truth_class))
            if predicted_index < truth_index:
                underestimate += 1
            else:
                overestimate += 1
    surge_count = sum(1 for truth_class, _predicted in rows if truth_class != "non_surge")
    magnitude_correct = sum(
        1
        for truth_class, predicted_class in rows
        if truth_class != "non_surge" and predicted_class == truth_class
    )
    tp_count = sum(
        1
        for truth_class, predicted_class in rows
        if truth_class != "non_surge" and predicted_class is not None
    )
    conditional_on_tp: float | None
    undefined_reason: str | None = None
    if tp_count == 0:
        conditional_on_tp = None
        undefined_reason = "no_true_positive_predictions"
    else:
        conditional_on_tp = magnitude_correct / tp_count
    return {
        "confusion_matrix": matrix,
        "per_class_support": {
            key: value for key, value in truth_distribution.items() if key != "non_surge"
        },
        "prediction_distribution": prediction_distribution,
        "truth_distribution": truth_distribution,
        "surge_case_count": surge_count,
        "magnitude_correct_count": magnitude_correct,
        "underestimate_count": underestimate,
        "overestimate_count": overestimate,
        "missed_surge_count": missed_surge,
        "conditional_accuracy_on_tp": conditional_on_tp,
        "tp_denominator": tp_count,
        "undefined_reason": undefined_reason,
    }


def magnitude_diagnostics(
    trajectories: Iterable[ExecutionTrajectory],
) -> dict[str, Any]:
    """Aggregate full score-denominator magnitude diagnostics for one batch."""

    return _magnitude_diagnostics_from_classes(
        (
            (
                row.ground_truth.magnitude.value
                if row.ground_truth.is_surge
                else "non_surge",
                row.prediction.magnitude.value
                if row.prediction.magnitude
                else None,
            )
            for row in trajectories
        )
    )


def is_technical_exclusion_trajectory(trajectory: Any) -> bool:
    """Return whether a scored trajectory is a framework-created abstention."""

    prediction = getattr(trajectory, "prediction", None)
    return str(getattr(prediction, "session_id", "")).startswith("exclusion_")


def technical_completion_diagnostics(
    trajectories: Iterable[ExecutionTrajectory],
) -> dict[str, Any]:
    """Separate research completion from the frozen score denominator."""

    rows = tuple(trajectories)
    excluded = tuple(row for row in rows if is_technical_exclusion_trajectory(row))
    completed = len(rows) - len(excluded)
    return {
        "scored_case_count": len(rows),
        "research_completed_case_count": completed,
        "technical_exclusion_count": len(excluded),
        "technical_completion_rate": (completed / len(rows) if rows else None),
        "failure_class_counts": (
            {"bounded_structured_correction_exhaustion": len(excluded)}
            if excluded
            else {}
        ),
        "scoring_effect_counts": {
            "false_negative": sum(row.ground_truth.is_surge for row in excluded),
            "technical_negative_abstention_not_true_negative": sum(
                not row.ground_truth.is_surge for row in excluded
            ),
        },
    }


def research_magnitude_diagnostics(
    trajectories: Iterable[ExecutionTrajectory],
) -> dict[str, Any]:
    """Build magnitude attribution only from cases with completed research."""

    rows = tuple(trajectories)
    completed = tuple(
        row for row in rows if not is_technical_exclusion_trajectory(row)
    )
    diagnostics = magnitude_diagnostics(completed)
    diagnostics.update(
        {
            "diagnostic_population": "research_completed",
            "scored_case_count": len(rows),
            "research_completed_case_count": len(completed),
            "excluded_technical_case_count": len(rows) - len(completed),
        }
    )
    return diagnostics


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
    reflection_items: tuple[ReflectionItem, ...] = ()
    source_identity: str | None = None
    source_snapshot: Mapping[str, Any] | None = None
    no_findings_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reflection_items", tuple(self.reflection_items))
        if self.source_identity is not None or self.source_snapshot is not None:
            object.__setattr__(self, "source_snapshot", validate_source_snapshot(self.source_identity, self.source_snapshot))
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
        value = {
            "prediction_outcome": {"correct": self.correct},
            "decision_drivers": list(self.decision_drivers),
            "why_prediction_failed": list(self.why_prediction_failed),
            "misleading_signals": list(self.misleading_signals),
            "ignored_evidence": list(self.ignored_evidence),
            "missing_information": list(self.missing_information),
            "plan_issues": list(self.plan_issues),
        }
        if self.reflection_items or self.no_findings_reason is not None:
            value["reflection_items"] = [item.to_dict() for item in self.reflection_items]
        if self.source_identity is not None:
            value["source_identity"] = self.source_identity
            value["source_snapshot"] = deepcopy(dict(self.source_snapshot or {}))
        if self.no_findings_reason is not None:
            value["no_findings_reason"] = self.no_findings_reason
        return value

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
            reflection_items=reflection_items_from_dict(data.get("reflection_items", ())),
            source_identity=data.get("source_identity"),
            source_snapshot=data.get("source_snapshot"),
            no_findings_reason=data.get("no_findings_reason"),
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
    jev_routing_decisions: tuple[JevDecisionSignal, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "selections", tuple(self.selections))
        decisions = tuple(self.jev_routing_decisions)
        if any(not isinstance(item, JevDecisionSignal) for item in decisions):
            decisions = tuple(
                item
                if isinstance(item, JevDecisionSignal)
                else JevDecisionSignal.from_dict(item)
                for item in decisions
            )
        if len({item.question_id for item in decisions}) != len(decisions):
            raise ValidationError("Signal round Jev question ids must be unique")
        object.__setattr__(self, "jev_routing_decisions", decisions)
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
        value = {
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
        if self.jev_routing_decisions:
            value["jev_routing_decisions"] = [
                item.to_dict() for item in self.jev_routing_decisions
            ]
        return value

    def to_model_context_dict(self) -> dict[str, Any]:
        """Return semantic Signal evidence without cache-variant usage metadata."""

        value = {
            "information_needs": list(self.information_needs),
            "selected_signals": list(self.selected_signals),
            "selections": [item.to_dict() for item in self.selections],
            "batch": {
                "results": [result.to_dict() for result in self.batch.results],
                "signal_calls": self.batch.signal_calls,
            },
        }
        if self.jev_routing_decisions:
            value["jev_routing_decisions"] = [
                item.to_dict() for item in self.jev_routing_decisions
            ]
        return value

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalRound":
        batch = dict(data["batch"])
        raw_jev_decisions = data.get("jev_routing_decisions", ())
        if not isinstance(raw_jev_decisions, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in raw_jev_decisions
        ):
            raise ValidationError("Signal round Jev decisions must be objects")
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
            jev_routing_decisions=tuple(
                JevDecisionSignal.from_dict(item)
                for item in raw_jev_decisions
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
    max_tokens: int = 256_000
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
    state_deltas: tuple[Mapping[str, Any], ...] = ()

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
        object.__setattr__(
            self, "state_deltas", tuple(dict(row) for row in self.state_deltas)
        )
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
            "state_deltas": [dict(row) for row in self.state_deltas],
            "stop_reason": self.stop_reason.value,
            "termination_trigger": (
                self.termination_trigger.value if self.termination_trigger else None
            ),
            "usage": self.usage.to_dict(),
        }
        decision_feedback = jev_decision_feedback(self.prediction, self.ground_truth)
        if decision_feedback is not None:
            value["jev_decision_feedback"] = decision_feedback
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
            state_deltas=tuple(
                dict(item) for item in data.get("state_deltas", ())
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
        serialized_jev_feedback = data.get("jev_decision_feedback")
        expected_jev_feedback = jev_decision_feedback(
            trajectory.prediction,
            trajectory.ground_truth,
        )
        if serialized_jev_feedback is not None:
            if not isinstance(serialized_jev_feedback, Mapping):
                raise ValidationError("jev_decision_feedback must be an object")
            if (
                dict(serialized_jev_feedback) != expected_jev_feedback
                and (
                    expected_jev_feedback is None
                    or dict(serialized_jev_feedback)
                    != _legacy_jev_decision_feedback(expected_jev_feedback)
                )
            ):
                raise ValidationError(
                    "jev_decision_feedback does not match prediction and truth"
                )
        return trajectory


@dataclass(frozen=True)
class CaseReflectionEvidence:
    """Anonymous original post-hoc reflection retained in round meta-info."""

    case_index: int
    stop_reason: RuntimeStopReason
    termination_trigger: RuntimeStopReason | None
    candidate_judgment_feedback: Mapping[str, Any] | None = None
    self_reflection: PredictionSelfReflection | None = None
    magnitude_feedback: Mapping[str, Any] | None = None
    jev_decision_feedback: Mapping[str, Any] | None = None
    technical_exclusion: Mapping[str, Any] | None = None

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
        if self.technical_exclusion is not None:
            technical = dict(self.technical_exclusion)
            if set(technical) != {
                "failure_class",
                "scoring_effect",
                "research_attribution_allowed",
            }:
                raise ValidationError(
                    "case reflection technical-exclusion fields are invalid"
                )
            if technical["failure_class"] != (
                "bounded_structured_correction_exhaustion"
            ) or technical["scoring_effect"] not in {
                "false_negative",
                "technical_negative_abstention_not_true_negative",
            } or technical["research_attribution_allowed"] is not False:
                raise ValidationError(
                    "case reflection technical-exclusion semantics are invalid"
                )
            if (
                self.candidate_judgment_feedback is not None
                or self.self_reflection is not None
                or self.magnitude_feedback is not None
                or self.jev_decision_feedback is not None
            ):
                raise ValidationError(
                    "technical exclusion cannot carry research-attribution feedback"
                )
            object.__setattr__(self, "technical_exclusion", technical)
            return
        if self.candidate_judgment_feedback is None or self.self_reflection is None:
            raise ValidationError(
                "research case reflection requires judgment feedback and reflection"
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
        if self.magnitude_feedback is not None:
            object.__setattr__(
                self,
                "magnitude_feedback",
                _validated_magnitude_feedback_block(
                    dict(self.magnitude_feedback),
                    predicted_is_surge=predicted_is_surge,
                    true_is_surge=true_is_surge,
                ),
            )
        if self.jev_decision_feedback is not None:
            jev_feedback = dict(self.jev_decision_feedback)
            if not isinstance(jev_feedback.get("candidate_judgment"), Mapping):
                raise ValidationError("case reflection Jev feedback is invalid")
            object.__setattr__(self, "jev_decision_feedback", jev_feedback)

    def to_dict(self) -> dict[str, Any]:
        if self.technical_exclusion is not None:
            return {
                "case_index": self.case_index,
                "stop_reason": self.stop_reason.value,
                "termination_trigger": (
                    self.termination_trigger.value
                    if self.termination_trigger
                    else None
                ),
                "technical_exclusion": dict(self.technical_exclusion),
            }
        value = {
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
        if self.magnitude_feedback is not None:
            value["magnitude_feedback"] = dict(self.magnitude_feedback)
        if self.jev_decision_feedback is not None:
            value["jev_decision_feedback"] = dict(self.jev_decision_feedback)
        return value

    @classmethod
    def from_trajectory(
        cls,
        trajectory: ExecutionTrajectory,
        *,
        case_index: int,
    ) -> "CaseReflectionEvidence":
        """Build the identity-free layer from one immutable trajectory."""

        if is_technical_exclusion_trajectory(trajectory):
            return cls(
                case_index=case_index,
                stop_reason=trajectory.stop_reason,
                termination_trigger=trajectory.termination_trigger,
                technical_exclusion={
                    "failure_class": (
                        "bounded_structured_correction_exhaustion"
                    ),
                    "scoring_effect": (
                        "false_negative"
                        if trajectory.ground_truth.is_surge
                        else "technical_negative_abstention_not_true_negative"
                    ),
                    "research_attribution_allowed": False,
                },
            )
        return cls(
            case_index=case_index,
            stop_reason=trajectory.stop_reason,
            termination_trigger=trajectory.termination_trigger,
            candidate_judgment_feedback=candidate_judgment_feedback(
                trajectory.prediction,
                trajectory.ground_truth,
            ),
            self_reflection=trajectory.self_reflection,
            magnitude_feedback=magnitude_feedback(
                trajectory.prediction,
                trajectory.ground_truth,
            ),
            jev_decision_feedback=jev_decision_feedback(
                trajectory.prediction,
                trajectory.ground_truth,
            ),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CaseReflectionEvidence":
        if "technical_exclusion" in data:
            required = {
                "case_index",
                "stop_reason",
                "termination_trigger",
                "technical_exclusion",
            }
            if set(data) != required or not isinstance(
                data["technical_exclusion"], Mapping
            ):
                raise ValidationError(
                    "technical case reflection evidence fields are invalid"
                )
            return cls(
                case_index=int(data["case_index"]),
                stop_reason=RuntimeStopReason(str(data["stop_reason"])),
                termination_trigger=(
                    RuntimeStopReason(str(data["termination_trigger"]))
                    if data["termination_trigger"] is not None
                    else None
                ),
                technical_exclusion=dict(data["technical_exclusion"]),
            )
        required = {
            "case_index",
            "stop_reason",
            "termination_trigger",
            "candidate_judgment_feedback",
            "self_reflection",
        }
        if not set(data) <= required | {
            "magnitude_feedback",
            "jev_decision_feedback",
        } or not required <= set(data):
            raise ValidationError("case reflection evidence fields are invalid")
        feedback = data["candidate_judgment_feedback"]
        reflection = data["self_reflection"]
        if not isinstance(feedback, Mapping) or not isinstance(reflection, Mapping):
            raise ValidationError("case reflection evidence objects are invalid")
        serialized_magnitude = data.get("magnitude_feedback")
        if serialized_magnitude is not None and not isinstance(
            serialized_magnitude, Mapping
        ):
            raise ValidationError("case reflection magnitude feedback is invalid")
        serialized_jev = data.get("jev_decision_feedback")
        if serialized_jev is not None and not isinstance(serialized_jev, Mapping):
            raise ValidationError("case reflection Jev feedback is invalid")
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
            magnitude_feedback=(
                dict(serialized_magnitude)
                if serialized_magnitude is not None
                else None
            ),
            jev_decision_feedback=(
                dict(serialized_jev) if serialized_jev is not None else None
            ),
        )

    @property
    def is_technical_exclusion(self) -> bool:
        """Recognize both current typed rows and legacy synthetic reflections."""

        if self.technical_exclusion is not None:
            return True
        return bool(
            self.self_reflection is not None
            and any(
                str(item).startswith("technical_case_exclusion:")
                for item in self.self_reflection.plan_issues
            )
        )

    def to_model_dict(self) -> dict[str, Any]:
        """Project legacy technical rows without synthetic research feedback."""

        if not self.is_technical_exclusion:
            return self.to_dict()
        if self.technical_exclusion is not None:
            return self.to_dict()
        scoring_effect = (
            "false_negative"
            if self.candidate_judgment_feedback is not None
            and self.candidate_judgment_feedback.get("true_binary_label") == "surge"
            else "technical_negative_abstention_not_true_negative"
        )
        return {
            "case_index": self.case_index,
            "stop_reason": self.stop_reason.value,
            "termination_trigger": (
                self.termination_trigger.value if self.termination_trigger else None
            ),
            "technical_exclusion": {
                "failure_class": "bounded_structured_correction_exhaustion",
                "scoring_effect": scoring_effect,
                "research_attribution_allowed": False,
            },
        }


def case_reflection_completion_diagnostics(
    reflections: Iterable[CaseReflectionEvidence],
) -> dict[str, Any]:
    """Summarize technical exclusions without turning them into judgments."""

    rows = tuple(reflections)
    excluded = tuple(row for row in rows if row.is_technical_exclusion)
    completed = len(rows) - len(excluded)
    effects = Counter(
        str(row.to_model_dict()["technical_exclusion"]["scoring_effect"])
        for row in excluded
    )
    return {
        "scored_case_count": len(rows),
        "research_completed_case_count": completed,
        "technical_exclusion_count": len(excluded),
        "technical_completion_rate": (completed / len(rows) if rows else None),
        "failure_class_counts": (
            {"bounded_structured_correction_exhaustion": len(excluded)}
            if excluded
            else {}
        ),
        "scoring_effect_counts": dict(sorted(effects.items())),
    }


def case_reflection_magnitude_diagnostics(
    reflections: Iterable[CaseReflectionEvidence],
) -> dict[str, Any] | None:
    """Rebuild attribution diagnostics from non-technical reflection blocks."""

    rows = tuple(reflections)
    completed = tuple(row for row in rows if not row.is_technical_exclusion)
    blocks = tuple(
        dict(row.magnitude_feedback)
        for row in completed
        if row.magnitude_feedback is not None
    )
    if len(blocks) != len(completed):
        return None
    diagnostics = _magnitude_diagnostics_from_classes(
        (
            (
                str(block["true_magnitude"])
                if block["magnitude_applicable"]
                else "non_surge",
                (
                    str(block["predicted_magnitude"])
                    if block["predicted_magnitude"] is not None
                    else None
                ),
            )
            for block in blocks
        )
    )
    diagnostics.update(
        {
            "diagnostic_population": "research_completed",
            "scored_case_count": len(rows),
            "research_completed_case_count": len(completed),
            "excluded_technical_case_count": len(rows) - len(completed),
        }
    )
    return diagnostics


def case_reflection_jev_calibration_diagnostics(
    reflections: Iterable[CaseReflectionEvidence],
) -> dict[str, Any] | None:
    """Rebuild Jev diagnostics from non-technical case-reflection evidence."""

    rows = tuple(reflections)
    completed = tuple(row for row in rows if not row.is_technical_exclusion)
    feedback = tuple(
        dict(row.jev_decision_feedback)
        for row in completed
        if row.jev_decision_feedback is not None
    )
    summary = _jev_calibration_summary(feedback)
    if summary is not None:
        summary["scored_case_count"] = len(rows)
        summary["research_completed_case_count"] = len(completed)
        summary["excluded_technical_case_count"] = len(rows) - len(completed)
    return summary


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
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.stage = str(stage)
        self.usage = usage
        self.details = dict(details or {})
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
    _set_evaluation_context(signal_agent, prediction_time)
    status_setter = getattr(controller, "set_signal_research_status", None)
    if callable(status_setter):
        status_setter(signal_registry.research_status)
    # Computation before interpretation: the anchor block is derived once
    # from complete PIT market documents and disclosed verbatim at every
    # stage; the state validator rejects numeric restatements of it.
    market_documents_for_anchor = tuple(
        document
        for resolution in basic_info_bundle.requests
        if set(resolution.request.source_types)
        & {"historical_price", "market_data", "price_daily", "prices"}
        for document in signal_executor.resolver.load_documents(
            resolution, as_of=prediction_time
        )
    )
    evaluation_anchor = _prediction_baseline_from_market_documents(
        market_documents_for_anchor, prediction_time
    )
    if evaluation_anchor.get("status") == "available":
        _set_evaluation_anchor(controller, evaluation_anchor)
    # Computation before interpretation at bootstrap: one closed-form price
    # shape card over the trailing window joins the anchor so orientation
    # numbers are computed, never narrated.
    bootstrap_computed: list[dict[str, Any]] = []
    try:
        from stock_opportunity_agent.research.compute_tools import compute_metric

        bootstrap_computed.append(
            compute_metric(
                "price_shape",
                {"window_days": 180},
                documents=market_documents_for_anchor,
                as_of=prediction_time,
            )
        )
    except ValidationError:
        bootstrap_computed = []
    _set_computed_metrics_if_capable = getattr(
        controller, "set_computed_metrics", None
    )
    if callable(_set_computed_metrics_if_capable):
        _set_computed_metrics_if_capable(bootstrap_computed)
    document_channel = _DocumentChannelProvider(
        signal_executor.raw_info_store,
        company_id=company_id,
        as_of=prediction_time,
        market_documents=market_documents_for_anchor,
        anchor=(evaluation_anchor if evaluation_anchor.get("status") == "available" else None),
    )
    _set_document_channel_if_capable = getattr(controller, "set_document_channel", None)
    if callable(_set_document_channel_if_capable):
        _set_document_channel_if_capable(document_channel)
    initial_step = controller.initialize(plan, basic_info)
    model_usage = _consume_model_step(model_usage, initial_step.usage, limits)
    initial_state = initial_step.value
    state = initial_state
    rounds: list[SignalRound] = []
    state_deltas: list[dict[str, Any]] = []
    signal_calls = 0
    stop_reason = RuntimeStopReason.FINALIZED
    termination_trigger: RuntimeStopReason | None = None
    terminal_reflection_attempted = False
    signal_fingerprints: dict[str, tuple[str, ...]] = {}
    prior_signal_results: dict[str, Mapping[str, Any]] = {}

    def current_final_context() -> dict[str, Any]:
        """Compose the same complete evidence closure for preflight and prediction."""

        return _assemble_final_context(
            plan=plan,
            company_id=company_id,
            additional_identity_aliases=tuple(str(item) for item in source_aliases),
            basic_info=basic_info,
            state=state,
            rounds=rounds,
            prediction_time=prediction_time,
            market_documents=market_documents_for_anchor,
            prediction_baseline=(
                evaluation_anchor
                if evaluation_anchor.get("status") == "available"
                else None
            ),
            state_deltas=tuple(state_deltas),
            computed_metrics=(*bootstrap_computed, *document_channel.computed_metrics),
            document_views=document_channel.document_views,
            signal_research_status=signal_registry.research_status,
        )

    def predictor_reservation() -> int:
        estimator = getattr(predictor, "estimate_prediction_tokens", None)
        if not callable(estimator):
            return 0
        required = estimator(current_final_context())
        if required is None:
            return 0
        if isinstance(required, bool) or not isinstance(required, int) or required < 0:
            raise ValidationError("Predictor reservation must be a nonnegative integer")
        return required

    while state.decision is ResearchDecision.CONTINUE:
        finalization_reserve = limits.finalization_token_reserve + predictor_reservation()
        if len(rounds) >= limits.max_signal_rounds:
            termination_trigger = RuntimeStopReason.MAX_SIGNAL_ROUNDS
            break
        if signal_calls >= limits.max_signal_calls:
            termination_trigger = RuntimeStopReason.MAX_SIGNAL_CALLS
            break
        if model_usage.llm_calls + 4 > limits.max_llm_calls:
            termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
            break
        if model_usage.tokens >= limits.max_tokens - finalization_reserve:
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
            limits.max_tokens - model_usage.tokens - finalization_reserve,
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
        raw_jev_routing_decisions = selection_step.metadata.get(
            "jev_routing_decisions", ()
        )
        if not isinstance(raw_jev_routing_decisions, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in raw_jev_routing_decisions
        ):
            raise ValidationError(
                "Signal Retrieval Agent Jev decisions must be objects"
            )
        jev_routing_decisions = tuple(
            JevDecisionSignal.from_dict(item)
            for item in raw_jev_routing_decisions
        )
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
        finalization_reserve = limits.finalization_token_reserve + predictor_reservation()
        _set_request_token_budget(
            signal_executor.llm_runner,
            limits.max_tokens - model_usage.tokens - finalization_reserve,
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
                jev_routing_decisions=jev_routing_decisions,
            )
        )
        prediction_reserve = predictor_reservation()
        finalization_reserve = limits.finalization_token_reserve + prediction_reserve
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
            limits.max_tokens - finalization_reserve
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
            reflection_budget -= finalization_reserve
        else:
            reflection_budget -= prediction_reserve
        _set_request_token_budget(controller, reflection_budget)
        terminal_reflection_attempted = reflection_termination_trigger is not None
        try:
            reflection_step = controller.reflect(plan, state, batch)
        except RuntimeBudgetExceeded as exc:
            model_usage = _consume_usage(model_usage, exc.usage, limits)
            termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
            if reflection_termination_trigger is not None:
                break
            reflection_termination_trigger = RuntimeStopReason.BUDGET_EXHAUSTED
            terminal_reflection_attempted = True
            _set_reflection_runtime_context(
                controller,
                selections=rounds[-1].selections,
                must_finalize=True,
                termination_trigger=reflection_termination_trigger,
            )
            _set_request_token_budget(
                controller, limits.max_tokens - model_usage.tokens - predictor_reservation()
            )
            try:
                reflection_step = controller.reflect(plan, state, batch)
            except RuntimeBudgetExceeded as terminal_error:
                model_usage = _consume_usage(model_usage, terminal_error.usage, limits)
                break
        model_usage = _consume_model_step(model_usage, reflection_step.usage, limits)
        reflected_state = reflection_step.value
        state_deltas.append(
            {
                "round": len(rounds),
                "delta": _research_state_delta(state, reflected_state),
            }
        )
        state = reflected_state
        if reflection_termination_trigger is not None:
            termination_trigger = reflection_termination_trigger
            if state.decision is ResearchDecision.CONTINUE:
                break
        if soft_budget_exhausted:
            stop_reason = (
                RuntimeStopReason.FINALIZED
                if state.decision is ResearchDecision.FINALIZE
                else RuntimeStopReason.BUDGET_EXHAUSTED
            )
            break
        if state.decision is ResearchDecision.FINALIZE:
            stop_reason = RuntimeStopReason.FINALIZED

    if (
        state.decision is ResearchDecision.CONTINUE
        and rounds
        and not terminal_reflection_attempted
        and termination_trigger in {
            RuntimeStopReason.BUDGET_EXHAUSTED,
            RuntimeStopReason.MAX_SIGNAL_ROUNDS,
            RuntimeStopReason.MAX_SIGNAL_CALLS,
        }
    ):
        _set_reflection_runtime_context(
            controller, selections=(), must_finalize=True,
            termination_trigger=termination_trigger,
        )
        _set_request_token_budget(
            controller, limits.max_tokens - model_usage.tokens - predictor_reservation()
        )
        try:
            closure_step = controller.reflect(plan, state, rounds[-1].batch)
        except RuntimeBudgetExceeded as exc:
            model_usage = _consume_usage(model_usage, exc.usage, limits)
        else:
            model_usage = _consume_model_step(model_usage, closure_step.usage, limits)
            state_deltas.append({"round": len(rounds), "delta": _research_state_delta(state, closure_step.value)})
            state = closure_step.value
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

    final_context = current_final_context()
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
    except RuntimeBudgetExceeded as exc:
        model_usage = _consume_usage(model_usage, exc.usage, limits)
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
        state_deltas=tuple(state_deltas),
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
    """Expose the fixed point-in-time horizon to capable role adapters."""

    setter = getattr(component, "set_evaluation_context", None)
    if callable(setter):
        setter(prediction_time)


def _set_evaluation_anchor(component: Any, anchor: Mapping[str, Any]) -> None:
    """Expose the computed evaluation anchor to capable role adapters."""

    setter = getattr(component, "set_evaluation_anchor", None)
    if callable(setter):
        setter(anchor)


class _DocumentChannelProvider:
    """Bounded point-in-time Raw Info catalog/fetch/compute channel for one case."""

    def __init__(
        self,
        store: Any,
        *,
        company_id: str,
        as_of: Any,
        market_documents: Iterable[RawInfoDocument] = (),
        anchor: Mapping[str, Any] | None = None,
    ) -> None:
        self.document_views: list[dict[str, Any]] = []
        self.computed_metrics: list[dict[str, Any]] = []
        self.store = store
        self.company_id = company_id
        self.as_of = as_of
        self.market_documents = tuple(market_documents)
        self.anchor = dict(anchor) if isinstance(anchor, Mapping) else None

    def catalog_view(self) -> dict[str, Any]:
        from stock_opportunity_agent.data.disclosure import document_catalog

        return document_catalog(
            self.store, company_id=self.company_id, as_of=self.as_of
        )

    def fetch(self, entries: Any) -> list[dict[str, Any]]:
        from stock_opportunity_agent.data.disclosure import fetch_entry

        cards = [
            fetch_entry(
                self.store,
                str(entry["document_id"]),
                as_of=self.as_of,
                section_id=(
                    str(entry["section_id"])
                    if entry.get("section_id") is not None
                    else None
                ),
            )
            for entry in entries
        ]
        self.document_views.extend(cards)
        return cards

    def compute(self, entries: Any) -> list[dict[str, Any]]:
        from stock_opportunity_agent.research.compute_tools import (
            compute_metric_requests,
        )

        cards = compute_metric_requests(
            entries,
            documents=self.market_documents,
            as_of=self.as_of,
            anchor=self.anchor,
        )
        self.computed_metrics.extend(cards)
        return cards


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
    aggregate role cannot use unrestricted expansion because ordinary brands
    such as ``News`` or ``Open`` are also protocol vocabulary. Keep only opaque
    ids, exact ticker-like aliases, and multi-token formal names here. Source rows
    use the narrower scoped inventory below when a case owner is known.
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


def _scoped_slow_identity_guard_inventory(
    cases: Iterable[EvolutionCase],
) -> tuple[str, ...]:
    """Add safe brand aliases only for source rows owned by known cases."""

    materialized = tuple(cases)
    guards = list(_slow_role_identity_guard_inventory(materialized))
    for alias in _identity_alias_variants(_case_identity_alias_inventory(materialized)):
        tokens = re.findall(r"[A-Za-z0-9]+", alias)
        if (
            len(tokens) == 1
            and sum(character.isalnum() for character in alias) >= 4
            and alias.casefold() not in _GENERIC_AGGREGATE_IDENTITY_WORDS
        ):
            guards.append(alias)
    return tuple(dict.fromkeys(guards))


def _is_strong_slow_identity_term(value: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9]+", value)
    return len(tokens) >= 2 or (
        len(tokens) == 1
        and value.isalnum()
        and value.isupper()
        and 2 <= len(value) <= 5
    )


def _prediction_baseline_from_market_documents(
    documents: Iterable[RawInfoDocument],
    prediction_time: datetime,
) -> dict[str, Any]:
    """Compute the fixed baseline from complete PIT sources, never display slices."""

    market_source_types = {
        "historical_price",
        "market_data",
        "price_daily",
        "prices",
    }
    bars: dict[str, float] = {}
    for document in documents:
        if document.source_type not in market_source_types:
            continue
        if document.available_at > prediction_time:
            raise ValidationError("Predictor baseline document is not point-in-time")
        for match in re.finditer(r"\{[^{}]*\}", document.content):
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
            "reason": "fewer_than_5_source_market_bars",
        }
    mean_adjusted_close = sum(close for _date, close in recent) / 5
    doubling_threshold = 2.0 * mean_adjusted_close
    recent_close_date, recent_close = recent[-1]
    return {
        "status": "available",
        "method": method,
        "mean_adjusted_close": mean_adjusted_close,
        "trading_dates": [bar_date for bar_date, _close in recent],
        # Deterministic derived anchors: the model consumes these verbatim
        # and never restates or recomputes baseline/threshold arithmetic.
        "doubling_threshold": doubling_threshold,
        "recent_close": recent_close,
        "recent_close_date": recent_close_date,
    }


def _research_state_delta(
    previous: ResearchState, current: ResearchState
) -> dict[str, Any]:
    """Deterministic per-round delta between two research states.

    Rows are compared by value on the text-array fields and by their stable
    ref identity (projection_id / signal tuple) on supporting evidence, so
    the assembled artifact records what each round added, removed, or
    changed instead of restating the whole frontier.
    """

    def text_delta(field_name: str) -> dict[str, list[str]]:
        old_values = list(getattr(previous, field_name))
        new_values = list(getattr(current, field_name))
        added = [row for row in new_values if row not in old_values]
        removed = [row for row in old_values if row not in new_values]
        return {"added": added, "removed": removed}

    def evidence_key(ref: Any) -> str:
        if isinstance(ref, str):
            return "text:" + ref
        if getattr(ref, "kind", None) == "signal":
            return "signal:{0}:{1}:{2}".format(
                ref.signal_ref, ref.evidence_group, ref.evidence_index
            )
        return "basic_info:{0}".format(getattr(ref, "projection_id", ""))

    old_evidence = {evidence_key(ref): ref for ref in previous.supporting_evidence}
    new_evidence = {evidence_key(ref): ref for ref in current.supporting_evidence}
    added_evidence = [
        {
            "key": key,
            "claim": (
                new_evidence[key]
                if isinstance(new_evidence[key], str)
                else getattr(new_evidence[key], "claim", "")
            ),
        }
        for key in sorted(set(new_evidence) - set(old_evidence))
    ]
    removed_evidence = sorted(set(old_evidence) - set(new_evidence))
    decision_changed = previous.decision is not current.decision
    delta: dict[str, Any] = {
        field_name: text_delta(field_name)
        for field_name in (
            "hypotheses",
            "current_beliefs",
            "contradictions",
            "resolved_questions",
            "open_questions",
            "next_information_needs",
        )
    }
    delta["supporting_evidence"] = {
        "added": added_evidence,
        "removed_keys": removed_evidence,
    }
    if decision_changed:
        delta["decision"] = {
            "from": previous.decision.value,
            "to": current.decision.value,
        }
    return delta


def _basic_info_projection_cards(
    basic_info: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Carry every already-disclosed bootstrap projection into the final view.

    Source disclosure is bounded upstream. Cutting these complete visible
    projections again would break the final Predictor's evidence closure.
    """

    cards: list[dict[str, Any]] = []
    for row in basic_info.get("requests", ()):
        if not isinstance(row, Mapping):
            continue
        request = row.get("request")
        for item in row.get("projections", ()):
            if not isinstance(item, Mapping):
                continue
            text = item.get("exact_text")
            if not isinstance(text, str) or not text.strip():
                continue
            cards.append({
                "request_id": request.get("request_id") if isinstance(request, Mapping) else None,
                "projection_id": item.get("projection_id"),
                **{key: item[key] for key in ("document_id", "available_at") if key in item},
                "exact_text": text,
                "truncated": False,
            })
    counts = {
        "available_projections": len(cards),
        "included_cards": len(cards),
        "deferred_projections": 0,
    }
    return cards, counts


def _assemble_final_context(
    *,
    plan: InformationPlan,
    company_id: str,
    additional_identity_aliases: tuple[str, ...],
    basic_info: Mapping[str, Any],
    state: ResearchState,
    rounds: Iterable[SignalRound],
    prediction_time: datetime,
    market_documents: Iterable[RawInfoDocument] = (),
    prediction_baseline: Mapping[str, Any] | None = None,
    state_deltas: Iterable[Mapping[str, Any]] = (),
    computed_metrics: Iterable[Mapping[str, Any]] = (),
    document_views: Iterable[Mapping[str, Any]] = (),
    signal_research_status: Mapping[str, Mapping[str, Any]] | None = None,
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
    for ref, result in model_signal_results.items():
        if ref in (signal_research_status or {}):
            result["research_status"] = dict(signal_research_status[ref])
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
                        **({"research_status": model_signal_results[result.ref]["research_status"]}
                           if "research_status" in model_signal_results[result.ref] else {}),
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

    projection_cards, projection_card_counts = _basic_info_projection_cards(
        basic_info
    )
    context = {
        "prediction_time": prediction_time.isoformat(),
        "context_contract": {
            "kind": "typed_append_only_assembly",
            "target_utf8_bytes": MAX_PREDICTOR_CONTEXT_UTF8_BYTES,
            "budget_enforcement": "exact_wire_remaining_case_tokens",
            "complete_trajectory_retained_locally": True,
            # The append order of typed blocks: content visible at any
            # stage stays present or explicitly dispositioned; numeric
            # decision inputs come only from the computed anchor block.
            "assembly_blocks": [
                {"block_type": "basic_info_cards", "provenance": "projection_id"},
                {"block_type": "computed_anchor", "provenance": "runtime_market_computation"},
                {"block_type": "computed_metrics", "provenance": "runtime_market_computation"},
                {"block_type": "document_channel", "provenance": "runtime_pit_disclosure"},
                {"block_type": "signal_results", "provenance": "signal_ref"},
                {"block_type": "cited_signal_evidence", "provenance": "signal_evidence_ref"},
                {"block_type": "state_evolution", "provenance": "per_round_delta"},
                {"block_type": "research_state", "provenance": "runtime_validated_state"},
                {"block_type": "analysis_prompt", "provenance": "plan"},
            ],
            "numeric_decision_inputs_permitted_only_in": [
                "prediction_baseline",
                "computed_metrics",
            ],
        },
        "basic_info": {
            "source_index": source_index,
            "data_gaps": data_gaps,
            "projection_cards": projection_cards,
            "projection_card_counts": projection_card_counts,
        },
        "prediction_baseline": (
            dict(prediction_baseline)
            if isinstance(prediction_baseline, Mapping)
            else _prediction_baseline_from_market_documents(
                market_documents, prediction_time
            )
        ),
        "computed_metrics": [dict(card) for card in computed_metrics],
        "document_channel": [dict(view) for view in document_views],
        "signal_rounds": signal_rounds,
        "cited_signal_evidence": cited_signal_evidence,
        "state_evolution": [dict(row) for row in state_deltas],
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
    masked_context["context_contract"]["presentation_target_exceeded"] = (
        context_bytes > MAX_PREDICTOR_CONTEXT_UTF8_BYTES
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
    technical_exclusion_case_ids: Iterable[str] = (),
) -> FitnessEligibility:
    """Assess completeness, finalization, evidence, and non-degenerate fitness.

    ``technical_exclusion_case_ids`` marks recorded abstain rows (bounded
    correction exhaustion): they must still be finalized predictions and still
    count in the confusion matrix, but their lack of source evidence reflects
    the recorded failure, not a research gap, and never blocks eligibility.
    """

    rows = tuple(trajectories)
    expected = tuple(str(item) for item in expected_case_ids)
    exclusions = frozenset(str(item) for item in technical_exclusion_case_ids)
    actual = tuple(row.case_id for row in rows)
    valid_rows = tuple(
        row for row in rows if _trajectory_is_fitness_finalized(row)
    )
    evidence_covered = sum(
        _trajectory_has_source_evidence(row)
        for row in rows
        if row.case_id not in exclusions
    )
    evidence_required = sum(
        1 for row in rows if row.case_id not in exclusions
    )
    predicted_positive = sum(row.prediction.is_surge for row in rows)
    true_positive = sum(
        row.prediction.is_surge and row.ground_truth.is_surge for row in rows
    )
    reasons: list[str] = []
    if len(expected) != len(rows) or set(expected) != set(actual):
        reasons.append("incomplete_case_set")
    if len(valid_rows) != len(rows):
        reasons.append("unfinalized_case")
    if evidence_covered != evidence_required:
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
    reflection_items: tuple[ReflectionItem, ...] = ()
    selected_reflection_refs: tuple[str, ...] = ()
    no_findings_reason: str | None = None

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
        value = {
            "successful_patterns": list(self.successful_patterns),
            "failed_patterns": list(self.failed_patterns),
            "repeated_failure_modes": list(self.repeated_failure_modes),
            "misleading_signals": list(self.misleading_signals),
            "missing_information_needs": list(self.missing_information_needs),
            "next_explorations": list(self.next_explorations),
        }
        if self.reflection_items or self.selected_reflection_refs or self.no_findings_reason is not None:
            value["reflection_items"] = [item.to_dict() for item in self.reflection_items]
            value["selected_reflection_refs"] = list(self.selected_reflection_refs)
        if self.no_findings_reason is not None:
            value["no_findings_reason"] = self.no_findings_reason
        return value

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
            reflection_items=reflection_items_from_dict(data.get("reflection_items", ())),
            selected_reflection_refs=tuple(data.get("selected_reflection_refs", ())),
            no_findings_reason=data.get("no_findings_reason"),
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
    magnitude_diagnostics: Mapping[str, Any] | None = None

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
        if self.magnitude_diagnostics is not None:
            diagnostics = dict(self.magnitude_diagnostics)
            missing = _MAGNITUDE_DIAGNOSTICS_REQUIRED_KEYS - set(diagnostics)
            if missing:
                raise ValidationError(
                    "Plan meta reflection magnitude diagnostics are invalid: "
                    + ", ".join(sorted(missing))
                )
            object.__setattr__(self, "magnitude_diagnostics", diagnostics)

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    def to_dict(self) -> dict[str, Any]:
        value = {
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
        if self.magnitude_diagnostics is not None:
            value["magnitude_diagnostics"] = dict(self.magnitude_diagnostics)
        return value

    def to_model_dict(self) -> dict[str, Any]:
        """Return an attribution-safe FIFO view, including for legacy rows."""

        value = self.to_dict()
        value["original_case_reflections"] = [
            item.to_model_dict() for item in self.original_case_reflections
        ]
        value["technical_completion"] = case_reflection_completion_diagnostics(
            self.original_case_reflections
        )
        diagnostics = case_reflection_magnitude_diagnostics(
            self.original_case_reflections
        )
        if diagnostics is None:
            value.pop("magnitude_diagnostics", None)
        else:
            value["magnitude_diagnostics"] = diagnostics
        calibration = case_reflection_jev_calibration_diagnostics(
            self.original_case_reflections
        )
        if calibration is not None:
            value["jev_calibration_diagnostics"] = calibration
        return value

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
            magnitude_diagnostics=research_magnitude_diagnostics(
                record.trajectories
            ),
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
        if not set(data) <= required | {"magnitude_diagnostics"} or not required <= set(
            data
        ):
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
            magnitude_diagnostics=(
                dict(data["magnitude_diagnostics"])
                if data.get("magnitude_diagnostics") is not None
                else None
            ),
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
    magnitude_metric_delta: dict[str, Any] | None = None
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
        magnitude_metric_delta = {
            "magnitude_accuracy": (
                child_metrics.magnitude_accuracy - parent_combined.magnitude_accuracy
            ),
            "magnitude_macro_f1": (
                child_metrics.magnitude_macro_f1
                - parent_combined.magnitude_macro_f1
            ),
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
        "magnitude_metric_delta": magnitude_metric_delta,
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
            key=lambda record: (
                -binary_f1_fraction(record.metrics),
                -record.metrics.magnitude_macro_f1,
                record.plan_id,
            ),
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
    reflection_items: tuple[ReflectionItem, ...] = ()
    selected_reflection_refs: tuple[str, ...] = ()
    no_findings_reason: str | None = None

    def __post_init__(self) -> None:
        # Negative ids are the reserved in-memory range for imported
        # committed-history reflections rebased below local numbering; they
        # are never persisted to per-round meta artifacts.
        if self.round_id == 0 or self.round_id < -1_000_000:
            raise ValidationError(
                "meta entry round_id must be a local positive round or a "
                "reserved imported-history id"
            )
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
        value = {
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
        if self.reflection_items or self.selected_reflection_refs or self.no_findings_reason is not None:
            value["reflection_items"] = [item.to_dict() for item in self.reflection_items]
            value["selected_reflection_refs"] = list(self.selected_reflection_refs)
        if self.no_findings_reason is not None:
            value["no_findings_reason"] = self.no_findings_reason
        return value

    def to_model_dict(self) -> dict[str, Any]:
        """Return the additive FIFO with attribution-safe Plan reflections."""

        value = self.to_dict()
        value["plan_reflections"] = [
            item.to_model_dict() for item in self.plan_reflections
        ]
        return value

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
        allowed = required | {"plan_reflections", "reflection_items", "selected_reflection_refs", "no_findings_reason"}
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
            reflection_items=reflection_items_from_dict(data.get("reflection_items", ())),
            selected_reflection_refs=tuple(data.get("selected_reflection_refs", ())),
            no_findings_reason=data.get("no_findings_reason"),
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
            reflection_items=self.reflection_items,
            selected_reflection_refs=self.selected_reflection_refs,
            no_findings_reason=self.no_findings_reason,
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

    def archive_view(self) -> tuple[Mapping[str, Any], ...]:
        """Serialize the complete retained FIFO for local audit and fingerprints."""
        return tuple(entry.to_model_dict() for entry in self._entries)

    def model_view(self, *, max_bytes: int = 48_000, max_items: int = 48) -> dict[str, Any]:
        """Return the bounded model working view; originals require indexed reads."""
        return self.brief_view(max_bytes=max_bytes, max_items=max_items)

    def reflection_index(self) -> ReflectionMemoryIndex:
        """Build an exact retrospective catalog without mutating archived entries."""
        return ReflectionMemoryIndex.from_entries(entry.to_model_dict() for entry in self._entries)

    def brief_view(self, *, max_bytes: int = 48_000, max_items: int = 48) -> dict[str, Any]:
        """Return a bounded working view, separate from the full archival view."""
        return self.reflection_index().brief_view(max_bytes=max_bytes, max_items=max_items)

    def read_refs(self, refs: Iterable[str], *, role: str, max_bytes: int = 16_000) -> dict[str, Any]:
        """Read complete approved source units through registered references only."""
        return self.reflection_index().read_refs(refs, role=role, max_bytes=max_bytes)


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
        "Select unchanged lower-level reflection items or add individually sourced "
        "horizontal facts, hypotheses and actions with concrete briefs, scope, "
        "limitations and counterreferences. Canonical outcome facts constrain "
        "success/failure claims; citations do not prove research interpretations. "
        "Do not rewrite preserved original case or vertical Plan layers."
    ),
    propose_plan=(
        "Propose one complete Information Plan S=(B,H_init,H_reflect,H_analyse). "
        "Use the quality-diverse parents and bounded sourced reflection briefs. "
        "Read approved original units by reference when needed, preserve limitations "
        "and counterexamples, make an attributable change, and never change labels, "
        "datasets, metrics, priors, runtime guards, or the stable Signal Registry."
    ),
    mine_signal=(
        "Develop reusable source-grounded measurements relevant to the supplied "
        "fixed research objective. Follow the current stage's output contract. "
        "Runtime owns case selection, stage-specific outcome visibility, evidence "
        "acquisition, staging, fixture execution, holdout validation and promotion. "
        "Do not claim to perform those runtime actions or invent candidate refs. "
        "Distinguish evidence limitations from business features. Support a "
        "candidate only with an observable contrast and a reason it could inform "
        "the fixed target; preserve counterevidence and honest empty results. "
        "Use an exact registered deterministic implementation or a grounded LLM "
        "skill when allowed by the supplied candidate contract."
    ),
    update_signal=(
        "Evaluate only the supplied exact stable Signal and its induction "
        "evidence under the fixed research objective. Return no_change, defer, "
        "or update according to the current role contract. An update contains "
        "the complete vNext candidate while changing only permitted paths and "
        "preserving frozen definition, execution identity and fixtures. "
        "Explain the correctable defect separately from outcome association; "
        "do not repair insufficient source evidence by guessing. Runtime owns "
        "target selection, execution, holdout tests, staging and promotion. "
        "Never claim those actions occurred or return invented staged refs."
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


def _signal_learning_events_from_record(
    record: PlanRecord,
) -> tuple[SignalLearningEvent, ...]:
    """Derive stable learning events from one authoritative Plan record."""

    learning_events: list[SignalLearningEvent] = []
    for trajectory in record.trajectories:
        for round_index, signal_round in enumerate(trajectory.signal_rounds):
            for result_index, result in enumerate(signal_round.batch.results):
                if result.execution_status not in {
                    SignalExecutionStatus.SUCCESS,
                    SignalExecutionStatus.DOMAIN_UNAVAILABLE,
                }:
                    continue
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
                        "Read the latest applicable annual or interim operating report "
                        "available before the prediction time for the business model, "
                        "risks, and segment economics."
                    ),
                    source_types=("filing",),
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
    structured_context = _company_facts_context(
        document,
        max_content_chars=max_content_chars,
        query=query,
    )
    if structured_context is None:
        excerpt, truncated = _query_relevant_excerpt(
            document,
            query=query,
            max_chars=max_content_chars,
        )
        projection = "normalized_query_window_v1"
    else:
        excerpt = ""
        truncated = bool(structured_context["partial"])
        projection = "sec_company_facts_context_v1"
    compact_metadata = {
        str(key): (value[:500] if isinstance(value, str) else value)
        for key, value in document.metadata.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
    view = {
        "document_id": document.document_id,
        "company_id": document.company_id,
        "source_type": document.source_type,
        "published_at": document.published_at.isoformat(),
        "available_at": document.available_at.isoformat(),
        "content_hash": document.content_hash,
        "content_length": len(document.content),
        "content_excerpt": excerpt,
        "content_truncated": truncated,
        "content_projection": projection,
        "metadata": compact_metadata,
        "metadata_keys": sorted(document.metadata),
    }
    if structured_context is not None:
        view["structured_context"] = structured_context
    return view


def _company_facts_context(
    document: RawInfoDocument,
    *,
    max_content_chars: int,
    query: str | None,
) -> dict[str, Any] | None:
    """Project supported SEC Company Facts with exact raw record spans."""

    try:
        payload = json.loads(document.content)
    except (json.JSONDecodeError, TypeError):
        return None
    facts = payload.get("facts") if isinstance(payload, Mapping) else None
    if not isinstance(facts, Mapping):
        return None

    leaf_spans: dict[str, list[tuple[int, int, str]]] = {}
    for match in re.finditer(r"\{[^{}]*\}", document.content):
        try:
            leaf = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(leaf, Mapping):
            leaf_spans.setdefault(_canonical_hash(dict(leaf)), []).append(
                (match.start(), match.end(), match.group(0))
            )
    leaf_span_cursors: dict[str, int] = {}

    query_terms = _h3_content_terms(query or "", exclude_generic=True)
    cutoff = document.available_at.date()
    candidates: list[tuple[tuple[Any, ...], dict[str, Any], bool]] = []
    for taxonomy, concepts in facts.items():
        if not isinstance(concepts, Mapping):
            continue
        for concept, definition in concepts.items():
            if not isinstance(definition, Mapping):
                continue
            label = str(definition.get("label", ""))
            units = definition.get("units")
            if not isinstance(units, Mapping):
                continue
            concept_terms = _h3_content_terms(
                f"{taxonomy} {concept} {label}", exclude_generic=True
            )
            for unit, raw_records in units.items():
                if not isinstance(raw_records, list):
                    continue
                matched_records: list[
                    tuple[str, str, Mapping[str, Any], dict[str, Any]]
                ] = []
                ambiguous = False
                for record in raw_records:
                    if not isinstance(record, Mapping):
                        continue
                    record_hash = _canonical_hash(dict(record))
                    occurrences = leaf_spans.get(record_hash, ())
                    occurrence_index = leaf_span_cursors.get(record_hash, 0)
                    if occurrence_index >= len(occurrences):
                        ambiguous = True
                        continue
                    start, end, exact_span = occurrences[occurrence_index]
                    leaf_span_cursors[record_hash] = occurrence_index + 1
                    filed = _optional_iso_date(record.get("filed"))
                    if filed is not None and filed > cutoff:
                        ambiguous = True
                        continue
                    period = str(record.get("end") or record.get("start") or "")
                    filed_key = str(record.get("filed") or "")
                    matched_records.append(
                        (
                            period,
                            filed_key,
                            record,
                            {
                                "exact_span": exact_span,
                                "start": start,
                                "end": end,
                            },
                        )
                    )
                matched_records.sort(
                    key=lambda item: (item[0], item[1], item[3]["start"]),
                    reverse=True,
                )
                distinct_records: list[
                    tuple[str, str, Mapping[str, Any], dict[str, Any]]
                ] = []
                seen_periods: set[str] = set()
                for matched in matched_records:
                    period, _filed, _record, record_view = matched
                    period_key = period or f"offset:{record_view['start']}"
                    if period_key in seen_periods:
                        continue
                    seen_periods.add(period_key)
                    distinct_records.append(matched)
                if not distinct_records:
                    continue
                latest = distinct_records[0]
                selected_records = [latest]
                for candidate_record in distinct_records[1:]:
                    if _company_fact_periods_comparable(
                        latest[2], candidate_record[2]
                    ):
                        selected_records.append(candidate_record)
                        break
                selected_periods = [item[3] for item in selected_records]
                entry = {
                    "taxonomy": str(taxonomy),
                    "concept": str(concept),
                    "label": label,
                    "unit": str(unit),
                    "records": selected_periods,
                }
                latest_period = matched_records[0][0]
                queryless_priority = _QUERYLESS_COMPANY_FACT_PRIORITY.get(
                    str(concept).casefold(), 0
                )
                score = (
                    (
                        len(query_terms.intersection(concept_terms)),
                        0,
                        latest_period,
                    )
                    if query_terms
                    else (
                        int(queryless_priority > 0),
                        latest_period,
                        queryless_priority,
                    )
                ) + (
                    str(taxonomy),
                    str(concept),
                    str(unit),
                )
                candidates.append(
                    (score, entry, ambiguous or len(matched_records) > 2)
                )
    if not candidates:
        return {
            "schema_version": "sec-company-facts-context-v1",
            "concepts": [],
            "omitted_concept_count": 0,
            "partial": True,
        }
    candidates.sort(key=lambda item: item[0], reverse=True)
    context: dict[str, Any] = {
        "schema_version": "sec-company-facts-context-v1",
        "concepts": [],
        "omitted_concept_count": len(candidates),
        "partial": True,
    }
    selected_partial = False
    for _score, entry, entry_partial in candidates:
        candidate = json.loads(json.dumps(context))
        candidate["concepts"].append(entry)
        candidate["omitted_concept_count"] -= 1
        candidate["partial"] = bool(
            candidate["omitted_concept_count"] or selected_partial or entry_partial
        )
        if len(
            json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
        ) > max_content_chars:
            continue
        context = candidate
        selected_partial = selected_partial or entry_partial
    context["partial"] = bool(
        context["omitted_concept_count"] or selected_partial
    )
    return context


def _company_fact_periods_comparable(
    current: Mapping[str, Any], prior: Mapping[str, Any]
) -> bool:
    """Return whether two SEC fact records form a meaningful time comparison."""

    current_start = _optional_iso_date(current.get("start"))
    prior_start = _optional_iso_date(prior.get("start"))
    if current_start is None or prior_start is None:
        return current_start is None and prior_start is None
    current_end = _optional_iso_date(current.get("end"))
    prior_end = _optional_iso_date(prior.get("end"))
    if current_end is not None and prior_end is not None:
        current_days = (current_end - current_start).days
        prior_days = (prior_end - prior_start).days
        if current_days >= 0 and prior_days >= 0:
            return abs(current_days - prior_days) <= 35
    current_fp = str(current.get("fp", "")).strip().casefold()
    prior_fp = str(prior.get("fp", "")).strip().casefold()
    return bool(current_fp and current_fp == prior_fp)


_QUERYLESS_COMPANY_FACT_CONCEPTS = (
    "OperatingIncomeLoss",
    "NetCashProvidedByUsedInOperatingActivities",
    "ResearchAndDevelopmentExpense",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "InventoryNet",
    "LongTermDebtCurrent",
    "LongTermDebtNoncurrent",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "GrossProfit",
    "NetIncomeLoss",
    "CashAndCashEquivalentsAtCarryingValue",
    "ShortTermInvestments",
    "AssetsCurrent",
    "LiabilitiesCurrent",
    "StockholdersEquity",
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
)
_QUERYLESS_COMPANY_FACT_PRIORITY = {
    concept.casefold(): len(_QUERYLESS_COMPANY_FACT_CONCEPTS) - index
    for index, concept in enumerate(_QUERYLESS_COMPANY_FACT_CONCEPTS)
}


def _optional_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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


def _exploration_case_pairs(
    cases: Iterable[EvolutionCase], *, cycle_id: int
) -> tuple[tuple[str, EvolutionCase], ...]:
    """Assign opaque refs after a cycle-bound ordering that excludes outcomes."""

    ordered = sorted(
        cases,
        key=lambda case: _canonical_hash(
            {
                "namespace": "exploration-presentation-v1",
                "cycle_id": cycle_id,
                "case_id": case.case_id,
                "company_id": case.company_id,
                "prediction_time": case.prediction_time.isoformat(),
            }
        ),
    )
    return tuple(
        (f"case-{index:03d}", case)
        for index, case in enumerate(ordered, start=1)
    )


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
    expand_aliases: bool = True,
    max_content_chars: int = 1_200,
) -> dict[str, Any]:
    """Return one bounded, masked model view with immutable source lineage."""

    view = _agent_raw_document_view(
        document, max_content_chars=max_content_chars, query=query
    )
    masked_excerpt = _mask_identity_values(
        view["content_excerpt"], aliases, expand_aliases=expand_aliases
    )
    masked_excerpt = _mask_target_affiliate_relations(masked_excerpt)
    model_view = {
        "document_ref": f"document-{index:02d}",
        "source_type": view["source_type"],
        "published_at": view["published_at"],
        "available_at": view["available_at"],
        "content_hash": view["content_hash"],
        "content_excerpt": masked_excerpt,
        "content_truncated": view["content_truncated"],
        "content_projection": view["content_projection"],
    }
    if "structured_context" in view:
        original_context = view["structured_context"]
        masked_context = _mask_identity_values(
            view["structured_context"],
            aliases,
            expand_aliases=expand_aliases,
        )
        masked_context = _mask_target_affiliate_relations(masked_context)
        redacted_records = 0
        for original_concept, masked_concept in zip(
            original_context.get("concepts", ()),
            masked_context.get("concepts", ()),
        ):
            original_records = original_concept.get("records", ())
            masked_records = masked_concept.get("records", ())
            retained = [
                masked_record
                for original_record, masked_record in zip(
                    original_records, masked_records
                )
                if masked_record.get("exact_span")
                == original_record.get("exact_span")
            ]
            redacted_records += len(masked_records) - len(retained)
            masked_concept["records"] = retained
        if redacted_records:
            masked_context["partial"] = True
            masked_context["redacted_record_count"] = redacted_records
            masked_context["concepts"] = [
                concept
                for concept in masked_context.get("concepts", ())
                if concept.get("records")
            ]
        model_view["structured_context"] = masked_context
    return model_view


def _mask_target_affiliate_relations(value: Any) -> Any:
    """Mask a named affiliate explicitly related to the already masked target."""

    if isinstance(value, str):
        affiliate_names = {
            match.group("name")
            for match in _TARGET_AFFILIATE_RELATION.finditer(value)
        }
        result = _TARGET_AFFILIATE_RELATION.sub(
            rf"{_MASKED_IDENTITY_VALUE}\g<relation>", value
        )
        for affiliate_name in sorted(affiliate_names, key=len, reverse=True):
            result = re.sub(
                rf"(?<![A-Za-z0-9]){re.escape(affiliate_name)}(?![A-Za-z0-9])",
                _MASKED_IDENTITY_VALUE,
                result,
            )
        return result
    if isinstance(value, list):
        return [_mask_target_affiliate_relations(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_target_affiliate_relations(item) for item in value)
    if isinstance(value, Mapping):
        return {
            key: _mask_target_affiliate_relations(item)
            for key, item in value.items()
        }
    return value


def _select_h3_model_evidence(
    documents: tuple[RawInfoDocument, ...],
    *,
    case: EvolutionCase,
    query: str | None,
    limit: int,
    aliases: tuple[str, ...] | None = None,
    expand_aliases: bool = True,
    prefer_source_diversity: bool = False,
    max_content_chars: int = 1_200,
) -> tuple[tuple[RawInfoDocument, ...], list[dict[str, Any]], dict[str, Any]]:
    """Select a bounded complementary H3 packet from an eligible ranked pool."""

    resolved_aliases = aliases or _discovery_identity_terms((case,))
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
                document, index=1, aliases=resolved_aliases, query=query,
                expand_aliases=expand_aliases,
                max_content_chars=max_content_chars,
            ),
        )
        for index, document in enumerate(eligible)
    ]
    selected: list[RawInfoDocument] = []
    evidence: list[dict[str, Any]] = []
    remaining = list(indexed_views)
    while remaining and len(selected) < limit:
        if prefer_source_diversity and query is None:
            selected_families = {
                _evidence_source_family(document.source_type)
                for document in selected
            }
            best = max(
                remaining,
                key=lambda item: (
                    int(
                        _evidence_source_family(item[1].source_type)
                        not in selected_families
                    ),
                    item[1].available_at,
                    item[1].published_at,
                    -item[0],
                ),
            )
        else:
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
        (_model_evidence_visible_text(item) for item in evidence), query=query
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


def _evidence_source_family(source_type: str) -> str:
    """Group exact Raw Info types only for queryless evidence diversity."""

    normalized = source_type.casefold()
    families = {
        "filing": {
            "10-k", "10-q", "20-f", "40-f", "6-k", "8-k",
            "filing", "filing_body", "sec_filing",
        },
        "transcript": {
            "alpha_vantage_earnings_raw_response", "earnings_call",
            "earnings_transcript", "transcript",
        },
        "news": {"company_news", "news"},
        "financial": {
            "company_facts", "financial_statements", "financials",
            "sec_company_facts", "sec_company_facts_raw_response",
        },
        "market": {
            "historical_price", "market_data", "price_daily", "prices",
        },
    }
    for family, values in families.items():
        if normalized in values:
            return family
    return normalized


def _h3_selection_score(
    evidence: tuple[dict[str, Any], ...],
    *,
    query: str | None,
    rank: int,
) -> tuple[int, int, int, int]:
    """Prefer sufficient, term-diverse, ordered evidence with stable rank ties."""

    coverage = _h3_text_query_coverage(
        (_model_evidence_visible_text(item) for item in evidence), query=query
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


def _model_evidence_visible_text(view: Mapping[str, Any]) -> str:
    """Return all model-visible evidence text used only for relevance scoring."""

    parts = [str(view.get("content_excerpt", ""))]
    structured = view.get("structured_context")
    if isinstance(structured, Mapping):
        for concept in structured.get("concepts", ()):
            if not isinstance(concept, Mapping):
                continue
            parts.extend(
                str(concept.get(key, ""))
                for key in ("taxonomy", "concept", "label", "unit")
            )
            for record in concept.get("records", ()):
                if isinstance(record, Mapping):
                    parts.append(str(record.get("exact_span", "")))
    return " ".join(parts)


_QUERYLESS_FILING_SUBSTANTIVE = re.compile(
    r"\b(?:business|operations?|results?|revenue|gross\s+profit|operating\s+income|"
    r"cash\s+flows?|liquidity|capital\s+resources?|debt|backlog|guidance|outlook|"
    r"risk\s+factors?|research\s+and\s+development|inventory)\b",
    re.IGNORECASE,
)
_QUERYLESS_FILING_BOILERPLATE = re.compile(
    r"\b(?:commission\s+file|exact\s+name\s+of\s+registrant|state\s+of\s+"
    r"incorporation|securities\s+registered|trading\s+symbol|annual\s+report\s+"
    r"pursuant|quarterly\s+report\s+pursuant|large\s+accelerated\s+filer)\b",
    re.IGNORECASE,
)



def _complete_evidence_window(text: str, start: int, max_chars: int) -> str:
    """Keep a literal bounded window without a partial final word or amount."""

    end = min(len(text), start + max_chars)
    if end < len(text) and end > start and not text[end].isspace():
        while end > start and not text[end - 1].isspace():
            end -= 1
    return text[start:end].rstrip()


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
    if not query_terms and document.content.lstrip().startswith(("{", "[")):
        # Keep original text/lineage; rank dated leaf records, not JSON headers.
        dated_records: list[tuple[str, int]] = []
        cutoff = document.available_at.date().isoformat()
        for record in re.finditer(r"\{[^{}]*\}", text_value):
            try:
                fields = json.loads(record.group(0))
            except json.JSONDecodeError:
                continue
            dates = []
            for value in fields.values():
                if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    continue
                try:
                    date.fromisoformat(value)
                except ValueError:
                    continue
                if value <= cutoff:
                    dates.append(value)
            if dates:
                dated_records.append((max(dates), record.start()))
        if dated_records:
            _latest, anchor = max(dated_records, key=lambda row: (row[0], -row[1]))
            return _complete_evidence_window(text_value, anchor, max_chars), True
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
    queryless_filing = (
        not query_terms and _evidence_source_family(document.source_type) == "filing"
    )
    if queryless_filing:
        anchors = [
            match.start()
            for match in _QUERYLESS_FILING_SUBSTANTIVE.finditer(text_value)
        ]
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
        window = _complete_evidence_window(text_value, start, max_chars)
        if queryless_filing:
            return (
                len(set(term.casefold() for term in
                        _QUERYLESS_FILING_SUBSTANTIVE.findall(window))),
                -len(_QUERYLESS_FILING_BOILERPLATE.findall(window)),
                len(re.findall(r"(?:\$|\b\d+(?:\.\d+)?%?\b)", window)),
                -start,
            )
        coverage = _h3_text_query_coverage(
            (window,), query=query
        )
        return (
            int(coverage["sufficient"]),
            len(coverage["matched_terms"]),
            len(coverage["matched_ordered_pairs"]),
            -start,
        )

    start = max(adjusted_starts, key=score)
    return _complete_evidence_window(text_value, start, max_chars), True


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
    *, expand_aliases: bool = True,
) -> tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...]:
    """Reuse bounded immutable matchers without expanding strict inventories."""

    return _cached_identity_matchers(tuple(aliases), expand_aliases)


@lru_cache(maxsize=8)
def _cached_identity_matchers(
    aliases: tuple[str, ...], expand_aliases: bool,
) -> tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...]:
    """Compile one exact inventory/mode pair without unbounded retention."""

    compiled: list[tuple[str, re.Pattern[str], re.Pattern[str]]] = []
    resolved = _identity_alias_variants(aliases) if expand_aliases else aliases
    derived_names = {
        variant.casefold()
        for name in aliases if expand_aliases and len(re.findall(r"[A-Za-z0-9]+", name)) >= 2
        for variant in _identity_alias_variants((name,))
        if variant.casefold() != name.casefold()
        and variant.casefold() not in _GENERIC_IDENTITY_LEADING_WORDS
    }
    for alias in resolved:
        escaped = _identity_alias_pattern(alias)
        pattern = (
            rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
            if alias[0].isalnum() and alias[-1].isalnum()
            else escaped
        )
        prose_flags = (
            0
            if alias.isalnum() and alias.isupper() and len(alias) <= 5
            and alias.casefold() not in derived_names
            else re.IGNORECASE
        )
        url_pattern = (
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"
            if alias.isalnum() and alias.isupper() and len(alias) <= 2
            else pattern
        )
        compiled.append(
            (
                alias,
                re.compile(pattern, flags=prose_flags),
                re.compile(url_pattern, flags=re.IGNORECASE),
            )
        )
    return tuple(compiled)


def _identity_alias_pattern(alias: str) -> str:
    """Allow common filing punctuation variants without broad fuzzy matching."""

    ticker_like = alias.isalnum() and alias.isupper() and len(alias) <= 5
    if ticker_like:
        if len(alias) <= 2:
            return (
                rf"(?:\${re.escape(alias)}(?![A-Za-z0-9])|"
                rf"(?i:\b(?:ticker|symbol|nasdaq|nyse|amex)\b)"
                rf"\s*(?::|=)?\s*{re.escape(alias)}(?![A-Za-z0-9]))"
            )
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


def _opaque_slow_case_ref(value: str) -> str:
    """Preserve retrospective case equality without exposing case identity."""

    return "anon-case-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _project_slow_case_refs(value: Any) -> Any:
    """Pseudonymize typed retrospective case fields before masking prose."""

    if isinstance(value, Mapping):
        return {
            key: (
                _opaque_slow_case_ref(child)
                if key == "case_id" and isinstance(child, str)
                else [_opaque_slow_case_ref(item) for item in child]
                if key == "case_ids" and isinstance(child, (list, tuple))
                and all(isinstance(item, str) for item in child)
                else _project_slow_case_refs(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_project_slow_case_refs(child) for child in value]
    return value


def _mask_identity_values(
    value: Any, aliases: Iterable[str], *, expand_aliases: bool = True,
) -> Any:
    matchers = _compiled_identity_aliases(aliases, expand_aliases=expand_aliases)

    def mask_url(match: re.Match[str]) -> str:
        result = match.group(0)
        for _alias, _prose_matcher, url_matcher in matchers:
            result = url_matcher.sub(_IDENTITY_MASK_SENTINEL, result)
        return result

    @lru_cache(maxsize=4096)
    def mask_text(item: str) -> str:
        result = item
        for _alias, prose_matcher, _url_matcher in matchers:
            result = prose_matcher.sub(_IDENTITY_MASK_SENTINEL, result)
        result = _URL_VALUE.sub(mask_url, result)
        return result.replace(_IDENTITY_MASK_SENTINEL, _MASKED_IDENTITY_VALUE)

    def mask(item: Any) -> Any:
        if isinstance(item, str):
            return mask_text(item)
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


def _assert_identity_values_masked(
    value: Any, aliases: Iterable[str], *, expand_aliases: bool = True,
) -> None:
    """Fail closed if the assembled Predictor context still names its target."""

    matchers = _compiled_identity_aliases(aliases, expand_aliases=expand_aliases)

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


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    """Reuse a crash-staged JSON object only when its canonical value is exact."""

    expected = json.loads(json.dumps(dict(value), sort_keys=True))
    if path.exists():
        actual = _read_json(path)
        if actual != expected:
            raise ValidationError(f"conflicting staged evolution artifact: {path}")
        return
    _atomic_write_json(path, expected)
