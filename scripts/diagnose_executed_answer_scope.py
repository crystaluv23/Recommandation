#!/usr/bin/env python3
"""Preview or execute two isolated Reflect stages; never run a research cycle."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    ExecutionTrajectory, InformationPlan, ResearchDecision, ResearchState, RuntimeStopReason, SignalRound,
    _assemble_final_context, _mask_identity_values, _research_state_delta,
)
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController, _plan_critic_trajectory
from stock_opportunity_agent.research.evolution_research_validation import (
    _validate_research_state_refs, validate_need_dispositions,
)
from stock_opportunity_agent.research.evolution_transport import (
    ExternalAttemptLedger, ExternalRequestPending, StructuredRoleClient,
)

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "runs/cold_start/minimal_rounds_v182_integrated"
REPORT = REPO / "reports/v182-executed-answer-scope-contract-review-20261007.json"
CONTENT_REPORT = REPO / "reports/v182-bumble-pair-content-and-future-source-audit-20261007.json"
CASE_ID = "cik_0001830043:20250930"
SAMPLES = (("plan_r0001_c01", 19, 20), ("plan_r0001_c02", 257, 258))
MODEL = "deepseek-v4-flash"
MAX_ATTEMPTS = 8
MAX_COST = 0.25
MAX_REQUEST_TOKENS = 131072
PRESERVED_PAYLOAD_FIELDS = (
    "research_state", "signal_batch", "signal_evidence_ref_catalog", "evaluation_context",
    "evaluation_anchor", "reflection_runtime", "computed_metrics", "executed_selection_intents",
    "signal_research_status", "reflection_skill",
)


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object without interpreting any source text as instructions."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"expected JSON object: {path}")
    return value


def file_hash(path: Path) -> str:
    """Return the exact byte identity of one saved source or code file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path, expected: str | None = None) -> dict[str, str]:
    """Bind a current original to its prior audit hash when one was recorded."""
    digest = file_hash(path)
    if expected is not None and digest != expected:
        raise ValidationError(f"original artifact changed: {path}")
    return {"path": str(path.resolve()), "sha256": digest}


@dataclass(frozen=True)
class StageContract:
    """Stage-only identity using the production transport's hash/limit interface."""

    record: Mapping[str, Any]

    @property
    def limits(self) -> Mapping[str, Any]:
        """Expose only limits actually consumed by the guarded transport."""
        return self.record["limits"]

    @property
    def contract_hash(self) -> str:
        """Bind the complete diagnostic contract, distinct from a cohort run."""
        return canonical_json_hash(self.record)


