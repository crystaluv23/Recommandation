"""Exact, resumable historical company-news acquisition into Raw Info."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib import parse

from stock_opportunity_agent.artifacts import (
    atomic_write_json as _atomic_write_json,
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import DataSourceError
from stock_opportunity_agent.data.sources.state import (
    DataQuotaDeferred,
    RawCacheKey,
    RawDataCache,
)
from stock_opportunity_agent.models import ValidationError


ALPHA_NEWS_PLAN_SCHEMA = "alpha-vantage-historical-news-plan-v1"
ALPHA_NEWS_PROGRESS_SCHEMA = "alpha-vantage-historical-news-progress-v1"
_ALPHA_ENDPOINT = "https://www.alphavantage.co/query"
_FORBIDDEN_SCOPE_FIELDS = frozenset(
    {
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
)


class HistoricalNewsClient(Protocol):
    """Provider boundary used by the historical-news executor."""

    def news_sentiment(
        self,
        symbol: str,
        *,
        limit: int,
        time_from: datetime,
        time_to: datetime,
        sort: str,
    ) -> dict[str, Any]:
        """Return one exact ticker news response."""


def write_alpha_vantage_news_plan(
    *,
    acquisition_scope_path: str | Path,
    output_path: str | Path,
    lookback_days: int = 365,
    limit: int = 1000,
    sort: str = "LATEST",
) -> dict[str, Any]:
    """Write one exact, label-free historical-news request per company."""

    if lookback_days < 1:
        raise ValidationError("historical news lookback_days must be positive")
    if not 1 <= limit <= 1000:
        raise ValidationError("historical news limit must be between 1 and 1000")
    if sort not in {"LATEST", "EARLIEST", "RELEVANCE"}:
        raise ValidationError("historical news sort is invalid")
    source_path = Path(acquisition_scope_path)
    scope = _read_json(source_path)
    if scope.get("schema_version") != "expanded-case-acquisition-scope-v1":
        raise ValidationError("unsupported expanded acquisition scope schema")
    if scope.get("outcome_fields_included") is not False:
        raise ValidationError("historical news scope must exclude outcomes")
    if scope.get("split_ownership_included") is not False:
        raise ValidationError("historical news scope must exclude split ownership")
    _assert_label_free(scope)
    companies = scope.get("companies")
    prediction_dates = scope.get("prediction_dates")
    if not isinstance(companies, list):
        raise ValidationError("historical news scope companies must be a list")
    if int(scope.get("company_count", -1)) != len(companies):
        raise ValidationError("historical news scope company count mismatch")
    if not isinstance(prediction_dates, list) or not prediction_dates:
        raise ValidationError("historical news prediction dates are missing")
    dates = sorted(
        _parse_date(value, "historical news prediction date")
        for value in prediction_dates
    )
    start_at = datetime.combine(
        dates[0] - timedelta(days=lookback_days), time.min, tzinfo=timezone.utc
    )
    end_at = datetime.combine(dates[-1], time(23, 59), tzinfo=timezone.utc)
    request_parameters = {
        "function": "NEWS_SENTIMENT",
        "limit": str(limit),
        "sort": sort,
        "time_from": _alpha_time(start_at),
        "time_to": _alpha_time(end_at),
    }
    items_by_symbol: dict[str, dict[str, Any]] = {}
    for company in companies:
        if not isinstance(company, Mapping):
            raise ValidationError("historical news company must be an object")
        symbol = str(company.get("symbol") or "").strip().upper()
        company_id = str(company.get("company_id") or "").strip()
        if not symbol or not company_id:
            raise ValidationError("historical news company identity is incomplete")
        item = {
            "item_id": "avnews_"
            + _canonical_hash({"company_id": company_id, "symbol": symbol})[:24],
            "company_id": company_id,
            "symbol": symbol,
            "source_endpoint": _ALPHA_ENDPOINT,
            "request_parameters": {
                **request_parameters,
                "tickers": symbol,
            },
        }
        existing = items_by_symbol.get(symbol)
        if existing is not None and existing != item:
            raise ValidationError(f"conflicting historical news symbol: {symbol}")
        items_by_symbol[symbol] = item
    items = sorted(items_by_symbol.values(), key=lambda item: item["symbol"])
    payload: dict[str, Any] = {
        "schema_version": ALPHA_NEWS_PLAN_SCHEMA,
        "source_artifact": _artifact_identity(source_path),
        "selection": {
            "provider": "alpha_vantage",
            "capability": DataCapability.NEWS.value,
            "prediction_dates": [value.isoformat() for value in dates],
            "lookback_days": lookback_days,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "limit": limit,
            "sort": sort,
            "availability_policy": "provider_time_published_as_utc",
            "relevance_policy": "exact_symbol_ticker_sentiment_row_required",
            "content_scope": "provider_title_summary",
            "saturation_policy": "limit_sized_response_requires_follow_up",
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
        "request_count": len(items),
        "items": items,
    }
    payload["plan_hash"] = _canonical_hash(payload)
    _atomic_write_json(Path(output_path), payload)
    return payload


def load_alpha_vantage_news_plan(path: str | Path) -> dict[str, Any]:
    """Load and validate one exact historical-news plan."""

    payload = _read_json(Path(path))
    if payload.get("schema_version") != ALPHA_NEWS_PLAN_SCHEMA:
        raise ValidationError("unsupported historical news plan schema")
    supplied_hash = str(payload.get("plan_hash") or "")
    without_hash = dict(payload)
    without_hash.pop("plan_hash", None)
    if supplied_hash != _canonical_hash(without_hash):
        raise ValidationError("historical news plan hash mismatch")
    selection = payload.get("selection")
    if not isinstance(selection, Mapping):
        raise ValidationError("historical news selection is missing")
    if selection.get("provider") != "alpha_vantage":
        raise ValidationError("historical news provider is invalid")
    start_at = _parse_aware_datetime(selection.get("start_at"), "start_at")
    end_at = _parse_aware_datetime(selection.get("end_at"), "end_at")
    if end_at <= start_at:
        raise ValidationError("historical news window is invalid")
    limit = int(selection.get("limit", 0))
    if not 1 <= limit <= 1000:
        raise ValidationError("historical news plan limit is invalid")
    sort = str(selection.get("sort") or "")
    if sort not in {"LATEST", "EARLIEST", "RELEVANCE"}:
        raise ValidationError("historical news plan sort is invalid")
    items = payload.get("items")
    if not isinstance(items, list) or int(payload.get("request_count", -1)) != len(items):
        raise ValidationError("historical news plan item count mismatch")
    seen_ids: set[str] = set()
    seen_symbols: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ValidationError("historical news plan item must be an object")
        item_id = str(item.get("item_id") or "")
        symbol = str(item.get("symbol") or "")
        if not item_id or item_id in seen_ids or not symbol or symbol in seen_symbols:
            raise ValidationError("historical news plan identities must be unique")
        seen_ids.add(item_id)
        seen_symbols.add(symbol)
        if item.get("source_endpoint") != _ALPHA_ENDPOINT:
            raise ValidationError("historical news plan endpoint is invalid")
        expected = {
            "function": "NEWS_SENTIMENT",
            "limit": str(limit),
            "sort": sort,
            "time_from": _alpha_time(start_at),
            "time_to": _alpha_time(end_at),
            "tickers": symbol,
        }
        if item.get("request_parameters") != expected:
            raise ValidationError("historical news request parameters are invalid")
    _assert_label_free(payload)
    return payload


def preview_alpha_vantage_news_backfill(
    *,
    plan_path: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
    raw_info_root: str | Path,
) -> dict[str, Any]:
    """Describe exact historical-news work without network I/O or writes."""

    plan = load_alpha_vantage_news_plan(plan_path)
    progress = _load_progress(Path(progress_path), str(plan["plan_hash"]))
    completed = dict(progress.get("completed", {}))
    pending = 0
    cached = 0
    for item in plan["items"]:
        if item["item_id"] in completed:
            continue
        pending += 1
        cached += int(cache.get_json(_cache_key(item)) is not None)
    return {
        "status": "zero_network_preview",
        "stage": "alpha_vantage_historical_news",
        "plan_hash": plan["plan_hash"],
        "request_count": plan["request_count"],
        "completed_count": len(completed),
        "pending_count": pending,
        "pending_cache_hits": cached,
        "maximum_new_network_requests": pending - cached,
        "provider_daily_limit": 25,
        "raw_info_root": str(Path(raw_info_root).resolve()),
        "external_calls": 0,
    }


def run_alpha_vantage_news_backfill(
    *,
    plan_path: str | Path,
    cache: RawDataCache,
    progress_path: str | Path,
    raw_info_root: str | Path,
    client: HistoricalNewsClient,
    max_network_requests: int,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute or resume one bounded historical-news invocation."""

    if max_network_requests < 0:
        raise ValidationError("max_network_requests must be non-negative")
    plan = load_alpha_vantage_news_plan(plan_path)
    plan_hash = str(plan["plan_hash"])
    selection = plan["selection"]
    start_at = _parse_aware_datetime(selection["start_at"], "start_at")
    end_at = _parse_aware_datetime(selection["end_at"], "end_at")
    limit = int(selection["limit"])
    sort = str(selection["sort"])
    state_path = Path(progress_path)
    progress = _load_progress(state_path, plan_hash)
    completed: dict[str, Any] = dict(progress.get("completed", {}))
    failures: list[dict[str, Any]] = list(progress.get("failures", ()))
    store = RawInfoStore(raw_info_root)
    network_requests = 0
    cache_hits = 0
    appended = 0
    reused = 0
    excluded = 0
    failures_this_run = 0
    last_stop = "plan_exhausted"

    for item_index, item in enumerate(plan["items"], start=1):
        item_id = str(item["item_id"])
        if item_id in completed:
            continue
        key = _cache_key(item)
        was_cached = cache.get_json(key) is not None
        if not was_cached and network_requests >= max_network_requests:
            last_stop = "invocation_network_limit_reached"
            _emit_progress(
                on_progress,
                status="paused_network_limit",
                item_index=item_index,
                item_count=len(plan["items"]),
                item=item,
                cache_hit=False,
            )
            break
        _emit_progress(
            on_progress,
            status="starting",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )
        try:
            response = client.news_sentiment(
                str(item["symbol"]),
                limit=limit,
                time_from=start_at,
                time_to=end_at,
                sort=sort,
            )
            feed = _validated_feed(response)
            cached_response = cache.get(key)
            retrieved_at = cached_response.retrieved_at if cached_response else now()
            documents, exclusion_counts = _normalize_feed(
                feed,
                company_id=str(item["company_id"]),
                symbol=str(item["symbol"]),
                start_at=start_at,
                end_at=end_at,
                retrieved_at=retrieved_at,
                plan_hash=plan_hash,
            )
            item_appended = 0
            item_reused = 0
            for document in documents:
                if store.append(document):
                    item_appended += 1
                else:
                    item_reused += 1
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
        appended += item_appended
        reused += item_reused
        item_excluded = sum(exclusion_counts.values())
        excluded += item_excluded
        times = [document.published_at for document in documents]
        completed[item_id] = {
            "cache_key": key.digest,
            "response_hash": _canonical_hash(response),
            "provider_feed_count": len(feed),
            "stored_document_count": len(documents),
            "documents_appended": item_appended,
            "documents_reused": item_reused,
            "excluded_feed_count": item_excluded,
            "exclusion_reason_counts": dict(sorted(exclusion_counts.items())),
            "provider_limit_reached": len(feed) >= limit,
            "earliest_stored_at": min(times).isoformat() if times else None,
            "latest_stored_at": max(times).isoformat() if times else None,
            "retrieved_at": retrieved_at.isoformat(),
            "completed_at": now().isoformat(),
        }
        last_stop = "item_completed"
        _store_progress(state_path, progress, completed, failures, last_stop, now())
        _emit_progress(
            on_progress,
            status="completed",
            item_index=item_index,
            item_count=len(plan["items"]),
            item=item,
            cache_hit=was_cached,
        )

    pending_count = len(plan["items"]) - len(completed)
    status = "completed" if pending_count == 0 else "paused_resumable"
    _store_progress(state_path, progress, completed, failures, last_stop, now())
    saturated = sum(
        bool(value.get("provider_limit_reached"))
        for value in completed.values()
        if isinstance(value, Mapping)
    )
    return {
        "status": status,
        "stage": "alpha_vantage_historical_news",
        "plan_hash": plan_hash,
        "request_count": plan["request_count"],
        "completed_count": len(completed),
        "pending_count": pending_count,
        "network_requests_this_run": network_requests,
        "cache_hits_this_run": cache_hits,
        "documents_appended_this_run": appended,
        "documents_reused_this_run": reused,
        "excluded_feed_rows_this_run": excluded,
        "failures_this_run": failures_this_run,
        "provider_limit_reached_count": saturated,
        "last_stop": last_stop,
        "progress_path": str(state_path.resolve()),
    }


