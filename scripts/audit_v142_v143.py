"""Recompute frozen evolution metrics and audit V142/V143 without network I/O.

Usage: PYTHONPATH=src python scripts/audit_v142_v143.py --output /tmp/audit.json
Incomplete attempts are diagnostic only. Stored negative technical outcomes
remain in the recorded confusion matrix but are not called research successes.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from stock_opportunity_agent.research.evolution_research_validation import (
    _runtime_evaluation_input_requested,
)


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs/cold_start/evolution"


def read(path: Path, fingerprints: dict[Path, str] | None = None) -> dict:
    """Read one immutable audit input."""
    content = path.read_bytes()
    if fingerprints is not None:
        digest = hashlib.sha256(content).hexdigest()
        if fingerprints.setdefault(path, digest) != digest:
            raise RuntimeError(f"Audit input changed during read: {path}")
    return json.loads(content)


def metrics(rows: list[dict]) -> dict:
    """Reproduce the recorded binary matrix and expose technical attribution."""
    counts = dict.fromkeys(("tp", "fp", "fn", "tn"), 0)
    for row in rows:
        if row["truth"]:
            key = "tp" if row["predicted"] else "fn"
        else:
            key = "fp" if row["predicted"] else "tn"
        counts[key] += 1
    denominator = 2 * counts["tp"] + counts["fp"] + counts["fn"]
    technical_positive = sum(row["technical"] and row["truth"] for row in rows)
    technical_negative = sum(row["technical"] and not row["truth"] for row in rows)
    return {
        **counts,
        "n": len(rows),
        "f1": 2 * counts["tp"] / denominator if denominator else 0.0,
        "precision": counts["tp"] / (counts["tp"] + counts["fp"])
        if counts["tp"] + counts["fp"] else 0.0,
        "recall": counts["tp"] / (counts["tp"] + counts["fn"])
        if counts["tp"] + counts["fn"] else 0.0,
        "technical": technical_positive + technical_negative,
        "technical_positive": technical_positive,
        "technical_negative": technical_negative,
        "research_true_negative": sum(
            not row["technical"] and not row["truth"] and not row["predicted"]
            for row in rows
        ),
    }


def audit() -> dict:
    """Inspect final attempts, exact request records and authoritative pointers."""
    output = {"runs": {}, "attempts": [], "comparisons": []}
    records = {}
    inputs: dict[Path, str] = {}
    for version in (130, 139, 141, 142, 143):
        matches = list(RUNS.glob(f"*-v{version}"))
        if len(matches) != 1:
            raise ValueError(f"Expected one exact workspace for V{version}: {matches}")
        workspace = matches[0]
        if version >= 142:
            ledger = read(workspace / "attempts.json", inputs)["attempts"]
            attempted = {row["request_hash"] for row in ledger}
            stages, sent_stages = Counter(), Counter()
            issues = {}
            for path in sorted((workspace / "requests").glob("*.json")):
                request = read(path)["request"]
                stage = request["stage"]
                stages[stage] += 1
                if path.stem in attempted:
                    sent_stages[stage] += 1
                if stage.startswith("research_controller") and stage.endswith("correction"):
                    payload = json.loads(request["messages"][-1]["content"])
                    codes = {
                        issue.get("issue_code", "untyped")
                        for issue in payload.get("validation_feedback", {}).get("obligations", [])
                    }
                    issues.setdefault(stage, Counter()).update(codes)
            output["runs"][str(version)] = {
                "workspace": str(workspace.relative_to(ROOT)),
                "state": read(workspace / "state.json", inputs),
                "cycle_state": read(workspace / "cycle_state.json", inputs),
                "contract": read(workspace / "run_contract.json", inputs),
                "attempt_count": len(ledger),
                "attempt_statuses": dict(Counter(row["status"] for row in ledger)),
                "recorded_actual_cost": sum(row.get("actual_cost") or 0.0 for row in ledger),
                "unfinished_attempts": [row for row in ledger if row["status"] == "in_progress"],
                "saved_requests_by_stage": dict(sorted(stages.items())),
                "distinct_attempted_requests_by_stage": dict(sorted(sent_stages.items())),
                "saved_correction_requests_by_issue": {
                    stage: dict(counts) for stage, counts in issues.items()
                },
            }
        for path in sorted((workspace / "experiments").glob("round-*/attempts/*.json")):
            attempt = read(path, inputs)
            round_id = int(path.parent.parent.name[-4:])
            snapshot_path = workspace / f"evaluation/round_{round_id:03d}/snapshot.json"
            snapshot = read(snapshot_path, inputs)
            anchors = set(snapshot["anchor_case_ids"])
            rows = []
            for trajectory in attempt.get("trajectories", []):
                prediction = trajectory.get("prediction") or {}
                truth = trajectory["ground_truth"]
                rows.append({
                    "case_id": trajectory["case_id"],
                    "truth": truth["is_surge"],
                    "predicted": prediction.get("is_surge"),
                    "judgment": prediction.get("candidate_judgment"),
                    "technical": prediction.get("session_id", "").startswith("exclusion_"),
                    "stop_reason": trajectory.get("stop_reason"),
                    "cohort": "anchor" if trajectory["case_id"] in anchors else "random",
                    "magnitude": prediction.get("magnitude"),
                    "actual_magnitude": truth.get("magnitude"),
                    "realized_multiple": truth["realized_max_multiple"],
                })
            recomputed = {
                cohort: metrics([row for row in rows if cohort == "combined" or row["cohort"] == cohort])
                for cohort in ("combined", "anchor", "random")
            }
            stored = attempt.get("metrics")
            if stored and abs(recomputed["combined"]["f1"] - stored["binary_f1"]) > 1e-10:
                raise ValueError(f"Stored F1 mismatch: {path}")
            observed = {row["case_id"] for row in rows}
            if len(observed) != len(rows) or not observed.issubset(snapshot["case_ids"]):
                raise ValueError(f"Duplicate or unfrozen case: {path}")
            record = {
                "run": version, "plan": attempt["plan_id"], "round": round_id,
                "complete": observed == set(snapshot["case_ids"]),
                "missing_case_ids": sorted(set(snapshot["case_ids"]) - observed),
                "eligible": attempt["fitness"]["eligible"],
                "fitness": attempt["fitness"], "stored_metrics": stored,
                "recomputed": recomputed, "rows": rows,
                "failures": attempt.get("failures"),
                "path": str(path.relative_to(ROOT)),
            }
            records[version, attempt["plan_id"]] = record
            output["attempts"].append(record)
    for left, right in (
        ((142, "plan_r0001_c01"), (143, "plan_r0001_c01")),
        ((142, "plan_r0001_c02"), (143, "plan_r0001_c01")),
        ((142, "plan_r0002_c02"), (143, "plan_r0002_c02")),
        ((143, "plan_r0001_c01"), (143, "plan_r0002_c02")),
        ((130, "plan_r0001_c01"), (143, "plan_r0001_c01")),
        ((141, "plan_r0001_c02"), (143, "plan_r0001_c01")),
    ):
        before = {row["case_id"]: row for row in records[left]["rows"]}
        after = {row["case_id"]: row for row in records[right]["rows"]}
        common = sorted(before.keys() & after.keys())
        output["comparisons"].append({
            "left": left, "right": right, "shared_count": len(common),
            "same_observed_cohort": before.keys() == after.keys(),
            "before": metrics([before[key] for key in common]),
            "after": metrics([after[key] for key in common]),
            "changes": [
                {"case_id": key, "before": before[key], "after": after[key]}
                for key in common
                if before[key]["predicted"] != after[key]["predicted"]
                or before[key]["technical"] != after[key]["technical"]
            ],
        })
    question = (
        "What quantified forward bridge to a doubling of the adjusted share price "
        "was disclosed by the prediction time, including guidance, backlog or RPO "
        "conversion, order value, analyst targets, or consensus estimates, and what source supplies it?"
    )
    output["runtime_input_guard_reproduction"] = [
        {"question": text, "rejected_as_runtime_input": _runtime_evaluation_input_requested(text, {"2025-03-31"})}
        for text in (question, question.replace("by the prediction time", "by the cutoff"))
    ]
    output["input_sha256"] = {
        str(path.relative_to(ROOT)): inputs[path] for path in sorted(inputs)
    }
    output["limits"] = [
        "No external calls; historical source files are read only.",
        "Incomplete attempt metrics are diagnostics, never eligible scores.",
        "Stored TN may include technical negative rows; research_true_negative excludes them.",
        "Same cohort comparisons are observational: plans, history and available source data differ.",
        "Saved request counts include local preflight records; attempted counts join the ledger.",
        "Jev decision HTTP bodies are not present in the StructuredCaller request archive.",
    ]
    return output


def main() -> None:
    """Write the audit outside run workspaces and verify audited inputs unchanged."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.is_relative_to(RUNS.resolve()):
        parser.error("audit output must not modify an evolution workspace")
    result = audit()
    for relative, expected in result["input_sha256"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Audit input changed during read: {relative}")
    destination.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(f"Recomputed {len(result['attempts'])} attempts; {len(result['input_sha256'])} inputs unchanged; {destination}")


if __name__ == "__main__":
    main()
