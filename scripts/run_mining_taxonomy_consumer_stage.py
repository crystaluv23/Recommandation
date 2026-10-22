#!/usr/bin/env python3
"""Inspect two frozen fact-source controls through native local Mining roles."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import json
import socket
import traceback
from unittest.mock import patch

from diagnose_executed_answer_scope import StageContract, binding, read_json
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedRawInfoStore, open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import EvolutionControlFlow
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleBudgetExhausted, LocalRoleExchange, LocalRoleRequestPending, _immutable
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "runs/diagnostics/mining_taxonomy_consumer_20261023_v1"
ROOT = BASE / "stage"
SPEC = REPO / "spec/scripts/run_mining_taxonomy_consumer_stage.md"
INVENTORY = REPO / "runs/diagnostics/mining_positive_frontier_20261021_v1/oracle/static-inventory.json"
NAMESPACE = REPO / "runs/diagnostics/mining_fact_semantics_repair_20261021_v1/root/namespace-before.json"
SAMPLES = ("actual", "namespace")
LIMITS = {"max_request_tokens": 32768, "max_case_tokens": 98304,
    "max_local_role_calls": 6, "max_structured_corrections": 1,
    "structured_reasoning_token_reserve": 0}
ENVELOPE = (
    " Module execution envelope: this is controlled inspection of one already-fetched "
    "structured source, not candidate discovery or a complete research comparison. "
    "The initial fetch was controlled by the diagnostic and is not your autonomous "
    "retrieval. Inspect the target concept {concept}: its source operands, periods "
    "and measurement identity; establish what comparison is supported and what "
    "remains unestablished within the fetched historical scope. Allowed actions "
    "are read_span with fact_ref only, compare_groups, compute_statistic, and "
    "record_deferred. Do not propose a candidate, claim catalog coverage, or fetch "
    "more documents in this module. You choose the refs and order of actions. "
    "When inspection is sufficient, send record_deferred with a rationale describing "
    "the established facts and uncertainties. The diagnostic intercepts that intent "
    "before executing a domain terminal; it denotes module stop, not evidence "
    "unavailability or no-pattern. Do not invent budget exhaustion."
)


class InputCaptured(EvolutionControlFlow):
    """Stop a local preflight before cache receive/inbox creation."""


class InspectionComplete(EvolutionControlFlow):
    """Save a stop intent without creating a domain verdict."""


class EffectRejected(EvolutionControlFlow):
    """Reject effects outside the read-only module envelope."""


def save(root, name, value):
    """Write one exact immutable diagnostic record."""
    _immutable(root / (name + ".json"), value)


def forbidden(*_args, **_kwargs):
    """Reject acquisition, labels, publication and Signal execution."""
    raise EffectRejected("module forbids external effects/labels/Signal execution")


@contextmanager
def guards():
    """Permit only constructor-owned in-memory synthetic source appends."""
    native_append = RawInfoStore.append
    def append_memory(self, document):
        if self.root is not None:
            forbidden()
        return native_append(self, document)
    with ExitStack() as stack:
        for owner, name in ((socket, "create_connection"), (socket.socket, "connect"),
                (socket.socket, "connect_ex"), (LabelStore, "__init__"), (LabelStore, "load"),
                (LabelStore, "ground_truth"), (LabelStore, "record"), (ReviewedRawInfoStore, "append"),
                (SignalRegistry, "freeze"), (SignalRegistry, "register_stable"),
                (SignalExecutor, "execute_batch"), (SignalExecutor, "prepare_inputs"),
                (ExternalAttemptLedger, "reserve")):
            stack.enter_context(patch.object(owner, name, forbidden))
        stack.enter_context(patch.object(RawInfoStore, "append", append_memory))
        yield


def code_bindings():
    """Bind all production modules and the current stage contract/tests."""
    paths = [*sorted((REPO / "src").rglob("*.py")), Path(__file__), SPEC,
        REPO / "scripts/diagnose_executed_answer_scope.py",
        REPO / "spec/src/stock_opportunity_agent/research/signal_mining_agent.md",
        REPO / "tests/test_mining_fact_read_progress.py", REPO / "tests/test_mining_taxonomy.py",
        REPO / "tests/test_mining_taxonomy_consumer_stage.py"]
    return [binding(path) for path in paths]


def check_bindings(rows):
    """Reject drift without rewriting any frozen receipt."""
    for row in rows:
        binding(Path(row["path"]), row["sha256"])


def authorities():
    """Import only prior opaque Discovery metadata and the original source view."""
    inventory = read_json(INVENTORY)
    source = inventory["sources"]["first_native_manifest_wire"]
    binding(Path(source["path"]), source["sha256"])
    inbox = read_json(Path(source["path"]))
    old_view = json.loads(next(m["content"] for m in inbox["messages"] if m["role"] == "user"))
    metadata = next(row for row in inventory["dev8"] if row["case_ref"] == "case-008")
    ref = metadata["case_ref"]
    if old_view["case_prediction_times"][ref] != metadata["cutoff"]:
        raise ValidationError("opaque Discovery cutoff changed")
    label = old_view["label_map"][ref]
    if label not in {"positive", "control"}:
        raise ValidationError("invalid imported runtime group")
    snapshot = dict(inventory["sources"]["reviewed_snapshot"])
    binding(Path(snapshot["path"]), snapshot["sha256"])
    original = read_json(NAMESPACE)
    inputs = {"actual": {"case_id": metadata["case_id"], "case_ref": ref,
        "company_id": metadata["case_id"].split(":", 1)[0], "cutoff": metadata["cutoff"],
        "label": label, "concept": "NetCashProvidedByUsedInOperatingActivities",
        "snapshot": snapshot, "scope": "controlled historical source; not latest retrieval"},
        "namespace": {"case_id": "synthetic-namespace-control", "case_ref": "synthetic",
            "company_id": "probe-issuer", "cutoff": original["facts"][0]["available_at"],
            "label": "control", "concept": "Metric", "content": original["content"],
            "scope": "explicitly synthetic namespace counterexample; not a business label"}}
    sources = [binding(INVENTORY), binding(NAMESPACE), binding(Path(source["path"]))]
    sources += [binding(p) for p in sorted(Path(snapshot["path"]).parent.rglob("*.json"))]
    return inputs, sources


def request_reservation(path):
    """Use the same logical message-byte plus output allowance as local transport."""
    request = read_json(path)["request"]
    return len(json.dumps(request["messages"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()) + request["max_output_tokens"]


def make_client(root, sample, contract, *, input_only=False):
    """Use exact native requests and enforce per-sample aggregate reservations."""
    def observe(event):
        if event.get("event_type") != "request_ready":
            return
        if event["stage"] != "mining_controller_step":
            raise EffectRejected("unexpected native stage")
        prepared = sorted((root / "requests").glob("*.json"))
        if request_reservation(Path(event["request_path"])) > LIMITS["max_request_tokens"]:
            raise LocalRoleBudgetExhausted("sample single-request logical reservation exhausted")
        if len(prepared) > LIMITS["max_local_role_calls"]:
            raise LocalRoleBudgetExhausted("sample prepared-request ceiling exhausted")
        if sum(request_reservation(p) for p in prepared) > LIMITS["max_case_tokens"]:
            raise LocalRoleBudgetExhausted("sample aggregate logical reservation exhausted")
        if input_only:
            save(root, "ready-" + event["request_hash"], event)
            raise InputCaptured()
    class Client(StructuredRoleClient):
        module_decisions = 0

        def complete_json(self, **kwargs):
            self.module_decisions += 1
            if self.module_decisions > LIMITS["max_local_role_calls"]:
                raise LocalRoleBudgetExhausted("sample native decision ceiling exhausted before prepare")
            kwargs["system_prompt"] += ENVELOPE.format(concept=sample["concept"])
            kwargs["max_request_tokens"] = min(
                LIMITS["max_request_tokens"], kwargs.get("max_request_tokens") or LIMITS["max_request_tokens"])
            return super().complete_json(**kwargs)
    return Client(registration=get_model("independent-subagent"), contract=StageContract(contract),
        workspace=root, ledger=ExternalAttemptLedger(root / "unused_external.json", max_attempts=1, max_total_cost=.01),
        local_role_exchange=LocalRoleExchange(root / "exchange", max_calls=6),
        allow_external=False, environ={}, on_progress=observe)


def build_controller(root, sample, client):
    """Construct the real Controller and execute the declared controlled fetch."""
    if "snapshot" in sample:
        snap = sample["snapshot"]
        store = open_raw_info_store(Path(snap["path"]).parent, reviewed_snapshot={
            "root": str(Path(snap["path"]).parent), "store_type": "reviewed", "manifest_sha256": snap["sha256"]})
    else:
        clock = datetime.fromisoformat(sample["cutoff"])
        document = RawInfoDocument.create(document_id="namespace-control-only", company_id=sample["company_id"],
            source_type="sec_company_facts", published_at=clock, available_at=clock, content=sample["content"])
        store = RawInfoStore(documents=(document,))
    # Only this existing opaque runtime label supplies the constructor's default;
    # no new outcome magnitude or real issuer label is authored here.
    case = SimpleNamespace(case_id=sample["case_id"], company_id=sample["company_id"],
        prediction_time=datetime.fromisoformat(sample["cutoff"]),
        ground_truth=SimpleNamespace(is_surge=sample["label"] == "positive"))
    aliases = (sample["case_id"], sample["company_id"])
    inner = MiningAgentRoleModel(client, identity_aliases=aliases, max_output_tokens=2000)
    class RecordingModel:
        def __init__(self):
            self.calls = 0
        def next_action(self, view):
            self.calls += 1
            save(root, f"view-{self.calls:03}", view)
            action = inner.next_action(view)
            save(root, f"action-{self.calls:03}", action)
            return action
    class Controller(LabelAwareMiningController):
        def _execute(self, action, raw):
            if action == "record_deferred":
                save(root, "boundary", {"assembled_intent": dict(raw), "view": self._model_view(),
                    "ledger": self.ledger.to_dict(), "facts": [asdict(f) for f in self._facts.values()],
                    "relations": [asdict(r) for r in self._relations.values()],
                    "native_domain_terminal_executed": False})
                raise InspectionComplete()
            if action not in {"read_span", "compare_groups", "compute_statistic"} or (
                    action == "read_span" and set(raw) - {"action", "rationale", "fact_ref"}):
                raise EffectRejected("action outside frozen module envelope")
            return super()._execute(action, raw)
    controller = Controller(store=store, model=RecordingModel(), case_pairs=[(sample["case_ref"], case)],
        measurable_evidence_manifest={}, signal_catalog=[], seed="discovery", heavy_action_limit=6,
        label_map={sample["case_ref"]: sample["label"]}, identity_aliases=aliases)
    controlled = {"action": "fetch_evidence", "rationale": ["Controlled module source preparation."],
        "case_refs": [sample["case_ref"]], "source_families": ["sec_company_facts"], "max_documents": 1}
    controller._validate_action_shape(controlled)
    LabelAwareMiningController._execute(controller, "fetch_evidence", controlled)
    save(root, "controlled-fetch", {"action": controlled, "receipt": controller._last_action_result,
        "facts": [asdict(f) for f in controller._facts.values()], "ledger": controller.ledger.to_dict()})
    return controller


def preflight():
    """Capture every target read/comparison request without any model receive."""
    destination = BASE / "preflight"
    if destination.exists():
        raise ValidationError("preflight is single-entry")
    destination.mkdir()
    with guards():
        inputs, sources = authorities()
        for key in SAMPLES:
            sample = inputs[key]
            root = destination / key
            root.mkdir()
            client = make_client(root, sample, {"limits": LIMITS}, input_only=True)
            controller = build_controller(root, sample, client)
            facts = [f for f in controller._facts.values() if f.concept == sample["concept"]]
            if len(facts) != 2:
                raise ValidationError("preflight requires the two source operands")
            actions = [{"action": "read_span", "fact_ref": f.fact_ref, "rationale": ["Controlled local wiring probe."]} for f in facts]
            actions += [{"action": "compare_groups", "concepts": [sample["concept"]], "rationale": ["Controlled local comparison."]},
                {"action": "record_deferred", "rationale": ["Controlled module boundary only."]}]
            for index, action in enumerate(actions, 1):
                view = controller._model_view()
                save(root, f"wire-input-{index}", view)
                try:
                    controller.model.next_action(view)
                except InputCaptured:
                    pass
                else:
                    raise ValidationError("preflight crossed model receive")
                if index < len(actions):
                    controller._validate_action_shape(action)
                    controller._execute(action["action"], action)
            page = controller._model_view()["structured_read_progress"]
            if len(page["items"]) != 2 or not page["selection_is_exhaustive"]:
                raise ValidationError("two complete operands did not survive comparison")
        check_bindings(sources)
        if list(destination.rglob("inbox/*.json")):
            raise ValidationError("preflight created production inbox")
        save(destination, "result", {"state": "all_steps_input_only", "source_files": sources,
            "code_files": code_bindings(), "samples": list(SAMPLES), "production_answers": 0,
            "inboxes": 0, "external_API": 0, "new_business_labels": 0})
    return {"state": "preflight_complete", "samples": 2, "inboxes": 0}


def prepare():
    """Freeze the independent reference and current inputs before formal inboxes."""
    if ROOT.exists():
        raise ValidationError("formal stage already exists")
    with guards():
        inputs, sources = authorities()
        ready = read_json(BASE / "preflight/result.json")
        check_bindings(ready["code_files"])
        if ready["code_files"] != code_bindings():
            raise ValidationError("preflight code inventory changed; no refreeze")
        check_bindings(ready["source_files"])
        if ready["source_files"] != sources:
            raise ValidationError("preflight source inventory changed; no refreeze")
        references = [binding(p) for p in sorted((BASE / "reference").glob("*")) if p.is_file()]
        if not (BASE / "reference/prefreeze-obligations.json").is_file() or not references:
            raise ValidationError("independent pre-answer reference missing")
        sources += references + [binding(BASE / "preflight/result.json")]
        contract = {"schema_version": "mining-taxonomy-consumer-module-v1", "limits": LIMITS,
            "fixed_denominator": 2, "backend": "independent-subagent", "external_API": 0,
            "scope": "controlled fact-source consumption only; no candidate or domain terminal"}
        manifest = {"inputs_hash": canonical_json_hash(inputs), "contract_hash": canonical_json_hash(contract),
            "source_files": sources, "code_files": code_bindings()}
        manifest["manifest_hash"] = canonical_json_hash(manifest)
        ROOT.mkdir()
        for name, value in (("inputs", inputs), ("contract", contract), ("manifest", manifest)):
            save(ROOT, name, value)
    return {"state": "prepared", "fixed_denominator": 2}


def verify():
    """Reject any source/code/input/contract drift of the prepared stage."""
    manifest = read_json(ROOT / "manifest.json")
    digest = manifest.pop("manifest_hash")
    inputs, contract = read_json(ROOT / "inputs.json"), read_json(ROOT / "contract.json")
    if digest != canonical_json_hash(manifest) or manifest["inputs_hash"] != canonical_json_hash(inputs) or manifest["contract_hash"] != canonical_json_hash(contract):
        raise ValidationError("frozen stage integrity mismatch")
    check_bindings(manifest["source_files"] + manifest["code_files"])
    if manifest["code_files"] != code_bindings():
        raise ValidationError("frozen code inventory changed")
    return inputs, contract


def advance(key):
    """Replay only pending native decisions; completed samples verify seals only."""
    inputs, contract = verify()
    root = ROOT / key
    for name in ("completion", "failure"):
        if (root / (name + ".json")).is_file():
            terminal = read_json(root / (name + ".json"))
            body = {k: v for k, v in terminal.items() if k != "terminal_hash"}
            expected_state = "completed_module_boundary" if name == "completion" else "terminal_module_failure"
            if (terminal.get("terminal_hash") != canonical_json_hash(body)
                    or terminal.get("sample") != key or terminal.get("state") != expected_state):
                raise ValidationError("terminal metadata integrity/shape mismatch")
            check_bindings(terminal["sealed_files"])
            return terminal
    root.mkdir(exist_ok=True)
    controller = None
    try:
        with guards():
            controller = build_controller(root, inputs[key], make_client(root, inputs[key], contract))
            result = controller.run()
            raise EffectRejected("native domain/technical terminal: " + result.terminal_kind)
    except LocalRoleRequestPending as pending:
        verify()
        return {"state": "pending", "sample": key, **pending.pending}
    except InspectionComplete:
        name, value = "completion", {"state": "completed_module_boundary", "sample": key,
            "semantic_acceptance": "requires independent raw-answer/source review", "external_API": 0,
            "receipts": len(list((root / "exchange/receipts").glob("*.json")))}
    except BaseException as error:
        name, value = "failure", {"state": "terminal_module_failure", "sample": key,
            "type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc()}
        if controller is not None:
            save(root, "failed-controller", {"view": controller._model_view(), "ledger": controller.ledger.to_dict()})
    verify()
    value["sealed_files"] = [binding(p) for p in sorted(root.rglob("*")) if p.is_file() and p.name != ".dispatch.lock"]
    value["terminal_hash"] = canonical_json_hash(value)
    save(root, name, value)
    return value


def main():
    """Operate the fixed destination; never dispatch an agent or call an API."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preflight", "prepare", "advance"))
    parser.add_argument("--sample", choices=SAMPLES, default="actual")
    args = parser.parse_args()
    value = preflight() if args.operation == "preflight" else prepare() if args.operation == "prepare" else advance(args.sample)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
