"""Raw source cache, request ledger, and quota-aware transport helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib import parse

from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import DataSourceError, JsonTransport
from stock_opportunity_agent.models import ValidationError


SENSITIVE_QUERY_KEYS = frozenset({"apikey", "api_key", "token", "access_key"})
NETWORK_STATUSES = frozenset({"fetched", "error"})


class RequestStatus(str, Enum):
    """Outcome of a source request attempt."""

    FETCHED = "fetched"
    CACHE_HIT = "cache_hit"
    ERROR = "error"
    QUOTA_DEFERRED = "quota_deferred"


@dataclass(frozen=True)
class RawCacheKey:
    """Stable cache key for one raw source request."""

    source_key: str
    capability: DataCapability
    endpoint: str
    params: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_request(
        cls,
        source_key: str,
        capability: DataCapability,
        method: str,
        url: str,
        payload: Any = None,
    ) -> "RawCacheKey":
        """Build a key from an HTTP request while stripping credential query params."""

        parsed = parse.urlsplit(url)
        safe_query = tuple(
            sorted(
                (key, value)
                for key, value in parse.parse_qsl(parsed.query, keep_blank_values=True)
                if key.lower() not in SENSITIVE_QUERY_KEYS
            )
        )
        endpoint = parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        params = (("method", method.upper()), *safe_query)
        if payload is not None:
            params = (*params, ("payload_hash", _stable_hash(payload)))
        return cls(source_key=source_key, capability=capability, endpoint=endpoint, params=params)

    @property
    def digest(self) -> str:
        """Return a short stable digest suitable for a file name."""

        return _stable_hash(
            {
                "source_key": self.source_key,
                "capability": self.capability.value,
                "endpoint": self.endpoint,
                "params": self.params,
            }
        )


@dataclass(frozen=True)
class CachedRawResponse:
    """Cached raw source response with retrieval metadata."""

    key: RawCacheKey
    payload_kind: str
    body: Any
    retrieved_at: datetime


class RawDataCache:
    """File-backed cache for raw JSON and text source responses."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)

    def get_json(self, key: RawCacheKey) -> Any | None:
        """Return a cached JSON body, or ``None`` when absent."""

        cached = self.get(key)
        if cached is None:
            return None
        if cached.payload_kind != "json":
            raise DataSourceError(f"cached payload is not JSON: {key.digest}")
        return cached.body

    def set_json(self, key: RawCacheKey, body: Any, retrieved_at: datetime) -> None:
        """Store a JSON-serializable body."""

        self.set(key, "json", body, retrieved_at)

    def get_text(self, key: RawCacheKey) -> str | None:
        """Return a cached text body, or ``None`` when absent."""

        cached = self.get(key)
        if cached is None:
            return None
        if cached.payload_kind != "text":
            raise DataSourceError(f"cached payload is not text: {key.digest}")
        return str(cached.body)

    def set_text(self, key: RawCacheKey, body: str, retrieved_at: datetime) -> None:
        """Store a text body."""

        self.set(key, "text", body, retrieved_at)

    def get(self, key: RawCacheKey) -> CachedRawResponse | None:
        """Return a cached response, or ``None`` when absent."""

        path = self._path(key)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return CachedRawResponse(
            key=RawCacheKey(
                source_key=data["source_key"],
                capability=DataCapability(data["capability"]),
                endpoint=data["endpoint"],
                params=tuple(tuple(item) for item in data["params"]),
            ),
            payload_kind=data["payload_kind"],
            body=data["body"],
            retrieved_at=datetime.fromisoformat(data["retrieved_at"]),
        )

    def set(self, key: RawCacheKey, payload_kind: str, body: Any, retrieved_at: datetime) -> None:
        """Store a raw response payload."""

        if payload_kind not in {"json", "text"}:
            raise ValidationError("payload_kind must be json or text")
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "source_key": key.source_key,
            "capability": key.capability.value,
            "endpoint": key.endpoint,
            "params": list(key.params),
            "payload_kind": payload_kind,
            "retrieved_at": retrieved_at.isoformat(),
            "body": body,
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True)

    def _path(self, key: RawCacheKey) -> Path:
        return self.root_dir / key.source_key / key.capability.value / f"{key.digest}.json"


