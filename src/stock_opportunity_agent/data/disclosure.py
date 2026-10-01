"""Three-layer disclosure interface over the point-in-time Raw Info store.

Layer 1 (catalog): bounded cards of deterministic document metadata —
news titles, filing form types, section indexes, dates, readable sizes —
with totals, omitted counts, and cursor pagination.
Layer 2 (fetch): one bounded working view of summary plus a
content-addressed reference; the summary degenerates to verbatim readable
text when the unit fits the budget.
Layer 3 (provenance): a content-addressed reference resolves to the exact
original raw span, never a filesystem path.

Every layer is a pure function of immutable documents and the supplied
point-in-time cutoff; nothing here acquires, mutates, or calls a model.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.markup import visible_html_ranges
from stock_opportunity_agent.data.resolution import (
    _MARKUP_SOURCE_TYPES,
    _HTML_TAG,
    _normalized_visible_text,
)
from stock_opportunity_agent.models import ValidationError


MAX_CATALOG_CARDS = 20
_CATALOG_PREVIEW_CHARS = 140
_FETCH_DEFAULT_BUDGET_CHARS = 4_000
_FETCH_WINDOW_CHARS = 2_000
_FETCH_OMITTED_MARKERS = 6

# SEC filings encode the mandatory spaces in "FORM 8-K" / "ITEM 1A" as
# non-breaking-space entities; heading and form matching tolerates them
# (offsets stay on the raw readable string, entities are decoded for
# display only).
_ENTITY_GAP = r"(?:\s|&#1?60;|&nbsp;|&#x0*a0;)+"
_FORM_TYPE_PATTERN = re.compile(
    r"\bFORM" + _ENTITY_GAP +
    r"(10-K|10-Q|8-K|20-F|40-F|6-K|S-1|S-3|SC" + _ENTITY_GAP +
    r"13D|SC" + _ENTITY_GAP + r"13G|424B[1-9]|DEF" + _ENTITY_GAP + r"14A)\b",
    re.IGNORECASE,
)
_SECTION_HEADING_PATTERN = re.compile(
    r"(?:^|\s)((?:PART" + _ENTITY_GAP + r"I{1,3}|ITEM" + _ENTITY_GAP +
    r"\d+[A-Z]?(?:\.\d+)?)\b[^\n]{0,80})",
    re.IGNORECASE,
)
_NEWS_TITLE_KEYS = ("title", "headline")


def raw_span_view(
    document: RawInfoDocument, offset: int, length: int,
    *, visible_ranges: tuple[tuple[int, int], ...] | None = None,
) -> dict[str, Any]:
    """Disclose readable content from an exact raw window without relocating it.

    Optional immutable visibility intervals let repeated reads reuse one index.
    ``raw_span_view(doc, 0, 4000)`` reports a hidden header as unreadable and
    supplies the next body coordinate, rather than silently reading that body.
    """

    if offset < 0 or length < 1:
        raise ValidationError("raw span offset/length is invalid")
    raw = document.content
    ranges = visible_ranges
    if ranges is None:
        ranges = (visible_html_ranges(raw) if document.source_type.casefold() in _MARKUP_SOURCE_TYPES
                  else ((0, len(raw)),))
    end = min(len(raw), offset + length)
    parts = [raw[max(offset, start):min(end, stop)]
             for start, stop in ranges if start < end and stop > offset]
    readable = " ".join(" ".join(parts).split())
    next_start = None
    for start, stop in ranges:
        candidate = max(end, start)
        while candidate < stop and raw[candidate].isspace():
            candidate += 1
        if candidate < stop:
            next_start = candidate
            break
    return {"readable_text": readable, "has_readable_text": bool(readable),
            "readable_chars": len(readable), "raw_window_chars": max(0, end - offset),
            "next_readable_start": next_start}


def _decode_entities(text: str) -> str:
    """Decode the non-breaking-space entities used by SEC headings."""

    return (
        text.replace("&#160;", " ")
        .replace("&#xA0;", " ")
        .replace("&#xa0;", " ")
        .replace("&nbsp;", " ")
    )


def _readable_text(document: RawInfoDocument) -> tuple[str, list[tuple[int, int]]]:
    """Return normalized readable text plus per-character raw offsets."""

    if (
        document.source_type.casefold() in _MARKUP_SOURCE_TYPES
        and _HTML_TAG.search(document.content)
    ):
        visible, origins = _normalized_visible_text(document.content)
        return "".join(visible), origins
    return document.content, [
        (index, index + 1) for index in range(len(document.content))
    ]


def _news_title(document: RawInfoDocument) -> str | None:
    """Extract a provider news title deterministically, if present."""

    stripped = document.content.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(document.content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    for key in _NEWS_TITLE_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:_CATALOG_PREVIEW_CHARS]
    return None


def _filing_sections(
    readable: str, origins: list[tuple[int, int]]
) -> list[dict[str, Any]]:
    """Index SEC Part/Item headings with exact raw-offset boundaries."""

    sections: list[dict[str, Any]] = []
    for match in _SECTION_HEADING_PATTERN.finditer(readable):
        heading = " ".join(_decode_entities(match.group(1)).split())
        start_origin = origins[match.start(1)][0]
        end_origin = origins[match.end(1) - 1][1]
        if sections and sections[-1]["raw_start"] == start_origin:
            continue
        sections.append(
            {
                "section_id": f"sec{len(sections):02d}",
                "heading": heading[:120],
                "raw_start": start_origin,
                "raw_end": end_origin,
            }
        )
    return sections


def document_card(
    document: RawInfoDocument,
    *,
    include_sections: bool,
) -> dict[str, Any]:
    """Index one already PIT-selected document without changing evidence authority."""

    readable, origins = _readable_text(document)
    card: dict[str, Any] = {
        "document_id": document.document_id,
        "content_hash": document.content_hash,
        "source_type": document.source_type,
        "available_at": document.available_at.isoformat(),
        "visible_chars": len(readable),
        "raw_chars": len(document.content),
        "readable_start": origins[0][0] if origins else None,
    }
    title = _news_title(document)
    form_match = _FORM_TYPE_PATTERN.search(readable[:20_000])
    if title is not None:
        card["title"] = title
    metadata = getattr(document, "metadata", None)
    metadata_form = (
        metadata.get("form") if isinstance(metadata, Mapping) else None
    )
    if isinstance(metadata_form, str) and metadata_form.strip():
        # Authoritative acquisition metadata beats text detection.
        card["form_type"] = metadata_form.strip().upper()
    elif form_match is not None:
        card["form_type"] = (
            _decode_entities(form_match.group(1)).upper().replace(" ", "")
        )
    card["preview"] = readable[:_CATALOG_PREVIEW_CHARS].strip()
    if include_sections and document.source_type.casefold() in _MARKUP_SOURCE_TYPES:
        sections = _filing_sections(readable, origins)
        if sections:
            card["sections"] = sections[:24]
            card["section_count"] = len(sections)
    return card


def document_catalog(
    store: RawInfoStore,
    *,
    company_id: str,
    as_of: Any,
    source_types: Iterable[str] | None = None,
    title_query: str | None = None,
    cursor: int = 0,
    max_cards: int = MAX_CATALOG_CARDS,
) -> dict[str, Any]:
    """Return one bounded page of point-in-time document cards.

    The envelope discloses the total eligible count and the omitted tail so
    a consumer can see that more content exists without fetching it.
    """

    from datetime import datetime as _datetime

    if not isinstance(as_of, _datetime):
        raise ValidationError("document catalog requires a timezone-aware as_of")
    wanted = {str(item) for item in source_types} if source_types is not None else None
    eligible = [
        document
        for document in store.search(company_id, as_of=as_of)
        if wanted is None or document.source_type in wanted
    ]
    if title_query:
        tokens = [
            token.casefold()
            for token in re.findall(r"[A-Za-z0-9]+", title_query)
            if len(token) > 2
        ]
        if tokens:
            eligible = [
                document
                for document in eligible
                if _matches_title_query(document, tokens)
            ]
    total = len(eligible)
    if type(cursor) is not int or not 0 <= cursor <= total:
        raise ValidationError("document catalog cursor is invalid")
    page = eligible[cursor : cursor + max_cards]
    return {
        "schema_version": "raw-info-disclosure-catalog-v1",
        "company_id": company_id,
        "as_of": as_of.isoformat(),
        "cards": [
            document_card(document, include_sections=True) for document in page
        ],
        "counts": {
            "eligible": total,
            "included": len(page),
            "omitted": total - cursor - len(page),
        },
        "cursor": cursor,
        "next_cursor": (
            cursor + len(page) if cursor + len(page) < total else None
        ),
    }


def _matches_title_query(document: RawInfoDocument, tokens: list[str]) -> bool:
    title = _news_title(document)
    haystack = (title or "").casefold()
    if not haystack:
        readable, _origins = _readable_text(document)
        haystack = readable[:2_000].casefold()
    return all(token in haystack for token in tokens)


def fetch_entry(
    store: RawInfoStore,
    document_id: str,
    *,
    as_of: Any,
    section_id: str | None = None,
    budget_chars: int = _FETCH_DEFAULT_BUDGET_CHARS,
) -> dict[str, Any]:
    """Return one bounded working view: summary plus provenance reference.

    When the readable unit fits the budget the view is the complete
    verbatim readable text; otherwise the head windows are returned with
    bounded omission markers, and the reference remains valid for
    provenance reads and distillation.
    """

    from datetime import datetime as _datetime

    if not isinstance(as_of, _datetime):
        raise ValidationError("fetch_entry requires a timezone-aware as_of")
    document = store.load(document_id, as_of=as_of)
    readable, origins = _readable_text(document)
    raw_start, raw_end = 0, len(document.content)
    if section_id is not None:
        sections = _filing_sections(readable, origins)
        match = next(
            (row for row in sections if row["section_id"] == section_id), None
        )
        if match is None:
            raise ValidationError(
                "fetch_entry section is not in the document section index"
            )
        index = sections.index(match)
        raw_start = match["raw_start"]
        raw_end = (
            sections[index + 1]["raw_start"]
            if index + 1 < len(sections)
            else len(document.content)
        )
        # Map raw offsets back to readable offsets through the origins list.
        readable_start = next(
            (
                position
                for position, (start, _end) in enumerate(origins)
                if start >= raw_start
            ),
            len(readable),
        )
        readable_end = next(
            (
                position
                for position, (start, _end) in enumerate(origins)
                if start >= raw_end
            ),
            len(readable),
        )
        unit = readable[readable_start:readable_end]
    else:
        unit = readable
    reference = {
        "document_id": document.document_id,
        "content_hash": document.content_hash,
        "raw_start": raw_start,
        "raw_end": raw_end,
    }
    if len(unit) <= budget_chars:
        return {
            "schema_version": "raw-info-disclosure-fetch-v1",
            "reference": reference,
            "kind": "verbatim",
            "text": unit,
            "omitted_context_markers": [],
        }
    windows: list[str] = []
    used = 0
    position = 0
    while position < len(unit) and used < budget_chars:
        window = unit[position : position + _FETCH_WINDOW_CHARS]
        if used + len(window) > budget_chars:
            window = window[: budget_chars - used]
        windows.append(window)
        used += len(window)
        position += _FETCH_WINDOW_CHARS
    remaining_previews = max(0, len(unit) - used)
    omitted: list[str] = []
    tail = unit[used:]
    tail_position = 0
    while (
        tail_position < len(tail) and len(omitted) < _FETCH_OMITTED_MARKERS
    ):
        marker = tail[tail_position : tail_position + 110].strip()
        if marker:
            omitted.append(marker)
        tail_position += 2_000
    return {
        "schema_version": "raw-info-disclosure-fetch-v1",
        "reference": reference,
        "kind": "bounded",
        "text": "\n".join(windows),
        "visible_chars": len(unit),
        "delivered_chars": used,
        "omitted_chars": remaining_previews,
        "omitted_context_markers": omitted,
    }


def read_provenance(
    store: RawInfoStore,
    reference: Mapping[str, Any],
    *,
    as_of: Any,
    max_chars: int = 48_000,
) -> dict[str, Any]:
    """Resolve one content-addressed reference to exact original content."""

    from datetime import datetime as _datetime

    if not isinstance(as_of, _datetime):
        raise ValidationError("read_provenance requires a timezone-aware as_of")
    document_id = reference.get("document_id")
    content_hash = reference.get("content_hash")
    if not isinstance(document_id, str) or not isinstance(content_hash, str):
        raise ValidationError(
            "provenance reference requires document_id and content_hash"
        )
    document = store.load(document_id, as_of=as_of)
    if document.content_hash != content_hash:
        raise ValidationError(
            "provenance reference content hash does not match the document"
        )
    start = int(reference.get("raw_start", 0))
    end = int(reference.get("raw_end", len(document.content)))
    if not 0 <= start < end <= len(document.content):
        raise ValidationError("provenance reference offsets are invalid")
    exact = document.content[start:end]
    if len(exact) > max_chars:
        raise ValidationError(
            "provenance read exceeds its budget; fetch a bounded view instead"
        )
    return {
        "schema_version": "raw-info-disclosure-provenance-v1",
        "document_id": document.document_id,
        "content_hash": document.content_hash,
        "raw_start": start,
        "raw_end": end,
        "exact_text": exact,
    }
