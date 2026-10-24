"""A real late inherited-file mutation must never publish repaired versions."""
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
    with tempfile.TemporaryDirectory(dir=OUT, prefix="late-failure-") as temp:
        root = Path(temp) / "case"
        with driver.guards():
            plan = driver.prepare_at(root)
            registry = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            path = root / "registry/market/price_momentum_126d/versions/v2/tests.json"
            prior = path.read_bytes(); fired = []
            def fault(stage, ref):
                if stage == "after_stable_admission" and ref == "revenue_growth_yoy:v4":
                    path.write_bytes(prior + b" "); fired.append(ref)
            registry._fault_injector = fault
            try: registry.capability_repair(plan, plan_hash=canonical_json_hash(plan))
            except ValidationError as exc: error = str(exc)
            else: raise AssertionError("Late inherited mutation published")
            assert fired and registry.version == 12
            assert not list((root / "candidates").rglob("promotion.json"))
            reopened = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            try: reopened.freeze()
            except ValidationError: blocked = True
            else: raise AssertionError("Late failed output readable")
            path.write_bytes(prior)
            transition = reopened.capability_repair(plan, plan_hash=canonical_json_hash(plan))
            assert transition.output_version == 13 and len(reopened.freeze().specs) == 18
    for row in code: assert driver.binding(row["path"]) == row
    result = {"schema_version": "independent-late-output-failure-probe-v1", "late_mutation_rejected": error,
              "failed_version": 12, "promotion_markers_before_recovery": 0, "prepared_reads_blocked": blocked,
              "restored_exact_recovery_version": 13, "code_files": code,
              "limit": "Real late file drift is rejected by permitted-byte guard before capability audit; this does not claim an injected failure inside the audit implementation.",
              "formal_destination_touched": False}
    (OUT / "late-failure-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("late_mutation_rejected", "failed_version", "restored_exact_recovery_version")}, indent=2))


if __name__ == "__main__": main()
