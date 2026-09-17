"""Alpha Vantage data-source provider."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Iterable, Mapping
from urllib import parse

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import (
    DataSourceError,
    JsonTransport,
    PriceBar,
    SecurityListing,
    optional_date,
    parse_csv_rows,
    utc_now,
)
from stock_opportunity_agent.data.sources.state import (
    DataQuotaDeferred,
    QUOTA_DEFERRED_ERROR_PREFIX,
)
from stock_opportunity_agent.models import ValidationError


class AlphaVantageClient:
    """Alpha Vantage free-key adapter for compact stock data."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://www.alphavantage.co/query",
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValidationError("Alpha Vantage api_key must not be empty")
        from stock_opportunity_agent.data.sources.core import UrllibJsonTransport

        self.api_key = api_key
        self.base_url = base_url
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_config(
        cls,
        config: DataSourceConfig,
        environ: Mapping[str, str] | None = None,
        transport: JsonTransport | None = None,
    ) -> "AlphaVantageClient":
        """Create an Alpha Vantage client from the configured API-key env var."""

        env = os.environ if environ is None else environ
        api_key = env.get(config.alpha_vantage_api_key_env_var)
        if not api_key:
            raise DataSourceError(f"{config.alpha_vantage_api_key_env_var} is not set")
        return cls(api_key, transport=transport)

    def daily_prices(self, symbol: str, *, outputsize: str = "compact") -> list[PriceBar]:
        """Fetch and normalize daily prices from ``TIME_SERIES_DAILY``."""

        if outputsize not in {"compact", "full"}:
            raise ValidationError("outputsize must be compact or full")
        data = self._query({"function": "TIME_SERIES_DAILY", "symbol": symbol.upper(), "outputsize": outputsize})
        series = data.get("Time Series (Daily)")
        if not isinstance(series, Mapping):
            raise DataSourceError("Alpha Vantage response missing daily time series")
        retrieved_at = utc_now()
        bars = [
            PriceBar(
                symbol=symbol.upper(),
                as_of_date=date.fromisoformat(day),
                open=float(values["1. open"]),
                high=float(values["2. high"]),
                low=float(values["3. low"]),
                close=float(values["4. close"]),
                volume=int(values["5. volume"]),
                source="alpha_vantage",
                retrieved_at=retrieved_at,
            )
            for day, values in series.items()
        ]
        return sorted(bars, key=lambda bar: bar.as_of_date)

    def listing_status(self, *, listing_date: date | None = None, state: str = "active") -> list[SecurityListing]:
        """Fetch and normalize Alpha Vantage listing status CSV rows."""

        if state not in {"active", "delisted"}:
            raise ValidationError("state must be active or delisted")
        params = {"function": "LISTING_STATUS", "state": state}
        if listing_date is not None:
            params["date"] = listing_date.isoformat()
        text = self._query_text(params)
        if text.lstrip().startswith("{"):
            raise DataSourceError(f"Alpha Vantage listing status returned non-CSV response: {text[:200]}")
        rows = parse_csv_rows(text)
        retrieved_at = utc_now()
        listings: list[SecurityListing] = []
        for row in rows:
            symbol = (row.get("symbol") or "").strip()
            name = (row.get("name") or "").strip()
            if not symbol or not name:
                continue
            listings.append(
                SecurityListing(
                    symbol=symbol,
                    name=name,
                    exchange=row.get("exchange") or None,
                    asset_type=row.get("assetType") or None,
                    status=row.get("status") or state,
                    source="alpha_vantage",
                    retrieved_at=retrieved_at,
                    ipo_date=optional_date(row.get("ipoDate")),
                    delisting_date=optional_date(row.get("delistingDate")),
                )
            )
        if not listings:
            raise DataSourceError("Alpha Vantage listing status returned no listing rows")
        return listings

    def company_overview(self, symbol: str) -> dict[str, Any]:
        """Fetch raw company overview JSON."""

        return self._query({"function": "OVERVIEW", "symbol": symbol.upper()})

    def income_statement(self, symbol: str) -> dict[str, Any]:
        """Fetch raw annual and quarterly income statements."""

        return self._query({"function": "INCOME_STATEMENT", "symbol": symbol.upper()})

    def balance_sheet(self, symbol: str) -> dict[str, Any]:
        """Fetch raw annual and quarterly balance sheets."""

        return self._query({"function": "BALANCE_SHEET", "symbol": symbol.upper()})

    def cash_flow(self, symbol: str) -> dict[str, Any]:
        """Fetch raw annual and quarterly cash-flow statements."""

        return self._query({"function": "CASH_FLOW", "symbol": symbol.upper()})

    def earnings(self, symbol: str) -> dict[str, Any]:
        """Fetch raw earnings history and annual EPS data."""

        return self._query({"function": "EARNINGS", "symbol": symbol.upper()})

    def earnings_estimates(self, symbol: str) -> dict[str, Any]:
        """Fetch raw analyst earnings estimates when the endpoint is available."""

        return self._query({"function": "EARNINGS_ESTIMATES", "symbol": symbol.upper()})

    def dividends(self, symbol: str) -> dict[str, Any]:
        """Fetch raw dividend history."""

        return self._query({"function": "DIVIDENDS", "symbol": symbol.upper()})

    def splits(self, symbol: str) -> dict[str, Any]:
        """Fetch raw split history."""

        return self._query({"function": "SPLITS", "symbol": symbol.upper()})

    def earnings_calendar(self, symbol: str | None = None, *, horizon: str = "3month") -> list[dict[str, str]]:
        """Fetch earnings calendar CSV rows for a symbol or the full market."""

        if horizon not in {"3month", "6month", "12month"}:
            raise ValidationError("horizon must be 3month, 6month, or 12month")
        params = {"function": "EARNINGS_CALENDAR", "horizon": horizon}
        if symbol:
            params["symbol"] = symbol.upper()
        return parse_csv_rows(self._query_text(params))

    def ipo_calendar(self) -> list[dict[str, str]]:
        """Fetch IPO calendar CSV rows."""

        return parse_csv_rows(self._query_text({"function": "IPO_CALENDAR"}))

    def news_sentiment(
        self,
        symbol: str,
        *,
        limit: int = 50,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        sort: str = "LATEST",
    ) -> dict[str, Any]:
        """Fetch raw news sentiment JSON for later evidence normalization."""

        if not 1 <= limit <= 1000:
            raise ValidationError("limit must be between 1 and 1000")
        if sort not in {"LATEST", "EARLIEST", "RELEVANCE"}:
            raise ValidationError("sort must be LATEST, EARLIEST, or RELEVANCE")
        return self._news_sentiment_query(
            tickers=symbol.upper(),
            limit=limit,
            time_from=time_from,
            time_to=time_to,
            sort=sort,
        )

    def topic_news_sentiment(
        self,
        topics: Iterable[str],
        *,
        limit: int = 50,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        sort: str = "LATEST",
    ) -> dict[str, Any]:
        """Fetch raw news sentiment JSON for provider topic context."""

        topic_values = tuple(topic.strip() for topic in topics if topic.strip())
        if not topic_values:
            raise ValidationError("topics must not be empty")
        return self._news_sentiment_query(
            topics=",".join(topic_values),
            limit=limit,
            time_from=time_from,
            time_to=time_to,
            sort=sort,
        )

    def earnings_call_transcript(self, symbol: str, quarter: str) -> dict[str, Any]:
        """Fetch raw earnings-call transcript for a quarter such as ``2024Q1``."""

        if "Q" not in quarter:
            raise ValidationError("quarter must look like 2024Q1")
        return self._query({"function": "EARNINGS_CALL_TRANSCRIPT", "symbol": symbol.upper(), "quarter": quarter})

    def etf_profile(self, symbol: str) -> dict[str, Any]:
        """Fetch raw ETF profile and holdings for benchmark context."""

        return self._query({"function": "ETF_PROFILE", "symbol": symbol.upper()})

    def economic_indicator(self, function: str, **params: str) -> dict[str, Any]:
        """Fetch a raw Alpha Vantage economic-indicator endpoint."""

        if not function.strip():
            raise ValidationError("function must not be empty")
        return self._query({"function": function.upper(), **params})

    def _query(self, params: Mapping[str, str]) -> dict[str, Any]:
        query = parse.urlencode({**params, "apikey": self.api_key})
        data = self.transport.get_json(f"{self.base_url}?{query}", {})
        problem = alpha_vantage_json_error(data)
        if problem is not None:
            detail = self._redact_secret(_alpha_vantage_error_excerpt(data))
            message = f"{problem}: {detail}" if detail else problem
            if problem.startswith(QUOTA_DEFERRED_ERROR_PREFIX):
                raise DataQuotaDeferred("alpha_vantage", None, message)
            raise DataSourceError(message)
        return data

    def _news_sentiment_query(
        self,
        *,
        limit: int,
        tickers: str | None = None,
        topics: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        sort: str = "LATEST",
    ) -> dict[str, Any]:
        if not 1 <= limit <= 1000:
            raise ValidationError("limit must be between 1 and 1000")
        if sort not in {"LATEST", "EARLIEST", "RELEVANCE"}:
            raise ValidationError("sort must be LATEST, EARLIEST, or RELEVANCE")
        if not tickers and not topics:
            raise ValidationError("tickers or topics must be provided")
        params = {"function": "NEWS_SENTIMENT"}
        if tickers:
            params["tickers"] = tickers
        if topics:
            params["topics"] = topics
        params["limit"] = str(limit)
        params["sort"] = sort
        if time_from is not None:
            params["time_from"] = _alpha_news_time(time_from)
        if time_to is not None:
            params["time_to"] = _alpha_news_time(time_to)
        return self._query(params)

    def _query_text(self, params: Mapping[str, str]) -> str:
        query = parse.urlencode({**params, "apikey": self.api_key})
        get_text = getattr(self.transport, "get_text", None)
        if get_text is None:
            raise DataSourceError("transport does not support text downloads")
        text = get_text(f"{self.base_url}?{query}", {})
        if "Error Message" in text:
            raise DataSourceError(self._redact_secret(text))
        if "Thank you for using Alpha Vantage" in text:
            raise DataSourceError(self._redact_secret(text))
        return text

    def _redact_secret(self, value: object) -> str:
        return str(value).replace(self.api_key, "<redacted>")


