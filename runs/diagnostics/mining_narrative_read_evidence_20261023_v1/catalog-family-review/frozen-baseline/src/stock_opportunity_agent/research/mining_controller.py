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
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.disclosure import raw_span_view
from stock_opportunity_agent.data.markup import visible_html_ranges
from stock_opportunity_agent.data.resolution import _MARKUP_SOURCE_TYPES
from stock_opportunity_agent.models import StructuredValidationError, ValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from stock_opportunity_agent.research.evolution_output_validation import _validation_obligations
from stock_opportunity_agent.research.evolution_state_patch import apply_state_patch, state_patch_contract
from stock_opportunity_agent.research.repair import mechanical_repair_candidate
from stock_opportunity_agent.research.evolution_core import (
    EvolutionCase,
    _evidence_source_family,
    _mask_identity_values,
    _opaque_slow_case_ref,
)
from stock_opportunity_agent.research.stage_contracts import (
    NEED_ROW_RATIONALE_CONTRACT, bounded_entry_page, budget_claim_issues, json_bytes, read_whole_entries,
)
from stock_opportunity_agent.research.mining_agent_tools import (
    COMPUTE_RULES,
    EvidenceFact,
    EvidenceRelation,
    FetchResult,
    build_case_co_occurrence_relations,
    build_same_concept_relations,
    _unique_latest_fact,
    _unique_period_pair,
    compute_statistic,
    fetch_case_evidence,
    narrative_catalog,
    project_attributes,
    _events_by_document,
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
    "record_need_dispositions",
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
_CATALOG_SCOPE_BUDGETS = {
    "signals": "light", "evidence": "light", "memory": "browse", "backlog": "light",
}

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
    staged_need_dispositions: tuple[Mapping[str, Any], ...] = ()
    pending_need_refs: tuple[str, ...] = ()


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
        """Count executed fetches, excluding historical invalid-action rows."""
        return sum(1 for entry in self._entries if entry.action == "fetch_evidence"
                   and not str(entry.note or "").startswith("invalid_action:"))

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
        label_map: Mapping[str, str] | None = None,
        research_axis: Mapping[str, Any] | None = None,
        meta_memory_briefs: Mapping[str, Any] | None = None,
        meta_memory_disclosures: Sequence[Mapping[str, Any]] = (),
        need_progress_sink: Callable[[Mapping[str, Any]], None] | None = None,
        signal_originals: Mapping[str, Mapping[str, Any]] | None = None,
        memory_index: ReflectionMemoryIndex | None = None,
        slow_method_memory: Mapping[str, Any] | None = None,
    ) -> None:
        if seed not in {"hypothesis", "discovery"}:
            raise ValidationError("seed must be hypothesis or discovery")
        self.store = store
        self.model = model
        self.case_pairs = tuple(case_pairs)
        self.case_by_ref = {ref: case for ref, case in self.case_pairs}
        self._source_case_refs = {_opaque_slow_case_ref(case.case_id): ref for ref, case in self.case_pairs}
        self.manifest = dict(measurable_evidence_manifest)
        self.signal_catalog = tuple(signal_catalog)
        self._signal_originals = deepcopy(dict(signal_originals or {}))
        self._signal_hashes = {ref: canonical_json_hash(original) for ref, original in self._signal_originals.items()}
        self._signal_read_entries: dict[str, dict[str, Any]] = {}
        known_signals = {str(card.get("signal_ref", "")) for card in self.signal_catalog}
        if not set(self._signal_originals) <= known_signals:
            raise ValidationError("Signal originals must belong to the supplied catalog")
        enriched = []
        for card in self.signal_catalog:
            ref = str(card.get("signal_ref", ""))
            original = self._signal_originals.get(ref)
            projected = dict(card)
            projected["original_available"] = original is not None
            if original is not None:
                spec, skill = original.get("spec"), original.get("skill")
                if (not isinstance(spec, Mapping)
                    or f"{spec.get('signal_id')}:v{spec.get('version')}" != ref
                    or (skill is not None and not isinstance(skill, str))):
                    raise ValidationError("Signal original identity or skill is invalid")
                projected["source_hash"] = self._signal_hashes[ref]
                self._signal_read_entries[ref] = {
                    "source_ref": ref, "source_hash": self._signal_hashes[ref],
                    "content": _mask_identity_values(original, tuple(identity_aliases), expand_aliases=False),
                    "content_is_masked": True,
                }
                projected["read_bytes"] = json_bytes(self._signal_read_entries[ref])
                if not isinstance(spec.get("definition", {}), Mapping):
                    raise ValidationError("Signal original definition must be an object")
                definition = dict(spec.get("definition") or {})
                if "description" in definition:
                    projected["description"] = definition.pop("description")
                projected["capability_contract"] = {
                    **({"definition": definition} if definition else {}),
                    **{key: deepcopy(spec[key]) for key in (
                        "schema", "execution", "raw_retrieval", "parameters", "modality", "evidence_policy",
                    ) if key in spec},
                }
            enriched.append(_mask_identity_values(projected, tuple(identity_aliases), expand_aliases=False))
        self.signal_catalog = tuple(enriched)
        self.seed = seed
        if any(not isinstance(row, Mapping) or not isinstance(row.get("need_ref"), str)
               or not row["need_ref"].strip() for row in backlog_needs):
            raise ValidationError("backlog rows require non-empty string need refs")
        self.backlog_needs = tuple(deepcopy(dict(row)) for row in backlog_needs)
        self._backlog_by_ref = {row["need_ref"]: row for row in self.backlog_needs}
        if len(self._backlog_by_ref) != len(backlog_needs):
            raise ValidationError("backlog need refs must be unique")
        self._backlog_hash = canonical_json_hash(list(self.backlog_needs))
        self._staged_need_dispositions: list[Mapping[str, Any]] = []
        self.need_progress_sink = need_progress_sink
        self.heavy_action_limit = heavy_action_limit
        self.light_action_limit = light_action_limit
        self.browse_limit = browse_limit
        self.attribute_vocabulary = dict(attribute_vocabulary or {})
        self.prior_modality_footprints = tuple(
            dict(row) for row in prior_modality_footprints
        )
        # Fast reflection memory this controller must actually consume:
        # bounded masked briefs plus the paid selected original disclosures.
        # Without them the mining loop runs blind to prior-round lessons even
        # though the runtime paid to read them.
        self.meta_memory_briefs = dict(meta_memory_briefs or {})
        self.meta_memory_disclosures = tuple(
            dict(row) for row in meta_memory_disclosures
        )
        self.memory_index = memory_index
        self.slow_method_memory = deepcopy(dict(slow_method_memory or {}))
        self._memory_read_refs: set[str] = set()
        self._memory_shown_refs: set[str] = set()
        self._browse_used = 0
        self.validation_sink = validation_sink
        self.identity_aliases = tuple(identity_aliases)
        self.research_axis = dict(
            research_axis
            or {
                "axis_id": "surge_direction",
                "population": "eligible_discovery_cases",
                "positive": "realized_max_multiple >= 2.0",
                "control": "realized_max_multiple < 2.0",
            }
        )
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
        self._document_case_refs: dict[tuple[str, str], set[str]] = {}
        self._attribute_rows: dict[tuple[str, ...], dict[str, list[dict[str, object]]]] = {}
        self._document_cards: dict[tuple[str, str], dict[str, Any]] = {}
        self._visible_ranges: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {}
        self._read_progress: dict[tuple[str, str, int, int], dict[str, Any]] = {}
        self._materialization_reads: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._fact_read_progress: dict[str, dict[str, Any]] = {}
        self._comparison_progress: dict[str, dict[str, Any]] = {}
        self._comparison_snapshot: str | None = None
        self._last_action_result: Mapping[str, Any] | None = None
        self._narrative_explored = False
        self._narrative_reads = 0
        self._last_invalid: Mapping[str, Any] | None = None
        default_labels = {
            ref: ("positive" if case.ground_truth.is_surge else "control")
            for ref, case in self.case_pairs
        }
        self._label_map = (
            {str(ref): str(label) for ref, label in label_map.items()}
            if label_map is not None
            else default_labels
        )
        if set(self._label_map) != set(self.case_by_ref) or any(
            label not in {"positive", "control"}
            for label in self._label_map.values()
        ):
            raise ValidationError(
                "runtime-owned label_map must cover every case ref exactly "
                "with positive/control labels"
            )
        if not str(self.research_axis.get("axis_id", "")).strip():
            raise ValidationError("research_axis requires a stable axis_id")

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
                            "action budget exhausted; model repeated an "
                            "inadmissible action"
                        ),
                    )
                    terminal_kind = "deferred_budget"
            except (InvalidMiningAction, ValidationError) as exc:
                self._record_invalid(action, raw, str(exc))
                if not raw and self._last_invalid and "output_patch_contract" in self._last_invalid:
                    self._last_invalid = {**self._last_invalid, "patch_error": str(exc)}
                else:
                    self._last_invalid = {"action": action, "issue": str(exc)}
                    if isinstance(exc, StructuredValidationError):
                        feedback = _validation_obligations(exc, raw)
                        self._last_invalid.update(
                            invalid_output=deepcopy(raw), validation_feedback=feedback,
                            output_patch_contract=state_patch_contract(
                                raw, mode="correction", obligations=feedback["obligations"]),
                        )
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
            staged_need_dispositions=tuple(deepcopy(self._staged_need_dispositions)),
            pending_need_refs=() if need_dispositions else tuple(self._pending_need_refs()),
        )

    # ------------------------------------------------------------------
    # Model boundary
    def materialization_evidence(self) -> dict[str, dict[str, Any]]:
        """Export source-bound graph units and executed reads for this seed only."""
        evidence = {ref: {"evidence_kind": kind, **asdict(item)}
            for kind, items in (("fact", self._facts), ("relation", self._relations))
            for ref, item in items.items()}
        for row in evidence.values():
            if row["evidence_kind"] != "fact":
                continue
            document = self._document_by_ref(row["document_ref"])
            if document is None or document.content_hash != row["content_hash"]:
                raise ValidationError("materialization fact source binding is unavailable")
            row.update(source_type=document.source_type, published_at=document.published_at.isoformat())
        for event_ref, event in self._events.items():
            reads = [deepcopy(row) for row in self._materialization_reads.values()
                if row["document_ref"] == event.document_ref and event.case_ref in row["case_refs"]]
            if reads:
                # Discovery previews/anchors never replace the actual raw read.
                evidence[event_ref] = {"evidence_kind": "event_read",
                    **{key: value for key, value in asdict(event).items()
                       if key not in {"exact_span", "excerpt"}},
                    "source_type": reads[0]["source_type"], "read_windows": reads}
        for row in self._materialization_reads.values():
            ref = row["document_ref"]
            unit = evidence.setdefault(ref, {"evidence_kind": "document_read", "document_ref": ref,
                **{key: row[key] for key in ("content_hash", "source_type", "published_at", "available_at")},
                "read_windows": []})
            if unit["content_hash"] != row["content_hash"]:
                raise ValidationError("materialization document read hash conflict")
            unit["read_windows"].append(deepcopy(row))
        return evidence

    def _decide(self, view: Mapping[str, Any]) -> dict[str, Any]:
        self._model_calls += 1
        raw = self.model.next_action(dict(view))
        if not isinstance(raw, Mapping):
            raise InvalidMiningAction("model action must be a JSON object")
        if self._last_invalid and "output_patch_contract" in self._last_invalid:
            raw = apply_state_patch(self._last_invalid["invalid_output"], raw,
                                    contract=self._last_invalid["output_patch_contract"])
        original = deepcopy(dict(raw))
        repaired, operations = mechanical_repair_candidate(raw)
        if operations:
            self.ledger.append(LedgerEntry(
                action_id=len(self.ledger.entries) + 1, action="mechanical_repair",
                input_hash=canonical_json_hash(original), output_hash=canonical_json_hash(repaired),
                coverage={"repairs": [asdict(operation) for operation in operations]},
                note="shape-only action repair; full validation precedes execution",
            ))
        return repaired

    def _model_view(self) -> dict[str, Any]:
        signal_page = self._signal_view()
        view: dict[str, Any] = {
            "seed": self.seed,
            "state": self._state,
            "budget": self._remaining_budget(),
            "available_source_families": list(self.available_source_families),
            "measurable_evidence_manifest": self.manifest,
            "signal_catalog": signal_page["items"],
            "signal_catalog_disclosure": {
                key: value for key, value in signal_page.items()
                if key != "items"
            },
            "case_refs": [ref for ref, _case in self.case_pairs],
            "case_prediction_times": {ref: case.prediction_time.isoformat() for ref, case in self.case_pairs},
            "tool_contracts": {
                "inspect_catalog": {
                    "default_scope": "signals",
                    "budget_by_scope": dict(_CATALOG_SCOPE_BUDGETS),
                    "allowed_scopes": self._available_catalog_scopes(),
                },
                "compute_statistic": {"rules": sorted(COMPUTE_RULES), "operand_count": 2,
                    "operand_scope": "same_case", "operand_order": "numerator_then_denominator_or_latest_then_prior",
                    "numeric_requirements": "finite operands and result; non-zero denominator for ratios"},
                "read_span": {"target_fields": ["fact_ref", "event_ref", "document_ref"],
                    "target_count": 1, "offset_min": 0, "length_min": 1, "length_max": _READ_BYTE_LIMIT,
                    "window_applies_to": ["event_ref", "document_ref"],
                    "budget_by_target": {"fact_ref": "heavy", "event_ref": "browse", "document_ref": "browse"}},
            },
            "known_fact_refs": sorted(self._facts),
            "known_event_refs": sorted(self._events),
            "known_relation_refs": sorted(self._relations),
            "label_map": dict(self._label_map),
            "research_axis": dict(self.research_axis),
            "evidence_digest": self._evidence_digest(),
            "modality_coverage": self._modality_coverage(),
            "prior_modality_footprints": [
                dict(row) for row in self.prior_modality_footprints
            ],
            "meta_info": self._memory_view(),
            "meta_memory_disclosures": [
                dict(row) for row in self.meta_memory_disclosures
            ],
            "slow_method_memory": deepcopy(self.slow_method_memory),
            "memory_consumption": {"read_refs": sorted(self._memory_read_refs),
                "original_disclosure_bytes": json_bytes(self.meta_memory_disclosures),
                "original_disclosure_limit": 48_000},
        }
        if self._last_action_result is not None:
            view["last_action_result"] = deepcopy(self._last_action_result)
        if self._comparison_progress:
            current = self._comparison_snapshot == self._comparison_context_hash()
            entries = deepcopy(list(reversed(list(self._comparison_progress.values())))) if current else []
            progress = bounded_entry_page(entries, max_items=12, max_bytes=8_000)
            progress["oversized_entries"] = [
                {**row, "concept": entries[row["index"]]["concept"]}
                for row in progress["oversized_entries"]
            ]
            view["comparison_progress"] = {
                **progress, "snapshot_status": "current" if current else "invalidated",
                "invalidated_comparisons": 0 if current else len(self._comparison_progress),
                "selection_order": "most_recent_comparison_first",
                "refresh_action": "compare_groups with requested concepts; ordinary heavy cost",
            }
            if not current:
                view["comparison_progress"]["selection_is_exhaustive"] = False
                if self._last_action_result and self._last_action_result.get("action") == "compare_groups":
                    view["last_action_result"] = {"action": "compare_groups", "snapshot_status": "invalidated"}
        if self._read_progress:
            view["narrative_read_progress"] = bounded_entry_page(
                list(reversed(list(self._read_progress.values()))),
                max_items=max(1, len(self._read_progress)),
            )
            view["narrative_read_evidence"] = self._narrative_read_evidence_view()
        if self._fact_read_progress:
            entries = deepcopy(list(reversed(list(self._fact_read_progress.values()))))
            progress = bounded_entry_page(entries)
            progress["oversized_entries"] = [
                {**row, "fact_ref": entries[row["index"]]["fact_ref"]}
                for row in progress["oversized_entries"]
            ]
            view["structured_read_progress"] = {
                **progress, "selection_order": "most_recent_read_first",
                "revisit_action": "read_span with fact_ref; ordinary heavy cost",
            }
        view["available_actions"] = [
            action for action in ACTIONS
            if (action not in LIGHT_ACTIONS or self._light_used < self.light_action_limit
                or (action == "inspect_catalog" and self._browse_used < self.browse_limit))
            and (action not in HEAVY_ACTIONS or self._heavy_used < self.heavy_action_limit
                 or (action == "read_span" and self._browse_used < self.browse_limit))
            and (action != "record_need_dispositions"
                 or (self.seed == "hypothesis" and self._pending_need_refs()))
        ]
        if self._last_invalid is not None:
            view["last_invalid_action"] = dict(self._last_invalid)
        if self.seed == "hypothesis":
            page = self._backlog_view(pending_only=True)
            view["backlog_needs"] = page["items"]
            view["backlog_disclosure"] = {key: value for key, value in page.items() if key != "items"}
            view["need_disposition_contract"] = {
                "base_hash": self._need_state_hash(),
                "allowed_need_refs": self._disclosed_need_refs(),
                "pending_count": len(self._pending_need_refs()),
                "staged_count": len(self._backlog_by_ref) - len(self._pending_need_refs()),
                "dispositions": sorted(ALLOWED_DISPOSITIONS),
                "row_rationale": NEED_ROW_RATIONALE_CONTRACT,
            }
        return view

    def _narrative_read_evidence_view(self) -> dict[str, Any]:
        """Project whole executed narrative units without changing source handoff."""
        fields = ("document_ref", "content_hash", "verbatim_hash", "offset", "length",
                  "raw_window_chars", "has_readable_text", "readable_chars", "next_readable_start",
                  "source_type", "published_at", "available_at")
        groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
        for row in self._materialization_reads.values():
            if _evidence_source_family(row["source_type"]) in _NARRATIVE_FAMILIES:
                key = (row["document_ref"], row["content_hash"], row["offset"], row["length"])
                groups.setdefault(key, []).append(row)
        entries = []
        for receipt in reversed(list(self._read_progress.values())):
            key = (receipt["document_ref"], receipt["content_hash"], receipt["offset"], receipt["length"])
            reads = groups.get(key)
            if not reads:
                continue
            first = reads[0]
            unit = {field: first[field] for field in fields}
            unit["readable_text"] = strip_document_artifacts(str(_mask_identity_values(
                first["readable_text"], self.identity_aliases, expand_aliases=False)))
            unit["read_count"] = receipt["read_count"]
            unit["case_refs"] = sorted({ref for row in reads for ref in row["case_refs"]})
            # Targets retain their own observed scopes: a document alias must not
            # turn one case's event read into another case's event permission.
            unit["read_targets"] = [{"target": row["target"], "ref": row["ref"],
                                     "case_refs": list(row["case_refs"])} for row in reads]
            entries.append(unit)
        page = bounded_entry_page(entries, max_items=12, max_bytes=40_000)

        def location(index: int) -> dict[str, Any]:
            row = entries[index]
            return {**{field: row[field] for field in ("document_ref", "content_hash", "offset", "length")},
                    "required_bytes": json_bytes([row])}

        page["oversized_entries"] = [
            {**row, **location(row["index"])} for row in page["oversized_entries"]]
        page["omitted_entries"] = [location(index) for index in range(page["next_cursor"] or len(entries), len(entries))]
        return {**page, "max_items": 12, "selection_order": "most_recent_read_first",
                "revisit_action": "read_span with a known event_ref or document_ref at these coordinates; ordinary browse cost"}

    def _available_catalog_scopes(self) -> list[str]:
        """Disclose only catalog variants permitted by their actual budgets."""
        budget = self._remaining_budget()
        return [scope for scope, dimension in _CATALOG_SCOPE_BUDGETS.items()
                if budget[f"{dimension}_remaining"] > 0]

    def _remaining_budget(self) -> dict[str, int]:
        """One runtime source for disclosed counters and authored-claim checks."""
        return {"heavy_remaining": self.heavy_action_limit - self._heavy_used,
                "light_remaining": self.light_action_limit - self._light_used,
                "browse_remaining": self.browse_limit - self._browse_used}

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
            projected = self._projected_attributes()
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

    def _projected_attributes(self) -> dict[str, list[dict[str, object]]]:
        """Reuse immutable document projections, retaining current case ownership."""

        vocabulary_hash = canonical_json_hash(self.attribute_vocabulary)
        grouped_events = _events_by_document(self._events.values())
        seen: set[tuple[str, str]] = set()
        projected: dict[str, list[dict[str, object]]] = {}
        for result in self._documents.values():
            for document in result.documents:
                identity = (document.document_id, document.content_hash)
                if identity in seen:
                    continue
                seen.add(identity)
                case_events = grouped_events.get((f"document-{document.document_id}", document.content_hash), {})
                key = (*identity, document.source_type, document.available_at.isoformat(),
                       canonical_json_hash(sorted(case_events)), vocabulary_hash)
                if key not in self._attribute_rows:
                    self._attribute_rows[key] = project_attributes(
                        (document,), case_events.values(),
                        vocabulary=self.attribute_vocabulary,
                    )
                for name, rows in self._attribute_rows[key].items():
                    projected.setdefault(name, []).extend(rows)
        return projected

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
            "note": "inspect_catalog with scope=evidence pages titled documents "
            "by family and window; copy the result's next_cursor into the next "
            "request to reach omitted entries. A page is not the full directory; "
            "read_span on event_ref reads the verbatim text",
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
                f"remain unexplored ({', '.join(missing)}): fetch structured "
                "evidence or read a narrative event/document via read_span. "
                "Listing or fetching a narrative family proves availability "
                "but is not a grounded read; record_deferred remains the "
                "control-plane terminal."
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
            message = "rationale must be a non-empty array of short strings"
            if "rationale" not in raw or rationale == []:
                issues = [ValidationIssue(code="mining_rationale_missing", message=message,
                                          paths=("rationale",), allowed_repairs=("add",))]
            elif not isinstance(rationale, list):
                issues = [ValidationIssue(code="mining_rationale_shape", message=message,
                                          paths=("rationale",), allowed_repairs=("replace",),
                                          repair_context={"invalid_container_paths": ["rationale"]})]
            else:
                issues = [ValidationIssue(code="mining_rationale_member", message=message,
                          paths=(f"rationale[{index}]",), allowed_repairs=("replace",),
                          repair_context={"invalid_container_paths": [f"rationale[{index}]"]})
                          for index, item in enumerate(rationale)
                          if not isinstance(item, str) or not item.strip()]
            raise StructuredValidationError(issues)
        texts = [(f"rationale[{i}]", text) for i, text in enumerate(rationale)]
        coverage = raw.get("coverage")
        if isinstance(coverage, Mapping) and isinstance(coverage.get("note"), str):
            texts.append(("coverage.note", coverage["note"]))
        if action == "inspect_catalog":
            scope = str(raw.get("scope", "signals"))
            dimension = _CATALOG_SCOPE_BUDGETS.get(scope)
            if dimension is None:
                raise InvalidMiningAction("inspect_catalog scope must be signals, evidence, memory or backlog")
            if self._remaining_budget()[f"{dimension}_remaining"] == 0:
                message = "light action budget exhausted" if dimension == "light" else "browse budget exhausted"
                raise BudgetInadmissibleAction(
                    f"{message} for inspect_catalog(scope={scope}); "
                    f"allowed_scopes: {self._available_catalog_scopes()}"
                )
        elif action in LIGHT_ACTIONS and self._light_used >= self.light_action_limit:
            raise BudgetInadmissibleAction("light action budget exhausted")
        narrative_read = action == "read_span" and any(key in raw for key in ("event_ref", "document_ref"))
        if narrative_read and self._browse_used >= self.browse_limit:
            raise BudgetInadmissibleAction("browse budget exhausted")
        if action in HEAVY_ACTIONS and not narrative_read and self._heavy_used >= self.heavy_action_limit:
            raise BudgetInadmissibleAction("heavy action budget exhausted")
        issues = budget_claim_issues(texts, self._remaining_budget())
        if issues:
            raise InvalidMiningAction("; ".join(issue.message for issue in issues))

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
            if action == "inspect_manifest":
                payload = self.manifest
            else:
                scope = str(raw.get("scope", "signals"))
                cursor = raw.get("cursor", 0)
                if scope == "evidence":
                    payload = self._evidence_catalog_view(cursor=cursor)
                elif scope == "signals":
                    payload = self._signal_view(cursor=cursor, item_refs=raw.get("item_refs"))
                elif scope == "memory":
                    payload = self._memory_view(cursor=cursor, item_refs=raw.get("item_refs"), level=raw.get("level"), signal_ref=raw.get("signal_ref"))
                elif scope == "backlog":
                    payload = self._backlog_view(cursor=cursor, item_refs=raw.get("item_refs"))
                else:
                    raise InvalidMiningAction("inspect_catalog scope must be signals, evidence, memory or backlog")
            if action == "inspect_catalog" and raw.get("scope") == "memory":
                self._browse_used += 1
            else:
                self._light_used += 1
            self._last_action_result = {
                "action": action, "scope": raw.get("scope"), "result": deepcopy(payload),
            }
            self._append(
                action, raw, payload=payload,
                coverage={"keys": sorted(payload)},
                omitted_coverage=dict(payload.get("counts", {})),
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
        if action == "record_need_dispositions":
            return self._record_need_dispositions(raw)
        if action == "record_deferred":
            kind = (
                "deferred_budget"
                if self._budget_exhausted()
                else "evidence_unavailable"
            )
            self._mark_terminal(kind, raw, note="record_deferred")
            return kind, [], ()
        if action == "record_no_pattern":
            dispositions = self._validate_need_dispositions(raw) if self.seed == "hypothesis" else ()
            self._execute_no_pattern(raw)
            return "no_pattern_with_coverage", [], dispositions
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
        prior_fact_refs = set(self._facts)
        prior_relation_refs = set(self._relations)
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
                self._document_case_refs.setdefault((document.document_id, document.content_hash), set()).add(str(ref))
        evidence_refs: list[str] = []
        source_types: set[str] = set()
        for result in results:
            evidence_refs.extend(fact.fact_ref for fact in result.facts)
            evidence_refs.extend(
                event.event_ref for event in result.narrative_events
            )
            source_types.update(
                str(document.source_type) for document in result.documents
            )
        coverage = {
            "query_coverage": {
                "matched_terms": sorted({
                    term for result in results
                    for term in result.query_coverage.get("matched_terms", ())
                }),
                "sufficient": all(
                    result.query_coverage.get("sufficient", False)
                    for result in results
                ),
            },
            "unread_same_source": any(result.unread_same_source for result in results),
        }
        omitted = {
            "excluded_document_ids": sorted({
                document_id for result in results
                for document_id in result.excluded_by_limits
            }),
        }
        self._heavy_used += 1
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
        self._relations = {ref: relation for ref, relation in self._relations.items()
                           if relation.kind != "same_concept_period_pair"}
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
            "new_facts": len(set(self._facts) - prior_fact_refs),
            "total_facts": len(self._facts),
            "total_events": len(self._events),
            "new_relations": len(set(new_relations) - prior_relation_refs),
            "total_relations": len(self._relations),
            "excluded_document_ids": len(
                omitted.get("excluded_document_ids", ())
            ),
            "narrative_evidence": {
                "events": len(narrative_events),
                "sample_titles": sample_titles,
                "catalog_note": (
                    "the evidence catalog pages titled documents by family and "
                    "window (inspect_catalog scope=evidence); use next_cursor "
                    "to reach omitted entries"
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
        identity = (document.document_id, document.content_hash)
        if identity not in self._visible_ranges:
            self._visible_ranges[identity] = (
                visible_html_ranges(document.content)
                if document.source_type.casefold() in _MARKUP_SOURCE_TYPES
                else ((0, len(document.content)),)
            )
        disclosure = raw_span_view(document, offset, length, visible_ranges=self._visible_ranges[identity])
        readable = disclosure.pop("readable_text")
        masked = strip_document_artifacts(
            str(
                _mask_identity_values(
                    readable, self.identity_aliases, expand_aliases=False
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
            **disclosure,
            "case_refs": ([event.case_ref] if event is not None else
                          sorted(self._document_case_refs.get(identity, ()))),
        }
        if event is not None:
            entry["title"] = event.title
            entry["source_family"] = event.source_family
            entry["available_at"] = event.available_at
        read_key = (target_key, target_ref, document.document_id, document.content_hash,
                    offset, length, tuple(entry["case_refs"]))
        self._materialization_reads[read_key] = {
            **{key: value for key, value in entry.items() if key != "masked"},
            "readable_text": readable, "content_hash": document.content_hash,
            "source_type": document.source_type,
            "published_at": document.published_at.isoformat(),
            "available_at": document.available_at.isoformat(),
        }
        progress_key = (*identity, offset, length)
        previous_receipt = self._read_progress.pop(progress_key, {})
        self._read_progress[progress_key] = {
            "document_ref": document_ref,
            "content_hash": document.content_hash,
            **{key: entry[key] for key in (
                "offset", "length", "verbatim_hash", "has_readable_text",
                "next_readable_start",
            )},
            "read_count": previous_receipt.get("read_count", 0) + 1,
            "case_refs": sorted(set(entry["case_refs"]) | set(previous_receipt.get("case_refs", ()))),
        }
        self._last_action_result = {"action": "read_span", **dict(entry)}
        self._append(
            "read_span",
            raw,
            payload=entry,
            evidence_refs=(
                (target_ref,) if target_key == "event_ref" else (document_ref,)
            ),
            case_refs=tuple(entry["case_refs"]),
        )
        if (
            _evidence_source_family(document.source_type) in _NARRATIVE_FAMILIES
            and disclosure["has_readable_text"]
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
        entry = {"fact_ref": fact_ref, "context_chars": len(masked), "masked": masked,
                 "case_refs": [fact.case_ref], "document_ref": fact.document_ref,
                 "content_hash": fact.content_hash, "available_at": fact.available_at,
                 "fact": _mask_identity_values(
                     {"taxonomy": fact.taxonomy, "concept": fact.concept,
                      "unit": fact.unit, "period": dict(fact.period) if fact.period else None,
                      "value": fact.value}, self.identity_aliases, expand_aliases=False)}
        prior = self._fact_read_progress.get(fact_ref, {})
        if prior and {key: value for key, value in prior.items() if key != "read_count"} != entry:
            raise InvalidMiningAction("already-read fact receipt changed under the same fact_ref")
        self._last_action_result = {"action": "read_span", **entry}
        self._append(
            "read_span",
            raw,
            payload=entry,
            evidence_refs=(fact_ref,),
            case_refs=(fact.case_ref,),
        )
        self._fact_read_progress.pop(fact_ref, None)
        self._fact_read_progress[fact_ref] = {
            **deepcopy(entry), "read_count": prior.get("read_count", 0) + 1,
        }
        self._heavy_used += 1
        return "running", [], ()

    def _execute_compare(
        self, raw: Mapping[str, Any]
    ) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        self._require_state_at_least("evidence_ready", "compare_groups")
        concepts = raw.get("concepts")
        if not isinstance(concepts, list) or not concepts:
            raise InvalidMiningAction("compare_groups requires non-empty concepts")
        wanted = tuple(sorted({str(item) for item in concepts}))
        snapshot = self._comparison_context_hash()
        summary = self._group_summary(wanted)
        if snapshot != self._comparison_context_hash():
            raise InvalidMiningAction("comparison inputs changed during calculation")
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
        if self._comparison_snapshot != snapshot:
            self._comparison_progress.clear()
        self._comparison_snapshot = snapshot
        for concept in reversed(wanted):
            self._comparison_progress.pop(concept, None)
            self._comparison_progress[concept] = {
                "concept": concept, "source_snapshot_hash": snapshot,
                "groups": deepcopy({group: {"case_count": row["case_count"], **row["concepts"][concept]}
                    for group, row in summary.items()}),
            }
        self._heavy_used += 1
        return "running", [], ()

    def _comparison_context_hash(self) -> str:
        """Bind only the fetched graph and runtime grouping, without computing evidence."""

        return canonical_json_hash({
            "facts": [asdict(self._facts[ref]) for ref in sorted(self._facts)],
            "label_map": self._label_map, "research_axis": self.research_axis,
        })

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
                latest, prior, unresolved = {}, {}, {}
                for case_ref in sorted(group_refs):
                    case_facts = [fact for fact in concept_facts if fact.case_ref == case_ref]
                    current = _unique_latest_fact(case_facts)
                    pair = _unique_period_pair(case_facts)
                    if current is not None:
                        latest[case_ref] = {"value": current.value, "fact_ref": current.fact_ref}
                    if pair is not None:
                        prior[case_ref] = {"value": pair[1].value, "fact_ref": pair[1].fact_ref}
                    elif case_facts:
                        unresolved[case_ref] = ("latest basis is not unique across available units/periods/values"
                            if current is None else "no unique document-local comparable prior")
                by_concept[concept] = {
                    "available_cases": sorted({fact.case_ref for fact in concept_facts}),
                    "latest": latest, "comparable_prior": prior,
                    "unresolved_basis_cases": unresolved,
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
        if "usage_context" in candidate:
            from stock_opportunity_agent.memory.knowledge import usage_context

            try:
                context = usage_context(candidate["usage_context"])
            except ValidationError as exc:
                raise InvalidMiningAction(str(exc)) from exc
            if set(context["related_refs"]) - (self._memory_shown_refs | self._memory_read_refs):
                raise InvalidMiningAction("candidate usage context references undisclosed Experience")
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
        downstream by executable fixtures and the technical admission validator.
        Independent effect observations follow admission.
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
        # Use the same case/hash-bound units that S5 will actually receive.
        # An unrelated raw read cannot promote a discovery preview to evidence.
        evidence = self.materialization_evidence()
        narrative_refs = {
            ref for ref in cited_refs
            if ref in self._events or (
                ref.startswith("document-")
                and (document := self._document_by_ref(ref)) is not None
                and _evidence_source_family(document.source_type) in _NARRATIVE_FAMILIES
            )
        }
        unread = sorted(ref for ref in narrative_refs if not any(
            str(window.get("readable_text", "")).strip()
            for window in evidence.get(ref, {}).get("read_windows", ())
        ))
        if unread:
            raise InvalidMiningAction(
                "narrative citations require an executed readable window in "
                "their own document/hash and case scope; use read_span before "
                "proposing: " + ", ".join(unread)
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
        self, raw: Mapping[str, Any], *, require_complete: bool = True,
    ) -> tuple[Mapping[str, Any], ...]:
        rows = raw.get("need_dispositions", [] if self._staged_need_dispositions or not self.backlog_needs else None)
        if not isinstance(rows, list):
            raise InvalidMiningAction(
                "hypothesis seed terminal requires need_dispositions"
            )
        known_refs = {
            str(row.get("need_ref"))
            for row in self.backlog_needs
            if isinstance(row, Mapping)
        }
        seen = {str(ref) for row in self._staged_need_dispositions for ref in row["need_refs"]}
        clean: list[Mapping[str, Any]] = deepcopy(self._staged_need_dispositions) if require_complete else []
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
            if (not isinstance(refs, list) or not refs
                or any(not isinstance(ref, str) or not ref for ref in refs)
                or len(set(refs)) != len(refs)):
                row_issues.append(f"row[{index}] need_refs must be non-empty")
                continue
            if require_complete and not set(refs) <= set(self._disclosed_need_refs()):
                row_issues.append(f"row[{index}] new need refs must be currently disclosed and unresolved")
                continue
            disposition = row["disposition"]
            if not isinstance(disposition, str) or disposition not in ALLOWED_DISPOSITIONS:
                row_issues.append(
                    f"row[{index}] disposition must be one of "
                    + ", ".join(sorted(ALLOWED_DISPOSITIONS))
                )
                continue
            signal_refs = row["signal_refs"]
            if not isinstance(signal_refs, list):
                row_issues.append(f"row[{index}] signal_refs must be an array")
                continue
            if disposition == "update_existing":
                if len(signal_refs) != 1 or not isinstance(signal_refs[0], str) or signal_refs[0] not in {str(card.get("signal_ref")) for card in self.signal_catalog}:
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
            rationale = row["rationale"]
            if not isinstance(rationale, list) or not rationale or any(not isinstance(text, str) or not text.strip() for text in rationale):
                row_issues.append(f"row[{index}] {NEED_ROW_RATIONALE_CONTRACT}")
                continue
            issues = budget_claim_issues(
                [(f"row[{index}].rationale[{i}]", text) for i, text in enumerate(rationale)],
                self._remaining_budget(),
            )
            if issues:
                row_issues.extend(issue.message for issue in issues)
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
        if require_complete and missing:
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

    def _pending_need_refs(self) -> list[str]:
        """Keep frozen-order unresolved identities outside the model transcript."""
        staged = {ref for row in self._staged_need_dispositions for ref in row["need_refs"]}
        return [ref for ref in self._backlog_by_ref if ref not in staged]

    def _need_state_hash(self) -> str:
        """Bind disposition edits to this axis and the exact accepted intent."""
        return canonical_json_hash({"backlog_hash": self._backlog_hash,
            "axis": self.research_axis, "seed": self.seed,
            "staged_rows": self._staged_need_dispositions})

    def _disclosed_need_refs(self) -> list[str]:
        """Authorize only pending cards actually present in the current view."""
        refs = [row["need_ref"] for row in self._backlog_view(pending_only=True)["items"]]
        receipt = self._last_action_result or {}
        if receipt.get("scope") == "backlog":
            refs.extend(row["need_ref"] for row in receipt.get("result", {}).get("items", ()))
        pending = set(self._pending_need_refs())
        return list(dict.fromkeys(ref for ref in refs if ref in pending))

    def _backlog_view(self, *, cursor: int = 0, pending_only: bool = False,
                      item_refs: Any = None) -> dict[str, Any]:
        """Page exact semantic cards; supplied refs resolve whole original rows."""
        if item_refs is not None:
            try:
                return read_whole_entries(self._backlog_by_ref, item_refs, max_bytes=16_000)
            except ValidationError as exc:
                raise InvalidMiningAction(f"backlog read: {exc}") from exc
        refs = self._pending_need_refs() if pending_only else list(self._backlog_by_ref)
        cards = [{"need_ref": ref,
                  **{key: self._backlog_by_ref[ref][key] for key in ("need", "kind", "status") if key in self._backlog_by_ref[ref]},
                  "source_scope": self._need_source_scope(self._backlog_by_ref[ref]),
                  "source_hash": canonical_json_hash(self._backlog_by_ref[ref]),
                  "read_bytes": json_bytes(self._backlog_by_ref[ref])} for ref in refs]
        page = bounded_entry_page(cards, cursor=cursor)
        for entry in page["oversized_entries"]:
            entry["need_ref"] = refs[entry["index"]]
        return {**page, "backlog_hash": self._backlog_hash,
                "total_backlog_count": len(self._backlog_by_ref),
                "read_action": "inspect_catalog scope=backlog item_refs", "read_byte_limit": 16_000}

    def _need_source_scope(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Disclose source/current-cohort relation without case identities."""
        local = self._source_case_refs
        sources = [source for source in row.get("sources", ()) if isinstance(source, Mapping)]
        known = {source["source_case_ref"] for source in sources if source.get("source_case_ref")}
        matching = sorted(local[ref] for ref in known if ref in local)
        times = sorted({str(source["source_prediction_time"]) for source in sources if source.get("source_prediction_time")})
        unknown = sum(not source.get("source_case_ref") for source in sources)
        relation = ("plan_action" if row.get("kind") == "meta_reflection_action" else
                    "unknown" if not known else "outside_current_dev" if not matching else
                    "overlapping" if len(matching) == len(known) and not unknown else "mixed")
        return {"relation": relation, "known_source_case_count": len(known),
                "unknown_source_count": unknown, "current_dev_case_refs": matching,
                "unknown_source_time_count": sum(not source.get("source_prediction_time") for source in sources),
                "source_prediction_times": times[:4], "omitted_prediction_times": max(0, len(times) - 4)}

    def _signal_view(self, *, cursor: int = 0, item_refs: Any = None) -> dict[str, Any]:
        """Read hash-bound Signal originals or page capability cards."""
        if item_refs is None:
            page = bounded_entry_page(self.signal_catalog, cursor=cursor)
            for row in page["oversized_entries"]:
                row["signal_ref"] = self.signal_catalog[row["index"]]["signal_ref"]
            return {**page, "read_action": "inspect_catalog scope=signals item_refs", "read_byte_limit": 16_000}
        for ref, original in self._signal_originals.items():
            if canonical_json_hash(original) != self._signal_hashes[ref]:
                raise InvalidMiningAction(f"Signal original snapshot changed: {ref}")
        try:
            view = read_whole_entries(self._signal_read_entries, item_refs, max_bytes=16_000)
        except ValidationError as exc:
            raise InvalidMiningAction(f"Signal read: {exc}") from exc
        return view

    def _record_need_dispositions(self, raw: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]], tuple[Mapping[str, Any], ...]]:
        """Save valid independent intent rows and leave rejected siblings pending."""
        if self.seed != "hypothesis" or raw.get("base_hash") != self._need_state_hash():
            raise InvalidMiningAction("record_need_dispositions requires the issued hypothesis base_hash")
        rows = raw.get("need_dispositions")
        if not isinstance(rows, list) or not rows:
            raise InvalidMiningAction("record_need_dispositions requires non-empty need_dispositions")
        allowed = set(self._disclosed_need_refs())
        accepted, invalid = [], []
        base_hash = self._need_state_hash()
        for index, row in enumerate(rows):
            try:
                clean = self._validate_need_dispositions({"need_dispositions": [row]}, require_complete=False)
                if not set(clean[0]["need_refs"]) <= allowed:
                    raise InvalidMiningAction("need refs must belong to the currently disclosed unresolved page")
            except InvalidMiningAction as exc:
                invalid.append({"row_index": index, "issue": str(exc), "invalid_row": deepcopy(row)})
                continue
            self._staged_need_dispositions.extend(deepcopy(clean))
            accepted.extend(deepcopy(clean))
        if not accepted:
            raise InvalidMiningAction("no need-disposition progress: " + "; ".join(row["issue"] for row in invalid))
        unit = {"schema_version": "mining-need-disposition-unit-v1", "backlog_hash": self._backlog_hash,
                "axis_id": self.research_axis["axis_id"], "seed": self.seed,
                "base_hash": base_hash, "result_hash": self._need_state_hash(),
                "accepted_rows": accepted, "pending_count": len(self._pending_need_refs()),
                "invalid_rows": invalid}
        self._append("record_need_dispositions", raw, payload=unit)
        if self.need_progress_sink is not None:
            try:
                self.need_progress_sink(deepcopy(unit))
            except ValidationError as exc:
                raise RuntimeError("accepted need-unit persistence failed") from exc
        self._last_action_result = {"action": "record_need_dispositions", "result": unit}
        return "running", [], ()

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

    def _memory_view(self, *, cursor: int = 0, item_refs: Any = None, level: str | None = None,
                     signal_ref: str | None = None) -> dict[str, Any]:
        """Expose whole brief pages and resolve selected immutable local entries."""
        if self.memory_index is not None:
            if item_refs is not None:
                if (not isinstance(item_refs, list) or not 1 <= len(item_refs) <= 3
                    or any(not isinstance(ref, str) for ref in item_refs)
                    or len(set(item_refs)) != len(item_refs)):
                    raise InvalidMiningAction("memory read requires 1-3 unique supplied item_refs")
                try:
                    packet = self.memory_index.read_refs(item_refs, role="signal_mining", max_bytes=48_000)
                except ValidationError as exc:
                    raise InvalidMiningAction(str(exc)) from exc
                packet = _mask_identity_values(packet, self.identity_aliases, expand_aliases=False)
                known_sources = {row.get("ref") for row in self.meta_memory_disclosures}
                additions = [{"ref": source["source_ref"], "content": source}
                             for source in packet["sources"] if source["source_ref"] not in known_sources]
                disclosures = (*self.meta_memory_disclosures, *additions)
                if json_bytes(disclosures) > 48_000:
                    raise InvalidMiningAction("memory originals exceed the 48000 cumulative disclosure bytes")
                self.meta_memory_disclosures = disclosures
                self._memory_read_refs.update(item_refs)
                return packet
            try:
                directory = self.memory_index.directory(cursor=cursor, level=level, signal_ref=signal_ref, max_bytes=5_000)
                initial = self.memory_index.brief_view(max_bytes=6_000, max_items=6)
                self._memory_shown_refs.update(row["item_ref"] for row in [*directory["items"], *initial["items"]])
            except ValidationError as exc:
                raise InvalidMiningAction(str(exc)) from exc
            view = {**initial, "directory": directory,
                    "read_action": "inspect_catalog scope=memory cursor/level/signal_ref, or item_refs for item/source originals",
                    "read_byte_limit": 48_000, "budget_class": "browse"}
            return _mask_identity_values(view, self.identity_aliases, expand_aliases=False)
        items = self.meta_memory_briefs.get("items")
        if signal_ref is not None:
            raise InvalidMiningAction("Signal-filtered Experience browsing requires sourced indexed memory")
        if not isinstance(items, list):
            if json_bytes(self.meta_memory_briefs) > 8_000:
                raise ValidationError("mining memory requires indexed entries above 8000 bytes")
            return deepcopy(self.meta_memory_briefs)
        entries = [dict(row) for row in items if isinstance(row, Mapping)]
        if item_refs is not None:
            if not isinstance(item_refs, list) or not 1 <= len(item_refs) <= 3 or any(not isinstance(ref, str) for ref in item_refs) or len(set(item_refs)) != len(item_refs):
                raise InvalidMiningAction("memory read requires 1-3 unique supplied item_refs")
            by_ref = {str(row.get("item_ref")): row for row in entries}
            if any(ref not in by_ref for ref in item_refs):
                raise InvalidMiningAction("memory read references an unknown local item_ref")
            selected = [by_ref[ref] for ref in item_refs]
            if json_bytes(selected) > 16_000:
                raise InvalidMiningAction("memory read exceeds 16000 whole-entry bytes")
            self._memory_read_refs.update(item_refs)
            return {"items": deepcopy(selected), "included_refs": list(item_refs),
                    "counts": {"available": len(entries), "included": len(selected),
                               "omitted": len(entries) - len(selected)}}
        page = bounded_entry_page(entries, cursor=cursor, max_items=6, max_bytes=6_000)
        directory = bounded_entry_page([
            {"item_ref": row.get("item_ref"), "level": row.get("level"),
             "kind": row.get("kind"), "category": row.get("category"),
             "brief_preview": str(row.get("brief", ""))[:160],
             "preview_truncated": len(str(row.get("brief", ""))) > 160,
             "read_bytes": json_bytes(row)} for row in entries
        ], cursor=cursor, max_items=12, max_bytes=5_000)
        self._memory_shown_refs.update(row["item_ref"] for row in [*page["items"], *directory["items"]]
                                       if isinstance(row.get("item_ref"), str))
        return {**page, "included_refs": [row.get("item_ref") for row in page["items"]],
                "directory": directory, "read_action": "inspect_catalog scope=memory item_refs",
                "read_byte_limit": 16_000,
                "upstream_counts": deepcopy(self.meta_memory_briefs.get("counts", {}))}

    def _evidence_catalog_view(self, *, cursor: int = 0) -> dict[str, Any]:
        """Return a titled fetched-evidence page with reachable omitted entries."""
        documents = [document for result in self._documents.values() for document in result.documents]
        families = narrative_catalog(documents, self._events.values(), max_per_family=max(1, len(documents)),
                                     document_cards=self._document_cards,
                                     case_refs_by_document=self._document_case_refs)
        cards = []
        for family in families:
            for window in family["windows"]:
                for entry in window["entries"]:
                    card = {**entry, "family": family["family"], "window": window["window"]}
                    card["title"] = _mask_identity_values(card["title"], self.identity_aliases, expand_aliases=False)
                    reads = [{key: value for key, value in row.items()
                              if key not in {"document_ref", "content_hash"}}
                             for row in self._read_progress.values()
                             if row["document_ref"] == card["document_ref"]]
                    if reads:
                        card["read_windows"] = reads
                    cards.append(card)
        return bounded_entry_page(cards, cursor=cursor)

def _action_arguments(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in raw.items()
        if key not in {"rationale"} and isinstance(
            value, (str, int, float, bool, list, dict, type(None))
        )
    }
