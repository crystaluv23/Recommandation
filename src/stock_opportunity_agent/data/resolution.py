"""Local-first point-in-time resolution against the append-only Raw Info oracle."""

from __future__ import annotations

from stock_opportunity_agent.data.filing_orientation import exact_document_form, operating_order, OPERATING_REQUEST_ID

import hashlib
import json
import math
import threading
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.markup import nonvisible_html_ranges
from stock_opportunity_agent.data.point_in_time import utc_day_of_instant
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.sources.state import (
    DataQuotaDeferred,
    jsonl_append_lock,
)
from stock_opportunity_agent.models import ValidationError


MAX_BASIC_INFO_REQUESTS = 8
MAX_DOCUMENTS_PER_REQUEST = 10
CONTEXT_CHUNK_CHARS = 2_000
CONTEXT_CHUNK_OVERLAP = 200
MAX_BASIC_INFO_CONTEXT_CHARS = 48_000
DATA_ACQUISITION_WILDCARD = "*"
_TOKEN = re.compile(r"[A-Za-z0-9]+")
_HTML_TAG = re.compile(r"<[^>]*>", re.DOTALL)
_MARKUP_SOURCE_TYPES = frozenset(
    {
        "10-k",
        "10-q",
        "8-k",
        "20-f",
        "40-f",
        "6-k",
        "filing",
        "filing_body",
        "sec_filing",
    }
)
_EXACT_SEC_FORMS = frozenset({"10-k", "10-q", "8-k", "20-f", "40-f", "6-k"})
_GENERIC_FILING_TYPES = frozenset({"filing", "sec_filing", "filing_body"})
_CANONICAL_CIK_COMPANY_ID = re.compile(r"^cik_(\d{10})$")
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
        "international",
        "national",
        "new",
        "north",
        "the",
        "united",
        "universal",
    }
)


class DataGapReason(str, Enum):
    """Why a point-in-time information request could not be satisfied."""

    ADAPTER_MISSING = "adapter_missing"
    MISSING_IDENTIFIER = "missing_identifier"
    EXTERNAL_NOT_AUTHORIZED = "external_not_authorized"
    HISTORICAL_DATA_UNAVAILABLE = "historical_data_unavailable"
    QUOTA_DEFERRED = "quota_deferred"
    PROVIDER_NO_DATA = "provider_no_data"
    PROVIDER_ERROR = "provider_error"
    MATERIALIZATION_FAILED = "materialization_failed"
    NO_MATCHING_DOCUMENTS = "no_matching_documents"
    REQUIRED_COVERAGE_INCOMPLETE = "required_coverage_incomplete"


