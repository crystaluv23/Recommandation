#!/usr/bin/env python3
"""Zero-call audit of the completed V139 Fast/Slow live cycle.

This reads committed artifacts only, uses a temporary copy for interrupted
attempt reconciliation, never opens Locked Test, and performs no provider or
data-source calls.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.research.evolution_core import (
    PlanRecord,
    score_predictions,
)
from stock_opportunity_agent.research.evolution_transport import (
    ExternalAttemptLedger,
)
from stock_opportunity_agent.research.evolution_control import (
    load_approved_development_dataset,
)
from stock_opportunity_agent.research.research_targets import (
    MAGNITUDE_GE3_CONTRACT,
    build_target_group_manifest,
    build_target_sampling_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V130 = PROJECT_ROOT / (
    "runs/cold_start/evolution/"
    "information-evolution-dual-self-evolution-20260920-v130"
)
DEFAULT_V139 = PROJECT_ROOT / (
    "runs/cold_start/evolution/"
    "information-evolution-dual-self-evolution-20260922-v139"
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


def _records(workspace: Path) -> tuple[PlanRecord, ...]:
    checkpoint = _read(
        workspace / "experiments" / "round-0001" / "checkpoint.json"
    )
    return tuple(
        PlanRecord.from_dict(
            _read(workspace / "plans" / str(plan_id) / "record.json")
        )
        for plan_id in checkpoint["plan_ids"]
    )


def _metric(record: PlanRecord) -> dict[str, Any]:
    replayed = score_predictions(record.trajectories)
    if replayed.to_dict() != record.metrics.to_dict():
        raise ValueError(f"metric mismatch for {record.plan_id}")
    return {"plan_id": record.plan_id, "metrics": replayed.to_dict()}


def _paired_f1(v130: PlanRecord, candidate: PlanRecord) -> dict[str, Any]:
    baseline = {row.case_id: row for row in v130.trajectories}
    current = {row.case_id: row for row in candidate.trajectories}
    if set(baseline) != set(current):
        raise ValueError("V130 and V139 case sets differ")
    case_ids = sorted(baseline)

    def f1(rows: list[Any]) -> float:
        return score_predictions(rows).binary_f1

    rng = random.Random("v130-v139-paired-f1")
    deltas: list[float] = []
    for _ in range(20_000):
        sample = [case_ids[rng.randrange(len(case_ids))] for _ in case_ids]
        deltas.append(
            f1([current[case_id] for case_id in sample])
            - f1([baseline[case_id] for case_id in sample])
        )
    deltas.sort()
    paired_correctness = Counter(
        (
            baseline[case_id].prediction.is_surge
            == baseline[case_id].ground_truth.is_surge,
            current[case_id].prediction.is_surge
            == current[case_id].ground_truth.is_surge,
        )
        for case_id in case_ids
    )
    baseline_only = paired_correctness[(True, False)]
    candidate_only = paired_correctness[(False, True)]
    discordant = baseline_only + candidate_only
    mcnemar_p = (
        min(
            1.0,
            2
            * sum(
                math.comb(discordant, index)
                for index in range(min(baseline_only, candidate_only) + 1)
            )
            / (2**discordant),
        )
        if discordant
        else 1.0
    )
    delta = candidate.metrics.binary_f1 - v130.metrics.binary_f1
    lower = deltas[500]
    upper = deltas[19_499]
    return {
        "case_count": len(case_ids),
        "v130_f1": v130.metrics.binary_f1,
        "v139_f1": candidate.metrics.binary_f1,
        "absolute_delta": delta,
        "paired_bootstrap_95pct_interval": [lower, upper],
        "bootstrap_probability_delta_nonnegative": sum(
            item >= 0 for item in deltas
        )
        / len(deltas),
        "mcnemar_discordance": {
            "v130_only_correct": baseline_only,
            "v139_only_correct": candidate_only,
            "exact_two_sided_p": mcnemar_p,
        },
        "significant_decline_detected": upper < 0 or mcnemar_p < 0.05,
    }


def _parallel_replay(workspace: Path) -> dict[str, Any]:
    events = []
    for line in (
        workspace / "experiments" / "trajectory.jsonl"
    ).read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    starts = [event for event in events if event.get("event_type") == "case_started"]
    completions = [
        event for event in events if event.get("event_type") == "case_completed"
    ]
    witness = None
    for left in starts:
        left_finish = next(
            (
                event
                for event in completions
                if event.get("plan_id") == left.get("plan_id")
                and event.get("case_id") == left.get("case_id")
                and int(event.get("sequence", 0)) > int(left.get("sequence", 0))
            ),
            None,
        )
        if left_finish is None:
            continue
        right = next(
            (
                event
                for event in starts
                if event.get("plan_id") != left.get("plan_id")
                and int(left.get("sequence", 0))
                < int(event.get("sequence", 0))
                < int(left_finish.get("sequence", 0))
            ),
            None,
        )
        if right is not None:
            witness = {
                "left_started": {
                    key: left.get(key)
                    for key in ("sequence", "plan_id", "case_id", "at")
                },
                "right_started_before_left_finished": {
                    key: right.get(key)
                    for key in ("sequence", "plan_id", "case_id", "at")
                },
                "left_finished": {
                    key: left_finish.get(key)
                    for key in ("sequence", "plan_id", "case_id", "at")
                },
            }
            break
    if witness is None:
        raise ValueError("no cross-Plan overlap witness found")
    return {
        "actual_parallel_overlap": True,
        "witness": witness,
    }


def _attempt_recovery_replay(workspace: Path) -> dict[str, Any]:
    source = workspace / "attempts.json"
    stored = _read(source)
    before = Counter(str(row.get("status")) for row in stored["attempts"])
    with tempfile.TemporaryDirectory() as directory:
        copied = Path(directory) / "attempts.json"
        shutil.copyfile(source, copied)
        ledger = ExternalAttemptLedger(
            copied,
            max_attempts=int(stored["max_attempts"]),
            max_total_cost=float(stored["max_total_cost"]),
        )
        reconciled = ledger.reconcile_interrupted()
        after = ledger.summary
    return {
        "historical_status_counts": dict(sorted(before.items())),
        "reconciled_on_temporary_copy": reconciled,
        "post_reconcile_summary": after,
        "source_workspace_mutated": False,
    }


def _slow_replay(workspace: Path) -> dict[str, Any]:
    cycle = workspace / "experiments" / "cycles" / "cycle-0001"
    result = _read(cycle / "slow_loop_result.json")["result"]
    validation = _read(cycle / "slow_loop_validation.json")["validation"]
    slow_input = _read(cycle / "slow_input.json")
    mining = validation["agent_audits"]["mining_pipeline"]
    metrics = mining["modality_metrics"]
    magnitude_rows = [
        row
        for row in slow_input["feedback_rows"]
        if row.get("kind") == "magnitude_feedback"
    ]
    narrative_reads = int(metrics.get("narrative_read_count", 0))
    narrative_completed = int(
        metrics.get("narrative_exploration_completed", 0)
    )
    return {
        "magnitude_feedback_count": len(magnitude_rows),
        "magnitude_feedback_refs": sorted(
            str(row["feedback_ref"]) for row in magnitude_rows
        ),
        "historical_magnitude_contribution": result["magnitude_contribution"],
        "historical_target_track_present": bool(
            slow_input.get("research_targets")
        ),
        "historical_mining_axis": mining.get("axis_id", "surge_direction"),
        "narrative_reads": narrative_reads,
        "narrative_exploration_claims": narrative_completed,
        "narrative_exploration_claim_valid_under_current_contract": not (
            narrative_completed > 0 and narrative_reads == 0
        ),
        "conclusion": (
            "V139 consumed magnitude diagnostics but did not run a target-specific "
            "2-3x versus >=3x mining/effectiveness track. Its narrative "
            "exploration completion claim is not grounded by a raw span read."
        ),
    }


def _target_sampling_replay(dataset_path: Path) -> dict[str, Any]:
    dataset = load_approved_development_dataset(dataset_path)
    groups = build_target_group_manifest(
        dataset.discovery, MAGNITUDE_GE3_CONTRACT
    )
    sampling = build_target_sampling_manifest(
        dataset.discovery,
        MAGNITUDE_GE3_CONTRACT,
        cycle_id=1,
        base_seed="v139-post-fix-replay",
        dev_limit=32,
        check_limit=16,
    )["sampling"]
    labels = groups["groups"]
    dev = [str(case_id) for case_id in sampling["dev_case_ids"]]
    check = [str(case_id) for case_id in sampling["check_case_ids"]]
    issuers = sampling["issuer_groups"]

    def counts(case_ids: list[str]) -> dict[str, int]:
        return dict(sorted(Counter(labels[case_id] for case_id in case_ids).items()))

    return {
        "target_id": MAGNITUDE_GE3_CONTRACT.target_id,
        "dev_group_counts": counts(dev),
        "check_group_counts": counts(check),
        "issuer_disjoint": not (
            {issuers[case_id] for case_id in dev}
            & {issuers[case_id] for case_id in check}
        ),
        "locked_test_accessed": False,
    }


def replay(
    v130_path: Path, v139_path: Path, dataset_path: Path = DEFAULT_DATASET
) -> dict[str, Any]:
    state = _read(v139_path / "state.json")
    cycle_state = _read(v139_path / "cycle_state.json")
    if int(state.get("last_completed_round", 0)) != 1 or int(
        cycle_state.get("last_completed_cycle", 0)
    ) != 1:
        raise ValueError("V139 is not pointer-committed through round/cycle 1")
    v130 = _records(v130_path)[0]
    v139_records = _records(v139_path)
    best = max(v139_records, key=lambda record: record.metrics.binary_f1)
    return {
        "schema_version": "v139-zero-call-live-audit-v1",
        "external_calls": 0,
        "locked_test_accessed": False,
        "pointer_state": {
            "last_completed_round": 1,
            "last_completed_cycle": 1,
        },
        "v130": _metric(v130),
        "v139_plans": [_metric(record) for record in v139_records],
        "best_v139_vs_v130": _paired_f1(v130, best),
        "parallel_fast": _parallel_replay(v139_path),
        "attempt_recovery": _attempt_recovery_replay(v139_path),
        "slow": _slow_replay(v139_path),
        "post_fix_target_sampling": _target_sampling_replay(dataset_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v130", type=Path, default=DEFAULT_V130)
    parser.add_argument("--v139", type=Path, default=DEFAULT_V139)
    parser.add_argument(
        "--approved-dataset", type=Path, default=DEFAULT_DATASET
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = replay(args.v130, args.v139, args.approved_dataset)
    if args.output is not None:
        atomic_write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
