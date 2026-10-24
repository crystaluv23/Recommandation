"""Independent local resource/binding controls; no production calls or answers."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import hashlib
import run_classification_consumer_stage as stage
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleBudgetExhausted, LocalRoleRequestPending

results=[]
def require(label, condition):
    assert condition,label
    results.append({'control':label,'passed':True})
def event(root,name,messages,output=0):
    request={'stage':'research_controller_reflect','messages':messages,'max_output_tokens':output}
    p=root/(name+'.json');p.write_text(json.dumps({'request':request}))
    size=len(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+output
    return {'event_type':'request_ready','request_hash':name,'request_path':str(p)},size

def rejects(kind, fn):
    try:fn()
    except kind:return True
    return False

with TemporaryDirectory() as d, patch.object(stage,'ROOT',Path(d)):
    root=Path(d)
    # UTF8 complete bytes, output reservation, exact fit then one unit short.
    e,size=event(root,'utf8',[{'role':'user','content':'汉字🙂'}],13)
    with patch.object(stage,'ALLOWANCE',size):
        b=stage.Budget();b(e);require('UTF8 complete native message bytes plus output exact-fit',b.total==size)
    with patch.object(stage,'ALLOWANCE',size-1):
        require('One-unit-over fixed extra allowance refused',rejects(stage.RuntimeBudgetExceeded,lambda:stage.Budget()(e)))
    # Actual RuntimeBudgetExceeded must cross structured repair content family.
    require('Budget exception is control flow, outside content ValidationError',not issubclass(stage.RuntimeBudgetExceeded,ValidationError))
    e2,size2=event(root,'next',[{'role':'user','content':'x'}],1)
    for _ in range(2):
        b=stage.Budget();b(e);b(e2)
        require('Reconstruction reserves both ordered requests exactly once per logical chain',b.total==size+size2)
    old=(root/'reservations/utf8.json').read_bytes()
    changed,_=event(root,'utf8',[{'role':'user','content':'changed'}],13)
    require('Changed same-hash reservation rejects immutably',rejects(ValidationError,lambda:stage.Budget()(changed)))
    require('Rejected drift preserves original immutable reservation',(root/'reservations/utf8.json').read_bytes()==old)
    exchange=LocalRoleExchange(root/'exchange',max_calls=3)
    for i in range(3):
        request={'stage':'research_controller_reflect_correction','messages':[{'role':'user','content':str(i)}],'max_output_tokens':2}
        require('Physical unanswered inbox consumes shared slot '+str(i+1),rejects(LocalRoleRequestPending,lambda:exchange.receive(request,accounting_tokens=10)))
    fourth={'stage':'blind_predictor_predict','messages':[{'role':'user','content':'4'}],'max_output_tokens':2}
    require('Fourth physical handoff rejected before inbox',rejects(LocalRoleBudgetExhausted,lambda:exchange.receive(fourth,accounting_tokens=10)))
    require('Exactly three local physical inboxes persisted',len(list((root/'exchange/inbox').glob('*.json')))==3)

p=stage.BASE/'approved-preflight'
oracle=stage.read_json(stage.ORACLE)
actual=stage.read_json(p/'actual-batch.json')
require('Actual current measurement equals pre-frozen original complete result',actual['results']==[oracle['source_measurement']['expected_legacy_result']])
require('Complete original accepted bootstrap preserved',stage.read_json(p/'bootstrap.json')==oracle['bootstrap_gate']['original_bootstrap'])
result=actual['results'][0];declaration=actual['classification_contracts'][stage.REF]
require('Actual declaration canonical result binding',declaration['result_hash']==canonical_json_hash(result))
require('Actual declaration consumed parameters match frozen public semantics',declaration['execution']['configured_parameters']==oracle['classification']['expected_consumed_parameters'])
request_path=next((p/'requests').glob('*.json'))
request=stage.read_json(request_path)['request'];user=json.loads(request['messages'][1]['content'])
require('Actual anonymous Reflect request carries complete actual declaration',user['signal_batch'][0]['measurement_context']['classification_contract']==declaration)
require('Actual anonymous Reflect request preserves all five exact unresolved needs',user['research_state']['next_information_needs']==oracle['F7_needs']['exact_original_needs'])
require('Preflight created no production inbox',not list(p.rglob('inbox/*.json')))
require('Old terminal usage remains full historical debt',stage.read_json(stage.historical.ROOT/'prediction-sink.json')['combined_case_usage']['tokens']==235851)
for source in oracle['source_measurement']['complete_literal_sources']:
    source_path=Path(source['snapshot_path']);raw=source_path.read_bytes();record=json.loads(raw)
    require('Source record hash '+str(source['fact_index']),hashlib.sha256(raw).hexdigest()==source['record_sha256'])
    require('Source literal span '+str(source['fact_index']),record['content'][source['raw_start']:source['raw_end']]==source['literal'])
    require('Source available before prediction '+str(source['fact_index']),source['available_at']<oracle['source_measurement']['prediction_time'])
print(json.dumps({'counterexamples':results,'passed':len(results),'production_roles':0,'production_inboxes':0,'external_API':0,'labels':0},indent=2))
