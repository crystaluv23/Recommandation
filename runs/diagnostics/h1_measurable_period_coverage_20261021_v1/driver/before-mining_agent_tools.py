"""Lazy PIT Evidence Graph tools for the label-aware mining controller.

The graph specified in ``spec/src/stock_opportunity_agent/research/
signal_mining_agent.md`` is virtual: facts project only from documents that
were already selected for one case under the point-in-time rule, relations are
constructed deterministically inside the three bounded scopes, and no
cross-case enumeration or all-pairs construction exists. Every fetch returns
its coverage accounting so a bounded view can never be read as proof of
absence.

Minimal Phase 1 surface: store-local projections with bounded coverage
reporting. Ledger/budget integration routes through the existing evidence
resolver in Phase 2.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Sequence

from stock_opportunity_agent.data.disclosure import document_card
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    EvolutionCase,
    _company_facts_context,
    _company_fact_periods_comparable,
    _evidence_source_family,
    _optional_iso_date,
    _query_relevant_excerpt,
)

_FACT_PROJECTION_CHARS = 12_000
_NARRATIVE_EXCERPT_CHARS = 600

COMPUTE_RULES = frozenset(
    {
        "latest_over_comparable_prior",
        "latest_minus_comparable_prior",
        "latest_over_latest",
    }
)


def _opaque_ref(*parts: object) -> str:
    digest = hashlib.sha256(
        "\x1f".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()
    return digest[:16]


@dataclass(frozen=True)
class EvidenceFact:
    """One indivisible structured fact with verbatim source lineage."""

    fact_ref: str
    case_ref: str
    concept: str
    unit: str
    period: Mapping[str, str] | None
    value: str
    record_selection: str
    document_ref: str
    exact_span: str
    content_hash: str
    available_at: str
    source_display_name: str = ""


@dataclass(frozen=True)
class EvidenceRelation:
    """One deterministically constructed relation between existing facts."""

    relation_ref: str
    kind: str
    fact_refs: tuple[str, ...]
    case_ref: str
    rule: str | None = None
    value: str | None = None


@dataclass(frozen=True)
class NarrativeEvent:
    """One bounded narrative excerpt with immutable source lineage.

    ``title`` is a deterministic masked label (document metadata or masked
    headline); ``excerpt`` is a masked visible-text summary that is
    discovery-only and can never be candidate evidence on its own;
    ``exact_span`` is the verbatim raw-content window the excerpt anchors to,
    held inside the runtime and traceable to the content-hash-verified
    document. ``source_family`` is the normalized family (never the raw
    source_type) and ``event_ref`` identity is stable across paginated reads.
    """

    event_ref: str
    case_ref: str
    document_ref: str
    excerpt: str
    content_hash: str
    available_at: str
    title: str = ""
    source_family: str = ""
    published_at: str = ""
    exact_span: str = ""


@dataclass(frozen=True)
class FetchResult:
    """One bounded evidence fetch with complete coverage accounting."""

    request: Mapping[str, object]
    documents: tuple[RawInfoDocument, ...]
    facts: tuple[EvidenceFact, ...] = ()
    narrative_events: tuple[NarrativeEvent, ...] = ()
    excluded_by_limits: tuple[str, ...] = ()
    query_coverage: Mapping[str, object] = field(default_factory=dict)
    unread_same_source: bool = False


def _case_documents(
    store: RawInfoStore, case: EvolutionCase
) -> tuple[RawInfoDocument, ...]:
    return tuple(
        document
        for document in store.documents
        if document.company_id == case.company_id
        and document.available_at <= case.prediction_time
    )


def _facts_from_document(
    document: RawInfoDocument, *, case_ref: str
) -> tuple[EvidenceFact, ...]:
    context = _company_facts_context(
        document,
        max_content_chars=_FACT_PROJECTION_CHARS,
        query=None,
    )
    if context is None:
        return ()
    payload = json.loads(document.content)
    value_key = ("value" if payload.get("schema_version") == "sec-company-facts-document-v1" else "val")
    facts: list[EvidenceFact] = []
    for concept in context["concepts"]:
        records = tuple(concept.get("records", ()))
        parsed_records = []
        for record in records:
            try:
                parsed = json.loads(str(record.get("exact_span", "")))
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                parsed_records.append(parsed)
        latest_end = max((_optional_iso_date(row.get("end")) or date.min
                          for row in parsed_records), default=date.min)
        for record in records:
            span = str(record.get("exact_span", ""))
            if not span:
                continue
            try:
                parsed = json.loads(span)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, Mapping) or value_key not in parsed:
                continue
            period = {
                key: str(parsed[key])
                for key in ("start", "end")
                if parsed.get(key) is not None
            }
            facts.append(
                EvidenceFact(
                    fact_ref="fact-" + _opaque_ref(
                        document.document_id,
                        document.content_hash,
                        concept["concept"],
                        concept["unit"],
                        record.get("start"),
                        record.get("end"),
                        case_ref,
                    ),
                    case_ref=case_ref,
                    concept=str(concept["concept"]),
                    unit=str(concept["unit"]),
                    period=period or None,
                    value=str(parsed[value_key]),
                    record_selection=(
                        "latest" if _optional_iso_date(parsed.get("end")) == latest_end else "comparable_prior"
                    ),
                    document_ref=f"document-{document.document_id}",
                    exact_span=span,
                    content_hash=document.content_hash,
                    available_at=document.available_at.isoformat(),
                    source_display_name=str(concept.get("label", "")),
                )
            )
    return tuple(facts)


def project_case_facts(
    store: RawInfoStore, case: EvolutionCase, *, case_ref: str = ""
) -> tuple[EvidenceFact, ...]:
    """Project structured facts from one case's point-in-time documents."""

    ref = case_ref or f"case-{case.case_id}"
    facts: list[EvidenceFact] = []
    for document in _case_documents(store, case):
        source_type = document.source_type.casefold()
        if "fact" not in source_type and "financial" not in source_type:
            continue
        facts.extend(_facts_from_document(document, case_ref=ref))
    return tuple(facts)


