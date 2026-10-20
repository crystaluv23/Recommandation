"""Read-only final artifacts, exact raw operations and consumer/restore audit."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,re,time
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
from stock_opportunity_agent.research.evolution_core import _mask_identity_values,_basic_info_projection_cards
from stock_opportunity_agent.research.basic_info_visibility import basic_info_source_index
ROOT=Path('/Users/l/Project/Recommandation');P=ROOT/'runs/diagnostics/reviewed_owned_partial_stage_20261020_v1'
OUT=ROOT/'runs/diagnostics/reviewed_owned_partial_preflight_20261020_v1/independent'
D=ROOT/'runs/diagnostics/reviewed_owned_partial_driver_20261020_v1'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for z in iter(lambda:f.read(1024*1024),b''):h.update(z)
 return h.hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
started=time.monotonic();m=read(P/'manifest.json');co=read(P/'completion.json');s=read(P/'inputs.json')['sample'];fc=read(P/'final-context.json');pred=read(P/'prediction.json')
assert digest({k:v for k,v in co.items() if k!='completion_hash'})==co['completion_hash']
assert co['manifest_hash']==m['manifest_hash']
paths={}
for b in m['originals']+m['code_files']:
 assert b['path'] not in paths or paths[b['path']]==b['sha256'];paths[b['path']]=b['sha256']
assert len(paths)==6264
for p,h in paths.items():assert sha(p)==h,p
excluded={'progress.json','completion.json','.stage.lock','exchange/.dispatch.lock'}
actual=[bind(p) for p in sorted(P.rglob('*')) if p.is_file() and p.relative_to(P).as_posix() not in excluded]
assert actual==co['immutable_artifacts'] and len(actual)==28
before=read(D/'completed-restore-before.json');after=read(D/'completed-restore-after.json');summary=read(D/'completed-restore-summary.json')
assert before==after and len(before['all_files_including_completion_progress_and_operational_locks'])==32
for b in before['all_files_including_completion_progress_and_operational_locks']:assert sha(b['path'])==b['sha256']
assert {x['path'] for x in before['all_files_including_completion_progress_and_operational_locks']}=={str(p) for p in P.rglob('*') if p.is_file()}
assert summary['restored_without_execution'] is True and summary['new_dispatches']==summary['new_requests']==summary['new_receipts']==summary['new_raws']==0
assert summary['restore_result']=={**co['result'],'restored_without_execution':True}
expected_counts={'requests':3,'inboxes':3,'raw_outboxes':3,'receipts':3,'parsed_cache':3}
assert summary['counts_before']==summary['counts_after']==expected_counts
sets=[{p.stem for p in (P/name).glob(glob)} for name,glob in [('requests','*.json'),('exchange/inbox','*.json'),('exchange/outbox','*.txt'),('exchange/receipts','*.json'),('cache/responses','*.json')]]
assert all(x==sets[0] for x in sets) and len(sets[0])==3
trace=[];payloads={};raws={};total=0
for request_path in (P/'requests').glob('*.json'):
 h=request_path.stem;r=read(request_path)['request'];assert digest(r)==h
 inbox=read(P/'exchange/inbox'/(h+'.json'));receipt=read(P/'exchange/receipts'/(h+'.json'));cache=read(P/'cache/responses'/(h+'.json'))
 rawpath=P/'exchange/outbox'/(h+'.txt');raw=json.loads(rawpath.read_text());raws[h]=raw
 assert inbox['request_hash']==receipt['request_hash']==cache['request_hash']==h and inbox['messages']==r['messages']
 assert receipt['inbox_sha256']==sha(P/'exchange/inbox'/(h+'.json')) and receipt['raw_output_sha256']==sha(rawpath)
 assert cache['raw_output']==rawpath.read_text() and cache['json_output']==raw
 reservation=len(json.dumps(r['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+r['max_output_tokens']
 assert cache['usage']['accounting_tokens']==reservation and cache['usage']['agent_id']==receipt['agent_id']
 assert cache['usage']['inbox_sha256']==receipt['inbox_sha256'] and cache['usage']['raw_output_sha256']==receipt['raw_output_sha256']
 assert cache['usage']['token_usage'] is None and cache['usage']['internal_agent_cost'] is None and cache['usage']['cost']==0
 assert reservation<=131072
 total+=reservation;payloads[h]=json.loads(r['messages'][1]['content'])
 assert s['company_id'] not in json.dumps(inbox) and s['identity']['ticker'] not in json.dumps(inbox)
 trace.append({'request_hash':h,'stage':r['stage'],'agent_id':receipt['agent_id'],'reservation':reservation,'raw_sha256':sha(rawpath)})
assert total==180233==co['result']['logical_reservation'] and total<512000
r1=read(P/'reflect.json');r2=read(P/'closure.json');h1=r1['request_hashes'][0];h2=r2['request_hashes'][0];hp=next(h for h in raws if h not in (h1,h2))
assert {x['agent_id'] for x in trace}=={'/root/role_66','/root/role_67','/root/role_68'}
assert raws[h2]['operations']==[{'op':'replace','path':'decision','value':'finalize'}]
# Replay only the authored JSON operations as a pure data comparison, not a role or parser invocation.
base=deepcopy(s['prior_state']);base['need_dispositions']=[]
for op in raws[h1]['operations']:
 if op['op']=='append':base[op['path']].append(deepcopy(op['value']))
 elif op['op']=='replace' and op['path']=='next_information_needs[4]':base['next_information_needs'][4]=op['value']
 else:raise AssertionError(('unexpected operation',op))
rows=base.pop('need_dispositions');assert base==r1['state']
assert [{k:v for k,v in x.items() if k!='prior_need'} for x in r1['metadata']['need_dispositions']['items']]==rows
assert r1['metadata']['need_dispositions']['prior_state_hash']==digest(s['prior_state'])
expected=deepcopy(base);expected['decision']='finalize';assert expected==r2['state']
assert r2['metadata']['need_dispositions']=={'items':[],'prior_state_hash':digest(base)}
residual=rows[0]['residual_need'];assert len(residual)<=300 and len(base['next_information_needs'])==5 and base['next_information_needs'].count(residual)==1
assert base['next_information_needs'][:4]==s['prior_state']['next_information_needs'][:4]
assert rows[0]['need_index']==4 and rows[0]['answer_scope']=='partial'
assert payloads[h1]['reflection_runtime']=={'must_finalize':False,'termination_trigger':None}
assert payloads[h2]['reflection_runtime']=={'must_finalize':True,'termination_trigger':'max_signal_rounds'} and payloads[h2]['executed_selection_intents']==[]
for h in (h1,h2):assert raws[h]['base_hash']==payloads[h]['output_patch_contract']['base_hash']
aliases=[s['company_id'],*s['identity']['identity_aliases']]
assert fc['final_research_state']==_mask_identity_values(expected,aliases)
assert fc==pred['final_context']==payloads[hp]['final_context']
assert fc['runtime_termination']=={'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':'max_signal_rounds'}
cards,counts=_basic_info_projection_cards(s['basic_info'])
expected_basic={'source_index':basic_info_source_index(s['basic_info']),'data_gaps':[r['data_gap'] for r in s['basic_info']['requests'] if isinstance(r.get('data_gap'),dict)],'projection_cards':cards,'projection_card_counts':counts}
assert fc['basic_info']==_mask_identity_values(expected_basic,aliases) and len(cards)==17
assert fc['prediction_baseline']==s['prediction_baseline'] and fc['computed_metrics']==s['computed_metrics']
assert fc['prediction_baseline']['mean_adjusted_close']==6.494 and fc['prediction_baseline']['doubling_threshold']==12.988 and fc['prediction_baseline']['recent_close']==6.3
assert fc['computed_metrics'][0]['values']['return_pct']==-16.6667
round_=fc['signal_rounds'][0];assert round_['selected_signals']==['financing_listing_action:v5','operating_cash_flow_margin:v2']
assert [r['execution']['status'] for r in round_['batch']['results']]==['success','domain_unavailable']
assert [r['state']['value'] for r in round_['batch']['results']]==['neutral','unavailable'] and len(fc['cited_signal_evidence'])==2
assert len(fc['state_evolution'])==2 and fc['state_evolution'][0]['need_dispositions']['items'][0]['residual_need']==residual and fc['state_evolution'][1]['need_dispositions']['items']==[]
expected_pred=deepcopy(raws[hp]);expected_pred['is_surge']=True;assert expected_pred==pred['prediction']
assert pred['prediction']['candidate_judgment']=='possible' and pred['prediction']['magnitude']=='2-3x' and pred['prediction']['confidence']=={'level':'low'}
assert co['result']['mirror_correction_branch']=='not_exercised' and co['result']['independent_receipts']==3
assert co['result']['actual_host_tokens'] is None and co['result']['actual_host_cost'] is None
assert co['result']['historical_seed_not_new_F6'] is True and co['result']['new_Signal_apply']==co['result']['labels_read']==co['result']['external_api_calls']==0
out={'mechanical_verdict':'PASS_exact_native_authored_outputs_and_consumers','semantic_verdict':'FAIL_one_later_compliance_facet','fixed_denominator':1,
 'frozen_unique_SHA_verified':6264,'native_immutable_files':28,'restore_all_files_current_verified':32,'restore_before_after_equal':True,
 'restore_new_dispatches':0,'completion_binding':bind(P/'completion.json'),'restore_summary_binding':bind(D/'completed-restore-summary.json'),
 'trace':sorted(trace,key=lambda r:r['agent_id']),'logical_reservation':total,'raw_to_accepted_exact':True,'correction_requests':0,
 'no_authored_output_salvage':'Reflect exact authored operations reproduce accepted state+row; closure only authored decision replace; Predictor exact raw fields retained with native derived is_surge only. Events are not persisted here, so event absence is not used as evidence.',
 'partial_residual':residual,'prior_needs0_3_exact':True,'one_residual_five_needs_no_duplicate':True,
 'final_context_equals_predictor_wire_and_sink':True,'BasicInfo17_cards_and_visibility_exact':True,'runtime_termination':fc['runtime_termination'],
 'historical_signal_refs':round_['selected_signals'],'prediction_authored':{k:pred['prediction'][k] for k in ('candidate_judgment','magnitude','confidence')},
 'missing_semantic_facet':'Oracle requires covenant terms AND compliance after the disclosed interim period. Authored residual and its unanswered reason list retain terms but do not retain later compliance. Predictor June30-not-Sep30 financing caveat does not restore the lost state need.',
 'elapsed_seconds':round(time.monotonic()-started,6),'scope':'Read-only files/stream SHA and pure JSON comparisons/presentation helpers. No Store/GET/LabelStore/prepare/resume/parser/model call. Historical batch only seed; no fresh F6 or accuracy/gain conclusion.'}
(OUT/'actual-stage-evidence.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
