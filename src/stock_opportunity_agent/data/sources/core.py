"""Shared data-source types and helpers."""

from __future__ import annotations

import csv
import gzip
import io
import json
import zlib
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

    def get_json(self, url: str, headers: Mapping[str, str]) -> dict[str, Any] | list[Any]:
        """Fetch JSON from a URL."""


class TextTransport(Protocol):
    """Text transport boundary for CSV and document downloads."""

    def get_text(self, url: str, headers: Mapping[str, str]) -> str:
        """Fetch text from a URL."""


class PostJsonTransport(Protocol):
    """JSON POST transport boundary for APIs such as OpenFIGI."""

    def post_json(self, url: str, headers: Mapping[str, str], payload: Any) -> dict[str, Any] | list[Any]:
        """POST a JSON payload and return decoded JSON."""


class UrllibJsonTransport:
    """Standard-library HTTP transport for JSON GET, text GET, and JSON POST."""

    def get_json(self, url: str, headers: Mapping[str, str]) -> dict[str, Any] | list[Any]:
        return json.loads(self.get_text(url, headers))

    def get_text(self, url: str, headers: Mapping[str, str]) -> str:
        req = request.Request(url, headers=dict(headers), method="GET")
        try:
            with request.urlopen(req, timeout=60) as response:
                return decode_response_text(
                    response.read(),
                    response.headers.get("Content-Encoding"),
                )
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DataSourceError(f"data source returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise DataSourceError(f"data source request failed: {exc.reason}") from exc

    def post_json(self, url: str, headers: Mapping[str, str], payload: Any) -> dict[str, Any] | list[Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={**dict(headers), "Content-Type": "application/json"},
            method="POST",
        )
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


@dataclass(frozen=True)
class SecurityListing:
    """Normalized security listing row for universe construction."""

    symbol: str
    name: str
    exchange: str | None
    asset_type: str | None
    status: str
    source: str
    retrieved_at: datetime
    cik: str | None = None
    ipo_date: date | None = None
    delisting_date: date | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValidationError("symbol must not be empty")
        if not self.name.strip():
            raise ValidationError("name must not be empty")
        object.__setattr__(self, "symbol", self.symbol.upper())


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

    if not value or str(value).lower() in {"none", "null", "nan", "-"}:
        return None
    return date.fromisoformat(value)


def parse_csv_rows(text: str) -> list[dict[str, str]]:
    """Parse CSV text into rows with trimmed header names."""

    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, str]] = []
    for row in reader:
        normalized = {}
        for key, value in row.items():
            if key is None:
                continue
            if isinstance(value, list):
                normalized[key.strip()] = ",".join(str(item).strip() for item in value)
            else:
                normalized[key.strip()] = (value or "").strip()
        rows.append(normalized)
    return rows


def decode_response_text(body: bytes, content_encoding: str | None = None) -> str:
    """Decode a provider response body, including common HTTP compression."""

    encoding = (content_encoding or "").lower()
    try:
        if "gzip" in encoding or body.startswith(b"\x1f\x8b"):
            body = gzip.decompress(body)
        elif "deflate" in encoding:
            body = zlib.decompress(body)
        return body.decode("utf-8")
    except (OSError, zlib.error, UnicodeDecodeError) as exc:
        raise DataSourceError("data source response was not valid UTF-8 text") from exc


def utc_now() -> datetime:
    """Current UTC timestamp for source metadata."""

    return datetime.now(timezone.utc)
