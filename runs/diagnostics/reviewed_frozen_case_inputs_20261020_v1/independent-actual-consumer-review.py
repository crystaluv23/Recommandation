"""Read completed fixed40 output once; never reexecute or parse mixed origin."""
import ast,hashlib,json,socket,ssl
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.resolution import BasicInfoBundle,RawInfoRequest
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.research.basic_info_orientation import compile_basic_info_requests
from stock_opportunity_agent.research.evolution_core import default_information_plan,project_basic_info_bundle
from stock_opportunity_agent.signal_library import SignalSpec
P=Path(__file__).resolve().parent;S=P/'stage';R=P.parents[2]
ORIGIN=R/'runs/cold_start/minimal_rounds_v182_integrated/input_manifest.json';ORIGIN_SHA='3c6a74fea9c3e29742d9759f11a9087cbb16726e17d509ec1f4dd7d5e2b48d3c'
def forbidden(*a,**k):raise AssertionError('Network forbidden in independent source review')
socket.socket=forbidden;socket.create_connection=forbidden
# Reuse only pure independent coverage checks; never execute prior review main.
for file,names in [('runs/diagnostics/reviewed_anchor_financial_snapshot_20261020_v1/independent/final-source-review.py',{'instant','research_periods','observation_count'}),('runs/diagnostics/reviewed_periodic_operating_snapshot_20261020_v1/independent-source-consumer-review.py',{'check_resolution'})]:
 tree=ast.parse((R/file).read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'independent-pure-consumer-checks','exec'),globals())
def read(p):
 p=Path(p).resolve();assert p!=ORIGIN.resolve() and '/outcome-label-store' not in str(p) and p.name!='locked_test.json','forbidden label-bearing JSON read'
 return json.loads(p.read_bytes())
def hashfile(p):
 p=Path(p).resolve();assert '/outcome-label-store' not in str(p) and p.name!='locked_test.json','forbidden label file hash'
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
canon=canonical_json_hash