def project_facts_from_documents(
    documents: Iterable[RawInfoDocument], *, case_ref: str
) -> tuple[EvidenceFact, ...]:
    """Project structured facts from already-selected point-in-time documents."""

    facts: list[EvidenceFact] = []
    for document in documents:
        source_type = document.source_type.casefold()
        if "fact" not in source_type and "financial" not in source_type:
            continue
        facts.extend(_facts_from_document(document, case_ref=case_ref))
    return tuple(facts)


def _fact_period(fact: EvidenceFact) -> dict[str, str] | None:
    """Read an explicit valid period without inventing a comparison basis."""
    if not isinstance(fact.period, Mapping):
        return None
    try:
        end = date.fromisoformat(fact.period["end"])
        start = date.fromisoformat(fact.period["start"]) if "start" in fact.period else None
    except (KeyError, TypeError, ValueError):
        return None
    if start is not None and start > end:
        return None
    return {"end": end.isoformat(), **({"start": start.isoformat()} if start is not None else {})}


def _fact_taxonomy(fact: EvidenceFact) -> str:
    """Typed whole rows prove a namespace; legacy leaf spans do not."""
    try:
        row = json.loads(fact.exact_span)
    except (TypeError, ValueError):
        return ""
    value = row.get("taxonomy") if isinstance(row, Mapping) else None
    return value if isinstance(value, str) else ""


def _fact_value_key(fact: EvidenceFact) -> tuple[str, object]:
    """Compare numeric spellings exactly, preserving every original value/span."""
    try:
        value = Decimal(fact.value)
        if value.is_finite():
            return ("number", value)
    except (InvalidOperation, TypeError, ValueError):
        pass
    return ("literal", fact.value)


def _fact_basis(fact: EvidenceFact) -> tuple[object, ...]:
    period = _fact_period(fact) or {}
    return (fact.case_ref, fact.concept, fact.unit, _fact_taxonomy(fact),
            period.get("start"), period.get("end"), _fact_value_key(fact))


def _unique_latest_fact(facts: Sequence[EvidenceFact]) -> EvidenceFact | None:
    """Return a scalar only when all current unit/duration/value bases agree."""
    if not facts or any(_fact_period(fact) is None for fact in facts):
        return None
    if len({(fact.case_ref, fact.concept, fact.unit, _fact_taxonomy(fact)) for fact in facts}) != 1:
        return None
    latest_end = max(_fact_period(fact)["end"] for fact in facts)
    latest = [fact for fact in facts if _fact_period(fact)["end"] == latest_end]
    if len({_fact_basis(fact) for fact in latest}) != 1:
        return None
    return min(latest, key=lambda fact: fact.fact_ref)


