"""Read the one completed financial9 batch; standard library only, no product calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
STAGE = BASE / "native/stage"
reads = {}


def sha(path):
    """Stream bytes only, including any opaque historical authority envelope."""
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(1048576), b""):
            h.update(part)
    return h.hexdigest()


def read(path):
    """Deserialize only this stage/oracle and explicitly selected source records."""
    path = Path(path)
    reads[str(path)] = sha(path)
    return json.loads(path.read_text())


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


plan = read(STAGE / "plan.json")
assert plan["plan_hash"] == "8e8e406273d1f9805156e08d2f1155bf7da7044ddacc552d92c48da19239419a"
assert canonical({k: v for k, v in plan.items() if k != "plan_hash"}) == plan["plan_hash"]
all_bindings = plan["source_bindings"] + plan["code_bindings"]
assert len(all_bindings) == 4389
with ThreadPoolExecutor(max_workers=8) as workers:
    hashes = list(workers.map(lambda item: sha(item["path"]), all_bindings))
assert all(value == item["sha256"] for value, item in zip(hashes, all_bindings, strict=True))
seal = read(STAGE / "completed-files.json")
assert all(sha(item["path"]) == item["sha256"] for item in seal["files"])
assert {str(p.resolve()) for p in STAGE.rglob("*") if p.is_file()} == {item["path"] for item in seal["files"]} | {str((STAGE / "completed-files.json").resolve())}
result = read(STAGE / "result.json")
batch = read(STAGE / "native-batch.json")
assert result["status"] == "completed_acceptance_failed" and result["passed_unique"] == 6
assert batch["signal_calls"] == 9 and len(batch["results"]) == len(batch["resolutions"]) == 9
assert batch["usage"] == {"cost": 0.0, "llm_calls": 0, "tokens": 0} and not batch["skipped_unchanged_refs"]
assert (STAGE / "execution-start.json").is_file() and not (STAGE / "failure.json").exists()
old = read("runs/diagnostics/measurement_input_selection_20261021_v1/latest_v12.json")
old_rows = {row["signal_ref"]: row for row in old["rows"]}
materials = read(BASE / "oracle/raw-materials.json")
docs = {}
for item in materials["documents"]:
    doc = read(item["path"])
    assert reads[item["path"]] == item["sha256"]
    assert sha(item["path"]) == item["sha256"]
    assert hashlib.sha256(doc["content"].encode()).hexdigest() == doc["content_hash"]
    docs[doc["document_id"]] = doc
oracle = read(BASE / "oracle/oracle.json")
assert oracle == plan["oracle"]
cutoff = datetime.fromisoformat(plan["case"]["prediction_time"])
selection_checks = []
numeric_checks = []
evidence_count = 0
for index, (ref, resolution, raw, expected) in enumerate(zip(plan["signal_refs"], batch["resolutions"], batch["results"], oracle["rows"], strict=True)):
    assert ref == f'{raw["signal_id"]}:v{raw["version"]}' == expected["signal_ref"]
    assert raw == read(STAGE / f"results/{index:02d}.json")
    original = old_rows[ref]["resolution"]
    assert resolution["documents"] == original["documents"]
    assert resolution["request"] == original["request"]
    assert len(resolution["documents"]) <= 10 and not resolution["appended_documents"]
    selected = {d["document_id"]: d for d in resolution["documents"]}
    assert batch["document_fingerprints"][ref] == sorted(f'{d["document_id"]}:{d["content_hash"]}' for d in resolution["documents"])
    for identity in selected.values():
        assert identity["content_hash"] == docs[identity["document_id"]]["content_hash"]
        assert identity["available_at"] == docs[identity["document_id"]]["available_at"]
    for group in ("supporting", "counter"):
        for item in raw["evidence"][group]:
            doc = docs[item["document_id"]]
            assert item["document_id"] in selected
            assert item["exact_span"] in doc["content"]
            assert json.loads(item["exact_span"]) in json.loads(doc["content"])["facts"]
            assert datetime.fromisoformat(item["timestamp"]) == datetime.fromisoformat(doc["available_at"]) <= cutoff
            evidence_count += 1
    projection = read(STAGE / f"consumer-projections/{index:02d}.json")
    for field in ("signal_id", "version", "state", "status", "execution", "measurement", "evidence"):
        assert projection[field] == raw[field]
    context = projection["interpretation"]["measurement_context"]
    assert context["numeric_measurement"]["value"] == raw["measurement"]["value"]
    assert context["numeric_measurement"]["unit"] == raw["measurement"]["unit"]
    for observation in context["source_observations"]:
        item = raw["evidence"][observation["evidence_group"]][observation["evidence_index"]]
        fact = json.loads(item["exact_span"])
        assert all(observation[key] == fact.get(key) for key in ("tag", "unit", "value", "end"))
        assert observation.get("start") == fact.get("start")
    selection_checks.append({"ref": ref, "count": len(selected), "selected_ID_hash_available_order_equal_old": True,
                             "request_equal_old": True, "fingerprint_equal_actual_selection": True})
    if expected["oracle_status"] == "sufficient_unique":
        value = Decimal(str(raw["measurement"]["value"]))
        expected_fraction = Fraction(expected["expected_numeric"]["exact_fraction"])
        assert abs(value - Decimal(expected_fraction.numerator) / Decimal(expected_fraction.denominator)) <= Decimal("1e-12")
        assert raw["state"]["value"] == expected["expected_state"]
        assert {key: raw["measurement"]["period"].get(key) for key in ("start", "end")} == expected["measurement_period"]
        assert raw["measurement"]["unit"] == {"dimensionless ratio": "ratio", "dimensionless fraction": "fraction"}.get(expected["unit"], expected["unit"])
        numeric_checks.append({"ref": ref, "numeric_state_unit_current_period": True})
    else:
        comparison = next(c for c in result["comparisons"] if c["signal_ref"] == ref)
        assert comparison["passed"] is None

prior_expected = oracle["rows"][8]["operands"][1]
prior_actual = batch["results"][8]["evidence"]["supporting"][1]
actual_fact = json.loads(prior_actual["exact_span"])
differences = {key: [prior_expected["fact"].get(key), actual_fact.get(key)]
               for key in prior_expected["fact"].keys() | actual_fact.keys()
               if prior_expected["fact"].get(key) != actual_fact.get(key)}
assert differences == {"fiscal_year": [2025, 2024], "frame": ["CY2024Q1", None]}
assert all(actual_fact[key] == prior_expected["fact"][key] for key in ("taxonomy", "tag", "unit", "value", "start", "end"))
assert actual_fact["value"] == 597214000 and actual_fact["tag"] == "Revenues"
assert any(r["document_id"] == prior_actual["document_id"] and r["literal"] == prior_actual["exact_span"] for r in materials["records"])
assert all(a["fact"]["end"] == "2025-03-31" for a in oracle["rows"][8]["current_period_alternatives"])
assert all(sha(item["path"]) == item["sha256"] for item in seal["files"])
assert all(sha(path) == digest for path, digest in reads.items())
report = {"status": "AUDIT_COMPLETE_stage_strict_failure_preserved",
          "frozen_bindings_verified": {"source": len(plan["source_bindings"]), "code": len(plan["code_bindings"]), "total": 4389},
          "stage_sealed_files_verified": len(seal["files"]), "case": plan["case"]["case_id"],
          "actual_selection": selection_checks, "unique_numeric_category_unit_current_period": numeric_checks,
          "strict_acceptance": {"unique_pass": 6, "unique_failed_literal_allowlist": 1, "period_policy_ambiguous_record_only": 2, "denominator": 9,
                                "original_stage_status": result["status"], "oracle_or_result_modified": False},
          "prior_literal_diagnostic": {"ref": "revenue_growth_yoy:v3", "oracle_document": prior_expected["document_id"],
                                       "actual_document": prior_actual["document_id"], "field_differences": differences,
                                       "semantic_measurement_tuple_equal": True, "actual_prior_in_original_selected_set": True,
                                       "actual_prior_was_in_preexisting_frozen_raw_materials": True,
                                       "reason": "Oracle strict alternative inventory lists only current-period variants. Prior from2024 original filing is a complete same-value/tag/unit/duration source literal, whereas oracle operand specifies its2025 filing comparative copy. No evidence of numeric or revenue-total basis error; strict literal acceptance failure remains unchanged."},
          "consumer_projections_exact": 9, "whole_source_evidence_items_verified": evidence_count,
          "execution": {"native_batches_recorded": result["native_batches"], "native_result_count": batch["signal_calls"], "usage": batch["usage"]},
          "limits": ["Pure retained-file/stdlib audit; no stage commands, constructors, product helpers, Signal functions, model/GET/labels/append invoked.",
                     "No pass credit for2 ambiguous definitions, no oracle repair/re-execution, no overall9/9 or F5/MVP closure.",
                     "Native saved results and public consumer projections only, not fresh model consumption or OS-crash recovery. Completed restore separately performed by sole root executor."],
          "read_bindings": reads}
target = BASE / "independent/actual-review.json"
target.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": report["status"], "bindings": 4389, "selected_groups_equal": len(selection_checks), "numeric_unique_match": len(numeric_checks), "projection_count": 9, "review_sha256": sha(target)}))
