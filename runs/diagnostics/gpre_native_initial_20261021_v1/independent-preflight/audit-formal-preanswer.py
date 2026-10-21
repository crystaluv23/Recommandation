"""Read formal frozen input and neutral handoff only; never read an author answer."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/gpre_native_initial_20261021_v1';S=D/'stage';T=D/'driver/temp-native-preflight-v2/stage';O=D/'independent-preflight'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def binding(p):return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
m=read(S/'manifest.json');h=read(D/'root/handoff-01.json');dispatch=read(D/'root/dispatch-01.json')
assert m['manifest_hash']=='6f085fd1947d2f98725a8913ea35416198d6f6cd860df6e8366d06f7f6fee955'
assert digest({k:v for k,v in m.items() if k!='manifest_hash'})==m['manifest_hash']
assert m['root']==str(S)
for row in m['source_files']+m['code_files']+[m['expectations']]:assert sha(Path(row['path']))==row['sha256'],row['path']
assert sha(O/'pre-answer-source-oracle.json')=='0bce2212dfad502f8ad7adf8ac36661ff3da8bc43cb735cef633f9f9663d8189'
assert m['expectations']['sha256']=='5df8021c85ac69817491247578409a17a11a26c7d9499bdea8af08766dfae463'
for n,key in [('inputs.json','inputs_hash'),('contract.json','contract_hash')]:assert digest(read(S/n))==m[key] and (S/n).read_bytes()==(T/n).read_bytes()
assert (S/'samples/h01/bootstrap.json').read_bytes()==(T/'samples/h01/bootstrap.json').read_bytes()
req=h['request_hash'];ni=Path(h['native_inbox']);neutral=Path(h['neutral_inbox']);qi=S/'requests'/f'{req}.json'
assert ni==S/'exchange/inbox'/f'{req}.json'
assert ni.read_bytes()==neutral.read_bytes()==(T/'exchange/inbox'/f'{req}.json').read_bytes()
assert sha(ni)==h['inbox_sha256']=='bd54c8ea3b994e94b712cf0a02f10c713fc3f0f257062364d06a98664a7fddde'
assert qi.read_bytes()==(T/'requests'/f'{req}.json').read_bytes()
assert h['fork_turns']==dispatch['fork_turns']=='none' and dispatch['author_dispatch_number']==1
assert dispatch['agent_id']=='/root/exact_initial_87'
assert neutral.name=='inbox.json' and neutral.parent.name.startswith('native-role-')
assert Path(h['neutral_outbox'])==neutral.parent/'outbox.txt'
for x in ('gpre','green plains','1309402','oracle','pre-answer','Recommandation','stage/'):
 assert x.casefold() not in h['actor_message'].casefold(),x
assert str(neutral) in h['actor_message'] and str(Path(h['neutral_outbox'])) in h['actor_message']
r=read(qi)['request'];assert read(ni)['messages']==r['messages']
for x in ('gpre','green plains','1309402','pre-answer-source-oracle','private_anchor_crosscheck'):
 assert x.casefold() not in json.dumps(r['messages']).casefold()
reservation=read(S/'request-reservations.json');assert reservation['total']==61888 and len(reservation['requests'])==1
result={'status':'PASS_FORMAL_PREANSWER_AND_NEUTRAL_HANDOFF','audited_at_utc':datetime.now(timezone.utc).isoformat(),
 'formal_manifest':binding(S/'manifest.json'),'source_current_equal':len(m['source_files']),'code_current_equal':len(m['code_files']),
 'oracle_unchanged':binding(O/'pre-answer-source-oracle.json'),'preanswer_review_unchanged':binding(O/'pre-answer-native-review.json'),
 'formal_bootstrap_inputs_contract_and_request_exact_temp':True,'native_inbox':binding(ni),'neutral_inbox':binding(neutral),
 'request_journal':binding(qi),'handoff':binding(D/'root/handoff-01.json'),'dispatch':binding(D/'root/dispatch-01.json'),
 'actual_role':dispatch['agent_id'],'fork_turns':'none','actor_message_issuer_or_oracle_or_repo_path_leak':False,
 'native_messages_issuer_leak':False,'logical_reservation':61888,
 'author_answer_read':False,'author_response_bytes_handoff_not_yet_checked':True,
 'scope':'Formal frozen inputs/request/handoff only. No rawanswer read, native parser execution, acceptedstate or H_init semantic verdict. Actor policies in handoff verified, execution compliance not inferred from message alone.',
 'reviewer_native_calls':0,'Store':0,'model':0,'GET':0,'labels':0}
p=O/'formal-preanswer-review.json';assert not p.exists();p.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps({'status':'PASS','review':binding(p)},indent=2))
