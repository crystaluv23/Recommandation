"""Imported event authority across Slow consumption, Fast freeze and restart."""

import json
import hashlib
from dataclasses import replace
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.signal_library import SignalExecutor
from stock_opportunity_agent.research.evolution_control import _contract_bound_import_learning_events
from stock_opportunity_agent.research.signal_evolution import DualLoopEvolutionEngine
from stock_opportunity_agent.research.signal_tracking import imported_learning_events, record_committed_signal_use
from tests import test_signal_tracking as tracking_fixture
from tests.evolution_runtime_test_support import make_contract
from tests.scheme_evolution_test_support import NOW, sec_company_facts_content, make_record


class ImportedSignalFeedbackTests(TestCase):
    setUp = tracking_fixture.SignalTrackingTests.setUp
    event = tracking_fixture.SignalTrackingTests.event

    def commit_fixture_round(self):
        """Publish canonical round records as well as the ledger test's pointer."""
        workspace = self.engine.workspace
        record = make_record("fixture_plan", 1.0, (1.0,))
        atomic_write_json(workspace.root / "plans" / record.plan_id / "record.json", record.to_dict())
        checkpoint = workspace.root / "experiments" / "round-0001" / "checkpoint.json"
        atomic_write_json(checkpoint, {"round_id": 1, "plan_ids": [record.plan_id],
                                     "run_contract_hash": "fixture"})
        atomic_write_json(workspace.state_path, {"last_completed_round": 1, "checkpoint_ref": str(checkpoint)})

    def publish_next_version(self):
        """Use production admission/publication, preserving prior admission identity."""
        prior = self.registry.load_spec(self.ref)
        current = replace(prior, version=prior.version + 1,
            parameters={**prior.parameters, "positive_min": .18})
        self.registry.stage_candidate(current, skill=None, tests=self.registry.load_tests(prior.ref),
            origin="fixture:historical-feedback-update")
        empty = {"candidate_refs": (), "induction_case_ids": {}, "validation_case_ids": {},
            "failures": {}, "audit": {}}
        with patch.object(self.engine, "_run_signal_mining", return_value=empty), \
             patch.object(self.engine, "_run_signal_update", return_value={**empty, "candidate_refs": (current.ref,)}):
            result = self.engine._validate_cycle(self.registry.freeze(), cycle_id=2)
        self.assertIn(current.ref, result.validated_candidates)
        self.registry.promote_validated_batch(result.validated_candidates,
            validated_evaluations=result.candidate_evaluations, transition_id="historical-feedback-update",
            input_version=result.input_registry_version, input_hash=result.input_registry_hash,
            input_refs=result.input_signal_refs)
        return current

    def bind(self, events, *, history=False, mode=None, cycle_artifacts=()):
        root = self.engine.workspace.root
        directory = "slow_history" if history else "slow_bootstrap"
        field = "learning_events" if history else "signal_learning_events"
        manifest = {"schema_version": "slow-history-manifest-v2" if history else "slow-bootstrap-manifest-v2",
            field: [event.to_dict() for event in events]}
        if history:
            manifest.update(source_namespace="source-test", committed_slow_cycle=1, cycle_artifacts=list(cycle_artifacts))
        digest = canonical_json_hash(manifest)
        path = root / directory / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"manifest_hash": digest, "manifest": manifest}))
        mode = mode or ("slow_only" if history else "slow_bootstrap")
        base = make_contract()
        contract = replace(base, schema_version="evolution-run-contract-v8", cycle_mode=mode,
            limits={**base.limits, "plan_rounds_per_signal_cycle": 1 if mode == "fast_then_slow" else 0},
            **{f"{directory}_manifest_hash": digest})
        contract.freeze(root / "run_contract.json")
        return contract, path

    def bind_target_history(self, source, row, scope):
        """Copy one complete input unit with its recorded disclosure and hash."""
        root = self.engine.workspace.root
        relative = "experiments/cycles/cycle-0001/slow_input.json"
        path = root / "slow_history/source-test" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = {"feedback_rows": [row], "source_manifest": [] if scope is None else [
            {"ref": row["feedback_ref"], "content_hash": canonical_json_hash(row), "visible_to": scope}]}
        path.write_text(json.dumps(raw))
        (root / "run_contract.json").unlink(missing_ok=True)
        self.bind((source,), history=True, mode="fast_then_slow", cycle_artifacts=[
            {"cycle_id": 1, "path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}])
        return path.read_bytes()

    def test_imported_target_scope_ceiling_survives_nested_history(self):
        source = self.event("history-target", 4.0, round_id=1)
        record_committed_signal_use(self.registry, (source,))
        self.commit_fixture_round()
        rows, _manifest = self.engine._committed_slow_feedback()
        row = next(row for row in rows if row["kind"] == "signal_target_observation")
        original = self.bind_target_history(source, row, ["H1", "H3", "E2", "Update", "reflection"])
        rows, manifest = self.engine._committed_slow_feedback()
        imported = next(row for row in rows if row["kind"] == "signal_target_observation" and row["feedback_ref"].startswith("slow-history:"))
        scope = next(item["visible_to"] for item in manifest if item["ref"] == imported["feedback_ref"])
        self.assertNotIn("H1", scope)
        self.assertEqual((self.engine.workspace.root / "slow_history/source-test/experiments/cycles/cycle-0001/slow_input.json").read_bytes(), original)
        self.bind_target_history(source, imported, scope)
        rows, manifest = self.engine._committed_slow_feedback()
        self.engine._active_slow_input = {"feedback_rows": rows, "source_manifest": manifest}
        self.engine._active_slow_memory = {"processed_feedback_refs": [row["feedback_ref"] for row in rows if row["kind"] == "signal_target_observation"]}
        self.assertEqual(self.engine._slow_method_view("H1")["source_entries"], [])
        self.assertTrue(self.engine._slow_method_view("Update")["source_entries"])

    def test_imported_target_scope_preserves_narrower_roles_and_requires_scope(self):
        source = self.event("narrow-history", 4.0, round_id=1)
        record_committed_signal_use(self.registry, (source,))
        self.commit_fixture_round()
        rows, _manifest = self.engine._committed_slow_feedback()
        row = next(row for row in rows if row["kind"] == "signal_target_observation")
        self.bind_target_history(source, row, ["Update"])
        rows, manifest = self.engine._committed_slow_feedback()
        imported = next(row for row in rows if row["kind"] == "signal_target_observation" and row["feedback_ref"].startswith("slow-history:"))
        self.assertEqual(next(item["visible_to"] for item in manifest if item["ref"] == imported["feedback_ref"]), ["Update"])
        self.bind_target_history(source, row, None)
        with self.assertRaisesRegex(ValidationError, "explicit disclosure scope"):
            self.engine._committed_slow_feedback()

    def test_zero_local_pointer_consumes_only_exact_imports_and_targets(self):
        source = self.event("imported-high", 4.1, round_id=7)
        pending = self.event("pending-local", 8.0, round_id=1)
        unlisted = self.event("unlisted-source", 7.0, round_id=7)
        record_committed_signal_use(self.registry, (source, pending, unlisted))
        self.bind((source,))
        before = self.registry._target_evaluations_path().read_bytes()
        rows, manifest = self.engine._committed_slow_feedback()
        usage = [row["event"] for row in rows if row["kind"] == "signal_usage"]
        self.assertEqual(usage, [source.to_dict()])
        profiles = [row["artifact"] for row in rows if row["kind"] == "signal_target_observation"]
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["selection_events"], 1)
        self.assertEqual(profiles[0]["effect_status"], "unverified")
        self.assertEqual(self.engine.workspace.last_completed_round, 0)
        self.assertEqual(self.engine._committed_slow_feedback(), (rows, manifest))
        self.assertEqual(self.registry._target_evaluations_path().read_bytes(), before)
        source_manifest = next(item for item in manifest if item["ref"].startswith("target-use:"))
        self.assertNotIn("H1", source_manifest["visible_to"])
        self.engine._active_slow_input = {"feedback_rows": rows, "source_manifest": manifest}
        self.engine._active_slow_memory = {"processed_feedback_refs": [source_manifest["ref"]]}
        self.assertEqual(self.engine._slow_method_view("H1")["source_entries"], [])
        self.assertEqual(self.engine._slow_method_view("Update")["source_entries"][0]["content"]["artifact"]["selection_events"], 1)

    def test_history_attached_to_fast_successor_preserves_transitive_events(self):
        source = self.event("ancestor", 4.0, round_id=11)
        record_committed_signal_use(self.registry, (source,))
        contract, _path = self.bind((source,), history=True, mode="fast_then_slow")
        loaded = imported_learning_events(self.engine.workspace.root, registry=self.registry)
        self.assertEqual(loaded, (source,))
        self.assertEqual(_contract_bound_import_learning_events(
            source_root=self.engine.workspace.root, contract=contract), {source.event_id: source})
        self.assertEqual(sum(row["kind"] == "signal_usage" for row in self.engine._committed_slow_feedback()[0]), 1)

    def test_changed_missing_or_unbound_imports_fail_closed(self):
        source = self.event("authorized", 3.9, round_id=5)
        contract, path = self.bind((source,))
        with self.assertRaisesRegex(ValidationError, "Registry copy"):
            imported_learning_events(self.engine.workspace.root, registry=self.registry)
        record_committed_signal_use(self.registry, (replace(source, prediction_correct=False),))
        with self.assertRaisesRegex(ValidationError, "Registry copy"):
            self.engine._committed_slow_feedback()
        envelope = json.loads(path.read_text())
        envelope["manifest"]["signal_learning_events"] = []
        path.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValidationError, "manifest is invalid"):
            imported_learning_events(self.engine.workspace.root)
        (self.engine.workspace.root / "run_contract.json").unlink()
        with self.assertRaisesRegex(ValidationError, "frozen run contract"):
            imported_learning_events(self.engine.workspace.root)
        self.assertTrue(contract.contract_hash)

    def test_historical_imports_survive_publication_without_becoming_vnext_feedback(self):
        source = self.event("prior-version", 4.0, round_id=11)
        record_committed_signal_use(self.registry, (source,))
        prior = self.registry.load_spec(self.ref)
        current = self.publish_next_version()
        self.bind((source,), history=True, mode="fast_then_slow")
        loaded = imported_learning_events(self.engine.workspace.root, registry=self.registry)
        self.assertEqual(loaded, (source,))
        frozen = self.registry.freeze(learning_round_cutoff=0, imported_events=loaded)
        self.assertNotIn(prior.ref, frozen.learned_profiles)
        self.assertEqual(frozen.learned_profiles[current.ref]["selection_events"], 0)
        self.assertEqual(self.registry.load_committed_learning_profile(prior.ref,
            round_cutoff=0, imported_events=loaded)["selection_events"], 1)
        rows, _manifest = self.engine._committed_slow_feedback()
        self.assertEqual([row["event"] for row in rows if row["kind"] == "signal_usage"], [source.to_dict()])

    def test_freeze_validates_old_version_import_copies_and_unknown_versions(self):
        source = self.event("prior-copy", 4.0, round_id=11)
        prior = self.registry.load_spec(self.ref)
        with self.assertRaisesRegex(ValidationError, "Registry copy"):
            self.registry.freeze(learning_round_cutoff=0, imported_events=(source,))
        record_committed_signal_use(self.registry, (source,))
        self.publish_next_version()
        with self.assertRaisesRegex(ValidationError, "Registry copy"):
            self.registry.freeze(learning_round_cutoff=0,
                imported_events=(replace(source, prediction_correct=False),))
        unknown = self.event("missing-version", 4.0, round_id=11, ref=f"{prior.signal_id}:v99")
        self.bind((unknown,), history=True, mode="fast_then_slow")
        with self.assertRaisesRegex(ValidationError, "unknown stable signal ref"):
            imported_learning_events(self.engine.workspace.root, registry=self.registry)
        with self.assertRaisesRegex(ValidationError, "unknown stable signal ref"):
            self.registry.freeze(learning_round_cutoff=0, imported_events=(unknown,))

    def test_local_historical_feedback_keeps_committed_cutoff_after_publication(self):
        source = self.event("local-prior", 4.0, round_id=1)
        pending = self.event("local-uncommitted", 7.0, round_id=2)
        record_committed_signal_use(self.registry, (source, pending))
        current = self.publish_next_version()
        self.commit_fixture_round()
        rows, _manifest = self.engine._committed_slow_feedback()
        self.assertEqual([row["event"] for row in rows if row["kind"] == "signal_usage"], [source.to_dict()])
        profiles = [row for row in rows if row["kind"] == "signal_target_observation"]
        self.assertEqual([row["subject_ref"] for row in profiles], [self.ref])
        self.assertEqual(profiles[0]["artifact"]["selection_events"], 1)
        self.assertEqual(self.registry.freeze(learning_round_cutoff=1).learned_profiles[current.ref]["selection_events"], 0)

    def test_fast_cycle_restart_freezes_imports_and_excludes_own_cycle_events(self):
        source = self.event("source", 3.4, round_id=8)
        pending = self.event("local", 4.5, round_id=1)
        record_committed_signal_use(self.registry, (source, pending))
        prior = self.registry.load_spec(self.ref)
        current = self.publish_next_version()
        self.bind((source,), history=True, mode="fast_then_slow")
        workspace = self.engine.workspace
        captured = []
        class ReachedSlow(Exception):
            pass
        def slow_cycle(**kwargs):
            captured.append(kwargs["input_snapshot"])
            raise ReachedSlow
        signal_engine = SimpleNamespace(workspace=workspace, run_cycle=slow_cycle)
        plan_engine = SimpleNamespace(workspace=workspace, run_round=lambda **_kwargs: SimpleNamespace())
        engine = DualLoopEvolutionEngine(plan_engine=plan_engine, signal_engine=signal_engine,
            signal_registry=self.registry, dataset=SimpleNamespace(anchor=(), evolution_validation=()),
            plan_rounds_per_signal_cycle=1)
        with self.assertRaises(ReachedSlow):
            engine.run_cycle(cycle_id=1)
        self.commit_fixture_round()
        with self.assertRaises(ReachedSlow):
            engine.run_cycle(cycle_id=1, completed_plan_rounds=1)
        self.assertEqual(captured[0].learning_hash, captured[1].learning_hash)
        self.assertEqual(captured[0].learned_profiles[current.ref]["selection_events"], 0)
        self.assertNotIn(self.ref, captured[0].learned_profiles)
        imports = imported_learning_events(workspace.root, registry=self.registry)
        record_committed_signal_use(self.registry, (self.event("current-version", 3.7,
            round_id=1, ref=current.ref),))
        next_cycle = self.registry.freeze(learning_round_cutoff=1, imported_events=imports)
        self.assertEqual(next_cycle.learned_profiles[current.ref]["selection_events"], 1)
        self.assertNotEqual(next_cycle.learning_hash, captured[0].learning_hash)

    def test_corrupt_envelopes_are_validation_failures(self):
        source = self.event("source-json", 4.0)
        _contract, path = self.bind((source,))
        for raw in ("[]", "{broken"):
            path.write_text(raw)
            with self.assertRaises(ValidationError):
                imported_learning_events(self.engine.workspace.root)

    def test_update_payload_and_suppression_share_committed_feedback_scope(self):
        cases = self.engine.discovery_cases
        for index, case in enumerate(cases):
            self.engine.raw_info_store.append(RawInfoDocument.create(
                document_id=f"update-source-{index}", company_id=case.company_id,
                source_type="financials", published_at=NOW, available_at=NOW,
                content=sec_company_facts_content(
                    ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                    ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"))))
        source = self.event("update-import", 4.0, round_id=9, ref=self.direction)
        pending = self.event("update-pending", 7.0, round_id=1, ref=self.direction)
        record_committed_signal_use(self.registry, (source, pending))
        def execute():
            return self.engine._run_one_signal_update(cycle_id=2,
                target={"signal_ref": self.direction, "problem_type": "repeated_directional_wrong"},
                cases=cases, executor=SignalExecutor(self.registry.freeze(), self.engine.raw_info_store))
        first = execute()
        self.assertEqual(first["audit"]["disposition"], "no_change")
        self.assertEqual(self.engine.update_model.requests[-1]["target"]["learned_profile"]["selection_events"], 0)
        prior = self.engine.workspace.experiments_root / "cycles" / "cycle-0001" / "slow_loop_validation.json"
        prior.parent.mkdir(parents=True)
        prior.write_text(json.dumps({"validation": {"agent_audits": {"update_pipeline": {
            "schema_version": "signal-update-audit-v2", "targets": [first["audit"]]}}}}))
        self.assertEqual(execute()["audit"]["disposition"], "unchanged_work_suppressed")
        self.bind((source,))
        changed = execute()
        self.assertEqual(changed["audit"]["disposition"], "no_change")
        self.assertNotEqual(first["audit"]["work_fingerprint"], changed["audit"]["work_fingerprint"])
        payload = self.engine.update_model.requests[-1]["target"]
        self.assertEqual(payload["learned_profile"]["selection_events"], 1)
        self.assertEqual(payload["target_use_profiles"]["surge_direction"]["selection_events"], 1)
