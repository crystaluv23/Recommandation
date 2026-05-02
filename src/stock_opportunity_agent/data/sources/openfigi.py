"""OpenFIGI identifier-mapping data-source provider."""

from __future__ import annotations

import os
from typing import Any, Mapping

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import DataSourceError, JsonTransport
from stock_opportunity_agent.models import ValidationError


class OpenFigiClient:
    """OpenFIGI adapter for ticker, exchange, and FIGI mapping."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.openfigi.com/v3",
        transport: JsonTransport | None = None,
    ) -> None:
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
    ) -> "OpenFigiClient":
        """Create an OpenFIGI client, using a key only when the env var is set."""

        env = os.environ if environ is None else environ
        return cls(env.get(config.openfigi_api_key_env_var), transport=transport)

    def map_tickers(
        self,
        symbols: list[str],
        *,
        exchange_code: str = "US",
        security_type: str | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Map ticker symbols to FIGI records through OpenFIGI mapping jobs."""

        if not symbols:
            raise ValidationError("symbols must not be empty")
        jobs: list[dict[str, str]] = []
        for symbol in symbols:
            if not symbol.strip():
                raise ValidationError("symbols must not contain empty values")
            job = {"idType": "TICKER", "idValue": symbol.upper(), "exchCode": exchange_code}
            if security_type:
                job["securityType"] = security_type
            jobs.append(job)
        return self.map_jobs(jobs)

    def map_jobs(self, jobs: list[dict[str, str]]) -> dict[str, Any] | list[Any]:
        """Submit raw OpenFIGI mapping jobs."""

        if not jobs:
            raise ValidationError("jobs must not be empty")
        post_json = getattr(self.transport, "post_json", None)
        if post_json is None:
            raise DataSourceError("transport does not support JSON POST")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-OPENFIGI-APIKEY"] = self.api_key
        data = post_json(f"{self.base_url}/mapping", headers, jobs)
        if isinstance(data, dict) and "error" in data:
            raise DataSourceError(str(data["error"]))
        return data


@register("openfigi")
def source(
    config: DataSourceConfig,
    environ: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> OpenFigiClient:
    """Registered OpenFIGI source factory."""

    return OpenFigiClient.from_config(config, environ=environ, transport=transport)
