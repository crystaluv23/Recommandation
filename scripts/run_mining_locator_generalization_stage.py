#!/usr/bin/env python3
"""Freeze and inspect two distinct existing sources through native local Mining."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import run_mining_taxonomy_consumer_stage as module
from diagnose_executed_answer_scope import binding, read_json
from stock_opportunity_agent.models import ValidationError

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "runs/diagnostics/mining_locator_generalization_20261023_v1"
SPEC = REPO / "spec/scripts/run_mining_locator_generalization_stage.md"
SAMPLES = ("a", "b")
PREFLIGHT = BASE / "preflight-v2"
TARGETS = (("case-001", "1179.json", "CashFlowsFromUsedInOperatingActivities"),
           ("case-002", "0770.json", "NetCashProvidedByUsedInOperatingActivities"))
_base_build = module.build_controller
_base_code = module.code_bindings


def authorities():
    """Keep the existing first two opaque Discovery cases and source instances."""
    inventory = read_json(module.INVENTORY)
    wire = inventory["sources"]["first_native_manifest_wire"]
    binding(Path(wire["path"]), wire["sha256"])
    view = json.loads(next(m["content"] for m in read_json(Path(wire["path"]))["messages"] if m["role"] == "user"))
    snapshot = inventory["sources"]["reviewed_snapshot"]
    binding(Path(snapshot["path"]), snapshot["sha256"])
    inputs = {}
    for key, (ref, filename, concept) in zip(SAMPLES, TARGETS):
        row = next(r for r in inventory["dev8"] if r["case_ref"] == ref)
        source = row["first2_noquery_financial_documents"][0]["file"]
        if Path(source["path"]).name != filename or view["case_prediction_times"][ref] != row["cutoff"]:
            raise ValidationError("existing source/cutoff authority differs")
        binding(Path(source["path"]), source["sha256"])
        label = view["label_map"][ref]
        if label not in {"positive", "control"}:
            raise ValidationError("invalid existing opaque group")
        inputs[key] = {"case_id": row["case_id"], "case_ref": ref,
            "company_id": row["case_id"].split(":", 1)[0], "cutoff": row["cutoff"],
            "label": label, "concept": concept, "snapshot": snapshot, "expected_source": source,
            "scope": "controlled target-query historical normalized source; no latest/primary-filing claim"}
    sources = [binding(module.INVENTORY), binding(Path(wire["path"]))]
    sources += [binding(p) for p in sorted(Path(snapshot["path"]).parent.rglob("*.json"))]
    return inputs, sources


def code_bindings():
    """Bind the reused module, new driver and changed projection tests/spec."""
    rows = _base_code()
    rows += [binding(Path(__file__)), binding(REPO / "tests/test_mining_query_projection.py"),
        binding(REPO / "tests/test_mining_comparison_progress.py"),
        binding(REPO / "tests/test_source_coordinate_identity.py"),
        binding(REPO / "spec/src/stock_opportunity_agent/research/evolution_transport.md")]
    return rows


def build_controller(root, sample, client):
    """Use the existing targeted fetch; keep all native effects/accounting."""
    controller = _base_build(root, sample, client, controlled_query=sample["concept"])
    # Independently inspect selected documents in this controlled preparation;
    # subsequent selectors and authors never receive a private fact/ref table.
    expected = read_json(Path(sample["expected_source"]["path"]))
    documents = {d.document_id: d for result in controller._documents.values() for d in result.documents}
    if set(documents) != {expected["document_id"]}:
        raise ValidationError("targeted fetch selected a different source instance")
    return controller


def visible_operand(payload, concept, role):
    """Select a next ref exclusively from the current actual request."""
    page = payload.get("comparison_progress", {})
    if page.get("snapshot_status") == "current":
        for unit in page["items"]:
            if unit["concept"] == concept:
                return next(row[role][ref]["fact_ref"] for row in unit["groups"].values()
                    for ref in sorted(row[role]))
    raise ValidationError("current wire does not expose target operand locator")


def preflight():
    """Capture exact native inputs and all next-ref choices without receiving."""
    destination = PREFLIGHT
    if destination.exists():
        raise ValidationError("preflight is single-entry")
    destination.mkdir()
    with module.guards():
        inputs, sources = authorities()
        code = code_bindings()
        reservations = {}
        for key in SAMPLES:
            root = destination / key
            sample = inputs[key]
            controller = build_controller(root, sample,
                module.make_client(root, sample, {"limits": module.LIMITS}, input_only=True))
            reservations[key] = []
            for step in range(4):
                before = set((root / "requests").glob("*.json"))
                try:
                    controller.model.next_action(controller._model_view())
                except module.InputCaptured:
                    pass
                else:
                    raise ValidationError("preflight crossed receive boundary")
                added = set((root / "requests").glob("*.json")) - before
                if len(added) != 1:
                    raise ValidationError("unexpected native request count")
                request_path = added.pop()
                request = read_json(request_path)["request"]
                payload = json.loads(next(m["content"] for m in request["messages"] if m["role"] == "user"))
                if step == 0:
                    action = {"action": "compare_groups", "concepts": [sample["concept"]]}
                elif step < 3:
                    action = {"action": "read_span", "fact_ref": visible_operand(payload, sample["concept"],
                        "latest" if step == 1 else "comparable_prior")}
                else:
                    action = {"action": "record_deferred"}
                    if len(payload.get("structured_read_progress", {}).get("items", [])) != 2:
                        raise ValidationError("final request lacks two complete read receipts")
                action["rationale"] = ["Deterministic current-wire-only preflight, not an author answer."]
                module.save(root, f"selector-{step + 1:03}", {"request": binding(request_path), "action": action})
                reservations[key].append(module.request_reservation(request_path))
                if step < 3:
                    controller._validate_action_shape(action)
                    controller._execute(action["action"], action)
        module.check_bindings(sources + code)
        if list(destination.rglob("inbox/*.json")):
            raise ValidationError("preflight prepared a production inbox")
        module.save(destination, "result", {"state": "all_steps_input_only", "source_files": sources,
            "code_files": code, "samples": list(SAMPLES), "reservations": reservations,
            "production_answers": 0, "inboxes": 0, "external_API": 0, "new_business_labels": 0})
    return {"state": "preflight_complete", "reservations": reservations, "inboxes": 0}


def configure():
    """Route reused helpers only to this new process-local destination."""
    module.BASE, module.ROOT, module.SPEC = BASE, BASE / "stage", SPEC
    module.SAMPLES = SAMPLES
    module.authorities, module.code_bindings, module.build_controller = authorities, code_bindings, build_controller


def main():
    """Prepare/advance the two fixed controls without dispatching an agent."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preflight", "prepare", "advance"))
    parser.add_argument("--sample", choices=SAMPLES, default="a")
    args = parser.parse_args()
    configure()
    value = preflight() if args.operation == "preflight" else module.prepare(preflight_root=PREFLIGHT) if args.operation == "prepare" else module.advance(args.sample)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
