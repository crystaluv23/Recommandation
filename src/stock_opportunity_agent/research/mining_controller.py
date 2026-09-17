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
_MAX_STRUCTURED_CORRECTIONS = 2
_READ_SPAN_CONTEXT_CHARS = 200


class InvalidMiningAction(ValidationError):
    """One model action violated the closed contract; correction is bounded."""


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
        self.validation_sink = validation_sink
        self.identity_aliases = tuple(identity_aliases)
        self.ledger = MiningLedger(cycle_id=cycle_id, seed_id=f"seed-{seed}")
        self._state = "ready"
        self._heavy_used = 0
        self._light_used = 0
        self._corrections = 0
        self._model_calls = 0
        self._facts: dict[str, EvidenceFact] = {}
        self._relations: dict[str, EvidenceRelation] = {}
        self._documents: dict[str, Any] = {}
        self._last_read_span: str | None = None
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
            except (InvalidMiningAction, ValidationError) as exc:
                self._record_invalid(action, raw, str(exc))
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
            },
            "actions": list(ACTIONS),
            "measurable_evidence_manifest": self.manifest,
            "signal_catalog": [dict(card) for card in self.signal_catalog],
            "case_refs": [ref for ref, _case in self.case_pairs],
            "known_fact_refs": sorted(self._facts),
            "known_relation_refs": sorted(self._relations),
            "label_map": dict(self._label_map),
        }
        if self._last_read_span is not None:
            view["last_read_span"] = self._last_read_span
        if self.seed == "hypothesis":
            view["backlog_needs"] = [dict(row) for row in self.backlog_needs]
        return view

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
            raise InvalidMiningAction("heavy action budget exhausted")

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
            payload = (
                self.manifest if action == "inspect_manifest" else self._catalog_view()
            )
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
        self._append(
            "fetch_evidence",
            raw,
            payload={
                "fact_refs": sorted(
                    fact.fact_ref for fact in self._facts.values()
                ),
            },
            case_refs=tuple(str(ref) for ref in case_refs),
            evidence_refs=tuple(evidence_refs),
            source_types=tuple(sorted(source_types)),
            coverage=coverage,
            omitted_coverage=omitted,
        )
        self._heavy_used += 1
        self._advance("evidence_ready")
        self._relations.update(
            {r.relation_ref: r for r in build_same_concept_relations(list(self._facts.values()))}
        )
        self._relations.update(
            {
                r.relation_ref: r
                for r in build_case_co_occurrence_relations(
                    list(self._facts.values()), limit=64
                )
            }
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
                    "latest_values": {
                        fact.case_ref: fact.value
                        for fact in concept_facts
                        if fact.record_selection == "latest"
                    },
                }
            rows[group] = {"case_count": len(group_refs), "concepts": by_concept}
        return rows

    def _execute_propose(
        self, raw: Mapping[str, Any]
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        self._require_state_at_least("evidence_ready", "propose_candidate")
        if self.ledger.fetch_count() < 1:
            raise InvalidMiningAction(
                "a candidate requires at least one completed evidence fetch"
            )
        candidate = raw.get("candidate")
        if not isinstance(candidate, Mapping):
            raise InvalidMiningAction("candidate must be an object")
        measurement = candidate.get("measurement")
        if (
            not isinstance(measurement, Mapping)
            or set(measurement) != {"observable", "value_kind", "normalization"}
            or any(not str(measurement[k]).strip() for k in measurement)
            or measurement["value_kind"]
            not in {"boolean", "ordinal", "numeric", "categorical"}
        ):
            raise InvalidMiningAction(
                "candidate measurement requires observable, value_kind, normalization"
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
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {
                "need_refs",
                "disposition",
                "signal_refs",
                "rationale",
            }:
                raise InvalidMiningAction(
                    "need_dispositions rows require need_refs, disposition, "
                    "signal_refs, rationale"
                )
            refs = row["need_refs"]
            if not isinstance(refs, list) or not refs:
                raise InvalidMiningAction("need_dispositions need_refs required")
            disposition = row["disposition"]
            if disposition not in ALLOWED_DISPOSITIONS:
                raise InvalidMiningAction(
                    f"unknown disposition: {disposition}"
                )
            signal_refs = row["signal_refs"]
            if not isinstance(signal_refs, list):
                raise InvalidMiningAction("signal_refs must be an array")
            if disposition in {"update_existing", "already_covered"}:
                if len(signal_refs) != 1:
                    raise InvalidMiningAction(
                        f"{disposition} cites exactly one stable signal"
                    )
            elif signal_refs:
                raise InvalidMiningAction(
                    f"{disposition} cites no signal"
                )
            for ref in refs:
                ref = str(ref)
                if ref in seen:
                    raise InvalidMiningAction(
                        f"need {ref} is dispositioned more than once"
                    )
                seen.add(ref)
            clean.append(dict(row))
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
