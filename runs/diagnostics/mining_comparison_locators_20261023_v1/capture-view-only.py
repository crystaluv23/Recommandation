"""Offline actual-source next-locator and native-budget proof; never dispatch a role."""
from copy import deepcopy
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
from unittest.mock import patch

import run_mining_taxonomy_consumer_stage as stage
from diagnose_executed_answer_scope import binding
from tests.test_mining_comparison_progress import visible_operand


BASE = Path(__file__).resolve().parent
ROOT = BASE / "native-view-only"
if ROOT.exists():
    raise AssertionError("single entry; do not overwrite proof")
ROOT.mkdir()


def capture(root, sample, roles):
    """Each selected action depends only on that exact current native payload."""
    client = stage.make_client(root, sample, {"limits": stage.LIMITS}, input_only=True)
    controller = stage.build_controller(root, sample, client)
    rows = []
    for step in range(4):
        previous = set((root / "requests").glob("*.json"))
        try:
            controller.model.next_action(controller._model_view())
        except stage.InputCaptured:
            pass
        except stage.LocalRoleBudgetExhausted as error:
            stage.save(root, "budget-stop", {"step": step + 1, "reason": str(error)})
            return {"state": "blocked_by_original_budget", "completed_inputs": rows}
        else:
            raise AssertionError("crossed input-only boundary")
        added = set((root / "requests").glob("*.json")) - previous
        assert len(added) == 1
        request_path = added.pop()
        request = json.loads(request_path.read_text())["request"]
        payload = json.loads(next(m["content"] for m in request["messages"] if m["role"] == "user"))
        # Read only the current wire object. No ref from an earlier iteration,
        # controller private state, source document or independent oracle is used.
        if step == 0:
            action = {"action": "compare_groups", "concepts": [sample["concept"]]}
        elif step < 3:
            action = {"action": "read_span", "fact_ref": visible_operand(payload, sample["concept"], roles[step - 1])}
        else:
            action = {"action": "record_deferred"}
            assert len(payload["structured_read_progress"]["items"]) == 2
        action["rationale"] = ["Explicit deterministic offline locator test; not a model answer."]
        stage.save(root, f"selected-{step + 1:03}", {"input": binding(request_path),
            "action": action, "selector_source": "only current native payload"})
        wire = json.dumps(request["messages"], ensure_ascii=False)
        identities = (sample["company_id"], sample["case_id"], "0000800457", "GPRE", "Green Plains")
        assert all(value not in wire for value in identities)
        rows.append({"step": step + 1, "reservation": stage.request_reservation(request_path),
            "request": binding(request_path), "action": action["action"], "identity_strings_absent": True})
        if step < 3:
            controller._validate_action_shape(action)
            controller._execute(action["action"], action)
    stage.save(root, "final-view", controller._model_view())
    stage.save(root, "final-ledger", controller.ledger.to_dict())
    assert not list(root.rglob("inbox/*.json"))
    return {"state": "four_inputs_reachable_within_original_budget", "inputs": rows,
        "total_reservation": sum(r["reservation"] for r in rows), "heavy_used": controller._heavy_used,
        "domain_terminal_executed": False}


with stage.guards():
    inputs, sources = stage.authorities()
    sample = inputs["actual"]
    code = [binding(Path(stage.__file__)), binding(Path(__file__)),
        binding(Path("src/stock_opportunity_agent/research/mining_controller.py")),
        binding(Path("src/stock_opportunity_agent/research/mining_role_model.py")),
        binding(Path("tests/test_mining_comparison_progress.py"))]
    stage.save(ROOT, "source-and-code-before", {"sources": sources, "code": code})
    results = {}
    for name, roles in (("current-first", ("latest", "comparable_prior")),
                        ("prior-first", ("comparable_prior", "latest"))):
        results[name] = capture(ROOT / name, sample, roles)
        # Throwaway deterministic reconstruction, not a reentry of any old stage.
        results[name + "-reconstructed"] = capture(ROOT / (name + "-reconstructed"), sample, roles)
        for file in ("final-view.json", "final-ledger.json"):
            left, right = ROOT / name / file, ROOT / (name + "-reconstructed") / file
            if left.exists():
                assert left.read_bytes() == right.read_bytes()
    # Exact previous implementation must lose the semantic mapping after one read.
    old_path = ROOT / "before-controller.py"
    old_source = subprocess.check_output(["git", "show", "341b94a5:src/stock_opportunity_agent/research/mining_controller.py"])
    with old_path.open("xb") as stream:
        stream.write(old_source)
    name = "stock_opportunity_agent.research._before_comparison_locators"
    spec = importlib.util.spec_from_file_location(name, old_path)
    old = importlib.util.module_from_spec(spec)
    sys.modules[name] = old
    spec.loader.exec_module(old)
    with patch.object(stage, "LabelAwareMiningController", old.LabelAwareMiningController):
        controller = stage.build_controller(ROOT / "old-negative", sample, object())
        controller._execute_compare({"action": "compare_groups", "concepts": [sample["concept"]], "rationale": ["Offline old negative."]})
        controller._read_fact_span({"action": "read_span", "fact_ref": visible_operand(controller._model_view(), sample["concept"], "latest"),
            "rationale": ["Offline old negative."]})
        try:
            visible_operand(controller._model_view(), sample["concept"], "comparable_prior")
        except LookupError:
            results["old-negative"] = {"lost_mapping_after_first_read": True, "implementation": binding(old_path)}
        else:
            raise AssertionError("old negative unexpectedly retained locator")
    stage.check_bindings(sources)
    stage.check_bindings(code)
    assert not list(ROOT.rglob("inbox/*.json"))
    result = {"scope": "offline controlled real-source view-only request-ready capture; not fresh semantic obedience",
        "limits": stage.LIMITS, "results": results, "inboxes": 0, "model_answers": 0,
        "external_API": 0, "new_business_labels": 0, "source_and_code_unchanged": True,
        "old_fixed_production_result": "1/2 unchanged; no old stage advanced or budget reset"}
    stage.save(ROOT, "result", result)
print(json.dumps({k: {field: value for field, value in v.items() if field in
    ("state", "total_reservation", "heavy_used", "lost_mapping_after_first_read")}
    for k, v in result["results"].items()}))
