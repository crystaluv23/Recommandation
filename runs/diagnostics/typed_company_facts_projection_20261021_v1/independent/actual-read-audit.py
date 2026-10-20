"""Read saved projections only; do not instantiate or invoke production services."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = Path.cwd()
bindings = {}


def read(path):
    """Bind the exact file before decoding its saved JSON data."""
    path = Path(path)
    raw = path.read_bytes()
    bindings[str(path)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


result = read(BASE / "root/actual-read-result.json")
for path, expected in result["bindings"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    bindings[path] = expected
prior = read("runs/diagnostics/default_llm_financial_read_20261021_v1/driver/result.json")
matrix = read("runs/diagnostics/measurement_input_selection_20261021_v1/default_v6.json")
saved = next(row for row in matrix["rows"] if row["signal_ref"] == "cash_to_current_liabilities_ratio:v1")
assert [d["document_id"] for d in saved["resolution"]["documents"]] == prior["native_selected_order"]
documents = {}
for path in result["bindings"]:
    if "/snapshot/documents/" in path:
        document = read(path)
        assert hashlib.sha256(document["content"].encode()).hexdigest() == document["content_hash"]
        documents[document["document_id"]] = document
q1 = documents["rawcap:v1:64c9e4f193885e37ae497a75841bec6dec372f9fddf1ef7649710c28c40fc902"]
body = json.loads(q1["content"])
expected = {tag: next(f for f in body["facts"] if f["tag"] == tag and f["end"] == "2025-03-31" and f["unit"] == "USD")
            for tag in ("CashAndCashEquivalentsAtCarryingValue", "LiabilitiesCurrent")}
assert expected["CashAndCashEquivalentsAtCarryingValue"]["value"] == 98610000
assert expected["LiabilitiesCurrent"]["value"] == 325735000
details = {}
for mode in ("native", "counter"):
    rows = read(BASE / f"root/{mode}-projection.json")
    selected = prior[mode + "_selected_order"]
    assert len(selected) == 10 and len(set(selected)) == 10
    assert sum(len(r["exact_text"]) for r in rows) <= 32000
    for row in rows:
        doc = documents[row["document_id"]]
        assert row["document_id"] in selected
        assert row["content_hash"] == doc["content_hash"]
        assert row["exact_text"] in doc["content"]
        assert json.loads(row["exact_text"]) in json.loads(doc["content"])["facts"]
    matches = {tag: [r for r in rows if r["document_id"] == q1["document_id"] and json.loads(r["exact_text"]) == fact]
               for tag, fact in expected.items()}
    assert all(len(found) == (1 if mode == "counter" else 0) for found in matches.values())
    assert {tag: len(found) for tag, found in matches.items()} == result["results"][mode]["latest_operand_whole_literals_visible"]
    details[mode] = {"whole_latest_literals": {tag: len(found) for tag, found in matches.items()},
                     "projection_count": len(rows), "characters": sum(len(r["exact_text"]) for r in rows),
                     "selected_order_unchanged": result["results"][mode]["selected_order_unchanged"]}
    if mode == "counter":
        assert all(found[0]["fact_context"]["record_selection"] == "latest" for found in matches.values())
        assert all(found[0]["fact_context"]["unit"] == "USD" for found in matches.values())
connected = read(BASE / "root/connected-tests.json")
initial = read(BASE / "root/initial-overbroad-guard-connected-tests.json")
assert (connected["run"], connected["failures"], connected["errors"], connected["forbidden_calls"]) == (63, 0, 0, [])
assert initial["failures"] == 7
old_guard = (BASE / "root/initial-overbroad-guard-connected-check.py.txt").read_text()
new_guard = (BASE / "root/connected-check.py").read_text()
assert "(StructuredRoleClient, 'complete_json')" in old_guard
assert "(UrllibTransport, 'post_json')" in new_guard
assert "(StructuredRoleClient, 'complete_json')" not in new_guard
for path, expected_sha in bindings.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected_sha
report = {"status": "PASS_saved_read_projection_fidelity_only", "details": details,
          "latest_basis": {"end": "2025-03-31", "unit": "USD", "values": {tag: row["value"] for tag, row in expected.items()}},
          "connected_suite": "root executed 63 PASS/0 forbidden; independently read, not rerun",
          "initial_seven": "harness overguard blocked complete_json local pending transport; moved only guard to external UrllibTransport.post_json; initial failures retained",
          "limitation": "Only previously frozen counter selection contains the two latest operands. Native selection still contains zero; production ranking is unchanged. Pure retained-artifact audit, no prompt/model/Signal/Store/GET/labels execution or new measurement.",
          "all_read_bindings_unchanged": True, "bindings": bindings}
output = BASE / "independent/actual-read-review.json"
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "details": details, "review_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, ensure_ascii=False))