def alpha_vantage_error_message(payload: Any) -> str | None:
    """Return a provider error message before a response can enter raw cache."""

    if not isinstance(payload, Mapping):
        return None
    for key in ("Error Message", "Note", "Information"):
        if key in payload:
            return str(payload[key])
    return None


def _validated_feed(response: Any) -> list[Any]:
    if not isinstance(response, Mapping):
        raise DataSourceError("Alpha Vantage news response must be an object")
    feed = response.get("feed")
    if not isinstance(feed, list):
        raise DataSourceError("Alpha Vantage news response missing feed")
    return feed


def _normalize_feed(
    feed: list[Any],
    *,
    company_id: str,
    symbol: str,
    start_at: datetime,
    end_at: datetime,
    retrieved_at: datetime,
    plan_hash: str,
) -> tuple[list[RawInfoDocument], Counter[str]]:
    excluded: Counter[str] = Counter()
    by_identity: dict[str, RawInfoDocument] = {}
    for raw in feed:
        normalized = _normalize_news_item(
            raw,
            company_id=company_id,
            symbol=symbol,
            start_at=start_at,
            end_at=end_at,
            retrieved_at=retrieved_at,
            plan_hash=plan_hash,
        )
        if isinstance(normalized, str):
            excluded[normalized] += 1
            continue
        identity, document = normalized
        existing = by_identity.get(identity)
        if existing is not None:
            excluded["duplicate_provider_identity"] += 1
            if len(existing.content) >= len(document.content):
                continue
        by_identity[identity] = document
    documents = sorted(
        by_identity.values(),
        key=lambda item: (item.published_at, item.document_id),
    )
    return documents, excluded


