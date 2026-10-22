"""Sequential consumed native replay with future prepared file, synthetic only."""
from pathlib import Path
exec(Path(__file__).with_name('native_review_v3.py').read_text().split("with patch.object(socket,")[0])
c=client('sequential');settings=dict(max_request_tokens=99999,max_total_tokens=200000,max_calls=6,max_output_tokens=2000)
m=MiningAgentRoleModel(c,**settings);views=[{**view(),'state':'synthetic-sequence-'+str(i)} for i in range(4)];original=[]
for i,v in enumerate(views[:3]):
 p=pending(m,v);q=request(c,p);original.append({'hash':p['request_hash'],'reservation':reservation(q),'budget':budget_fields(q)});submit(c,p,'{"action":"inspect_manifest","rationale":["Synthetic sequence '+str(i)+' only."]}');m.next_action(v)
future=pending(m,views[3]);future_q=request(c,future);future_b=budget_fields(future_q)
assert m.reserved_calls==3 and m.reserved_tokens==sum(x['reservation'] for x in original)
root=c.local_role_exchange.root
physical_before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
m2=MiningAgentRoleModel(c,**settings);replayed=[]
for v,expected in zip(views[:3],original):
 m2.next_action(v);key=c.request_hash_trace[-1];q=json.loads((c.requests_root/(key+'.json')).read_text())['request'];replayed.append({'hash':key,'budget':budget_fields(q)});assert key==expected['hash'];assert budget_fields(q)==expected['budget']
future2=pending(m2,views[3]);assert future2['request_hash']==future['request_hash'];assert m2.reserved_calls==3;assert m2.reserved_tokens==m.reserved_tokens
physical_after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()};assert physical_before==physical_after
BIND_AFTER=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in TESTED];assert BIND_BEFORE==BIND_AFTER
save('sequential-results',{'source_bindings':BIND_BEFORE,'original':original,'replayed':replayed,'future_prepared_budget':future_b,'consumed_calls':m2.reserved_calls,'physical_receipts':len(list(root.glob('receipts/*.json'))),'all_physical_files_unchanged':True,'pass':True,'external_API':0,'scope':'native synthetic replay only, no fresh LLM or old stage advancement'})
print(json.dumps({'pass':True,'consumed_calls':m2.reserved_calls,'physical_receipts':len(list(root.glob('receipts/*.json'))),'future_prepared_excluded_from_earlier_budget':True,'original_hashes':[r['hash'] for r in original]}))
