"""Read-only audit of the exact formal migration; replay must perform no writes."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(OUT.parent / "transaction-review"))
import repair_historical_signal_registry as driver
from review_support import BASELINE, ORIGINAL, expected_candidate_data, inventory
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator, SignalEvolutionEngine
from stock_opportunity_agent.signal_capability_repair import _source
from stock_opportunity_agent.signal_library import SignalRegistry, SignalStats, signal_execution_behavior_identity, signal_version_content_hash

EXPECTED_PLAN = "54f5afd84576b7f1706f36407c318c164f10c6e4c63356910c2d2b004a521cac"
EXPECTED_OUTPUT = "cd4d0f4a31de885585f37becb85300505b51af59424e6183046b75807d6c0ab5"


def read(path):
    return json.loads(Path(path).read_bytes())


def bind(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    root = driver.ROOT
    assert root.is_dir()
    before = {"formal_root": inventory(root), "candidate_root": inventory(root / "candidates"), "original_source": inventory(ORIGINAL)}
    assert before["original_source"] == BASELINE["original_files"] and len(before["original_source"]) == 198
    plan = read(root / "plan.json"); result = read(root / "result.json"); prepared = read(root / "prepared.json")
    authority_path = Path(plan["authority"]["path"])
    assert bind(authority_path) == plan["authority"]
    authority = read(authority_path)
    assert canonical_json_hash(plan) == prepared["plan_hash"] == result["plan_hash"] == EXPECTED_PLAN
    prepublication = read(OUT.parent / "transaction-review/prepublication-review-v4.json")
    code = driver.code_bindings()
    assert prepublication["publication_allowed"] is True and code == prepublication["code_files"] == plan["code_files"]
    for row in code: assert bind(row["path"]) == row
    for row in authority["source_evidence"]: assert bind(row["path"]) == row
    assert bind(authority["approval"]["path"]) == authority["approval"]
    approval = read(authority["approval"]["path"])
    assert approval["approved"] is True and approval["registry_capability_repair_approved"] is True
    assert bind(approval["proposal"]["path"]) == approval["proposal"]

    decisions = []; description_seen = set(); behavior_seen = set()
    expected = expected_candidate_data()
    assert set(expected) == set(plan["validated_candidates"]) == set(plan["validated_evaluations"]) == set(plan["admission_records"]) == set(plan["validation_records"])
    with driver.guards():
        original = _source(authority)
        registry = SignalRegistry(root / "registry", candidate_root=root / "candidates")
        validator = SignalCandidateValidator(original, llm_runner=None,
            forbidden_identity_terms=read(REPO / "runs/diagnostics/gpre_native_initial_20261021_v1/stage/inputs.json")["sample"]["identity"]["identity_aliases"])
        policy = SimpleNamespace(validator=validator, _role_work_identity=SignalEvolutionEngine._role_work_identity)
        assert SignalEvolutionEngine._technical_validator_hash(policy) == plan["validator_hash"]
        for ref, data in expected.items():
            spec, skill = registry.load_candidate(ref)
            fixtures = registry.load_candidate_tests(ref)
            assert spec.to_dict() == data["spec"] and skill == data["skill"] and list(fixtures) == data["tests"]
            assert registry.load_spec(ref).to_dict() == data["spec"] and list(registry.load_tests(ref)) == data["tests"]
            digest = registry.candidate_hash(ref)
            assert digest == plan["validated_candidates"][ref] == signal_version_content_hash(spec, skill, fixtures)
            assert registry.load_skill(ref) is None
            checked = validator.validate(spec, skill=skill, tests=fixtures)
            assert checked.accepted and checked.executed_tests == len(fixtures)
            description = " ".join(__import__("re").findall(r"[a-z0-9]+", spec.description.casefold()))
            behavior = signal_execution_behavior_identity(spec, skill)
            assert description not in description_seen and behavior not in behavior_seen
            description_seen.add(description); behavior_seen.add(behavior)
            validation_binding = plan["validation_records"][ref]
            assert bind(validation_binding["path"]) == validation_binding
            validation = read(validation_binding["path"])
            contract = {"accepted": checked.accepted, "reasons": list(checked.reasons), "executed_tests": checked.executed_tests}
            assert {key: validation[key] for key in contract} == contract
            assert validation["signal_ref"] == ref and validation["candidate_hash"] == digest
            assert validation["validator_hash"] == plan["validator_hash"] and validation["input_registry_hash"] == authority["input_hash"]
            key = plan["validated_evaluations"][ref]
            admission_binding = plan["admission_records"][ref]
            assert bind(admission_binding["path"]) == admission_binding
            admission = registry.load_candidate_validation(ref, evaluation_key=key)
            assert admission == read(admission_binding["path"])
            assert admission["schema_version"] == "signal-candidate-admission-v1" and admission["accepted"] is True
            assert admission["contract_validation"] == contract and admission["candidate_hash"] == digest
            identity = admission["admission_identity"]
            assert identity["input_registry_hash"] == authority["input_hash"] and identity["validator_hash"] == plan["validator_hash"]
            assert identity["research_targets"] and identity["research_provenance"] == {
                "generation_case_ids": [], "induction_case_ids": [], "origin": "unknown", "source_input_hash": canonical_json_hash(authority)}
            folder = root / "registry" / spec.category / spec.signal_id / "versions" / f"v{spec.version}"
            assert (folder / "admission.json").read_bytes() == Path(admission_binding["path"]).read_bytes()
            marker = read(registry._candidate_spec_path(ref).parent / "promotion.json")
            assert canonical_json_hash(marker) == canonical_json_hash({"promoted": True, "mode": "capability_repair",
                "transition_id": plan["transition_id"], "evaluation_key": key,
                "output_registry_version": 13, "output_registry_hash": EXPECTED_OUTPUT})
            assert read(registry._candidate_spec_path(ref).parent / "candidate.json") == {"origin": "user-approved-capability-repair"}
            decisions.append({"ref": ref, "kind": data["kind"], "candidate_hash": digest,
                "validation_binding": validation_binding, "admission_binding": admission_binding,
                "admission_key": key, "executed_fixtures": checked.executed_tests, "effect_status": "unverified"})

        audit = registry.audit_capabilities()
        output = SignalRegistry(root / "registry", candidate_root=root / "candidates").freeze()
        assert audit.passed and len(audit.enabled_refs) == 18 and not audit.disabled
        assert output.version == 13 and output.registry_hash == EXPECTED_OUTPUT and len(output.specs) == 18
        assert [spec.ref for spec in output.specs] == result["refs"]
        assert set(expected).issubset(output.research_status)
        inherited_admission_status = {}
        for ref in authority["input_refs"]:
            if ref in authority["disabled"]:
                continue
            status = original.load_research_status(ref)
            assert dict(output.research_status.get(ref, {})) == status
            if status:
                inherited_admission_status[ref] = status
        assert set(output.research_status) == set(expected) | set(inherited_admission_status)
        assert all(output.research_status[ref]["technical_status"] == "admitted" and output.research_status[ref]["effect_status"] == "unverified" for ref in expected)
        old = registry.snapshot_from_refs(12, tuple(BASELINE["ordered_refs"]))
        assert old.registry_hash == BASELINE["registry_definition_hash"]
        transition_path = root / "registry/.transitions" / (plan["transition_id"] + ".json")
        transition_record = read(transition_path)
        assert transition_record["status"] == "applied" and transition_record["mode"] == "capability_repair"
        assert transition_record["repair_plan_hash"] == EXPECTED_PLAN and transition_record["repair_plan"] == plan
        assert transition_record["output_registry_version"] == 13 and transition_record["output_registry_hash"] == EXPECTED_OUTPUT
        assert transition_record["promoted"] == sorted(expected)
        replay = registry.capability_repair(plan, plan_hash=EXPECTED_PLAN)
        assert canonical_json_hash(asdict(replay)) == canonical_json_hash(result["transition"])

    successor = inventory(root / "registry")
    source = before["original_source"]
    changed = sorted(path for path, digest in source.items() if successor.get(path) != digest)
    deleted = sorted(set(source) - set(successor))
    added = sorted(set(successor) - set(source))
    allowed_changed = {"registry.json"}
    allowed_added = {".transitions/" + plan["transition_id"] + ".json"}
    empty_stats = []
    for ref, data in expected.items():
        spec = data["spec"]; prefix = spec["category"] + "/" + spec["signal_id"]
        allowed_changed.add(prefix + "/manifest.json")
        for name in ("spec.json", "tests.json", "admission.json"):
            allowed_added.add(prefix + "/versions/v" + str(spec["version"]) + "/" + name)
        old_manifest = read(ORIGINAL / prefix / "manifest.json")
        new_manifest = read(root / "registry" / prefix / "manifest.json")
        expected_manifest = {**old_manifest, "stable_version": spec["version"], "admission_keys": {
            **old_manifest.get("admission_keys", {}), str(spec["version"]): plan["validated_evaluations"][ref]}}
        assert canonical_json_hash(new_manifest) == canonical_json_hash(expected_manifest)
        stats = prefix + "/stats.json"
        if stats not in source:
            allowed_added.add(stats); empty_stats.append(stats)
            assert canonical_json_hash(read(root / "registry" / stats)) == canonical_json_hash(SignalStats().to_dict())
    assert not deleted and changed == sorted(allowed_changed) and added == sorted(allowed_added)
    assert len(changed) == 10 and len(added) == 32 and len(empty_stats) == 4
    assert len(decisions) == 9 and sum(row["executed_fixtures"] for row in decisions) == 27
    assert sum(row["kind"] == "fixture_identity_only" for row in decisions) == 7
    assert sum(row["kind"] == "approved_period_policy" for row in decisions) == 2
    after = {"formal_root": inventory(root), "candidate_root": inventory(root / "candidates"), "original_source": inventory(ORIGINAL)}
    assert after == before and after["original_source"] == BASELINE["original_files"]
    assert driver.code_bindings() == code
    manifest_path = OUT / "final-file-manifest.json"
    save(manifest_path, {"schema_version": "independent-formal-publication-file-manifest-v1", "before": before,
        "after": after, "successor_registry": successor, "inventory_identical_before_after_read_and_replay": True})
    verdict = {"schema_version": "independent-formal-capability-repair-review-v1",
        "verdict": "pass_exact_approved_publication", "actual_scope_verified": True,
        "migration_root": str(root), "plan_hash": EXPECTED_PLAN,
        "input_version": 12, "input_hash": BASELINE["registry_definition_hash"],
        "output_version": 13, "output_hash": EXPECTED_OUTPUT,
        "full_membership": [spec.ref for spec in output.specs], "capability_audit": audit.to_dict(),
        "actual_candidates": decisions, "fixture_count": 27,
        "inherited_admission_status_preserved": inherited_admission_status,
        "original_198_unchanged": True, "source_definition_snapshot_reconstructed": True,
        "successor_original_files_unchanged": 188, "successor_modified_paths": changed,
        "successor_new_files": added, "successor_empty_default_stats": empty_stats,
        "all_nine_exact_promotion_markers_verified": True, "transition_status": "applied",
        "normal_fresh_read": "pass", "exact_applied_replay": "pass_no_writes",
        "replay_transition": asdict(replay), "entire_formal_candidate_source_inventories_unchanged": True,
        "code_files": code,
        "evidence": [bind(root / "plan.json"), bind(root / "prepared.json"), bind(root / "result.json"),
            bind(authority_path), bind(transition_path), bind(driver.BASE / "formal-prepare.log"),
            bind(driver.BASE / "formal-execute.log"), bind(manifest_path),
            bind(OUT.parent / "transaction-review/prepublication-review-v4.json")],
        "external_calls": 0, "labels": 0, "business_pointer_actions": 0,
        "new_mining": 0, "fresh_consumers": 0, "full_slow_completion": False,
        "effect_status": "unverified", "independent_benefit": "unknown", "mvp": "open",
        "limits": ["The actual capability audit is the approved local executability criterion; untouched LLM skill presence is not fresh model execution.",
            "The 27-fixture rerun is deterministic technical contract verification, not independent research gain.",
            "All formal artifacts were read only; exact applied replay was verified against entire before/after inventories. The original result remains completed_pending_independent_review, with this review stored separately.",
            "Temporary prepublication successor tests do not establish actual new downstream use of this formal published Registry."]}
    save(OUT / "final-review.json", verdict)
    print(json.dumps({"verdict": verdict["verdict"], "output_version": 13, "count": 18,
        "updates": 9, "fixtures": 27, "modified_inherited_paths": 10, "new_registry_files": 32,
        "original_198_unchanged": True, "read_and_replay_writes": 0,
        "review_sha256": bind(OUT / "final-review.json")["sha256"]}, indent=2))


if __name__ == "__main__": main()
