"""Independent synthetic historical-identity/fresh-admission controls, no real export."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import socket
from unittest.mock import patch
from contextlib import ExitStack

from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.memory.knowledge import KnowledgeUseStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research import evolution_control as control
from stock_opportunity_agent.research.evolution_core import PlanEvaluationConfig
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.signal_library import SignalRegistry
from tests.test_historical_registry_definition_reads import HistoricalRegistryDefinitionReadsTests as Fixture
from tests.evolution_runtime_test_support import SHA_A, SHA_B

OUT = Path(__file__).resolve().parent
SOURCE = Path(control.__file__)
BEFORE = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
assert BEFORE == "593283673033f404ea39bd46b7872da7f704cf7d8b9902165381dbdaa5c3036d"
checks = []
forbidden_hits = []


def forbidden(*args, **kwargs):
    forbidden_hits.append(True)
    raise AssertionError("No real labels/network/model/full-stage operation")


def rejected(action, expected=(ValidationError, FileNotFoundError)):
    try:
        action()
    except expected:
        return
    raise AssertionError("negative control accepted")


f = Fixture()
f.setUp()
try:
    with ExitStack() as guards:
        for owner, method in ((socket, "socket"), (socket, "create_connection"),
                              (LabelStore, "__init__"), (LabelStore, "load"), (LabelStore, "record"),
                              (LabelStore, "ground_truth")):
            guards.enter_context(patch.object(owner, method, forbidden))
        for method in ("complete_json", "complete_json_with_token_scores", "complete_binary_token_with_scores"):
            guards.enter_context(patch.object(StructuredRoleClient, method, forbidden))
        source, registry, original, contract = f.source()
        f.make_legacy_fixture(registry)
        before = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}
        with patch.object(KnowledgeUseStore, "profiles", side_effect=AssertionError("history helper cannot fabricate/read profiles")), patch.object(SignalRegistry, "audit_capabilities", side_effect=AssertionError("history helper cannot certify fixtures")):
            historical = control._historical_registry_snapshot(registry)
        assert historical.registry_hash == original.registry_hash
        assert [s.ref for s in historical.specs] == [s.ref for s in original.specs]
        assert dict(historical.learned_profiles) == {} and dict(historical.skills) == dict(original.skills)
        assert before == {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}
        checks.append("legacy missing-CIK definition/order/skill identity reads without profile/audit or mutation")
        rejected(registry.freeze)
        checks.append("fresh capability-audited freeze still rejects the identical legacy fixture")

        header = registry.root / "registry.json"
        manifest = registry.root / "financial/cash_reserves/manifest.json"
        spec = registry.root / "financial/cash_reserves/versions/v1/spec.json"
        for path, field, values in ((header, "version", (True, 1.0)),
                                     (manifest, "stable_version", (True, 1.0)),
                                     (spec, "version", (True, 1.0))):
            raw = path.read_bytes()
            for value in values:
                payload = json.loads(raw)
                payload[field] = value
                path.write_text(json.dumps(payload))
                rejected(lambda: control._historical_registry_snapshot(registry))
            path.write_bytes(raw)
        checks.append("six raw header/stable/spec bool/float version mutations rejected")
        empty = SignalRegistry(f.root / "empty")
        rejected(lambda: control._historical_registry_snapshot(empty))
        duplicate = registry.root / "other/cash_reserves"
        shutil.copytree(registry.root / "financial/cash_reserves", duplicate)
        rejected(lambda: control._historical_registry_snapshot(registry))
        shutil.rmtree(duplicate.parent)
        checks.append("empty registry and duplicate/path-mismatched identity rejected")

        # These are temporary synthetic events, not historical market outcomes.
        committed, future = f.event(1), f.event(2)
        registry.record_learning_events((committed, future))
        target, envelope = f.export(source, contract)
        assert [event["event_id"] for event in envelope["manifest"]["learning_events"]] == [committed.event_id]
        control.apply_slow_history_manifest(workspace=target, manifest=envelope["manifest"])
        checks.append("temporary history export/apply retains only committed event cutoff, no future event")
        declared = replace(contract, slow_history_manifest_hash=envelope["manifest_hash"])
        assert control.validate_slow_history_manifest(workspace=target, contract=declared) == envelope["manifest"]
        artifact = source / "experiments/cycles/cycle-0001/slow_memory.json"
        prior = artifact.read_bytes()
        artifact.write_text('{"changed":true}')
        rejected(lambda: control.validate_slow_history_manifest(workspace=target, contract=declared))
        artifact.write_bytes(prior)
        checks.append("original frozen history artifact validation remains active")

        raw = spec.read_bytes()
        changed = json.loads(raw)
        changed["definition"]["description"] += " Changed historical definition."
        spec.write_text(json.dumps(changed))
        rejected(lambda: f.export(source, contract, f.root / "changed-definition"))
        spec.write_bytes(raw)
        unknown = json.loads(raw)
        unknown["execution"]["function"] = "financial.retired_unregistered_function"
        spec.write_text(json.dumps(unknown))
        unreadable_today = control._historical_registry_snapshot(registry)
        assert unreadable_today.registry_hash != original.registry_hash
        assert any(s.function == "financial.retired_unregistered_function" for s in unreadable_today.specs)
        audit = registry.audit_capabilities().to_dict()
        assert "deterministic_function_missing" in audit["disabled"]["cash_reserves:v1"]
        rejected(registry.freeze)
        spec.write_bytes(raw)
        checks.append("unknown current callable remains readable as historical definition, but fresh freeze does not certify it")
        skill = target / "signals/management/guidance_acceleration/versions/v1/skill.md"
        skill.write_text(skill.read_text() + "\nChanged frozen target skill.\n")
        rejected(lambda: control.apply_slow_history_manifest(workspace=target, manifest=envelope["manifest"]))
        checks.append("source definition and existing-target skill drift fail authority comparisons")

        cycle_path = source / "cycle_state.json"
        raw_cycle = cycle_path.read_bytes()
        for index, value in enumerate((True, 1.9, "1", 0)):
            changed = json.loads(raw_cycle)
            changed["current_signal_registry_version"] = value
            cycle_path.write_text(json.dumps(changed))
            destination = f.root / f"typed-pointer-{index}"
            rejected(lambda: f.export(source, contract, destination))
            assert not destination.exists()
            cycle_path.write_bytes(raw_cycle)
            invalid = deepcopy(envelope["manifest"])
            invalid["registry_version"] = value
            rejected(lambda: control.apply_slow_history_manifest(workspace=destination, manifest=invalid))
            assert not destination.exists()
            body_hash = control._canonical_hash(invalid)
            manifest_path = destination / "slow_history/manifest.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps({"manifest": invalid, "manifest_hash": body_hash}))
            bad_contract = replace(contract, slow_history_manifest_hash=body_hash)
            rejected(lambda: control.validate_slow_history_manifest(workspace=destination, contract=bad_contract))
        checks.append("typed source pointer/export, apply-before-write and coherently rehashed history-validator4badtypes reject")

        g = Fixture()
        g.setUp()
        try:
            boot_source, _, boot_snapshot, boot_contract = g.source(history=False)
            dataset = control.ApprovedDevelopmentDataset(discovery=(), anchor=(), evolution_validation=(),
                                                        locked_test_hash=SHA_B, approved_manifest_hash=SHA_A)
            bootstrap = g.root / "bootstrap"
            control.build_slow_bootstrap_manifest(workspace=bootstrap, source_workspaces=(boot_source,),
                dataset=dataset, signal_snapshot=boot_snapshot, evaluation_contract=PlanEvaluationConfig().to_dict())
            manifest_path = bootstrap / "slow_bootstrap/manifest.json"
            valid = json.loads(manifest_path.read_text())
            bound = replace(boot_contract, cycle_mode="slow_bootstrap",
                            limits={**boot_contract.limits, "plan_rounds_per_signal_cycle": 0},
                            slow_bootstrap_manifest_hash=valid["manifest_hash"])
            assert control.validate_slow_bootstrap_manifest(workspace=bootstrap, contract=bound,
                signal_snapshot=boot_snapshot) == valid["manifest"]
            for value in (True, 1.9, "1", 0):
                invalid = {**valid["manifest"], "input_signal_registry_version": value}
                invalid_hash = control._canonical_hash(invalid)
                manifest_path.write_text(json.dumps({"manifest": invalid, "manifest_hash": invalid_hash}))
                invalid_contract = replace(bound, slow_bootstrap_manifest_hash=invalid_hash)
                rejected(lambda: control.validate_slow_bootstrap_manifest(workspace=bootstrap,
                    contract=invalid_contract, signal_snapshot=boot_snapshot))
                manifest_path.write_text(json.dumps(valid))
                rejected(lambda: control.validate_slow_bootstrap_manifest(workspace=bootstrap,
                    contract=bound, signal_snapshot=replace(boot_snapshot, version=value)))
            assert control.validate_slow_bootstrap_manifest(workspace=bootstrap, contract=bound,
                signal_snapshot=boot_snapshot) == valid["manifest"]
        finally:
            g.doCleanups()
        checks.append("real temporary bootstrap build->validator validint positive and coherent manifest/snapshot4badtypes rejected")
finally:
    f.doCleanups()
assert not forbidden_hits and hashlib.sha256(SOURCE.read_bytes()).hexdigest() == BEFORE
report = {"status": "PASS_bounded_historical_read_and_typed_identity_controls",
          "source_sha256": BEFORE, "checks": checks, "forbidden_calls": len(forbidden_hits),
          "scope": "Only temporary synthetic source/catalog/committed records/events. No real source export, labels/API/model. Native fresh fixture execution occurs only inside temp audited freeze.",
          "remaining": "Original pointer coercion old/d966 accepted evidence retained; final caller/validator rejects it. No real source import/fresh execution readiness or whole control-plane numeric strictness claim."}
target = OUT / "review.json"
target.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": len(checks), "review_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}))
