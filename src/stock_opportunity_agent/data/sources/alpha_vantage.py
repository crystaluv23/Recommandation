"""Alpha Vantage data-source provider."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Mapping
from urllib import parse

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import DataSourceError, JsonTransport, PriceBar, utc_now
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

    def company_overview(self, symbol: str) -> dict[str, Any]:
        """Fetch raw company overview JSON."""

        return self._query({"function": "OVERVIEW", "symbol": symbol.upper()})

    def news_sentiment(self, symbol: str, *, limit: int = 50) -> dict[str, Any]:
        """Fetch raw news sentiment JSON for later evidence normalization."""

        if not 1 <= limit <= 1000:
            raise ValidationError("limit must be between 1 and 1000")
        return self._query({"function": "NEWS_SENTIMENT", "tickers": symbol.upper(), "limit": str(limit)})

    def _query(self, params: Mapping[str, str]) -> dict[str, Any]:
        query = parse.urlencode({**params, "apikey": self.api_key})
        data = self.transport.get_json(f"{self.base_url}?{query}", {})
        if "Error Message" in data:
            raise DataSourceError(str(data["Error Message"]))
        if "Note" in data:
            raise DataSourceError(str(data["Note"]))
        return data


@register("alpha_vantage")
def source(
    config: DataSourceConfig,
    environ: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> AlphaVantageClient:
    """Registered Alpha Vantage source factory."""

    return AlphaVantageClient.from_config(config, environ=environ, transport=transport)
