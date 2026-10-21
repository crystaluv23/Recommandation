"""Small negative controls without a role answer, source run or computation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import run_gpre_native_routing_stage as route
from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.research.evolution_core import RuntimeLimits


class RoutingSafety(unittest.TestCase):
    def test_native_slots_base_reserve_and_prior_case_budget(self):
        native = RuntimeLimits(max_llm_calls=5, max_tokens=256000, finalization_token_reserve=64000)
        self.assertFalse(1 + 4 > native.max_llm_calls)
        self.assertEqual(native.max_tokens - route.PRIOR_TOKENS - native.finalization_token_reserve, 130112)
        self.assertEqual(route.Budget().total, 61888)

    def test_request_case_role_and_two_author_boundaries(self):
        with TemporaryDirectory() as name, patch.object(route, 'ROOT', Path(name)):
            def event(stage, size):
                path = Path(name) / (stage + '.json')
                atomic_write_json(path, {'request': {'stage': stage, 'max_output_tokens': 2000,
                    'messages': [{'role': 'user', 'content': 'x' * size}]}})
                return {'event_type': 'request_ready', 'request_path': str(path), 'request_hash': stage}
            budget = route.Budget()
            budget(event('signal_retrieval_cards', 1))
            budget(event('signal_retrieval_cards_patch_mechanics_correction', 1))
            with self.assertRaises(route.RuntimeBudgetExceeded):
                budget(event('signal_retrieval_cards_correction', 1))
            with self.assertRaises(route.RuntimeBudgetExceeded):
                route.Budget()(event('signal_retrieval_cards', 131072))
            case = route.Budget()
            case(event('signal_retrieval_cards', 100000))
            with self.assertRaises(route.RuntimeBudgetExceeded):
                case(event('signal_retrieval_cards_correction', 100000))
            with self.assertRaises(route.ValidationError):
                route.Budget()(event('research_controller_initialize', 1))

    def test_existing_destination_before_source_read(self):
        with TemporaryDirectory() as name, patch.object(route, 'ROOT', Path(name)), \
                patch.object(route, 'authorities', side_effect=AssertionError('source must not be touched')):
            with self.assertRaises(route.ValidationError):
                route.prepare(expectations=Path(name) / 'unused')

    def test_initial_guard_actual_targets_and_persistent_store_blocked(self):
        with route.initial.guards():
            with self.assertRaises(route.ValidationError):
                route.SignalExecutor.execute_batch(None, ())
            with self.assertRaises(route.ValidationError):
                route.SignalExecutor.prepare_inputs(None, ())
            with self.assertRaises(route.ValidationError):
                route.SignalRegistry.freeze(None)
            with self.assertRaises(route.ValidationError):
                route.initial.LabelStore(None)
            with self.assertRaises(route.ValidationError):
                route.initial.RawInfoStore('/persistent')

    def test_only_exact_parent_operational_lock_is_not_an_authority(self):
        with TemporaryDirectory() as name, patch.object(route, 'PARENT', Path(name)):
            root = Path(name)
            substantive = ('samples/h01/initial_state.json', 'exchange/outbox/raw.txt',
                           'exchange/receipts/receipt.json', 'cache/responses/cache.json',
                           'requests/journal.json', 'results/.dispatch.lock')
            for relative in substantive:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('original', encoding='utf-8')
            baseline = route.parent_stage_files()
            lock = root / 'exchange/.dispatch.lock'
            lock.touch()
            self.assertEqual(route.parent_stage_files(), baseline)
            lock.unlink()
            self.assertEqual(route.parent_stage_files(), baseline)
            self.assertEqual(len(baseline), len(substantive))
            (root / 'cache/responses/cache.json').write_text('changed', encoding='utf-8')
            self.assertNotEqual(route.parent_stage_files(), baseline)


if __name__ == '__main__':
    unittest.main()
