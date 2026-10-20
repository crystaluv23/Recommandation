"""Production Raw Info acquisition adapters with historical fail-closed rules."""

from __future__ import annotations

from stock_opportunity_agent.data.filing_orientation import (
    filing_source_matches_form, operating_order, OPERATING_REQUEST_ID,
)

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

from stock_opportunity_agent.data.point_in_time import utc_day_of_instant
from stock_opportunity_agent.data.sec_company_facts import (
    materialize_company_fact_documents, validate_company_facts_response,
    STANDARD_TAXONOMIES, STANDARD_FORMS, CAPTURE_IDENTITY_POLICY,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import (
    AcquisitionFailure,
    AcquisitionResult,
    DataGapReason,
    RawInfoRequest,
    ResolutionEvent,
)
from stock_opportunity_agent.data.sources.state import DataQuotaDeferred


def _identity_value(identity: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = identity.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise AcquisitionFailure(
        DataGapReason.MISSING_IDENTIFIER,
        f"Acquisition requires one of these routing identifiers: {', '.join(keys)}.",
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _document_id(provider: str, company_id: str, source_type: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{provider}:{company_id}:{source_type}:{digest}"


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


class SecCompanyFactsAdapter:
    """Materialize issuer-verified, date-safe typed accession products."""

    provider = "sec_edgar"
    source_types = (
        "sec_company_facts",
        "company_facts",
        "financial_statements",
        "financials",
    )
    capabilities = ("company_profile", "financial_statements")

    def __init__(self, client: Any) -> None:
        self.client = client

    def acquire(
        self,
        request: RawInfoRequest,
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
    ) -> AcquisitionResult:
        cutoff_day = utc_day_of_instant(as_of)
        cursor = _event_cursor(self.client)
        cik = _identity_value(identity, "cik", "CIK").zfill(10)
        raw = self.client.company_facts(cik)
        validate_company_facts_response(raw, cik)
        raw_content = _canonical_json(raw)
        retrieved_at = datetime.now(timezone.utc)
        raw_document = RawInfoDocument.create(
            document_id=_document_id(
                self.provider,
                company_id,
                "sec_company_facts_raw_response",
                raw_content,
            ),
            company_id=company_id,
            source_type="sec_company_facts_raw_response",
            published_at=retrieved_at,
            available_at=retrieved_at,
            content=raw_content,
            metadata={"provider": self.provider, "cik": cik},
        )
        documents = [raw_document.as_capture()]
        selection = {"period_end_from": date.min.isoformat(),
            "period_end_through": cutoff_day.isoformat(),
            "available_at_through": as_of.astimezone(timezone.utc).isoformat(),
            "taxonomy_allowlist": list(STANDARD_TAXONOMIES), "form_allowlist": list(STANDARD_FORMS)}
        policy = {"schema_version": "sec-company-facts-acquisition-v1", "selection": selection}
        products, _stats = materialize_company_fact_documents(raw,
            item={"cik": cik, "company_id": company_id,
                "symbol": identity.get("ticker") or identity.get("symbol"),
                "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK" + cik + ".json"},
            selection=selection, retrieved_at=retrieved_at, identity_policy=CAPTURE_IDENTITY_POLICY,
            provenance={"acquisition_policy_hash": hashlib.sha256(_canonical_json(policy).encode()).hexdigest(),
                "acquisition_selection": selection})
        documents.extend(products)
        return AcquisitionResult(
            documents=tuple(documents),
            events=_provider_events(self.client, cursor),
        )


class SecFilingAdapter:
    """Retrieve eligible SEC filing metadata and complete primary-document bodies."""

    provider = "sec_edgar"
    source_types = (
        "sec_filing",
        "filing",
        "filing_body",
        "10-k",
        "10-q",
        "8-k",
        "20-f",
        "40-f",
        "6-k",
    )
    capabilities = ("filings", "filing_documents")

    def __init__(self, client: Any) -> None:
        self.client = client

    def acquire(
        self,
        request: RawInfoRequest,
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
    ) -> AcquisitionResult:
        cursor = _event_cursor(self.client)
        cik = _identity_value(identity, "cik", "CIK")
        lower = as_of.date() - timedelta(days=request.lookback_days or 3650)
        history_failures: list[str] = []
        history_truncated = False
        history_pages_requested: list[str] = []
        if hasattr(self.client, "filings_from_arrays_as_of") and hasattr(
            self.client, "submissions"
        ):
            submissions = self.client.submissions(cik)
            recent = submissions.get("filings", {}).get("recent", {})
            filings = self.client.filings_from_arrays_as_of(
                cik, recent, as_of.date()
            )
            history_pages = _overlapping_sec_history_files(
                submissions, lower=lower, upper=as_of.date()
            )
            history_truncated = len(history_pages) > 3
            for page in history_pages[:3]:
                filename = page["name"]
                history_pages_requested.append(filename)
                try:
                    history = self.client.historical_submissions(filename)
                    filings.extend(
                        self.client.filings_from_arrays_as_of(
                            cik, history, as_of.date()
                        )
                    )
                except DataQuotaDeferred:
                    raise
                except Exception as exc:
                    history_failures.append(type(exc).__name__)
        else:  # narrow compatibility boundary for existing scripted test clients
            filings = self.client.recent_filings_as_of(cik, as_of.date())
        filings = _deduplicate_filings_by_accession(filings)
        filings.sort(
            key=lambda item: (
                item.accepted_at or _midnight(item.filing_date),
                item.accession_number,
            ),
            reverse=True,
        )
        requested_forms = {
            item.upper()
            for item in request.source_types
            if item.casefold() in _SEC_OPERATING_FORMS
        }
        eligible = [
            item
            for item in filings
            if item.filing_date >= lower
            and (not requested_forms or item.form.upper() in requested_forms)
        ]
        if not requested_forms:
            core_filings = [
                item
                for item in eligible
                if item.form.casefold() in _SEC_OPERATING_FORMS
            ]
            if core_filings:
                eligible = core_filings
        if request.request_id == OPERATING_REQUEST_ID:
            eligible = operating_order(eligible, lambda item: item.form.strip().upper(),
                lambda item: item.accepted_at or _midnight(item.filing_date))
        documents: list[RawInfoDocument] = []
        failures: list[str] = []
        attempt_limit = min(len(eligible), request.max_documents + 3)
        for filing in eligible[:attempt_limit]:
            if len(documents) >= request.max_documents:
                break
            source_type = next((item for item in request.source_types
                if item in self.source_types and filing_source_matches_form(item, filing.form)), None)
            if source_type is None:
                continue
            try:
                body = self.client.filing_document_text(filing)
            except DataQuotaDeferred:
                raise
            except Exception as exc:  # one bad archive object must not mask later filings
                failures.append(type(exc).__name__)
                continue
            available = filing.accepted_at or _midnight(filing.filing_date)
            if available > as_of:
                continue
            documents.append(
                RawInfoDocument.create(
                    document_id=f"sec:{company_id}:{filing.accession_number.replace('-', '')}",
                    company_id=company_id,
                    source_type=source_type,
                    published_at=available,
                    available_at=available,
                    content=body,
                    metadata={
                        "provider": self.provider,
                        "cik": cik,
                        "form": filing.form,
                        "accession_number": filing.accession_number,
                        "source_url": filing.source_url,
                    },
                )
            )
        if not documents and (history_truncated or history_failures):
            raise AcquisitionFailure(
                DataGapReason.REQUIRED_COVERAGE_INCOMPLETE,
                "SEC submissions history scan was incomplete before a required "
                "filing body was obtained.",
            )
        if not documents and failures:
            raise AcquisitionFailure(
                DataGapReason.PROVIDER_ERROR,
                "SEC filing bodies were unavailable after trying eligible core filings: "
                + ", ".join(failures),
            )
        history_event = ResolutionEvent(
            "sec_history_scan",
            {
                "requested_files": history_pages_requested,
                "failed_file_count": len(history_failures),
                "history_truncated": history_truncated,
            },
        )
        return AcquisitionResult(
            documents=tuple(documents),
            events=(*_provider_events(self.client, cursor), history_event),
        )


class AlphaVantageNewsAdapter:
    """Materialize each historical Alpha Vantage news-feed item as raw JSON."""

    provider = "alpha_vantage"
    source_types = ("news", "company_news")
    capabilities = ("news",)

    def __init__(self, client: Any) -> None:
        self.client = client

    def acquire(
        self,
        request: RawInfoRequest,
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
    ) -> AcquisitionResult:
        cursor = _event_cursor(self.client)
        symbol = _identity_value(identity, "ticker", "symbol")
        start = as_of - timedelta(days=request.lookback_days or 180)
        raw = self.client.news_sentiment(
            symbol,
            limit=min(request.max_documents, 10),
            time_from=start,
            time_to=as_of,
            sort="LATEST",
        )
        feed = raw.get("feed", ()) if isinstance(raw, Mapping) else ()
        documents: list[RawInfoDocument] = []
        source_type = _first_supported(request.source_types, self.source_types)
        for item in feed:
            if not isinstance(item, Mapping):
                continue
            published = _alpha_datetime(item.get("time_published"))
            if published is None or published > as_of:
                continue
            content = _canonical_json(dict(item))
            documents.append(
                RawInfoDocument.create(
                    document_id=_document_id(self.provider, company_id, source_type, content),
                    company_id=company_id,
                    source_type=source_type,
                    published_at=published,
                    available_at=published,
                    content=content,
                    metadata={"provider": self.provider, "symbol": symbol, "url": item.get("url")},
                )
            )
        return AcquisitionResult(
            documents=tuple(documents[: request.max_documents]),
            events=_provider_events(self.client, cursor),
        )


class FinnhubNewsAdapter:
    """Materialize bounded historical Finnhub news as literal provider records."""

    provider = "finnhub"
    source_types = ("news", "company_news")
    capabilities = ("news",)

    def __init__(self, client: Any) -> None:
        self.client = client

    def acquire(
        self, request: RawInfoRequest, *, company_id: str,
        identity: Mapping[str, Any], as_of: datetime,
    ) -> AcquisitionResult:
        cursor = _event_cursor(self.client)
        symbol = _identity_value(identity, "ticker", "symbol")
        start = as_of - timedelta(days=request.lookback_days or 180)
        raw = self.client.company_news(symbol, start.date(), as_of.date())
        if not isinstance(raw, list):
            raise AcquisitionFailure(DataGapReason.PROVIDER_ERROR, "Finnhub news response is not a list.")
        documents: list[RawInfoDocument] = []
        source_type = _first_supported(request.source_types, self.source_types)
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            try:
                published = datetime.fromtimestamp(float(item["datetime"]), timezone.utc)
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
            related = {value.strip().upper() for value in str(item.get("related", "")).split(",")}
            if not start <= published <= as_of or symbol.upper() not in related:
                continue
            content = _canonical_json(dict(item))
            documents.append(RawInfoDocument.create(
                document_id=_document_id(self.provider, company_id, source_type, content),
                company_id=company_id, source_type=source_type,
                published_at=published, available_at=published, content=content,
                metadata={"provider": self.provider, "symbol": symbol, "url": item.get("url"),
                          "title": str(item.get("headline") or "")},
            ))
        documents.sort(key=lambda item: (item.available_at, item.document_id), reverse=True)
        return AcquisitionResult(
            documents=tuple(documents[:request.max_documents]),
            events=_provider_events(self.client, cursor),
        )


class AlphaVantageTranscriptAdapter:
    """Materialize complete historical transcripts with report-date lineage."""

    provider = "alpha_vantage"
    source_types = ("earnings_call", "transcript", "earnings_transcript")
    capabilities = ("transcripts",)

    def __init__(self, client: Any) -> None:
        self.client = client

    def acquire(
        self,
        request: RawInfoRequest,
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
    ) -> AcquisitionResult:
        cursor = _event_cursor(self.client)
        symbol = _identity_value(identity, "ticker", "symbol").upper()
        earnings = self.client.earnings(symbol)
        earnings_content = _canonical_json(earnings)
        retrieved_at = datetime.now(timezone.utc)
        raw_document = RawInfoDocument.create(
            document_id=_document_id(
                self.provider,
                company_id,
                "alpha_vantage_earnings_raw_response",
                earnings_content,
            ),
            company_id=company_id,
            source_type="alpha_vantage_earnings_raw_response",
            published_at=retrieved_at,
            available_at=retrieved_at,
            content=earnings_content,
            metadata={"provider": self.provider, "symbol": symbol},
        )
        lower = as_of - timedelta(days=request.lookback_days or 730)
        eligible = [
            item
            for item in _alpha_fiscal_quarters(earnings)
            if lower <= item[2] <= as_of
        ]
        eligible.sort(key=lambda item: (item[2], item[0]), reverse=True)
        source_type = _first_supported(request.source_types, self.source_types)
        documents: list[RawInfoDocument] = [raw_document]
        transcript_limit = min(request.max_documents, 2)
        failures: list[str] = []
        for quarter, fiscal_end, available in eligible[: transcript_limit + 2]:
            if len(documents) - 1 >= transcript_limit:
                break
            try:
                raw = self.client.earnings_call_transcript(symbol, quarter)
            except DataQuotaDeferred:
                raise
            except Exception as exc:
                failures.append(type(exc).__name__)
                continue
            turns = raw.get("transcript", ()) if isinstance(raw, Mapping) else ()
            valid_turns = [
                item
                for item in turns
                if isinstance(item, Mapping) and str(item.get("content", "")).strip()
            ]
            if (
                str(raw.get("symbol", "")).upper() != symbol
                or str(raw.get("quarter", "")) != quarter
                or not valid_turns
            ):
                failures.append("invalid_transcript_payload")
                continue
            content = _canonical_json(raw)
            documents.append(
                RawInfoDocument.create(
                    document_id=_document_id(
                        self.provider, company_id, source_type, content
                    ),
                    company_id=company_id,
                    source_type=source_type,
                    published_at=available - timedelta(days=1),
                    available_at=available,
                    content=content,
                    metadata={
                        "provider": self.provider,
                        "symbol": symbol,
                        "quarter": quarter,
                        "fiscal_date_ending": fiscal_end.isoformat(),
                        "reported_date": (available - timedelta(days=1)).date().isoformat(),
                    },
                )
            )
        if len(documents) == 1 and failures:
            raise AcquisitionFailure(
                DataGapReason.PROVIDER_ERROR,
                "Alpha Vantage transcripts were unavailable for eligible fiscal "
                "quarters: "
                + ", ".join(failures),
            )
        return AcquisitionResult(
            documents=tuple(documents),
            events=_provider_events(self.client, cursor),
        )


class HistoricalPriceAdapter:
    """Materialize a complete requested historical OHLCV window."""

    source_types = ("price_daily", "historical_price", "prices", "market_data")
    capabilities = ("price_daily",)

    def __init__(
        self,
        provider: str,
        fetch: Callable[[str, date, date], Iterable[Any]],
        *,
        event_source: Any = None,
    ) -> None:
        self.provider = provider
        self.fetch = fetch
        self.event_source = event_source

    def acquire(
        self,
        request: RawInfoRequest,
        *,
        company_id: str,
        identity: Mapping[str, Any],
        as_of: datetime,
    ) -> AcquisitionResult:
        cursor = _event_cursor(self.event_source)
        symbol = _identity_value(identity, "ticker", "symbol")
        cutoff_day = utc_day_of_instant(as_of)
        start = cutoff_day - timedelta(days=request.lookback_days or 365)
        end = cutoff_day - timedelta(days=1)
        bars = sorted(
            (
                item
                for item in self.fetch(symbol, start, end)
                if item.as_of_date <= end
            ),
            key=lambda item: item.as_of_date,
        )
        if not bars:
            return AcquisitionResult()
        content = _canonical_json([_price_bar_dict(item) for item in bars])
        prices = [
            float(
                item.adjusted_close
                if item.adjusted_close is not None
                else item.close
            )
            for item in bars
        ]
        available = _midnight(max(item.as_of_date for item in bars) + timedelta(days=1))
        if available > as_of:
            available = as_of
        source_type = _first_supported(request.source_types, self.source_types)
        document = RawInfoDocument.create(
            document_id=_document_id(self.provider, company_id, source_type, content),
            company_id=company_id,
            source_type=source_type,
            published_at=available,
            available_at=available,
            content=content,
            metadata={
                "provider": self.provider,
                "symbol": symbol,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "prices": prices,
            },
        )
        return AcquisitionResult(
            documents=(document,),
            events=_provider_events(self.event_source, cursor),
        )


class HistoricalUnavailableAdapter:
    """Fail closed for current-only provider capabilities such as overview."""

    capabilities = ("company_profile",)
    available = False
    unavailability_reason = "historical_data_unavailable"

    def __init__(self, provider: str, source_types: Iterable[str]) -> None:
        self.provider = provider
        self.source_types = tuple(source_types)

    def acquire(self, request: RawInfoRequest, **_: Any) -> AcquisitionResult:
        raise AcquisitionFailure(
            DataGapReason.HISTORICAL_DATA_UNAVAILABLE,
            "This provider endpoint has no auditable historical availability time.",
        )


class UnavailableProviderAdapter:
    """Represent a known adapter whose configured provider cannot be constructed."""

    available = False

    def __init__(
        self,
        provider: str,
        source_types: Iterable[str],
        capabilities: Iterable[str],
        message: str,
        *,
        unavailability_reason: str = "provider_unavailable",
    ) -> None:
        self.provider = provider
        self.source_types = tuple(source_types)
        self.capabilities = tuple(capabilities)
        self.message = message
        self.unavailability_reason = unavailability_reason

    def acquire(self, request: RawInfoRequest, **_: Any) -> AcquisitionResult:
        raise AcquisitionFailure(DataGapReason.PROVIDER_ERROR, self.message)


def _first_supported(requested: Iterable[str], supported: Iterable[str]) -> str:
    allowed = set(supported)
    return next(item for item in requested if item in allowed)


_SEC_OPERATING_FORMS = frozenset(
    {"10-k", "10-q", "8-k", "20-f", "40-f", "6-k"}
)


def _overlapping_sec_history_files(
    submissions: Mapping[str, Any],
    *,
    lower: date,
    upper: date,
) -> list[dict[str, str]]:
    files = submissions.get("filings", {}).get("files", ())
    if not isinstance(files, list):
        return []
    overlapping: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, Mapping):
            continue
        filing_from = _iso_date(item.get("filingFrom"))
        filing_to = _iso_date(item.get("filingTo"))
        name = str(item.get("name", ""))
        if (
            filing_from is None
            or filing_to is None
            or not name
            or filing_from > upper
            or filing_to < lower
        ):
            continue
        overlapping.append(
            {
                "name": name,
                "filingFrom": filing_from.isoformat(),
                "filingTo": filing_to.isoformat(),
            }
        )
    overlapping.sort(
        key=lambda item: (item["filingTo"], item["filingFrom"], item["name"]),
        reverse=True,
    )
    return overlapping


def _deduplicate_filings_by_accession(filings: Iterable[Any]) -> list[Any]:
    unique: dict[str, Any] = {}
    for filing in filings:
        unique.setdefault(str(filing.accession_number), filing)
    return list(unique.values())


def _alpha_datetime(value: Any) -> datetime | None:
    text = str(value or "")
    for pattern in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _alpha_fiscal_quarters(
    raw: Mapping[str, Any],
) -> tuple[tuple[str, date, datetime], ...]:
    """Map Alpha fiscal period ends to quarter labels and conservative availability."""

    annual_ends = sorted(
        {
            parsed
            for item in raw.get("annualEarnings", ())
            if isinstance(item, Mapping)
            if (parsed := _iso_date(item.get("fiscalDateEnding"))) is not None
        }
    )
    quarterly: dict[date, date] = {}
    for item in raw.get("quarterlyEarnings", ()):
        if not isinstance(item, Mapping):
            continue
        fiscal_end = _iso_date(item.get("fiscalDateEnding"))
        reported = _iso_date(item.get("reportedDate"))
        if fiscal_end is not None and reported is not None:
            quarterly[fiscal_end] = reported
    values: list[tuple[str, date, datetime]] = []
    previous_annual: date | None = None
    for annual_end in annual_ends:
        period_ends = sorted(
            item
            for item in quarterly
            if (previous_annual is None or item > previous_annual)
            and item <= annual_end
            and (annual_end - item).days <= 380
        )
        if len(period_ends) == 4:
            for index, fiscal_end in enumerate(period_ends, start=1):
                reported = quarterly[fiscal_end]
                values.append(
                    (
                        f"{annual_end.year}Q{index}",
                        fiscal_end,
                        _midnight(reported + timedelta(days=1)),
                    )
                )
        previous_annual = annual_end
    return tuple(values)


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _price_bar_dict(bar: Any) -> dict[str, Any]:
    value = asdict(bar)
    value["as_of_date"] = bar.as_of_date.isoformat()
    value["retrieved_at"] = bar.retrieved_at.isoformat()
    return value


def _event_cursor(client: Any) -> int:
    events = getattr(getattr(client, "transport", None), "request_events", ())
    return len(events)


def _provider_events(client: Any, cursor: int) -> tuple[ResolutionEvent, ...]:
    entries = getattr(getattr(client, "transport", None), "request_events", ())
    return tuple(
        ResolutionEvent(
            "provider_request",
            {
                "provider": entry.source_key,
                "capability": entry.capability.value,
                "status": entry.status.value,
                "cache_key": entry.cache_key,
                "endpoint": entry.endpoint,
            },
        )
        for entry in entries[cursor:]
    )
