"""Completed-result input controls; scripted roles prove plumbing only."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import socket
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_financial_context_consumer_stage as consumer
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, BlindPrediction, ResearchDecision,
)


class FinancialContextConsumerStageTests(TestCase):
    @classmethod
    def setUpClass(cls):
        with consumer.guards():
            cls.inputs, cls.bindings = consumer.authorities()
        cls.contract = {'limits': {**consumer.initial.LIMITS, 'max_local_role_calls': 3},
            'runtime_limits': consumer.read_json(consumer.ROUTING / 'contract.json')['runtime_limits']}

    def test_real_core_keeps_context_needs_and_persists_before_truth(self):
        def reflect(_controller, _plan, state, _batch):
            return AgentStep(replace(state, decision=ResearchDecision.FINALIZE),
                AgentUsage(tokens=100, llm_calls=1))
        def predict(_predictor, _context):
            return AgentStep(BlindPrediction.from_dict({'is_surge': False,
                'candidate_judgment': 'insufficient_information', 'magnitude': None,
                'confidence': {'level': 'low'}, 'key_reasons': ['Unit plumbing fixture.'],
                'uncertainties': ['Research questions remain unresolved.'], 'session_id': 'unit'}),
                AgentUsage(tokens=100, llm_calls=1))
        with tempfile.TemporaryDirectory() as directory, patch.object(consumer, 'ROOT', Path(directory)):
            with consumer.guards(), patch.object(consumer.LLMResearchController, 'reflect', reflect), \
                    patch.object(consumer.LLMBlindPredictor, 'predict', predict):
                with self.assertRaises(consumer.ConsumerBoundary):
                    consumer.native(self.inputs, self.contract, consumer.client_for(self.contract))
            saved = consumer.read_json(Path(directory) / 'prediction-sink.json')
            context = saved['context']
            text = str(context)
            for need in self.inputs['accepted_initial_step']['state']['next_information_needs']:
                self.assertIn(need, text)
            self.assertIn('5.374720662778656', text)
            self.assertEqual(saved['combined_case_usage']['tokens'], 111232)
            self.assertEqual(saved['combined_case_usage']['llm_calls'], 4)
            self.assertEqual(saved['labels'], 0)
            self.assertEqual(saved['new_Signal_calculations'], 0)
            self.assertEqual(consumer.read_json(Path(directory) / 'bootstrap.json'), self.inputs['bootstrap'])
            self.assertFalse((Path(directory) / 'exchange/inbox').exists())

    def test_whole_bootstrap_mismatch_blocks_before_model_request(self):
        changed = deepcopy(self.inputs)
        changed['bootstrap']['document_channel_set_by_core'] = False
        with tempfile.TemporaryDirectory() as directory, patch.object(consumer, 'ROOT', Path(directory)):
            with consumer.guards(), self.assertRaisesRegex(ValidationError, 'bootstrap differs'):
                consumer.native(changed, self.contract, consumer.client_for(self.contract, input_only=True))
            self.assertFalse((Path(directory) / 'role_requests').exists())
            self.assertFalse((Path(directory) / 'exchange/inbox').exists())

    def test_literal_mismatch_blocks_before_model_request(self):
        changed = deepcopy(self.inputs)
        changed['imported_batch']['results'][0]['evidence']['supporting'][0]['exact_span'] = 'absent exact source literal'
        with tempfile.TemporaryDirectory() as directory, patch.object(consumer, 'ROOT', Path(directory)):
            with consumer.guards(), self.assertRaisesRegex(ValidationError, 'source literal/PIT differs'):
                consumer.native(changed, self.contract, consumer.client_for(self.contract, input_only=True))
            self.assertFalse((Path(directory) / 'exchange/inbox').exists())

    def test_guards_reject_network_and_terminal_reentry(self):
        with consumer.guards(), self.assertRaises(ValidationError):
            socket.create_connection(('localhost', 9))
        with tempfile.TemporaryDirectory() as directory, patch.object(consumer, 'ROOT', Path(directory)):
            (Path(directory) / 'completion.json').write_text('{}')
            with self.assertRaisesRegex(ValidationError, 'terminal'):
                consumer.resume()