def _unique_period_pair(facts: Sequence[EvidenceFact]) -> tuple[EvidenceFact, EvidenceFact] | None:
    """Require one current basis before looking for a unique local prior."""
    latest = _unique_latest_fact(facts)
    if latest is None:
        return None
    by_ref = {fact.fact_ref: fact for fact in facts}
    pairs = [tuple(by_ref[ref] for ref in relation.fact_refs)
             for relation in build_same_concept_relations(facts)]
    pairs = [pair for pair in pairs if _fact_basis(pair[0]) == _fact_basis(latest)]
    if not pairs or len({(_fact_basis(pair[0]), _fact_basis(pair[1])) for pair in pairs}) != 1:
        return None
    return min(pairs, key=lambda pair: (pair[0].fact_ref, pair[1].fact_ref))


def build_same_concept_relations(
    facts: Sequence[EvidenceFact],
) -> tuple[EvidenceRelation, ...]:
    """Build at most one unambiguous nearest local pair per current period."""
    grouped: dict[tuple[str, ...], list[EvidenceFact]] = {}
    for fact in facts:
        key = (fact.case_ref, fact.concept, fact.unit, fact.document_ref,
               fact.content_hash, _fact_taxonomy(fact))
        grouped.setdefault(key, []).append(fact)
    relations = []
    for key, group in sorted(grouped.items()):
        if not key[3] or not key[4] or any(_fact_period(fact) is None for fact in group):
            continue
        latest_end = max(_fact_period(fact)["end"] for fact in group)
        periods: dict[tuple[str | None, str], list[EvidenceFact]] = {}
        for fact in group:
            periods.setdefault((_fact_period(fact).get("start"), _fact_period(fact)["end"]), []).append(fact)
        for period, alternatives in sorted(periods.items(), key=lambda item: str(item[0])):
            if period[1] != latest_end or len({_fact_value_key(fact) for fact in alternatives}) != 1:
                continue
            current = min(alternatives, key=lambda fact: fact.fact_ref)
            prior = [fact for fact in group if _fact_period(fact)["end"] < latest_end
                     and _company_fact_periods_comparable(current.period, fact.period)]
            if not prior:
                continue
            prior_end = max(_fact_period(fact)["end"] for fact in prior)
            prior = [fact for fact in prior if _fact_period(fact)["end"] == prior_end]
            if len({_fact_basis(fact) for fact in prior}) != 1:
                continue
            previous = min(prior, key=lambda fact: fact.fact_ref)
            relations.append(EvidenceRelation(
                relation_ref="relation-" + _opaque_ref("same_concept", current.fact_ref, previous.fact_ref),
                kind="same_concept_period_pair", fact_refs=(current.fact_ref, previous.fact_ref),
                case_ref=current.case_ref))
    return tuple(relations)


def compute_statistic(
    rule: str,
    fact_refs: Sequence[str],
    *,
    facts: Sequence[EvidenceFact],
) -> EvidenceRelation:
    """Compute one frozen-rule numeric relation with explicit fact lineage."""

    if rule not in COMPUTE_RULES:
        raise ValidationError(f"unknown compute_statistic rule: {rule}; allowed: {sorted(COMPUTE_RULES)}")
    if len(fact_refs) != 2:
        raise ValidationError("compute_statistic requires exactly two fact refs")
    by_ref = {fact.fact_ref: fact for fact in facts}
    try:
        numerator = by_ref[fact_refs[0]]
        denominator = by_ref[fact_refs[1]]
    except KeyError as exc:
        raise ValidationError(
            "compute_statistic fact refs must reference supplied facts"
        ) from exc
    if numerator.case_ref != denominator.case_ref:
        raise ValidationError(
            "compute_statistic operands must belong to one case"
        )
    try:
        left = float(numerator.value)
        right = float(denominator.value)
    except (ValueError, OverflowError) as exc:
        raise ValidationError(
            "compute_statistic operands must be numeric facts"
        ) from exc
    if not math.isfinite(left) or not math.isfinite(right):
        raise ValidationError("compute_statistic operands must be finite numeric facts")
    if rule == "latest_minus_comparable_prior":
        value: float = left - right
    else:
        if right == 0:
            raise ValidationError("compute_statistic ratio denominator must be non-zero")
        value = left / right
    if not math.isfinite(value):
        raise ValidationError("compute_statistic result must be finite")
    return EvidenceRelation(
        relation_ref="relation-" + _opaque_ref(
            "computed", rule, numerator.fact_ref, denominator.fact_ref
        ),
        kind="numerator_denominator",
        fact_refs=(numerator.fact_ref, denominator.fact_ref),
        case_ref=numerator.case_ref,
        rule=rule,
        value=f"{value:.6f}",
    )


