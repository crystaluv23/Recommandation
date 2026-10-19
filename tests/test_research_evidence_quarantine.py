"""Typed evidence quarantine preserves complete inputs and remaining obligations."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_core import ResearchState, SignalSelectionDecision, default_information_plan
from stock_opportunity_agent.research.evolution_output_validation import _research_state_evidence_grounding_fallback
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalEvidence, SignalResult, SignalValue
from tests.test_evolution_state_patch import PatchCaller, patch


class ResearchEvidenceQuarantineTests(TestCase):
    def setUp(self):
        self.basic = {'requests': [{'projections': [
            {'projection_id': 'p', 'exact_text': 'Revenue was $10 million.'},
        ]}]}
        self.raw = ResearchState(
            hypotheses=('Customer demand could support expansion.',),
            current_beliefs=('Revenue was $20 million.', 'Customer demand needs investigation.'),
            next_information_needs=('Which customer contracts were disclosed?',),
        ).to_dict()
        self.raw['supporting_evidence'] = [{'kind': 'basic_info', 'projection_id': 'p',
            'exact_text': 'Revenue was $10 million.', 'claim': 'Revenue was $20 million.'}]

    def test_all_invalid_evidence_can_be_quarantined_without_a_model_rewrite(self):
        original = deepcopy(self.basic)
        caller = PatchCaller(self.raw)
        state = LLMResearchController(caller).initialize(default_information_plan(), self.basic).value
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(state.supporting_evidence, ())
        self.assertEqual(state.current_beliefs, ('Customer demand needs investigation.',))
        self.assertEqual(state.hypotheses, tuple(self.raw['hypotheses']))
        self.assertEqual(state.next_information_needs, tuple(self.raw['next_information_needs']))
        self.assertEqual(state.decision.value, 'continue')
        self.assertEqual(self.basic, original)
        self.assertEqual(caller.calls[0]['payload']['basic_info'], original)
        self.assertIn('without numerical restatements', caller.calls[0]['system_prompt'])
        self.assertNotIn('reference their numbers in beliefs', caller.calls[0]['system_prompt'])

    def test_empty_quarantine_retains_progress_while_semantic_need_is_repaired(self):
        self.raw['next_information_needs'].insert(0, 'What actual revenue results will be reported in 2026?')
        corrected = 'Which customer delivery schedules for 2026 were disclosed by 2025-09-30?'
        def repair(call):
            payload = call['payload']
            base = payload['validation_feedback']['invalid_output']
            self.assertEqual(base['supporting_evidence'], [])
            self.assertEqual(base['current_beliefs'], ['Customer demand needs investigation.'])
            self.assertEqual(payload['validation_feedback']['required_change_paths'], ['next_information_needs[0]'])
            self.assertEqual(base['next_information_needs'][1], self.raw['next_information_needs'][1])
            return patch(payload['output_patch_contract'],
                {'op': 'replace', 'path': 'next_information_needs[0]', 'value': corrected})
        caller = PatchCaller(self.raw, repair)
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime(2025, 9, 30, tzinfo=timezone.utc))
        state = controller.initialize(default_information_plan(), self.basic).value
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(state.supporting_evidence, ())
        self.assertEqual(state.next_information_needs, (corrected, self.raw['next_information_needs'][1]))

    def test_unowned_or_untyped_errors_never_authorize_evidence_deletion(self):
        error = StructuredValidationError([ValidationIssue(
            code='future_information_unavailable', paths=('next_information_needs[0]',),
            allowed_repairs=('replace',), message='Need requires later actual results.',
        )])
        self.assertIsNone(_research_state_evidence_grounding_fallback(self.raw, error))
        self.assertEqual(len(self.raw['supporting_evidence']), 1)

    def test_reflection_uses_the_same_separate_control_contract(self):
        caller = PatchCaller(lambda call: patch(call['payload']['output_patch_contract'],
            {'op': 'replace', 'path': 'decision', 'value': 'finalize'}))
        controller = LLMResearchController(caller)
        controller.set_computed_metrics([{'metric': 'price_shape', 'readable': 'price shape: return 20%'}])
        prior = ResearchState(next_information_needs=('Which customer contracts were disclosed?',))
        state = controller.reflect(default_information_plan(), prior, SignalBatchResult((), 0)).value
        self.assertEqual(state.next_information_needs, prior.next_information_needs)
        prompt = caller.calls[0]['system_prompt']
        self.assertIn('without numerical restatements', prompt)
        self.assertIn('it remains in the final control block', prompt)
        self.assertNotIn('reference their numbers in beliefs', prompt)

    def test_quarantined_last_answer_restores_every_prior_need_occurrence(self):
        need = 'What is the current cash position?'
        prior = ResearchState(next_information_needs=(need, need))
        raw = prior.to_dict()
        raw['decision'] = 'finalize'
        raw['next_information_needs'] = []
        raw['current_beliefs'] = ['cash_reserves=20']
        raw['supporting_evidence'] = [{'kind': 'signal', 'signal_ref': 'cash_reserves:v1',
            'claim': 'cash_reserves=20', 'evidence_group': 'supporting', 'evidence_index': 0}]
        full_disposition = {'need_index': 0, 'answer_scope': 'full', 'residual_need': None,
            'evidence_refs': [{'signal_ref': 'cash_reserves:v1', 'evidence_group': 'supporting', 'evidence_index': 0}],
            'reason': 'The cash measurement answers the requested cash position.'}
        unanswered_disposition = {'need_index': 0, 'answer_scope': 'unanswered', 'residual_need': None,
            'evidence_refs': [], 'reason': 'The claimed cash evidence failed validation; the cash question remains unanswered.'}

        def correct_actual_scope(call):
            failed = call['payload']['validation_feedback']['invalid_output']
            self.assertEqual(failed['supporting_evidence'], [])
            self.assertEqual(failed['current_beliefs'], [])
            self.assertEqual(failed['next_information_needs'], [need, need])
            self.assertEqual(failed['need_dispositions'], [full_disposition])
            return patch(call['payload']['output_patch_contract'],
                {'op': 'replace', 'path': 'need_dispositions[0]', 'value': unanswered_disposition})

        caller = PatchCaller(lambda call: patch(call['payload']['output_patch_contract'],
            {'op': 'replace', 'path': 'decision', 'value': 'finalize'},
            {'op': 'remove', 'path': 'next_information_needs[0]'},
            {'op': 'remove', 'path': 'next_information_needs[1]'},
            {'op': 'append', 'path': 'current_beliefs', 'value': raw['current_beliefs'][0]},
            {'op': 'append', 'path': 'supporting_evidence', 'value': raw['supporting_evidence'][0]},
            {'op': 'append', 'path': 'need_dispositions', 'value': full_disposition}), correct_actual_scope)
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(selections=(SignalSelectionDecision(
            signal_ref='cash_reserves:v1', reason_code='answer_need',
            selection_reason='Answer the cash question.', applicability_hypothesis='Cash is disclosed.',
            expected_role='primary', target_need_indices=(0,),
        ),), must_finalize=False, termination_trigger=None)
        result = SignalResult(signal_id='cash_reserves', version=1, value=SignalValue.POSITIVE,
            confidence=1.0, interpretation='cash_reserves=10', supporting_evidence=(SignalEvidence(
                document_id='cash', exact_span='Cash was 10.',
                timestamp=datetime(2025, 9, 30, tzinfo=timezone.utc)),))
        state = controller.reflect(default_information_plan(), prior, SignalBatchResult((result,), 1)).value
        # Numeric evidence quarantine is mechanical; changing actual scope is
        # the model's correction, never a fabricated fallback disposition.
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(state.supporting_evidence, ())
        self.assertEqual(state.current_beliefs, ())
        self.assertEqual(state.next_information_needs, prior.next_information_needs)
