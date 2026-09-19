"""Read-only acceptance snapshot of a frozen evolution workspace."""
import collections
import decimal
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
def read(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default

rows = read(root / "attempts.json", {}).get("attempts", [])
stages = collections.Counter()
seen = set()
for row in rows:
    key = row.get("request_hash")
    if not key or key in seen:
        continue
    seen.add(key)
    request = read(root / "requests" / f"{key}.json", {}).get("request", {})
    stages[request.get("stage", "unknown")] += 1
failures = []
for path in sorted((root / "experiments").rglob("*.failure.json")):
    value = read(path, {})
    failures.append({"path": str(path), "stage": value.get("stage"),
                     "message": str(value.get("message", ""))[:1500]})
summary = {
    "workspace": str(root),
    "state": read(root / "state.json", {}),
    "cycle_state": read(root / "cycle_state.json", {}),
    "attempts": len(rows),
    "attempt_status_counts": dict(collections.Counter(r.get("status") for r in rows)),
    "actual_cost": str(sum(decimal.Decimal(str(r.get("actual_cost") or 0)) for r in rows)),
    "request_stage_counts": dict(stages),
    "failure_artifacts": failures,
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
