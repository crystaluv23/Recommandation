"""Massive.com REST data-source provider."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Mapping
from urllib import parse

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import DataSourceError, JsonTransport, PriceBar, utc_now
from stock_opportunity_agent.models import ValidationError


class MassiveClient:
    """Massive API adapter for U.S. equity aggregate bars."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.massive.com",
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValidationError("Massive api_key must not be empty")
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
    ) -> "MassiveClient":
        """Create a Massive client from the configured API-key env var."""

        env = os.environ if environ is None else environ
        api_key = env.get(config.massive_api_key_env_var)
        if not api_key:
            raise DataSourceError(f"{config.massive_api_key_env_var} is not set")
        return cls(api_key, transport=transport)

    def daily_prices(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        adjusted: bool = True,
    ) -> list[PriceBar]:
        """Fetch and normalize daily OHLCV aggregate bars for an explicit date window."""

        if start_date is None or end_date is None:
            raise ValidationError("Massive daily_prices requires start_date and end_date")
        if end_date < start_date:
            raise ValidationError("end_date cannot be before start_date")

        ticker = _ticker(symbol)
        path = (
            f"/v2/aggs/ticker/{parse.quote(ticker, safe='')}/range/1/day/"
            f"{start_date.isoformat()}/{end_date.isoformat()}"
        )
        query = parse.urlencode(
            {
                "adjusted": str(adjusted).lower(),
                "sort": "asc",
                "limit": "50000",
                "apiKey": self.api_key,
            }
        )
        data = self.transport.get_json(f"{self.base_url}{path}?{query}", {})
        if not isinstance(data, Mapping):
            raise DataSourceError("Massive aggregate response is not an object")
        if "error" in data:
            raise DataSourceError(str(data["error"]))
        if str(data.get("status", "")).upper() == "ERROR":
            raise DataSourceError(str(data.get("message", "Massive aggregate request failed")))

        results = data.get("results")
        if not isinstance(results, list) or not results:
            raise DataSourceError(f"Massive returned no daily prices for {ticker}")

        retrieved_at = utc_now()
        bars: list[PriceBar] = []
        for row in results:
            if not isinstance(row, Mapping):
                raise DataSourceError("Massive aggregate row is not an object")
            bars.append(_price_bar_from_result(ticker, row, retrieved_at, adjusted=adjusted))
        return sorted(bars, key=lambda bar: bar.as_of_date)


def _ticker(symbol: str) -> str:
    if not symbol.strip():
        raise ValidationError("symbol must not be empty")
    return symbol.upper()


def _price_bar_from_result(
    symbol: str,
    row: Mapping[str, Any],
    retrieved_at: datetime,
    *,
    adjusted: bool,
) -> PriceBar:
    try:
        close = float(row["c"])
        return PriceBar(
            symbol=symbol,
            as_of_date=datetime.fromtimestamp(int(row["t"]) / 1000, timezone.utc).date(),
            open=float(row["o"]),
            high=float(row["h"]),
            low=float(row["l"]),
            close=close,
            volume=int(float(row["v"])),
            source="massive",
            retrieved_at=retrieved_at,
            adjusted_close=close if adjusted else None,
        )
    except KeyError as exc:
        raise DataSourceError(f"Massive aggregate row missing field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise DataSourceError("Massive aggregate row contains invalid price data") from exc


@register("massive")
def source(
    config: DataSourceConfig,
    environ: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> MassiveClient:
    """Registered Massive source factory."""

    return MassiveClient.from_config(config, environ=environ, transport=transport)
