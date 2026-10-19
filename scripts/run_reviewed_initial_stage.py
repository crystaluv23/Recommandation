#!/usr/bin/env python3
"""Freeze/resume actual reviewed Basic Info projection and independent H_init."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import socket

from diagnose_executed_answer_scope import StageContract, binding, read_json
from run_reviewed_signal_stage import REPO, SOURCE_INPUTS, IDENTITY, COMPANY, _save_exact
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.data.resolution import EvidenceResolver
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import InformationPlan, default_information_plan, project_basic_info_bundle
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending, LocalRoleBudgetExhausted


def _samples():
    return [{"sample_id": name, "prediction_time": cutoff, "company_id": COMPANY,
             "identity": IDENTITY, "plan": default_information_plan().to_dict()}
            for name, cutoff in (("s01", "2025-09-30T00:00:00+00:00"),
                                 ("s02", "2025-07-01T00:00:00+00:00"))]


def _bootstrap(resolver, sample):
    plan = InformationPlan.from_dict(sample["plan"])
    bundle = resolver.resolve_basic_info(plan.basic_info_policy.requests,
        company_id=sample["company_id"], identity=sample["identity"],
        as_of=datetime.fromisoformat(sample["prediction_time"]))
    model, lineage = project_basic_info_bundle(bundle)
    return {"bundle": bundle.to_dict(), "model_context": model, "projection_lineage": lineage}


def _code_bindings():
    return [binding(p) for p in sorted([*(REPO / "src").rglob("*.py"), Path(__file__),
        REPO / "scripts/run_reviewed_signal_stage.py", REPO / "scripts/diagnose_executed_answer_scope.py",
        REPO / "spec/scripts/run_reviewed_initial_stage.md"])]


def prepare(root: Path, expectations: Path):
    """Freeze original production bootstrap inputs and a separate semantic oracle."""
    if root.exists():
        raise ValidationError("stage destination must be new")
    sb = read_json(SOURCE_INPUTS)["reviewed_source_snapshot"]
    store = open_raw_info_store(sb["root"], reviewed_snapshot=sb)
    inputs = {"samples": _samples(), "reviewed_source_snapshot": sb}
    expected = read_json(expectations)
    if [s["sample_id"] for s in expected["samples"]] != [s["sample_id"] for s in inputs["samples"]]:
        raise ValidationError("independent expectations must retain the two neutral samples")
    resolver = EvidenceResolver(store)
    preflight = [{"sample_id": s["sample_id"], **_bootstrap(resolver, s)} for s in inputs["samples"]]
    contract = {"schema_version": "reviewed-initial-stage-v1", "backend": "independent-subagent",
        "scope": "production default Basic Info collection/projection -> H_init only; no evaluator/Predictor",
        "fixed_denominator": 2, "max_local_calls": 8, "external_llm_calls": 0,
        "readonly_data_requests": 0, "actual_model_version": None,
        "model_selection": "inherited_host_default_precise_version_unknown",
        "input_hash": canonical_json_hash(inputs), "expectations_hash": canonical_json_hash(expected),
        "preflight_hash": canonical_json_hash(preflight), "limits": {"max_request_tokens": 131072,
            "max_structured_corrections": 1, "structured_reasoning_token_reserve": 0}}
    manifest = {"schema_version": "reviewed-initial-stage-freeze-v1", "contract_hash": canonical_json_hash(contract),
        "code_files": _code_bindings(), "originals": [binding(SOURCE_INPUTS), binding(expectations)],
        "full_cycle": False, "market_baseline_present": False}
    manifest["manifest_hash"] = canonical_json_hash(manifest)
    for name, value in (("inputs", inputs), ("expectations", expected), ("preflight", preflight),
                        ("contract", contract), ("manifest", manifest)):
        atomic_write_json(root / (name + ".json"), value)
    return {"manifest_hash": manifest["manifest_hash"], "fixed_denominator": 2, "role_dispatches": 0}


def resume(root: Path):
    """Replay actual bootstrap and suspend only at production LLM requests."""
    manifest = read_json(root / "manifest.json")
    digest = manifest.pop("manifest_hash")
    if canonical_json_hash(manifest) != digest:
        raise ValidationError("stage manifest changed")
    for row in manifest["code_files"] + manifest["originals"]:
        binding(Path(row["path"]), row["sha256"])
    contract, inputs = read_json(root / "contract.json"), read_json(root / "inputs.json")
    if (canonical_json_hash(contract) != manifest["contract_hash"]
        or canonical_json_hash(inputs) != contract["input_hash"]
        or canonical_json_hash(read_json(root / "expectations.json")) != contract["expectations_hash"]
        or canonical_json_hash(json.loads((root / "preflight.json").read_text())) != contract["preflight_hash"]):
        raise ValidationError("frozen stage contract/input/oracle/preflight changed")
    sb = inputs["reviewed_source_snapshot"]
    resolver = EvidenceResolver(open_raw_info_store(sb["root"], reviewed_snapshot=sb))
    exchange = LocalRoleExchange(root / "exchange", max_calls=contract["max_local_calls"])
    ledger = ExternalAttemptLedger(root / "unused_external_attempts.json", max_attempts=1, max_total_cost=0.01)
    pending, outcomes = [], []
    for sample in inputs["samples"]:
        path = root / "samples" / sample["sample_id"]
        client = StructuredRoleClient(registration=get_model("independent-subagent"), contract=StageContract(contract),
            workspace=root, ledger=ledger, local_role_exchange=exchange, allow_external=False, environ={})
        try:
            bootstrap = _bootstrap(resolver, sample)
            frozen = next(s for s in json.loads((root / "preflight.json").read_text()) if s["sample_id"] == sample["sample_id"])
            if bootstrap != {k: v for k, v in frozen.items() if k != "sample_id"}:
                raise ValidationError("actual production bootstrap differs from frozen preflight")
            _save_exact(path / "basic_info.json", bootstrap)
            with client.anonymous_case(aliases=tuple(sample["identity"]["identity_aliases"]), company_id=COMPANY, ticker="BMBL"):
                controller = LLMResearchController(client)
                controller.set_evaluation_context(datetime.fromisoformat(sample["prediction_time"]))
                controller.set_request_token_budget(contract["limits"]["max_request_tokens"])
                step = controller.initialize(InformationPlan.from_dict(sample["plan"]), bootstrap["model_context"])
                _save_exact(path / "initial_state.json", {"state": step.value.to_dict(), "metadata": dict(step.metadata),
                    "usage": asdict(step.usage), "request_hashes": client.request_hash_trace})
            outcome = {"sample_id": sample["sample_id"], "status": "accepted_requires_independent_review"}
            _save_exact(path / "outcome.json", outcome)
            outcomes.append(outcome)
        except LocalRoleRequestPending as exc:
            pending.append({"sample_id": sample["sample_id"], **exc.pending})
        except LocalRoleBudgetExhausted as exc:
            outcomes.append({"sample_id": sample["sample_id"], "status": "control_budget_stopped", "error": str(exc)})
            break
        except Exception as exc:
            outcome = {"sample_id": sample["sample_id"], "status": "stage_failed", "error_type": type(exc).__name__, "error": str(exc)}
            atomic_write_json(path / "failure.json", outcome)
            outcomes.append(outcome)
    result = {"fixed_denominator": 2, "outcomes": outcomes, "pending": pending,
        "external_llm_calls": 0, "readonly_data_requests": 0,
        "independent_receipts": len(list((root / "exchange/receipts").glob("*.json"))),
        "actual_model_version": None, "engineering_mvp_closed": False}
    atomic_write_json(root / "progress.json", result)
    return result


def main():
    """Run one explicit prepare or resume operation with network disabled."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expectations", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.prepare and args.expectations is None:
        parser.error("--prepare requires separate --expectations")
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network forbidden in reviewed initial stage")
    socket.socket = forbidden
    print(json.dumps(prepare(args.root.resolve(), args.expectations.resolve()) if args.prepare else resume(args.root.resolve()), indent=2))


if __name__ == "__main__":
    main()
