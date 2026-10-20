"""Offline authoring-contract and existing disposition/consumer connections.

Scripted answers prove reachable native behavior, not fresh semantic obedience.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from unittest import TestCase

from stock_opportunity_agent.research.evolution_core import (
    InformationPlan, ResearchState, SignalSelectionDecision, SignalRound, _assemble_final_context,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController, LLMBlindPredictor
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalResult
from tests.test_evolution_state_patch import PatchCaller, patch


FIXTURE = Path(__file__).parent / 'fixtures/owned_partial_residual_mirror.json'
NOW = datetime(2025, 9, 30, tzinfo=timezone.utc)


class ReflectFacetScopeTests(TestCase):
    def setUp(self):
        data = json.loads(FIXTURE.read_bytes())
        self.prior = ResearchState.from_dict(data['prior'])
        self.plan = InformationPlan.from_dict(data['plan'])
        self.selections = tuple(SignalSelectionDecision.from_dict(row) for row in data['selections'])
        self.batch = SignalBatchResult(results=tuple(SignalResult.from_dict(row) for row in data['results']), signal_calls=2)
        self.adoption = deepcopy(data['raw49']['operations'][1])
        self.ref = {'signal_ref': 'financing_listing_action:v5', 'evidence_group': 'counter', 'evidence_index': 3}

    def controller(self, caller):
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(NOW)
        controller.set_reflection_runtime_context(selections=self.selections, must_finalize=False, termination_trigger=None)
        return controller

    def test_scope_guidance_reaches_actual_initial_request_without_answer_injection(self):
        needs = (
            self.prior.next_information_needs[4],
            'By prediction time, what agreement terms and operating status were disclosed through the latest interim period and afterwards?',
            'By prediction time, what future delivery schedule had already been disclosed?',
        )
        for need in needs:
            with self.subTest(need=need):
                prior = replace(self.prior, next_information_needs=(*self.prior.next_information_needs[:4], need))
                caller = PatchCaller(RuntimeError('captured request without answer'))
                with self.assertRaisesRegex(RuntimeError, 'captured request without answer'):
                    self.controller(caller).reflect(self.plan, prior, self.batch)
                self.assertEqual(len(caller.calls), 1)
                request = caller.calls[0]
                prompt = request['system_prompt']
                for instruction in ('static attributes or terms, dynamic status',
                    "does not extend the fact's observation or coverage period",
                    'preserve every unsupported requested facet and its time scope',
                    'cannot fit losslessly', 'valid evidence may still be adopted independently',
                    'In reason, explain which requested facets and coverage the actual evidence answers',
                    'what remains missing; the reason never substitutes for the residual',
                    'a forecast already public at prediction_time may answer'):
                    self.assertIn(instruction, prompt)
                payload = request['payload']
                self.assertEqual(payload['research_state']['next_information_needs'][4], need)
                self.assertEqual(payload['need_transition_contract']['required_disposition_need_indices'], [4])
                self.assertIsNone(payload['validation_feedback'])
                self.assertNotIn('expected_residual', payload)
                self.assertNotIn('oracle', payload)
                self.assertIn('June 30, 2025', json.dumps(payload['signal_batch']))

    def test_unanswered_keeps_whole_need_while_adopting_evidence_and_reaching_consumer(self):
        def authored(call):
            return patch(call['payload']['output_patch_contract'], self.adoption,
                {'op': 'append', 'path': 'need_dispositions', 'value': {
                    'need_index': 4, 'answer_scope': 'unanswered', 'residual_need': None,
                    'evidence_refs': [self.ref],
                    'reason': 'Retain the exact compound question without losing unsupported attributes, status or coverage; the adopted observation is contextual.'}})
        caller = PatchCaller(authored)
        result = self.controller(caller).reflect(self.plan, self.prior, self.batch)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(result.value.next_information_needs, self.prior.next_information_needs)
        self.assertEqual(result.value.supporting_evidence[-1].claim, self.adoption['value']['claim'])
        row = result.metadata['need_dispositions']['items'][0]
        self.assertEqual((row['answer_scope'], row['residual_need']), ('unanswered', None))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accepted.json'
            path.write_text(json.dumps({'state': result.value.to_dict(), 'metadata': result.metadata}))
            saved = json.loads(path.read_bytes())
            state = ResearchState.from_dict(saved['state'])
            final = _assemble_final_context(plan=self.plan, company_id='anonymous-test', additional_identity_aliases=(),
                basic_info={}, state=state, rounds=(SignalRound(information_needs=self.prior.next_information_needs,
                    selections=self.selections, batch=self.batch),), prediction_time=NOW,
                state_deltas=({'round': 1, 'need_dispositions': saved['metadata']['need_dispositions']},))
            capture = PatchCaller(RuntimeError('captured predictor without answer'))
            with self.assertRaisesRegex(RuntimeError, 'captured predictor without answer'):
                LLMBlindPredictor(capture).predict(final)
            wire = capture.calls[0]['payload']['final_context']
            self.assertEqual(wire['final_research_state']['next_information_needs'], list(self.prior.next_information_needs))
            self.assertEqual(wire['state_evolution'][0]['need_dispositions'], saved['metadata']['need_dispositions'])

    def test_full_remains_valid_for_exact_period_question_answered_by_visible_evidence(self):
        question = 'By prediction time, what revolving availability at June 30, 2025 and compliance during the six months then ended were disclosed?'
        prior = replace(self.prior, next_information_needs=(*self.prior.next_information_needs[:4], question))
        def authored(call):
            return patch(call['payload']['output_patch_contract'], self.adoption,
                {'op': 'remove', 'path': 'next_information_needs[4]'},
                {'op': 'append', 'path': 'need_dispositions', 'value': {
                    'need_index': 4, 'answer_scope': 'full', 'residual_need': None,
                    'evidence_refs': [self.ref],
                    'reason': 'The adopted literal answers the exact requested facility and compliance period; no later status or agreement terms were requested.'}})
        caller = PatchCaller(authored)
        result = self.controller(caller).reflect(self.plan, prior, self.batch)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(result.value.next_information_needs, prior.next_information_needs[:4])
        self.assertEqual(result.metadata['need_dispositions']['items'][0]['answer_scope'], 'full')
