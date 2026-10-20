"""Append-only point-in-time source store for adaptive signal execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

import fcntl

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
_ORACLE_METADATA_NAME = "oracle.json"
_ORACLE_SCHEMA = "raw-info-oracle-v1"
_APPEND_LOCK_NAME = ".raw-info-append.lock"
_CAPTURE_PREFIX = "rawcap:v1:"
_CAPTURE_FIELDS = {"document_id", "company_id", "source_type", "published_at",
                   "available_at", "content", "content_hash", "metadata"}


def _strict_capture_json(value: Any) -> str:
    """Encode JSON without collapsing typed metadata or permitting NaN."""
    def check(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValidationError("capture JSON object keys must be strings")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ValidationError("capture metadata must use JSON types")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
        check(value)
        return encoded
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValidationError("capture record must be finite, strict JSON") from exc


def capture_document_id(record: Mapping[str, Any]) -> str:
    """Derive a capture ID from the complete typed record except its ID."""
    if set(record) != _CAPTURE_FIELDS:
        raise ValidationError("capture identity requires the complete Raw Info record")
    payload = {key: value for key, value in record.items() if key != "document_id"}
    return _CAPTURE_PREFIX + hashlib.sha256(_strict_capture_json(payload).encode("utf-8")).hexdigest()



@dataclass(frozen=True)
class RawInfoOracle:
    """Stable identity for one global append-only Raw Info oracle."""

    oracle_id: str
    created_at: str
    schema_version: str = _ORACLE_SCHEMA

    def __post_init__(self) -> None:
        _validate_component(self.oracle_id, "oracle_id")
        if self.schema_version != _ORACLE_SCHEMA:
            raise ValidationError("unsupported Raw Info oracle schema")
        _require_aware(_parse_datetime(self.created_at), "created_at")

    def to_dict(self) -> dict[str, str]:
        """Return the immutable, secret-free oracle identity."""

        return {
            "schema_version": self.schema_version,
            "oracle_id": self.oracle_id,
            "created_at": self.created_at,
        }

    @classmethod
    def load_or_create(cls, root: str | Path) -> "RawInfoOracle":
        """Load the oracle identity, creating it only for a new empty root."""

        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        metadata_path = root_path / _ORACLE_METADATA_NAME
        if metadata_path.is_file():
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            return cls(
                oracle_id=str(data["oracle_id"]),
                created_at=str(data["created_at"]),
                schema_version=str(data.get("schema_version", "")),
            )
        if any(root_path.iterdir()):
            raise ValidationError(
                "existing Raw Info root has no oracle identity; migrate it explicitly"
            )
        oracle = cls(
            oracle_id=f"raw-info-{uuid.uuid4().hex}",
            created_at=datetime.now().astimezone().isoformat(),
        )
        descriptor, temporary = tempfile.mkstemp(
            prefix=".oracle.", dir=root_path
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(oracle.to_dict(), handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, metadata_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return oracle


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
        self._validate_capture_identity()

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

    def as_capture(self) -> "RawInfoDocument":
        """Version this exact recorded capture without altering its facts or clocks."""
        record = json.loads(_strict_capture_json(self.to_dict()))
        record["document_id"] = capture_document_id(record)
        return type(self).from_dict(record)

    def _validate_capture_identity(self) -> None:
        if self.document_id.startswith("rawcap:") and self.document_id != capture_document_id(self.to_dict()):
            raise ValidationError("raw info capture identity differs from complete record")

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

        if str(data["document_id"]).startswith("rawcap:") and data["document_id"] != capture_document_id(data):
            raise ValidationError("serialized capture identity differs from complete record")
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
        self._validated_files: dict[Path, tuple[int, ...]] = {}
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
            self.refresh()
        for document in documents:
            self.append(document)

    def append(self, document: RawInfoDocument) -> bool:
        """Append one document, returning false for an identical replay.

        A reused id with any different field fails; the public API intentionally
        provides no update or delete operation.
        """

        document._validate_capture_identity()
        if self.root is None:
            return self._append_in_memory(document)

        with self._append_lock():
            self.refresh()
            existing = self._documents.get(document.document_id)
            if existing is not None:
                return self._resolve_replay(
                    existing, document, idempotent_refetch=True
                )

            path = self._path_for(document)
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{path.name}.", dir=path.parent
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(document.to_dict(), handle, sort_keys=True, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    persisted = RawInfoDocument.from_dict(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                    replay = self._resolve_replay(
                        persisted, document, idempotent_refetch=True
                    )
                    self._documents[document.document_id] = persisted
                    return replay
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
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
        document._validate_capture_identity()
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

    def snapshot(self) -> "RawInfoStore":
        """Return an isolated in-memory view of the documents seen so far."""

        return RawInfoStore(documents=self.documents)

    def refresh(self) -> int:
        """Load newly committed file-backed documents into this snapshot.

        Returns the number of newly visible documents. Existing in-memory stores
        have no backing state and therefore return zero.
        """

        if self.root is None:
            return 0
        added = 0
        for path in sorted(self.root.rglob("*.json")):
            if path == self.root / _ORACLE_METADATA_NAME:
                continue
            before = self._file_revision(path)
            if self._validated_files.get(path) == before:
                continue
            document = RawInfoDocument.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if self._file_revision(path) != before:
                raise ValidationError("raw info file changed during refresh")
            if path != self._path_for(document):
                raise ValidationError(
                    f"raw info document is stored outside its canonical path: {path}"
                )
            existing = self._documents.get(document.document_id)
            if existing is not None:
                self._resolve_replay(existing, document)
                self._validated_files[path] = before
                continue
            self._documents[document.document_id] = document
            self._validated_files[path] = before
            added += 1
        return added

    @staticmethod
    def _file_revision(path: Path) -> tuple[int, ...]:
        """Identify unchanged local immutable files, including same-size rewrites."""

        stat = path.stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    @property
    def inventory_hash(self) -> str:
        """Hash document identities without treating oracle growth as run state."""

        payload = [
            {
                "document_id": item.document_id,
                "content_hash": item.content_hash,
                "available_at": item.available_at.isoformat(),
            }
            for item in self.documents
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()

    def _append_in_memory(self, document: RawInfoDocument) -> bool:
        existing = self._documents.get(document.document_id)
        if existing is not None:
            return self._resolve_replay(
                existing, document, idempotent_refetch=True
            )
        self._documents[document.document_id] = document
        return True

    @staticmethod
    def _resolve_replay(
        existing: RawInfoDocument,
        incoming: RawInfoDocument,
        *,
        idempotent_refetch: bool = False,
    ) -> bool:
        if incoming.document_id.startswith("rawcap:") or existing.document_id.startswith("rawcap:"):
            existing._validate_capture_identity()
            incoming._validate_capture_identity()
            if _strict_capture_json(existing.to_dict()) == _strict_capture_json(incoming.to_dict()):
                return False
            raise ValidationError("raw info capture replay differs from complete record")
        if existing == incoming:
            return False
        if (
            idempotent_refetch
            and existing.document_id == incoming.document_id
            and existing.company_id == incoming.company_id
            and existing.content == incoming.content
        ):
            # An appended refetch whose id-embedded content digest matches
            # replays idempotently even though retrieval provenance
            # (timestamps, metadata) moved: the stored copy stays canonical
            # and nothing in the append-only record is rewritten. Refresh
            # keeps full strictness so on-disk tampering still fails closed.
            return False
        raise ValidationError(
            "raw info document_id already exists with different content or "
            f"provenance: {incoming.document_id}"
        )

    @contextmanager
    def _append_lock(self) -> Iterator[None]:
        assert self.root is not None
        lock_path = self.root / _APPEND_LOCK_NAME
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

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
