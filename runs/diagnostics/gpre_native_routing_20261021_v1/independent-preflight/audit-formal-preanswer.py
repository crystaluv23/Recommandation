"""Pure read-only formal manifest/handoff audit; explicitly never read raw output."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/gpre_native_routing_20261021_v1';S=D/'stage';T=D/'driver/temp-native-preflight-v3/stage';O=D/'independent-preflight'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return {'path':str(p),'sha256':h(p),'bytes':p.stat().st_size}
def hv(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
m=read(S/'manifest.json');ho=read(D/'root/handoff-01.json');di=read(D/'root/dispatch-01.json')
assert m['manifest_hash']=='5fa5965db3a256df1fc267c1eee79de52178e2136dc5d7015b7f2cd55e6aadbf' and m['root']==str(S)
assert hv({k:v for k,v in m.items() if k!='manifest_hash'})==m['manifest_hash']
for row in m['source_files']+m['code_files']+[m['expectations']]:assert h(Path(row['path']))==row['sha256'],row['path']
assert len(m['source_files'])==1844 and len(m['code_files'])==105
assert h(O/'pre-answer-routing-oracle.json')=='9ba88dc139e18e0e50142ea68f17cfd73e76de56ae19dcf1f6d4c51facd930df'
assert h(O/'pre-answer-budget-amendment.json')=='f34cc8b2da4a3f8cecb6ed3851b75312b3004573b25097c5329b8d5c41e0f086'
assert m['expectations']['sha256']==h(O/'pre-answer-native-review.json')=='9115654a1ef1b0bd238d4d1c95dc03962445a8c36dac06a0c183cad02231004d'
for n,key in (('inputs.json','inputs_hash'),('contract.json','contract_hash')):
 assert (S/n).read_bytes()==(T/n).read_bytes() and hv(read(S/n))==m[key]
for n in ('recomputed-bootstrap.json','native-select-context.json','native-predictor-reservation.json','request-reservations.json'):assert (S/n).read_bytes()==(T/n).read_bytes()
req=ho['request_hash'];assert req=='6dd836684a001330e31e78797bfbb439f2d751fc1aa79a6364224836029aabf8'
ni=Path(ho['native_inbox']);neutral=Path(ho['neutral_inbox']);assert ni==S/'exchange/inbox'/f'{req}.json'
assert ni.read_bytes()==neutral.read_bytes()==(T/'exchange/inbox'/f'{req}.json').read_bytes()
assert h(ni)==ho['inbox_sha256']=='7404e51bc9b498d408b5fb90b6085ee7acb7d5bb068d981652a7628751656ff9'
q=S/'requests'/f'{req}.json';assert q.read_bytes()==(T/'requests'/f'{req}.json').read_bytes()
assert read(ni)['messages']==read(q)['request']['messages']
assert di['agent_id']=='/root/exact_routing_88' and di['fork_turns']==ho['fork_turns']=='none' and di['author_dispatch_number']==1
assert neutral.name=='inbox.json' and neutral.parent.name.startswith('native-role-') and Path(ho['neutral_outbox'])==neutral.parent/'outbox.txt'
for token in ('gpre','green plains','1309402','oracle','Recommandation','pre-answer','stage/'):
 assert token.casefold() not in ho['actor_message'].casefold(),token
assert str(neutral) in ho['actor_message'] and str(Path(ho['neutral_outbox'])) in ho['actor_message']
reservations=read(S/'request-reservations.json');assert reservations['combined_case_reservation']==111032 and reservations['prior_case_usage']==61888
ctx=read(S/'native-select-context.json');assert ctx['native_request_token_budget']==68139 and ctx['native_predictor_reservation']==61973
report={'status':'PASS_FORMAL_PREANSWER_NEUTRAL_HANDOFF','audited_at_utc':datetime.now(timezone.utc).isoformat(),
 'manifest':bind(S/'manifest.json'),'source_current_equal':1844,'code_current_equal':105,'source_oracle':bind(O/'pre-answer-routing-oracle.json'),'budget_amendment':bind(O/'pre-answer-budget-amendment.json'),'preanswer_native_review':bind(O/'pre-answer-native-review.json'),
 'formal_inputs_contract_bootstrap_context_estimator_and_reservations_exact_v3':True,'journal':bind(q),'native_inbox':bind(ni),'neutral_inbox':bind(neutral),'handoff':bind(D/'root/handoff-01.json'),'dispatch':bind(D/'root/dispatch-01.json'),
 'actual_actor':di['agent_id'],'fork_turns':'none','actor_message_identity_or_oracle_path_leak':False,'case_prior':61888,'new_request_reservation':49144,'combined':111032,'native_chain_budget':68139,'native_correction_remaining':18995,
 'author_output_read':False,'native_parser_or_core_after_answer_not_checked':True,'reviewer_native_calls':0,'models':0,'GET':0,'Store':0,'labels':0}
p=O/'formal-preanswer-review.json';assert not p.exists();p.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');print(json.dumps({'status':'PASS','review':bind(p)},indent=2))
