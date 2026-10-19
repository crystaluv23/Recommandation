"""Native cache preserves budget units; synthetic receipts never prove model behavior."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_core import (
    _consume_model_step, RuntimeLimits, RuntimeBudgetExceeded,
)
from stock_opportunity_agent.research.evolution_plan_roles import _DocumentChannelCaller
from stock_opportunity_agent.research.evolution_output_validation import _complete_parsed_role
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.research.evolution_transport import (
    StructuredRoleClient, ExternalAttemptLedger, _usage_from_cache,
)
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
import tests.test_signal_correction_reservation as signal_fixtures


class NativeCacheBudgetTests(TestCase):
    def _client(self, root, answer):
        class FixtureExchange(LocalRoleExchange):
            def receive(exchange, request, **kwargs):
                try:
                    return super().receive(request, **kwargs)
                except LocalRoleRequestPending as exc:
                    raw = Path(exc.pending['outbox_path'])
                    raw.parent.mkdir(parents=True, exist_ok=True)
                    raw.write_text(json.dumps(answer(json.loads(request['messages'][-1]['content']))))
                    exchange.submit(exc.pending['request_hash'], agent_id='synthetic-unit-not-a-model')
                    return super().receive(request, **kwargs)
        return StructuredRoleClient(registration=get_model('independent-subagent'),
            contract=SimpleNamespace(contract_hash='c'*64,limits={'max_local_role_calls':8,'max_structured_corrections':1}),
            workspace=root, local_role_exchange=FixtureExchange(root/'exchange',max_calls=8),
            ledger=ExternalAttemptLedger(root/'unused.json',max_attempts=1,max_total_cost=.01),
            allow_external=False,environ={})

    def _files(self, root):
        return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def _check_replay(self, run):
        with tempfile.TemporaryDirectory() as directory, patch('socket.socket',side_effect=AssertionError('network forbidden')):
            root=Path(directory)
            fresh=run(root)
            originals=self._files(root)
            warm=run(root)
            self.assertEqual(fresh,warm)
            self.assertEqual(originals,self._files(root))
            self.assertEqual(fresh['usage']['llm_calls'],2)
            self.assertEqual(len(list((root/'exchange/receipts').glob('*.json'))),2)
            self.assertEqual(len(list((root/'exchange/inbox').glob('*.json'))),2)
            return fresh

    def test_document_read_aggregate_and_actual_core_ceiling_are_equal(self):
        class Provider:
            document_views=()
            def catalog_view(self): return {'documents':[{'document_id':'fixture'}]}
            def fetch(self, entries): return [{'document_id':'fixture','exact_text':'Synthetic material.'}]
        def run(root):
            client=self._client(root,lambda payload: {'fixture_done':True} if 'document_channel' in payload
                                else {'fetch_documents':[{'document_id':'fixture'}]})
            value,usage=_DocumentChannelCaller(client,Provider()).complete_json(stage='fixture_document_read',
                system_prompt='Synthetic test fixture.',payload={'fixture':True},allow_outcomes=False,
                max_output_tokens=200,max_request_tokens=10000)
            try:
                _consume_model_step(AgentUsage(llm_calls=23),usage,RuntimeLimits(max_llm_calls=24))
                stopped=False
            except RuntimeBudgetExceeded:
                stopped=True
            admitted=_consume_model_step(AgentUsage(llm_calls=22),usage,RuntimeLimits(max_llm_calls=24))
            return {'value':value,'usage':asdict(usage),'stopped':stopped,'admitted':asdict(admitted)}
        self.assertTrue(self._check_replay(run)['stopped'])

    def test_typed_role_correction_retains_each_original_budget_call(self):
        def run(root):
            client=self._client(root,lambda payload:{'answer': bool(payload.get('validation_feedback'))})
            def parser(value):
                if not value.get('answer'):
                    raise StructuredValidationError((ValidationIssue(code='fixture_value', paths=('answer',),
                        message='Synthetic answer must be true.',allowed_repairs=('replace',)),))
                return value
            value,usage=_complete_parsed_role(client,stage='fixture_role',system_prompt='Synthetic test fixture.',
                payload={'fixture':True},parser=parser,allow_outcomes=False,max_output_tokens=200,stable_correction_prefix=True)
            return {'value':value,'usage':asdict(usage)}
        self._check_replay(run)

    def test_native_signal_batch_correction_replays_same_results_and_budget(self):
        fixture=signal_fixtures.SignalCorrectionReservationTests()
        fixture.setUp()
        def answer(payload):
            correcting='validation_feedback' in payload
            call={'payload':payload}
            return {'results':[fixture.row(call,row,
                invalid=not correcting and row['signal_ref']=='pending:v1') for row in payload['signals']]}
        def run(root):
            runner=StructuredLLMSignalRunner(self._client(root,answer))
            results,usage=runner.execute_many(fixture.inputs,fixture.as_of)
            consumed=_consume_model_step(AgentUsage(),usage,RuntimeLimits())
            return {'results':{key:value.to_dict() for key,value in results.items()},
                    'usage':asdict(usage),'consumed':asdict(consumed)}
        self._check_replay(run)

    def test_remote_cache_remains_zero_new_calls_and_cost(self):
        usage=_usage_from_cache({'usage':{'input_tokens':20,'output_tokens':10,'accounting_tokens':45}})
        self.assertEqual(usage.llm_calls,0)
        self.assertEqual(usage.cost,0)
