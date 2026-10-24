"""Independent real-input helpers for disposable repair-transaction controls.

Import is read-only. No staging occurs unless a later review explicitly invokes
prepare_disposable_bundle after the product implementation is ready.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator, SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalRegistry, SignalSpec

REPO = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
ORIGINAL = REPO / "runs/cold_start/minimal_rounds_v182_integrated/signals"
BASELINE = json.loads((OUT.parent / "baseline.json").read_text())
APPROVED = REPO / "runs/diagnostics/financial_period_policy_20261023_v1/independent"


def read(path):
    return json.loads(Path(path).read_text())


def inventory(root):
    root = Path(root)
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def assert_original_unchanged():
    actual = inventory(ORIGINAL)
    assert actual == BASELINE["original_files"] and len(actual) == 198


def expected_candidate_data():
    """Derive seven unchanged definitions independently of product repair code."""
    approved_specs = {SignalSpec.from_dict(raw).ref: raw for raw in read(APPROVED / "new-version-specs.json")["specs"]}
    approved_tests = read(APPROVED / "lineage-fixtures.json")["by_ref"]
    result = {}
    for ref in BASELINE["audit"]["disabled"]:
        signal_id, version = ref.rsplit(":v", 1)
        version_dir = ORIGINAL / "financial" / signal_id / "versions" / f"v{version}"
        prior = SignalSpec.from_dict(read(version_dir / "spec.json"))
        next_ref = f"{signal_id}:v{int(version) + 1}"
        if next_ref in approved_specs:
            spec = SignalSpec.from_dict(approved_specs[next_ref])
            tests = deepcopy(approved_tests[next_ref])
            kind = "approved_period_policy"
        else:
            spec = replace(prior, version=prior.version + 1)
            tests = deepcopy(read(version_dir / "tests.json")["tests"])
            for fixture in tests:
                for doc in fixture["documents"]:
                    body = json.loads(doc["content"])
                    body["cik"] = "0001999991"  # Synthetic diagnostic fixture issuer only.
                    doc.setdefault("metadata", {})["cik"] = "0001999991"
                    doc["content"] = json.dumps(body, sort_keys=True, separators=(",", ":"))
            kind = "fixture_identity_only"
            assert replace(spec, version=prior.version).to_dict() == prior.to_dict()
        result[next_ref] = {"spec": spec.to_dict(), "tests": tests, "skill": None,
                            "prior_ref": ref, "kind": kind}
    assert len(result) == 9 and sum(row["kind"] == "fixture_identity_only" for row in result.values()) == 7
    return result


def prepare_disposable_bundle(root):
    """Stage/admit only a caller-owned disposable clone for actual API testing."""
    if not hasattr(SignalRegistry, "capability_repair"):
        raise RuntimeError("Product capability_repair implementation is not ready")
    assert_original_unchanged()
    root = Path(root).resolve()
    assert OUT in root.parents and root != ORIGINAL.resolve()
    shutil.copytree(ORIGINAL, root / "signals")
    registry = SignalRegistry(root / "signals", candidate_root=root / "candidates")
    snapshot = registry.snapshot_from_refs(BASELINE["registry_version"], tuple(BASELINE["ordered_refs"]))
    assert snapshot.registry_hash == BASELINE["registry_definition_hash"]
    validator = SignalCandidateValidator(registry, llm_runner=None)
    policy = SimpleNamespace(validator=validator, _role_work_identity=SignalEvolutionEngine._role_work_identity)
    validator_hash = SignalEvolutionEngine._technical_validator_hash(policy)
    candidate_hashes, admission_keys, validations = {}, {}, {}
    expected = expected_candidate_data()
    for ref, data in expected.items():
        spec = SignalSpec.from_dict(data["spec"])
        registry.stage_candidate(spec, tests=data["tests"], origin="independent-disposable-transaction-control")
        checked = validator.validate(spec, skill=None, tests=data["tests"])
        assert checked.accepted and checked.executed_tests == len(data["tests"]), checked
        key = registry.record_candidate_admission(ref,
            input_registry_hash=snapshot.registry_hash, validator_hash=validator_hash,
            research_targets=("surge_direction",),
            contract_validation={"accepted": checked.accepted, "reasons": list(checked.reasons),
                                 "executed_tests": checked.executed_tests},
            research_provenance={"generation_case_ids": [], "induction_case_ids": [],
                                 "origin": "unknown", "source_input_hash": None})
        candidate_hashes[ref] = registry.candidate_hash(ref)
        admission_keys[ref] = key
        validations[ref] = asdict(checked)
    assert_original_unchanged()
    return {"registry": registry, "snapshot": snapshot, "validator": validator,
            "validator_hash": validator_hash, "validated_candidates": candidate_hashes,
            "validated_evaluations": admission_keys, "validations": validations,
            "expected_candidate_data": expected}
