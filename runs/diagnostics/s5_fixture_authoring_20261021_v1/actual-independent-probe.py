"""Read-only actual S5 artifact audit; no native execution/Store/model/label calls."""
from pathlib import Path
from datetime import datetime,timedelta
import hashlib,json,re
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/s5_fixture_authoring_20261021_v1';P=R/'runs/diagnostics/reviewed_fixture_author_stage_20261021_v1';H='3c5b05db2520bdcd35b63f88a684cfd0e644f418026346915ee19311ffcb4d30'
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();bind=lambda p:{'path':str(Path(p).resolve()),'sha256':sha(p)}
manifest=read(P/'manifest.json');completion=read(P/'completion.json');inputs=read(P/'inputs.json');expected=read(P/'expectations.json')
assert manifest['manifest_hash']=='cadf061d99611e3dff7564f8357536a0d97b2f7f836a30643d0bf3f320b90f8e'==completion['manifest_hash']
assert digest({k:v for k,v in manifest.items() if k!='manifest_hash'})==manifest['manifest_hash']
assert digest({k:v for k,v in completion.items() if k!='seal'})==completion['seal']
assert len(manifest['code'])==177
for row in manifest['code']+completion['artifacts']:assert sha(row['path'])==row['sha256'],row['path']
for name in ['contract','inputs','expectations']:assert digest(read(P/f'{name}.json'))==digest(manifest[name])
assert not (P/'failure.json').exists();assert expected['fixed_denominator']==2
contract=manifest['contract'];assert contract['max_calls']==1 and contract['limits']['max_case_llm_calls']==1 and contract['max_output_tokens']==4000 and contract['limits']['max_case_tokens']==contract['limits']['max_request_tokens']==131072
sets=[{p.stem for p in (P/folder).glob('*'+ext)} for folder,ext in [('requests','.json'),('exchange/inbox','.json'),('exchange/outbox','.txt'),('exchange/receipts','.json'),('cache/responses','.json')]];assert all(x=={H} for x in sets)
journal=read(P/'requests'/f'{H}.json');req=journal['request'];inbox=read(P/'exchange/inbox'/f'{H}.json');receipt=read(P/'exchange/receipts'/f'{H}.json');cache=read(P/'cache/responses'/f'{H}.json');rawpath=P/'exchange/outbox'/f'{H}.txt';rawtext=rawpath.read_text();raw=json.loads(rawtext)
assert digest(req)==H==journal['request_hash']==inbox['request_hash']==receipt['request_hash']==cache['request_hash']
assert receipt['agent_id']=='/root/role_78'==cache['usage']['agent_id']
assert receipt['inbox_sha256']==sha(P/'exchange/inbox'/f'{H}.json')=='99aba2421c2ff47be01b93fa30426dcd22fa724c3e6ddd6ce660616a3d555134'
assert receipt['raw_output_sha256']==sha(rawpath)=='e13d33245349b5286c87f5de37b3928f2a1e37b73d5c1446a39e82ea1c39a962'
assert req['messages']==inbox['messages'] and req['stage']=='mining_candidate_materialize_tests' and req['max_output_tokens']==4000
reservation=len(json.dumps(req['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+4000
assert reservation==14241==cache['usage']['accounting_tokens']==completion['result']['logical_reservation']<=131072
assert raw==cache['json_output'] and rawtext==cache['raw_output'] and set(raw)=={'tests'} and len(raw['tests'])==2
payload=json.loads(req['messages'][1]['content']);assert set(payload)=={'candidate','cited_evidence','execution_semantics','last_issues','skill','spec','tests_schema'}
assert payload['candidate']==inputs['candidate'] and payload['spec']==inputs['accepted']['spec'] and payload['skill'] is None and not payload['last_issues']
assert 'metadata.cik' in payload['execution_semantics']['retrieval']['fixtures'] and 'sort_keys' in payload['execution_semantics']['retrieval']['fixtures']
assert 'positive_measurement' not in json.dumps(payload) and 'expectations' not in payload and '0.25' not in json.dumps(payload)
assert len(payload['cited_evidence'])==len(inputs['evidence'])==6
for row in payload['cited_evidence']:
 source=inputs['evidence'][row['ref']];assert row['exact_span']==source['exact_span'] and row['available_at']==source['available_at'] and row['published_at']==source['published_at'];assert len(row['exact_span'])<=600
assert payload['tests_schema']['items']['properties']['documents']['items']['properties']['content']['type']=='string'
assert payload['tests_schema']['items']['properties']['documents']['items']['properties']['metadata']['type']=='object'
assert 'metadata' not in payload['tests_schema']['items']['properties']['documents']['items']['required']
cp=P/'isolated/candidates/financial/fixture_author_revenue_growth/v1';persisted=read(cp/'tests.json')['tests'];loaded=read(P/'loaded-candidate.json');spec=read(cp/'spec.json')
assert digest(spec)==digest(inputs['accepted']['spec']) and persisted==raw['tests']==loaded['loaded_tests']
assert spec['signal_id']=='fixture_author_revenue_growth' and spec['version']==1 and spec['execution']['type']=='deterministic'
assert read(P/'isolated/signals/registry.json')=={'version':1} and len(list((P/'isolated/signals').rglob('spec.json')))==0
assert read(cp/'candidate.json')=={'origin':'mining:controller'}
# Check original seed leaves without running schema constructors or functions.
seed=next(x['spec'] for x in read(R/'configs/signals_v1.json')['signals'] if x['spec']['signal_id']=='revenue_growth_yoy')
def leaves(a,b,path=''):
 if isinstance(a,dict):
  for k,value in a.items():
   if path=='' and k in ['signal_id','version']:continue
   leaves(value,b[k],path+'.'+k)
 else:assert digest(a)==digest(b),path
leaves(seed,spec)
assert loaded['schemas']==['legacy','typed'] and len(loaded['results'])==2
cases=[]
for index,(fixture,result) in enumerate(zip(raw['tests'],loaded['results'])):
 assert fixture['expected']=='positive' and fixture['company_id']=='cik_0000000001' and fixture['as_of']==expected['cutoff']
 assert len(fixture['documents'])==1
 doc=fixture['documents'][0];assert type(doc['content']) is str;body=json.loads(doc['content']);assert body['cik']==doc['metadata']['cik']=='0000000001'
 assert doc['source_type']=='financials' and doc['published_at']==doc['available_at']==expected['available_at']
 cutoff=datetime.fromisoformat(fixture['as_of']);public=datetime.fromisoformat(doc['available_at']);assert cutoff.utcoffset() is not None and public<=cutoff
 if body.get('schema_version')=='sec-company-facts-document-v1':
  schema='typed';facts=body['facts'];assert body['filing_date']=='2025-02-15' and body['form']=='10-K'
  assert all(x['taxonomy']=='us-gaap' and x['tag']=='Revenues' and x['unit']=='USD' for x in facts)
  vals=[x['value'] for x in facts]
 else:
  schema='legacy';facts=body['facts']['us-gaap']['Revenues']['units']['USD'];vals=[x['val'] for x in facts]
 supplied={x['exact_span'] for x in inputs['evidence'].values() if x.get('title')==schema+' SEC fact row'}
 actual={json.dumps(x,sort_keys=True,separators=(',',':')) for x in facts}
 assert len(facts)==2 and actual==supplied and vals==[120,150]
 assert [(x['start'],x['end']) for x in facts]==[('2023-01-01','2023-12-31'),('2024-01-01','2024-12-31')]
 assert all(x['filed']=='2025-02-15' and x['form']=='10-K' for x in facts)
 assert public.date()==datetime.fromisoformat('2025-02-15').date()+timedelta(days=1)
 assert 150/120-1==.25==result['measurement']['value'] and result['measurement']['unit']=='fraction'
 assert result['measurement']['period']=={'start':'2024-01-01','end':'2024-12-31'} and result['measurement']['formula']=='current / comparable prior-year revenue - 1'
 assert result['signal_id']=='fixture_author_revenue_growth' and result['version']==1 and result['execution']['status']=='success' and result['state']['value']=='positive' and result['status']['coverage']=='sufficient' and result['evidence']['counter']==[]
 supporters=result['evidence']['supporting'];assert {x['exact_span'] for x in supporters}==supplied and len(supporters)==2
 assert all(x['timestamp']==doc['available_at'] and x['document_id']==f'author-{index}-0' for x in supporters)
 cases.append({'schema':schema,'passed':True,'model_document_id':doc['document_id'],'diagnostic_executor_document_id':f'author-{index}-0','issuer':'0000000001','source_type':'financials','unit':'USD','values':vals,'filed':'2025-02-15','published_and_available':doc['available_at'],'cutoff':fixture['as_of'],'actual_fact_literals':sorted(actual),'measurement':result['measurement'],'classification':result['state']})
assert {x['schema'] for x in cases}=={'legacy','typed'}
restorepath=D/'actual-completed-restore.json';restore=read(restorepath)
actualfiles={str(x.relative_to(P)):sha(x) for x in P.rglob('*') if x.is_file()}
def normalize(files):return {str(Path(k).relative_to(P)) if Path(k).is_absolute() else k:v for k,v in files.items()}
assert restore['exit_code']==0 and restore['all_bytes_equal'] and normalize(restore['before'])==normalize(restore['after'])==actualfiles
assert restore['stage_file_count']==len(actualfiles)==20 and restore['inboxes']==restore['receipts']==1 and restore['stdout']['restored_without_execution']
report={'verdict':'PASS_actual_first_answer_two_schema_fixture_authoring','fixed_schema_denominator':2,'schema_passes':2,'cases':cases,'request_hash':H,'receipt':receipt,'first_answers':1,'model_corrections':0,'mechanical_fixture_rewrites':False,'logical_reservation':reservation,'host_tokens':None,'host_cost':None,'frozen_bindings_verified':177,'completion_artifacts_verified':len(completion['artifacts']),'whole_stage_files_verified_against_root_restore':len(actualfiles),'request_schema_and_six_excerpt_content_exact':True,'private_expected_outcome_not_in_wire':True,'raw_cached_parsed_staged_loaded_tests_exact':True,'native_results_are_actual_persisted_not_reexecuted':True,'seed_formula_parameters_unchanged':True,'only_isolated_candidate_no_stable_publication':True,'restore':bind(restorepath),'source_bindings':{x:bind(P/x) for x in ['manifest.json','inputs.json','expectations.json','completion.json','loaded-candidate.json']},'probe':bind(__file__),'limitations':['One fresh exact-inbox role78 with synthetic facts; not full Mining/controller, new measurement implementation, stable publication, subsequent reuse, whole S5/MVP or independent benefit.','Strict timestamp-string equality in this diagnostic can reject equivalent Z/offset spellings; actual +00:00 inputs match, so this case is unaffected. No equivalent-timezone capability was tested or claimed.','Two successful native persisted results are independently audited by source facts/arithmetic/period/units; no validator/Signal execution/Store or formal resume was rerun.','Root performed one completed restore; this read-only comparison is not a second restore and does not establish OS-crash recovery.','A candidate origin string mining:controller identifies the reused staging API, not proof a full Mining cycle was executed.']}
p=D/'actual-independent-review.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('PASS actual role78;2/2schemas;177bindings;20restorefiles;',sha(p))
