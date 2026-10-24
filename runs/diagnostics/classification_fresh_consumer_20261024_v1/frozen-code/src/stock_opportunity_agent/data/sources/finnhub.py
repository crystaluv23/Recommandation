"""Finnhub free-key data-source provider."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Mapping
from urllib import parse

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import DataSourceError, JsonTransport
from stock_opportunity_agent.models import ValidationError


class FinnhubClient:
    """Finnhub adapter for company news, metrics, filings mirrors, and estimates."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://finnhub.io/api/v1",
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValidationError("Finnhub api_key must not be empty")
        from stock_opportunity_agent.data.sources.core import UrllibJsonTransport

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_config(
        cls,
        config: DataSourceConfig,
        environ: Mapping[str, str] | None = None,
        transport: JsonTransport | None = None,
    ) -> "FinnhubClient":
        """Create a Finnhub client from the configured API-key env var."""

        env = os.environ if environ is None else environ
        api_key = env.get(config.finnhub_api_key_env_var)
        if not api_key:
            raise DataSourceError(f"{config.finnhub_api_key_env_var} is not set")
        return cls(api_key, transport=transport)

    def company_profile(self, symbol: str) -> dict[str, Any]:
        """Fetch raw company profile data."""

        return self._query("stock/profile2", {"symbol": _symbol(symbol)})

    def quote(self, symbol: str) -> dict[str, Any]:
        """Fetch raw quote data."""

        return self._query("quote", {"symbol": _symbol(symbol)})

    def company_news(self, symbol: str, from_date: date, to_date: date) -> dict[str, Any] | list[Any]:
        """Fetch raw company news for a date window."""

        return self._query(
            "company-news",
            {"symbol": _symbol(symbol), "from": from_date.isoformat(), "to": to_date.isoformat()},
        )

    def basic_financials(self, symbol: str, *, metric: str = "all") -> dict[str, Any]:
        """Fetch raw basic financial metrics."""

        return self._query("stock/metric", {"symbol": _symbol(symbol), "metric": metric})

    def financials_reported(self, symbol: str) -> dict[str, Any]:
        """Fetch raw as-reported financial statements."""

        return self._query("stock/financials-reported", {"symbol": _symbol(symbol)})

    def company_filings(self, symbol: str, from_date: date, to_date: date) -> dict[str, Any] | list[Any]:
        """Fetch raw company filings mirror metadata."""

        return self._query(
            "stock/filings",
            {"symbol": _symbol(symbol), "from": from_date.isoformat(), "to": to_date.isoformat()},
        )

    def recommendation_trends(self, symbol: str) -> dict[str, Any] | list[Any]:
        """Fetch raw analyst recommendation trend data."""

        return self._query("stock/recommendation", {"symbol": _symbol(symbol)})

    def earnings_calendar(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """Fetch raw earnings-calendar data."""

        params: dict[str, str] = {}
        if from_date is not None:
            params["from"] = from_date.isoformat()
        if to_date is not None:
            params["to"] = to_date.isoformat()
        if symbol:
            params["symbol"] = _symbol(symbol)
        return self._query("calendar/earnings", params)

    def earnings_surprises(self, symbol: str) -> dict[str, Any] | list[Any]:
        """Fetch raw earnings surprise history."""

        return self._query("stock/earnings", {"symbol": _symbol(symbol)})

    def transcript_list(self, symbol: str) -> dict[str, Any]:
        """Fetch raw transcript list for a symbol."""

        return self._query("stock/transcripts", {"symbol": _symbol(symbol)})

    def transcript(self, transcript_id: str) -> dict[str, Any]:
        """Fetch one raw transcript by provider transcript id."""

        if not transcript_id.strip():
            raise ValidationError("transcript_id must not be empty")
        return self._query("stock/transcripts", {"id": transcript_id})

    def _query(self, path: str, params: Mapping[str, str]) -> dict[str, Any] | list[Any]:
        query = parse.urlencode({**params, "token": self.api_key})
        data = self.transport.get_json(f"{self.base_url}/{path}?{query}", {})
        if isinstance(data, dict) and "error" in data:
            raise DataSourceError(str(data["error"]))
        return data


def _symbol(symbol: str) -> str:
    if not symbol.strip():
        raise ValidationError("symbol must not be empty")
    return symbol.upper()


@register("finnhub")
def source(
    config: DataSourceConfig,
    environ: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> FinnhubClient:
    """Registered Finnhub source factory."""

    return FinnhubClient.from_config(config, environ=environ, transport=transport)
