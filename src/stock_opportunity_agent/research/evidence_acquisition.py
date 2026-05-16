"""Evidence acquisition and context-coverage checks for cold-start packets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Literal

from stock_opportunity_agent.cases import HistoricalCase
from stock_opportunity_agent.data.documents import DocumentRecord
from stock_opportunity_agent.llm.openai import ChatMessage, OpenAIChatClient
from stock_opportunity_agent.models import (
    Catalyst,
    CatalystStatus,
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    ValidationError,
)


WEB_EVIDENCE_SCHEMA_VERSION = "web-evidence-v0.1"


@dataclass(frozen=True)
class EvidenceAcquisitionRequest:
    """One web-context request for a selected historical cold-start candidate."""

    symbol: str
    company_name: str
    inflection_date: date
    as_of_dates: tuple[date, ...]
    sector: str = "Unknown"
    industry: str = "Unknown"
    priority_themes: tuple[str, ...] = ()
    existing_document_titles: tuple[str, ...] = ()
    existing_feature_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValidationError("symbol must not be empty")
        if not self.company_name.strip():
            raise ValidationError("company_name must not be empty")
        if not self.as_of_dates:
            raise ValidationError("as_of_dates must not be empty")
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class EvidenceAcquisitionResult:
    """Evidence returned by a web-context acquisition pass."""

    documents: tuple[DocumentRecord, ...]
    catalysts: tuple[Catalyst, ...]
    queries: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextCoverageReport:
    """Coverage buckets for one built historical case packet."""

    case_id: str
    symbol: str
    as_of_date: date
    buckets: dict[str, bool]
    sufficient_context: bool
    missing_buckets: tuple[str, ...]
    mode: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible coverage report."""

        return {
            "case_id": self.case_id,
            "symbol": self.symbol,
            "as_of_date": self.as_of_date.isoformat(),
            "buckets": dict(self.buckets),
            "sufficient_context": self.sufficient_context,
            "missing_buckets": list(self.missing_buckets),
            "mode": self.mode,
        }


@dataclass(frozen=True)
class ContextCoverageGateResult:
    """Cases included or excluded after applying the context gate."""

    cases: tuple[HistoricalCase, ...]
    coverage_by_case_id: dict[str, ContextCoverageReport]
    excluded_case_ids: tuple[str, ...]


class OpenAIWebEvidenceResearcher:
    """Collect source-linked public evidence summaries before blind analysis."""

    def __init__(
        self,
        client: OpenAIChatClient,
        *,
        max_documents: int = 8,
        max_theme_documents: int = 4,
    ) -> None:
        if max_documents < 1:
            raise ValidationError("max_documents must be at least 1")
        if max_theme_documents < 0:
            raise ValidationError("max_theme_documents cannot be negative")
        self.client = client
        self.max_documents = max_documents
        self.max_theme_documents = max_theme_documents

    def collect(self, request: EvidenceAcquisitionRequest, retrieved_at: datetime) -> EvidenceAcquisitionResult:
        """Use web search to collect as-of-bounded evidence summaries."""

        queries = build_web_context_queries(request)
        response = self.client.complete(
            [
                ChatMessage(
                    "developer",
                    (
                        "You collect public, source-linked historical stock research evidence. "
                        "Use web search only for pre-packet context acquisition. Do not judge whether "
                        "the stock later won, failed, or surged. Do not use future information after "
                        "the cutoff date. Return compact JSON only."
                    ),
                ),
                ChatMessage("user", _request_prompt(request, queries, self.max_documents, self.max_theme_documents)),
            ],
            max_output_tokens=2600,
            response_format={"type": "json_object"},
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
        )
        return _result_from_json(
            request,
            response.output_text,
            retrieved_at,
            max_documents=self.max_documents,
            max_theme_documents=self.max_theme_documents,
            queries=queries,
        )


def build_web_context_queries(request: EvidenceAcquisitionRequest) -> tuple[str, ...]:
    """Return deterministic web-search queries for a candidate."""

    cutoff = request.inflection_date.isoformat()
    base = f"{request.company_name} {request.symbol}"
    queries = [
        f"{base} news contracts earnings catalysts before {cutoff}",
        f"{base} analyst report investor presentation fundamentals before {cutoff}",
        f"{base} risks dilution debt going concern short seller before {cutoff}",
    ]
    themes = [theme for theme in request.priority_themes if theme.strip()]
    if request.sector != "Unknown":
        themes.append(request.sector)
    if request.industry != "Unknown":
        themes.append(request.industry)
    for theme in tuple(dict.fromkeys(themes))[:3]:
        queries.append(f"{theme} market trend supply chain {request.company_name} before {cutoff}")
    return tuple(queries)


