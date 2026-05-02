"""Document archive and as-of retrieval helpers for the data layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from stock_opportunity_agent.models import DataQuality, EvidenceItem, EvidenceKind, ValidationError


@dataclass(frozen=True)
class DocumentRecord:
    """Source-linked text document with public-availability metadata."""

    document_id: str
    symbol: str
    kind: EvidenceKind
    title: str
    text: str
    source_id: str
    source_url: str
    published_date: date
    retrieved_at: datetime
    available_date: date | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(self.title, "title")
        _require_non_empty(self.text, "text")
        _require_non_empty(self.source_id, "source_id")
        _require_non_empty(self.source_url, "source_url")
        if self.kind is EvidenceKind.INFERENCE:
            raise ValidationError("documents cannot use inference evidence kind")
        object.__setattr__(self, "symbol", self.symbol.upper())
        if self.available_date is None:
            object.__setattr__(self, "available_date", self.published_date)
        elif self.available_date < self.published_date:
            raise ValidationError("available_date cannot be before published_date")

    def available_as_of(self, as_of_date: date) -> bool:
        """Return whether the document was publicly available by ``as_of_date``."""

        return self.available_date is not None and self.available_date <= as_of_date

    def to_evidence(self, as_of_date: date) -> EvidenceItem:
        """Convert document metadata into source-linked packet evidence."""

        if not self.available_as_of(as_of_date):
            raise ValidationError("document is not available as of evidence date")
        return EvidenceItem(
            kind=self.kind,
            summary=f"{self.kind.value} document available: {self.title}",
            as_of_date=as_of_date,
            source_id=self.source_id,
            source_url=self.source_url,
            published_date=self.published_date,
            data_quality=DataQuality.CONFIRMED,
        )


@dataclass(frozen=True)
class DocumentChunk:
    """Chunk of a source-linked document for later retrieval and packet assembly."""

    chunk_id: str
    document_id: str
    symbol: str
    kind: EvidenceKind
    index: int
    text: str
    source_id: str
    source_url: str
    published_date: date
    available_date: date
    retrieved_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(self.text, "text")
        _require_non_empty(self.source_id, "source_id")
        _require_non_empty(self.source_url, "source_url")
        if self.index < 0:
            raise ValidationError("chunk index cannot be negative")
        object.__setattr__(self, "symbol", self.symbol.upper())

    def available_as_of(self, as_of_date: date) -> bool:
        """Return whether this chunk may be used in a point-in-time packet."""

        return self.available_date <= as_of_date

    def to_evidence(self, as_of_date: date) -> EvidenceItem:
        """Convert chunk metadata into source-linked evidence."""

        if not self.available_as_of(as_of_date):
            raise ValidationError("document chunk is not available as of evidence date")
        return EvidenceItem(
            kind=self.kind,
            summary=f"{self.kind.value} excerpt available from {self.document_id} chunk {self.index}",
            as_of_date=as_of_date,
            source_id=f"{self.source_id}:chunk:{self.index}",
            source_url=self.source_url,
            published_date=self.published_date,
            data_quality=DataQuality.CONFIRMED,
        )


class DocumentStore:
    """Simple in-memory document store with deterministic as-of retrieval."""

    def __init__(self, documents: Iterable[DocumentRecord] | None = None) -> None:
        self._documents: list[DocumentRecord] = []
        for document in documents or ():
            self.add(document)

    def add(self, document: DocumentRecord) -> None:
        """Add a document, replacing any existing record with the same id."""

        self._documents = [existing for existing in self._documents if existing.document_id != document.document_id]
        self._documents.append(document)

    def documents_as_of(
        self,
        symbol: str,
        as_of_date: date,
        *,
        kinds: Iterable[EvidenceKind] | None = None,
    ) -> list[DocumentRecord]:
        """Return source documents for a symbol that were available by ``as_of_date``."""

        return documents_as_of(self._documents, symbol, as_of_date, kinds=kinds)

    def chunks_as_of(
        self,
        symbol: str,
        as_of_date: date,
        *,
        kinds: Iterable[EvidenceKind] | None = None,
        max_chars: int = 1200,
        overlap_chars: int = 120,
    ) -> list[DocumentChunk]:
        """Return chunks from documents available by ``as_of_date``."""

        chunks: list[DocumentChunk] = []
        for document in self.documents_as_of(symbol, as_of_date, kinds=kinds):
            chunks.extend(chunk_document_text(document, max_chars=max_chars, overlap_chars=overlap_chars))
        return chunks


def documents_as_of(
    documents: Iterable[DocumentRecord],
    symbol: str,
    as_of_date: date,
    *,
    kinds: Iterable[EvidenceKind] | None = None,
) -> list[DocumentRecord]:
    """Filter documents by ticker, public availability, and optional evidence kind."""

    symbol_upper = symbol.upper()
    kind_set = set(kinds) if kinds is not None else None
    selected = [
        document
        for document in documents
        if document.symbol == symbol_upper
        and document.available_as_of(as_of_date)
        and (kind_set is None or document.kind in kind_set)
    ]
    return sorted(selected, key=lambda document: (document.available_date or date.min, document.document_id))


def chunk_document_text(
    document: DocumentRecord,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 120,
) -> list[DocumentChunk]:
    """Split a document into overlapping chunks while preserving source metadata."""

    if max_chars < 1:
        raise ValidationError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValidationError("overlap_chars must be non-negative and less than max_chars")

    chunks: list[DocumentChunk] = []
    start = 0
    text = document.text
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document.document_id}:chunk:{len(chunks)}",
                    document_id=document.document_id,
                    symbol=document.symbol,
                    kind=document.kind,
                    index=len(chunks),
                    text=chunk_text,
                    source_id=document.source_id,
                    source_url=document.source_url,
                    published_date=document.published_date,
                    available_date=document.available_date or document.published_date,
                    retrieved_at=document.retrieved_at,
                )
            )
        if end == len(text):
            break
        start = end - overlap_chars
    return chunks


def documents_to_evidence(documents: Iterable[DocumentRecord], as_of_date: date) -> list[EvidenceItem]:
    """Convert available documents into packet evidence."""

    return [document.to_evidence(as_of_date) for document in documents if document.available_as_of(as_of_date)]


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValidationError(f"{name} must not be empty")