class BoundedReflectClient(StructuredRoleClient):
    """Use the real transport while allowing only initial Reflect and one correction."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.logical_calls = 0

    def complete_json(self, **kwargs: Any):
        """Reject other stages or additional calls before any request can be sent."""
        allowed = {"research_controller_reflect"} if not self.logical_calls else {
            "research_controller_reflect_correction", "research_controller_reflect_patch_mechanics_correction"}
        if self.logical_calls >= 2 or kwargs.get("stage") not in allowed:
            raise ValidationError("diagnostic permits one initial Reflect and one native correction")
        self.logical_calls += 1
        return super().complete_json(**kwargs)


def _source_inputs() -> tuple[dict[str, Any], list[dict[str, str]]]:
    report = read_json(REPORT)
    content_report = read_json(CONTENT_REPORT)
    originals = [binding(REPORT), binding(CONTENT_REPORT)]
    for name in ("state.json", "cycle_state.json", "input_manifest.json", "run_contract.json",
                 "attempts.json", "experiments/round-0001/checkpoint.json"):
        expected = report.get(name.removesuffix(".json") + "_sha256")
        originals.append(binding(SOURCE / name, expected))
    if (read_json(SOURCE / "state.json").get("last_completed_round") != 1
            or read_json(SOURCE / "cycle_state.json").get("last_completed_cycle") != 1
            or read_json(SOURCE / "cycle_state.json").get("active_cycle") is not None):
        raise ValidationError("source is not the audited completed v182 cycle")
    attempts = {row["attempt_id"]: row for row in read_json(SOURCE / "attempts.json")["attempts"]}
    audited = {row["attempt_id"]: row for row in content_report["inspected_original_attempts"]}
    source_rows = content_report["verified_bound_source_files"]
    for row in source_rows:
        originals.append(binding(Path(row["source_path"]), row["sha256"]))
    frozen = read_json(SOURCE / "input_manifest.json")
    case = next(row for rows in frozen["splits"].values() for row in rows if row["case_id"] == CASE_ID)
    cases = []
    for plan_id, initial_attempt, terminal_attempt in SAMPLES:
        old = report["bumble_owning_validator_and_fallback_replay"]["plans"][plan_id]
        trajectory_path = SOURCE / "experiments/trajectories" / plan_id / f"{CASE_ID}.json"
        originals.append(binding(trajectory_path, old["trajectory_file_sha256"]))
        trajectory = read_json(trajectory_path)["trajectory"]
        plan_path = SOURCE / "plans" / plan_id / "record.json"
        originals.append(binding(plan_path))
        plan = read_json(plan_path)["plan"]
        payloads = {}
        original_requests = []
        for attempt_id in (initial_attempt, terminal_attempt):
            row = audited[attempt_id]
            if attempts[attempt_id]["status"] != "completed" or attempts[attempt_id]["request_hash"] != row["request_hash"]:
                raise ValidationError("original completed attempt does not match audited request")
            request_path = SOURCE / "requests" / f"{row['request_hash']}.json"
            response_path = SOURCE / "cache/responses" / f"{row['request_hash']}.json"
            request_ref = binding(request_path, row["request_file_sha256"])
            response_ref = binding(response_path, row["response_cache_file_sha256"])
            originals.extend((request_ref, response_ref))
            original_requests.append({"attempt_id": attempt_id, "request": request_ref, "response": response_ref,
                                      "role": "initial_reflect" if attempt_id == initial_attempt else "later_terminal_patch"})
            payloads[attempt_id] = json.loads(read_json(request_path)["request"]["messages"][1]["content"])
        payload, terminal = payloads[initial_attempt], payloads[terminal_attempt]
        if payload["reflection_skill"] != plan["reflection_skill"]:
            raise ValidationError("original Reflect skill does not match committed Plan")
        if (payload["reflection_runtime"] != {"must_finalize": False, "termination_trigger": None}
                or terminal["reflection_runtime"] != {"must_finalize": True, "termination_trigger": "budget_exhausted"}
                or terminal["executed_selection_intents"] or terminal["research_state"]["decision"] != "continue"):
            raise ValidationError("original initial/closure runtime is not the audited production sequence")
        for key in ("computed_metrics", "evaluation_context", "evaluation_anchor"):
            if terminal.get(key) != payload.get(key):
                raise ValidationError(f"original closure changed frozen context: {key}")
        masked_batches = [re.sub(r"\[ANON_ID_\d+\]", "[ANON_ID]", json.dumps(row["signal_batch"], sort_keys=True))
                          for row in (payload, terminal)]
        if masked_batches[0] != masked_batches[1]:
            raise ValidationError("original closure changed the executed batch beyond anonymous placeholder numbering")
        prior = ResearchState.from_dict(trajectory["initial_state"])
        round_row = SignalRound.from_dict(trajectory["signal_rounds"][0])
        guidance = next(row for row in round_row.selections if row.signal_ref == "guidance_acceleration:v3")
        target_index = guidance.target_need_indices[0]
        if prior.next_information_needs[target_index] != old["actual_need"]:
            raise ValidationError("original targeted need differs from audited scope defect")
        cases.append({
            "sample_id": plan_id, "case_id": CASE_ID, "company_id": trajectory["company_id"],
            "prediction_time": trajectory["prediction_time"], "identity": case["basic_info"],
            "plan": plan, "prior_state": prior.to_dict(), "signal_round": round_row.to_dict(),
            "target_need_index": target_index, "target_need": prior.next_information_needs[target_index],
            "original_requests": original_requests,
            "original_final_state_is_later_than_initial_reflect": True,
            "original_trajectory": binding(trajectory_path),
            "reflection_runtime": payload["reflection_runtime"],
            "closure_runtime": terminal["reflection_runtime"],
            "closure_estimate_state": prior.to_dict(),
            "original_terminal_prior_payload_hash": canonical_json_hash(terminal["research_state"]),
            "evaluation_context": payload["evaluation_context"],
            "evaluation_anchor": payload.get("evaluation_anchor"),
            "computed_metrics": payload.get("computed_metrics", []),
            "computed_metric_cards": trajectory["final_context"].get("computed_metrics", []),
            "signal_research_status": payload.get("signal_research_status", {}),
            "basic_info": trajectory["basic_info_bundle"],
            "prediction_baseline": trajectory["final_context"]["prediction_baseline"],
            "excluded_tools": ["document_catalog", "fetch_documents", "compute"],
            "original_catalog_sha256": canonical_json_hash(payload.get("document_catalog", {})),
            "original_initial_context": {key: payload.get(key) for key in PRESERVED_PAYLOAD_FIELDS},
        })
    return {"schema_version": "executed-answer-scope-inputs-v1", "samples": cases}, originals


def _code_bindings() -> list[dict[str, str]]:
    paths = list((REPO / "src/stock_opportunity_agent").rglob("*.py"))
    paths += [Path(__file__), REPO / "scripts/run_minimal_rounds.py", REPO / "pyproject.toml",
              REPO / "spec/scripts/diagnose_executed_answer_scope.md"]
    return [binding(path) for path in sorted(set(paths))]


def _readable_identity(cards: list[dict[str, Any]]) -> list[tuple[str, Counter]]:
    """Compare exact visible clauses while tolerating saved dictionary key ordering."""
    result = []
    for card in cards:
        if set(card) != {"readable"} or not isinstance(card["readable"], str):
            raise ValidationError("unexpected computed readable card shape")
        title, clauses = card["readable"].split(": ", 1)
        result.append((title, Counter(clauses.split("; "))))
    return result


def _controller(client: BoundedReflectClient, sample: Mapping[str, Any], *, closure: bool = False) -> LLMResearchController:
    controller = LLMResearchController(client)
    controller.set_request_token_budget(MAX_REQUEST_TOKENS)
    controller.set_evaluation_context(datetime.fromisoformat(sample["prediction_time"]))
    controller.set_evaluation_anchor(sample["evaluation_anchor"])
    if controller.evaluation_context != sample["evaluation_context"]:
        raise ValidationError("production evaluation context differs from original request")
    controller.set_computed_metrics(sample["computed_metric_cards"])
    if _readable_identity(controller.computed_metrics) != _readable_identity(sample["computed_metrics"]):
        raise ValidationError("saved computed cards differ from original visible metrics")
    # Preserve the original visible order after verifying every clause through the setter.
    controller.computed_metrics = list(sample["computed_metrics"])
    controller.set_signal_research_status(sample["signal_research_status"])
    runtime = sample["closure_runtime" if closure else "reflection_runtime"]
    controller.set_reflection_runtime_context(
        selections=() if closure else SignalRound.from_dict(sample["signal_round"]).selections,
        must_finalize=runtime["must_finalize"],
        termination_trigger=RuntimeStopReason(runtime["termination_trigger"]) if runtime["termination_trigger"] else None,
    )
    return controller


def _reflect(client: BoundedReflectClient, sample: Mapping[str, Any], *,
             state: ResearchState | None = None, closure: bool = False):
    identity = sample["identity"]
    aliases = tuple(identity.get("identity_aliases", ())) + (str(identity.get("company_name", "")),)
    with client.anonymous_case(aliases=aliases, company_id=sample["company_id"], ticker=identity.get("ticker", "")):
        return _controller(client, sample, closure=closure).reflect(
            InformationPlan.from_dict(sample["plan"]), state or ResearchState.from_dict(sample["prior_state"]),
            SignalRound.from_dict(sample["signal_round"]).batch,
        )


def _compare_original_request(request: Mapping[str, Any], sample: Mapping[str, Any]) -> dict[str, bool]:
    """Check the actual new wire payload against saved inputs modulo opaque token numbering."""
    payload = json.loads(request["messages"][1]["content"])

    def identity(value: Any) -> str:
        return re.sub(r"\[ANON_ID_\d+\]", "[ANON_ID]", json.dumps(value, sort_keys=True))

    compared = {key: identity(payload.get(key)) == identity(sample["original_initial_context"][key])
                for key in PRESERVED_PAYLOAD_FIELDS}
    if not all(compared.values()):
        changed = ", ".join(key for key, matches in compared.items() if not matches)
        raise ValidationError(f"new initial request differs from the original executed context: {changed}")
    return compared


def preview(root: Path) -> dict[str, Any]:
    """Freeze exact originals and real production initial requests without credentials or I/O."""
    root = root.resolve()
    if root.exists() or any((parent / "run_contract.json").exists() or (parent / "diagnostic_contract.json").exists()
                            for parent in root.parents):
        raise ValidationError("preview requires a new isolated directory outside every existing run")
    inputs, originals = _source_inputs()
    registration = get_model(MODEL)
    contract_record = {
        "schema_version": "executed-answer-scope-stage-contract-v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "separately_authorized_reflect_stage_only", "input_hash": canonical_json_hash(inputs),
        "model": registration.to_public_dict(), "max_external_attempts": MAX_ATTEMPTS, "max_total_cost": MAX_COST,
        "limits": {"max_structured_corrections": 1, "structured_reasoning_token_reserve": 0,
                   "max_request_tokens": MAX_REQUEST_TOKENS, "max_samples": 2,
                   "max_reflect_invocations_per_sample": 2, "max_calls_per_invocation": 2},
        "forbidden": ["full_cycle", "prediction", "posthoc_model", "provider_acquisition", "goal_resume", "tool_exchange"],
    }
    manifest = {
        "schema_version": "executed-answer-scope-diagnostic-v1", "input_hash": canonical_json_hash(inputs),
        "contract_hash": canonical_json_hash(contract_record), "code_files": _code_bindings(), "original_files": originals,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "source_pit_accepted": False, "research_acceptance_closed": False,
    }
    root.mkdir(parents=True, exist_ok=False)
    atomic_write_json(root / "inputs.json", inputs)
    atomic_write_json(root / "diagnostic_contract.json", contract_record)
    ledger = ExternalAttemptLedger(root / "attempts.json", max_attempts=MAX_ATTEMPTS, max_total_cost=MAX_COST)
    initial_requests = []
    closure_estimates = []
    for sample in inputs["samples"]:
        for closure in (False, True):
            client = BoundedReflectClient(registration=registration, contract=StageContract(contract_record),
                                          workspace=root, ledger=ledger, allow_external=False, environ={})
            try:
                _reflect(client, sample, closure=closure,
                         state=ResearchState.from_dict(sample["closure_estimate_state"]) if closure else None)
            except ExternalRequestPending as pending:
                request = read_json(pending.request_path)["request"]
                preserved = {} if closure else _compare_original_request(request, sample)
                body_bytes = request.get("wire_request", {}).get("body_bytes", len(json.dumps(request["messages"]).encode()))
                cost = (body_bytes * registration.default_input_cost_per_million_tokens
                        + request["max_output_tokens"] * registration.default_output_cost_per_million_tokens) / 1_000_000
                (closure_estimates if closure else initial_requests).append({
                    "sample_id": sample["sample_id"], "request_hash": pending.request_hash,
                    "kind": "initial_prior_state_closure_estimate" if closure else "exact_initial_request",
                    "preserved_original_context": preserved,
                    "file": binding(pending.request_path), "conservative_reserved_cost": cost})
            else:
                raise ValidationError("preview unexpectedly returned a model result")
    manifest["initial_requests"] = initial_requests
    manifest["closure_estimates"] = closure_estimates
    manifest["manifest_hash"] = canonical_json_hash(manifest)
    atomic_write_json(root / "manifest.json", manifest)
    return {"status": "preview_ready", "root": str(root), "manifest_hash": manifest["manifest_hash"],
            "external_attempts": ledger.summary["attempt_count"], "initial_requests": initial_requests,
            "closure_estimates": closure_estimates,
            "estimated_four_invocations_plus_equal_size_corrections": 2 * sum(
                row["conservative_reserved_cost"] for row in initial_requests + closure_estimates),
            "cost_basis": "existing registered conservative rates; not invoice or current quote"}


def verify_preview(root: Path, acknowledged_hash: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reject altered code, inputs or originals before environment loading or execution."""
    manifest = read_json(root / "manifest.json")
    digest = manifest.pop("manifest_hash", None)
    if digest != acknowledged_hash or canonical_json_hash(manifest) != digest:
        raise ValidationError("diagnostic manifest is changed or unacknowledged")
    contract = read_json(root / "diagnostic_contract.json")
    inputs = read_json(root / "inputs.json")
    if canonical_json_hash(contract) != manifest["contract_hash"] or canonical_json_hash(inputs) != manifest["input_hash"]:
        raise ValidationError("diagnostic frozen contract or input bundle changed")
    if contract["max_external_attempts"] != MAX_ATTEMPTS or contract["max_total_cost"] != MAX_COST or len(inputs["samples"]) != 2:
        raise ValidationError("diagnostic ceilings or sample denominator changed")
    if _code_bindings() != manifest["code_files"]:
        raise ValidationError("diagnostic code inventory changed; create a new preview")
    for row in [*manifest["code_files"], *manifest["original_files"],
                *(row["file"] for row in manifest["initial_requests"] + manifest["closure_estimates"])]:
        binding(Path(row["path"]), row["sha256"])
    if (root / "execution_started.json").exists() or (root / "result.json").exists():
        raise ValidationError("diagnostic was already executed; resuming or repeating it is forbidden")
    if read_json(root / "attempts.json")["attempts"]:
        raise ValidationError("preview ledger is not empty")
    return contract, inputs


