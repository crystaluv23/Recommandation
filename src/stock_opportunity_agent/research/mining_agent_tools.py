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
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    EvolutionCase,
    _company_facts_context,
    _evidence_source_family,
)

_FACT_PROJECTION_CHARS = 12_000
_NARRATIVE_EXCERPT_CHARS = 600

_COMPUTE_RULES = frozenset(
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
    """One bounded narrative excerpt with immutable source lineage."""

    event_ref: str
    case_ref: str
    document_ref: str
    excerpt: str
    content_hash: str
    available_at: str


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
    facts: list[EvidenceFact] = []
    for concept in context["concepts"]:
        for record_index, record in enumerate(concept.get("records", ())):
            span = str(record.get("exact_span", ""))
            if not span:
                continue
            try:
                parsed = json.loads(span)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, Mapping) or "val" not in parsed:
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
                    ),
                    case_ref=case_ref,
                    concept=str(concept["concept"]),
                    unit=str(concept["unit"]),
                    period=period or None,
                    value=str(parsed["val"]),
                    record_selection=(
                        "latest" if record_index == 0 else "comparable_prior"
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


def build_same_concept_relations(
    facts: Sequence[EvidenceFact],
) -> tuple[EvidenceRelation, ...]:
    """Pair each concept's latest record with its comparable prior."""

    grouped: dict[tuple[str, str, str], dict[str, EvidenceFact]] = {}
    for fact in facts:
        grouped.setdefault(
            (fact.case_ref, fact.concept, fact.unit), {}
        )[fact.record_selection] = fact
    relations: list[EvidenceRelation] = []
    for (case_ref, _concept, _unit), roles in sorted(grouped.items()):
        latest = roles.get("latest")
        prior = roles.get("comparable_prior")
        if latest is None or prior is None:
            continue
        relations.append(
            EvidenceRelation(
                relation_ref="relation-" + _opaque_ref(
                    "same_concept", latest.fact_ref, prior.fact_ref
                ),
                kind="same_concept_period_pair",
                fact_refs=(latest.fact_ref, prior.fact_ref),
                case_ref=case_ref,
            )
        )
    return tuple(relations)


def compute_statistic(
    rule: str,
    fact_refs: Sequence[str],
    *,
    facts: Sequence[EvidenceFact],
) -> EvidenceRelation:
    """Compute one frozen-rule numeric relation with explicit fact lineage."""

    if rule not in _COMPUTE_RULES:
        raise ValidationError(f"unknown compute_statistic rule: {rule}")
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
    except ValueError as exc:
        raise ValidationError(
            "compute_statistic operands must be numeric facts"
        ) from exc
    if rule == "latest_minus_comparable_prior":
        value: float = left - right
    elif rule == "latest_over_latest":
        value = left / right
    else:
        value = left / right
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
        excerpt = document.content[:_NARRATIVE_EXCERPT_CHARS]
        tokens = set(re.findall(r"[a-z0-9]+", excerpt.casefold()))
        matched_terms.update(term for term in terms if term in tokens)
        events.append(
            NarrativeEvent(
                event_ref="event-" + _opaque_ref(
                    document.document_id, document.content_hash, len(excerpt)
                ),
                case_ref=ref,
                document_ref=f"document-{document.document_id}",
                excerpt=excerpt,
                content_hash=document.content_hash,
                available_at=document.available_at.isoformat(),
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