def apply_context_coverage_gate(
    cases: Iterable[HistoricalCase],
    *,
    mode: Literal["warn", "enforce"] = "warn",
) -> ContextCoverageGateResult:
    """Assess packet context and optionally exclude insufficient cases."""

    if mode not in {"warn", "enforce"}:
        raise ValidationError("coverage gate mode must be warn or enforce")
    case_list = tuple(cases)
    reports = {case.case_id: assess_context_coverage(case, mode=mode) for case in case_list}
    insufficient = tuple(case_id for case_id, report in reports.items() if not report.sufficient_context)
    excluded = insufficient if mode == "enforce" else ()
    if mode == "enforce":
        included = tuple(case for case in case_list if case.case_id not in excluded)
    else:
        included = case_list
    return ContextCoverageGateResult(
        cases=included,
        coverage_by_case_id=reports,
        excluded_case_ids=excluded,
    )


def assess_context_coverage(case: HistoricalCase, *, mode: str = "warn") -> ContextCoverageReport:
    """Assess whether one packet has enough context for useful learning."""

    packet = case.packet
    evidence = packet.evidence
    feature_names = {feature.name for feature in packet.features if feature.data_quality is not DataQuality.MISSING}
    evidence_kinds = {item.kind for item in evidence if item.data_quality is not DataQuality.MISSING}
    summaries = " ".join(item.summary.lower() for item in evidence)
    buckets = {
        "company_evidence": bool(
            evidence_kinds
            & {EvidenceKind.FILING, EvidenceKind.TRANSCRIPT, EvidenceKind.NEWS, EvidenceKind.RESEARCH_REPORT}
        )
        or any(name.startswith(("financial.", "valuation.", "analyst.")) for name in feature_names),
        "financial_valuation_context": any(
            name.startswith(("financial.", "valuation.", "analyst."))
            for name in feature_names
        )
        or bool(evidence_kinds & {EvidenceKind.FINANCIAL, EvidenceKind.VALUATION}),
        "theme_context": bool(evidence_kinds & {EvidenceKind.THEME_CONTEXT}) or bool(packet.theme_ids),
        "catalyst_event_context": bool(packet.catalysts)
        or any(word in summaries for word in ("catalyst", "contract", "order", "approval", "earnings", "launch")),
        "contrary_risk_context": any(
            word in summaries
            for word in ("risk", "dilution", "debt", "cash burn", "going concern", "lawsuit", "investigation", "delist")
        ),
    }
    supporting = sum(
        1
        for name, present in buckets.items()
        if name != "company_evidence" and present
    )
    sufficient = buckets["company_evidence"] and supporting >= 2
    return ContextCoverageReport(
        case_id=case.case_id,
        symbol=packet.company.ticker.symbol,
        as_of_date=packet.as_of.as_of_date,
        buckets=buckets,
        sufficient_context=sufficient,
        missing_buckets=tuple(name for name, present in buckets.items() if not present),
        mode=mode,
    )


