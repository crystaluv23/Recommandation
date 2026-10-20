"""Independent standard-library source and arithmetic audit; never execute product code."""
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
bindings = {}


def read(path):
    """Bind and parse only the explicitly referenced source/oracle JSON file."""
    path = Path(path)
    raw = path.read_bytes()
    bindings[str(path)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def canonical(value):
    """Use the manifest's ordinary JSON canonical form, without importing helpers."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


manifest = read(BASE / "oracle/frozen-manifest.json")
assert bindings[str(BASE / "oracle/frozen-manifest.json")] == "475f89606878bdc808fcdcc34e8890a2e937c29f680ade1450211f6e69db595e"
assert canonical({k: v for k, v in manifest.items() if k != "manifest_hash"}) == manifest["manifest_hash"]
for item in manifest["files"]:
    raw = Path(item["path"]).read_bytes()
    assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    bindings[item["path"]] = item["sha256"]
oracle = read(BASE / "oracle/oracle.json")
materials = read(BASE / "oracle/raw-materials.json")
definitions = read(BASE / "oracle/definitions.json")
docs = {}
for entry in materials["documents"]:
    document = read(entry["path"])
    assert bindings[entry["path"]] == entry["sha256"]
    assert document["document_id"] == entry["document_id"]
    assert document["company_id"] == "cik_0001309402"
    assert hashlib.sha256(document["content"].encode()).hexdigest() == entry["content_hash"] == document["content_hash"]
    assert datetime.fromisoformat(document["available_at"]) <= datetime.fromisoformat("2025-05-30T00:00:00+00:00")
    docs[document["document_id"]] = document
assert len(docs) == 23
snapshot_path = Path(materials["documents"][0]["path"]).parents[1] / "reviewed_snapshot.json"
snapshot = read(snapshot_path)
admitted = {item["document_id"]: item for item in snapshot["documents"]}
for entry in materials["documents"]:
    bound = admitted[entry["document_id"]]
    assert (snapshot_path.parent / bound["path"]).resolve() == Path(entry["path"]).resolve()
    assert bound["sha256"] == entry["sha256"]
for row in materials["records"]:
    doc = docs[row["document_id"]]
    assert doc["content"][row["raw_start"]:row["raw_end"]] == row["literal"]
    assert json.loads(row["literal"]) == row["fact"]
    assert json.loads(doc["content"])["facts"][row["fact_index"]] == row["fact"]
assert len(materials["records"]) == 504
matrix = read("runs/diagnostics/measurement_input_selection_20261021_v1/latest_v12.json")
selected = {row["signal_ref"]: {d["document_id"] for d in row["resolution"]["documents"]} for row in matrix["rows"]}
for ref, item in definitions["definitions"].items():
    assert read(item["path"]) == item["spec"] and bindings[item["path"]] == item["sha256"]
counts = Counter(row["oracle_status"] for row in oracle["rows"])
assert counts == {"sufficient_unique": 7, "period_policy_ambiguous": 2}
assert len(oracle["rows"]) == oracle["fixed_denominator"] == 9
for row in oracle["rows"]:
    for operand in row.get("operands", []):
        assert operand in materials["records"] and operand["document_id"] in selected[row["signal_ref"]]
    if row["oracle_status"] == "period_policy_ambiguous":
        assert row["expected_numeric"] is None and row["expected_state"] is None
        assert "not an any-of" in row["acceptance_rule"]


def quantity(row, index):
    """Read one already literal-verified source operand as an exact fraction."""
    return Fraction(row["operands"][index]["fact"]["value"])


results = []
for row in oracle["rows"]:
    if row["oracle_status"] != "sufficient_unique":
        continue
    ref = row["signal_ref"]
    spec = definitions["definitions"][ref]["spec"]
    p = spec["parameters"]
    facts = [operand["fact"] for operand in row["operands"]]
    assert all(f["end"] in ("2025-03-31", "2024-03-31") for f in facts)
    expected_unit = "shares" if ref.startswith("net_share") else "USD"
    assert all(f["unit"] == expected_unit for f in facts)
    if ref.startswith("cash_burn"):
        value = abs(quantity(row, 0)) / quantity(row, 1)
        state = "positive" if value >= Fraction(str(p["burn_threshold"])) else "neutral"
    elif ref.startswith("cash_reserves"):
        value = quantity(row, 0)
    elif ref.startswith("cash_to_current"):
        assert facts[0]["start"] is facts[1]["start"] is None
        assert facts[0]["end"] == facts[1]["end"] and quantity(row, 1) > 0
        value = quantity(row, 0) / quantity(row, 1)
    elif ref.startswith("liquidity_runway"):
        duration = facts[1]
        assert (duration["start"], duration["end"]) == ("2025-01-01", "2025-03-31")
        assert duration["fiscal_period"] == "Q1"
        months = 3  # This literal reported Q1, not a policy for arbitrary durations.
        value = quantity(row, 0) / (abs(quantity(row, 1)) / months)
        state = ("positive" if value <= p["positive_runway_max_months"] else
                 "negative" if value >= p["negative_runway_min_months"] else "neutral")
    elif ref.startswith("net_share"):
        assert all(f["tag"] == "WeightedAverageNumberOfSharesOutstandingBasic" for f in facts)
        assert [(f["start"], f["end"]) for f in facts] == [("2025-01-01", "2025-03-31"), ("2024-01-01", "2024-03-31")]
        value = 1 - quantity(row, 0) / quantity(row, 1)
    elif ref.startswith("operating_cash_flow"):
        assert (facts[0]["start"], facts[0]["end"]) == (facts[1]["start"], facts[1]["end"])
        assert facts[1]["tag"] == "Revenues" and quantity(row, 1) == 601515000
        value = quantity(row, 0) / quantity(row, 1)
    elif ref.startswith("revenue_growth"):
        assert all(f["tag"] == "Revenues" for f in facts)
        assert [(f["start"], f["end"]) for f in facts] == [("2025-01-01", "2025-03-31"), ("2024-01-01", "2024-03-31")]
        value = quantity(row, 0) / quantity(row, 1) - 1
    else:
        raise AssertionError(ref)
    if not ref.startswith(("cash_burn", "liquidity_runway")):
        state = ("positive" if value >= Fraction(str(p["positive_min"])) else
                 "negative" if value <= Fraction(str(p["negative_max"])) else "neutral")
    assert value == Fraction(row["expected_numeric"]["exact_fraction"])
    assert state == row["expected_state"]
    with localcontext() as context:
        context.prec = 60
        decimal = Decimal(value.numerator) / Decimal(value.denominator)
        assert abs(decimal - Decimal(row["expected_numeric"]["decimal"])) < Decimal("1e-47")
    results.append({"signal_ref": ref, "fraction": str(value), "decimal": str(decimal), "state": state,
                    "source_units": expected_unit, "periods": [(f["start"], f["end"]) for f in facts]})

current = next(doc for doc in docs.values() if doc["document_id"].startswith("rawcap:v1:64c9"))
facts = json.loads(current["content"])["facts"]
alternatives = [f for f in facts if f["start"] == "2025-01-01" and f["end"] == "2025-03-31" and f["tag"] in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")]
assert {(f["tag"], f["unit"], f["value"]) for f in alternatives} == {("Revenues", "USD", 601515000), ("RevenueFromContractWithCustomerExcludingAssessedTax", "USD", 35846000)}
assert 601515000 > 3 * 35846000
for end, start, value in (("2025-03-31", "2025-01-01", 64069000), ("2024-03-31", "2024-01-01", 63341000)):
    assert {f["value"] for f in facts if f["tag"] in ("WeightedAverageNumberOfSharesOutstandingBasic", "WeightedAverageNumberOfDilutedSharesOutstanding") and f["start"] == start and f["end"] == end and f["unit"] == "shares"} == {value}


class InlineFact(HTMLParser):
    """Parse the supplied single inline-XBRL element without product helpers."""
    def __init__(self):
        super().__init__()
        self.attributes = {}
        self.text = ""

    def handle_starttag(self, tag, attrs):
        self.attributes.update(attrs)

    def handle_data(self, data):
        self.text += data


primary = read(BASE / "oracle/primary-filing-corroboration.json")
source = read(primary["path"])
assert bindings[primary["path"]] == primary["sha256"]
assert source["content_hash"] == primary["content_hash"]
for record in primary["records"]:
    literal_context = record["context_literal"]
    assert literal_context in source["content"] and "0001309402" in literal_context
    end = re.search(r"<(?:\w+:)?(?:instant|endDate)>([^<]+)", literal_context, re.I).group(1)
    match = re.search(r"<(?:\w+:)?startDate>([^<]+)", literal_context, re.I)
    start = match.group(1) if match else None
    for item in record["facts"]:
        assert source["content"][item["raw_start"]:item["raw_end"]] == item["literal"]
        parser = InlineFact()
        parser.feed(item["literal"])
        assert parser.attributes["name"].split(":")[-1] == record["tag"]
        amount = Decimal(parser.text.replace(",", "")) * (Decimal(10) ** int(parser.attributes.get("scale", "0")))
        if parser.attributes.get("sign") == "-":
            amount = -amount
        assert parser.attributes["unitref"].lower() in ("usd", "shares")
        unit = "USD" if parser.attributes["unitref"].lower() == "usd" else "shares"
        assert any(f["tag"] == record["tag"] and f["start"] == start and f["end"] == end and f["unit"] == unit and Decimal(f["value"]) == amount for f in facts)
assert len(primary["records"]) == 7
assert (date(2025, 5, 30) - date(2025, 3, 31)).days == 60
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in bindings.items())
report = {"status": "PASS_seven_unique_oracle_source_arithmetic", "denominator": 9,
          "unique_count": 7, "ambiguous_record_only": 2, "recomputed": results,
          "whole_literals_verified": 504, "selected_source_documents_verified": 23,
          "primary_inline_fact_contexts_verified": 7,
          "revenue_basis": "Total Revenues 601515000, not smaller alternate tag35846000; same-duration USD and primary inline-XBRL corroborate.",
          "share_basis": "Q1 weighted-average basic shares64069000/63341000, diluted agrees; not ending shares or cash repurchases.",
          "runway_basis": "This reported Jan1-Mar31 Q1 is3 rounded reported months; not89 calendar days treated as months or a new arbitrary-duration policy.",
          "limits": ["No native Signal/helper/product import, model/API/labels/Store/prepare/execute/append.",
                     "2 ambiguous refs retain denominator/no pass credit; no any-of choice after output.",
                     "No native-stage qualification or measurement success claimed before execution; later native runner/source/evidence/persistence audit remains separate."],
          "bindings": bindings}
target = BASE / "independent/oracle-review.json"
target.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": report["status"], "counts": [7, 2, 9], "review_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}))
