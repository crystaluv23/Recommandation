"""Historical repaired fixtures must still match their bound candidate hash."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile

from successor_addition_probe import driver, ordinary, OUT
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import SignalRegistry
from review_support import assert_original_unchanged


def main():
    code = driver.code_bindings()
    with tempfile.TemporaryDirectory(dir=OUT, prefix="historical-fixture-") as temp:
        root = Path(temp) / "case"
        with driver.guards():
            plan = driver.prepare_at(root)
            registry = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            registry.capability_repair(plan, plan_hash=canonical_json_hash(plan))
            spec = registry.load_spec("cash_reserves:v3")
            ordinary(registry, replace(spec, version=4), registry.load_tests(spec.ref), "historical-fixture-ordinary-update")
            path = root / "registry/financial/cash_reserves/versions/v3/tests.json"
            row = driver.read(path); body = json.loads(row["tests"][0]["documents"][0]["content"])
            body["facts"][0]["value"] += 1
            row["tests"][0]["documents"][0]["content"] = json.dumps(body, sort_keys=True, separators=(",", ":"))
            path.write_text(json.dumps(row))
            fresh = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            try:
                snapshot = fresh.freeze()
                fresh_read_accepted = True; error = None; version = snapshot.version
            except ValidationError as exc:
                fresh_read_accepted = False; error = str(exc); version = None
            try:
                fresh.load_research_status("cash_reserves:v3")
                old_status_rejected = False; old_error = None
            except ValidationError as exc:
                old_status_rejected = True; old_error = str(exc)
    for bound in code: assert driver.binding(bound["path"]) == bound
    assert_original_unchanged()
    result = {"schema_version": "independent-historical-fixture-lineage-probe-v1",
              "ordinary_fresh_read_accepted_changed_repaired_historical_fixture": fresh_read_accepted,
              "version": version, "read_error": error, "direct_old_status_rejected": old_status_rejected,
              "old_status_error": old_error, "code_files": code, "original_198_unchanged": True,
              "formal_destination_touched": False}
    name = sys.argv[1] if len(sys.argv) > 1 else "historical-fixture-before-fix.json"
    (OUT / name).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("ordinary_fresh_read_accepted_changed_repaired_historical_fixture", "version", "direct_old_status_rejected", "old_status_error")}, indent=2))


if __name__ == "__main__": main()
