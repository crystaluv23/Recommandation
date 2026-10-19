"""Synthetic transport fixture, not independent-role/model behavior evidence."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.evolution_plan_roles import _DocumentChannelCaller
from stock_opportunity_agent.research.evolution_core import _consume_model_step, AgentUsage, RuntimeLimits, RuntimeBudgetExceeded
from stock_opportunity_agent.artifacts import canonical_json_hash

class FixtureExchange(LocalRoleExchange):
    def receive(self,request,**kwargs):
        try: return super().receive(request,**kwargs)
        except LocalRoleRequestPending as exc:
            payload=json.loads(request['messages'][-1]['content'])
            value={'fixture_done': True} if 'document_channel' in payload else {'fetch_documents':[{'document_id':'fixture'}]}
            Path(exc.pending['outbox_path']).parent.mkdir(parents=True,exist_ok=True)
            Path(exc.pending['outbox_path']).write_text(json.dumps(value))
            self.submit(exc.pending['request_hash'],agent_id='synthetic-unit-fixture-not-a-model')
            return super().receive(request,**kwargs)
class Provider:
    document_views=()
    def catalog_view(self): return {'documents':[{'document_id':'fixture'}]}
    def fetch(self,entries): return [{'document_id':'fixture','exact_text':'Synthetic test material.'}]

def main():
    with tempfile.TemporaryDirectory() as tmp,patch('socket.socket',side_effect=AssertionError('network forbidden')):
        root=Path(tmp)
        contract=SimpleNamespace(contract_hash='b'*64,limits={'max_local_role_calls':4,'max_structured_corrections':1})
        def client(): return StructuredRoleClient(registration=get_model('independent-subagent'),contract=contract,
            workspace=root,local_role_exchange=FixtureExchange(root/'exchange',max_calls=4),
            ledger=ExternalAttemptLedger(root/'unused.json',max_attempts=1,max_total_cost=.01),allow_external=False,environ={})
        def run():
            caller=client()
            value,usage=_DocumentChannelCaller(caller,Provider()).complete_json(stage='synthetic_document_budget_probe',
                system_prompt='Synthetic wiring fixture. Return only the requested JSON.',payload={'fixture':True},
                allow_outcomes=False,max_output_tokens=200,max_request_tokens=10000)
            try:
                consumed=_consume_model_step(AgentUsage(llm_calls=23),usage,RuntimeLimits(max_llm_calls=24))
                outcome={'accepted':True,'result':asdict(consumed)}
            except RuntimeBudgetExceeded as exc: outcome={'accepted':False,'error':str(exc)}
            return {'value':value,'usage':asdict(usage),'consumption_after_23_calls':outcome,'requests':caller.request_hash_trace}
        first,repeat=run(),run()
        return {'scope':'Synthetic native DocumentChannelCaller/StructuredRoleClient receipt fixture; no role or research behavior',
                'first':first,'cached':repeat,'same_requests':first['requests']==repeat['requests'],
                'inbox_count':len(list((root/'exchange/inbox').glob('*.json'))),
                'receipt_count':len(list((root/'exchange/receipts').glob('*.json'))),
                'external_llm_calls':0,'readonly_data_requests':0,'fresh_independent_roles':0,
                'same_budget_and_ceiling_outcome':first['usage']==repeat['usage'] and first['consumption_after_23_calls']==repeat['consumption_after_23_calls']}
if __name__=='__main__': print(json.dumps(main(),indent=2))
