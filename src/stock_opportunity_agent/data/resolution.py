"""Local-first point-in-time resolution against the append-only Raw Info oracle."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
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
    {"10-k", "10-q", "filing", "filing_body", "sec_filing"}
)
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


@dataclass(frozen=True)
class RawInfoRequest:
    """One auditable source-retrieval need; ``as_of`` is supplied by the case."""

    request_id: str
    description: str
    source_types: tuple[str, ...]
    lookback_days: int | None = None
    max_documents: int = 5
    query: str | None = None

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
        object.__setattr__(self, "source_types", tuple(self.source_types))
        object.__setattr__(self, "query", self.query.strip() if self.query else None)

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
        )


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "content_hash": self.content_hash,
            "available_at": self.available_at.isoformat(),
            "start": self.start,
            "end": self.end,
            "exact_text": self.exact_text,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawInfoContextSpan":
        return cls(
            document_id=str(data["document_id"]),
            content_hash=str(data["content_hash"]),
            available_at=datetime.fromisoformat(str(data["available_at"])),
            start=int(data["start"]),
            end=int(data["end"]),
            exact_text=str(data["exact_text"]),
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


def aggregate_capability_gaps(
    trajectories: Iterable[Mapping[str, Any]],
    *,
    available_source_types: Iterable[str] = (),
    signal_need_items: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a deterministic data/Signal backlog from durable diagnostics."""

    available = {item.casefold() for item in available_source_types}
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for trajectory in trajectories:
        case_id = str(trajectory.get("case_id", "unknown"))
        resolutions = list(
            dict(trajectory.get("basic_info_bundle", {})).get("requests", ())
        )
        for signal_round in trajectory.get("signal_rounds", ()):
            batch = dict(signal_round).get("batch", {})
            resolutions.extend(dict(batch).get("resolutions", ()))
        for resolution in resolutions:
            if not isinstance(resolution, Mapping):
                continue
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
        resolved = item["reason"] in {
            DataGapReason.ADAPTER_MISSING.value,
            DataGapReason.EXTERNAL_NOT_AUTHORIZED.value,
        } and source_types_compatible(item["source_types"], available)
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
        normalized = need.casefold()
        if not need or normalized in seen_needs:
            continue
        seen_needs.add(normalized)
        occurrences = int(raw_item.get("occurrences", 0))
        source_count = int(raw_item.get("source_count", 0))
        if occurrences < 1 or source_count < 1:
            raise ValidationError("Signal-need backlog counts must be positive")
        needs.append(
            {
                "kind": "unmatched_signal_need",
                "need": need,
                "stop_reason": "no_signal_match",
                "occurrences": occurrences,
                "source_count": source_count,
                "status": "open",
            }
        )
    return {
        "schema_version": "capability-gap-report-v2",
        "items": items,
        "signal_need_items": needs,
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
class RawInfoResolution:
    """Resolved documents, exact spans, and complete acquisition lineage."""

    request: RawInfoRequest
    status: str
    documents: tuple[RawInfoDocumentRef, ...] = ()
    context_spans: tuple[RawInfoContextSpan, ...] = ()
    events: tuple[ResolutionEvent, ...] = ()
    appended_documents: tuple[RawInfoDocumentRef, ...] = ()
    gap: DataGap | None = None

    def __post_init__(self) -> None:
        if self.status not in {"resolved", "unresolved"}:
            raise ValidationError("raw info resolution status is invalid")
        if self.status == "resolved" and not self.documents:
            raise ValidationError("resolved raw info request requires documents")
        object.__setattr__(self, "documents", tuple(self.documents))
        object.__setattr__(self, "context_spans", tuple(self.context_spans))
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "appended_documents", tuple(self.appended_documents))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "status": self.status,
            "documents": [item.to_dict() for item in self.documents],
            "context_spans": [item.to_dict() for item in self.context_spans],
            "events": [item.to_dict() for item in self.events],
            "appended_documents": [item.to_dict() for item in self.appended_documents],
            "data_gap": self.gap.to_dict() if self.gap else None,
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
        """Durably reserve one provider-level acquisition request."""

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
        self.store = store
        self.adapters = tuple(adapters)
        self.policy = policy
        self.budget = budget or DataAcquisitionBudget()
        self._acquisition_failures: dict[
            tuple[str, str, str, str, int | None, int], DataGapReason
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
    ) -> RawInfoResolution:
        """Resolve one request and optionally select exact Basic Info spans."""

        documents, filtered_news_ids = self._local_documents(
            request,
            company_id=company_id,
            identity=identity,
            as_of=as_of,
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
        if not documents:
            matching_adapters = self._select_adapters(request)
            if not matching_adapters:
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
                    adapter_identity = _adapter_routing_identity(company_id, identity)
                    failures: list[tuple[str, DataGapReason]] = []
                    for adapter in authorized_adapters:
                        failure_key = _acquisition_failure_key(
                            adapter,
                            request,
                            company_id=company_id,
                            as_of=as_of,
                        )
                        reused_failure = self._acquisition_failures.get(failure_key)
                        if reused_failure is not None:
                            failures.append((adapter.provider, reused_failure))
                            events.append(
                                ResolutionEvent(
                                    "acquisition_failure_reused",
                                    {
                                        "provider": adapter.provider,
                                        "reason": reused_failure.value,
                                    },
                                )
                            )
                            continue
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
                            documents, filtered_news_ids = self._local_documents(
                                request,
                                company_id=company_id,
                                identity=identity,
                                as_of=as_of,
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
                            if documents:
                                break
                            reason = (
                                DataGapReason.PROVIDER_NO_DATA
                                if not result.documents
                                else DataGapReason.NO_MATCHING_DOCUMENTS
                            )
                            failures.append((adapter.provider, reason))
                            self._acquisition_failures[failure_key] = reason
                            events.append(
                                ResolutionEvent(
                                    "acquisition_failed",
                                    {
                                        "provider": adapter.provider,
                                        "reason": reason.value,
                                    },
                                )
                            )
                        except AcquisitionFailure as exc:
                            failures.append((adapter.provider, exc.reason))
                            self._acquisition_failures[failure_key] = exc.reason
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
                                if type(exc).__name__ == "DataQuotaDeferred"
                                else (
                                    DataGapReason.PROVIDER_NO_DATA
                                    if "returned no daily prices" in str(exc).casefold()
                                    else DataGapReason.PROVIDER_ERROR
                                )
                            )
                            failures.append((adapter.provider, reason))
                            self._acquisition_failures[failure_key] = reason
                            events.append(
                                ResolutionEvent(
                                    "acquisition_failed",
                                    {
                                        "provider": adapter.provider,
                                        "reason": reason.value,
                                    },
                                )
                            )
                    if not documents and failures:
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

        if documents:
            spans = (
                tuple(
                    _select_context_spans(
                        documents,
                        request,
                        context_budget,
                        as_of=as_of,
                    )
                )
                if include_context
                else ()
            )
            return RawInfoResolution(
                request=request,
                status="resolved",
                documents=tuple(RawInfoDocumentRef.from_document(item) for item in documents),
                context_spans=spans,
                events=tuple(events),
                appended_documents=tuple(appended),
            )
        return RawInfoResolution(
            request=request,
            status="unresolved",
            events=tuple(events),
            appended_documents=tuple(appended),
            gap=gap
            or self._gap(
                request,
                DataGapReason.NO_MATCHING_DOCUMENTS,
                "No point-in-time documents matched the request.",
            ),
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

        remaining = MAX_BASIC_INFO_CONTEXT_CHARS
        resolutions: list[RawInfoResolution] = []
        request_values = tuple(requests)
        if len(request_values) > MAX_BASIC_INFO_REQUESTS:
            raise ValidationError("Basic Info policy cannot exceed 8 requests")
        for request in request_values:
            resolution = self.resolve(
                request,
                company_id=company_id,
                identity=identity,
                as_of=as_of,
                include_context=True,
                context_budget=remaining,
            )
            remaining -= sum(len(span.exact_text) for span in resolution.context_spans)
            resolutions.append(resolution)
        return BasicInfoBundle(tuple(resolutions))

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
    ) -> tuple[list[RawInfoDocument], tuple[str, ...]]:
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
        return (
            _rank_documents(documents, request)[: request.max_documents],
            filtered_news_ids,
        )

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
    company_id: str, identity: Mapping[str, Any]
) -> dict[str, Any]:
    """Add a canonical CIK route without exposing it to model context."""

    routed = dict(identity)
    if any(str(routed.get(key) or "").strip() for key in ("cik", "CIK")):
        return routed
    match = _CANONICAL_CIK_COMPANY_ID.fullmatch(company_id)
    if match is not None:
        routed["cik"] = match.group(1)
    return routed


