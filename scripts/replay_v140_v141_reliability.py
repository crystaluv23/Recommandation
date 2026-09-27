#!/usr/bin/env python3
"""Zero-network replay of the V140/V141 reliability failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_core import (
    ExecutionTrajectory,
    ResearchState,
    research_jev_calibration_diagnostics,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _research_state_evidence_grounding_fallback,
)
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs/cold_start/evolution"
V140 = RUNS_ROOT / "information-evolution-jev-dual-self-evolution-20260926-v140"
V141 = RUNS_ROOT / "information-evolution-jev-dual-self-evolution-20260926-v141"
NO_PROGRESS_REQUEST = (
    "412ab062a75dc81ba848bbe7a1492da5e1e4188fd009ade97dc734f824d806b0"
)
COORDINATE_REQUEST = (
    "b00b35debe51918e2438281ae239cbcc5fd3e14eff43ca96753f540a2d7c8f7a"
)
MIXED_REQUEST = (
    "fbdabc07a3c7caf6dfbc30dbc6ac6c94b48ba6b71893bed833166fa6ce79d867"
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validation_feedback(path: Path) -> dict[str, Any]:
    request = _read_json(path)["request"]
    payload = json.loads(request["messages"][-1]["content"])
    return dict(payload["validation_feedback"])


def _failure_from_feedback(feedback: Mapping[str, Any]) -> StructuredValidationError:
    authority_keys = {
        "issue_code",
        "instruction",
        "must_change_paths",
        "must_change_any_of_paths",
        "permitted_dependency_paths",
        "allowed_repairs",
        "retryability",
        "severity",
        "source_refs",
        "obligation_index",
    }
    issues = []
    for raw in feedback["obligations"]:
        obligation = dict(raw)
        issues.append(
            ValidationIssue(
                code=str(obligation["issue_code"]),
                message=str(obligation["instruction"]),
                paths=tuple(obligation["must_change_paths"]),
                dependent_paths=tuple(
                    obligation.get("permitted_dependency_paths", ())
                ),
                allowed_repairs=tuple(obligation["allowed_repairs"]),
                retryability=str(obligation["retryability"]),
                severity=str(obligation["severity"]),
                source_refs=tuple(obligation.get("source_refs", ())),
                repair_context={
                    key: value
                    for key, value in obligation.items()
                    if key not in authority_keys
                },
            )
        )
    return StructuredValidationError(issues)


def _replay_fallback(request_hash: str) -> dict[str, Any]:
    feedback = _validation_feedback(V141 / "requests" / f"{request_hash}.json")
    invalid = dict(feedback["invalid_output"])
    fallback = _research_state_evidence_grounding_fallback(
        invalid,
        _failure_from_feedback(feedback),
    )
    if fallback is None:
        raise AssertionError(f"fallback did not repair request {request_hash}")
    repaired, actions = fallback
    ResearchState.from_dict(repaired)
    return {
        "request_hash": request_hash,
        "before_evidence_count": len(invalid["supporting_evidence"]),
        "after_evidence_count": len(repaired["supporting_evidence"]),
        "removed_paths": list(actions["removed_paths"]),
        "typed_state_reload": True,
    }


def _jev_replay(run_root: Path) -> dict[str, Any]:
    trajectory_root = run_root / "experiments/trajectories/plan_r0001_c02"
    trajectories = []
    for path in sorted(trajectory_root.glob("*.json")):
        if path.name.endswith((".failure.json", ".abstain.json")):
            continue
        payload = _read_json(path)
        if isinstance(payload.get("trajectory"), Mapping):
            trajectories.append(ExecutionTrajectory.from_dict(payload["trajectory"]))
    diagnostics = research_jev_calibration_diagnostics(trajectories)
    if diagnostics is None:
        raise AssertionError(f"no Jev diagnostics reconstructed from {run_root.name}")
    return {
        "trajectory_count": len(trajectories),
        "diagnostics": diagnostics,
    }


def run_replay() -> dict[str, Any]:
    """Replay persisted failures and diagnostics without model or data calls."""

    mixed_response = _read_json(
        V141 / "cache/responses" / f"{MIXED_REQUEST}.json"
    )
    candidate = mixed_response["json_output"]["candidate"]
    modality = SignalEvolutionEngine._candidate_modality(candidate)
    if modality != "mixed":
        raise AssertionError("V141 ratio candidate was not classified as mixed")
    capability_gap = SignalEvolutionEngine._candidate_capability_gap(
        candidate,
        axis_id="magnitude_ge3_v1",
        seed="discovery",
    )
    if capability_gap is None:
        raise AssertionError("V141 ratio candidate reached materialization")
    gap_ref, gap = capability_gap
    return {
        "schema_version": "v140-v141-reliability-replay-v1",
        "network_calls": 0,
        "jev": {
            "v140": _jev_replay(V140),
            "v141": _jev_replay(V141),
        },
        "correction_recovery": {
            "no_progress_frontier": _replay_fallback(NO_PROGRESS_REQUEST),
            "same_signal_coordinate_frontier": _replay_fallback(
                COORDINATE_REQUEST
            ),
        },
        "mixed_modality": {
            "request_hash": MIXED_REQUEST,
            "observable": candidate["measurement"]["observable"],
            "classification": modality,
            "capability_gap_ref": gap_ref,
            "disposition": gap["status"],
            "materialization_allowed": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_replay()
    if args.output is not None:
        atomic_write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