@dataclass(frozen=True)
class RequestLedgerEntry:
    """Durable request ledger entry used for audit and quota accounting."""

    source_key: str
    capability: DataCapability
    endpoint: str
    cache_key: str
    status: RequestStatus
    requested_at: datetime
    next_retry_at: datetime | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSONL-compatible dictionary."""

        return {
            "source_key": self.source_key,
            "capability": self.capability.value,
            "endpoint": self.endpoint,
            "cache_key": self.cache_key,
            "status": self.status.value,
            "requested_at": self.requested_at.isoformat(),
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RequestLedgerEntry":
        """Build a ledger entry from a JSONL row."""

        return cls(
            source_key=str(data["source_key"]),
            capability=DataCapability(data["capability"]),
            endpoint=str(data["endpoint"]),
            cache_key=str(data["cache_key"]),
            status=RequestStatus(data["status"]),
            requested_at=datetime.fromisoformat(data["requested_at"]),
            next_retry_at=(
                datetime.fromisoformat(data["next_retry_at"])
                if data.get("next_retry_at")
                else None
            ),
            message=data.get("message"),
        )


class RequestLedger:
    """Append-only JSONL request ledger."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, entry: RequestLedgerEntry) -> None:
        """Append one request event."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")

    def entries(self, *, source_key: str | None = None) -> list[RequestLedgerEntry]:
        """Return ledger entries, optionally filtered by source."""

        if not self.path.exists():
            return []
        entries: list[RequestLedgerEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = RequestLedgerEntry.from_dict(json.loads(line))
                if source_key is None or entry.source_key == source_key:
                    entries.append(entry)
        return entries


@dataclass(frozen=True)
class SourceQuota:
    """Quota rules for one data source."""

    source_key: str
    daily_limit: int | None = None
    per_minute_limit: int | None = None
    per_second_limit: int | None = None

    def __post_init__(self) -> None:
        for name in ("daily_limit", "per_minute_limit", "per_second_limit"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValidationError(f"{name} must be positive when set")


@dataclass(frozen=True)
class BudgetDecision:
    """Whether a source request can proceed right now."""

    allowed: bool
    reason: str | None = None
    next_retry_at: datetime | None = None


class DataQuotaDeferred(DataSourceError):
    """Raised when a source request should be retried after quota reset."""

    def __init__(self, source_key: str, next_retry_at: datetime, reason: str) -> None:
        super().__init__(f"{source_key} quota deferred until {next_retry_at.isoformat()}: {reason}")
        self.source_key = source_key
        self.next_retry_at = next_retry_at
        self.reason = reason


DEFAULT_SOURCE_QUOTAS: dict[str, SourceQuota] = {
    "sec_edgar": SourceQuota("sec_edgar", per_second_limit=10),
    "alpha_vantage": SourceQuota("alpha_vantage", daily_limit=25, per_minute_limit=5),
    "openfigi": SourceQuota("openfigi", per_minute_limit=25),
}


class SourceBudget:
    """Quota checker backed by the request ledger."""

    def __init__(
        self,
        ledger: RequestLedger,
        quotas: Mapping[str, SourceQuota] | None = None,
    ) -> None:
        self.ledger = ledger
        self.quotas = dict(DEFAULT_SOURCE_QUOTAS if quotas is None else quotas)

    def check(self, source_key: str, now: datetime) -> BudgetDecision:
        """Return whether a network request may be attempted now."""

        now = _aware_utc(now)
        quota = self.quotas.get(source_key)
        if quota is None:
            return BudgetDecision(True)

        source_entries = [
            entry
            for entry in self.ledger.entries(source_key=source_key)
            if entry.status.value in NETWORK_STATUSES
        ]
        checks = (
            (quota.per_second_limit, now - timedelta(seconds=1), now + timedelta(seconds=1), "per_second_limit"),
            (quota.per_minute_limit, now - timedelta(minutes=1), now + timedelta(minutes=1), "per_minute_limit"),
            (quota.daily_limit, _day_start(now), _next_day_start(now), "daily_limit"),
        )
        for limit, window_start, reset_at, label in checks:
            if limit is None:
                continue
            count = sum(1 for entry in source_entries if window_start <= _aware_utc(entry.requested_at) <= now)
            if count >= limit:
                return BudgetDecision(
                    allowed=False,
                    reason=f"{label} reached for {source_key}",
                    next_retry_at=reset_at,
                )
        return BudgetDecision(True)

    def require(self, source_key: str, now: datetime) -> None:
        """Raise :class:`DataQuotaDeferred` if the source is currently exhausted."""

        decision = self.check(source_key, now)
        if decision.allowed:
            return
        if decision.next_retry_at is None or decision.reason is None:
            raise DataSourceError(f"quota denied without retry metadata for {source_key}")
        raise DataQuotaDeferred(source_key, decision.next_retry_at, decision.reason)


class ManagedHttpTransport:
    """Cache- and quota-aware transport wrapper for source adapters."""

    def __init__(
        self,
        source_key: str,
        capability: DataCapability,
        inner: JsonTransport,
        cache: RawDataCache,
        ledger: RequestLedger,
        budget: SourceBudget,
        *,
        clock: Callable[[], datetime] | None = None,
        json_error_detector: Callable[[Any], str | None] | None = None,
        text_error_detector: Callable[[str], str | None] | None = None,
    ) -> None:
        self.source_key = source_key
        self.capability = capability
        self.inner = inner
        self.cache = cache
        self.ledger = ledger
        self.budget = budget
        self.clock = clock or _utc_now
        self.json_error_detector = json_error_detector
        self.text_error_detector = text_error_detector

    def get_json(self, url: str, headers: Mapping[str, str]) -> dict[str, Any] | list[Any]:
        """Fetch JSON through cache and quota accounting."""

        key = RawCacheKey.from_request(self.source_key, self.capability, "GET", url)
        cached = self.cache.get_json(key)
        if cached is not None:
            self._record(key, RequestStatus.CACHE_HIT)
            return cached
        self._require_budget_or_record(key)
        try:
            body = self.inner.get_json(url, headers)
        except Exception as exc:
            self._record(key, RequestStatus.ERROR, message=str(exc))
            raise
        now = self.clock()
        message = self.json_error_detector(body) if self.json_error_detector else None
        if message:
            self._record(key, RequestStatus.ERROR, requested_at=now, message=message)
            raise DataSourceError(message)
        self.cache.set_json(key, body, now)
        self._record(key, RequestStatus.FETCHED, requested_at=now)
        return body

    def get_text(self, url: str, headers: Mapping[str, str]) -> str:
        """Fetch text through cache and quota accounting."""

        key = RawCacheKey.from_request(self.source_key, self.capability, "GET", url)
        cached = self.cache.get_text(key)
        if cached is not None:
            self._record(key, RequestStatus.CACHE_HIT)
            return cached
        self._require_budget_or_record(key)
        get_text = getattr(self.inner, "get_text", None)
        if get_text is None:
            self._record(key, RequestStatus.ERROR, message="inner transport does not support text")
            raise DataSourceError("inner transport does not support text")
        try:
            body = get_text(url, headers)
        except Exception as exc:
            self._record(key, RequestStatus.ERROR, message=str(exc))
            raise
        now = self.clock()
        message = self.text_error_detector(body) if self.text_error_detector else None
        if message:
            self._record(key, RequestStatus.ERROR, requested_at=now, message=message)
            raise DataSourceError(message)
        self.cache.set_text(key, body, now)
        self._record(key, RequestStatus.FETCHED, requested_at=now)
        return body

    def post_json(self, url: str, headers: Mapping[str, str], payload: Any) -> dict[str, Any] | list[Any]:
        """POST JSON through cache and quota accounting."""

        key = RawCacheKey.from_request(self.source_key, self.capability, "POST", url, payload=payload)
        cached = self.cache.get_json(key)
        if cached is not None:
            self._record(key, RequestStatus.CACHE_HIT)
            return cached
        self._require_budget_or_record(key)
        post_json = getattr(self.inner, "post_json", None)
        if post_json is None:
            self._record(key, RequestStatus.ERROR, message="inner transport does not support JSON POST")
            raise DataSourceError("inner transport does not support JSON POST")
        try:
            body = post_json(url, headers, payload)
        except Exception as exc:
            self._record(key, RequestStatus.ERROR, message=str(exc))
            raise
        now = self.clock()
        message = self.json_error_detector(body) if self.json_error_detector else None
        if message:
            self._record(key, RequestStatus.ERROR, requested_at=now, message=message)
            raise DataSourceError(message)
        self.cache.set_json(key, body, now)
        self._record(key, RequestStatus.FETCHED, requested_at=now)
        return body

    def _require_budget_or_record(self, key: RawCacheKey) -> None:
        now = self.clock()
        decision = self.budget.check(self.source_key, now)
        if decision.allowed:
            return
        self._record(
            key,
            RequestStatus.QUOTA_DEFERRED,
            requested_at=now,
            next_retry_at=decision.next_retry_at,
            message=decision.reason,
        )
        if decision.next_retry_at is None or decision.reason is None:
            raise DataSourceError(f"quota denied without retry metadata for {self.source_key}")
        raise DataQuotaDeferred(self.source_key, decision.next_retry_at, decision.reason)

    def _record(
        self,
        key: RawCacheKey,
        status: RequestStatus,
        *,
        requested_at: datetime | None = None,
        next_retry_at: datetime | None = None,
        message: str | None = None,
    ) -> None:
        self.ledger.append(
            RequestLedgerEntry(
                source_key=self.source_key,
                capability=self.capability,
                endpoint=key.endpoint,
                cache_key=key.digest,
                status=status,
                requested_at=requested_at or self.clock(),
                next_retry_at=next_retry_at,
                message=message,
            )
        )


def _stable_hash(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _day_start(value: datetime) -> datetime:
    return datetime.combine(_aware_utc(value).date(), time.min, tzinfo=timezone.utc)


def _next_day_start(value: datetime) -> datetime:
    return _day_start(value) + timedelta(days=1)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
