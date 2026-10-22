"""Frozen, bounded source sessions for production LLM Signal extraction.

This module owns reading state, not measurement semantics. Complete source
records remain immutable; only disclosed windows authorize final citations.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import LLMSignalBatchInput


CATALOG_PREFIX = "source_catalog:v1:"
MAX_EXCHANGES = 2
MAX_DOCUMENTS = 10
MAX_CHARACTERS = 32_000
PAGE_SIZE = 20


def catalog_signature(item: LLMSignalBatchInput, as_of: datetime) -> str:
    """Bind the entire eligible pool, exact skill/spec and point in time."""

    return CATALOG_PREFIX + canonical_json_hash({
        "spec": item.spec.to_dict(), "skill": item.skill, "as_of": as_of.isoformat(),
        "documents": [d.to_dict() for d in item.eligible_documents or ()],
    })


class SignalSourceSession:
    """Apply at most two validated read/page actions to one frozen pool."""

    def __init__(self, item: LLMSignalBatchInput, as_of: datetime) -> None:
        from stock_opportunity_agent.research.evolution_core import _company_facts_context
        from stock_opportunity_agent.research.scheme_evolution import _normalized_projection_text

        self.item = deepcopy(item)
        self.as_of = as_of
        self.signature = catalog_signature(self.item, as_of)
        pool = self.item.eligible_documents or ()
        if len({d.document_id for d in pool}) != len(pool):
            raise ValidationError("source catalog requires unique document ids")
        if len({d.company_id for d in pool}) > 1 or any(
            d.available_at > as_of or d.published_at > as_of for d in pool
        ):
            raise ValidationError("source catalog mixes owners or future sources")
        self.sources = {}
        self.views = {}
        self.groups = {}
        for document in pool:
            handle = "source_" + canonical_json_hash(document.to_dict())[:24]
            self.sources[handle] = document
            facts = _company_facts_context(document,
                max_content_chars=max(MAX_CHARACTERS, len(document.content) * 4),
                query=item.spec.retrieval_policy.query, include_history=True)
            if facts is not None:
                # This local index is not model disclosure. Default callers
                # retain latest/comparable views; explicit reads can address
                # older original periods without changing their raw literals.
                self.groups[handle] = facts
                self.views[handle] = (document.content,
                    ((0, len(document.content), 0, len(document.content)),))
            else:
                self.views[handle] = _normalized_projection_text(document.content,
                    strip_market_metadata=document.source_type.casefold() in
                    {"market_data", "historical_price", "price_daily", "prices"})
        self.exchanges = 0
        self.characters = 0
        self.rows: list[dict[str, Any]] = []
        self.lineage: dict[str, Any] = {}
        self.read_handles: set[str] = set()
        self.intervals: dict[str, list[tuple[int, int]]] = {}
        self.history: list[dict[str, Any]] = []
        self.catalogued_handles: set[str] = set()
        self.preview_characters = 0
        self.closed = False

    def catalog(self, cursor: int = 0) -> dict[str, Any]:
        """Return bounded cards; previews consume budget but cannot be cited."""

        handles = tuple(self.sources)
        if type(cursor) is not int or cursor < 0 or (cursor >= len(handles) and cursor != 0):
            raise ValidationError("invalid source catalog cursor")
        cards = []
        for handle in handles[cursor:cursor + PAGE_SIZE]:
            d = self.sources[handle]
            text, _ = self.views[handle]
            card = {"source_ref": handle, "source_type": d.source_type,
                    "available_at": d.available_at.isoformat(),
                    "published_at": d.published_at.isoformat(),
                    "content_hash": d.content_hash, "coordinate_length": len(text),
                    "coordinates": "raw" if handle in self.groups else "normalized_readable",
                    "read_start": 0, "preview": text[:140]}
            if handle not in self.catalogued_handles:
                self.catalogued_handles.add(handle)
                self.characters += len(card["preview"])
                self.preview_characters += len(card["preview"])
            if handle in self.groups:
                groups = self.groups[handle]["concepts"]
                card.update(self._group_page(handle, 0))
                card["read_start"] = min((r["start"] for c in groups for r in c["records"]), default=0)
            cards.append(card)
        end = cursor + len(cards)
        return {"signature": self.signature, "total": len(handles), "cursor": cursor,
                "cards": cards, "next_cursor": end if end < len(handles) else None,
                "limits": {"remaining_exchanges": MAX_EXCHANGES - self.exchanges,
                    "max_documents_per_read": 5, "remaining_documents": MAX_DOCUMENTS - len(self.read_handles),
                    "remaining_source_characters": MAX_CHARACTERS - self.characters},
                "metadata_is_not_evidence": True}

    def _group_page(self, handle: str, cursor: int) -> dict[str, Any]:
        from stock_opportunity_agent.research.evolution_core import _optional_iso_date

        queues = []
        for concept in self.groups[handle]["concepts"]:
            periods = {}
            for record in concept["records"]:
                period = _optional_iso_date(json.loads(record["exact_span"]).get("end"))
                periods.setdefault(period, []).append(record)
            queues.append([{**concept, "records": periods[p], "period_end": p.isoformat()}
                           for p in sorted(periods, reverse=True)])
        groups = [q[index] for index in range(max(map(len, queues), default=0))
                  for q in queues if index < len(q)]
        if type(cursor) is not int or cursor < 0 or (cursor >= len(groups) and cursor != 0):
            raise ValidationError("invalid fact group cursor")
        return {"fact_group_count": len(groups), "group_cursor": cursor,
                "fact_groups": [{"taxonomy": c["taxonomy"], "concept": c["concept"],
                    "unit": c["unit"], "period_end": c["period_end"],
                    "offset": min(r["start"] for r in c["records"]),
                    "length": max(r["end"] for r in c["records"]) - min(r["start"] for r in c["records"])}
                    for c in groups[cursor:cursor + PAGE_SIZE]],
                "next_group_cursor": cursor + PAGE_SIZE if cursor + PAGE_SIZE < len(groups) else None,
                "source_context_partial": self.groups[handle]["partial"]}

    def apply(self, action: Mapping[str, Any]) -> dict[str, Any]:
        """Validate an entire exchange before committing any disclosed source."""

        if self.closed or self.exchanges >= MAX_EXCHANGES:
            raise ValidationError("source reading session is closed or exhausted")
        if not isinstance(action, Mapping):
            raise ValidationError("source reading action must be an object")
        if set(action) == {"finalize"} and action["finalize"] is True:
            self.closed = True
            self.history.append({"action": dict(action), "result": {"closed": True}})
            return {"closed": True}
        if set(action) == {"catalog_cursor"}:
            result = self.catalog(action["catalog_cursor"])
        elif set(action) == {"catalog_source_ref", "group_cursor"}:
            handle = action["catalog_source_ref"]
            if not isinstance(handle, str) or handle not in self.groups:
                raise ValidationError("unknown structured source handle")
            result = {"source_ref": handle, **self._group_page(handle, action["group_cursor"])}
        elif set(action) == {"reads"}:
            reads = action["reads"]
            if not isinstance(reads, list) or not 1 <= len(reads) <= 5:
                raise ValidationError("source read exchange requires one to five windows")
            handles = {r.get("source_ref") for r in reads if isinstance(r, Mapping)
                       and isinstance(r.get("source_ref"), str)}
            if len(self.read_handles | handles) > MAX_DOCUMENTS:
                raise ValidationError("source document ceiling exceeded")
            rows, lineage, intervals, windows = [], {}, deepcopy(self.intervals), []
            for request in reads:
                window, projected, mapped, read_intervals = self._read(request)
                handle = request["source_ref"]
                for interval in read_intervals:
                    if any(interval[0] < end and start < interval[1]
                           for start, end in intervals.get(handle, ())):
                        raise ValidationError("duplicate or overlapping source read")
                    intervals.setdefault(handle, []).append(interval)
                if any(row["projection_id"] in self.lineage or row["projection_id"] in lineage for row in projected):
                    raise ValidationError("source fact group was already read")
                windows.append(window)
                rows.extend(projected)
                lineage.update(mapped)
            added = sum(len(r["exact_text"]) for r in rows)
            if self.characters + added > MAX_CHARACTERS:
                raise ValidationError("source character ceiling exceeded; request a smaller window")
            self.rows.extend(rows)
            self.lineage.update(lineage)
            self.intervals = intervals
            self.read_handles.update(handles)
            self.characters += added
            result = {"windows": windows, "source_projection": rows,
                      "visible_source_characters": self.characters,
                      "omitted_text_may_contain_additional_evidence": True}
        else:
            raise ValidationError("unknown source reading action or extra fields")
        self.exchanges += 1
        result["remaining_exchanges"] = MAX_EXCHANGES - self.exchanges
        self.history.append({"action": deepcopy(dict(action)), "result": deepcopy(result)})
        return result

    def _read(self, request: Any) -> tuple[Any, ...]:
        from stock_opportunity_agent.research.evolution_signal_roles import (
            _SignalProjectionLineage, _slice_projection_offset_runs,
        )

        if not isinstance(request, Mapping) or set(request) != {"source_ref", "offset", "length"}:
            raise ValidationError("read requires exactly source_ref, offset and length")
        handle, start, length = request["source_ref"], request["offset"], request["length"]
        if not isinstance(handle, str) or handle not in self.sources:
            raise ValidationError("read references an unknown source version")
        text, runs = self.views[handle]
        if type(start) is not int or type(length) is not int or start < 0 or start >= len(text) or length < 1:
            raise ValidationError("invalid source read coordinates")
        end = min(len(text), start + length)
        document = self.sources[handle]
        selections = []
        if handle in self.groups:
            from stock_opportunity_agent.research.evolution_core import (
                _company_fact_periods_comparable, _optional_iso_date,
            )

            for concept in self.groups[handle]["concepts"]:
                records = concept["records"]
                addressed = [r for r in records if start < r["end"] and r["start"] < end]
                if not addressed:
                    continue
                parsed = [(r, json.loads(r["exact_span"])) for r in records]
                periods = {_optional_iso_date(json.loads(r["exact_span"]).get("end")) for r in addressed}
                # Retain all alternatives at addressed ends, then the nearest
                # earlier comparable end for each of their durations.
                primary = [(r, value) for r, value in parsed
                           if _optional_iso_date(value.get("end")) in periods]
                prior_periods = set()
                for _r, value in primary:
                    older = [_optional_iso_date(v.get("end")) for _other, v in parsed
                        if _optional_iso_date(v.get("end")) < _optional_iso_date(value.get("end"))
                        and _company_fact_periods_comparable(value, v)]
                    if older:
                        prior_periods.add(max(older))
                selected = [r for r, v in parsed if _optional_iso_date(v.get("end")) in periods | prior_periods]
                context = {k: concept[k] for k in ("taxonomy", "concept", "unit")}
                context.update(source_context_partial=True,
                    omitted_concept_count=self.groups[handle]["omitted_concept_count"])
                selections.extend((r["start"], r["end"], context) for r in selected)
        else:
            # Preserve complete sentence units inside the requested window.
            # No relocation, character clipping or boundary-validator exception.
            boundaries = [0, *(m.end() for m in re.finditer(r'[.!?](?:["\')\]]*)(?=\s|$)', text)), len(text)]
            units = [(a, b) for a, b in zip(boundaries, boundaries[1:]) if a < b]
            selected = [(a, b) for a, b in units if a >= start and b <= end and text[a:b].strip()]
            if selected:
                selections.append((selected[0][0], selected[-1][1], None))
        rows, lineage = [], {}
        for a, b, context in selections:
            exact = text[a:b]
            projection_id = "projection_" + canonical_json_hash([document.document_id, document.content_hash, a, b, exact])[:24]
            rows.append({"projection_id": projection_id, "document_id": document.document_id,
                "content_hash": document.content_hash, "source_type": document.source_type,
                "published_at": document.published_at.isoformat(), "available_at": document.available_at.isoformat(),
                "exact_text": exact, "source_window": {"start": a, "end": b},
                **({"fact_context": context} if context is not None else {})})
            lineage[projection_id] = _SignalProjectionLineage(document, exact,
                _slice_projection_offset_runs(runs, a, b, rebase=a),
                0 if context else a, len(exact) if context else b,
                len(exact) if context else len(text), (self.item.spec.ref,))
        next_offset = end
        if handle not in self.groups:
            next_offset = selections[-1][1] if selections else start
        return ({"source_ref": handle, "requested_start": start, "requested_end": end,
                 "returned_units": len(rows), "next_offset": next_offset if next_offset < len(text) else None,
                 "source_complete": start == 0 and end == len(text) and handle not in self.groups},
                rows, lineage, tuple((a, b) for a, b, _context in selections))

    @property
    def documents(self) -> tuple[RawInfoDocument, ...]:
        """Return only versions whose source text actually reached the session."""

        ids = {row["document_id"] for row in self.rows}
        return tuple(d for d in self.sources.values() if d.document_id in ids)

    @property
    def visible_documents(self) -> tuple[RawInfoDocument, ...]:
        """Build coverage-only views without metadata from unseen source rows."""

        result = []
        for d in self.documents:
            rows = [r for r in self.rows if r["document_id"] == d.document_id]
            if any(r.get("fact_context") for r in rows):
                content = json.dumps({"rows": [json.loads(r["exact_text"]) for r in rows]})
            else:
                content = " ".join(r["exact_text"] for r in rows)
            result.append(RawInfoDocument.create(
                document_id="visibility_" + canonical_json_hash([d.document_id, content])[:24],
                company_id=d.company_id, source_type=d.source_type,
                published_at=d.published_at, available_at=d.available_at,
                content=content, metadata={},
            ))
        return tuple(result)

    def trace(self) -> dict[str, Any]:
        """Return deterministic replay data; role requests live in native journals."""

        return {"catalog_signature": self.signature, "catalog_size": len(self.sources),
                "exchanges": self.exchanges, "characters": self.characters,
                "preview_characters": self.preview_characters,
                "history": deepcopy(self.history), "closed": self.closed,
                "read_documents": [d.document_id for d in self.documents]}
