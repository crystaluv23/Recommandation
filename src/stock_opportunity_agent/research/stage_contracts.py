"""Deterministic dependency and disclosure boundaries shared by research roles.

Domain validators own output correctness. These helpers reject invalid input
construction before transport and page immutable whole entries without hiding
omissions. They never rewrite model judgments or relax evidence constraints.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError

# Required top-level dependencies; each owning role validates their contents.
_STAGE_INPUTS: dict[str, tuple[str, ...]] = {
    "information_plan_propose": ("proposal_context",),
    "research_controller_initialize": ("initial_research_skill", "basic_info"),
    "signal_retrieval_cards": ("available_signal_cards", "information_needs", "research_context", "selection_caps"),
    "llm_signal_batch_execute": ("signals", "source_projection", "as_of"),
    "research_controller_reflect": ("research_state", "signal_batch", "need_transition_contract"),
    "blind_predictor_predict": ("final_context",),
    "blind_predictor_jev_explain": ("final_context",),
    "blind_predictor_posthoc_reflect": ("compact_context", "original_prediction", "revealed_ground_truth"),
    "plan_critic": ("plan", "metrics", "trajectories"),
    "round_reflect": ("records", "parent_comparisons_by_plan_id"),
    "signal_mining_reflect": ("feedback_units", "measurement_contract"),
    "slow_source_read": ("role_scope", "available_sources"),
    "mining_controller_step": ("research_axis", "label_map", "budget", "measurable_evidence_manifest", "signal_catalog"),
    "mining_candidate_materialize_spec": ("candidate", "candidate_contract", "cited_evidence"),
    "mining_candidate_materialize_skill": ("candidate", "spec", "cited_evidence"),
    "mining_candidate_materialize_tests": ("candidate", "spec", "skill", "cited_evidence"),
    "signal_update_decision": ("target", "induction_cases", "candidate_contract"),
}
_BLIND_STAGES = frozenset({
    "research_controller_initialize", "signal_retrieval_cards",
    "llm_signal_batch_execute", "research_controller_reflect",
    "blind_predictor_predict", "blind_predictor_jev_explain",
})


def json_bytes(value: Any) -> int:
    """Measure canonical compact UTF-8 JSON bytes, not estimated tokens."""
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def validate_stage_input(
    stage: str, payload: Mapping[str, Any], *, allow_outcomes: bool,
) -> dict[str, Any]:
    """Validate required dependencies and return local request audit metadata.

    Example: ``validate_stage_input('blind_predictor_predict',
    {'final_context': context}, allow_outcomes=False)``. Unknown extension
    stages are labeled unregistered; their owning interface remains responsible.
    """
    base = stage.removesuffix("_correction")
    required = _STAGE_INPUTS.get(base)
    if required is not None:
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValidationError(f"{stage} input dependency missing: {missing}")
    if base in _BLIND_STAGES and allow_outcomes:
        raise ValidationError(f"{stage} prediction-time input cannot allow outcomes")
    return {
        "schema_version": "research-stage-input-v1",
        "stage": base,
        "registered": required is not None,
        "required_fields": list(required or ()),
        "payload_hash": canonical_json_hash(dict(payload)),
        "payload_utf8_bytes": json_bytes(payload),
        "allow_outcomes": allow_outcomes,
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
