#!/usr/bin/env python3
"""Freeze/resume real routing, retrieval, Signal and Reflect over reviewed SEC inputs."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from datetime import datetime
import json
import re
from pathlib import Path
import socket
from types import SimpleNamespace

from diagnose_executed_answer_scope import StageContract, binding, read_json
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import EvidenceResolver, source_types_compatible
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    ResearchState, ResearchDecision, RuntimeStopReason, SignalRound, default_information_plan, AgentStep,
    InformationPlan, RuntimeLimits, RuntimeBudgetExceeded, _consume_usage,
    _assemble_final_context, _mask_identity_values, _research_state_delta,
    _bounded_runtime_signal_selections, _merge_runtime_signal_batches,
    _finalize_exhausted_research_collection,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController, LLMSignalRetrievalAgent
from stock_opportunity_agent.research.evolution_research_validation import _normalize_research_state_output, _validate_research_state_refs, validate_need_dispositions
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner, _single_llm_signal_projection
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending, LocalRoleBudgetExhausted
from stock_opportunity_agent.signal_library import SignalRegistry, SignalExecutor, LLMSignalBatchInput, SignalExecutionType, FrozenSignalRegistry, _thaw_json


REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "runs/cold_start/minimal_rounds_v182_integrated/signals"
SOURCE_INPUTS = REPO / "runs/diagnostics/reviewed_source_snapshot_20261019_v3/input_manifest.json"
IDENTITY = {"ticker": "BMBL", "company_name": "Bumble Inc.", "identity_aliases": ["Bumble", "Bumble Inc.", "BMBL"]}
COMPANY = "cik_0001830043"


def samples():
    """Declare fact-free neutral sample needs before any independent response."""
    rows = []
    for name, cutoff in (("s01", "2025-09-30T00:00:00+00:00"), ("s02", "2025-07-01T00:00:00+00:00"), ("s03", "2025-09-30T00:00:00+00:00")):
        needs = (["What does the issuer disclose about revenue customer concentration for the three and six months ended June 30, 2025 and 2024?"]
                 if name != "s03" else ["What is the issuer's Q2 2025 revenue guidance, and was it raised or lowered from prior guidance?",
                                           "What is the issuer's Q3 2025 revenue guidance?"])
        needs = [need.rstrip("?") + ", using only disclosures available by " + cutoff + "?" for need in needs]
        controller = LLMResearchController(None)
        controller.set_evaluation_context(datetime.fromisoformat(cutoff))
        prior = ResearchState(next_information_needs=tuple(needs))
        normalized = _normalize_research_state_output(prior.to_dict(), previous_state=prior,
            evaluation_context=controller.evaluation_context, computed_metric_cards=())
        _validate_research_state_refs(prior, phase="reflect", previous_state=prior, basic_info={},
            need_dispositions=[], evaluation_context=controller.evaluation_context)
        if normalized != prior.to_dict():
            raise ValidationError("stage preflight cannot rewrite prior state")
        rows.append({"sample_id": name, "prediction_time": cutoff, "company_id": COMPANY,
            "identity": IDENTITY, "plan": default_information_plan().to_dict(), "prior_state": prior.to_dict(),
            "basic_info": {}, "evaluation_context": controller.evaluation_context,
            "computed_metric_cards": [], "seeded_needs_not_h_init_output": True})
    return rows


def _code_bindings():
    return [binding(path) for path in sorted([*list((REPO / "src").rglob("*.py")), Path(__file__),
        REPO / "scripts/diagnose_executed_answer_scope.py", REPO / "spec/scripts/run_reviewed_signal_stage.md"])]


MEASUREMENT_LIMITS = {"max_request_tokens": 131072, "max_structured_corrections": 1,
    "structured_reasoning_token_reserve": 0, "max_signal_rounds": 1,
    "max_signals_per_round": 4, "max_llm_signals_per_round": 2,
    "max_case_tokens": 512000, "max_case_llm_calls": 8}


def _measurement_snapshot(registry, base, sample):
    """Derive an isolated exact archived version without changing stable manifests."""
    ref = sample["snapshot_ref"]
    replacement = registry.load_spec(ref)
    original = next(spec for spec in base.specs if spec.signal_id == replacement.signal_id)
    if original.ref == ref:
        return base
    specs = tuple(replacement if spec.ref == original.ref else spec for spec in base.specs)
    skills = _thaw_json(base.skills); skills.pop(original.ref, None)
    skill = registry.load_skill(ref)
    if skill is not None:
        skills[ref] = skill
    profiles = _thaw_json(base.learned_profiles); profiles.pop(original.ref, None)
    profiles[ref] = registry.load_learning_profile(ref)
    status = _thaw_json(base.research_status); status.pop(original.ref, None)
    replacement_status = registry.load_research_status(ref)
    if replacement_status:
        status[ref] = replacement_status
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return FrozenSignalRegistry(base.version,
        digest({"version": base.version, "specs": [spec.to_dict() for spec in specs], "skills": skills}),
        specs, skills, profiles,
        digest({"profiles": profiles, "research_status": status} if status else profiles), status)


def _snapshot_binding(snapshot):
    """Expose exact definition and learning identity for every sample inventory."""
    return {"registry_hash": snapshot.registry_hash, "learning_hash": snapshot.learning_hash,
        "registry_refs": [spec.ref for spec in snapshot.specs]}


def _measurement_store(sample):
    """Load only this case's explicitly synthetic immutable documents."""
    documents = tuple(RawInfoDocument.from_dict(read_json(Path(path))) for path in sample["document_paths"])
    if not documents or any(document.company_id != sample["company_id"] for document in documents):
        raise ValidationError("synthetic case documents must belong to their isolated company")
    return RawInfoStore(documents=documents)


