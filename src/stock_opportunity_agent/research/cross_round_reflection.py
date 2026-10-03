"""Pure, source-bound retrospective same-case observations and comparisons."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError


def prediction_observation(
    trajectory: Mapping[str, Any], *, case_reflection: Mapping[str, Any],
    plan_hash: str, origin_contract_hash: str, record_hash: str,
    locator: str, prediction_semantics_hash: str,
) -> dict[str, Any]:
    """Project one approved committed trajectory without exposing issuer identity."""

    value = {
        "schema_version": "prediction-observation-v1",
        "case_key": "comparison_case:" + canonical_json_hash({
            "issuer": trajectory["company_id"],
            "prediction_time": trajectory["prediction_time"],
            "prediction_semantics_hash": prediction_semantics_hash,
        }),
        "prediction_time": trajectory["prediction_time"],
        "outcome_contract_hash": canonical_json_hash(trajectory["ground_truth"]),
        "source": {"origin_contract_hash": origin_contract_hash,
                   "record_hash": record_hash, "json_locator": locator,
                   "trajectory_hash": canonical_json_hash(trajectory)},
        "plan_hash": plan_hash,
        "canonical_context_hash": canonical_json_hash(trajectory.get("final_context", {})),
        "prediction": deepcopy(dict(trajectory["prediction"])),
        "technical_exclusion": bool(case_reflection.get("technical_exclusion")),
        "case_reflection": deepcopy(dict(case_reflection)),
    }
    return validate_prediction_observation({
        **value, "observation_ref": "prediction_observation:" + canonical_json_hash(value),
    })


def validate_prediction_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Reject malformed or edited frozen observation derivatives on every read."""

    if not isinstance(value, Mapping):
        raise ValidationError("prediction observation must be an object")
    row = deepcopy(dict(value))
    ref = row.pop("observation_ref", None)
    fields = {"schema_version", "case_key", "prediction_time", "outcome_contract_hash",
              "source", "plan_hash", "canonical_context_hash", "prediction",
              "technical_exclusion", "case_reflection"}
    if (set(row) != fields or row.get("schema_version") != "prediction-observation-v1"
        or ref != "prediction_observation:" + canonical_json_hash(row)
        or any(not isinstance(row.get(name), str) or not row[name] for name in
               ("case_key", "prediction_time", "outcome_contract_hash", "plan_hash", "canonical_context_hash"))
        or not isinstance(row.get("source"), Mapping)
        or set(row["source"]) != {"origin_contract_hash", "record_hash", "json_locator", "trajectory_hash"}
        or any(not isinstance(item, str) or not item for item in row["source"].values())
        or not isinstance(row.get("case_reflection"), Mapping)
        or type(row.get("technical_exclusion")) is not bool
        or not isinstance(row.get("prediction"), Mapping)
        or type(row["prediction"].get("is_surge")) is not bool):
        raise ValidationError("prediction observation identity or shape is invalid")
    return {**row, "observation_ref": ref}


def prediction_comparisons(observations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Compare adjacent immutable same-case observations in approved commit order.

    Input equality concerns canonical artifacts only. It cannot certify equal
    provider requests, technically correct semantics, or a model-only cause.
    """

    previous: dict[tuple[str, str], dict[str, Any]] = {}
    seen: set[str] = set()
    comparisons = []
    for raw in observations:
        right = validate_prediction_observation(raw)
        if right["observation_ref"] in seen:
            continue
        seen.add(right["observation_ref"])
        key = (right["case_key"], right["outcome_contract_hash"])
        left = previous.get(key)
        previous[key] = right
        if left is None:
            continue
        changes = [name for name in ("is_surge", "magnitude")
                   if left["prediction"].get(name) != right["prediction"].get(name)]
        technical = left["technical_exclusion"] or right["technical_exclusion"]
        if not changes and left["technical_exclusion"] == right["technical_exclusion"]:
            continue
        classification = (
            "technical_execution_change" if technical else
            "changed_canonical_input" if any(left[name] != right[name] for name in
                ("canonical_context_hash", "plan_hash")) else
            "equal_canonical_input_wire_unverified"
        )
        value = {
            "schema_version": "prediction-comparison-v1",
            "case_key": right["case_key"], "changed_outputs": changes,
            "classification": classification, "cause_status": "unestablished",
            "research_attribution_allowed": not technical,
            "left": left, "right": right,
            "limitations": ["Canonical hashes do not establish equal provider prompts/model parameters.",
                            "A reversal and outcome correctness do not establish a causal explanation."],
        }
        if technical:
            value["limitations"].append("Technical exclusion cannot support economic research attribution.")
        comparisons.append({**value, "comparison_ref": "prediction_comparison:" + canonical_json_hash(value)})
    return comparisons


def validate_prediction_comparison(value: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a pair's facts instead of accepting supplied classifications."""

    if not isinstance(value, Mapping):
        raise ValidationError("prediction comparison must be an object")
    rows = prediction_comparisons((value.get("left", {}), value.get("right", {})))
    if len(rows) != 1 or rows[0] != dict(value):
        raise ValidationError("prediction comparison differs from its immutable observations")
    return rows[0]


def comparison_original(value: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve a nested imported feedback wrapper without changing the original."""

    while value.get("schema_version") != "prediction-comparison-v1":
        artifact = value.get("artifact")
        if not isinstance(artifact, Mapping):
            raise ValidationError("comparison feedback lacks its paired original")
        value = artifact
    return validate_prediction_comparison(value)
