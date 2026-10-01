"""Shared price geometry and optional-proof rules in production role adapters."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.models import StructuredValidationError, ValidationError
from stock_opportunity_agent.research.evolution_core import GroundTruth, ResearchState, default_information_plan
from stock_opportunity_agent.research.evolution_output_validation import (
    _blind_prediction_from_role, _price_reasoning_issues, _validate_fixed_plan_semantics,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMBlindPredictor, LLMResearchController, _structured_reflection_items,
)
from stock_opportunity_agent.research.evolution_reflection_memory import (
    ReflectionMemoryIndex, violates_opportunity_proof_gate,
)
from tests.test_evolution_state_patch import PatchCaller, patch

ANCHOR = {'status': 'available', 'mean_adjusted_close': 10.0,
          'recent_close': 9.6, 'doubling_threshold': 20.0}
WRONG = 'The recent close leaves the stock roughly 108% below the doubling threshold.'
CORRECT = 'Reaching 20.00 requires a 108.33% gain from the most recent close.'
GATE = 'Before assigning a possible-surge label, require a dated catalyst plus a stated path from the current price to the threshold; otherwise downgrade to non-surge.'
CONDITIONAL = 'If no in-horizon catalyst and no path are identified, record the call as non-surge rather than possible-surge. This is not a requirement for a quantified valuation bridge.'
OPTIONAL = 'Before assigning a possible-surge label, inspect the catalyst timing and optionally analyze the price path; no quantified path is required for a positive judgment.'


def prediction():
    return {'candidate_judgment': 'unlikely', 'magnitude': None, 'confidence': {'level': 'medium'},
            'session_id': 'anonymous', 'key_reasons': [WRONG, 'Keep this reason.'],
            'uncertainties': ['Keep this uncertainty.']}


def package(call, brief=GATE, detail=CONDITIONAL):
    source = call['payload']['source_catalog'][0]
    row = {'category': 'plan_issues', 'kind': 'action', 'brief': brief, 'detail': detail,
           'scope': {'case_refs': source['case_refs'], 'plan_refs': source['plan_refs'], 'conditions': 'When evaluating a surge candidate.'},
           'limitations': ['This is an untested research improvement.'],
           'source_refs': [source['source_ref']], 'counter_refs': [], 'outcome_claims': []}
    sibling = {**deepcopy(row), 'category': 'missing_information', 'kind': 'hypothesis',
               'brief': 'Coverage may be incomplete.', 'detail': 'Keep this coverage caveat.'}
    return {'reflection_items': [row, sibling], 'selected_reflection_refs': [], 'no_findings_reason': None}


class PricePolicyContractTests(TestCase):
    def test_price_shortfall_range_has_scalar_authority_without_guessing_denominator(self):
        for text in (WRONG, 'The price is ~108% below $20.00 from the $10.00 baseline.',
                     'The stock is 108.3% short of the doubling threshold.'):
            with self.subTest(text=text):
                issues = _price_reasoning_issues((('key_reasons[0]', text),), ANCHOR)
                self.assertEqual([i.code for i in issues], ['price_shortfall_percentage_invalid'])
                self.assertEqual(issues[0].paths, ('key_reasons[0]',))
                self.assertEqual(issues[0].repair_context['price_target'], 20)
                self.assertNotIn('mechanical_action', issues[0].repair_context)
                self.assertEqual(issues[0].allowed_repairs, ('replace', 'remove'))

    def test_correct_gains_shortfalls_negations_and_unrelated_numbers_are_retained(self):
        safe = (CORRECT, 'The recent price is 52% below the doubling threshold.',
                'The price is 100% below the doubling threshold after rounding.',
                'The stock is not 108% below the doubling threshold.',
                '108% below the doubling threshold is incorrect.',
                'The stock cannot be 108% below the doubling threshold.',
                'Sales were 108% below $20.00.', 'The stock price is 108% below $90.00.')
        for text in safe:
            with self.subTest(text=text):
                self.assertEqual(_price_reasoning_issues((('text', text),), ANCHOR), [])
        for anchor in ({}, {'status': 'unavailable'}, {**ANCHOR, 'mean_adjusted_close': float('nan')},
                       {**ANCHOR, 'doubling_threshold': 0}, {**ANCHOR, 'doubling_threshold': True}):
            self.assertEqual(_price_reasoning_issues((('text', WRONG),), anchor), [])

    def test_state_and_predictor_use_same_guard_and_preserve_valid_members(self):
        raw = ResearchState(resolved_questions=(WRONG, 'Keep this sibling.'),
                            next_information_needs=('Which customer contracts were disclosed?',)).to_dict()
        def repair_state(call):
            self.assertEqual(call['payload']['validation_feedback']['required_change_paths'], ['resolved_questions[0]'])
            return patch(call['payload']['output_patch_contract'],
                         {'op': 'replace', 'path': 'resolved_questions[0]', 'value': CORRECT})
        caller = PatchCaller(raw, repair_state); controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime(2025, 1, 1, tzinfo=timezone.utc)); controller.set_evaluation_anchor(ANCHOR)
        state = controller.initialize(default_information_plan(), {'requests': []}).value
        self.assertEqual(state.resolved_questions, (CORRECT, raw['resolved_questions'][1]))
        self.assertIn('denominator', caller.calls[0]['system_prompt'])
        def repair_prediction(call):
            self.assertEqual(call['payload']['required_change_paths'], ['key_reasons[0]'])
            return patch(call['payload']['output_patch_contract'],
                         {'op': 'replace', 'path': 'key_reasons[0]', 'value': CORRECT})
        caller = PatchCaller(prediction(), repair_prediction)
        result = LLMBlindPredictor(caller).predict({'prediction_baseline': ANCHOR}).value
        self.assertEqual(result.key_reasons, (CORRECT, 'Keep this reason.'))
        self.assertEqual(result.uncertainties, ('Keep this uncertainty.',))
        self.assertEqual(result.candidate_judgment.value, 'unlikely')
        self.assertEqual(len(caller.calls), 2)

    def test_posthoc_revalidates_price_even_in_hypothesis_brief(self):
        saved = {}
        def initial(call):
            saved.update(package(call, WRONG, 'The threshold distance may have been overweighted.'))
            saved['reflection_items'][0].update(category='misleading_signals', kind='hypothesis')
            return saved
        def repair(call):
            self.assertEqual(call['payload']['required_change_paths'], ['reflection_items[0].brief'])
            return patch(call['payload']['output_patch_contract'],
                         {'op': 'replace', 'path': 'reflection_items[0].brief', 'value': CORRECT})
        caller = PatchCaller(initial, repair)
        raw = prediction(); raw['key_reasons'][0] = CORRECT
        result = LLMBlindPredictor(caller).reflect({'prediction_baseline': ANCHOR},
                 _blind_prediction_from_role(raw), GroundTruth(1.1)).value
        self.assertEqual(result.reflection_items[0].brief, CORRECT)
        self.assertEqual(result.reflection_items[0].detail, saved['reflection_items'][0]['detail'])
        self.assertEqual(result.reflection_items[1].detail, saved['reflection_items'][1]['detail'])

    def test_shared_fixed_semantics_gate_rejects_explicit_paths_and_conditional_downgrades(self):
        for text in (GATE, CONDITIONAL,
                     'A surge judgment requires an explicit bridge to the share price threshold.',
                     'If no quantified price path is found, downgrade to unlikely.'):
            with self.subTest(text=text):
                self.assertTrue(violates_opportunity_proof_gate(text))
        for text in (OPTIONAL,
                     'For surge candidates require source-backed evidence about customer orders.',
                     'Require an explicit path to commercial production for this catalyst assessment.',
                     'If no path to commercial production is identified, record the call as non-surge.',
                     'If no path to regulatory approval is found, label the candidate unlikely.',
                     'If no path is identified, do not record the call as non-surge.',
                     "Do not say 'if no path is identified, record the call as non-surge'."):
            with self.subTest(text=text):
                self.assertFalse(violates_opportunity_proof_gate(text))
        from dataclasses import replace
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_fixed_plan_semantics(replace(default_information_plan(), analysis_prompt=GATE))
        self.assertEqual(caught.exception.issues[0].paths, ('H_analyse',))
        _validate_fixed_plan_semantics(replace(default_information_plan(), analysis_prompt=OPTIONAL))

    def test_all_action_fields_join_first_frontier_and_one_patch_preserves_sibling(self):
        saved = {}
        def initial(call):
            saved.update(package(call)); return saved
        def repair(call):
            self.assertEqual(call['payload']['required_change_paths'],
                             ['reflection_items[0].brief', 'reflection_items[0].detail'])
            return patch(call['payload']['output_patch_contract'],
                         {'op': 'replace', 'path': 'reflection_items[0].brief', 'value': OPTIONAL},
                         {'op': 'replace', 'path': 'reflection_items[0].detail', 'value': OPTIONAL})
        caller = PatchCaller(initial, repair)
        raw = prediction(); raw['key_reasons'][0] = CORRECT
        result = LLMBlindPredictor(caller).reflect({'prediction_baseline': ANCHOR},
                 _blind_prediction_from_role(raw), GroundTruth(1.1)).value
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.reflection_items[0].brief, OPTIONAL)
        self.assertEqual(result.reflection_items[0].detail, OPTIONAL)
        self.assertEqual(result.reflection_items[0].source_refs, tuple(saved['reflection_items'][0]['source_refs']))
        self.assertEqual(result.reflection_items[1].detail, saved['reflection_items'][1]['detail'])

    def test_salvage_cannot_accept_policy_violation_after_failed_patch(self):
        raw = prediction(); raw['key_reasons'][0] = CORRECT
        caller = PatchCaller(package, lambda call: patch(call['payload']['output_patch_contract'],
                             {'op': 'replace', 'path': 'reflection_items[0].brief', 'value': GATE+' Keep this requirement.'}))
        caller.max_structured_corrections = 1
        result = LLMBlindPredictor(caller).reflect({'prediction_baseline': ANCHOR},
                 _blind_prediction_from_role(raw), GroundTruth(1.1)).value
        self.assertEqual(len(result.reflection_items), 1)
        self.assertEqual(result.reflection_items[0].detail, 'Keep this coverage caveat.')