def build_case_co_occurrence_relations(
    facts: Sequence[EvidenceFact], *, limit: int
) -> tuple[EvidenceRelation, ...]:
    """Relate facts of one case that corroborate across different documents."""

    if limit < 1:
        raise ValidationError("co-occurrence limit must be positive")
    by_case: dict[str, list[EvidenceFact]] = {}
    for fact in facts:
        by_case.setdefault(fact.case_ref, []).append(fact)
    relations: list[EvidenceRelation] = []
    for case_ref, case_facts in sorted(by_case.items()):
        ordered = sorted(case_facts, key=lambda fact: fact.fact_ref)
        for left in ordered:
            for right in ordered:
                if left.document_ref >= right.document_ref:
                    continue
                relations.append(
                    EvidenceRelation(
                        relation_ref="relation-" + _opaque_ref(
                            "co_occurrence", left.fact_ref, right.fact_ref
                        ),
                        kind="case_co_occurrence",
                        fact_refs=(left.fact_ref, right.fact_ref),
                        case_ref=case_ref,
                    )
                )
                if len(relations) >= limit:
                    return tuple(relations)
    return tuple(relations)


def _query_terms(query: str | None) -> tuple[str, ...]:
    if not query:
        return ()
    return tuple(
        term
        for term in re.findall(r"[a-z0-9]+", query.casefold())
        if len(term) >= 4
    )


def fetch_case_evidence(
    store: RawInfoStore,
    case: EvolutionCase,
    *,
    source_families: Sequence[str],
    query: str | None = None,
    max_documents: int,
    case_ref: str = "",
) -> FetchResult:
    """Fetch bounded evidence for one case with complete coverage accounting."""

    if max_documents < 1:
        raise ValidationError("max_documents must be positive")
    ref = case_ref or f"case-{case.case_id}"
    wanted = {str(family).casefold() for family in source_families}
    terms = _query_terms(query)

    def eligible(document: RawInfoDocument) -> bool:
        normalized = document.source_type.casefold()
        return normalized in wanted or _evidence_source_family(
            document.source_type
        ) in wanted

    candidates = [
        document for document in _case_documents(store, case) if eligible(document)
    ]
    if terms:
        scored = []
        for document in candidates:
            tokens = set(re.findall(r"[a-z0-9]+", document.content.casefold()))
            overlap = sum(1 for term in terms if term in tokens)
            if overlap:
                scored.append((overlap, document))
        scored.sort(key=lambda item: (-item[0], item[1].available_at, item[1].document_id))
        candidates = [document for _score, document in scored]

    selected = candidates[:max_documents]
    excluded = tuple(document.document_id for document in candidates[max_documents:])

    facts: list[EvidenceFact] = []
    events: list[NarrativeEvent] = []
    matched_terms: set[str] = set()
    for document in selected:
        source_type = document.source_type.casefold()
        structured = "fact" in source_type or "financial" in source_type
        if structured:
            projected = _facts_from_document(document, case_ref=ref)
            if projected:
                facts.extend(projected)
                continue
        family = _evidence_source_family(document.source_type)
        if family not in {"filing", "transcript", "news"}:
            # Structured families that project no facts (price series, raw
            # provider envelopes) stay fetched documents with ledger
            # coverage; they are never laundered into narrative events.
            continue
        excerpt, _clipped = _query_relevant_excerpt(
            document, query=query, max_chars=_NARRATIVE_EXCERPT_CHARS
        )
        tokens = set(re.findall(r"[a-z0-9]+", excerpt.casefold()))
        matched_terms.update(term for term in terms if term in tokens)
        exact_span = _verbatim_window(document.content, excerpt)
        events.append(
            NarrativeEvent(
                event_ref="event-" + _opaque_ref(
                    document.document_id, document.content_hash, ref
                ),
                case_ref=ref,
                document_ref=f"document-{document.document_id}",
                excerpt=excerpt,
                content_hash=document.content_hash,
                available_at=document.available_at.isoformat(),
                title=_narrative_title(document),
                source_family=_evidence_source_family(document.source_type),
                published_at=document.published_at.isoformat(),
                exact_span=exact_span,
            )
        )
    return FetchResult(
        request={
            "case_ref": ref,
            "source_families": tuple(source_families),
            "query": query,
            "max_documents": max_documents,
        },
        documents=tuple(selected),
        facts=tuple(facts),
        narrative_events=tuple(events),
        excluded_by_limits=excluded,
        query_coverage={
            "matched_terms": sorted(matched_terms),
            "sufficient": bool(terms) and bool(matched_terms),
        },
        unread_same_source=bool(excluded),
    )