def _prepare_measurement(root, expectations, measurement_inputs):
    """Freeze the existing pipeline with isolated synthetic cases and exact archived specs."""
    supplied, expected = read_json(measurement_inputs), read_json(expectations)
    rows = supplied.get("samples", [])
    if (supplied.get("profile") != "synthetic_measurement" or expected.get("profile") != "synthetic_measurement"
        or [row["sample_id"] for row in rows] != ["m01", "m02", "m03"]
        or [row["sample_id"] for row in expected["samples"]] != ["m01", "m02", "m03"]):
        raise ValidationError("synthetic measurement profile requires the fixed three cases")
    registry = SignalRegistry(REGISTRY); base = registry.freeze()
    preflight, snapshots, document_files = [], {}, []
    for sample, ref in zip(rows, ("net_share_retirement_yoy:v3", "net_share_retirement_yoy:v3", "net_share_retirement_yoy:v2")):
        if sample.get("synthetic") is not True or sample["snapshot_ref"] != ref:
            raise ValidationError("synthetic case exact version or source declaration differs")
        cutoff = datetime.fromisoformat(sample["prediction_time"])
        controller = LLMResearchController(None); controller.set_evaluation_context(cutoff)
        prior = ResearchState.from_dict(sample["prior_state"])
        InformationPlan.from_dict(sample["plan"])
        _validate_research_state_refs(prior, phase="reflect", previous_state=prior,
            basic_info={}, need_dispositions=[], evaluation_context=controller.evaluation_context)
        sample["evaluation_context"] = controller.evaluation_context
        sample["basic_info"] = {}
        snapshot = _measurement_snapshot(registry, base, sample)
        snapshots[sample["sample_id"]] = _snapshot_binding(snapshot)
        store = _measurement_store(sample)
        spec = snapshot.load_spec(ref)
        if any(not source_types_compatible((document.source_type,), spec.source_types)
               for document in store.documents):
            raise ValidationError("synthetic fixture source is incompatible with its declared target")
        executor = SignalExecutor(snapshot, store)
        batch = executor.execute_batch((ref,), company_id=sample["company_id"], as_of=cutoff,
            identity=sample["identity"])
        if (any(resolution.status != "resolved" for resolution in batch.resolutions)
                or not batch.results or any(result.value.value == "unavailable" for result in batch.results)):
            raise ValidationError("synthetic control target must be measurable before freeze")
        preflight.append({"sample_id": sample["sample_id"], "source_is_synthetic": True,
            "snapshot": snapshots[sample["sample_id"]], "target_probe": {
                "results": [result.to_dict() for result in batch.results],
                "resolutions": [result.to_dict() for result in batch.resolutions]}})
        document_files.extend(binding(Path(path)) for path in sample["document_paths"])
    inputs = {**supplied, "registry_root": str(REGISTRY), "registry_version": base.version,
        **_snapshot_binding(base), "sample_snapshots": snapshots, "actual_model_version": None}
    contract = {"schema_version": "reviewed-direct-signal-measurement-stage-v1", "profile": "synthetic_measurement",
        "backend": "independent-subagent", "scope": "synthetic seeded needs -> native routing/Signal/ownedReflect/consumers; no labels",
        "fixed_denominator": 3, "max_local_calls": 24, "max_external_api_calls": 0,
        "actual_model_version": None, "model_selection": "inherited_host_default_precise_version_unknown",
        "input_hash": canonical_json_hash(inputs), "expectations_hash": canonical_json_hash(expected),
        "preflight_hash": canonical_json_hash(preflight), "limits": MEASUREMENT_LIMITS}
    if expected.get("limits") != {"max_local_calls": 24, **{k: v for k, v in MEASUREMENT_LIMITS.items() if k != "structured_reasoning_token_reserve"}}:
        raise ValidationError("independent oracle and stage finite limits differ")
    manifest = {"schema_version": "reviewed-direct-signal-stage-freeze-v1", "contract_hash": canonical_json_hash(contract),
        "code_files": _code_bindings(), "originals": [binding(measurement_inputs), binding(expectations),
            *document_files, *[binding(path) for path in sorted(REGISTRY.rglob("*")) if path.is_file()]],
        "full_cycle": False, "market_baseline_present": False, "source_is_synthetic": True}
    manifest["manifest_hash"] = canonical_json_hash(manifest)
    for name, value in (("inputs", inputs), ("expectations", expected), ("preflight", preflight), ("contract", contract), ("manifest", manifest)):
        atomic_write_json(root / (name + ".json"), value)
    return {"manifest_hash": manifest["manifest_hash"], "samples": 3, "registry_refs": len(base.specs), "role_dispatches": 0}


