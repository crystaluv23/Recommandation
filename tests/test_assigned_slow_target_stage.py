"""Temporary native Controller controls; no real child/source stage operation."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from scripts import run_assigned_slow_target_stage as stage
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController


class AssignedSlowTargetStageTests(TestCase):
    def request(self, *, invalid=False, size=1, name=None):
        return {'stage': name or stage.MINING_CONTROLLER_STAGE, 'max_output_tokens': 4000,
            'messages': [{'role': 'system', 'content': 'x' * size},
                {'role': 'user', 'content': json.dumps({'last_invalid_action': {'issue': 'schema'}} if invalid else {})}]}

    def test_budget_has_two_regular_one_native_correction_and_no_prefix_or_cross_borrow(self):
        budget = stage.Budget()
        a, b, c = self.request(size=1), self.request(size=2), self.request(invalid=True)
        for row in (a, b, c):
            budget.reserve(canonical_json_hash(row), row)
        budget.reserve(canonical_json_hash(a), a)
        self.assertEqual(len(budget.requests), 3)
        for request in (self.request(size=3), self.request(invalid=True, size=3),
                        self.request(name='slow_source_read'), self.request(name='signal_mining_reflect')):
            with self.subTest(request=request['stage']), self.assertRaises(stage.base.StageRejected):
                budget.reserve(canonical_json_hash(request), request)
        with self.assertRaises(stage.base.StageRejected):
            stage.Budget().reserve('wronghash', a)

    def test_request_cap_checked_before_dispatch(self):
        request = self.request(size=stage.REQUEST_CAP)
        with self.assertRaises(stage.base.StageRejected):
            stage.Budget().reserve(canonical_json_hash(request), request)

    def test_fixed_child_root_cannot_rename_budget(self):
        with self.assertRaises(ValidationError):
            stage._root(stage.ROOT.parent / 'renamed')
        self.assertEqual(stage._root(stage.ROOT), stage.ROOT.resolve())

    def test_system_assignment_is_only_native_ref_and_leaves_payload_unchanged(self):
        calls = []
        caller = stage.Caller(SimpleNamespace(complete_json=lambda **kw: calls.append(kw)))
        payload = {'backlog_needs': [{'need_ref': stage.TARGET}], 'opaque': [1, True]}
        before = deepcopy(payload)
        caller.complete_json(stage=stage.MINING_CONTROLLER_STAGE, system_prompt='native', payload=payload)
        self.assertEqual(payload, before)
        self.assertEqual(calls[0]['payload'], before)
        self.assertIn(stage.TARGET, calls[0]['system_prompt'])
        self.assertTrue(calls[0]['system_prompt'].startswith('native'))
        with self.assertRaises(stage.base.StageRejected):
            caller.complete_json(stage='signal_mining_reflect', system_prompt='', payload={})

    def test_shared_factory_real_controller_and_original_sink_canonical_idempotency(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Only the actual shared methods are called; no Engine facade executes
            # a production stage. Empty fixture store/cases suffice for this API.
            engine = object.__new__(SignalEvolutionEngine)
            engine.workspace = SimpleNamespace(experiments_root=root / 'experiments')
            controller = engine._new_mining_controller(cycle_id=1, store=RawInfoStore(),
                model=SimpleNamespace(), case_pairs=(), measurable_evidence_manifest={},
                signal_catalog=(), signal_originals={}, seed='hypothesis',
                backlog_needs=({'need_ref': 'fixture-need'},), label_map={})
            self.assertIsInstance(controller, LabelAwareMiningController)
            unit = {'schema_version': 'mining-need-disposition-unit-v1', 'axis_id': 'surge_direction',
                'seed': 'hypothesis', 'base_hash': 'before', 'result_hash': 'after',
                'accepted_rows': [], 'pending_count': 1, 'invalid_rows': []}
            controller.need_progress_sink(unit)
            files = list(root.rglob('after.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(stage.read(files[0]), unit)
            before = files[0].read_bytes()
            controller.need_progress_sink(unit)
            self.assertEqual(files[0].read_bytes(), before)
            with self.assertRaises(ValidationError):
                controller.need_progress_sink({**unit, 'pending_count': 2})

    def test_terminal_exact_bytes_returns_without_constructing_runtime(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = {'status': 'completed_semantics_unreviewed'}
            stage.base._seal(root, result)
            with patch.object(stage, 'ROOT', root), patch.object(stage, '_construct', side_effect=AssertionError('runtime')):
                self.assertEqual(stage.advance(root), result)
            (root / 'extra.json').write_text('{}')
            with patch.object(stage, 'ROOT', root), self.assertRaises(ValidationError):
                stage.advance(root)

    def test_guard_blocks_all_prefix_and_complete_axis_entrances(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with stage._guard(root):
                for method in ('_prepare_slow_input', '_prepare_slow_memory', '_mining_context', '_run_controller_mining_axis'):
                    with self.subTest(method=method), self.assertRaises(stage.base.StageRejected):
                        getattr(SignalEvolutionEngine, method)(None)

    def test_native_need_row_calls_shared_sink_and_keeps_invalid_sibling_pending(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = object.__new__(SignalEvolutionEngine)
            engine.workspace = SimpleNamespace(experiments_root=root)
            controller = engine._new_mining_controller(cycle_id=1, store=RawInfoStore(),
                model=SimpleNamespace(), case_pairs=(), measurable_evidence_manifest={},
                signal_catalog=(), signal_originals={}, seed='hypothesis', label_map={},
                backlog_needs=({'need_ref': 'a'}, {'need_ref': 'b'}))
            view = controller._model_view()
            row = {'need_refs': ['a'], 'disposition': 'deferred_measurement',
                'signal_refs': [], 'rationale': ['Fixture uncertainty stays pending.']}
            controller._record_need_dispositions({
                'base_hash': view['need_disposition_contract']['base_hash'],
                'need_dispositions': [row, {**row, 'need_refs': ['unknown']}],
            })
            units = list(root.rglob('*.json'))
            self.assertEqual(len(units), 1)
            unit = stage.read(units[0])
            self.assertEqual(unit['accepted_rows'], [row])
            self.assertEqual(len(unit['invalid_rows']), 1)
            self.assertEqual(unit['pending_count'], 1)
            self.assertEqual(controller._pending_need_refs(), ['b'])