def _rank_documents(
    documents: Iterable[RawInfoDocument], request: RawInfoRequest
) -> list[RawInfoDocument]:
    tokens = tuple(token.casefold() for token in _TOKEN.findall(request.query or ""))

    def key(document: RawInfoDocument) -> tuple[Any, ...]:
        hit_count = sum(document.content.casefold().count(token) for token in tokens)
        return (-hit_count, -document.available_at.timestamp(), document.document_id)

    return sorted(documents, key=key)


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
    visible_text = f"{str(document.metadata.get('title', ''))}\n{document.content}"
    return any(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            visible_text,
            flags=0 if ticker_like else re.IGNORECASE,
        )
        for alias, ticker_like in resolved_aliases
    )


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
    if actual in requested:
        return True
    if requested.intersection({"10-k", "10-q", "8-k"}) and actual in {
        "filing",
        "sec_filing",
        "filing_body",
    }:
        searchable = " ".join(
            str(document.metadata.get(key, "")) for key in ("form", "title")
        ).casefold()
        return any(form in searchable for form in requested.intersection({"10-k", "10-q", "8-k"}))
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
    frozenset({"filing", "sec_filing", "filing_body", "10-k", "10-q", "8-k"}),
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
) -> tuple[str, str, str, str, int | None, int]:
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
    )


