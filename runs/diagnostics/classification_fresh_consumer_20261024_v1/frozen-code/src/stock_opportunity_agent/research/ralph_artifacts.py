"""Load persisted Ralph case and point-in-time document artifacts."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stock_opportunity_agent.cases import CaseOutcomeLabel, HistoricalCase
from stock_opportunity_agent.data.documents import (
    DocumentContentScope,
    DocumentRecord,
)
from stock_opportunity_agent.models import EvidenceKind, ResearchPacket, ValidationError


def load_historical_cases(path: str | Path) -> tuple[HistoricalCase, ...]:
    """Load formal historical cases without changing their packets."""

    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    records = data.get("cases") or data.get("historical_cases")
    if not isinstance(records, list):
        raise ValidationError(f"{source} does not contain cases")
    return tuple(_case_from_record(record) for record in records)


def load_documents_by_symbol(
    path: str | Path,
) -> dict[str, tuple[DocumentRecord, ...]]:
    """Load and deduplicate the persisted point-in-time source archive."""

    source = Path(path)
    if not source.exists():
        return {}
    data = json.loads(source.read_text(encoding="utf-8"))
    records_by_symbol = data.get("documents_by_symbol")
    if not isinstance(records_by_symbol, dict):
        archive_records = data.get("documents")
        if not isinstance(archive_records, list):
            return {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in archive_records:
            if not isinstance(record, dict) or not isinstance(record.get("symbol"), str):
                continue
            grouped.setdefault(record["symbol"].upper(), []).append(record)
        records_by_symbol = grouped
    documents: dict[str, tuple[DocumentRecord, ...]] = {}
    for symbol, records in records_by_symbol.items():
        if not isinstance(records, list):
            continue
        deduped: dict[str, DocumentRecord] = {}
        for record in records:
            if not isinstance(record, dict):
                raise ValidationError("document artifact records must be objects")
            document = _document_from_record(record)
            key = (
                document.source_url
                if document.source_url.startswith("http")
                else document.source_id
            )
            current = deduped.get(key)
            if current is None or len(document.text) > len(current.text):
                deduped[key] = document
        documents[str(symbol).upper()] = tuple(
            sorted(
                deduped.values(),
                key=lambda item: (item.published_date, item.source_id),
            )
        )
    return documents


def _case_from_record(record: Any) -> HistoricalCase:
    if not isinstance(record, dict):
        raise ValidationError("historical case artifact records must be objects")
    return HistoricalCase(
        case_id=_string(record, "case_id"),
        label=CaseOutcomeLabel(_string(record, "label")),
        packet=ResearchPacket.from_dict(_mapping(record, "packet")),
        outcome_start_date=date.fromisoformat(_string(record, "outcome_start_date")),
        outcome_end_date=date.fromisoformat(_string(record, "outcome_end_date")),
        outcome_return=_optional_float(record.get("outcome_return")),
        matched_group_id=_string(record, "matched_group_id"),
        hidden_outcome_summary=_string(record, "hidden_outcome_summary"),
        outcome_definition_id=record.get("outcome_definition_id"),
    )


def _document_from_record(record: dict[str, Any]) -> DocumentRecord:
    available = record.get("available_date")
    return DocumentRecord(
        document_id=_string(record, "document_id"),
        symbol=_string(record, "symbol"),
        kind=EvidenceKind(_string(record, "kind")),
        title=_string(record, "title"),
        text=_string(record, "text"),
        source_id=_string(record, "source_id"),
        source_url=_string(record, "source_url"),
        published_date=date.fromisoformat(_string(record, "published_date")),
        retrieved_at=datetime.fromisoformat(_string(record, "retrieved_at")),
        available_date=(
            date.fromisoformat(str(available))
            if isinstance(available, str)
            else None
        ),
        content_scope=DocumentContentScope(
            str(record.get("content_scope", DocumentContentScope.UNKNOWN.value))
        ),
    )


def _string(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"artifact field {key} must be a non-empty string")
    return value


def _mapping(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    if not isinstance(value, dict):
        raise ValidationError(f"artifact field {key} must be an object")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("optional artifact number must be numeric")
    return float(value)
