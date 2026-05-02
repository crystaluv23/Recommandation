"""FRED macroeconomic data-source provider."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Mapping
from urllib import parse

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import DataSourceError, JsonTransport
from stock_opportunity_agent.models import ValidationError


class FredClient:
    """FRED adapter for macro and economic context series."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.stlouisfed.org/fred",
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValidationError("FRED api_key must not be empty")
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
    ) -> "FredClient":
        """Create a FRED client from the configured API-key env var."""

        env = os.environ if environ is None else environ
        api_key = env.get(config.fred_api_key_env_var)
        if not api_key:
            raise DataSourceError(f"{config.fred_api_key_env_var} is not set")
        return cls(api_key, transport=transport)

    def series_observations(
        self,
        series_id: str,
        *,
        observation_start: date | None = None,
        observation_end: date | None = None,
        realtime_start: date | None = None,
        realtime_end: date | None = None,
    ) -> dict[str, Any]:
        """Fetch raw FRED observations with optional observation and vintage windows."""

        _require_series_id(series_id)
        params = {"series_id": series_id.upper()}
        if observation_start is not None:
            params["observation_start"] = observation_start.isoformat()
        if observation_end is not None:
            params["observation_end"] = observation_end.isoformat()
        if realtime_start is not None:
            params["realtime_start"] = realtime_start.isoformat()
        if realtime_end is not None:
            params["realtime_end"] = realtime_end.isoformat()
        return self._query("series/observations", params)

    def series_metadata(self, series_id: str) -> dict[str, Any]:
        """Fetch raw FRED series metadata."""

        _require_series_id(series_id)
        return self._query("series", {"series_id": series_id.upper()})

    def _query(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        query = parse.urlencode({**params, "api_key": self.api_key, "file_type": "json"})
        data = self.transport.get_json(f"{self.base_url}/{path}?{query}", {})
        if "error_code" in data:
            raise DataSourceError(str(data.get("error_message", data["error_code"])))
        return data


def _require_series_id(series_id: str) -> None:
    if not series_id.strip():
        raise ValidationError("series_id must not be empty")


@register("fred")
def source(
    config: DataSourceConfig,
    environ: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> FredClient:
    """Registered FRED source factory."""

    return FredClient.from_config(config, environ=environ, transport=transport)
