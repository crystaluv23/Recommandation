"""Supplemental independently constructed equality, decimal, projection and seed-scope controls."""
from pathlib import Path
exec(Path(__file__).with_name('native_review_v3.py').read_text().split("with patch.object(socket,")[0])
from stock_opportunity_agent.research.mining_role_model import MiningRequestBudgetExhausted

def decimal_boundaries():
 rows=[]
 for used in (9,10,99,100,999,1000):
  c=client('decimal-'+str(used));m=MiningAgentRoleModel(c,max_request_tokens=99999,max_total_tokens=999999,max_calls=20,max_output_tokens=2000);m.reserved_tokens=used;m.reserved_calls=9 if used%2 else 10;p=pending(m,view());q=request(c,p);b=budget_fields(q);assert int(b['this_request'])==reservation(q);assert int(b['remaining_after'])==999999-used-reservation(q);rows.append({'used':used,'calls_used':b['calls_used'],'required':reservation(q)})
 c=client('wide-cap');m=MiningAgentRoleModel(c,max_request_tokens=10**25,max_total_tokens=10**26,max_output_tokens=2000);q=request(c,pending(m,view()));b=budget_fields(q);assert int(b['this_request'])==reservation(q);assert int(b['remaining_after'])==10**26-reservation(q);return {'digit_boundaries':rows,'wide_cap_width':len(b['this_request'])}
def equal_single():
 c=client('single-probe');m=MiningAgentRoleModel(c,max_request_tokens=99999,max_output_tokens=2000);q=request(c,pending(m,view()));n=reservation(q)
 c2=client('single-equal');m2=MiningAgentRoleModel(c2,max_request_tokens=n,max_output_tokens=2000);q2=request(c2,pending(m2,view()));assert reservation(q2)==n
 c3=client('single-minus-one');m3=MiningAgentRoleModel(c3,max_request_tokens=n-1,max_output_tokens=2000)
 try:m3.next_action(view())
 except MiningRequestBudgetExhausted:pass
 else:raise AssertionError('single minus one admitted')
 assert not list(c3.local_role_exchange.root.glob('inbox/*.json'));return {'equal_admitted':n,'minus_one_rejected':n-1}
def equal_total():
 c=client('total-probe');m=MiningAgentRoleModel(c,max_total_tokens=99999,max_output_tokens=2000);q=request(c,pending(m,view()));n=reservation(q)
 c2=client('total-equal');m2=MiningAgentRoleModel(c2,max_total_tokens=n,max_output_tokens=2000);q2=request(c2,pending(m2,view()));assert reservation(q2)==n;assert int(budget_fields(q2)['remaining_after'])==0
 c3=client('total-minus-one');m3=MiningAgentRoleModel(c3,max_total_tokens=n-1,max_output_tokens=2000)
 try:m3.next_action(view())
 except MiningRequestBudgetExhausted:pass
 else:raise AssertionError('total minus one admitted')
 return {'equal_admitted':n,'remaining_after':0,'minus_one_rejected':n-1}
def call_and_seed_scope():
 c=client('seeds');m=MiningAgentRoleModel(c,max_calls=1,max_output_tokens=2000);v=view();q,_=valid(c,m,v);v2={**v,'seed':'hypothesis'}
 try:m.next_action(v2)
 except MiningRequestBudgetExhausted:pass
 else:raise AssertionError('shared model cross-seed call cap reset')
 assert m.reserved_calls==1;assert len(list(c.local_role_exchange.root.glob('inbox/*.json')))==1;return {'consumed_calls':1,'other_seed_rejected':True}
def source_projection():
 c=client('projection');m=MiningAgentRoleModel(c,max_request_tokens=99999,max_total_tokens=999999,max_output_tokens=2000,identity_aliases=('cik_0001951089','Issuer Alpha'))
 v=view();v['source_probe']={'document_ref':'document-secfacts:0001951089:0001213900-24-092156:'+'a'*64,'url':'https://www.sec.gov/Archives/edgar/data/1951089/000121390024092156/form20-f.htm','literal':'利润 400 USD; 2024-06-30'}
 p=pending(m,v);q=request(c,p);b=budget_fields(q);assert int(b['this_request'])==reservation(q);text=json.dumps(q['messages']);assert '0001213900-24-092156' not in text and '1951089/' not in text;assert '利润' in q['messages'][1]['content'];return {'reservation':reservation(q),'masked_explicit_coordinates':True,'unicode_preserved':True}
with patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
 record('decimal-boundaries-widecaps',decimal_boundaries)
 record('single-equality',equal_single)
 record('aggregate-equality',equal_total)
 record('calls-shared-seed-instance',call_and_seed_scope)
 record('identity-projected-exact-envelope',source_projection)
BIND_AFTER=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in TESTED];assert BIND_BEFORE==BIND_AFTER
save('boundary-results',{'source_bindings':BIND_BEFORE,'results':RESULT,'pass':all(r['pass'] for r in RESULT),'external_API':0,'evidence':'native synthetic only'})
print(json.dumps(RESULT,sort_keys=True))