_NARRATIVE_TITLE_CHARS = 120
_DOCUMENT_FILENAME_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]{1,11}-\d{6,12}(?![A-Za-z0-9])"
)


def strip_document_artifacts(text: str) -> str:
    """Remove document-internal filename tokens from narrative projections.

    SEC submissions embed their own document names (e.g. ``cenx-20240325``)
    and namespace prefixes in body text; these carry issuer tickers in
    lowercase forms the case-sensitive alias mask does not replace. Titles
    and read windows pass through this strip before entering any model view.
    """

    return _DOCUMENT_FILENAME_TOKEN.sub("<doc>", text)


def _narrative_title(document: RawInfoDocument) -> str:
    """Deterministic masked title label for one narrative document.

    Filing bodies derive from form metadata; JSON news payloads expose their
    headline field; anything else falls back to the first visible words of
    the projection text. All paths are identity-masked by the caller's view
    projection; the label itself never invents content.
    """

    metadata_title = str(document.metadata.get("title", "")).strip()
    if metadata_title:
        return metadata_title[:_NARRATIVE_TITLE_CHARS]
    if document.content.lstrip().startswith("{"):
        try:
            payload = json.loads(document.content)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            headline = str(
                payload.get("title")
                or payload.get("headline")
                or ""
            ).strip()
            if headline:
                return headline[:_NARRATIVE_TITLE_CHARS]
    form = str(document.metadata.get("form", "")).strip()
    if form:
        period = str(
            document.metadata.get("period_end", "")
            or document.available_at.date().isoformat()
        ).strip()
        return f"{form} {period}"[:_NARRATIVE_TITLE_CHARS].strip()
    visible, _clipped = _query_relevant_excerpt(
        document, query=None, max_chars=_NARRATIVE_TITLE_CHARS * 2
    )
    visible = strip_document_artifacts(" ".join(visible.split()))
    first_sentence = re.split(r"(?<=[.!?])\s", visible, maxsplit=1)[0]
    return (first_sentence or visible)[:_NARRATIVE_TITLE_CHARS]


