"""Post-label realized-return ownership and snapshot-local semantic repairs."""

from copy import deepcopy
from unittest import TestCase

from stock_opportunity_agent.research.evolution_core import GroundTruth
from stock_opportunity_agent.research.evolution_output_validation import _realized_outcome_issues, _blind_prediction_from_role
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
from tests.test_price_policy_contract import package, prediction, OPTIONAL
from tests.test_evolution_state_patch import PatchCaller, patch

ANCHOR = {'status': 'available', 'mean_adjusted_close': 98.168,
          'recent_close': 96.16, 'doubling_threshold': 196.336}
TRUTH = GroundTruth(1.0834895281558146)
WRONG = 'The realized max multiple is 1.0835 (about +8.3% from the recent close of 96.16).'
CORRECT = 'The realized max multiple is 1.0835 (about +8.3% from the baseline mean of 98.168).'


class RealizedOutcomeContractTests(TestCase):
    def test_runtime_outcome_controls_both_named_denominators(self):
        issues = _realized_outcome_issues((('detail', WRONG),), ANCHOR, TRUTH.to_dict())
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.code, 'realized_outcome_measurement_invalid')
        self.assertEqual(issue.paths, ('detail',))
        self.assertEqual(issue.allowed_repairs, ('replace', 'remove'))
        self.assertNotIn('mechanical_action', issue.repair_context)
        self.assertAlmostEqual(issue.repair_context['expected_percentage'], 10.6115, places=4)
        for text in (CORRECT, WRONG.replace('+8.3%', '+10.6%'),
                     'realized_max_multiple=1.08; operating growth remains uncertain.'):
            self.assertEqual(_realized_outcome_issues((('detail', text),), ANCHOR, TRUTH.to_dict()), [])

    def test_literal_rounding_outcome_mismatch_and_zero_are_owned(self):
        for text in ('The realized max multiple is 1.19.',
                     'The realized max multiple is 1.19x.',
                     'The realized max multiple is 1.0835 (20% from baseline).'):
            self.assertEqual(len(_realized_outcome_issues((('detail', text),), ANCHOR, TRUTH.to_dict())), 1)
        self.assertEqual(_realized_outcome_issues((('detail', 'The realized max multiple is 0 (a -100% return from baseline).'),),
                                                ANCHOR, GroundTruth(0).to_dict()), [])

    def test_denials_forecasts_and_separate_clauses_are_not_inferred(self):
        for text in ('This is not a realized max multiple of 1.19.',
                     'A hypothetical realized max multiple of 1.19 may occur.',
                     'The realized max multiple is 1.0835. A different period rose 20% from recent close.',
                     'The realized max multiple is 1.0835; next year could return 20% from recent close.',
                     'The realized max multiple is 1.0835, while a forecast assumes 20% from recent close.',
                     'The realized max multiple is 1.0835 (8.3% from recent close is incorrect).',
                     'Operating margins grew 20% from baseline.'):
            with self.subTest(text=text):
                self.assertEqual(_realized_outcome_issues((('detail', text),), ANCHOR, TRUTH.to_dict()), [])
        for invalid in ({}, {'status': 'unavailable'}, {**ANCHOR, 'recent_close': 0},
                        {**ANCHOR, 'mean_adjusted_close': float('nan')}):
            self.assertEqual(_realized_outcome_issues((('detail', WRONG),), invalid, TRUTH.to_dict()), [])

    def test_first_frontier_combines_policy_and_numeric_fields_and_preserves_siblings(self):
        original = {}
        def initial(call):
            original.update(package(call))
            original['reflection_items'][1]['detail'] = WRONG
            return original
        def repair(call):
            paths = call['payload']['required_change_paths']
            self.assertEqual(set(paths), {'reflection_items[0].brief', 'reflection_items[0].detail', 'reflection_items[1].detail'})
            return patch(call['payload']['output_patch_contract'],
                {'op': 'replace', 'path': 'reflection_items[0].brief', 'value': OPTIONAL},
                {'op': 'replace', 'path': 'reflection_items[0].detail', 'value': OPTIONAL},
                {'op': 'replace', 'path': 'reflection_items[1].detail', 'value': CORRECT})
        caller = PatchCaller(initial, repair)
        saved = prediction(); saved['key_reasons'][0] = 'Operating uncertainty remains.'
        before = deepcopy(saved)
        result = LLMBlindPredictor(caller).reflect({'prediction_baseline': ANCHOR},
            _blind_prediction_from_role(saved), TRUTH).value
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(saved, before)
        self.assertEqual(len(result.reflection_items), 2)
        self.assertEqual(result.reflection_items[1].detail, CORRECT)
        self.assertEqual(result.reflection_items[1].brief, original['reflection_items'][1]['brief'])
        self.assertEqual(result.reflection_items[1].source_refs, tuple(original['reflection_items'][1]['source_refs']))
        self.assertIn('five-complete-trading-day', caller.calls[0]['system_prompt'])

    def test_row_salvage_cannot_accept_rejected_outcome_text(self):
        def initial(call):
            value = package(call, OPTIONAL, OPTIONAL)
            value['reflection_items'][1]['detail'] = WRONG
            return value
        caller = PatchCaller(initial, lambda call: patch(call['payload']['output_patch_contract'],
            {'op': 'replace', 'path': 'reflection_items[1].detail', 'value': WRONG+' Still wrong.'}))
        caller.max_structured_corrections = 1
        saved = prediction(); saved['key_reasons'][0] = 'Operating uncertainty remains.'
        result = LLMBlindPredictor(caller).reflect({'prediction_baseline': ANCHOR},
            _blind_prediction_from_role(saved), TRUTH).value
        self.assertEqual(len(result.reflection_items), 1)
        self.assertEqual(result.reflection_items[0].detail, OPTIONAL)