def _request_prompt(
    request: EvidenceAcquisitionRequest,
    queries: tuple[str, ...],
    max_documents: int,
    max_theme_documents: int,
) -> str:
    payload = {
        "task": (
            "Collect source-linked public evidence available no later than the cutoff date. "
            "Prefer concrete company events, fundamentals, analyst/research commentary, theme context, "
            "and contrary/risk evidence. Summarize; do not copy full articles or reports."
        ),
        "schema_version": WEB_EVIDENCE_SCHEMA_VERSION,
        "symbol": request.symbol,
        "company_name": request.company_name,
        "sector": request.sector,
        "industry": request.industry,
        "cutoff_date": request.inflection_date.isoformat(),
        "packet_as_of_dates": [item.isoformat() for item in request.as_of_dates],
        "priority_themes": list(request.priority_themes),
        "existing_document_titles": list(request.existing_document_titles[:12]),
        "existing_feature_names": list(request.existing_feature_names[:20]),
        "queries_to_run": list(queries),
        "limits": {
            "max_documents": max_documents,
            "max_theme_documents": max_theme_documents,
        },
        "required_json_schema": {
            "documents": [
                {
                    "kind": "news | research_report | theme_context",
                    "title": "string",
                    "summary": "short source-grounded summary",
                    "source_url": "https://...",
                    "published_date": "YYYY-MM-DD",
                }
            ],
            "catalysts": [
                {
                    "name": "string",
                    "expected_date": "YYYY-MM-DD",
                    "source_title": "string",
                    "source_url": "https://...",
                    "published_date": "YYYY-MM-DD",
                }
            ],
            "warnings": ["string"],
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _result_from_json(
    request: EvidenceAcquisitionRequest,
    text: str,
    retrieved_at: datetime,
    *,
    max_documents: int,
    max_theme_documents: int,
    queries: tuple[str, ...],
) -> EvidenceAcquisitionResult:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("web evidence response was not valid JSON") from exc
    raw_documents = data.get("documents", [])
    if not isinstance(raw_documents, list):
        raise ValidationError("web evidence documents must be a list")
    documents: list[DocumentRecord] = []
    theme_count = 0
    for item in raw_documents:
        if not isinstance(item, dict):
            continue
        kind = _document_kind(item.get("kind"))
        if kind is EvidenceKind.THEME_CONTEXT:
            if theme_count >= max_theme_documents:
                continue
            theme_count += 1
        if len(documents) >= max_documents:
            break
        published = _optional_date(item.get("published_date"))
        if published is None or published > request.inflection_date:
            continue
        try:
            title = _string(item.get("title"), "document title")
            source_url = _string(item.get("source_url"), "source_url")
            summary = _string(item.get("summary"), "summary")
        except ValidationError:
            continue
        documents.append(
            DocumentRecord(
                document_id=_document_id(request.symbol, kind, title, source_url),
                symbol=request.symbol,
                kind=kind,
                title=title,
                text=summary,
                source_id=f"web:{request.symbol}:{kind.value}:{len(documents)}",
                source_url=source_url,
                published_date=published,
                available_date=published,
                retrieved_at=retrieved_at,
            )
        )
    catalysts = _catalysts_from_json(request, data.get("catalysts", []), retrieved_at)
    raw_warnings = data.get("warnings", [])
    warnings = tuple(str(item) for item in raw_warnings if isinstance(item, str))
    return EvidenceAcquisitionResult(
        documents=tuple(documents),
        catalysts=catalysts,
        queries=queries,
        warnings=warnings,
    )


def _catalysts_from_json(
    request: EvidenceAcquisitionRequest,
    raw_catalysts: object,
    retrieved_at: datetime,
) -> tuple[Catalyst, ...]:
    if not isinstance(raw_catalysts, list):
        return ()
    catalysts: list[Catalyst] = []
    for item in raw_catalysts:
        if not isinstance(item, dict):
            continue
        published = _optional_date(item.get("published_date"))
        expected = _optional_date(item.get("expected_date"))
        if published is None or expected is None or published > request.inflection_date:
            continue
        try:
            source_url = _string(item.get("source_url"), "source_url")
            name = _string(item.get("name"), "catalyst name")
        except ValidationError:
            continue
        source_title = str(item.get("source_title") or item.get("name") or "Web catalyst evidence")
        evidence = EvidenceItem(
            kind=EvidenceKind.NEWS,
            summary=f"Web catalyst evidence: {source_title}",
            as_of_date=published,
            source_id=f"web:{request.symbol}:catalyst:{len(catalysts)}",
            source_url=source_url,
            published_date=published,
        )
        catalysts.append(
            Catalyst(
                name=name,
                expected_date=expected,
                status=CatalystStatus.EXPECTED,
                evidence=[evidence],
            )
        )
    return tuple(catalysts)


def _document_kind(value: object) -> EvidenceKind:
    text = str(value or "news").strip().lower()
    if text == "research_report":
        return EvidenceKind.RESEARCH_REPORT
    if text == "theme_context":
        return EvidenceKind.THEME_CONTEXT
    return EvidenceKind.NEWS


def _optional_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _document_id(symbol: str, kind: EvidenceKind, title: str, source_url: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in f"{title}-{source_url}")
    slug = "-".join(part for part in slug.split("-") if part)
    return f"web:{symbol.upper()}:{kind.value}:{slug[:96]}"