def _verbatim_window(content: str, excerpt: str, radius: int = 80) -> str:
    """Return a verbatim raw-content window anchored to an excerpt.

    The excerpt itself is normalized visible text and may not be a literal
    substring; the verbatim window keeps ledger traceability by locating the
    excerpt's leading tokens inside the raw content and slicing around them,
    falling back to the raw head when no anchor is found.
    """

    anchor_tokens = [token for token in excerpt.split() if token][:6]
    if anchor_tokens:
        anchor = " ".join(anchor_tokens)
        start = content.find(anchor[: max(8, len(anchor) // 2)])
        if start >= 0:
            left = max(0, start - radius)
            right = min(len(content), start + len(anchor) + radius)
            return content[left:right]
    return content[: 2 * radius]


def _events_by_document(
    events: Iterable[NarrativeEvent],
) -> dict[tuple[str, str], dict[str, NarrativeEvent]]:
    """Group the latest case-scoped orientation by immutable document."""
    grouped: dict[tuple[str, str], dict[str, NarrativeEvent]] = {}
    for event in events:
        grouped.setdefault((event.document_ref, event.content_hash), {})[event.case_ref] = event
    return grouped


def narrative_catalog(
    documents: Iterable[RawInfoDocument],
    events: Iterable[NarrativeEvent],
    *,
    max_per_family: int = 8,
    document_cards: dict[tuple[str, str], dict[str, Any]] | None = None,
    case_refs_by_document: Mapping[tuple[str, str], Iterable[str]] | None = None,
) -> list[dict[str, object]]:
    """Build the discovery-only fetched-evidence directory.

    Organizes already-fetched narrative evidence as
    family -> time window -> document refs with masked titles and bounded
    summaries. Every row is discovery_only: it steers search but can never be
  cited as candidate evidence.
    """

    windows: dict[str, dict[str, dict[str, object]]] = {}
    grouped_events = _events_by_document(events)
    seen_documents: set[tuple[str, str]] = set()
    for document in documents:
        family = _evidence_source_family(document.source_type)
        if family not in {"filing", "transcript", "news"}:
            continue
        identity = (document.document_id, document.content_hash)
        if identity in seen_documents:
            continue
        seen_documents.add(identity)
        window = f"{document.available_at.year}Q{(document.available_at.month - 1) // 3 + 1}"
        bucket = windows.setdefault(family, {}).setdefault(window, {})
        case_events = grouped_events.get((f"document-{document.document_id}", document.content_hash), {})
        event = next(reversed(case_events.values()), None)
        case_refs = set((case_refs_by_document or {}).get(identity, ())) | set(case_events)
        bindings = [{"case_ref": ref, "event_ref": case_events[ref].event_ref if ref in case_events else None}
                    for ref in sorted(case_refs)]
        if event is not None:
            bucket[event.event_ref] = {
                "event_ref": event.event_ref,
                "document_ref": event.document_ref,
                "title": event.title,
                "available_at": event.available_at,
                "discovery_only": True,
                "case_bindings": bindings,
            }
        elif len(bucket) < max_per_family:
            bucket[f"document-{document.document_id}"] = {
                "event_ref": None,
                "document_ref": f"document-{document.document_id}",
                "title": _narrative_title(document),
                "available_at": document.available_at.isoformat(),
                "discovery_only": True,
                "case_bindings": bindings,
            }
        else:
            continue
        card = document_cards.get(identity) if document_cards is not None else None
        if card is None:
            card = document_card(document, include_sections=True)
            if document_cards is not None:
                document_cards[identity] = card
        row = bucket[event.event_ref if event is not None else f"document-{document.document_id}"]
        row.update({
            "raw_chars": card["raw_chars"],
            "readable_start": card["readable_start"],
            "sections": card.get("sections", []),
            "section_count": card.get("section_count", 0),
        })
    catalog: list[dict[str, object]] = []
    for family in sorted(windows):
        family_rows = []
        for window in sorted(windows[family], reverse=True):
            entries = list(windows[family][window].values())
            family_rows.append(
                {"window": window, "entries": entries[:max_per_family]}
            )
        catalog.append({"family": family, "windows": family_rows})
    return catalog


# ---------------------------------------------------------------------------
# Optional attribute projection (action plan v2, Phase 4)
#
# An index layer only: it may aggregate, rank, and feed reflection, but it
# can never be the sole evidence for a narrative candidate and can never
# interpret a projection miss as the event's absence. The vocabulary is
# derived zero-call from the corpus (see derive_attribute_vocabulary); low
# support removes a pattern from the INDEX, never from the raw read path.


_ATTRIBUTE_VERB = r"(?:announced?|received?|awarded?|confirmed|entered|signed|secured|delivered|won|granted)"
_ATTRIBUTE_OBJECT = r"(?:purchase order|purchase agreement|supply agreement|commercial agreement|order|orders|contract|contracts|agreement|commitment|offtake(?: agreement)?|backlog(?: order)?)"
_MONEY = r"(?:US\$|USD\s?|\$)\s?([0-9][0-9,\.]*(?:\s?(?:million|billion|m|bn|k))?)"

_ATTRIBUTE_PATTERN = re.compile(
    rf"{_ATTRIBUTE_VERB}\s+(?:a\s+|an\s+|the\s+|its\s+)?(?:definitive\s+|binding\s+|multi-?year\s+|large\s+)?{_ATTRIBUTE_OBJECT}",
    re.IGNORECASE,
)
_ATTRIBUTE_NAME = "order_confirmation_disclosed"
_MIN_ATTRIBUTE_SUPPORT = 2


@dataclass(frozen=True)
class AttributeEvent:
    """One projected attribute hit with verbatim lineage (index-only)."""

    attribute_ref: str
    name: str
    case_ref: str
    document_ref: str
    exact_span: str
    content_hash: str
    available_at: str
    amount_usd: float | None = None


def _money_to_usd(raw: str) -> float | None:
    """Normalize a matched money literal to USD when unambiguous."""

    text = raw.replace(",", "").replace("USD", "").replace("$", "").strip()
    multiplier = 1.0
    low = text.lower()
    if low.endswith("billion") or low.endswith("bn"):
        multiplier, text = 1e9, low.rsplit(" ", 1)[0]
    elif low.endswith("million") or low.endswith("m"):
        multiplier, text = 1e6, low.rsplit(" ", 1)[0]
    elif low.endswith("k"):
        multiplier, text = 1e3, low.rsplit(" ", 1)[0]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def derive_attribute_vocabulary(
    documents: Iterable[RawInfoDocument],
    *,
    case_refs_by_company: Mapping[str, str] | None = None,
    min_support: int = _MIN_ATTRIBUTE_SUPPORT,
) -> dict[str, object]:
    """Zero-call corpus derivation of the attribute index vocabulary.

    Deterministic pattern mining over narrative documents; the returned
    artifact (name, pattern digest, support, corpus hash) is frozen into the
    run contract by the caller. Derivation only gates the INDEX: patterns
    below support stay discoverable through the raw read path regardless.
    """

    corpus = list({(document.document_id, document.content_hash): document for document in documents}.values())
    pattern_hits = 0
    for document in corpus:
        if _ATTRIBUTE_PATTERN.search(document.content):
            pattern_hits += 1
    vocabulary = {
        "schema_version": "attribute-vocabulary-v1",
        "attributes": (
            [
                {
                    "name": _ATTRIBUTE_NAME,
                    "pattern_sha256": hashlib.sha256(
                        _ATTRIBUTE_PATTERN.pattern.encode("utf-8")
                    ).hexdigest(),
                    "support": pattern_hits,
                }
            ]
            if pattern_hits >= min_support
            else []
        ),
        "min_support": min_support,
        "corpus_sha256": hashlib.sha256(
            "".join(
                sorted(document.content_hash for document in corpus)
            ).encode("utf-8")
        ).hexdigest(),
    }
    return vocabulary


def project_attributes(
    documents: Iterable[RawInfoDocument],
    events: Iterable[NarrativeEvent],
    *,
    vocabulary: Mapping[str, object],
) -> dict[str, list[dict[str, object]]]:
    """Project attribute index rows for fetched narrative evidence.

    Outcomes are typed per case: projected_positive / projected_counter /
    projected_unresolved / projection_unavailable. A miss never asserts the
    event's absence, and the projection is never the sole evidence path.
    """

    rows: dict[str, list[dict[str, object]]] = {}
    attributes = list(vocabulary.get("attributes", ()) or ())
    if not attributes:
        return rows
    wanted_names = {str(entry.get("name")) for entry in attributes}
    if _ATTRIBUTE_NAME not in wanted_names:
        return rows
    grouped_events = _events_by_document(events)
    narrative_documents = [
        document
        for document in documents
        if _evidence_source_family(document.source_type)
        in {"filing", "transcript", "news"}
    ]
    seen_documents: set[tuple[str, str]] = set()
    for document in narrative_documents:
        identity = (document.document_id, document.content_hash)
        if identity in seen_documents:
            continue
        seen_documents.add(identity)
        case_refs = sorted(grouped_events.get((f"document-{document.document_id}", document.content_hash), {})) or [""]
        for match in _ATTRIBUTE_PATTERN.finditer(document.content):
            money = re.search(_MONEY, document.content[match.end():match.end() + 160])
            amount = _money_to_usd(money.group(1)) if money else None
            start = match.start()
            for case_ref in case_refs:
                rows.setdefault(_ATTRIBUTE_NAME, []).append({
                    "attribute_ref": "attr-"
                    + _opaque_ref(
                        document.document_id,
                        document.content_hash,
                        start,
                        case_ref,
                    ),
                    "name": _ATTRIBUTE_NAME,
                    "case_ref": case_ref,
                    "document_ref": f"document-{document.document_id}",
                    "exact_span": document.content[
                        start : start + 200
                    ],
                    "content_hash": document.content_hash,
                    "available_at": document.available_at.isoformat(),
                    "amount_usd": amount,
                    "state": (
                        "projected_unresolved"
                        if amount is None
                        else "projected_positive"
                    ),
                })
    return rows
