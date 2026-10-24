"""Independent actual-driver controls on disposable local Registry clones only."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts"))
import repair_historical_signal_registry as driver
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import SignalRegistry
from stock_opportunity_agent.signal_library import signal_execution_behavior_identity
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator
from dataclasses import replace
from review_support import BASELINE, ORIGINAL, assert_original_unchanged, expected_candidate_data, inventory


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def reopen(root):
    return SignalRegistry(root / "registry", candidate_root=root / "candidates")


def apply(root, plan, registry=None):
    with driver.guards():
        return (registry or reopen(root)).capability_repair(plan, plan_hash=canonical_json_hash(plan))


def child():
    mode, raw_root = sys.argv[1:3]
    root = Path(raw_root)
    assert OUT in root.resolve().parents and root != driver.ROOT
    plan = driver.read(root / "plan.json")
    if mode == "--child-interrupt":
        registry = reopen(root)
        stage, target_ref = sys.argv[3:5]
        def fault(actual_stage, ref):
            if actual_stage == stage and (target_ref == "any" or ref == target_ref):
                os._exit(73)
        registry._fault_injector = fault
        apply(root, plan, registry)
        raise AssertionError("OS interruption checkpoint not reached")
    elif mode == "--child-recover":
        driver.execute(root, canonical_json_hash(plan))
    else:
        raise AssertionError(mode)


def main():
    original_before = inventory(ORIGINAL)
    formal_existed = driver.ROOT.exists()
    code_before = driver.code_bindings()
    rows = []
    def record(name, details):
        assert_original_unchanged()
        for bound in code_before:
            assert driver.binding(bound["path"]) == bound, "Production code drift during independent controls"
        rows.append({"name": name, "passed": True, **details})
        save(OUT / "partial-results.json", {"controls": rows, "original_198_unchanged": True})

    with tempfile.TemporaryDirectory(prefix="scratch-", dir=OUT) as temp:
        base = Path(temp) / "prepared"
        with driver.guards():
            base_plan = driver.prepare_at(base)
        independent = expected_candidate_data()
        base_registry = reopen(base)
        for ref, expected in independent.items():
            spec, skill = base_registry.load_candidate(ref)
            assert spec.to_dict() == expected["spec"] and skill == expected["skill"]
            assert list(base_registry.load_candidate_tests(ref)) == list(expected["tests"])
        assert driver.read(base / "prepared.json")["fixture_count"] == 27
        assert inventory(base / "registry") == BASELINE["original_files"]
        record("actual_preparation_independent_candidate_crosscheck", {"candidates": 9, "fixtures": 27, "published": 0})

        counter = 0
        def fresh(name):
            nonlocal counter
            counter += 1
            root = Path(temp) / f"case-{counter:03d}-{name}"
            shutil.copytree(base, root)
            plan = deepcopy(base_plan)
            for field in ("authority",):
                plan[field] = driver.binding(root / Path(plan[field]["path"]).relative_to(base))
            for field in ("admission_records", "validation_records"):
                for ref, bound in plan[field].items():
                    plan[field][ref] = driver.binding(root / Path(bound["path"]).relative_to(base))
            save(root / "plan.json", plan)
            save(root / "prepared.json", {"plan_hash": canonical_json_hash(plan)})
            return root, plan

        def authority_change(root, plan, mutate):
            path = root / "authority.json"
            data = driver.read(path); mutate(data); save(path, data)
            plan["authority"] = driver.binding(path)

        def reject(name, mutate, expected_text=None):
            root, plan = fresh(name)
            mutate(root, plan)
            reg = reopen(root)
            try:
                apply(root, plan, reg)
            except ValidationError as exc:
                message = str(exc)
                assert "frozen implementation changed" not in message, message
                if expected_text:
                    assert expected_text in message, (name, message)
            else:
                raise AssertionError("Unauthorized counterexample accepted: " + name)
            assert reg.version == 12
            assert not (reg.root / ".transitions" / (plan["transition_id"] + ".json")).exists()
            assert not list(reg.candidate_root.rglob("promotion.json"))
            record(name, {"rejected": message, "version": 12, "prepared": False})

        # Complete real driver flow including exact applied replay and all effects unverified.
        root, plan = fresh("positive")
        result = driver.execute(root, canonical_json_hash(plan))
        output = reopen(root).freeze()
        assert result["updates"] == 9 and output.version == 13 and len(output.specs) == 18
        assert {row["next_ref"] for row in BASELINE["disabled_fixture_details"].values()} == set(result["transition"]["promoted"])
        before = inventory(root)
        assert asdict(apply(root, plan)) == result["transition"]
        assert inventory(root) == before
        record("complete_driver_publish_replay_disposable_only", {"output_version": 13, "count": 18,
            "promoted": result["transition"]["promoted"], "output_hash": output.registry_hash,
            "all_nine_effect_unverified": all(output.research_status[ref]["effect_status"] == "unverified" for ref in plan["validated_candidates"]),
            "replay_writes": 0})

        # Ordinary entry remains fail-closed on the exact unhealthy baseline.
        root, plan = fresh("ordinary")
        reg = reopen(root); authority = driver.read(root / "authority.json")
        try:
            reg.promote_validated_batch(plan["validated_candidates"], validated_evaluations=plan["validated_evaluations"],
                transition_id="ordinary-independent", input_version=12, input_hash=authority["input_hash"], input_refs=authority["input_refs"])
        except ValidationError as exc:
            assert "capability audit failed" in str(exc)
        else:
            raise AssertionError("Ordinary unhealthy promotion accepted")
        assert not (reg.root / ".transitions/ordinary-independent.json").exists()
        record("ordinary_entry_unhealthy_baseline", {"rejected": True, "version": reg.version})

        root, plan = fresh("source_aliases"); template = reopen(root)
        for mode in ("original", "target_alias", "candidate_alias"):
            alias = root / (mode + "-alias")
            if mode != "original": alias.symlink_to(ORIGINAL, target_is_directory=True)
            reg = object.__new__(SignalRegistry); reg.__dict__.update(template.__dict__)
            if mode == "original": reg.root = ORIGINAL
            elif mode == "target_alias": reg.root = alias
            else: reg.candidate_root = alias
            try: apply(root, plan, reg)
            except ValidationError as exc: assert "must be separate" in str(exc)
            else: raise AssertionError("Source/root alias accepted")
            record("source_alias_" + mode, {"rejected_before_write": True})

        def candidate_symlink(root, plan):
            path = reopen(root)._candidate_spec_path("cash_reserves:v3").parent / "unexpected-link"
            path.symlink_to(root / "authority.json")
        reject("candidate_symlink_tree", candidate_symlink, "symlink")

        # Preserve the exact approved scope; renamed duplicate is only a validator negative control.
        root, plan = fresh("stable_duplicate"); reg = reopen(root)
        prior, skill = reg.load_candidate("cash_reserves:v3")
        duplicate = replace(prior, signal_id="independent_duplicate_cash", version=1,
            description="Measure the point-in-time cash buffer for an independent duplicate control.")
        original_view = object.__new__(SignalRegistry); original_view.__dict__.update(reg.__dict__)
        original_view.root = ORIGINAL; original_view.knowledge_workspace_root = ORIGINAL.parent
        checked = SignalCandidateValidator(original_view, llm_runner=None).validate(duplicate,
            skill=None, tests=reg.load_candidate_tests(prior.ref))
        assert not checked.accepted and checked.executed_tests == 0
        assert any("execution-semantic duplicate" in reason for reason in checked.reasons)
        assert signal_execution_behavior_identity(prior, skill) == signal_execution_behavior_identity(duplicate, skill)
        assert SignalCandidateValidator._behavior_identity(prior, skill) == signal_execution_behavior_identity(prior, skill)
        record("actual_validator_rename_resistant_stable_duplicate", {"reasons": list(checked.reasons), "staged_duplicate": 0})
        def mutate_duplicate_description(root, plan):
            reg = reopen(root); ref = "cash_reserves:v3"; path = reg._candidate_spec_path(ref)
            spec = driver.read(path)
            spec["definition"]["description"] = reg.load_spec("revenue_growth_yoy:v3").description
            save(path, spec); plan["validated_candidates"][ref] = reg.candidate_hash(ref)
        reject("duplicate_description_stopped_by_immutable_scope", lambda r, p: mutate_duplicate_description(r, p), "unapproved definition")

        for field, value in (("input_version", 11), ("input_hash", "f" * 64), ("input_refs", BASELINE["ordered_refs"][::-1])):
            reject("wrong_" + field, lambda r, p, f=field, v=value: authority_change(r, p, lambda a: a.update({f: v})))
        reject("disabled_reason_changed", lambda r, p: authority_change(r, p, lambda a: a["disabled"]["cash_reserves:v2"].append("other failure")))
        reject("disabled_ref_omitted", lambda r, p: authority_change(r, p, lambda a: a["disabled"].pop("cash_reserves:v2")))
        reject("missing_update", lambda r, p: p["validated_candidates"].pop("cash_reserves:v3"))
        reject("extra_update", lambda r, p: p["validated_candidates"].update({"guidance_acceleration:v4": "a" * 64}))
        reject("skipped_next_version", lambda r, p: p["validated_candidates"].update({"cash_reserves:v4": p["validated_candidates"].pop("cash_reserves:v3")}))
        reject("candidate_hash_wrong", lambda r, p: p["validated_candidates"].update({"cash_reserves:v3": "a" * 64}))
        reject("admission_key_wrong", lambda r, p: p["validated_evaluations"].update({"cash_reserves:v3": "a" * 64}))
        reject("missing_admission_key", lambda r, p: p["validated_evaluations"].pop("cash_reserves:v3"))
        reject("missing_validation_binding", lambda r, p: p["validation_records"].pop("cash_reserves:v3"))
        reject("missing_code_binding", lambda r, p: p.update(code_files=[x for x in p["code_files"] if not x["path"].endswith("signal_capability_repair.py")]))

        def mutate_spec(root, plan, field, value, ref="cash_reserves:v3"):
            reg = reopen(root); path = reg._candidate_spec_path(ref)
            spec = driver.read(path)
            if field == "description": spec["definition"]["description"] = value
            elif field == "parameter": spec["parameters"]["positive_min"] = value
            elif field == "function": spec["execution"]["function"] = value
            elif field == "source": spec["raw_retrieval"]["source_types"] = value
            elif field == "policy": spec["parameters"]["period_policy"] = value
            save(path, spec); plan["validated_candidates"][ref] = reg.candidate_hash(ref)
        reject("seven_threshold_drift", lambda r, p: mutate_spec(r, p, "parameter", 99000000), "unapproved definition")
        reject("seven_description_drift", lambda r, p: mutate_spec(r, p, "description", "Measure cash reserves."), "unapproved definition")
        reject("seven_function_drift", lambda r, p: mutate_spec(r, p, "function", "financial.revenue_growth_yoy"), "unapproved definition")
        reject("seven_retrieval_drift", lambda r, p: mutate_spec(r, p, "source", ["financials", "filing", "company_facts"]), "unapproved definition")
        reject("approved_margin_policy_drift", lambda r, p: mutate_spec(r, p, "policy", "adjacent_yoy", "gross_margin_change:v4"), "approved definition")

        def mutate_fixture(root, plan, mode):
            reg = reopen(root); ref = "cash_reserves:v3"
            path = reg._candidate_spec_path(ref).parent / "tests.json"
            data = driver.read(path); fixture = data["tests"][0]; doc = fixture["documents"][0]
            body = json.loads(doc["content"])
            if mode == "body_only": doc.pop("metadata")
            elif mode == "metadata_only": body.pop("cik")
            elif mode == "mismatched": doc["metadata"]["cik"] = "0001999992"
            elif mode == "malformed": body["cik"] = "synthetic"
            elif mode == "expected": fixture["expected"] = "unavailable"
            elif mode == "period": body["facts"][0]["end"] = "2024-12-30"
            elif mode == "value": body["facts"][0]["value"] = 151000000
            elif mode == "unit": body["facts"][0]["unit"] = "EUR"
            elif mode == "company": fixture["company_id"] = "cik_0001999991"
            elif mode == "empty": data["tests"] = []
            doc["content"] = json.dumps(body, sort_keys=True, separators=(",", ":"))
            save(path, data); plan["validated_candidates"][ref] = reg.candidate_hash(ref)
        for mode in ("body_only", "metadata_only", "mismatched", "malformed", "expected", "period", "value", "unit", "company", "empty"):
            reject("fixture_" + mode, lambda r, p, m=mode: mutate_fixture(r, p, m))

        def bound_validation(root, plan, field, value):
            ref = "cash_reserves:v3"; path = Path(plan["validation_records"][ref]["path"])
            row = driver.read(path); row[field] = value; save(path, row)
            plan["validation_records"][ref] = driver.binding(path)
        for field, value in (("executed_tests", 0), ("validator_hash", "a" * 64), ("input_registry_hash", "a" * 64), ("accepted", False)):
            reject("validation_" + field, lambda r, p, f=field, v=value: bound_validation(r, p, f, v))
        def legacy_admission(root, plan):
            ref = "cash_reserves:v3"; path = Path(plan["admission_records"][ref]["path"])
            row = driver.read(path); row["schema_version"] = "signal-candidate-validation-v2"; save(path, row)
            plan["admission_records"][ref] = driver.binding(path)
        reject("legacy_admission", legacy_admission)
        reject("unbound_validation_bytes", lambda r, p: Path(p["validation_records"]["cash_reserves:v3"]["path"]).write_text("{}"))
        reject("unbound_admission_bytes", lambda r, p: Path(p["admission_records"]["cash_reserves:v3"]["path"]).write_text("{}"))

        def mutate_inherited(root, plan, mode):
            path = root / "registry/financial/cash_reserves/versions/v1/tests.json"
            if mode == "changed": path.write_bytes(path.read_bytes() + b" ")
            elif mode == "deleted": path.unlink()
            elif mode == "extra": (root / "registry/extra.json").write_text("{}")
        for mode in ("changed", "deleted", "extra"):
            reject("inherited_" + mode, lambda r, p, m=mode: mutate_inherited(r, p, m))
        for status in ("prepared", "unknown"):
            reject("unrelated_" + status, lambda r, p, s=status: save(r / "registry/.transitions/unrelated.json", {"status": s}))

        phases = ("after_transition_prepared", "after_stable_spec", "after_stable_tests", "after_stable_stats",
            "after_stable_manifest", "after_stable_admission", "after_repair_output_audit", "after_registry_version",
            "before_output_snapshot", "after_output_snapshot", "after_promotion_record", "before_transition_applied")
        for phase in phases:
            root, plan = fresh(phase); reg = reopen(root); fired = []
            def fault(stage, ref):
                if stage == phase and not fired:
                    fired.append((stage, ref))
                    if phase == "after_repair_output_audit":
                        assert reg.version == 12 and not list(reg.candidate_root.rglob("promotion.json"))
                    raise RuntimeError("independent interruption")
            reg._fault_injector = fault
            try: apply(root, plan, reg)
            except RuntimeError as exc: assert str(exc) == "independent interruption"
            else: raise AssertionError("Fault did not fire: " + phase)
            reopened = reopen(root)
            for read in (reopened.freeze, reopened.list_signal_cards, lambda: reopened.load_spec("cash_reserves:v2")):
                try: read()
                except ValidationError: pass
                else: raise AssertionError("Prepared read became visible: " + phase)
            transition = apply(root, plan, reopened)
            assert transition.output_version == 13 and len(reopened.freeze().specs) == 18
            before = inventory(root); assert apply(root, plan) == transition and inventory(root) == before
            record("fault_" + phase, {"fired": fired, "recovered_version": 13, "idempotent": True})

        # Inspect unknown status/schema/missing status after a genuinely healthy pre-bump output.
        root, plan = fresh("invalid_status"); reg = reopen(root)
        def halt_after_audit(stage, ref):
            if stage == "after_repair_output_audit": raise RuntimeError("independent interruption")
        reg._fault_injector = halt_after_audit
        try: apply(root, plan, reg)
        except RuntimeError: pass
        transition_path = root / "registry/.transitions" / (plan["transition_id"] + ".json")
        original_transition = driver.read(transition_path)
        for mode in ("unknown_status", "missing_status", "unknown_schema"):
            row = deepcopy(original_transition)
            if mode == "unknown_status": row["status"] = "unknown"
            elif mode == "missing_status": row.pop("status")
            else: row["schema_version"] = "unknown"
            save(transition_path, row); recovered = reopen(root)
            for read in (recovered.freeze, recovered.list_signal_cards, lambda: recovered.load_spec("cash_reserves:v3")):
                try: read()
                except ValidationError: pass
                else: raise AssertionError("Invalid transition exposed next versions")
            try: apply(root, plan, recovered)
            except ValidationError: pass
            else: raise AssertionError("Invalid transition recovered")
            assert recovered.version == 12
            record("invalid_transition_" + mode, {"normal_reads_blocked": 3, "version": 12})
        save(transition_path, original_transition)
        assert apply(root, plan).output_version == 13

        # Exact applied replay checks all durable promotion records, with no automatic repair writes.
        root, plan = fresh("markers"); apply(root, plan); reg = reopen(root)
        for ref in ("cash_burn_rate_elevated:v3", "revenue_growth_yoy:v4"):
            path = reg._candidate_spec_path(ref).parent / "promotion.json"; prior = path.read_bytes()
            for mode in ("missing", "corrupt", "boolean_to_integer", "integer_to_float"):
                if mode == "missing": path.unlink()
                elif mode == "corrupt": path.write_text("{}")
                else:
                    row = json.loads(prior)
                    if mode == "boolean_to_integer": row["promoted"] = 1
                    else: row["output_registry_version"] = 13.0
                    save(path, row)
                before = inventory(root)
                try: apply(root, plan)
                except ValidationError as exc: assert "marker" in str(exc)
                else: raise AssertionError("Applied marker mutation accepted")
                assert inventory(root) == before and reg.version == 13
                record("applied_marker_" + ref + "_" + mode, {"rejected": True, "writes": 0})
                path.write_bytes(prior)
        assert apply(root, plan).output_version == 13

        # Changed prepared candidate/plan refuses exact recovery, remaining unreadable.
        root, plan = fresh("recovery_identity"); reg = reopen(root)
        def halt_prepared(stage, ref):
            if stage == "after_transition_prepared": raise RuntimeError("independent interruption")
        reg._fault_injector = halt_prepared
        try: apply(root, plan, reg)
        except RuntimeError: pass
        changed = deepcopy(plan); changed["validated_evaluations"]["cash_reserves:v3"] = "b" * 64
        try: apply(root, changed)
        except ValidationError: pass
        else: raise AssertionError("Changed prepared plan accepted")
        path = reopen(root)._candidate_spec_path("cash_reserves:v3"); prior = path.read_bytes()
        row = driver.read(path); row["parameters"]["positive_min"] = 99000000; save(path, row)
        try: apply(root, plan)
        except ValidationError: pass
        else: raise AssertionError("Changed prepared candidate accepted")
        try: reopen(root).freeze()
        except ValidationError: pass
        else: raise AssertionError("Failed recovery became readable")
        path.write_bytes(prior)
        assert apply(root, plan).output_version == 13
        record("prepared_exact_candidate_key_plan_identity", {"wrong_key_rejected": True, "candidate_change_rejected": True, "read_blocked": True})

        # Abrupt process exit after a real durable partial admission, then fresh process recovery.
        root, plan = fresh("os_exit")
        command = [sys.executable, str(Path(__file__).resolve())]
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(REPO / "src")}
        exited = subprocess.run(command + ["--child-interrupt", str(root), "after_stable_admission", "liquidity_runway_months:v4"],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
        assert exited.returncode == 73, exited.stderr
        try: reopen(root).freeze()
        except ValidationError: pass
        else: raise AssertionError("OS partial output readable")
        recovered = subprocess.run(command + ["--child-recover", str(root)], cwd=REPO, env=env,
            capture_output=True, text=True, timeout=60)
        assert recovered.returncode == 0, recovered.stderr
        assert reopen(root).freeze().version == 13
        record("abrupt_process_exit_fresh_process_exact_recovery", {"exit_code": 73, "recovery_exit": 0, "version": 13})

    assert inventory(ORIGINAL) == original_before
    assert driver.ROOT.exists() == formal_existed, "Formal migration destination was touched"
    result = {"schema_version": "independent-capability-repair-controls-v1", "controls": rows,
        "passed_controls": len(rows), "original_198_unchanged": True, "formal_migration_destination_touched": False,
        "production_source_bindings": code_before, "external_calls": 0, "labels": 0,
        "scope": "Disposable local clone transaction controls. No formal migration, fresh consumer, Mining, Slow completion or gain claim."}
    save(OUT / "result.json", result)
    print(json.dumps({"passed_controls": len(rows), "original_198_unchanged": True, "formal_destination_touched": False}))


if __name__ == "__main__":
    if len(sys.argv) > 1: child()
    else: main()