def _select_context_spans(
    documents: Iterable[RawInfoDocument],
    request: RawInfoRequest,
    budget: int,
    *,
    as_of: datetime,
) -> list[RawInfoContextSpan]:
    candidates: list[tuple[tuple[Any, ...], RawInfoContextSpan]] = []
    tokens = tuple(token.casefold() for token in _TOKEN.findall(request.query or ""))
    for document in documents:
        market_ranges = _structured_market_context_ranges(document, request, as_of)
        markup_windows = (
            _markup_context_windows(document.content)
            if market_ranges is None
            and document.source_type.casefold() in _MARKUP_SOURCE_TYPES
            and _HTML_TAG.search(document.content)
            else None
        )
        windows = (
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
        for start, end, rank_text in windows:
            text = document.content[start:end]
            hit_count = sum(
                rank_text.casefold().count(token) for token in tokens
            )
            rank = (
                -hit_count,
                -document.available_at.timestamp(),
                document.document_id,
                start,
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
                        text,
                    ),
                )
            )
    selected: list[RawInfoContextSpan] = []
    used = 0
    for _, span in sorted(candidates, key=lambda item: item[0]):
        if used + len(span.exact_text) > budget:
            continue
        selected.append(span)
        used += len(span.exact_text)
    return selected


def _markup_context_windows(
    raw_text: str,
) -> tuple[tuple[int, int, str], ...]:
    """Choose readable markup windows while retaining exact raw boundaries."""

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

    cursor = 0
    for match in _HTML_TAG.finditer(raw_text):
        for index in range(cursor, match.start()):
            append(raw_text[index], index, index + 1)
        append(" ", match.start(), match.end())
        cursor = match.end()
    for index in range(cursor, len(raw_text)):
        append(raw_text[index], index, index + 1)
    while visible and visible[-1] == " ":
        visible.pop()
        origins.pop()
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
    lower = (as_of - timedelta(days=request.lookback_days)).date()
    upper = as_of.date()
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
