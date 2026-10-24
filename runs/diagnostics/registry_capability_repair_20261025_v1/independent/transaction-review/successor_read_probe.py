"""Actual repaired Registry must remain readable after a later ordinary update."""
from dataclasses import replace
import json
from pathlib import Path
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


def main():
    code = driver.code_bindings()
    with tempfile.TemporaryDirectory(dir=OUT, prefix="successor-read-") as temp:
        root = Path(temp) / "case"
        with driver.guards():
            plan = driver.prepare_at(root)
            registry = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            repair = registry.capability_repair(plan, plan_hash=canonical_json_hash(plan))
            snapshot = registry.freeze()
            prior = registry.load_spec("cash_reserves:v3")
            spec = replace(prior, version=4)
            tests = registry.load_tests(prior.ref)
            validator = SignalCandidateValidator(registry, llm_runner=None)
            checked = validator.validate(spec, skill=None, tests=tests)
            assert checked.accepted and checked.executed_tests == len(tests)
            registry.stage_candidate(spec, tests=tests, origin="independent-disposable-ordinary-successor")
            policy = SimpleNamespace(validator=validator, _role_work_identity=SignalEvolutionEngine._role_work_identity)
            key = registry.record_candidate_admission(spec.ref, input_registry_hash=snapshot.registry_hash,
                validator_hash=SignalEvolutionEngine._technical_validator_hash(policy), research_targets=("surge_direction",),
                contract_validation={"accepted": True, "reasons": [], "executed_tests": checked.executed_tests},
                research_provenance={"generation_case_ids": [], "induction_case_ids": [], "origin": "unknown", "source_input_hash": None})
            ordinary = registry.promote_validated_batch({spec.ref: registry.candidate_hash(spec.ref)},
                validated_evaluations={spec.ref: key}, transition_id="independent-ordinary-followup",
                input_version=snapshot.version, input_hash=snapshot.registry_hash,
                input_refs=tuple(s.ref for s in snapshot.specs))
            reopened = SignalRegistry(root / "registry", candidate_root=root / "candidates")
            try:
                latest = reopened.freeze()
                readable = True; read_error = None; latest_ref = next(s.ref for s in latest.specs if s.signal_id == "cash_reserves")
            except ValidationError as exc:
                readable = False; read_error = str(exc); latest_ref = None
    for row in code: assert driver.binding(row["path"]) == row
    result = {"schema_version": "independent-post-repair-ordinary-successor-probe-v1", "repair_version": repair.output_version,
        "ordinary_update_version": ordinary.output_version, "ordinary_update_validated_fixtures": checked.executed_tests,
        "fresh_ordinary_read_succeeded": readable, "read_error": read_error, "latest_cash_ref": latest_ref,
        "code_files": code, "formal_destination_touched": False, "external_calls": 0, "labels": 0}
    name = sys.argv[1] if len(sys.argv) > 1 else "successor-read-result.json"
    (OUT / name).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("repair_version", "ordinary_update_version", "fresh_ordinary_read_succeeded", "read_error", "latest_cash_ref")}, indent=2))


if __name__ == "__main__": main()
