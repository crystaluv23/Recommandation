"""Check JSON scalar-type fidelity of applied markers on a disposable clone."""
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
    results = []
    with tempfile.TemporaryDirectory(dir=OUT, prefix="marker-type-") as temp:
        root = Path(temp) / "case"
        with driver.guards():
            plan = driver.prepare_at(root)
            registry = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            registry.capability_repair(plan, plan_hash=canonical_json_hash(plan))
            marker = registry._candidate_spec_path("cash_reserves:v3").parent / "promotion.json"
            original = marker.read_bytes()
            for field, value in (("promoted", 1), ("output_registry_version", 13.0)):
                row = json.loads(original); row[field] = value
                marker.write_text(json.dumps(row))
                try:
                    registry.capability_repair(plan, plan_hash=canonical_json_hash(plan))
                    accepted = True; reason = None
                except ValidationError as exc:
                    assert "frozen implementation changed" not in str(exc)
                    accepted = False; reason = str(exc)
                results.append({"field": field, "value": value, "wrong_json_type_accepted": accepted, "reason": reason})
                marker.write_bytes(original)
    for row in code:
        assert driver.binding(row["path"]) == row
    output = {"schema_version": "independent-marker-scalar-type-probe-v1", "cases": results,
              "code_files": code, "formal_destination_touched": False}
    name = sys.argv[1] if len(sys.argv) > 1 else "marker-type-result.json"
    (OUT / name).write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