def _alpha_vantage_error_excerpt(body: Any) -> str:
    """Return one bounded, whitespace-collapsed provider envelope excerpt."""

    if not isinstance(body, Mapping):
        return ""
    for key in ("Information", "Note", "Error Message"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:200]
    return ""


def alpha_vantage_json_error(body: Any) -> str | None:
    """Return a stable secret-free reason for an Alpha Vantage error envelope."""

    if not isinstance(body, Mapping):
        return None
    if "Error Message" in body:
        return "alpha_vantage_invalid_request"
    if "Note" in body:
        return f"{QUOTA_DEFERRED_ERROR_PREFIX}alpha_vantage_request_limit"
    if "Information" not in body:
        return None
    information = str(body["Information"]).casefold()
    quota_markers = (
        "rate limit",
        "call frequency",
        "requests per day",
        "api frequency",
    )
    if any(marker in information for marker in quota_markers):
        return f"{QUOTA_DEFERRED_ERROR_PREFIX}alpha_vantage_request_limit"
    return "alpha_vantage_information_error"


@register("alpha_vantage")
def source(
    config: DataSourceConfig,
    environ: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> AlphaVantageClient:
    """Registered Alpha Vantage source factory."""

    return AlphaVantageClient.from_config(config, environ=environ, transport=transport)


def _alpha_news_time(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M")
