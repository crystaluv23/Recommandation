"""Probe a status-only counterfeit terminal marker after a real pre-bump fault."""
import json
from pathlib import Path
import sys
import tempfile

REPO = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts"))
import repair_historical_signal_registry as driver
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import SignalRegistry


def main():
    code = driver.code_bindings()
    with tempfile.TemporaryDirectory(dir=OUT, prefix="status-probe-") as temp:
        root = Path(temp) / "case"
        with driver.guards():
            plan = driver.prepare_at(root)
            registry = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            def fault(stage, ref):
                if stage == "after_repair_output_audit": raise RuntimeError("controlled pre-bump interruption")
            registry._fault_injector = fault
            try: registry.capability_repair(plan, plan_hash=canonical_json_hash(plan))
            except RuntimeError: pass
            else: raise AssertionError("Fault did not fire")
            path = registry.root / ".transitions" / (plan["transition_id"] + ".json")
            row = driver.read(path)
            assert row["status"] == "prepared" and registry.version == 12
            row["status"] = "applied"  # No completed output fields or version publication exists.
            path.write_text(json.dumps(row))
            reopened = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            try:
                snapshot = reopened.freeze()
                normal_read_accepted = True
                normal_read = {"version": snapshot.version, "refs": [s.ref for s in snapshot.specs]}
            except ValidationError as exc:
                normal_read_accepted = False; normal_read = {"error": str(exc)}
            try:
                reopened.capability_repair(plan, plan_hash=canonical_json_hash(plan))
                repair_accepted = True; repair_error = None
            except ValidationError as exc:
                repair_accepted = False; repair_error = str(exc)
    for bound in code: assert driver.binding(bound["path"]) == bound
    result = {"schema_version": "independent-status-only-applied-marker-probe-v1",
              "normal_read_accepted_status_only_applied": normal_read_accepted,
              "normal_read": normal_read, "repair_entry_accepted": repair_accepted,
              "repair_error": repair_error, "code_files": code,
              "formal_destination_touched": False}
    name = sys.argv[1] if len(sys.argv) > 1 else "applied-status-result.json"
    (OUT / name).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("normal_read_accepted_status_only_applied", "normal_read", "repair_entry_accepted", "repair_error")}, indent=2))


if __name__ == "__main__":
    main()
