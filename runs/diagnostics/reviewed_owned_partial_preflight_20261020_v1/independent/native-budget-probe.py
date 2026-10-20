"""Offline fixture only: native Reflect/correction and pre-receive budget boundary."""
from copy import deepcopy
from contextlib import nullcontext
from dataclasses import asdict
import hashlib,json,tempfile
from pathlib import Path
from unittest.mock import patch
import run_reviewed_owned_partial_stage as s
from test_reviewed_owned_partial_stage import ReviewedOwnedPartialStageTests
from stock_opportunity_agent.research.evolution_core import ResearchState,SignalRound,RuntimeBudgetExceeded

HERE=Path(__file__).resolve().parent

def bh(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}

def exercise(mode,pad):
    fixture=ReviewedOwnedPartialStageTests();fixture.setUp();fixture.overlong=True
    root=fixture.base/'exchange-probe';root.mkdir()
    sample=deepcopy(fixture.sample)
    sample['signal_research_status']={'financing_listing_action:v5':{'offline_padding':'x'*pad}}
    prior=ResearchState.from_dict(sample['prior_state'])
    batch=SignalRound.from_dict({'information_needs':list(prior.next_information_needs),'selections':sample['selections'],
        'batch':{'results':sample['results'],'signal_calls':2}}).batch
    contract={'limits':s.LIMITS};records=[];outcome=None
    Old=s.LLMResearchController
    class OldCap(Old):
        def set_request_token_budget(self,value):super().set_request_token_budget(min(131072,value))
    for _ in range(3):
        budget=s._Budget(contract)
        client=s.StructuredRoleClient(registration=s.get_model('independent-subagent'),contract=s.StageContract(contract),workspace=root,
            local_role_exchange=s.LocalRoleExchange(root/'exchange',max_calls=6),
            ledger=s.ExternalAttemptLedger(root/'unused.json',max_attempts=1,max_total_cost=.01),allow_external=False,environ={},on_progress=budget)
        try:
            with s._guard(),patch.object(s,'LLMResearchController',OldCap if mode=='prior_min_cap' else Old), (patch.object(s.LocalRoleExchange,'receive',side_effect=AssertionError('oversized must reject before receive')) if pad>=131072 else nullcontext()):
                step,_controller=s._reflect(client,sample,prior,batch,False,budget)
            outcome={'status':'accepted','usage':asdict(step.usage),'need_count':len(step.value.next_information_needs)};break
        except s.LocalRoleRequestPending as exc:
            records.append({'pending_stage':exc.pending['stage'],'request_hash':exc.pending['request_hash']})
            fixture.author(exc.pending)
        except RuntimeBudgetExceeded as exc:
            outcome={'status':'RuntimeBudgetExceeded','error':str(exc),'callback_calls':budget.calls,'callback_tokens':budget.tokens};break
    requests=[]
    for p in sorted((root/'requests').glob('*.json')):
        v=json.loads(p.read_text())['request'];n=len(json.dumps(v['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+v['max_output_tokens']
        requests.append({'stage':v['stage'],'reservation':n})
    result={'mode':mode,'pad':pad,'requests':requests,'inboxes':len(list((root/'exchange/inbox').glob('*.json'))),
        'receipts':len(list((root/'exchange/receipts').glob('*.json'))),'outcome':outcome}
    fixture.doCleanups();return result

rows=[exercise('prior_min_cap',40000),exercise('current_remaining',40000)]
assert rows[0]['outcome']['status']=='RuntimeBudgetExceeded',rows
assert rows[1]['outcome']['status']=='accepted',rows
assert len(rows[1]['requests'])==2 and all(r['reservation']<131072 for r in rows[1]['requests'])
assert 131072<sum(r['reservation'] for r in rows[1]['requests'])<448000
assert rows[0]['inboxes']==1 and rows[1]['inboxes']==2
# Same native controller path: callback rejects before exchange.receive.
over=exercise('oversized_current',140000)
assert over['outcome']['status']=='RuntimeBudgetExceeded' and over['inboxes']==0 and over['outcome']['callback_calls']==0,over
result={'scope':'Offline scripted native transport/parser fixture, no fresh model/production prepare/GET/labels/Store.',
    'code_bindings':[bh(s.__file__),bh(s.SPEC)],'comparison':rows,'oversized_native':over}
(HERE/'native-budget-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
