"""Independent native synthetic request-budget controls; these are never fresh LLM evidence."""
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
import hashlib, inspect, json, socket, sys, traceback
R=Path(__file__).resolve().parents[4];sys.path[:0]=[str(R/'src'),str(R/'scripts'),str(R)]
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import EvolutionControlFlow
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient,ExternalAttemptLedger,StructuredOutputInvalid,IdentityOutputRejected
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from tests.test_mining_controller import _fixture_store,_controller
O=Path(__file__).resolve().parent
OUT=O/sys.argv[1];OUT.mkdir(exist_ok=False)
RESULT=[]
def save(name,value): (OUT/(name+'.json')).open('x').write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
def record(name,fn):
 try:
  detail=fn();RESULT.append({'id':name,'pass':True,'detail':detail})
 except BaseException as e:RESULT.append({'id':name,'pass':False,'error':str(e),'type':type(e).__name__,'traceback':traceback.format_exc()})
def client(name,calls=30):
 root=OUT/name
 return StructuredRoleClient(registration=get_model('independent-subagent'),contract=SimpleNamespace(contract_hash='b'*64,limits={'max_local_role_calls':calls}),workspace=root,ledger=ExternalAttemptLedger(root/'unused_external.json',max_attempts=1,max_total_cost=.01),allow_external=False,environ={})
def view():
 cases,store=_fixture_store();return _controller(store,cases,object(),seed='discovery')._model_view()
def request(c,p):return json.loads((c.requests_root/(p['request_hash']+'.json')).read_text())['request']
def reservation(q):return len(json.dumps(q['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+q['max_output_tokens']
def pending(m,v):
 try:m.next_action(v)
 except LocalRoleRequestPending as e:return e.pending
 raise AssertionError('expected native pending')
def submit(c,p,raw):
 Path(p['outbox_path']).write_text(raw);c.local_role_exchange.submit(p['request_hash'],agent_id='synthetic-independent-budget-fixture-not-fresh-LLM')
def valid(c,m,v,p=None):
 p=p or pending(m,v);q=request(c,p);submit(c,p,'{"action":"inspect_manifest","rationale":["Synthetic fixture only."]}');a=m.next_action(v);return q,a

def budget_fields(q):
 p=json.loads(q['messages'][1]['content']);return p['request_budget']
def default_unchanged():
 c=client('default');m=MiningAgentRoleModel(c);p=pending(m,view());q=request(c,p);assert 'request_budget' not in json.loads(q['messages'][1]['content']);return {'reservation':reservation(q),'model_budget_enabled':False}
def exact_and_pending():
 c=client('exact');m=MiningAgentRoleModel(c,max_request_tokens=32768,max_total_tokens=98304,max_calls=6,max_output_tokens=2000);v=view();p=pending(m,v);q=request(c,p);b=budget_fields(q);assert reservation(q)==int(b['this_request']);assert int(b['remaining_after'])==98304-reservation(q);assert b['used']==0
 # Retry pending on same live instance has identical bytes and remains uncharged.
 p2=pending(m,v);assert p2['request_hash']==p['request_hash'];q,a=valid(c,m,v,p);v2={**v,'state':'second-synthetic-fixture'};p3=pending(m,v2);b2=budget_fields(request(c,p3));assert b2['used']==reservation(q);return {'first':b,'second':b2,'first_reservation':reservation(q),'physical_receipts':len(list((c.local_role_exchange.root/'receipts').glob('*.json')))}
def malformed(kind,raw):
 c=client(kind);m=MiningAgentRoleModel(c,max_request_tokens=50000,max_total_tokens=200000,max_calls=3,max_output_tokens=2000,identity_aliases=('Issuer Alpha',));v=view();p=pending(m,v);q=request(c,p);submit(c,p,raw)
 try:m.next_action(v)
 except (StructuredOutputInvalid,IdentityOutputRejected):pass
 else:raise AssertionError('expected malformed or identity exception')
 v2={**v,'state':'after-invalid-'+kind};p2=pending(m,v2);b=budget_fields(request(c,p2));assert b['used']==reservation(q);return {'charged':b,'original_reservation':reservation(q)}
def typed_and_lower_bound():
 c=client('typed');m=MiningAgentRoleModel(c,max_request_tokens=50000,max_total_tokens=200000,max_calls=3,max_output_tokens=2000);v=view();v['last_invalid_action']={'invalid_output':{'action':'inspect_manifest'},'output_patch_contract':{'base_hash':'f'*64,'allowed_paths':['rationale']},'patch_error':'Preserve action.'};p=pending(m,v);q=request(c,p);wire=json.loads(q['messages'][1]['content']);b=wire['request_budget'];assert 'Output only a JSON object with exactly base_hash and operations.' in q['messages'][0]['content'];assert wire['last_invalid_action']==v['last_invalid_action'];assert int(b['this_request'])==reservation(q)
 # A normal empty payload request must not cost less than universal next lower bound.
 estimate=c.estimate_json_request_tokens(system_prompt=q['messages'][0]['content'].removeprefix('Return exactly one JSON object and no non-JSON text. '),payload={},allow_outcomes=True,max_output_tokens=2000)
 assert b['next_request_lower_bound']<=estimate
 return {'budget':b,'empty_payload_current_grammar':estimate}
def replay_receipts():
 c=client('replay');v=view();m=MiningAgentRoleModel(c,max_request_tokens=50000,max_total_tokens=200000,max_calls=3,max_output_tokens=2000);q,a=valid(c,m,v);root=c.local_role_exchange.root;before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
 m2=MiningAgentRoleModel(c,max_request_tokens=50000,max_total_tokens=200000,max_calls=3,max_output_tokens=2000);assert m2.next_action(v)==a;after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()};assert before==after;return {'physical_receipts':len(list((root/'receipts').glob('*.json'))),'logical_replay_once':True}
def hard_stop():
 c=client('hard-stop');m=MiningAgentRoleModel(c,max_request_tokens=10,max_total_tokens=100000,max_calls=3,max_output_tokens=2000)
 try:m.next_action(view())
 except EvolutionControlFlow as e:assert not isinstance(e,ValidationError)
 else:raise AssertionError('no hard budget stop')
 assert not list(c.local_role_exchange.root.glob('inbox/*.json'));return {'inboxes':0,'propagates_control_flow':True}
with patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
 record('defaults-identical',default_unchanged)
 record('exact-pending-sequential',exact_and_pending)
 record('malformed-consumed',lambda:malformed('malformed','not JSON'))
 record('nonobject-consumed',lambda:malformed('nonobject','[]'))
 record('identity-consumed',lambda:malformed('identity','{"action":"inspect_manifest","rationale":["Issuer Alpha"]}'))
 record('typed-grammar-lower-bound',typed_and_lower_bound)
 record('cache-replay-no-duplicate-receipts',replay_receipts)
 record('hard-stop-control-flow',hard_stop)
save('results',{'at':datetime.now(timezone.utc).isoformat(),'evidence':'native synthetic fixtures only; no fresh LLM semantic evidence','external_API':0,'results':RESULT,'pass':all(r['pass'] for r in RESULT)})
print(json.dumps(RESULT,sort_keys=True))