def main():
 assert (S/'result.json').is_file(),'Wait for unique execute completed result'
 plan=read(S/'plan.json');result=read(S/'result.json');assert canon({k:v for k,v in plan.items() if k!='plan_hash'})==plan['plan_hash']==result['plan_hash']
 assert plan['origin']['path']==str(ORIGIN) and plan['origin']['sha256']==ORIGIN_SHA==hashfile(ORIGIN)
 bindings=[b for key in ('metadata_authorities','source_bindings','old_periodic_tree','code_bindings') for b in plan[key]]+[plan['projection']]+[b for g in plan['groups'] for b in g['definition_bindings']]
 for b in bindings:assert hashfile(b['path'])==b['sha256'],b['path']
 projection=read(plan['projection']['path']);assert projection['origin']==plan['origin']
 assert set(projection)=={'origin','origin_control','split_order','cases','identities'}
 assert projection['origin_control']=={'schema_version':'diagnostic-development-subset-v1','selection_seed':42,'selection_before_model_calls':True,'approved_manifest_hash':'13772d031162179f7468cb0e9d9aea0424f78084d18c65fe059d5b72840013e9','locked_test_hash':projection['origin_control']['locked_test_hash']}
 cases=projection['cases'];assert len(cases)==len({c['case_id'] for c in cases})==40
 counts=Counter(c['split'] for c in cases);assert counts=={'anchor':16,'evolution_validation':8,'discovery':16}
 observed=Counter();splitorder=[]
 for i,c in enumerate(cases):
  assert set(c)=={'case_id','company_id','prediction_time','split','split_case_index','order'}
  assert c['order']==i and c['split_case_index']==observed[c['split']];observed[c['split']]+=1
  if not splitorder or splitorder[-1]!=c['split']:splitorder.append(c['split'])
  assert isinstance(c['prediction_time'],str) and instant(c['prediction_time']).utcoffset() is not None
 assert splitorder==projection['split_order'];assert set(projection['identities'])=={c['company_id'] for c in cases}
 assert all(set(v)=={'cik','ticker'} and v['cik']==k[4:] for k,v in projection['identities'].items())
 view=plan['reviewed_source_snapshot'];store=open_raw_info_store(view['root'],reviewed_snapshot=view);worker=store.snapshot();restart=open_raw_info_store(view['root'],reviewed_snapshot=view)
 assert canon([d.to_dict() for d in store.documents])==canon([d.to_dict() for d in worker.documents])==canon([d.to_dict() for d in restart.documents]);assert len(store.documents)==653
 assert not any(d.source_type in {'financials','sec_company_facts_raw_response'} for d in store.documents)
 expectedrequests=[r.to_dict() for r in compile_basic_info_requests(default_information_plan().basic_info_policy)];payloads={};basic=[]
 assert len(list((S/'basic-info').glob('*.json')))==40
 for c in cases:
  row=read(S/'basic-info'/(c['case_id']+'.json'));assert row['case']==c;bundle=row['bundle'];cutoff=instant(c['prediction_time'])
  assert [r['request'] for r in bundle['requests']]==expectedrequests
  for r in bundle['requests']:check_resolution(r,cutoff,c['company_id'],worker,payloads)
  model,lineage=project_basic_info_bundle(BasicInfoBundle.from_dict(bundle));assert canon(model)==canon(row['model']) and canon(lineage)==canon(row['lineage'])
  basic.append({'case_id':c['case_id'],'requests':[{'request_id':r['request']['request_id'],'status':r['status'],'projection_status':r['projection_status'],'effective_context_truncated':r['effective_context_truncated'],'omitted_projection_count':r['omitted_projection_count'],'omitted_context_markers':r['omitted_context_markers']} for r in model['requests']]})
 groups=[]
 assert [g['name'] for g in plan['groups']]==['default_v6','latest_v12']
 for g in plan['groups']:
  refs=g['refs'];assert len(refs)==len(set(refs))==18;specs=[];skills={};specmap={}
  for ref in refs:
   sid,v=ref.rsplit(':',1);paths=list(Path(g['root']).glob('*/'+sid+'/versions/'+v+'/spec.json'));assert len(paths)==1
   spec=SignalSpec.from_dict(read(paths[0]));assert spec.ref==ref;specs.append(spec.to_dict());specmap[ref]=spec
   skill=paths[0].parent/'skill.md'
   if skill.is_file():skills[ref]=skill.read_text()
  rh=hashlib.sha256(json.dumps({'version':g['version'],'specs':specs,'skills':skills},sort_keys=True,separators=(',',':')).encode()).hexdigest();assert rh==g['registry_hash']==result['groups'][g['name']]['registry_hash']
  assert len(list((S/g['name']/'cases').glob('*.json')))==40
  totals=Counter();perref={r:Counter() for r in refs};summaries=[];audit=[]
  for c in cases:
   row=read(S/g['name']/'cases'/(c['case_id']+'.json'));assert row['case']==c and row['registry_version']==g['version'] and row['registry_hash']==rh
   exact=row['exact_signal_input_resolutions'];assert [x['signal_ref'] for x in exact]==refs;ready=0
   for x in exact:
    r=x['resolution'];spec=specmap[x['signal_ref']];p=spec.retrieval_policy
    expected=RawInfoRequest(request_id='signal:'+spec.ref,description=spec.description,source_types=spec.source_types,lookback_days=p.lookback_days,max_documents=10,query=p.query,required_source_groups=p.required_source_groups,minimum_distinct_periods=p.minimum_distinct_periods,minimum_period_span_days=p.minimum_period_span_days,minimum_observations=p.minimum_observations).to_dict()
    assert r['request']==expected
    docs=check_resolution(r,instant(c['prediction_time']),c['company_id'],worker,payloads);totals[r['status']]+=1;perref[x['signal_ref']][r['status']]+=1;ready+=r['status']=='resolved'
    audit.append({'case_id':c['case_id'],'signal_ref':x['signal_ref'],'status':r['status'],'document_ids':[d.document_id for d in docs],'coverage':r['coverage'],'data_gap':r['data_gap']})
   expectedsummary={'case_id':c['case_id'],'split':c['split'],'resolved_signal_inputs':ready,'signal_ref_denominator':18,'resolved_fraction':ready/18,'meets_existing_0_8_signal_input_fraction':ready/18>=.8};assert row['summary']==expectedsummary;summaries.append(expectedsummary)
  actual=result['groups'][g['name']];assert len(audit)==720 and actual['cases']==summaries and actual['resolved_count']==totals['resolved'] and actual['cases_meeting_existing_0_8']==sum(s['meets_existing_0_8_signal_input_fraction'] for s in summaries)
  groups.append({'name':g['name'],'version':g['version'],'registry_hash':rh,'refs':refs,'status_counts':dict(totals),'per_ref_status_counts':{r:dict(v) for r,v in perref.items()},'cases_meeting_existing_0_8':actual['cases_meeting_existing_0_8'],'case_summaries':summaries,'all720_saved_inputs':audit})
 for k in ('outcome_fields_consumed_or_output','LabelStore_read','LockedTest_file_opened','signal_apply_executed','full_prepare_executed','mixed_origin_deserialized_during_execute'):assert result[k] is False
 assert result['mixed_origin_bytes_accessed_for_hash'] is True and result['network_requests']==result['model_calls']==result['global_source_writes']==0
 assert result['worker_restart_canonical_equal'] and result['old_sources_and_view_unchanged']
 # Verify saved source bindings again after consumers without touching global stores.
 for b in bindings:assert hashfile(b['path'])==b['sha256']
 report={'scope':'Independent readonly completed-artifact source/consumer audit, no prepare/execute/Signalapply/model/LabelStore/LockedTest/GET/globalstore construction or refresh. Origin bytes streamed for exact hash, never parsed.','plan_hash':plan['plan_hash'],'stage_bindings':{n:{'path':str(S/n),'sha256':hashfile(S/n)} for n in ('plan.json','case-identities.json','execution-start.json','result.json')},'source_binding_checks':len(bindings),'origin_sha256':ORIGIN_SHA,'mixed_origin_stream_hash_read':True,'mixed_origin_JSON_read':False,'projection_counts':dict(counts),'split_order':splitorder,'case_identities':cases,'original_row_comparison_limit':'Does not parse real mixed origin; exactoriginSHA plus frozen exporter and prior independent temp whitelist/order tests establish projection provenance.','view_count':653,'worker_restart_canonical_equal':True,'BasicInfo40':basic,'groups':groups,'limits':['Exact v6/v12 input status matrices are separate; source coverage is not numeric Signal correctness or model behavior.','PIT gaps and partial BasicInfo are retained; no labels or old run resume; no fitness/MVP/benefit claim.']}
 out=P/'independent-actual-consumer-review.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'review_sha256':hashfile(out),'groups':[{'name':g['name'],'counts':g['status_counts'],'atleast0_8':g['cases_meeting_existing_0_8']} for g in groups],'BasicInfo_cases':40,'view_docs':653}))
if __name__=='__main__':main()
