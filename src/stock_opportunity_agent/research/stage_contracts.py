"""Deterministic dependency and disclosure boundaries shared by research roles.

Domain validators own output correctness. These helpers reject invalid input
construction before transport and page immutable whole entries without hiding
omissions. They never rewrite model judgments or relax evidence constraints.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Mapping, Sequence

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError, ValidationIssue

NEED_ROW_RATIONALE_CONTRACT = (
    "rationale must be a non-empty array of nonblank strings; "
    "a single reason uses a one-element array."
)

# Required top-level dependencies; each owning role validates their contents.
_STAGE_INPUTS: dict[str, tuple[str, ...]] = {
    "information_plan_propose": ("proposal_context",),
    "research_controller_initialize": ("initial_research_skill", "basic_info"),
    "signal_retrieval_cards": ("available_signal_cards", "information_needs", "research_context", "selection_caps"),
    "llm_signal_batch_execute": ("signals", "source_projection", "as_of"),
    "llm_signal_source_read": ("signal_spec", "skill", "as_of", "source_catalog", "last_read_result", "already_read_projection"),
    "llm_signal_source_read_next": ("signal_spec", "skill", "as_of", "source_catalog", "last_read_result", "already_read_projection"),
    "research_controller_reflect": ("research_state", "signal_batch", "need_transition_contract"),
    "blind_predictor_predict": ("final_context",),
    "blind_predictor_jev_explain": ("final_context",),
    "blind_predictor_posthoc_reflect": ("compact_context", "original_prediction", "revealed_ground_truth"),
    "plan_critic": ("plan", "metrics", "trajectories"),
    "round_reflect": ("records", "parent_comparisons_by_plan_id"),
    "signal_mining_reflect": ("feedback_units", "measurement_contract"),
    "slow_source_read": ("role_scope", "available_sources"),
    "mining_controller_step": ("research_axis", "label_map", "budget", "measurable_evidence_manifest",
                               "signal_catalog", "signal_catalog_disclosure", "case_refs", "case_prediction_times", "tool_contracts"),
    "mining_candidate_materialize_spec": ("candidate", "candidate_contract", "cited_evidence"),
    "mining_candidate_materialize_skill": ("candidate", "spec", "cited_evidence"),
    "mining_candidate_materialize_tests": ("candidate", "spec", "skill", "cited_evidence"),
    "signal_update_decision": ("target", "induction_cases", "candidate_contract"),
}
_BLIND_STAGES = frozenset({
    "research_controller_initialize", "signal_retrieval_cards",
    "llm_signal_batch_execute", "research_controller_reflect",
    "llm_signal_source_read", "llm_signal_source_read_next",
    "blind_predictor_predict", "blind_predictor_jev_explain",
})


def json_bytes(value: Any) -> int:
    """Measure canonical compact UTF-8 JSON bytes, not estimated tokens."""
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def read_whole_entries(
    entries: Mapping[str, Mapping[str, Any]], item_refs: Any, *, max_bytes: int,
) -> dict[str, Any]:
    """Select known complete originals within a byte cap, without clipping.

    Example: ``read_whole_entries({'n1': row}, ['n1'], max_bytes=16000)``.
    Duplicate supplied refs select one original; unknown refs fail closed.
    """
    if (not isinstance(item_refs, list) or not item_refs
        or any(not isinstance(ref, str) or ref not in entries for ref in item_refs)):
        raise ValidationError("whole read requires non-empty known item_refs")
    refs = list(dict.fromkeys(item_refs))
    selected = [deepcopy(dict(entries[ref])) for ref in refs]
    size = json_bytes(selected)
    if size > max_bytes:
        raise ValidationError(f"whole read requires {size} bytes, exceeding {max_bytes}; select fewer complete entries")
    return {"items": selected, "included_refs": refs, "read_bytes": size,
            "read_byte_limit": max_bytes,
            "counts": {"available": len(entries), "included": len(refs)}}


def budget_claim_issues(
    text_rows: Sequence[tuple[str, str]], budget: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Check explicit current remaining-action facts against runtime counters.

    Example: a claim of ``heavy_remaining=0`` conflicts with
    ``{'heavy_remaining': 26}``; a conditional future cost is not inferred.
    """

    issues: list[ValidationIssue] = []
    for key, remaining in budget.items():
        if not key.endswith("_remaining") or type(remaining) is not int:
            continue
        dimension = re.escape(key.removesuffix("_remaining"))
        named = re.compile(
            rf"\b{dimension}[ _-]+remaining\s*(?:=|:|is|are)\s*(?P<count>[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?!\w|\.\d)", re.I,
        )
        literal_count = re.compile(
            rf"\b{dimension}\s+(?:action\s+)?budget\s*(?:=|:|is|are)\s*(?P<count>[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?!\w|\.\d)", re.I,
        )
        available = re.compile(
            rf"\b{dimension}\s+(?:action\s+)?budget\s+(?:is|remains)\s+(?:positive|available)\b", re.I,
        )
        exhausted = re.compile(
            rf"\b(?:no|zero)\s+(?:(?:remaining|admissible|available)\s+)?{dimension}\s+(?:action\s+)?budget\b"
            rf"(?=\s*(?:$|[.;,!?]|(?:for|left|remaining|available|remains|and)\b|(?:is|was)\s+(?:left|remaining|available)\b))"
            rf"|\b(?:out\s+of|exhausted|depleted)\s+(?:the\s+)?{dimension}\s+budget\b"
            rf"|\b{dimension}\s+(?:action\s+)?budget\s+(?:(?:is|was|has\s+been)\s+)?(?:exhausted|depleted|used\s+up)\b", re.I,
        )
        for path, text in text_rows:
            found = False
            for pattern in (named, literal_count, exhausted, available):
                for match in pattern.finditer(text):
                    prefix = re.split(r"[.;!?]", text[:match.start()])[-1][-80:]
                    if re.search(r"\b(?:if|when|unless|assuming|suppose|hypothetical|next|future|previous|prior|not|never|false|incorrect|denied)\b", prefix, re.I):
                        continue
                    invalid = (float(match.group("count")) != remaining
                               if pattern in (named, literal_count) else
                               remaining <= 0 if pattern is available else remaining > 0)
                    if invalid:
                        issues.append(ValidationIssue(
                            code="runtime_budget_claim_invalid", paths=(path,),
                            message=f"{path}: current runtime {key}={remaining}; correct or remove the conflicting budget claim without changing the runtime counter or inventing a research reason.",
                            repair_context={"budget": dict(budget), "counter": key,
                                            "matched_text": match.group(), "source": "runtime_budget"},
                        ))
                        found = True
                        break
                if found:
                    break
    return issues