@dataclass(frozen=True)
class RawInfoRequest:
    """One auditable source-retrieval need; ``as_of`` is supplied by the case."""

    request_id: str
    description: str
    source_types: tuple[str, ...]
    lookback_days: int | None = None
    max_documents: int = 5
    query: str | None = None
    required_source_groups: tuple[tuple[str, ...], ...] = ()
    minimum_distinct_periods: int | None = None
    minimum_period_span_days: int | None = None
    minimum_observations: int | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.description.strip():
            raise ValidationError("raw info request requires id and description")
        if not self.source_types or any(not item.strip() for item in self.source_types):
            raise ValidationError("raw info request requires source_types")
        if len(set(self.source_types)) != len(self.source_types):
            raise ValidationError("raw info request source_types must be unique")
        if self.lookback_days is not None and self.lookback_days < 1:
            raise ValidationError("raw info lookback_days must be positive")
        if not 1 <= self.max_documents <= MAX_DOCUMENTS_PER_REQUEST:
            raise ValidationError("raw info max_documents must be between 1 and 10")
        if self.query is not None and not self.query.strip():
            raise ValidationError("raw info query must be omitted or non-empty")
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
                "raw info required source groups must be non-empty and unique"
            )
        if len(set(groups)) != len(groups):
            raise ValidationError("raw info required source groups must be unique")
        if len(groups) > self.max_documents:
            raise ValidationError(
                "raw info required source groups exceed document limit"
            )
        if any(
            not source_types_compatible((item,), self.source_types)
            for group in groups
            for item in group
        ):
            raise ValidationError("raw info required source group is outside source_types")
        for name in (
            "minimum_distinct_periods",
            "minimum_period_span_days",
            "minimum_observations",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 1):
                raise ValidationError(f"raw info {name} must be a positive integer")
        object.__setattr__(self, "source_types", tuple(self.source_types))
        object.__setattr__(self, "query", self.query.strip() if self.query else None)
        object.__setattr__(self, "required_source_groups", groups)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "request_id": self.request_id,
            "description": self.description,
            "source_types": list(self.source_types),
            "max_documents": self.max_documents,
        }
        if self.lookback_days is not None:
            value["lookback_days"] = self.lookback_days
        if self.query is not None:
            value["query"] = self.query
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
    def from_dict(cls, data: Mapping[str, Any]) -> "RawInfoRequest":
        return cls(
            request_id=str(data["request_id"]),
            description=str(data["description"]),
            source_types=tuple(str(item) for item in data.get("source_types", ())),
            lookback_days=(
                int(data["lookback_days"])
                if data.get("lookback_days") is not None
                else None
            ),
            max_documents=int(data.get("max_documents", 5)),
            query=(str(data["query"]) if data.get("query") is not None else None),
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


DocumentSelector = Callable[
    [tuple[RawInfoDocument, ...], RawInfoRequest], Iterable[RawInfoDocument]
]


class _DocumentSelectionError(ValidationError):
    """A local selection contract failure, never a provider/acquisition error."""


@dataclass(frozen=True)
class RawInfoDocumentRef:
    """Immutable Raw Info lineage without repeating source content."""

    document_id: str
    content_hash: str
    available_at: datetime

    @classmethod
    def from_document(cls, document: RawInfoDocument) -> "RawInfoDocumentRef":
        return cls(document.document_id, document.content_hash, document.available_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "content_hash": self.content_hash,
            "available_at": self.available_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawInfoDocumentRef":
        return cls(
            document_id=str(data["document_id"]),
            content_hash=str(data["content_hash"]),
            available_at=datetime.fromisoformat(str(data["available_at"])),
        )


@dataclass(frozen=True)
class RawInfoContextSpan:
    """One literal source substring selected for Basic Info context."""

    document_id: str
    content_hash: str
    available_at: datetime
    start: int
    end: int
    exact_text: str
    # Readable-character count used for budget accounting. Markup windows
    # carry raw exact_text padded with tags; visibility budgets bill this
    # normalized size instead. None means exact_text is already readable.
    visible_chars: int | None = None

    def __post_init__(self) -> None:
        if self.visible_chars is not None and (
            type(self.visible_chars) is not int
            or not 1 <= self.visible_chars <= len(self.exact_text)
        ):
            raise ValidationError(
                "raw info context span visible characters must be a positive "
                "count within the literal span"
            )

    @property
    def billable_chars(self) -> int:
        """Characters charged against visibility budgets for this span."""

        return self.visible_chars if self.visible_chars is not None else len(
            self.exact_text
        )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "document_id": self.document_id,
            "content_hash": self.content_hash,
            "available_at": self.available_at.isoformat(),
            "start": self.start,
            "end": self.end,
            "exact_text": self.exact_text,
        }
        if self.visible_chars is not None:
            value["visible_chars"] = self.visible_chars
        return value

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawInfoContextSpan":
        return cls(
            document_id=str(data["document_id"]),
            content_hash=str(data["content_hash"]),
            available_at=datetime.fromisoformat(str(data["available_at"])),
            start=int(data["start"]),
            end=int(data["end"]),
            exact_text=str(data["exact_text"]),
            visible_chars=(
                int(data["visible_chars"])
                if data.get("visible_chars") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class DataGap:
    """Structured, trajectory-safe unresolved data need."""

    request_id: str
    reason: DataGapReason
    message: str
    source_types: tuple[str, ...] = ()
    provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "reason": self.reason.value,
            "message": self.message,
            "source_types": list(self.source_types),
            "provider": self.provider,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DataGap":
        return cls(
            request_id=str(data["request_id"]),
            reason=DataGapReason(str(data["reason"])),
            message=str(data.get("message", "")),
            source_types=tuple(str(item) for item in data.get("source_types", ())),
            provider=(str(data["provider"]) if data.get("provider") else None),
        )


def extract_unresolved_signal_needs(
    sources: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Extract stable, provenance-complete unresolved needs from admitted sources."""

    grouped: dict[str, dict[str, Any]] = {}
    for source in sources:
        trajectory = source.get("trajectory")
        if not isinstance(trajectory, Mapping):
            raise ValidationError("signal-need source requires a trajectory object")
        source_ref = str(source.get("source_ref", "")).strip()
        source_round = source.get("source_round")
        if (
            not source_ref
            or type(source_round) is not int
            or source_round < 1
        ):
            raise ValidationError(
                "signal-need source requires source_ref and positive source_round"
            )
        source_fingerprint = str(source.get("source_fingerprint", "")).strip()
        if not source_fingerprint:
            source_fingerprint = hashlib.sha256(
                json.dumps(
                    trajectory,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        final_state = trajectory.get("final_state")
        if not isinstance(final_state, Mapping):
            raise ValidationError("signal-need trajectory requires final_state")
        raw_needs = final_state.get("next_information_needs", ())
        if not isinstance(raw_needs, (list, tuple)):
            raise ValidationError(
                "signal-need trajectory next_information_needs must be an array"
            )
        stop_reason = str(trajectory.get("stop_reason", "")).strip()
        if not stop_reason:
            raise ValidationError("signal-need trajectory requires stop_reason")
        for raw_need in raw_needs:
            original_need = " ".join(str(raw_need).split())
            normalized = original_need.casefold()
            if not original_need:
                continue
            need_ref = "need-" + hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest()[:24]
            item = grouped.setdefault(
                need_ref,
                {
                    "kind": "unmatched_signal_need",
                    "need_ref": need_ref,
                    "need": original_need,
                    "sources": [],
                },
            )
            item["sources"].append(
                {
                    "source_ref": source_ref,
                    "source_round": source_round,
                    "source_fingerprint": source_fingerprint,
                    "original_need": original_need,
                    "stop_reason": stop_reason,
                }
            )
    result: list[dict[str, Any]] = []
    for need_ref in sorted(grouped):
        item = grouped[need_ref]
        sources_by_identity = {
            (
                str(source["source_ref"]),
                int(source["source_round"]),
                str(source["source_fingerprint"]),
                str(source["original_need"]),
                str(source["stop_reason"]),
            ): source
            for source in item["sources"]
        }
        retained_sources = [
            sources_by_identity[key] for key in sorted(sources_by_identity)
        ]
        result.append(
            {
                **item,
                "sources": retained_sources,
                "source_rounds": sorted(
                    {int(source["source_round"]) for source in retained_sources}
                ),
                "source_fingerprints": sorted(
                    {
                        str(source["source_fingerprint"])
                        for source in retained_sources
                    }
                ),
                "stop_reasons": sorted(
                    {str(source["stop_reason"]) for source in retained_sources}
                ),
                "occurrences": len(retained_sources),
                "source_count": len(
                    {str(source["source_ref"]) for source in retained_sources}
                ),
                "status": "open",
            }
        )
    return tuple(result)


def aggregate_capability_gaps(
    trajectories: Iterable[Mapping[str, Any]],
    *,
    available_source_types: Iterable[str] = (),
    signal_need_items: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a deterministic data/Signal backlog from durable diagnostics."""

    del available_source_types
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    actual_resolutions: set[tuple[str, str]] = set()
    technical_failures: list[dict[str, Any]] = []
    for trajectory in trajectories:
        case_id = str(trajectory.get("case_id", "unknown"))
        resolutions = list(
            dict(trajectory.get("basic_info_bundle", {})).get("requests", ())
        )
        for signal_round in trajectory.get("signal_rounds", ()):
            batch = dict(signal_round).get("batch", {})
            resolutions.extend(dict(batch).get("resolutions", ()))
            for result in dict(batch).get("results", ()):
                if not isinstance(result, Mapping):
                    continue
                execution = result.get("execution")
                status = (
                    str(execution.get("status", ""))
                    if isinstance(execution, Mapping)
                    else ""
                )
                if status and status not in {"success", "domain_unavailable"}:
                    technical_failures.append(
                        {
                            "case_id": case_id,
                            "signal_ref": (
                                f"{result.get('signal_id')}:v{result.get('version')}"
                            ),
                            "status": status,
                            "error_code": execution.get("error_code"),
                            "error_message": execution.get("error_message"),
                        }
                    )
        for resolution in resolutions:
            if not isinstance(resolution, Mapping):
                continue
            request = resolution.get("request")
            request_id = (
                str(request.get("request_id", ""))
                if isinstance(request, Mapping)
                else ""
            )
            if resolution.get("status") == "resolved" and request_id:
                actual_resolutions.add((case_id, request_id))
            gap = resolution.get("data_gap")
            if not isinstance(gap, Mapping):
                continue
            source_types = tuple(sorted(str(item) for item in gap.get("source_types", ())))
            key = (
                str(gap.get("reason", "")),
                str(gap.get("provider") or ""),
                ",".join(source_types),
                str(gap.get("request_id", "")),
            )
            item = grouped.setdefault(
                key,
                {
                    "reason": key[0],
                    "provider": key[1] or None,
                    "source_types": list(source_types),
                    "request_id": key[3],
                    "signal_ref": (
                        key[3].removeprefix("signal:")
                        if key[3].startswith("signal:")
                        else None
                    ),
                    "basic_info_request_id": (
                        None if key[3].startswith("signal:") else key[3]
                    ),
                    "affected_case_ids": set(),
                    "occurrences": 0,
                },
            )
            item["affected_case_ids"].add(case_id)
            item["occurrences"] += 1
    items: list[dict[str, Any]] = []
    for key in sorted(grouped):
        item = grouped[key]
        resolved = all(
            (case_id, item["request_id"]) in actual_resolutions
            for case_id in item["affected_case_ids"]
        )
        items.append(
            {
                **item,
                "affected_case_ids": sorted(item["affected_case_ids"]),
                "status": "resolved" if resolved else "open",
            }
        )
    needs: list[dict[str, Any]] = []
    seen_needs: set[str] = set()
    for raw_item in sorted(
        (dict(item) for item in signal_need_items),
        key=lambda item: str(item.get("need", "")).casefold(),
    ):
        need = " ".join(str(raw_item.get("need", "")).split())
        normalized = str(raw_item.get("need_ref") or need.casefold())
        if not need or normalized in seen_needs:
            continue
        seen_needs.add(normalized)
        occurrences = int(raw_item.get("occurrences", 0))
        source_count = int(raw_item.get("source_count", 0))
        if occurrences < 1 or source_count < 1:
            raise ValidationError("Signal-need backlog counts must be positive")
        if raw_item.get("need_ref"):
            needs.append({**raw_item, "need": need, "status": "open"})
        else:
            need_ref = "need-" + hashlib.sha256(
                need.casefold().encode("utf-8")
            ).hexdigest()[:24]
            needs.append(
                {
                    "kind": "unmatched_signal_need",
                    "need_ref": need_ref,
                    "need": need,
                    "sources": [],
                    "source_rounds": [],
                    "source_fingerprints": [],
                    "stop_reasons": ["no_signal_match"],
                    "occurrences": occurrences,
                    "source_count": source_count,
                    "status": "open",
                }
            )
    return {
        "schema_version": "capability-gap-report-v3",
        "items": items,
        "signal_need_items": needs,
        "technical_failures": sorted(
            technical_failures,
            key=lambda item: (
                item["case_id"], item["signal_ref"], item["status"]
            ),
        ),
        "open_count": (
            sum(item["status"] == "open" for item in items) + len(needs)
        ),
        "resolved_count": sum(item["status"] == "resolved" for item in items),
    }


@dataclass(frozen=True)
class ResolutionEvent:
    """One local-query or acquisition event retained in the trajectory."""

    kind: str
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", dict(self.details))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "details": dict(self.details)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResolutionEvent":
        return cls(str(data["kind"]), dict(data.get("details", {})))


@dataclass(frozen=True)
class RawInfoCoverage:
    """Retrieval and visibility facts that do not claim semantic answerability."""

    eligible_document_count: int
    selected_document_count: int
    query_matched_document_count: int | None
    selection_truncated: bool
    query_requested: bool = False
    query_evaluated: bool = False
    deduplicated_document_count: int = 0
    visible_span_count: int = 0
    context_truncated: bool | None = None
    required_source_group_count: int = 0
    satisfied_source_group_count: int = 0
    observed_distinct_period_count: int = 0
    observed_period_span_days: int | None = None
    observed_observation_count: int = 0
    contract_satisfied: bool = True
    missing_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        counts = (
            self.eligible_document_count,
            self.selected_document_count,
            self.deduplicated_document_count,
            self.visible_span_count,
            self.required_source_group_count,
            self.satisfied_source_group_count,
            self.observed_distinct_period_count,
            self.observed_observation_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValidationError("raw info coverage counts must be non-negative")
        if self.selected_document_count > self.eligible_document_count:
            raise ValidationError(
                "raw info selected count cannot exceed eligible count"
            )
        if self.query_matched_document_count is not None and (
            type(self.query_matched_document_count) is not int
            or not 0
            <= self.query_matched_document_count
            <= self.eligible_document_count
        ):
            raise ValidationError("raw info query match count is invalid")
        if not self.query_requested and self.query_matched_document_count is not None:
            raise ValidationError("raw info query matches require a requested query")
        if self.query_evaluated != (self.query_matched_document_count is not None):
            raise ValidationError(
                "raw info query evaluation and match count must agree"
            )
        if self.satisfied_source_group_count > self.required_source_group_count:
            raise ValidationError(
                "raw info satisfied source groups exceed required groups"
            )
        if (
            self.observed_period_span_days is not None
            and self.observed_period_span_days < 0
        ):
            raise ValidationError("raw info observed period span must be non-negative")
        if self.contract_satisfied != (not self.missing_requirements):
            raise ValidationError(
                "raw info contract status and missing requirements disagree"
            )
        object.__setattr__(
            self, "missing_requirements", tuple(self.missing_requirements)
        )

    @property
    def query_status(self) -> str:
        if not self.query_requested:
            return "not_requested"
        if not self.query_evaluated:
            return "not_recorded"
        if self.query_matched_document_count:
            return "matched"
        return "unmatched"

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible_document_count": self.eligible_document_count,
            "selected_document_count": self.selected_document_count,
            "query_matched_document_count": self.query_matched_document_count,
            "query_status": self.query_status,
            "query_requested": self.query_requested,
            "query_evaluated": self.query_evaluated,
            "selection_truncated": self.selection_truncated,
            "deduplicated_document_count": self.deduplicated_document_count,
            "visible_span_count": self.visible_span_count,
            "context_truncated": self.context_truncated,
            "required_source_group_count": self.required_source_group_count,
            "satisfied_source_group_count": self.satisfied_source_group_count,
            "observed_distinct_period_count": self.observed_distinct_period_count,
            "observed_period_span_days": self.observed_period_span_days,
            "observed_observation_count": self.observed_observation_count,
            "contract_satisfied": self.contract_satisfied,
            "missing_requirements": list(self.missing_requirements),
        }

    def with_visibility(
        self, *, span_count: int, truncated: bool
    ) -> "RawInfoCoverage":
        """Return the same retrieval facts with model-visibility measurements."""

        value = self.to_dict()
        value["visible_span_count"] = span_count
        value["context_truncated"] = truncated
        return RawInfoCoverage.from_dict(value)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawInfoCoverage":
        query_count = data.get("query_matched_document_count")
        return cls(
            eligible_document_count=int(data.get("eligible_document_count", 0)),
            selected_document_count=int(data.get("selected_document_count", 0)),
            query_matched_document_count=(
                int(query_count) if query_count is not None else None
            ),
            selection_truncated=bool(data.get("selection_truncated", False)),
            query_requested=bool(data.get("query_requested", query_count is not None)),
            query_evaluated=bool(data.get("query_evaluated", query_count is not None)),
            deduplicated_document_count=int(
                data.get("deduplicated_document_count", 0)
            ),
            visible_span_count=int(data.get("visible_span_count", 0)),
            context_truncated=(
                bool(data["context_truncated"])
                if data.get("context_truncated") is not None
                else None
            ),
            required_source_group_count=int(
                data.get("required_source_group_count", 0)
            ),
            satisfied_source_group_count=int(
                data.get("satisfied_source_group_count", 0)
            ),
            observed_distinct_period_count=int(
                data.get("observed_distinct_period_count", 0)
            ),
            observed_period_span_days=(
                int(data["observed_period_span_days"])
                if data.get("observed_period_span_days") is not None
                else None
            ),
            observed_observation_count=int(data.get("observed_observation_count", 0)),
            contract_satisfied=bool(data.get("contract_satisfied", True)),
            missing_requirements=tuple(
                str(item) for item in data.get("missing_requirements", ())
            ),
        )


@dataclass(frozen=True)
class RawInfoResolution:
    """Resolved documents, exact spans, and complete acquisition lineage."""

    request: RawInfoRequest
    status: str
    documents: tuple[RawInfoDocumentRef, ...] = ()
    context_spans: tuple[RawInfoContextSpan, ...] = ()
    events: tuple[ResolutionEvent, ...] = ()
    appended_documents: tuple[RawInfoDocumentRef, ...] = ()
    gap: DataGap | None = None
    coverage: RawInfoCoverage | None = None
    # Bounded readable previews of ranked-but-unfunded spans, disclosed so a
    # consumer can see what the budget omitted instead of treating the
    # selected spans as the complete relevant content.
    omitted_context_markers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"resolved", "unresolved"}:
            raise ValidationError("raw info resolution status is invalid")
        if self.status == "resolved" and not self.documents:
            raise ValidationError("resolved raw info request requires documents")
        object.__setattr__(self, "documents", tuple(self.documents))
        object.__setattr__(self, "context_spans", tuple(self.context_spans))
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "appended_documents", tuple(self.appended_documents))
        object.__setattr__(
            self, "omitted_context_markers", tuple(self.omitted_context_markers)
        )
        if self.coverage is None:
            object.__setattr__(
                self,
                "coverage",
                RawInfoCoverage(
                    eligible_document_count=len(self.documents),
                    selected_document_count=len(self.documents),
                    query_matched_document_count=None,
                    selection_truncated=False,
                    query_requested=bool(self.request.query),
                    query_evaluated=False,
                    deduplicated_document_count=0,
                    visible_span_count=len(self.context_spans),
                    context_truncated=None,
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "status": self.status,
            "documents": [item.to_dict() for item in self.documents],
            "context_spans": [item.to_dict() for item in self.context_spans],
            "events": [item.to_dict() for item in self.events],
            "appended_documents": [
                item.to_dict() for item in self.appended_documents
            ],
            "data_gap": self.gap.to_dict() if self.gap else None,
            "coverage": self.coverage.to_dict(),
            "omitted_context_markers": list(self.omitted_context_markers),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawInfoResolution":
        return cls(
            request=RawInfoRequest.from_dict(dict(data["request"])),
            status=str(data["status"]),
            documents=tuple(
                RawInfoDocumentRef.from_dict(item) for item in data.get("documents", ())
            ),
            context_spans=tuple(
                RawInfoContextSpan.from_dict(item)
                for item in data.get("context_spans", ())
            ),
            events=tuple(
                ResolutionEvent.from_dict(item) for item in data.get("events", ())
            ),
            appended_documents=tuple(
                RawInfoDocumentRef.from_dict(item)
                for item in data.get("appended_documents", ())
            ),
            gap=(
                DataGap.from_dict(dict(data["data_gap"]))
                if data.get("data_gap")
                else None
            ),
            coverage=(
                RawInfoCoverage.from_dict(dict(data["coverage"]))
                if isinstance(data.get("coverage"), Mapping)
                else None
            ),
            omitted_context_markers=tuple(
                str(item) for item in data.get("omitted_context_markers", ())
            ),
        )


@dataclass(frozen=True)
class BasicInfoBundle:
    """Ordered exact-source bootstrap context for one case."""

    requests: tuple[RawInfoResolution, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"requests": [item.to_dict() for item in self.requests]}

    def to_model_context_dict(self) -> dict[str, Any]:
        """Expose request purpose and literal spans, not acquisition diagnostics."""

        return {
            "requests": [
                {
                    "request": item.request.to_dict(),
                    "status": item.status,
                    "coverage": item.coverage.to_dict(),
                    "context_spans": [span.to_dict() for span in item.context_spans],
                    "data_gap": item.gap.to_dict() if item.gap else None,
                }
                for item in self.requests
            ]
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BasicInfoBundle":
        return cls(
            tuple(RawInfoResolution.from_dict(item) for item in data.get("requests", ()))
        )


@dataclass(frozen=True)
class AcquisitionResult:
    """Complete documents and provider/cache diagnostics from one adapter call."""

    documents: tuple[RawInfoDocument, ...] = ()
    events: tuple[ResolutionEvent, ...] = ()


class AcquisitionFailure(Exception):
    """Typed adapter failure converted into a DataGap by the resolver."""

    def __init__(self, reason: DataGapReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class _AcquisitionFailureMemo:
    reason: DataGapReason
    retryable: bool
    next_retry_at: datetime | None = None

    def should_reuse(self, now: datetime) -> bool:
        if not self.retryable:
            return True
        if self.next_retry_at is None:
            return True
        return now < self.next_retry_at


class AcquisitionAdapter(Protocol):
    """Provider adapter capable of materializing complete Raw Info documents."""

    provider: str
    source_types: tuple[str, ...]
    capabilities: tuple[str, ...]

    def acquire(
        self,
        request: RawInfoRequest,
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
    ) -> AcquisitionResult:
        """Fetch and materialize point-in-time source documents."""


@dataclass(frozen=True)
class DataAcquisitionPolicy:
    """Frozen authorization independent from LLM external execution."""

    enabled: bool = False
    allowed_providers: tuple[str, ...] = ()
    allowed_capabilities: tuple[str, ...] = ()
    allowed_source_types: tuple[str, ...] = ()
    max_requests_per_cycle: int = 0
    max_requests_per_run: int = 0

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValidationError("data acquisition enabled must be a boolean")
        for name in (
            "allowed_providers",
            "allowed_capabilities",
            "allowed_source_types",
        ):
            values = tuple(str(item).strip() for item in getattr(self, name))
            if any(not item for item in values) or len(set(values)) != len(values):
                raise ValidationError(
                    f"data acquisition {name} must contain unique non-empty values"
                )
            if DATA_ACQUISITION_WILDCARD in values and values != (
                DATA_ACQUISITION_WILDCARD,
            ):
                raise ValidationError(
                    f"data acquisition {name} wildcard must be the only value"
                )
            object.__setattr__(self, name, values)
        if type(self.max_requests_per_cycle) is not int or type(
            self.max_requests_per_run
        ) is not int:
            raise ValidationError("data acquisition limits must be integers")
        if self.enabled:
            if min(self.max_requests_per_cycle, self.max_requests_per_run) < 1:
                raise ValidationError(
                    "enabled data acquisition requires positive limits"
                )
            if not all(
                (
                    self.allowed_providers,
                    self.allowed_capabilities,
                    self.allowed_source_types,
                )
            ):
                raise ValidationError(
                    "enabled data acquisition requires explicit provider, "
                    "capability, and source-type allowlists"
                )
        elif any(
            (
                self.allowed_providers,
                self.allowed_capabilities,
                self.allowed_source_types,
                self.max_requests_per_cycle,
                self.max_requests_per_run,
            )
        ):
            raise ValidationError(
                "disabled data acquisition requires empty allowlists and zero limits"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "allowed_providers": list(self.allowed_providers),
            "allowed_capabilities": list(self.allowed_capabilities),
            "allowed_source_types": list(self.allowed_source_types),
            "max_requests_per_cycle": self.max_requests_per_cycle,
            "max_requests_per_run": self.max_requests_per_run,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DataAcquisitionPolicy":
        enabled = data.get("enabled", False)
        if type(enabled) is not bool:
            raise ValidationError("data acquisition enabled must be a boolean")

        def string_list(name: str) -> tuple[str, ...]:
            value = data.get(name, ())
            if not isinstance(value, (list, tuple)):
                raise ValidationError(f"data acquisition {name} must be an array")
            return tuple(str(item) for item in value)

        return cls(
            enabled=enabled,
            allowed_providers=string_list("allowed_providers"),
            allowed_capabilities=string_list("allowed_capabilities"),
            allowed_source_types=string_list("allowed_source_types"),
            max_requests_per_cycle=int(data.get("max_requests_per_cycle", 0)),
            max_requests_per_run=int(data.get("max_requests_per_run", 0)),
        )


BROAD_RESEARCH_DATA_MAX_REQUESTS_PER_CYCLE = 1_000
BROAD_RESEARCH_DATA_MAX_REQUESTS_PER_RUN = 10_000


def broad_research_data_policy_v1() -> DataAcquisitionPolicy:
    """Return the explicit historical Raw Info authorization for new research runs."""

    return DataAcquisitionPolicy(
        enabled=True,
        allowed_providers=(DATA_ACQUISITION_WILDCARD,),
        allowed_capabilities=(DATA_ACQUISITION_WILDCARD,),
        allowed_source_types=(DATA_ACQUISITION_WILDCARD,),
        max_requests_per_cycle=BROAD_RESEARCH_DATA_MAX_REQUESTS_PER_CYCLE,
        max_requests_per_run=BROAD_RESEARCH_DATA_MAX_REQUESTS_PER_RUN,
    )


_COUNTER_LOCK = threading.Lock()


@dataclass
class DataAcquisitionBudget:
    """Mutable request counters shared by every resolver in one run/cycle."""

    cycle_requests: int = 0
    run_requests: int = 0
    ledger_path: Path | None = None
    cycle_id: int = 0

    def __post_init__(self) -> None:
        if self.ledger_path is None or not self.ledger_path.exists():
            return
        entries = [
            json.loads(line)
            for line in self.ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.run_requests = len(entries)
        self.cycle_requests = sum(
            int(entry.get("cycle_id", -1)) == self.cycle_id for entry in entries
        )

    def reserve(self, request: RawInfoRequest, provider: str) -> None:
        """Durably reserve one provider-level acquisition request.

        The counter update and the complete JSONL append share the path
        append lock so bounded parallel workers never interleave half lines,
        double-count, or lose settled status.
        """

        lock = (
            jsonl_append_lock(self.ledger_path)
            if self.ledger_path is not None
            else _COUNTER_LOCK
        )
        with lock:
            self.cycle_requests += 1
            self.run_requests += 1
            if self.ledger_path is None:
                return
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "cycle_id": self.cycle_id,
                            "request_id": request.request_id,
                            "provider": provider,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())


class EvidenceResolver:
    """Resolve Raw Info locally first, then through authorized acquisition."""

    def __init__(
        self,
        store: RawInfoStore,
        *,
        adapters: Iterable[AcquisitionAdapter] = (),
        policy: DataAcquisitionPolicy = DataAcquisitionPolicy(),
        budget: DataAcquisitionBudget | None = None,
    ) -> None:
        if getattr(store, "acquisition_allowed", True) is False and policy.enabled:
            from stock_opportunity_agent.data.reviewed_snapshot import ReviewedSourceRejected
            raise ReviewedSourceRejected("reviewed source snapshot forbids enabled acquisition")
        self.store = store
        self.adapters = tuple(adapters)
        self.policy = policy
        self.budget = budget or DataAcquisitionBudget()
        self._acquisition_failures: dict[
            tuple[Any, ...], _AcquisitionFailureMemo
        ] = {}

    def resolve(
        self,
        request: RawInfoRequest,
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
        include_context: bool = False,
        context_budget: int = MAX_BASIC_INFO_CONTEXT_CHARS,
        select_documents: DocumentSelector | None = None,
    ) -> RawInfoResolution:
        """Resolve a request, with an optional pure selector over eligible inputs.

        The selector returns unique unchanged documents within the request limit;
        an empty selection permits normal authorized acquisition fallback.
        """

        documents, filtered_news_ids, coverage = self._local_documents(
            request,
            company_id=company_id,
            identity=identity,
            as_of=as_of,
            select_documents=select_documents,
        )
        events = [self._local_event(request, documents, phase="initial")]
        if filtered_news_ids:
            events.append(
                self._news_filter_event(
                    request,
                    filtered_news_ids,
                    phase="initial",
                )
            )
        appended: list[RawInfoDocumentRef] = []
        gap: DataGap | None = None
        if not coverage.contract_satisfied:
            matching_adapters = self._select_adapters(request)
            if not matching_adapters:
                if coverage.eligible_document_count == 0:
                    # Zero eligible point-in-time documents plus no
                    # acquisition route for these source types is an empty
                    # corpus, not a configuration failure: an existential
                    # Signal read abstains honestly (no-match is never
                    # negative, and no documents is never a technical error),
                    # exactly like the closed fixture corpora boundary.
                    return RawInfoResolution(
                        request=request,
                        status="unresolved",
                        documents=(),
                        events=tuple(events),
                        coverage=coverage,
                        gap=self._gap(
                            request,
                            DataGapReason.NO_MATCHING_DOCUMENTS,
                            "No point-in-time documents matched the request "
                            "and no acquisition adapter supports the "
                            "requested source types.",
                        ),
                    )
                gap = self._gap(
                    request,
                    DataGapReason.ADAPTER_MISSING,
                    "No acquisition adapter supports the requested source types.",
                )
            elif not self.policy.enabled:
                gap = self._gap(
                    request,
                    DataGapReason.EXTERNAL_NOT_AUTHORIZED,
                    "Source-data external acquisition is not authorized.",
                    provider=matching_adapters[0].provider,
                )
            else:
                authorized_adapters = tuple(
                    adapter
                    for adapter in matching_adapters
                    if self._adapter_authorized(adapter, request)
                )
                if not authorized_adapters:
                    gap = self._gap(
                        request,
                        DataGapReason.EXTERNAL_NOT_AUTHORIZED,
                        "The providers or capabilities are outside the frozen data authorization.",
                        provider=matching_adapters[0].provider,
                    )
                else:
                    adapter_identity = _adapter_routing_identity(
                        company_id,
                        identity,
                        local_symbol_provider=(
                            lambda cid: _local_market_symbol(
                                self.store, cid, as_of
                            )
                        ),
                    )
                    failures: list[tuple[str, DataGapReason]] = []
                    for adapter in authorized_adapters:
                        failure_key = _acquisition_failure_key(
                            adapter,
                            request,
                            company_id=company_id,
                            as_of=as_of,
                        )
                        reused_failure = self._acquisition_failures.get(failure_key)
                        if reused_failure is not None and reused_failure.should_reuse(
                            datetime.now(timezone.utc)
                        ):
                            failures.append((adapter.provider, reused_failure.reason))
                            events.append(
                                ResolutionEvent(
                                    "acquisition_failure_reused",
                                    {
                                        "provider": adapter.provider,
                                        "reason": reused_failure.reason.value,
                                        "retryable": reused_failure.retryable,
                                        "next_retry_at": (
                                            reused_failure.next_retry_at.isoformat()
                                            if reused_failure.next_retry_at
                                            else None
                                        ),
                                    },
                                )
                            )
                            continue
                        if reused_failure is not None:
                            self._acquisition_failures.pop(failure_key, None)
                        if self._budget_exhausted():
                            failures.append(
                                (adapter.provider, DataGapReason.QUOTA_DEFERRED)
                            )
                            events.append(
                                ResolutionEvent(
                                    "acquisition_failed",
                                    {
                                        "provider": adapter.provider,
                                        "reason": DataGapReason.QUOTA_DEFERRED.value,
                                    },
                                )
                            )
                            break
                        self.budget.reserve(request, adapter.provider)
                        events.append(
                            ResolutionEvent(
                                "acquisition_started",
                                {
                                    "provider": adapter.provider,
                                    "request_id": request.request_id,
                                },
                            )
                        )
                        try:
                            result = adapter.acquire(
                                request,
                                company_id=company_id,
                                identity=adapter_identity,
                                as_of=as_of,
                            )
                            events.extend(result.events)
                            if any(
                                document.company_id != company_id
                                for document in result.documents
                            ):
                                raise AcquisitionFailure(
                                    DataGapReason.MATERIALIZATION_FAILED,
                                    "Adapter returned a document for a different company.",
                                )
                            appended_count = 0
                            for document in result.documents:
                                if self.store.append(document):
                                    appended.append(
                                        RawInfoDocumentRef.from_document(document)
                                    )
                                    appended_count += 1
                            events.append(
                                ResolutionEvent(
                                    "acquisition_completed",
                                    {
                                        "provider": adapter.provider,
                                        "returned_documents": len(result.documents),
                                        "appended_documents": appended_count,
                                    },
                                )
                            )
                            documents, filtered_news_ids, coverage = self._local_documents(
                                request,
                                company_id=company_id,
                                identity=identity,
                                as_of=as_of,
                                select_documents=select_documents,
                            )
                            events.append(
                                self._local_event(
                                    request, documents, phase="after_acquisition"
                                )
                            )
                            if filtered_news_ids:
                                events.append(
                                    self._news_filter_event(
                                        request,
                                        filtered_news_ids,
                                        phase="after_acquisition",
                                    )
                                )
                            if coverage.contract_satisfied:
                                break
                            reason = (
                                DataGapReason.PROVIDER_NO_DATA
                                if not result.documents
                                else (
                                    DataGapReason.REQUIRED_COVERAGE_INCOMPLETE
                                    if documents
                                    else DataGapReason.NO_MATCHING_DOCUMENTS
                                )
                            )
                            failures.append((adapter.provider, reason))
                            self._remember_acquisition_failure(failure_key, reason)
                            events.append(
                                ResolutionEvent(
                                    "acquisition_failed",
                                    {
                                        "provider": adapter.provider,
                                        "reason": reason.value,
                                    },
                                )
                            )
                        except _DocumentSelectionError:
                            raise
                        except AcquisitionFailure as exc:
                            failures.append((adapter.provider, exc.reason))
                            self._remember_acquisition_failure(
                                failure_key, exc.reason
                            )
                            events.append(
                                ResolutionEvent(
                                    "acquisition_failed",
                                    {
                                        "provider": adapter.provider,
                                        "reason": exc.reason.value,
                                    },
                                )
                            )
                        except Exception as exc:  # provider boundary: retain type, not secrets
                            reason = (
                                DataGapReason.QUOTA_DEFERRED
                                if isinstance(exc, DataQuotaDeferred)
                                else (
                                    DataGapReason.PROVIDER_NO_DATA
                                    if "returned no daily prices" in str(exc).casefold()
                                    else DataGapReason.PROVIDER_ERROR
                                )
                            )
                            failures.append((adapter.provider, reason))
                            self._remember_acquisition_failure(
                                failure_key,
                                reason,
                                next_retry_at=(
                                    exc.next_retry_at
                                    if isinstance(exc, DataQuotaDeferred)
                                    else None
                                ),
                            )
                            events.append(
                                ResolutionEvent(
                                    "acquisition_failed",
                                    {
                                        "provider": adapter.provider,
                                        "reason": reason.value,
                                    },
                                )
                            )
                    if not coverage.contract_satisfied and failures:
                        provider, reason = failures[-1]
                        attempts = ", ".join(
                            f"{name}:{failure.value}"
                            for name, failure in failures
                        )
                        gap = self._gap(
                            request,
                            reason,
                            "Authorized acquisition adapters did not resolve the "
                            f"request ({attempts}).",
                            provider=provider,
                        )

        if documents and coverage.contract_satisfied:
            if include_context:
                all_spans = tuple(
                    _select_context_spans(
                        documents,
                        request,
                        10**12,
                        as_of=as_of,
                    )
                )
                spans = tuple(
                    _select_context_spans(
                        documents,
                        request,
                        context_budget,
                        as_of=as_of,
                    )
                )
                coverage = coverage.with_visibility(
                    span_count=len(spans), truncated=len(spans) < len(all_spans)
                )
                omitted_markers = _omitted_context_markers(spans, all_spans)
            else:
                spans = ()
                omitted_markers = ()
            return RawInfoResolution(
                request=request,
                status="resolved",
                documents=tuple(
                    RawInfoDocumentRef.from_document(item) for item in documents
                ),
                context_spans=spans,
                events=tuple(events),
                appended_documents=tuple(appended),
                coverage=coverage,
                omitted_context_markers=omitted_markers,
            )
        if documents and include_context:
            all_spans = tuple(
                _select_context_spans(documents, request, 10**12, as_of=as_of)
            )
            spans = tuple(
                _select_context_spans(
                    documents, request, context_budget, as_of=as_of
                )
            )
            coverage = coverage.with_visibility(
                span_count=len(spans), truncated=len(spans) < len(all_spans)
            )
            omitted_markers = _omitted_context_markers(spans, all_spans)
        else:
            spans = ()
            omitted_markers = ()
        incomplete_message = (
            "Point-in-time documents were found but required coverage is incomplete: "
            + "; ".join(coverage.missing_requirements)
            if documents
            else "No point-in-time documents matched the request."
        )
        return RawInfoResolution(
            request=request,
            status="unresolved",
            documents=tuple(
                RawInfoDocumentRef.from_document(item) for item in documents
            ),
            context_spans=spans,
            events=tuple(events),
            appended_documents=tuple(appended),
            omitted_context_markers=omitted_markers,
            gap=(
                self._gap(
                    request,
                    DataGapReason.REQUIRED_COVERAGE_INCOMPLETE,
                    incomplete_message,
                )
                if documents
                else gap
                or self._gap(
                    request,
                    DataGapReason.NO_MATCHING_DOCUMENTS,
                    incomplete_message,
                )
            ),
            coverage=coverage,
        )

    def _remember_acquisition_failure(
        self,
        key: tuple[Any, ...],
        reason: DataGapReason,
        *,
        next_retry_at: datetime | None = None,
    ) -> None:
        if reason is DataGapReason.PROVIDER_ERROR:
            return
        self._acquisition_failures[key] = _AcquisitionFailureMemo(
            reason=reason,
            retryable=reason is DataGapReason.QUOTA_DEFERRED,
            next_retry_at=next_retry_at,
        )

    def can_acquire(self, request: RawInfoRequest) -> bool:
        """Return whether an available authorized adapter can serve ``request``.

        This check is side-effect free: it does not search the store, reserve
        budget, contact a provider, or promise that provider data exists.
        """

        return self.policy.enabled and any(
            getattr(adapter, "available", True)
            and self._adapter_authorized(adapter, request)
            for adapter in self._select_adapters(request)
        )

    def acquisition_unavailability_reason(
        self, request: RawInfoRequest
    ) -> str | None:
        """Return one stable non-secret reason when acquisition is impossible."""

        if self.can_acquire(request):
            return None
        matching = self._select_adapters(request)
        if not matching:
            return DataGapReason.ADAPTER_MISSING.value
        if not self.policy.enabled:
            return DataGapReason.EXTERNAL_NOT_AUTHORIZED.value
        authorized = tuple(
            adapter
            for adapter in matching
            if self._adapter_authorized(adapter, request)
        )
        if not authorized:
            return DataGapReason.EXTERNAL_NOT_AUTHORIZED.value
        reasons = {
            str(
                getattr(
                    adapter,
                    "unavailability_reason",
                    "provider_unavailable",
                )
            )
            for adapter in authorized
            if not getattr(adapter, "available", True)
        }
        if len(reasons) == 1:
            return reasons.pop()
        return "provider_unavailable"

    def resolve_basic_info(
        self,
        requests: Iterable[RawInfoRequest],
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
    ) -> BasicInfoBundle:
        """Resolve an ordered Plan bootstrap under one shared context budget."""

        request_values = tuple(requests)
        if len(request_values) > MAX_BASIC_INFO_REQUESTS:
            raise ValidationError("Basic Info policy cannot exceed 8 requests")
        resolved_without_context: list[RawInfoResolution] = []
        for request in request_values:
            resolution = self.resolve(
                request,
                company_id=company_id,
                identity=identity,
                as_of=as_of,
                include_context=False,
            )
            resolved_without_context.append(resolution)

        candidates: list[list[RawInfoContextSpan]] = []
        all_candidates: list[list[RawInfoContextSpan]] = []
        for resolution in resolved_without_context:
            if not resolution.documents:
                candidates.append([])
                all_candidates.append([])
                continue
            documents = self.load_documents(resolution, as_of=as_of)
            candidates.append(
                _select_context_spans(
                    documents,
                    resolution.request,
                    MAX_BASIC_INFO_CONTEXT_CHARS,
                    as_of=as_of,
                )
            )
            all_candidates.append(
                _select_context_spans(
                    documents,
                    resolution.request,
                    10**12,
                    as_of=as_of,
                )
            )

        selected: list[list[RawInfoContextSpan]] = [
            [] for _resolution in resolved_without_context
        ]
        remaining = MAX_BASIC_INFO_CONTEXT_CHARS
        for index, rows in enumerate(candidates):
            if rows and rows[0].billable_chars <= remaining:
                selected[index].append(rows[0])
                remaining -= rows[0].billable_chars
        for index, rows in enumerate(candidates):
            for span in rows[1:]:
                if span.billable_chars > remaining:
                    continue
                selected[index].append(span)
                remaining -= span.billable_chars

        resolutions = tuple(
            RawInfoResolution(
                request=resolution.request,
                status=resolution.status,
                documents=resolution.documents,
                context_spans=tuple(selected[index]),
                events=resolution.events,
                appended_documents=resolution.appended_documents,
                gap=resolution.gap,
                coverage=resolution.coverage.with_visibility(
                    span_count=len(selected[index]),
                    truncated=len(selected[index]) < len(all_candidates[index]),
                ),
                omitted_context_markers=_omitted_context_markers(
                    selected[index], all_candidates[index]
                ),
            )
            for index, resolution in enumerate(resolved_without_context)
        )
        return BasicInfoBundle(resolutions)

    def load_documents(
        self, resolution: RawInfoResolution, *, as_of: datetime
    ) -> tuple[RawInfoDocument, ...]:
        """Load the complete documents cited by one resolution."""

        return tuple(
            self.store.load(item.document_id, as_of=as_of)
            for item in resolution.documents
        )

    @property
    def available_source_types(self) -> tuple[str, ...]:
        """Return locally present or explicitly authorized source types."""

        available = {document.source_type for document in self.store.documents}
        if self.policy.enabled:
            for adapter in self.adapters:
                if (
                    getattr(adapter, "available", True)
                    and self._adapter_policy_authorized(adapter)
                ):
                    available.update(adapter.source_types)
        return tuple(sorted(available))

    def _local_documents(
        self,
        request: RawInfoRequest,
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
        select_documents: DocumentSelector | None = None,
    ) -> tuple[list[RawInfoDocument], tuple[str, ...], RawInfoCoverage]:
        documents = [
            item
            for item in self.store.search(company_id, as_of=as_of)
            if _matches_source_type(item, request.source_types)
        ]
        if request.lookback_days is not None:
            lower = as_of - timedelta(days=request.lookback_days)
            documents = [item for item in documents if item.published_at >= lower]
        documents, filtered_news_ids = _filter_company_news_documents(
            documents,
            identity=identity,
        )
        documents, duplicate_ids = _deduplicate_documents(documents)
        ranked = _rank_documents(documents, request)
        if select_documents is None:
            selected = _select_required_source_documents(ranked, request)
        else:
            try:
                available = {item.document_id: item for item in ranked}
                original_records = {
                    item.document_id: canonical_json_hash(item.to_dict()) for item in ranked
                }
                selected = list(select_documents(deepcopy(tuple(ranked)), request))
                selected_ids = [item.document_id for item in selected]
                if (
                    len(selected) > request.max_documents
                    or len(set(selected_ids)) != len(selected_ids)
                    or any(not isinstance(item, RawInfoDocument)
                           or item.document_id not in original_records
                           or canonical_json_hash(item.to_dict()) != original_records[item.document_id]
                           for item in selected)
                ):
                    raise _DocumentSelectionError(
                        "Document selector must return unique unchanged eligible "
                        "documents within the request limit"
                    )
                selected = [available[document_id] for document_id in selected_ids]
            except _DocumentSelectionError:
                raise
            except Exception as exc:
                raise _DocumentSelectionError(
                    f"Local document selection failed ({type(exc).__name__})"
                ) from exc
        query_tokens = _request_query_tokens(request)
        query_matches = (
            sum(_document_query_hit_count(item, query_tokens) > 0 for item in ranked)
            if query_tokens
            else None
        )
        coverage = RawInfoCoverage(
            eligible_document_count=len(ranked),
            selected_document_count=len(selected),
            query_matched_document_count=query_matches,
            selection_truncated=len(selected) < len(ranked),
            query_requested=bool(query_tokens),
            query_evaluated=bool(query_tokens),
            deduplicated_document_count=len(duplicate_ids),
            **_retrieval_contract_coverage(selected, request),
        )
        return selected, filtered_news_ids, coverage

    def _select_adapters(
        self, request: RawInfoRequest
    ) -> tuple[AcquisitionAdapter, ...]:
        return tuple(
            adapter
            for adapter in self.adapters
            if source_types_compatible(request.source_types, adapter.source_types)
        )

    def _adapter_authorized(
        self, adapter: AcquisitionAdapter, request: RawInfoRequest
    ) -> bool:
        return (
            self._adapter_policy_authorized(adapter)
            and (
                DATA_ACQUISITION_WILDCARD
                in self.policy.allowed_source_types
                or source_types_compatible(
                    request.source_types,
                    self.policy.allowed_source_types,
                )
            )
        )

    def _adapter_policy_authorized(self, adapter: AcquisitionAdapter) -> bool:
        return (
            (
                not self.policy.allowed_providers
                or DATA_ACQUISITION_WILDCARD
                in self.policy.allowed_providers
                or adapter.provider in self.policy.allowed_providers
            )
            and (
                not self.policy.allowed_source_types
                or DATA_ACQUISITION_WILDCARD
                in self.policy.allowed_source_types
                or source_types_compatible(
                    adapter.source_types,
                    self.policy.allowed_source_types,
                )
            )
            and (
                not self.policy.allowed_capabilities
                or DATA_ACQUISITION_WILDCARD
                in self.policy.allowed_capabilities
                or bool(
                    set(adapter.capabilities).intersection(
                        self.policy.allowed_capabilities
                    )
                )
            )
        )

    def _budget_exhausted(self) -> bool:
        return (
            self.budget.cycle_requests >= self.policy.max_requests_per_cycle
            or self.budget.run_requests >= self.policy.max_requests_per_run
        )

    @staticmethod
    def _local_event(
        request: RawInfoRequest,
        documents: Iterable[RawInfoDocument],
        *,
        phase: str,
    ) -> ResolutionEvent:
        values = tuple(documents)
        return ResolutionEvent(
            "local_query",
            {
                "phase": phase,
                "request_id": request.request_id,
                "source_types": list(request.source_types),
                "matched_document_ids": [item.document_id for item in values],
            },
        )

    @staticmethod
    def _news_filter_event(
        request: RawInfoRequest,
        document_ids: Iterable[str],
        *,
        phase: str,
    ) -> ResolutionEvent:
        return ResolutionEvent(
            "news_documents_filtered",
            {
                "phase": phase,
                "request_id": request.request_id,
                "reason": "missing_strong_issuer_match",
                "filtered_document_ids": sorted(set(document_ids)),
            },
        )

    @staticmethod
    def _gap(
        request: RawInfoRequest,
        reason: DataGapReason,
        message: str,
        *,
        provider: str | None = None,
    ) -> DataGap:
        return DataGap(request.request_id, reason, message, request.source_types, provider)


def _adapter_routing_identity(
    company_id: str,
    identity: Mapping[str, Any],
    local_symbol_provider: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Add canonical CIK and ticker routes without exposing them to model context.

    Third-party adapters (Alpha Vantage, Finnhub) route by ticker or symbol,
    while internal case identity is a canonical ``cik_##########`` company id.
    When identity does not already carry a ticker/symbol, the resolver
    enriches it from local point-in-time market documents — every stored
    market row contains a ``symbol`` field — so any adapter that needs a
    ticker works regardless of what identity the calling case supplies.
    """

    routed = dict(identity)
    if not any(str(routed.get(key) or "").strip() for key in ("cik", "CIK")):
        match = _CANONICAL_CIK_COMPANY_ID.fullmatch(company_id)
        if match is not None:
            routed["cik"] = match.group(1)
    if not any(
        str(routed.get(key) or "").strip() for key in ("ticker", "symbol")
    ):
        symbol = (
            local_symbol_provider(company_id)
            if local_symbol_provider is not None
            else None
        )
        if symbol:
            routed["ticker"] = symbol
            routed["symbol"] = symbol
    return routed


def _local_market_symbol(store: Any, company_id: str, as_of: datetime) -> str | None:
    """Derive the issuer ticker from local PIT market documents, if any."""

    import re as _re

    try:
        documents = store.search(company_id, as_of=as_of)
    except Exception:
        return None
    for document in documents:
        if document.source_type.casefold() not in {
            "market_data", "prices", "price_daily", "historical_price",
        }:
            continue
        match = _re.search(r'"symbol":\s*"([A-Z]{1,10})"', document.content[:500])
        if match is not None:
            return match.group(1)
    return None


def _select_required_source_documents(
    ranked: list[RawInfoDocument], request: RawInfoRequest
) -> list[RawInfoDocument]:
    """Reserve source groups and comparison coverage before ordinary ranking."""

    selected: list[RawInfoDocument] = []
    selected_ids: set[str] = set()
    for group in request.required_source_groups:
        match = next(
            (
                document
                for document in ranked
                if document.document_id not in selected_ids
                and _matches_source_type(document, group)
            ),
            None,
        )
        if match is not None:
            selected.append(match)
            selected_ids.add(match.document_id)
    while len(selected) < request.max_documents:
        current_score = _retrieval_contract_selection_score(selected, request)
        best: RawInfoDocument | None = None
        best_score = current_score
        for document in ranked:
            if document.document_id in selected_ids:
                continue
            score = _retrieval_contract_selection_score(
                (*selected, document), request
            )
            if score > best_score:
                best = document
                best_score = score
        if best is None:
            break
        selected.append(best)
        selected_ids.add(best.document_id)
    for document in ranked:
        if len(selected) >= request.max_documents:
            break
        if document.document_id not in selected_ids:
            selected.append(document)
            selected_ids.add(document.document_id)
    return selected


def _retrieval_contract_selection_score(
    documents: Iterable[RawInfoDocument], request: RawInfoRequest
) -> tuple[int, int, int, int]:
    coverage = _retrieval_contract_coverage(documents, request)
    period_target = request.minimum_distinct_periods or 0
    span_target = request.minimum_period_span_days or 0
    observation_target = request.minimum_observations or 0
    return (
        coverage["satisfied_source_group_count"],
        min(coverage["observed_distinct_period_count"], period_target),
        min(coverage["observed_period_span_days"] or 0, span_target),
        min(coverage["observed_observation_count"], observation_target),
    )


def _retrieval_contract_coverage(
    documents: Iterable[RawInfoDocument], request: RawInfoRequest
) -> dict[str, Any]:
    values = tuple(documents)
    satisfied_groups = sum(
        any(_matches_source_type(document, group) for document in values)
        for group in request.required_source_groups
    )
    periods = sorted(
        {
            period
            for document in values
            for period in _document_research_periods(document)
        }
    )
    period_span = (periods[-1] - periods[0]).days if len(periods) >= 2 else None
    observation_count = max(
        (_document_observation_count(document) for document in values),
        default=0,
    )
    missing: list[str] = []
    if not values:
        missing.append("documents=0/1")
    if satisfied_groups < len(request.required_source_groups):
        for index, group in enumerate(request.required_source_groups):
            if not any(_matches_source_type(document, group) for document in values):
                missing.append(f"source_group[{index}]={'|'.join(group)}")
    if (
        request.minimum_distinct_periods is not None
        and len(periods) < request.minimum_distinct_periods
    ):
        missing.append(
            "distinct_periods="
            f"{len(periods)}/{request.minimum_distinct_periods}"
        )
    if request.minimum_period_span_days is not None and (
        period_span is None or period_span < request.minimum_period_span_days
    ):
        missing.append(
            "period_span_days="
            f"{period_span or 0}/{request.minimum_period_span_days}"
        )
    if (
        request.minimum_observations is not None
        and observation_count < request.minimum_observations
    ):
        missing.append(
            f"observations={observation_count}/{request.minimum_observations}"
        )
    return {
        "required_source_group_count": len(request.required_source_groups),
        "satisfied_source_group_count": satisfied_groups,
        "observed_distinct_period_count": len(periods),
        "observed_period_span_days": period_span,
        "observed_observation_count": observation_count,
        "contract_satisfied": not missing,
        "missing_requirements": tuple(missing),
    }


def _document_research_periods(document: RawInfoDocument) -> set[datetime]:
    """Extract domain periods from known structured fields, never source times."""

    values: list[Any] = [document.metadata]
    try:
        values.append(json.loads(document.content))
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    result: set[datetime] = set()
    period_keys = {
        "as_of_date",
        "date",
        "end",
        "fiscaldateending",
        "fiscal_date_ending",
        "period_end",
    }

    def visit(value: Any, key: str | None = None) -> None:
        if isinstance(value, Mapping):
            for nested_key, nested in value.items():
                visit(nested, str(nested_key).casefold())
        elif isinstance(value, (list, tuple)):
            for nested in value:
                visit(nested, key)
        elif key in period_keys and isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return
            result.add(parsed.replace(tzinfo=None))

    for value in values:
        visit(value)
    return result


def _document_observation_count(document: RawInfoDocument) -> int:
    """Return the largest explicit structured observation series in a document."""

    values: list[Any] = [document.metadata]
    try:
        values.append(json.loads(document.content))
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    counts: list[int] = []

    def visit(value: Any, key: str | None = None) -> None:
        if isinstance(value, Mapping):
            for nested_key, nested in value.items():
                visit(nested, str(nested_key).casefold())
        elif isinstance(value, list):
            if key in {"prices", "observations", "rows", "series"}:
                counts.append(len(value))
            elif value and all(
                isinstance(item, Mapping)
                and any(str(name).casefold() in {"date", "timestamp"} for name in item)
                for item in value
            ):
                counts.append(len(value))
            for nested in value:
                visit(nested, key)

    for value in values:
        visit(value)
    return max(counts, default=0)


def _request_query_tokens(request: RawInfoRequest) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(token.casefold() for token in _TOKEN.findall(request.query or ""))
    )


def _document_query_hit_count(
    document: RawInfoDocument,
    tokens: tuple[str, ...],
) -> int:
    searchable = document.content.casefold()
    return sum(searchable.count(token) for token in tokens)


def _deduplicate_documents(
    documents: Iterable[RawInfoDocument],
) -> tuple[list[RawInfoDocument], tuple[str, ...]]:
    """Keep one earliest-visible copy for identical content in one source type."""

    by_content: dict[tuple[str, str], RawInfoDocument] = {}
    duplicate_ids: list[str] = []
    for document in sorted(
        documents,
        key=lambda item: (item.available_at, item.document_id),
    ):
        key = (document.source_type.casefold(), document.content_hash)
        if key in by_content:
            duplicate_ids.append(document.document_id)
            continue
        by_content[key] = document
    return list(by_content.values()), tuple(sorted(duplicate_ids))


def _rank_documents(
    documents: Iterable[RawInfoDocument], request: RawInfoRequest
) -> list[RawInfoDocument]:
    tokens = _request_query_tokens(request)

    def key(document: RawInfoDocument) -> tuple[Any, ...]:
        hit_count = _document_query_hit_count(document, tokens)
        return (-hit_count, -document.available_at.timestamp(), document.document_id)

    ranked = sorted(documents, key=key)
    if request.request_id == OPERATING_REQUEST_ID:
        return operating_order(ranked, exact_document_form, lambda item: item.available_at)
    return ranked


def _filter_company_news_documents(
    documents: Iterable[RawInfoDocument],
    *,
    identity: Mapping[str, Any],
) -> tuple[list[RawInfoDocument], tuple[str, ...]]:
    """Reject provider-associated news whose visible text never names the issuer."""

    aliases = _issuer_relevance_aliases(identity)
    if not aliases:
        return list(documents), ()
    kept: list[RawInfoDocument] = []
    filtered: list[str] = []
    for document in documents:
        if document.source_type.casefold() not in {"news", "company_news"}:
            kept.append(document)
            continue
        if document_has_strong_issuer_match(document, identity, aliases=aliases):
            kept.append(document)
        else:
            filtered.append(document.document_id)
    return kept, tuple(sorted(filtered))


def document_has_strong_issuer_match(
    document: RawInfoDocument,
    identity: Mapping[str, Any],
    *,
    aliases: tuple[tuple[str, bool], ...] | None = None,
) -> bool:
    """Return whether visible title/body text names the routed issuer."""

    resolved_aliases = aliases or _issuer_relevance_aliases(identity)
    if not resolved_aliases:
        return False
    visible_text = _document_visible_issuer_text(document)
    return any(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            visible_text,
            flags=0 if ticker_like else re.IGNORECASE,
        )
        for alias, ticker_like in resolved_aliases
    )


def _document_visible_issuer_text(document: RawInfoDocument) -> str:
    """Project legacy provider JSON to reader-visible title/body text."""

    metadata_title = str(document.metadata.get("title", ""))
    if document.source_type.casefold() not in {"news", "company_news"}:
        return f"{metadata_title}\n{document.content}"
    try:
        payload = json.loads(document.content)
    except (json.JSONDecodeError, TypeError):
        return f"{metadata_title}\n{document.content}"
    if not isinstance(payload, Mapping):
        return f"{metadata_title}\n{document.content}"
    visible_fields = (
        str(payload.get(key) or "")
        for key in ("title", "summary", "body", "content")
    )
    return "\n".join((metadata_title, *visible_fields))


def _issuer_relevance_aliases(
    identity: Mapping[str, Any],
) -> tuple[tuple[str, bool], ...]:
    """Expand label-free routing identity into strong visible-text aliases."""

    raw_aliases: list[tuple[str, bool]] = []
    ticker_values = {
        value.strip()
        for key in ("ticker", "symbol")
        for value in (identity.get(key),)
        if isinstance(value, str) and value.strip()
    }
    for key in ("company_name", "name"):
        value = identity.get(key)
        if isinstance(value, str) and value.strip():
            raw_aliases.append((value.strip(), False))
    raw_aliases.extend((value, True) for value in ticker_values)
    supplied = identity.get("identity_aliases", ())
    if isinstance(supplied, str):
        supplied = (supplied,)
    if isinstance(supplied, (list, tuple)):
        raw_aliases.extend(
            (item.strip(), item.strip() in ticker_values)
            for item in supplied
            if isinstance(item, str) and item.strip()
        )

    variants: set[tuple[str, bool]] = set()
    for raw_alias, ticker_like in raw_aliases:
        alias = " ".join(raw_alias.split()).strip()
        if not alias:
            continue
        variants.add((alias, ticker_like))
        if ticker_like:
            continue
        for component in _IDENTITY_NAME_SEPARATOR.split(alias):
            component = " ".join(component.split()).strip(" ,")
            if not _meaningful_identity_alias(component):
                continue
            variants.add((component, False))
            natural_name = component
            while True:
                stripped = _IDENTITY_LEGAL_SUFFIX.sub("", natural_name).strip(" ,")
                if stripped == natural_name:
                    break
                natural_name = stripped
            if _meaningful_identity_alias(natural_name):
                variants.add((natural_name, False))
            brand = natural_name.split(maxsplit=1)[0].strip(".,'\"")
            brand_length = sum(character.isalnum() for character in brand)
            if (
                (brand_length >= 5 or (brand_length >= 3 and brand.isupper()))
                and brand.casefold() not in _GENERIC_IDENTITY_LEADING_WORDS
            ):
                variants.add((brand, False))
    return tuple(
        sorted(
            variants,
            key=lambda item: (-len(item[0]), item[0].casefold(), item[0], item[1]),
        )
    )


def _meaningful_identity_alias(value: str) -> bool:
    compact = "".join(character for character in value if character.isalnum())
    if len(compact) >= 4:
        return True
    return len(compact) >= 2 and any(character.isdigit() for character in compact)


def _matches_source_type(
    document: RawInfoDocument, requested_types: Iterable[str]
) -> bool:
    requested = {item.casefold() for item in requested_types}
    actual = document.source_type.casefold()
    requested_forms = requested.intersection(_EXACT_SEC_FORMS)
    if requested_forms:
        form = exact_document_form(document)
        if form is not None and form.casefold() in requested_forms:
            return True
        requested = requested - requested_forms
        if not requested:
            return False
    if actual in requested:
        return True
    if actual in _EXACT_SEC_FORMS and requested.intersection(_GENERIC_FILING_TYPES):
        return True
    return source_types_compatible((actual,), requested)



_SOURCE_TYPE_FAMILIES = (
    frozenset({"news", "company_news"}),
    frozenset({"earnings_call", "transcript", "earnings_transcript"}),
    frozenset({"price_daily", "market_data", "historical_price", "prices"}),
    frozenset(
        {
            "sec_company_facts",
            "company_facts",
            "financial_statements",
            "financials",
        }
    ),
    _GENERIC_FILING_TYPES | _EXACT_SEC_FORMS,
)


def source_types_compatible(
    left: Iterable[str], right: Iterable[str]
) -> bool:
    """Return whether two source declarations share one semantic route."""

    left_values = {str(item).casefold() for item in left}
    right_values = {str(item).casefold() for item in right}
    if left_values.intersection(right_values):
        return True
    return any(
        bool(left_values.intersection(family))
        and bool(right_values.intersection(family))
        for family in _SOURCE_TYPE_FAMILIES
    )


def _acquisition_failure_key(
    adapter: AcquisitionAdapter,
    request: RawInfoRequest,
    *,
    company_id: str,
    as_of: datetime,
) -> tuple[Any, ...]:
    adapter_types = {str(item).casefold() for item in adapter.source_types}
    requested_types = {str(item).casefold() for item in request.source_types}
    route = "|".join(sorted(adapter_types.intersection(requested_types)))
    for index, family in enumerate(_SOURCE_TYPE_FAMILIES):
        if adapter_types.intersection(family) and requested_types.intersection(family):
            route = f"family:{index}"
            break
    return (
        str(adapter.provider),
        route,
        company_id,
        as_of.isoformat(),
        request.lookback_days,
        request.max_documents,
        request.query,
        request.required_source_groups,
        request.minimum_distinct_periods,
        request.minimum_period_span_days,
        request.minimum_observations,
    )


# Per-query-token hit cap and rarity weighting keep boilerplate sections from
# out-scoring rare substantive language: a token repeated many times in one
# window (risk/business/management in filings) contributes a capped count, and
# tokens present in most candidate windows are down-weighted by inverse
# document frequency while rare tokens are up-weighted.
_TOKEN_HIT_CAP_PER_WINDOW = 3
_NEAR_DUPLICATE_OVERLAP_FRACTION = 0.6
_OMITTED_MARKER_COUNT = 6
_OMITTED_MARKER_CHARS = 110


def _readable_span_preview(text: str) -> str:
    """Collapse one raw span into a short readable marker preview."""

    stripped = _HTML_TAG.sub(" ", text)
    collapsed = " ".join(stripped.split())
    return collapsed[:_OMITTED_MARKER_CHARS]


def _omitted_context_markers(
    selected: Iterable[RawInfoContextSpan],
    all_candidates: Iterable[RawInfoContextSpan],
) -> tuple[str, ...]:
    """Disclose bounded previews of ranked-but-unfunded spans.

    Visibility budgets can drop relevant windows even from selected
    documents. The ranked-but-omitted previews let a consumer see that the
    content exists instead of treating the funded spans as everything the
    documents had to offer.
    """

    selected_keys = {
        (span.document_id, span.start, span.end) for span in selected
    }
    markers: list[str] = []
    for span in all_candidates:
        if (span.document_id, span.start, span.end) in selected_keys:
            continue
        markers.append(_readable_span_preview(span.exact_text))
        if len(markers) >= _OMITTED_MARKER_COUNT:
            break
    return tuple(markers)


def _select_context_spans(
    documents: Iterable[RawInfoDocument],
    request: RawInfoRequest,
    budget: int,
    *,
    as_of: datetime,
) -> list[RawInfoContextSpan]:
    candidates: list[tuple[tuple[Any, ...], RawInfoContextSpan]] = []
    tokens = tuple(token.casefold() for token in _TOKEN.findall(request.query or ""))
    windows: list[tuple[RawInfoDocument, int, int, str]] = []
    for document in documents:
        market_ranges = _structured_market_context_ranges(document, request, as_of)
        markup_windows = (
            _markup_context_windows(document.content)
            if market_ranges is None
            and document.source_type.casefold() in _MARKUP_SOURCE_TYPES
            and _HTML_TAG.search(document.content)
            else None
        )
        window_rows = (
            ((start, end, document.content[start:end]) for start, end in market_ranges)
            if market_ranges is not None
            else (
                markup_windows
                if markup_windows is not None
                else (
                    (start, end, document.content[start:end])
                    for start, end in _chunk_ranges(len(document.content))
                )
            )
        )
        for start, end, rank_text in window_rows:
            windows.append((document, start, end, rank_text))
    scores: list[float] = []
    if tokens:
        document_frequency: dict[str, int] = {token: 0 for token in tokens}
        hit_counts: list[dict[str, int]] = []
        for _document, _start, _end, rank_text in windows:
            lowered = rank_text.casefold()
            counts = {
                token: count
                for token in tokens
                if (count := lowered.count(token))
            }
            hit_counts.append(counts)
            for token in counts:
                document_frequency[token] += 1
        total_windows = len(windows)
        weights = {
            token: math.log((total_windows + 1) / (frequency + 1)) + 1.0
            for token, frequency in document_frequency.items()
        }
        for counts in hit_counts:
            scores.append(
                sum(
                    min(count, _TOKEN_HIT_CAP_PER_WINDOW) * weights[token]
                    for token, count in counts.items()
                )
            )
    else:
        scores = [0.0] * len(windows)
    for (document, start, end, rank_text), score in zip(windows, scores):
        rank = (
            -score,
            -document.available_at.timestamp(),
            document.document_id,
            start,
        )
        exact_text = document.content[start:end]
        visible_chars = (
            len(rank_text) if len(rank_text) != len(exact_text) else None
        )
        candidates.append(
            (
                rank,
                RawInfoContextSpan(
                    document.document_id,
                    document.content_hash,
                    document.available_at,
                    start,
                    end,
                    exact_text,
                    visible_chars=visible_chars,
                ),
            )
        )
    selected: list[RawInfoContextSpan] = []
    used = 0
    # Deterministic head retention: the first readable window of every
    # document that contributes any selected span is pinned ahead of that
    # document's other windows (event-driven filings carry their substance
    # up front) and is exempt from near-duplicate suppression.
    head_by_document: dict[str, RawInfoContextSpan] = {}
    for (document, _start, _end, _rank_text), (_rank, span) in zip(
        windows, candidates
    ):
        existing = head_by_document.get(span.document_id)
        if existing is None or span.start < existing.start:
            head_by_document[span.document_id] = span

    def _overlaps_selected(span: RawInfoContextSpan) -> bool:
        return any(
            span.document_id == kept.document_id
            and max(0, min(span.end, kept.end) - max(span.start, kept.start))
            >= _NEAR_DUPLICATE_OVERLAP_FRACTION * (span.end - span.start)
            for kept in selected
        )

    pinned_documents: set[str] = set()

    def _try_pin_head(document_id: str) -> None:
        nonlocal used
        head = head_by_document.get(document_id)
        if head is None or document_id in pinned_documents:
            return
        pinned_documents.add(document_id)
        if any(kept is head for kept in selected):
            return
        if head.billable_chars > budget - used:
            return
        selected.append(head)
        used += head.billable_chars

    for _, span in sorted(candidates, key=lambda item: item[0]):
        billable = span.billable_chars
        if used + billable > budget:
            continue
        if any(kept is span for kept in selected):
            continue
        # Near-duplicate suppression: skip a window almost entirely covered
        # by an already-selected window of the same document. The fixed
        # chunk overlap (200 characters) stays well below this fraction, so
        # only substantively repeated windows are dropped.
        if _overlaps_selected(span):
            continue
        selected.append(span)
        used += billable
        _try_pin_head(span.document_id)
    return selected


def _normalized_visible_text(
    raw_text: str,
) -> tuple[list[str], list[tuple[int, int]]]:
    """Map markup content to readable characters with raw-offset origins."""

    visible: list[str] = []
    origins: list[tuple[int, int]] = []

    def append(character: str, start: int, end: int) -> None:
        if character.isspace():
            if visible and visible[-1] != " ":
                visible.append(" ")
                origins.append((start, end))
            return
        visible.append(character)
        origins.append((start, end))

    removed = [*nonvisible_html_ranges(raw_text), *(
        (match.start(), match.end()) for match in _HTML_TAG.finditer(raw_text)
    )]
    cursor = 0
    for start, end in sorted(removed):
        if start < cursor:
            cursor = max(cursor, end)
            continue
        for index in range(cursor, start):
            append(raw_text[index], index, index + 1)
        append(" ", start, end)
        cursor = end
    for index in range(cursor, len(raw_text)):
        append(raw_text[index], index, index + 1)
    while visible and visible[-1] == " ":
        visible.pop()
        origins.pop()
    return visible, origins


def _markup_context_windows(
    raw_text: str,
) -> tuple[tuple[int, int, str], ...]:
    """Choose readable markup windows while retaining exact raw boundaries."""

    visible, origins = _normalized_visible_text(raw_text)
    if not visible:
        return ()

    text_value = "".join(visible)
    windows: list[tuple[int, int, str]] = []
    for start, end in _chunk_ranges(len(text_value)):
        while start < end and visible[start] == " ":
            start += 1
        while end > start and visible[end - 1] == " ":
            end -= 1
        if start == end:
            continue
        windows.append(
            (
                origins[start][0],
                origins[end - 1][1],
                text_value[start:end],
            )
        )
    return tuple(windows)


def _structured_market_context_ranges(
    document: RawInfoDocument,
    request: RawInfoRequest,
    as_of: datetime,
) -> tuple[tuple[int, int], ...] | None:
    """Return complete-row market chunks inside the requested observation window."""

    if request.lookback_days is None or document.source_type.casefold() not in {
        "historical_price",
        "market_data",
        "price_daily",
        "prices",
    }:
        return None
    rows = _json_array_rows_with_offsets(document.content)
    if not rows:
        return ()
    upper = utc_day_of_instant(as_of)
    lower = upper - timedelta(days=request.lookback_days)
    eligible = [
        (start, end)
        for start, end, value in rows
        if (observed := _market_observation_date(value)) is not None
        and lower <= observed <= upper
    ]
    if not eligible:
        return ()

    grouped: list[tuple[int, int]] = []
    group_start, group_end = eligible[0]
    for start, end in eligible[1:]:
        if end - group_start <= CONTEXT_CHUNK_CHARS:
            group_end = end
            continue
        grouped.append((group_start, group_end))
        group_start, group_end = start, end
    grouped.append((group_start, group_end))
    return tuple(grouped)


def _json_array_rows_with_offsets(
    content: str,
) -> list[tuple[int, int, Mapping[str, Any]]]:
    """Decode a top-level JSON array while retaining each literal row offset."""

    decoder = json.JSONDecoder()
    index = 0
    length = len(content)
    while index < length and content[index].isspace():
        index += 1
    if index >= length or content[index] != "[":
        return []
    index += 1
    rows: list[tuple[int, int, Mapping[str, Any]]] = []
    while True:
        while index < length and content[index].isspace():
            index += 1
        if index < length and content[index] == "]":
            return rows
        try:
            value, end = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            return []
        if not isinstance(value, Mapping):
            return []
        rows.append((index, end, value))
        index = end
        while index < length and content[index].isspace():
            index += 1
        if index < length and content[index] == ",":
            index += 1
            continue
        if index < length and content[index] == "]":
            return rows
        return []


def _market_observation_date(value: Mapping[str, Any]):
    for key in ("as_of_date", "date"):
        raw = value.get(key)
        if raw is None:
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return None


def _chunk_ranges(length: int) -> Iterable[tuple[int, int]]:
    start = 0
    step = CONTEXT_CHUNK_CHARS - CONTEXT_CHUNK_OVERLAP
    while start < length:
        end = min(start + CONTEXT_CHUNK_CHARS, length)
        yield start, end
        if end == length:
            break
        start += step