def _load_execution_environment() -> None:
    """Invoke the established local loader only after all execution checks pass."""
    spec = importlib.util.spec_from_file_location("diagnostic_existing_loader", REPO / "scripts/run_minimal_rounds.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._load_env()


def _load_stage(root: Path, sample: Mapping[str, Any], prior: ResearchState, *, closure: bool = False):
    """Revalidate saved model state and metadata through the owning production validators."""
    stage = "terminal_closure" if closure else "initial_reflect"
    result = read_json(root / "samples" / sample["sample_id"] / f"{stage}.json")
    state = ResearchState.from_dict(result["state"])
    disposition = result["metadata"].get("need_dispositions")
    if (not isinstance(disposition, dict) or set(disposition) != {"prior_state_hash", "items"}
            or disposition["prior_state_hash"] != canonical_json_hash(prior.to_dict())):
        raise ValidationError("saved disposition does not bind the exact prior ResearchState")
    items = disposition["items"]
    if not isinstance(items, list):
        raise ValidationError("saved disposition items must be an array")
    rows = []
    for item in items:
        if not isinstance(item, dict) or "prior_need" not in item:
            raise ValidationError("saved disposition omitted prior need identity")
        index = item.get("need_index")
        if (not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(prior.next_information_needs)
                or item["prior_need"] != prior.next_information_needs[index]):
            raise ValidationError("saved disposition occurrence differs from prior state")
        rows.append({key: value for key, value in item.items() if key != "prior_need"})
    round_row = SignalRound.from_dict(sample["signal_round"])
    selections = () if closure else round_row.selections
    checked = _validate_research_state_refs(
        state, phase="reflect", previous_state=prior, selections=selections,
        batch=round_row.batch, need_dispositions=rows, must_finalize=closure,
        evaluation_context=sample["evaluation_context"],
    )
    normalized = validate_need_dispositions(
        rows, previous_state=prior, state=state, selections=selections,
        batch=round_row.batch, evaluation_context=sample["evaluation_context"],
    )
    if checked.to_dict() != state.to_dict() or list(normalized) != rows:
        raise ValidationError("saved state or disposition is not the accepted normalized form")
    return state, {"round": 1, "delta": _research_state_delta(prior, state),
                   "need_dispositions": disposition}


def assemble_consumers(root: Path, sample: Mapping[str, Any]) -> dict[str, Any]:
    """Reload both saved stages and construct actual production consumer views."""
    prior = ResearchState.from_dict(sample["prior_state"])
    initial, delta = _load_stage(root, sample, prior)
    deltas = [delta]
    state = initial
    if initial.decision is ResearchDecision.CONTINUE:
        state, closure_delta = _load_stage(root, sample, initial, closure=True)
        deltas.append(closure_delta)
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
    assembled = replace(original, initial_state=prior, final_state=state, state_deltas=tuple(deltas), final_context=context)
    critic = _plan_critic_trajectory(assembled, case_index=1)
    raw_expected = [{"round": row["round"], "need_dispositions": row["need_dispositions"]} for row in deltas]
    aliases = (sample["company_id"], *sample["identity"].get("identity_aliases", ()), *(
        str(value) for key, value in sample["basic_info"].items()
        if key in {"company_id", "company_name", "ticker", "symbol"} and value is not None))
    expected = _mask_identity_values(raw_expected, aliases)
    context_projection = [{"round": row.get("round"), "need_dispositions": row.get("need_dispositions")}
                          for row in context.get("state_evolution", ())]
    target = sample["target_need"]
    target_rows = [row for row in delta["need_dispositions"]["items"] if row["need_index"] == sample["target_need_index"]]
    retained = (target in state.next_information_needs and target not in state.resolved_questions
                and len(target_rows) == 1 and target_rows[0]["answer_scope"] == "unanswered")
    selected = {index for row in SignalRound.from_dict(sample["signal_round"]).selections
                if row.reason_code == "answer_need" for index in row.target_need_indices}
    untargeted = Counter(need for index, need in enumerate(prior.next_information_needs) if index not in selected)
    retained_others = not (untargeted - Counter(state.next_information_needs))
    checks = {"target_not_falsely_resolved": retained, "untargeted_needs_preserved": retained_others,
              "terminal_state_finalized": state.decision is ResearchDecision.FINALIZE,
              "disposition_survives_final_context": context_projection == expected,
              "disposition_survives_posthoc": compact.get("state_evolution") == expected,
              "disposition_survives_critic": critic.get("state_evolution") == raw_expected}
    artifact = {"kind": "stageassembly", "actual_prediction_executed": False, "actual_posthoc_executed": False,
                "actual_critic_executed": False, "critic_prediction_and_labels_are_historical_only": True,
                "final_state": state.to_dict(), "state_deltas": deltas, "final_context": context,
                "compact_posthoc": compact, "critic_trajectory": critic, "checks": checks}
    path = root / "consumers" / f"{sample['sample_id']}.json"
    atomic_write_json(path, artifact)
    reloaded = read_json(path)
    if reloaded != artifact:
        raise ValidationError("persisted consumer assembly changed on reload")
    return reloaded["checks"]


def execute(root: Path, acknowledged_hash: str) -> dict[str, Any]:
    """Execute a verified one-shot stage diagnostic under independent hard ceilings."""
    root = root.resolve()
    contract, inputs = verify_preview(root, acknowledged_hash)
    with (root / "execution_started.json").open("x", encoding="utf-8") as marker:
        json.dump({"started_at": datetime.now(timezone.utc).isoformat(), "manifest_hash": acknowledged_hash}, marker)
    _load_execution_environment()
    ledger = ExternalAttemptLedger(root / "attempts.json", max_attempts=MAX_ATTEMPTS, max_total_cost=MAX_COST)
    outcomes = []
    for sample in inputs["samples"]:
        traces = []
        try:
            state = ResearchState.from_dict(sample["prior_state"])
            for closure in (False, True):
                client = BoundedReflectClient(registration=get_model(MODEL), contract=StageContract(contract), workspace=root,
                                              ledger=ledger, allow_external=True,
                                              acknowledged_contract_hash=canonical_json_hash(contract))
                try:
                    step = _reflect(client, sample, state=state, closure=closure)
                finally:
                    traces.extend(client.request_hash_trace)
                stage = "terminal_closure" if closure else "initial_reflect"
                atomic_write_json(root / "samples" / sample["sample_id"] / f"{stage}.json",
                                  {"kind": "new_reflect_stage", "stage": stage,
                                   "state": step.value.to_dict(), "metadata": dict(step.metadata),
                                   "usage": asdict(step.usage), "request_hashes": client.request_hash_trace})
                state = step.value
                if state.decision is not ResearchDecision.CONTINUE:
                    break
            checks = assemble_consumers(root, sample)
            outcomes.append({"sample_id": sample["sample_id"], "passed": all(checks.values()), "checks": checks,
                             "request_hashes": traces})
        except Exception as exc:
            # Provider failures already have production raw diagnostics; never echo credential-bearing exceptions.
            outcomes.append({"sample_id": sample["sample_id"], "passed": False, "failure_type": type(exc).__name__,
                             "request_hashes": traces})
    result = {"schema_version": "executed-answer-scope-result-v1", "scope": "reflect_stage_and_local_consumer_assembly",
              "passed": len(outcomes) == 2 and all(row["passed"] for row in outcomes), "samples": outcomes,
              "usage": ledger.summary, "source_pit_accepted": False, "research_acceptance_closed": False,
              "finished_at": datetime.now(timezone.utc).isoformat()}
    atomic_write_json(root / "result.json", result)
    return result


def main() -> int:
    """Run only an explicit preview or acknowledged isolated stage execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "execute"):
        sub = commands.add_parser(name)
        sub.add_argument("--root", type=Path, required=True)
        if name == "execute":
            sub.add_argument("--acknowledge-manifest", required=True)
    args = parser.parse_args()
    result = preview(args.root) if args.command == "preview" else execute(args.root, args.acknowledge_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("passed") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
