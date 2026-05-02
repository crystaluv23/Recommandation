"""Stooq CSV daily-price source."""

from __future__ import annotations

from datetime import date
from urllib import parse

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import DataSourceError, JsonTransport, PriceBar, parse_csv_rows, utc_now
from stock_opportunity_agent.models import ValidationError


class StooqClient:
    """No-key Stooq CSV adapter for historical daily OHLCV bars."""

    def __init__(
        self,
        *,
        base_url: str = "https://stooq.com/q/d/l/",
        transport: JsonTransport | None = None,
    ) -> None:
        from stock_opportunity_agent.data.sources.core import UrllibJsonTransport

        self.base_url = base_url
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_config(cls, config: DataSourceConfig, transport: JsonTransport | None = None) -> "StooqClient":
        """Create a Stooq client from data-source config.

        The current config has no Stooq-specific settings; the argument keeps
        the registry factory signature uniform.
        """

        _ = config
        return cls(transport=transport)

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
        if start_date is not None:
            params["d1"] = start_date.strftime("%Y%m%d")
        if end_date is not None:
            params["d2"] = end_date.strftime("%Y%m%d")
        query = parse.urlencode(params)
        get_text = getattr(self.transport, "get_text", None)
        if get_text is None:
            raise DataSourceError("transport does not support text downloads")
        text = get_text(f"{self.base_url}?{query}", {})
        rows = parse_csv_rows(text)
        if not rows or rows[0].get("Date") == "No data":
            raise DataSourceError(f"Stooq returned no daily prices for {symbol.upper()}")

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
def source(config: DataSourceConfig, transport: JsonTransport | None = None) -> StooqClient:
    """Registered Stooq source factory."""

    return StooqClient.from_config(config, transport=transport)
