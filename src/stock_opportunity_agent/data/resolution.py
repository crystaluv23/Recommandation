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
_TOKEN = re.compile(r"[A-Za-z0-9]+")


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
        if self.enabled and min(self.max_requests_per_cycle, self.max_requests_per_run) < 1:
            raise ValidationError("enabled data acquisition requires positive limits")

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
        return cls(
            enabled=bool(data.get("enabled", False)),
            allowed_providers=tuple(str(item) for item in data.get("allowed_providers", ())),
            allowed_capabilities=tuple(str(item) for item in data.get("allowed_capabilities", ())),
            allowed_source_types=tuple(str(item) for item in data.get("allowed_source_types", ())),
            max_requests_per_cycle=int(data.get("max_requests_per_cycle", 0)),
            max_requests_per_run=int(data.get("max_requests_per_run", 0)),
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

        documents = self._local_documents(request, company_id=company_id, as_of=as_of)
        events = [self._local_event(request, documents, phase="initial")]
        appended: list[RawInfoDocumentRef] = []
        gap: DataGap | None = None
        if not documents:
            adapter = self._select_adapter(request)
            if adapter is None:
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
                    provider=adapter.provider,
                )
            elif not self._adapter_authorized(adapter, request):
                gap = self._gap(
                    request,
                    DataGapReason.EXTERNAL_NOT_AUTHORIZED,
                    "The provider or capability is outside the frozen data authorization.",
                    provider=adapter.provider,
                )
            elif self._budget_exhausted():
                gap = self._gap(
                    request,
                    DataGapReason.QUOTA_DEFERRED,
                    "The frozen source-data request ceiling was reached.",
                    provider=adapter.provider,
                )
            else:
                self.budget.reserve(request, adapter.provider)
                events.append(
                    ResolutionEvent(
                        "acquisition_started",
                        {"provider": adapter.provider, "request_id": request.request_id},
                    )
                )
                try:
                    result = adapter.acquire(
                        request,
                        company_id=company_id,
                        identity=identity,
                        as_of=as_of,
                    )
                    events.extend(result.events)
                    for document in result.documents:
                        if document.company_id != company_id:
                            raise AcquisitionFailure(
                                DataGapReason.MATERIALIZATION_FAILED,
                                "Adapter returned a document for a different company.",
                            )
                        if self.store.append(document):
                            appended.append(RawInfoDocumentRef.from_document(document))
                    events.append(
                        ResolutionEvent(
                            "acquisition_completed",
                            {
                                "provider": adapter.provider,
                                "returned_documents": len(result.documents),
                                "appended_documents": len(appended),
                            },
                        )
                    )
                    documents = self._local_documents(
                        request, company_id=company_id, as_of=as_of
                    )
                    events.append(self._local_event(request, documents, phase="after_acquisition"))
                    if not result.documents:
                        gap = self._gap(
                            request,
                            DataGapReason.PROVIDER_NO_DATA,
                            "The provider returned no point-in-time documents.",
                            provider=adapter.provider,
                        )
                except AcquisitionFailure as exc:
                    gap = self._gap(request, exc.reason, str(exc), provider=adapter.provider)
                    events.append(
                        ResolutionEvent(
                            "acquisition_failed",
                            {"provider": adapter.provider, "reason": exc.reason.value},
                        )
                    )
                except Exception as exc:  # provider boundary: retain type, not secrets
                    reason = (
                        DataGapReason.QUOTA_DEFERRED
                        if type(exc).__name__ == "DataQuotaDeferred"
                        else DataGapReason.PROVIDER_ERROR
                    )
                    gap = self._gap(
                        request,
                        reason,
                        f"{type(exc).__name__}: {exc}",
                        provider=adapter.provider,
                    )
                    events.append(
                        ResolutionEvent(
                            "acquisition_failed",
                            {"provider": adapter.provider, "reason": reason.value},
                        )
                    )

        if documents:
            spans = (
                tuple(_select_context_spans(documents, request, context_budget))
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

    def _local_documents(
        self, request: RawInfoRequest, *, company_id: str, as_of: datetime
    ) -> list[RawInfoDocument]:
        documents = [
            item
            for item in self.store.search(company_id, as_of=as_of)
            if _matches_source_type(item, request.source_types)
        ]
        if request.lookback_days is not None:
            lower = as_of - timedelta(days=request.lookback_days)
            documents = [item for item in documents if item.published_at >= lower]
        return _rank_documents(documents, request)[: request.max_documents]

    def _select_adapter(self, request: RawInfoRequest) -> AcquisitionAdapter | None:
        requested = set(request.source_types)
        matches = tuple(
            adapter
            for adapter in self.adapters
            if requested.intersection(adapter.source_types)
        )
        if self.policy.enabled:
            return next(
                (item for item in matches if self._adapter_authorized(item, request)),
                matches[0] if matches else None,
            )
        return matches[0] if matches else None

    def _adapter_authorized(
        self, adapter: AcquisitionAdapter, request: RawInfoRequest
    ) -> bool:
        return (
            (
                not self.policy.allowed_providers
                or adapter.provider in self.policy.allowed_providers
            )
            and (
                not self.policy.allowed_source_types
                or bool(set(request.source_types).intersection(self.policy.allowed_source_types))
            )
            and (
                not self.policy.allowed_capabilities
                or bool(set(adapter.capabilities).intersection(self.policy.allowed_capabilities))
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
    def _gap(
        request: RawInfoRequest,
        reason: DataGapReason,
        message: str,
        *,
        provider: str | None = None,
    ) -> DataGap:
        return DataGap(request.request_id, reason, message, request.source_types, provider)


def _rank_documents(
    documents: Iterable[RawInfoDocument], request: RawInfoRequest
) -> list[RawInfoDocument]:
    tokens = tuple(token.casefold() for token in _TOKEN.findall(request.query or ""))

    def key(document: RawInfoDocument) -> tuple[Any, ...]:
        hit_count = sum(document.content.casefold().count(token) for token in tokens)
        return (-hit_count, -document.available_at.timestamp(), document.document_id)

    return sorted(documents, key=key)


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
    aliases = {
        "news": {"company_news"},
        "company_news": {"news"},
        "price_daily": {"market_data", "historical_price", "prices"},
        "historical_price": {"market_data", "price_daily", "prices"},
        "prices": {"market_data", "price_daily", "historical_price"},
        "sec_company_facts": {"company_facts", "financial_statements"},
        "company_facts": {"sec_company_facts", "financial_statements"},
    }
    return any(actual in aliases.get(item, set()) for item in requested)


def _select_context_spans(
    documents: Iterable[RawInfoDocument],
    request: RawInfoRequest,
    budget: int,
) -> list[RawInfoContextSpan]:
    candidates: list[tuple[tuple[Any, ...], RawInfoContextSpan]] = []
    tokens = tuple(token.casefold() for token in _TOKEN.findall(request.query or ""))
    for document in documents:
        for start, end in _chunk_ranges(len(document.content)):
            text = document.content[start:end]
            hit_count = sum(text.casefold().count(token) for token in tokens)
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


def _chunk_ranges(length: int) -> Iterable[tuple[int, int]]:
    start = 0
    step = CONTEXT_CHUNK_CHARS - CONTEXT_CHUNK_OVERLAP
    while start < length:
        end = min(start + CONTEXT_CHUNK_CHARS, length)
        yield start, end
        if end == length:
            break
        start += step
