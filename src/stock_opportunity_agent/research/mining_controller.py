"""Fixed-state label-aware mining controller over the lazy Evidence Graph.

Implements the contract in ``spec/src/stock_opportunity_agent/research/
signal_mining_agent.md``: one closed action enum, one deterministic state
machine, dual-dimension budgets, runtime-owned tool execution and mining
ledger, Seed A hypothesis validation with a need-disposition ledger, and Seed
B label-aware discovery whose labels arrive only through the runtime-owned
structured label map. The model decides actions; the runtime alone executes
tools, writes the ledger, enforces budgets, and admits candidates into the
unchanged validation pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    EvolutionCase,
    _evidence_source_family,
    _mask_identity_values,
)
from stock_opportunity_agent.research.mining_agent_tools import (
    EvidenceFact,
    EvidenceRelation,
    FetchResult,
    build_case_co_occurrence_relations,
    build_same_concept_relations,
    compute_statistic,
    fetch_case_evidence,
    narrative_catalog,
    project_attributes,
    strip_document_artifacts,
)

ACTIONS = (
    "inspect_manifest",
    "inspect_catalog",
    "fetch_evidence",
    "compute_statistic",
    "read_span",
    "compare_groups",
    "propose_candidate",
    "record_deferred",
    "record_no_pattern",
)
HEAVY_ACTIONS = frozenset(
    {
        "fetch_evidence",
        "compute_statistic",
        "read_span",
        "compare_groups",
        "propose_candidate",
    }
)
LIGHT_ACTIONS = frozenset({"inspect_manifest", "inspect_catalog"})

ALLOWED_DISPOSITIONS = frozenset(
    {
        "new_measurement",
        "deferred_measurement",
        "update_existing",
        "repair_dependency",
        "not_testable",
        "fast_plan_action",
    }
)
_TERMINAL_KINDS = frozenset(
    {
        "candidate",
        "no_pattern_with_coverage",
        "evidence_unavailable",
        "deferred_budget",
        "technical_failure",
    }
)
_STATE_ORDER = {
    "ready": 0,
    "exploring": 1,
    "evidence_ready": 2,
    "candidate_proposed": 3,
    "locally_validated": 4,
    "terminal": 5,
}
_MAX_STRUCTURED_CORRECTIONS = 3
_READ_SPAN_CONTEXT_CHARS = 200
_DEFAULT_BROWSE_LIMIT = 24
_NARRATIVE_FAMILIES = frozenset({"filing", "transcript", "news"})
_READ_BYTE_LIMIT = 4000
_CONCEPT_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{5,}")


def _ledger_text_hash(text: str) -> str:
    """Hash one verbatim window so replay can re-derive it from documents."""

    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class InvalidMiningAction(ValidationError):
    """One model action violated the closed contract; correction is bounded."""


class BudgetInadmissibleAction(InvalidMiningAction):
    """A heavy action requested after the heavy budget was exhausted.

    Budget exhaustion is a runtime-owned state, not a model contract fault:
    repeated inadmissible heavy actions end in a deterministic
    ``deferred_budget`` terminal with a resumable ledger instead of burning
    the structured-correction quota as a technical failure.
    """


@dataclass(frozen=True)
class LedgerEntry:
    """One runtime-owned mining-ledger row."""

    action_id: int
    action: str
    input_hash: str
    output_hash: str
    case_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    pit_status: str = "enforced"
    coverage: Mapping[str, Any] = field(default_factory=dict)
    omitted_coverage: Mapping[str, Any] = field(default_factory=dict)
    usage: Mapping[str, Any] = field(default_factory=dict)
    terminal_disposition: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action": self.action,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "case_refs": list(self.case_refs),
            "evidence_refs": list(self.evidence_refs),
            "source_types": list(self.source_types),
            "pit_status": self.pit_status,
            "coverage": dict(self.coverage),
            "omitted_coverage": dict(self.omitted_coverage),
            "usage": dict(self.usage),
            "terminal_disposition": self.terminal_disposition,
            "note": self.note,
        }


@dataclass(frozen=True)
class ControllerResult:
    """The controller's terminal outcome plus its complete ledger."""

    seed: str
    state: str
    terminal_kind: str
    candidates: tuple[Mapping[str, Any], ...]
    ledger: tuple[LedgerEntry, ...]
    need_dispositions: tuple[Mapping[str, Any], ...]
    model_calls: int
    narrative_reads: int = 0
    modality_coverage: Mapping[str, Any] = field(default_factory=dict)


class MiningLedger:
    """Append-only within one seed run; every entry is runtime-authored."""

    def __init__(self, *, cycle_id: int, seed_id: str) -> None:
        self.cycle_id = cycle_id
        self.seed_id = seed_id
        self._entries: list[LedgerEntry] = []

    def append(self, entry: LedgerEntry) -> None:
        if entry.action_id != len(self._entries) + 1:
            raise ValidationError("ledger entries must be append-only by id")
        self._entries.append(entry)

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def evidence_refs(self) -> set[str]:
        refs: set[str] = set()
        for entry in self._entries:
            refs.update(entry.evidence_refs)
        return refs

    def explored_families(self) -> tuple[str, ...]:
        families: set[str] = set()
        for entry in self._entries:
            families.update(entry.source_types)
        return tuple(sorted(families))

    def fetch_count(self) -> int:
        return sum(1 for entry in self._entries if entry.action == "fetch_evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "seed_id": self.seed_id,
            "entries": [entry.to_dict() for entry in self._entries],
        }