def _normalize_news_item(
    raw: Any,
    *,
    company_id: str,
    symbol: str,
    start_at: datetime,
    end_at: datetime,
    retrieved_at: datetime,
    plan_hash: str,
) -> tuple[str, RawInfoDocument] | str:
    if not isinstance(raw, Mapping):
        return "non_object_feed_row"
    published_at = _parse_alpha_published(raw.get("time_published"))
    if published_at is None:
        return "missing_or_invalid_time_published"
    if published_at < start_at or published_at > end_at:
        return "outside_plan_window"
    title = str(raw.get("title") or "").strip()
    if not title:
        return "missing_title"
    ticker_rows = raw.get("ticker_sentiment")
    if not isinstance(ticker_rows, list):
        return "missing_ticker_sentiment"
    matches = [
        row
        for row in ticker_rows
        if isinstance(row, Mapping)
        and str(row.get("ticker") or "").strip().upper() == symbol
    ]
    if not matches:
        return "missing_exact_symbol_relevance"
    match = max(matches, key=_ticker_relevance)
    summary = str(raw.get("summary") or "").strip()
    content = title if not summary else f"{title}\n\n{summary}"
    raw_url = str(raw.get("url") or "").strip()
    source_url = raw_url if _is_http_url(raw_url) else ""
    identity = _canonical_hash(
        {
            "symbol": symbol,
            "time_published": published_at.isoformat(),
            "source_url": source_url,
            "title": title,
        }
    )
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    document_id = "avnews_" + _canonical_hash(
        {"identity": identity, "content_hash": content_hash}
    )[:24]
    source_id = f"alpha_vantage_news:{symbol}:{identity[:20]}"
    topics = raw.get("topics")
    topic_rows = [dict(row) for row in topics if isinstance(row, Mapping)] if isinstance(topics, list) else []
    authors = raw.get("authors")
    author_rows = [str(value) for value in authors if str(value).strip()] if isinstance(authors, list) else []
    document = RawInfoDocument.create(
        document_id=document_id,
        company_id=company_id,
        source_type="news",
        published_at=published_at,
        available_at=published_at,
        content=content,
        metadata={
            "provider": "alpha_vantage",
            "source_id": source_id,
            "source_url": source_url or f"urn:{source_id}",
            "symbol": symbol,
            "title": title,
            "publisher": str(raw.get("source") or ""),
            "publisher_category": str(raw.get("category_within_source") or ""),
            "authors": author_rows,
            "topics": topic_rows,
            "overall_sentiment_score": raw.get("overall_sentiment_score"),
            "provider_overall_sentiment_class": raw.get(
                "overall_sentiment_label"
            ),
            "ticker_relevance_score": match.get("relevance_score"),
            "ticker_sentiment_score": match.get("ticker_sentiment_score"),
            "provider_ticker_sentiment_class": match.get(
                "ticker_sentiment_label"
            ),
            "time_published_raw": raw.get("time_published"),
            "content_scope": "provider_title_summary",
            "retrieved_at": retrieved_at.isoformat(),
            "backfill_plan_hash": plan_hash,
        },
    )
    return identity, document


