#!/usr/bin/env python3
"""Check saved v3 results at production model boundaries without answering roles."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket

from diagnose_executed_answer_scope import StageContract, _reflect, binding, read_json
from verify_local_role_consumers import verify_sample
from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_core import ExecutionTrajectory, SignalRound
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor, _plan_critic_trajectory
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.signal_library import SignalModelInputRejected


def diagnose(root: Path, output: Path) -> dict:
    """Retain fixed seven samples and prove rejection versus caller admission."""
    if output.exists():
        raise ValueError("diagnostic output must be new; do not rewrite prior evidence")
    output.mkdir(parents=True)
    source_files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != ".dispatch.lock")
    before = [binding(path) for path in source_files]
    samples = read_json(root / "inputs.json")["samples"]
    sample = next(row for row in samples if row["sample_id"] == "future_actual")
    contract = StageContract(read_json(root / "contract.json"))
    workspace = output / "workspace"
    client = StructuredRoleClient(registration=get_model("independent-subagent"), contract=contract,
        workspace=workspace, ledger=ExternalAttemptLedger(workspace / "attempts.json", max_attempts=1, max_total_cost=1),
        local_role_exchange=LocalRoleExchange(output / "exchange", max_calls=1), allow_external=False, environ={})
    old_context = read_json(root / "consumers/future_actual.json")["final_context"]
    original = ExecutionTrajectory.from_dict(read_json(Path(sample["original_trajectory"]["path"]))["trajectory"])
    injected = replace(original, signal_rounds=(SignalRound.from_dict(sample["signal_round"]),))
    mixed_clock_context = deepcopy(old_context)
    card = mixed_clock_context["signal_rounds"][0]["batch"]["results"][0]
    card["evidence"] = {"supporting": [], "counter": []}
    card["input_evidence_available_at"] = ["2025-11-10T12:00:00+00:00"]
    inconsistent_context = deepcopy(mixed_clock_context)
    inconsistent_context["signal_rounds"][0]["batch"]["results"][0]["input_evidence_available_at"] = ["2025-06-01T00:00:00Z"]
    checks = []
    actions = (
        ("reflect", lambda: _reflect(client, sample)),
        ("final_assembly", lambda: verify_sample(root, sample, output / "consumers")),
        ("posthoc_existing_context", lambda: _compact_posthoc_context(old_context)),
        ("critic_full_result", lambda: _plan_critic_trajectory(injected, case_index=1)),
        ("predictor_existing_context", lambda: LLMBlindPredictor(client).predict(old_context)),
        ("posthoc_all_present_clocks", lambda: _compact_posthoc_context(mixed_clock_context)),
        ("posthoc_exact_runtime_copy", lambda: _compact_posthoc_context(inconsistent_context)),
    )
    for name, action in actions:
        try:
            action()
            checks.append({"entry": name, "status": "unexpected_admission"})
        except SignalModelInputRejected as exc:
            checks.append({"entry": name, "status": "typed_input_rejected", "reason_code": exc.reason_code,
                           "path": exc.path, "reason": exc.reason})
    rejected_inbox_count = len(list((output / "exchange/inbox").glob("*.json")))
    outcomes = []
    for current in samples:
        if current["sample_id"] != "future_actual":
            outcomes.append(verify_sample(root, current, output / "consumers"))
    positive = read_json(output / "consumers/future_forecast.json")["final_context"]
    try:
        LLMBlindPredictor(client).predict(positive)
        positive_status = "unexpected_completion"
    except LocalRoleRequestPending as exc:
        positive_status = "pending_original_caller"
        positive_pending = exc.pending
    unchanged = before == [binding(path) for path in source_files]
    code_paths = [Path(__file__), Path("src/stock_opportunity_agent/signal_library.py"),
        *[Path("src/stock_opportunity_agent/research") / name for name in (
            "evolution_core.py", "evolution_output_validation.py", "evolution_plan_roles.py", "signal_evolution.py")]]
    result = {"schema_version": "signal-model-pit-boundary-v1", "source_bindings": before,
        "code_bindings": [binding(path.resolve()) for path in code_paths], "fixed_sample_denominator": len(samples),
        "negative": checks, "negative_new_inbox_count": rejected_inbox_count,
        "legal_consumer_outcomes": outcomes, "positive_predictor_status": positive_status,
        "positive_pending": positive_pending if positive_status == "pending_original_caller" else None,
        "original_v3_files_unchanged": unchanged, "external_api_calls": 0, "new_independent_role_responses": 0,
        "fresh_model_behavior_revalidated": False, "prediction_executed": False,
        "boundary_checks_passed": unchanged and rejected_inbox_count == 0
            and all(row["status"] == "typed_input_rejected" for row in checks)
            and all(row["status"] == "consumers_verified" for row in outcomes)
            and positive_status == "pending_original_caller",
        "engineering_mvp_closed": False}
    atomic_write_json(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("external network forbidden in this diagnostic")
    socket.socket = forbidden
    result = diagnose(args.root.resolve(), args.output.resolve())
    print(json.dumps({key: value for key, value in result.items() if key not in {"source_bindings", "code_bindings"}}, indent=2))


if __name__ == "__main__":
    main()
