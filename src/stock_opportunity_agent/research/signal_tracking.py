"""Committed-use observations, separate from technical admission and benefit."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    SignalLearningEvent, SignalRegistry, SignalTargetEvaluation, SignalValue,
)
from stock_opportunity_agent.research.research_targets import (
    active_research_targets, project_magnitude_ge3_group, MAGNITUDE_GE3_TARGET_ID,
)


def _protocol(target_id: str) -> str:
    if target_id == "surge_direction":
        contract_hash = canonical_json_hash({"target": target_id, "outcome": "canonical_is_surge"})
    else:
        target = next((item for item in active_research_targets() if item.target_id == target_id), None)
        if target is None:
            raise ValidationError("unapproved target in committed Signal tracking")
        contract_hash = target.identity_hash()
    return f"committed-use-observation-v1:{contract_hash}"


def _targets(registry: SignalRegistry, signal_ref: str) -> tuple[str, ...]:
    status = registry.load_research_status(signal_ref)
    return tuple(status.get("research_targets", ("surge_direction",)))


def _evaluation(event: SignalLearningEvent, target_id: str, created_at: str) -> SignalTargetEvaluation:
    protocol = _protocol(target_id)
    result = "insufficient_evidence" if event.result_value is SignalValue.UNAVAILABLE else "inconclusive"
    key = canonical_json_hash({
        "signal_ref": event.signal_ref, "observation_key": event.observation_key,
        "target_id": target_id, "evaluation_protocol": protocol,
        "state": event.result_value.value, "coverage": event.coverage.value,
        "is_surge": event.is_surge, "realized_max_multiple": event.realized_max_multiple,
    })
    return SignalTargetEvaluation(evaluation_id=key, signal_ref=event.signal_ref,
        target_id=target_id, evaluation_protocol=protocol, observation_key=event.observation_key,
        result=result, created_at=created_at)


def record_committed_signal_use(registry: SignalRegistry, events: Iterable[SignalLearningEvent]) -> int:
    """Persist committed/imported learning, then idempotent target use derivatives.

    Only call with pointer-reachable or hash-verified committed events. For example,
    a Fast coordinator invokes this after its round commit, never while staging.
    """

    materialized = tuple(events)
    rows: dict[str, SignalTargetEvaluation] = {}
    known: dict[str, SignalTargetEvaluation] = {}
    targets: dict[str, tuple[str, ...]] = {}
    for ref in sorted({event.signal_ref for event in materialized}):
        targets[ref] = _targets(registry, ref)
        known.update({row.evaluation_id: row for row in registry.load_target_evaluations(ref)})
    created_at = datetime.now(timezone.utc).isoformat()
    for event in materialized:
        for target_id in targets[event.signal_ref]:
            row = _evaluation(event, target_id, created_at)
            prior = known.get(row.evaluation_id) or rows.get(row.evaluation_id)
            if prior is not None:
                row = _evaluation(event, target_id, prior.created_at)
            rows[row.evaluation_id] = row
    registry.record_learning_events(materialized)
    return registry.record_target_evaluations(rows.values())


def target_use_profiles(registry: SignalRegistry, signal_ref: str, *, round_cutoff: int) -> dict[str, Any]:
    """Return bounded source-bound selected-use associations, never effect support."""

    if round_cutoff < 0:
        raise ValidationError("target tracking round cutoff cannot be negative")
    events = tuple(event for event in registry.load_learning_events(signal_ref) if event.round_id <= round_cutoff)
    evaluations = {row.evaluation_id: row for row in registry.load_target_evaluations(signal_ref)}
    profiles = {}
    for target_id in _targets(registry, signal_ref):
        selected = []
        sources = {}
        for event in events:
            expected = _evaluation(event, target_id, "identity-only")
            row = evaluations.get(expected.evaluation_id)
            if row is None:
                continue
            if row.to_dict() != _evaluation(event, target_id, row.created_at).to_dict():
                raise ValidationError("target use record differs from its learning source")
            selected.append(event)
            sources[row.evaluation_id] = row.to_dict()
        if not selected:
            continue
        observations: dict[str, SignalLearningEvent] = {}
        disputed: set[str] = set()
        for event in selected:
            prior = observations.get(event.observation_key)
            if prior is not None:
                if (prior.case_id, prior.company_id, prior.prediction_time, prior.document_fingerprint,
                    prior.is_surge, prior.realized_max_multiple) != (event.case_id, event.company_id,
                    event.prediction_time, event.document_fingerprint, event.is_surge, event.realized_max_multiple):
                    raise ValidationError("conflicting target use outcome/source")
                if (prior.result_value, prior.coverage) != (event.result_value, event.coverage):
                    disputed.add(event.observation_key)
            observations.setdefault(event.observation_key, event)
        groups = ("surge", "non_surge") if target_id == "surge_direction" else ("ge3_high", "ge3_low")
        matrix = {state.value: {group: 0 for group in groups} for state in SignalValue}
        multiples: dict[str, list[float]] = {state.value: [] for state in SignalValue}
        outside = unavailable = eligible = 0
        for key, event in observations.items():
            if key in disputed:
                continue
            if target_id == "surge_direction":
                group = "surge" if event.is_surge else "non_surge"
            elif target_id == MAGNITUDE_GE3_TARGET_ID:
                group = project_magnitude_ge3_group(event.realized_max_multiple)
            else:
                raise ValidationError("unsupported target use projection")
            unavailable += int(event.result_value is SignalValue.UNAVAILABLE)
            if group is None:
                outside += 1
                continue
            eligible += 1
            matrix[event.result_value.value][group] += 1
            if event.result_value is not SignalValue.UNAVAILABLE:
                multiples[event.result_value.value].append(event.realized_max_multiple)
        profiles[target_id] = {
            "schema_version": "signal-target-use-profile-v1", "signal_ref": signal_ref,
            "target_id": target_id, "evaluation_protocol": _protocol(target_id),
            "round_cutoff": round_cutoff, "effect_status": "unverified",
            "selection_events": len(selected), "physical_observations": len(observations),
            "unique_issuers": len({event.company_id for event in observations.values()}),
            "disputed_observations": len(disputed), "eligible_observations": eligible,
            "outside_population": outside, "unavailable_observations": unavailable,
            "state_outcome_matrix": matrix,
            "mean_realized_multiple_by_state": {state: sum(values) / len(values) if values else None for state, values in multiples.items()},
            "source_hash": canonical_json_hash({"events": [event.to_dict() for event in sorted(selected, key=lambda event: event.event_id)], "evaluations": sources}),
            "limitations": ["selected-use association, not independent causal benefit", "technical execution failures excluded from research effect counts"],
        }
    return profiles
