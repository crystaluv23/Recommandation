"""Approved consumer resource controls; these tests do not author model answers."""
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_classification_consumer_stage as stage
from stock_opportunity_agent.models import ValidationError


class ClassificationConsumerStageTests(TestCase):
    def event(self, root, name, size=10, output=0, role='research_controller_reflect'):
        path = root / (name + '.json')
        request = {'stage': role, 'messages': ['x' * size], 'max_output_tokens': output}
        path.write_text(json.dumps({'request': request}))
        charge = len(json.dumps(request['messages'], ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()) + output
        return {'event_type': 'request_ready', 'request_hash': name,
            'request_path': str(path), 'stage': role}, charge

    def test_reconstruction_preserves_whole_ordered_charge_and_immutable_receipts(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(stage, 'ROOT', Path(directory)):
            root = Path(directory)
            first, a = self.event(root, 'a')
            second, b = self.event(root, 'b', role='blind_predictor_predict')
            for _ in range(2):
                budget = stage.Budget()
                budget(first)
                budget(second)
                self.assertEqual(budget.total, a + b)
            saved = stage.read_json(root / 'request-reservations.json')
            self.assertEqual(saved['historical_cumulative_reserved'], 235851 + a + b)
            self.assertEqual(len(list((root / 'reservations').glob('*.json'))), 2)
            self.assertFalse((root / 'exchange/inbox').exists())
            changed, _ = self.event(root, 'a', size=11)
            with self.assertRaisesRegex(ValidationError, 'immutable artifact changed'):
                stage.Budget()(changed)

    def test_new_allowance_cannot_be_replaced_by_native_or_goal_allowance(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(stage, 'ROOT', Path(directory)):
            root = Path(directory)
            first, _ = self.event(root, 'first', size=70000)
            second, _ = self.event(root, 'second', size=75000, role='blind_predictor_predict')
            budget = stage.Budget()
            budget(first)
            with self.assertRaises(stage.ApprovedAllowanceStop):
                budget(second)
            self.assertFalse((root / 'reservations/second.json').exists())

    def test_request_and_shared_call_ceiling_are_checked_before_handoff(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(stage, 'ROOT', Path(directory)):
            root = Path(directory)
            too_large, _ = self.event(root, 'large', size=131073)
            with self.assertRaises(stage.ApprovedAllowanceStop):
                stage.Budget()(too_large)
            budget = stage.Budget()
            for index in range(3):
                event, _ = self.event(root, str(index), role='research_controller_reflect_correction')
                budget(event)
            fourth, _ = self.event(root, 'fourth', role='blind_predictor_predict')
            with self.assertRaises(stage.ApprovedAllowanceStop):
                budget(fourth)
            self.assertFalse((root / 'reservations/fourth.json').exists())

    def test_unknown_role_and_duplicate_request_do_not_dispatch(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(stage, 'ROOT', Path(directory)):
            root = Path(directory)
            bad, _ = self.event(root, 'bad', role='posthoc')
            with self.assertRaises(ValidationError):
                stage.Budget()(bad)
            event, _ = self.event(root, 'same')
            budget = stage.Budget()
            budget(event)
            with self.assertRaisesRegex(ValidationError, 'duplicate native'):
                budget(event)

    def test_terminal_stages_reject_reentry(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(stage, 'ROOT', Path(directory)):
            (Path(directory) / 'completion.json').write_text('{}')
            with self.assertRaisesRegex(ValidationError, 'terminal'):
                stage.resume()
            with self.assertRaisesRegex(ValidationError, 'destination must be new'):
                stage.prepare()

    def test_same_native_limits_and_old_debt_are_kept(self):
        contract = stage.contract()
        self.assertEqual(contract['runtime_limits']['max_tokens'], 256000)
        self.assertEqual(contract['runtime_limits']['max_llm_calls'], 5)
        self.assertEqual(contract['runtime_limits']['finalization_token_reserve'], 64000)
        self.assertEqual(contract['prior_case_usage']['tokens'], 111032)
        self.assertEqual(contract['historical_usage']['tokens'], 235851)
        self.assertEqual(contract['new_logical_units'], 144968)

    def test_extra_allowance_stop_escapes_native_validation_and_budget_handlers(self):
        from stock_opportunity_agent.research.evolution_core import RuntimeBudgetExceeded
        self.assertTrue(issubclass(stage.ApprovedAllowanceStop, stage.EvolutionControlFlow))
        self.assertFalse(issubclass(stage.ApprovedAllowanceStop, ValidationError))
        self.assertFalse(issubclass(stage.ApprovedAllowanceStop, RuntimeBudgetExceeded))
