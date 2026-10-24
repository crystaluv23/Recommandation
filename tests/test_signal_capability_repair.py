"""Actual issuer-fixture repair, scope rejection and interruption recovery."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import repair_historical_signal_registry as driver
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator
from stock_opportunity_agent.signal_capability_repair import _inventory
from stock_opportunity_agent.signal_library import SignalRegistry


class CapabilityRepairTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.base_directory.cleanup)
        cls.base = Path(cls.base_directory.name) / 'prepared'
        with driver.guards():
            cls.base_plan = driver.prepare_at(cls.base)
        cls.source_root = Path(driver.read(cls.base / 'authority.json')['source_root'])
        cls.source_files = _inventory(cls.source_root)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / 'case'
        shutil.copytree(self.base, self.root)
        self.plan = deepcopy(self.base_plan)
        self.plan['authority'] = driver.binding(self.root / 'authority.json')
        self.registry = self.reopen()

    def tearDown(self):
        self.assertEqual(_inventory(self.source_root), self.source_files)

    def reopen(self):
        return SignalRegistry(self.root / 'registry', candidate_root=self.root / 'candidates')

    def apply(self, registry=None):
        with driver.guards():
            return (registry or self.registry).capability_repair(self.plan, plan_hash=canonical_json_hash(self.plan))

    def rewrite_authority(self, change):
        path = self.root / 'authority.json'
        data = driver.read(path); change(data)
        path.write_text(json.dumps(data))
        self.plan['authority'] = driver.binding(path)

    def test_exact_nine_real_validations_publish_full_eighteen_and_replay_without_writes(self):
        self.assertEqual(driver.read(self.base / 'prepared.json')['fixture_count'], 27)
        transition = self.apply()
        output = self.registry.freeze()
        self.assertEqual((transition.input_version, transition.output_version, len(output.specs)), (12, 13, 18))
        self.assertEqual(len(transition.promoted), 9)
        self.assertTrue(all(output.research_status[ref]['effect_status'] == 'unverified' for ref in transition.promoted))
        before = _inventory(self.root)
        self.assertEqual(self.apply(self.reopen()), transition)
        self.assertEqual(_inventory(self.root), before)

    def test_ordinary_promotion_still_rejects_the_unhealthy_input(self):
        a = driver.read(self.plan['authority']['path'])
        with self.assertRaises(ValidationError):
            self.registry.promote_validated_batch(self.plan['validated_candidates'],
                validated_evaluations=self.plan['validated_evaluations'], transition_id='ordinary',
                input_version=a['input_version'], input_hash=a['input_hash'], input_refs=a['input_refs'])
        self.assertFalse((self.registry.root / '.transitions/ordinary.json').exists())
        self.assertEqual(self.registry.version, 12)

    def test_original_or_alias_target_and_candidate_roots_are_refused(self):
        for target in (self.source_root, self.source_root / 'nested-target'):
            with self.subTest(target=target):
                other = object.__new__(SignalRegistry)
                other.__dict__.update(self.registry.__dict__)
                other.root = target
                with self.assertRaisesRegex(ValidationError, 'must be separate'):
                    self.apply(other)
        alias = self.root / 'source-alias'
        alias.symlink_to(self.source_root, target_is_directory=True)
        self.registry.candidate_root = alias
        with self.assertRaisesRegex(ValidationError, 'must be separate'):
            self.apply()

    def test_all_missing_extra_or_drifted_baseline_inventory_is_refused(self):
        path = self.registry.root / 'financial/cash_reserves/versions/v1/tests.json'
        original = path.read_bytes()
        for action in ('change', 'delete', 'extra'):
            with self.subTest(action=action):
                if action == 'change': path.write_bytes(original + b' ')
                if action == 'delete': path.unlink()
                extra = self.registry.root / 'unexpected.json'
                if action == 'extra': extra.write_text('{}')
                with self.assertRaisesRegex(ValidationError, 'byte clone|removed'):
                    self.apply()
                path.write_bytes(original)
                extra.unlink(missing_ok=True)

    def test_input_refs_hash_version_and_disabled_reasons_are_complete(self):
        for field in ('input_refs', 'input_hash', 'input_version', 'disabled'):
            with self.subTest(field=field):
                original = (self.root / 'authority.json').read_bytes()
                def change(row):
                    if field == 'input_refs': row[field] = row[field][:-1]
                    elif field == 'input_hash': row[field] = '0' * 64
                    elif field == 'input_version': row[field] = 13
                    else: row[field].pop(next(iter(row[field])))
                self.rewrite_authority(change)
                with self.assertRaises(ValidationError): self.apply()
                (self.root / 'authority.json').write_bytes(original)
                self.plan['authority'] = driver.binding(self.root / 'authority.json')

    def test_missing_update_and_changed_candidate_or_admission_key_are_refused(self):
        for field in ('validated_candidates', 'validated_evaluations'):
            with self.subTest(field=field):
                prior = deepcopy(self.plan[field]); ref = next(iter(prior))
                self.plan[field].pop(ref)
                with self.assertRaises(ValidationError): self.apply()
                self.plan[field] = prior
                self.plan[field][ref] = 'f' * 64
                with self.assertRaises(ValidationError): self.apply()
                self.plan[field] = prior

    def test_unapproved_threshold_drift_rejects_even_when_generic_validator_passes(self):
        ref = 'cash_reserves:v3'
        spec, _ = self.registry.load_candidate(ref)
        changed = replace(spec, parameters={**dict(spec.parameters), 'positive_min': 99000000})
        path = self.registry._candidate_spec_path(ref)
        path.write_text(json.dumps(changed.to_dict()))
        original = object.__new__(SignalRegistry); original.__dict__.update(self.registry.__dict__)
        original.root = self.source_root; original.knowledge_workspace_root = self.source_root.parent
        checked = SignalCandidateValidator(original, llm_runner=None).validate(changed, skill=None,
            tests=self.registry.load_candidate_tests(ref))
        self.assertTrue(checked.accepted, checked.reasons)
        self.plan['validated_candidates'][ref] = self.registry.candidate_hash(ref)
        with self.assertRaisesRegex(ValidationError, 'unapproved definition'):
            self.apply()

    def test_fixture_body_metadata_expected_or_period_drift_refused(self):
        ref = 'cash_reserves:v3'
        path = self.registry._candidate_spec_path(ref).parent / 'tests.json'
        original = path.read_bytes()
        for mode in ('body', 'metadata', 'expected', 'period'):
            with self.subTest(mode=mode):
                data = json.loads(original); fixture = data['tests'][0]; doc = fixture['documents'][0]
                body = json.loads(doc['content'])
                if mode == 'body': body.pop('cik')
                if mode == 'metadata': doc['metadata']['cik'] = '0001999992'
                if mode == 'expected': fixture['expected'] = 'unavailable'
                if mode == 'period': body['facts'][0]['end'] = '2024-12-30'
                doc['content'] = json.dumps(body, sort_keys=True, separators=(',', ':'))
                path.write_text(json.dumps(data))
                self.plan['validated_candidates'][ref] = self.registry.candidate_hash(ref)
                with self.assertRaises(ValidationError): self.apply()
                path.write_bytes(original)
        self.plan['validated_candidates'][ref] = self.registry.candidate_hash(ref)

    def test_every_materialization_and_publication_fault_recovers_exactly_once(self):
        phases = ('after_transition_prepared', 'after_stable_spec', 'after_stable_tests',
            'after_stable_stats', 'after_stable_manifest', 'after_stable_admission',
            'after_repair_output_audit', 'after_registry_version', 'before_output_snapshot',
            'after_output_snapshot', 'after_promotion_record', 'before_transition_applied')
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'case'; shutil.copytree(self.base, root)
                registry = SignalRegistry(root / 'registry', candidate_root=root / 'candidates')
                fired = []
                def fault(stage, ref):
                    if stage == phase and not fired:
                        fired.append(stage)
                        if stage == 'after_repair_output_audit':
                            self.assertEqual(registry.version, 12)
                            self.assertFalse(list((root / 'candidates').rglob('promotion.json')))
                        raise RuntimeError('controlled interruption')
                registry._fault_injector = fault
                with self.assertRaisesRegex(RuntimeError, 'controlled interruption'): self.apply(registry)
                self.assertEqual(fired, [phase])
                recovered = SignalRegistry(root / 'registry', candidate_root=root / 'candidates')
                for read in (recovered.freeze, recovered.list_signal_cards,
                    lambda: recovered.load_spec('cash_reserves:v2')):
                    with self.assertRaisesRegex(ValidationError, 'prepared'): read()
                output = self.apply(recovered)
                self.assertEqual(output.output_version, 13)
                self.assertEqual(len(recovered.freeze().specs), 18)
                self.assertEqual(self.apply(recovered), output)

    def test_unknown_transition_status_cannot_expose_partially_materialized_output(self):
        def fault(stage, ref):
            if stage == 'after_repair_output_audit': raise RuntimeError('interrupt')
        self.registry._fault_injector = fault
        with self.assertRaises(RuntimeError): self.apply()
        path = self.registry.root / '.transitions' / (self.plan['transition_id'] + '.json')
        row = driver.read(path); row['status'] = 'unknown'; path.write_text(json.dumps(row))
        recovered = self.reopen()
        with self.assertRaisesRegex(ValidationError, 'prepared'): recovered.freeze()
        with self.assertRaisesRegex(ValidationError, 'identity/status'): self.apply(recovered)
        self.assertEqual(recovered.version, 12)

    def test_mutated_or_missing_applied_promotion_marker_refuses_replay(self):
        self.apply()
        marker = next(self.registry.candidate_root.rglob('promotion.json'))
        prior = marker.read_bytes()
        marker.unlink()
        with self.assertRaisesRegex(ValidationError, 'marker'): self.apply()
        marker.write_text('{}')
        with self.assertRaisesRegex(ValidationError, 'marker'): self.apply()
        marker.write_bytes(prior)
        self.assertEqual(self.apply().output_version, 13)

    def test_promotion_marker_boolean_type_cannot_coerce_an_integer(self):
        self.apply()
        marker = next(self.registry.candidate_root.rglob('promotion.json'))
        original = marker.read_bytes()
        for field, value in (('promoted', 1), ('output_registry_version', 13.0)):
            with self.subTest(field=field):
                row = json.loads(original); row[field] = value
                marker.write_text(json.dumps(row))
                with self.assertRaisesRegex(ValidationError, 'marker'):
                    self.apply()
        marker.write_bytes(original)
        transition = self.registry.root / '.transitions' / (self.plan['transition_id'] + '.json')
        row = driver.read(transition); row['output_registry_version'] = 13.0
        transition.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValidationError, 'applied output identity'):
            self.apply()

    def test_unrelated_prepared_or_unknown_transition_blocks_recovery(self):
        for status in ('prepared', 'unknown'):
            with self.subTest(status=status):
                path = self.registry.root / '.transitions/unrelated.json'
                path.write_text(json.dumps({'status': status}))
                with self.assertRaisesRegex(ValidationError, 'unrelated'): self.apply()
                path.unlink()

    def test_applied_word_alone_cannot_expose_uncommitted_versions(self):
        def fault(stage, ref):
            if stage == 'after_repair_output_audit': raise RuntimeError('interrupt')
        self.registry._fault_injector = fault
        with self.assertRaises(RuntimeError): self.apply()
        path = self.registry.root / '.transitions' / (self.plan['transition_id'] + '.json')
        row = driver.read(path); row['status'] = 'applied'; path.write_text(json.dumps(row))
        recovered = self.reopen()
        self.assertEqual(recovered.version, 12)
        for read in (recovered.freeze, recovered.list_signal_cards,
            lambda: recovered.load_spec('cash_reserves:v3')):
            with self.assertRaises(ValidationError): read()
        with self.assertRaises(ValidationError): self.apply(recovered)

    def test_committed_registry_reads_locally_and_rejects_bad_terminal_shape_or_hash(self):
        self.apply()
        path = self.registry.root / '.transitions' / (self.plan['transition_id'] + '.json')
        original = path.read_bytes()
        for field, value in (('output_registry_version', 13.0), ('output_registry_hash', '0' * 64),
                            ('promoted', []), ('repair_plan_hash', 'f' * 64)):
            with self.subTest(field=field):
                row = json.loads(original); row[field] = value; path.write_text(json.dumps(row))
                with self.assertRaises(ValidationError): self.reopen().list_signal_cards()
        path.write_bytes(original)
        # Ordinary committed reads must not depend on external preparation records.
        (self.root / 'authority.json').unlink()
        self.assertEqual(len(self.reopen().freeze().specs), 18)

    def test_actual_ordinary_successor_stays_readable_and_preserves_old_repair_proof(self):
        repair = self.apply()
        before = self.registry.freeze()
        prior = self.registry.load_spec('cash_reserves:v3')
        spec = replace(prior, version=4)
        fixtures = self.registry.load_tests(prior.ref)
        self.registry.stage_candidate(spec, skill=None, tests=fixtures, origin='ordinary-successor-control')
        checked = SignalCandidateValidator(self.registry, llm_runner=None).validate(spec, skill=None, tests=fixtures)
        self.assertTrue(checked.accepted, checked.reasons)
        key = self.registry.record_candidate_admission(spec.ref, input_registry_hash=before.registry_hash,
            validator_hash='a' * 64, research_targets=['surge_direction'],
            contract_validation={'accepted': True, 'reasons': [], 'executed_tests': checked.executed_tests})
        update = self.registry.promote_validated_batch({spec.ref: self.registry.candidate_hash(spec.ref)},
            validated_evaluations={spec.ref: key}, transition_id='ordinary-successor', input_version=before.version,
            input_hash=before.registry_hash, input_refs=tuple(row.ref for row in before.specs))
        self.assertEqual(update.output_version, 14)
        fresh = self.reopen()
        self.assertEqual(fresh.freeze().version, 14)
        self.assertEqual(fresh.latest_spec('cash_reserves').ref, spec.ref)
        self.assertEqual(fresh.load_spec('cash_reserves:v3'), prior)
        old = fresh.snapshot_from_refs(repair.output_version, tuple(row.ref for row in before.specs))
        self.assertEqual(old.registry_hash, repair.output_hash)
        tests_path = fresh.root / 'financial/cash_reserves/versions/v3/tests.json'
        row = driver.read(tests_path); row['tests'][0]['expected'] = 'unavailable'
        tests_path.write_text(json.dumps(row))
        with self.assertRaises(ValidationError):
            self.reopen().freeze()
