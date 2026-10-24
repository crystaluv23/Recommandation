"""Stooq CSV daily-price source."""

from __future__ import annotations

import os
from datetime import date
from typing import Mapping
from urllib import parse

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import DataSourceError, JsonTransport, PriceBar, parse_csv_rows, utc_now
from stock_opportunity_agent.models import ValidationError


class StooqClient:
    """Stooq CSV adapter for historical daily OHLCV bars."""

    def __init__(
        self,
        *,
        base_url: str = "https://stooq.com/q/d/l/",
        api_key: str | None = None,
        transport: JsonTransport | None = None,
    ) -> None:
        from stock_opportunity_agent.data.sources.core import UrllibJsonTransport

        self.base_url = base_url
        self.api_key = api_key
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_config(
        cls,
        config: DataSourceConfig,
        environ: Mapping[str, str] | None = None,
        transport: JsonTransport | None = None,
    ) -> "StooqClient":
        """Create a Stooq client from data-source config.

        Stooq CSV downloads can require an API key. When ``STOOQ_API_KEY`` is
        present, the adapter appends it as the ``apikey`` query parameter.
        """

        env = os.environ if environ is None else environ
        api_key = env.get(config.stooq_api_key_env_var)
        return cls(api_key=api_key, transport=transport)

    def daily_prices(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceBar]:
        """Fetch and normalize daily prices from Stooq's CSV download endpoint."""

        source_symbol = self._source_symbol(symbol)
        params = {"s": source_symbol, "i": "d"}
        if self.api_key:
            params["apikey"] = self.api_key
        if start_date is not None:
            params["d1"] = start_date.strftime("%Y%m%d")
        if end_date is not None:
            params["d2"] = end_date.strftime("%Y%m%d")
        query = parse.urlencode(params)
        get_text = getattr(self.transport, "get_text", None)
        if get_text is None:
            raise DataSourceError("transport does not support text downloads")
        text = get_text(f"{self.base_url}?{query}", {})
        if "Get your apikey" in text or "captcha code" in text:
            raise DataSourceError("Stooq CSV download requires STOOQ_API_KEY")
        rows = parse_csv_rows(text)
        if not rows or rows[0].get("Date") == "No data":
            raise DataSourceError(f"Stooq returned no daily prices for {symbol.upper()}")
        if "Date" not in rows[0]:
            raise DataSourceError(f"Stooq returned non-price CSV for {symbol.upper()}")

        retrieved_at = utc_now()
        bars: list[PriceBar] = []
        for row in rows:
            bars.append(
                PriceBar(
                    symbol=symbol.upper(),
                    as_of_date=date.fromisoformat(row["Date"]),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(float(row["Volume"])),
                    source="stooq",
                    retrieved_at=retrieved_at,
                )
            )
        return sorted(bars, key=lambda bar: bar.as_of_date)

    def _source_symbol(self, symbol: str) -> str:
        if not symbol.strip():
            raise ValidationError("symbol must not be empty")
        normalized = symbol.lower()
        if "." not in normalized:
            normalized = f"{normalized}.us"
        return normalized


@register("stooq")
def source(
    config: DataSourceConfig,
    environ: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> StooqClient:
    """Registered Stooq source factory."""

    return StooqClient.from_config(config, environ=environ, transport=transport)
