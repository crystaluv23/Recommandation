"""Independent readonly completed periodic source/view/consumer audit, never executor."""
import ast,hashlib,json,socket,ssl
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import BasicInfoBundle
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.research.basic_info_orientation import compile_basic_info_requests
from stock_opportunity_agent.research.evolution_core import default_information_plan,project_basic_info_bundle
from stock_opportunity_agent.signal_library import SignalSpec
P=Path(__file__).resolve().parent;S=P/'stage';R=P.parents[2]
def forbidden(*a,**kw):raise RuntimeError('Independent source review forbids networking')
socket.socket=forbidden;socket.create_connection=forbidden
# Reuse only the prior independent date/coverage readers, never its main/run.
old=R/'runs/diagnostics/reviewed_anchor_financial_snapshot_20261020_v1/independent/final-source-review.py'
tree=ast.parse(old.read_text());names={'read','hashfile','check','instant','research_periods','observation_count'}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'prior-pure-review-functions','exec'),globals())
def canon(x):return canonical_json_hash(x)
def documents_hash(values):return canon([x.to_dict() for x in values])
def check_resolution(r,cutoff,company,store,payloads):
 docs=[];periods=set()
 for ref in r['documents']:
  d=store.load(ref['document_id'],as_of=cutoff);assert d.company_id==company and d.content_hash==ref['content_hash'] and d.available_at==instant(ref['available_at']) and d.available_at<=cutoff
  if d.document_id not in payloads:
   try:payloads[d.document_id]=json.loads(d.content)
   except ValueError:payloads[d.document_id]=None
  docs.append(d);periods|=research_periods(d,payloads[d.document_id])
 c=r['coverage'];span=(max(periods)-min(periods)).days if len(periods)>=2 else None
 assert c['selected_document_count']==len(docs)
 assert c['observed_distinct_period_count']==len(periods) and c['observed_period_span_days']==span
 assert c['observed_observation_count']==max((observation_count(d,payloads[d.document_id]) for d in docs),default=0)
 if r['status']=='resolved':assert docs and c['contract_satisfied']
 for a in r['context_spans']:
  d=store.load(a['document_id'],as_of=cutoff);assert d.content_hash==a['content_hash'] and d.content[a['start']:a['end']]==a['exact_text'] and d.available_at==instant(a['available_at'])
 return docs