def _request_progress(root, contract, sample_id):
    """Enforce exact single/cumulative logical reservation before cache and dispatch."""
    used = {"llm_calls": 0, "tokens": 0}
    def progress(event):
        if event.get("event_type") != "request_ready":
            return
        request = read_json(Path(event["request_path"]))["request"]
        reservation = len(json.dumps(request["messages"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")) + request["max_output_tokens"]
        limits = contract["limits"]
        if (reservation > limits["max_request_tokens"] or used["tokens"] + reservation > limits["max_case_tokens"]
                or used["llm_calls"] + 1 > limits["max_case_llm_calls"]):
            raise RuntimeBudgetExceeded("Signal stage exact request/case reservation ceiling exceeded: " + sample_id)
        used["tokens"] += reservation; used["llm_calls"] += 1
    return progress


def prepare(root: Path, expectations: Path, *, measurement_inputs: Path | None = None):
    """Freeze exact sources/catalog and a separate independent acceptance oracle."""
    if root.exists():
        raise ValidationError("stage destination must be new")
    if measurement_inputs is not None:
        return _prepare_measurement(root, expectations, measurement_inputs)
    if read_json(expectations).get("profile") == "synthetic_measurement":
        raise ValidationError("synthetic measurement oracle requires explicit measurement inputs")
    frozen_source = read_json(SOURCE_INPUTS)
    source_binding = frozen_source["reviewed_source_snapshot"]
    store = open_raw_info_store(source_binding["root"], reviewed_snapshot=source_binding)
    registry = SignalRegistry(REGISTRY).freeze()
    inputs = {"samples": samples(), "reviewed_source_snapshot": source_binding, "registry_root": str(REGISTRY),
        "registry_version": registry.version, "registry_hash": registry.registry_hash,
        "registry_refs": [spec.ref for spec in registry.specs], "actual_model_version": None}
    expected = read_json(expectations)
    if [row["sample_id"] for row in expected["samples"]] != [row["sample_id"] for row in inputs["samples"]]:
        raise ValidationError("independent oracle must preserve the exact neutral sample denominator")
    for row in expected["samples"]:
        if "raw_quote" in row:
            original = store.load(row["document_id"])
            if (original.content_hash != row["content_hash"]
                or original.content[row["raw_start"]:row["raw_end"]] != row["raw_quote"]):
                raise ValidationError("independent oracle quote differs from complete reviewed original")
    resolver = EvidenceResolver(store)
    preflight = []
    for sample in inputs["samples"]:
        for ref in ("customer_concentration:v2", "guidance_acceleration:v3"):
            spec = registry.load_spec(ref)
            executor = SignalExecutor(registry, store, resolver=resolver)
            resolution = executor.prepare_inputs((ref,), company_id=COMPANY,
                as_of=datetime.fromisoformat(sample["prediction_time"]), identity=IDENTITY)[0]
            documents = resolver.load_documents(resolution, as_of=datetime.fromisoformat(sample["prediction_time"]))
            views, _lineage = _single_llm_signal_projection(LLMSignalBatchInput(spec, documents, registry.skills[ref]))
            preflight.append({"sample_id": sample["sample_id"], "signal_ref": ref, "resolution": resolution.to_dict(),
                "document_ids": [document.document_id for document in documents],
                "production_projection": views, "projection_hash": canonical_json_hash(views)})
    customer_quote = expected["samples"][0]["normalized_quote"]
    for name, required in (("s01", True), ("s02", False)):
        row = next(row for row in preflight if row["sample_id"] == name and row["signal_ref"] == "customer_concentration:v2")
        present = any(customer_quote in re.sub(r"\s+", " ", view["exact_text"]) for view in row["production_projection"])
        if present is not required:
            raise ValidationError("production source projection fails predeclared availability/completeness control")
    contract = {"schema_version": "reviewed-direct-signal-stage-v1", "backend": "independent-subagent",
        "scope": "seeded needs -> production routing/retrieval/Signal/Reflect/terminal/final/posthoc; no H_init/Predictor/cohort cycle",
        "fixed_denominator": 3, "max_local_calls": 36, "max_external_api_calls": 0,
        "actual_model_version": None, "model_selection": "inherited_host_default_precise_version_unknown",
        "input_hash": canonical_json_hash(inputs), "expectations_hash": canonical_json_hash(expected),
        "preflight_hash": canonical_json_hash(preflight), "limits": {"max_request_tokens": 131072,
            "max_structured_corrections": 1, "structured_reasoning_token_reserve": 0, "max_signal_rounds": 1,
            "max_signals_per_round": 4, "max_llm_signals_per_round": 2}}
    manifest = {"schema_version": "reviewed-direct-signal-stage-freeze-v1", "contract_hash": canonical_json_hash(contract),
        "code_files": _code_bindings(), "originals": [binding(SOURCE_INPUTS), binding(expectations),
            *[binding(path) for path in sorted(REGISTRY.rglob("*")) if path.is_file()]],
        "full_cycle": False, "market_baseline_present": False, "expected_model_response_count": None}
    manifest["manifest_hash"] = canonical_json_hash(manifest)
    for name, value in (("inputs", inputs), ("expectations", expected), ("preflight", preflight), ("contract", contract), ("manifest", manifest)):
        atomic_write_json(root / (name + ".json"), value)
    return {"manifest_hash": manifest["manifest_hash"], "samples": 3, "registry_refs": len(registry.specs), "role_dispatches": 0}


def _save_exact(path: Path, value: dict):
    if path.exists():
        existing = read_json(path)
        if {k: v for k, v in existing.items() if k != "usage"} != {k: v for k, v in value.items() if k != "usage"}:
            raise ValidationError("accepted stage artifact differs on validated replay: " + str(path))
    else:
        atomic_write_json(path, value)


def resume(root: Path):
    """Run actual production functions; suspend at each independent local role."""
    manifest = read_json(root / "manifest.json")
    digest = manifest.pop("manifest_hash")
    if canonical_json_hash(manifest) != digest:
        raise ValidationError("stage manifest changed")
    for row in manifest["code_files"] + manifest["originals"]:
        binding(Path(row["path"]), row["sha256"])
    contract, inputs = read_json(root / "contract.json"), read_json(root / "inputs.json")
    if (canonical_json_hash(contract) != manifest["contract_hash"] or canonical_json_hash(inputs) != contract["input_hash"]
        or canonical_json_hash(read_json(root / "expectations.json")) != contract["expectations_hash"]
        or canonical_json_hash(json.loads((root / "preflight.json").read_text())) != contract["preflight_hash"]):
        raise ValidationError("stage frozen contract/input/oracle/preflight changed")
    measurement = contract.get("profile") == "synthetic_measurement"
    sb = inputs.get("reviewed_source_snapshot")
    store = open_raw_info_store(sb["root"], reviewed_snapshot=sb) if sb else None
    registry_source = SignalRegistry(inputs["registry_root"])
    registry = registry_source.freeze()
    if registry.registry_hash != inputs["registry_hash"] or [spec.ref for spec in registry.specs] != inputs["registry_refs"]:
        raise ValidationError("full frozen Registry changed")
    base = registry
    if measurement and registry.learning_hash != inputs["learning_hash"]:
        raise ValidationError("full frozen Registry learning changed")
    exchange = LocalRoleExchange(root / "exchange", max_calls=contract["max_local_calls"])
    ledger = ExternalAttemptLedger(root / "unused_external_attempts.json", max_attempts=1, max_total_cost=0.01)
    pending, outcomes = [], []
    for sample in inputs["samples"]:
        path = root / "samples" / sample["sample_id"]
        client = StructuredRoleClient(registration=get_model("independent-subagent"), contract=StageContract(contract),
            workspace=root, ledger=ledger, local_role_exchange=exchange, allow_external=False, environ={},
            on_progress=_request_progress(root, contract, sample["sample_id"]) if measurement else None)
        try:
            cutoff = datetime.fromisoformat(sample["prediction_time"])
            prior = ResearchState.from_dict(sample["prior_state"])
            company, identity = sample["company_id"], sample["identity"]
            registry = _measurement_snapshot(registry_source, base, sample) if measurement else base
            if measurement and _snapshot_binding(registry) != inputs["sample_snapshots"][sample["sample_id"]]:
                raise ValidationError("isolated sample Registry changed")
            sample_store = _measurement_store(sample) if measurement else store
            resolver = EvidenceResolver(sample_store)
            plan = InformationPlan.from_dict(sample["plan"])
            usage = AgentUsage()
            case_limits = RuntimeLimits(max_tokens=contract["limits"].get("max_case_tokens", 512000),
                max_llm_calls=contract["limits"].get("max_case_llm_calls", 8))
            runner = StructuredLLMSignalRunner(client)
            runner.set_identity_cases((SimpleNamespace(case_id=sample["sample_id"], company_id=company, basic_info=identity),))
            executor = SignalExecutor(registry, sample_store, resolver=resolver, llm_runner=runner)
            aliases = tuple(sample["identity"]["identity_aliases"])
            with client.anonymous_case(aliases=aliases, company_id=company, ticker=identity["ticker"]):
                router = LLMSignalRetrievalAgent(client)
                router.set_evaluation_context(cutoff)
                router.set_deterministic_functions(executor.deterministic_functions)
                router.set_request_token_budget((case_limits.max_tokens - usage.tokens) if measurement else 131072)
                trace_start = len(client.request_hash_trace)
                route = router.select(prior.next_information_needs, registry, {}, research_state=prior)
                if measurement: usage = _consume_usage(usage, route.usage, case_limits)
                _save_exact(path / "routing.json", {"selections": [row.to_dict() for row in route.value], "usage": asdict(route.usage),
                    "request_hashes": client.request_hash_trace[trace_start:]})
                selections = _bounded_runtime_signal_selections(route.value, registry, max_signals=4, max_llm_signals=2)
                _save_exact(path / "executed_portfolio.json", {"bounded_selections": [row.to_dict() for row in selections],
                    "max_signals": 4, "max_llm_signals": 2})
                runner.set_request_token_budget((case_limits.max_tokens - usage.tokens) if measurement else 131072)
                groups = [tuple(row.signal_ref for row in selections if registry.load_spec(row.signal_ref).execution_type is kind)
                    for kind in (SignalExecutionType.DETERMINISTIC, SignalExecutionType.LLM)]
                trace_start = len(client.request_hash_trace)
                batches = [executor.execute_batch(refs, company_id=company, as_of=cutoff, identity=identity) for refs in groups if refs]
                batch = _merge_runtime_signal_batches(tuple(row.signal_ref for row in selections), batches)
                if measurement: usage = _consume_usage(usage, batch.usage, case_limits)
                round_row = SignalRound(information_needs=prior.next_information_needs, selections=selections, batch=batch)
                # Usage differs on cache replay; the original accepted artifact retains it.
                round_dict = round_row.to_dict()
                batch_usage = round_dict["batch"].pop("usage")
                _save_exact(path / "signal_round.json", {"signal_round": round_dict, "usage": batch_usage,
                    "request_hashes": client.request_hash_trace[trace_start:]})
                round_dict["batch"]["usage"] = batch_usage
                trigger = RuntimeStopReason.MAX_SIGNAL_ROUNDS if batch.results else RuntimeStopReason.NO_SIGNAL_MATCH
                runtime = {"must_finalize": True, "termination_trigger": trigger.value,
                    "attempted_signal_rounds": 1, "completed_signal_rounds": int(bool(batch.results)),
                    "signal_calls": batch.signal_calls, "max_signal_rounds": 1}
                _save_exact(path / "runtime.json", runtime)
                controller = LLMResearchController(client)
                controller.set_evaluation_context(cutoff)
                controller.set_request_token_budget((case_limits.max_tokens - usage.tokens) if measurement else 131072)
                controller.set_signal_research_status(registry.research_status)
                controller.set_reflection_runtime_context(selections=selections,
                    must_finalize=True, termination_trigger=trigger)
                trace_start = len(client.request_hash_trace)
                step = (controller.reflect(plan, prior, batch) if batch.results
                    else AgentStep(_finalize_exhausted_research_collection(prior), AgentUsage()))
                if measurement: usage = _consume_usage(usage, step.usage, case_limits)
                _save_exact(path / "reflect.json", {"state": step.value.to_dict(), "metadata": dict(step.metadata), "usage": asdict(step.usage),
                    "request_hashes": client.request_hash_trace[trace_start:],
                    "execution_mode": "not_called_due_to_no_signal_match" if not batch.results else
                        ("not_called_due_to_production_guard" if not step.metadata else "independent_local_role")})
                saved = read_json(path / "reflect.json")
                state = ResearchState.from_dict(saved["state"])
                dispositions = saved["metadata"].get("need_dispositions")
                delta = {"round": 1, "delta": _research_state_delta(prior, state)}
                if dispositions is not None:
                    if dispositions["prior_state_hash"] != canonical_json_hash(prior.to_dict()):
                        raise ValidationError("saved Reflect metadata differs from exact prior")
                    rows = [{key: value for key, value in item.items() if key != "prior_need"} for item in dispositions["items"]]
                    _validate_research_state_refs(state, phase="reflect", previous_state=prior,
                        selections=selections, batch=batch, need_dispositions=rows, must_finalize=True,
                        evaluation_context=controller.evaluation_context)
                    validate_need_dispositions(rows, previous_state=prior, state=state, selections=selections,
                        batch=batch, evaluation_context=controller.evaluation_context)
                    delta["need_dispositions"] = dispositions
                elif state.to_dict() != {**prior.to_dict(), "decision": "finalize"}:
                    raise ValidationError("automatic finalize without metadata may only change decision")
                deltas = [delta]
                context = _assemble_final_context(plan=plan, company_id=company,
                    additional_identity_aliases=aliases, basic_info={}, state=state, rounds=(round_row,) if batch.results else (), prediction_time=cutoff,
                    state_deltas=deltas, signal_research_status=registry.research_status,
                    **({"runtime_termination": {"phase": "prediction_ready", "stop_reason": "finalized",
                        "termination_trigger": trigger.value}} if measurement else {}))
                compact = _compact_posthoc_context(context)
                projection = [{"round": row["round"], "need_dispositions": row["need_dispositions"]} for row in deltas if "need_dispositions" in row]
                expected = _mask_identity_values(projection, (company, *aliases))
                checks = {"finalized": state.decision is ResearchDecision.FINALIZE,
                    "final_disposition_projection_exact": [{"round": row["round"], "need_dispositions": row["need_dispositions"]} for row in context["state_evolution"] if "need_dispositions" in row] == expected,
                    "posthoc_disposition_projection_exact": compact["state_evolution"] == expected}
                _save_exact(path / "consumers.json", {"final_context": context, "posthoc": compact})
                outcome = {"sample_id": sample["sample_id"], "status": "accepted_requires_independent_review", "checks": checks}
                _save_exact(path / "outcome.json", outcome)
                if measurement:
                    _save_exact(path / "case_usage.json", {"usage": asdict(usage), "limits": contract["limits"]})
                outcomes.append(outcome)
        except LocalRoleRequestPending as exc:
            pending.append({"sample_id": sample["sample_id"], **exc.pending})
        except (LocalRoleBudgetExhausted, RuntimeBudgetExceeded) as exc:
            outcomes.append({"sample_id": sample["sample_id"], "status": "control_budget_stopped", "error": str(exc)})
            break
        except Exception as exc:
            outcome = {"sample_id": sample["sample_id"], "status": "stage_failed", "error_type": type(exc).__name__, "error": str(exc)}
            atomic_write_json(path / "failure.json", outcome)
            outcomes.append(outcome)
    result = {"fixed_denominator": 3, "outcomes": outcomes, "pending": pending, "external_api_calls": 0,
        "external_llm_calls": 0, "readonly_data_requests": 0,
        "independent_receipts": len(list((root / "exchange/receipts").glob("*.json"))),
        "actual_model_version": None, "engineering_mvp_closed": False}
    atomic_write_json(root / "progress.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expectations", type=Path)
    parser.add_argument("--measurement-inputs", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network forbidden in reviewed Signal stage")
    socket.socket = forbidden
    if args.prepare and args.expectations is None:
        parser.error("--prepare requires a separately authored --expectations file")
    if args.resume and args.measurement_inputs is not None:
        parser.error("--measurement-inputs is only valid on fresh prepare")
    print(json.dumps(prepare(args.root.resolve(), args.expectations.resolve(), measurement_inputs=args.measurement_inputs.resolve() if args.measurement_inputs else None) if args.prepare else resume(args.root.resolve()), indent=2))


if __name__ == "__main__":
    main()
