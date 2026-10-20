"""Audit completed persisted source-only outputs; never instantiate a store or execute."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime
from functools import lru_cache
from types import SimpleNamespace
import hashlib,json
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.resolution import BasicInfoBundle,_matches_source_type
from stock_opportunity_agent.research.evolution_core import project_basic_info_bundle
P=Path(__file__).resolve().parent;S=P/'stage'
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(path):
 p=Path(path);assert not(p.name=='input_manifest.json' and 'minimal_rounds_v182_integrated' in str(p));return json.loads(p.read_bytes())
def bound(p):p=Path(p).resolve();return {'path':str(p),'sha256':digest(p)}
hashes={}
def check(b):
 p=Path(b['path']).resolve();key=str(p)
 if key not in hashes:hashes[key]=digest(p)
 assert hashes[key]==b['sha256'],str(p)
 return p
R=read(S/'result.json');assert R['status']=='completed' and not(S/'failure.json').exists()
plan=read(S/'plan.json');assert digest(S/'plan.json')=='b099d0af1ecc3720faaa23b884cb810122408c2b7470d494a81b7e4195987761';assert R['plan_hash']==plan['plan_hash']=='114a50b2b037409e36eee1439ca1497d94d183df8d342ba984b3f6b8e2ffeb50'
for b in plan['source_bindings']+plan['code_bindings']:check(b)
B=read(check(plan['bundle']));projection=read(check(B['projection']));cases=projection['cases'];assert len(cases)==40
base=read(check(B['base_inputs']));oldreview=read(check(base['source_review']));review=read(check(R['source_review']));assert canonical_json_hash(review['records'][:658])==canonical_json_hash(oldreview['records'])
assert len(review['records'])==1781 and Counter(r['verdict'] for r in review['records'])['admitted']==1776
assert R['old_review_rows_preserved'] is True and R['old_global_hashes_preserved'] is True and R['worker_restart_equal'] is True
for k,v in [('GETs',0),('models',0),('labels',False),('Signal_apply',False),('fullprepare',False),('MVP_closed',False)]:assert type(R[k]) is type(v) and R[k]==v
assert canonical_json_hash(R['target_dispositions'])==canonical_json_hash(B['target_dispositions'])
unknown={k:v for k,v in R['target_dispositions'].items() if not v['candidate_ids']};assert len(unknown)==6
before=read(S/'global-originals-before.json');beforepaths={b['path'] for b in before};assert len(beforepaths)==len(before)
for b in before:check(b)
oracle=Path(plan['oracle_identity']['path']).resolve().parent;currentpaths={str(p.resolve()) for p in oracle.rglob('*') if p.is_file()};additions=currentpaths-beforepaths;assert not(beforepaths-currentpaths)
receipts=R['append_receipts'];assert len(receipts)==1123 and len({r['document_id'] for r in receipts})==1123
candidates={read(check(c['document']))['document_id']:c for c in B['candidates']};assert set(candidates)=={r['document_id'] for r in receipts}
insert_counts=Counter();reuse_counts=Counter();expectedpaths=set();candidatecanon={}
for receipt in receipts:
 d=read(check(candidates[receipt['document_id']]['document']));p=check(receipt['original_record']);assert canonical_json_hash(read(p))==canonical_json_hash(d)
 assert p==oracle/d['source_type']/d['company_id']/(d['document_id']+'.json')
 assert receipt['canonical_load_equal'] is True and type(receipt['inserted']) is bool and receipt['inserted']==(str(p) not in beforepaths)
 saved=read(S/'append-receipts'/(d['document_id']+'.json'));assert canonical_json_hash(saved)==canonical_json_hash(receipt)
 fam=candidates[d['document_id']]['target_keys'][0].split('|')[0];(insert_counts if receipt['inserted'] else reuse_counts)[fam]+=1;expectedpaths.add(str(p));candidatecanon[d['document_id']]=canonical_json_hash(d)
assert sum(insert_counts.values())==853 and sum(reuse_counts.values())==270
assert additions<=expectedpaths|{str(oracle/'.raw-info-append.lock')}
assert {b['path'] for b in R['global_additions']}==additions
for b in R['global_additions']:check(b)
view=R['reviewed_source_snapshot'];vp=Path(view['root']);assert digest(vp/'reviewed_snapshot.json')==view['manifest_sha256'];vm=read(vp/'reviewed_snapshot.json');assert len(vm['documents'])==1776 and vm['scope']['acquisition_allowed'] is False
assert vm['source_review']==R['source_review'] and digest(vp/'oracle.json')==vm['oracle_sha256']==digest(plan['oracle_identity']['path'])
rr={r['document_id']:r for r in review['records'] if r['verdict']=='admitted'};info={}
for entry in vm['documents']:
 p=vp/entry['path'];check({'path':str(p),'sha256':entry['sha256']});d=read(p);r=rr[d['document_id']];original=read(check(r['original_record']));assert canonical_json_hash(d)==canonical_json_hash(original)
 assert d['document_id']==entry['document_id'] and d['content_hash']==r['content_hash']==hashlib.sha256(d['content'].encode()).hexdigest()
 info[d['document_id']]={'company_id':d['company_id'],'content_hash':d['content_hash'],'available_at':d['available_at'],'source_type':d['source_type'],'metadata':d['metadata'],'path':str(p)}
assert set(info)==set(rr)
for did,h in candidatecanon.items():assert canonical_json_hash(read(info[did]['path']))==h
@lru_cache(maxsize=8)
def content(did):return read(info[did]['path'])['content']
def verify_resolution(r,case):
 assert r['status'] in {'resolved','unresolved'};cut=datetime.fromisoformat(case['prediction_time']);refs={d['document_id']:d for d in r['documents']}
 if r['status']=='resolved':assert refs
 else:assert r['data_gap'] is not None
 assert not r['appended_documents']
 for did,ref in refs.items():
  m=info[did];assert m['company_id']==case['company_id'] and ref['content_hash']==m['content_hash'] and datetime.fromisoformat(ref['available_at'])==datetime.fromisoformat(m['available_at'])<=cut
  assert _matches_source_type(SimpleNamespace(**m),r['request']['source_types'])
 for span in r['context_spans']:
  did=span['document_id'];assert did in refs and span['content_hash']==info[did]['content_hash'] and content(did)[span['start']:span['end']]==span['exact_text'] and datetime.fromisoformat(span['available_at'])<=cut
 return r['status']
baseline=Path('runs/diagnostics/reviewed_frozen_case_inputs_20261020_v1/stage');groups={};allstatuses=Counter();types=Counter();gaprows=Counter();case_statuses={}
for group in plan['groups']:
 name=group['name'];counts=Counter();splitcounts=defaultdict(Counter);rows=[];assert len(list((S/name).glob('*.json')))==40
 for case in cases:
  d=read(S/name/(case['case_id']+'.json'));assert d['case']==case and d['registry']==group
  resolutions=d['exact_signal_input_resolutions'];assert [r['signal_ref'] for r in resolutions]==group['refs'] and len(resolutions)==18
  for row in resolutions:
   r=row['resolution'];assert r['request']['request_id']=='signal:'+row['signal_ref'];status=verify_resolution(r,case);counts[status]+=1;splitcounts[case['split']][status]+=1
   if r['data_gap']:gaprows[(name,r['data_gap']['reason'])]+=1
   for doc in r['documents']:types[(name,info[doc['document_id']]['source_type'])]+=1
  ready=sum(row['resolution']['status']=='resolved' for row in resolutions);assert d['summary']['resolved']==ready and d['summary']['denominator']==18 and d['summary']['fraction']==ready/18 and d['summary']['meets_existing_0_8']==(ready/18>=.8)
  rows.append(d['summary']);case_statuses[(name,case['case_id'])]=ready
 assert rows==R['groups'][name] and counts.total()==720
 oldrows=[read(baseline/name/'cases'/(c['case_id']+'.json')) for c in cases];oldready=sum(x['summary']['resolved_signal_inputs'] for x in oldrows);oldmeet=sum(x['summary']['meets_existing_0_8_signal_input_fraction'] for x in oldrows);assert oldready==262 and oldmeet==15
 groups[name]={'registry_version':group['version'],'registry_hash':group['registry_hash'],'refs':group['refs'],'status_counts':dict(counts),'split_status_counts':{k:dict(v) for k,v in splitcounts.items()},'cases_meeting_existing_0_8':sum(x['meets_existing_0_8'] for x in rows),'prior_resolved':oldready,'prior_cases_ge0_8':oldmeet,'resolved_delta':counts['resolved']-oldready,'per_case':rows};allstatuses.update(counts)
basic=Counter();basicflags=Counter();basicgaps=Counter();basic_percase=[];assert len(list((S/'basic-info').glob('*.json')))==40
for case in cases:
 d=read(S/'basic-info'/(case['case_id']+'.json'));assert d['case']==case and len(d['bundle']['requests'])==4
 model,lineage=project_basic_info_bundle(BasicInfoBundle.from_dict(d['bundle']));assert canonical_json_hash(model)==canonical_json_hash(d['model']) and canonical_json_hash(lineage)==canonical_json_hash(d['lineage'])
 local=[]
 for r,m in zip(d['bundle']['requests'],d['model']['requests'],strict=True):
  status=verify_resolution(r,case);basic[status]+=1;rid=r['request']['request_id'];local.append({'request_id':rid,'status':status,'gap':r['data_gap']['reason'] if r['data_gap'] else None,'visible_projection_count':m['visible_projection_count'],'effective_context_truncated':m['effective_context_truncated']})
  for flag in ['source_context_truncated','projection_context_truncated','effective_context_truncated']:basicflags[(flag,str(m[flag]))]+=1
  if r['data_gap']:basicgaps[(rid,r['data_gap']['reason'])]+=1
 basic_percase.append({'case_id':case['case_id'],'requests':local})
assert basic.total()==160
collections=[]
for manifest in [Path('runs/diagnostics/frozen40_source_proofs_20261020_v1/collection-terminal-bindings.json'),Path('runs/diagnostics/frozen40_source_proofs_20261020_v1/supplemental-v1/terminal-file-bindings.json')]:
 data=read(manifest);bindings=data['files'];assert len(bindings) in {277,20}
 for b in bindings:check(b)
 collections.append({'manifest':bound(manifest),'file_count':len(bindings),'all_unchanged':True})
assert sum(r['file_count'] for r in collections)==297
# Explicit final repeat of frozen source/code hash comparisons, using no business API.
for b in plan['source_bindings']+plan['code_bindings']:assert digest(b['path'])==b['sha256']
result={'schema_version':'independent-actual-source-consumer-review-v1','result':bound(S/'result.json'),'plan':bound(S/'plan.json'),'source_bindings_checked':len(plan['source_bindings']),'code_bindings_checked':len(plan['code_bindings']),'old_global_file_count':len(before),'old_global_all_bytes_unchanged':True,'append_receipts':1123,'actual_new_by_family':dict(insert_counts),'actual_replay_by_family':dict(reuse_counts),'old_review_rows_exact':658,'new_review_rows':1781,'admitted_view_documents':1776,'view_every_document_canonical_equal':True,'runtime_worker_restart_reported_equal':R['worker_restart_equal'],'worker_restart_independent_scope':'Persisted manifest membership and canonical files independently checked; reviewer did not instantiate Store. Actual _consume reaches result only after its native worker/restart equality guard.','unknown_target_dispositions':unknown,'groups':groups,'basic_info_status_counts':dict(basic),'basic_info_flags':{'|'.join(k):v for k,v in basicflags.items()},'basic_info_gaps':{'|'.join(k):v for k,v in basicgaps.items()},'basic_info_per_case':basic_percase,'signal_input_gap_counts':{'|'.join(k):v for k,v in gaprows.items()},'signal_input_source_type_reference_counts':{'|'.join(k):v for k,v in types.items()},'collection_binding_checks':collections,'blocking_findings':[],'limits':['First reviewer harness assumed newstage summary field names in oldbaseline files and raised KeyError; original log preserved, oldfields adapted without product changes.','Source resolution/0.8 threshold is not measurement/model semantic correctness or independent benefit.','GPRE53subset omits four canonical conflicts including latestQ1; no complete latest-quarter financial readiness claim.','Nonempty split source family and wrongtypedFTIinterim remain unknown, never negative company observations.','All model projections remain partial/unknown as persisted; whole-source retention does not establish whole-fact or model reading.','No reviewer Store/restart/materialize/prepare/execute/GET/Signalapply/model/LabelStore/LockedTest or mixedoriginJSON.']}
out=P/'independent-actual-consumer-review.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'path':str(out),'sha256':digest(out),'groups':{k:(v['status_counts'],v['cases_meeting_existing_0_8']) for k,v in groups.items()},'basic_info':dict(basic),'old_files':len(before),'checks_passed':True}))
