"""Real ordinary updates/additions and portable historical repair-proof reads."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts"))
import repair_historical_signal_registry as driver
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator, SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalRegistry
from review_support import assert_original_unchanged


def ordinary(registry, spec, tests, transition_id):
    snapshot = registry.freeze()
    validator = SignalCandidateValidator(registry, llm_runner=None)
    checked = validator.validate(spec, skill=None, tests=tests)
    assert checked.accepted and checked.executed_tests == len(tests), checked
    registry.stage_candidate(spec, tests=tests, origin="independent-disposable-ordinary-continuity")
    policy = SimpleNamespace(validator=validator, _role_work_identity=SignalEvolutionEngine._role_work_identity)
    key = registry.record_candidate_admission(spec.ref, input_registry_hash=snapshot.registry_hash,
        validator_hash=SignalEvolutionEngine._technical_validator_hash(policy), research_targets=("surge_direction",),
        contract_validation={"accepted": True, "reasons": [], "executed_tests": checked.executed_tests},
        research_provenance={"generation_case_ids": [], "induction_case_ids": [], "origin": "unknown", "source_input_hash": None})
    return registry.promote_validated_batch({spec.ref: registry.candidate_hash(spec.ref)}, validated_evaluations={spec.ref: key},
        transition_id=transition_id, input_version=snapshot.version, input_hash=snapshot.registry_hash,
        input_refs=tuple(s.ref for s in snapshot.specs))


def main():
    code = driver.code_bindings()
    rows = []
    with tempfile.TemporaryDirectory(dir=OUT, prefix="continuity-") as temp:
        root = Path(temp) / "case"
        with driver.guards():
            plan = driver.prepare_at(root)
            registry = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            repaired = registry.capability_repair(plan, plan_hash=canonical_json_hash(plan))
            repaired_snapshot = registry.freeze()
            repair_refs = tuple(s.ref for s in repaired_snapshot.specs)
            prior = registry.load_spec("cash_reserves:v3")
            update = ordinary(registry, replace(prior, version=4), registry.load_tests(prior.ref), "independent-continuity-update")
            assert update.output_version == 14 and registry.freeze().version == 14
            rows.append({"case": "actual_full_validated_ordinary_update", "passed": True, "version": 14, "latest_ref": registry.latest_spec("cash_reserves").ref})
            fixtures = deepcopy(registry.load_tests("cash_reserves:v4"))
            for fixture in fixtures: fixture["expected"] = "neutral"
            addition = replace(prior, signal_id="independent_high_cash_threshold", version=1,
                description="Measure cash balance against an independently stricter threshold.",
                parameters={**dict(prior.parameters), "positive_min": 200000000})
            added = ordinary(registry, addition, fixtures, "independent-continuity-addition")
            fresh = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            snapshot = fresh.freeze()
            assert added.output_version == 15 and snapshot.version == 15 and len(snapshot.specs) == 19
            assert fresh.load_spec("cash_reserves:v3") == prior
            assert fresh.snapshot_from_refs(13, repair_refs).registry_hash == repaired.output_hash
            rows.append({"case": "actual_full_validated_new_signal", "passed": True, "version": 15, "count": 19,
                         "new_ref": addition.ref, "old_repair_hash_preserved": True})

            # Copy only the Registry; all producer/admission source paths become absent.
            portable = Path(temp) / "portable-registry"
            shutil.copytree(root / "registry", portable)
            shutil.rmtree(root)
            local = SignalRegistry(portable, candidate_root=Path(temp) / "empty-candidates")
            assert local.freeze().version == 15 and len(local.list_signal_cards()) == 19
            assert local.snapshot_from_refs(13, repair_refs).registry_hash == repaired.output_hash
            rows.append({"case": "portable_committed_reads_without_any_preparation_files_or_candidate_root", "passed": True, "version": 15})

            paths = {
                "historical_admission_bytes": portable / "financial/cash_reserves/versions/v3/admission.json",
                "historical_spec_version_type": portable / "financial/cash_reserves/versions/v3/spec.json",
                "repair_output_hash": portable / ".transitions" / (plan["transition_id"] + ".json"),
                "repair_output_version_type": portable / ".transitions" / (plan["transition_id"] + ".json"),
            }
            for name, path in paths.items():
                original = path.read_bytes()
                if name == "historical_admission_bytes": path.write_bytes(original + b" ")
                else:
                    value = json.loads(original)
                    if name == "historical_spec_version_type": value["version"] = 3.0
                    elif name == "repair_output_hash": value["output_registry_hash"] = "0" * 64
                    else: value["output_registry_version"] = 13.0
                    path.write_text(json.dumps(value))
                rejected = []
                for reader in (local.freeze, local.list_signal_cards, lambda: local.load_spec("cash_reserves:v4")):
                    try: reader()
                    except ValidationError as exc: rejected.append(str(exc))
                    else: raise AssertionError("Corrupt historical repair proof readable: " + name)
                rows.append({"case": name, "passed": True, "rejected_readers": len(rejected), "error": rejected[0]})
                path.write_bytes(original)
            assert local.freeze().version == 15
    assert_original_unchanged()
    for row in code: assert driver.binding(row["path"]) == row
    result = {"schema_version": "independent-repair-ordinary-continuity-portability-v1", "controls": rows,
              "passed": len(rows), "code_files": code, "original_198_unchanged": True,
              "formal_destination_touched": False, "external_calls": 0, "labels": 0,
              "limit": "Ordinary additions/updates occur only on disposable clones. No old completed repair is reexecuted after its later mutation, and no new transition-chain admission policy is inferred."}
    (OUT / "successor-addition-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": len(rows), "ordinary_update_version": 14, "ordinary_addition_version": 15, "count": 19,
                      "portable_historical_proof_checked": True}))


if __name__ == "__main__": main()
