"""Read-only actual-validator counterreview of ordered ratio descriptions."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from stock_opportunity_agent.signal_library import SignalRegistry
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator, signal_description_concept_contracts
from stock_opportunity_agent.research import signal_evolution as evolution

ROOT = Path(__file__).resolve().parents[5]
ORIGINAL = ROOT / "runs/cold_start/minimal_rounds_v182_integrated/signals"
OUT = Path(__file__).resolve().parent


def manifest():
    return {str(p.relative_to(ORIGINAL)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ORIGINAL.rglob("*")) if p.is_file()}


def fixtures(registry, ref):
    result = deepcopy(registry.load_tests(ref))
    for fixture in result:
        for doc in fixture["documents"]:
            body = json.loads(doc["content"])
            body["cik"] = "0001999991"  # Explicit synthetic diagnostic identity only.
            doc.setdefault("metadata", {})["cik"] = "0001999991"
            doc["content"] = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return result


def main():
    before = manifest()
    baseline = json.loads((OUT.parent / "baseline.json").read_text())
    assert before == baseline["original_files"]
    registry = object.__new__(SignalRegistry)
    registry.root = ORIGINAL
    registry.knowledge_workspace_root = ORIGINAL.parent
    registry.candidate_root = OUT / "unused"
    registry._transition_recovery_active = False
    registry._fault_injector = None
    validator = SignalCandidateValidator(registry, llm_runner=None)
    seven = {}
    for ref in baseline["audit"]["disabled"]:
        if ref.startswith(("gross_margin_change:", "revenue_acceleration:")):
            continue
        prior = registry.load_spec(ref)
        candidate = replace(prior, version=prior.version + 1)
        tests = fixtures(registry, ref)
        checked = validator.validate(candidate, skill=None, tests=tests)
        seven[ref] = {"next_ref": candidate.ref, "accepted": checked.accepted,
                      "executed_tests": checked.executed_tests, "fixture_count": len(tests),
                      "reasons": list(checked.reasons),
                      "spec_equal_except_version": replace(candidate, version=prior.version).to_dict() == prior.to_dict()}
        mismatch = deepcopy(tests)
        for fixture in mismatch:
            for doc in fixture["documents"]:
                doc["metadata"]["cik"] = "0001999992"
        rejected = validator.validate(candidate, skill=None, tests=mismatch)
        seven[ref]["mismatched_identity_rejected"] = not rejected.accepted
        seven[ref]["mismatched_identity_reasons"] = list(rejected.reasons)
    prior = registry.load_spec("operating_cash_flow_margin:v2")
    candidate = replace(prior, version=3)
    tests = fixtures(registry, prior.ref)
    positives = [
        prior.description,
        "Measure operating cash flow as a share of revenue.",
        "Measure OPERATING CASH FLOW as a percentage of revenue.",
        "Measure operating cash-flow divided by revenue.",
        "Measure operating cash flow to revenue ratio.",
        "Measure operating cash flow margin.",
        "Measure operating cash flow divided by revenue for the same exact reported duration.",
        "Measure operating cash flow as a share of revenue for the same reported duration.",
        "Measure operating cash flow as a share of revenue using same-period operands.",
        "Measure operating cash flow divided by revenue from the latest reported duration.",
        "Measure operating cash flow divided by revenue based on matching currency and period.",
        "Measure operating cash flow as a percentage of revenue over the latest year.",
        "Measure operating cash flow to revenue ratio during the latest quarter.",
        "Measure operating   cash\tflow divided by REVENUE.",
        "Measure operating cash-flow as a share of revenue for the latest period.",
    ]
    negatives = [
        "Measure revenue as a share of operating cash flow.",
        "Measure revenue divided by operating cash flow.",
        "Measure operating cash flow as a share of cash.",
        "Measure net income as a share of revenue.",
        "Measure operating cash flow divided by current liabilities.",
        "Measure operating cash flow growth and revenue growth.",
        "Measure investing cash flow divided by revenue.",
        "Measure financing cash flow as a percentage of revenue.",
        "Measure nonoperating cash flow as a share of revenue.",
        "Measure operating cash flow as a share of revenue growth.",
        "Measure operating cash flow divided by revenue growth.",
        "Measure operating cash flow as a percentage of revenue per share.",
        "Measure operating cash flow to revenue growth ratio.",
        "Measure operating cash flow as a share of revenue minus expenses.",
        # The new disclosed grammar conservatively requires an allowed qualifier.
        "Measure operating cash flow to revenue ratio, preserving matching currency and period.",
        "Measure non-operating cash flow as a share of revenue.",
        "Measure not operating cash flow as a share of revenue.",
        "Measure not-operating cash flow divided by revenue.",
        "Measure operating cash flow divided by revenuegrowth.",
        "Measure operating cash flow as a share of revenue_per_share.",
        "Measure xoperating cash flow divided by revenue.",
    ]
    outcomes = []
    for expected, descriptions in ((True, positives), (False, negatives)):
        for description in descriptions:
            checked = validator.validate(replace(candidate, description=description), skill=None, tests=tests)
            outcomes.append({"description": description, "expected_accepted": expected,
                             "accepted": checked.accepted, "executed_tests": checked.executed_tests,
                             "reasons": list(checked.reasons), "matched_expected": checked.accepted is expected})
    current_concepts = evolution._FUNCTION_DESCRIPTION_CONCEPTS["financial.operating_cash_flow_margin"]
    legacy_results = []
    try:
        # Restore precisely the unchanged pre-fix alternative in process only.
        evolution._FUNCTION_DESCRIPTION_CONCEPTS["financial.operating_cash_flow_margin"] = (("operating", "cash", "flow", "margin"),)
        for row in outcomes:
            if row["expected_accepted"] or not row["accepted"]:
                continue
            checked = validator.validate(replace(candidate, description=row["description"]), skill=None, tests=tests)
            legacy_results.append({"description": row["description"], "accepted": checked.accepted,
                                   "executed_tests": checked.executed_tests, "reasons": list(checked.reasons)})
    finally:
        evolution._FUNCTION_DESCRIPTION_CONCEPTS["financial.operating_cash_flow_margin"] = current_concepts
    assert manifest() == before
    result = {"schema_version": "independent-description-fix-review-v1", "seven_identity_only_candidates": seven,
              "description_cases": outcomes, "unexpected_acceptances": [r for r in outcomes if not r["matched_expected"]],
              "pre_fix_screen_on_unexpected_acceptances": legacy_results,
              "disclosed_contract": signal_description_concept_contracts(validator.deterministic_functions)["financial.operating_cash_flow_margin"],
              "matcher_contract": evolution._DESCRIPTION_MATCHING_CONTRACT,
              "original_198_unchanged": True, "staged": 0, "admitted": 0, "promoted": 0,
              "reviewed_source_hash": hashlib.sha256((ROOT / "src/stock_opportunity_agent/research/signal_evolution.py").read_bytes()).hexdigest()}
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"seven_accepted": sum(r["accepted"] for r in seven.values()),
                      "seven_fixture_count": sum(r["executed_tests"] for r in seven.values()),
                      "description_cases": len(outcomes), "unexpected_acceptances": result["unexpected_acceptances"],
                      "original_198_unchanged": True}, indent=2))


if __name__ == "__main__":
    main()
