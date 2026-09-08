"""Audited, bounded historical source backfills into append-only Raw Info."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from stock_opportunity_agent.artifacts import (
    atomic_write_json as _atomic_write_json,
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import DataSourceError, FilingMetadata
from stock_opportunity_agent.data.sources.state import (
    DataQuotaDeferred,
    RawCacheKey,
    RawDataCache,
)
from stock_opportunity_agent.models import ValidationError


SEC_PLAN_SCHEMA = "sec-filing-backfill-plan-v1"
SEC_PROGRESS_SCHEMA = "sec-filing-backfill-progress-v1"
SEC_SUBMISSIONS_PLAN_SCHEMA = "sec-submissions-backfill-plan-v1"
SEC_SUBMISSIONS_PROGRESS_SCHEMA = "sec-submissions-backfill-progress-v1"
SEC_COMPANY_FACTS_PLAN_SCHEMA = "sec-company-facts-backfill-plan-v1"
SEC_COMPANY_FACTS_PROGRESS_SCHEMA = "sec-company-facts-backfill-progress-v1"
SEC_HISTORICAL_SUBMISSIONS_PLAN_SCHEMA = "sec-historical-submissions-plan-v1"
SEC_HISTORICAL_SUBMISSIONS_PROGRESS_SCHEMA = "sec-historical-submissions-progress-v1"
SEC_DISCOVERED_FILING_PLAN_SCHEMA = "sec-discovered-filing-backfill-plan-v1"
_SEC_ARCHIVE_HOST = "www.sec.gov"
_SEC_ARCHIVE_PREFIX = "/Archives/edgar/data/"
_SEC_DATA_HOST = "data.sec.gov"
_SEC_SUBMISSIONS_PREFIX = "/submissions/CIK"
_SEC_COMPANY_FACTS_PREFIX = "/api/xbrl/companyfacts/CIK"
_SEC_FACT_TAXONOMIES = ("dei", "ifrs-full", "srt", "us-gaap")
_SEC_FACT_FORMS = (
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
    "6-K/A",
    "8-K",
    "8-K/A",
)
_FORM_PATTERN = re.compile(
    r"(?<![A-Z0-9])(10-K(?:/A)?|10-Q(?:/A)?|8-K(?:/A)?|20-F(?:/A)?|"
    r"40-F(?:/A)?|6-K(?:/A)?)(?![A-Z0-9])",
    flags=re.IGNORECASE,
)
_FORM_PRIORITY = {
    "10-K": 0,
    "20-F": 0,
    "40-F": 0,
    "10-Q": 1,
    "8-K": 2,
    "6-K": 2,
}


class SecFilingBodyClient(Protocol):
    """Small provider boundary used by the backfill executor."""

    def filing_document_text(self, filing: FilingMetadata) -> str:
        """Return one exact SEC primary-document body."""


class SecSubmissionsClient(Protocol):
    """Small provider boundary used by submissions discovery."""

    def submissions(self, cik: str) -> dict[str, Any]:
        """Return one exact SEC submissions JSON object."""


class SecCompanyFactsClient(Protocol):
    """Small provider boundary used by Company Facts acquisition."""

    def company_facts(self, cik: str) -> dict[str, Any]:
        """Return one exact SEC Company Facts JSON object."""


class SecHistoricalSubmissionsClient(Protocol):
    """Provider boundary for exact SEC-referenced history files."""

    def historical_submissions(self, filename: str) -> dict[str, Any]:
        """Return one exact historical submissions JSON object."""


def audit_historical_data_coverage(
    *,
    cases_path: str | Path,
    documents_path: str | Path,
) -> dict[str, Any]:
    """Measure actual point-in-time document coverage without reading outcomes."""

    case_path = Path(cases_path)
    document_path = Path(documents_path)
    case_data = _read_json(case_path)
    document_data = _read_json(document_path)
    cases = case_data.get("cases", ())
    documents_by_symbol = document_data.get("documents_by_symbol", {})
    if not isinstance(cases, list):
        raise ValidationError("historical case artifact cases must be a list")
    if not isinstance(documents_by_symbol, Mapping):
        raise ValidationError("document artifact documents_by_symbol must be an object")

    kind_counts: Counter[str] = Counter()
    form_counts: Counter[str] = Counter()
    text_lengths: dict[str, list[int]] = {}
    symbols_by_form_family: dict[str, set[str]] = {
        "annual": set(),
        "quarterly": set(),
        "event": set(),
    }
    document_count = 0
    likely_truncated_sec_filings = 0
    transcript_count = 0
    normalized_documents: dict[str, list[Mapping[str, Any]]] = {}
    for raw_symbol, rows in documents_by_symbol.items():
        symbol = str(raw_symbol).upper()
        if not isinstance(rows, list):
            raise ValidationError(f"documents for {symbol} must be a list")
        normalized_rows: list[Mapping[str, Any]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValidationError(f"document for {symbol} must be an object")
            kind = str(row.get("kind", "unknown")).casefold()
            text = str(row.get("text", ""))
            kind_counts[kind] += 1
            text_lengths.setdefault(kind, []).append(len(text))
            document_count += 1
            if kind == "transcript":
                transcript_count += 1
            if kind == "filing":
                form = _filing_form(row)
                form_counts[form] += 1
                family = _form_family(form)
                if family is not None:
                    symbols_by_form_family[family].add(symbol)
                if len(text) == 1500 and _is_sec_archive_url(str(row.get("source_url", ""))):
                    likely_truncated_sec_filings += 1
            normalized_rows.append(row)
        normalized_documents[symbol] = normalized_rows

    case_coverage: Counter[str] = Counter()
    case_symbols: set[str] = set()
    unknown_profile_cases = 0
    for row in cases:
        if not isinstance(row, Mapping):
            raise ValidationError("historical case row must be an object")
        packet = row.get("packet", {})
        if not isinstance(packet, Mapping):
            raise ValidationError("historical case packet must be an object")
        company = packet.get("company", {})
        as_of = packet.get("as_of", {})
        if not isinstance(company, Mapping) or not isinstance(as_of, Mapping):
            raise ValidationError("historical case packet is missing company/as_of")
        ticker = company.get("ticker", {})
        if not isinstance(ticker, Mapping) or not ticker.get("symbol"):
            raise ValidationError("historical case is missing ticker symbol")
        symbol = str(ticker["symbol"]).upper()
        as_of_date = _parse_date(as_of.get("as_of_date"), "case as_of_date")
        case_symbols.add(symbol)
        if str(company.get("industry", "")).casefold() in {"", "unknown"}:
            unknown_profile_cases += 1
        available = [
            document
            for document in normalized_documents.get(symbol, ())
            if _document_available_date(document) <= as_of_date
        ]
        kinds = {str(document.get("kind", "unknown")).casefold() for document in available}
        has_filing = "filing" in kinds
        has_news = "news" in kinds
        if not available:
            case_coverage["no_documents"] += 1
        if not has_filing:
            case_coverage["no_filing"] += 1
        if not has_news:
            case_coverage["no_news"] += 1
        if has_filing and has_news:
            case_coverage["filing_and_news"] += 1
        elif has_filing:
            case_coverage["filing_only"] += 1
        elif has_news:
            case_coverage["news_only"] += 1

    symbol_count = len(case_symbols)
    missing_capabilities = []
    if likely_truncated_sec_filings:
        missing_capabilities.append("complete_sec_filing_bodies")
    if len(symbols_by_form_family["annual"]) < symbol_count:
        missing_capabilities.append("annual_filings")
    if case_coverage["no_news"]:
        missing_capabilities.append("point_in_time_company_news")
    if transcript_count == 0:
        missing_capabilities.append("earnings_transcripts")
    if unknown_profile_cases:
        missing_capabilities.append("point_in_time_company_profile")

    return {
        "schema_version": "historical-data-coverage-audit-v1",
        "cases_artifact": _artifact_identity(case_path),
        "documents_artifact": _artifact_identity(document_path),
        "case_count": len(cases),
        "symbol_count": symbol_count,
        "document_count": document_count,
        "document_kind_counts": dict(sorted(kind_counts.items())),
        "filing_form_counts": dict(sorted(form_counts.items())),
        "symbol_form_family_coverage": {
            family: len(symbols) for family, symbols in symbols_by_form_family.items()
        },
        "symbols_without_any_documents": sum(
            not normalized_documents.get(symbol) for symbol in case_symbols
        ),
        "case_coverage": dict(sorted(case_coverage.items())),
        "unknown_industry_case_count": unknown_profile_cases,
        "transcript_count": transcript_count,
        "likely_truncated_sec_filing_count": likely_truncated_sec_filings,
        "text_length_stats": {
            kind: _length_stats(values) for kind, values in sorted(text_lengths.items())
        },
        "missing_capabilities": missing_capabilities,
    }


def audit_expanded_acquisition_coverage(
    *,
    acquisition_scope_path: str | Path,
    documents_path: str | Path,
) -> dict[str, Any]:
    """Measure saved point-in-time documents for a label-free expanded scope."""

    scope_path = Path(acquisition_scope_path)
    document_path = Path(documents_path)
    scope = _read_json(scope_path)
    if scope.get("schema_version") != "expanded-case-acquisition-scope-v1":
        raise ValidationError("unsupported expanded acquisition scope schema")
    _assert_label_free_scope(scope)
    if scope.get("outcome_fields_included") is not False:
        raise ValidationError("expanded acquisition audit requires no outcomes")
    if scope.get("split_ownership_included") is not False:
        raise ValidationError("expanded acquisition audit requires no split ownership")
    companies = scope.get("companies")
    prediction_dates = scope.get("prediction_dates")
    if not isinstance(companies, list) or not isinstance(prediction_dates, list):
        raise ValidationError("expanded acquisition scope is incomplete")
    dates = [_parse_date(value, "acquisition prediction date") for value in prediction_dates]
    document_data = _read_json(document_path)
    documents_by_symbol = document_data.get("documents_by_symbol", {})
    if not isinstance(documents_by_symbol, Mapping):
        raise ValidationError("document artifact documents_by_symbol must be an object")

    company_coverage: Counter[str] = Counter()
    observation_coverage: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    form_counts: Counter[str] = Counter()
    selected_document_count = 0
    existing_sec_primary_urls = 0
    likely_truncated_sec_filings = 0
    missing_cik = 0
    for company in companies:
        if not isinstance(company, Mapping):
            raise ValidationError("expanded acquisition company must be an object")
        symbol = str(company.get("symbol") or "").upper()
        if not symbol:
            raise ValidationError("expanded acquisition company is missing symbol")
        missing_cik += int(_normalize_cik(company.get("cik")) is None)
        raw_rows = documents_by_symbol.get(symbol, ())
        if not isinstance(raw_rows, (list, tuple)):
            raise ValidationError(f"documents for {symbol} must be a list")
        rows: list[Mapping[str, Any]] = []
        for row in raw_rows:
            if not isinstance(row, Mapping):
                raise ValidationError(f"document for {symbol} must be an object")
            rows.append(row)
            kind = str(row.get("kind", "unknown")).casefold()
            kind_counts[kind] += 1
            selected_document_count += 1
            if kind == "filing":
                form_counts[_filing_form(row)] += 1
                source_url = str(row.get("source_url", ""))
                if _is_sec_archive_url(source_url):
                    existing_sec_primary_urls += 1
                    if len(str(row.get("text", ""))) == 1500:
                        likely_truncated_sec_filings += 1
        kinds = {str(row.get("kind", "unknown")).casefold() for row in rows}
        company_coverage["with_any_documents" if rows else "without_documents"] += 1
        company_coverage["with_filing" if "filing" in kinds else "without_filing"] += 1
        company_coverage["with_news" if "news" in kinds else "without_news"] += 1
        for prediction_date in dates:
            available = [
                row for row in rows if _document_available_date(row) <= prediction_date
            ]
            available_kinds = {
                str(row.get("kind", "unknown")).casefold() for row in available
            }
            has_filing = "filing" in available_kinds
            has_news = "news" in available_kinds
            if not available:
                observation_coverage["no_documents"] += 1
            if not has_filing:
                observation_coverage["no_filing"] += 1
            if not has_news:
                observation_coverage["no_news"] += 1
            if has_filing and has_news:
                observation_coverage["filing_and_news"] += 1
            elif has_filing:
                observation_coverage["filing_only"] += 1
            elif has_news:
                observation_coverage["news_only"] += 1

    return {
        "schema_version": "expanded-acquisition-coverage-audit-v1",
        "acquisition_scope": _artifact_identity(scope_path),
        "documents_artifact": _artifact_identity(document_path),
        "company_count": len(companies),
        "prediction_dates": [value.isoformat() for value in dates],
        "case_observation_count": len(companies) * len(dates),
        "company_coverage": dict(sorted(company_coverage.items())),
        "point_in_time_observation_coverage": dict(
            sorted(observation_coverage.items())
        ),
        "saved_document_count": selected_document_count,
        "saved_document_kind_counts": dict(sorted(kind_counts.items())),
        "saved_filing_form_counts": dict(sorted(form_counts.items())),
        "existing_sec_primary_url_count": existing_sec_primary_urls,
        "likely_truncated_sec_filing_count": likely_truncated_sec_filings,
        "missing_cik_count": missing_cik,
        "missing_capabilities": [
            "historical_registrant_identity",
            "complete_sec_filing_bodies",
            "annual_and_quarterly_filings",
            "point_in_time_company_profile",
            "point_in_time_company_news",
            "earnings_transcripts",
        ],
        "outcome_fields_read": False,
        "split_ownership_read": False,
        "external_calls": 0,
    }


def write_sec_filing_backfill_plan(
    *,
    documents_path: str | Path,
    output_path: str | Path,
    forms: Iterable[str] = (),
) -> dict[str, Any]:
    """Write a deterministic, exact, label-free plan for legacy SEC bodies."""

    source_path = Path(documents_path)
    data = _read_json(source_path)
    documents_by_symbol = data.get("documents_by_symbol", {})
    if not isinstance(documents_by_symbol, Mapping):
        raise ValidationError("document artifact documents_by_symbol must be an object")
    selected_forms = {_normalize_form(value) for value in forms if str(value).strip()}
    items_by_id: dict[str, dict[str, Any]] = {}
    for raw_symbol, rows in documents_by_symbol.items():
        symbol = str(raw_symbol).upper()
        if not isinstance(rows, list):
            raise ValidationError(f"documents for {symbol} must be a list")
        for row in rows:
            if not isinstance(row, Mapping) or str(row.get("kind", "")).casefold() != "filing":
                continue
            source_url = str(row.get("source_url", ""))
            if not _is_sec_archive_url(source_url):
                continue
            form = _filing_form(row)
            if selected_forms and form not in selected_forms:
                continue
            published_date = _parse_date(row.get("published_date"), "published_date")
            legacy_available_date = _document_available_date(row)
            source_id = str(row.get("source_id") or row.get("document_id") or "")
            cik, accession = _sec_identity(source_id, source_url)
            item_seed = {
                "source_id": source_id,
                "source_url": source_url,
                "legacy_available_date": legacy_available_date.isoformat(),
            }
            item_id = "secitem_" + _canonical_hash(item_seed)[:24]
            item = {
                "item_id": item_id,
                "symbol": symbol,
                "company_id": _company_id_from_symbol(symbol),
                "original_document_id": str(row.get("document_id") or source_id),
                "source_id": source_id,
                "source_url": source_url,
                "cik": cik,
                "accession_number": accession,
                "primary_document": Path(urlsplit(source_url).path).name,
                "form": form,
                "published_at": _midnight_utc(published_date).isoformat(),
                "available_at": _midnight_utc(
                    legacy_available_date + timedelta(days=1)
                ).isoformat(),
                "legacy_content_chars": len(str(row.get("text", ""))),
            }
            existing = items_by_id.get(item_id)
            if existing is not None and existing != item:
                raise ValidationError(f"conflicting SEC backfill item: {item_id}")
            items_by_id[item_id] = item

    items = sorted(
        items_by_id.values(),
        key=lambda item: (
            _FORM_PRIORITY.get(_base_form(str(item["form"])), 9),
            item["published_at"],
            item["symbol"],
            item["item_id"],
        ),
    )
    payload: dict[str, Any] = {
        "schema_version": SEC_PLAN_SCHEMA,
        "source_artifact": _artifact_identity(source_path),
        "selection": {
            "kind": "filing",
            "forms": sorted(selected_forms),
            "allowed_url_prefix": f"https://{_SEC_ARCHIVE_HOST}{_SEC_ARCHIVE_PREFIX}",
            "availability_policy": "next_utc_day_after_legacy_available_date",
        },
        "request_count": len(items),
        "items": items,
    }
    payload["plan_hash"] = _canonical_hash(payload)
    _atomic_write_json(Path(output_path), payload)
    return payload


def write_sec_submissions_backfill_plan(
    *,
    acquisition_scope_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Write exact per-CIK SEC discovery requests from a label-free scope."""

    source_path = Path(acquisition_scope_path)
    scope = _read_json(source_path)
    if scope.get("schema_version") != "expanded-case-acquisition-scope-v1":
        raise ValidationError("unsupported expanded acquisition scope schema")
    if scope.get("outcome_fields_included") is not False:
        raise ValidationError("SEC discovery scope must exclude outcome fields")
    if scope.get("split_ownership_included") is not False:
        raise ValidationError("SEC discovery scope must exclude split ownership")
    _assert_label_free_scope(scope)
    companies = scope.get("companies")
    prediction_dates = scope.get("prediction_dates")
    if not isinstance(companies, list):
        raise ValidationError("expanded acquisition scope companies must be a list")
    if int(scope.get("company_count", -1)) != len(companies):
        raise ValidationError("expanded acquisition scope company count mismatch")
    if not isinstance(prediction_dates, list) or not prediction_dates:
        raise ValidationError("expanded acquisition scope prediction dates are missing")
    parsed_dates = sorted(
        _parse_date(value, "acquisition prediction date") for value in prediction_dates
    )
    items_by_cik: dict[str, dict[str, Any]] = {}
    missing_cik: list[dict[str, str]] = []
    for company in companies:
        if not isinstance(company, Mapping):
            raise ValidationError("expanded acquisition company must be an object")
        symbol = str(company.get("symbol") or "").upper()
        company_id = str(company.get("company_id") or "")
        if not symbol or not company_id:
            raise ValidationError("expanded acquisition company identity is incomplete")
        cik = _normalize_cik(company.get("cik"))
        if cik is None:
            missing_cik.append({"company_id": company_id, "symbol": symbol})
            continue
        item = {
            "item_id": f"secsub_{cik}",
            "company_id": company_id,
            "symbol": symbol,
            "cik": cik,
            "source_url": f"https://{_SEC_DATA_HOST}/submissions/CIK{cik}.json",
            "required_as_of_min": parsed_dates[0].isoformat(),
            "required_as_of_max": parsed_dates[-1].isoformat(),
        }
        existing = items_by_cik.get(cik)
        if existing is not None and existing != item:
            raise ValidationError(f"conflicting SEC submissions CIK in scope: {cik}")
        items_by_cik[cik] = item
    items = sorted(items_by_cik.values(), key=lambda item: str(item["cik"]))
    payload: dict[str, Any] = {
        "schema_version": SEC_SUBMISSIONS_PLAN_SCHEMA,
        "source_artifact": _artifact_identity(source_path),
        "selection": {
            "kind": "sec_submissions_metadata",
            "allowed_url_pattern": (
                f"https://{_SEC_DATA_HOST}{_SEC_SUBMISSIONS_PREFIX}##########.json"
            ),
            "prediction_dates": [value.isoformat() for value in parsed_dates],
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
        "request_count": len(items),
        "missing_cik_count": len(missing_cik),
        "missing_cik": sorted(missing_cik, key=lambda item: item["company_id"]),
        "items": items,
    }
    payload["plan_hash"] = _canonical_hash(payload)
    _atomic_write_json(Path(output_path), payload)
    return payload


def load_sec_submissions_backfill_plan(path: str | Path) -> dict[str, Any]:
    """Load and validate one exact SEC submissions discovery plan."""

    payload = _read_json(Path(path))
    if payload.get("schema_version") != SEC_SUBMISSIONS_PLAN_SCHEMA:
        raise ValidationError("unsupported SEC submissions backfill plan schema")
    supplied_hash = str(payload.get("plan_hash", ""))
    without_hash = dict(payload)
    without_hash.pop("plan_hash", None)
    if supplied_hash != _canonical_hash(without_hash):
        raise ValidationError("SEC submissions backfill plan hash mismatch")
    items = payload.get("items")
    if not isinstance(items, list) or int(payload.get("request_count", -1)) != len(items):
        raise ValidationError("SEC submissions backfill plan item count mismatch")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ValidationError("SEC submissions backfill item must be an object")
        cik = _normalize_cik(item.get("cik"))
        if cik is None or cik in seen:
            raise ValidationError("SEC submissions backfill CIKs must be unique")
        seen.add(cik)
        expected = f"https://{_SEC_DATA_HOST}/submissions/CIK{cik}.json"
        if item.get("source_url") != expected:
            raise ValidationError("SEC submissions backfill contains an invalid URL")
    return payload


def preview_sec_submissions_backfill(
    *,
    plan_path: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
) -> dict[str, Any]:
    """Describe exact SEC discovery work without network I/O or writes."""

    plan = load_sec_submissions_backfill_plan(plan_path)
    progress = _load_submissions_progress(
        Path(progress_path), str(plan["plan_hash"])
    )
    completed = dict(progress.get("completed", {}))
    cached = 0
    pending = 0
    for item in plan["items"]:
        if item["item_id"] in completed:
            continue
        pending += 1
        key = RawCacheKey.from_request(
            "sec_edgar",
            DataCapability.FILINGS,
            "GET",
            str(item["source_url"]),
        )
        cached += int(cache.get_json(key) is not None)
    return {
        "status": "zero_network_preview",
        "stage": "sec_submissions_metadata",
        "plan_hash": plan["plan_hash"],
        "request_count": plan["request_count"],
        "missing_cik_count": plan["missing_cik_count"],
        "completed_count": len(completed),
        "pending_count": pending,
        "pending_cache_hits": cached,
        "maximum_new_network_requests": pending - cached,
        "filing_bodies_completed": 0,
        "external_calls": 0,
    }


def run_sec_submissions_backfill(
    *,
    plan_path: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
    client: SecSubmissionsClient,
    max_network_requests: int,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute/resume bounded SEC submissions discovery into raw cache."""

    if max_network_requests < 0:
        raise ValidationError("max_network_requests must be non-negative")
    plan = load_sec_submissions_backfill_plan(plan_path)
    plan_hash = str(plan["plan_hash"])
    state_path = Path(progress_path)
    progress = _load_submissions_progress(state_path, plan_hash)
    completed: dict[str, Any] = dict(progress.get("completed", {}))
    failures: list[dict[str, Any]] = list(progress.get("failures", ()))
    network_requests = 0
    cache_hits = 0
    failures_this_run = 0
    last_stop = "plan_exhausted"
    for item_index, item in enumerate(plan["items"], start=1):
        item_id = str(item["item_id"])
        if item_id in completed:
            continue
        key = RawCacheKey.from_request(
            "sec_edgar",
            DataCapability.FILINGS,
            "GET",
            str(item["source_url"]),
        )
        was_cached = cache.get_json(key) is not None
        if not was_cached and network_requests >= max_network_requests:
            last_stop = "invocation_network_limit_reached"
            _emit_progress(
                on_progress,
                stage="sec_submissions_metadata",
                status="paused_network_limit",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=False,
            )
            break
        _emit_progress(
            on_progress,
            stage="sec_submissions_metadata",
            status="starting",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )
        try:
            response = client.submissions(str(item["cik"]))
            _validate_submissions_response(response, str(item["cik"]))
        except DataQuotaDeferred as exc:
            last_stop = "source_quota_deferred"
            progress["last_deferred"] = {
                "item_id": item_id,
                "next_retry_at": exc.next_retry_at.isoformat(),
                "reason": exc.reason,
            }
            _store_progress(
                state_path, progress, completed, failures, last_stop, now()
            )
            _emit_progress(
                on_progress,
                stage="sec_submissions_metadata",
                status="quota_deferred",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=was_cached,
            )
            break
        except Exception as exc:
            if not was_cached:
                network_requests += 1
            failures_this_run += 1
            failures.append(
                {
                    "item_id": item_id,
                    "at": now().isoformat(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            last_stop = "item_failed"
            _store_progress(
                state_path, progress, completed, failures, last_stop, now()
            )
            _emit_progress(
                on_progress,
                stage="sec_submissions_metadata",
                status="failed",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=was_cached,
            )
            continue
        if was_cached:
            cache_hits += 1
        else:
            network_requests += 1
        cached = cache.get(key)
        retrieved_at = cached.retrieved_at if cached is not None else now()
        recent = response.get("filings", {}).get("recent", {})
        files = response.get("filings", {}).get("files", ())
        recent_accessions = recent.get("accessionNumber", ()) if isinstance(recent, Mapping) else ()
        completed[item_id] = {
            "cache_key": key.digest,
            "response_hash": _canonical_hash(response),
            "recent_filing_count": len(recent_accessions)
            if isinstance(recent_accessions, list)
            else 0,
            "referenced_historical_file_count": len(files)
            if isinstance(files, list)
            else 0,
            "retrieved_at": retrieved_at.isoformat(),
            "completed_at": now().isoformat(),
        }
        last_stop = "item_completed"
        _store_progress(
            state_path, progress, completed, failures, last_stop, now()
        )
        _emit_progress(
            on_progress,
            stage="sec_submissions_metadata",
            status="completed",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )
    pending_count = len(plan["items"]) - len(completed)
    status = "completed" if pending_count == 0 else "paused_resumable"
    _store_progress(
        state_path, progress, completed, failures, last_stop, now()
    )
    return {
        "status": status,
        "stage": "sec_submissions_metadata",
        "plan_hash": plan_hash,
        "request_count": plan["request_count"],
        "missing_cik_count": plan["missing_cik_count"],
        "completed_count": len(completed),
        "pending_count": pending_count,
        "network_requests_this_run": network_requests,
        "cache_hits_this_run": cache_hits,
        "failures_this_run": failures_this_run,
        "filing_bodies_completed": 0,
        "last_stop": last_stop,
        "progress_path": str(state_path.resolve()),
    }


def write_sec_company_facts_backfill_plan(
    *,
    acquisition_scope_path: str | Path,
    output_path: str | Path,
    period_lookback_days: int = 1100,
) -> dict[str, Any]:
    """Write exact per-CIK SEC Company Facts requests from a label-free scope."""

    if period_lookback_days < 1:
        raise ValidationError("period_lookback_days must be positive")
    source_path = Path(acquisition_scope_path)
    scope = _read_json(source_path)
    if scope.get("schema_version") != "expanded-case-acquisition-scope-v1":
        raise ValidationError("unsupported expanded acquisition scope schema")
    if scope.get("outcome_fields_included") is not False:
        raise ValidationError("SEC Company Facts scope must exclude outcome fields")
    if scope.get("split_ownership_included") is not False:
        raise ValidationError("SEC Company Facts scope must exclude split ownership")
    _assert_label_free_scope(scope)
    companies = scope.get("companies")
    prediction_dates = scope.get("prediction_dates")
    if not isinstance(companies, list):
        raise ValidationError("expanded acquisition scope companies must be a list")
    if int(scope.get("company_count", -1)) != len(companies):
        raise ValidationError("expanded acquisition scope company count mismatch")
    if not isinstance(prediction_dates, list) or not prediction_dates:
        raise ValidationError("expanded acquisition scope prediction dates are missing")
    parsed_dates = sorted(
        _parse_date(value, "acquisition prediction date") for value in prediction_dates
    )
    period_end_from = parsed_dates[0] - timedelta(days=period_lookback_days)
    items_by_cik: dict[str, dict[str, Any]] = {}
    missing_cik: list[dict[str, str]] = []
    for company in companies:
        if not isinstance(company, Mapping):
            raise ValidationError("expanded acquisition company must be an object")
        symbol = str(company.get("symbol") or "").upper()
        company_id = str(company.get("company_id") or "")
        if not symbol or not company_id:
            raise ValidationError("expanded acquisition company identity is incomplete")
        cik = _normalize_cik(company.get("cik"))
        if cik is None:
            missing_cik.append({"company_id": company_id, "symbol": symbol})
            continue
        item = {
            "item_id": f"secfacts_{cik}",
            "company_id": company_id,
            "symbol": symbol,
            "cik": cik,
            "source_url": (
                f"https://{_SEC_DATA_HOST}{_SEC_COMPANY_FACTS_PREFIX}{cik}.json"
            ),
            "required_as_of_min": parsed_dates[0].isoformat(),
            "required_as_of_max": parsed_dates[-1].isoformat(),
        }
        existing = items_by_cik.get(cik)
        if existing is not None and existing != item:
            raise ValidationError(f"conflicting SEC Company Facts CIK in scope: {cik}")
        items_by_cik[cik] = item
    items = sorted(items_by_cik.values(), key=lambda item: str(item["cik"]))
    payload: dict[str, Any] = {
        "schema_version": SEC_COMPANY_FACTS_PLAN_SCHEMA,
        "source_artifact": _artifact_identity(source_path),
        "selection": {
            "kind": "sec_company_facts",
            "allowed_url_pattern": (
                f"https://{_SEC_DATA_HOST}{_SEC_COMPANY_FACTS_PREFIX}##########.json"
            ),
            "prediction_dates": [value.isoformat() for value in parsed_dates],
            "period_lookback_days": period_lookback_days,
            "period_end_from": period_end_from.isoformat(),
            "period_end_through": parsed_dates[-1].isoformat(),
            "available_at_through": _midnight_utc(parsed_dates[-1]).isoformat(),
            "taxonomy_allowlist": list(_SEC_FACT_TAXONOMIES),
            "form_allowlist": list(_SEC_FACT_FORMS),
            "availability_policy": "next_utc_day_after_companyfacts_filed_date",
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
        "request_count": len(items),
        "missing_cik_count": len(missing_cik),
        "missing_cik": sorted(missing_cik, key=lambda item: item["company_id"]),
        "items": items,
    }
    payload["plan_hash"] = _canonical_hash(payload)
    _atomic_write_json(Path(output_path), payload)
    return payload


def load_sec_company_facts_backfill_plan(path: str | Path) -> dict[str, Any]:
    """Load and validate one exact SEC Company Facts plan."""

    payload = _read_json(Path(path))
    if payload.get("schema_version") != SEC_COMPANY_FACTS_PLAN_SCHEMA:
        raise ValidationError("unsupported SEC Company Facts backfill plan schema")
    supplied_hash = str(payload.get("plan_hash", ""))
    without_hash = dict(payload)
    without_hash.pop("plan_hash", None)
    if supplied_hash != _canonical_hash(without_hash):
        raise ValidationError("SEC Company Facts backfill plan hash mismatch")
    selection = payload.get("selection")
    if not isinstance(selection, Mapping):
        raise ValidationError("SEC Company Facts backfill selection is missing")
    if selection.get("outcome_fields_included") is not False:
        raise ValidationError("SEC Company Facts plan must exclude outcome fields")
    if selection.get("split_ownership_included") is not False:
        raise ValidationError("SEC Company Facts plan must exclude split ownership")
    if tuple(selection.get("taxonomy_allowlist", ())) != _SEC_FACT_TAXONOMIES:
        raise ValidationError("SEC Company Facts taxonomy allow-list is invalid")
    if tuple(selection.get("form_allowlist", ())) != _SEC_FACT_FORMS:
        raise ValidationError("SEC Company Facts form allow-list is invalid")
    _parse_date(selection.get("period_end_from"), "fact period_end_from")
    _parse_date(selection.get("period_end_through"), "fact period_end_through")
    _parse_datetime(
        selection.get("available_at_through"), "fact available_at_through"
    )
    items = payload.get("items")
    if not isinstance(items, list) or int(payload.get("request_count", -1)) != len(items):
        raise ValidationError("SEC Company Facts plan item count mismatch")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ValidationError("SEC Company Facts item must be an object")
        cik = _normalize_cik(item.get("cik"))
        if cik is None or cik in seen:
            raise ValidationError("SEC Company Facts CIKs must be unique")
        seen.add(cik)
        expected = (
            f"https://{_SEC_DATA_HOST}{_SEC_COMPANY_FACTS_PREFIX}{cik}.json"
        )
        if item.get("source_url") != expected:
            raise ValidationError("SEC Company Facts plan contains an invalid URL")
    return payload


def preview_sec_company_facts_backfill(
    *,
    plan_path: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
) -> dict[str, Any]:
    """Describe exact Company Facts work without network I/O or writes."""

    plan = load_sec_company_facts_backfill_plan(plan_path)
    progress = _load_company_facts_progress(
        Path(progress_path), str(plan["plan_hash"])
    )
    completed = dict(progress.get("completed", {}))
    cached = 0
    pending = 0
    for item in plan["items"]:
        if item["item_id"] in completed:
            continue
        pending += 1
        key = _company_facts_cache_key(item)
        cached += int(cache.get_json(key) is not None)
    return {
        "status": "zero_network_preview",
        "stage": "sec_company_facts",
        "plan_hash": plan["plan_hash"],
        "request_count": plan["request_count"],
        "missing_cik_count": plan["missing_cik_count"],
        "completed_count": len(completed),
        "pending_count": pending,
        "pending_cache_hits": cached,
        "maximum_new_network_requests": pending - cached,
        "fact_document_count": sum(
            int(row.get("fact_document_count", 0)) for row in completed.values()
        ),
        "external_calls": 0,
    }


def run_sec_company_facts_backfill(
    *,
    plan_path: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
    raw_info_root: str | Path,
    client: SecCompanyFactsClient,
    max_network_requests: int,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute/resume bounded SEC Company Facts acquisition and materialization."""

    if max_network_requests < 0:
        raise ValidationError("max_network_requests must be non-negative")
    plan = load_sec_company_facts_backfill_plan(plan_path)
    plan_hash = str(plan["plan_hash"])
    state_path = Path(progress_path)
    progress = _load_company_facts_progress(state_path, plan_hash)
    completed: dict[str, Any] = dict(progress.get("completed", {}))
    failures: list[dict[str, Any]] = list(progress.get("failures", ()))
    store = RawInfoStore(raw_info_root)
    network_requests = 0
    cache_hits = 0
    failures_this_run = 0
    appended_this_run = 0
    reused_this_run = 0
    last_stop = "plan_exhausted"
    for item_index, item in enumerate(plan["items"], start=1):
        item_id = str(item["item_id"])
        if item_id in completed:
            continue
        key = _company_facts_cache_key(item)
        was_cached = cache.get_json(key) is not None
        if not was_cached and network_requests >= max_network_requests:
            last_stop = "invocation_network_limit_reached"
            _emit_progress(
                on_progress,
                stage="sec_company_facts",
                status="paused_network_limit",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=False,
            )
            break
        _emit_progress(
            on_progress,
            stage="sec_company_facts",
            status="starting",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )
        try:
            response = client.company_facts(str(item["cik"]))
            _validate_company_facts_response(response, str(item["cik"]))
            cached = cache.get(key)
            retrieved_at = cached.retrieved_at if cached is not None else now()
            documents, extraction = _company_fact_documents(
                response,
                item=item,
                selection=plan["selection"],
                plan_hash=plan_hash,
                retrieved_at=retrieved_at,
            )
            appended = 0
            reused = 0
            for document in documents:
                if store.append(document):
                    appended += 1
                else:
                    reused += 1
        except DataQuotaDeferred as exc:
            last_stop = "source_quota_deferred"
            progress["last_deferred"] = {
                "item_id": item_id,
                "next_retry_at": exc.next_retry_at.isoformat(),
                "reason": exc.reason,
            }
            _store_progress(
                state_path, progress, completed, failures, last_stop, now()
            )
            _emit_progress(
                on_progress,
                stage="sec_company_facts",
                status="quota_deferred",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=was_cached,
            )
            break
        except Exception as exc:
            if not was_cached:
                network_requests += 1
            failures_this_run += 1
            failures.append(
                {
                    "item_id": item_id,
                    "at": now().isoformat(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            last_stop = "item_failed"
            _store_progress(
                state_path, progress, completed, failures, last_stop, now()
            )
            _emit_progress(
                on_progress,
                stage="sec_company_facts",
                status="failed",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=was_cached,
            )
            continue
        if was_cached:
            cache_hits += 1
        else:
            network_requests += 1
        appended_this_run += appended
        reused_this_run += reused
        completed[item_id] = {
            "cache_key": key.digest,
            "response_hash": _canonical_hash(response),
            "raw_fact_row_count": extraction["raw_fact_row_count"],
            "selected_fact_row_count": extraction["selected_fact_row_count"],
            "fact_document_count": len(documents),
            "appended_document_count": appended,
            "reused_document_count": reused,
            "excluded_reason_counts": extraction["excluded_reason_counts"],
            "retrieved_at": retrieved_at.isoformat(),
            "completed_at": now().isoformat(),
        }
        last_stop = "item_completed"
        _store_progress(
            state_path, progress, completed, failures, last_stop, now()
        )
        _emit_progress(
            on_progress,
            stage="sec_company_facts",
            status="completed",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )
    pending_count = len(plan["items"]) - len(completed)
    status = "completed" if pending_count == 0 else "paused_resumable"
    _store_progress(
        state_path, progress, completed, failures, last_stop, now()
    )
    return {
        "status": status,
        "stage": "sec_company_facts",
        "plan_hash": plan_hash,
        "request_count": plan["request_count"],
        "missing_cik_count": plan["missing_cik_count"],
        "completed_count": len(completed),
        "pending_count": pending_count,
        "network_requests_this_run": network_requests,
        "cache_hits_this_run": cache_hits,
        "failures_this_run": failures_this_run,
        "fact_document_count": sum(
            int(row.get("fact_document_count", 0)) for row in completed.values()
        ),
        "selected_fact_row_count": sum(
            int(row.get("selected_fact_row_count", 0))
            for row in completed.values()
        ),
        "zero_fact_company_count": sum(
            int(row.get("fact_document_count", 0)) == 0
            for row in completed.values()
        ),
        "appended_documents_this_run": appended_this_run,
        "reused_documents_this_run": reused_this_run,
        "last_stop": last_stop,
        "progress_path": str(state_path.resolve()),
        "raw_info_root": str(Path(raw_info_root).resolve()),
    }


def write_sec_historical_submissions_plan(
    *,
    primary_plan_path: str | Path,
    cache: RawDataCache,
    output_path: str | Path,
    metadata_lookback_days: int = 550,
) -> dict[str, Any]:
    """Derive exact SEC history-file requests from cached primary submissions."""

    if metadata_lookback_days < 1:
        raise ValidationError("metadata_lookback_days must be positive")
    primary_path = Path(primary_plan_path)
    primary = load_sec_submissions_backfill_plan(primary_path)
    raw_dates = primary.get("selection", {}).get("prediction_dates", ())
    if not isinstance(raw_dates, list) or not raw_dates:
        raise ValidationError("primary SEC plan prediction dates are missing")
    prediction_dates = sorted(
        _parse_date(value, "SEC primary prediction date") for value in raw_dates
    )
    window_start = prediction_dates[0] - timedelta(days=metadata_lookback_days)
    window_end = prediction_dates[-1]
    missing_primary: list[str] = []
    items_by_id: dict[str, dict[str, Any]] = {}
    for primary_item in primary["items"]:
        key = RawCacheKey.from_request(
            "sec_edgar",
            DataCapability.FILINGS,
            "GET",
            str(primary_item["source_url"]),
        )
        response = cache.get_json(key)
        if response is None:
            missing_primary.append(str(primary_item["item_id"]))
            continue
        _validate_submissions_response(response, str(primary_item["cik"]))
        files = response.get("filings", {}).get("files", ())
        if not isinstance(files, list):
            raise DataSourceError("SEC submissions response filings.files must be a list")
        for file_row in files:
            if not isinstance(file_row, Mapping):
                raise DataSourceError("SEC historical submissions reference must be an object")
            filename = _validated_sec_history_filename(file_row.get("name"))
            filing_from = _parse_date(
                file_row.get("filingFrom"), "SEC history filingFrom"
            )
            filing_to = _parse_date(file_row.get("filingTo"), "SEC history filingTo")
            if filing_to < filing_from:
                raise DataSourceError("SEC history filing range is reversed")
            if filing_to < window_start or filing_from > window_end:
                continue
            item_id = "sechist_" + _canonical_hash(
                {"cik": primary_item["cik"], "filename": filename}
            )[:24]
            item = {
                "item_id": item_id,
                "company_id": primary_item["company_id"],
                "symbol": primary_item["symbol"],
                "cik": primary_item["cik"],
                "filename": filename,
                "source_url": f"https://{_SEC_DATA_HOST}/submissions/{filename}",
                "filing_from": filing_from.isoformat(),
                "filing_to": filing_to.isoformat(),
                "filing_count": int(file_row.get("filingCount") or 0),
            }
            existing = items_by_id.get(item_id)
            if existing is not None and existing != item:
                raise ValidationError(f"conflicting SEC history plan item: {item_id}")
            items_by_id[item_id] = item
    if missing_primary:
        raise ValidationError(
            "SEC primary submissions cache is incomplete for historical planning: "
            f"{len(missing_primary)} missing"
        )
    items = sorted(
        items_by_id.values(),
        key=lambda item: (item["cik"], item["filing_from"], item["filename"]),
    )
    payload: dict[str, Any] = {
        "schema_version": SEC_HISTORICAL_SUBMISSIONS_PLAN_SCHEMA,
        "source_artifact": _artifact_identity(primary_path),
        "parent_plan_hash": primary["plan_hash"],
        "selection": {
            "kind": "sec_historical_submissions_metadata",
            "metadata_lookback_days": metadata_lookback_days,
            "metadata_window_start": window_start.isoformat(),
            "metadata_window_end": window_end.isoformat(),
            "prediction_dates": [value.isoformat() for value in prediction_dates],
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
        "primary_response_count": len(primary["items"]),
        "request_count": len(items),
        "items": items,
    }
    payload["plan_hash"] = _canonical_hash(payload)
    _atomic_write_json(Path(output_path), payload)
    return payload


def load_sec_historical_submissions_plan(path: str | Path) -> dict[str, Any]:
    """Load and validate an exact SEC historical-submissions plan."""

    payload = _read_json(Path(path))
    if payload.get("schema_version") != SEC_HISTORICAL_SUBMISSIONS_PLAN_SCHEMA:
        raise ValidationError("unsupported SEC historical submissions plan schema")
    supplied_hash = str(payload.get("plan_hash", ""))
    without_hash = dict(payload)
    without_hash.pop("plan_hash", None)
    if supplied_hash != _canonical_hash(without_hash):
        raise ValidationError("SEC historical submissions plan hash mismatch")
    items = payload.get("items")
    if not isinstance(items, list) or int(payload.get("request_count", -1)) != len(items):
        raise ValidationError("SEC historical submissions plan item count mismatch")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ValidationError("SEC historical submissions item must be an object")
        item_id = str(item.get("item_id") or "")
        if not item_id or item_id in seen:
            raise ValidationError("SEC historical submissions item ids must be unique")
        seen.add(item_id)
        filename = _validated_sec_history_filename(item.get("filename"))
        if item.get("source_url") != f"https://{_SEC_DATA_HOST}/submissions/{filename}":
            raise ValidationError("SEC historical submissions plan contains invalid URL")
        if _parse_date(item.get("filing_to"), "filing_to") < _parse_date(
            item.get("filing_from"), "filing_from"
        ):
            raise ValidationError("SEC historical submissions range is reversed")
    return payload


def preview_sec_historical_submissions_backfill(
    *,
    plan_path: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
) -> dict[str, Any]:
    """Describe exact historical metadata work without network I/O or writes."""

    plan = load_sec_historical_submissions_plan(plan_path)
    progress = _load_historical_submissions_progress(
        Path(progress_path), str(plan["plan_hash"])
    )
    completed = dict(progress.get("completed", {}))
    cached = 0
    pending = 0
    for item in plan["items"]:
        if item["item_id"] in completed:
            continue
        pending += 1
        key = RawCacheKey.from_request(
            "sec_edgar",
            DataCapability.FILINGS,
            "GET",
            str(item["source_url"]),
        )
        cached += int(cache.get_json(key) is not None)
    return {
        "status": "zero_network_preview",
        "stage": "sec_historical_submissions_metadata",
        "plan_hash": plan["plan_hash"],
        "request_count": plan["request_count"],
        "completed_count": len(completed),
        "pending_count": pending,
        "pending_cache_hits": cached,
        "maximum_new_network_requests": pending - cached,
        "filing_bodies_completed": 0,
        "external_calls": 0,
    }


def run_sec_historical_submissions_backfill(
    *,
    plan_path: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
    client: SecHistoricalSubmissionsClient,
    max_network_requests: int,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute/resume bounded SEC historical submissions discovery."""

    if max_network_requests < 0:
        raise ValidationError("max_network_requests must be non-negative")
    plan = load_sec_historical_submissions_plan(plan_path)
    plan_hash = str(plan["plan_hash"])
    state_path = Path(progress_path)
    progress = _load_historical_submissions_progress(state_path, plan_hash)
    completed: dict[str, Any] = dict(progress.get("completed", {}))
    failures: list[dict[str, Any]] = list(progress.get("failures", ()))
    network_requests = 0
    cache_hits = 0
    failures_this_run = 0
    last_stop = "plan_exhausted"
    for item_index, item in enumerate(plan["items"], start=1):
        item_id = str(item["item_id"])
        if item_id in completed:
            continue
        key = RawCacheKey.from_request(
            "sec_edgar",
            DataCapability.FILINGS,
            "GET",
            str(item["source_url"]),
        )
        was_cached = cache.get_json(key) is not None
        if not was_cached and network_requests >= max_network_requests:
            last_stop = "invocation_network_limit_reached"
            _emit_progress(
                on_progress,
                stage="sec_historical_submissions_metadata",
                status="paused_network_limit",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=False,
            )
            break
        _emit_progress(
            on_progress,
            stage="sec_historical_submissions_metadata",
            status="starting",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )
        try:
            response = client.historical_submissions(str(item["filename"]))
            filing_rows = _filing_rows_from_submission_payload(response)
        except DataQuotaDeferred as exc:
            last_stop = "source_quota_deferred"
            progress["last_deferred"] = {
                "item_id": item_id,
                "next_retry_at": exc.next_retry_at.isoformat(),
                "reason": exc.reason,
            }
            _store_progress(
                state_path, progress, completed, failures, last_stop, now()
            )
            _emit_progress(
                on_progress,
                stage="sec_historical_submissions_metadata",
                status="quota_deferred",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=was_cached,
            )
            break
        except Exception as exc:
            if not was_cached:
                network_requests += 1
            failures_this_run += 1
            failures.append(
                {
                    "item_id": item_id,
                    "at": now().isoformat(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            last_stop = "item_failed"
            _store_progress(
                state_path, progress, completed, failures, last_stop, now()
            )
            _emit_progress(
                on_progress,
                stage="sec_historical_submissions_metadata",
                status="failed",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=was_cached,
            )
            continue
        if was_cached:
            cache_hits += 1
        else:
            network_requests += 1
        cached = cache.get(key)
        retrieved_at = cached.retrieved_at if cached is not None else now()
        completed[item_id] = {
            "cache_key": key.digest,
            "response_hash": _canonical_hash(response),
            "filing_count": len(filing_rows),
            "retrieved_at": retrieved_at.isoformat(),
            "completed_at": now().isoformat(),
        }
        last_stop = "item_completed"
        _store_progress(
            state_path, progress, completed, failures, last_stop, now()
        )
        _emit_progress(
            on_progress,
            stage="sec_historical_submissions_metadata",
            status="completed",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )
    pending_count = len(plan["items"]) - len(completed)
    status = "completed" if pending_count == 0 else "paused_resumable"
    _store_progress(
        state_path, progress, completed, failures, last_stop, now()
    )
    return {
        "status": status,
        "stage": "sec_historical_submissions_metadata",
        "plan_hash": plan_hash,
        "request_count": plan["request_count"],
        "completed_count": len(completed),
        "pending_count": pending_count,
        "network_requests_this_run": network_requests,
        "cache_hits_this_run": cache_hits,
        "failures_this_run": failures_this_run,
        "filing_bodies_completed": 0,
        "last_stop": last_stop,
        "progress_path": str(state_path.resolve()),
    }


def write_sec_filing_plan_from_submissions(
    *,
    primary_plan_path: str | Path,
    historical_plan_path: str | Path,
    cache: RawDataCache,
    output_path: str | Path,
    forms: Iterable[str] = ("10-K", "20-F", "40-F", "10-Q", "8-K", "6-K"),
    annual_per_as_of: int = 2,
    quarterly_per_as_of: int = 4,
    event_per_as_of: int = 8,
    event_lookback_days: int = 120,
) -> dict[str, Any]:
    """Build an exact accepted-time filing-body plan from cached SEC metadata."""

    for name, value in (
        ("annual_per_as_of", annual_per_as_of),
        ("quarterly_per_as_of", quarterly_per_as_of),
        ("event_per_as_of", event_per_as_of),
        ("event_lookback_days", event_lookback_days),
    ):
        if value < 1:
            raise ValidationError(f"{name} must be positive")
    selected_forms = {_base_form(value) for value in forms}
    if not selected_forms:
        raise ValidationError("discovered filing plan requires at least one form")
    primary_path = Path(primary_plan_path)
    historical_path = Path(historical_plan_path)
    primary = load_sec_submissions_backfill_plan(primary_path)
    historical = load_sec_historical_submissions_plan(historical_path)
    if historical.get("parent_plan_hash") != primary.get("plan_hash"):
        raise ValidationError("SEC historical plan does not belong to primary plan")
    raw_dates = primary.get("selection", {}).get("prediction_dates", ())
    if not isinstance(raw_dates, list) or not raw_dates:
        raise ValidationError("SEC filing plan prediction dates are missing")
    prediction_dates = sorted(
        _parse_date(value, "SEC filing prediction date") for value in raw_dates
    )

    rows_by_company: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    missing_metadata: list[str] = []
    excluded_reasons: Counter[str] = Counter()
    for item in primary["items"]:
        response = _cached_json_for_plan_item(cache, item)
        if response is None:
            missing_metadata.append(str(item["item_id"]))
            continue
        _validate_submissions_response(response, str(item["cik"]))
        _merge_filing_rows(
            rows_by_company,
            plan_item=item,
            payload=response,
            metadata_source="primary_submissions",
            excluded_reasons=excluded_reasons,
        )
    for item in historical["items"]:
        response = _cached_json_for_plan_item(cache, item)
        if response is None:
            missing_metadata.append(str(item["item_id"]))
            continue
        _merge_filing_rows(
            rows_by_company,
            plan_item=item,
            payload=response,
            metadata_source=str(item["filename"]),
            excluded_reasons=excluded_reasons,
        )
    if missing_metadata:
        raise ValidationError(
            "SEC metadata cache is incomplete for filing-body planning: "
            f"{len(missing_metadata)} missing"
        )

    selected_items: dict[tuple[str, str], dict[str, Any]] = {}
    for company_id, company_rows in rows_by_company.items():
        normalized_rows = list(company_rows.values())
        for prediction_date in prediction_dates:
            as_of = _midnight_utc(prediction_date)
            available = [
                row
                for row in normalized_rows
                if row["available_at_datetime"] <= as_of
                and _base_form(row["form"]) in selected_forms
            ]
            annual = _latest_filing_rows(
                [row for row in available if _form_family(row["form"]) == "annual"],
                annual_per_as_of,
            )
            quarterly = _latest_filing_rows(
                [row for row in available if _form_family(row["form"]) == "quarterly"],
                quarterly_per_as_of,
            )
            event_start = as_of - timedelta(days=event_lookback_days)
            events = _latest_filing_rows(
                [
                    row
                    for row in available
                    if _form_family(row["form"]) == "event"
                    and row["available_at_datetime"] >= event_start
                ],
                event_per_as_of,
            )
            for row in (*annual, *quarterly, *events):
                identity = (str(row["cik"]), str(row["accession_number"]))
                item = selected_items.get(identity)
                if item is None:
                    item = {
                        "item_id": "secitem_"
                        + _canonical_hash(
                            {"cik": identity[0], "accession_number": identity[1]}
                        )[:24],
                        "company_id": company_id,
                        "symbol": row["symbol"],
                        "original_document_id": row["source_id"],
                        "source_id": row["source_id"],
                        "source_url": row["source_url"],
                        "cik": row["cik"],
                        "accession_number": row["accession_number"],
                        "primary_document": row["primary_document"],
                        "form": row["form"],
                        "published_at": row["published_at"],
                        "available_at": row["available_at"],
                        "acceptance_datetime_raw": row["acceptance_datetime_raw"],
                        "availability_policy": row["availability_policy"],
                        "metadata_sources": list(row["metadata_sources"]),
                        "required_as_of_dates": [],
                        "legacy_content_chars": 0,
                    }
                    selected_items[identity] = item
                required_dates = item["required_as_of_dates"]
                prediction_text = prediction_date.isoformat()
                if prediction_text not in required_dates:
                    required_dates.append(prediction_text)
    items = sorted(
        selected_items.values(),
        key=lambda item: (
            item["company_id"],
            _FORM_PRIORITY.get(_base_form(str(item["form"])), 9),
            item["available_at"],
            item["accession_number"],
        ),
    )
    for item in items:
        item["required_as_of_dates"].sort()
    payload: dict[str, Any] = {
        "schema_version": SEC_DISCOVERED_FILING_PLAN_SCHEMA,
        "source_artifacts": {
            "primary_submissions_plan": _artifact_identity(primary_path),
            "historical_submissions_plan": _artifact_identity(historical_path),
        },
        "parent_plan_hashes": {
            "primary": primary["plan_hash"],
            "historical": historical["plan_hash"],
        },
        "selection": {
            "kind": "filing",
            "source": "cached_sec_submissions_metadata",
            "forms": sorted(selected_forms),
            "prediction_dates": [value.isoformat() for value in prediction_dates],
            "annual_per_as_of": annual_per_as_of,
            "quarterly_per_as_of": quarterly_per_as_of,
            "event_per_as_of": event_per_as_of,
            "event_lookback_days": event_lookback_days,
            "availability_policy": (
                "timezone_aware_sec_acceptance_else_next_utc_day_after_filing_date"
            ),
            "allowed_url_prefix": f"https://{_SEC_ARCHIVE_HOST}{_SEC_ARCHIVE_PREFIX}",
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
        "metadata_filing_count": sum(len(rows) for rows in rows_by_company.values()),
        "excluded_filing_count": sum(excluded_reasons.values()),
        "excluded_reason_counts": dict(sorted(excluded_reasons.items())),
        "request_count": len(items),
        "items": items,
    }
    payload["plan_hash"] = _canonical_hash(payload)
    _atomic_write_json(Path(output_path), payload)
    return payload


def load_sec_filing_backfill_plan(path: str | Path) -> dict[str, Any]:
    """Load and validate one exact SEC backfill plan."""

    payload = _read_json(Path(path))
    if payload.get("schema_version") not in {
        SEC_PLAN_SCHEMA,
        SEC_DISCOVERED_FILING_PLAN_SCHEMA,
    }:
        raise ValidationError("unsupported SEC filing backfill plan schema")
    supplied_hash = str(payload.get("plan_hash", ""))
    without_hash = dict(payload)
    without_hash.pop("plan_hash", None)
    if supplied_hash != _canonical_hash(without_hash):
        raise ValidationError("SEC filing backfill plan hash mismatch")
    items = payload.get("items")
    if not isinstance(items, list) or int(payload.get("request_count", -1)) != len(items):
        raise ValidationError("SEC filing backfill plan item count mismatch")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ValidationError("SEC filing backfill item must be an object")
        item_id = str(item.get("item_id", ""))
        if not item_id or item_id in seen:
            raise ValidationError("SEC filing backfill item ids must be unique")
        seen.add(item_id)
        if not _is_sec_archive_url(str(item.get("source_url", ""))):
            raise ValidationError("SEC filing backfill plan contains a non-SEC URL")
        published_at = datetime.fromisoformat(str(item["published_at"]))
        available_at = datetime.fromisoformat(str(item["available_at"]))
        if available_at <= published_at:
            raise ValidationError("SEC filing availability must be after publication")
    return payload


def preview_sec_filing_backfill(
    *,
    plan_path: str | Path,
    raw_info_root: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
) -> dict[str, Any]:
    """Return current exact work without performing network I/O or writes."""

    plan = load_sec_filing_backfill_plan(plan_path)
    progress = _load_progress(Path(progress_path), str(plan["plan_hash"]))
    completed = dict(progress.get("completed", {}))
    cached = 0
    pending = 0
    for item in plan["items"]:
        if item["item_id"] in completed:
            continue
        pending += 1
        key = RawCacheKey.from_request(
            "sec_edgar",
            DataCapability.FILING_DOCUMENTS,
            "GET",
            str(item["source_url"]),
        )
        cached += int(cache.get_text(key) is not None)
    return {
        "status": "zero_network_preview",
        "plan_hash": plan["plan_hash"],
        "request_count": plan["request_count"],
        "completed_count": len(completed),
        "pending_count": pending,
        "pending_cache_hits": cached,
        "maximum_new_network_requests": pending - cached,
        "raw_info_root": str(Path(raw_info_root).resolve()),
        "external_calls": 0,
    }


def run_sec_filing_backfill(
    *,
    plan_path: str | Path,
    raw_info_root: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
    client: SecFilingBodyClient,
    max_network_requests: int,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute/resume one bounded SEC primary-document backfill invocation."""

    if max_network_requests < 0:
        raise ValidationError("max_network_requests must be non-negative")
    plan = load_sec_filing_backfill_plan(plan_path)
    plan_hash = str(plan["plan_hash"])
    state_path = Path(progress_path)
    progress = _load_progress(state_path, plan_hash)
    completed: dict[str, Any] = dict(progress.get("completed", {}))
    failures: list[dict[str, Any]] = list(progress.get("failures", ()))
    store = RawInfoStore(raw_info_root)
    network_requests = 0
    cache_hits = 0
    appended = 0
    reused = 0
    failures_this_run = 0
    last_stop = "plan_exhausted"

    for item_index, item in enumerate(plan["items"], start=1):
        item_id = str(item["item_id"])
        if item_id in completed:
            continue
        source_url = str(item["source_url"])
        key = RawCacheKey.from_request(
            "sec_edgar",
            DataCapability.FILING_DOCUMENTS,
            "GET",
            source_url,
        )
        was_cached = cache.get_text(key) is not None
        if not was_cached and network_requests >= max_network_requests:
            last_stop = "invocation_network_limit_reached"
            _emit_progress(
                on_progress,
                stage="sec_filing_bodies",
                status="paused_network_limit",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=False,
            )
            break
        _emit_progress(
            on_progress,
            stage="sec_filing_bodies",
            status="starting",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )
        filing = FilingMetadata(
            cik=str(item["cik"]),
            accession_number=str(item["accession_number"]),
            filing_date=datetime.fromisoformat(str(item["published_at"])).date(),
            report_date=None,
            form=str(item["form"]),
            primary_document=str(item["primary_document"]),
            source_url=source_url,
            retrieved_at=now(),
            accepted_at=_optional_aware_datetime(
                item.get("acceptance_datetime_raw")
            ),
        )
        try:
            content = client.filing_document_text(filing).strip()
            if not content:
                raise DataSourceError("SEC primary document body was empty")
        except DataQuotaDeferred as exc:
            last_stop = "source_quota_deferred"
            progress["last_deferred"] = {
                "item_id": item_id,
                "next_retry_at": exc.next_retry_at.isoformat(),
                "reason": exc.reason,
            }
            _store_progress(state_path, progress, completed, failures, last_stop, now())
            _emit_progress(
                on_progress,
                stage="sec_filing_bodies",
                status="quota_deferred",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=was_cached,
            )
            break
        except Exception as exc:
            if not was_cached:
                network_requests += 1
            failures_this_run += 1
            failures.append(
                {
                    "item_id": item_id,
                    "at": now().isoformat(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            last_stop = "item_failed"
            _store_progress(state_path, progress, completed, failures, last_stop, now())
            _emit_progress(
                on_progress,
                stage="sec_filing_bodies",
                status="failed",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=was_cached,
            )
            continue
        if was_cached:
            cache_hits += 1
        else:
            network_requests += 1
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        raw_document_id = "secfull_" + hashlib.sha256(
            f"{item['source_id']}:{content_hash}".encode("utf-8")
        ).hexdigest()[:24]
        cached = cache.get(key)
        retrieved_at = cached.retrieved_at if cached is not None else now()
        document = RawInfoDocument.create(
            document_id=raw_document_id,
            company_id=str(item["company_id"]),
            source_type="filing",
            published_at=datetime.fromisoformat(str(item["published_at"])),
            available_at=datetime.fromisoformat(str(item["available_at"])),
            content=content,
            metadata={
                "original_document_id": item["original_document_id"],
                "source_id": item["source_id"],
                "source_url": source_url,
                "symbol": item["symbol"],
                "cik": item["cik"],
                "accession_number": item["accession_number"],
                "form": item["form"],
                "content_scope": "complete_body",
                "legacy_content_chars": int(item.get("legacy_content_chars", 0)),
                "retrieved_at": retrieved_at.isoformat(),
                "backfill_plan_hash": plan_hash,
                "acceptance_datetime_raw": item.get("acceptance_datetime_raw"),
                "availability_policy": item.get(
                    "availability_policy",
                    plan.get("selection", {}).get("availability_policy"),
                ),
                "required_as_of_dates": list(item.get("required_as_of_dates", ())),
                "metadata_sources": list(item.get("metadata_sources", ())),
            },
        )
        did_append = store.append(document)
        appended += int(did_append)
        reused += int(not did_append)
        completed[item_id] = {
            "raw_info_document_id": raw_document_id,
            "content_hash": content_hash,
            "content_chars": len(content),
            "cache_key": key.digest,
            "completed_at": now().isoformat(),
        }
        last_stop = "item_completed"
        _store_progress(state_path, progress, completed, failures, last_stop, now())
        _emit_progress(
            on_progress,
            stage="sec_filing_bodies",
            status="completed",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )

    pending_count = len(plan["items"]) - len(completed)
    status = "completed" if pending_count == 0 else "paused_resumable"
    _store_progress(state_path, progress, completed, failures, last_stop, now())
    return {
        "status": status,
        "plan_hash": plan_hash,
        "request_count": plan["request_count"],
        "completed_count": len(completed),
        "pending_count": pending_count,
        "network_requests_this_run": network_requests,
        "cache_hits_this_run": cache_hits,
        "raw_info_appended_this_run": appended,
        "raw_info_reused_this_run": reused,
        "failures_this_run": failures_this_run,
        "last_stop": last_stop,
        "progress_path": str(state_path.resolve()),
    }


def _load_progress(path: Path, plan_hash: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SEC_PROGRESS_SCHEMA,
            "plan_hash": plan_hash,
            "completed": {},
            "failures": [],
        }
    progress = _read_json(path)
    if progress.get("schema_version") != SEC_PROGRESS_SCHEMA:
        raise ValidationError("unsupported SEC filing backfill progress schema")
    if progress.get("plan_hash") != plan_hash:
        raise ValidationError("SEC filing backfill progress plan hash mismatch")
    return progress


def _emit_progress(
    callback: Callable[[Mapping[str, Any]], None] | None,
    *,
    stage: str,
    status: str,
    item_index: int,
    item_count: int,
    item: Mapping[str, Any],
    cache_hit: bool,
) -> None:
    if callback is None:
        return
    callback(
        {
            "stage": stage,
            "status": status,
            "item_index": item_index,
            "item_count": item_count,
            "item_id": str(item["item_id"]),
            "company_id": str(item["company_id"]),
            "symbol": str(item["symbol"]),
            "cache_hit": cache_hit,
        }
    )


def _load_submissions_progress(path: Path, plan_hash: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SEC_SUBMISSIONS_PROGRESS_SCHEMA,
            "plan_hash": plan_hash,
            "completed": {},
            "failures": [],
        }
    progress = _read_json(path)
    if progress.get("schema_version") != SEC_SUBMISSIONS_PROGRESS_SCHEMA:
        raise ValidationError("unsupported SEC submissions backfill progress schema")
    if progress.get("plan_hash") != plan_hash:
        raise ValidationError("SEC submissions backfill progress plan hash mismatch")
    return progress


def _load_company_facts_progress(path: Path, plan_hash: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SEC_COMPANY_FACTS_PROGRESS_SCHEMA,
            "plan_hash": plan_hash,
            "completed": {},
            "failures": [],
        }
    progress = _read_json(path)
    if progress.get("schema_version") != SEC_COMPANY_FACTS_PROGRESS_SCHEMA:
        raise ValidationError("unsupported SEC Company Facts progress schema")
    if progress.get("plan_hash") != plan_hash:
        raise ValidationError("SEC Company Facts progress plan hash mismatch")
    return progress


def _load_historical_submissions_progress(
    path: Path, plan_hash: str
) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SEC_HISTORICAL_SUBMISSIONS_PROGRESS_SCHEMA,
            "plan_hash": plan_hash,
            "completed": {},
            "failures": [],
        }
    progress = _read_json(path)
    if progress.get("schema_version") != SEC_HISTORICAL_SUBMISSIONS_PROGRESS_SCHEMA:
        raise ValidationError(
            "unsupported SEC historical submissions progress schema"
        )
    if progress.get("plan_hash") != plan_hash:
        raise ValidationError("SEC historical submissions progress plan hash mismatch")
    return progress


def _store_progress(
    path: Path,
    progress: dict[str, Any],
    completed: Mapping[str, Any],
    failures: list[dict[str, Any]],
    last_stop: str,
    updated_at: datetime,
) -> None:
    progress.update(
        {
            "completed": dict(completed),
            "failures": failures,
            "last_stop": last_stop,
            "updated_at": updated_at.isoformat(),
        }
    )
    _atomic_write_json(path, progress)


def _company_facts_cache_key(item: Mapping[str, Any]) -> RawCacheKey:
    return RawCacheKey.from_request(
        "sec_edgar",
        DataCapability.FINANCIAL_STATEMENTS,
        "GET",
        str(item["source_url"]),
    )


def _validate_company_facts_response(response: Any, expected_cik: str) -> None:
    if not isinstance(response, Mapping):
        raise DataSourceError("SEC Company Facts response must be an object")
    response_cik = _normalize_cik(response.get("cik"))
    if response_cik is None or response_cik != expected_cik:
        raise DataSourceError("SEC Company Facts response CIK mismatch")
    if not isinstance(response.get("facts"), Mapping):
        raise DataSourceError("SEC Company Facts response missing facts")


def _company_fact_documents(
    response: Mapping[str, Any],
    *,
    item: Mapping[str, Any],
    selection: Mapping[str, Any],
    plan_hash: str,
    retrieved_at: datetime,
) -> tuple[list[RawInfoDocument], dict[str, Any]]:
    cik = str(item["cik"])
    company_id = str(item["company_id"])
    symbol = str(item["symbol"])
    source_url = str(item["source_url"])
    period_end_from = _parse_date(
        selection.get("period_end_from"), "fact period_end_from"
    )
    period_end_through = _parse_date(
        selection.get("period_end_through"), "fact period_end_through"
    )
    available_at_through = _parse_datetime(
        selection.get("available_at_through"), "fact available_at_through"
    )
    allowed_taxonomies = set(selection.get("taxonomy_allowlist", ()))
    allowed_forms = set(selection.get("form_allowlist", ()))
    facts = response.get("facts")
    if not isinstance(facts, Mapping):
        raise DataSourceError("SEC Company Facts response missing facts")
    excluded: Counter[str] = Counter()
    raw_fact_rows = 0
    groups: dict[str, dict[str, Any]] = {}
    for raw_taxonomy, raw_concepts in facts.items():
        taxonomy = str(raw_taxonomy)
        if not isinstance(raw_concepts, Mapping):
            excluded["invalid_taxonomy_payload"] += 1
            continue
        if taxonomy not in allowed_taxonomies:
            skipped = _count_company_fact_rows(raw_concepts)
            raw_fact_rows += skipped
            excluded["taxonomy_not_allowed"] += skipped
            continue
        for raw_tag, raw_concept in raw_concepts.items():
            tag = str(raw_tag)
            if not isinstance(raw_concept, Mapping):
                excluded["invalid_concept_payload"] += 1
                continue
            label = str(raw_concept.get("label") or "").strip() or None
            description = (
                str(raw_concept.get("description") or "").strip() or None
            )
            units = raw_concept.get("units")
            if not isinstance(units, Mapping):
                excluded["missing_units"] += 1
                continue
            for raw_unit, raw_rows in units.items():
                unit = str(raw_unit)
                if not isinstance(raw_rows, list):
                    excluded["invalid_unit_rows"] += 1
                    continue
                for raw_row in raw_rows:
                    raw_fact_rows += 1
                    if not isinstance(raw_row, Mapping):
                        excluded["invalid_fact_row"] += 1
                        continue
                    accession = str(raw_row.get("accn") or "")
                    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                        excluded["invalid_accession"] += 1
                        continue
                    form = str(raw_row.get("form") or "").strip().upper()
                    if form not in allowed_forms:
                        excluded["form_not_allowed"] += 1
                        continue
                    filed_date = _optional_fact_date(raw_row.get("filed"))
                    if filed_date is None:
                        excluded["invalid_filed_date"] += 1
                        continue
                    available_at = _midnight_utc(filed_date + timedelta(days=1))
                    if available_at > available_at_through:
                        excluded["unavailable_by_latest_cutoff"] += 1
                        continue
                    end_date = _optional_fact_date(raw_row.get("end"))
                    if end_date is None:
                        excluded["invalid_period_end"] += 1
                        continue
                    if end_date < period_end_from:
                        excluded["period_before_lookback"] += 1
                        continue
                    if end_date > period_end_through:
                        excluded["period_after_latest_cutoff"] += 1
                        continue
                    start_date: date | None = None
                    if raw_row.get("start") is not None:
                        start_date = _optional_fact_date(raw_row.get("start"))
                        if start_date is None or start_date > end_date:
                            excluded["invalid_period_start"] += 1
                            continue
                    value = raw_row.get("val")
                    if isinstance(value, bool) or not isinstance(
                        value, (int, float, str)
                    ):
                        excluded["invalid_fact_value"] += 1
                        continue
                    fact = {
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "label": label,
                        "description": description,
                        "unit": unit,
                        "value": value,
                        "start": start_date.isoformat() if start_date else None,
                        "end": end_date.isoformat(),
                        "fiscal_year": raw_row.get("fy"),
                        "fiscal_period": raw_row.get("fp"),
                        "frame": raw_row.get("frame"),
                    }
                    fact_key = _canonical_hash(fact)
                    group = groups.setdefault(
                        accession,
                        {
                            "filing_date": filed_date,
                            "form": form,
                            "available_at": available_at,
                            "facts": {},
                        },
                    )
                    if group["filing_date"] != filed_date or group["form"] != form:
                        raise DataSourceError(
                            f"conflicting SEC Company Facts filing metadata: {accession}"
                        )
                    group["facts"][fact_key] = fact
    documents: list[RawInfoDocument] = []
    selected_fact_rows = 0
    for accession, group in sorted(groups.items()):
        selected_facts = sorted(
            group["facts"].values(),
            key=lambda fact: (
                fact["taxonomy"],
                fact["tag"],
                fact["unit"],
                fact["end"],
                fact["start"] or "",
                json.dumps(fact["value"], sort_keys=True),
            ),
        )
        if not selected_facts:
            continue
        selected_fact_rows += len(selected_facts)
        content_payload = {
            "schema_version": "sec-company-facts-document-v1",
            "cik": cik,
            "accession_number": accession,
            "filing_date": group["filing_date"].isoformat(),
            "form": group["form"],
            "facts": selected_facts,
        }
        content = json.dumps(
            content_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        version_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        documents.append(
            RawInfoDocument.create(
                document_id=(
                    f"secfacts:{cik}:{accession}:{version_hash[:16]}"
                ),
                company_id=company_id,
                source_type="sec_company_facts",
                published_at=_midnight_utc(group["filing_date"]),
                available_at=group["available_at"],
                content=content,
                metadata={
                    "symbol": symbol,
                    "cik": cik,
                    "accession_number": accession,
                    "form": group["form"],
                    "source_key": "sec_edgar",
                    "source_url": source_url,
                    "retrieved_at": retrieved_at.isoformat(),
                    "backfill_plan_hash": plan_hash,
                    "content_scope": "standard_taxonomy_facts_for_accession",
                    "fact_count": len(selected_facts),
                    "taxonomy_namespaces": sorted(
                        {fact["taxonomy"] for fact in selected_facts}
                    ),
                    "period_end_from": period_end_from.isoformat(),
                    "period_end_through": period_end_through.isoformat(),
                    "availability_policy": (
                        "next_utc_day_after_companyfacts_filed_date"
                    ),
                    "retrospective_api_extraction": True,
                    "requires_primary_filing_audit": True,
                },
            )
        )
    return documents, {
        "raw_fact_row_count": raw_fact_rows,
        "selected_fact_row_count": selected_fact_rows,
        "excluded_reason_counts": dict(sorted(excluded.items())),
    }


def _count_company_fact_rows(concepts: Mapping[str, Any]) -> int:
    count = 0
    for concept in concepts.values():
        units = concept.get("units") if isinstance(concept, Mapping) else None
        if not isinstance(units, Mapping):
            continue
        count += sum(len(rows) for rows in units.values() if isinstance(rows, list))
    return count


def _optional_fact_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _validate_submissions_response(response: Any, expected_cik: str) -> None:
    if not isinstance(response, Mapping):
        raise DataSourceError("SEC submissions response must be an object")
    response_cik = _normalize_cik(response.get("cik"))
    if response_cik is not None and response_cik != expected_cik:
        raise DataSourceError("SEC submissions response CIK mismatch")
    filings = response.get("filings")
    if not isinstance(filings, Mapping) or not isinstance(filings.get("recent"), Mapping):
        raise DataSourceError("SEC submissions response missing filings.recent")


def _assert_label_free_scope(value: Any, path: str = "scope") -> None:
    forbidden = {
        "ground_truth",
        "outcome",
        "outcome_label",
        "label",
        "is_surge",
        "magnitude",
        "magnitude_class",
        "realized_max_multiple",
        "future_return",
        "split",
        "split_name",
        "split_ownership",
        "locked_test",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in forbidden:
                raise ValidationError(f"forbidden label/split field in acquisition scope: {path}.{key}")
            _assert_label_free_scope(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_label_free_scope(nested, f"{path}[{index}]")


def _normalize_cik(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits or len(digits) > 10:
        raise ValidationError("CIK must contain at most ten digits")
    return digits.zfill(10)


def _validated_sec_history_filename(value: Any) -> str:
    filename = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.json", filename):
        raise ValidationError("SEC historical submissions filename is unsafe")
    return filename


def _cached_json_for_plan_item(
    cache: RawDataCache, item: Mapping[str, Any]
) -> Any | None:
    key = RawCacheKey.from_request(
        "sec_edgar",
        DataCapability.FILINGS,
        "GET",
        str(item["source_url"]),
    )
    return cache.get_json(key)


def _filing_rows_from_submission_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        raise DataSourceError("SEC filing metadata payload must be an object")
    filings = payload.get("filings")
    if isinstance(filings, Mapping) and isinstance(filings.get("recent"), Mapping):
        table = filings["recent"]
    else:
        table = payload
    required = ("accessionNumber", "filingDate", "form", "primaryDocument")
    if not all(isinstance(table.get(key), list) for key in required):
        raise DataSourceError("SEC filing metadata arrays are incomplete")
    count = len(table["accessionNumber"])
    if any(len(table[key]) < count for key in required):
        raise DataSourceError("SEC filing metadata arrays have inconsistent lengths")
    rows: list[dict[str, Any]] = []
    for index in range(count):
        rows.append(
            {
                "accession_number": table["accessionNumber"][index],
                "filing_date": table["filingDate"][index],
                "report_date": _array_value(table, "reportDate", index),
                "acceptance_datetime_raw": _array_value(
                    table, "acceptanceDateTime", index
                ),
                "form": table["form"][index],
                "primary_document": table["primaryDocument"][index],
            }
        )
    return rows


def _array_value(table: Mapping[str, Any], key: str, index: int) -> Any:
    values = table.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _merge_filing_rows(
    rows_by_company: dict[str, dict[tuple[str, str], dict[str, Any]]],
    *,
    plan_item: Mapping[str, Any],
    payload: Any,
    metadata_source: str,
    excluded_reasons: Counter[str],
) -> None:
    company_id = str(plan_item["company_id"])
    symbol = str(plan_item["symbol"])
    cik = str(plan_item["cik"])
    company_rows = rows_by_company.setdefault(company_id, {})
    for raw in _filing_rows_from_submission_payload(payload):
        try:
            accession = str(raw["accession_number"])
            if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                raise ValidationError("invalid_accession_number")
            filing_date = _parse_date(raw["filing_date"], "SEC filing date")
            form = _normalize_form(str(raw["form"]))
            primary_document = _validated_primary_document(raw["primary_document"])
        except (TypeError, ValueError, ValidationError) as exc:
            excluded_reasons[str(exc)] += 1
            continue
        acceptance_raw = (
            str(raw["acceptance_datetime_raw"])
            if raw.get("acceptance_datetime_raw")
            else None
        )
        accepted_at = _optional_aware_datetime(acceptance_raw)
        if accepted_at is not None:
            available_at = accepted_at
            availability_policy = "timezone_aware_sec_acceptance_datetime"
        else:
            available_at = _midnight_utc(filing_date + timedelta(days=1))
            availability_policy = "next_utc_day_after_filing_date"
        cik_no_zeros = str(int(cik))
        accession_path = accession.replace("-", "")
        source_url = (
            f"https://{_SEC_ARCHIVE_HOST}{_SEC_ARCHIVE_PREFIX}"
            f"{cik_no_zeros}/{accession_path}/{primary_document}"
        )
        key = (cik, accession)
        normalized = {
            "company_id": company_id,
            "symbol": symbol,
            "cik": cik,
            "accession_number": accession,
            "filing_date": filing_date.isoformat(),
            "report_date": str(raw["report_date"])
            if raw.get("report_date")
            else None,
            "form": form,
            "primary_document": primary_document,
            "source_id": f"sec:{cik}:{accession}",
            "source_url": source_url,
            "published_at": _midnight_utc(filing_date).isoformat(),
            "available_at": available_at.isoformat(),
            "available_at_datetime": available_at,
            "acceptance_datetime_raw": acceptance_raw,
            "availability_policy": availability_policy,
            "metadata_sources": [metadata_source],
        }
        existing = company_rows.get(key)
        if existing is None:
            company_rows[key] = normalized
            continue
        for field in ("filing_date", "form", "primary_document", "source_url"):
            if existing[field] != normalized[field]:
                raise DataSourceError(
                    f"conflicting SEC metadata for {cik}/{accession}: {field}"
                )
        existing["metadata_sources"] = sorted(
            set(existing["metadata_sources"]) | {metadata_source}
        )
        if (
            existing["availability_policy"] == "next_utc_day_after_filing_date"
            and availability_policy == "timezone_aware_sec_acceptance_datetime"
        ):
            for field in (
                "available_at",
                "available_at_datetime",
                "acceptance_datetime_raw",
                "availability_policy",
            ):
                existing[field] = normalized[field]


def _validated_primary_document(value: Any) -> str:
    filename = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", filename):
        raise ValidationError("unsafe_primary_document")
    return filename


def _optional_aware_datetime(value: Any) -> datetime | None:
    if not value or str(value).casefold() in {"none", "null", "nan", "-"}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _latest_filing_rows(
    rows: Iterable[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            row["available_at_datetime"],
            row["filing_date"],
            row["accession_number"],
        ),
        reverse=True,
    )[:count]


def _artifact_identity(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _filing_form(row: Mapping[str, Any]) -> str:
    explicit = row.get("form")
    if explicit:
        return _normalize_form(str(explicit))
    text = " ".join(
        str(row.get(key, "")) for key in ("title", "source_id", "document_id")
    )
    match = _FORM_PATTERN.search(text)
    return _normalize_form(match.group(1)) if match else "OTHER"


def _normalize_form(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValidationError("filing form must not be empty")
    return normalized


def _base_form(form: str) -> str:
    return _normalize_form(form).removesuffix("/A")


def _form_family(form: str) -> str | None:
    base = _base_form(form)
    if base in {"10-K", "20-F", "40-F"}:
        return "annual"
    if base == "10-Q":
        return "quarterly"
    if base in {"8-K", "6-K"}:
        return "event"
    return None


def _document_available_date(row: Mapping[str, Any]) -> date:
    value = row.get("available_date") or row.get("published_date")
    return _parse_date(value, "document available_date")


def _sec_identity(source_id: str, source_url: str) -> tuple[str, str]:
    match = re.fullmatch(r"sec:(\d+):([0-9-]+)", source_id)
    if match:
        return match.group(1).zfill(10), match.group(2)
    parts = [part for part in urlsplit(source_url).path.split("/") if part]
    try:
        data_index = parts.index("data")
        cik = parts[data_index + 1].zfill(10)
        accession_compact = parts[data_index + 2]
    except (ValueError, IndexError) as exc:
        raise ValidationError("cannot derive SEC filing identity") from exc
    if len(accession_compact) != 18 or not accession_compact.isdigit():
        raise ValidationError("SEC archive URL contains invalid accession number")
    accession = (
        f"{accession_compact[:10]}-{accession_compact[10:12]}-"
        f"{accession_compact[12:]}"
    )
    return cik, accession


def _is_sec_archive_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == _SEC_ARCHIVE_HOST
        and parsed.path.startswith(_SEC_ARCHIVE_PREFIX)
        and not parsed.query
        and not parsed.fragment
    )


def _parse_date(value: Any, name: str) -> date:
    if not value:
        raise ValidationError(f"missing {name}")
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"invalid {name}") from exc


def _parse_datetime(value: Any, name: str) -> datetime:
    if not value:
        raise ValidationError(f"missing {name}")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"invalid {name}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _midnight_utc(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _company_id_from_symbol(symbol: str) -> str:
    value = re.sub(r"[^a-z0-9_.:-]+", "_", symbol.casefold()).strip("_")
    if not value:
        raise ValidationError("cannot derive company_id from symbol")
    return value

def _length_stats(values: list[int]) -> dict[str, int]:
    ordered = sorted(values)
    if not ordered:
        return {"min": 0, "median": 0, "max": 0}
    return {
        "min": ordered[0],
        "median": ordered[len(ordered) // 2],
        "max": ordered[-1],
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"JSON artifact must be an object: {path}")
    return value
