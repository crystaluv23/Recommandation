"""Native synthetic-only carrier/correction/callback controls; no real inputs."""
from datetime import datetime, timezone
from pathlib import Path
import json
import socket
import ssl
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from diagnose_executed_answer_scope import StageContract
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_core import ResearchDecision, ResearchState, default_information_plan
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.evolution_transport import ExactResponseCache, ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalEvidence, SignalExecutor, SignalResult, SignalValue, NumericMeasurement

NOW = datetime(2025, 5, 30, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parent
FORBIDDEN = []


class Boundary(BaseException):
    pass


def denied(*args, **kwargs):
    FORBIDDEN.append('forbidden')
    raise AssertionError('cache/receive/network/labels/Signal forbidden')


class NativeCarrierBoundaryTests(unittest.TestCase):
    def batch(self):
        return SignalBatchResult((SignalResult(
            'synthetic_ratio', 1, SignalValue.POSITIVE, 1.0, 'synthetic_ratio=0.25',
            supporting_evidence=(SignalEvidence('synthetic-doc', '{"value":2}', NOW),),
            measurement=NumericMeasurement(0.25, 'ratio', 'synthetic division', '2025-03-31', '2025-01-01'),
        ),), 1)

    def invoke(self, root, corrections, state):
        counts = {'ready': 0, 'pre_egress': 0}

        def progress(event):
            if event['event_type'] == 'request_ready':
                counts['ready'] += 1
                raise Boundary()

        client = StructuredRoleClient(
            registration=get_model('independent-subagent'),
            contract=StageContract({'limits': {'max_local_role_calls': 1, 'max_structured_corrections': corrections}}),
            workspace=root, local_role_exchange=LocalRoleExchange(root / 'exchange', max_calls=1),
            ledger=ExternalAttemptLedger(root / 'unused.json', max_attempts=1, max_total_cost=0.01),
            allow_external=False, environ={}, on_progress=progress,
        )
        complete = client.complete_json

        def observe(**kwargs):
            counts['pre_egress'] += 1
            # Same complete_json forwarding/serialization boundary as the real
            # harness, but a synthetic result and no original source is read.
            json.dumps(kwargs, ensure_ascii=False, allow_nan=False)
            return complete(**kwargs)

        client.complete_json = observe
        controller = LLMResearchController(client)
        controller.set_evaluation_context(NOW)
        controller.set_request_token_budget(131072)
        return controller, counts

    def test_default_continue_empty_carrier_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'continuing research requires'):
            ResearchState()

    def test_zero_corrections_is_rejected_before_any_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller, counts = self.invoke(root, 0, ResearchState(decision=ResearchDecision.FINALIZE))
            with self.assertRaisesRegex(ValueError, 'correction budget must be 1 or 2'):
                controller.reflect(default_information_plan(), ResearchState(decision=ResearchDecision.FINALIZE), self.batch())
            self.assertEqual(counts, {'ready': 0, 'pre_egress': 0})
            self.assertEqual(list((root / 'requests').glob('*.json')), [])

    def test_legal_finalize_and_one_correction_configuration_reach_real_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = ResearchState(decision=ResearchDecision.FINALIZE)
            controller, counts = self.invoke(root, 1, state)
            with self.assertRaises(Boundary):
                controller.reflect(default_information_plan(), state, self.batch())
            self.assertEqual(counts, {'ready': 1, 'pre_egress': 1})
            self.assertEqual(len(list((root / 'requests').glob('*.json'))), 1)
            self.assertEqual(list((root / 'exchange' / 'outbox').glob('*')), [])


    def test_narrative_schema_and_distinct_document_reach_same_native_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = ResearchState(decision=ResearchDecision.FINALIZE)
            controller, counts = self.invoke(root, 1, state)
            literal = 'An independently authored synthetic disclosure is present.'
            batch = SignalBatchResult((SignalResult(
                'synthetic_disclosure', 1, SignalValue.NEUTRAL, 0.5,
                'A synthetic disclosure requires further interpretation.',
                supporting_evidence=(SignalEvidence('different-narrative-doc', literal, NOW),),
            ),), 1)
            with self.assertRaises(Boundary):
                controller.reflect(default_information_plan(), state, batch)
            self.assertEqual(counts, {'ready': 1, 'pre_egress': 1})
            journals = list((root / 'requests').glob('*.json'))
            self.assertEqual(len(journals), 1)
            request = json.loads(journals[0].read_bytes())['request']
            payload = json.loads(next(item['content'] for item in request['messages'] if item['role'] == 'user'))
            row = payload['signal_batch'][0]
            self.assertEqual(row['signal_ref'], 'synthetic_disclosure:v1')
            self.assertNotIn('measurement_context', row)
            self.assertEqual(row['evidence']['supporting'][0]['model_evidence_text'], literal)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeCarrierBoundaryTests)
    with patch.object(ExactResponseCache, 'load', denied), patch.object(LocalRoleExchange, 'receive', denied), patch.object(ExternalAttemptLedger, 'reserve', denied), patch.object(socket, 'create_connection', denied), patch.object(socket.socket, 'connect', denied), patch.object(urllib.request, 'urlopen', denied), patch.object(LabelStore, '__init__', denied), patch.object(SignalExecutor, 'execute_batch', denied):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    with (ROOT / 'synthetic-boundary-controls-v2-result.json').open('x') as handle:
        json.dump({'tests_run': result.testsRun, 'errors': len(result.errors), 'failures': len(result.failures), 'forbidden_calls': FORBIDDEN, 'real_source_calls': 0}, handle, indent=2)
        handle.write('\n')
    raise SystemExit(0 if result.wasSuccessful() and not FORBIDDEN else 1)
