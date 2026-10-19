#!/usr/bin/env python3
"""Independently revalidate saved local role states and actual consumer projections."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_executed_answer_scope import _load_stage, binding, read_json
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.research.evolution_core import (
    ExecutionTrajectory, InformationPlan, ResearchState, ResearchDecision, SignalRound,
    _assemble_final_context, _mask_identity_values,
)
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_plan_roles import _plan_critic_trajectory


def verify_sample(root: Path, sample: dict, output: Path) -> dict:
    """Reload accepted stage envelopes and compare exact disposition projections."""
    state = ResearchState.from_dict(sample["prior_state"])
    deltas = []
    stage_files = []
    for closure in ((True,) if sample.get("closure_only") else (False, True)):
        stage_file = root / "samples" / sample["sample_id"] / ("terminal_closure.json" if closure else "initial_reflect.json")
        if not stage_file.exists():
            return {"sample_id": sample["sample_id"], "status": "missing_accepted_stage", "stage": str(stage_file)}
        stage_files.append(binding(stage_file))
        state, delta = _load_stage(root, sample, state, closure=closure)
        deltas.append(delta)
        if state.decision is not ResearchDecision.CONTINUE:
            break
    context = _assemble_final_context(
        plan=InformationPlan.from_dict(sample["plan"]), company_id=sample["company_id"],
        additional_identity_aliases=tuple(sample["identity"].get("identity_aliases", ())),
        basic_info=sample["basic_info"], state=state, rounds=(SignalRound.from_dict(sample["signal_round"]),),
        prediction_time=datetime.fromisoformat(sample["prediction_time"]), prediction_baseline=sample["prediction_baseline"],
        state_deltas=tuple(deltas), computed_metrics=sample["computed_metric_cards"],
        signal_research_status=sample["signal_research_status"],
    )
    compact = _compact_posthoc_context(context)
    original_ref = sample["original_trajectory"]
    binding(Path(original_ref["path"]), original_ref["sha256"])
    original = ExecutionTrajectory.from_dict(read_json(Path(original_ref["path"]))["trajectory"])
    trajectory = replace(original, initial_state=ResearchState.from_dict(sample["prior_state"]),
                         final_state=state, signal_rounds=(SignalRound.from_dict(sample["signal_round"]),),
                         state_deltas=tuple(deltas), final_context=context, basic_info=sample["basic_info"])
    critic = _plan_critic_trajectory(trajectory, case_index=1)
    raw = [{"round": row["round"], "need_dispositions": row["need_dispositions"]} for row in deltas]
    aliases = (sample["company_id"], *sample["identity"].get("identity_aliases", ()), *(
        str(value) for key, value in sample["basic_info"].items()
        if key in {"company_id", "company_name", "ticker", "symbol"} and value is not None))
    expected = _mask_identity_values(raw, aliases)
    context_projection = [{"round": row.get("round"), "need_dispositions": row.get("need_dispositions")}
                          for row in context.get("state_evolution", ())]
    checks = {"final_context_dispositions_exact": context_projection == expected,
              "posthoc_dispositions_exact": compact.get("state_evolution") == expected,
              "critic_dispositions_exact": critic.get("state_evolution") == raw,
              "terminal_state_finalized": state.decision is ResearchDecision.FINALIZE}
    result = {"sample_id": sample["sample_id"], "status": "consumers_verified" if all(checks.values()) else "consumer_mismatch",
              "checks": checks, "accepted_stage_files": stage_files, "final_state": state.to_dict(),
              "state_deltas": deltas, "final_context": context, "compact_posthoc": compact, "critic": critic,
              "semantic_answer_scope_review_required": True, "new_prediction_or_posthoc_or_critic_executed": False,
              "critic_prediction_and_labels_are_historical_only": True, "external_api_calls": 0,
              "original_stage_outcome_unchanged": True}
    atomic_write_json(output / f"{sample['sample_id']}.json", result)
    if read_json(output / f"{sample['sample_id']}.json") != result:
        raise ValueError("consumer artifact changed on persistence/reload")
    return {"sample_id": sample["sample_id"], "status": result["status"], "checks": checks}


def verify(root: Path, output: Path, *, sample_id: str | None = None) -> dict:
    """Produce a separate evidence artifact without changing the frozen batch."""
    samples = read_json(root / "inputs.json")["samples"]
    if sample_id is not None:
        samples = [sample for sample in samples if sample["sample_id"] == sample_id]
        if not samples:
            raise ValueError("unknown frozen sample")
    outcomes = []
    for sample in samples:
        try:
            outcomes.append(verify_sample(root, sample, output))
        except Exception as exc:
            outcomes.append({"sample_id": sample["sample_id"], "status": "revalidation_failed", "error": str(exc)})
    result = {"schema_version": "local-role-separate-consumer-verification-v1",
              "source_manifest": binding(root / "manifest.json"), "source_inputs": binding(root / "inputs.json"),
              "verification_code": binding(Path(__file__)), "outcomes": outcomes,
              "all_selected_consumers_verified": all(row["status"] == "consumers_verified" for row in outcomes),
              "original_batch_outcomes_unchanged": True, "semantic_review_required": True,
              "external_api_calls": 0, "engineering_mvp_closed": False}
    atomic_write_json(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-id")
    args = parser.parse_args()
    print(json.dumps(verify(args.root, args.output, sample_id=args.sample_id), indent=2))


if __name__ == "__main__":
    main()
