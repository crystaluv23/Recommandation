"""Imported event authority across Slow consumption, Fast freeze and restart."""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.signal_library import SignalExecutor
from stock_opportunity_agent.research.evolution_control import _contract_bound_import_learning_events
from stock_opportunity_agent.research.signal_evolution import DualLoopEvolutionEngine
from stock_opportunity_agent.research.signal_tracking import imported_learning_events, record_committed_signal_use
from tests import test_signal_tracking as tracking_fixture
from tests.evolution_runtime_test_support import make_contract
from tests.scheme_evolution_test_support import NOW, sec_company_facts_content


class ImportedSignalFeedbackTests(TestCase):
    setUp = tracking_fixture.SignalTrackingTests.setUp
    event = tracking_fixture.SignalTrackingTests.event

    def bind(self, events, *, history=False, mode=None):
        root = self.engine.workspace.root
        directory = "slow_history" if history else "slow_bootstrap"
        field = "learning_events" if history else "signal_learning_events"
        manifest = {"schema_version": "slow-history-manifest-v2" if history else "slow-bootstrap-manifest-v2",
            field: [event.to_dict() for event in events]}
        if history:
            manifest.update(source_namespace="source-test", committed_slow_cycle=1, cycle_artifacts=[])
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

    def test_fast_cycle_restart_freezes_imports_and_excludes_own_cycle_events(self):
        source = self.event("source", 3.4, round_id=8)
        pending = self.event("local", 4.5, round_id=1)
        record_committed_signal_use(self.registry, (source, pending))
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
        workspace.state_path.write_text('{"last_completed_round":1}')
        with self.assertRaises(ReachedSlow):
            engine.run_cycle(cycle_id=1, completed_plan_rounds=1)
        self.assertEqual(captured[0].learning_hash, captured[1].learning_hash)
        self.assertEqual(captured[0].learned_profiles[self.ref]["selection_events"], 1)
        imports = imported_learning_events(workspace.root, registry=self.registry)
        next_cycle = self.registry.freeze(learning_round_cutoff=1, imported_events=imports)
        self.assertEqual(next_cycle.learned_profiles[self.ref]["selection_events"], 2)
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