def _ticker_relevance(row: Mapping[str, Any]) -> float:
    try:
        return float(row.get("relevance_score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _parse_alpha_published(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    for format_string, length in (("%Y%m%dT%H%M%S", 15), ("%Y%m%dT%H%M", 13)):
        try:
            return datetime.strptime(value[:length], format_string).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    return None


def _is_http_url(value: str) -> bool:
    parsed = parse.urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _cache_key(item: Mapping[str, Any]) -> RawCacheKey:
    parameters = item.get("request_parameters")
    if not isinstance(parameters, Mapping):
        raise ValidationError("historical news request parameters are missing")
    query = parse.urlencode({**dict(parameters), "apikey": "configured-secret"})
    return RawCacheKey.from_request(
        "alpha_vantage",
        DataCapability.NEWS,
        "GET",
        f"{item['source_endpoint']}?{query}",
    )


def _load_progress(path: Path, plan_hash: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": ALPHA_NEWS_PROGRESS_SCHEMA,
            "plan_hash": plan_hash,
            "completed": {},
            "failures": [],
        }
    progress = _read_json(path)
    if progress.get("schema_version") != ALPHA_NEWS_PROGRESS_SCHEMA:
        raise ValidationError("unsupported historical news progress schema")
    if progress.get("plan_hash") != plan_hash:
        raise ValidationError("historical news progress plan hash mismatch")
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


def _emit_progress(
    callback: Callable[[Mapping[str, Any]], None] | None,
    *,
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
            "stage": "alpha_vantage_historical_news",
            "status": status,
            "item_index": item_index,
            "item_count": item_count,
            "item_id": str(item["item_id"]),
            "company_id": str(item["company_id"]),
            "symbol": str(item["symbol"]),
            "cache_hit": cache_hit,
        }
    )


def _assert_label_free(value: Any, path: str = "scope") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in _FORBIDDEN_SCOPE_FIELDS:
                raise ValidationError(f"forbidden label/split field: {path}.{key}")
            _assert_label_free(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_label_free(nested, f"{path}[{index}]")


def _alpha_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M")


def _parse_date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"invalid {label}: {value}") from exc


def _parse_aware_datetime(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"invalid {label}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _artifact_identity(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValidationError(f"JSON object required: {path}")
    return value
