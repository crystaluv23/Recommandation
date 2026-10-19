#!/usr/bin/env python3
"""Freeze/resume independent local Reflect roles through the production runtime."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from diagnose_executed_answer_scope import (
    REPO, StageContract, _source_inputs, _reflect, _load_stage, binding, read_json,
    assemble_consumers,
)
from verify_local_role_consumers import verify_sample
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState, ResearchDecision, _assemble_final_context, InformationPlan, SignalRound
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.research.evolution_research_validation import (
    _normalize_research_state_output, _validate_research_state_refs,
    _reject_unrepresentable_partial_selections,
)


def _variants(original):
    definitions = (
        ("q2_only", "What is the issuer's Q3 2025 revenue guidance?", "For Q2 2025, the company expects revenue of $120 million.", "2025-06-25T12:00:00+00:00", "unanswered", None),
        ("future_forecast", "What is the issuer's Q3 2025 revenue guidance?", "For Q3 2025, the company expects revenue of $140 million.", "2025-06-25T12:00:00+00:00", "full", None),
        ("partial_numeric", "What is the issuer's Q3 2025 revenue guidance, and was it raised or lowered from prior guidance?", "For Q3 2025, the company expects revenue of $140 million.", "2025-06-25T12:00:00+00:00", "partial", "direction_of_change"),
        ("future_actual", "What is the issuer's Q3 2025 revenue guidance?", "For Q3 2025, the company reported actual revenue of $140 million.", "2025-11-10T12:00:00+00:00", "unanswered", None),
        ("terminal_empty_owner", "What is the issuer's Q3 2025 revenue guidance?", "For Q2 2025, the company expects revenue of $120 million.", "2025-06-25T12:00:00+00:00", None, None),
    )
    samples, expected = [], []
    for name, need, quote, timestamp, scope, residual in definitions:
        need = need.rstrip("?") + ", using only disclosures available by " + original["prediction_time"] + "?"
        sample = deepcopy(original)
        sample.update(sample_id=name, synthetic=True, target_need_index=0, target_need=need)
        sample["prior_state"] = {"hypotheses": [], "current_beliefs": [], "supporting_evidence": [],
                                 "contradictions": [], "resolved_questions": [], "open_questions": [],
                                 "next_information_needs": [need], "decision": "continue"}
        result = {"signal_id": "guidance_acceleration", "version": 3,
                  "state": {"value": "neutral", "confidence": 0.5},
                  "interpretation": {"summary": quote + " Prior guidance is not supplied; change direction is unavailable."},
                  "evidence": {"supporting": [{"document_id": "synthetic:guidance:" + name, "exact_span": quote, "timestamp": timestamp}], "counter": []},
                  "status": {"coverage": "partial"}, "execution": {"status": "success"}}
        selection = {"signal_ref": "guidance_acceleration:v3", "reason_code": "answer_need",
                     "selection_reason": "Assess the requested management guidance.",
                     "applicability_hypothesis": "The disclosed outlook may inform the requested guidance.",
                     "expected_role": "primary", "context_tags": [], "target_need_indices": [0],
                     "answer_scope": "full", "residual_need": None}
        sample["signal_round"] = {"information_needs": [need], "selected_signals": ["guidance_acceleration:v3"],
                                  "selections": [selection], "batch": {"results": [result], "signal_calls": 1,
                                  "usage": {"llm_calls": 0, "tokens": 0, "cost": 0.0}, "resolutions": []}}
        sample["basic_info"] = {}
        sample["closure_only"] = name == "terminal_empty_owner"
        expected.append({"sample_id": name, "answer_scope": scope, "residual_semantics": residual,
                         "need": need, "exact_quote": quote, "timestamp": timestamp,
                         "must_preserve_need": scope in {None, "unanswered"},
                         "must_not_adopt_future_actual": name == "future_actual"})
        samples.append(sample)
    return samples, expected


def preflight_samples(inputs):
    """Reject illegal prior states and unrepresentable routing before dispatch."""
    checked = []
    for sample in inputs["samples"]:
        state = ResearchState.from_dict(sample["prior_state"])
        normalized = _normalize_research_state_output(state.to_dict(), previous_state=state,
            evaluation_context=sample["evaluation_context"], computed_metric_cards=tuple(sample["computed_metric_cards"]))
        if normalized != state.to_dict():
            raise ValidationError("preflight may not rewrite a prior state")
        _validate_research_state_refs(state, phase="reflect", previous_state=state,
            basic_info=sample["basic_info"], need_dispositions=[], evaluation_context=sample["evaluation_context"])
        round_row = SignalRound.from_dict(sample["signal_round"])
        _reject_unrepresentable_partial_selections(round_row.selections, state.next_information_needs, sample["evaluation_context"])
        checked.append({"sample_id": sample["sample_id"], "prior_state_hash": canonical_json_hash(state.to_dict()),
                        "legal_prior_and_routing": True, "source_pit_accepted": False,
                        "future_signal_evidence_fault_injection": sample["sample_id"] == "future_actual"})
    return {"samples": checked, "fixed_denominator": len(checked)}


def prepare(root):
    """Freeze the fixed seven-case denominator and independent expectations."""
    if root.exists():
        raise ValidationError("prepare requires a new directory")
    inputs, originals = _source_inputs()
    for sample in inputs["samples"]:
        sample["synthetic"] = False
    variants, expected = _variants(inputs["samples"][0])
    expected = [{"sample_id": s["sample_id"], "answer_scope": "unanswered", "must_preserve_need": True,
                 "need": s["target_need"], "historical_input_pit_accepted": False} for s in inputs["samples"]] + expected
    inputs["samples"].extend(variants)
    preflight = preflight_samples(inputs)
    contract = {"schema_version": "engineering-mvp-local-reflect-v2", "backend": "independent-subagent",
                "actual_model_version": None, "model_selection": "inherited_host_default_precise_version_unknown",
                "fixed_denominator": 7, "max_local_calls": 28, "max_external_api_calls": 0,
                "limits": {"max_structured_corrections": 1, "structured_reasoning_token_reserve": 0,
                           "max_request_tokens": 131072},
                "scope": "Reflect and actual local consumer assembly; no predictor or whole-cycle acceptance",
                "input_hash": canonical_json_hash(inputs), "expectations_hash": canonical_json_hash(expected),
                "preflight_hash": canonical_json_hash(preflight)}
    files = [*list((REPO / "src/stock_opportunity_agent").rglob("*.py")), Path(__file__),
             REPO / "scripts/diagnose_executed_answer_scope.py", REPO / "scripts/verify_local_role_consumers.py"]
    manifest = {"contract_hash": canonical_json_hash(contract), "code_files": [binding(p) for p in sorted(files)],
                "originals": originals, "fixed_sample_ids": [s["sample_id"] for s in inputs["samples"]]}
    manifest["manifest_hash"] = canonical_json_hash(manifest)
    root.mkdir(parents=True)
    for name, value in (("inputs", inputs), ("expectations", expected), ("contract", contract), ("manifest", manifest), ("preflight", preflight)):
        atomic_write_json(root / f"{name}.json", value)
    return {"status": "frozen", "manifest_hash": manifest["manifest_hash"], "samples": manifest["fixed_sample_ids"]}


def stage_consumer_checks(root, sample, state, expectation, *, output=None):
    """Exercise the same actual consumer branch in diagnostics and CLI tests."""
    if not sample["synthetic"]:
        return assemble_consumers(root, sample)
    stage = "terminal_closure" if sample.get("closure_only") else "initial_reflect"
    saved = read_json(root / "samples" / sample["sample_id"] / f"{stage}.json")
    rows = saved["metadata"].get("need_dispositions", {}).get("items", [])
    scope = expectation["answer_scope"]
    checks = {"correct_scope": not rows if scope is None else len(rows) == 1 and rows[0]["answer_scope"] == scope,
              "preserved_need": not expectation["must_preserve_need"] or sample["target_need"] in state.next_information_needs,
              "terminal_finalized": state.decision is ResearchDecision.FINALIZE}
    consumer_result = verify_sample(root, sample, output or root / "consumers")
    checks.update(consumer_result.get("checks", {}))
    checks["accepted_consumers_verified"] = consumer_result["status"] == "consumers_verified"
    return checks


def resume(root):
    """Reenter production roles; pending requests never become sample failures."""
    manifest = read_json(root / "manifest.json")
    digest = manifest.pop("manifest_hash")
    if canonical_json_hash(manifest) != digest:
        raise ValidationError("manifest changed")
    for row in manifest["code_files"] + manifest["originals"]:
        binding(Path(row["path"]), row["sha256"])
    contract, inputs = read_json(root / "contract.json"), read_json(root / "inputs.json")
    expected = json.loads((root / "expectations.json").read_text())
    if (canonical_json_hash(contract) != manifest["contract_hash"] or canonical_json_hash(inputs) != contract["input_hash"]
            or canonical_json_hash(expected) != contract["expectations_hash"]
            or canonical_json_hash(read_json(root / "preflight.json")) != contract["preflight_hash"]):
        raise ValidationError("frozen inputs, expectations or contract changed")
    exchange = LocalRoleExchange(root / "exchange", max_calls=contract["max_local_calls"])
    ledger = ExternalAttemptLedger(root / "unused_external_attempts.json", max_attempts=1, max_total_cost=0.01)
    pending, outcomes = [], []
    for sample in inputs["samples"]:
        sample_root = root / "samples" / sample["sample_id"]
        verdict = sample_root / "outcome.json"
        if verdict.exists():
            outcomes.append(read_json(verdict))
            continue
        traces = []
        try:
            state = ResearchState.from_dict(sample["prior_state"])
            for closure in ((True,) if sample.get("closure_only") else (False, True)):
                client = StructuredRoleClient(registration=get_model("independent-subagent"),
                    contract=StageContract(contract), workspace=root, ledger=ledger,
                    local_role_exchange=exchange, allow_external=False, environ={})
                try:
                    step = _reflect(client, sample, state=state, closure=closure)
                finally:
                    traces.extend(client.request_hash_trace)
                stage = "terminal_closure" if closure else "initial_reflect"
                atomic_write_json(sample_root / f"{stage}.json", {"kind": "independent_local_role", "stage": stage,
                    "state": step.value.to_dict(), "metadata": dict(step.metadata), "usage": asdict(step.usage),
                    "request_hashes": client.request_hash_trace})
                state = step.value
                if state.decision is not ResearchDecision.CONTINUE:
                    break
            checks = stage_consumer_checks(root, sample, state,
                next(e for e in expected if e["sample_id"] == sample["sample_id"]))
            outcome = {"sample_id": sample["sample_id"], "mechanical_checks": checks,
                       "mechanical_passed": all(checks.values()), "independent_semantic_verdict": "pending_review",
                       "request_hashes": traces}
            atomic_write_json(verdict, outcome)
            outcomes.append(outcome)
        except LocalRoleRequestPending as exc:
            pending.append({"sample_id": sample["sample_id"], **exc.pending})
        except Exception as exc:
            outcome = {"sample_id": sample["sample_id"], "mechanical_passed": False,
                       "failure_type": type(exc).__name__, "error": str(exc)[:2000], "request_hashes": traces}
            atomic_write_json(verdict, outcome)
            outcomes.append(outcome)
    result = {"status": "pending_roles" if pending else "completed_requires_independent_review", "fixed_denominator": 7,
              "outcomes": outcomes, "pending": pending, "external_api_calls": 0,
              "source_pit_accepted": False, "engineering_mvp_closed": False}
    atomic_write_json(root / "progress.json", result)
    return result


def main():
    """Prepare, resume or receipt-bind a local stage execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "resume", "submit"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--request-hash")
    parser.add_argument("--agent-id")
    args = parser.parse_args()
    result = (prepare(args.root) if args.command == "prepare" else resume(args.root) if args.command == "resume"
              else LocalRoleExchange(args.root / "exchange", max_calls=28).submit(args.request_hash, agent_id=args.agent_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
