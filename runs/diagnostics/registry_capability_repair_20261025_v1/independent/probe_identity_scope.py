"""Probe fixture-only repair and unauthorized drift entirely in memory."""
from copy import deepcopy
from dataclasses import replace
import json

from capture_baseline import ORIGINAL, OUT, content_manifest
from stock_opportunity_agent.signal_library import SignalRegistry, _audit_deterministic_fixture
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator


def main():
    before = content_manifest()
    registry = object.__new__(SignalRegistry)
    registry.root = ORIGINAL
    registry.knowledge_workspace_root = ORIGINAL.parent
    registry.candidate_root = OUT / "unused_candidates"
    registry._transition_recovery_active = False
    registry._fault_injector = None
    validator = SignalCandidateValidator(registry, llm_runner=None)
    disabled = registry.audit_capabilities().disabled
    results = {}
    for ref in disabled:
        if ref.startswith(("gross_margin_change:", "revenue_acceleration:")):
            continue
        prior = registry.load_spec(ref)
        spec = replace(prior, version=prior.version + 1)
        rows = {}
        for mode in ("neither", "body_only", "metadata_only", "matched", "mismatched"):
            tests = deepcopy(registry.load_tests(ref))
            for fixture in tests:
                # This is a declared synthetic identity for the diagnostic only.
                # It makes no historical issuer/source claim and is not staged.
                for document in fixture["documents"]:
                    body = json.loads(document["content"])
                    if mode in {"body_only", "matched", "mismatched"}:
                        body["cik"] = "0001999991"
                    if mode in {"metadata_only", "matched", "mismatched"}:
                        document.setdefault("metadata", {})["cik"] = "0001999992" if mode == "mismatched" else "0001999991"
                    document["content"] = json.dumps(body, sort_keys=True, separators=(",", ":"))
            checked = validator.validate(spec, skill=None, tests=tests)
            rows[mode] = {"accepted": checked.accepted, "reasons": list(checked.reasons), "executed_tests": checked.executed_tests}
            if mode != "matched":
                assert not checked.accepted, (ref, mode, checked)
            if mode == "matched":
                fixture_audit = []
                for index, fixture in enumerate(tests):
                    try:
                        _audit_deterministic_fixture(spec, fixture, index=index)
                        fixture_audit.append({"name": fixture["name"], "passed": True})
                    except Exception as exc:
                        fixture_audit.append({"name": fixture["name"], "passed": False, "failure": str(exc)})
                rows["matched_stable_fixture_audit"] = fixture_audit
                if prior.signal_id == "operating_cash_flow_margin":
                    concept_control = replace(spec, description="Measure operating cash flow margin as a share of revenue for the latest exact reported duration.")
                    control = validator.validate(concept_control, skill=None, tests=tests)
                    rows["disallowed_description_control"] = {"accepted": control.accepted,
                        "executed_tests": control.executed_tests, "reasons": list(control.reasons),
                        "note": "Diagnostic only: changes approved immutable spec wording and must not be used for repair under current scope."}
                if prior.signal_id == "cash_reserves":
                    drift = replace(spec, parameters={**dict(spec.parameters), "positive_min": 99000000})
                    checked_drift = validator.validate(drift, skill=None, tests=tests)
                    rows["unauthorized_threshold_drift"] = {"accepted": checked_drift.accepted,
                        "reasons": list(checked_drift.reasons), "executed_tests": checked_drift.executed_tests,
                        "note": "Probe whether generic validator permits fixture-compatible drift; repair-specific equality must reject any such drift."}
        results[ref] = rows
    assert before == content_manifest(), "original changed"
    result = {"schema_version": "independent-in-memory-identity-scope-probes-v1", "results": results,
              "original_unchanged": True, "external_calls": 0, "staged_candidates": 0,
              "admissions": 0, "promotions": 0,
              "claim": "In-memory diagnostic probes only; no repair implementation or publication."}
    (OUT / "identity-scope-probes.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"signals": len(results), "identity_variants_each": 5,
                      "matched_accepted_refs": [k for k, v in results.items() if v["matched"]["accepted"]],
                      "matched_rejected_refs": [k for k, v in results.items() if not v["matched"]["accepted"]],
                      "matched_fixture_count": sum(v["matched"]["executed_tests"] for v in results.values()),
                      "unauthorized_threshold_drift_generic_validator_accepted": results["cash_reserves:v2"]["unauthorized_threshold_drift"]["accepted"],
                      "original_unchanged": True}, indent=2))


if __name__ == "__main__":
    main()