def validate_stage_input(
    stage: str, payload: Mapping[str, Any], *, allow_outcomes: bool,
) -> dict[str, Any]:
    """Validate required dependencies and return local request audit metadata.

    Example: ``validate_stage_input('blind_predictor_predict',
    {'final_context': context}, allow_outcomes=False)``. Unknown extension
    stages are labeled unregistered; their owning interface remains responsible.
    """
    mechanics = stage.endswith("_patch_mechanics_correction")
    base = stage.removesuffix("_patch_mechanics_correction") if mechanics else stage.removesuffix("_correction")
    required = _STAGE_INPUTS.get(base)
    if mechanics:
        required = ("invalid_patch", "original_patch_base", "original_patch_contract",
                    "patch_mechanics_repair", "output_patch_contract")
        view = payload.get("patch_mechanics_repair")
        if not isinstance(view, Mapping) or view.get("schema_version") != "state-patch-mechanics-repair-v1":
            raise ValidationError("patch mechanics correction requires its runtime schema")
    if required is not None:
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValidationError(f"{stage} input dependency missing: {missing}")
    if base in _BLIND_STAGES and allow_outcomes:
        raise ValidationError(f"{stage} prediction-time input cannot allow outcomes")
    return {
        "schema_version": "research-stage-input-v1",
        "stage": base,
        "registered": base in _STAGE_INPUTS,
        "required_fields": list(required or ()),
        "payload_hash": canonical_json_hash(dict(payload)),
        "payload_utf8_bytes": json_bytes(payload),
        "allow_outcomes": allow_outcomes,
        **({"phase": "patch_mechanics"} if mechanics else {}),
    }


def bounded_entry_page(
    entries: Sequence[Mapping[str, Any]], *, cursor: int = 0,
    max_items: int = 12, max_bytes: int = 8_000,
) -> dict[str, Any]:
    """Page whole entries with explicit omissions and an oversized-entry escape.

    An entry exceeding the byte limit is disclosed by index and read size;
    pagination advances over it so a large first item cannot hide all later
    items. Consumers retain originals and supply their own stable-ref resolver.
    """
    if type(cursor) is not int or not 0 <= cursor <= len(entries):
        raise ValidationError("entry page cursor is invalid")
    if type(max_items) is not int or max_items < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise ValidationError("entry page limits must be positive integers")
    selected: list[dict[str, Any]] = []
    oversized: list[dict[str, int]] = []
    position = cursor
    while position < len(entries) and len(selected) + len(oversized) < max_items:
        row = dict(entries[position])
        required = json_bytes([row])
        if required > max_bytes:
            oversized.append({"index": position, "required_bytes": required})
            position += 1
            continue
        if json_bytes([*selected, row]) > max_bytes:
            break
        selected.append(row)
        position += 1
    return {
        "items": selected,
        "counts": {
            "available": len(entries), "included": len(selected),
            "omitted_before": cursor,
            "omitted_after": len(entries) - position,
            "oversized": len(oversized),
        },
        "cursor": cursor,
        "next_cursor": position if position < len(entries) else None,
        "oversized_entries": oversized,
        "max_entry_bytes": max_bytes,
        "selection_is_exhaustive": cursor == 0 and position == len(entries) and not oversized,
    }
