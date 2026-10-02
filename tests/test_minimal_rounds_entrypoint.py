"""Acceptance entry point must freeze an executable production contract."""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scripts import run_minimal_rounds as entry
from scripts.run_minimal_rounds import _evaluation, prepare
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.resolution import EvidenceResolver
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoOracle, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import _signal_learning_events_from_record
from stock_opportunity_agent.research.signal_tracking import imported_learning_events, record_committed_signal_use
from tests.evolution_runtime_test_support import make_contract
from tests.scheme_evolution_test_support import (
    EvolutionWorkspace, MagnitudeClass, RoundMetaEntry, SEED_CATALOG, SignalRegistry,
    SignalResult, SignalValue, NOW, make_case, make_record, make_trajectory,
)


class MinimalCycleContractTests(TestCase):
    def test_prepared_registry_seed_cannot_silently_change(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / 'run'
            root.mkdir()
            (root / 'input_manifest.json').write_text('{}')
            seed = Path(temp) / 'seed'
            frozen = {'registry_source': str(seed)}
            with patch('scripts.run_minimal_rounds._verify_inputs', return_value=frozen):
                self.assertEqual(prepare(root, seed_registry=seed), frozen)
                self.assertEqual(prepare(root), frozen)
                with self.assertRaises(ValidationError):
                    prepare(root, seed_registry=Path(temp) / 'different')

    def test_missing_registry_seed_fails_without_creating_a_source(self):
        with TemporaryDirectory() as temp:
            seed = Path(temp) / 'missing'
            with self.assertRaises(ValidationError):
                prepare(Path(temp) / 'run', seed_registry=seed)
            self.assertFalse(seed.exists())

    def test_partial_registry_is_not_silently_promoted_to_prepared_inputs(self):
        with TemporaryDirectory() as temp:
            seed = Path(temp) / 'seed'
            seed.mkdir()
            (seed / 'registry.json').write_text('{"version":7}')
            root = Path(temp) / 'run'
            (root / 'signals').mkdir(parents=True)
            with self.assertRaises(ValidationError):
                prepare(root, seed_registry=seed)
            self.assertFalse((root / 'input_manifest.json').exists())

    def test_diagnostic_evaluation_obeys_production_v8_floor(self):
        template = make_contract()
        contract = replace(template, limits={**template.limits, 'evaluation': _evaluation().to_dict()})
        self.assertTrue(contract.executable)
        self.assertEqual(_evaluation().cases_per_round, 24)
        self.assertEqual(_evaluation().anchor_cases, 16)
        self.assertEqual(_evaluation().random_cases, 8)
        self.assertTrue(_evaluation().require_finalized)
        self.assertTrue(_evaluation().require_source_evidence)


class CommittedFastDiagnosticTests(TestCase):
    def source(self, root):
        source = root / 'source'
        registry = SignalRegistry(source / 'signals')
        registry.install_catalog(SEED_CATALOG)
        snapshot = registry.freeze()
        contract = replace(make_contract(), initial_signal_registry_version=snapshot.version,
            initial_signal_registry_hash=snapshot.registry_hash)
        contract.freeze(source / 'run_contract.json')
        workspace = EvolutionWorkspace(source)
        workspace.start_or_resume_cycle(run_contract_hash=contract.contract_hash, target_plan_rounds=1,
            initial_signal_registry_version=snapshot.version, initial_signal_registry_hash=snapshot.registry_hash,
            observed_signal_registry_version=snapshot.version, observed_signal_registry_hash=snapshot.registry_hash)
        record = make_record('source-plan', 1.0, (1.0,))
        record = replace(record, trajectories=(make_trajectory('source-issuer', 2.5, True,
            MagnitudeClass.TWO_TO_THREE, signal_result=SignalResult(signal_id='revenue_growth_yoy',
                version=1, value=SignalValue.POSITIVE, confidence=1.0, interpretation='Fixture source.'),
            case_id=record.trajectories[0].case_id),))
        workspace.commit_round(round_id=1, records=(record,), meta_entry=RoundMetaEntry(round_id=1,
            evidence_refs=(record.plan.plan_id,)), signal_registry_version=snapshot.version,
            signal_registry_hash=snapshot.registry_hash, run_contract_hash=contract.contract_hash)
        # These mutable source derivatives must not become import authority.
        registry.record_retrieval('revenue_growth_yoy:v1')
        cases = tuple(make_case(f'diagnostic-{index}', 3.5 if index < 4 else 2.5) for index in range(8))
        frozen = {'approved_manifest_hash': contract.dataset_manifest_hash, 'locked_test_hash': 'b' * 64,
            'evaluation': _evaluation().to_dict(), 'splits': {'discovery': [case.to_discovery_dict() for case in cases],
                'anchor': [], 'evolution_validation': []}, 'source_files': [], 'registry_source': str(source / 'signals')}
        (source / 'input_manifest.json').write_text(json.dumps(frozen))
        return source, contract, frozen

    def committed_slow_source(self, root):
        """Produce a real pointer-reachable source, with a stable vNext fixture."""
        source, contract, frozen = self.source(root)
        registry = SignalRegistry(source / 'signals')
        workspace = EvolutionWorkspace(source)
        archive = workspace.restore_archive(expected_run_contract_hash=contract.contract_hash)
        record_committed_signal_use(registry, _signal_learning_events_from_record(archive.records[0]))
        stable = registry.load_spec('revenue_growth_yoy:v1')
        registry.register_stable(replace(stable, version=2, parameters={'positive_min': 0.3}),
            tests=registry.load_tests(stable.ref))
        snapshot = registry.freeze()
        workspace.stage_slow_result(cycle_id=1, result={
            'input_registry_version': contract.initial_signal_registry_version,
            'input_registry_hash': contract.initial_signal_registry_hash,
            'output_registry_version': snapshot.version, 'output_registry_hash': snapshot.registry_hash})
        workspace.complete_cycle(cycle_id=1, observed_signal_registry_version=snapshot.version,
            observed_signal_registry_hash=snapshot.registry_hash)
        # These opaque fixture artifacts test the history copier, not research quality.
        cycle = source / 'experiments/cycles/cycle-0001'
        for name in ('slow_input.json', 'slow_memory.json', 'slow_experiments.json', 'slow_loop_validation.json'):
            (cycle / name).write_text(json.dumps({'fixture': name}))
        staged = source / 'signals_candidates/financial/uncommitted/v1/spec.json'
        staged.parent.mkdir(parents=True); staged.write_text('{"not_committed": true}')
        return source, contract, frozen

    def test_history_prepare_preserves_stable_versions_events_subset_and_local_pointers(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); source, _contract, frozen = self.committed_slow_source(root)
            before = {str(path): path.read_bytes() for path in source.rglob('*') if path.is_file()}
            target = root / 'target'
            # An inherited source mode must not accidentally make this a zero-Fast bootstrap.
            inherited = {**frozen, 'slow_bootstrap_source': 'ancestor', 'slow_bootstrap_manifest_hash': 'a' * 64}
            with patch.object(entry, '_verify_inputs', return_value=inherited):
                prepared = prepare(target, slow_history_from=source)
            registry = SignalRegistry(target / 'signals')
            self.assertEqual(registry.latest_spec('revenue_growth_yoy').version, 2)
            self.assertEqual(len(registry.load_learning_events('revenue_growth_yoy:v1')), 1)
            self.assertEqual(prepared['splits'], frozen['splits'])
            self.assertEqual(prepared['source_files'], frozen['source_files'])
            self.assertNotIn('slow_bootstrap_manifest_hash', prepared)
            self.assertEqual(EvolutionWorkspace(target).last_completed_round, 0)
            self.assertEqual(EvolutionWorkspace(target).last_completed_cycle, 0)
            self.assertFalse((target / 'signals_candidates/financial/uncommitted').exists())
            envelope = json.loads((target / 'slow_history/manifest.json').read_text())
            self.assertEqual(prepared['slow_history_manifest_hash'], envelope['manifest_hash'])
            self.assertEqual(before, {str(path): path.read_bytes() for path in source.rglob('*') if path.is_file()})
            with patch.object(entry, '_verify_inputs', return_value=prepared):
                self.assertEqual(prepare(target, slow_history_from=source), prepared)
                with self.assertRaises(ValidationError):
                    prepare(target, slow_history_from=root / 'different')
            with self.assertRaises(ValidationError):
                prepare(root / 'other', seed_registry=source / 'signals', slow_history_from=source)

    def test_history_requires_a_committed_cycle_and_cannot_mix_bootstrap(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); source, _contract, frozen = self.source(root)
            with patch.object(entry, '_verify_inputs', return_value=frozen):
                with self.assertRaisesRegex(ValidationError, 'fully committed'):
                    prepare(root / 'target', slow_history_from=source)
            with self.assertRaises(ValidationError):
                prepare(root / 'other', slow_history_from=source, slow_bootstrap_from=source)

    def test_history_run_wires_positive_fast_and_preserved_meta_into_actual_engines(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); source, source_contract, source_inputs = self.committed_slow_source(root)
            target = root / 'target'
            with patch.object(entry, '_verify_inputs', return_value=source_inputs):
                frozen = prepare(target, slow_history_from=source)
            RawInfoOracle.load_or_create(root / 'raw')
            RawInfoStore(root / 'raw').append(RawInfoDocument.create(
                document_id='history-entry', company_id='diagnostic-0', source_type='financials',
                published_at=NOW, available_at=NOW, content='Fixture reported source.'))
            built = []
            def build(**kwargs):
                built.append(kwargs)
                return replace(source_contract, run_id=target.name,
                    initial_signal_registry_version=frozen['initial_registry_version'],
                    initial_signal_registry_hash=frozen['initial_registry_hash'],
                    raw_info_inventory_hash=canonical_json_hash(frozen), limits=kwargs['limits'],
                    cycle_mode=kwargs['cycle_mode'], slow_history_manifest_hash=kwargs['slow_history_manifest_hash'])
            class ReachedCycle(Exception):
                pass
            def cycle(engine, **_kwargs):
                self.assertEqual(engine.plan_rounds_per_signal_cycle, 1)
                self.assertEqual(engine.cycle_mode, 'fast_then_slow')
                self.assertEqual(engine.plan_engine.archive.records, ())
                self.assertEqual([row.round_id for row in engine.signal_engine.meta_memory.entries], [-1])
                self.assertEqual(engine.signal_registry.latest_spec('revenue_growth_yoy').version, 2)
                self.assertEqual(len(engine.signal_registry.load_learning_events('revenue_growth_yoy:v1')), 1)
                imports = imported_learning_events(target, registry=engine.signal_registry)
                snapshot = engine.signal_registry.freeze(learning_round_cutoff=0, imported_events=imports)
                self.assertEqual([event.signal_ref for event in imports], ['revenue_growth_yoy:v1'])
                self.assertEqual(snapshot.learned_profiles['revenue_growth_yoy:v2']['selection_events'], 0)
                self.assertNotIn('revenue_growth_yoy:v1', snapshot.learned_profiles)
                raise ReachedCycle
            with patch.object(entry, 'HISTORY', source), patch.object(entry, 'ORACLE', root / 'raw'), \
                 patch.object(entry, '_load_env'), patch.object(entry, 'build_run_contract', side_effect=build), \
                 patch.object(entry, 'StructuredRoleClient', return_value=object()), \
                 patch.object(entry, '_build_evidence_resolver', side_effect=lambda _root, store, **_kwargs: EvidenceResolver(store)), \
                 patch.object(entry.DualLoopEvolutionEngine, 'run_cycle', autospec=True, side_effect=cycle):
                with self.assertRaises(ReachedCycle):
                    entry.run(target, frozen)
            self.assertEqual(built[0]['limits']['plan_rounds_per_signal_cycle'], 1)
            self.assertIsNone(built[0]['slow_bootstrap_manifest_hash'])
            self.assertEqual(built[0]['slow_history_manifest_hash'], frozen['slow_history_manifest_hash'])
            self.assertEqual(EvolutionWorkspace(target).last_completed_cycle, 0)

    def test_prepare_keeps_exact_subset_and_excludes_mutable_registry_derivatives(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); source, _contract, frozen = self.source(root)
            before = {str(path): path.read_bytes() for path in source.rglob('*') if path.is_file()}
            target = root / 'target'
            with patch.object(entry, '_verify_inputs', return_value=frozen):
                prepared = prepare(target, slow_bootstrap_from=source)
            self.assertEqual(prepared['splits'], frozen['splits'])
            self.assertEqual(prepared['source_files'], frozen['source_files'])
            registry = SignalRegistry(target / 'signals')
            self.assertEqual(registry.load_stats('revenue_growth_yoy').retrieved, 0)
            self.assertEqual(registry.load_learning_events('revenue_growth_yoy:v1'), ())
            self.assertEqual(EvolutionWorkspace(target).last_completed_round, 0)
            envelope = json.loads((target / 'slow_bootstrap/manifest.json').read_text())
            self.assertEqual(envelope['manifest']['source_kind'], 'committed_fast')
            self.assertEqual(len(envelope['manifest']['signal_learning_events']), 1)
            self.assertEqual(prepared['slow_bootstrap_manifest_hash'], envelope['manifest_hash'])
            self.assertEqual(before, {str(path): path.read_bytes() for path in source.rglob('*') if path.is_file()})
            with patch.object(entry, '_verify_inputs', return_value=prepared):
                self.assertEqual(prepare(target), prepared)
                with self.assertRaises(ValidationError):
                    prepare(target, slow_bootstrap_from=root / 'different')
            with self.assertRaises(ValidationError):
                prepare(root / 'other', seed_registry=source / 'signals', slow_bootstrap_from=source)

    def test_run_wires_zero_fast_and_rebased_meta_into_actual_engines(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); source, source_contract, source_inputs = self.source(root)
            target = root / 'target'
            with patch.object(entry, '_verify_inputs', return_value=source_inputs):
                frozen = prepare(target, slow_bootstrap_from=source)
            RawInfoOracle.load_or_create(root / 'raw')
            RawInfoStore(root / 'raw').append(RawInfoDocument.create(
                document_id='entry-fixture', company_id='diagnostic-0', source_type='financials',
                published_at=NOW, available_at=NOW, content='Fixture reported source.'))
            built = []
            def build(**kwargs):
                built.append(kwargs)
                return replace(source_contract, run_id=target.name,
                    code_revision=source_contract.code_revision,
                    raw_info_inventory_hash=canonical_json_hash(frozen), limits=kwargs['limits'],
                    cycle_mode=kwargs['cycle_mode'], slow_bootstrap_manifest_hash=kwargs['slow_bootstrap_manifest_hash'])
            class ReachedCycle(Exception):
                pass
            def cycle(engine, **_kwargs):
                self.assertEqual(engine.plan_rounds_per_signal_cycle, 0)
                self.assertEqual(engine.cycle_mode, 'slow_bootstrap')
                self.assertEqual(engine.plan_engine.archive.records, ())
                self.assertEqual([row.round_id for row in engine.signal_engine.meta_memory.entries], [-1])
                self.assertEqual(engine.signal_engine.meta_memory, engine.plan_engine.meta_memory)
                self.assertEqual(len(engine.signal_registry.load_learning_events('revenue_growth_yoy:v1')), 1)
                raise ReachedCycle
            with patch.object(entry, 'HISTORY', source), patch.object(entry, 'ORACLE', root / 'raw'), \
                 patch.object(entry, '_load_env'), patch.object(entry, 'build_run_contract', side_effect=build), \
                 patch.object(entry, 'StructuredRoleClient', return_value=object()), \
                 patch.object(entry, '_build_evidence_resolver', side_effect=lambda _root, store, **_kwargs: EvidenceResolver(store)), \
                 patch.object(entry.DualLoopEvolutionEngine, 'run_cycle', autospec=True, side_effect=cycle):
                with self.assertRaises(ReachedCycle):
                    entry.run(target, frozen)
            self.assertEqual(len(built), 1)
            self.assertEqual(built[0]['limits']['plan_rounds_per_signal_cycle'], 0)
            self.assertEqual(EvolutionWorkspace(target).last_completed_round, 0)
            self.assertEqual(EvolutionWorkspace(source).last_completed_round, 1)

    def test_definition_snapshot_recomputes_identity_and_rejects_wrong_order_or_version(self):
        with TemporaryDirectory() as temp:
            source, _contract, _frozen = self.source(Path(temp))
            registry = SignalRegistry(source / 'signals')
            initial = registry.freeze()
            refs = tuple(spec.ref for spec in initial.specs)
            self.assertEqual(registry.snapshot_from_refs(initial.version, refs).registry_hash, initial.registry_hash)
            # A different order/version must not impersonate the original hash.
            self.assertNotEqual(registry.snapshot_from_refs(initial.version, tuple(reversed(refs))).registry_hash, initial.registry_hash)
            self.assertNotEqual(registry.snapshot_from_refs(initial.version + 1, refs).registry_hash, initial.registry_hash)
