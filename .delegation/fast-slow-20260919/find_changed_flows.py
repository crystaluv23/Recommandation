"""Find accepted reflection need changes carried into the next actual routing call."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = json.loads((root / "attempts.json").read_text())["attempts"]
def request(row):
    key = row["request_hash"]
    envelope = json.loads((root / "requests" / f"{key}.json").read_text())["request"]
    payload = json.loads(next(m["content"] for m in envelope["messages"] if m["role"] == "user"))
    return envelope, payload

found = []
for index, row in enumerate(rows[:-1]):
    current, payload = request(row)
    if not current["stage"].startswith("research_controller_reflect"):
        continue
    cache = root / "cache/responses" / f"{row['request_hash']}.json"
    if not cache.exists():
        continue
    output = json.loads(cache.read_text()).get("json_output", {})
    previous = payload.get("research_state", {}).get("next_information_needs")
    revised = output.get("next_information_needs")
    following, following_payload = request(rows[index + 1])
    if following["stage"] != "signal_retrieval_cards" or previous == revised:
        continue
    next_hash = rows[index + 1]["request_hash"]
    next_cache = root / "cache/responses" / f"{next_hash}.json"
    selected = json.loads(next_cache.read_text()).get("json_output") if next_cache.exists() else None
    found.append({"reflect_attempt": index + 1, "reflect_hash": row["request_hash"],
                  "next_routing_hash": next_hash, "previous": previous, "reflected": revised,
                  "exact_next_input_match": following_payload.get("information_needs") == revised,
                  "next_selection": selected})
print(json.dumps({"attempts": len(rows), "changed_flows": found}, ensure_ascii=False, indent=2))
