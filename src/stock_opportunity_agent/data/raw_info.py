"""Append-only point-in-time source store for adaptive signal execution."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.models import ValidationError


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_FORBIDDEN_OUTCOME_FIELDS = frozenset(
    {
        "ground_truth",
        "outcome",
        "outcome_label",
        "label",
        "is_surge",
        "magnitude_class",
        "realized_return",
        "realized_max_multiple",
        "future_price",
        "future_return",
        "post_outcome",
    }
)


@dataclass(frozen=True)
class RawInfoDocument:
    """One immutable source document with public-availability provenance."""

    document_id: str
    company_id: str
    source_type: str
    published_at: datetime
    available_at: datetime
    content: str
    content_hash: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("document_id", "company_id", "source_type"):
            _validate_component(str(getattr(self, name)), name)
        if self.source_type.casefold() in _FORBIDDEN_OUTCOME_FIELDS:
            raise ValidationError("raw info source_type cannot contain outcome data")
        if not self.content.strip():
            raise ValidationError("raw info content must not be empty")
        _require_aware(self.published_at, "published_at")
        _require_aware(self.available_at, "available_at")
        if self.available_at < self.published_at:
            raise ValidationError("available_at cannot be before published_at")
        expected = content_sha256(self.content)
        if self.content_hash != expected:
            raise ValidationError("raw info content_hash does not match content")
        _reject_outcome_metadata(self.metadata)
        try:
            json.dumps(dict(self.metadata), sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValidationError("raw info metadata must be JSON-serializable") from exc
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def create(
        cls,
        *,
        document_id: str,
        company_id: str,
        source_type: str,
        published_at: datetime,
        available_at: datetime,
        content: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> "RawInfoDocument":
        """Create a document and derive its canonical content hash."""

        return cls(
            document_id=document_id,
            company_id=company_id,
            source_type=source_type,
            published_at=published_at,
            available_at=available_at,
            content=content,
            content_hash=content_sha256(content),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "document_id": self.document_id,
            "company_id": self.company_id,
            "source_type": self.source_type,
            "published_at": self.published_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "content": self.content,
            "content_hash": self.content_hash,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawInfoDocument":
        """Restore a document from :meth:`to_dict` output."""

        return cls(
            document_id=str(data["document_id"]),
            company_id=str(data["company_id"]),
            source_type=str(data["source_type"]),
            published_at=_parse_datetime(data["published_at"]),
            available_at=_parse_datetime(data["available_at"]),
            content=str(data["content"]),
            content_hash=str(data["content_hash"]),
            metadata=dict(data.get("metadata", {})),
        )


class RawInfoStore:
    """Append-only in-memory or file-backed Raw Info Store.

    Example:
        ``store.search("issuer-1", as_of=prediction_time)`` returns only
        documents that were publicly available by the prediction time.
    """

    def __init__(
        self,
        root: str | Path | None = None,
        documents: Iterable[RawInfoDocument] = (),
    ) -> None:
        self.root = Path(root) if root is not None else None
        self._documents: dict[str, RawInfoDocument] = {}
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load_existing()
        for document in documents:
            self.append(document)

    def append(self, document: RawInfoDocument) -> bool:
        """Append one document, returning false for an identical replay.

        A reused id with any different field fails; the public API intentionally
        provides no update or delete operation.
        """

        existing = self._documents.get(document.document_id)
        if existing is not None:
            if existing == document:
                return False
            raise ValidationError(
                f"raw info document_id already exists with different content: "
                f"{document.document_id}"
            )

        if self.root is not None:
            path = self._path_for(document)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("x", encoding="utf-8") as handle:
                    json.dump(document.to_dict(), handle, sort_keys=True, indent=2)
                    handle.write("\n")
            except FileExistsError as exc:
                raise ValidationError(
                    f"raw info path already exists for {document.document_id}"
                ) from exc
        self._documents[document.document_id] = document
        return True

    def load(
        self,
        document_id: str,
        *,
        as_of: datetime | None = None,
    ) -> RawInfoDocument:
        """Load an exact document and optionally enforce an availability time."""

        try:
            document = self._documents[document_id]
        except KeyError as exc:
            raise ValidationError(f"unknown raw info document: {document_id}") from exc
        if as_of is not None:
            _require_aware(as_of, "as_of")
            if document.available_at > as_of:
                raise ValidationError(
                    "raw info document is not available as of prediction time"
                )
        return document

    def search(
        self,
        company_id: str,
        *,
        as_of: datetime,
        source_types: Iterable[str] | None = None,
        query: str | None = None,
    ) -> list[RawInfoDocument]:
        """Return deterministic point-in-time results for one company."""

        _require_aware(as_of, "as_of")
        allowed_types = set(source_types) if source_types is not None else None
        query_lower = query.casefold() if query else None
        selected = [
            document
            for document in self._documents.values()
            if document.company_id == company_id
            and document.available_at <= as_of
            and (allowed_types is None or document.source_type in allowed_types)
            and (query_lower is None or query_lower in document.content.casefold())
        ]
        return sorted(
            selected,
            key=lambda document: (
                document.available_at,
                document.published_at,
                document.document_id,
            ),
        )

    @property
    def documents(self) -> tuple[RawInfoDocument, ...]:
        """Return all immutable documents in deterministic id order."""

        return tuple(self._documents[key] for key in sorted(self._documents))

    def _load_existing(self) -> None:
        assert self.root is not None
        for path in sorted(self.root.rglob("*.json")):
            document = RawInfoDocument.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
            existing = self._documents.get(document.document_id)
            if existing is not None and existing != document:
                raise ValidationError(
                    f"conflicting persisted raw info id: {document.document_id}"
                )
            self._documents[document.document_id] = document

    def _path_for(self, document: RawInfoDocument) -> Path:
        assert self.root is not None
        return (
            self.root
            / document.source_type
            / document.company_id
            / f"{document.document_id}.json"
        )


def content_sha256(content: str) -> str:
    """Return the canonical UTF-8 SHA-256 for source content."""

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _validate_component(value: str, name: str) -> None:
    if not _SAFE_COMPONENT.fullmatch(value):
        raise ValidationError(
            f"{name} must contain only safe identifier characters"
        )


def _reject_outcome_metadata(value: Any, *, path: str = "metadata") -> None:
    """Reject hidden label/post-outcome fields while leaving source prose alone."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in _FORBIDDEN_OUTCOME_FIELDS or any(
                normalized.startswith(f"{field}_")
                or normalized.endswith(f"_{field}")
                for field in _FORBIDDEN_OUTCOME_FIELDS
            ):
                raise ValidationError(
                    f"raw info metadata contains forbidden outcome field: {path}.{key}"
                )
            _reject_outcome_metadata(nested, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_outcome_metadata(nested, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
        if normalized in _FORBIDDEN_OUTCOME_FIELDS:
            raise ValidationError(
                f"raw info metadata contains forbidden outcome marker: {path}"
            )


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"raw info {name} must be timezone-aware")
