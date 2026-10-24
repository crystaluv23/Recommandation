"""Issue a code-bound local prepublication review only from completed controls."""
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts"))
import repair_historical_signal_registry as driver
from review_support import assert_original_unchanged


def read(name):
    return json.loads((OUT / name).read_text())


def main():
    matrix = read("result.json")
    continuity = read("successor-addition-result.json")
    r3 = read("applied-status-final.json")
    r6 = read("historical-fixture-after-fix.json")
    late = read("late-failure-result.json")
    code = driver.code_bindings()
    assert matrix["production_source_bindings"] == continuity["code_files"] == r3["code_files"] == r6["code_files"] == late["code_files"] == code
    assert matrix["passed_controls"] == 74 and all(row["passed"] for row in matrix["controls"])
    assert continuity["passed"] == 7 and all(row["passed"] for row in continuity["controls"])
    assert not r3["normal_read_accepted_status_only_applied"] and not r3["repair_entry_accepted"]
    assert not r6["ordinary_fresh_read_accepted_changed_repaired_historical_fixture"] and r6["direct_old_status_rejected"]
    assert late["failed_version"] == 12 and late["promotion_markers_before_recovery"] == 0 and late["prepared_reads_blocked"] and late["restored_exact_recovery_version"] == 13
    assert not driver.ROOT.exists(), "Formal migration already exists; prepublication review would be stale"
    assert_original_unchanged()
    names = ["result.json", "successor-addition-result.json", "applied-status-final.json", "historical-fixture-after-fix.json", "late-failure-result.json"]
    result = {
        "schema_version": "independent-capability-repair-prepublication-review-v1",
        "publication_allowed": True,
        "scope": "Only the already user-approved exact v12/18 capability repair at the fixed migration destination, under these exact code_files and actual driver's frozen authority/plan. This does not authorize any new research run or resource budget.",
        "code_files": code,
        "independent_passed_transaction_controls": 74,
        "independent_transaction_controls": matrix["controls"],
        "continuity_portability_controls": continuity["controls"],
        "targeted_resolutions": [
            {"id": "R1", "passed": True, "claim": "Missing/corrupt first and last exact promotion markers reject applied replay without writes."},
            {"id": "R2", "passed": True, "claim": "Unknown/missing state and unknown schema block ordinary reads and recovery after real pre-bump output materialization."},
            {"id": "R3", "passed": True, "claim": "Status-only forged applied cannot expose unpublished versions.", "evidence": "applied-status-final.json"},
            {"id": "R4", "passed": True, "claim": "Promotion marker bool/int and int/float type changes reject exact replay."},
            {"id": "R5", "passed": True, "claim": "Actual ordinary update to v14 and actual new Signal addition to v15/count19 remain readable while preserving repair v13 snapshot.", "evidence": "successor-addition-result.json"},
            {"id": "R6", "passed": True, "claim": "After a genuine ordinary update, changed old repaired fixture content blocks fresh ordinary reads via its frozen candidate hash.", "evidence": "historical-fixture-after-fix.json"}
        ],
        "late_output_failure": {"passed": True, "evidence": "late-failure-result.json", "failed_version": 12, "promotion_markers": 0, "prepared_reads_blocked": True, "exact_recovery_version": 13},
        "original_198_unchanged": True,
        "formal_migration_destination_touched": False,
        "external_calls": 0,
        "labels": 0,
        "limitations": [
            "This is a local prepublication implementation review on disposable clones. The formal migration has not been prepared or executed.",
            "All current passing control artifacts were rerun against exactly the code_files above; previous failures/code hashes remain separate historical evidence.",
            "Within-batch dedup evidence combines the approved batch's actual uniqueness, shared execution identity, actual stable-duplicate validation and immutable-scope rejection. Approved scope was not widened to manufacture otherwise unreachable duplicates.",
            "All nine repairs are deterministic; the skill-materialization fault is inapplicable. Twelve relevant fault phases plus abrupt process exit/fresh-process driver recovery cover this transaction, not complete Fast/Slow OS recovery.",
            "Late inherited-file drift is rejected by the permitted-byte guard before audit; no injected audit-implementation failure is claimed.",
            "Ordinary portable reads need local committed proof, not deleted preparation files; exact repair replay remains restricted to the original transaction state and is not reexecuted after a later legitimate mutation.",
            "No fresh downstream consumer, new Mining, actual Slow completion, independent benefit or MVP closure is established."
        ],
        "artifacts": {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in names},
        "preserved_failed_reviews": ["prepublication-review.json", "prepublication-review-v2.json", "prepublication-review-v3.json"]
    }
    output = OUT / "prepublication-review-v4.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"publication_allowed": True, "transaction_controls": 74, "continuity_portability_controls": 7,
                      "original_198_unchanged": True, "formal_destination_touched": False,
                      "review_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__": main()
