#!/usr/bin/env python3
"""Zero-call replay acceptance for the V130/V138 evolution regression.

The replay reads immutable run artifacts only. It never opens the Locked Test,
contacts a model/provider, mutates a run workspace, or treats a counterfactual
score as an observed live result.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.research.evolution_control import (
    load_approved_development_dataset,
)
from stock_opportunity_agent.research.evolution_core import (
    PlanMetaMemory,
    PlanRecord,
    ResearchState,
    RoundMetaEntry,
    is_technical_exclusion_trajectory,
    research_magnitude_diagnostics,
    score_predictions,
    technical_completion_diagnostics,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _scoped_correction_drift_paths,
)
from stock_opportunity_agent.research.evolution_research_validation import (
    _validate_signal_claim_quantities,
)
from stock_opportunity_agent.research.research_targets import (
    MAGNITUDE_GE3_CONTRACT,
    build_target_group_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V130 = PROJECT_ROOT / (
    "runs/cold_start/evolution/"
    "information-evolution-dual-self-evolution-20260920-v130"
)
DEFAULT_V138 = PROJECT_ROOT / (
    "runs/cold_start/evolution/"
    "information-evolution-dual-self-evolution-20260922-v138"
)
DEFAULT_DATASET = PROJECT_ROOT / (
    "runs/cold_start/evolution/"
    "full-market-expanded-2025plus-v13-approved-inputs/"
    "expanded_dataset_proposal/dataset_manifest.approved.json"
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _committed_record(workspace: Path, round_id: int = 1) -> PlanRecord:
    checkpoint = _read(
        workspace / "experiments" / f"round-{round_id:04d}" / "checkpoint.json"
    )
    plan_ids = checkpoint.get("plan_ids")
    if not isinstance(plan_ids, list) or len(plan_ids) != 1:
        raise ValueError("replay expects one committed Plan in the selected round")
    record = _read(workspace / "plans" / str(plan_ids[0]) / "record.json")
    return PlanRecord.from_dict(record)


def _metric_report(record: PlanRecord) -> dict[str, Any]:
    recomputed = score_predictions(record.trajectories)
    if recomputed.to_dict() != record.metrics.to_dict():
        raise ValueError(f"stored metric mismatch for {record.plan_id}")
    return {
        "plan_id": record.plan_id,
        "metrics": recomputed.to_dict(),
        "technical_completion": technical_completion_diagnostics(
            record.trajectories
        ),
        "research_magnitude": research_magnitude_diagnostics(
            record.trajectories
        ),
    }


def _counterfactual_recovery(v130: PlanRecord, v138: PlanRecord) -> dict[str, Any]:
    """Reuse V130 predictions only where V138 has a technical abstention."""

    baseline_by_case = {row.case_id: row for row in v130.trajectories}
    recovered = []
    replaced_case_ids = []
    for row in v138.trajectories:
        if is_technical_exclusion_trajectory(row) and row.case_id in baseline_by_case:
            baseline = baseline_by_case[row.case_id]
            recovered.append(replace(row, prediction=baseline.prediction))
            replaced_case_ids.append(row.case_id)
        else:
            recovered.append(row)
    return {
        "interpretation": (
            "diagnostic counterfactual only; not an observed post-fix score"
        ),
        "replaced_technical_case_ids": sorted(replaced_case_ids),
        "metrics": score_predictions(recovered).to_dict(),
    }


def _signal_evidence(
    payload: Mapping[str, Any],
) -> tuple[dict[str, list[tuple[str, int, str]]], dict[str, Any]]:
    available: dict[str, list[tuple[str, int, str]]] = {}
    for raw_result in payload.get("signal_batch", ()):
        if not isinstance(raw_result, Mapping):
            continue
        signal_ref = str(raw_result.get("signal_ref", ""))
        evidence = raw_result.get("evidence", {})
        if not signal_ref or not isinstance(evidence, Mapping):
            continue
        rows: list[tuple[str, int, str]] = []
        for group_name in ("supporting", "counter"):
            for raw_item in evidence.get(group_name, ()):
                if not isinstance(raw_item, Mapping):
                    continue
                if "evidence_index" not in raw_item or (
                    "model_evidence_text" not in raw_item
                ):
                    continue
                rows.append(
                    (
                        group_name,
                        int(raw_item["evidence_index"]),
                        str(raw_item["model_evidence_text"]),
                    )
                )
        available[signal_ref] = rows
    return available, {
        ref: {(group, index): text for group, index, text in rows}
        for ref, rows in available.items()
    }


def _replay_corrections(workspace: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for request_path in sorted((workspace / "requests").glob("*.json")):
        envelope = _read(request_path)
        request = envelope.get("request", {})
        if not isinstance(request, Mapping) or not str(
            request.get("stage", "")
        ).endswith("_correction"):
            continue
        messages = request.get("messages", ())
        if not isinstance(messages, list) or len(messages) < 2:
            continue
        try:
            payload = json.loads(str(messages[-1]["content"]))
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
        feedback = payload.get("validation_feedback", {})
        invalid = feedback.get("invalid_output") if isinstance(
            feedback, Mapping
        ) else None
        if not isinstance(invalid, Mapping):
            continue
        response_path = workspace / "cache" / "responses" / request_path.name
        if not response_path.is_file():
            continue
        corrected = _read(response_path).get("json_output")
        if not isinstance(corrected, Mapping):
            continue
        available, evidence_index = _signal_evidence(payload)
        try:
            state = ResearchState.from_dict(invalid)
        except Exception:
            continue
        grouped: dict[str, list[tuple[int, str]]] = {}
        for index, ref in enumerate(state.supporting_evidence):
            signal_ref = getattr(ref, "signal_ref", None)
            group = getattr(ref, "evidence_group", None)
            evidence_position = getattr(ref, "evidence_index", None)
            if signal_ref is None or group is None or evidence_position is None:
                continue
            text = evidence_index.get(str(signal_ref), {}).get(
                (str(group), int(evidence_position))
            )
            if text is not None:
                grouped.setdefault(str(ref.claim), []).append((index, text))
        issues = _validate_signal_claim_quantities(grouped, state, available)
        provenance_paths = sorted(
            {
                path
                for issue in issues
                if issue.code == "claim_quantity_not_supported"
                for path in issue.dependent_paths
                if path.endswith((".evidence_group", ".evidence_index"))
            }
        )
        old_paths = [
            *feedback.get("required_change_paths", ()),
            *feedback.get("permitted_dependency_paths", ()),
        ]
        old_drift = _scoped_correction_drift_paths(invalid, corrected, old_paths)
        repaired_paths = [*old_paths, *provenance_paths]
        new_drift = _scoped_correction_drift_paths(
            invalid, corrected, repaired_paths
        )
        newly_authorized = sorted(set(old_drift) & set(provenance_paths))
        if newly_authorized:
            rows.append(
                {
                    "request_hash": request_path.stem,
                    "stage": request.get("stage"),
                    "old_drift_paths": old_drift,
                    "current_provenance_dependency_paths": provenance_paths,
                    "newly_authorized_response_paths": newly_authorized,
                    "remaining_response_drift_paths": new_drift,
                    "full_revalidation_required": True,
                }
            )
    if not rows:
        raise ValueError("no historical correction gained provenance authorization")
    return {
        "matched_request_count": len(rows),
        "requests": rows,
    }


def _reflection_replay(workspace: Path) -> dict[str, Any]:
    meta = RoundMetaEntry.from_dict(
        _read(workspace / "meta" / "round-0001.json")
    )
    model_view = PlanMetaMemory(entries=(meta,)).archive_view()[0]
    serialized = json.dumps(model_view, sort_keys=True)
    if "technical_case_exclusion:" in serialized:
        raise ValueError("legacy synthetic technical reflection reached model view")
    technical_rows = sum(
        "technical_exclusion" in case
        for plan in model_view.get("plan_reflections", ())
        for case in plan.get("original_case_reflections", ())
    )
    proposer_rounds: list[int] = []
    local_round_one_visible = False
    for request_path in sorted((workspace / "requests").glob("*.json")):
        request = _read(request_path).get("request", {})
        if not isinstance(request, Mapping) or request.get("stage") != (
            "information_plan_propose"
        ):
            continue
        messages = request.get("messages", ())
        try:
            payload = json.loads(str(messages[-1]["content"]))
        except (IndexError, KeyError, TypeError, json.JSONDecodeError):
            continue
        context = payload.get("proposal_context", payload)
        if not isinstance(context, Mapping):
            continue
        slot = context.get("proposal_slot", {})
        round_id = int(slot.get("round_id", 0)) if isinstance(slot, Mapping) else 0
        proposer_rounds.append(round_id)
        if round_id == 2:
            meta_rows = context.get("meta_info", ())
            local_round_one_visible = any(
                isinstance(row, Mapping) and int(row.get("round_id", 0)) == 1
                for row in meta_rows
            )
    if 2 not in proposer_rounds:
        raise ValueError("round-two proposer request was not found")
    if not local_round_one_visible:
        raise ValueError("round-one reflection did not reach round-two proposer")
    return {
        "round_two_proposer_found": 2 in proposer_rounds,
        "round_one_reflection_visible_to_round_two": local_round_one_visible,
        "technical_rows_projected_as_typed_exclusions": technical_rows,
        "synthetic_research_feedback_visible": False,
    }


def _slow_modality_replay(workspace: Path) -> dict[str, Any]:
    artifact = _read(
        workspace
        / "experiments"
        / "cycles"
        / "cycle-0001"
        / "slow_loop_validation.json"
    )
    mining = dict(
        artifact["validation"]["agent_audits"]["mining_pipeline"]
    )
    seeds = [
        row for row in mining.get("seeds", ()) if isinstance(row, Mapping)
    ]
    for row in seeds:
        coverage = row.get("modality_coverage", {})
        for modality in ("structured", "narrative"):
            state = coverage.get(modality, {}) if isinstance(coverage, Mapping) else {}
            if state.get("available") and not state.get("explored"):
                raise ValueError(f"historical Slow skipped available {modality}")
    metrics = dict(mining.get("modality_metrics", {}))
    if int(metrics.get("narrative_materialization_count", 0)) < 1 or int(
        metrics.get("narrative_validation_count", 0)
    ) < 1:
        raise ValueError("historical narrative factor lifecycle was not preserved")
    return {
        "seed_modality_coverage": [
            {
                "seed": row.get("seed"),
                "coverage": row.get("modality_coverage", {}),
            }
            for row in seeds
        ],
        "narrative_candidate_refs": mining.get("narrative_candidate_refs", []),
        "modality_metrics": metrics,
    }


def _magnitude_target_replay(dataset_path: Path) -> dict[str, Any]:
    dataset = load_approved_development_dataset(dataset_path)
    cases = (*dataset.discovery, *dataset.evolution_validation)
    manifest = build_target_group_manifest(cases, MAGNITUDE_GE3_CONTRACT)
    by_id = {case.case_id: case for case in cases}
    groups = manifest["groups"]
    high_multiples = [
        by_id[case_id].ground_truth.realized_max_multiple
        for case_id, group in groups.items()
        if group == "ge3_high"
    ]
    low_multiples = [
        by_id[case_id].ground_truth.realized_max_multiple
        for case_id, group in groups.items()
        if group == "ge3_low"
    ]
    if not high_multiples or not low_multiples:
        raise ValueError("magnitude target lacks one contrast group")
    if not any(value >= 10.0 for value in high_multiples):
        raise ValueError("10x+ examples do not reach the ge3 high group")
    if not all(2.0 <= value < 3.0 for value in low_multiples):
        raise ValueError("ge3 low group is not the 2-3x population")
    return {
        "target_id": MAGNITUDE_GE3_CONTRACT.target_id,
        "target_identity_hash": MAGNITUDE_GE3_CONTRACT.identity_hash(),
        "group_counts": {
            "ge3_high": len(high_multiples),
            "ge3_low": len(low_multiples),
        },
        "ten_plus_case_count_in_ge3_high": sum(
            value >= 10.0 for value in high_multiples
        ),
        "low_group_range_verified": True,
        "locked_test_accessed": False,
    }


def replay(v130_path: Path, v138_path: Path, dataset_path: Path) -> dict[str, Any]:
    v130 = _committed_record(v130_path)
    v138 = _committed_record(v138_path)
    if {row.case_id for row in v130.trajectories} != {
        row.case_id for row in v138.trajectories
    }:
        raise ValueError("V130/V138 round-one case sets differ")
    return {
        "schema_version": "v130-v138-zero-call-acceptance-v1",
        "external_calls": 0,
        "locked_test_accessed": False,
        "v130": _metric_report(v130),
        "v138": _metric_report(v138),
        "technical_recovery_counterfactual": _counterfactual_recovery(v130, v138),
        "correction_scope_replay": _replay_corrections(v138_path),
        "reflection_flow_replay": _reflection_replay(v138_path),
        "slow_modality_replay": _slow_modality_replay(v138_path),
        "magnitude_target_replay": _magnitude_target_replay(dataset_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v130", type=Path, default=DEFAULT_V130)
    parser.add_argument("--v138", type=Path, default=DEFAULT_V138)
    parser.add_argument("--approved-dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = replay(args.v130, args.v138, args.approved_dataset)
    if args.output is not None:
        atomic_write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