def main():
 assert (S/'result.json').is_file(),'wait for completed result'
 plan=read(S/'plan.json');result=read(S/'result.json');inputs=read(S/'input_manifest.json');app=read(S/'append-inventory.json')
 assert canon({k:v for k,v in plan.items() if k!='plan_hash'})==plan['plan_hash']==result['plan_hash']
 assert canon(inputs)==result['input_manifest_hash']
 for key in ['fixed_authorities','old_financial_tree','old_source_bindings','source_bindings','candidates','registry_bindings','code_bindings']:
  for b in plan[key]:assert hashfile(b['path'])==b['sha256'],b['path']
 oldreview=check(plan['old_source_review']);review=check(inputs['source_review']);assert len(oldreview['records'])==655
 assert canon(review['records'][:655])==canon(oldreview['records'])
 oldinputbinding=next(b for b in plan['old_financial_tree'] if Path(b['path']).name=='input_manifest.json')
 oldinput=check(oldinputbinding);oldviewroot=Path(oldinput['reviewed_source_snapshot']['root']);oldmanifest=read(oldviewroot/'reviewed_snapshot.json')
 old_ids={x['document_id'] for x in oldmanifest['documents']};assert len(old_ids)==650
 cases=plan['cases'];refs=plan['registry_refs'];assert len(cases)==len({c['case_id'] for c in cases})==15 and len(refs)==len(set(refs))==18
 authority=check(plan['registry_source_inputs']);specs=[];skills={}
 for ref in refs:
  sid,version=ref.split(':');paths=list(Path(authority['registry_root']).glob('*/'+sid+'/versions/'+version+'/spec.json'));assert len(paths)==1
  spec=SignalSpec.from_dict(read(paths[0]));assert spec.ref==ref;specs.append(spec.to_dict())
  if spec.execution_type.value=='llm':skills[ref]=(paths[0].parent/'skill.md').read_text()
 registry_hash=hashlib.sha256(json.dumps({'version':12,'specs':specs,'skills':skills},sort_keys=True,separators=(',',':')).encode()).hexdigest()
 assert registry_hash==plan['registry_hash']==inputs['registry_hash']==authority['registry_hash'] and plan['registry_version']==12
 candidates=[check(b) for b in plan['candidates']];assert len(candidates)==3
 receiptmap={x['candidate']:x for x in app['receipts']};candidate_checks=[]
 for c in candidates:
  d=RawInfoDocument.from_dict(c['document']);a=receiptmap[c['candidate']];assert a['document_id']==d.document_id
  saved=RawInfoDocument.from_dict(check(a['original_record']));assert canon(saved.to_dict())==canon(d.to_dict())
  proofmap={p['kind']:p for p in c['proofs']};b=proofmap['sec_static_archive_body_response'];receipt=check(b['artifact']);matches=[x for x in receipt['requests'] if x['name']==b['entry_name']];assert len(matches)==1
  raw=Path(b['raw_response']['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==b['raw_response']['sha256']==matches[0]['raw_sha256']
  assert raw.decode('utf-8')==d.content and b['endpoint']==d.metadata['source_url']==matches[0]['url']
  assert matches[0]['method']=='GET' and matches[0]['http_status']==200 and matches[0]['response_url']==matches[0]['url']
  if c['candidate'].startswith('KGC'):
   assert c['proof_profile']=='sec_filing_exhibit_response_v1' and d.metadata['form']==d.metadata['parent_form']=='40-F'
   assert d.available_at==d.published_at==instant('2025-03-27T20:55:21Z')
   assert d.document_id.startswith('sec-exhibit:cik_0000701818:000110465925028819:')
   assert d.metadata['exhibit_type']==('99.1' if c['candidate']=='KGC_AIF' else '99.2')
  else:
   assert c['candidate']=='MS_Q1' and d.metadata['form']=='10-Q' and d.available_at==instant('2025-05-05T20:13:06Z')
  candidate_checks.append({'candidate':c['candidate'],'document_id':d.document_id,'raw_sha256':b['raw_response']['sha256'],'canonical_saved_equal':True,'published_at':d.published_at.isoformat(),'available_at':d.available_at.isoformat(),'form':d.metadata['form'],'metadata':d.metadata})
 before=read(S/'global-originals-before.json');assert all(hashfile(x['path'])==x['sha256'] for x in before)
 oracle_root=Path(plan['oracle_identity']['path']).parent;existing={x['path'] for x in before};now={str(p.resolve()) for p in oracle_root.rglob('*') if p.is_file()};added=now-existing
 declared={x['path'] for x in result['global_new_files']};assert added==declared=={x['path'] for x in app['global_new_files']}
 assert added<={x['original_record']['path'] for x in app['receipts']}|{str(oracle_root/'.raw-info-append.lock')}
 assert all(hashfile(x['path'])==x['sha256'] for x in result['global_new_files'])
 store=open_raw_info_store(inputs['reviewed_source_snapshot']['root'],reviewed_snapshot=inputs['reviewed_source_snapshot']);worker=store.snapshot();restart=open_raw_info_store(inputs['reviewed_source_snapshot']['root'],reviewed_snapshot=inputs['reviewed_source_snapshot'])
 assert documents_hash(store.documents)==documents_hash(worker.documents)==documents_hash(restart.documents)
 docmap={d.document_id:d for d in worker.documents};new_ids={c['document']['document_id'] for c in candidates}
 assert set(docmap)==old_ids|new_ids
 for candidate in candidates:assert canon(docmap[candidate['document']['document_id']].to_dict())==canon(candidate['document'])
 for oldrow in oldmanifest['documents']:
  assert canon(read(oldviewroot/oldrow['path']))==canon(docmap[oldrow['document_id']].to_dict())
 annual_id='sec:cik_0000895421:000089542125000304';assert annual_id not in docmap
 assert plan['excluded_unresolved']==inputs['excluded_unresolved']==result['excluded_unresolved'] and len(plan['excluded_unresolved'])==1
 assert plan['excluded_unresolved'][0]['candidate']=='MS_FY2024_annual' and plan['excluded_unresolved'][0]['verdict']=='unknown'
 assert not any(d.source_type in {'financials','sec_company_facts_raw_response'} for d in store.documents)
 default_requests=compile_basic_info_requests(default_information_plan().basic_info_policy);default_rows=[x.to_dict() for x in default_requests]
 counts=Counter();per_ref={r:Counter() for r in refs};payloads={};rows=[];basic=[]
 for c in cases:
  x=read(S/'cases'/(c['case_id']+'.json'));assert x['case']==c;cutoff=instant(c['cutoff']);bundle=x['basic_info_bundle']
  assert [r['request'] for r in bundle['requests']]==default_rows
  model,lineage=project_basic_info_bundle(BasicInfoBundle.from_dict(bundle))
  assert canon(model)==canon(x['basic_info_model']) and canon(lineage)==canon(x['basic_info_lineage'])
  for r in bundle['requests']:check_resolution(r,cutoff,c['company_id'],worker,payloads)
  op=next(r for r in model['requests'] if r['request']['request_id']=='orientation.v1.operating_report')
  raw_op=next(r for r in bundle['requests'] if r['request']['request_id']=='orientation.v1.operating_report')
  basic.append({'case_id':c['case_id'],'status':op['status'],'projection_status':op['projection_status'],'source_context_truncated':op['source_context_truncated'],'projection_context_truncated':op['projection_context_truncated'],'effective_context_truncated':op['effective_context_truncated'],'available_projection_count':op['available_projection_count'],'visible_projection_count':op['visible_projection_count'],'omitted_projection_count':op['omitted_projection_count'],'omitted_context_markers':op['omitted_context_markers'],'selected_document_ids':[d['document_id'] for d in raw_op['documents']],'visible_projection_document_ids':list(dict.fromkeys(p['document_id'] for p in op['projections'])),'actual_visible_operating_text':' '.join(p['exact_text'] for p in op['projections']) if c['ticker'] in {'KGC','MS'} else None})
  exact=x['exact_signal_input_resolutions'];assert [z['signal_ref'] for z in exact]==refs;ready=0
  for z in exact:
   r=z['resolution'];docs=check_resolution(r,cutoff,c['company_id'],worker,payloads);counts[r['status']]+=1;per_ref[z['signal_ref']][r['status']]+=1;ready+=r['status']=='resolved'
   rows.append({'case_id':c['case_id'],'signal_ref':z['signal_ref'],'status':r['status'],'document_ids':[d.document_id for d in docs],'coverage':r['coverage'],'data_gap':r['data_gap']})
  expected={'case_id':c['case_id'],'resolved_signal_inputs':ready,'signal_ref_denominator':18,'resolved_fraction':ready/18,'meets_existing_0_8_signal_input_fraction':ready/18>=.8};assert x['summary']==expected
 assert len(rows)==270 and result['cases']==[read(S/'cases'/(c['case_id']+'.json'))['summary'] for c in cases]
 assert result['cases_meeting_existing_0_8']==sum(v['meets_existing_0_8_signal_input_fraction'] for v in result['cases'])
 for k in ['labels_loaded','signal_apply_executed','full_prepare_executed','full48_readiness_proven','engineering_mvp_closed']:assert result[k] is False
 assert result['network_requests']==result['external_llm_calls']==0
 out={'scope':'Independent completed readonly source/consumer review, no prepare/execute/Signalapply/model/labels/GET/globalstore construction orrefresh','plan_hash':plan['plan_hash'],'input_manifest_hash':canon(inputs),'code_bindings_verified':plan['code_bindings'],'stage_bindings':{n:{'path':str(S/n),'sha256':hashfile(S/n)} for n in ['plan.json','input_manifest.json','result.json','append-inventory.json','source-review.json','global-originals-before.json']},'candidates':candidate_checks,'all_old_review_rows_preserved':655,'all_old_admitted_records_preserved_canonically':650,'new_view_documents':len(docmap),'old_global_files_hashed_unchanged':len(before),'allowed_additions':len(added),'oracle_identity_unchanged':check(plan['oracle_identity']),'worker_restart_canonical_equal':True,'MS_annual_primary_unknown_not_in_view':True,'MS_annual_CompanyFacts_approved_policy_not_reclassified':True,'fixed_cases':15,'exact_registry_version':12,'registry_hash':registry_hash,'ordered_ref_denominator':18,'resolution_denominator':270,'status_counts':dict(counts),'per_ref_counts':{r:dict(v) for r,v in per_ref.items()},'cases_meeting_existing_0_8':result['cases_meeting_existing_0_8'],'BasicInfo_actual_projection_and_omissions':basic,'all270_resolutions':rows,'limits':['Source presence/coverage and literal projection preservation do not prove Signal measurement or model understanding.','MSannualprimary time conflict remainsunknown; separate approved CompanyFacts filed-nextUTCday policy remainsunchanged.','Whole KGC AIF/MDA are not all audited FS99.3notes or external referenced materials.','Only fixed15 input consumers, notfull48,modelbehavior,MVP or benefit.']}
 (P/'independent-source-consumer-review.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['code_bindings_verified','all270_resolutions','BasicInfo_actual_projection_and_omissions','oracle_identity_unchanged','stage_bindings']},indent=2))
if __name__=='__main__':main()
