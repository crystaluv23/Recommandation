#!/usr/bin/env python3
"""Replay one immutable paid Update output through production parsing and fixtures.

Usage: PYTHONPATH=src:. python scripts/replay_signal_update_literal_repair.py
    --run RUN_ROOT --request-ref SHA256 --report OUTPUT_JSON
No model request, Registry write or promotion occurs. The production fixture
method is bound to its real Registry/validator dependencies; orchestration and
future semantic corrections are outside this replay's acceptance scope.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.research.evolution_core import CandidateExecutionRejected
from stock_opportunity_agent.research.evolution_signal_roles import LLMSignalUpdateModel
from stock_opportunity_agent.research.signal_evolution import (
    SignalCandidateValidator, SignalEvolutionEngine,
)
from stock_opportunity_agent.signal_library import SignalRegistry
from tests.evolution_runtime_test_support import ScriptedRoleCaller


def replay(run: Path, request_ref: str) -> dict:
    """Retain exact source hashes and report repair plus the next real frontier."""

    request_path = run / "requests" / f"{request_ref}.json"
    response_path = run / "cache/responses" / f"{request_ref}.json"
    source_hashes = {str(path): sha256(path.read_bytes()).hexdigest()
                     for path in (request_path, response_path)}
    request = json.loads(request_path.read_text())["request"]
    payload = json.loads(request["messages"][-1]["content"])
    output = json.loads(response_path.read_text())["json_output"]
    original = deepcopy(output)
    events: list[dict] = []
    # A native no-op delta is a deliberately ineffective *offline* correction,
    # not a claim that a new LLM correction succeeds or fails in production.
    caller = ScriptedRoleCaller([output, lambda kwargs: {
        "base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
        "operations": [],
    }])
    caller.on_progress = events.append
    registry = SignalRegistry(run / "signals")
    dependencies = SimpleNamespace(
        registry=registry,
        validator=SignalCandidateValidator(registry, llm_runner=None),
    )
    model = LLMSignalUpdateModel(caller)
    model.set_candidate_validator(lambda ref, candidate, paths:
        SignalEvolutionEngine._validate_update_candidate_for_role(
            dependencies, ref, candidate, paths))
    accepted = False
    frontier = None
    try:
        model.update(payload)
        accepted = True
    except CandidateExecutionRejected as exc:
        frontier = str(exc)
    feedback = caller.calls[1]["payload"]["validation_feedback"] if len(caller.calls) > 1 else None
    baseline = feedback["invalid_output"] if feedback else output
    changed_literals = []
    for index, (before, after) in enumerate(zip(output["case_diagnostics"], baseline["case_diagnostics"])):
        for fact_index, (old, new) in enumerate(zip(before["facts"], after["facts"])):
            if old != new:
                assert old["document_ref"] == new["document_ref"]
                changed_literals.append({"path": f"case_diagnostics[{index}].facts[{fact_index}].exact_span",
                    "case_ref": before["case_ref"], "before": old["exact_span"], "after": new["exact_span"]})
        untouched_before, untouched_after = deepcopy(before), deepcopy(after)
        untouched_before.pop("facts"); untouched_after.pop("facts")
        assert untouched_before == untouched_after
    for key in ("candidate", "signal_ref", "disposition", "problem_type", "rationale"):
        assert baseline[key] == original[key]
    assert output == original
    assert all(sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in source_hashes.items())
    return {"run": str(run.resolve()), "request_ref": request_ref,
        "scope": "offline exact role parsing and production deterministic fixture checks; no new model calls",
        "source_file_hashes": source_hashes, "source_files_preserved": True,
        "repair_events": events, "restored_literals": changed_literals,
        "original_changed_paths": output["changed_paths"], "normalized_changed_paths": baseline["changed_paths"],
        "candidate_and_nonliteral_diagnostics_preserved": True,
        "visible_prior_year_comparisons": {
            packet["case_ref"]: packet.get("evidence_observation", {}).get("visible_prior_year_comparisons", [])
            for packet in caller.calls[0]["payload"]["induction_cases"]},
        "first_correction_issue_codes": [row["issue_code"] for row in feedback["obligations"]] if feedback else [],
        "first_correction_error": feedback["validation_error"] if feedback else None,
        "full_role_accepted": accepted, "terminal_frontier_with_ineffective_scripted_correction": frontier}


def main() -> None:
    """Write one reviewable replay report without modifying the source run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--request-ref", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.run, args.request_ref)
    atomic_write_json(args.report, result)
    print(json.dumps({"restored_literal_count": len(result["restored_literals"]),
        "first_correction_issue_codes": result["first_correction_issue_codes"],
        "full_role_accepted": result["full_role_accepted"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
