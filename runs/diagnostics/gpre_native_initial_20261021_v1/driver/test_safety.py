"""Pure temporary budget/guard controls; no author responses or native stage."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import run_gpre_native_initial_stage as stage
from stock_opportunity_agent.artifacts import atomic_write_json


class InitialSafety(unittest.TestCase):
    def test_native_configuration_and_guard_targets(self):
        self.assertEqual(replace(stage.orientation.LIMITS, max_llm_calls=3).max_tokens, 256000)
        with stage.guards():
            with self.assertRaises(stage.ValidationError):
                stage.LabelStore(None)
            with self.assertRaises(stage.ValidationError):
                stage.SignalRegistry.freeze(None)
            with self.assertRaises(stage.ValidationError):
                stage.SignalExecutor.execute_batch(None, ())
            with self.assertRaises(stage.ValidationError):
                stage.RawInfoStore('/persistent')
            memory = stage.RawInfoStore()
            self.assertEqual(memory.documents, ())

    def test_request_case_and_two_author_bounds(self):
        with TemporaryDirectory() as name, patch.object(stage, 'ROOT', Path(name)):
            def event(role, content):
                path = Path(name) / (role + '.json')
                atomic_write_json(path, {'request': {'stage': role,
                    'messages': [{'role': 'user', 'content': content}], 'max_output_tokens': 8000}})
                return {'event_type': 'request_ready', 'request_hash': role, 'request_path': str(path)}
            budget = stage.Budget()
            budget(event('research_controller_initialize', 'x'))
            budget(event('research_controller_initialize_patch_mechanics_correction', 'x'))
            with self.assertRaises(stage.RuntimeBudgetExceeded):
                budget(event('research_controller_initialize_correction', 'x'))
            with self.assertRaises(stage.RuntimeBudgetExceeded):
                stage.Budget()(event('research_controller_initialize', 'x' * 131072))
            case = stage.Budget()
            case(event('research_controller_initialize', 'x' * 120100))
            with self.assertRaises(stage.RuntimeBudgetExceeded):
                case(event('research_controller_initialize_correction', 'x' * 120100))
            with self.assertRaises(stage.ValidationError):
                stage.Budget()(event('research_controller_reflect', 'x'))

    def test_existing_destination_rejects_before_authorities(self):
        with TemporaryDirectory() as name, patch.object(stage, 'ROOT', Path(name)), \
                patch.object(stage, 'authorities', side_effect=AssertionError('not reached')):
            with self.assertRaises(stage.ValidationError):
                stage.prepare(expectations=Path(name) / 'missing')


if __name__ == '__main__':
    unittest.main()
