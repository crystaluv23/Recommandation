"""Shared data-source types and helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Protocol
from urllib import request
from urllib.error import HTTPError, URLError

from stock_opportunity_agent.models import DataQuality, EvidenceItem, EvidenceKind, ValidationError


class DataSourceError(RuntimeError):
    """Raised when an upstream data source fails or returns unusable data."""


class JsonTransport(Protocol):
    """Transport boundary for offline tests and caching wrappers."""

    def get_json(self, url: str, headers: Mapping[str, str]) -> dict[str, Any]:
        """Fetch JSON from a URL."""


class UrllibJsonTransport:
    """Standard-library JSON GET transport."""

    def get_json(self, url: str, headers: Mapping[str, str]) -> dict[str, Any]:
        req = request.Request(url, headers=dict(headers), method="GET")
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DataSourceError(f"data source returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise DataSourceError(f"data source request failed: {exc.reason}") from exc


@dataclass(frozen=True)
class PriceBar:
    """Normalized daily OHLCV bar with explicit source metadata."""

    symbol: str
    as_of_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str
    retrieved_at: datetime
    adjusted_close: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValidationError("symbol must not be empty")
        if min(self.open, self.high, self.low, self.close) < 0:
            raise ValidationError("price fields cannot be negative")
        if self.volume < 0:
            raise ValidationError("volume cannot be negative")


@dataclass(frozen=True)
class FilingMetadata:
    """Normalized SEC filing metadata."""

    cik: str
    accession_number: str
    filing_date: date
    report_date: date | None
    form: str
    primary_document: str
    source_url: str
    retrieved_at: datetime


def filing_to_evidence(filing: FilingMetadata, as_of_date: date) -> EvidenceItem:
    """Convert SEC filing metadata to source-linked evidence."""

    return EvidenceItem(
        kind=EvidenceKind.FILING,
        summary=f"{filing.form} filed on {filing.filing_date.isoformat()}",
        as_of_date=as_of_date,
        source_id=f"sec:{filing.cik}:{filing.accession_number}",
        source_url=filing.source_url,
        published_date=filing.filing_date,
        data_quality=DataQuality.CONFIRMED,
    )


def format_cik(cik: str) -> str:
    """Return a 10-digit SEC CIK string."""

    digits = "".join(char for char in cik if char.isdigit())
    if not digits:
        raise ValidationError("cik must contain digits")
    return digits.zfill(10)


def array_get(data: Mapping[str, Any], key: str, index: int) -> Any:
    """Return an indexed array value or ``None`` when absent."""

    value = data.get(key)
    if not isinstance(value, list) or index >= len(value):
        return None
    return value[index]


def optional_date(value: Any) -> date | None:
    """Parse an optional ISO date."""

    if not value:
        return None
    return date.fromisoformat(value)


def utc_now() -> datetime:
    """Current UTC timestamp for source metadata."""

    return datetime.now(timezone.utc)
