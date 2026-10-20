"""Locate one exact eligible FTI daily window in already-bound cache roots only."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.state import RawCacheKey

ROOT = Path(__file__).resolve().parents[3]
PARENT = Path(__file__).resolve().parent


def bound(path):
    """Bind a local input without changing it."""
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    """Check fixed request identities; do not acquire or materialize anything."""
    output = PARENT / "fti-market-window-local-check.json"
    assert not output.exists(), "This bounded check is terminal."
    inventory_path = ROOT / "runs/diagnostics/frozen40_source_completion_20261020_v1/local-cache-chain-inventory.json"
    inventory_binding = bound(inventory_path)
    assert inventory_binding["sha256"] == "5bf5a7bbe1c86ef8ca58b7270695eb32b846f64ce306fedaf42f3ed88f1eeb9a"
    inventory = json.loads(inventory_path.read_bytes())
    case = next(row for row in inventory["cases"] if row["company_id"] == "cik_0001681459")
    assert case["ticker"] == "FTI" and case["prediction_time"] == "2025-05-30T00:00:00+00:00"
    cohort_plan = ROOT / "runs/diagnostics/reviewed_frozen_case_inputs_20261020_v1/stage/plan.json"
    assert bound(cohort_plan)["sha256"] == "20ee4d2f386a237fbeacfedfbe32dbd0406310166cb5f7b4f48014e391645696"
    definitions = []
    for group in json.loads(cohort_plan.read_bytes())["groups"]:
        for binding in group["definition_bindings"]:
            if not binding["path"].endswith("/spec.json") or "/market/" not in binding["path"]:
                continue
            assert bound(binding["path"]) == binding
            spec = json.loads(Path(binding["path"]).read_bytes())
            assert spec["signal_id"] in {"max_drawdown_1y", "price_momentum_126d"}
            assert spec["raw_retrieval"]["lookback_days"] == 400
            definitions.append({"registry_group": group["name"], "spec": binding,
                "signal_id": spec["signal_id"], "version": spec["version"],
                "raw_retrieval": spec["raw_retrieval"]})
    assert len(definitions) == 4
    cutoff = datetime.fromisoformat(case["prediction_time"]).astimezone(timezone.utc)
    start, end = cutoff.date() - timedelta(days=400), cutoff.date() - timedelta(days=1)
    url = ("https://api.massive.com/v2/aggs/ticker/FTI/range/1/day/" + start.isoformat()
        + "/" + end.isoformat() + "?adjusted=true&sort=asc&limit=50000")
    key = RawCacheKey.from_request("massive", DataCapability.PRICE_DAILY, "GET", url)
    directories = sorted({str(Path(binding["path"]).parent)
        for binding in inventory["read_file_bindings"]
        if "/cache/data/massive/price_daily/" in binding["path"]})
    probes = [str(Path(directory) / (key.digest + ".json")) for directory in directories]
    matches = [bound(path) for path in probes if Path(path).is_file()]
    for binding in matches:
        cache = json.loads(Path(binding["path"]).read_bytes())
        assert cache["source_key"] == "massive" and cache["capability"] == "price_daily"
        assert cache["endpoint"] == key.endpoint and cache["params"] == [list(pair) for pair in key.params]
    value = {"scope": "Original FTI identity/cutoff and both exact Registry market definitions; bounded direct-path cache check only.",
        "case": {name: case[name] for name in ("case_id", "company_id", "ticker", "split", "prediction_time")},
        "inputs": [inventory_binding, bound(cohort_plan)], "definitions": definitions,
        "request": {"method": "GET", "endpoint": key.endpoint,
            "query": {k: v for k, v in key.params if k != "method"}, "cache_key": key.digest},
        "lookback_days": 400, "native_date_bounds": {"start": start.isoformat(), "end": end.isoformat()},
        "cache_directories_checked": directories, "direct_paths_checked": probes, "matches": matches,
        "conclusion": "exact_cache_candidates_located" if matches else "exact_cache_unlocated_in_checked_roots",
        "next_step": "Verify each retained exact response, or freeze one new daily GET; derive issuer/latest-bar and split-interval proofs from its actual result before qualification.",
        "no_original_trimming_or_retiming": True, "network_requests": 0, "models": 0,
        "global_store_or_append": False, "labels_or_mixed_manifest_read": False}
    atomic_write_json(output, value)
    print(json.dumps({"checked_directories": len(directories), "exact_matches": len(matches),
        "request_start": start.isoformat(), "request_end": end.isoformat(), "output": bound(output)}))


if __name__ == "__main__":
    main()