class LabelAwareMiningController:
    """Drive one mining seed as a fixed state machine over shared tools."""

    def __init__(
        self,
        *,
        store: RawInfoStore,
        model: Any,
        case_pairs: Sequence[tuple[str, EvolutionCase]],
        measurable_evidence_manifest: Mapping[str, Any],
        signal_catalog: Sequence[Mapping[str, Any]],
        seed: str,
        cycle_id: int = 1,
        backlog_needs: Sequence[Mapping[str, Any]] = (),
        heavy_action_limit: int = 12,
        light_action_limit: int = 4,
        browse_limit: int = _DEFAULT_BROWSE_LIMIT,
        attribute_vocabulary: Mapping[str, Any] | None = None,
        prior_modality_footprints: Sequence[Mapping[str, Any]] = (),
        validation_sink: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        identity_aliases: Sequence[str] = (),
    ) -> None:
        if seed not in {"hypothesis", "discovery"}:
            raise ValidationError("seed must be hypothesis or discovery")
        self.store = store
        self.model = model
        self.case_pairs = tuple(case_pairs)
        self.case_by_ref = {ref: case for ref, case in self.case_pairs}
        self.manifest = dict(measurable_evidence_manifest)
        self.signal_catalog = tuple(signal_catalog)
        self.seed = seed
        self.backlog_needs = tuple(backlog_needs)
        self.heavy_action_limit = heavy_action_limit
        self.light_action_limit = light_action_limit
        self.browse_limit = browse_limit
        self.attribute_vocabulary = dict(attribute_vocabulary or {})
        self.prior_modality_footprints = tuple(
            dict(row) for row in prior_modality_footprints
        )
        self._browse_used = 0
        self.validation_sink = validation_sink
        self.identity_aliases = tuple(identity_aliases)
        available: set[str] = set()
        cohort_companies = {case.company_id for _ref, case in self.case_pairs}
        for document in store.documents:
            if document.company_id in cohort_companies:
                available.add(document.source_type)
                available.add(_evidence_source_family(document.source_type))
        self.available_source_families = tuple(sorted(available))
        self.ledger = MiningLedger(cycle_id=cycle_id, seed_id=f"seed-{seed}")
        self._state = "ready"
        self._heavy_used = 0
        self._light_used = 0
        self._corrections = 0
        self._model_calls = 0
        self._facts: dict[str, EvidenceFact] = {}
        self._events: dict[str, Any] = {}
        self._relations: dict[str, EvidenceRelation] = {}
        self._documents: dict[str, Any] = {}
        self._last_read_span: str | None = None
        self._last_action_result: Mapping[str, Any] | None = None
        self._narrative_explored = False
        self._narrative_reads = 0
        self._last_invalid: Mapping[str, Any] | None = None
        self._label_map: dict[str, str] = {
            ref: ("positive" if case.ground_truth.is_surge else "control")
            for ref, case in self.case_pairs
        }

    # ------------------------------------------------------------------
    # Public entry
    def run(self) -> ControllerResult:
        terminal_kind = "technical_failure"
        candidates: list[Mapping[str, Any]] = []
        need_dispositions: tuple[Mapping[str, Any], ...] = ()
        budget_inadmissible_streak = 0
        while self._state != "terminal":
            view = self._model_view()
            action = ""
            raw: Mapping[str, Any] = {}
            try:
                raw = self._decide(view)
                action = str(raw.get("action", ""))
                self._validate_action_shape(raw)
                terminal_kind, candidates, need_dispositions = self._execute(
                    action, raw
                )
                self._corrections = 0
                self._last_invalid = None
                budget_inadmissible_streak = 0
            except BudgetInadmissibleAction as exc:
                self._record_invalid(action, raw, str(exc))
                self._last_invalid = {"action": action, "issue": str(exc)}
                budget_inadmissible_streak += 1
                if budget_inadmissible_streak >= 2:
                    self._mark_terminal(
                        "deferred_budget",
                        raw,
                        note=(
                            "heavy budget exhausted; model repeated an "
                            "inadmissible heavy action"
                        ),
                    )
                    terminal_kind = "deferred_budget"
            except (InvalidMiningAction, ValidationError) as exc:
                self._record_invalid(action, raw, str(exc))
                self._last_invalid = {"action": action, "issue": str(exc)}
                budget_inadmissible_streak = 0
                self._corrections += 1
                if self._corrections > _MAX_STRUCTURED_CORRECTIONS:
                    terminal_kind = "technical_failure"
                    self._state = "terminal"
        return ControllerResult(
            seed=self.seed,
            state=self._state,
            terminal_kind=terminal_kind,
            candidates=tuple(candidates),
            ledger=self.ledger.entries,
            need_dispositions=need_dispositions,
            model_calls=self._model_calls,
            narrative_reads=self._narrative_reads,
            modality_coverage=self._modality_coverage(),
        )

    # ------------------------------------------------------------------
    # Model boundary
    def _decide(self, view: Mapping[str, Any]) -> dict[str, Any]:
        self._model_calls += 1
        raw = self.model.next_action(dict(view))
        if not isinstance(raw, Mapping):
            raise InvalidMiningAction("model action must be a JSON object")
        return dict(raw)

    def _model_view(self) -> dict[str, Any]:
        view: dict[str, Any] = {
            "seed": self.seed,
            "state": self._state,
            "budget": {
                "heavy_remaining": self.heavy_action_limit - self._heavy_used,
                "light_remaining": self.light_action_limit - self._light_used,
                "browse_remaining": self.browse_limit - self._browse_used,
            },
            "actions": list(ACTIONS),
            "available_source_families": list(self.available_source_families),
            "measurable_evidence_manifest": self.manifest,
            "signal_catalog": [dict(card) for card in self.signal_catalog],
            "case_refs": [ref for ref, _case in self.case_pairs],
            "known_fact_refs": sorted(self._facts),
            "known_event_refs": sorted(self._events),
            "known_relation_refs": sorted(self._relations),
            "label_map": dict(self._label_map),
            "evidence_digest": self._evidence_digest(),
            "modality_coverage": self._modality_coverage(),
            "prior_modality_footprints": [
                dict(row) for row in self.prior_modality_footprints
            ],
        }
        if self._last_action_result is not None:
            view["last_action_result"] = dict(self._last_action_result)
        if self._last_read_span is not None:
            view["last_read_span"] = self._last_read_span
        if self._last_invalid is not None:
            view["last_invalid_action"] = dict(self._last_invalid)
        if self.seed == "hypothesis":
            view["backlog_needs"] = [dict(row) for row in self.backlog_needs]
        return view

    def _evidence_digest(self) -> dict[str, Any]:
        """Runtime-owned summary of what fetches have already collected."""

        concept_cases: dict[str, dict[str, set[str]]] = {}
        for fact in self._facts.values():
            groups = concept_cases.setdefault(
                fact.concept, {"positive": set(), "control": set()}
            )
            label = self._label_map.get(fact.case_ref, "control")
            groups[label if label in groups else "control"].add(fact.case_ref)
        concepts = {
            concept: {
                "positive_cases": len(groups["positive"]),
                "control_cases": len(groups["control"]),
            }
            for concept, groups in concept_cases.items()
        }
        label_counts = {"positive": 0, "control": 0}
        for label in self._label_map.values():
            label_counts[label] = label_counts.get(label, 0) + 1
        narrative_summary = self._narrative_summary()
        attribute_index: dict[str, Any] = {}
        if self.attribute_vocabulary:
            documents = [
                document
                for result in self._documents.values()
                for document in result.documents
            ]
            projected = project_attributes(
                documents,
                self._events.values(),
                vocabulary=self.attribute_vocabulary,
            )
            for name, rows in projected.items():
                by_case: dict[str, dict[str, set[str]]] = {}
                for row in rows:
                    case_ref = str(row.get("case_ref", ""))
                    if not case_ref:
                        continue
                    groups = by_case.setdefault(
                        case_ref, {"positive": set(), "control": set()}
                    )
                    label = self._label_map.get(case_ref, "control")
                    groups[label if label in groups else "control"].add(case_ref)
                positive_cases = {
                    case for case, g in by_case.items() if g["positive"]
                }
                control_cases = {
                    case for case, g in by_case.items() if g["control"]
                }
                amounts = [
                    row.get("amount_usd")
                    for row in rows
                    if row.get("amount_usd") is not None
                ]
                attribute_index[name] = {
                    "positive_cases": len(positive_cases),
                    "control_cases": len(control_cases),
                    "hits": len(rows),
                    "amount_usd_median": (
                        sorted(amounts)[len(amounts) // 2] if amounts else None
                    ),
                    "discovery_only": True,
                    "note": "index only; never sole evidence; a miss never "
                    "asserts absence",
                }
        return {
            "fetches": self.ledger.fetch_count(),
            "families_fetched": list(self.ledger.explored_families()),
            "fact_count": len(self._facts),
            "event_count": len(self._events),
            "relation_count": len(self._relations),
            "cases_with_facts": sorted({fact.case_ref for fact in self._facts.values()}),
            "concept_case_coverage": dict(
                sorted(
                    concepts.items(),
                    key=lambda item: (-item[1]["positive_cases"], item[0]),
                )
            ),
            "label_counts": label_counts,
            **({"narrative_summary": narrative_summary} if narrative_summary else {}),
            **(
                {"attribute_case_coverage": attribute_index}
                if attribute_index
                else {}
            ),
        }

    def _narrative_summary(self) -> dict[str, Any]:
        """Semantic surface for fetched narrative evidence.

        Raw event refs are opaque; without titles and per-family counts the
        decision view collapses back to the concept matrix even after a
        narrative-including fetch (V99 post-mortem). Titles are masked with
        the same identity inventory used everywhere else.
        """

        events = [
            event
            for event in self._events.values()
            if event.source_family in _NARRATIVE_FAMILIES
        ]
        if not events:
            return {}
        family_counts: dict[str, int] = {}
        for event in events:
            family_counts[event.source_family] = (
                family_counts.get(event.source_family, 0) + 1
            )
        # Real news headlines carry the semantic signal; filing metadata
        # titles (form + period) only orient. News first, filings fill.
        news_events = [
            event for event in events if event.source_family == "news"
        ]
        other_events = [
            event for event in events if event.source_family != "news"
        ]
        sample_titles: list[str] = []
        seen_titles: set[str] = set()
        for event in [*news_events, *other_events]:
            title = event.title.strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            sample_titles.append(
                str(
                    _mask_identity_values(
                        title, self.identity_aliases, expand_aliases=False
                    )
                )
            )
            if len(sample_titles) >= 8:
                break
        return {
            "event_count": len(events),
            "family_counts": dict(sorted(family_counts.items())),
            "sample_titles": sample_titles,
            "note": "inspect_catalog with scope=evidence lists every titled "
            "document by family and window; read_span on event_ref reads "
            "the verbatim text",
        }

    def _modality_coverage(self) -> dict[str, Any]:
        """Runtime-computed structured/narrative exploration coverage."""

        normalized_available = {
            _evidence_source_family(family)
            for family in self.available_source_families
        }
        structured_available = bool(
            normalized_available - _NARRATIVE_FAMILIES
        ) or bool(self.manifest.get("structured_financial_concepts")) or bool(
            self.manifest.get("pre_cutoff_price_series_cases")
        )
        narrative_available = bool(normalized_available & _NARRATIVE_FAMILIES)
        structured_explored = any(
            _evidence_source_family(family) not in _NARRATIVE_FAMILIES
            for family in self.ledger.explored_families()
        )
        narrative_status = "not_available"
        if narrative_available:
            if self._narrative_explored:
                narrative_status = "explored"
            else:
                narrative_status = "required"
        return {
            "structured": {
                "available": structured_available,
                "explored": structured_explored,
                "status": (
                    "not_available"
                    if not structured_available
                    else "explored"
                    if structured_explored
                    else "required"
                ),
            },
            "narrative": {
                "available": narrative_available,
                "explored": self._narrative_explored,
                "status": narrative_status,
            },
        }

    def _require_modality_obligation(self, action: str) -> None:
        """Domain terminals are inadmissible while a modality is unexplored.

        The obligation binds exploration opportunity, never candidate
        outcomes: control-plane terminals (record_deferred and its outcomes)
        remain admissible, and the correction names every legitimate path.
        """

        coverage = self._modality_coverage()
        missing = [
            modality
            for modality in ("structured", "narrative")
            if coverage[modality]["available"]
            and not coverage[modality]["explored"]
        ]
        if missing:
            raise InvalidMiningAction(
                f"{action} is inadmissible while available evidence modalities "
                f"remain unexplored ({', '.join(missing)}): fetch the missing "
                "structured or narrative families, read a narrative event/document "
                "via read_span, inspect the evidence catalog (inspect_catalog with "
                "scope=evidence), or take a control-plane terminal "
                "(record_deferred)"
            )

    # ------------------------------------------------------------------
    # Contract validation
    def _validate_action_shape(self, raw: Mapping[str, Any]) -> None:
        action = str(raw.get("action", ""))
        if action not in ACTIONS:
            raise InvalidMiningAction(f"unknown action: {action}")
        if "label" in raw or any(
            isinstance(value, Mapping) and "label" in value
            for value in raw.values()
            if isinstance(value, Mapping)
        ):
            raise InvalidMiningAction(
                "labels are runtime-owned; model-authored label fields are invalid"
            )
        rationale = raw.get("rationale")
        if (
            not isinstance(rationale, list)
            or not rationale
            or any(not isinstance(item, str) or not item.strip() for item in rationale)
        ):
            raise InvalidMiningAction(
                "rationale must be a non-empty array of short strings"
            )
        if action in HEAVY_ACTIONS and self._heavy_used >= self.heavy_action_limit:
            raise BudgetInadmissibleAction("heavy action budget exhausted")

    def _require_state_at_least(self, minimum: str, action: str) -> None:
        if _STATE_ORDER[self._state] < _STATE_ORDER[minimum]:
            raise InvalidMiningAction(
                f"{action} requires state {minimum}, currently {self._state}"
            )

    # ------------------------------------------------------------------
    # Execution
    def _execute(
        self, action: str, raw: Mapping[str, Any]
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        if action in ("inspect_manifest", "inspect_catalog"):
            self._light_used += 1
            if action == "inspect_manifest":
                payload = self.manifest
            else:
                scope = str(raw.get("scope", "signals"))
                if scope not in {"signals", "evidence"}:
                    raise InvalidMiningAction(
                        "inspect_catalog scope must be signals or evidence"
                    )
                if scope == "evidence":
                    payload = {"families": self._evidence_catalog_view()}
                    self._narrative_explored = True
                else:
                    payload = self._catalog_view()
            self._last_action_result = {
                "action": action,
                "inspected": sorted(payload),
            }
            self._append(
                action,
                raw,
                payload={"inspected": action},
                coverage={"keys": sorted(payload)},
            )
            self._advance("exploring")
            return "running", [], ()
        if action == "fetch_evidence":
            return "running", [], self._execute_fetch(raw)
        if action == "compute_statistic":
            return self._execute_compute(raw)
        if action == "read_span":
            return self._execute_read_span(raw)
        if action == "compare_groups":
            return self._execute_compare(raw)
        if action == "propose_candidate":
            return self._execute_propose(raw)
        if action == "record_deferred":
            kind = (
                "deferred_budget"
                if self._budget_exhausted()
                else "evidence_unavailable"
            )
            self._mark_terminal(kind, raw, note="record_deferred")
            return kind, [], ()
        if action == "record_no_pattern":
            self._execute_no_pattern(raw)
            return "no_pattern_with_coverage", [], ()
        raise InvalidMiningAction(f"unhandled action: {action}")

    def _budget_exhausted(self) -> bool:
        return self._heavy_used >= self.heavy_action_limit

    def _execute_fetch(self, raw: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        case_refs = raw.get("case_refs")
        families = raw.get("source_families")
        if (
            not isinstance(case_refs, list)
            or not case_refs
            or not isinstance(families, list)
            or not families
            or any(str(ref) not in self.case_by_ref for ref in case_refs)
        ):
            raise InvalidMiningAction(
                "fetch_evidence requires non-empty known case_refs and source_families"
            )
        unknown_families = sorted(
            {
                str(family)
                for family in families
                if str(family) not in self.available_source_families
            }
        )
        if unknown_families:
            raise InvalidMiningAction(
                "fetch_evidence source_families must come from "
                "available_source_families in the view; unknown: "
                + ", ".join(unknown_families)
            )
        max_documents = raw.get("max_documents", 3)
        if not isinstance(max_documents, int) or max_documents < 1:
            raise InvalidMiningAction("max_documents must be a positive integer")
        query = raw.get("query")
        if query is not None and not isinstance(query, str):
            raise InvalidMiningAction("query must be a string or null")
        self._advance("exploring")
        results: list[FetchResult] = []
        for ref in case_refs:
            result = fetch_case_evidence(
                self.store,
                self.case_by_ref[str(ref)],
                source_families=tuple(str(item) for item in families),
                query=query,
                max_documents=max_documents,
                case_ref=str(ref),
            )
            results.append(result)
            for fact in result.facts:
                self._facts[fact.fact_ref] = fact
            for event in result.narrative_events:
                self._events[event.event_ref] = event
                self._documents[event.event_ref] = result
            for document in result.documents:
                self._documents[f"document-{document.document_id}"] = result
        evidence_refs: list[str] = []
        source_types: set[str] = set()
        coverage: dict[str, Any] = {}
        omitted: dict[str, Any] = {}
        for result in results:
            evidence_refs.extend(fact.fact_ref for fact in result.facts)
            evidence_refs.extend(
                event.event_ref for event in result.narrative_events
            )
            source_types.update(
                str(document.source_type) for document in result.documents
            )
            coverage.update(
                {
                    "query_coverage": dict(result.query_coverage),
                    "unread_same_source": result.unread_same_source,
                }
            )
            omitted.update(
                {"excluded_document_ids": list(result.excluded_by_limits)}
            )
        self._heavy_used += 1
        if any(
            _evidence_source_family(document.source_type) in _NARRATIVE_FAMILIES
            for result in results
            for document in result.documents
        ):
            self._narrative_explored = True
        self._advance("evidence_ready")
        new_relations = {
            relation.relation_ref: relation
            for relation in (
                *build_same_concept_relations(list(self._facts.values())),
                *build_case_co_occurrence_relations(
                    list(self._facts.values()), limit=64
                ),
            )
        }
        self._relations.update(new_relations)
        narrative_events = [
            event
            for event in self._events.values()
            if event.source_family in _NARRATIVE_FAMILIES
        ]
        sample_titles: list[str] = []
        for event in sorted(narrative_events, key=lambda item: item.available_at):
            title = str(
                _mask_identity_values(
                    event.title.strip(), self.identity_aliases, expand_aliases=False
                )
            )
            if title and title not in sample_titles:
                sample_titles.append(title)
            if len(sample_titles) >= 3:
                break
        self._last_action_result = {
            "action": "fetch_evidence",
            "cases_requested": len(case_refs),
            "families": sorted(source_types),
            "new_facts": len(evidence_refs)
            - sum(1 for ref in evidence_refs if ref.startswith("relation-")),
            "total_facts": len(self._facts),
            "total_events": len(self._events),
            "new_relations": len(new_relations),
            "total_relations": len(self._relations),
            "excluded_document_ids": len(
                omitted.get("excluded_document_ids", ())
            ),
            "narrative_evidence": {
                "events": len(narrative_events),
                "sample_titles": sample_titles,
                "catalog_note": (
                    "the evidence catalog now lists every titled document "
                    "by family and window (inspect_catalog scope=evidence)"
                ),
            }
            if narrative_events
            else None,
        }
        self._append(
            "fetch_evidence",
            raw,
            payload={
                "fact_refs": sorted(
                    fact.fact_ref for fact in self._facts.values()
                ),
                "relation_refs": sorted(new_relations),
            },
            case_refs=tuple(str(ref) for ref in case_refs),
            evidence_refs=tuple(
                [*evidence_refs, *sorted(new_relations)]
            ),
            source_types=tuple(sorted(source_types)),
            coverage=coverage,
            omitted_coverage=omitted,
        )
        return ()

    def _execute_compute(
        self, raw: Mapping[str, Any]
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        self._require_state_at_least("evidence_ready", "compute_statistic")
        rule = str(raw.get("rule", ""))
        fact_refs = raw.get("fact_refs")
        if not isinstance(fact_refs, list) or len(fact_refs) != 2:
            raise InvalidMiningAction("compute_statistic requires two fact_refs")
        relation = compute_statistic(
            rule,
            [str(ref) for ref in fact_refs],
            facts=tuple(self._facts.values()),
        )
        self._relations[relation.relation_ref] = relation
        self._last_action_result = {
            "action": "compute_statistic",
            "rule": rule,
            "relation_ref": relation.relation_ref,
            "value": relation.value,
            "fact_refs": list(relation.fact_refs),
        }
        self._append(
            "compute_statistic",
            raw,
            payload={"relation": relation.relation_ref, "value": relation.value},
            evidence_refs=(relation.relation_ref, *relation.fact_refs),
        )
        self._heavy_used += 1
        return "running", [], ()

    def _execute_read_span(
        self, raw: Mapping[str, Any]
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        self._require_state_at_least("evidence_ready", "read_span")
        targets = [key for key in ("fact_ref", "event_ref", "document_ref") if raw.get(key)]
        if len(targets) != 1:
            raise InvalidMiningAction(
                "read_span requires exactly one of fact_ref, event_ref, or "
                "document_ref"
            )
        if targets[0] == "fact_ref":
            return self._read_fact_span(raw)
        return self._read_narrative_span(raw, targets[0])

    def _read_narrative_span(
        self, raw: Mapping[str, Any], target_key: str
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        """Read a bounded verbatim window of one event or document.

        Budget dimension is the target class: event/document reads charge the
        browse budget (never heavy), the window is masked for the model while
        the ledger keeps the verbatim slice for replay, and event_ref identity
        stays stable across paginated reads.
        """

        if self._browse_used >= self.browse_limit:
            raise BudgetInadmissibleAction("browse budget exhausted")
        target_ref = str(raw.get(target_key, ""))
        offset = raw.get("offset", 0)
        length = raw.get("length", 1200)
        if not isinstance(offset, int) or offset < 0:
            raise InvalidMiningAction("read_span offset must be a non-negative int")
        if not isinstance(length, int) or length < 1 or length > _READ_BYTE_LIMIT:
            raise InvalidMiningAction(
                f"read_span length must be between 1 and {_READ_BYTE_LIMIT}"
            )
        document_ref = target_ref
        event = None
        if target_key == "event_ref":
            event = self._events.get(target_ref)
            if event is None:
                raise InvalidMiningAction(
                    "read_span requires a known event_ref"
                )
            document_ref = event.document_ref
        document = self._document_by_ref(document_ref)
        if document is None:
            raise InvalidMiningAction(
                "read_span requires a fetched document_ref"
            )
        window = document.content[offset : offset + length]
        if not window:
            raise InvalidMiningAction(
                "read_span window is empty; adjust offset/length within the "
                "document bounds"
            )
        masked = strip_document_artifacts(
            str(
                _mask_identity_values(
                    window, self.identity_aliases, expand_aliases=False
                )
            )
        )
        entry: dict[str, Any] = {
            "target": target_key,
            "ref": target_ref,
            "document_ref": document_ref,
            "offset": offset,
            "length": length,
            "masked": masked,
            "verbatim_hash": _ledger_text_hash(window),
        }
        if event is not None:
            entry["title"] = event.title
            entry["source_family"] = event.source_family
            entry["available_at"] = event.available_at
            self._last_read_span = masked
        self._last_action_result = {"action": "read_span", **dict(entry)}
        self._append(
            "read_span",
            raw,
            payload=entry,
            evidence_refs=(
                (target_ref,) if target_key == "event_ref" else (document_ref,)
            ),
        )
        if (
            _evidence_source_family(document.source_type) in _NARRATIVE_FAMILIES
        ):
            self._narrative_explored = True
        self._narrative_reads += 1
        self._browse_used += 1
        return "running", [], ()

    def _document_by_ref(self, document_ref: str):
        for result in self._documents.values():
            for document in result.documents:
                if f"document-{document.document_id}" == document_ref:
                    return document
        return None

    def _read_fact_span(
        self, raw: Mapping[str, Any]
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        fact_ref = str(raw.get("fact_ref", ""))
        fact = self._facts.get(fact_ref)
        if fact is None:
            raise InvalidMiningAction("read_span requires a known fact_ref")
        context = fact.exact_span
        for document_ref, result in self._documents.items():
            for document in result.documents:
                if f"document-{document.document_id}" != fact.document_ref:
                    continue
                start = document.content.find(fact.exact_span)
                if start >= 0:
                    left = max(0, start - _READ_SPAN_CONTEXT_CHARS)
                    right = min(
                        len(document.content),
                        start + len(fact.exact_span) + _READ_SPAN_CONTEXT_CHARS,
                    )
                    context = document.content[left:right]
        masked = _mask_identity_values(
            context, self.identity_aliases, expand_aliases=False
        )
        self._last_read_span = masked
        self._append(
            "read_span",
            raw,
            payload={
                "fact_ref": fact_ref,
                "context_chars": len(masked),
                "masked": masked,
            },
            evidence_refs=(fact_ref,),
        )
        self._heavy_used += 1
        return "running", [], ()

    def _execute_compare(
        self, raw: Mapping[str, Any]
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        self._require_state_at_least("evidence_ready", "compare_groups")
        concepts = raw.get("concepts")
        if not isinstance(concepts, list) or not concepts:
            raise InvalidMiningAction("compare_groups requires non-empty concepts")
        summary = self._group_summary(tuple(str(item) for item in concepts))
        self._last_action_result = {
            "action": "compare_groups",
            "groups": summary,
        }
        self._append(
            "compare_groups",
            raw,
            payload=summary,
            coverage={"groups": sorted(summary)},
            evidence_refs=tuple(
                fact.fact_ref for fact in self._facts.values()
                if fact.concept in {str(item) for item in concepts}
            ),
        )
        self._heavy_used += 1
        return "running", [], ()

    def _group_summary(self, concepts: Sequence[str]) -> dict[str, Any]:
        wanted = set(concepts)
        rows: dict[str, dict[str, Any]] = {}
        for group in ("positive", "control"):
            group_refs = {
                ref for ref, label in self._label_map.items() if label == group
            }
            facts = [
                fact
                for fact in self._facts.values()
                if fact.concept in wanted and fact.case_ref in group_refs
            ]
            by_concept: dict[str, dict[str, Any]] = {}
            for concept in sorted(wanted):
                concept_facts = [
                    fact for fact in facts if fact.concept == concept
                ]
                by_concept[concept] = {
                    "available_cases": sorted(
                        {fact.case_ref for fact in concept_facts}
                    ),
                    "latest": {
                        fact.case_ref: {
                            "value": fact.value,
                            "fact_ref": fact.fact_ref,
                        }
                        for fact in concept_facts
                        if fact.record_selection == "latest"
                    },
                    "comparable_prior": {
                        fact.case_ref: {
                            "value": fact.value,
                            "fact_ref": fact.fact_ref,
                        }
                        for fact in concept_facts
                        if fact.record_selection == "comparable_prior"
                    },
                }
            rows[group] = {"case_count": len(group_refs), "concepts": by_concept}
        return rows

    def _execute_propose(
        self, raw: Mapping[str, Any]
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        self._require_state_at_least("evidence_ready", "propose_candidate")
        self._require_modality_obligation("propose_candidate")
        if self.ledger.fetch_count() < 1:
            raise InvalidMiningAction(
                "a candidate requires at least one completed evidence fetch"
            )
        candidate = raw.get("candidate")
        if not isinstance(candidate, Mapping):
            raise InvalidMiningAction("candidate must be an object")
        measurement = candidate.get("measurement")
        allowed_keys = {"observable", "value_kind", "normalization"}
        if (
            not isinstance(measurement, Mapping)
            or not allowed_keys <= set(measurement)
            or not set(measurement) <= allowed_keys | {"predicate"}
            or any(
                not str(measurement[k]).strip() for k in measurement
                if k != "predicate"
            )
        ):
            raise InvalidMiningAction(
                "candidate measurement requires exactly observable, "
                "value_kind, and normalization (plus an optional predicate)"
            )
        predicate = measurement.get("predicate")
        if predicate is not None and not isinstance(predicate, Mapping):
            raise InvalidMiningAction(
                "measurement predicate must be an object"
            )
        if measurement["value_kind"] not in {
            "boolean",
            "ordinal",
            "numeric",
            "categorical",
        }:
            raise InvalidMiningAction(
                "candidate measurement value_kind must be exactly one of "
                "boolean, ordinal, numeric, categorical (a ratio is numeric)"
            )
        observable = str(measurement["observable"])
        catalog_names = {
            str(card.get("signal_ref", "")).split(":")[0]
            for card in self.signal_catalog
            if str(card.get("signal_ref", "")).strip()
        }
        proposed_base = observable.split(":")[0].strip()
        if proposed_base and proposed_base in catalog_names:
            raise InvalidMiningAction(
                "candidate observable duplicates the existing Signal "
                f"{proposed_base}; changing an existing Signal belongs to the "
                "Update path, so propose a genuinely new measurement instead"
            )
        falsifiers = candidate.get("falsifiers")
        if (
            not isinstance(falsifiers, list)
            or not falsifiers
            or any(
                not isinstance(item, Mapping)
                or set(item) != {"condition", "expected_observation"}
                for item in falsifiers
            )
        ):
            raise InvalidMiningAction("candidate requires executable falsifiers")
        evidence_refs = candidate.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise InvalidMiningAction("candidate requires evidence_refs")
        known = self.ledger.evidence_refs()
        unknown = sorted(set(str(ref) for ref in evidence_refs) - known)
        if unknown:
            raise InvalidMiningAction(
                "candidate cites evidence outside the ledger: "
                + ", ".join(unknown)
            )
        cited_set = set(str(ref) for ref in evidence_refs)
        if predicate is not None:
            self._validate_narrative_predicate(predicate, cited_set)
        cited_fact_concepts = {
            fact.concept
            for fact in self._facts.values()
            if fact.fact_ref in cited_set
        }
        text = " ".join(
            (str(measurement["observable"]), str(measurement["normalization"]))
        )
        named_concepts = sorted(
            {
                token
                for token in _CONCEPT_TOKEN_RE.findall(text)
                if token in {fact.concept for fact in self._facts.values()}
            }
        )
        unsupported = [
            concept for concept in named_concepts
            if concept not in cited_fact_concepts
        ]
        if unsupported:
            raise InvalidMiningAction(
                "measurement names concepts the cited evidence does not "
                "cover: " + ", ".join(unsupported)
            )
        need_dispositions: tuple[Mapping[str, Any], ...] = ()
        if self.seed == "hypothesis":
            need_dispositions = self._validate_need_dispositions(raw)
        self._append(
            "propose_candidate",
            raw,
            payload={"observable": measurement["observable"]},
            evidence_refs=tuple(str(ref) for ref in evidence_refs),
            terminal_disposition="candidate_proposed",
        )
        self._heavy_used += 1
        self._advance("candidate_proposed")
        sink_result: Mapping[str, Any] = {"status": "validated"}
        if self.validation_sink is not None:
            sink_result = self.validation_sink(dict(candidate))
        status = str(sink_result.get("status", "validated"))
        if status not in {"validated", "rejected"}:
            raise ValidationError("validation sink returned an invalid status")
        self._append(
            "validate_candidate",
            {"action": "validate_candidate", "rationale": list(raw.get("rationale", ()))},
            payload={"status": status},
            evidence_refs=tuple(str(ref) for ref in evidence_refs),
            terminal_disposition="locally_validated" if status == "validated" else "rejected",
        )
        self._state = "terminal"
        terminal_kind = "candidate" if status == "validated" else "rejected"
        return terminal_kind, [dict(candidate)], need_dispositions

    def _validate_narrative_predicate(
        self, predicate: Mapping[str, Any], cited_refs: set[str]
    ) -> None:
        """Mechanical grounding checks for a narrative measurement predicate.

        Existence, family intersection, and raw-narrative citation are
        runtime-checkable here; semantic satisfaction is judged only
        downstream by fixtures, holdout, and the paired gates.
        """

        required = {"modality", "source_families", "semantic_condition"}
        if not required <= set(predicate):
            raise InvalidMiningAction(
                "predicate requires modality, source_families, and "
                "semantic_condition"
            )
        if str(predicate["modality"]) != "narrative":
            raise InvalidMiningAction(
                "predicate modality must be narrative"
            )
        families = predicate.get("source_families")
        if not isinstance(families, list) or not families:
            raise InvalidMiningAction(
                "predicate source_families must be a non-empty array"
            )
        predicate_families = {
            str(family) for family in families
        }
        cited_events = [
            self._events[ref] for ref in cited_refs if ref in self._events
        ]
        cited_document_families = set()
        for ref in cited_refs:
            if ref.startswith("document-"):
                document = self._document_by_ref(ref)
                if document is not None:
                    family = _evidence_source_family(document.source_type)
                    if family in _NARRATIVE_FAMILIES:
                        cited_document_families.add(family)
        if not cited_events and not cited_document_families:
            raise InvalidMiningAction(
                "a narrative predicate requires at least one cited raw "
                "narrative ref (event or document read)"
            )
        event_families = {
            event.source_family for event in cited_events
        } | cited_document_families
        if not predicate_families & event_families:
            raise InvalidMiningAction(
                "predicate source_families do not intersect the cited "
                f"narrative evidence families ({sorted(event_families)})"
            )
        threshold = predicate.get("threshold")
        if threshold is not None and (
            not isinstance(threshold, Mapping)
            or not {"field", "operator", "value"} <= set(threshold)
            or str(threshold.get("operator", "")) not in {">=", ">", "<=", "<", "=="}
        ):
            raise InvalidMiningAction(
                "predicate threshold requires field, operator "
                "(>=, >, <=, <, ==), and value"
            )
        lookback = predicate.get("lookback_days")
        if lookback is not None and (
            not isinstance(lookback, int) or lookback < 1
        ):
            raise InvalidMiningAction(
                "predicate lookback_days must be a positive integer"
            )

    def _validate_need_dispositions(
        self, raw: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any], ...]:
        rows = raw.get("need_dispositions")
        if not isinstance(rows, list):
            raise InvalidMiningAction(
                "hypothesis seed terminal requires need_dispositions"
            )
        known_refs = {
            str(row.get("need_ref"))
            for row in self.backlog_needs
            if isinstance(row, Mapping)
        }
        seen: set[str] = set()
        clean: list[Mapping[str, Any]] = []
        row_issues: list[str] = []
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping) or set(row) != {
                "need_refs",
                "disposition",
                "signal_refs",
                "rationale",
            }:
                row_issues.append(
                    f"row[{index}] requires exactly need_refs, disposition, "
                    "signal_refs, rationale"
                )
                continue
            refs = row["need_refs"]
            if not isinstance(refs, list) or not refs:
                row_issues.append(f"row[{index}] need_refs must be non-empty")
                continue
            disposition = row["disposition"]
            if disposition not in ALLOWED_DISPOSITIONS:
                row_issues.append(
                    f"row[{index}] disposition must be one of "
                    + ", ".join(sorted(ALLOWED_DISPOSITIONS))
                )
                continue
            signal_refs = row["signal_refs"]
            if not isinstance(signal_refs, list):
                row_issues.append(f"row[{index}] signal_refs must be an array")
                continue
            if disposition in {"update_existing", "already_covered"}:
                if len(signal_refs) != 1:
                    row_issues.append(
                        f"row[{index}] {disposition} cites exactly one signal"
                    )
                    continue
            elif signal_refs:
                row_issues.append(
                    f"row[{index}] {disposition} must cite no signal_refs; "
                    "only update_existing cites exactly one existing signal"
                )
                continue
            duplicates = sorted(
                {str(ref) for ref in refs if str(ref) in seen}
            )
            if duplicates:
                row_issues.append(
                    f"row[{index}] repeats needs: " + ", ".join(duplicates)
                )
                continue
            for ref in refs:
                seen.add(str(ref))
            clean.append(dict(row))
        if row_issues:
            raise InvalidMiningAction(
                "need_dispositions issues: " + "; ".join(row_issues)
            )
        missing = sorted(known_refs - seen)
        if missing:
            raise InvalidMiningAction(
                "need_dispositions must cover every backlog need: missing "
                + ", ".join(missing)
            )
        unknown = sorted(seen - known_refs)
        if unknown:
            raise InvalidMiningAction(
                "need_dispositions cite unknown needs: " + ", ".join(unknown)
            )
        return tuple(clean)

    def _execute_no_pattern(self, raw: Mapping[str, Any]) -> None:
        if self.ledger.fetch_count() < 1:
            raise InvalidMiningAction(
                "no_pattern requires at least one completed evidence fetch"
            )
        self._require_modality_obligation("record_no_pattern")
        coverage = raw.get("coverage")
        if not isinstance(coverage, Mapping):
            raise InvalidMiningAction("record_no_pattern requires coverage")
        families = tuple(sorted(self.ledger.explored_families()))
        claimed = tuple(str(item) for item in coverage.get("explored_families", ()))
        if not claimed or set(claimed) - set(families):
            raise InvalidMiningAction(
                "no_pattern coverage must cite ledger-explored families"
            )
        self._append(
            "record_no_pattern",
            raw,
            payload={"coverage": dict(coverage)},
            coverage={"explored_families": list(families)},
            terminal_disposition="no_pattern_with_coverage",
        )
        self._state = "terminal"

    # ------------------------------------------------------------------
    # Ledger and state helpers
    def _append(
        self,
        action: str,
        raw: Mapping[str, Any],
        *,
        payload: Mapping[str, Any],
        case_refs: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        source_types: tuple[str, ...] = (),
        coverage: Mapping[str, Any] | None = None,
        omitted_coverage: Mapping[str, Any] | None = None,
        terminal_disposition: str | None = None,
        note: str | None = None,
    ) -> None:
        self.ledger.append(
            LedgerEntry(
                action_id=len(self.ledger.entries) + 1,
                action=action,
                input_hash=canonical_json_hash(
                    {"action": action, "args": _action_arguments(raw)}
                ),
                output_hash=canonical_json_hash(dict(payload)),
                case_refs=case_refs,
                evidence_refs=evidence_refs,
                source_types=source_types,
                coverage=dict(coverage or {}),
                omitted_coverage=dict(omitted_coverage or {}),
                usage={"model_calls": self._model_calls},
                terminal_disposition=terminal_disposition,
                note=note,
            )
        )

    def _record_invalid(
        self, action: str, raw: Mapping[str, Any], issue: str
    ) -> None:
        self.ledger.append(
            LedgerEntry(
                action_id=len(self.ledger.entries) + 1,
                action=action or "invalid",
                input_hash=canonical_json_hash(
                    {"action": action, "args": _action_arguments(raw)}
                ),
                output_hash=canonical_json_hash({"invalid": issue}),
                usage={"model_calls": self._model_calls},
                note=f"invalid_action: {issue}",
            )
        )

    def _mark_terminal(
        self,
        kind: str,
        raw: Mapping[str, Any],
        *,
        note: str,
        coverage: Mapping[str, Any] | None = None,
    ) -> None:
        if kind not in _TERMINAL_KINDS and kind not in {"deferred"}:
            raise ValidationError(f"unknown terminal kind: {kind}")
        self._append(
            "record_deferred",
            raw,
            payload={"kind": kind},
            coverage=dict(coverage or {}),
            terminal_disposition=kind,
            note=note,
        )
        self._state = "terminal"

    def _advance(self, target: str) -> None:
        if _STATE_ORDER[target] > _STATE_ORDER[self._state]:
            self._state = target

    def _evidence_catalog_view(self) -> list[dict[str, Any]]:
        """Discovery-only directory over the fetched narrative evidence."""

        documents = [
            document
            for result in self._documents.values()
            for document in result.documents
        ]
        return narrative_catalog(
            documents,
            self._events.values(),
        )

    def _catalog_view(self) -> dict[str, Any]:
        return {
            "signals": [
                {
                    "signal_ref": str(card.get("signal_ref", "")),
                    "description": str(card.get("description", "")),
                }
                for card in self.signal_catalog
            ]
        }


def _action_arguments(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in raw.items()
        if key not in {"rationale"} and isinstance(
            value, (str, int, float, bool, list, dict, type(None))
        )
    }
