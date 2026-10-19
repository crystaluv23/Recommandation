"""Recheck the two fixed canonical identity counterexamples plus readonly consumers."""
import ast, hashlib, json, tempfile
from datetime import datetime, timedelta
from pathlib import Path
R=Path(__file__).resolve().parents[3];D=Path(__file__).resolve().parent
source=(D/'probe.py').read_text();tree=ast.parse(source)
keep=[]
for n in tree.body:
    if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef)):keep.append(n)
    elif isinstance(n,ast.Assign) and all(isinstance(t,ast.Name) and t.id in {'PROFILE','HERE','ROOT'} for t in n.targets):keep.append(n)
ns={'__file__':str(D/'probe.py')};exec(compile(ast.Module(body=keep,type_ignores=[]),'independent-fixture-definitions','exec'),ns)
Fixture,reader,stamp=ns['Fixture'],ns['reader'],ns['stamp']
report={'code_bindings':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'src/stock_opportunity_agent/data/reviewed_snapshot.py',R/'src/stock_opportunity_agent/data/sec_company_facts.py']},'checks':{}}
def reject(fn):
    try:fn();return {'rejected':False}
    except reader.ReviewedSourceRejected as e:return {'rejected':True,'type':type(e).__name__,'message':str(e)}
with tempfile.TemporaryDirectory() as temporary:
    base=Path(temporary)
    for name,key,v in [('metadata_bool_as_integer','requires_primary_filing_audit',1),('metadata_count_as_float','fact_count',1.0)]:
        f=Fixture(base/name);f.records[0]['metadata'][key]=v
        report['checks'][name]=reject(lambda f=f:reader.materialize_reviewed_snapshot(f.save(),f.base/'view'))
    f=Fixture(base/'readonly');binding=reader.materialize_reviewed_snapshot(f.save(),f.base/'view');store=reader.open_raw_info_store(binding['root'],reviewed_snapshot=binding)
    first=store.documents[0];m=first.to_dict();m['metadata']['requires_primary_filing_audit']=1
    record=ns['RawInfoDocument'].from_dict(m)
    report['checks']['nonexact_append']=reject(lambda:store.append(record))
    report['checks']['exact_append_idempotent']=store.append(first) is False
    manifest_path=f.base/'view/reviewed_snapshot.json';manifest=json.loads(manifest_path.read_bytes())
    item=manifest['documents'][0];original=f.base/'view'/item['path'];b=stamp(original,m);item['sha256']=b['sha256']
    mb=stamp(manifest_path,manifest);new_binding={**binding,'manifest_sha256':mb['sha256']}
    report['checks']['rehashed_materialized_record_restart']=reject(lambda:reader.open_raw_info_store(binding['root'],reviewed_snapshot=new_binding))
    # A single real retained provider-body positive, in a synthetic temporary proof graph.
    cp=R/'runs/cold_start/evolution/deepseek-v4-flash-signal-wildcard-20260822-v1/cache/data/sec_edgar/financial_statements/4edb17b1b165004265179f8f.json'
    cb=cp.read_bytes();cache=json.loads(cb);body=cache['body']
    if isinstance(body,str):body=json.loads(body)
    f=Fixture(base/'retained_FTAI_body',body=body,cik='0001590364',cutoff='2025-07-31T00:00:00+00:00');f.cache=cache
    rawtime=datetime.fromisoformat(cache['retrieved_at'])+timedelta(seconds=1)
    f.raw.update(published_at=rawtime.isoformat(),available_at=rawtime.isoformat())
    binding=reader.materialize_reviewed_snapshot(f.save(),f.base/'view');store=reader.open_raw_info_store(binding['root'],reviewed_snapshot=binding)
    report['checks']['retained_FTAI_body_positive']={'source_cache_sha256':hashlib.sha256(cb).hexdigest(),'synthetic_raw_proof_and_temporary_products':True,'products':len(store.documents),'same_day_accessions':sum(json.loads(d.content)['filing_date']=='2025-07-31' for d in store.documents),'worker_exact':store.snapshot().documents==store.documents,'cache_unchanged':cp.read_bytes()==cb}
assert all(report['checks'][k]['rejected'] for k in ['metadata_bool_as_integer','metadata_count_as_float','nonexact_append','rehashed_materialized_record_restart'])
assert report['checks']['exact_append_idempotent']
assert report['checks']['retained_FTAI_body_positive']['products']==42
assert report['checks']['retained_FTAI_body_positive']['same_day_accessions']==0
p=D/'final-results.json';p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
