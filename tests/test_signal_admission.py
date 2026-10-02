"""Technical admission identity, publication, and recovery without effect claims."""

from dataclasses import replace
from pathlib import Path
import json
import tempfile
from unittest import TestCase

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import SignalRegistry
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator
from tests.scheme_evolution_test_support import SEED_CATALOG, candidate_growth_fixture


class SignalAdmissionTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "signals"
        self.registry = SignalRegistry(self.root)
        self.registry.install_catalog(SEED_CATALOG)
        self.snapshot = self.registry.freeze()
        self.spec = replace(self.registry.load_spec("revenue_growth_yoy:v1"), version=2)
        self.registry.stage_candidate(self.spec, skill=None, tests=(candidate_growth_fixture(),), origin="update:revenue_growth_yoy:v1")
        checked = SignalCandidateValidator(self.registry, llm_runner=None).validate(self.spec, skill=None, tests=self.registry.load_candidate_tests(self.spec.ref))
        self.assertTrue(checked.accepted, checked.reasons)
        self.contract = {"accepted": checked.accepted, "reasons": list(checked.reasons), "executed_tests": checked.executed_tests}

    def admit(self, **overrides):
        arguments = {"input_registry_hash": self.snapshot.registry_hash, "validator_hash": "a" * 64,
                     "research_targets": ("surge_direction", "magnitude_ge3_v1"), "contract_validation": self.contract}
        return self.registry.record_candidate_admission(self.spec.ref, **{**arguments, **overrides})

    def publish(self, key, registry=None):
        return (registry or self.registry).promote_validated_batch(
            {self.spec.ref: self.registry.candidate_hash(self.spec.ref)}, validated_evaluations={self.spec.ref: key},
            transition_id=f"admission-test-v{self.spec.version}", input_version=self.snapshot.version, input_hash=self.snapshot.registry_hash,
            input_refs=tuple(spec.ref for spec in self.snapshot.specs))

    def test_technical_admission_publishes_without_effect_claim_and_freezes_status(self):
        key = self.admit()
        record = self.registry.load_candidate_validation(self.spec.ref, evaluation_key=key)
        self.assertNotIn("effectiveness", record)
        transition = self.publish(key)
        self.assertEqual(transition.promoted, (self.spec.ref,))
        snapshot = self.registry.freeze()
        status = snapshot.research_status[self.spec.ref]
        self.assertEqual(status["effect_status"], "unverified")
        self.assertEqual(set(status["research_targets"]), {"surge_direction", "magnitude_ge3_v1"})
        self.assertEqual(self.snapshot.research_status, {})
        self.assertEqual(self.publish(key).output_hash, transition.output_hash)
        with self.assertRaises(TypeError):
            status["effect_status"] = "supported"

    def test_new_rejected_pointer_cannot_replace_exact_admitted_identity(self):
        admitted = self.admit()
        before = self.registry.load_candidate_validation(self.spec.ref, evaluation_key=admitted)
        rejected = self.admit(validator_hash="b" * 64, contract_validation={"accepted": False, "reasons": ["Independent policy rejection"], "executed_tests": 0})
        self.assertNotEqual(admitted, rejected)
        self.assertEqual(before, self.registry.load_candidate_validation(self.spec.ref, evaluation_key=admitted))
        with self.assertRaises(ValidationError):
            self.publish(rejected)
        self.assertEqual(self.publish(admitted).promoted, (self.spec.ref,))

    def test_all_nonempty_fixtures_must_have_run(self):
        for contract in ({"accepted": True, "reasons": [], "executed_tests": 0},
                         {"accepted": True, "reasons": ["unresolved"], "executed_tests": 1},
                         {"accepted": True, "reasons": [], "executed_tests": True}):
            with self.subTest(contract=contract), self.assertRaises(ValidationError):
                self.admit(contract_validation=contract)
        self.registry.stage_candidate(replace(self.spec, version=3), skill=None, tests=(), origin="empty")
        with self.assertRaises(ValidationError):
            self.registry.record_candidate_admission("revenue_growth_yoy:v3", input_registry_hash=self.snapshot.registry_hash,
                validator_hash="a" * 64, research_targets=("surge_direction",), contract_validation={"accepted": True, "reasons": [], "executed_tests": 0})

    def test_wrong_input_registry_cannot_authorize_transition(self):
        key = self.admit(input_registry_hash="f" * 64)
        with self.assertRaises(ValidationError):
            self.publish(key)
        self.assertEqual(self.registry.freeze().registry_hash, self.snapshot.registry_hash)

    def test_prepared_transition_recovers_after_manifest_publication(self):
        key = self.admit()
        fired = []
        def fault(stage, signal_ref):
            if stage == "after_stable_manifest" and not fired:
                fired.append(stage)
                raise RuntimeError("Interrupted before admission copy")
        self.registry._fault_injector = fault
        with self.assertRaises(RuntimeError):
            self.publish(key)
        recovered = SignalRegistry(self.root)
        with self.assertRaises(ValidationError):
            recovered.freeze()
        transition = self.publish(key, recovered)
        self.assertEqual(recovered.freeze().research_status[self.spec.ref]["admission_key"], key)
        self.assertEqual(transition.output_version, self.snapshot.version + 1)

    def test_published_missing_or_corrupt_metadata_fails_closed(self):
        key = self.admit()
        self.publish(key)
        path = self.root / self.spec.category / self.spec.signal_id / "versions/v2/admission.json"
        original = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(ValidationError, "missing"):
            self.registry.freeze()
        path.write_bytes(original)
        record = json.loads(original)
        record["contract_validation"]["executed_tests"] = 2
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValidationError, "identity"):
            self.registry.freeze()

    def test_recovery_after_version_increment_keeps_input_binding(self):
        key = self.admit()
        def fault(stage, signal_ref):
            if stage == "after_registry_version":
                raise RuntimeError("Interrupted after version increment")
        self.registry._fault_injector = fault
        with self.assertRaises(RuntimeError):
            self.publish(key)
        recovered = SignalRegistry(self.root)
        transition = self.publish(key, recovered)
        self.assertEqual(transition.input_hash, self.snapshot.registry_hash)
        self.assertEqual(transition.output_version, self.snapshot.version + 1)

    def test_stable_content_tampering_invalidates_admission(self):
        key = self.admit()
        self.publish(key)
        path = self.root / self.spec.category / self.spec.signal_id / "versions/v2/tests.json"
        content = json.loads(path.read_text())
        content["tests"][0]["name"] = "Modified after admission"
        path.write_text(json.dumps(content))
        with self.assertRaisesRegex(ValidationError, "version content"):
            self.registry.load_research_status(self.spec.ref)

    def test_vnext_preserves_old_proof_and_starts_unverified(self):
        old_key = self.admit()
        self.publish(old_key)
        old_ref = self.spec.ref
        old_snapshot = self.registry.freeze()
        self.snapshot = old_snapshot
        self.spec = replace(self.spec, version=3)
        self.registry.stage_candidate(self.spec, skill=None, tests=(candidate_growth_fixture(),), origin=f"update:{old_ref}")
        new_key = self.admit()
        self.publish(new_key)
        self.assertNotEqual(old_key, new_key)
        self.assertEqual(self.registry.load_research_status(old_ref)["admission_key"], old_key)
        self.assertEqual(self.registry.load_research_status(self.spec.ref)["effect_status"], "unverified")
        self.assertEqual(old_snapshot.research_status[old_ref]["admission_key"], old_key)
        path = self.root / self.spec.category / self.spec.signal_id / "versions/v2/admission.json"
        path.unlink()
        with self.assertRaisesRegex(ValidationError, "missing"):
            self.registry.load_research_status(old_ref)

    def test_identity_binds_targets_policy_and_executable_content(self):
        key = self.admit()
        self.assertNotEqual(key, self.admit(research_targets=("surge_direction",)))
        self.assertNotEqual(key, self.admit(validator_hash="b" * 64))
        record = self.registry.load_candidate_validation(self.spec.ref, evaluation_key=key)
        path = next(self.registry.candidate_root.glob(f"*/{self.spec.signal_id}/v2/evaluations/{key}.json"))
        record = dict(record)
        record["accepted"] = False
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValidationError, "identity"):
            self.registry.load_candidate_validation(self.spec.ref, evaluation_key=key)
