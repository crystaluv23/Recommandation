"""Offline safety/composition controls; no real stage, model or source export."""
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import tempfile
from unittest import TestCase
from unittest.mock import patch

from scripts import run_reviewed_slow_feedback_stage as stage
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.memory.knowledge import KnowledgeUseStore
from stock_opportunity_agent.research.signal_tracking import imported_learning_events
from stock_opportunity_agent.research.evolution_core import EvolutionCase, GroundTruth
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController


class ReviewedSlowFeedbackStageTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'stage'
        self.root.mkdir()
        patched = patch.object(stage, 'STAGE_ROOT', self.root)
        patched.start()
        self.addCleanup(patched.stop)

    def request(self, name, output, payload=None, size=8):
        return {'stage': name, 'max_output_tokens': output,
                'messages': [{'role': 'system', 'content': 'x' * size},
                             {'role': 'user', 'content': json.dumps(payload or {})}]}

    def reserve(self, budget, request):
        key = canonical_json_hash(request)
        path = self.root / f'{key}.json'
        atomic_write_json(path, {'request_hash': key, 'request': request})
        budget({'event_type': 'request_ready', 'request_hash': key, 'request_path': str(path)})
        return path

    def test_budget_reconstructs_receipts_across_memory_checkpoint_and_deduplicates(self):
        requests = self.root / 'requests'
        requests.mkdir()
        budget = stage._Budget()
        for index in range(3):
            request = self.request('slow_source_read', 512, {'role_scope': str(index)})
            key = canonical_json_hash(request)
            atomic_write_json(requests / f'{key}.json', {'request_hash': key, 'request': request})
            self.reserve(budget, request)
        self.reserve(budget, self.request('signal_mining_reflect', 5000))
        self.reserve(budget, self.request('signal_mining_reflect_correction', 5000))
        self.reserve(budget, self.request(stage.MINING_CONTROLLER_STAGE, 4000, {'case': 1}))
        self.reserve(budget, self.request(stage.MINING_CONTROLLER_STAGE, 4000, {'last_invalid_action': {'issue': 'bad'}}))
        self.reserve(budget, self.request(stage.MINING_CONTROLLER_STAGE, 4000, {'case': 2}))
        self.assertEqual(len(budget.requests), 8)
        self.reserve(budget, self.request('signal_mining_reflect', 5000))
        self.assertEqual(len(budget.requests), 8)
        restored = stage._Budget(requests)
        self.assertEqual(len(restored.requests), 3)
        with self.assertRaises(stage.StageRejected):
            self.reserve(restored, self.request('slow_source_read', 512, {'fourth': True}))
        with self.assertRaises(stage.StageRejected):
            self.reserve(budget, self.request(stage.MINING_CONTROLLER_STAGE, 4000, {'case': 3}))

    def test_budget_rejects_selector_correction_heavy_role_size_and_output_drift(self):
        for request in [self.request('slow_source_read_correction', 512),
                        self.request('mining_candidate_materialize_tests', 4000),
                        self.request('signal_mining_reflect', 5001),
                        self.request('slow_source_read', 512, size=stage.REQUEST_CAP)]:
            with self.subTest(stage=request['stage']), self.assertRaises(stage.StageRejected):
                self.reserve(stage._Budget(), request)

    def test_native_real_run_contract_uses_new_independent_budget_without_execution(self):
        history = stage.read(stage.SOURCE / 'stage/slow_history/manifest.json')['manifest']
        cases = stage.read(stage.CASES)
        contract = stage._new_contract(history, cases, [])
        self.assertEqual(contract.cycle_mode, 'slow_only')
        self.assertEqual(contract.limits['max_local_role_calls'], 8)
        self.assertEqual(contract.limits['max_case_tokens'], 1048576)
        self.assertEqual(contract.limits['plan_rounds_per_signal_cycle'], 0)
        self.assertEqual(contract.max_external_attempts, 8)
        self.assertEqual(contract.max_total_cost, .01)
        self.assertFalse(contract.data_acquisition.enabled)
        self.assertFalse(contract.locked_test_accessed)
        self.assertTrue(all(row['alias'] == 'independent-subagent' for row in contract.models.values()))
        self.assertEqual(contract.slow_history_manifest_hash, stage.HISTORY_HASH)
        self.assertFalse((self.root / 'workspace').exists())

    def test_guard_confines_writes_and_blocks_network_labels_and_signal(self):
        outside = self.base / 'outside.txt'
        with stage._guard(self.root):
            (self.root / 'allowed.txt').write_text('okay')
            for operation in (lambda: outside.write_text('bad'), socket.socket,
                              lambda: stage.LabelStore(self.base),
                              lambda: stage.SignalExecutor.execute_batch(None, (), company_id='x', as_of=None),
                              lambda: stage.SignalRegistry.freeze(None)):
                with self.assertRaises(stage.StageRejected):
                    operation()
            with self.assertRaises(stage.StageRejected):
                (self.base / 'labels.jsonl').read_text()
        self.assertFalse(outside.exists())
        outside.write_text('guard is inactive')
        self.assertEqual(outside.read_text(), 'guard is inactive')

    def test_case_authority_rejects_locked_or_extra_split_before_roles(self):
        approved = {'schema_version': 'diagnostic-development-subset-v1', 'locked_test_accessed': True,
                    'splits': {'anchor': [], 'discovery': [], 'evolution_validation': []}}
        with self.assertRaises(stage.StageRejected):
            stage._cases(approved)
        approved['locked_test_accessed'] = False
        approved['splits']['locked_test'] = []
        with self.assertRaises(stage.StageRejected):
            stage._cases(approved)

    def test_source_check_footprint_positive_and_counterexample(self):
        history = self.root / 'slow_history'
        path = history / 'source-a/experiments/cycles/cycle-0001/slow_loop_validation.json'
        atomic_write_json(path, {'validation': {'agent_audits': {'mining_pipeline': {'modality_metrics': {}}},
                                                'candidate_effectiveness': {'old': {'status': 'pending'}}}})
        rows = stage._footprint_preflight(history)
        self.assertEqual(rows[0]['candidate_outcome_mappings'], 0)
        self.assertFalse(rows[0]['has_modality_metrics'])
        atomic_write_json(path, {'validation': {'agent_audits': {'mining_pipeline': {'modality_metrics': {'count': 1}}},
                                                'candidate_effectiveness': {'old': {'candidate': {'available': 4},
                                                                                     'candidate_confusion': {'tp': 3}}}}})
        with self.assertRaises(stage.StageRejected):
            stage._footprint_preflight(history)

    def controller(self, *, seed='hypothesis', sink=None):
        # Synthetic Controller mechanics only. Production _construct is not
        # entered and an empty store is never passed as an approved stage input.
        case = EvolutionCase('synthetic', datetime(2025, 1, 1, tzinfo=timezone.utc), {}, GroundTruth(1.0), 'synthetic-case')
        return LabelAwareMiningController(store=RawInfoStore(), model=None,
            case_pairs=[('case-001', case)], measurable_evidence_manifest={}, signal_catalog=[],
            seed=seed, backlog_needs=[{'need_ref': f'need-{index}', 'kind': 'meta_reflection_action',
                                     'need': 'Synthetic technical dependency.'} for index in range(60)],
            label_map={'case-001': 'control'}, need_progress_sink=sink)

    def test_controlled_native_page_preserves_full_backlog_and_honest_partial_stop(self):
        manifest = {'native_prepared': {'target_need_ref': 'need-55'}}
        units = self.root / 'workspace/experiments/cycles/cycle-0001/mining_need_units/synthetic'
        written = []

        def sink(unit):
            written.append(unit)
            atomic_write_json(units / f"{unit['result_hash']}.json", unit)

        with stage._controller_boundary(self.root, manifest):
            controller = self.controller(sink=sink)
            self.assertEqual(len(controller.backlog_needs), 60)
            self.assertIn('need-55', controller._disclosed_need_refs())
            self.assertEqual(controller.ledger.entries[0].action, 'inspect_catalog')
            page = stage.read(self.root / 'controlled-page.json')
            self.assertTrue(page['controlled_read_not_autonomous_search'])
            self.assertEqual(page['cursor'], 55)
            for action, raw in [('fetch_evidence', {}), ('inspect_catalog', {'scope': 'signals'})]:
                with self.assertRaises(stage.StageRejected):
                    controller._execute(action, raw)
            action = {'action': 'record_need_dispositions', 'base_hash': controller._need_state_hash(),
                      'rationale': ['Synthetic mechanics only.'], 'need_dispositions': [
                          {'need_refs': ['need-55'], 'disposition': 'repair_dependency', 'signal_refs': [],
                           'rationale': ['Technical source control requires investigation.']}]}
            with self.assertRaises(stage.NeedProgressSaved):
                controller._execute('record_need_dispositions', action)
        self.assertEqual(len(written), 1)
        saved = stage.read(self.root / 'controller-boundary.json')
        self.assertEqual(saved['module_status'], 'partial_running')
        self.assertEqual(len(saved['pending_need_refs']), 59)
        self.assertEqual(written[0]['pending_count'], 59)
        self.assertEqual([row['action'] for row in saved['ledger']], ['inspect_catalog', 'record_need_dispositions'])
        self.assertEqual(controller._state, 'exploring')

    def test_second_seed_rejected_before_original_constructor(self):
        with stage._controller_boundary(self.root, {'native_prepared': {'target_need_ref': 'need-55'}}):
            with self.assertRaises(stage.StageRejected):
                self.controller(seed='discovery')
        self.assertFalse((self.root / 'factory-input.json').exists())

    def test_terminal_restore_has_zero_native_construction_or_calls_and_detects_drift(self):
        atomic_write_json(self.root / 'artifact.json', {'evidence': 'original'})
        result = {'status': 'native_need_unit_saved_semantics_unreviewed'}
        stage._seal(self.root, result)
        before = stage._stage_files(self.root)
        with patch.object(stage, '_construct', side_effect=AssertionError('must not construct')), \
                patch.object(stage, '_verify', side_effect=AssertionError('must not reopen sources')):
            self.assertEqual(stage.advance(self.root), result)
            self.assertEqual(stage.pending(self.root), result)
        self.assertEqual(stage._stage_files(self.root), before)
        atomic_write_json(self.root / 'artifact.json', {'evidence': 'changed'})
        with self.assertRaises(ValidationError):
            stage.advance(self.root)

    def test_first_setup_failure_is_sealed_and_same_root_cannot_retry(self):
        self.root.rmdir()
        with patch.object(stage, '_history_authority', side_effect=stage.StageRejected('frozen source mismatch')), \
                patch.object(stage, '_construct', side_effect=AssertionError('must not construct')):
            failure = stage.prepare(self.root)
        self.assertEqual(failure['status'], 'preflight_failed_no_dispatch')
        self.assertFalse((self.root / 'exchange').exists())
        self.assertEqual(stage.advance(self.root), failure)
        with self.assertRaises(ValidationError):
            stage.prepare(self.root)

    def test_advance_keeps_unanswered_role_pending_without_retry_or_terminal_claim(self):
        waiting = {'request_hash': 'a' * 64, 'stage': 'slow_source_read'}
        with patch.object(stage, '_verify', return_value={}), \
                patch.object(stage, '_preserved'), \
                patch.object(stage, '_construct', side_effect=LocalRoleRequestPending(waiting)):
            result = stage.advance(self.root)
        self.assertEqual(result, {'status': 'pending', **waiting})
        self.assertFalse((self.root / 'completion.json').exists())

    def test_controller_scope_addition_preserves_native_payload_and_supplies_no_route(self):
        class Client:
            def complete_json(self, **kwargs):
                self.request = kwargs
                return {'action': 'inspect_catalog'}, None
        client = Client()
        caller = stage._Caller(client, stage._Budget())
        payload = {'native': {'unchanged': True}}
        caller.complete_json(stage=stage.MINING_CONTROLLER_STAGE, system_prompt='native system', payload=payload)
        self.assertIs(client.request['payload'], payload)
        self.assertTrue(client.request['system_prompt'].startswith('native system'))
        self.assertIn('controlled initialization', client.request['system_prompt'])
        self.assertIn('record_need_dispositions', client.request['system_prompt'])
        self.assertNotIn('repair_dependency', client.request['system_prompt'])
        self.assertNotIn(stage.CONTROL, client.request['system_prompt'])
        with self.assertRaises(stage.StageRejected):
            stage._Caller(client, stage._Budget(), prepare=True).complete_json(stage='slow_source_read')

    def test_copied_registry_write_and_extra_members_are_rejected(self):
        copied = self.root / 'workspace/signals/example.json'
        atomic_write_json(copied, {'stable': 'original'})
        with stage._guard(self.root):
            with self.assertRaises(stage.StageRejected):
                copied.write_text('changed')
            with self.assertRaises(stage.StageRejected):
                atomic_write_json(copied.parent / 'extra.json', {})
        self.assertEqual(stage.read(copied), {'stable': 'original'})
        work = self.root / 'workspace'
        atomic_write_json(work / 'state.json', {'last_completed_round': 0})
        atomic_write_json(work / 'cycle_state.json', {'last_completed_cycle': 0,
            'active_cycle': {'cycle_id': 1, 'phase': 'slow_loop'}})
        atomic_write_json(self.root / 'unused_external_attempts.json', {'attempts': []})
        contract_value = {'stage_only_test': 'same authority'}
        envelope = {'contract': contract_value, 'contract_hash': canonical_json_hash(contract_value)}
        atomic_write_json(self.root / 'run_contract.json', envelope)
        atomic_write_json(work / 'run_contract.json', envelope)
        manifest = {'run_contract': contract_value, 'copied_files': {'signals/example.json': stage.binding(copied)['sha256']}}
        stage._preserved(self.root, manifest)
        atomic_write_json(copied.parent / 'extra.json', {})
        with self.assertRaises(stage.StageRejected):
            stage._preserved(self.root, manifest)

    def test_native_import_readers_need_workspace_contract_and_recover_exact_authority(self):
        source_envelope = stage.read(stage.SOURCE / 'stage/slow_history/manifest.json')
        history = source_envelope['manifest']
        work = self.root / 'workspace'
        stage.EvolutionWorkspace(work)
        atomic_write_json(work / 'slow_history/manifest.json', source_envelope)
        # Actual native readers, no mock or contract= escape hatch: this is the
        # Engine's workspace-root path that earlier transport tests omitted.
        with self.assertRaisesRegex(ValidationError, 'require a frozen run contract'):
            imported_learning_events(work)
        self.assertEqual(KnowledgeUseStore(work).profiles(publish=False), {})
        contract = stage._new_contract(history, stage.read(stage.CASES), [])
        contract.freeze(self.root / 'run_contract.json')
        with self.assertRaisesRegex(ValidationError, 'require a frozen run contract'):
            imported_learning_events(work)
        stage._freeze_contract(self.root, contract)
        self.assertEqual((self.root / 'run_contract.json').read_bytes(), (work / 'run_contract.json').read_bytes())
        events = imported_learning_events(work)
        self.assertEqual(len(events), 914)
        self.assertEqual(canonical_json_hash([row.to_dict() for row in events]),
                         canonical_json_hash(history['learning_events']))
        observations = KnowledgeUseStore(work).committed_rows(repair=False)
        self.assertEqual(len(observations), 192)
        self.assertEqual(canonical_json_hash(list(observations)),
                         canonical_json_hash(sorted(history['knowledge_observations'], key=lambda row: row['event_id'])))
        self.assertTrue(KnowledgeUseStore(work).profiles(publish=False))
        self.assertFalse(list((self.root / 'exchange').glob('**/*')))

    def test_dual_contract_drift_or_missing_workspace_copy_rejects_before_construction(self):
        value = {'slow_history_manifest_hash': 'a' * 64, 'scope': 'offline-test'}
        envelope = {'contract': value, 'contract_hash': canonical_json_hash(value)}
        atomic_write_json(self.root / 'run_contract.json', envelope)
        with self.assertRaises(FileNotFoundError):
            stage._verify_contracts(self.root, value)
        atomic_write_json(self.root / 'workspace/run_contract.json', envelope)
        stage._verify_contracts(self.root, value)
        modified = {**value, 'scope': 'unauthorized'}
        atomic_write_json(self.root / 'workspace/run_contract.json', {
            'contract': modified, 'contract_hash': canonical_json_hash(modified)})
        with self.assertRaises(stage.StageRejected):
            stage._verify_contracts(self.root, value)
        with patch.object(stage, 'validate_slow_history_manifest', side_effect=AssertionError('must not read history')):
            with self.assertRaises(stage.StageRejected):
                stage._construct(self.root, {'run_contract': value})
