"""Independent synthetic runner boundary checks; no real prepare/execute/source open."""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
RUNNER = BASE / "native/run_native.py"
EXPECTED = "5ebe26fa354cdeb7057e5c95556b61c5aaab419686e34cc080a705bac141b9e8"
assert hashlib.sha256(RUNNER.read_bytes()).hexdigest() == EXPECTED
spec = importlib.util.spec_from_file_location("independent_financial9", RUNNER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert not m.OUTPUT.exists()
checks = []
with TemporaryDirectory() as temporary:
    root = Path(temporary).resolve()
    with m.bounded_operations(), patch.object(m.ReviewedRawInfoStore, "refresh", return_value=0):
        bound = {"store_type": "reviewed", "root": str(root / "uncreated"), "manifest_sha256": "a" * 64}
        store = m.ReviewedRawInfoStore(bound)
        assert not (root / "uncreated").exists() and store._documents == {}
        try:
            m.RawInfoStore(root=root / "forbidden")
        except RuntimeError:
            pass
        else:
            raise AssertionError("persistent root not blocked")
        assert not (root / "forbidden").exists()
    checks.append("native ReviewedStore constructor empty-parent connection; no filesystem source open")
    stage = root / "stage"
    stage.mkdir()
    plan = {"output": str(stage), "head": m.head(), "source_bindings": [], "code_bindings": [],
            "limits": {"batches": 1, "signal_calls": 9, "model_calls": 0, "network_calls": 0, "label_reads": 0}}
    plan["plan_hash"] = m.canonical_json_hash(plan)
    m.write_new(stage / "plan.json", plan)
    m.write_new(stage / "result.json", {"status": "completed_acceptance_failed", "passed_unique": 6})
    m.write_new(stage / "completed-files.json", m.tree(stage))
    with patch.object(m, "OUTPUT", stage), patch.object(m.SignalExecutor, "execute_batch", side_effect=AssertionError("must not execute")):
        actual = m.restore(stage)
        assert actual["new_batches"] == 0 and actual["result"]["status"] == "completed_acceptance_failed"
        m.write_new(stage / "consumer-projections/completed-files.json", {"unexpected": True})
        try:
            m.restore(stage)
        except ValueError as error:
            assert "inventory differs" in str(error)
        else:
            raise AssertionError("nested seal basename bypass")
    checks.append("completed acceptance failure readback zero execution; added nested seal basename rejected")

oracle = {"signal_ref": "synthetic:v1", "oracle_status": "sufficient_unique", "expected_state": "neutral",
          "unit": "dimensionless ratio", "expected_numeric": {"decimal": "0.25"},
          "measurement_period": {"start": None, "end": "2024-12-31"},
          "operands": [{"document_id": "source", "literal": '{"value":10}', "fact": {"tag": "Cash", "value": 10}}],
          "numeric_comparison_policy": {"raw_numeric_absolute_tolerance": "1e-12"}}
result = {"execution": {"status": "success"}, "state": {"value": "neutral"},
          "measurement": {"value": 0.25, "unit": "ratio", "period": {"start": None, "end": "2024-12-31"}},
          "evidence": {"supporting": [{"document_id": "source", "exact_span": '{"value":10}'}], "counter": []}}
assert m.compare(oracle, result)["passed"] is True
for mutation in (
    {**result, "measurement": {**result["measurement"], "value": "0.25"}},
    {**result, "measurement": {**result["measurement"], "unit": "months"}},
    {**result, "evidence": {"supporting": [{"document_id": "foreign", "exact_span": '{"value":10}'}]}},
    {**result, "evidence": {"supporting": [{"document_id": "source", "exact_span": 'prefix {"value":10}'}]}},
):
    assert m.compare(oracle, mutation)["passed"] is False
assert m.compare({"signal_ref": "ambiguous:v1", "oracle_status": "period_policy_ambiguous"}, result)["passed"] is None
checks.append("full operand tuple/literal and numeric/unit positive, four negative mutations, ambiguity record-only")
assert not m.OUTPUT.exists() and hashlib.sha256(RUNNER.read_bytes()).hexdigest() == EXPECTED
report = {"status": "PASS_bounded_runner_preflight", "runner_sha256": EXPECTED,
          "controls_sha256": hashlib.sha256((BASE / "native/safety_controls.py").read_bytes()).hexdigest(),
          "independent_checks": checks, "formal_stage_exists": False,
          "static_findings": [
              "Fixed output and oracle file+canonical authority before write; historical source/code separation; current code/spec frozen separately.",
              "One irreversible execute marker before native batch; all native results persisted before oracle acceptance; failures never retried and two ambiguous rows record-only.",
              "Actual selected resolutions/fingerprints are retained, but equality with old selected source IDs/order is not an acceptance assertion. Must independently audit actual batch after execution before claiming exact old selection.",
              "Read-only restore hashes files/directories, excludes exact root seal only, never invokes batch. This is not OS-crash or research recovery."],
          "limits": "Synthetic temp fixtures only; constructor refresh mocked. No actual prepare/execute/native financial batch/real source Store/GET/model/LabelStore/append. Driver10safe read but not rerun."}
output = BASE / "independent/native-preflight-review.json"
output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": report["status"], "review_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))
