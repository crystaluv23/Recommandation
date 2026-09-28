"""Slow Signal evolution and finite dual-loop orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime
from math import comb
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from stock_opportunity_agent.artifacts import (
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    EvidenceResolver,
    RawInfoRequest,
    RawInfoResolution,
    source_types_compatible,
)
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm.openai import OpenAIClientError
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    LLMSignalRunner,
    SignalExecutionStatus,
    SignalExecutionType,
    SignalExecutor,
    SignalModality,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
    default_deterministic_signal_functions,
    deterministic_signal_function_contracts,
    signal_result_model_view,
)

from stock_opportunity_agent.research.research_targets import (
    active_research_targets,
)
from stock_opportunity_agent.research.evolution_core import (
    AgentStep,
    CandidateExecutionRejected,
    DEFAULT_EVOLUTION_PRIORS,
    EvolutionCase,
    EvolutionDataset,
    EvolutionControlFlow,
    EvolutionPriors,
    PlanMetaMemory,
    ProgressCallback,
    RuntimeBudgetExceeded,
    SlowLoopDataUnavailable,
    _compiled_identity_aliases,
    _MASKED_IDENTITY_VALUE,
    _QUERYLESS_COMPANY_FACT_PRIORITY,
    _assert_identity_values_masked,
    _company_facts_context,
    _discovery_identity_terms,
    _emit_progress,
    _exploration_case_pairs,
    _h3_ordered_content_terms,
    _h3_text_query_coverage,
    _item1_business_excerpt,
    _json_array,
    _json_string_array,
    _listing_age_bucket,
    _market_cap_bucket,
    _evidence_source_family,
    _mask_identity_values,
    _opaque_slow_case_ref,
    _project_slow_case_refs,
    _model_evidence_view,
    _normalize_semantics,
    _ordered_unique,
    _point_in_time_profile_fields,
    _read_json,
    _require_aware_datetime,
    _sample_binary_discovery_cases,
    _sample_signal_discovery_cases,
    _scoped_slow_identity_guard_inventory,
    _select_h3_model_evidence,
    _slow_role_identity_guard_inventory,
    _usable_business_description,
    _usage_from_dict,
    _usage_to_dict,
    _validate_id,
)
from stock_opportunity_agent.research.evolution_settings import (
    FIXED_PREDICTOR_SEMANTICS,
    ROLE_OUTPUT_TOKEN_LIMITS,
)
from stock_opportunity_agent.research.mining_agent_tools import (
    derive_attribute_vocabulary,
    strip_document_artifacts,
)
from stock_opportunity_agent.research.mining_controller import (
    LabelAwareMiningController,
)
from stock_opportunity_agent.research.mining_role_model import (
    MiningAgentRoleModel,
)
from stock_opportunity_agent.research.plan_evolution import (
    EvolutionWorkspace,
    PlanEvolutionEngine,
    PlanRoundResult,
)


def signal_research_objective() -> dict[str, Any]:  # noqa: PLR0911
    """Expose fixed task semantics without individual case identities or outcomes."""

    return {
        "fixed_prediction_semantics": {
            key: FIXED_PREDICTOR_SEMANTICS[key]
            for key in ("target", "baseline", "future", "horizon")
        },
        "purpose": (
            "Find reusable point-in-time evidence that helps distinguish the fixed "
            "surge target from controls through expectation gaps, catalysts, changing "
            "fundamentals or early confirmation. Generic company quality alone does "
            "not establish relevance. Measurements contribute research evidence; "
            "they need not independently predict a surge."
        ),
        "boundary": (
            "This is the shared task definition, not a case outcome. Use only "
            "information available by each prediction time. Acquisition quality "
            "and missing observations must remain separate from business features."
        ),
        "research_targets": [
            contract.descriptor()
            for contract in active_research_targets()
        ],
    }


def signal_candidate_execution_contract() -> dict[str, Any]:
    """Expose existing value and retrieval semantics before candidate generation."""

    return {
        "modality": {
            "structured": (
                "A typed point-in-time measurement whose value is fully determined "
                "by inputs and parameters; it requires an exact registered "
                "deterministic function."
            ),
            "narrative": (
                "A semantic predicate over source text; it requires a grounded LLM skill."
            ),
            "mixed": (
                "Split numeric measurement and narrative fallback into separate Signals."
            ),
        },
        "value_semantics": {
            "positive": "Evidence in the direction of the fixed surge target.",
            "negative": "Evidence in the control/opposing direction.",
            "neutral": "Available measurement without decisive directional evidence.",
            "unavailable": "Required point-in-time measurement inputs are insufficient.",
            "orientation": (
                "Do not equate numeric sign with Signal direction. Derive a new "
                "candidate's orientation from the observed contrast and keep its "
                "definition, implementation and fixtures consistent. Report the "
                "underlying quantity in interpretation/evidence. Do not reverse "
                "an existing stable definition or copy case labels into the skill."
            ),
        },
        "retrieval": {
            "execution_order": "Coverage must resolve before the function or LLM skill runs.",
            "source_types": "Use source types/formats supported by the supplied evidence; do not invent a provider category.",
            "minimum_observations": (
                "Counts the largest explicit structured series in a document: lists "
                "named prices, observations, rows or series, or lists of records "
                "with date/timestamp fields. A standalone financial fact is not "
                "such a series. Leave null unless this is a real input requirement."
            ),
            "period_requirements": (
                "minimum_distinct_periods and minimum_period_span_days check period "
                "coverage, not concept completeness or comparable duration. The "
                "implementation must still check every required component and period."
            ),
            "fixtures": (
                "Non-unavailable fixtures must satisfy the same retrieval coverage "
                "as production, with literal source evidence and point-in-time dates. "
                "Missing-input fixtures may expect unavailable; technical failures "
                "are not successful unavailable measurements."
            ),
        },
    }


SIGNAL_UPDATE_MUTABLE_PATHS = (
    "spec.raw_retrieval.source_types",
    "spec.raw_retrieval.query_terms",
    "spec.raw_retrieval.lookback_days",
    "spec.raw_retrieval.comparison_requirement",
    "spec.raw_retrieval.required_source_groups",
    "spec.raw_retrieval.minimum_distinct_periods",
    "spec.raw_retrieval.minimum_period_span_days",
    "spec.raw_retrieval.minimum_observations",
    "spec.parameters",
    "spec.execution.skill_file",
    "skill",
)


_EXPLORATION_BOILERPLATE = re.compile(
    r"\b(?:commission\s+file|exact\s+name\s+of\s+registrant|state\s+of\s+"
    r"incorporation|securities\s+registered|trading\s+symbol|annual\s+report\s+"
    r"pursuant|quarterly\s+report\s+pursuant|large\s+accelerated\s+filer)\b|"
    r"^\s*(?:for\s+the\s+month\s+of\s+[a-z]+\s+\d{4}|on\s+[a-z]+\s+\d{1,2},\s+"
    r"\d{4},?\s+the\s+registrant\s+(?:issued|furnished)\s+a\s+press\s+release)"
    r"(?:,?\s+a\s+copy\s+of\s+which\s+(?:is|was)\s+(?:attached|furnished)\s+"
    r"(?:hereto\s+)?as\s+exhibit\s+\d+(?:\.\d+)?)?"
    r"\s*[.,]?\s*$",
    re.IGNORECASE,
)

_EXPLORATION_FINANCIAL_SOURCE_TYPES = (
    "company_facts",
    "financial_statements",
    "financials",
    "sec_company_facts",
    "sec_company_facts_raw_response",
)
_EXPLORATION_FILING_SOURCE_TYPES = (
    "10-k",
    "10-q",
    "20-f",
    "40-f",
    "6-k",
    "8-k",
    "filing",
    "filing_body",
    "sec_filing",
)
_H1_MANIFEST_CONCEPT_LIMIT = 24
_H1_MANIFEST_PROJECTION_CHARS = 12_000


_SLOW_FEEDBACK_KINDS = {
    "signal_usage",
    "candidate_result",
    "search_result",
    "technical_failure",
    "magnitude_feedback",
}
_SLOW_MEMORY_STATUSES = {
    "appended",
    "no_new_lesson",
    "reused",
    "failed",
}
_SLOW_SOURCE_ROLES = {"reflection", "H1", "H3", "E2", "Update"}

_UNASSESSED_MAGNITUDE_CONTRIBUTION: dict[str, Any] = {
    "assessed": False,
    "reason": (
        "first-version promotion gates are directional only; magnitude-only "
        "improvement is not separately evaluated"
    ),
}


def magnitude_feedback_rows(
    meta_entries: Iterable[Any],
    *,
    last_completed_round: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project committed magnitude diagnostics into Slow feedback rows.

    First-version Slow integration: magnitude learning tasks enter the
    existing source view as diagnostic evidence with stable cross-stage refs.
    Only locally committed rounds (``1 <= round_id <= last_completed_round``)
    contribute; rebased imported-history entries keep reserved negative ids
    and are proposer-view constructs, not locally committed feedback. Rows are
    derived only from Plan reflections that authentically carry research-case
    magnitude evidence — legacy entries without the block contribute no row
    rather than a zero-valued substitute. Legacy technical exclusions are
    projected out through the same model-view boundary used by Fast roles.
    These rows are reflection evidence only; no promotion gate reads them.
    """

    rows: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    for entry in meta_entries:
        round_id = getattr(entry, "round_id", 0)
        if round_id < 1 or round_id > last_completed_round:
            continue
        for reflection in getattr(entry, "plan_reflections", ()):
            if getattr(reflection, "magnitude_diagnostics", None) is None:
                continue
            model_view = reflection.to_model_dict()
            diagnostics = model_view.get("magnitude_diagnostics")
            if diagnostics is None:
                continue
            event = {
                "plan_id": reflection.plan_id,
                "round_id": round_id,
                "magnitude_diagnostics": dict(diagnostics),
                "technical_completion": dict(
                    model_view["technical_completion"]
                ),
            }
            feedback_ref = f"magnitude:{reflection.plan_id}"
            rows.append(
                {
                    "feedback_ref": feedback_ref,
                    "kind": "magnitude_feedback",
                    "subject_ref": reflection.plan_id,
                    "source_refs": [feedback_ref],
                    "limitations": [
                        "diagnostic reflection evidence; not a promotion gate"
                    ],
                    "event": event,
                }
            )
            manifest.append(
                {
                    "ref": feedback_ref,
                    "content_hash": _canonical_hash(event),
                    "visible_to": sorted(_SLOW_SOURCE_ROLES),
                }
            )
    rows.sort(key=lambda item: item["feedback_ref"])
    manifest.sort(key=lambda item: item["ref"])
    return rows, manifest


def build_slow_sampling_manifest(
    cases: Iterable[EvolutionCase],
    *,
    cycle_id: int,
    base_seed: str,
    dev_limit: int,
    check_limit: int,
) -> dict[str, Any]:
    """Freeze an outcome-independent ordering and issuer-disjoint dev/check split.

    Each cycle permutes the whole population afresh: any case may serve a
    mining or evaluation role in any later cycle. Evaluation honesty is
    enforced per candidate at the effectiveness gate, which excludes the
    proposal cycle's dev cohort and the candidate's own previously evaluated
    cases. Labels are used only for the explicitly disclosed binary
    stratification; they never affect the stable ordering within a class or
    allow case replacement.
    """

    if cycle_id < 1 or not base_seed.strip() or dev_limit < 1 or check_limit < 1:
        raise ValidationError("Slow sampling inputs are invalid")
    population = tuple(cases)
    if not population:
        raise ValidationError("Slow sampling requires Discovery cases")
    seed = _canonical_hash(
        {
            "schema_version": "slow-sampling-seed-v1",
            "base_seed": base_seed,
            "cycle_id": cycle_id,
            "population": sorted(
                {
                    (case.case_id, case.company_id, case.prediction_time.isoformat())
                    for case in population
                }
            ),
        }
    )
    one_per_issuer: dict[str, EvolutionCase] = {}
    for case in sorted(
        population,
        key=lambda item: _canonical_hash(
            {
                "seed": seed,
                "company_id": item.company_id,
                "case_id": item.case_id,
                "prediction_time": item.prediction_time.isoformat(),
            }
        ),
    ):
        one_per_issuer.setdefault(case.company_id, case)
    ordered = tuple(
        sorted(
            one_per_issuer.values(),
            key=lambda item: _canonical_hash(
                {"seed": seed, "issuer": item.company_id, "case": item.case_id}
            ),
        )
    )
    buckets = {
        True: [case for case in ordered if case.ground_truth.is_surge],
        False: [case for case in ordered if not case.ground_truth.is_surge],
    }
    interleaved: list[EvolutionCase] = []
    for index in range(max(len(buckets[True]), len(buckets[False]))):
        for label in (True, False):
            if index < len(buckets[label]):
                interleaved.append(buckets[label][index])
    selected = interleaved[: dev_limit + check_limit]
    check_target = min(check_limit, len(selected) // 2)
    dev_target = min(dev_limit, len(selected) - check_target)
    dev = selected[:dev_target]
    check = selected[dev_target : dev_target + check_target]
    issuer_ref = {
        case.company_id: "issuer-"
        + _canonical_hash({"seed": seed, "issuer": case.company_id})[:16]
        for case in selected
    }
    return {
        "schema_version": "slow-sampling-manifest-v1",
        "seed": seed,
        "population_hash": _canonical_hash(
            {
                "cases": sorted(
                    {
                        (case.case_id, case.company_id, case.prediction_time.isoformat())
                        for case in population
                    }
                )
            }
        ),
        "eligibility": {
            "source_split": "discovery",
            "one_case_per_issuer": True,
            "ordering_uses_outcome": False,
            "label_stratification": "binary_balanced",
        },
        "selection_order": [case.case_id for case in selected],
        "dev_case_ids": [case.case_id for case in dev],
        "check_case_ids": [case.case_id for case in check],
        "issuer_groups": {
            case.case_id: issuer_ref[case.company_id] for case in selected
        },
        "previously_exposed": [],
        "exclusions": [],
    }


def validate_slow_input(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one immutable Slow input without inventing missing v8 fields."""

    payload = dict(value)
    required = {
        "schema_version",
        "cycle_id",
        "contract_hash",
        "registry_hash",
        "source_cutoff",
        "source_manifest",
        "feedback_rows",
        "sampling_manifest",
        "previous_memory_head",
        "previous_memory_hash",
        "feedback_hash",
    }
    allowed_shapes = {
        frozenset(required),
        frozenset(required | {"research_targets"}),
    }
    if (
        set(payload) not in allowed_shapes
        or payload.get("schema_version") != "slow-input-v1"
    ):
        raise ValidationError("Slow input shape is invalid")
    if int(payload.get("cycle_id", 0)) < 1 or not str(
        payload.get("contract_hash", "")
    ):
        raise ValidationError("Slow input identity is invalid")
    rows = payload.get("feedback_rows")
    if not isinstance(rows, list):
        raise ValidationError("Slow input feedback_rows must be an array")
    refs: set[str] = set()
    content_hashes: dict[str, str] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ValidationError(f"Slow feedback row {index} must be an object")
        row = dict(raw)
        if row.get("kind") not in _SLOW_FEEDBACK_KINDS:
            raise ValidationError(f"Slow feedback row {index} kind is invalid")
        feedback_ref = str(row.get("feedback_ref", ""))
        source_refs = row.get("source_refs")
        if (
            not feedback_ref
            or feedback_ref in refs
            or not isinstance(source_refs, list)
            or not source_refs
            or any(not str(item) for item in source_refs)
        ):
            raise ValidationError(f"Slow feedback row {index} refs are invalid")
        refs.add(feedback_ref)
        content = row.get("event", row.get("artifact"))
        if content is None:
            raise ValidationError(f"Slow feedback row {index} content is missing")
        content_hashes[feedback_ref] = _canonical_hash(content)
    source_rows = payload.get("source_manifest")
    if not isinstance(source_rows, list):
        raise ValidationError("Slow input source_manifest must be an array")
    source_by_ref: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(source_rows):
        if not isinstance(raw, Mapping):
            raise ValidationError(f"Slow source manifest row {index} is invalid")
        ref = str(raw.get("ref", ""))
        if not ref or ref in source_by_ref:
            raise ValidationError("Slow source manifest refs must be unique")
        visible_to = set(str(item) for item in raw.get("visible_to", ()))
        if (
            str(raw.get("content_hash", "")) != content_hashes.get(ref)
            or not visible_to
            or not visible_to <= _SLOW_SOURCE_ROLES
        ):
            raise ValidationError("Slow source manifest content or scope mismatch")
        source_by_ref[ref] = raw
    if set(source_by_ref) != refs:
        raise ValidationError("Slow source manifest must cover every feedback row")
    if payload["feedback_hash"] != _canonical_hash({"feedback_rows": rows}):
        raise ValidationError("Slow input feedback hash mismatch")
    sampling = payload.get("sampling_manifest")
    if not isinstance(sampling, Mapping) or sampling.get("schema_version") != (
        "slow-sampling-manifest-v1"
    ):
        raise ValidationError("Slow input sampling manifest is invalid")
    dev = set(str(item) for item in sampling.get("dev_case_ids", ()))
    check = set(str(item) for item in sampling.get("check_case_ids", ()))
    groups = dict(sampling.get("issuer_groups", {}))
    if dev & check or ({groups.get(item) for item in dev} & {groups.get(item) for item in check}):
        raise ValidationError("Slow dev/check samples must be issuer-disjoint")
    research_targets = payload.get("research_targets", [])
    if not isinstance(research_targets, list) or any(
        not isinstance(item, Mapping)
        or not str(item.get("target_id", ""))
        or not isinstance(item.get("group_manifest"), Mapping)
        or not isinstance(item.get("sampling_manifest"), Mapping)
        for item in research_targets
    ):
        raise ValidationError("Slow input research targets are invalid")
    return payload


def validate_slow_memory(
    value: Mapping[str, Any],
    *,
    available_feedback_refs: Iterable[str],
    available_source_refs: Iterable[str],
    available_lesson_refs: Iterable[str] = (),
) -> dict[str, Any]:
    """Validate one append-only memory delta and its complete reference graph."""

    payload = dict(value)
    required = {
        "schema_version",
        "cycle_id",
        "contract_hash",
        "input_hash",
        "parent_memory_hash",
        "reflection_work_hash",
        "status",
        "processed_feedback_refs",
        "pending_feedback_refs",
        "episode_reflections",
        "lesson_additions",
        "model_view_manifest",
        "usage_ref",
        "failure_ref",
    }
    if set(payload) != required or payload.get("schema_version") != "slow-memory-v1":
        raise ValidationError("Slow memory shape is invalid")
    status = payload.get("status")
    if status not in _SLOW_MEMORY_STATUSES:
        raise ValidationError("Slow memory status is invalid")
    available_feedback = set(available_feedback_refs)
    processed = tuple(str(item) for item in payload["processed_feedback_refs"])
    pending = tuple(str(item) for item in payload["pending_feedback_refs"])
    if set(processed) & set(pending) or not set(processed) <= available_feedback:
        raise ValidationError("Slow memory feedback consumption is invalid")
    if status == "failed" and processed:
        raise ValidationError("failed Slow memory cannot consume feedback")
    if status == "reused" and (processed or payload["episode_reflections"] or payload["lesson_additions"]):
        raise ValidationError("reused Slow memory cannot append content")
    model_view = payload["model_view_manifest"]
    if not isinstance(model_view, Mapping):
        raise ValidationError("Slow memory model view manifest is invalid")
    canonicalized = model_view.get("canonicalized_nested_refs", {})
    if not isinstance(canonicalized, Mapping) or any(
        not isinstance(source_ref, str)
        or not source_ref
        or not isinstance(owner_ref, str)
        or owner_ref not in processed
        for source_ref, owner_ref in canonicalized.items()
    ):
        raise ValidationError("Slow memory canonicalized refs are invalid")
    sources = set(available_source_refs)
    episode_refs: set[str] = set()
    for index, raw in enumerate(payload["episode_reflections"]):
        if not isinstance(raw, Mapping):
            raise ValidationError(f"Slow episode {index} must be an object")
        episode = dict(raw)
        if "brief" in episode or "kind" in episode:
            if not isinstance(episode.get("kind"), str) or episode.get("kind") not in {"fact", "hypothesis", "action"} or not isinstance(episode.get("brief"), str) or not episode["brief"].strip():
                raise ValidationError(f"Slow episode {index} authored brief is invalid")
        episode_ref = str(episode.get("episode_ref", ""))
        source_refs = {str(item) for item in episode.get("source_refs", ())}
        if (
            not episode_ref
            or episode_ref in episode_refs
            or not source_refs
            or not source_refs <= sources
            or not str(episode.get("reflection", "")).strip()
        ):
            raise ValidationError(f"Slow episode {index} source closure is invalid")
        episode_refs.add(episode_ref)
    known_lessons = set(available_lesson_refs)
    additions = payload["lesson_additions"]
    addition_refs = {str(item.get("lesson_id", "")) for item in additions if isinstance(item, Mapping)}
    if "" in addition_refs or known_lessons & addition_refs:
        raise ValidationError("Slow lesson ids are invalid")
    resolvable = sources | episode_refs | known_lessons | addition_refs
    for index, raw in enumerate(additions):
        if not isinstance(raw, Mapping):
            raise ValidationError(f"Slow lesson {index} must be an object")
        lesson = dict(raw)
        if "brief" in lesson or "kind" in lesson:
            if not isinstance(lesson.get("kind"), str) or lesson.get("kind") not in {"fact", "hypothesis", "action"} or not isinstance(lesson.get("brief"), str) or not lesson["brief"].strip():
                raise ValidationError(f"Slow lesson {index} authored brief is invalid")
            lower_sources = sources | episode_refs | known_lessons
            if not set(lesson.get("support_refs", ())) <= lower_sources:
                raise ValidationError(f"Slow lesson {index} support requires actual lower-level sources")
            if any(lesson.get("lesson_id") in lesson.get(field, ()) for field in (
                "support_refs", "counterevidence_refs", "qualifies_refs", "challenges_refs",
            )):
                raise ValidationError(f"Slow lesson {index} cannot cite itself")
        cited = {
            str(item)
            for key in (
                "support_refs",
                "counterevidence_refs",
                "qualifies_refs",
                "challenges_refs",
            )
            for item in lesson.get(key, ())
        }
        if (
            not str(lesson.get("guidance", "")).strip()
            or not str(lesson.get("applicable_scope", "")).strip()
            or not str(lesson.get("limitations", "")).strip()
            or not set(str(item) for item in lesson.get("support_refs", ()))
            or not cited <= resolvable
        ):
            raise ValidationError(f"Slow lesson {index} reference graph is invalid")
    return payload


def validate_slow_experiments(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a sealed index that retains every terminal Slow work attempt."""

    payload = dict(value)
    required = {
        "schema_version",
        "cycle_id",
        "contract_hash",
        "input_hash",
        "memory_hash",
        "attempts",
    }
    if set(payload) != required or payload.get("schema_version") != "slow-experiments-v1":
        raise ValidationError("Slow experiments shape is invalid")
    work_ids: set[str] = set()
    for index, raw in enumerate(payload["attempts"]):
        if not isinstance(raw, Mapping):
            raise ValidationError(f"Slow experiment {index} must be an object")
        work_id = str(raw.get("work_id", ""))
        if not work_id or work_id in work_ids or not str(raw.get("stage", "")):
            raise ValidationError(f"Slow experiment {index} identity is invalid")
        if not str(raw.get("outcome", "")):
            raise ValidationError(f"Slow experiment {index} outcome is required")
        work_ids.add(work_id)
    return payload


def read_slow_sources(
    refs: Iterable[str],
    *,
    role_scope: str,
    source_catalog: Mapping[str, Mapping[str, Any]],
    budget_bytes: int,
    forbidden_refs: Iterable[str] = (),
    max_items: int | None = None,
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    """Resolve opaque Slow refs once, preserving whole entries and role scope."""

    if (
        role_scope not in _SLOW_SOURCE_ROLES
        or budget_bytes < 1
        or (max_items is not None and max_items < 1)
    ):
        raise ValidationError("Slow source read scope or budget is invalid")
    requested = tuple(dict.fromkeys(str(item) for item in refs))
    forbidden = set(str(item) for item in forbidden_refs)
    included: list[dict[str, Any]] = []
    deferred: list[dict[str, str]] = []
    used = 0
    for ref in requested:
        if ref in forbidden:
            raise ValidationError("Slow source ref is hidden from this role")
        raw = source_catalog.get(ref)
        if raw is None:
            raise ValidationError("unknown Slow source ref")
        scopes = {str(item) for item in raw.get("visible_to", ())}
        if role_scope not in scopes:
            raise ValidationError("Slow source ref is outside the role scope")
        if max_items is not None and len(included) >= max_items:
            deferred.append({"ref": ref, "reason": "item_limit"})
            continue
        entry = {"ref": ref, **dict(raw)}
        size = len(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        if used + size > budget_bytes:
            deferred.append({"ref": ref, "reason": "whole_entry_budget"})
            continue
        included.append(entry)
        used += size
    manifest = {
        "schema_version": "slow-source-view-v1",
        "role_scope": role_scope,
        "requested_refs": list(requested),
        "included_refs": [item["ref"] for item in included],
        "included_hashes": {
            item["ref"]: _canonical_hash(item) for item in included
        },
        "deferred": deferred,
        "available_count": len(requested),
        "included_count": len(included),
        "deferred_count": len(deferred),
        "bytes": used,
        "budget_bytes": budget_bytes,
        "max_items": max_items,
    }
    return tuple(included), manifest


def _prioritize_reflection_feedback(
    rows: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Order complete units by cycle then outcome-independent evidence value."""

    values = list(rows)
    subject_order: dict[str, int] = {}
    for row in values:
        subject = str(row.get("subject_ref", ""))
        subject_order.setdefault(subject, len(subject_order))

    def subject_rank(row: Mapping[str, Any]) -> tuple[int, int, int]:
        subject = str(row.get("subject_ref", ""))
        local = re.fullmatch(r"cycle-(\d+)", subject)
        if local is not None:
            return 0, -int(local.group(1)), subject_order[subject]
        imported = re.search(r":cycle-(\d+)$", subject)
        if imported is not None:
            return 1, -int(imported.group(1)), subject_order[subject]
        return 2, 0, subject_order[subject]

    def stage_rank(row: Mapping[str, Any]) -> int:
        ref = str(row.get("feedback_ref", ""))
        ordered_markers = (
            ":slow_loop_result:summary",
            ":slow_loop_validation:summary",
            ":slow_loop_validation:effect-",
            ":slow_loop_validation:fixture-",
            ":slow_loop_validation:mining-decision-E2-",
            ":slow_loop_validation:mining-decision-H3-",
            ":slow_loop_validation:mining-decision-H1-",
            ":slow_loop_validation:mining-exploration",
            ":slow_loop_validation:mining-hypothesis",
            ":slow_loop_validation:update-target-",
            ":slow_loop_validation:update-summary",
            ":slow_memory:summary",
            ":slow_memory:lesson-",
            ":slow_memory:episode-",
            ":slow_experiments:attempt-",
            ":slow_input:feedback-",
        )
        return next(
            (
                index
                for index, marker in enumerate(ordered_markers)
                if marker in ref
            ),
            len(ordered_markers),
        )

    return sorted(
        values,
        key=lambda row: (
            subject_rank(row),
            stage_rank(row),
            str(row.get("feedback_ref", "")),
        ),
    )


def slow_method_memory_sources(
    deltas: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Register exact authored memory originals for the existing scoped resolver."""
    result: dict[str, dict[str, Any]] = {}
    for delta in deltas:
        for kind, field, identity_field in (
            ("episode", "episode_reflections", "episode_ref"),
            ("lesson", "lesson_additions", "lesson_id"),
        ):
            for value in delta.get(field, ()):
                if not isinstance(value, Mapping) or not value.get("brief"):
                    continue
                ref = f"slow-memory:{int(delta.get('cycle_id', 0))}:{kind}:{value[identity_field]}"
                if ref in result:
                    raise ValidationError("Slow method-memory entry refs must be unique")
                result[ref] = {
                    "visible_to": sorted(_SLOW_SOURCE_ROLES),
                    "content": deepcopy(dict(value)),
                }
    return result


def project_slow_method_memory(
    deltas: Iterable[Mapping[str, Any]],
    *,
    budget_bytes: int,
) -> dict[str, Any]:
    """Build one bounded whole-entry view without rewriting stored memory."""

    if budget_bytes < 1:
        raise ValidationError("Slow method-memory budget must be positive")
    source_deltas = tuple(dict(item) for item in deltas)
    entry_rows: list[tuple[str, int, str, dict[str, Any]]] = []
    seen_refs: set[str] = set()
    for delta_index in range(len(source_deltas) - 1, -1, -1):
        delta = source_deltas[delta_index]
        cycle_id = int(delta.get("cycle_id", 0))
        episodes = tuple(
            dict(item)
            for item in delta.get("episode_reflections", ())
            if isinstance(item, Mapping)
        )
        lessons = tuple(
            dict(item)
            for item in delta.get("lesson_additions", ())
            if isinstance(item, Mapping)
        )
        for index in range(max(len(episodes), len(lessons))):
            for kind, values, identity_field in (
                ("episode", episodes, "episode_ref"),
                ("lesson", lessons, "lesson_id"),
            ):
                if index >= len(values):
                    continue
                value = values[index]
                identity = str(value.get(identity_field, index + 1))
                ref = f"slow-memory:{cycle_id}:{kind}:{identity}"
                if ref in seen_refs:
                    raise ValidationError("Slow method-memory entry refs must be unique")
                seen_refs.add(ref)
                entry_rows.append((ref, delta_index, kind, value))

    requested_refs = tuple(row[0] for row in entry_rows)
    included_refs: list[str] = []

    def brief_entry(ref: str, kind: str, value: Mapping[str, Any]) -> dict[str, Any]:
        projected = dict(value)
        if value.get("brief") and value.get("kind") in {"fact", "hypothesis", "action"}:
            projected.pop("reflection" if kind == "episode" else "guidance", None)
            projected["original_ref"] = ref
            projected["original_hash"] = _canonical_hash(value)
        return projected

    def render(refs: Iterable[str]) -> dict[str, Any]:
        included = set(refs)
        projected = []
        for delta_index, delta in enumerate(source_deltas):
            cycle_id = int(delta.get("cycle_id", 0))
            projected.append(
                {
                    "schema_version": "slow-method-memory-delta-view-v1",
                    "cycle_id": cycle_id,
                    "status": str(delta.get("status", "")),
                    "memory_hash": _canonical_hash(delta),
                    "failure_ref": delta.get("failure_ref"),
                    "episode_reflections": [
                        brief_entry(ref, kind, value)
                        for ref, owner, kind, value in entry_rows
                        if ref in included
                        and owner == delta_index
                        and kind == "episode"
                    ],
                    "lesson_additions": [
                        brief_entry(ref, kind, value)
                        for ref, owner, kind, value in entry_rows
                        if ref in included
                        and owner == delta_index
                        and kind == "lesson"
                    ],
                }
            )
        manifest = {
            "schema_version": "slow-method-memory-view-v1",
            "budget_bytes": budget_bytes,
            "bytes": 0,
            "requested_refs": list(requested_refs),
            "included_refs": list(refs),
            "included_hashes": {
                ref: _canonical_hash(value)
                for ref, _owner, _kind, value in entry_rows
                if ref in included
            },
            "deferred": [
                {"ref": ref, "reason": "whole_entry_budget"}
                for ref in requested_refs
                if ref not in included
            ],
            "source_memory_hashes": [
                _canonical_hash(delta) for delta in source_deltas
            ],
        }
        result = {
            "memory_deltas": projected,
            "memory_view_manifest": manifest,
        }
        for _index in range(4):
            size = len(
                json.dumps(
                    result,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if manifest["bytes"] == size:
                break
            manifest["bytes"] = size
        return result

    if render(included_refs)["memory_view_manifest"]["bytes"] > budget_bytes:
        raise ValidationError("Slow method-memory manifest exceeds its budget")
    for ref in requested_refs:
        candidate_refs = [*included_refs, ref]
        candidate = render(candidate_refs)
        if candidate["memory_view_manifest"]["bytes"] <= budget_bytes:
            included_refs.append(ref)
    return render(included_refs)


def _comparison_ready_exploration_signature(
    signature: "SignalMiningSignature",
) -> tuple["SignalMiningSignature", tuple[str, ...]]:
    """Quarantine generic filing boilerplate before label reveal."""

    kept = tuple(
        observation
        for observation in signature.observations
        if _EXPLORATION_BOILERPLATE.search(observation.exact_span) is None
    )
    removed = len(signature.observations) - len(kept)
    if not removed:
        return signature, ()
    reason = (
        f"{removed} observation(s) were generic filing cover or registration "
        "boilerplate and are not comparison-ready",
    )
    return replace(
        signature,
        observations=kept,
        evidence_gaps=(*signature.evidence_gaps, *reason),
    ), reason


def _exploration_comparison_concepts(
    packets: Iterable[Mapping[str, Any]], *, limit: int = 12
) -> list[dict[str, Any]]:
    """Return frequent source-owned concepts without values or outcome labels."""

    inventory: dict[tuple[str, str, str, str], set[str]] = {}
    comparable_cases: dict[tuple[str, str, str, str], set[str]] = {}
    for packet in packets:
        case_ref = str(packet.get("case_ref", ""))
        for evidence in packet.get("evidence", ()):
            if not isinstance(evidence, Mapping):
                continue
            context = evidence.get("structured_context", {})
            if not isinstance(context, Mapping):
                continue
            for concept in context.get("concepts", ()):
                if not isinstance(concept, Mapping):
                    continue
                key = tuple(
                    str(concept.get(field, ""))
                    for field in ("taxonomy", "concept", "label", "unit")
                )
                if not key[1]:
                    continue
                inventory.setdefault(key, set()).add(case_ref)
                records = concept.get("records", ())
                if isinstance(records, (list, tuple)) and len({
                    str(record.get("exact_span"))
                    for record in records
                    if isinstance(record, Mapping) and record.get("exact_span")
                }) >= 2:
                    comparable_cases.setdefault(key, set()).add(case_ref)
    ranked = sorted(
        (key for key, refs in inventory.items() if len(refs) >= 2),
        key=lambda key: (
            -len(comparable_cases.get(key, ())),
            -len(inventory[key]),
            -_QUERYLESS_COMPANY_FACT_PRIORITY.get(key[1].casefold(), 0),
            key,
        ),
    )[:limit]
    return [
        {
            "taxonomy": key[0],
            "concept": key[1],
            "source_display_name": key[2],
            "unit": key[3],
            "case_count": len(inventory[key]),
        }
        for key in ranked
    ]


def _literal_only_signature_view(
    signature: "SignalMiningSignature",
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the label-reveal view without forwarding model-authored claims."""

    evidence_by_ref = {
        str(item.get("document_ref")): item
        for item in packet.get("evidence", ())
        if isinstance(item, Mapping) and item.get("document_ref")
    }

    def source_summary(
        document_ref: str,
        metadata: tuple[str, str, str, str] | None = None,
    ) -> str:
        evidence = evidence_by_ref.get(document_ref, {})
        source_type = str(evidence.get("source_type", "source"))
        prefix = f"Literal point-in-time excerpt from source_type={source_type}; "
        if metadata is not None:
            taxonomy, concept, label, unit = metadata
            prefix += (
                "source-owned structured context: "
                f"taxonomy={taxonomy}; concept={concept}; label={label}; unit={unit}; "
            )
        return prefix + "compare exact_span only."

    def structured_binding(
        observation: "SignalMiningObservation",
    ) -> tuple[tuple[str, str, str, str], tuple[str, ...]] | None:
        evidence = evidence_by_ref.get(observation.document_ref, {})
        matches: dict[tuple[str, str, str, str], tuple[set[str], list[str]]] = {}
        structured = evidence.get("structured_context")
        if isinstance(structured, Mapping):
            for concept in structured.get("concepts", ()):
                if not isinstance(concept, Mapping):
                    continue
                metadata = tuple(
                    str(concept.get(key, ""))
                    for key in ("taxonomy", "concept", "label", "unit")
                )
                matched_spans: set[str] = set()
                all_spans: list[str] = []
                for record in concept.get("records", ()):
                    record_span = (
                        record.get("exact_span")
                        if isinstance(record, Mapping)
                        else None
                    )
                    if not isinstance(record_span, str) or not record_span:
                        continue
                    all_spans.append(record_span)
                    if observation.exact_span in record_span:
                        matched_spans.add(record_span)
                if matched_spans:
                    prior_matched, prior_all = matches.setdefault(
                        metadata, (set(), [])
                    )
                    prior_matched.update(matched_spans)
                    prior_all.extend(all_spans)
        if len(matches) != 1:
            return None
        metadata, (matched_spans, all_spans) = next(iter(matches.items()))
        companions = (
            tuple(dict.fromkeys(all_spans))
            if len(matched_spans) == 1
            else ()
        )
        return metadata, companions

    observations: list[dict[str, str]] = []
    seen_literals: set[tuple[str, str]] = set()
    for observation in signature.observations:
        binding = structured_binding(observation)
        metadata = binding[0] if binding is not None else None
        key = (observation.document_ref, observation.exact_span)
        if key not in seen_literals:
            observations.append(
                {
                    "summary": source_summary(observation.document_ref, metadata),
                    "document_ref": observation.document_ref,
                    "exact_span": observation.exact_span,
                }
            )
            seen_literals.add(key)
        for companion in binding[1] if binding is not None else ():
            companion_key = (observation.document_ref, companion)
            if (
                companion_key in seen_literals
                or observation.exact_span in companion
                or len(companion) < 8
                or len(observations) >= 12
            ):
                continue
            observations.append(
                {
                    "summary": source_summary(observation.document_ref, metadata),
                    "document_ref": observation.document_ref,
                    "exact_span": companion,
                }
            )
            seen_literals.add(companion_key)

    return {
        "case_ref": signature.case_ref,
        "observations": observations,
        "evidence_gaps": list(signature.evidence_gaps),
    }


@dataclass(frozen=True)
class SignalCandidateValidation:
    """Fail-closed validation result before stable Signal promotion."""

    signal_ref: str
    accepted: bool
    reasons: tuple[str, ...]
    candidate_hash: str = ""
    executed_tests: int = 0


class SignalCandidateValidator:
    """Validate schema, executability, leakage, evidence, and uniqueness."""

    def __init__(
        self,
        registry: SignalRegistry,
        *,
        llm_runner: LLMSignalRunner | None,
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        forbidden_identity_terms: Iterable[str] = (),
    ) -> None:
        self.registry = registry
        self.llm_runner = llm_runner
        self.deterministic_functions = {
            **default_deterministic_signal_functions(),
            **dict(deterministic_functions or {}),
        }
        self.forbidden_identity_terms = tuple(
            sorted(
                {
                    str(item).strip()
                    for item in forbidden_identity_terms
                    if len(str(item).strip()) >= 3
                },
                key=len,
                reverse=True,
            )
        )

    def validate(
        self,
        spec: SignalSpec,
        *,
        skill: str | None,
        tests: Iterable[Mapping[str, Any]],
    ) -> SignalCandidateValidation:
        reasons: list[str] = []
        materialized_tests = tuple(dict(item) for item in tests)
        try:
            current = self.registry.latest_spec(spec.signal_id)
        except ValidationError:
            current = None
        if current is None and spec.version != 1:
            reasons.append("new signal must start at version 1")
        if current is not None and spec.version != current.version + 1:
            reasons.append("update must use exactly the next stable version")
        if current is not None and spec.category != current.category:
            reasons.append("update must preserve the stable category")
        if spec.modality is None:
            reasons.append("candidate must declare structured or narrative modality")
        if current is not None and spec.execution_type is not current.execution_type:
            reasons.append("update must preserve the stable execution type")
        if (
            current is not None
            and current.execution_type is SignalExecutionType.DETERMINISTIC
            and spec.function != current.function
        ):
            reasons.append("deterministic update must preserve the registered function")
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            if spec.function not in self.deterministic_functions:
                reasons.append("deterministic function is not registered")
            reasons.extend(self._measurement_semantic_reasons(spec))
        elif self.llm_runner is None or not (skill or "").strip():
            reasons.append("LLM executor or skill is unavailable")
        if not all(
            (
                spec.evidence_policy.require_source,
                spec.evidence_policy.require_timestamp,
                spec.evidence_policy.require_exact_span,
            )
        ):
            reasons.append("candidate weakens required evidence traceability")
        serialized = json.dumps(spec.to_dict(), sort_keys=True)
        serialized += " " + (skill or "")
        serialized += " " + json.dumps(materialized_tests, sort_keys=True)
        for phrase in (
            "ground truth",
            "outcome label",
            "realized return",
            "future price",
            "post-outcome",
        ):
            if phrase in serialized.casefold():
                reasons.append(f"obvious leakage phrase: {phrase}")
        for identity, prose_matcher, _url_matcher in _compiled_identity_aliases(
            self.forbidden_identity_terms, expand_aliases=False
        ):
            if prose_matcher.search(serialized):
                reasons.append(f"discovery identity leaked into candidate: {identity}")
        normalized = _normalize_semantics(spec.description)
        behavior_identity = self._behavior_identity(spec, skill)
        for card in self.registry.list_signal_cards():
            if card.signal_id == spec.signal_id:
                continue
            if _normalize_semantics(card.description) == normalized:
                reasons.append(f"semantic duplicate of stable signal {card.signal_id}")
                break
            stable = self.registry.load_spec(card.ref)
            if self._behavior_identity(
                stable, self.registry.load_skill(card.ref)
            ) == behavior_identity:
                reasons.append(
                    f"execution-semantic duplicate of stable signal {card.signal_id}"
                )
                break
        executed_tests = 0
        if not materialized_tests:
            reasons.append("candidate requires non-empty executable fixtures")
        elif not reasons:
            for index, fixture in enumerate(materialized_tests):
                try:
                    self._execute_fixture(spec, skill, fixture, index=index)
                    executed_tests += 1
                except (EvolutionControlFlow, OpenAIClientError):
                    raise
                except Exception as exc:
                    reasons.append(f"fixture {index + 1} failed: {exc}")
        return SignalCandidateValidation(
            signal_ref=spec.ref,
            accepted=not reasons,
            reasons=tuple(reasons),
            executed_tests=executed_tests,
        )

    @staticmethod
    def _measurement_semantic_reasons(spec: SignalSpec) -> tuple[str, ...]:
        """Reject known deterministic functions mislabeled as another concept."""

        concepts = {
            "financial.revenue_growth_yoy": (("revenue", "growth"),),
            "financial.revenue_acceleration": (("revenue", "accelerat"),),
            "financial.gross_margin_change": (("gross", "margin"),),
            "financial.operating_cash_flow_margin": (
                ("operating", "cash", "flow", "margin"),
            ),
            "financial.net_share_retirement_yoy": (
                ("share", "retirement"),
                ("share", "dilution"),
            ),
            "financial.cash_to_current_liabilities_ratio": (
                ("cash", "current", "liabilit", "ratio"),
            ),
            "financial.cash_burn_rate_elevated": (
                ("cash", "burn", "rate"),
            ),
            "financial.liquidity_runway_months": (
                ("liquidity", "runway", "month"),
            ),
            "market.max_drawdown_1y": (("drawdown",),),
            "market.price_momentum_126d": (("momentum",), ("total", "return")),
            "company.market_cap": (("market", "capital"), ("market", "cap")),
            "financial.cash_reserves": (("cash",),),
            "news.negative_word_count": (("negative", "word"),),
        }
        alternatives = concepts.get(str(spec.function))
        if alternatives is None:
            return ()
        description = _normalize_semantics(spec.description)
        if any(all(token in description for token in group) for group in alternatives):
            return ()
        return (
            "definition-to-implementation mismatch: description does not name "
            f"the concept measured by {spec.function}",
        )

    @staticmethod
    def _behavior_identity(spec: SignalSpec, skill: str | None) -> str:
        """Return a rename-resistant first-pass execution identity."""

        return _canonical_hash(
            {
                "modality": (
                    spec.modality.value if spec.modality is not None else None
                ),
                "execution_type": spec.execution_type.value,
                "function": spec.function,
                "skill": _normalize_semantics(skill or ""),
                "source_types": list(spec.source_types),
                "retrieval": spec.retrieval_policy.to_dict(),
                "parameters": dict(spec.parameters),
            }
        )

    def _execute_fixture(
        self,
        spec: SignalSpec,
        skill: str | None,
        fixture: Mapping[str, Any],
        *,
        index: int,
    ) -> None:
        name = str(fixture.get("name", "")).strip()
        if not name:
            raise ValidationError("fixture name is required")
        expected = SignalValue(str(fixture["expected"]))
        as_of = datetime.fromisoformat(
            str(fixture.get("as_of", "2025-01-01T00:00:00+00:00"))
        )
        _require_aware_datetime(as_of, "candidate fixture as_of")
        company_id = str(fixture.get("company_id", f"candidate_fixture_{index + 1}"))
        _validate_id(company_id, "candidate fixture company_id")
        documents_data = fixture.get("documents")
        if not isinstance(documents_data, list) or not documents_data:
            raise ValidationError("fixture requires point-in-time documents")
        documents: list[RawInfoDocument] = []
        for document_index, raw_document in enumerate(documents_data):
            if not isinstance(raw_document, Mapping):
                raise ValidationError("fixture document must be an object")
            published_at = datetime.fromisoformat(
                str(
                    raw_document.get(
                        "published_at",
                        raw_document.get("available_at", as_of.isoformat()),
                    )
                )
            )
            available_at = datetime.fromisoformat(
                str(raw_document.get("available_at", published_at.isoformat()))
            )
            source_type = str(raw_document["source_type"])
            if not source_types_compatible((source_type,), spec.source_types):
                raise ValidationError("fixture source_type is outside candidate retrieval")
            documents.append(
                RawInfoDocument.create(
                    document_id=str(
                        raw_document.get(
                            "document_id",
                            f"candidate_fixture_{index + 1}_{document_index + 1}",
                        )
                    ),
                    company_id=company_id,
                    source_type=source_type,
                    published_at=published_at,
                    available_at=available_at,
                    content=str(raw_document["content"]),
                    metadata=dict(raw_document.get("metadata", {})),
                )
            )
        if not any(document.available_at <= as_of for document in documents):
            # A closed fixture corpus with zero point-in-time visible
            # documents is unavailable by construction: no signal can cite
            # evidence from an empty corpus, and fixture corpora never
            # acquire, so resolving or executing would misreport this
            # legitimate abstention as a technical adapter failure.
            if expected is SignalValue.UNAVAILABLE:
                return
            raise ValidationError(
                "fixture expects "
                f"{expected.value} but provides no point-in-time visible "
                "documents"
            )
        snapshot_payload = {
            "spec": spec.to_dict(),
            "skill": (skill or "").rstrip(),
        }
        snapshot_hash = hashlib.sha256(
            json.dumps(snapshot_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        executor = SignalExecutor(
            FrozenSignalRegistry(
                version=0,
                registry_hash=snapshot_hash,
                specs=(spec,),
                skills=({spec.ref: skill} if skill is not None else {}),
            ),
            RawInfoStore(documents=documents),
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_runner,
        )
        batch = executor.execute_batch(
            (spec.ref,), company_id=company_id, as_of=as_of
        )
        result = batch.results[0]
        if result.execution_status not in {
            SignalExecutionStatus.SUCCESS, SignalExecutionStatus.DOMAIN_UNAVAILABLE
        }:
            raise ValidationError(
                f"technical execution failure: {result.execution_status.value}: "
                f"{result.execution_error_code}: {result.execution_error_message}"
            )
        if result.value is not expected:
            resolution = batch.resolutions[0]
            detail = resolution.gap.message if resolution.gap is not None else "no data gap"
            interpretation = str(result.interpretation).strip()
            judge_note = (
                f"; executor interpretation: {interpretation[:400]}"
                if interpretation
                else ""
            )
            raise ValidationError(
                f"expected {expected.value}, received {result.value.value}; "
                f"resolution={resolution.status}; {detail}{judge_note}"
            )


@dataclass(frozen=True)
class SignalMiningConfig:
    """Bounded local orchestration limits for the two Mining tracks."""

    hypothesis_limit: int = 3
    selected_hypothesis_limit: int = 2
    case_pool_limit: int = 32
    ranking_case_limit: int = 12
    h2_profile_scan_limit: int = 96
    h2_min_ready_issuers: int = 16
    h2_min_ready_per_class: int = 4
    induction_cases_per_class: int = 4
    validation_cases_per_class: int = 8
    exploration_interval: int = 3
    evidence_documents_per_case: int = 4
    evidence_lookback_days: int = 365
    exploration_microbatch_size: int = 4
    reflection_feedback_limit: int = 12

    def __post_init__(self) -> None:
        positive_fields = (
            "hypothesis_limit",
            "selected_hypothesis_limit",
            "case_pool_limit",
            "ranking_case_limit",
            "h2_profile_scan_limit",
            "h2_min_ready_issuers",
            "h2_min_ready_per_class",
            "induction_cases_per_class",
            "validation_cases_per_class",
            "exploration_interval",
            "evidence_documents_per_case",
            "evidence_lookback_days",
            "exploration_microbatch_size",
            "reflection_feedback_limit",
        )
        if any(getattr(self, name) < 1 for name in positive_fields):
            raise ValidationError("Signal Mining limits must be positive")
        if self.selected_hypothesis_limit > self.hypothesis_limit:
            raise ValidationError(
                "selected Signal Mining hypotheses cannot exceed the portfolio limit"
            )
        if self.h2_profile_scan_limit < self.case_pool_limit:
            raise ValidationError("H2 profile scan limit must cover the target pool")
        if self.h2_min_ready_issuers > self.case_pool_limit:
            raise ValidationError("H2 minimum ready issuers exceeds the target pool")
        if self.evidence_documents_per_case > 10:
            raise ValidationError(
                "Signal Mining evidence_documents_per_case cannot exceed 10"
            )

    def to_dict(self) -> dict[str, int]:
        return {
            "hypothesis_limit": self.hypothesis_limit,
            "selected_hypothesis_limit": self.selected_hypothesis_limit,
            "case_pool_limit": self.case_pool_limit,
            "ranking_case_limit": self.ranking_case_limit,
            "h2_profile_scan_limit": self.h2_profile_scan_limit,
            "h2_min_ready_issuers": self.h2_min_ready_issuers,
            "h2_min_ready_per_class": self.h2_min_ready_per_class,
            "induction_cases_per_class": self.induction_cases_per_class,
            "validation_cases_per_class": self.validation_cases_per_class,
            "exploration_interval": self.exploration_interval,
            "evidence_documents_per_case": self.evidence_documents_per_case,
            "evidence_lookback_days": self.evidence_lookback_days,
            "exploration_microbatch_size": self.exploration_microbatch_size,
            "reflection_feedback_limit": self.reflection_feedback_limit,
        }


@dataclass(frozen=True)
class SignalMiningHypothesis:
    """One falsifiable, company-agnostic Signal Mining hypothesis."""

    hypothesis_id: str
    statement: str
    applicability: str
    expected_positive_pattern: str
    source_types: tuple[str, ...]
    query: str
    falsifiers: tuple[str, ...]
    lookback_days: int = 365
    measurement: Mapping[str, str] | None = None
    expected_direction: str | None = None
    comparison: str = "fixed_discovery_positive_vs_control"

    def __post_init__(self) -> None:
        _validate_id(self.hypothesis_id, "mining hypothesis_id")
        text_fields = (
            self.statement,
            self.applicability,
            self.expected_positive_pattern,
            self.query,
        )
        if any(not value.strip() for value in text_fields):
            raise ValidationError("Signal Mining hypothesis text cannot be empty")
        if not self.source_types or any(not item.strip() for item in self.source_types):
            raise ValidationError("Signal Mining hypothesis requires source_types")
        if len(set(self.source_types)) != len(self.source_types):
            raise ValidationError("Signal Mining hypothesis source_types must be unique")
        if not self.falsifiers or any(not item.strip() for item in self.falsifiers):
            raise ValidationError("Signal Mining hypothesis requires falsifiers")
        if self.lookback_days < 1 or self.lookback_days > 1825:
            raise ValidationError("Signal Mining lookback_days must be in [1, 1825]")
        if self.measurement is not None:
            required_measurement = {"observable", "value_kind", "normalization"}
            if set(self.measurement) != required_measurement or any(
                not str(self.measurement[key]).strip() for key in required_measurement
            ):
                raise ValidationError(
                    "Signal Mining measurement requires observable, value_kind, and "
                    "normalization"
                )
        if self.expected_direction is not None and self.expected_direction not in {
            "higher_in_positive",
            "lower_in_positive",
            "more_frequent_in_positive",
            "less_frequent_in_positive",
            "different_between_groups",
        }:
            raise ValidationError("Signal Mining expected_direction is invalid")
        if self.comparison != "fixed_discovery_positive_vs_control":
            raise ValidationError("Signal Mining comparison must use fixed groups")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "applicability": self.applicability,
            "expected_positive_pattern": self.expected_positive_pattern,
            "source_types": list(self.source_types),
            "query": self.query,
            "falsifiers": list(self.falsifiers),
            "lookback_days": self.lookback_days,
        }
        if self.measurement is not None:
            result.update(
                {
                    "measurement": dict(self.measurement),
                    "expected_direction": self.expected_direction,
                    "comparison": self.comparison,
                }
            )
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningHypothesis":
        required = {
            "hypothesis_id",
            "statement",
            "applicability",
            "expected_positive_pattern",
            "source_types",
            "query",
            "falsifiers",
            "lookback_days",
        }
        structured = {"measurement", "expected_direction", "comparison"}
        if frozenset(data) not in {
            frozenset(required),
            frozenset(required | structured),
        }:
            raise ValidationError(
                "Signal Mining hypothesis requires exactly: "
                + ", ".join(sorted(required))
                + " with optional structured v2 fields"
            )
        return cls(
            hypothesis_id=str(data["hypothesis_id"]),
            statement=str(data["statement"]),
            applicability=str(data["applicability"]),
            expected_positive_pattern=str(data["expected_positive_pattern"]),
            source_types=_json_string_array(data, "source_types"),
            query=str(data["query"]),
            falsifiers=_json_string_array(data, "falsifiers"),
            lookback_days=int(data["lookback_days"]),
            measurement=(
                {str(key): str(value) for key, value in data["measurement"].items()}
                if isinstance(data.get("measurement"), Mapping)
                else None
            ),
            expected_direction=(
                str(data["expected_direction"])
                if data.get("expected_direction") is not None
                else None
            ),
            comparison=str(
                data.get("comparison", "fixed_discovery_positive_vs_control")
            ),
        )


@dataclass(frozen=True)
class SignalMiningDecision:
    """A label-revealed contrast decision with an optional complete draft."""

    hypothesis_id: str
    disposition: str
    rationale: tuple[str, ...]
    candidate: Mapping[str, Any] | None = None
    sample_basis: Mapping[str, tuple[str, ...]] | None = None

    def __post_init__(self) -> None:
        _validate_id(self.hypothesis_id, "mining decision hypothesis_id")
        if self.disposition not in {
            "supported",
            "refine",
            "rejected",
            "inconclusive",
        }:
            raise ValidationError(
                "Mining disposition must be supported, refine, rejected, or inconclusive"
            )
        if not self.rationale or any(not item.strip() for item in self.rationale):
            raise ValidationError("Mining decision requires rationale")
        if self.disposition == "supported" and not isinstance(self.candidate, Mapping):
            raise ValidationError("supported Mining decision requires a candidate")
        if self.disposition != "supported" and self.candidate is not None:
            raise ValidationError("only a supported Mining decision may carry a candidate")
        if self.candidate is not None:
            object.__setattr__(self, "candidate", dict(self.candidate))
        if self.sample_basis is not None:
            required_basis = {"positive_refs", "control_refs"}
            if set(self.sample_basis) != required_basis:
                raise ValidationError(
                    "Mining sample_basis requires positive_refs and control_refs"
                )
            normalized_basis: dict[str, tuple[str, ...]] = {}
            for key in sorted(required_basis):
                raw_refs = self.sample_basis[key]
                if not isinstance(raw_refs, (list, tuple)) or any(
                    not isinstance(item, str) for item in raw_refs
                ):
                    raise ValidationError(
                        "Mining sample_basis values must be string arrays"
                    )
                normalized_basis[key] = tuple(raw_refs)
            if any(
                not refs or any(not ref for ref in refs) or len(set(refs)) != len(refs)
                for refs in normalized_basis.values()
            ) or set(normalized_basis["positive_refs"]) & set(
                normalized_basis["control_refs"]
            ):
                raise ValidationError(
                    "Mining sample_basis requires non-empty, unique, disjoint refs"
                )
            object.__setattr__(self, "sample_basis", normalized_basis)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "hypothesis_id": self.hypothesis_id,
            "disposition": self.disposition,
            "rationale": list(self.rationale),
            "candidate": (dict(self.candidate) if self.candidate is not None else None),
        }
        if self.sample_basis is not None:
            result["sample_basis"] = {
                key: list(refs) for key, refs in self.sample_basis.items()
            }
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningDecision":
        required = {"hypothesis_id", "disposition", "rationale", "candidate"}
        if set(data) not in (required, required | {"sample_basis"}):
            raise ValidationError(
                "Signal Mining decision requires exactly: "
                + ", ".join(sorted(required))
            )
        raw_candidate = data["candidate"]
        if raw_candidate is not None and not isinstance(raw_candidate, Mapping):
            raise ValidationError("Mining candidate must be an object or null")
        raw_sample_basis = data.get("sample_basis")
        if "sample_basis" in data and not isinstance(raw_sample_basis, Mapping):
            raise ValidationError("Mining sample_basis must be an object")
        parsed_sample_basis: dict[str, tuple[str, ...]] | None = None
        if isinstance(raw_sample_basis, Mapping):
            parsed_sample_basis = {}
            for key, value in raw_sample_basis.items():
                if not isinstance(value, list) or any(
                    not isinstance(item, str) for item in value
                ):
                    raise ValidationError(
                        "Mining sample_basis values must be string arrays"
                    )
                parsed_sample_basis[str(key)] = tuple(value)
        return cls(
            hypothesis_id=str(data["hypothesis_id"]),
            disposition=str(data["disposition"]),
            rationale=_json_string_array(data, "rationale"),
            candidate=(dict(raw_candidate) if raw_candidate is not None else None),
            sample_basis=parsed_sample_basis,
        )


@dataclass(frozen=True)
class SignalMiningObservation:
    """One locally verifiable observation over a model-visible evidence span."""

    summary: str
    document_ref: str
    exact_span: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.summary, str)
            or not self.summary.strip()
            or len(self.summary) > 500
        ):
            raise ValidationError(
                "Mining observation summary must contain 1-500 characters"
            )
        _validate_id(self.document_ref, "mining observation document_ref")
        if len(self.exact_span) < 8:
            raise ValidationError(
                "Mining observation exact_span must contain at least 8 characters"
            )
        visible_tokens = re.findall(
            r"[A-Za-z0-9]+", self.exact_span.replace(_MASKED_IDENTITY_VALUE, "")
        )
        if len(visible_tokens) < 2:
            raise ValidationError(
                "Mining observation exact_span must contain at least two visible tokens"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "summary": self.summary,
            "document_ref": self.document_ref,
            "exact_span": self.exact_span,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningObservation":
        required = {"summary", "document_ref", "exact_span"}
        if set(data) != required:
            raise ValidationError(
                "Mining observation requires exactly: "
                + ", ".join(sorted(required))
            )
        return cls(
            summary=str(data["summary"]),
            document_ref=str(data["document_ref"]),
            exact_span=str(data["exact_span"]),
        )


@dataclass(frozen=True)
class SignalMiningSignature:
    """One outcome-hidden observable signature extracted from Raw Info."""

    case_ref: str
    observations: tuple[SignalMiningObservation, ...]
    evidence_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_id(self.case_ref, "mining signature case_ref")
        if any(
            not isinstance(item, SignalMiningObservation)
            for item in self.observations
        ):
            raise ValidationError("Mining signature observations must be objects")
        if len(self.observations) > 6:
            raise ValidationError("Mining signature allows at most six observations")
        if not self.observations and not self.evidence_gaps:
            raise ValidationError(
                "Mining signature without observations requires an evidence gap"
            )
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.evidence_gaps
        ):
            raise ValidationError("Mining signature evidence gaps must be non-empty")
        identities = [
            (item.document_ref, item.exact_span) for item in self.observations
        ]
        if len(set(identities)) != len(identities):
            raise ValidationError("Mining signature observations must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_ref": self.case_ref,
            "observations": [item.to_dict() for item in self.observations],
            "evidence_gaps": list(self.evidence_gaps),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalMiningSignature":
        required = {"case_ref", "observations", "evidence_gaps"}
        if set(data) != required:
            raise ValidationError(
                "Signal Mining signature requires exactly: "
                + ", ".join(sorted(required))
            )
        observations: list[SignalMiningObservation] = []
        for item in _json_array(data, "observations"):
            if not isinstance(item, Mapping):
                raise ValidationError("Mining observation must be an object")
            observations.append(SignalMiningObservation.from_dict(item))
        return cls(
            case_ref=str(data["case_ref"]),
            observations=tuple(observations),
            evidence_gaps=_json_string_array(data, "evidence_gaps", required=False),
        )


def validate_signal_mining_signatures(
    signatures: Iterable[SignalMiningSignature],
    evidence_packets: Iterable[Mapping[str, Any]],
) -> tuple[SignalMiningSignature, ...]:
    """Bind every E1 observation to one exact supplied model-visible literal."""

    values = tuple(signatures)
    packets = tuple(evidence_packets)
    packet_by_ref: dict[str, Mapping[str, Any]] = {}
    for packet_index, packet in enumerate(packets):
        if not isinstance(packet, Mapping):
            raise ValidationError(
                f"exploration evidence packet must be an object at cases[{packet_index}]"
            )
        case_ref = packet.get("case_ref")
        if not isinstance(case_ref, str) or not case_ref:
            raise ValidationError(
                "exploration evidence packets require non-empty case_ref values"
            )
        _validate_id(case_ref, "exploration evidence case_ref")
        if case_ref in packet_by_ref:
            raise ValidationError(
                "exploration evidence packets require unique case_ref values"
            )
        packet_by_ref[case_ref] = packet
    expected_refs = set(packet_by_ref)
    actual_refs = [item.case_ref for item in values]
    if len(set(actual_refs)) != len(actual_refs) or set(actual_refs) != expected_refs:
        raise ValidationError(
            "exploration extraction must return one signature per supplied case_ref"
        )
    for signature_index, signature in enumerate(values):
        packet = packet_by_ref[signature.case_ref]
        evidence = packet.get("evidence", ())
        if not isinstance(evidence, (list, tuple)):
            raise ValidationError(
                "exploration evidence must be an array at "
                f"cases[{signature_index}].evidence"
            )
        documents: dict[str, tuple[str, ...]] = {}
        for evidence_index, item in enumerate(evidence):
            item_path = f"cases[{signature_index}].evidence[{evidence_index}]"
            if not isinstance(item, Mapping):
                raise ValidationError(
                    f"exploration evidence item must be an object at {item_path}"
                )
            document_ref = item.get("document_ref")
            content_excerpt = item.get("content_excerpt")
            if not isinstance(document_ref, str) or not document_ref:
                raise ValidationError(
                    f"exploration evidence requires document_ref at {item_path}"
                )
            _validate_id(document_ref, "exploration evidence document_ref")
            if not isinstance(content_excerpt, str):
                raise ValidationError(
                    f"exploration evidence requires content_excerpt at {item_path}"
                )
            if document_ref in documents:
                raise ValidationError(
                    f"exploration evidence document_ref must be unique at {item_path}"
                )
            allowed_spans = [content_excerpt] if content_excerpt else []
            structured = item.get("structured_context")
            if isinstance(structured, Mapping):
                for concept in structured.get("concepts", ()):
                    if not isinstance(concept, Mapping):
                        continue
                    for record in concept.get("records", ()):
                        if not isinstance(record, Mapping):
                            continue
                        exact_span = record.get("exact_span")
                        start = record.get("start")
                        end = record.get("end")
                        if (
                            isinstance(exact_span, str)
                            and exact_span
                            and type(start) is int
                            and type(end) is int
                            and 0 <= start < end
                        ):
                            allowed_spans.append(exact_span)
            documents[document_ref] = tuple(allowed_spans)
        if signature.observations and not documents:
            raise ValidationError(
                "Mining signature cannot observe an evidence-empty packet at "
                f"signatures[{signature_index}].observations"
            )
        for observation_index, observation in enumerate(signature.observations):
            path = (
                f"signatures[{signature_index}].observations[{observation_index}]"
            )
            allowed_spans = documents.get(observation.document_ref)
            if allowed_spans is None:
                raise ValidationError(
                    f"Mining observation uses an unknown document_ref at {path}.document_ref"
                )
            if not any(
                observation.exact_span in exact_span
                for exact_span in allowed_spans
            ):
                raise ValidationError(
                    "Mining observation exact_span is not a supplied literal "
                    "contained within one "
                    f"supplied record literal at {path}.exact_span"
                )
    return values


class SignalMiningModel(Protocol):
    """Four narrow structured roles used by the local Mining controller."""

    def reflect_feedback(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[Mapping[str, Any]]:
        """Return one append-only method-memory delta over exact feedback refs."""

    def request_slow_sources(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[str, ...]]:
        """Select at most one bounded set of runtime-owned opaque source refs."""

    def propose_hypotheses(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningHypothesis, ...]]:
        """Return a bounded hypothesis portfolio."""

    def contrast(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningDecision, ...]]:
        """Contrast exact positive/control evidence."""

    def extract_exploration(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningSignature, ...]]:
        """Extract outcome-hidden case signatures."""

    def discover_exploration(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningDecision, ...]]:
        """Discover label-associated candidates from frozen signatures."""


@dataclass(frozen=True)
class SignalUpdateDecision:
    """One semantic decision for an exact locally selected stable Signal."""

    signal_ref: str
    disposition: str
    problem_type: str
    rationale: tuple[str, ...]
    candidate: Mapping[str, Any] | None = None
    case_diagnostics: tuple[Mapping[str, Any], ...] = ()
    changed_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if re.fullmatch(
            r"[a-z0-9][a-z0-9_.:-]*:v[1-9][0-9]*", self.signal_ref
        ) is None:
            raise ValidationError("Signal Update signal_ref is invalid")
        if self.disposition not in {"no_change", "defer", "update"}:
            raise ValidationError(
                "Signal Update disposition must be no_change, defer, or update"
            )
        if not self.problem_type.strip():
            raise ValidationError("Signal Update problem_type must not be empty")
        if not self.rationale or any(not item.strip() for item in self.rationale):
            raise ValidationError("Signal Update requires non-empty rationale")
        if self.disposition == "update" and not isinstance(self.candidate, Mapping):
            raise ValidationError("Signal Update disposition update requires candidate")
        if self.disposition != "update" and self.candidate is not None:
            raise ValidationError(
                "only Signal Update disposition update may carry candidate"
            )
        changed_paths = tuple(str(item) for item in self.changed_paths)
        if any(not item.strip() for item in changed_paths) or len(
            set(changed_paths)
        ) != len(changed_paths):
            raise ValidationError(
                "Signal Update changed_paths must be unique non-empty strings"
            )
        if self.disposition != "update" and changed_paths:
            raise ValidationError("only Signal Update disposition update may change paths")
        if self.candidate is not None:
            object.__setattr__(self, "candidate", dict(self.candidate))
        object.__setattr__(
            self,
            "case_diagnostics",
            tuple(dict(item) for item in self.case_diagnostics),
        )
        object.__setattr__(self, "changed_paths", changed_paths)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "signal_ref": self.signal_ref,
            "disposition": self.disposition,
            "problem_type": self.problem_type,
            "rationale": list(self.rationale),
            "changed_paths": list(self.changed_paths),
            "candidate": dict(self.candidate) if self.candidate is not None else None,
        }
        if self.case_diagnostics:
            result["case_diagnostics"] = [
                dict(item) for item in self.case_diagnostics
            ]
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalUpdateDecision":
        required = {
            "signal_ref",
            "disposition",
            "problem_type",
            "rationale",
            "candidate",
        }
        optional = {"case_diagnostics", "changed_paths"}
        if not required.issubset(data) or set(data) - required - optional:
            raise ValidationError(
                "Signal Update decision requires exactly: "
                + ", ".join(sorted(required))
            )
        candidate = data["candidate"]
        if candidate is not None and not isinstance(candidate, Mapping):
            raise ValidationError("Signal Update candidate must be object or null")
        return cls(
            signal_ref=str(data["signal_ref"]),
            disposition=str(data["disposition"]),
            problem_type=str(data["problem_type"]),
            rationale=_json_string_array(data, "rationale"),
            changed_paths=tuple(
                str(item) for item in data.get("changed_paths", ())
            ),
            candidate=dict(candidate) if candidate is not None else None,
            case_diagnostics=tuple(
                dict(item)
                for item in data.get("case_diagnostics", ())
                if isinstance(item, Mapping)
            ),
        )


class SignalUpdateModel(Protocol):
    """One bounded semantic Signal Update role behind local data boundaries."""

    def update(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[SignalUpdateDecision]:
        """Return no_change, defer, or a complete vNext candidate."""

    def request_slow_sources(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[str, ...]]:
        """Select at most one bounded set of runtime-owned opaque source refs."""


_SIGNAL_UPDATE_TARGET_LIMIT = 3


@dataclass(frozen=True)
class SignalCandidateEffectiveness:
    """Paired Signal-level evidence required after contract validation."""

    signal_ref: str
    current_ref: str | None
    accepted: bool
    disposition: str
    reasons: tuple[str, ...]
    case_ids: tuple[str, ...]
    candidate_available: int
    candidate_decisive: int
    candidate_correct: int
    candidate_wrong: int
    candidate_execution_failed: int = 0
    current_available: int = 0
    current_decisive: int = 0
    current_correct: int = 0
    current_wrong: int = 0
    current_execution_failed: int = 0
    candidate_confusion: Mapping[str, int] = field(default_factory=dict)
    current_confusion: Mapping[str, int] = field(default_factory=dict)
    research_axis: Mapping[str, Any] = field(default_factory=dict)
    case_diagnostics: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.disposition not in {"promoted", "provisional", "rejected"}:
            raise ValidationError("invalid Signal candidate effectiveness disposition")
        if self.accepted != (self.disposition == "promoted"):
            raise ValidationError(
                "accepted Signal effectiveness must match promoted disposition"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "signal-candidate-effectiveness-v4",
            "signal_ref": self.signal_ref,
            "current_ref": self.current_ref,
            "accepted": self.accepted,
            "disposition": self.disposition,
            "reasons": list(self.reasons),
            "case_ids": list(self.case_ids),
            "candidate": {
                "available": self.candidate_available,
                "decisive": self.candidate_decisive,
                "directional_correct": self.candidate_correct,
                "directional_wrong": self.candidate_wrong,
                "execution_failed": self.candidate_execution_failed,
            },
            "current": {
                "available": self.current_available,
                "decisive": self.current_decisive,
                "directional_correct": self.current_correct,
                "directional_wrong": self.current_wrong,
                "execution_failed": self.current_execution_failed,
            },
            "candidate_confusion": dict(self.candidate_confusion),
            "current_confusion": dict(self.current_confusion),
            "research_axis": dict(self.research_axis),
            "case_diagnostics": [dict(item) for item in self.case_diagnostics],
        }


_PROVISIONAL_RESIDENT_LIMIT = 2
_PROVISIONAL_ACCUMULATION_HORIZON = 5
_POOLED_PROMOTION_DECISIVE_MINIMUM = 12
_POOLED_PROMOTION_SIGNIFICANCE = 0.10
_RECALL_FLOOR = 0.5
_DIRECTIONAL_FLOOR_REASON = (
    "candidate lacks positive directional evidence over controls"
)
_RECALL_FLOOR_REASON = (
    "candidate leaves over half of the positive-label check cases unflagged"
)


def _confusion_counts(
    values: Iterable[tuple[SignalValue, bool, SignalExecutionStatus]],
) -> dict[str, int]:
    """Confusion matrix over available cases, keyed by the surge class.

    A POSITIVE call on a surge case is TP, on a control case FP; an available
    surge case without a POSITIVE call (NEGATIVE or NEUTRAL) is FN, an
    available control case without one is TN. Unavailable executions stay
    outside the matrix — the availability floor already governs them.
    """

    tp = fp = fn = tn = 0
    for value, is_surge, execution_status in values:
        if execution_status not in {
            SignalExecutionStatus.SUCCESS,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        } or value is SignalValue.UNAVAILABLE:
            continue
        if value is SignalValue.POSITIVE:
            if is_surge:
                tp += 1
            else:
                fp += 1
        elif is_surge:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _positive_recall(confusion: Mapping[str, int]) -> float | None:
    denominator = int(confusion.get("tp", 0)) + int(confusion.get("fn", 0))
    if denominator <= 0:
        return None
    return int(confusion.get("tp", 0)) / denominator


def _binomial_tail_at_least(count: int, trials: int) -> float:
    """One-sided chance of at least ``count`` successes in fair ``trials``."""

    if trials <= 0 or count <= 0:
        return 1.0 if count <= 0 else 0.0
    return sum(comb(trials, i) for i in range(count, trials + 1)) / 2**trials


def _pooled_candidate_count(row: Mapping[str, Any], key: str) -> int:
    """Read one candidate count from either record shape.

    Effectiveness records serialize candidate counts under the nested
    ``candidate`` mapping (``decisive``, ``directional_correct``,
    ``directional_wrong``); a legacy flat ``candidate_*`` key is honored as
    a fallback so old rows never silently pool as zeros.
    """

    candidate = row.get("candidate")
    if isinstance(candidate, Mapping):
        return int(candidate.get(key, 0) or 0)
    return int(row.get(f"candidate_{key}", 0) or 0)


def pooled_provisional_decision(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply the pooled three-zone rule to one provisional resident.

    ``records`` are the resident's per-cycle paired-effectiveness records (its
    current cycle included). Zones: promote when pooled decisive evidence
    reaches the promotion significance and the pooled positive recall meets
    the recall floor; eliminate when the accumulation horizon passed with
    pooled evidence at or below chance, starved, or never covering the
    positive class; otherwise continue as a provisional resident.
    """

    rows = [dict(row) for row in records]
    decisive = sum(_pooled_candidate_count(row, "decisive") for row in rows)
    correct = sum(
        _pooled_candidate_count(row, "directional_correct") for row in rows
    )
    wrong = sum(
        _pooled_candidate_count(row, "directional_wrong") for row in rows
    )
    tp = sum(
        int(row.get("candidate_confusion", {}).get("tp", 0))
        for row in rows
        if isinstance(row.get("candidate_confusion"), Mapping)
    )
    fn = sum(
        int(row.get("candidate_confusion", {}).get("fn", 0))
        for row in rows
        if isinstance(row.get("candidate_confusion"), Mapping)
    )
    cycles = len(rows)
    counts = {
        "cycles": cycles,
        "decisive": decisive,
        "correct": correct,
        "wrong": wrong,
        "tp": tp,
        "fn": fn,
    }
    recall = tp / (tp + fn) if tp + fn > 0 else None
    if (
        decisive >= _POOLED_PROMOTION_DECISIVE_MINIMUM
        and _binomial_tail_at_least(correct, decisive)
        <= _POOLED_PROMOTION_SIGNIFICANCE
        and recall is not None
        and recall >= _RECALL_FLOOR
    ):
        return {
            "action": "promote",
            "reason": (
                f"pooled paired evidence reached promotion significance: "
                f"{correct}/{decisive} decisive correct over {cycles} cycles "
                f"with positive recall {recall:.0%}"
            ),
            "counts": counts,
        }
    if cycles >= _PROVISIONAL_ACCUMULATION_HORIZON and (
        correct < wrong
        or decisive < 4
        or (recall is not None and recall < _RECALL_FLOOR)
    ):
        return {
            "action": "eliminate",
            "reason": (
                f"pooled paired evidence stayed at or below chance over "
                f"{cycles} cycles: {correct} correct vs {wrong} wrong "
                f"({decisive} decisive"
                + (
                    f", positive recall {recall:.0%}"
                    if recall is not None
                    else ""
                )
                + ")"
            ),
            "counts": counts,
        }
    return {"action": "continue", "reason": "accumulating", "counts": counts}


class SignalCandidateEffectivenessEvaluator:
    """Compare candidate and stable Signal behavior on one frozen sample."""

    def __init__(
        self,
        registry: SignalRegistry,
        *,
        raw_info_store: RawInfoStore,
        discovery_cases: tuple[EvolutionCase, ...],
        llm_runner: LLMSignalRunner | None,
        evidence_resolver: EvidenceResolver | None = None,
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        case_limit: int = 8,
        minimum_cases: int = 4,
    ) -> None:
        if case_limit < 1 or minimum_cases < 1 or minimum_cases > case_limit:
            raise ValidationError("Signal effectiveness case limits are invalid")
        self.registry = registry
        self.raw_info_store = raw_info_store
        self.discovery_cases = tuple(discovery_cases)
        self.llm_runner = llm_runner
        self.evidence_resolver = evidence_resolver or EvidenceResolver(raw_info_store)
        self.deterministic_functions = dict(deterministic_functions or {})
        self.case_limit = case_limit
        self.minimum_cases = minimum_cases

    def evaluate(
        self,
        spec: SignalSpec,
        *,
        skill: str | None,
        preferred_case_ids: Iterable[str] = (),
        excluded_case_ids: Iterable[str] = (),
        induction_supported: bool = False,
        strict_preferred: bool = False,
        labels_by_case_id: Mapping[str, bool] | None = None,
        research_axis: Mapping[str, Any] | None = None,
    ) -> SignalCandidateEffectiveness:
        cases = self._select_cases(
            preferred_case_ids=preferred_case_ids,
            excluded_case_ids=excluded_case_ids,
            strict_preferred=strict_preferred,
        )
        case_ids = tuple(case.case_id for case in cases)
        axis = dict(research_axis or {})
        if labels_by_case_id is not None and any(
            case.case_id not in labels_by_case_id for case in cases
        ):
            raise ValidationError(
                "target effectiveness labels must cover every selected case"
            )
        try:
            current = self.registry.latest_spec(spec.signal_id)
        except ValidationError:
            current = None
        if len(cases) < self.minimum_cases:
            return SignalCandidateEffectiveness(
                signal_ref=spec.ref,
                current_ref=(current.ref if current is not None else None),
                accepted=False,
                disposition=("provisional" if induction_supported else "rejected"),
                reasons=(
                    "paired effectiveness requires at least "
                    f"{self.minimum_cases} Discovery cases",
                ),
                case_ids=case_ids,
                candidate_available=0,
                candidate_decisive=0,
                candidate_correct=0,
                candidate_wrong=0,
                research_axis=axis,
            )

        candidate_hash = hashlib.sha256(
            json.dumps(
                {"spec": spec.to_dict(), "skill": skill or ""},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        materialized = self._materialize_case_inputs(spec, cases)

        frozen_store = RawInfoStore(documents=self.raw_info_store.documents)
        candidate_executor = SignalExecutor(
            FrozenSignalRegistry(
                version=0,
                registry_hash=candidate_hash,
                specs=(spec,),
                skills=({spec.ref: skill} if skill is not None else {}),
            ),
            frozen_store,
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_runner,
        )
        current_executor = (
            SignalExecutor(
                self.registry.freeze(),
                frozen_store,
                deterministic_functions=self.deterministic_functions,
                llm_runner=self.llm_runner,
            )
            if current is not None
            else None
        )
        candidate_values: list[
            tuple[SignalValue, bool, SignalExecutionStatus]
        ] = []
        current_values: list[
            tuple[SignalValue, bool, SignalExecutionStatus]
        ] = []
        case_diagnostics: list[dict[str, Any]] = []
        try:
            for case in cases:
                candidate_result = candidate_executor.execute_batch(
                    (spec.ref,),
                    company_id=case.company_id,
                    as_of=case.prediction_time,
                    identity=case.basic_info,
                ).results[0]
                candidate_values.append(
                    (
                        candidate_result.value,
                        (
                            bool(labels_by_case_id[case.case_id])
                            if labels_by_case_id is not None
                            else case.ground_truth.is_surge
                        ),
                        candidate_result.execution_status,
                    )
                )
                diagnostic: dict[str, Any] = {
                    "case_id": case.case_id,
                    "candidate": _effectiveness_arm_diagnostic(
                        materialized[case.case_id]["candidate"], candidate_result
                    ),
                }
                if current is not None and current_executor is not None:
                    current_result = current_executor.execute_batch(
                        (current.ref,),
                        company_id=case.company_id,
                        as_of=case.prediction_time,
                        identity=case.basic_info,
                    ).results[0]
                    current_values.append(
                        (
                            current_result.value,
                            (
                                bool(labels_by_case_id[case.case_id])
                                if labels_by_case_id is not None
                                else case.ground_truth.is_surge
                            ),
                            current_result.execution_status,
                        )
                    )
                    diagnostic["current"] = _effectiveness_arm_diagnostic(
                        materialized[case.case_id]["current"], current_result
                    )
                case_diagnostics.append(diagnostic)
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            return SignalCandidateEffectiveness(
                signal_ref=spec.ref,
                current_ref=(current.ref if current is not None else None),
                accepted=False,
                disposition="rejected",
                reasons=("paired effectiveness execution failed: " + str(exc),),
                case_ids=case_ids,
                candidate_available=0,
                candidate_decisive=0,
                candidate_correct=0,
                candidate_wrong=0,
                research_axis=axis,
            )

        candidate_counts = _signal_effectiveness_counts(candidate_values)
        current_counts = _signal_effectiveness_counts(current_values)
        candidate_confusion = _confusion_counts(candidate_values)
        current_confusion = _confusion_counts(current_values)
        insufficient_reasons: list[str] = []
        if candidate_counts[0] < self.minimum_cases:
            insufficient_reasons.append(
                "candidate availability is below paired minimum: "
                f"{candidate_counts[0]}/{self.minimum_cases}"
            )
        decisive_floor = min(2, self.minimum_cases)
        if candidate_counts[1] < decisive_floor:
            insufficient_reasons.append(
                "candidate decisive support is below paired minimum: "
                f"{candidate_counts[1]}/{decisive_floor}"
            )
        rejection_reasons: list[str] = []
        if (
            candidate_counts[1] >= decisive_floor
            and candidate_counts[2] <= candidate_counts[3]
        ):
            rejection_reasons.append(_DIRECTIONAL_FLOOR_REASON)
        candidate_recall = _positive_recall(candidate_confusion)
        if candidate_recall is not None and candidate_recall < _RECALL_FLOOR:
            rejection_reasons.append(_RECALL_FLOOR_REASON)
        if current is not None:
            labels = (
                (0, "availability"),
                (2, "directional correct count"),
            )
            for index, label in labels:
                if candidate_counts[index] < current_counts[index]:
                    rejection_reasons.append(f"candidate reduces {label}")
            if candidate_counts[3] > current_counts[3]:
                rejection_reasons.append("candidate increases directional wrong count")
            if not insufficient_reasons and not (
                candidate_counts[0] > current_counts[0]
                or candidate_counts[2] > current_counts[2]
                or candidate_counts[3] < current_counts[3]
            ):
                rejection_reasons.append(
                    "candidate shows no strict paired effectiveness gain"
                )
        if rejection_reasons:
            if current is None and set(rejection_reasons) <= {
                _DIRECTIONAL_FLOOR_REASON,
                _RECALL_FLOOR_REASON,
            }:
                # A new signal that passed every correctness, availability, and
                # decisiveness floor but failed only the directional or recall
                # floor at the check cohort's small n is not disproved: it
                # becomes a provisional resident and accumulates paired
                # evidence on later fresh check cohorts under the pooled
                # three-zone rule.
                disposition = "provisional"
            else:
                disposition = "rejected"
            reasons = rejection_reasons + insufficient_reasons
        elif insufficient_reasons:
            disposition = "provisional" if induction_supported else "rejected"
            reasons = insufficient_reasons
        else:
            disposition = "promoted"
            reasons = []
        return SignalCandidateEffectiveness(
            signal_ref=spec.ref,
            current_ref=(current.ref if current is not None else None),
            accepted=disposition == "promoted",
            disposition=disposition,
            reasons=tuple(reasons),
            case_ids=case_ids,
            candidate_available=candidate_counts[0],
            candidate_decisive=candidate_counts[1],
            candidate_correct=candidate_counts[2],
            candidate_wrong=candidate_counts[3],
            candidate_execution_failed=candidate_counts[4],
            current_available=current_counts[0],
            current_decisive=current_counts[1],
            current_correct=current_counts[2],
            current_wrong=current_counts[3],
            current_execution_failed=current_counts[4],
            candidate_confusion=candidate_confusion,
            current_confusion=current_confusion,
            research_axis=axis,
            case_diagnostics=tuple(case_diagnostics),
        )

    def _materialize_case_inputs(
        self,
        spec: SignalSpec,
        cases: Iterable[EvolutionCase],
    ) -> dict[str, dict[str, RawInfoResolution]]:
        """Resolve both paired arms before one common local corpus is frozen."""

        candidate_executor = SignalExecutor(
            FrozenSignalRegistry(
                version=0,
                registry_hash=_canonical_hash(spec.to_dict()),
                specs=(spec,),
                skills={},
            ),
            self.raw_info_store,
            resolver=self.evidence_resolver,
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_runner,
        )
        try:
            current = self.registry.latest_spec(spec.signal_id)
        except ValidationError:
            current = None
        current_executor = (
            SignalExecutor(
                self.registry.freeze(),
                self.raw_info_store,
                resolver=self.evidence_resolver,
                deterministic_functions=self.deterministic_functions,
                llm_runner=self.llm_runner,
            )
            if current is not None
            else None
        )
        materialized: dict[str, dict[str, RawInfoResolution]] = {}
        for case in cases:
            arms: dict[str, RawInfoResolution] = {}
            if current is not None and current_executor is not None:
                arms["current"] = current_executor.prepare_inputs(
                    (current.ref,),
                    company_id=case.company_id,
                    as_of=case.prediction_time,
                    identity=case.basic_info,
                )[0]
            arms["candidate"] = candidate_executor.prepare_inputs(
                (spec.ref,),
                company_id=case.company_id,
                as_of=case.prediction_time,
                identity=case.basic_info,
            )[0]
            materialized[case.case_id] = arms
        return materialized

    def evaluation_identity(
        self,
        spec: SignalSpec,
        *,
        candidate_hash: str,
        preferred_case_ids: Iterable[str] = (),
        excluded_case_ids: Iterable[str] = (),
        induction_supported: bool = False,
        strict_preferred: bool = False,
        labels_by_case_id: Mapping[str, bool] | None = None,
        research_axis: Mapping[str, Any] | None = None,
    ) -> Mapping[str, str]:
        """Return the complete stable identity used to cache one paired gate."""

        preferred_ids = tuple(str(item) for item in preferred_case_ids)
        excluded_ids = tuple(str(item) for item in excluded_case_ids)
        cases = self._select_cases(
            preferred_case_ids=preferred_ids,
            excluded_case_ids=excluded_ids,
            strict_preferred=strict_preferred,
        )
        self._materialize_case_inputs(spec, cases)
        try:
            current = self.registry.latest_spec(spec.signal_id)
            baseline = {
                "spec": current.to_dict(),
                "skill": self.registry.load_skill(current.ref),
            }
        except ValidationError:
            baseline = {"spec": None, "skill": None}
        source_manifest = []
        for case in cases:
            documents = self.raw_info_store.search(
                case.company_id,
                as_of=case.prediction_time,
            )
            source_manifest.append(
                {
                    "case_id": case.case_id,
                    "company_id": case.company_id,
                    "prediction_time": case.prediction_time.isoformat(),
                    "documents": [
                        {
                            "document_id": document.document_id,
                            "content_hash": document.content_hash,
                            "source_type": document.source_type,
                            "available_at": document.available_at.isoformat(),
                        }
                        for document in documents
                    ],
                }
            )
        runner_identity: dict[str, Any] = {
            "type": (
                None
                if self.llm_runner is None
                else f"{type(self.llm_runner).__module__}."
                f"{type(self.llm_runner).__qualname__}"
            )
        }
        caller = getattr(self.llm_runner, "caller", None)
        registration = getattr(caller, "registration", None)
        if registration is not None and callable(
            getattr(registration, "to_public_dict", None)
        ):
            runner_identity["registration"] = registration.to_public_dict()
        contract = getattr(caller, "contract", None)
        if contract is not None and getattr(contract, "contract_hash", None):
            runner_identity["contract_hash"] = str(contract.contract_hash)
        return {
            "baseline_hash": _canonical_hash(baseline),
            "cohort_hash": _canonical_hash(
                {
                    "selected": [
                        {
                            "case_id": case.case_id,
                            "company_id": case.company_id,
                            "prediction_time": case.prediction_time.isoformat(),
                        }
                        for case in cases
                    ],
                    "excluded_case_ids": list(excluded_ids),
                    "induction_supported": induction_supported,
                    "strict_preferred": strict_preferred,
                    "labels_by_case_id": (
                        {
                            case.case_id: bool(labels_by_case_id[case.case_id])
                            for case in cases
                        }
                        if labels_by_case_id is not None
                        else None
                    ),
                    "research_axis": dict(research_axis or {}),
                }
            ),
            "source_manifest_hash": _canonical_hash(
                {"source_manifest": source_manifest}
            ),
            "projection_hash": _canonical_hash(
                {
                    "schema": "signal-paired-projection-v1",
                    "executor": "SignalExecutor",
                    "point_in_time": True,
                    "research_axis": dict(research_axis or {}),
                }
            ),
            "validator_hash": _canonical_hash(
                {
                    "contract": "signal-candidate-validation-v2",
                    "effectiveness": "signal-candidate-effectiveness-v4",
                    "minimum_cases": self.minimum_cases,
                    "case_limit": self.case_limit,
                    "functions": sorted(self.deterministic_functions),
                }
            ),
            "model_hash": _canonical_hash(runner_identity),
            "sampling_hash": _canonical_hash(
                {
                    "schema": "issuer-distinct-preferred-then-stratified-v1",
                    "preferred_case_ids": list(preferred_ids),
                    "selected_case_ids": [case.case_id for case in cases],
                    "strict_preferred": strict_preferred,
                }
            ),
        }

    def _select_cases(
        self,
        *,
        preferred_case_ids: Iterable[str],
        excluded_case_ids: Iterable[str],
        strict_preferred: bool = False,
    ) -> tuple[EvolutionCase, ...]:
        case_by_id = {case.case_id: case for case in self.discovery_cases}
        excluded_companies = {
            case_by_id[case_id].company_id
            for case_id in excluded_case_ids
            if case_id in case_by_id
        }
        eligible = tuple(
            case
            for case in self.discovery_cases
            if case.company_id not in excluded_companies
        )
        preferred: list[EvolutionCase] = []
        seen_companies: set[str] = set()
        for case_id in preferred_case_ids:
            case = case_by_id.get(str(case_id))
            if (
                case is None
                or case.company_id in excluded_companies
                or case.company_id in seen_companies
            ):
                continue
            preferred.append(case)
            seen_companies.add(case.company_id)
            if len(preferred) >= self.case_limit:
                break
        if strict_preferred:
            return tuple(preferred)
        for case in _sample_signal_discovery_cases(eligible, limit=self.case_limit):
            if len(preferred) >= self.case_limit:
                break
            if case.company_id in seen_companies:
                continue
            preferred.append(case)
            seen_companies.add(case.company_id)
        return tuple(preferred)


def _effectiveness_arm_diagnostic(
    resolution: RawInfoResolution,
    result: SignalResult,
) -> dict[str, Any]:
    """Return a compact, label-free account of one paired execution arm."""

    return {
        "resolution_status": resolution.status,
        "resolution_gap_reason": (
            resolution.gap.reason.value if resolution.gap is not None else None
        ),
        "document_count": len(resolution.documents),
        "execution_status": result.execution_status.value,
        "error_code": result.execution_error_code,
        "error_message": result.execution_error_message,
    }


def signal_effectiveness_measurement_contract() -> dict[str, Any]:
    """Explain runtime counters to retrospective Slow readers without new labels."""

    return {
        "schema_version": "signal-effectiveness-measurement-v1",
        "available": "Non-UNAVAILABLE values after excluding technical execution failures; includes NEUTRAL.",
        "decisive": "POSITIVE or NEGATIVE values only; NEUTRAL is available but not decisive.",
        "directional_correct": "POSITIVE on a positive case or NEGATIVE on a control case.",
        "directional_wrong": "Other decisive values; correct plus wrong equals decisive.",
        "execution_failed": "Statuses other than SUCCESS and DOMAIN_UNAVAILABLE; domain unavailability is not a technical failure.",
        "candidate_confusion": (
            "TP/FP/FN/TN over available cases keyed by the positive label: a "
            "POSITIVE call is TP on a positive case and FP on a control; an "
            "available case without a POSITIVE call is FN on a positive case "
            "and TN on a control."
        ),
        "positive_recall": (
            "TP divided by (TP plus FN). The paired gate requires at least "
            "half of the positive-label check cases to receive a POSITIVE "
            "call, so abstaining on positives cannot farm accuracy."
        ),
        "paired_population": "Both arms use the same frozen case pool. Their availability and decisive subsets may differ with their measurements or thresholds.",
        "interpretation": "A decisive/available gap is expected for neutral results, not unexplained sample exclusion. Historical model rationales are claims, not definitions; qualify or challenge obsolete lessons using these rules and the cited measurements.",
    }


def _signal_effectiveness_counts(
    values: Iterable[tuple[SignalValue, bool, SignalExecutionStatus]],
) -> tuple[int, int, int, int, int]:
    available = decisive = correct = wrong = execution_failed = 0
    for value, is_surge, execution_status in values:
        if execution_status not in {
            SignalExecutionStatus.SUCCESS,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        }:
            execution_failed += 1
            continue
        if value is not SignalValue.UNAVAILABLE:
            available += 1
        if value not in (SignalValue.POSITIVE, SignalValue.NEGATIVE):
            continue
        decisive += 1
        if (value is SignalValue.POSITIVE) == is_surge:
            correct += 1
        else:
            wrong += 1
    return available, decisive, correct, wrong, execution_failed


def _mining_needs_exploration_fallback(audit: Mapping[str, Any]) -> bool:
    """Return whether H1/H3 ended without a substantive semantic decision."""

    stages = audit.get("stages", {})
    if not isinstance(stages, Mapping):
        return True
    h1 = stages.get("H1", {})
    if not isinstance(h1, Mapping) or not h1.get("hypotheses"):
        return True
    h3 = stages.get("H3", {})
    if not isinstance(h3, Mapping):
        return True
    decisions = h3.get("decisions", ())
    return not decisions or all(
        isinstance(item, Mapping) and item.get("disposition") == "inconclusive"
        for item in decisions
    )


def _merge_mining_fallback(
    hypothesis: Mapping[str, Any], exploration: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge two independent Mining results without changing either audit."""

    def merged_mapping(key: str) -> dict[str, Any]:
        return {**dict(hypothesis.get(key, {})), **dict(exploration.get(key, {}))}

    hypothesis_has_candidate = bool(hypothesis.get("candidate_refs"))
    combined_audit = (
        {
            **dict(hypothesis["audit"]),
            "independent_exploration": dict(exploration["audit"]),
        }
        if hypothesis_has_candidate
        else {
            "schema_version": "signal-mining-audit-v2",
            "status": (
                "completed_with_hypothesis_failure"
                if hypothesis["audit"].get("status") == "failed"
                else "completed"
            ),
            "track": "hypothesis_then_exploration_fallback",
            "hypothesis": dict(hypothesis["audit"]),
            "exploration": dict(exploration["audit"]),
            "candidate_refs": list(exploration.get("candidate_refs", ())),
        }
    )
    return {
        "candidate_refs": tuple(
            (*hypothesis.get("candidate_refs", ()), *exploration.get("candidate_refs", ()))
        ),
        "induction_case_ids": merged_mapping("induction_case_ids"),
        "validation_case_ids": merged_mapping("validation_case_ids"),
        "candidate_research_targets": merged_mapping(
            "candidate_research_targets"
        ),
        "refined_hypotheses": merged_mapping("refined_hypotheses"),
        "failures": merged_mapping("failures"),
        "capability_gaps": merged_mapping("capability_gaps"),
        "audit": combined_audit,
    }


@dataclass(frozen=True)
class SlowLoopValidation:
    """Durable Slow-loop decision staged before stable Registry mutation."""

    mined_candidates: tuple[str, ...]
    updated_candidates: tuple[str, ...]
    validated_candidates: Mapping[str, str]
    provisional_candidates: Mapping[str, tuple[str, ...]]
    rejected: Mapping[str, tuple[str, ...]]
    refined_hypotheses: Mapping[str, tuple[str, ...]]
    input_registry_version: int
    input_registry_hash: str
    input_signal_refs: tuple[str, ...]
    candidate_evaluations: Mapping[str, str] = field(default_factory=dict)
    candidate_effectiveness: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    candidate_research_targets: Mapping[str, str] = field(default_factory=dict)
    agent_audits: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    search_input_fingerprint: str = ""
    slow_input_hash: str = ""
    slow_memory_hash: str = ""
    slow_experiments_hash: str = ""
    sampling_manifest_hash: str = ""
    new_candidate_count: int = 0
    new_validated_signal_count: int = 0
    updated_signal_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mined_candidates": list(self.mined_candidates),
            "updated_candidates": list(self.updated_candidates),
            "validated_candidates": dict(self.validated_candidates),
            "provisional_candidates": {
                ref: list(reasons)
                for ref, reasons in self.provisional_candidates.items()
            },
            "rejected": {
                ref: list(reasons) for ref, reasons in self.rejected.items()
            },
            "refined_hypotheses": {
                ref: list(reasons)
                for ref, reasons in self.refined_hypotheses.items()
            },
            "input_registry_version": self.input_registry_version,
            "input_registry_hash": self.input_registry_hash,
            "input_signal_refs": list(self.input_signal_refs),
            "candidate_evaluations": dict(self.candidate_evaluations),
            "candidate_effectiveness": {
                ref: dict(value)
                for ref, value in self.candidate_effectiveness.items()
            },
            "candidate_research_targets": dict(
                self.candidate_research_targets
            ),
            "agent_audits": {
                name: dict(value) for name, value in self.agent_audits.items()
            },
            "search_input_fingerprint": self.search_input_fingerprint,
            "slow_input_hash": self.slow_input_hash,
            "slow_memory_hash": self.slow_memory_hash,
            "slow_experiments_hash": self.slow_experiments_hash,
            "sampling_manifest_hash": self.sampling_manifest_hash,
            "new_candidate_count": self.new_candidate_count,
            "new_validated_signal_count": self.new_validated_signal_count,
            "updated_signal_count": self.updated_signal_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SlowLoopValidation":
        return cls(
            mined_candidates=tuple(
                str(item) for item in data.get("mined_candidates", ())
            ),
            updated_candidates=tuple(
                str(item) for item in data.get("updated_candidates", ())
            ),
            validated_candidates={
                str(ref): str(candidate_hash)
                for ref, candidate_hash in dict(
                    data.get("validated_candidates", {})
                ).items()
            },
            provisional_candidates={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(
                    data.get("provisional_candidates", {})
                ).items()
            },
            rejected={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("rejected", {})).items()
            },
            refined_hypotheses={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("refined_hypotheses", {})).items()
            },
            input_registry_version=int(data["input_registry_version"]),
            input_registry_hash=str(data["input_registry_hash"]),
            input_signal_refs=tuple(
                str(item) for item in data.get("input_signal_refs", ())
            ),
            candidate_evaluations={
                str(ref): str(evaluation_key)
                for ref, evaluation_key in dict(
                    data.get("candidate_evaluations", {})
                ).items()
            },
            candidate_effectiveness={
                str(ref): dict(value)
                for ref, value in dict(
                    data.get("candidate_effectiveness", {})
                ).items()
            },
            candidate_research_targets={
                str(ref): str(target)
                for ref, target in dict(
                    data.get("candidate_research_targets", {})
                ).items()
            },
            agent_audits={
                str(name): dict(value)
                for name, value in dict(data.get("agent_audits", {})).items()
            },
            search_input_fingerprint=str(
                data.get("search_input_fingerprint", "")
            ),
            slow_input_hash=str(data.get("slow_input_hash", "")),
            slow_memory_hash=str(data.get("slow_memory_hash", "")),
            slow_experiments_hash=str(data.get("slow_experiments_hash", "")),
            sampling_manifest_hash=str(data.get("sampling_manifest_hash", "")),
            new_candidate_count=int(data.get("new_candidate_count", 0)),
            new_validated_signal_count=int(
                data.get("new_validated_signal_count", 0)
            ),
            updated_signal_count=int(data.get("updated_signal_count", 0)),
        )


@dataclass(frozen=True)
class SlowLoopResult:
    """Validated and automatically promoted Signal slow-loop outcome."""

    mined_candidates: tuple[str, ...]
    updated_candidates: tuple[str, ...]
    validated_candidates: Mapping[str, str]
    promoted: tuple[str, ...]
    provisional_candidates: Mapping[str, tuple[str, ...]]
    rejected: Mapping[str, tuple[str, ...]]
    refined_hypotheses: Mapping[str, tuple[str, ...]]
    input_registry_version: int
    input_registry_hash: str
    output_registry_version: int
    output_registry_hash: str
    candidate_evaluations: Mapping[str, str] = field(default_factory=dict)
    candidate_effectiveness: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    candidate_research_targets: Mapping[str, str] = field(default_factory=dict)
    agent_audits: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    search_input_fingerprint: str = ""
    slow_input_hash: str = ""
    slow_memory_hash: str = ""
    slow_experiments_hash: str = ""
    sampling_manifest_hash: str = ""
    new_candidate_count: int = 0
    new_validated_signal_count: int = 0
    new_promoted_signal_count: int = 0
    updated_signal_count: int = 0
    min_new_signals_per_cycle: int = 1
    signal_goal_status: str = "unmet"
    magnitude_contribution: Mapping[str, Any] = field(
        default_factory=lambda: dict(_UNASSESSED_MAGNITUDE_CONTRIBUTION)
    )

    @property
    def registry_version(self) -> int:
        """Compatibility alias for the committed output Registry version."""

        return self.output_registry_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "mined_candidates": list(self.mined_candidates),
            "updated_candidates": list(self.updated_candidates),
            "validated_candidates": dict(self.validated_candidates),
            "promoted": list(self.promoted),
            "provisional_candidates": {
                ref: list(reasons)
                for ref, reasons in self.provisional_candidates.items()
            },
            "rejected": {
                ref: list(reasons) for ref, reasons in self.rejected.items()
            },
            "refined_hypotheses": {
                ref: list(reasons)
                for ref, reasons in self.refined_hypotheses.items()
            },
            "input_registry_version": self.input_registry_version,
            "input_registry_hash": self.input_registry_hash,
            "output_registry_version": self.output_registry_version,
            "output_registry_hash": self.output_registry_hash,
            "candidate_evaluations": dict(self.candidate_evaluations),
            "candidate_effectiveness": {
                ref: dict(value)
                for ref, value in self.candidate_effectiveness.items()
            },
            "candidate_research_targets": dict(
                self.candidate_research_targets
            ),
            "agent_audits": {
                name: dict(value) for name, value in self.agent_audits.items()
            },
            "search_input_fingerprint": self.search_input_fingerprint,
            "slow_input_hash": self.slow_input_hash,
            "slow_memory_hash": self.slow_memory_hash,
            "slow_experiments_hash": self.slow_experiments_hash,
            "sampling_manifest_hash": self.sampling_manifest_hash,
            "new_candidate_count": self.new_candidate_count,
            "new_validated_signal_count": self.new_validated_signal_count,
            "new_promoted_signal_count": self.new_promoted_signal_count,
            "updated_signal_count": self.updated_signal_count,
            "min_new_signals_per_cycle": self.min_new_signals_per_cycle,
            "signal_goal_status": self.signal_goal_status,
            "magnitude_contribution": dict(self.magnitude_contribution),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SlowLoopResult":
        return cls(
            mined_candidates=tuple(
                str(item) for item in data.get("mined_candidates", ())
            ),
            updated_candidates=tuple(
                str(item) for item in data.get("updated_candidates", ())
            ),
            validated_candidates={
                str(ref): str(candidate_hash)
                for ref, candidate_hash in dict(
                    data.get(
                        "validated_candidates",
                        data.get("validated_pending_approval", {}),
                    )
                ).items()
            },
            promoted=tuple(str(item) for item in data.get("promoted", ())),
            provisional_candidates={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(
                    data.get("provisional_candidates", {})
                ).items()
            },
            rejected={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("rejected", {})).items()
            },
            refined_hypotheses={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("refined_hypotheses", {})).items()
            },
            input_registry_version=int(
                data.get("input_registry_version", data.get("registry_version", 0))
            ),
            input_registry_hash=str(data.get("input_registry_hash", "")),
            output_registry_version=int(
                data.get("output_registry_version", data.get("registry_version", 0))
            ),
            output_registry_hash=str(data.get("output_registry_hash", "")),
            candidate_evaluations={
                str(ref): str(evaluation_key)
                for ref, evaluation_key in dict(
                    data.get("candidate_evaluations", {})
                ).items()
            },
            candidate_effectiveness={
                str(ref): dict(value)
                for ref, value in dict(
                    data.get("candidate_effectiveness", {})
                ).items()
            },
            candidate_research_targets={
                str(ref): str(target)
                for ref, target in dict(
                    data.get("candidate_research_targets", {})
                ).items()
            },
            agent_audits={
                str(name): dict(value)
                for name, value in dict(data.get("agent_audits", {})).items()
            },
            search_input_fingerprint=str(
                data.get("search_input_fingerprint", "")
            ),
            slow_input_hash=str(data.get("slow_input_hash", "")),
            slow_memory_hash=str(data.get("slow_memory_hash", "")),
            slow_experiments_hash=str(data.get("slow_experiments_hash", "")),
            sampling_manifest_hash=str(data.get("sampling_manifest_hash", "")),
            new_candidate_count=int(data.get("new_candidate_count", 0)),
            new_validated_signal_count=int(
                data.get("new_validated_signal_count", 0)
            ),
            new_promoted_signal_count=int(
                data.get("new_promoted_signal_count", 0)
            ),
            updated_signal_count=int(data.get("updated_signal_count", 0)),
            min_new_signals_per_cycle=int(
                data.get("min_new_signals_per_cycle", 1)
            ),
            signal_goal_status=str(data.get("signal_goal_status", "unmet")),
            magnitude_contribution=dict(
                data.get("magnitude_contribution")
                or _UNASSESSED_MAGNITUDE_CONTRIBUTION
            ),
        )


def candidate_signal_spec_from_dict(spec: Mapping[str, Any]) -> SignalSpec:
    """Parse a candidate with the same strict evidence contract at every boundary."""

    if spec.get("modality") not in {item.value for item in SignalModality}:
        raise ValidationError(
            "candidate SignalSpec modality must be structured or narrative"
        )
    evidence_policy = spec.get("evidence_policy")
    if not isinstance(evidence_policy, Mapping):
        raise ValidationError(
            "candidate SignalSpec evidence_policy must be an object"
        )
    required_policy = {
        "require_source",
        "require_timestamp",
        "require_exact_span",
    }
    if set(evidence_policy) != required_policy:
        raise ValidationError(
            "candidate SignalSpec evidence_policy requires source, timestamp, "
            "and exact-span fields"
        )
    try:
        return SignalSpec.from_dict(dict(spec))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(
            f"candidate SignalSpec JSON is invalid: {type(exc).__name__}: {exc}"
        ) from exc


def _magnitude_mining_track_statuses(
    agent_audits: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    """Return explicit non-direction mining-axis statuses from one Slow audit."""

    mining = agent_audits.get("mining_pipeline", {})
    if not isinstance(mining, Mapping):
        return {}
    statuses: dict[str, str] = {}
    axes = mining.get("axes", {})
    if isinstance(axes, Mapping):
        for axis_id, axis_audit in axes.items():
            if str(axis_id) == "surge_direction" or not isinstance(
                axis_audit, Mapping
            ):
                continue
            statuses[str(axis_id)] = str(axis_audit.get("status", "unknown"))
    axis_id = str(mining.get("axis_id", ""))
    if axis_id and axis_id != "surge_direction":
        statuses.setdefault(axis_id, str(mining.get("status", "unknown")))
    return statuses


def signal_update_effective_changed_paths(
    stable: SignalSpec,
    updated: SignalSpec,
    *,
    stable_skill: str | None,
    updated_skill: str | None,
) -> tuple[str, ...]:
    """Return the exact mutable-path diff for one validated Signal update."""

    stable_dict = stable.to_dict()
    updated_dict = updated.to_dict()
    retrieval_fields = tuple(
        path.removeprefix("spec.raw_retrieval.")
        for path in SIGNAL_UPDATE_MUTABLE_PATHS
        if path.startswith("spec.raw_retrieval.")
    )
    actual_paths = {
        f"spec.raw_retrieval.{name}"
        for name in retrieval_fields
        if stable_dict["raw_retrieval"].get(name)
        != updated_dict["raw_retrieval"].get(name)
    }
    if stable_dict["parameters"] != updated_dict["parameters"]:
        actual_paths.add("spec.parameters")
    if stable_dict["execution"].get("skill_file") != updated_dict[
        "execution"
    ].get("skill_file"):
        actual_paths.add("spec.execution.skill_file")
    if stable_skill != updated_skill:
        actual_paths.add("skill")
    return tuple(
        path for path in SIGNAL_UPDATE_MUTABLE_PATHS if path in actual_paths
    )


def validate_signal_update_candidate(
    signal_ref: str,
    candidate: Mapping[str, Any],
    stable: SignalSpec,
    *,
    stable_skill: str | None = None,
    stable_tests: Iterable[Mapping[str, Any]] | None = None,
    changed_paths: Iterable[str] | None = None,
) -> tuple[SignalSpec, str | None, list[Any]]:
    """Validate and baseline-overlay an update without mutating the Registry."""

    if set(candidate) not in (
        {"signal_ref", "spec", "tests"},
        {"signal_ref", "spec", "skill", "tests"},
    ):
        raise ValidationError(
            "Signal Update candidate requires signal_ref, spec, tests and optional skill"
        )
    if str(candidate["signal_ref"]) != signal_ref:
        raise ValidationError("Signal Update candidate changed target signal_ref")
    raw_spec = candidate["spec"]
    raw_tests = candidate["tests"]
    if not isinstance(raw_spec, Mapping) or not isinstance(raw_tests, list):
        raise ValidationError("Signal Update candidate spec/tests shape is invalid")
    if not raw_tests or any(not isinstance(item, Mapping) for item in raw_tests):
        raise ValidationError(
            "Signal Update candidate requires non-empty executable fixtures"
        )
    if stable_tests is not None:
        inherited_tests = [dict(item) for item in stable_tests]
        if not inherited_tests:
            raise ValidationError(
                "stable Signal requires non-empty executable fixtures before Update"
            )
        if raw_tests != inherited_tests:
            raise ValidationError(
                "Signal Update candidate must preserve stable executable fixtures"
            )
    candidate_spec = dict(raw_spec)
    candidate_retrieval = candidate_spec.get("raw_retrieval")
    if not isinstance(candidate_retrieval, Mapping):
        raise ValidationError("Signal Update candidate raw_retrieval must be an object")
    retrieval = dict(stable.to_dict()["raw_retrieval"])
    retrieval.update(dict(candidate_retrieval))
    candidate_spec["raw_retrieval"] = retrieval
    updated = candidate_signal_spec_from_dict(candidate_spec)
    if updated.signal_id != stable.signal_id or updated.version != stable.version + 1:
        raise ValidationError("Signal Update candidate must preserve id and use vNext")
    if updated.category != stable.category:
        raise ValidationError("Signal Update candidate must preserve category")
    if updated.description != stable.description:
        raise ValidationError("Signal Update candidate must preserve description")
    if updated.execution_type is not stable.execution_type:
        raise ValidationError("Signal Update candidate must preserve execution type")
    if updated.evidence_policy != stable.evidence_policy:
        raise ValidationError("Signal Update candidate must preserve evidence policy")
    if (
        stable.execution_type is SignalExecutionType.DETERMINISTIC
        and updated.function != stable.function
    ):
        raise ValidationError(
            "Signal Update deterministic candidate must preserve function"
        )
    skill_value = candidate.get("skill", stable_skill)
    if skill_value is not None and not isinstance(skill_value, str):
        raise ValidationError("Signal Update skill must be string or null")
    if updated.execution_type is SignalExecutionType.DETERMINISTIC and (
        skill_value is not None
    ):
        raise ValidationError("deterministic Signal Update skill must be null")
    if updated.execution_type is SignalExecutionType.LLM and not (
        isinstance(skill_value, str) and skill_value.strip()
    ):
        raise ValidationError("LLM Signal Update requires a complete skill")

    actual_paths = set(
        signal_update_effective_changed_paths(
            stable,
            updated,
            stable_skill=stable_skill,
            updated_skill=skill_value,
        )
    )
    if not actual_paths:
        raise ValidationError(
            "Signal Update candidate has no effective change; use no_change"
        )
    if changed_paths is not None:
        declared = tuple(str(item) for item in changed_paths)
        allowed_paths = set(SIGNAL_UPDATE_MUTABLE_PATHS)
        unknown = sorted(set(declared) - allowed_paths)
        if unknown:
            raise ValidationError(
                "Signal Update changed_paths contains unknown path: "
                + ", ".join(unknown)
            )
        if len(set(declared)) != len(declared):
            raise ValidationError("Signal Update changed_paths must be unique")
        missing = sorted(actual_paths - set(declared))
        surplus = sorted(set(declared) - actual_paths)
        if missing or surplus:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if surplus:
                details.append("surplus " + ", ".join(surplus))
            raise ValidationError(
                "Signal Update changed_paths does not match effective diff: "
                + "; ".join(details)
            )
    return updated, skill_value, raw_tests


class SignalEvolutionEngine:
    """Locally orchestrated Signal Mining and one-call Signal Update."""

    def __init__(
        self,
        *,
        registry: SignalRegistry,
        raw_info_store: RawInfoStore,
        discovery_cases: tuple[EvolutionCase, ...],
        meta_memory: PlanMetaMemory,
        workspace: EvolutionWorkspace,
        mining_model: SignalMiningModel,
        update_model: SignalUpdateModel,
        llm_signal_runner: LLMSignalRunner | None,
        identity_cases: tuple[EvolutionCase, ...] | None = None,
        evidence_resolver: EvidenceResolver | None = None,
        on_progress: ProgressCallback | None = None,
        priors: EvolutionPriors = DEFAULT_EVOLUTION_PRIORS,
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        effectiveness_case_limit: int = 16,
        effectiveness_minimum_cases: int = 4,
        mining_config: SignalMiningConfig = SignalMiningConfig(),
        min_new_signals_per_cycle: int = 1,
        research_target_reveal: Mapping[str, Any] | None = None,
        research_target_sampling: Mapping[str, Any] | None = None,
    ) -> None:
        if not discovery_cases:
            raise ValidationError("Signal evolution requires label-visible Discovery cases")
        if min_new_signals_per_cycle < 1:
            raise ValidationError("minimum new Signals per cycle must be positive")
        self.registry = registry
        self.raw_info_store = raw_info_store
        self.discovery_cases = discovery_cases
        self.meta_memory = meta_memory
        self.research_target_reveal = research_target_reveal
        self.research_target_sampling = research_target_sampling
        self.workspace = workspace
        self.on_progress = on_progress
        self.mining_model = mining_model
        self.update_model = update_model
        identity_population = identity_cases or discovery_cases
        discovery_aliases = _slow_role_identity_guard_inventory(identity_population)
        self.slow_role_identity_guards = discovery_aliases
        self._discovery_cases_by_id = {
            case.case_id: case for case in identity_population
        }
        for role in (self.mining_model, self.update_model):
            setter = getattr(role, "set_identity_guard_aliases", None)
            if callable(setter):
                setter(discovery_aliases)
        self.llm_signal_runner = llm_signal_runner
        self.evidence_resolver = evidence_resolver or EvidenceResolver(raw_info_store)
        self.priors = priors
        self.mining_config = mining_config
        self.min_new_signals_per_cycle = min_new_signals_per_cycle
        self._active_sampling_manifest: Mapping[str, Any] | None = None
        self._active_slow_input: Mapping[str, Any] | None = None
        self._active_slow_memory: Mapping[str, Any] | None = None
        self.validator = SignalCandidateValidator(
            registry,
            llm_runner=llm_signal_runner,
            deterministic_functions=deterministic_functions,
            forbidden_identity_terms=_discovery_identity_terms(identity_population),
        )
        candidate_validator_setter = getattr(
            self.update_model, "set_candidate_validator", None
        )
        if callable(candidate_validator_setter):
            candidate_validator_setter(self._validate_update_candidate_for_role)
        self.effectiveness_evaluator = SignalCandidateEffectivenessEvaluator(
            registry,
            raw_info_store=raw_info_store,
            discovery_cases=discovery_cases,
            llm_runner=llm_signal_runner,
            evidence_resolver=self.evidence_resolver,
            deterministic_functions=deterministic_functions,
            case_limit=effectiveness_case_limit,
            minimum_cases=effectiveness_minimum_cases,
        )

    def _validate_update_candidate_for_role(
        self,
        signal_ref: str,
        candidate: Mapping[str, Any],
        changed_paths: tuple[str, ...],
    ) -> None:
        """Run deterministic immutable fixtures during bounded role correction."""

        stable = self.registry.load_spec(signal_ref)
        updated, skill, tests = validate_signal_update_candidate(
            signal_ref,
            candidate,
            stable,
            stable_skill=self.registry.load_skill(signal_ref),
            stable_tests=self.registry.load_tests(signal_ref),
            changed_paths=changed_paths,
        )
        if updated.execution_type is not SignalExecutionType.DETERMINISTIC:
            return
        result = self.validator.validate(updated, skill=skill, tests=tests)
        if not result.accepted:
            raise ValidationError(
                "updated deterministic Signal must preserve executable fixture "
                "behavior: " + "; ".join(result.reasons)
            )

    @staticmethod
    def _role_work_identity(role: Any) -> Any:
        identity = getattr(role, "work_identity", None)
        if isinstance(identity, Mapping):
            return dict(identity)
        return f"{type(role).__module__}.{type(role).__qualname__}"

    def _search_input_fingerprint(
        self, input_snapshot: FrozenSignalRegistry
    ) -> str:
        """Hash the committed inputs that can change Slow candidate search."""

        relevant_documents = self._relevant_search_documents()
        backlog_path = self.workspace.root / "capability_backlog.json"
        backlog = _read_json(backlog_path) if backlog_path.exists() else {}

        return _canonical_hash(
            {
                "schema_version": "slow-search-input-v1",
                "input_registry_hash": input_snapshot.registry_hash,
                "discovery_cases": [
                    {
                        "case_id": case.case_id,
                        "company_id": case.company_id,
                        "prediction_time": case.prediction_time.isoformat(),
                    }
                    for case in self.discovery_cases
                ],
                "relevant_raw_info": relevant_documents,
                "capability_backlog": backlog,
                "meta_info": list(self.meta_memory.archive_view()),
                "mining_config": self.mining_config.to_dict(),
                "mining_model": self._role_work_identity(self.mining_model),
                "update_model": self._role_work_identity(self.update_model),
                "slow_sampling_manifest": dict(
                    self._active_sampling_manifest or {}
                ),
                "research_target_reveal": dict(
                    self.research_target_reveal or {}
                ),
                "research_target_sampling": dict(
                    self.research_target_sampling or {}
                ),
                "slow_memory": dict(self._active_slow_memory or {}),
            }
        )

    def _relevant_search_documents(self) -> list[dict[str, Any]]:
        """Return exact PIT Raw Info identities relevant to Discovery cases."""

        cutoff_by_company: dict[str, datetime] = {}
        for case in self.discovery_cases:
            prior = cutoff_by_company.get(case.company_id)
            if prior is None or case.prediction_time > prior:
                cutoff_by_company[case.company_id] = case.prediction_time
        return sorted(
            (
                {
                    "document_id": document.document_id,
                    "content_hash": document.content_hash,
                    "company_id": document.company_id,
                    "source_type": document.source_type,
                    "available_at": document.available_at.isoformat(),
                }
                for document in self.raw_info_store.documents
                if document.company_id in cutoff_by_company
                and document.available_at <= cutoff_by_company[document.company_id]
            ),
            key=lambda item: (
                item["company_id"],
                item["available_at"],
                item["document_id"],
            ),
        )

    def _hypothesis_work_fingerprint(
        self,
        hypothesis: SignalMiningHypothesis,
        *,
        packets: Iterable[Mapping[str, Any]],
        validation_refs: Iterable[str],
        case_by_ref: Mapping[str, EvolutionCase],
    ) -> str:
        """Hash one H3 comparison without its cycle-owned proposal id."""

        hypothesis_definition = hypothesis.to_dict()
        hypothesis_definition.pop("hypothesis_id", None)
        validation_cases = [
            {
                "case_id": case_by_ref[case_ref].case_id,
                "company_id": case_by_ref[case_ref].company_id,
                "prediction_time": case_by_ref[case_ref].prediction_time.isoformat(),
            }
            for case_ref in validation_refs
        ]
        return _canonical_hash(
            {
                "schema_version": "signal-mining-h3-work-v1",
                "hypothesis": hypothesis_definition,
                "induction_packets": [dict(packet) for packet in packets],
                "validation_cases": validation_cases,
                "input_registry_hash": self.registry.freeze().registry_hash,
                "mining_config": self.mining_config.to_dict(),
                "mining_model": self._role_work_identity(self.mining_model),
                "projection_protocol": "signal-mining-h3-evidence-v2",
            }
        )

    def _prior_terminal_hypothesis_work(self) -> dict[str, Mapping[str, Any]]:
        """Load exact committed H3 work that must not be retried unchanged."""

        terminal_statuses = {
            "candidate_rejected",
            "evidence_unavailable",
            "inconclusive",
            "refine",
            "rejected",
            "unchanged_work_suppressed",
        }
        prior: dict[str, Mapping[str, Any]] = {}
        paths = tuple(
            self.workspace.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_validation.json"
            for cycle_id in range(1, self.workspace.last_completed_cycle + 1)
        )
        for path in reversed(paths):
            if not path.is_file():
                continue
            payload = _read_json(path)
            validation = payload.get("validation", {})
            if not isinstance(validation, Mapping):
                continue
            audits = validation.get("agent_audits", {})
            if not isinstance(audits, Mapping):
                continue
            audit = audits.get("mining_pipeline", {})
            if (
                isinstance(audit, Mapping)
                and audit.get("track") == "hypothesis_then_exploration_fallback"
                and isinstance(audit.get("hypothesis"), Mapping)
            ):
                audit = audit["hypothesis"]
            if not isinstance(audit, Mapping):
                continue
            rows = audit.get("hypothesis_work", ())
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                fingerprint = str(row.get("work_fingerprint", ""))
                if (
                    fingerprint
                    and row.get("status") in terminal_statuses
                    and fingerprint not in prior
                ):
                    prior[fingerprint] = row
        return prior

    @staticmethod
    def _with_runtime_sample_basis(
        decisions: Iterable[SignalMiningDecision],
        *,
        positive_refs: Iterable[str],
        control_refs: Iterable[str],
    ) -> tuple[SignalMiningDecision, ...]:
        """Replace model sample claims with the exact runtime-owned groups."""

        basis = {
            "positive_refs": tuple(positive_refs),
            "control_refs": tuple(control_refs),
        }
        if not basis["positive_refs"] or not basis["control_refs"]:
            raise ValidationError(
                "Signal Mining association requires positive and control sample refs"
            )
        return tuple(replace(item, sample_basis=basis) for item in decisions)

    def run_cycle(
        self,
        *,
        cycle_id: int,
        input_snapshot: FrozenSignalRegistry | None = None,
    ) -> SlowLoopResult:
        """Validate, durably stage, and automatically promote one Slow batch."""

        staged = self.workspace.staged_slow_validation(cycle_id)
        if staged is None:
            if input_snapshot is None:
                raise ValidationError("new Slow loop requires its input Signal snapshot")
            self.workspace.refresh_capability_backlog(
                available_source_types=self.evidence_resolver.available_source_types
            )
            slow_input = self._prepare_slow_input(
                cycle_id=cycle_id,
                input_snapshot=input_snapshot,
            )
            slow_memory = self._prepare_slow_memory(
                cycle_id=cycle_id,
                slow_input=slow_input,
            )
            self._active_sampling_manifest = dict(slow_input["sampling_manifest"])
            self._active_slow_input = slow_input
            self._active_slow_memory = slow_memory
            validation = self._validate_cycle(input_snapshot, cycle_id=cycle_id)
            slow_experiments = self._seal_slow_experiments(
                cycle_id=cycle_id,
                slow_input=slow_input,
                slow_memory=slow_memory,
                validation=validation,
            )
            validation = replace(
                validation,
                slow_input_hash=_canonical_hash(slow_input),
                slow_memory_hash=_canonical_hash(slow_memory),
                slow_experiments_hash=_canonical_hash(slow_experiments),
                sampling_manifest_hash=_canonical_hash(
                    dict(slow_input["sampling_manifest"])
                ),
            )
            self.workspace.stage_slow_validation(
                cycle_id=cycle_id,
                validation=validation.to_dict(),
            )
        else:
            validation = SlowLoopValidation.from_dict(staged)
            slow_input = self.workspace.load_slow_input(cycle_id)
            slow_memory = self.workspace.load_slow_memory(cycle_id)
            slow_experiments = self.workspace.load_slow_experiments(cycle_id)
            if all(item is not None for item in (slow_input, slow_memory, slow_experiments)):
                self._active_sampling_manifest = dict(slow_input["sampling_manifest"])
                self._active_slow_input = slow_input
                self._active_slow_memory = slow_memory
        transition = self.registry.promote_validated_batch(
            validation.validated_candidates,
            validated_evaluations=(
                validation.candidate_evaluations
                if validation.candidate_evaluations
                else None
            ),
            transition_id=f"cycle-{cycle_id:04d}",
            input_version=validation.input_registry_version,
            input_hash=validation.input_registry_hash,
            input_refs=validation.input_signal_refs,
        )
        input_signal_ids = {
            ref.rsplit(":v", 1)[0] for ref in validation.input_signal_refs
        }
        promoted_new = tuple(
            ref
            for ref in transition.promoted
            if ref.rsplit(":v", 1)[0] not in input_signal_ids
        )
        goal_status = (
            "met"
            if len(promoted_new) >= self.min_new_signals_per_cycle
            else "unmet"
        )
        magnitude_refs = tuple(
            ref
            for ref, target_id in validation.candidate_research_targets.items()
            if target_id != "surge_direction"
        )
        magnitude_supported = tuple(
            ref
            for ref in magnitude_refs
            if validation.candidate_effectiveness.get(ref, {}).get(
                "target_supported"
            )
        )
        magnitude_track_statuses = _magnitude_mining_track_statuses(
            validation.agent_audits
        )
        magnitude_contribution = {
            "assessed": False,
            "reason": (
                "target mining/effectiveness may be assessed, but the required "
                "Fast absent/present consumption experiment and Binary-F1 "
                "protection have not run"
            ),
            "target_mining_assessed": bool(magnitude_refs)
            or any(
                status == "completed"
                for status in magnitude_track_statuses.values()
            ),
            "target_track_statuses": magnitude_track_statuses,
            "target_candidate_refs": list(magnitude_refs),
            "target_supported_candidate_refs": list(magnitude_supported),
            "fast_consumption_assessed": False,
        }
        return SlowLoopResult(
            mined_candidates=validation.mined_candidates,
            updated_candidates=validation.updated_candidates,
            validated_candidates=validation.validated_candidates,
            promoted=transition.promoted,
            provisional_candidates=validation.provisional_candidates,
            rejected=validation.rejected,
            refined_hypotheses=validation.refined_hypotheses,
            input_registry_version=transition.input_version,
            input_registry_hash=transition.input_hash,
            output_registry_version=transition.output_version,
            output_registry_hash=transition.output_hash,
            candidate_evaluations=validation.candidate_evaluations,
            candidate_effectiveness=validation.candidate_effectiveness,
            candidate_research_targets=validation.candidate_research_targets,
            agent_audits=validation.agent_audits,
            search_input_fingerprint=validation.search_input_fingerprint,
            slow_input_hash=validation.slow_input_hash,
            slow_memory_hash=validation.slow_memory_hash,
            slow_experiments_hash=validation.slow_experiments_hash,
            sampling_manifest_hash=validation.sampling_manifest_hash,
            new_candidate_count=validation.new_candidate_count,
            new_validated_signal_count=validation.new_validated_signal_count,
            new_promoted_signal_count=len(promoted_new),
            updated_signal_count=validation.updated_signal_count,
            min_new_signals_per_cycle=self.min_new_signals_per_cycle,
            signal_goal_status=goal_status,
            magnitude_contribution=magnitude_contribution,
        )

    def _prepare_slow_input(
        self,
        *,
        cycle_id: int,
        input_snapshot: FrozenSignalRegistry,
    ) -> dict[str, Any]:
        """Freeze committed feedback and a neutral issuer-disjoint sample once."""

        existing = self.workspace.load_slow_input(cycle_id)
        if existing is not None:
            return validate_slow_input(existing)
        cycle_state = _read_json(self.workspace.cycle_state_path)
        contract_hash = str(cycle_state.get("run_contract_hash", ""))
        feedback_rows, source_manifest = self._committed_slow_feedback()
        imported_cutoff = self._imported_slow_history_cutoff()
        prior_memory = tuple(self.workspace.committed_slow_artifacts())
        previous = prior_memory[-1]["slow_memory"] if prior_memory else None
        sampling = build_slow_sampling_manifest(
            self.discovery_cases,
            cycle_id=cycle_id,
            base_seed=contract_hash,
            dev_limit=max(
                self.mining_config.case_pool_limit,
                2 * self.mining_config.induction_cases_per_class,
            ),
            check_limit=self.effectiveness_evaluator.case_limit,
        )
        value = validate_slow_input(
            {
                "schema_version": "slow-input-v1",
                "cycle_id": cycle_id,
                "contract_hash": contract_hash,
                "registry_hash": input_snapshot.registry_hash,
                "source_cutoff": {
                    "committed_fast_round": self.workspace.last_completed_round,
                    "committed_slow_cycle": max(
                        self.workspace.last_completed_cycle,
                        imported_cutoff,
                    ),
                },
                "source_manifest": source_manifest,
                "feedback_rows": feedback_rows,
                "sampling_manifest": sampling,
                **(
                    {
                        "research_targets": [
                            {
                                "target_id": str(
                                    self.research_target_sampling.get(
                                        "target_id", ""
                                    )
                                ),
                                "group_manifest": dict(
                                    self.research_target_reveal
                                ),
                                "sampling_manifest": dict(
                                    self.research_target_sampling
                                ),
                            }
                        ]
                    }
                    if self.research_target_reveal
                    and self.research_target_sampling
                    else {}
                ),
                "previous_memory_head": (
                    None if previous is None else previous.get("cycle_id")
                ),
                "previous_memory_hash": (
                    "" if previous is None else _canonical_hash(previous)
                ),
                "feedback_hash": _canonical_hash(
                    {"feedback_rows": feedback_rows}
                ),
            }
        )
        self.workspace.stage_slow_input(cycle_id=cycle_id, slow_input=value)
        return value

    def _committed_slow_feedback(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Project exact-version usage and pointer-reachable Slow outcomes."""

        rows: list[dict[str, Any]] = []
        manifest: list[dict[str, Any]] = []
        for card in self.registry.list_signal_cards():
            for event in self.registry.load_learning_events(card.ref):
                if event.round_id > self.workspace.last_completed_round:
                    continue
                raw = event.to_dict()
                feedback_ref = f"usage:{event.event_id}"
                row = {
                    "feedback_ref": feedback_ref,
                    "kind": "signal_usage",
                    "subject_ref": event.signal_ref,
                    "source_refs": [feedback_ref],
                    "limitations": [
                        "observational association; not causal Signal credit"
                    ],
                    "event": raw,
                }
                rows.append(row)
                manifest.append(
                    {
                        "ref": feedback_ref,
                        "content_hash": _canonical_hash(raw),
                        "visible_to": sorted(_SLOW_SOURCE_ROLES),
                    }
                )
        magnitude_rows, magnitude_manifest = magnitude_feedback_rows(
            self.meta_memory.entries,
            last_completed_round=self.workspace.last_completed_round,
        )
        rows.extend(magnitude_rows)
        manifest.extend(magnitude_manifest)
        for prior_cycle in range(1, self.workspace.last_completed_cycle + 1):
            for filename, kind in (
                ("slow_loop_validation.json", "candidate_result"),
                ("slow_loop_result.json", "search_result"),
            ):
                path = (
                    self.workspace.experiments_root
                    / "cycles"
                    / f"cycle-{prior_cycle:04d}"
                    / filename
                )
                if not path.is_file():
                    continue
                raw = _read_json(path)
                for suffix, unit_kind, locator, unit in self._imported_artifact_units(
                    filename, raw
                ):
                    feedback_ref = (
                        f"slow:{prior_cycle}:{filename[:-5]}:{suffix}"
                    )
                    row = {
                        "feedback_ref": feedback_ref,
                        "kind": unit_kind or kind,
                        "subject_ref": f"cycle-{prior_cycle:04d}",
                        "source_refs": [feedback_ref],
                        "limitations": [],
                        "source_artifact": {
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "json_locator": locator,
                        },
                        "artifact": unit,
                    }
                    rows.append(row)
                    manifest.append(
                        {
                            "ref": feedback_ref,
                            "content_hash": _canonical_hash(unit),
                            "visible_to": sorted(_SLOW_SOURCE_ROLES),
                        }
                    )
        imported_rows, imported_manifest = self._imported_slow_feedback()
        rows.extend(imported_rows)
        manifest.extend(imported_manifest)
        refs = [str(item["feedback_ref"]) for item in rows]
        if len(refs) != len(set(refs)):
            raise ValidationError("Slow feedback refs must be globally unique")
        rows.sort(key=lambda item: item["feedback_ref"])
        manifest.sort(key=lambda item: item["ref"])
        return rows, manifest

    def _imported_slow_history_manifest(self) -> dict[str, Any] | None:
        """Load and verify the local immutable Slow-history envelope, if any."""

        path = self.workspace.root / "slow_history" / "manifest.json"
        if not path.is_file():
            return None
        envelope = _read_json(path)
        manifest = dict(envelope.get("manifest", {}))
        if (
            manifest.get("schema_version") not in {"slow-history-manifest-v1", "slow-history-manifest-v2"}
            or envelope.get("manifest_hash") != _canonical_hash(manifest)
        ):
            raise ValidationError("imported Slow history manifest hash mismatch")
        return manifest

    def _imported_slow_history_cutoff(self) -> int:
        """Return the immutable source Slow pointer represented by history."""

        manifest = self._imported_slow_history_manifest()
        return 0 if manifest is None else int(manifest["committed_slow_cycle"])

    def _imported_slow_feedback(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Project namespaced committed Slow artifacts from their local copies."""

        history = self._imported_slow_history_manifest()
        if history is None:
            return [], []
        namespace = str(history.get("source_namespace", ""))
        if not namespace:
            raise ValidationError("imported Slow history namespace is missing")
        rows: list[dict[str, Any]] = []
        source_manifest: list[dict[str, Any]] = []
        # Each committed cycle's slow_input already contains every prior
        # cycle's imported feedback rows, so projecting every cycle's input
        # multiplies the catalog quadratically across successor generations.
        # Feedback rows come only from the newest committed input (a strict
        # superset); older inputs remain hash-verified for their manifests.
        latest_input_cycle = max(
            (
                int(item.get("cycle_id", 0))
                for item in history.get("cycle_artifacts", ())
                if isinstance(item, Mapping)
                and Path(str(item.get("path", ""))).name == "slow_input.json"
            ),
            default=0,
        )
        for item in history.get("cycle_artifacts", ()):
            if not isinstance(item, Mapping):
                raise ValidationError("imported Slow artifact row must be an object")
            relative = Path(str(item.get("path", "")))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValidationError("imported Slow artifact path is invalid")
            filename = relative.name
            if filename not in {
                "slow_input.json",
                "slow_memory.json",
                "slow_experiments.json",
                "slow_loop_validation.json",
                "slow_loop_result.json",
            }:
                raise ValidationError("imported Slow artifact type is invalid")
            path = self.workspace.root / "slow_history" / namespace / relative
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest()
                != str(item.get("sha256", ""))
            ):
                raise ValidationError("imported Slow artifact copy hash mismatch")
            raw = _read_json(path)
            cycle_id = int(item.get("cycle_id", 0))
            if filename == "slow_input.json" and cycle_id != latest_input_cycle:
                continue
            for suffix, kind, locator, unit in self._imported_artifact_units(
                filename, raw
            ):
                feedback_ref = (
                    f"slow-history:{namespace}:{cycle_id}:{filename[:-5]}:{suffix}"
                )
                row = {
                    "feedback_ref": feedback_ref,
                    "kind": kind,
                    "subject_ref": f"{namespace}:cycle-{cycle_id:04d}",
                    "source_refs": [feedback_ref],
                    "limitations": [
                        "imported committed history; source protocol may be read-only"
                    ],
                    "source_artifact": {
                        "sha256": str(item["sha256"]),
                        "json_locator": locator,
                    },
                    "artifact": unit,
                }
                rows.append(row)
                source_manifest.append(
                    {
                        "ref": feedback_ref,
                        "content_hash": _canonical_hash(unit),
                        "visible_to": sorted(_SLOW_SOURCE_ROLES),
                    }
                )
        return rows, source_manifest

    @staticmethod
    def _imported_artifact_units(
        filename: str, raw: Mapping[str, Any]
    ) -> tuple[tuple[str, str, str, dict[str, Any]], ...]:
        """Split a committed artifact only at explicit complete-work boundaries."""

        units: list[tuple[str, str, str, dict[str, Any]]] = []
        if filename == "slow_loop_validation.json":
            validation = dict(raw.get("validation", {}))
            audits = dict(validation.pop("agent_audits", {}))
            evaluations = dict(validation.pop("candidate_evaluations", {}))
            effectiveness = dict(validation.pop("candidate_effectiveness", {}))
            units.append(("summary", "candidate_result", "/validation", validation))
            mining = audits.get("mining_pipeline")
            if isinstance(mining, Mapping):
                mining = dict(mining)
                tracks = [
                    (name, mining[name]) for name in ("hypothesis", "exploration")
                    if isinstance(mining.get(name), Mapping)
                ]
                if not tracks:
                    tracks = [("", mining)]
                for track_name, track in tracks:
                    stages = track.get("stages", {})
                    if not isinstance(stages, Mapping):
                        continue
                    for stage, collection in (("H1", "hypotheses"), ("H3", "decisions"), ("E2", "decisions")):
                        stage_data = stages.get(stage, {})
                        if not isinstance(stage_data, Mapping):
                            continue
                        values = stage_data.get(collection, ())
                        if not isinstance(values, (list, tuple)):
                            continue
                        track_path = f"/{track_name}" if track_name else ""
                        if not values and stage_data:
                            units.append((
                                f"mining-decision-{stage}-empty",
                                "candidate_result",
                                "/validation/agent_audits/mining_pipeline"
                                f"{track_path}/stages/{stage}",
                                dict(stage_data),
                            ))
                        for index, decision in enumerate(values):
                            if not isinstance(decision, Mapping):
                                continue
                            units.append((
                                f"mining-decision-{stage}-{index + 1:03d}",
                                "candidate_result",
                                "/validation/agent_audits/mining_pipeline"
                                f"{track_path}/stages/{stage}/{collection}/{index}",
                                dict(decision),
                            ))
                if isinstance(mining.get("hypothesis"), Mapping):
                    units.append(
                        (
                            "mining-hypothesis",
                            "candidate_result",
                            "/validation/agent_audits/mining_pipeline/hypothesis",
                            dict(mining["hypothesis"]),
                        )
                    )
                if isinstance(mining.get("exploration"), Mapping):
                    units.append(
                        (
                            "mining-exploration",
                            "candidate_result",
                            "/validation/agent_audits/mining_pipeline/exploration",
                            dict(mining["exploration"]),
                        )
                    )
                if not any(
                    isinstance(mining.get(key), Mapping)
                    for key in ("hypothesis", "exploration")
                ):
                    units.append(
                        (
                            "mining",
                            "candidate_result",
                            "/validation/agent_audits/mining_pipeline",
                            mining,
                        )
                    )
            update = audits.get("update_pipeline")
            if isinstance(update, Mapping):
                update_summary = dict(update)
                targets = update_summary.pop("targets", ())
                units.append(
                    (
                        "update-summary",
                        "candidate_result",
                        "/validation/agent_audits/update_pipeline",
                        update_summary,
                    )
                )
                for index, target in enumerate(targets):
                    if isinstance(target, Mapping):
                        units.append(
                            (
                                f"update-target-{index + 1:03d}",
                                "candidate_result",
                                f"/validation/agent_audits/update_pipeline/targets/{index}",
                                dict(target),
                            )
                        )
            for signal_ref, evaluation in sorted(evaluations.items()):
                if isinstance(evaluation, Mapping):
                    units.append(
                        (
                            "fixture-" + _canonical_hash(signal_ref)[:12],
                            "candidate_result",
                            f"/validation/candidate_evaluations/{signal_ref}",
                            dict(evaluation),
                        )
                    )
            for signal_ref, evaluation in sorted(effectiveness.items()):
                if isinstance(evaluation, Mapping):
                    units.append(
                        (
                            "effect-" + _canonical_hash(signal_ref)[:12],
                            "candidate_result",
                            f"/validation/candidate_effectiveness/{signal_ref}",
                            dict(evaluation),
                        )
                    )
        elif filename == "slow_loop_result.json":
            result = dict(raw.get("result", {}))
            for key in (
                "agent_audits",
                "candidate_evaluations",
                "candidate_effectiveness",
            ):
                result.pop(key, None)
            units.append(("summary", "search_result", "/result", result))
        elif filename == "slow_experiments.json":
            for index, attempt in enumerate(raw.get("attempts", ())):
                if isinstance(attempt, Mapping):
                    units.append(
                        (
                            f"attempt-{index + 1:03d}",
                            "candidate_result",
                            f"/attempts/{index}",
                            dict(attempt),
                        )
                    )
        elif filename == "slow_memory.json":
            summary = dict(raw)
            episodes = summary.pop("episode_reflections", ())
            lessons = summary.pop("lesson_additions", ())
            units.append(("summary", "search_result", "/", summary))
            for collection, values in (("episode", episodes), ("lesson", lessons)):
                for index, value in enumerate(values):
                    if isinstance(value, Mapping):
                        units.append(
                            (
                                f"{collection}-{index + 1:03d}",
                                "search_result",
                                (
                                    f"/episode_reflections/{index}"
                                    if collection == "episode"
                                    else f"/lesson_additions/{index}"
                                ),
                                dict(value),
                            )
                        )
        elif filename == "slow_input.json":
            for index, feedback in enumerate(raw.get("feedback_rows", ())):
                if isinstance(feedback, Mapping):
                    units.append(
                        (
                            f"feedback-{index + 1:03d}",
                            str(feedback.get("kind", "search_result")),
                            f"/feedback_rows/{index}",
                            dict(feedback),
                        )
                    )
        if not units:
            units.append(("complete", "search_result", "/", dict(raw)))
        return tuple(units)

    def _prepare_slow_memory(
        self,
        *,
        cycle_id: int,
        slow_input: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Run one bounded entry reflection or persist an honest reused/failed delta."""

        existing = self.workspace.load_slow_memory(cycle_id)
        if existing is not None:
            return existing
        prior = tuple(self.workspace.committed_slow_artifacts())
        processed_before = {
            str(ref)
            for item in prior
            for ref in item["slow_memory"].get("processed_feedback_refs", ())
        }
        feedback_rows = list(slow_input["feedback_rows"])
        pending_rows = [
            row
            for row in feedback_rows
            if str(row["feedback_ref"]) not in processed_before
        ]
        previous_memory_head = slow_input.get("previous_memory_head")
        recent_subject = (
            f"cycle-{int(previous_memory_head):04d}"
            if isinstance(previous_memory_head, int)
            and previous_memory_head == cycle_id - 1
            else None
        )
        recent_rows = [
            row
            for row in pending_rows
            if recent_subject is not None
            and str(row.get("subject_ref", "")) == recent_subject
        ]
        recent_refs = {
            str(row["feedback_ref"])
            for row in recent_rows
        }
        if recent_rows:
            pending_rows = [
                *recent_rows,
                *[
                    row
                    for row in pending_rows
                    if str(row["feedback_ref"]) not in recent_refs
                ],
            ]
        pending_rows = _prioritize_reflection_feedback(pending_rows)
        prior_memory = prior[-1]["slow_memory"] if prior else None
        known_lessons = {
            str(lesson.get("lesson_id"))
            for item in prior
            for lesson in item["slow_memory"].get("lesson_additions", ())
            if isinstance(lesson, Mapping)
        }
        source_catalog = {
            str(row["feedback_ref"]): {
                "visible_to": sorted(_SLOW_SOURCE_ROLES),
                "content": row,
            }
            for row in pending_rows
        }
        selected, view = read_slow_sources(
            source_catalog,
            role_scope="reflection",
            source_catalog=source_catalog,
            budget_bytes=64_000,
            max_items=self.mining_config.reflection_feedback_limit,
        )
        required_refs = tuple(
            str(item["ref"])
            for item in selected
            if str(item["ref"]) in recent_refs
        )
        view = {**view, "required_refs": list(required_refs)}
        source_read_failure: str | None = None
        try:
            selected, view = self._optional_slow_source_read(
                model=self.mining_model,
                role_scope="reflection",
                source_catalog=source_catalog,
                selected=selected,
                manifest=view,
                required_refs=required_refs,
            )
        except CandidateExecutionRejected as exc:
            source_read_failure = "source_read_failed: " + str(exc)
            selected = ()
            view = {
                **view,
                "included_refs": [],
                "included_hashes": {},
                "included_count": 0,
                "deferred": [
                    {"ref": ref, "reason": "source_read_failed"}
                    for ref in source_catalog
                ],
                "deferred_count": len(source_catalog),
                "source_read_request_refs": list(
                    exc.details.get("request_refs", ())
                ),
                "source_read_mode": "failed",
            }
        selected_refs = [item["ref"] for item in selected]
        deferred_refs = [item["ref"] for item in view["deferred"]]
        contract_hash = str(slow_input["contract_hash"])
        common = {
            "schema_version": "slow-memory-v1",
            "cycle_id": cycle_id,
            "contract_hash": contract_hash,
            "input_hash": _canonical_hash(dict(slow_input)),
            "parent_memory_hash": (
                "" if prior_memory is None else _canonical_hash(prior_memory)
            ),
            "reflection_work_hash": _canonical_hash(
                {
                    "selected_refs": selected_refs,
                    "parent_memory_hash": (
                        "" if prior_memory is None else _canonical_hash(prior_memory)
                    ),
                    "model": self._role_work_identity(self.mining_model),
                    "protocol": "signal-mining-reflect-v5",
                }
            ),
            "model_view_manifest": {
                **view,
                "canonicalized_nested_refs": {},
            },
            "usage_ref": None,
            "failure_ref": None,
        }
        if not selected_refs:
            memory = {
                **common,
                "status": "failed" if deferred_refs else "reused",
                "processed_feedback_refs": [],
                "pending_feedback_refs": deferred_refs,
                "episode_reflections": [],
                "lesson_additions": [],
                "failure_ref": (
                    source_read_failure
                    or ("reflection_context_budget" if deferred_refs else None)
                ),
            }
        else:
            reflector = getattr(self.mining_model, "reflect_feedback", None)
            if not callable(reflector):
                memory = {
                    **common,
                    "status": "failed",
                    "processed_feedback_refs": [],
                    "pending_feedback_refs": [*selected_refs, *deferred_refs],
                    "episode_reflections": [],
                    "lesson_additions": [],
                    "failure_ref": "reflection_role_unavailable",
                }
            else:
                episode_slots = [
                    f"episode-c{cycle_id:04d}-{index:03d}"
                    for index in range(1, len(selected_refs) + 1)
                ]
                lesson_slots = [
                    f"lesson-c{cycle_id:04d}-{index:03d}"
                    for index in range(1, 5)
                ]
                try:
                    prior_deltas = [item["slow_memory"] for item in prior[-3:]]
                    prior_view = project_slow_method_memory(prior_deltas, budget_bytes=32_000)
                    prior_catalog = slow_method_memory_sources(prior_deltas)
                    prior_sources, prior_manifest = read_slow_sources(
                        (), role_scope="reflection", source_catalog=prior_catalog,
                        budget_bytes=32_000,
                    )
                    prior_manifest = {
                        **prior_manifest,
                        "requested_refs": list(prior_catalog),
                        "deferred": [{"ref": ref, "reason": "authored_brief_original_on_request"} for ref in prior_catalog],
                        "available_count": len(prior_catalog),
                        "deferred_count": len(prior_catalog),
                    }
                    prior_sources, prior_manifest = self._optional_slow_source_read(
                        model=self.mining_model, role_scope="reflection",
                        source_catalog=prior_catalog, selected=prior_sources,
                        manifest=prior_manifest,
                    )
                    step = reflector(
                        {
                            "reflection_contract_version": "signal-mining-reflect-v5",
                            "research_objective": signal_research_objective(),
                            "measurement_contract": signal_effectiveness_measurement_contract(),
                            "episode_slots": episode_slots,
                            "lesson_slots": lesson_slots,
                            "feedback_units": [item["content"] for item in selected],
                            "prior_memory": prior_view["memory_deltas"],
                            "prior_memory_manifest": prior_view["memory_view_manifest"],
                            "prior_memory_disclosures": [dict(item) for item in prior_sources],
                            "rules": {
                                "append_only": True,
                                "complete_source_coverage": True,
                            },
                        }
                    )
                    result = dict(step.value)
                    episodes = list(result.get("episode_reflections", ()))
                    lessons = list(result.get("lesson_additions", ()))
                    if any(
                        str(item.get("episode_ref", "")) not in episode_slots
                        for item in episodes
                    ) or any(
                        str(item.get("lesson_id", "")) not in lesson_slots
                        for item in lessons
                    ):
                        raise ValidationError("reflection used an unassigned output ref")
                    covered_refs = {
                        str(ref)
                        for item in episodes
                        if isinstance(item, Mapping)
                        for ref in item.get("source_refs", ())
                    }
                    if covered_refs != set(selected_refs):
                        raise ValidationError(
                            "reflection must cover every selected feedback ref"
                        )
                    memory = {
                        **common,
                        "status": (
                            "appended" if episodes or lessons else "no_new_lesson"
                        ),
                        "processed_feedback_refs": selected_refs,
                        "pending_feedback_refs": deferred_refs,
                        "episode_reflections": episodes,
                        "lesson_additions": lessons,
                        "usage_ref": (
                            list(step.metadata.get("request_refs", ()))[-1]
                            if step.metadata.get("request_refs")
                            else None
                        ),
                        "model_view_manifest": {
                            **common["model_view_manifest"],
                            "prior_memory_view": prior_view["memory_view_manifest"],
                            "prior_original_reads": prior_manifest,
                            "canonicalized_nested_refs": dict(
                                step.metadata.get("canonicalized_nested_refs", {})
                            ),
                        },
                    }
                except (EvolutionControlFlow, OpenAIClientError):
                    raise
                except Exception as exc:
                    memory = {
                        **common,
                        "status": "failed",
                        "processed_feedback_refs": [],
                        "pending_feedback_refs": [*selected_refs, *deferred_refs],
                        "episode_reflections": [],
                        "lesson_additions": [],
                        "failure_ref": type(exc).__name__ + ": " + str(exc),
                    }
        memory = validate_slow_memory(
            memory,
            available_feedback_refs=[row["feedback_ref"] for row in feedback_rows],
            available_source_refs=[row["ref"] for row in slow_input["source_manifest"]],
            available_lesson_refs=known_lessons,
        )
        self.workspace.stage_slow_memory(cycle_id=cycle_id, slow_memory=memory)
        return memory

    def _seal_slow_experiments(
        self,
        *,
        cycle_id: int,
        slow_input: Mapping[str, Any],
        slow_memory: Mapping[str, Any],
        validation: SlowLoopValidation,
    ) -> dict[str, Any]:
        """Seal pipeline and candidate outcomes without claiming promotion."""

        existing = self.workspace.load_slow_experiments(cycle_id)
        if existing is not None:
            return existing
        attempts: list[dict[str, Any]] = []

        def append_attempt(
            *,
            work_id: str,
            stage: str,
            audit: Mapping[str, Any],
            outcome: str,
            parent_signal_ref: str | None = None,
            candidate_ref: str | None = None,
            failure_ref: str | None = None,
            action_summary: str = "",
        ) -> None:
            request_refs = _ordered_unique(
                str(item) for item in audit.get("request_refs", ()) if item
            )
            attempts.append(
                {
                    "work_id": work_id,
                    "stage": stage,
                    "proposal_hash": _canonical_hash(audit),
                    "parent_signal_ref": parent_signal_ref,
                    "need_refs": [],
                    "lesson_refs": [],
                    "action_summary": action_summary or stage,
                    "outcome": outcome,
                    "candidate_ref": candidate_ref,
                    "candidate_hash": (
                        self.registry.candidate_hash(candidate_ref)
                        if candidate_ref
                        else None
                    ),
                    "evidence_or_evaluation_refs": [],
                    "failure_ref": failure_ref,
                    "usage_ref": request_refs[-1] if request_refs else None,
                    "request_refs": list(request_refs),
                }
            )

        mining = dict(validation.agent_audits.get("mining_pipeline", {}))
        hypothesis = (
            dict(mining.get("hypothesis", {}))
            if isinstance(mining.get("hypothesis"), Mapping)
            else (mining if mining.get("track") == "hypothesis" else {})
        )
        exploration_raw = mining.get("exploration", mining.get("independent_exploration"))
        exploration = (
            dict(exploration_raw)
            if isinstance(exploration_raw, Mapping)
            else (mining if mining.get("track") == "exploration" else {})
        )
        if hypothesis:
            h1 = dict(hypothesis.get("stages", {})).get("H1", {})
            h1 = dict(h1) if isinstance(h1, Mapping) else {}
            if not h1:
                h1 = {
                    "status": hypothesis.get("status", "failed"),
                    "error": hypothesis.get("error"),
                    "request_refs": dict(hypothesis.get("failure_details", {})).get(
                        "request_refs", ()
                    ),
                }
            append_attempt(
                work_id=f"cycle-{cycle_id:04d}:H1",
                stage="H1",
                audit=h1,
                outcome=str(h1.get("status", hypothesis.get("status", "completed"))),
                failure_ref=("H1" if hypothesis.get("status") == "failed" else None),
                action_summary="hypothesis portfolio",
            )
            h3 = dict(hypothesis.get("stages", {})).get("H3", {})
            if isinstance(h3, Mapping) and h3:
                append_attempt(
                    work_id=f"cycle-{cycle_id:04d}:H3",
                    stage="H3",
                    audit=dict(h3),
                    outcome=str(h3.get("status", "completed")),
                    failure_ref=("H3" if h3.get("status") == "failed" else None),
                    action_summary="hypothesis contrast",
                )
        if exploration:
            stages = dict(exploration.get("stages", {}))
            e1 = stages.get("E1", {})
            microbatches = e1.get("microbatches", ()) if isinstance(e1, Mapping) else ()
            if microbatches:
                for index, raw in enumerate(microbatches, start=1):
                    item = dict(raw)
                    append_attempt(
                        work_id=f"cycle-{cycle_id:04d}:E1:{index:03d}",
                        stage="E1",
                        audit=item,
                        outcome=str(item.get("status", "completed")),
                        failure_ref=(
                            f"E1:{index:03d}"
                            if item.get("status") in {"technical_failure", "validation_failure"}
                            else None
                        ),
                        action_summary="exploration extraction microbatch",
                    )
            else:
                e1_audit = dict(e1) if isinstance(e1, Mapping) else dict(exploration)
                append_attempt(
                    work_id=f"cycle-{cycle_id:04d}:E1",
                    stage="E1",
                    audit=e1_audit,
                    outcome=str(e1_audit.get("status", exploration.get("status", "completed"))),
                    failure_ref=("E1" if exploration.get("status") == "failed" else None),
                    action_summary="exploration extraction",
                )
            e2 = stages.get("E2", {})
            if isinstance(e2, Mapping) and e2:
                append_attempt(
                    work_id=f"cycle-{cycle_id:04d}:E2",
                    stage="E2",
                    audit=dict(e2),
                    outcome=str(e2.get("status", "completed")),
                    failure_ref=("E2" if e2.get("status") == "failed" else None),
                    action_summary="exploration comparison",
                )

        update = dict(validation.agent_audits.get("update_pipeline", {}))
        targets = update.get("targets", ())
        if isinstance(targets, list) and targets:
            for index, raw in enumerate(targets, start=1):
                item = dict(raw)
                target = item.get("target", {})
                parent_ref = (
                    str(target.get("signal_ref"))
                    if isinstance(target, Mapping) and target.get("signal_ref")
                    else None
                )
                append_attempt(
                    work_id=f"cycle-{cycle_id:04d}:Update:{index:03d}",
                    stage="Update",
                    audit=item,
                    outcome=str(item.get("disposition", item.get("status", "completed"))),
                    parent_signal_ref=parent_ref,
                    candidate_ref=str(item.get("staged_ref")) if item.get("staged_ref") else None,
                    failure_ref=(f"Update:{index:03d}" if item.get("status") == "failed" else None),
                    action_summary=str(item.get("disposition", "update target")),
                )
        else:
            append_attempt(
                work_id=f"cycle-{cycle_id:04d}:Update",
                stage="Update",
                audit=update,
                outcome=str(update.get("disposition", update.get("status", "completed"))),
                failure_ref=("Update" if update.get("status") == "failed" else None),
                action_summary="update portfolio",
            )
        for signal_ref in _ordered_unique(
            [*validation.mined_candidates, *validation.updated_candidates]
        ):
            candidate_hash = self.registry.candidate_hash(signal_ref)
            if signal_ref in validation.validated_candidates:
                outcome = "validated"
            elif signal_ref in validation.provisional_candidates:
                outcome = "provisional"
            else:
                outcome = "rejected"
            attempts.append(
                {
                    "work_id": f"cycle-{cycle_id:04d}:candidate:{signal_ref}",
                    "stage": (
                        "Update"
                        if signal_ref in validation.updated_candidates
                        else "Mining"
                    ),
                    "proposal_hash": candidate_hash,
                    "parent_signal_ref": (
                        signal_ref.rsplit(":v", 1)[0]
                        if signal_ref in validation.updated_candidates
                        else None
                    ),
                    "need_refs": [],
                    "lesson_refs": [],
                    "action_summary": "candidate validation",
                    "outcome": outcome,
                    "candidate_ref": signal_ref,
                    "candidate_hash": candidate_hash,
                    "evidence_or_evaluation_refs": [
                        validation.candidate_evaluations.get(signal_ref)
                    ] if validation.candidate_evaluations.get(signal_ref) else [],
                    "failure_ref": (
                        signal_ref if outcome in {"provisional", "rejected"} else None
                    ),
                    "usage_ref": None,
                    "request_refs": [],
                }
            )
        value = validate_slow_experiments(
            {
                "schema_version": "slow-experiments-v1",
                "cycle_id": cycle_id,
                "contract_hash": str(slow_input["contract_hash"]),
                "input_hash": _canonical_hash(dict(slow_input)),
                "memory_hash": _canonical_hash(dict(slow_memory)),
                "attempts": attempts,
            }
        )
        self.workspace.stage_slow_experiments(
            cycle_id=cycle_id,
            slow_experiments=value,
        )
        return value

    def _validate_cycle(
        self,
        input_snapshot: FrozenSignalRegistry,
        *,
        cycle_id: int = 1,
    ) -> SlowLoopValidation:
        """Stage all candidates and return the exact pre-promotion decision."""

        current = self.registry.freeze()
        if (
            current.version != input_snapshot.version
            or current.registry_hash != input_snapshot.registry_hash
        ):
            raise ValidationError("Slow-loop input Signal snapshot changed")

        mined: list[str] = []
        updated: list[str] = []
        agent_failures: dict[str, tuple[str, ...]] = {}
        agent_audits: dict[str, Mapping[str, Any]] = {}
        induction_case_ids: dict[str, tuple[str, ...]] = {}
        validation_case_ids: dict[str, tuple[str, ...]] = {}
        candidate_research_targets: dict[str, str] = {}
        refined_hypotheses: dict[str, tuple[str, ...]] = {}
        try:
            mining_output = self._run_signal_mining(cycle_id=cycle_id)
            mined = list(mining_output["candidate_refs"])
            induction_case_ids = dict(mining_output["induction_case_ids"])
            validation_case_ids = dict(mining_output["validation_case_ids"])
            candidate_research_targets = dict(
                mining_output.get("candidate_research_targets", {})
            )
            refined_hypotheses = dict(mining_output["refined_hypotheses"])
            agent_failures.update(dict(mining_output["failures"]))
            agent_audits["mining_pipeline"] = dict(mining_output["audit"])
        except (EvolutionControlFlow, OpenAIClientError):
            raise
        except Exception as exc:
            _emit_progress(
                self.on_progress,
                "slow_pipeline_failed",
                cycle_id=cycle_id,
                pipeline="mining",
                error_type=type(exc).__name__,
                error=str(exc),
                usage=_usage_to_dict(getattr(exc, "usage", AgentUsage())),
            )
            failure_prefix = (
                "structured_output_failed"
                if isinstance(exc, (ValidationError, AssertionError))
                else "unexpected_pipeline_failure"
            )
            agent_failures["slow_loop:mining_pipeline"] = (
                failure_prefix + ": " + str(exc),
            )
            agent_audits["mining_pipeline"] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "usage": _usage_to_dict(getattr(exc, "usage", AgentUsage())),
            }
        try:
            update_output = self._run_signal_update(
                cycle_id=cycle_id,
                suggested_refs=self._h1_update_refs(
                    agent_audits.get("mining_pipeline", {})
                ),
            )
            updated = list(update_output["candidate_refs"])
            induction_case_ids.update(update_output["induction_case_ids"])
            validation_case_ids.update(update_output["validation_case_ids"])
            candidate_research_targets.update(
                {
                    ref: "surge_direction"
                    for ref in update_output["candidate_refs"]
                }
            )
            agent_failures.update(update_output["failures"])
            agent_audits["update_pipeline"] = dict(update_output["audit"])
        except (EvolutionControlFlow, OpenAIClientError):
            raise
        except Exception as exc:
            _emit_progress(
                self.on_progress,
                "slow_pipeline_failed",
                cycle_id=cycle_id,
                pipeline="update",
                error_type=type(exc).__name__,
                error=str(exc),
                usage=_usage_to_dict(getattr(exc, "usage", AgentUsage())),
            )
            failure_prefix = (
                "structured_output_failed"
                if isinstance(exc, (ValidationError, AssertionError))
                else "unexpected_pipeline_failure"
            )
            agent_failures["slow_loop:update_pipeline"] = (
                failure_prefix + ": " + str(exc),
            )
            agent_audits["update_pipeline"] = {
                "schema_version": "signal-update-audit-v2",
                "cycle_id": cycle_id,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "usage": _usage_to_dict(
                    getattr(exc, "usage", AgentUsage())
                ),
            }
        all_refs = _ordered_unique([*mined, *updated])

        validations: dict[str, SignalCandidateValidation] = {}
        accepted_hashes: dict[str, str] = {}
        accepted_evaluations: dict[str, str] = {}
        semantic_seen: dict[str, str] = {}
        effectiveness_by_ref: dict[str, Mapping[str, Any]] = {}
        for signal_ref in all_refs:
            spec, skill = self.registry.load_candidate(signal_ref)
            tests = self.registry.load_candidate_tests(signal_ref)
            candidate_hash = self.registry.candidate_hash(signal_ref)
            try:
                stable_ref = self.registry.latest_spec(spec.signal_id).ref
            except ValidationError:
                stable_ref = None
            target_id = candidate_research_targets.get(
                signal_ref, "surge_direction"
            )
            target_labels: dict[str, bool] | None = None
            research_axis: dict[str, Any] = {
                "axis_id": "surge_direction",
                "population": "eligible_discovery_cases",
                "positive": "realized_max_multiple >= 2.0",
                "control": "realized_max_multiple < 2.0",
            }
            if target_id != "surge_direction":
                target_groups = (
                    self.research_target_reveal.get("groups", {})
                    if isinstance(self.research_target_reveal, Mapping)
                    else {}
                )
                target_labels = {
                    str(case_id): str(group) == "ge3_high"
                    for case_id, group in dict(target_groups).items()
                    if str(group) in {"ge3_high", "ge3_low"}
                }
                contract = next(
                    (
                        item
                        for item in active_research_targets()
                        if item.target_id == target_id
                    ),
                    None,
                )
                if contract is None:
                    raise ValidationError(
                        "candidate references an unknown research target"
                    )
                research_axis = contract.descriptor()
            evaluation_identity = self.effectiveness_evaluator.evaluation_identity(
                spec,
                candidate_hash=candidate_hash,
                preferred_case_ids=validation_case_ids.get(signal_ref, ()),
                excluded_case_ids=tuple(
                    _ordered_unique(
                        [
                            *induction_case_ids.get(signal_ref, ()),
                            *self._candidate_evaluation_exclusions(signal_ref),
                        ]
                    )
                ),
                induction_supported=signal_ref in induction_case_ids,
                strict_preferred=self._active_sampling_manifest is not None,
                labels_by_case_id=target_labels,
                research_axis=research_axis,
            )
            evaluation_key, _identity = self.registry.candidate_evaluation_key(
                signal_ref,
                candidate_hash=candidate_hash,
                evaluation_identity=evaluation_identity,
            )
            prior_validation = self.registry.load_candidate_validation(
                signal_ref,
                evaluation_key=evaluation_key,
            )
            reusable_prior = (
                prior_validation is not None
                and prior_validation.get("schema_version")
                == "signal-candidate-evaluation-v3"
                and isinstance(prior_validation.get("effectiveness"), Mapping)
            )
            contract_validation: Mapping[str, Any]
            if stable_ref == signal_ref:
                validation = SignalCandidateValidation(
                    signal_ref=signal_ref,
                    accepted=False,
                    reasons=("candidate version is already stable",),
                    candidate_hash=candidate_hash,
                )
                effectiveness = {
                    "accepted": False,
                    "disposition": "rejected",
                    "status": "not_run",
                    "reasons": ["candidate version is already stable"],
                }
                contract_validation = {
                    "accepted": False,
                    "reasons": ["candidate version is already stable"],
                    "executed_tests": 0,
                }
            elif reusable_prior:
                assert prior_validation is not None
                validation = SignalCandidateValidation(
                    signal_ref=signal_ref,
                    accepted=bool(prior_validation.get("accepted")),
                    reasons=tuple(
                        str(item) for item in prior_validation.get("reasons", ())
                    ),
                    candidate_hash=candidate_hash,
                )
                effectiveness = dict(prior_validation["effectiveness"])
                contract_validation = dict(
                    prior_validation.get("contract_validation", {})
                )
            else:
                checked = self.validator.validate(spec, skill=skill, tests=tests)
                contract_validation = {
                    "accepted": checked.accepted,
                    "reasons": list(checked.reasons),
                    "executed_tests": checked.executed_tests,
                }
                if checked.accepted:
                    paired = self.effectiveness_evaluator.evaluate(
                        spec,
                        skill=skill,
                        preferred_case_ids=validation_case_ids.get(signal_ref, ()),
                        excluded_case_ids=tuple(
                            _ordered_unique(
                                [
                                    *induction_case_ids.get(signal_ref, ()),
                                    *self._candidate_evaluation_exclusions(
                                        signal_ref
                                    ),
                                ]
                            )
                        ),
                        induction_supported=signal_ref in induction_case_ids,
                        strict_preferred=self._active_sampling_manifest is not None,
                        labels_by_case_id=target_labels,
                        research_axis=research_axis,
                    )
                    effectiveness = paired.to_dict()
                    effectiveness = self._attach_generation_case_ids(
                        signal_ref, effectiveness
                    )
                    if target_id != "surge_direction" and paired.accepted:
                        target_reason = (
                            "magnitude target evidence passed its frozen "
                            "high/low check, but Fast absent/present consumption "
                            "and Binary-F1 protection are not assessed"
                        )
                        effectiveness = {
                            **effectiveness,
                            "accepted": False,
                            "disposition": "provisional",
                            "target_supported": True,
                            "promotion_blocked": "fast_consumption_unassessed",
                            "reasons": [target_reason],
                        }
                        reasons = (target_reason,)
                        accepted = False
                    else:
                        effectiveness = {
                            **effectiveness,
                            "target_supported": (
                                paired.accepted
                                if target_id != "surge_direction"
                                else None
                            ),
                        }
                        reasons = paired.reasons
                        accepted = paired.accepted
                else:
                    effectiveness = {
                        "schema_version": "signal-candidate-effectiveness-v4",
                        "signal_ref": signal_ref,
                        "accepted": False,
                        "disposition": "rejected",
                        "status": "not_run",
                        "reasons": ["contract validation failed"],
                    }
                    reasons = checked.reasons
                    accepted = False
                validation = SignalCandidateValidation(
                    signal_ref=checked.signal_ref,
                    accepted=accepted,
                    reasons=tuple(reasons),
                    candidate_hash=candidate_hash,
                    executed_tests=checked.executed_tests,
                )
            if (
                target_id == "surge_direction"
                and stable_ref is None
                and effectiveness.get("disposition") == "provisional"
            ):
                effectiveness = self._apply_pooled_provisional_decision(
                    signal_ref, effectiveness, is_new_signal=True
                )
                if effectiveness.get("disposition") == "promoted":
                    validation = SignalCandidateValidation(
                        signal_ref=signal_ref,
                        accepted=True,
                        reasons=tuple(
                            str(item)
                            for item in effectiveness.get("reasons", ())
                        ),
                        candidate_hash=candidate_hash,
                        executed_tests=validation.executed_tests,
                    )
            semantic = _normalize_semantics(spec.description)
            prior_ref = semantic_seen.get(semantic)
            if validation.accepted and prior_ref is not None:
                duplicate_reason = f"semantic duplicate of candidate {prior_ref}"
                validation = SignalCandidateValidation(
                    signal_ref=signal_ref,
                    accepted=False,
                    reasons=(duplicate_reason,),
                    candidate_hash=candidate_hash,
                    executed_tests=validation.executed_tests,
                )
                contract_validation = {
                    **dict(contract_validation),
                    "accepted": False,
                    "reasons": [
                        *list(contract_validation.get("reasons", ())),
                        duplicate_reason,
                    ],
                }
                effectiveness = {
                    **dict(effectiveness),
                    "accepted": False,
                    "disposition": "rejected",
                    "reasons": [
                        *list(effectiveness.get("reasons", ())),
                        duplicate_reason,
                    ],
                }
            effectiveness_by_ref[signal_ref] = effectiveness
            if validation.accepted:
                semantic_seen[semantic] = signal_ref
                accepted_hashes[signal_ref] = candidate_hash
                accepted_evaluations[signal_ref] = evaluation_key
            validations[signal_ref] = validation
            if not reusable_prior and stable_ref != signal_ref:
                recorded_key = self.registry.record_candidate_validation(
                    signal_ref,
                    candidate_hash=candidate_hash,
                    evaluation_identity=evaluation_identity,
                    accepted=validation.accepted,
                    reasons=validation.reasons,
                    contract_validation=contract_validation,
                    effectiveness=effectiveness,
                )
                if validation.accepted:
                    accepted_evaluations[signal_ref] = recorded_key
        self._revisit_provisional_residents(
            proposed_refs=set(all_refs),
            validations=validations,
            effectiveness_by_ref=effectiveness_by_ref,
            accepted_hashes=accepted_hashes,
            accepted_evaluations=accepted_evaluations,
            agent_audits=agent_audits,
        )
        rejected = dict(agent_failures)
        provisional = {
            signal_ref: tuple(
                str(reason) for reason in effectiveness.get("reasons", ())
            )
            for signal_ref, effectiveness in effectiveness_by_ref.items()
            if effectiveness.get("disposition") == "provisional"
        }
        rejected.update(
            {
                signal_ref: validation.reasons
                for signal_ref, validation in validations.items()
                if not validation.accepted and signal_ref not in provisional
            }
        )
        return SlowLoopValidation(
            mined_candidates=tuple(mined),
            updated_candidates=tuple(updated),
            validated_candidates=accepted_hashes,
            provisional_candidates=provisional,
            rejected=rejected,
            refined_hypotheses=refined_hypotheses,
            input_registry_version=input_snapshot.version,
            input_registry_hash=input_snapshot.registry_hash,
            input_signal_refs=tuple(spec.ref for spec in input_snapshot.specs),
            candidate_evaluations=accepted_evaluations,
            candidate_effectiveness=effectiveness_by_ref,
            candidate_research_targets=candidate_research_targets,
            agent_audits=agent_audits,
            search_input_fingerprint=self._search_input_fingerprint(
                input_snapshot
            ),
            new_candidate_count=sum(
                ref.rsplit(":v", 1)[0]
                not in {
                    item.ref.rsplit(":v", 1)[0] for item in input_snapshot.specs
                }
                for ref in mined
            ),
            new_validated_signal_count=sum(
                ref.rsplit(":v", 1)[0]
                not in {
                    item.ref.rsplit(":v", 1)[0] for item in input_snapshot.specs
                }
                for ref in accepted_hashes
            ),
            updated_signal_count=sum(
                ref.rsplit(":v", 1)[0]
                in {
                    item.ref.rsplit(":v", 1)[0] for item in input_snapshot.specs
                }
                for ref in updated
            ),
        )

    def _candidate_evaluation_exclusions(self, signal_ref: str) -> tuple[str, ...]:
        """Cases a candidate must never be (re-)evaluated on.

        Per-candidate holdout hygiene: the proposal cycle's dev cohort (whose
        labels the generator saw — recorded as ``generation_case_ids`` on the
        candidate's first evaluation) plus every case this exact candidate was
        already evaluated on, so pooled paired evidence counts each case at
        most once and never scores a case the frozen spec was authored
        against.
        """

        excluded: set[str] = set()
        records = self.registry.list_candidate_evaluations(signal_ref)
        for record in records:
            effectiveness = record.get("effectiveness", {})
            excluded.update(
                str(case_id) for case_id in effectiveness.get("case_ids", ())
            )
        for record in records:
            generation = record.get("effectiveness", {}).get("generation_case_ids")
            if isinstance(generation, list):
                excluded.update(str(case_id) for case_id in generation)
                break
        return tuple(sorted(excluded))

    def _current_generation_case_ids(self) -> tuple[str, ...]:
        """The proposal-cycle dev cohort for candidates staged this cycle."""

        return tuple(
            case.case_id for case in self._manifest_cases("dev_case_ids")
        )

    def _attach_generation_case_ids(
        self, signal_ref: str, effectiveness: dict[str, Any]
    ) -> dict[str, Any]:
        """Carry the candidate's original proposal-cycle dev cohort forward.

        A re-proposed or revisited candidate inherits the generation context
        of its first evaluation; only a genuinely first evaluation records
        the current cycle's dev cohort.
        """

        prior_generation = next(
            (
                record.get("effectiveness", {}).get("generation_case_ids")
                for record in self.registry.list_candidate_evaluations(signal_ref)
                if isinstance(
                    record.get("effectiveness", {}).get("generation_case_ids"),
                    list,
                )
            ),
            None,
        )
        effectiveness["generation_case_ids"] = (
            list(prior_generation)
            if isinstance(prior_generation, list)
            else list(self._current_generation_case_ids())
        )
        return effectiveness

    def _provisional_resident_refs(self) -> tuple[str, ...]:
        """New-signal candidates whose latest stored evaluation is provisional.

        A resident is any candidate that a committed cycle recorded as
        provisional — as a new attempt or as a revisited resident whose
        committed evaluation still says provisional — whose signal base is
        not yet stable, and whose latest immutable evaluation still says
        provisional (promotions and pooled eliminations overwrite that
        pointer, so they drop out naturally).
        """

        refs: list[str] = []
        for item in self.workspace.committed_slow_artifacts():
            for attempt in item["slow_experiments"].get("attempts", ()):
                if not isinstance(attempt, Mapping):
                    continue
                if attempt.get("outcome") == "provisional" and attempt.get(
                    "candidate_ref"
                ):
                    refs.append(str(attempt["candidate_ref"]))
            refs.extend(self._provisional_validation_refs(int(item["cycle_id"])))
        refs.extend(self._imported_provisional_refs())
        residents: list[str] = []
        for ref in dict.fromkeys(refs):
            try:
                spec, _skill = self.registry.load_candidate(ref)
            except ValidationError:
                continue
            try:
                self.registry.latest_spec(spec.signal_id)
                continue
            except ValidationError:
                pass
            latest = self.registry.load_candidate_validation(ref)
            if latest is None:
                continue
            if latest.get("effectiveness", {}).get("disposition") == "provisional":
                residents.append(ref)
        return tuple(residents)

    def _provisional_validation_refs(self, cycle_id: int) -> list[str]:
        """Provisional refs in one committed cycle's validation payload.

        Revisited residents never re-enter the experiments attempts list;
        their committed outcome rows live in the cycle's
        slow_loop_validation candidate_effectiveness map.
        """

        path = (
            self.workspace.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_validation.json"
        )
        try:
            payload = _read_json(path)
        except (OSError, ValueError):
            return []
        effectiveness = dict(
            dict(dict(payload).get("validation", {})).get(
                "candidate_effectiveness", {}
            )
        )
        return [
            str(ref)
            for ref, record in effectiveness.items()
            if isinstance(record, Mapping)
            and record.get("disposition") == "provisional"
        ]

    def _imported_provisional_refs(self) -> list[str]:
        """Provisional candidate refs recorded in imported source workspaces.

        Workspace succession carries provisional residents and their pooled
        evaluation history in signals_candidates; their original provisional
        attempts live in the namespaced slow-history cycle artifacts, so
        pooled accumulation continues across workspace boundaries instead of
        restarting from zero in every successor.
        """

        refs: list[str] = []
        history_root = self.workspace.root / "slow_history"
        for path in sorted(
            history_root.glob("*/experiments/cycles/*/slow_experiments.json")
        ):
            try:
                payload = _read_json(path)
            except (OSError, ValueError):
                continue
            for attempt in dict(payload).get("attempts", ()):
                if not isinstance(attempt, Mapping):
                    continue
                if attempt.get("outcome") == "provisional" and attempt.get(
                    "candidate_ref"
                ):
                    refs.append(str(attempt["candidate_ref"]))
        for path in sorted(
            history_root.glob("*/experiments/cycles/*/slow_loop_validation.json")
        ):
            try:
                payload = _read_json(path)
            except (OSError, ValueError):
                continue
            effectiveness = dict(
                dict(dict(payload).get("validation", {})).get(
                    "candidate_effectiveness", {}
                )
            )
            refs.extend(
                str(ref)
                for ref, record in effectiveness.items()
                if isinstance(record, Mapping)
                and record.get("disposition") == "provisional"
            )
        return refs

    def _apply_pooled_provisional_decision(
        self,
        signal_ref: str,
        effectiveness: Mapping[str, Any],
        *,
        is_new_signal: bool,
    ) -> dict[str, Any]:
        """Resolve one provisional new-signal outcome through pooled evidence.

        The resident limit is enforced before pooling: with the cap occupied,
        a fresh directional tie is rejected with an explicit reason instead of
        admitting a third resident.
        """

        payload = dict(effectiveness)
        if not is_new_signal or payload.get("disposition") != "provisional":
            return payload
        other_residents = [
            ref for ref in self._provisional_resident_refs() if ref != signal_ref
        ]
        if len(other_residents) >= _PROVISIONAL_RESIDENT_LIMIT:
            return {
                **payload,
                "disposition": "rejected",
                "reasons": [
                    *list(payload.get("reasons", ())),
                    "provisional resident limit "
                    f"({_PROVISIONAL_RESIDENT_LIMIT}) reached; re-propose after "
                    "a resident resolves",
                ],
            }
        prior_rows = [
            dict(record.get("effectiveness", {}))
            for record in self.registry.list_candidate_evaluations(signal_ref)
            if record.get("effectiveness", {}).get("disposition") == "provisional"
        ]
        decision = pooled_provisional_decision([*prior_rows, payload])
        payload["pooled"] = decision["counts"]
        if decision["action"] == "promote":
            return {
                **payload,
                "disposition": "promoted",
                "accepted": True,
                "reasons": [
                    *list(payload.get("reasons", ())),
                    decision["reason"],
                ],
            }
        if decision["action"] == "eliminate":
            return {
                **payload,
                "disposition": "rejected",
                "reasons": [
                    *list(payload.get("reasons", ())),
                    decision["reason"],
                ],
            }
        return payload

    def _revisit_provisional_residents(
        self,
        *,
        proposed_refs: set[str],
        validations: dict[str, Any],
        effectiveness_by_ref: dict[str, Mapping[str, Any]],
        accepted_hashes: dict[str, str],
        accepted_evaluations: dict[str, str],
        agent_audits: dict[str, Any],
    ) -> None:
        """Re-evaluate surviving residents on this cycle's fresh check cohort."""

        pending = [
            ref for ref in self._provisional_resident_refs() if ref not in proposed_refs
        ]
        audit: dict[str, Any] = {
            "schema_version": "provisional-revisit-audit-v1",
            "residents": list(pending),
            "evaluated": [],
            "skipped": pending[_PROVISIONAL_RESIDENT_LIMIT:],
        }
        check_cases = self._manifest_cases("check_case_ids")
        for ref in pending[:_PROVISIONAL_RESIDENT_LIMIT]:
            spec, skill = self.registry.load_candidate(ref)
            candidate_hash = self.registry.candidate_hash(ref)
            preferred = tuple(case.case_id for case in check_cases)
            excluded = self._candidate_evaluation_exclusions(ref)
            paired = self.effectiveness_evaluator.evaluate(
                spec,
                skill=skill,
                preferred_case_ids=preferred,
                excluded_case_ids=excluded,
                induction_supported=True,
                strict_preferred=bool(check_cases),
            )
            effectiveness = self._apply_pooled_provisional_decision(
                ref, paired.to_dict(), is_new_signal=True
            )
            effectiveness = self._attach_generation_case_ids(ref, effectiveness)
            accepted = effectiveness.get("disposition") == "promoted"
            evaluation_identity = self.effectiveness_evaluator.evaluation_identity(
                spec,
                candidate_hash=candidate_hash,
                preferred_case_ids=preferred,
                excluded_case_ids=excluded,
                induction_supported=True,
                strict_preferred=bool(check_cases),
            )
            recorded_key = self.registry.record_candidate_validation(
                ref,
                candidate_hash=candidate_hash,
                evaluation_identity=evaluation_identity,
                accepted=accepted,
                reasons=tuple(
                    str(item) for item in effectiveness.get("reasons", ())
                ),
                contract_validation={
                    "accepted": accepted,
                    "reasons": [
                        "provisional resident re-evaluated on the fresh check cohort"
                    ],
                    "executed_tests": 0,
                },
                effectiveness=effectiveness,
            )
            validations[ref] = SignalCandidateValidation(
                signal_ref=ref,
                accepted=accepted,
                reasons=tuple(str(item) for item in effectiveness.get("reasons", ())),
                candidate_hash=candidate_hash,
            )
            effectiveness_by_ref[ref] = effectiveness
            if accepted:
                accepted_hashes[ref] = candidate_hash
                accepted_evaluations[ref] = recorded_key
            audit["evaluated"].append(
                {
                    "signal_ref": ref,
                    "disposition": effectiveness.get("disposition"),
                    "pooled": effectiveness.get("pooled"),
                }
            )
        agent_audits["provisional_revisit"] = audit

    def _run_signal_update(
        self,
        *,
        cycle_id: int,
        suggested_refs: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Run a bounded portfolio of independent single-target Updates."""

        suggested = tuple(suggested_refs)
        targets = (
            self._select_signal_update_targets(suggested_refs=suggested)
            if suggested
            else self._select_signal_update_targets()
        )
        base_audit: dict[str, Any] = {
            "schema_version": "signal-update-audit-v2",
            "cycle_id": cycle_id,
            "status": "completed",
            "model_called": False,
            "model_target_count": 0,
            "model_usage": _usage_to_dict(AgentUsage()),
            "target_limit": _SIGNAL_UPDATE_TARGET_LIMIT,
            "target_count": len(targets),
            "candidate_refs": [],
            "targets": [],
        }
        if not targets:
            return self._signal_update_output(
                audit={**base_audit, "disposition": "no_actionable_target"}
            )

        dev_cases = self._manifest_cases("dev_case_ids")
        check_cases = self._manifest_cases("check_case_ids")
        cases = dev_cases or _sample_signal_discovery_cases(
            self.discovery_cases,
            limit=self.effectiveness_evaluator.case_limit + 4,
        )
        executor = SignalExecutor(
            self.registry.freeze(),
            self.raw_info_store,
            resolver=self.evidence_resolver,
            deterministic_functions=self.validator.deterministic_functions,
            llm_runner=self.llm_signal_runner,
        )
        candidate_refs: list[str] = []
        induction_case_ids: dict[str, tuple[str, ...]] = {}
        validation_case_ids: dict[str, tuple[str, ...]] = {}
        failures: dict[str, tuple[str, ...]] = {}
        target_audits: list[dict[str, Any]] = []
        for target in targets:
            signal_ref = str(target["signal_ref"])
            try:
                call_args = {
                    "cycle_id": cycle_id,
                    "target": target,
                    "cases": cases,
                    "executor": executor,
                }
                if check_cases:
                    call_args["check_cases"] = check_cases
                output = self._run_one_signal_update(**call_args)
            except ValidationError as exc:
                failures[f"update:{signal_ref}"] = (
                    "structured_output_failed: " + str(exc),
                )
                target_audits.append(
                    {
                        "schema_version": "signal-update-target-audit-v1",
                        "cycle_id": cycle_id,
                        "status": "failed",
                        "model_called": bool(
                            getattr(exc, "usage", AgentUsage()).llm_calls
                        ),
                        "target": dict(target),
                        "issue_fingerprint": _canonical_hash(target),
                        "error": str(exc),
                        "request_refs": list(
                            getattr(exc, "details", {}).get("request_refs", ())
                        ),
                        "usage": _usage_to_dict(
                            getattr(exc, "usage", AgentUsage())
                        ),
                    }
                )
                continue
            candidate_refs.extend(output["candidate_refs"])
            induction_case_ids.update(output["induction_case_ids"])
            validation_case_ids.update(output["validation_case_ids"])
            failures.update(output["failures"])
            target_audits.append(dict(output["audit"]))

        model_usage = AgentUsage()
        for item in target_audits:
            raw_usage = item.get("model_usage", item.get("usage", {}))
            if isinstance(raw_usage, Mapping):
                model_usage = model_usage + _usage_from_dict(dict(raw_usage))
        model_target_count = sum(
            bool(item.get("model_called")) for item in target_audits
        )
        aggregate_audit = {
            **base_audit,
            "disposition": "portfolio_completed",
            "model_called": model_target_count > 0,
            "model_target_count": model_target_count,
            "model_usage": _usage_to_dict(model_usage),
            "candidate_refs": list(candidate_refs),
            "targets": target_audits,
        }
        return self._signal_update_output(
            candidate_refs=candidate_refs,
            induction_case_ids=induction_case_ids,
            validation_case_ids=validation_case_ids,
            failures=failures,
            audit=aggregate_audit,
        )

    def _run_one_signal_update(
        self,
        *,
        cycle_id: int,
        target: Mapping[str, Any],
        cases: tuple[EvolutionCase, ...],
        check_cases: tuple[EvolutionCase, ...] = (),
        executor: SignalExecutor,
    ) -> dict[str, Any]:
        """Run one issuer-split Update without affecting sibling targets."""

        base_audit: dict[str, Any] = {
            "schema_version": "signal-update-target-audit-v1",
            "cycle_id": cycle_id,
            "status": "completed",
            "model_called": False,
            "candidate_refs": [],
        }
        signal_ref = str(target["signal_ref"])
        issue_fingerprint = _canonical_hash(target)
        base_audit.update(
            {
                "target": dict(target),
                "issue_fingerprint": issue_fingerprint,
            }
        )
        spec = self.registry.load_spec(signal_ref)
        skill = self.registry.load_skill(signal_ref)
        stable_tests = list(self.registry.load_tests(signal_ref))
        classified: dict[
            str, list[tuple[EvolutionCase, SignalResult, RawInfoResolution]]
        ] = {
            "wrong": [],
            "correct": [],
            "unavailable": [],
            "neutral": [],
        }
        technical_failures: list[dict[str, Any]] = []
        execution_usage = AgentUsage()
        for case in cases:
            batch = executor.execute_batch(
                (signal_ref,),
                company_id=case.company_id,
                as_of=case.prediction_time,
                identity=case.basic_info,
            )
            execution_usage = execution_usage + batch.usage
            result = batch.results[0]
            resolution = batch.resolutions[0]
            if result.execution_status not in {
                SignalExecutionStatus.SUCCESS,
                SignalExecutionStatus.DOMAIN_UNAVAILABLE,
            }:
                technical_failures.append(
                    {
                        "case_id": case.case_id,
                        "company_id": case.company_id,
                        "execution_status": result.execution_status.value,
                        "error_code": result.execution_error_code,
                        "error_message": result.execution_error_message,
                        "resolution": resolution.to_dict(),
                    }
                )
                continue
            if result.value is SignalValue.UNAVAILABLE:
                bucket = "unavailable"
            elif result.value is SignalValue.NEUTRAL:
                bucket = "neutral"
            elif (result.value is SignalValue.POSITIVE) == case.ground_truth.is_surge:
                bucket = "correct"
            else:
                bucket = "wrong"
            classified[bucket].append((case, result, resolution))

        problem_type = str(target["problem_type"])
        primary_name = (
            "unavailable" if problem_type == "repeated_unavailable" else "wrong"
        )
        primary = list(classified[primary_name][:2])
        primary_sources = [primary_name] * len(primary)
        if problem_type == "repeated_explicit_misleading" and len(primary) < 2:
            sourced_unavailable = [
                item for item in classified["unavailable"] if item[2].documents
            ]
            supplement = sourced_unavailable[: 2 - len(primary)]
            primary.extend(supplement)
            primary_sources.extend(["domain_unavailable"] * len(supplement))
        boundary_pool = [
            *classified["correct"],
            *classified["neutral"],
        ]
        boundary = boundary_pool[:2]
        induction = tuple([*primary, *boundary])
        induction_companies = {
            case.company_id for case, _result, _resolution in induction
        }
        holdout = (
            check_cases[: self.effectiveness_evaluator.case_limit]
            if check_cases
            else tuple(
                case
                for case in cases
                if case.company_id not in induction_companies
            )[: self.effectiveness_evaluator.case_limit]
        )
        local_selection = {
            "problem_bucket": primary_name,
            "primary_sources": primary_sources,
            "available_bucket_counts": {
                name: len(values) for name, values in classified.items()
            },
            "technical_failure_count": len(technical_failures),
            "induction_case_ids": [
                case.case_id for case, _result, _resolution in induction
            ],
            "holdout_case_ids": [case.case_id for case in holdout],
            "issuer_disjoint": not (
                induction_companies & {case.company_id for case in holdout}
            ),
        }
        execution_inputs = sorted(
            (
                {
                    "case_id": case.case_id,
                    "company_id": case.company_id,
                    "prediction_time": case.prediction_time.isoformat(),
                    "resolution": resolution.to_dict(),
                }
                for values in classified.values()
                for case, _result, resolution in values
            ),
            key=lambda item: item["case_id"],
        )
        work_fingerprint = _canonical_hash(
            {
                "schema_version": "signal-update-work-v1",
                "issue_fingerprint": issue_fingerprint,
                "local_selection": local_selection,
                "execution_inputs": execution_inputs,
                "update_model": self._role_work_identity(self.update_model),
                "projection_protocol": "signal-update-evidence-packet-v2",
            }
        )
        base_audit["work_fingerprint"] = work_fingerprint
        prior = self._prior_signal_update(work_fingerprint)
        if prior is not None:
            staged_ref = str(prior.get("staged_ref", ""))
            if staged_ref:
                validation = self.registry.load_candidate_validation(staged_ref)
                effectiveness = (
                    dict(validation.get("effectiveness", {}))
                    if validation is not None
                    else {}
                )
                if effectiveness.get("disposition") == "provisional":
                    return self._signal_update_output(
                        candidate_refs=(staged_ref,),
                        induction_case_ids={
                            staged_ref: tuple(local_selection["induction_case_ids"])
                        },
                        validation_case_ids={
                            staged_ref: tuple(local_selection["holdout_case_ids"])
                        },
                        audit={
                            **base_audit,
                            "disposition": "reused_provisional",
                            "staged_ref": staged_ref,
                            "local_selection": local_selection,
                        },
                    )
            return self._signal_update_output(
                audit={
                    **base_audit,
                    "disposition": "unchanged_work_suppressed",
                    "local_selection": local_selection,
                }
            )
        if (
            not primary
            or not boundary
            or len(holdout) < self.effectiveness_evaluator.minimum_cases
        ):
            return self._signal_update_output(
                audit={
                    **base_audit,
                    "disposition": "defer",
                    "defer_reason": "insufficient_local_induction_or_holdout",
                    "local_selection": local_selection,
                    "execution_usage": _usage_to_dict(execution_usage),
                    "technical_failures": technical_failures,
                }
            )

        next_ref = f"{spec.signal_id}:v{spec.version + 1}"
        try:
            prior_candidate_validation = self.registry.load_candidate_validation(
                next_ref
            )
            prior_candidate, _prior_skill = self.registry.load_candidate(next_ref)
        except ValidationError:
            prior_candidate_validation = None
            prior_candidate = None
        if (
            prior_candidate is not None
            and prior_candidate.signal_id == spec.signal_id
            and prior_candidate.version == spec.version + 1
            and prior_candidate_validation is not None
            and prior_candidate_validation.get("status") == "provisional"
        ):
            return self._signal_update_output(
                candidate_refs=(next_ref,),
                induction_case_ids={
                    next_ref: tuple(local_selection["induction_case_ids"])
                },
                validation_case_ids={
                    next_ref: tuple(local_selection["holdout_case_ids"])
                },
                audit={
                    **base_audit,
                    "disposition": "reused_provisional_new_evaluation",
                    "staged_ref": next_ref,
                    "local_selection": local_selection,
                    "execution_usage": _usage_to_dict(execution_usage),
                    "technical_failures": technical_failures,
                },
            )

        induction_packets: list[dict[str, Any]] = []
        resolutions: list[dict[str, Any]] = []
        for index, (case, result, resolution) in enumerate(induction, start=1):
            case_ref = f"update-case-{index:03d}"
            packet, resolution_audit = self._signal_update_evidence_packet(
                case_ref,
                case,
                spec=spec,
                result=result,
                resolution=resolution,
            )
            induction_packets.append(packet)
            resolutions.append(resolution_audit)

        payload = {
            "update_contract_version": "signal-update-decision-v2",
            "research_objective": signal_research_objective(),
            "fixed_prior": self.priors.update_signal,
            "target": {
                "signal_ref": signal_ref,
                "problem_type": target["problem_type"],
                "stable_spec": spec.to_dict(),
                "stable_skill": skill,
                "learned_profile": self.registry.load_learning_profile(signal_ref),
            },
            "induction_cases": induction_packets,
            "slow_method_memory": self._slow_method_view("Update"),
            "candidate_contract": {
                "execution_semantics": signal_candidate_execution_contract(),
                "arguments_schema": self._candidate_arguments_schema(clone=True),
                "deterministic_function_contracts": deterministic_signal_function_contracts(
                    self.validator.deterministic_functions
                ),
                "changed_paths_allowed": list(SIGNAL_UPDATE_MUTABLE_PATHS),
                "changed_paths_excluded": [
                    "spec.version",
                    "spec.definition",
                    "tests",
                    "whole-section aliases",
                ],
                "vnext_template": {
                    "signal_ref": signal_ref,
                    "spec": {**spec.to_dict(), "version": spec.version + 1},
                    "skill": skill,
                    "tests": stable_tests,
                },
            },
            "rules": {
                "dispositions": ["no_change", "defer", "update"],
                "distinguish_routing_applicability_from_signal_defect": True,
                "holdout_hidden": True,
                "candidate_only_when_update": True,
            },
        }
        step = self.update_model.update(payload)
        decision = step.value
        if decision.signal_ref != signal_ref:
            raise CandidateExecutionRejected(
                "signal_update_decision",
                "Signal Update decision changed the local target ref",
                step.usage,
            )
        audit = {
            **base_audit,
            "model_called": True,
            "model_usage": _usage_to_dict(
                step.usage
                + _usage_from_dict(
                    dict(
                        dict(
                            payload["slow_method_memory"].get(
                                "source_view_manifest", {}
                            )
                        ).get("source_read_usage", {})
                    )
                )
            ),
            "request_refs": list(
                _ordered_unique(
                    [
                        *dict(
                            payload["slow_method_memory"].get(
                                "source_view_manifest", {}
                            )
                        ).get("source_read_request_refs", ()),
                        *step.metadata.get("request_refs", ()),
                    ]
                )
            ),
            "execution_usage": _usage_to_dict(execution_usage),
            "local_selection": local_selection,
            "resolutions": resolutions,
            "technical_failures": technical_failures,
            "decision": decision.to_dict(),
            "disposition": decision.disposition,
        }
        audit["diagnostic_counts"] = {
            "evidence_verdict": {
                name: sum(
                    str(item.get("evidence_verdict", "")) == name
                    for item in decision.case_diagnostics
                )
                for name in ("supported", "contradicted", "insufficient")
            },
            "outcome_relation": {
                name: sum(
                    str(item.get("outcome_relation", "")) == name
                    for item in decision.case_diagnostics
                )
                for name in ("aligned", "misaligned", "not_assessable")
            },
        }
        if decision.disposition != "update":
            return self._signal_update_output(audit=audit)
        assert decision.candidate is not None
        try:
            staged_ref = self._stage_update_candidate(
                signal_ref=signal_ref,
                candidate=decision.candidate,
                changed_paths=decision.changed_paths,
            )
        except ValidationError as exc:
            raise CandidateExecutionRejected(
                "signal_update_candidate",
                str(exc),
                step.usage,
            ) from exc
        audit["candidate_refs"] = [staged_ref]
        audit["staged_ref"] = staged_ref
        return self._signal_update_output(
            candidate_refs=(staged_ref,),
            induction_case_ids={
                staged_ref: tuple(
                    case.case_id for case, _result, _resolution in induction
                )
            },
            validation_case_ids={
                staged_ref: tuple(case.case_id for case in holdout)
            },
            audit=audit,
        )

    def _recent_update_target_refs(self, *, cycles: int = 2) -> dict[str, int]:
        """Count staged update targets per signal over the last committed cycles.

        A signal whose vNext was already staged recently keeps accruing
        evaluation observations, so it stays at the top of the problem
        ranking forever; this count is the rotation input that gives other
        equally problematic signals a turn.
        """

        counts: dict[str, int] = {}
        for item in self.workspace.committed_slow_artifacts()[-cycles:]:
            for attempt in item["slow_experiments"].get("attempts", ()):
                if not isinstance(attempt, Mapping):
                    continue
                parent = attempt.get("parent_signal_ref")
                if attempt.get("stage") == "Update" and parent:
                    base = str(parent).rsplit(":v", 1)[0]
                    counts[base] = counts.get(base, 0) + 1
        return counts

    def _select_signal_update_targets(
        self,
        *,
        limit: int = _SIGNAL_UPDATE_TARGET_LIMIT,
        suggested_refs: Iterable[str] = (),
        recent_worked: Mapping[str, int] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        if limit < 1:
            raise ValidationError("Signal Update target limit must be positive")
        suggested = set(str(item) for item in suggested_refs)
        worked = (
            dict(recent_worked)
            if recent_worked is not None
            else self._recent_update_target_refs()
        )
        targets: list[tuple[int, str, dict[str, Any]]] = []
        for card in self.registry.list_signal_cards():
            profile = dict(card.learned_profile)
            unique = int(profile.get("unique_observations", 0))
            if unique < 2:
                continue
            directional = dict(profile.get("directional", {}))
            attribution = dict(profile.get("reflection_attribution", {}))
            misleading = int(attribution.get("misleading", 0))
            wrong = int(directional.get("wrong", 0))
            unavailable = int(directional.get("unavailable", 0))
            unavailable_with_inputs = int(
                directional.get("unavailable_with_inputs", 0)
            )
            if misleading >= 2:
                problem_type = "repeated_explicit_misleading"
                score = 300 + misleading
            elif wrong >= 2:
                problem_type = "repeated_directional_wrong"
                score = 200 + wrong
            elif unavailable_with_inputs >= 2 and unavailable * 2 >= unique:
                problem_type = "repeated_unavailable"
                score = 100 + unavailable_with_inputs
            else:
                continue
            recent = int(worked.get(card.ref.rsplit(":v", 1)[0], 0))
            if card.ref in suggested:
                score += 1000
            score -= 600 * recent
            target = {
                "signal_ref": card.ref,
                "problem_type": problem_type,
                "support": {
                    "unique_observations": unique,
                    "misleading_attributions": misleading,
                    "directional_wrong": wrong,
                    "unavailable": unavailable,
                    "unavailable_with_inputs": unavailable_with_inputs,
                },
                "worked_recent_cycles": recent,
                "recurring_contexts": list(
                    profile.get("recurring_contexts", ())
                )[:3],
            }
            targets.append((score, card.ref, target))
        ranked = sorted(targets, key=lambda item: (-item[0], item[1]))
        return tuple(item[2] for item in ranked[:limit])

    @staticmethod
    def _h1_update_refs(audit: Mapping[str, Any]) -> tuple[str, ...]:
        """Recover adapter-validated H1 update suggestions for target ordering."""

        value: Mapping[str, Any] = audit
        if (
            audit.get("track") == "hypothesis_then_exploration_fallback"
            and isinstance(audit.get("hypothesis"), Mapping)
        ):
            value = audit["hypothesis"]
        h1 = dict(value.get("stages", {})).get("H1", {})
        metadata = h1.get("conclusion", {}) if isinstance(h1, Mapping) else {}
        if not isinstance(metadata, Mapping):
            return ()
        refs: list[str] = []
        for row in metadata.get("need_dispositions", ()):
            if not isinstance(row, Mapping) or row.get("disposition") != "update_existing":
                continue
            refs.extend(str(item) for item in row.get("signal_refs", ()))
        return _ordered_unique(refs)

    def _prior_signal_update(
        self, work_fingerprint: str
    ) -> Mapping[str, Any] | None:
        for path in reversed(
            sorted(
                (self.workspace.experiments_root / "cycles").glob(
                    "cycle-*/slow_loop_validation.json"
                )
            )
        ):
            payload = _read_json(path)
            validation = payload.get("validation", {})
            if not isinstance(validation, Mapping):
                continue
            audits = validation.get("agent_audits", {})
            if not isinstance(audits, Mapping):
                continue
            audit = audits.get("update_pipeline", {})
            if not isinstance(audit, Mapping):
                continue
            candidates = [audit]
            target_audits = audit.get("targets", ())
            if isinstance(target_audits, list):
                candidates.extend(
                    item for item in target_audits if isinstance(item, Mapping)
                )
            for candidate in candidates:
                if (
                    candidate.get("work_fingerprint") == work_fingerprint
                    and (
                        candidate.get("disposition") == "no_change"
                        or bool(candidate.get("staged_ref"))
                    )
                ):
                    return candidate
        return None

    def _stage_update_candidate(
        self,
        *,
        signal_ref: str,
        candidate: Mapping[str, Any],
        changed_paths: Iterable[str],
    ) -> str:
        stable = self.registry.load_spec(signal_ref)
        updated, skill_value, raw_tests = validate_signal_update_candidate(
            signal_ref,
            candidate,
            stable,
            stable_skill=self.registry.load_skill(signal_ref),
            stable_tests=self.registry.load_tests(signal_ref),
            changed_paths=changed_paths,
        )
        return self.registry.stage_candidate(
            updated,
            skill=skill_value,
            tests=raw_tests,
            origin=f"update:{signal_ref}",
        )

    @staticmethod
    def _signal_update_output(
        *,
        audit: Mapping[str, Any],
        candidate_refs: Iterable[str] = (),
        induction_case_ids: Mapping[str, tuple[str, ...]] | None = None,
        validation_case_ids: Mapping[str, tuple[str, ...]] | None = None,
        failures: Mapping[str, tuple[str, ...]] | None = None,
    ) -> dict[str, Any]:
        return {
            "candidate_refs": tuple(candidate_refs),
            "induction_case_ids": dict(induction_case_ids or {}),
            "validation_case_ids": dict(validation_case_ids or {}),
            "failures": dict(failures or {}),
            "audit": dict(audit),
        }

    def _run_signal_mining(self, *, cycle_id: int) -> dict[str, Any]:
        """Run the production mining entry for this cycle.

        Dispatch is capability-based: with a frozen v8 sampling manifest and a
        mining model exposing a JSON role caller, the LabelAwareMining
        controller is the production path (Phase 6 cutover). H/E role-protocol
        models keep their tracks for read-only history replay, and workspaces
        without an active manifest keep the v7 cadence.
        """

        if cycle_id < 1:
            raise ValidationError("Signal Mining cycle id must be positive")
        caller = getattr(self.mining_model, "caller", None)
        controller_ready = callable(getattr(caller, "complete_json", None))
        if self._active_sampling_manifest is not None and controller_ready:
            return self._run_controller_mining(cycle_id=cycle_id)
        if self._active_sampling_manifest is None:
            return self._run_signal_mining_legacy(cycle_id=cycle_id)
        return self._run_signal_mining_role_tracks(cycle_id=cycle_id)

    def _run_signal_mining_role_tracks(self, *, cycle_id: int) -> dict[str, Any]:
        """Run bounded H and independent E role tracks for H/E-style models.

        Kept for mining models built on the H/E role protocol (no JSON role
        caller); production LLM models dispatch to the controller instead.
        """

        if cycle_id < 1:
            raise ValidationError("Signal Mining cycle id must be positive")
        hypothesis_failure: Exception | None = None
        try:
            hypothesis_result = self._run_hypothesis_mining(cycle_id=cycle_id)
        except (EvolutionControlFlow, OpenAIClientError):
            raise
        except Exception as exc:
            hypothesis_failure = exc
            _emit_progress(
                self.on_progress, "signal_mining_track_failed", cycle_id=cycle_id,
                track="hypothesis", failure_stage=getattr(exc, "stage", "hypothesis"),
                error_type=type(exc).__name__, reason=str(exc),
            )
            hypothesis_result = self._mining_output(
                audit={
                    "schema_version": "signal-mining-audit-v1",
                    "status": "failed",
                    "cycle_id": cycle_id,
                    "track": "hypothesis",
                    "limits": self.mining_config.to_dict(),
                    "stages": {},
                    "failure_stage": getattr(exc, "stage", "hypothesis"),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "failure_details": dict(getattr(exc, "details", {})),
                    "usage": _usage_to_dict(
                        getattr(exc, "usage", AgentUsage())
                    ),
                    "candidate_refs": [],
                    "refined_hypotheses": {},
                },
                refined={},
            )
        try:
            exploration_result = self._run_exploration_mining(cycle_id=cycle_id)
        except (EvolutionControlFlow, OpenAIClientError):
            raise
        except Exception as exc:
            _emit_progress(
                self.on_progress, "signal_mining_track_failed", cycle_id=cycle_id,
                track="exploration", failure_stage=getattr(exc, "stage", "exploration"),
                error_type=type(exc).__name__, reason=str(exc),
            )
            exploration_result = self._mining_output(
                audit={
                    "schema_version": "signal-mining-audit-v1",
                    "status": "failed",
                    "cycle_id": cycle_id,
                    "track": "exploration",
                    "stages": {},
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "usage": _usage_to_dict(getattr(exc, "usage", AgentUsage())),
                    "candidate_refs": [],
                },
                refined={
                    "exploration": (
                        "independent Exploration failed: " + str(exc),
                    )
                },
                failures={
                    "slow_loop:exploration": (
                        "structured_output_failed: " + str(exc),
                    )
                },
            )
            if hypothesis_failure is not None:
                exploration_result["audit"]["hypothesis_failure"] = str(
                    hypothesis_failure
                )
        return _merge_mining_fallback(hypothesis_result, exploration_result)

    def _run_controller_mining(self, *, cycle_id: int) -> dict[str, Any]:
        """Run direction and active magnitude tracks without label mixing."""

        direction_dev = self._manifest_cases("dev_case_ids")
        direction_check = self._manifest_cases("check_case_ids")
        direction_labels = {
            case.case_id: (
                "positive" if case.ground_truth.is_surge else "control"
            )
            for case in (*direction_dev, *direction_check)
        }
        outputs = [
            self._run_controller_mining_axis(
                cycle_id=cycle_id,
                axis_id="surge_direction",
                research_axis={
                    "axis_id": "surge_direction",
                    "population": "eligible_discovery_cases",
                    "positive": "realized_max_multiple >= 2.0",
                    "control": "realized_max_multiple < 2.0",
                },
                dev_cases=direction_dev,
                check_cases=direction_check,
                labels_by_case_id=direction_labels,
            )
        ]

        target_sampling = (
            self.research_target_sampling.get("sampling", {})
            if isinstance(self.research_target_sampling, Mapping)
            else {}
        )
        target_groups = (
            self.research_target_reveal.get("groups", {})
            if isinstance(self.research_target_reveal, Mapping)
            else {}
        )
        target_id = (
            str(self.research_target_sampling.get("target_id", ""))
            if isinstance(self.research_target_sampling, Mapping)
            else ""
        )
        if target_id and isinstance(target_sampling, Mapping) and isinstance(
            target_groups, Mapping
        ):
            case_by_id = {case.case_id: case for case in self.discovery_cases}
            target_dev = tuple(
                case_by_id[str(case_id)]
                for case_id in target_sampling.get("dev_case_ids", ())
                if str(case_id) in case_by_id
            )
            target_check = tuple(
                case_by_id[str(case_id)]
                for case_id in target_sampling.get("check_case_ids", ())
                if str(case_id) in case_by_id
            )
            target_labels = {
                str(case_id): (
                    "positive" if str(group) == "ge3_high" else "control"
                )
                for case_id, group in target_groups.items()
                if str(group) in {"ge3_high", "ge3_low"}
            }
            target_contract = next(
                (
                    contract
                    for contract in active_research_targets()
                    if contract.target_id == target_id
                ),
                None,
            )
            if target_contract is None:
                raise ValidationError(
                    "active magnitude sampling references an unknown target"
                )
            required_ids = {
                case.case_id for case in (*target_dev, *target_check)
            }
            if not target_dev or not target_check or not required_ids <= set(
                target_labels
            ):
                raise ValidationError(
                    "active magnitude target lacks complete dev/check labels"
                )
            outputs.append(
                self._run_controller_mining_axis(
                    cycle_id=cycle_id,
                    axis_id=target_id,
                    research_axis={
                        "axis_id": target_id,
                        **target_contract.descriptor(),
                    },
                    dev_cases=target_dev,
                    check_cases=target_check,
                    labels_by_case_id=target_labels,
                )
            )

        if len(outputs) == 1:
            return outputs[0]

        def merged_mapping(key: str) -> dict[str, Any]:
            merged: dict[str, Any] = {}
            for output in outputs:
                overlap = set(merged) & set(dict(output.get(key, {})))
                if overlap:
                    raise ValidationError(
                        f"research axes produced conflicting {key}: "
                        + ", ".join(sorted(overlap))
                    )
                merged.update(dict(output.get(key, {})))
            return merged

        return {
            "candidate_refs": tuple(
                ref
                for output in outputs
                for ref in output.get("candidate_refs", ())
            ),
            "induction_case_ids": merged_mapping("induction_case_ids"),
            "validation_case_ids": merged_mapping("validation_case_ids"),
            "candidate_research_targets": merged_mapping(
                "candidate_research_targets"
            ),
            "refined_hypotheses": merged_mapping("refined_hypotheses"),
            "failures": merged_mapping("failures"),
            "capability_gaps": merged_mapping("capability_gaps"),
            "audit": {
                "schema_version": "signal-mining-multi-axis-audit-v1",
                "cycle_id": cycle_id,
                "track": "controller_multi_axis",
                "status": "completed",
                "axes": {
                    str(output["audit"].get("axis_id", "surge_direction")): dict(
                        output["audit"]
                    )
                    for output in outputs
                },
                "candidate_refs": [
                    ref
                    for output in outputs
                    for ref in output.get("candidate_refs", ())
                ],
            },
        }

    def _run_controller_mining_axis(
        self,
        *,
        cycle_id: int,
        axis_id: str,
        research_axis: Mapping[str, Any],
        dev_cases: tuple[EvolutionCase, ...],
        check_cases: tuple[EvolutionCase, ...],
        labels_by_case_id: Mapping[str, str],
    ) -> dict[str, Any]:
        """Drive both controller seeds for one runtime-owned research axis."""

        caller = getattr(self.mining_model, "caller", None)
        if not callable(getattr(caller, "complete_json", None)):
            audit = {
                "schema_version": "signal-mining-audit-v1",
                "cycle_id": cycle_id,
                "track": "controller",
                "axis_id": axis_id,
                "status": "unavailable",
                "reason": "controller caller is not configured",
                "candidate_refs": [],
                "refined_hypotheses": {},
            }
            return self._mining_output(audit=audit, refined={})

        opaque = {
            case.case_id: f"case-{index:03d}"
            for index, case in enumerate(dev_cases, start=1)
        }
        case_pairs = [(opaque[case.case_id], case) for case in dev_cases]
        label_map = {
            opaque[case.case_id]: str(labels_by_case_id[case.case_id])
            for case in dev_cases
        }
        context = self._mining_context(cycle_id=cycle_id)
        evidence_manifest = _mask_identity_values(
            self._h1_measurable_evidence_manifest(case_pairs),
            self.slow_role_identity_guards,
            expand_aliases=False,
        )
        backlog_needs = tuple(
            dict(row)
            for row in dict(context.get("capability_backlog", {})).get(
                "signal_need_items", ()
            )
            if isinstance(row, Mapping) and row.get("need_ref")
        )
        catalog = tuple(
            {
                "signal_ref": str(card.get("signal_ref", "")),
                "description": str(card.get("description", "")),
            }
            for card in context.get("stable_signal_cards", ())
            if isinstance(card, Mapping)
        )
        model = MiningAgentRoleModel(caller)

        narrative_documents = [
            document
            for case in dev_cases
            for document in self.raw_info_store.documents
            if document.company_id == case.company_id
            and document.available_at <= case.prediction_time
            and _evidence_source_family(document.source_type)
            in {"filing", "transcript", "news"}
        ]
        attribute_vocabulary = derive_attribute_vocabulary(
            narrative_documents
        )

        candidates: list[dict[str, Any]] = []
        cited: dict[str, dict[str, Any]] = {}

        seed_reports: list[dict[str, Any]] = []
        failures: dict[str, tuple[str, ...]] = {}
        capability_gaps: dict[str, dict[str, Any]] = {}
        need_disposition_counts: dict[str, int] = {}
        fetched_case_refs: dict[str, tuple[str, ...]] = {}
        for seed in ("hypothesis", "discovery"):
            def seed_sink(candidate: Mapping[str, Any], _seed=seed) -> Mapping[str, Any]:
                candidates.append((_seed, dict(candidate)))
                return {"status": "validated"}

            try:
                controller = LabelAwareMiningController(
                    store=self.raw_info_store,
                    model=model,
                    case_pairs=case_pairs,
                    measurable_evidence_manifest=evidence_manifest,
                    signal_catalog=catalog,
                    seed=seed,
                    cycle_id=cycle_id,
                    backlog_needs=backlog_needs if seed == "hypothesis" else (),
                    identity_aliases=self.slow_role_identity_guards,
                    attribute_vocabulary=attribute_vocabulary,
                    prior_modality_footprints=tuple(
                        context.get("prior_modality_footprints", ())
                    ),
                    validation_sink=seed_sink,
                    label_map=label_map,
                    research_axis=research_axis,
                )
                result = controller.run()
            except (EvolutionControlFlow, OpenAIClientError):
                raise
            except Exception as exc:
                failures[f"slow_loop:mining_controller:{axis_id}:{seed}"] = (
                    f"{type(exc).__name__}: {exc}",
                )
                seed_reports.append(
                    {"seed": seed, "status": "failed", "error": str(exc)}
                )
                continue
            for row in result.need_dispositions:
                key = str(row.get("disposition", ""))
                need_disposition_counts[key] = (
                    need_disposition_counts.get(key, 0) + 1
                )
            fetched = tuple(
                sorted(
                    {
                        ref
                        for entry in result.ledger
                        for ref in entry.case_refs
                    }
                )
            )
            fetched_case_refs[seed] = fetched
            evidence_by_ref: dict[str, Any] = {
                **getattr(controller, "_facts", {}),
                **getattr(controller, "_events", {}),
            }
            cited[seed] = evidence_by_ref
            seed_reports.append(
                {
                    "seed": seed,
                    "axis_id": axis_id,
                    "status": "completed",
                    "terminal_kind": result.terminal_kind,
                    "model_calls": result.model_calls,
                    "ledger_actions": len(result.ledger),
                    "explored_families": list(controller.ledger.explored_families()),
                    "fetched_case_refs": list(fetched),
                    "need_dispositions": len(result.need_dispositions),
                    "modality_coverage": dict(result.modality_coverage),
                    "narrative_reads": result.narrative_reads,
                    "candidate_count": len(result.candidates),
                    "narrative_candidate_count": sum(
                        1
                        for candidate in result.candidates
                        if self._is_narrative_candidate(candidate)
                    ),
                    "structured_candidate_count": sum(
                        1
                        for candidate in result.candidates
                        if self._candidate_modality(candidate) == "structured"
                    ),
                    "mixed_candidate_count": sum(
                        1
                        for candidate in result.candidates
                        if self._candidate_modality(candidate) == "mixed"
                    ),
                }
            )

        candidate_refs: list[str] = []
        narrative_candidate_refs: list[str] = []
        structured_candidate_refs: list[str] = []
        induction_case_ids: dict[str, tuple[str, ...]] = {}
        validation_case_ids: dict[str, tuple[str, ...]] = {}
        validation_by_class: dict[str, list[str]] = {
            "positive": [],
            "control": [],
        }
        for case in check_cases:
            validation_by_class[str(labels_by_case_id[case.case_id])].append(
                case.case_id
            )
        narrative_materialized = 0
        narrative_validated = 0
        structured_materialized = 0
        structured_validated = 0
        for candidate_seed, candidate in candidates:
            capability_gap = self._candidate_capability_gap(
                candidate,
                axis_id=axis_id,
                seed=candidate_seed,
            )
            if capability_gap is not None:
                gap_ref, gap = capability_gap
                capability_gaps[gap_ref] = gap
                continue
            evidence = {}
            for seed_cited in cited.values():
                evidence.update(
                    {
                        ref: item
                        for ref, item in seed_cited.items()
                        if ref in set(candidate.get("evidence_refs", ()))
                    }
                )
            staged = self._materialize_controller_candidate(
                candidate,
                caller=caller,
                failures=failures,
                evidence=evidence,
                seed=candidate_seed,
            )
            if staged is None:
                continue
            signal_ref, staged_seed = staged
            candidate_refs.append(signal_ref)
            is_narrative = self._is_narrative_candidate(candidate)
            if is_narrative:
                narrative_materialized += 1
                narrative_candidate_refs.append(signal_ref)
            else:
                structured_materialized += 1
                structured_candidate_refs.append(signal_ref)
            induction_case_ids[signal_ref] = (
                tuple(
                    controller_case.case_id
                    for ref in fetched_case_refs.get(staged_seed, ())
                    for controller_case in (dict(case_pairs).get(ref),)
                    if controller_case is not None
                )
                or tuple(case.case_id for case in dev_cases)
            )
            validation_case_ids[signal_ref] = tuple(
                [
                    *validation_by_class["positive"][
                        : self.mining_config.validation_cases_per_class
                    ],
                    *validation_by_class["control"][
                        : self.mining_config.validation_cases_per_class
                    ],
                ]
            )
            if is_narrative:
                narrative_validated += 1
            else:
                structured_validated += 1
        modality_metrics = {
            "eligible_structured_seed_count": sum(
                1
                for report in seed_reports
                if isinstance(report, Mapping)
                and report.get("status") == "completed"
                and dict(report.get("modality_coverage", {}))
                .get("structured", {})
                .get("available")
            ),
            "structured_exploration_completed": sum(
                1
                for report in seed_reports
                if isinstance(report, Mapping)
                and report.get("status") == "completed"
                and dict(report.get("modality_coverage", {}))
                .get("structured", {})
                .get("explored")
            ),
            "structured_candidate_count": sum(
                int(report.get("structured_candidate_count", 0) or 0)
                for report in seed_reports
                if isinstance(report, Mapping)
            ),
            "structured_materialization_count": structured_materialized,
            "structured_validation_count": structured_validated,
            "eligible_narrative_seed_count": sum(
                1
                for report in seed_reports
                if isinstance(report, Mapping)
                and report.get("status") == "completed"
                and dict(report.get("modality_coverage", {}))
                .get("narrative", {})
                .get("available")
            ),
            "narrative_exploration_completed": sum(
                1
                for report in seed_reports
                if isinstance(report, Mapping)
                and self._seed_satisfied_narrative_obligation(report)
            ),
            "narrative_unavailable_count": sum(
                1
                for report in seed_reports
                if isinstance(report, Mapping)
                and report.get("status") == "completed"
                and not dict(report.get("modality_coverage", {}))
                .get("narrative", {})
                .get("available")
            ),
            "narrative_read_count": sum(
                int(report.get("narrative_reads", 0) or 0)
                for report in seed_reports
                if isinstance(report, Mapping)
            ),
            "narrative_candidate_count": sum(
                int(report.get("narrative_candidate_count", 0) or 0)
                for report in seed_reports
                if isinstance(report, Mapping)
            ),
            "narrative_materialization_count": narrative_materialized,
            "narrative_validation_count": narrative_validated,
        }
        audit = {
            "schema_version": "signal-mining-audit-v1",
            "cycle_id": cycle_id,
            "track": "controller",
            "axis_id": axis_id,
            "research_axis": dict(research_axis),
            "status": "completed",
            "limits": self.mining_config.to_dict(),
            "seeds": seed_reports,
            "modality_metrics": modality_metrics,
            "need_disposition_counts": need_disposition_counts,
            "candidate_refs": list(candidate_refs),
            "narrative_candidate_refs": list(narrative_candidate_refs),
            "structured_candidate_refs": list(structured_candidate_refs),
            "capability_gaps": capability_gaps,
            "refined_hypotheses": {},
        }
        return self._mining_output(
            audit=audit,
            refined={},
            candidate_refs=candidate_refs,
            induction_case_ids=induction_case_ids,
            validation_case_ids=validation_case_ids,
            failures=failures,
            capability_gaps=capability_gaps,
            candidate_research_targets={
                signal_ref: axis_id for signal_ref in candidate_refs
            },
        )

    @staticmethod
    def _evidence_document_source_type(document_ref: str) -> str:
        """Recover the source type from an evidence document ref.

        Controller evidence refs are ``document-<provider>:<company>:<type>:<hash>``;
        the embedded type is the retrieval family the measurement was actually
        grounded in.
        """

        document_id = document_ref[len("document-"):] if document_ref.startswith(
            "document-"
        ) else document_ref
        parts = document_id.split(":")
        return parts[2] if len(parts) >= 4 else ""

    @staticmethod
    def _controller_signal_id_slug(candidate: Mapping[str, Any], spec: Any) -> str:
        """Normalize a materialized signal_id into the registry's safe form.

        Model-authored ids routinely carry casing, spaces, or formula
        punctuation; the runtime owns identifier safety, so the id is
        deterministically slugged (falling back to the candidate observable)
        instead of losing a grounded candidate to a naming technicality.
        """

        raw = ""
        if isinstance(spec, Mapping):
            raw = str(spec.get("signal_id") or "")
        if not raw.strip():
            measurement = candidate.get("measurement")
            if isinstance(measurement, Mapping):
                raw = str(measurement.get("observable") or "")
        slug = re.sub(r"[^a-z0-9]+", "_", raw.casefold())
        slug = re.sub(r"_+", "_", slug).strip("_")[:64].strip("_")
        return slug or "controller_mined_signal"

    @staticmethod
    def _candidate_modality(candidate: Mapping[str, Any]) -> str:
        """Classify one controller candidate before materialization.

        A numeric value whose predicate is narrative and whose evidence mixes
        structured facts with narrative events/documents is deliberately
        neither executable type: it requires a split contract.
        """

        measurement = candidate.get("measurement")
        if not isinstance(measurement, Mapping):
            return "structured"
        predicate = measurement.get("predicate")
        narrative_predicate = isinstance(predicate, Mapping) and (
            str(predicate.get("modality", "narrative")) == "narrative"
        )
        if not narrative_predicate:
            return "structured"
        evidence_refs = {
            str(ref) for ref in candidate.get("evidence_refs", ())
        }
        cites_structured = any(ref.startswith("fact-") for ref in evidence_refs)
        cites_narrative = any(
            ref.startswith(("event-", "document-")) for ref in evidence_refs
        )
        if (
            str(measurement.get("value_kind", "")).casefold() == "numeric"
            and cites_structured
            and cites_narrative
        ):
            return "mixed"
        return "narrative"

    @staticmethod
    def _is_narrative_candidate(candidate: Mapping[str, Any]) -> bool:
        """Return whether a candidate is a pure narrative executable."""

        return SignalEvolutionEngine._candidate_modality(candidate) == "narrative"

    @staticmethod
    def _candidate_capability_gap(
        candidate: Mapping[str, Any],
        *,
        axis_id: str,
        seed: str,
    ) -> tuple[str, dict[str, Any]] | None:
        """Return the pre-materialization disposition for a mixed candidate."""

        if SignalEvolutionEngine._candidate_modality(candidate) != "mixed":
            return None
        measurement = candidate.get("measurement", {})
        observable = (
            str(measurement.get("observable", "mixed_candidate"))
            if isinstance(measurement, Mapping)
            else "mixed_candidate"
        )
        slug = re.sub(r"[^a-z0-9]+", "_", observable.casefold())
        slug = re.sub(r"_+", "_", slug).strip("_") or "mixed_candidate"
        return (
            f"slow_loop:mining_capability_gap:{axis_id}:{slug}",
            {
                "status": "split_required",
                "reason": (
                    "numeric measurement mixes structured fact refs with a "
                    "narrative predicate and must be split into separately "
                    "executable structured and narrative candidates before "
                    "materialization"
                ),
                "axis_id": axis_id,
                "seed": seed,
                "observable": observable,
            },
        )

    @staticmethod
    def _seed_satisfied_narrative_obligation(report: Mapping[str, Any]) -> bool:
        """Whether one eligible seed met the narrative exploration duty.

        Exploration satisfies the obligation directly; control-plane
        terminals (deferred_budget, evidence_unavailable, correction
        exhaustion) are exempt by spec. The metric counts only seeds
        whose narrative evidence was actually available.
        """

        narrative = dict(report.get("modality_coverage", {})).get(
            "narrative", {}
        )
        if not isinstance(narrative, Mapping) or not narrative.get(
            "available"
        ):
            return False
        if narrative.get("explored"):
            return True
        return str(report.get("terminal_kind", "")) in {
            "deferred_budget",
            "evidence_unavailable",
            "technical_failure",
        }

    @staticmethod
    def _controller_evidence_excerpts(
        candidate: Mapping[str, Any],
        evidence: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Render the candidate's cited controller evidence for materialization.

        The spans, concepts, periods, and source families of the cited facts
        and events are exactly what a faithful spec, retrieval contract, and
        verbatim fixtures must be built from, so the model authors them
        against real evidence instead of inventing a contradictory retrieval
        contract.
        """

        wanted = {str(ref) for ref in candidate.get("evidence_refs", ())}
        excerpts: list[dict[str, Any]] = []
        measurement = candidate.get("measurement")
        predicate = (
            measurement.get("predicate")
            if isinstance(measurement, Mapping)
            else None
        )
        if isinstance(predicate, Mapping):
            excerpts.append(
                {"predicate": dict(predicate), "kind": "narrative_predicate"}
            )
        for ref, item in evidence.items():
            if str(ref) not in wanted or len(excerpts) >= 12:
                continue
            row = {"ref": str(ref)}
            for key in (
                "concept",
                "unit",
                "value",
                "exact_span",
                "excerpt",
                "title",
                "source_family",
                "published_at",
                "available_at",
            ):
                value = getattr(item, key, None)
                if value is not None and str(value).strip():
                    row[key] = str(value)[:600]
            document_source_type = (
                SignalEvolutionEngine._evidence_document_source_type(
                    str(getattr(item, "document_ref", ""))
                )
            )
            if document_source_type:
                # Structured-fact rows carry no source_family attribute, so
                # the retrieval vocabulary is derived from the cited
                # document itself; the model can then align
                # raw_retrieval.source_types on the first attempt.
                row.setdefault("document_source_type", document_source_type)
            period = getattr(item, "period", None)
            if isinstance(period, Mapping):
                row["period"] = dict(period)
            if "exact_span" not in row and "excerpt" not in row:
                continue
            excerpts.append(row)
        return excerpts

    def _masked_controller_evidence_excerpts(
        self,
        candidate: Mapping[str, Any],
        evidence: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Identity-mask the evidence rows handed to the materializing model.

        Verbatim spans are replay evidence for the controller ledger, but the
        materializing model must never receive — and copy into fixtures — a
        discovery-cohort identity embedded in raw narrative or filing text.
        Rows are masked with the slow-role guards plus the validator's
        forbidden terms and stripped of document artifacts, the same
        discipline every other model-facing view already applies.
        """

        excerpts = self._controller_evidence_excerpts(candidate, evidence)
        aliases = tuple(self.slow_role_identity_guards) + tuple(
            self.validator.forbidden_identity_terms
        )

        def strip_artifacts(value: Any) -> Any:
            if isinstance(value, str):
                return strip_document_artifacts(value)
            if isinstance(value, list):
                return [strip_artifacts(item) for item in value]
            if isinstance(value, Mapping):
                return {key: strip_artifacts(item) for key, item in value.items()}
            return value

        masked = _mask_identity_values(
            excerpts, aliases, expand_aliases=False
        )
        return strip_artifacts(masked)

    def _materialize_controller_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        caller: Any,
        failures: dict[str, tuple[str, ...]],
        evidence: Mapping[str, Any],
        seed: str,
    ) -> tuple[str, str] | None:
        """Convert one controller candidate into a staged executable Signal.

        The controller grounds the measurement; one bounded model call renders
        it into the same staging payload ({spec, skill, tests}) the legacy
        mining path uses, after which the unchanged contract validator and
        paired gates judge it. A narrative predicate candidate must materialize
        as an LLM skill, so every fixture is itself an LLM judgment; its
        correction loop gets the wider bound because expected-value and
        executor-taxonomy disagreements converge over more rounds than
        deterministic-function fixtures.
        """

        corrections = 0
        max_corrections = 4 if self._is_narrative_candidate(candidate) else 2
        failure_key = "slow_loop:mining_materialize:" + (
            self._controller_signal_id_slug(candidate, {})
        )
        last_issues: list[str] = []
        while True:
            parsed, issues = self._materialize_once(
                candidate,
                caller=caller,
                evidence=evidence,
                last_issues=last_issues,
                seed=seed,
            )
            if parsed is not None and not issues:
                return parsed
            last_issues = issues or ["materialization call failed"]
            corrections += 1
            if corrections > max_corrections:
                failures[failure_key] = tuple(last_issues)
                return None

    def _materialize_once(
        self,
        candidate: Mapping[str, Any],
        *,
        caller: Any,
        evidence: Mapping[str, Any],
        last_issues: Sequence[str],
        seed: str,
    ) -> tuple[tuple[str, str] | None, list[str]]:
        """One materialization attempt: model call, validate, stage."""

        try:
            parsed, _usage = caller.complete_json(
                stage="mining_candidate_materialize",
                system_prompt=(
                    "Return exactly one JSON object. Convert the grounded "
                    "mining-controller candidate into a storable Signal "
                    "candidate following the supplied candidate contract: a "
                    "new signal_id in lowercase snake_case ([a-z0-9_] only; "
                    "the runtime normalizes it), a definition faithful to the "
                    "measurement, point-in-time fixtures whose documents "
                    "embed the supplied identity-masked evidence spans "
                    "verbatim, and preserve the controller modality. A "
                    "structured measurement must use a registered deterministic "
                    "function that exactly matches it; if none matches, report "
                    "the capability gap instead of recasting it as LLM. A "
                    "narrative predicate must use a source-grounded LLM skill. For a "
                    "narrative predicate candidate, author an LLM skill that "
                    "judges the semantic condition over the narrative family "
                    "inside the lookback window, cites verbatim supporting "
                    "and counter spans, and returns unavailable when "
                    "evidence is insufficient; fixtures must cover confirmed "
                    "events, mere proposals or memoranda, cancellations, "
                    "below-threshold amounts, paraphrases, lookalikes, "
                    "post-cutoff documents, and evidence-insufficient "
                    "cases. The skill's classification rules must name each "
                    "fixture class and assign it the same expected value the "
                    "fixture asserts: confirmed qualifying events are "
                    "positive; explicit cancellations or denials of a "
                    "qualifying event are negative; adequate documents that "
                    "contain only proposals, memoranda, non-binding intent, "
                    "lookalikes, or below-threshold mentions are neutral, "
                    "not unavailable; unavailable is reserved for empty or "
                    "post-cutoff-only corpora and genuinely insufficient "
                    "text. Output exactly {spec, skill, tests}."
                ),
                payload={
                    "candidate": dict(candidate),
                    "candidate_contract": self._mining_candidate_contract(),
                    "cited_evidence": self._masked_controller_evidence_excerpts(
                        candidate, evidence
                    ),
                    "retrieval_guidance": {
                        "rule": (
                            "raw_retrieval.source_types must cover the "
                            "source types of the cited evidence (a family "
                            "name like news, filing, or transcript is "
                            "interchangeable with its concrete types like "
                            "company_news, sec_filing, earnings_call), and "
                            "coverage minima must not exceed what the cited "
                            "evidence itself demonstrates"
                        ),
                    },
                    "last_issues": list(last_issues),
                },
                allow_outcomes=True,
                max_output_tokens=ROLE_OUTPUT_TOKEN_LIMITS["proposer"],
                temperature=0.2,
            )
        except (EvolutionControlFlow, OpenAIClientError):
            raise
        except Exception as exc:
            return None, [
                f"materialization call failed: {type(exc).__name__}: {exc}"
            ]
        if not isinstance(parsed, Mapping) or set(parsed) != {
            "spec",
            "skill",
            "tests",
        }:
            return None, ["materialization requires exactly spec, skill, and tests"]
        if not isinstance(parsed["spec"], Mapping):
            return None, ["materialized spec must be an object"]
        if not isinstance(parsed["tests"], list) or not parsed["tests"]:
            return None, ["materialized tests must be a non-empty array"]
        spec_dict = dict(parsed["spec"])
        spec_dict["signal_id"] = self._controller_signal_id_slug(
            candidate, spec_dict
        )
        skill = (
            str(parsed["skill"]) if parsed["skill"] is not None else None
        )
        try:
            spec = candidate_signal_spec_from_dict(spec_dict)
        except (EvolutionControlFlow, OpenAIClientError):
            raise
        except Exception as exc:
            return None, [f"spec parse failed: {type(exc).__name__}: {exc}"]
        expected_modality = (
            SignalModality.NARRATIVE
            if self._is_narrative_candidate(candidate)
            else SignalModality.STRUCTURED
        )
        if spec.modality is not expected_modality:
            return None, [
                "materialized Signal modality does not preserve the controller "
                f"candidate modality: expected {expected_modality.value}"
            ]
        retrieval_families = {
            str(item)
            for item in dict(spec_dict.get("raw_retrieval", {}) or {}).get(
                "source_types", ()
            )
        }
        evidence_families = {
            family
            for family in (
                self._evidence_document_source_type(
                    str(getattr(item, "document_ref", ""))
                )
                for item in evidence.values()
            )
            if family
        }
        if retrieval_families and evidence_families and not (
            source_types_compatible(retrieval_families, evidence_families)
        ):
            return None, [
                "raw_retrieval.source_types do not include any cited-evidence "
                "source family; retrieve from the source types or families "
                "the measurement actually cites (cited evidence source "
                f"types: {sorted(evidence_families)}; equivalent families "
                "such as news/company_news, filing/10-k/8-k, or "
                "transcript/earnings_call are interchangeable)"
            ]
        checked = self.validator.validate(
            spec, skill=skill, tests=parsed["tests"]
        )
        if not checked.accepted:
            return None, [
                f"contract validation rejected the materialized candidate: "
                + "; ".join(str(reason) for reason in checked.reasons)
            ]
        try:
            signal_ref = self._stage_from_tool(
                spec=spec.to_dict(),
                skill=skill,
                tests=parsed["tests"],
                origin="mining:controller",
                collected=[],
            )
        except (EvolutionControlFlow, OpenAIClientError):
            raise
        except Exception as exc:
            return None, [f"staging failed: {type(exc).__name__}: {exc}"]
        return (signal_ref, seed), []

    def _run_signal_mining_legacy(self, *, cycle_id: int) -> dict[str, Any]:
        """Preserve read-only v7 cadence outside an active v8 frozen input."""

        if cycle_id % self.mining_config.exploration_interval == 0:
            return self._run_exploration_mining(cycle_id=cycle_id)
        fallback_supported = bool(
            getattr(self.mining_model, "supports_exploration_fallback", False)
        )
        try:
            hypothesis = self._run_hypothesis_mining(cycle_id=cycle_id)
        except CandidateExecutionRejected as exc:
            if not fallback_supported:
                raise
            hypothesis = self._mining_output(
                audit={
                    "schema_version": "signal-mining-audit-v1",
                    "status": "failed",
                    "cycle_id": cycle_id,
                    "track": "hypothesis",
                    "limits": self.mining_config.to_dict(),
                    "stages": {},
                    "failure_stage": exc.stage,
                    "error": str(exc),
                    "failure_details": dict(exc.details),
                    "usage": _usage_to_dict(exc.usage),
                    "candidate_refs": [],
                    "refined_hypotheses": {},
                },
                refined={},
            )
        if (
            hypothesis["candidate_refs"]
            or not fallback_supported
            or not _mining_needs_exploration_fallback(hypothesis["audit"])
        ):
            return hypothesis
        exploration = self._run_exploration_mining(cycle_id=cycle_id)
        return _merge_mining_fallback(hypothesis, exploration)

    def _run_hypothesis_mining(self, *, cycle_id: int) -> dict[str, Any]:
        config = self.mining_config
        scanned_pairs = self._mining_case_universe(
            limit=config.h2_profile_scan_limit
        )
        self._preflight_h2_profiles(scanned_pairs)
        refined: dict[str, tuple[str, ...]] = {}
        audit: dict[str, Any] = {
            "schema_version": "signal-mining-audit-v1",
            "status": "completed",
            "cycle_id": cycle_id,
            "track": "hypothesis",
            "limits": config.to_dict(),
            "stages": {},
        }
        ready_rows: list[tuple[str, EvolutionCase, dict[str, Any]]] = []
        profile_audit: list[dict[str, Any]] = []
        positive_ready_count = 0
        control_ready_count = 0
        for case_ref, case in scanned_pairs:
            brief = self._mining_case_brief(case_ref, case)
            profile_audit.append(
                {
                    "case_ref": case_ref,
                    "ready": bool(brief.pop("_profile_ready", False)),
                    "profile_resolution": brief.pop("_profile_resolution", None),
                }
            )
            if profile_audit[-1]["ready"]:
                ready_rows.append((case_ref, case, brief))
                if case.ground_truth.is_surge:
                    positive_ready_count += 1
                else:
                    control_ready_count += 1
                if (
                    len(ready_rows) >= config.case_pool_limit
                    and positive_ready_count >= config.h2_min_ready_per_class
                    and control_ready_count >= config.h2_min_ready_per_class
                ):
                    break
        positives = [item for item in ready_rows if item[1].ground_truth.is_surge]
        controls = [item for item in ready_rows if not item[1].ground_truth.is_surge]
        if (
            len(ready_rows) < config.h2_min_ready_issuers
            or len(positives) < config.h2_min_ready_per_class
            or len(controls) < config.h2_min_ready_per_class
        ):
            reason = "insufficient_h2_profile_readiness"
            audit["status"] = reason
            audit["h2_profile_readiness"] = {
                "scanned": len(profile_audit),
                "ready": len(ready_rows),
                "positive_ready": len(positives),
                "control_ready": len(controls),
                "minimum_ready": config.h2_min_ready_issuers,
                "minimum_per_class": config.h2_min_ready_per_class,
                "cases": profile_audit,
            }
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
            return self._mining_output(audit=audit, refined=refined)
        mandatory_refs = {
            item[0]
            for item in (
                *positives[: config.h2_min_ready_per_class],
                *controls[: config.h2_min_ready_per_class],
            )
        }
        selected_ready = [item for item in ready_rows if item[0] in mandatory_refs]
        selected_ready.extend(
            item
            for item in ready_rows
            if item[0] not in mandatory_refs
        )
        selected_ready = selected_ready[: config.case_pool_limit]
        case_pairs = tuple((ref, case) for ref, case, _brief in selected_ready)
        briefs_by_ref = {ref: brief for ref, _case, brief in selected_ready}
        context = self._mining_context(cycle_id=cycle_id)
        measurable_evidence_manifest = _mask_identity_values(
            self._h1_measurable_evidence_manifest(case_pairs),
            self.slow_role_identity_guards,
            expand_aliases=False,
        )
        prior_terminal_work = self._prior_terminal_hypothesis_work()
        hypothesis_work: list[dict[str, Any]] = []
        applicability_contract = self._h2_applicability_contract(
            briefs_by_ref.values()
        )
        h1_payload = {
            "track": "hypothesis",
            "h1_contract_version": "signal-mining-hypothesis-v7",
            "hypothesis_slots": [
                f"h1-c{cycle_id:04d}-s{index:02d}"
                for index in range(1, config.hypothesis_limit + 1)
            ],
            "fixed_comparison": "fixed_discovery_positive_vs_control",
            "limits": config.to_dict(),
            "h2_applicability_contract": applicability_contract,
            "measurable_evidence_manifest": measurable_evidence_manifest,
            **context,
        }
        h1_input_fingerprint = _canonical_hash(
            {
                "schema_version": "signal-mining-h1-input-v7",
                "contract": h1_payload["h1_contract_version"],
                "limits": h1_payload["limits"],
                "h2_applicability_contract": applicability_contract,
                "capability_backlog": context["capability_backlog"],
                "meta_info": context["meta_info"],
                "meta_source_catalog": context["meta_source_catalog"],
                "meta_memory_disclosures": context["meta_memory_disclosures"],
                "research_objective": context["research_objective"],
                "fixed_prior": context["fixed_prior"],
                "reflection_action_audit": context["reflection_action_audit"],
                "stable_signal_cards": context["stable_signal_cards"],
                **(
                    {
                        "prior_slow_work": context["prior_slow_work"],
                        "slow_method_memory": context["slow_method_memory"],
                    }
                    if self._active_sampling_manifest is not None
                    else {}
                ),
                "available_raw_source_types": context[
                    "available_raw_source_types"
                ],
                "measurable_evidence_manifest": measurable_evidence_manifest,
                "registered_deterministic_functions": context[
                    "registered_deterministic_functions"
                ],
                "relevant_raw_info": self._relevant_search_documents(),
                "mining_model": self._role_work_identity(self.mining_model),
            }
        )
        source_manifests = (
            dict(context["meta_memory_read_manifest"]),
            dict(context["slow_method_memory"].get("source_view_manifest", {})),
        )
        source_usage = AgentUsage()
        for source_manifest in source_manifests:
            source_usage = source_usage + _usage_from_dict(dict(source_manifest.get("source_read_usage", {})))
        source_request_refs = _ordered_unique(
            ref for source_manifest in source_manifests
            for ref in source_manifest.get("source_read_request_refs", ())
        )
        prior_h1 = next(
            (
                item
                for item in reversed(context["prior_slow_work"])
                if item.get("h1_input_fingerprint") == h1_input_fingerprint
                and dict(item.get("h1_conclusion", {})).get("conclusion")
                == "no_testable_hypothesis"
            ),
            None,
        )
        if prior_h1 is not None:
            prior_conclusion = dict(prior_h1["h1_conclusion"])
            audit["status"] = "unchanged_h1_work_suppressed"
            audit["stages"]["H1"] = {
                "contract_version": "signal-mining-hypothesis-v7",
                "input_fingerprint": h1_input_fingerprint,
                "conclusion": prior_conclusion,
                "hypotheses": [],
                "reused_from_prior_cycle": True,
                "usage": _usage_to_dict(source_usage),
                "request_refs": list(source_request_refs),
            }
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {}
            audit["hypothesis_work"] = []
            return self._mining_output(audit=audit, refined={})
        try:
            hypotheses_step = self.mining_model.propose_hypotheses(h1_payload)
        except RuntimeBudgetExceeded as exc:
            exc.usage = exc.usage + source_usage
            raise
        except CandidateExecutionRejected as exc:
            raise CandidateExecutionRejected(
                exc.stage,
                str(exc),
                exc.usage + source_usage,
                details={
                    **dict(exc.details),
                    "request_refs": list(_ordered_unique((*source_request_refs, *exc.details.get("request_refs", ())))),
                    "contract_version": "signal-mining-hypothesis-v7",
                    "input_fingerprint": h1_input_fingerprint,
                    "conclusion": {
                        "conclusion": "technical_failure",
                        "reason_code": "structured_recovery_exhausted",
                    },
                },
            ) from exc
        if len(hypotheses_step.value) > config.hypothesis_limit:
            raise ValidationError(
                "Signal Mining hypothesis portfolio exceeds the configured limit"
            )
        hypotheses: list[SignalMiningHypothesis] = []
        available_sources = set(self.evidence_resolver.available_source_types)
        seen_ids: set[str] = set()
        for hypothesis in hypotheses_step.value:
            if hypothesis.hypothesis_id in seen_ids:
                raise ValidationError("Signal Mining hypothesis ids must be unique")
            seen_ids.add(hypothesis.hypothesis_id)
            unsupported = sorted(set(hypothesis.source_types) - available_sources)
            if unsupported:
                refined[hypothesis.hypothesis_id] = (
                    "required source types are unavailable: " + ", ".join(unsupported),
                )
                continue
            hypotheses.append(hypothesis)
        audit["stages"]["H1"] = {
            "contract_version": "signal-mining-hypothesis-v7",
            "input_fingerprint": h1_input_fingerprint,
            "conclusion": dict(hypotheses_step.metadata),
            "hypotheses": [item.to_dict() for item in hypotheses_step.value],
            "usage": _usage_to_dict(hypotheses_step.usage + source_usage),
            "request_refs": list(_ordered_unique((
                *source_request_refs, *hypotheses_step.metadata.get("request_refs", ()),
            ))),
        }
        if not hypotheses:
            if hypotheses_step.metadata.get("conclusion") == "no_testable_hypothesis":
                audit["status"] = "no_testable_hypothesis"
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
            audit["hypothesis_work"] = []
            return self._mining_output(audit=audit, refined=refined)
        case_by_ref = dict(case_pairs)
        check_pairs = tuple(
            (f"check-{index:03d}", case)
            for index, case in enumerate(
                self._manifest_cases("check_case_ids"), start=1
            )
        )
        case_by_ref.update(check_pairs)
        check_refs = tuple(ref for ref, _case in check_pairs)
        ranking_limit = min(config.ranking_case_limit, len(case_pairs))
        rankings = {
            hypothesis.hypothesis_id: tuple(
                case_ref
                for case_ref, _case in case_pairs
                if self._h2_applicability_matches(
                    hypothesis.applicability,
                    briefs_by_ref[case_ref],
                )
            )[:ranking_limit]
            for hypothesis in hypotheses
        }
        audit["stages"]["H2"] = {
            "mode": "deterministic_canonical_applicability",
            "rankings": {key: list(value) for key, value in rankings.items()},
            "case_briefs": [
                briefs_by_ref[case_ref] for case_ref, _case in case_pairs
            ],
            "profile_readiness": {
                "scanned": len(profile_audit),
                "ready": len(ready_rows),
                "selected": len(case_pairs),
                "cases": profile_audit,
            },
            "usage": _usage_to_dict(AgentUsage()),
        }

        selections: list[dict[str, Any]] = []
        for hypothesis in hypotheses:
            selected = self._select_mining_cases(
                rankings[hypothesis.hypothesis_id],
                case_by_ref=case_by_ref,
                validation_ranked_refs=check_refs,
            )
            if selected is None:
                refined[hypothesis.hypothesis_id] = (
                    "label-hidden ranking did not contain both positive and control cases",
                )
                continue
            selections.append(
                {
                    "hypothesis": hypothesis,
                    **selected,
                }
            )
        if not selections:
            audit["local_selection"] = []
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
            audit["hypothesis_work"] = []
            return self._mining_output(audit=audit, refined=refined)

        contrast_packets: list[dict[str, Any]] = []
        evidence_packets_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        resolution_audit: list[dict[str, Any]] = []
        evidence_unavailable: dict[str, tuple[str, ...]] = {}
        evaluable_selections: list[dict[str, Any]] = []
        for selection in selections:
            hypothesis = selection["hypothesis"]
            if len(evaluable_selections) >= config.selected_hypothesis_limit:
                refined[hypothesis.hypothesis_id] = (
                    "deferred because the per-cycle evidence contrast budget was reached",
                )
                continue
            usable_by_class: dict[bool, list[str]] = {True: [], False: []}
            attempted_case_refs: list[str] = []
            attempted_packet_refs: list[str] = []
            packet_ref_by_case: dict[str, str] = {}
            target_groups = (
                self.research_target_reveal.get("groups")
                if isinstance(self.research_target_reveal, Mapping)
                else None
            )
            evidence_case_refs = (
                selection["induction_refs"]
                if self._active_sampling_manifest is not None
                else rankings[hypothesis.hypothesis_id]
            )
            if target_groups is not None:
                # Direction-sampled induction refs can miss a target class
                # entirely. In target mode the induction source becomes a
                # class-balanced prefix of the research population (at most
                # induction_cases_per_class per group), so attempted-case
                # bookkeeping and the issuer-disjoint validation pool keep
                # their direction-mode semantics.
                per_class_limit = config.induction_cases_per_class
                target_sampling = (
                    self.research_target_sampling.get("sampling")
                    if isinstance(self.research_target_sampling, Mapping)
                    else None
                )
                ref_by_case_id = {
                    case.case_id: ref for ref, case in case_by_ref.items()
                }
                dev_case_ids = (
                    target_sampling.get("dev_case_ids", ())
                    if isinstance(target_sampling, Mapping)
                    else ()
                )
                dev_refs = [
                    ref_by_case_id[str(case_id)]
                    for case_id in dev_case_ids
                    if str(case_id) in ref_by_case_id
                ]
                balanced: list[str] = []
                for wanted_group in ("ge3_high", "ge3_low"):
                    taken = 0
                    for source in (dev_refs, list(case_by_ref)):
                        for ref in source:
                            case = case_by_ref[ref]
                            if (
                                target_groups.get(str(case.case_id))
                                == wanted_group
                                and taken < per_class_limit
                                and ref not in balanced
                            ):
                                balanced.append(ref)
                                taken += 1
                        if taken >= per_class_limit:
                            break
                evidence_case_refs = balanced or list(evidence_case_refs)
            comparator_by_class: dict[bool, list[str]] = {True: [], False: []}
            for case_ref in evidence_case_refs:
                case = case_by_ref[case_ref]
                if target_groups is not None:
                    target_group = target_groups.get(str(case.case_id))
                    if target_group is None:
                        continue
                    case_class = target_group == "ge3_high"
                else:
                    case_class = bool(case.ground_truth.is_surge)
                if (
                    len(usable_by_class[case_class])
                    >= config.induction_cases_per_class
                ):
                    continue
                packet_key = (
                    case_ref,
                    tuple(hypothesis.source_types),
                    hypothesis.query,
                    hypothesis.lookback_days,
                )
                if packet_key not in evidence_packets_by_key:
                    packet, resolution = self._mining_evidence_packet(
                        case_ref,
                        case,
                        source_types=hypothesis.source_types,
                        query=hypothesis.query,
                        lookback_days=hypothesis.lookback_days,
                        reveal_label=True,
                        label_override=(
                            ("positive" if case_class else "control")
                            if target_groups is not None
                            else None
                        ),
                    )
                    packet_ref = "packet_" + hashlib.sha256(
                        json.dumps(packet_key, sort_keys=True).encode("utf-8")
                    ).hexdigest()[:20]
                    evidence_packets_by_key[packet_key] = {
                        "packet_ref": packet_ref,
                        **packet,
                    }
                    resolution_audit.append({"packet_ref": packet_ref, **resolution})
                stored_packet = evidence_packets_by_key[packet_key]
                attempted_case_refs.append(case_ref)
                attempted_packet_refs.append(stored_packet["packet_ref"])
                if stored_packet["evidence"]:
                    packet_ref_by_case[case_ref] = stored_packet["packet_ref"]
                    if self._active_sampling_manifest is not None:
                        usable_by_class[case_class].append(case_ref)
                    else:
                        target = (
                            usable_by_class
                            if stored_packet.get("query_match_status") == "matched"
                            else comparator_by_class
                        )
                        target[case_class].append(case_ref)
                if self._active_sampling_manifest is None and all(
                    len(refs) >= config.induction_cases_per_class
                    for refs in usable_by_class.values()
                ):
                    break
            if self._active_sampling_manifest is None:
                for case_class in (True, False):
                    needed = (
                        config.induction_cases_per_class
                        - len(usable_by_class[case_class])
                    )
                    usable_by_class[case_class].extend(
                        comparator_by_class[case_class][:needed]
                    )
            if not all(
                len(refs) >= config.induction_cases_per_class
                for refs in usable_by_class.values()
            ):
                reasons = (
                    "fewer than the configured issuer-distinct cases had usable "
                    "hypothesis-relevant point-in-time evidence; attempted refs: "
                    + ", ".join(attempted_case_refs),
                )
                attempted_ref_set = set(attempted_packet_refs)
                work_fingerprint = self._hypothesis_work_fingerprint(
                    hypothesis,
                    packets=(
                        packet
                        for packet in evidence_packets_by_key.values()
                        if packet["packet_ref"] in attempted_ref_set
                    ),
                    validation_refs=selection["validation_refs"],
                    case_by_ref=case_by_ref,
                )
                prior_work = prior_terminal_work.get(work_fingerprint)
                if prior_work is not None:
                    reasons = (
                        "unchanged hypothesis work suppressed until evidence or "
                        "strategy changes",
                    )
                    status = "unchanged_work_suppressed"
                    refined[hypothesis.hypothesis_id] = reasons
                else:
                    status = "evidence_unavailable"
                    evidence_unavailable[hypothesis.hypothesis_id] = reasons
                hypothesis_work.append(
                    {
                        "hypothesis_id": hypothesis.hypothesis_id,
                        "work_fingerprint": work_fingerprint,
                        "status": status,
                        "reasons": list(reasons),
                    }
                )
                continue
            induction_refs = tuple(
                (*usable_by_class[True], *usable_by_class[False])
            )
            if self._active_sampling_manifest is None:
                validation_by_class: dict[bool, list[str]] = {
                    True: [],
                    False: [],
                }
                used_companies = {
                    case_by_ref[case_ref].company_id for case_ref in induction_refs
                }
                for case_ref in rankings[hypothesis.hypothesis_id]:
                    case = case_by_ref[case_ref]
                    case_class = bool(case.ground_truth.is_surge)
                    if (
                        case.company_id in used_companies
                        or len(validation_by_class[case_class])
                        >= config.validation_cases_per_class
                    ):
                        continue
                    used_companies.add(case.company_id)
                    validation_by_class[case_class].append(case_ref)
                frozen_validation_refs = tuple(
                    (*validation_by_class[True], *validation_by_class[False])
                )
            else:
                frozen_validation_refs = tuple(selection["validation_refs"])
            actual_selection = {
                **selection,
                "induction_refs": induction_refs,
                "validation_refs": frozen_validation_refs,
                "sample_basis": {
                    "positive_refs": tuple(
                        packet_ref_by_case[case_ref]
                        for case_ref in usable_by_class[True]
                    ),
                    "control_refs": tuple(
                        packet_ref_by_case[case_ref]
                        for case_ref in usable_by_class[False]
                    ),
                },
            }
            active_refs = {
                packet_ref_by_case[case_ref] for case_ref in induction_refs
            }
            work_fingerprint = self._hypothesis_work_fingerprint(
                hypothesis,
                packets=(
                    packet
                    for packet in evidence_packets_by_key.values()
                    if packet["packet_ref"] in active_refs
                ),
                validation_refs=actual_selection["validation_refs"],
                case_by_ref=case_by_ref,
            )
            prior_work = prior_terminal_work.get(work_fingerprint)
            if prior_work is not None:
                reasons = (
                    "unchanged hypothesis work suppressed until evidence or "
                    "strategy changes",
                )
                refined[hypothesis.hypothesis_id] = reasons
                hypothesis_work.append(
                    {
                        "hypothesis_id": hypothesis.hypothesis_id,
                        "work_fingerprint": work_fingerprint,
                        "status": "unchanged_work_suppressed",
                        "reasons": list(reasons),
                        "prior_status": str(prior_work.get("status", "")),
                    }
                )
                continue
            actual_selection["work_fingerprint"] = work_fingerprint
            evaluable_selections.append(actual_selection)
            contrast_packets.append(
                {
                    "hypothesis": hypothesis.to_dict(),
                    "evidence_packets": [
                        evidence_packets_by_key[
                            (
                                case_ref,
                                tuple(hypothesis.source_types),
                                hypothesis.query,
                                hypothesis.lookback_days,
                            )
                        ]
                        for case_ref in induction_refs
                    ],
                }
            )
        audit["local_selection"] = [
            {
                "hypothesis_id": item["hypothesis"].hypothesis_id,
                "induction_case_refs": list(item["induction_refs"]),
                "validation_case_refs": list(item["validation_refs"]),
            }
            for item in evaluable_selections
        ]
        audit["evidence_unavailable"] = {
            key: list(value) for key, value in evidence_unavailable.items()
        }
        if not contrast_packets:
            suppressed = any(
                item.get("status") == "unchanged_work_suppressed"
                for item in hypothesis_work
            )
            h3_status = "not_called_evidence_unavailable"
            if suppressed and not evidence_unavailable:
                h3_status = "not_called_unchanged_work"
            elif suppressed:
                h3_status = "not_called_no_evaluable_work"
            audit["stages"]["H3"] = {
                "status": h3_status,
                "decisions": [],
                "resolutions": resolution_audit,
                "usage": _usage_to_dict(AgentUsage()),
            }
            audit["candidate_refs"] = []
            audit["refined_hypotheses"] = {
                key: list(value) for key, value in refined.items()
            }
            audit["hypothesis_work"] = hypothesis_work
            return self._mining_output(audit=audit, refined=refined)
        h3_payload = {
                "track": "hypothesis",
                "fixed_prior": self.priors.mine_signal,
                "research_objective": signal_research_objective(),
                "comparisons": contrast_packets,
                "candidate_contract": self._mining_candidate_contract(),
                "slow_method_memory": self._slow_method_view("H3"),
                "rules": {
                    "decisions": [
                        "supported",
                        "refine",
                        "rejected",
                        "inconclusive",
                    ],
                    "candidate_only_when_supported": True,
                },
            }
        decisions_step = self.mining_model.contrast(h3_payload)
        allowed_hypotheses = {
            item["hypothesis"].hypothesis_id for item in evaluable_selections
        }
        decisions = self._validate_mining_decisions(
            decisions_step.value,
            allowed_hypothesis_ids=allowed_hypotheses,
        )
        selection_by_id = {
            item["hypothesis"].hypothesis_id: item
            for item in evaluable_selections
        }
        decisions = tuple(
            self._with_runtime_sample_basis(
                (decision,),
                **selection_by_id[decision.hypothesis_id]["sample_basis"],
            )[0]
            for decision in decisions
        )
        for decision in decisions:
            if decision.disposition == "inconclusive":
                evidence_unavailable[decision.hypothesis_id] = tuple(
                    "H3 judged the model-facing evidence semantically insufficient: "
                    + reason
                    for reason in decision.rationale
                )
        audit["stages"]["H3"] = {
            "status": (
                "completed_with_inconclusive"
                if any(item.disposition == "inconclusive" for item in decisions)
                else "completed"
            ),
            "decisions": [item.to_dict() for item in decisions],
            "resolutions": resolution_audit,
            "usage": _usage_to_dict(
                decisions_step.usage
                + _usage_from_dict(
                    dict(
                        dict(
                            h3_payload["slow_method_memory"].get(
                                "source_view_manifest", {}
                            )
                        ).get("source_read_usage", {})
                    )
                )
            ),
            "request_refs": list(
                _ordered_unique(
                    [
                        *dict(
                            h3_payload["slow_method_memory"].get(
                                "source_view_manifest", {}
                            )
                        ).get("source_read_request_refs", ()),
                        *decisions_step.metadata.get("request_refs", ()),
                    ]
                )
            ),
        }
        audit["evidence_unavailable"] = {
            key: list(value) for key, value in evidence_unavailable.items()
        }
        staged = self._stage_mining_decisions(
            decisions,
            selection_by_id=selection_by_id,
            case_by_ref=case_by_ref,
            refined=refined,
        )
        staging_by_id = {
            str(item.get("hypothesis_id", "")): item
            for item in staged["staging"]
            if isinstance(item, Mapping)
        }
        for decision in decisions:
            selection = selection_by_id[decision.hypothesis_id]
            status = decision.disposition
            reasons = decision.rationale
            if decision.disposition == "supported":
                staging = staging_by_id.get(decision.hypothesis_id, {})
                if staging.get("status") == "contract_accepted":
                    status = "candidate_staged"
                    reasons = ()
                else:
                    status = "candidate_rejected"
                    reasons = tuple(
                        str(reason)
                        for reason in staging.get(
                            "reasons",
                            ("candidate staging did not produce an accepted draft",),
                        )
                    )
            hypothesis_work.append(
                {
                    "hypothesis_id": decision.hypothesis_id,
                    "work_fingerprint": selection["work_fingerprint"],
                    "status": status,
                    "reasons": list(reasons),
                }
            )
        audit["candidate_refs"] = list(staged["candidate_refs"])
        audit["staging"] = list(staged["staging"])
        audit["hypothesis_work"] = hypothesis_work
        audit["refined_hypotheses"] = {
            key: list(value) for key, value in refined.items()
        }
        return self._mining_output(
            audit=audit,
            refined=refined,
            **staged,
        )

    def _run_exploration_mining(self, *, cycle_id: int) -> dict[str, Any]:
        config = self.mining_config
        dev_cases = self._manifest_cases("dev_case_ids")
        check_cases = self._manifest_cases("check_case_ids")
        cases = (
            (*dev_cases, *check_cases)
            if dev_cases and check_cases
            else _sample_binary_discovery_cases(
                self.discovery_cases,
                per_class=(
                    (2 * config.induction_cases_per_class)
                    + config.validation_cases_per_class
                ),
            )
        )
        case_pairs = _exploration_case_pairs(cases, cycle_id=cycle_id)
        case_by_ref = dict(case_pairs)
        refs_by_class = {
            case_class: tuple(
                case_ref
                for case_ref, case in case_pairs
                if bool(case.ground_truth.is_surge) == case_class
            )
            for case_class in (True, False)
        }
        minimum_per_class = (
            config.induction_cases_per_class
            + config.validation_cases_per_class
        )
        if any(
            len(refs) < minimum_per_class for refs in refs_by_class.values()
        ):
            audit = {
                "schema_version": "signal-mining-audit-v1",
                "status": "completed",
                "cycle_id": cycle_id,
                "track": "exploration",
                "limits": config.to_dict(),
                "stages": {},
                "candidate_refs": [],
                "refined_hypotheses": {
                    "exploration_sampling": [
                        "Discovery pool lacks the configured issuer-distinct "
                        "induction and validation cases in one or both groups"
                    ]
                },
            }
            return self._mining_output(
                audit=audit,
                refined={
                    "exploration_sampling": (
                        "Discovery pool lacks the configured issuer-distinct "
                        "induction and validation cases in one or both groups",
                    )
                },
            )
        dev_ids = {case.case_id for case in dev_cases}
        check_ids = {case.case_id for case in check_cases}
        e1_by_class: dict[bool, tuple[str, ...]] = {}
        for label, refs in refs_by_class.items():
            if dev_ids:
                e1_by_class[label] = tuple(
                    ref for ref in refs if case_by_ref[ref].case_id in dev_ids
                )[: 2 * config.induction_cases_per_class]
            else:
                candidate_count = min(
                    2 * config.induction_cases_per_class,
                    len(refs) - config.validation_cases_per_class,
                )
                e1_by_class[label] = refs[:candidate_count]
        validation_by_class: dict[bool, tuple[str, ...]] = {
            label: tuple(
                ref
                for ref in refs
                if (
                    case_by_ref[ref].case_id in check_ids
                    if check_ids
                    else ref not in e1_by_class[label]
                )
            )[: config.validation_cases_per_class]
            for label, refs in refs_by_class.items()
        }
        e1_ref_set = {*e1_by_class[True], *e1_by_class[False]}
        validation_ref_set = {
            *validation_by_class[True],
            *validation_by_class[False],
        }
        selected = {
            "e1_refs": tuple(
                case_ref for case_ref, _case in case_pairs if case_ref in e1_ref_set
            ),
            "validation_refs": tuple(
                case_ref
                for case_ref, _case in case_pairs
                if case_ref in validation_ref_set
            ),
        }
        available = set(self.evidence_resolver.available_source_types)
        source_types = tuple(sorted(available))
        evidence_packets: list[dict[str, Any]] = []
        resolution_audit: list[dict[str, Any]] = []
        for case_ref in selected["e1_refs"]:
            packet, resolution = self._mining_evidence_packet(
                case_ref,
                case_by_ref[case_ref],
                source_types=source_types,
                query=None,
                lookback_days=config.evidence_lookback_days,
                reveal_label=False,
            )
            evidence_packets.append(packet)
            resolution_audit.append(resolution)
        comparison_concepts = _exploration_comparison_concepts(evidence_packets)
        signatures_list: list[SignalMiningSignature] = []
        extraction_usage = AgentUsage()
        extraction_failures: dict[str, tuple[str, ...]] = {}
        microbatches: list[dict[str, Any]] = []
        for start in range(0, len(evidence_packets), config.exploration_microbatch_size):
            batch_packets = evidence_packets[
                start : start + config.exploration_microbatch_size
            ]
            batch_refs = tuple(str(item["case_ref"]) for item in batch_packets)
            try:
                extraction_step = self.mining_model.extract_exploration(
                    {
                        "track": "exploration",
                        "fixed_prior": self.priors.mine_signal,
                        "research_objective": signal_research_objective(),
                        "microbatch_ref": f"e1-batch-{start // config.exploration_microbatch_size + 1:03d}",
                        "cases": batch_packets,
                        "comparison_concepts": comparison_concepts,
                        "rules": {
                            "labels_hidden": True,
                            "identities_hidden": True,
                            "describe_only_observable_patterns": True,
                        },
                    }
                )
                extraction_usage = extraction_usage + extraction_step.usage
                batch_signatures = validate_signal_mining_signatures(
                    extraction_step.value,
                    batch_packets,
                )
                comparison_ready: list[SignalMiningSignature] = []
                for signature in batch_signatures:
                    filtered_signature, reasons = (
                        _comparison_ready_exploration_signature(signature)
                    )
                    comparison_ready.append(filtered_signature)
                    if reasons:
                        extraction_failures[signature.case_ref] = tuple(
                            "Exploration E1 observation quarantined: " + reason
                            for reason in reasons
                        )
                batch_signatures = tuple(comparison_ready)
            except CandidateExecutionRejected as exc:
                extraction_usage = extraction_usage + exc.usage
                reason = (
                    "Exploration E1 microbatch exhausted structured recovery: "
                    + str(exc),
                )
                for case_ref in batch_refs:
                    extraction_failures[case_ref] = reason
                microbatches.append(
                    {
                        "case_refs": list(batch_refs),
                        "status": "technical_failure",
                        "error": str(exc),
                        "request_refs": list(exc.details.get("request_refs", ())),
                    }
                )
                continue
            except RuntimeBudgetExceeded:
                raise
            except ValidationError as exc:
                reason = (
                    "Exploration E1 microbatch failed local result validation: "
                    + str(exc),
                )
                for case_ref in batch_refs:
                    extraction_failures[case_ref] = reason
                microbatches.append(
                    {
                        "case_refs": list(batch_refs),
                        "status": "validation_failure",
                        "error": str(exc),
                    }
                )
                continue
            signatures_list.extend(batch_signatures)
            quarantined = extraction_step.metadata.get("quarantined_observations", {})
            for case_ref, reasons in quarantined.items():
                extraction_failures[case_ref] = tuple(
                    "Exploration E1 observation quarantined: " + str(reason)
                    for reason in reasons
                )
            microbatches.append(
                {
                    "case_refs": list(batch_refs),
                    "status": "partial_technical_failure" if quarantined else "completed",
                    "quarantined_observations": quarantined,
                    "request_refs": list(
                        extraction_step.metadata.get("request_refs", ())
                    ),
                }
            )
        signatures = tuple(signatures_list)
        signature_by_ref = {item.case_ref: item for item in signatures}
        grounded_signatures = tuple(
            signature_by_ref[case_ref]
            for case_ref in selected["e1_refs"]
            if case_ref in signature_by_ref
            and signature_by_ref[case_ref].observations
        )
        grounded_by_class = {
            case_class: tuple(
                item
                for item in grounded_signatures
                if bool(case_by_ref[item.case_ref].ground_truth.is_surge)
                == case_class
            )
            for case_class in (True, False)
        }
        selected_grounded_refs = {
            item.case_ref
            for item in (
                *grounded_by_class[True][: config.induction_cases_per_class],
                *grounded_by_class[False][: config.induction_cases_per_class],
            )
        }
        selected_grounded_signatures = tuple(
            signature_by_ref[case_ref]
            for case_ref, _case in case_pairs
            if case_ref in selected_grounded_refs
        )
        if any(
            len(items) < config.induction_cases_per_class
            for items in grounded_by_class.values()
        ):
            reason = (
                "Exploration E1 produced fewer than the configured grounded "
                "signatures in one or both fixed groups"
            )
            audit = {
                "schema_version": "signal-mining-audit-v1",
                "status": "completed",
                "cycle_id": cycle_id,
                "track": "exploration",
                "limits": config.to_dict(),
                "local_selection": {
                    "e1_candidate_case_refs": list(selected["e1_refs"]),
                    "induction_case_refs": [
                        item.case_ref for item in selected_grounded_signatures
                    ],
                    "validation_case_refs": list(selected["validation_refs"]),
                    "grounded_case_refs": [
                        item.case_ref for item in grounded_signatures
                    ],
                },
                "stages": {
                    "E1": {
                        "signatures": [item.to_dict() for item in signatures],
                        "resolutions": resolution_audit,
                        "microbatches": microbatches,
                        "failures": {
                            key: list(value)
                            for key, value in extraction_failures.items()
                        },
                        "usage": _usage_to_dict(extraction_usage),
                    },
                    "E2": {
                        "status": "not_called_evidence_unavailable",
                        "decisions": [],
                        "usage": _usage_to_dict(AgentUsage()),
                    },
                },
                "candidate_refs": [],
                "refined_hypotheses": {"exploration_evidence": [reason]},
            }
            return self._mining_output(
                audit=audit,
                refined={"exploration_evidence": (reason,)},
                failures={
                    f"slow_loop:exploration_e1:{case_ref}": reasons
                    for case_ref, reasons in extraction_failures.items()
                },
            )
        packet_by_ref = {
            str(packet["case_ref"]): packet for packet in evidence_packets
        }
        revealed = [
            {
                **_literal_only_signature_view(
                    signature, packet_by_ref[signature.case_ref]
                ),
                "label": (
                    "positive"
                    if case_by_ref[signature.case_ref].ground_truth.is_surge
                    else "control"
                ),
            }
            for signature in selected_grounded_signatures
        ]
        evidence_limited = any(
            not signature.observations for signature in selected_grounded_signatures
        )
        decision_slots = [
            f"e2-c{cycle_id:04d}-s{index:02d}"
            for index in range(1, config.hypothesis_limit + 1)
        ]
        e2_payload = {
                "track": "exploration",
                "fixed_prior": self.priors.mine_signal,
                "research_objective": signal_research_objective(),
                "signatures": revealed,
                "decision_slots": decision_slots,
                "candidate_contract": self._mining_candidate_contract(),
                "slow_method_memory": self._slow_method_view("E2"),
                "stable_signal_cards": [
                    card.to_dict() for card in self.registry.list_signal_cards()
                ],
                "rules": {
                    "candidate_only_for_repeated_observable_pattern": True,
                    "exact_spans_authoritative_over_summaries": True,
                    "evidence_limited": evidence_limited,
                    "decisions": ["supported"],
                },
            }
        discovery_step = self.mining_model.discover_exploration(e2_payload)
        decisions = self._validate_mining_decisions(
            discovery_step.value,
            allowed_hypothesis_ids=None,
        )
        decisions = tuple(
            decision
            if decision.sample_basis is not None
            else self._with_runtime_sample_basis(
                (decision,),
                positive_refs=(
                    signature.case_ref
                    for signature in selected_grounded_signatures
                    if case_by_ref[signature.case_ref].ground_truth.is_surge
                ),
                control_refs=(
                    signature.case_ref
                    for signature in selected_grounded_signatures
                    if not case_by_ref[signature.case_ref].ground_truth.is_surge
                ),
            )[0]
            for decision in decisions
        )
        refined: dict[str, tuple[str, ...]] = {}
        selection_by_id = {
            item.hypothesis_id: {
                "induction_refs": tuple(
                    signature.case_ref for signature in selected_grounded_signatures
                ),
                "validation_refs": selected["validation_refs"],
            }
            for item in decisions
        }
        staged = self._stage_mining_decisions(
            decisions,
            selection_by_id=selection_by_id,
            case_by_ref=case_by_ref,
            refined=refined,
        )
        audit = {
            "schema_version": "signal-mining-audit-v1",
            "status": "completed",
            "cycle_id": cycle_id,
            "track": "exploration",
            "limits": config.to_dict(),
            "local_selection": {
                "e1_candidate_case_refs": list(selected["e1_refs"]),
                "induction_case_refs": [
                    item.case_ref for item in selected_grounded_signatures
                ],
                "validation_case_refs": list(selected["validation_refs"]),
                "grounded_case_refs": [
                    item.case_ref for item in grounded_signatures
                ],
            },
            "stages": {
                "E1": {
                    "signatures": [item.to_dict() for item in signatures],
                    "resolutions": resolution_audit,
                    "microbatches": microbatches,
                    "failures": {
                        key: list(value) for key, value in extraction_failures.items()
                    },
                    "usage": _usage_to_dict(extraction_usage),
                },
                "E2": {
                    "decisions": [item.to_dict() for item in decisions],
                    "no_candidate": discovery_step.metadata.get("no_candidate"),
                    "considered_case_count": len(selected_grounded_signatures),
                    "usage": _usage_to_dict(
                        discovery_step.usage
                        + _usage_from_dict(
                            dict(
                                dict(
                                    e2_payload["slow_method_memory"].get(
                                        "source_view_manifest", {}
                                    )
                                ).get("source_read_usage", {})
                            )
                        )
                    ),
                    "request_refs": list(
                        _ordered_unique(
                            [
                                *dict(
                                    e2_payload["slow_method_memory"].get(
                                        "source_view_manifest", {}
                                    )
                                ).get("source_read_request_refs", ()),
                                *discovery_step.metadata.get("request_refs", ()),
                            ]
                        )
                    ),
                },
            },
            "candidate_refs": list(staged["candidate_refs"]),
            "staging": list(staged["staging"]),
            "refined_hypotheses": {
                key: list(value) for key, value in refined.items()
            },
        }
        staged_with_failures = dict(staged)
        staged_with_failures["failures"] = {
            **dict(staged["failures"]),
            **{
                f"slow_loop:exploration_e1:{case_ref}": reasons
                for case_ref, reasons in extraction_failures.items()
            },
        }
        return self._mining_output(
            audit=audit,
            refined=refined,
            **staged_with_failures,
        )

    def _mining_output(
        self,
        *,
        audit: Mapping[str, Any],
        refined: Mapping[str, tuple[str, ...]],
        candidate_refs: Iterable[str] = (),
        induction_case_ids: Mapping[str, tuple[str, ...]] | None = None,
        validation_case_ids: Mapping[str, tuple[str, ...]] | None = None,
        failures: Mapping[str, tuple[str, ...]] | None = None,
        capability_gaps: Mapping[str, Mapping[str, Any]] | None = None,
        candidate_research_targets: Mapping[str, str] | None = None,
        staging: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        del staging
        refs = tuple(candidate_refs)
        default_target = (
            str(self.research_target_sampling.get("target_id", ""))
            if isinstance(self.research_target_sampling, Mapping)
            else ""
        ) or "surge_direction"
        target_map = dict(candidate_research_targets or {})
        for signal_ref in refs:
            target_map.setdefault(signal_ref, default_target)
        return {
            "candidate_refs": refs,
            "induction_case_ids": dict(induction_case_ids or {}),
            "validation_case_ids": dict(validation_case_ids or {}),
            "candidate_research_targets": target_map,
            "refined_hypotheses": dict(refined),
            "failures": dict(failures or {}),
            "capability_gaps": {
                str(key): dict(value)
                for key, value in dict(capability_gaps or {}).items()
            },
            "audit": dict(audit),
        }

    def _mining_context(self, *, cycle_id: int) -> dict[str, Any]:
        prior_work: list[dict[str, Any]] = []
        committed_paths = [
            self.workspace.experiments_root
            / "cycles"
            / f"cycle-{prior_cycle:04d}"
            / "slow_loop_validation.json"
            for prior_cycle in range(1, self.workspace.last_completed_cycle + 1)
        ]
        for path in [item for item in committed_paths if item.is_file()][-3:]:
            payload = _read_json(path)
            validation = payload.get("validation", {})
            if not isinstance(validation, Mapping):
                continue
            provisional_rows = []
            for signal_ref, reasons in dict(
                validation.get("provisional_candidates", {})
            ).items():
                try:
                    spec, _skill = self.registry.load_candidate(str(signal_ref))
                except ValidationError:
                    continue
                provisional_rows.append(
                    {
                        "signal_ref": str(signal_ref),
                        "description": spec.description,
                        "source_types": list(spec.source_types),
                        "reasons": list(reasons),
                    }
                )
            audit = dict(validation.get("agent_audits", {})).get(
                "mining_pipeline", {}
            )
            if (
                isinstance(audit, Mapping)
                and audit.get("track") == "hypothesis_then_exploration_fallback"
                and isinstance(audit.get("hypothesis"), Mapping)
            ):
                audit = dict(audit["hypothesis"])
            h1_rows = (
                dict(dict(audit).get("stages", {}))
                .get("H1", {})
                .get("hypotheses", [])
                if isinstance(audit, Mapping)
                else []
            )
            h1_stage = (
                dict(dict(audit).get("stages", {})).get("H1", {})
                if isinstance(audit, Mapping)
                else {}
            )
            failure_details = (
                dict(audit.get("failure_details", {}))
                if isinstance(audit, Mapping)
                and isinstance(audit.get("failure_details"), Mapping)
                else {}
            )
            refined_ids = set(
                dict(validation.get("refined_hypotheses", {}))
            )
            refined_reasons = dict(
                validation.get("refined_hypotheses", {})
            )
            evidence_unavailable = (
                dict(audit.get("evidence_unavailable", {}))
                if isinstance(audit, Mapping)
                else {}
            )
            prior_work.append(
                {
                    "provisional_candidates": provisional_rows,
                    "refined_hypotheses": [
                        {
                            "hypothesis": dict(item),
                            "reasons": list(
                                refined_reasons.get(
                                    str(item.get("hypothesis_id")), ()
                                )
                            ),
                        }
                        for item in h1_rows
                        if isinstance(item, Mapping)
                        and item.get("hypothesis_id") in refined_ids
                    ],
                    "evidence_unavailable": [
                        {
                            "hypothesis": dict(item),
                            "reasons": list(
                                evidence_unavailable.get(
                                    str(item.get("hypothesis_id")), ()
                                )
                            ),
                        }
                        for item in h1_rows
                        if isinstance(item, Mapping)
                        and item.get("hypothesis_id") in evidence_unavailable
                    ],
                    "h1_conclusion": (
                        dict(
                            h1_stage.get(
                                "conclusion", failure_details.get("conclusion", {})
                            )
                        )
                        if isinstance(h1_stage, Mapping)
                        and isinstance(h1_stage.get("conclusion"), Mapping)
                        else {}
                    ),
                    "h1_input_fingerprint": (
                        str(
                            h1_stage.get(
                                "input_fingerprint",
                                failure_details.get("input_fingerprint", ""),
                            )
                        )
                        if isinstance(h1_stage, Mapping)
                        else ""
                    ),
                }
            )
        cards: list[dict[str, Any]] = []
        for category in self.registry.list_categories():
            for card in self.registry.list_signal_cards(category):
                projected_card = self._mining_signal_card_view(card.to_dict())
                answer_phrases = self.registry.load_spec(card.ref).parameters.get(
                    "routing_answer_need_phrases", ()
                )
                if answer_phrases:
                    projected_card["routing_answer_need_phrases"] = list(
                        answer_phrases
                    )
                cards.append(projected_card)
        backlog_path = self.workspace.root / "capability_backlog.json"
        capability_backlog = (
            _read_json(backlog_path)
            if backlog_path.exists()
            else {
                "schema_version": "capability-gap-report-v3",
                "items": [],
                "signal_need_items": [],
                "open_count": 0,
                "resolved_count": 0,
            }
        )
        capability_backlog = dict(capability_backlog)
        capability_backlog = self._mask_owned_backlog_identities(
            capability_backlog
        )
        capability_backlog["signal_need_items"] = [
            {
                **dict(item),
                "need_ref": str(item.get("need_ref") or "need-" + _canonical_hash(item)[:16]),
            }
            for item in capability_backlog.get("signal_need_items", ())
            if isinstance(item, Mapping)
        ]
        reflection_actions, reflection_action_audit = (
            self._reflection_action_inventory()
        )
        capability_backlog["signal_need_items"].extend(reflection_actions)
        capability_backlog = self._mining_capability_backlog_view(
            capability_backlog
        )
        # The reflection index must be built from the authoritative unmasked
        # archive: every item_ref and source_ref is a content hash, so masking
        # entries first would break ref verification and closure. Identity is
        # removed only from the model-facing views below and from the originals
        # staged for on-demand reads.
        meta_entries = list(self.meta_memory.archive_view())
        meta_index = ReflectionMemoryIndex.from_entries(meta_entries)
        meta_view = _mask_identity_values(
            meta_index.brief_view(max_bytes=32_000),
            self.slow_role_identity_guards,
            expand_aliases=False,
        )
        meta_catalog = _mask_identity_values(
            meta_index.catalog_view(max_bytes=16_000),
            self.slow_role_identity_guards,
            expand_aliases=False,
        )
        visible_refs = {row["source_ref"] for row in meta_catalog["sources"]}
        previews = {}
        for action in reflection_actions:
            visible_refs.update(action.get("reflection_source_refs", ()))
            if action.get("reflection_item_ref"):
                visible_refs.add(action["reflection_item_ref"])
        for item in meta_view["items"]:
            for ref in (item["item_ref"], *item["source_refs"], *item["counter_refs"]):
                visible_refs.add(ref)
            previews[item["item_ref"]] = item["brief"]
        fast_sources = {}
        for row in meta_index.source_catalog():
            ref = row["source_ref"]
            if ref not in visible_refs or row["read_bytes"] > 48_000:
                continue
            original = meta_index.read_refs([ref], role="signal_mining", max_bytes=48_000)["sources"][0]
            fast_sources[ref] = {
                "visible_to": sorted(_SLOW_SOURCE_ROLES),
                "content": _mask_identity_values(
                    original,
                    self.slow_role_identity_guards,
                    expand_aliases=False,
                ),
                **({"brief": previews[ref]} if ref in previews else {}),
            }
        originals, original_manifest = read_slow_sources(
            (), role_scope="H1", source_catalog=fast_sources, budget_bytes=48_000,
        )
        original_manifest = {
            **original_manifest, "requested_refs": list(fast_sources),
            "deferred": [{"ref": ref, "reason": "fast_reflection_original_on_request"} for ref in fast_sources],
            "available_count": len(fast_sources), "deferred_count": len(fast_sources),
        }
        originals, original_manifest = self._optional_slow_source_read(
            model=self.mining_model, role_scope="H1", source_catalog=fast_sources,
            selected=originals, manifest=original_manifest,
        )
        prior_modality_footprints: list[dict[str, Any]] = []
        footprint_paths = [
            item
            for item in committed_paths
            if item.is_file()
        ] + sorted(
            (self.workspace.root / "slow_history").glob(
                "*/experiments/cycles/*/slow_loop_validation.json"
            )
        )
        for path in footprint_paths[-3:]:
            payload = _read_json(path)
            validation = dict(payload.get("validation", {}))
            audits = dict(validation.get("agent_audits", {}))
            metrics = dict(audits.get("mining_pipeline", {})).get(
                "modality_metrics", {}
            )
            if isinstance(metrics, Mapping) and metrics:
                footprint: dict[str, Any] = {
                    "cycle_id": int(validation.get("cycle_id", 0)),
                    **dict(metrics),
                }
                outcomes: list[dict[str, Any]] = []
                for signal_ref, record in dict(
                    validation.get("candidate_effectiveness", {})
                ).items():
                    if not isinstance(record, Mapping) or len(outcomes) >= 4:
                        continue
                    counts = dict(record.get("candidate", {}) or {})
                    confusion = dict(
                        record.get("candidate_confusion", {}) or {}
                    )
                    outcomes.append(
                        {
                            "signal_ref": str(signal_ref),
                            "disposition": str(record.get("disposition", "")),
                            "available": counts.get("available", 0),
                            "decisive": counts.get("decisive", 0),
                            "tp": confusion.get("tp", 0),
                            "fn": confusion.get("fn", 0),
                            "fp": confusion.get("fp", 0),
                            "tn": confusion.get("tn", 0),
                        }
                    )
                if outcomes:
                    # Prior candidates' real check-cohort outcomes: a
                    # predicate whose fires never overlap the positive
                    # class (tp near zero, fn high) is a semantic mismatch
                    # the next proposal must not repeat.
                    footprint["staged_candidate_outcomes"] = outcomes
                prior_modality_footprints.append(footprint)
        try:
            slow_method_view = self._slow_method_view("H1")
        except RuntimeBudgetExceeded as exc:
            exc.usage = exc.usage + _usage_from_dict(dict(original_manifest.get("source_read_usage", {})))
            raise
        except CandidateExecutionRejected as exc:
            raise CandidateExecutionRejected(exc.stage, str(exc),
                exc.usage + _usage_from_dict(dict(original_manifest.get("source_read_usage", {}))),
                details={**dict(exc.details), "request_refs": list(_ordered_unique((
                    *original_manifest.get("source_read_request_refs", ()), *exc.details.get("request_refs", ()),
                )))}) from exc
        return {
            "cycle_id": cycle_id,
            "fixed_prior": self.priors.mine_signal,
            "meta_info": meta_view,
            "meta_source_catalog": meta_catalog,
            "meta_memory_disclosures": [dict(item) for item in originals],
            "meta_memory_read_manifest": original_manifest,
            "research_objective": signal_research_objective(),
            "prior_modality_footprints": _mask_identity_values(
                prior_modality_footprints,
                self.slow_role_identity_guards,
                expand_aliases=False,
            ),
            "meta_context_audit": {
                "content_hash": _canonical_hash(meta_view),
                "round_ids": [entry.round_id for entry in self.meta_memory.entries],
                "case_count": sum(
                    len(plan.original_case_reflections)
                    for entry in self.meta_memory.entries
                    for plan in entry.plan_reflections
                ),
            },
            "reflection_action_audit": reflection_action_audit,
            "capability_backlog": _mask_identity_values(
                capability_backlog, self.slow_role_identity_guards, expand_aliases=False
            ),
            "stable_signal_cards": cards,
            "prior_slow_work": _mask_identity_values(
                prior_work, self.slow_role_identity_guards, expand_aliases=False
            ),
            "slow_method_memory": _mask_identity_values(
                slow_method_view,
                self.slow_role_identity_guards,
                expand_aliases=False,
            ),
            "available_raw_source_types": list(
                self.evidence_resolver.available_source_types
            ),
            "registered_deterministic_functions": sorted(
                self.validator.deterministic_functions
            ),
            "locked_test_available": False,
        }

    def _slow_method_view(self, role_scope: str) -> dict[str, Any]:
        """Project a bounded whole-entry evidence closure for one Slow role."""

        if self._active_slow_memory is None or self._active_slow_input is None:
            return {}
        processed = tuple(
            str(item)
            for item in self._active_slow_memory.get(
                "processed_feedback_refs", ()
            )
        )
        source_catalog = {
            str(row["feedback_ref"]): {
                "visible_to": sorted(_SLOW_SOURCE_ROLES),
                "content": dict(row),
            }
            for row in self._active_slow_input.get("feedback_rows", ())
            if isinstance(row, Mapping) and row.get("feedback_ref")
        }
        sources, manifest = read_slow_sources(
            processed,
            role_scope=role_scope,
            source_catalog=source_catalog,
            budget_bytes=64_000,
        )
        prior_deltas = [
            dict(item["slow_memory"])
            for item in self.workspace.committed_slow_artifacts()[-3:]
        ]
        method_deltas = [*prior_deltas, dict(self._active_slow_memory)]
        method_sources = slow_method_memory_sources(method_deltas)
        source_catalog.update(method_sources)
        if method_sources:
            manifest = {
                **manifest,
                "requested_refs": [*manifest["requested_refs"], *method_sources],
                "deferred": [*manifest["deferred"], *(
                    {"ref": ref, "reason": "authored_brief_original_on_request"}
                    for ref in method_sources
                )],
                "available_count": manifest["available_count"] + len(method_sources),
                "deferred_count": manifest["deferred_count"] + len(method_sources),
            }
        model = self.update_model if role_scope == "Update" else self.mining_model
        sources, manifest = self._optional_slow_source_read(
            model=model,
            role_scope=role_scope,
            source_catalog=source_catalog,
            selected=sources,
            manifest=manifest,
        )
        memory_view = project_slow_method_memory(
            method_deltas,
            budget_bytes=64_000,
        )
        return _project_slow_case_refs({
            **memory_view,
            "measurement_contract": signal_effectiveness_measurement_contract(),
            "source_entries": [dict(item) for item in sources],
            "source_view_manifest": manifest,
        })

    def _optional_slow_source_read(
        self,
        *,
        model: Any,
        role_scope: str,
        source_catalog: Mapping[str, Mapping[str, Any]],
        selected: tuple[dict[str, Any], ...],
        manifest: Mapping[str, Any],
        required_refs: Iterable[str] = (),
    ) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
        """Allow one typed source-view replacement without evicting required refs."""

        required = tuple(dict.fromkeys(str(item) for item in required_refs))
        available_refs = tuple(str(item) for item in manifest.get("requested_refs", ()))
        if not set(required) <= set(available_refs):
            raise ValidationError("required Slow source refs must be available")
        deferred = tuple(
            str(item.get("ref"))
            for item in manifest.get("deferred", ())
            if isinstance(item, Mapping) and item.get("ref")
        )
        selector = getattr(model, "request_slow_sources", None)
        if not deferred or not callable(selector):
            return selected, {**dict(manifest), "required_refs": list(required)}
        requested = tuple(str(ref) for ref in manifest.get("requested_refs", ()))
        selector_payload = {
            "source_read_contract_version": "slow-source-read-v1", "role_scope": role_scope,
            "validation_feedback": None,
            "available_sources": [], "omitted_available_sources": len(requested),
            "available_count": len(requested),
            "included_count": len(manifest.get("included_refs", ())), "deferred_count": len(deferred),
            "current_view": {
                "included_refs": [], "deferred_refs": [], "required_refs": list(required),
                "budget_bytes": int(manifest.get("budget_bytes", 64_000)), "max_items": manifest.get("max_items"),
            },
        }
        for ref in sorted(requested[-1024:], key=lambda ref: not bool(source_catalog.get(ref, {}).get("brief") or source_catalog.get(ref, {}).get("content", {}).get("brief"))):
            raw = source_catalog.get(str(ref))
            if raw is None:
                continue
            entry_size = len(json.dumps({"ref": ref, **dict(raw)}, sort_keys=True, ensure_ascii=False).encode("utf-8"))
            compact_row = {
                "ref": str(ref), "content_hash": _canonical_hash(dict(raw)),
                "currently_included": str(ref) in manifest.get("included_refs", ()),
                "read_bytes": entry_size,
            }
            preview = {
                **compact_row,
                **({"brief": raw["content"]["brief"], "kind": raw["content"].get("kind"),
                    "limitations": raw["content"].get("limitations"),
                    "applicable_scope": raw["content"].get("applicable_scope")}
                   if isinstance(raw.get("content"), Mapping) and raw["content"].get("brief") else {}),
                **({"brief": raw["brief"]} if raw.get("brief") else {}),
                **({"support_refs": raw["content"]["content"].get("source_refs", [])}
                   if raw.get("brief") and isinstance(raw.get("content", {}).get("content"), Mapping) else {}),
            }
            for offered in (preview, {**compact_row, "preview_omitted": "whole_preview_budget"}):
                candidate = deepcopy(selector_payload)
                candidate["available_sources"].append(offered)
                candidate["omitted_available_sources"] -= 1
                if ref in manifest.get("included_refs", ()):
                    candidate["current_view"]["included_refs"].append(ref)
                if ref in deferred:
                    candidate["current_view"]["deferred_refs"].append(ref)
                if len(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= 32_000:
                    selector_payload = candidate
                    break
        if len(json.dumps(selector_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) > 32_000:
            raise ValidationError("Slow source selector required manifest exceeds 32KB")
        step = selector(selector_payload)
        requested = tuple(str(item) for item in step.value)
        if not requested:
            return selected, {
                **dict(manifest),
                "source_read_request_refs": list(
                    step.metadata.get("request_refs", ())
                ),
                "source_read_usage": _usage_to_dict(step.usage),
                "source_read_mode": "kept_default_view",
                "required_refs": list(required),
            }
        combined = tuple(dict.fromkeys((*required, *requested)))
        try:
            replacement, replacement_manifest = read_slow_sources(
                combined,
                role_scope=role_scope,
                source_catalog=source_catalog,
                budget_bytes=int(manifest.get("budget_bytes", 64_000)),
                max_items=manifest.get("max_items"),
            )
            if not replacement:
                raise ValidationError("requested Slow source view exceeds whole-entry budget")
            included_refs = {str(item["ref"]) for item in replacement}
            if not set(required) <= included_refs:
                raise ValidationError("required Slow source view exceeds whole-entry budget")
        except ValidationError as exc:
            raise CandidateExecutionRejected(
                "slow_source_read", str(exc), step.usage,
                details={"request_refs": list(step.metadata.get("request_refs", ())),
                         "requested_refs": list(combined), "role_scope": role_scope},
            ) from exc
        all_requested = [str(item) for item in manifest.get("requested_refs", ())]
        replacement_deferred = {
            str(item.get("ref")): str(item.get("reason"))
            for item in replacement_manifest.get("deferred", ())
            if isinstance(item, Mapping) and item.get("ref")
        }
        deferred_all = [
            {
                "ref": ref,
                "reason": (
                    replacement_deferred.get(ref, "whole_entry_budget")
                    if ref in requested or ref in required
                    else "source_read_not_selected"
                ),
            }
            for ref in all_requested
            if ref not in included_refs
        ]
        return replacement, {
            **replacement_manifest,
            "requested_refs": all_requested,
            "deferred": deferred_all,
            "available_count": len(all_requested),
            "deferred_count": len(deferred_all),
            "source_read_request_refs": list(step.metadata.get("request_refs", ())),
            "source_read_usage": _usage_to_dict(step.usage),
            "source_read_mode": "replaced_default_view",
            "required_refs": list(required),
            "default_included_refs": list(manifest.get("included_refs", ())),
            "default_deferred_refs": list(deferred),
        }

    def _mask_owned_backlog_identities(
        self, backlog: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Mask safe local brands only inside rows with explicit case ownership."""

        result = dict(backlog)
        masked_needs: list[Any] = []
        for raw_item in backlog.get("signal_need_items", ()):
            if not isinstance(raw_item, Mapping):
                masked_needs.append(raw_item)
                continue
            case_ids: list[str] = []
            sources = []
            for source in raw_item.get("sources", ()):
                if not isinstance(source, Mapping):
                    continue
                source_ref = str(source.get("source_ref", ""))
                candidate = source_ref.split(":", 1)[1] if ":" in source_ref else ""
                if candidate in self._discovery_cases_by_id:
                    case_ids.append(candidate)
                sources.append({
                    **dict(source),
                    "source_ref": "source-" + _canonical_hash(source_ref)[:16],
                    **({"source_case_ref": _opaque_slow_case_ref(candidate)}
                       if candidate in self._discovery_cases_by_id else {}),
                })
            cases = tuple(
                self._discovery_cases_by_id[case_id]
                for case_id in dict.fromkeys(case_ids)
            )
            aliases = _scoped_slow_identity_guard_inventory(cases)
            masked = _mask_identity_values(
                {**dict(raw_item), "sources": sources}, aliases, expand_aliases=False
            )
            _assert_identity_values_masked(
                masked, aliases, expand_aliases=False
            )
            masked_needs.append(masked)
        result["signal_need_items"] = masked_needs
        return result

    def _reflection_action_inventory(
        self, *, limit: int = 48, budget_bytes: int = 32_000
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Project whole actionable briefs without replaying compatibility detail."""

        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        field_names = (
            "next_explorations",
            "missing_information_needs",
            "repeated_failure_modes",
            "misleading_signals",
        )
        for entry in reversed(self.meta_memory.entries):
            for plan in entry.plan_reflections:
                reflection = plan.vertical_plan_reflection
                structured = bool(reflection.reflection_items or reflection.selected_reflection_refs or reflection.no_findings_reason is not None)
                items = (*reflection.reflection_items, *(self.meta_memory.reflection_index().select_items(reflection.selected_reflection_refs) if reflection.selected_reflection_refs else ())) if structured else ()
                for field_name in field_names:
                    texts = [(item.brief, item) for item in items if item.category == field_name] if structured else [(text, None) for text in getattr(reflection, field_name)]
                    for raw_text, item in texts:
                        text = " ".join(str(raw_text).split())
                        semantic_key = _normalize_semantics(text)
                        if not semantic_key or semantic_key in seen:
                            continue
                        seen.add(semantic_key)
                        provenance = {
                            "source_round": entry.round_id,
                            "source_plan_ref": "plan-" + _canonical_hash(plan.plan_id)[:16],
                            "reflection_field": field_name,
                            "text": text,
                        }
                        rows.append({
                            "need_ref": "reflection-" + _canonical_hash(provenance)[:16],
                            "kind": "meta_reflection_action", "need": text,
                            "reflection_field": field_name, "source_round": entry.round_id,
                            "sources": [],
                            **({"reflection_item_ref": item.item_ref,
                                "reflection_source_refs": list(item.source_refs),
                                "limitations": list(item.limitations)} if item else {}),
                        })
        projected: list[dict[str, Any]] = []
        audit = {
            "schema_version": "reflection-action-projection-v1",
            "available_count": len(rows), "projected_count": 0,
            "omitted_count": len(rows), "limit": limit, "budget_bytes": budget_bytes,
            "field_counts": {field_name: 0 for field_name in field_names},
        }
        for row in rows:
            if len(projected) >= limit:
                break
            proposed_audit = {**audit, "projected_count": len(projected) + 1,
                "omitted_count": len(rows) - len(projected) - 1,
                "field_counts": {**audit["field_counts"], row["reflection_field"]: audit["field_counts"][row["reflection_field"]] + 1}}
            envelope = {"items": [*projected, row], "audit": proposed_audit}
            if len(json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= budget_bytes:
                projected.append(row)
                audit = proposed_audit
        return projected, audit

    @staticmethod
    def _mining_capability_backlog_view(
        backlog: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Remove local identities and paths from the H1-only backlog view."""

        needs = []
        for raw_item in backlog.get("signal_need_items", ()):
            if not isinstance(raw_item, Mapping):
                continue
            item = dict(raw_item)
            item["sources"] = [
                {
                    "source_ref": str(source["source_ref"])
                    if re.fullmatch(r"source-[0-9a-f]{16}", str(source.get("source_ref", "")))
                    else "source-" + _canonical_hash(
                        str(source.get("source_ref", ""))
                    )[:16],
                    **({"source_case_ref": source["source_case_ref"]}
                       if source.get("source_case_ref") else {}),
                    "source_round": source.get("source_round"),
                    "source_fingerprint": source.get("source_fingerprint"),
                    "original_need": source.get("original_need"),
                    "stop_reason": source.get("stop_reason"),
                }
                for source in item.get("sources", ())
                if isinstance(source, Mapping)
            ]
            needs.append(item)
        items = []
        for raw_item in backlog.get("items", ()):
            if not isinstance(raw_item, Mapping):
                continue
            item = {
                key: value
                for key, value in raw_item.items()
                if key != "affected_case_ids"
            }
            item["affected_source_count"] = len(
                raw_item.get("affected_case_ids", ())
            )
            items.append(item)
        technical = []
        for raw_item in backlog.get("technical_failures", ()):
            if not isinstance(raw_item, Mapping):
                continue
            technical.append(
                {
                    key: value
                    for key, value in raw_item.items()
                    if key != "case_id"
                }
            )
        return {
            "schema_version": backlog.get("schema_version"),
            "items": items,
            "signal_need_items": needs,
            "technical_failures": technical,
            "diagnostic_attempt_count": len(backlog.get("diagnostic_attempts", ())),
            "open_count": backlog.get("open_count", 0),
            "resolved_count": backlog.get("resolved_count", 0),
        }

    @staticmethod
    def _mining_signal_card_view(card: Mapping[str, Any]) -> dict[str, Any]:
        """Omit an all-zero learned profile from the H1-only card projection."""

        result = dict(card)
        profile = result.get("learned_profile")
        if not isinstance(profile, Mapping):
            return result
        if (
            int(profile.get("selection_events", 0)) == 0
            and int(profile.get("unique_observations", 0)) == 0
        ):
            result.pop("learned_profile", None)
        return result

    def _mining_case_universe(
        self, *, limit: int
    ) -> tuple[tuple[str, EvolutionCase], ...]:
        manifest_cases = self._manifest_cases("dev_case_ids")
        selected = (
            manifest_cases[:limit]
            if manifest_cases
            else _sample_signal_discovery_cases(self.discovery_cases, limit=limit)
        )
        return tuple(
            (f"case-{index:03d}", case)
            for index, case in enumerate(selected, start=1)
        )

    def _manifest_cases(self, key: str) -> tuple[EvolutionCase, ...]:
        """Resolve one frozen sample partition without filling missing ids."""

        manifest = self._active_sampling_manifest
        if not isinstance(manifest, Mapping):
            return ()
        case_by_id = {case.case_id: case for case in self.discovery_cases}
        return tuple(
            case_by_id[case_id]
            for case_id in (str(item) for item in manifest.get(key, ()))
            if case_id in case_by_id
        )

    def _preflight_h2_profiles(
        self, case_pairs: Iterable[tuple[str, EvolutionCase]]
    ) -> None:
        """Pause before H1 when mandatory H2 profiles cannot be obtained."""

        pairs = tuple(case_pairs)
        config = self.mining_config
        potential_positive = sum(case.ground_truth.is_surge for _, case in pairs)
        potential_control = len(pairs) - potential_positive
        if (
            len(pairs) < config.h2_min_ready_issuers
            or potential_positive < config.h2_min_ready_per_class
            or potential_control < config.h2_min_ready_per_class
        ):
            return
        ready = 0
        positive_ready = 0
        control_ready = 0
        first_case_ref = "profile-preflight"
        for case_ref, case in pairs:
            if first_case_ref == "profile-preflight":
                first_case_ref = case_ref
            _documents, profile = self._mining_local_profile(case)
            if not self._mining_profile_ready(profile):
                continue
            ready += 1
            if case.ground_truth.is_surge:
                positive_ready += 1
            else:
                control_ready += 1
        if (
            ready >= config.h2_min_ready_issuers
            and positive_ready >= config.h2_min_ready_per_class
            and control_ready >= config.h2_min_ready_per_class
        ):
            return
        request = self._mining_profile_request(first_case_ref)
        can_acquire = getattr(self.evidence_resolver, "can_acquire", None)
        if can_acquire is None or can_acquire(request):
            return
        reason_resolver = getattr(
            self.evidence_resolver,
            "acquisition_unavailability_reason",
            None,
        )
        reason = (
            reason_resolver(request)
            if reason_resolver is not None
            else "profile_adapter_unavailable"
        )
        raise SlowLoopDataUnavailable(
            "profile-preflight",
            reason or "profile_adapter_unavailable",
        )

    @staticmethod
    def _mining_profile_request(case_ref: str) -> RawInfoRequest:
        return RawInfoRequest(
            request_id=f"signal_mining_profile:{case_ref}",
            description="Latest point-in-time annual filing business profile.",
            source_types=("10-k", "filing", "sec_filing"),
            lookback_days=730,
            max_documents=1,
            query="item 1 business",
        )

    def _mining_local_profile(
        self, case: EvolutionCase
    ) -> tuple[tuple[RawInfoDocument, ...], dict[str, Any]]:
        documents = tuple(
            document
            for document in self.raw_info_store.documents
            if document.company_id == case.company_id
            and document.available_at <= case.prediction_time
        )
        profile = _point_in_time_profile_fields(case.basic_info, documents)
        if not _usable_business_description(profile.get("business_description")):
            profile.pop("business_description", None)
            excerpt = _item1_business_excerpt(documents)
            if excerpt:
                profile["business_description"] = excerpt
        return documents, profile

    def _h1_measurable_evidence_manifest(
        self, case_pairs: Iterable[tuple[str, EvolutionCase]]
    ) -> dict[str, Any]:
        """Project value-free measurable evidence families for the H1 cohort.

        Enumerates recurring structured financial concepts, price-series
        coverage, and narrative source families from the selected cohort's
        point-in-time documents without exposing record values, issuer
        identities, or outcome labels.
        """

        concept_cases: dict[tuple[str, str, str, str], set[str]] = {}
        comparable_cases: dict[tuple[str, str, str, str], set[str]] = {}
        price_cases: set[str] = set()
        narrative_cases: dict[str, set[str]] = {}
        cohort = [(str(ref), case) for ref, case in case_pairs]
        all_documents = self.raw_info_store.documents
        for case_ref, case in cohort:
            for document in all_documents:
                if (
                    document.company_id != case.company_id
                    or document.available_at > case.prediction_time
                ):
                    continue
                source_type = document.source_type.casefold()
                if source_type in {
                    "market_data",
                    "historical_price",
                    "price_daily",
                    "prices",
                }:
                    price_cases.add(case_ref)
                    continue
                if "fact" in source_type or "financial" in source_type:
                    context = _company_facts_context(
                        document,
                        max_content_chars=_H1_MANIFEST_PROJECTION_CHARS,
                        query=None,
                    )
                    if context is not None:
                        for concept in context["concepts"]:
                            key = (
                                str(concept["taxonomy"]),
                                str(concept["concept"]),
                                str(concept.get("label", "")),
                                str(concept["unit"]),
                            )
                            if not key[1]:
                                continue
                            concept_cases.setdefault(key, set()).add(case_ref)
                            if len(concept.get("records", ())) >= 2:
                                comparable_cases.setdefault(key, set()).add(
                                    case_ref
                                )
                        continue
                narrative_cases.setdefault(document.source_type, set()).add(
                    case_ref
                )
        ranked = sorted(
            (key for key, refs in concept_cases.items() if len(refs) >= 2),
            key=lambda key: (
                -len(comparable_cases.get(key, ())),
                -len(concept_cases[key]),
                -_QUERYLESS_COMPANY_FACT_PRIORITY.get(key[1].casefold(), 0),
                key,
            ),
        )[:_H1_MANIFEST_CONCEPT_LIMIT]
        return {
            "schema_version": "h1-measurable-evidence-manifest-v1",
            "cohort_case_count": len(cohort),
            "structured_financial_concepts": [
                {
                    "taxonomy": key[0],
                    "concept": key[1],
                    "source_display_name": key[2],
                    "unit": key[3],
                    "case_count": len(concept_cases[key]),
                    "cases_with_comparable_records": len(
                        comparable_cases.get(key, ())
                    ),
                }
                for key in ranked
            ],
            "pre_cutoff_price_series_cases": len(price_cases),
            "narrative_source_families": [
                {"source_type": source_type, "case_count": len(refs)}
                for source_type, refs in sorted(
                    narrative_cases.items(),
                    key=lambda item: (-len(item[1]), item[0]),
                )[:10]
            ],
            "coverage_note": (
                "Runtime-owned, value-free coverage of this cohort's "
                "point-in-time documents. A measurement input outside these "
                "families has no in-window source in this cohort."
            ),
        }

    @staticmethod
    def _mining_profile_ready(profile: Mapping[str, Any]) -> bool:
        return bool(
            _usable_business_description(profile.get("business_description"))
            or profile.get("industry")
            or profile.get("sector")
        )

    @staticmethod
    def _h2_applicability_contract(
        briefs: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Describe only fields and categorical values visible in this H2 pool."""

        rows = tuple(briefs)
        field_by_rule = {
            "industry_values": "industry",
            "sector_values": "sector",
            "exchange_values": "exchange",
            "market_cap_bucket_values": "market_cap_bucket",
            "listing_age_bucket_values": "listing_age_bucket",
        }
        observed_values = {
            rule_name: sorted(
                {
                    str(brief[field_name])
                    for brief in rows
                    if field_name in brief and str(brief[field_name]).strip()
                }
            )
            for rule_name, field_name in field_by_rule.items()
        }
        observed_values["raw_info_source_type_values"] = sorted(
            {
                str(source_type)
                for brief in rows
                for source_type in (
                    brief.get("raw_info_coverage", {}).get("source_types", ())
                    if isinstance(brief.get("raw_info_coverage"), Mapping)
                    else ()
                )
            }
        )
        return {
            "schema_version": "h2-applicability-contract-v1",
            "canonical_rule_names": [
                "all_ready_issuers",
                "business_description_topics",
                *[
                    rule_name
                    for rule_name, values in observed_values.items()
                    if values
                ],
            ],
            "observed_values": observed_values,
            "business_description_topic_limits": {
                "max_values": 6,
                "max_terms_per_value": 4,
                "max_total_terms": 8,
            },
        }

    @staticmethod
    def _h2_applicability_matches(
        applicability: str,
        brief: Mapping[str, Any],
    ) -> bool:
        """Apply an H1 canonical rule without model judgment or label access."""

        if applicability == "all_ready_issuers":
            return True
        rule_name, separator, raw_values = applicability.partition(":")
        if not separator:
            return False
        values = tuple(item.casefold() for item in raw_values.split("|") if item)
        if not values:
            return False
        if rule_name == "business_description_topics":
            description_terms = set(
                _h3_ordered_content_terms(
                    str(brief.get("business_description", "")),
                    exclude_generic=False,
                )
            )
            return any(
                set(
                    _h3_ordered_content_terms(value, exclude_generic=False)
                ).issubset(description_terms)
                for value in values
            )
        if rule_name == "raw_info_source_type_values":
            coverage = brief.get("raw_info_coverage", {})
            visible = (
                coverage.get("source_types", ())
                if isinstance(coverage, Mapping)
                else ()
            )
        else:
            field_by_rule = {
                "industry_values": "industry",
                "sector_values": "sector",
                "exchange_values": "exchange",
                "market_cap_bucket_values": "market_cap_bucket",
                "listing_age_bucket_values": "listing_age_bucket",
            }
            field_name = field_by_rule.get(rule_name)
            if field_name is None:
                return False
            visible = (brief.get(field_name),)
        visible_values = {
            str(item).casefold() for item in visible if item is not None and str(item)
        }
        return any(value in visible_values for value in values)

    def _mining_case_brief(
        self, case_ref: str, case: EvolutionCase
    ) -> dict[str, Any]:
        aliases = self.slow_role_identity_guards
        documents, profile = self._mining_local_profile(case)
        profile_resolution: dict[str, Any] | None = None
        if not self._mining_profile_ready(profile):
            request = self._mining_profile_request(case_ref)
            can_acquire = getattr(self.evidence_resolver, "can_acquire", None)
            acquisition_available = can_acquire is None or can_acquire(request)
            if not acquisition_available:
                profile_resolution = {
                    "status": "unavailable",
                    "data_gap": {"reason": "profile_adapter_unavailable"},
                    "document_count": 0,
                }
            else:
                resolution = self.evidence_resolver.resolve(
                    request,
                    company_id=case.company_id,
                    identity=case.basic_info,
                    as_of=case.prediction_time,
                )
                if resolution.gap is not None and resolution.gap.reason.value in {
                    "provider_error",
                    "quota_deferred",
                    "materialization_failed",
                }:
                    raise SlowLoopDataUnavailable(
                        case_ref,
                        resolution.gap.reason.value,
                    )
                acquired = self.evidence_resolver.load_documents(
                    resolution, as_of=case.prediction_time
                )
                documents = tuple(
                    {
                        item.document_id: item
                        for item in (*documents, *acquired)
                    }.values()
                )
                profile = _point_in_time_profile_fields(case.basic_info, documents)
                if not _usable_business_description(
                    profile.get("business_description")
                ):
                    profile.pop("business_description", None)
                profile_resolution = {
                    "status": resolution.status,
                    "data_gap": resolution.gap.to_dict() if resolution.gap else None,
                    "document_count": len(acquired),
                }
        if not _usable_business_description(profile.get("business_description")):
            profile.pop("business_description", None)
            excerpt = _item1_business_excerpt(documents)
            if excerpt:
                profile["business_description"] = excerpt
        profile_ready = self._mining_profile_ready(profile)
        description = str(
            profile.get("business_description") or "unavailable"
        )[:600]
        safe_info = {
            "business_description": description,
            "industry": profile.get("industry") or "unavailable",
            "sector": profile.get("sector") or "unavailable",
            "exchange": profile.get("exchange") or "unavailable",
            "market_cap_bucket": _market_cap_bucket(profile.get("market_cap")),
            "listing_age_bucket": _listing_age_bucket(
                profile.get("listing_date"),
                as_of=case.prediction_time,
            ),
        }
        safe_info = {
            key: value
            for key, value in safe_info.items()
            if key == "business_description" or value != "unavailable"
        }
        masked_info = dict(_mask_identity_values(safe_info, aliases, expand_aliases=False))
        _assert_identity_values_masked(masked_info, aliases, expand_aliases=False)
        return {
            "case_ref": case_ref,
            "prediction_year": case.prediction_time.year,
            **masked_info,
            "raw_info_coverage": {
                "document_count": len(documents),
                "source_types": sorted({item.source_type for item in documents}),
            },
            "_profile_ready": profile_ready,
            "_profile_resolution": profile_resolution,
        }

    def _select_mining_cases(
        self,
        ranked_refs: Iterable[str],
        *,
        case_by_ref: Mapping[str, EvolutionCase],
        validation_ranked_refs: Iterable[str] = (),
    ) -> dict[str, tuple[str, ...]] | None:
        positives: list[str] = []
        controls: list[str] = []
        seen_companies: set[str] = set()
        for case_ref in ranked_refs:
            case = case_by_ref[case_ref]
            if case.company_id in seen_companies:
                continue
            seen_companies.add(case.company_id)
            target = positives if case.ground_truth.is_surge else controls
            target.append(case_ref)
        induction_count = self.mining_config.induction_cases_per_class
        validation_count = self.mining_config.validation_cases_per_class
        if not positives or not controls:
            return None
        induction = tuple(
            [*positives[:induction_count], *controls[:induction_count]]
        )
        validation_refs = tuple(validation_ranked_refs)
        if validation_refs:
            validation_positives = [
                ref for ref in validation_refs if case_by_ref[ref].ground_truth.is_surge
            ]
            validation_controls = [
                ref for ref in validation_refs if not case_by_ref[ref].ground_truth.is_surge
            ]
            validation = tuple(
                [
                    *validation_positives[:validation_count],
                    *validation_controls[:validation_count],
                ]
            )
        else:
            validation = tuple(
                [
                    *positives[induction_count : induction_count + validation_count],
                    *controls[induction_count : induction_count + validation_count],
                ]
            )
        return {"induction_refs": induction, "validation_refs": validation}

    def _signal_update_evidence_packet(
        self,
        case_ref: str,
        case: EvolutionCase,
        *,
        spec: SignalSpec,
        result: SignalResult,
        resolution: RawInfoResolution,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Project the exact documents already consumed by one Signal execution."""

        documents = self.evidence_resolver.load_documents(
            resolution, as_of=case.prediction_time
        )
        aliases = self.slow_role_identity_guards
        cited_evidence = (
            ("supporting", result.supporting_evidence),
            ("counter", result.counter_evidence),
        )
        cited_document_ids = {
            item.document_id
            for _group, items in cited_evidence
            for item in items
        }
        documents = tuple(
            sorted(
                documents,
                key=lambda item: (
                    item.document_id not in cited_document_ids,
                    item.document_id,
                ),
            )
        )
        document_ref_by_id = {
            document.document_id: f"document-{index:02d}"
            for index, document in enumerate(documents, start=1)
        }
        evidence = [
            _model_evidence_view(
                document,
                index=index,
                aliases=aliases,
                query=spec.retrieval_policy.query,
                expand_aliases=False,
            )
            for index, document in enumerate(documents, start=1)
        ]
        result_view = signal_result_model_view(result)
        for group in ("supporting", "counter"):
            for item in result_view["evidence"][group]:
                item["document_id"] = document_ref_by_id.get(
                    item["document_id"], "missing-document"
                )
        masked_result = _mask_identity_values(result_view, aliases, expand_aliases=False)
        executed_evidence = [
            {
                "role": group,
                "document_ref": document_ref_by_id.get(
                    item.document_id, "missing-document"
                ),
                "exact_span": _mask_identity_values(
                    item.exact_span, aliases, expand_aliases=False
                ),
                "timestamp": item.timestamp.isoformat(),
            }
            for group, items in cited_evidence
            for item in items
        ]
        _assert_identity_values_masked(evidence, aliases, expand_aliases=False)
        _assert_identity_values_masked(masked_result, aliases, expand_aliases=False)
        _assert_identity_values_masked(executed_evidence, aliases, expand_aliases=False)
        packet = {
            "case_ref": case_ref,
            "evidence_observation": {
                "prediction_time": case.prediction_time.isoformat(),
                "executed_evidence": executed_evidence,
                "evidence": evidence,
                "evidence_scope": (
                    "executed_evidence is the Signal's exact cited projection; evidence "
                    "adds bounded context from every exact Signal execution input; "
                    "an excerpt cannot prove that an absent fact is absent from the source"
                ),
                "resolution_status": resolution.status,
                "resolution_coverage": resolution.coverage.to_dict(),
                "current_signal_result": masked_result,
            },
            "outcome_relation": {
                "label": "positive" if case.ground_truth.is_surge else "control",
                "current_signal_relation": (
                    "not_assessable"
                    if result.value in {SignalValue.UNAVAILABLE, SignalValue.NEUTRAL}
                    else (
                        "aligned"
                        if (result.value is SignalValue.POSITIVE)
                        == case.ground_truth.is_surge
                        else "misaligned"
                    )
                ),
                "rule": (
                    "The label may assess directional association only after source "
                    "support is judged; it is not evidence that a fact or event exists."
                ),
            },
        }
        return packet, {
            "case_ref": case_ref,
            "status": resolution.status,
            "input_request": resolution.request.to_dict(),
            "document_count": len(documents),
            "document_ids": [item.document_id for item in documents],
            "document_hashes": [item.content_hash for item in documents],
            "cited_document_refs": [
                item["document_ref"] for item in executed_evidence
            ],
            "as_of": case.prediction_time.isoformat(),
            "reused_signal_execution_input": True,
        }

    def _mining_evidence_packet(
        self,
        case_ref: str,
        case: EvolutionCase,
        *,
        source_types: tuple[str, ...],
        query: str | None,
        lookback_days: int,
        reveal_label: bool,
        label_override: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        selection: dict[str, Any] = {}
        available_source_types = set(source_types)
        required_source_groups: tuple[tuple[str, ...], ...] = ()
        if query is None:
            financial_group = tuple(
                item
                for item in _EXPLORATION_FINANCIAL_SOURCE_TYPES
                if item in available_source_types
            )
            filing_group = tuple(
                item
                for item in _EXPLORATION_FILING_SOURCE_TYPES
                if item in available_source_types
            )
            if financial_group and filing_group:
                required_source_groups = (financial_group, filing_group)

        def select_documents(
            candidates: tuple[RawInfoDocument, ...],
            request: RawInfoRequest,
        ) -> tuple[RawInfoDocument, ...]:
            selected, evidence, audit = _select_h3_model_evidence(
                candidates,
                case=case,
                query=query,
                limit=request.max_documents,
                aliases=_discovery_identity_terms((case,)),
                expand_aliases=True,
                prefer_source_diversity=True,
                max_content_chars=2_400,
            )
            evidence = _mask_identity_values(
                evidence,
                self.slow_role_identity_guards,
                expand_aliases=False,
            )
            selection.clear()
            selection.update(audit)
            selection["evidence"] = evidence
            return selected

        resolution = self.evidence_resolver.resolve(
            RawInfoRequest(
                request_id=f"signal_mining:{case_ref}",
                description="Exact point-in-time evidence for Signal Mining comparison.",
                source_types=source_types,
                lookback_days=lookback_days,
                max_documents=self.mining_config.evidence_documents_per_case,
                query=query,
                required_source_groups=required_source_groups,
            ),
            company_id=case.company_id,
            identity=case.basic_info,
            as_of=case.prediction_time,
            select_documents=select_documents,
        )
        if resolution.gap is not None and resolution.gap.reason.value in {
            "provider_error",
            "quota_deferred",
            "materialization_failed",
        }:
            raise SlowLoopDataUnavailable(case_ref, resolution.gap.reason.value)
        documents = self.evidence_resolver.load_documents(
            resolution,
            as_of=case.prediction_time,
        )
        evidence = list(selection.pop("evidence", ())) if documents else []
        filtered_documents = list(selection.get("filtered_documents", ()))
        query_coverage = dict(
            selection.get(
                "query_coverage",
                _h3_text_query_coverage((), query=query),
            )
        )
        packet: dict[str, Any] = {
            "case_ref": case_ref,
            "prediction_time": case.prediction_time.isoformat(),
            "evidence": evidence,
            "query_match_status": selection.get(
                "query_match_status", "no_exact_source"
            ),
            "resolution_status": (
                resolution.status
                if documents
                else "unresolved_after_relevance_filter"
            ),
        }
        if reveal_label:
            if label_override is not None:
                if label_override not in {"positive", "control"}:
                    raise ValidationError(
                        "comparison label override must be positive or control"
                    )
                packet["label"] = label_override
            else:
                packet["label"] = (
                    "positive" if case.ground_truth.is_surge else "control"
                )
        return packet, {
            "case_ref": case_ref,
            "status": (
                resolution.status
                if documents
                else "unresolved_after_relevance_filter"
            ),
            "requested_source_types": list(source_types),
            "required_source_groups": [
                list(group) for group in required_source_groups
            ],
            "document_count": len(documents),
            "usable": bool(documents),
            "document_hashes": [item.content_hash for item in documents],
            "filtered_documents": filtered_documents,
            "query_coverage": query_coverage,
            "as_of": case.prediction_time.isoformat(),
        }

    def _mining_candidate_contract(self) -> dict[str, Any]:
        return {
            "execution_semantics": signal_candidate_execution_contract(),
            "arguments_schema": self._candidate_arguments_schema(clone=False),
            "deterministic_function_contracts": deterministic_signal_function_contracts(
                self.validator.deterministic_functions
            ),
            "constraints": [
                "new signal_id only; existing stable identities belong to Update",
                "non-empty point-in-time fixtures required",
                "choose a deterministic function only when its documented measurement "
                "matches the definition; parameters do not replace its formula",
                "structured modality requires an exact registered deterministic "
                "function; otherwise retain a capability gap",
                "narrative modality requires a source-grounded LLM skill",
                "split mixed structured-formula and narrative-fallback proposals",
                "candidate text and fixtures must not contain Discovery identities or labels",
            ],
        }

    @staticmethod
    def _validate_mining_decisions(
        decisions: Iterable[SignalMiningDecision],
        *,
        allowed_hypothesis_ids: set[str] | None,
    ) -> tuple[SignalMiningDecision, ...]:
        values = tuple(decisions)
        ids = [item.hypothesis_id for item in values]
        if len(set(ids)) != len(ids):
            raise ValidationError("Signal Mining decisions must have unique hypothesis ids")
        if allowed_hypothesis_ids is not None:
            if set(ids) != allowed_hypothesis_ids:
                raise ValidationError(
                    "Signal Mining decisions must cover every supplied comparison"
                )
        return values

    def _target_mode_validation_case_ids(self) -> tuple[str, ...] | None:
        """Balanced target-check case ids when a target sampling is active."""

        target_groups = (
            self.research_target_reveal.get("groups")
            if isinstance(self.research_target_reveal, Mapping)
            else None
        )
        target_check_case_ids = (
            self.research_target_sampling.get("sampling", {}).get(
                "check_case_ids", ()
            )
            if isinstance(self.research_target_sampling, Mapping)
            else ()
        )
        if not target_check_case_ids or not target_groups:
            return None
        balanced: list[str] = []
        for wanted_group in ("ge3_high", "ge3_low"):
            taken = 0
            for case_id in target_check_case_ids:
                case_id = str(case_id)
                if (
                    target_groups.get(case_id) == wanted_group
                    and taken
                    < self.mining_config.validation_cases_per_class
                    and case_id not in balanced
                ):
                    balanced.append(case_id)
                    taken += 1
        return tuple(balanced)

    def _stage_mining_decisions(
        self,
        decisions: Iterable[SignalMiningDecision],
        *,
        selection_by_id: Mapping[str, Mapping[str, Any]],
        case_by_ref: Mapping[str, EvolutionCase],
        refined: dict[str, tuple[str, ...]],
    ) -> dict[str, Any]:
        candidate_refs: list[str] = []
        induction_case_ids: dict[str, tuple[str, ...]] = {}
        validation_case_ids: dict[str, tuple[str, ...]] = {}
        failures: dict[str, tuple[str, ...]] = {}
        staging: list[dict[str, Any]] = []
        for decision in decisions:
            if decision.disposition != "supported":
                if decision.disposition == "refine":
                    refined[decision.hypothesis_id] = decision.rationale
                staging.append(
                    {
                        "hypothesis_id": decision.hypothesis_id,
                        "status": decision.disposition,
                        "reasons": list(decision.rationale),
                    }
                )
                continue
            candidate = dict(decision.candidate or {})
            if set(candidate) != {"spec", "skill", "tests"}:
                failures[f"slow_loop:mining_stage:{decision.hypothesis_id}"] = (
                    "supported candidate requires exactly spec, skill, and tests",
                )
                continue
            tests = candidate["tests"]
            if not isinstance(tests, list):
                failures[f"slow_loop:mining_stage:{decision.hypothesis_id}"] = (
                    "candidate tests must be an array",
                )
                continue
            try:
                signal_ref = self._stage_from_tool(
                    spec=candidate["spec"],
                    skill=(
                        str(candidate["skill"])
                        if candidate["skill"] is not None
                        else None
                    ),
                    tests=tests,
                    origin=f"mining:{decision.hypothesis_id}",
                    collected=candidate_refs,
                )
                contract = self._run_signal_tests_tool(signal_ref)
                if not contract["accepted"]:
                    candidate_refs.remove(signal_ref)
                    failures[signal_ref] = tuple(
                        str(reason) for reason in contract["reasons"]
                    )
                    staging.append(
                        {
                            "hypothesis_id": decision.hypothesis_id,
                            "signal_ref": signal_ref,
                            "status": "contract_rejected",
                            "reasons": list(contract["reasons"]),
                        }
                    )
                    continue
                selection = selection_by_id[decision.hypothesis_id]
                target_dev_ids = (
                    self.research_target_sampling.get("sampling", {}).get(
                        "dev_case_ids", ()
                    )
                    if isinstance(self.research_target_sampling, Mapping)
                    else ()
                )
                if target_dev_ids:
                    induction_case_ids[signal_ref] = tuple(
                        str(case_id) for case_id in target_dev_ids
                    )
                else:
                    induction_case_ids[signal_ref] = tuple(
                        case_by_ref[case_ref].case_id
                        for case_ref in selection["induction_refs"]
                    )
                target_validation = self._target_mode_validation_case_ids()
                validation_case_ids[signal_ref] = target_validation or tuple(
                    case_by_ref[case_ref].case_id
                    for case_ref in selection["validation_refs"]
                )
                staging.append(
                    {
                        "hypothesis_id": decision.hypothesis_id,
                        "signal_ref": signal_ref,
                        "status": "contract_accepted",
                    }
                )
            except ValidationError as exc:
                failures[f"slow_loop:mining_stage:{decision.hypothesis_id}"] = (
                    str(exc),
                )
                staging.append(
                    {
                        "hypothesis_id": decision.hypothesis_id,
                        "status": "staging_failed",
                        "reasons": [str(exc)],
                    }
                )
        return {
            "candidate_refs": tuple(candidate_refs),
            "induction_case_ids": induction_case_ids,
            "validation_case_ids": validation_case_ids,
            "failures": failures,
            "staging": tuple(staging),
        }

    def _candidate_arguments_schema(self, *, clone: bool) -> dict[str, Any]:
        registered_functions = sorted(self.validator.deterministic_functions)
        schema: dict[str, Any] = {
            "type": "object",
            "required": ["spec", "tests"],
            "additionalProperties": False,
            "properties": {
                "spec": {
                    "type": "object",
                    "required": [
                        "signal_id",
                        "version",
                        "category",
                        "modality",
                        "definition",
                        "schema",
                        "execution",
                        "raw_retrieval",
                        "evidence_policy",
                        "parameters",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "signal_id": {"type": "string"},
                        "version": {"type": "integer", "minimum": 1},
                        "category": {"type": "string"},
                        "modality": {
                            "enum": ["structured", "narrative"]
                        },
                        "definition": {
                            "type": "object",
                            "required": ["description"],
                            "properties": {"description": {"type": "string"}},
                            "additionalProperties": False,
                        },
                        "schema": {
                            "const": {
                                "value": {
                                    "type": "categorical",
                                    "values": [
                                        "positive",
                                        "neutral",
                                        "negative",
                                        "unavailable",
                                    ],
                                },
                                "confidence": {"type": "float"},
                            }
                        },
                        "execution": {
                            "oneOf": [
                                {
                                    "type": "object",
                                    "required": ["type", "function"],
                                    "properties": {
                                        "type": {"const": "deterministic"},
                                        "function": {
                                            "enum": registered_functions,
                                        },
                                    },
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "required": ["type", "skill_file"],
                                    "properties": {
                                        "type": {"const": "llm"},
                                        "skill_file": {"type": "string"},
                                    },
                                    "additionalProperties": False,
                                },
                            ]
                        },
                        "raw_retrieval": {
                            "type": "object",
                            "required": ["source_types", "query_terms"],
                            "properties": {
                                "source_types": {
                                    "type": "array",
                                    "minItems": 1,
                                    "uniqueItems": True,
                                    "items": {"type": "string"},
                                },
                                "query_terms": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": 12,
                                    "uniqueItems": True,
                                    "items": {
                                        "type": "string",
                                        "minLength": 1,
                                        "maxLength": 80,
                                    },
                                },
                                "lookback_days": {
                                    "type": ["integer", "null"],
                                    "minimum": 1,
                                },
                                "comparison_requirement": {
                                    "type": ["string", "null"],
                                    "minLength": 1,
                                    "maxLength": 240,
                                },
                                "required_source_groups": {
                                    "type": "array",
                                    "uniqueItems": True,
                                    "items": {
                                        "type": "array",
                                        "minItems": 1,
                                        "uniqueItems": True,
                                        "items": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                    },
                                },
                                "minimum_distinct_periods": {
                                    "type": ["integer", "null"],
                                    "minimum": 1,
                                },
                                "minimum_period_span_days": {
                                    "type": ["integer", "null"],
                                    "minimum": 1,
                                },
                                "minimum_observations": {
                                    "type": ["integer", "null"],
                                    "minimum": 1,
                                },
                            },
                            "additionalProperties": False,
                        },
                        "evidence_policy": {
                            "const": {
                                "require_source": True,
                                "require_timestamp": True,
                                "require_exact_span": True,
                            }
                        },
                        "parameters": {"type": "object"},
                    },
                },
                "skill": {"type": ["string", "null"]},
                "tests": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["name", "as_of", "expected", "documents"],
                        "properties": {
                            "name": {"type": "string"},
                            "as_of": {
                                "type": "string",
                                "description": "timezone-aware ISO-8601 timestamp",
                            },
                            "company_id": {"type": "string"},
                            "expected": {
                                "enum": [
                                    "positive",
                                    "neutral",
                                    "negative",
                                    "unavailable",
                                ]
                            },
                            "documents": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "required": [
                                        "document_id",
                                        "source_type",
                                        "published_at",
                                        "available_at",
                                        "content",
                                    ],
                                },
                            },
                        },
                    },
                },
            },
            "constraints": [
                "deterministic execution cannot include skill",
                "LLM execution requires non-empty skill",
                "fixture source_type must be declared by raw_retrieval",
            ],
        }
        if clone:
            schema["required"] = ["signal_ref", "spec", "tests"]
            schema["properties"] = {
                "signal_ref": {"type": "string", "description": "exact stable ref"},
                **schema["properties"],
            }
            schema["properties"]["spec"]["properties"]["raw_retrieval"].pop(
                "required"
            )
            schema["properties"]["tests"]["items"]["properties"]["documents"][
                "items"
            ]["required"] = ["source_type", "available_at", "content"]
            schema["constraints"] = [
                *schema["constraints"],
                "spec must preserve signal_id, category, description, evidence policy, execution type, and deterministic function",
                "spec.version must equal stable version plus one",
                "tests must copy vnext_template.tests byte-for-byte",
            ]
        return schema

    def _stage_from_tool(
        self,
        *,
        spec: Mapping[str, Any],
        skill: str | None,
        tests: Iterable[Mapping[str, Any]],
        origin: str,
        collected: list[str],
    ) -> str:
        candidate = self._candidate_spec_from_tool(spec)
        if origin == "mining" or origin.startswith("mining:"):
            try:
                stable = self.registry.latest_spec(candidate.signal_id)
            except ValidationError:
                stable = None
            if stable is not None:
                raise ValidationError(
                    "mined candidate duplicates stable Signal identity "
                    f"{stable.ref}; use the Update Agent for vNext"
                )
        signal_ref = self.registry.stage_candidate(
            candidate,
            skill=skill,
            tests=tests,
            origin=origin,
        )
        collected.append(signal_ref)
        return signal_ref

    @staticmethod
    def _candidate_spec_from_tool(spec: Mapping[str, Any]) -> SignalSpec:
        return candidate_signal_spec_from_dict(spec)

    def _run_signal_tests_tool(self, signal_ref: str) -> dict[str, Any]:
        spec, skill = self.registry.load_candidate(str(signal_ref))
        validation = self.validator.validate(
            spec,
            skill=skill,
            tests=self.registry.load_candidate_tests(str(signal_ref)),
        )
        return {
            "signal_ref": signal_ref,
            "accepted": validation.accepted,
            "reasons": list(validation.reasons),
        }


@dataclass(frozen=True)
class DualLoopResult:
    """One finite fast-loop group followed by one Signal slow loop."""

    plan_rounds: tuple[PlanRoundResult, ...]
    signal_evolution: SlowLoopResult


class DualLoopEvolutionEngine:
    """Run a finite Plan group, then commit one validated Signal transition."""

    def __init__(
        self,
        *,
        plan_engine: PlanEvolutionEngine,
        signal_engine: SignalEvolutionEngine,
        signal_registry: SignalRegistry,
        dataset: EvolutionDataset,
        plan_rounds_per_signal_cycle: int = 5,
        cycle_mode: str = "fast_then_slow",
        on_progress: ProgressCallback | None = None,
    ) -> None:
        if cycle_mode not in {"fast_then_slow", "slow_bootstrap", "slow_only"}:
            raise ValidationError("dual-loop cycle mode is invalid")
        if (
            (cycle_mode == "fast_then_slow" and plan_rounds_per_signal_cycle < 1)
            or (
                cycle_mode in {"slow_bootstrap", "slow_only"}
                and plan_rounds_per_signal_cycle != 0
            )
        ):
            raise ValidationError("dual-loop mode and Fast-round target conflict")
        self.plan_engine = plan_engine
        self.signal_engine = signal_engine
        self.signal_registry = signal_registry
        self.dataset = dataset
        self.plan_rounds_per_signal_cycle = plan_rounds_per_signal_cycle
        self.cycle_mode = cycle_mode
        self.on_progress = on_progress

    def run_cycle(
        self,
        *,
        cycle_id: int,
        completed_plan_rounds: int = 0,
    ) -> DualLoopResult:
        """Resume remaining Fast rounds, then automatically promote Slow output."""

        if not 0 <= completed_plan_rounds <= self.plan_rounds_per_signal_cycle:
            raise ValidationError("completed Fast-round count is outside cycle target")

        staged_validation = self.signal_engine.workspace.staged_slow_validation(cycle_id)
        if staged_validation is not None and (
            completed_plan_rounds != self.plan_rounds_per_signal_cycle
        ):
            raise ValidationError("staged Slow validation exists before Fast completion")
        learning_round_cutoff = (
            self.plan_engine.workspace.last_completed_round - completed_plan_rounds
        )
        if learning_round_cutoff < 0:
            raise ValidationError("Fast-loop learning cutoff cannot be negative")
        snapshot = (
            None
            if staged_validation is not None
            else self.signal_registry.freeze(
                learning_round_cutoff=learning_round_cutoff
            )
        )
        rounds: list[PlanRoundResult] = []
        if self.cycle_mode == "fast_then_slow":
            _emit_progress(
                self.on_progress,
                "fast_loop_started",
                cycle_mode=self.cycle_mode,
                completed_plan_rounds=completed_plan_rounds,
                target_plan_rounds=self.plan_rounds_per_signal_cycle,
                signal_registry_hash=(
                    str(staged_validation["input_registry_hash"])
                    if staged_validation is not None
                    else snapshot.registry_hash
                ),
            )
        if snapshot is None and completed_plan_rounds < self.plan_rounds_per_signal_cycle:
            raise ValidationError("Fast-loop resume requires an input Signal snapshot")
        for _ in range(
            completed_plan_rounds,
            self.plan_rounds_per_signal_cycle,
        ):
            round_id = self.plan_engine.workspace.last_completed_round + 1
            rounds.append(
                self.plan_engine.run_round(
                    round_id=round_id,
                    validation_cases=self.dataset.evolution_validation,
                    anchor_cases=self.dataset.anchor,
                    signal_snapshot=snapshot,  # type: ignore[arg-type]
                )
            )
        if snapshot is not None and self.signal_registry.version != snapshot.version:
            raise ValidationError("stable Signal definitions changed during fast loop")
        _emit_progress(
            self.on_progress,
            "slow_loop_started",
            cycle_mode=self.cycle_mode,
            completed_plan_rounds=self.plan_rounds_per_signal_cycle,
            target_plan_rounds=self.plan_rounds_per_signal_cycle,
        )
        signal_result = self.signal_engine.run_cycle(
            cycle_id=cycle_id,
            input_snapshot=snapshot,
        )
        _emit_progress(
            self.on_progress,
            "slow_loop_completed",
            mined_candidates=list(signal_result.mined_candidates),
            updated_candidates=list(signal_result.updated_candidates),
            validated_candidates=dict(signal_result.validated_candidates),
            promoted=list(signal_result.promoted),
            rejected={
                ref: list(reasons)
                for ref, reasons in signal_result.rejected.items()
            },
            input_registry_version=signal_result.input_registry_version,
            input_registry_hash=signal_result.input_registry_hash,
            output_registry_version=signal_result.output_registry_version,
            output_registry_hash=signal_result.output_registry_hash,
            new_candidate_count=signal_result.new_candidate_count,
            new_validated_signal_count=signal_result.new_validated_signal_count,
            new_promoted_signal_count=signal_result.new_promoted_signal_count,
            updated_signal_count=signal_result.updated_signal_count,
            signal_goal_status=signal_result.signal_goal_status,
        )
        return DualLoopResult(
            plan_rounds=tuple(rounds),
            signal_evolution=signal_result,
        )
