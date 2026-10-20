"""Read terminal cases and use pure native models/assemblers only; no execution/store."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime
import hashlib,json,re,sys
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.evolution_core import InformationPlan,ResearchState,SignalRound,_assemble_final_context,_research_state_delta
from stock_opportunity_agent.research.evolution_research_validation import _unavailable_signal_state_errors,_validate_research_state_refs
from stock_opportunity_agent.research.repair import is_mechanical_issue
R=Path('/Users/l/Project/Recommandation'); O=R/'runs/diagnostics/reviewed_owned_temporal_preflight_20261021_v1';B=R/'runs/diagnostics/reviewed_owned_temporal_stage_20261021_v1'
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
bind=lambda p:{'path':str(Path(p).resolve()),'sha256':sha(p)}
def check_bind(row):assert sha(row['path'])==row['sha256'],row['path']
def apply(prior,operations):
 d=deepcopy(prior);rows=[]
 for op in operations:
  path=op['path']
  if path=='need_dispositions':rows.append(op['value']);continue
  m=re.fullmatch(r'(\w+)\[(\d+)\]',path)
  if m:
   key,index=m[1],int(m[2]);assert op['op'] in ('replace','remove')
   if op['op']=='replace':d[key][index]=op['value']
   else:d[key].pop(index)
  elif op['op']=='append':d[path].append(op['value'])
  elif op['op']=='replace':d[path]=op['value']
  else:raise AssertionError(op)
 return d,rows
oracle=O.parent/'owned_partial_three_controls_20261021_v1/expectations.json'
assert sha(oracle)=='a5d5d3049ce6efaa1bc2609824d277ed29d55e074160bd4c89d97617097714d8'
report={'scope':'actual terminal cases only; file reads + pure native parser/validator/assembler; no Store/network/models/labels/resume', 'oracle':bind(oracle),'cases':{},'harness_notes':['Exploratory reads corrected a missing hyphen in completed-restore-review filename and result version key; no product execution or passing conclusion came from those reads.']}
for sid in sys.argv[1:]:
 p=B/sid;assert (p/'completion.json').exists() and not (p/'failure.json').exists()
 sample=read(p/'inputs.json')['sample'];manifest=read(p/'manifest.json');completion=read(p/'completion.json');contract=read(p/'contract.json')
 assert digest({k:v for k,v in manifest.items() if k!='manifest_hash'})==manifest['manifest_hash']==completion['manifest_hash']
 assert digest({k:v for k,v in completion.items() if k!='completion_hash'})==completion['completion_hash']
 for row in manifest['code_files']+completion['immutable_artifacts']:check_bind(row)
 assert digest(read(p/'inputs.json'))==contract['input_hash'] and digest(read(p/'expectations.json'))==contract['expectations_hash']
 restore_path=O/'actual-execution'/sid/'completed-restore-review.json';restore=read(restore_path)
 actual={str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}
 assert restore['all_files_exactly_equal'] and restore['new_dispatches']==0 and restore['before']==restore['after']==actual and restore['files']==len(actual)
 trace=[];payloads={};raws={};reservation=0
 sets=[{f.stem for f in (p/sub).glob('*'+suffix)} for sub,suffix in [('requests','.json'),('exchange/inbox','.json'),('exchange/outbox','.txt'),('exchange/receipts','.json'),('cache/responses','.json')]]
 assert all(s==sets[0] for s in sets) and len(sets[0])==3
 for h in sorted(sets[0]):
  journal=read(p/'requests'/f'{h}.json');req=journal['request'];inbox=read(p/'exchange/inbox'/f'{h}.json');receipt=read(p/'exchange/receipts'/f'{h}.json');cache=read(p/'cache/responses'/f'{h}.json');rawpath=p/'exchange/outbox'/f'{h}.txt';raw=read(rawpath)
  assert journal['request_hash']==digest(req)==h==inbox['request_hash']==receipt['request_hash']==cache['request_hash']
  assert inbox['messages']==req['messages'] and inbox['max_output_tokens']==req['max_output_tokens']
  assert receipt['inbox_sha256']==sha(p/'exchange/inbox'/f'{h}.json')==cache['usage']['inbox_sha256']
  assert receipt['raw_output_sha256']==sha(rawpath)==cache['usage']['raw_output_sha256'] and receipt['agent_id']==cache['usage']['agent_id']
  assert cache['json_output']==raw and cache['raw_output']==rawpath.read_text()
  units=len(json.dumps(req['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+req['max_output_tokens'];assert units==cache['usage']['accounting_tokens']<=131072;reservation+=units
  payload=json.loads(req['messages'][1]['content']);payloads[h]=payload;raws[h]=raw
  assert not any(alias.casefold() in json.dumps(inbox['messages']).casefold() for alias in sample['identity']['identity_aliases'])
  trace.append({'request_hash':h,'stage':req['stage'],'receipt':receipt,'logical_reservation':units})
 assert reservation==completion['result']['logical_reservation'] and len({x['receipt']['agent_id'] for x in trace})==3
 first=read(p/'reflect.json');closure=read(p/'closure.json');context=read(p/'final-context.json');sink=read(p/'prediction.json')
 fh=first['request_hashes'];ch=closure['request_hashes'];assert len(fh)==len(ch)==1
 fraw=raws[fh[0]];fp=payloads[fh[0]];cp=payloads[ch[0]]
 assert 'basic_info' not in fp and 'document_channel' not in fp and fraw['base_hash']==fp['output_patch_contract']['base_hash']
 assert cp['reflection_runtime']['must_finalize'] and cp['reflection_runtime']['termination_trigger']=='max_signal_rounds' and not cp['executed_selection_intents']
 proposed,rows=apply(sample['prior_state'],fraw['operations']);prior=ResearchState.from_dict(sample['prior_state']);current=ResearchState.from_dict(proposed)
 roundrow=SignalRound.from_dict({'information_needs':list(prior.next_information_needs),'selections':sample['selections'],'batch':{'results':sample['results'],'signal_calls':2}})
 dropped=_unavailable_signal_state_errors(prior,current,roundrow.batch);issues=[]
 try:_validate_research_state_refs(current,phase='reflect',previous_state=prior,batch=roundrow.batch,selections=roundrow.selections,need_dispositions=rows,evaluation_context={'prediction_time':sample['prediction_time']})
 except StructuredValidationError as exc:
  for issue in exc.issues:
   if issue.code=='unavailable_signal_treated_as_finding':
    assert is_mechanical_issue(issue);issues.append({'code':issue.code,'paths':list(issue.paths),'allowed_repairs':list(issue.allowed_repairs),'repair_context':dict(issue.repair_context)})
 for item in dropped:proposed[item['field']].remove(item['text'])
 assert proposed==first['state'],sid+' raw→accepted discrepancy beyond identified mechanical drop'
 assert len(issues)==len(dropped)
 assert first['metadata']['need_dispositions']['prior_state_hash']==digest(sample['prior_state'])
 assert [{k:v for k,v in row.items() if k!='prior_need'} for row in first['metadata']['need_dispositions']['items']]==rows
 assert first['state']['next_information_needs'][:4]==sample['prior_state']['next_information_needs'][:4]
 assert {**first['state'],'decision':'finalize'}==closure['state'] and not closure['metadata']['need_dispositions']['items']
 deltas=[{'round':1,'delta':_research_state_delta(prior,ResearchState.from_dict(first['state'])),'need_dispositions':first['metadata']['need_dispositions']},{'round':1,'delta':_research_state_delta(ResearchState.from_dict(first['state']),ResearchState.from_dict(closure['state'])),'need_dispositions':closure['metadata']['need_dispositions']}]
 rebuilt=_assemble_final_context(plan=InformationPlan.from_dict(sample['plan']),company_id=sample['company_id'],additional_identity_aliases=tuple(sample['identity']['identity_aliases']),basic_info=sample['basic_info'],state=ResearchState.from_dict(closure['state']),rounds=(roundrow,),prediction_time=datetime.fromisoformat(sample['prediction_time']),prediction_baseline=sample['prediction_baseline'],computed_metrics=sample['computed_metrics'],state_deltas=tuple(deltas),signal_research_status=sample['signal_research_status'],runtime_termination={'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':'max_signal_rounds'})
 assert digest(rebuilt)==digest(context)==digest(sink['final_context'])
 ph=next(h for h,payload in payloads.items() if 'final_context' in payload);assert payloads[ph]['final_context']==context
 assert {**raws[ph],'is_surge':False}==sink['prediction']
 assert context['basic_info']['projection_card_counts']['included_cards']==len(context['basic_info']['projection_cards'])==17
 assert context['prediction_baseline']==sample['prediction_baseline'];assert context['prediction_baseline']['mean_adjusted_close']==6.494 and context['prediction_baseline']['doubling_threshold']==12.988
 assert context['computed_metrics']==sample['computed_metrics'] and context['computed_metrics'][0]['values']['return_pct']==-16.6667
 assert [r.ref for r in roundrow.batch.results]==['financing_listing_action:v5','operating_cash_flow_margin:v2']
 docpath=R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/0001.json';doc=read(docpath)
 evidence=[]
 for op in fraw['operations']:
  if op['path']!='supporting_evidence':continue
  v=op['value'];assert v['signal_ref']=='financing_listing_action:v5' and v['evidence_group']=='counter';e=sample['results'][0]['evidence']['counter'][v['evidence_index']]
  assert e['exact_span'] in doc['content'] and e['timestamp']==doc['available_at'] and datetime.fromisoformat(e['timestamp'])<=datetime.fromisoformat(sample['prediction_time'])
  evidence.append({'reference':v,'original_evidence':e})
 row=rows[0];assert row['need_index']==4 and row['answer_scope']==('full' if sid=='p03' else 'partial')
 if sid!='p03':assert row['residual_need']==first['state']['next_information_needs'][4] and len(first['state']['next_information_needs'])==5 and len(set(first['state']['next_information_needs']))==5
 else:assert row['residual_need'] is None and first['state']['next_information_needs']==sample['prior_state']['next_information_needs'][:4]
 report['cases'][sid]={'target_semantic_verdict':'PASS_proper_partial' if sid!='p03' else 'PASS_full','fixed_case_denominator':1,'manifest_hash':manifest['manifest_hash'],'code_files_current_verified':len(manifest['code_files']),'immutable_verified':len(completion['immutable_artifacts']),'restore':{'binding':bind(restore_path),'all_current_before_after_sha_equal':True,'files':len(actual),'new_dispatches':0},'trace':trace,'first_answers':3,'model_corrections':0,'logical_reservation':reservation,'reflect_raw_operations':len(fraw['operations']),'residual':row['residual_need'],'reason':row['reason'],'prior_0_3_exact_occurrences':True,'need_count':len(first['state']['next_information_needs']),'adopted_evidence':evidence,'source_body':bind(docpath),'closure_empty_owner_decision_only':True,'pure_native_reassembly_equals_final_wire_and_sink':True,'basic_info_cards':17,'basic_info_visibility':context['basic_info']['source_index'],'prediction':sink['prediction'],'mirror':'not_exercised','ancillary_mechanical_belief_drop':{'errors':dropped,'typed_mechanical_issues':issues,'raw_minus_identified_drop_equals_accepted':True,'semantic_interpretation':'False positive: explicit unresolved coverage and negation of economic absence is removed by topic-token + marker matching without negation semantics.' if dropped else 'No such ancillary drop in this case.'},'bindings':{name:bind(p/name) for name in ['manifest.json','inputs.json','reflect.json','closure.json','final-context.json','prediction.json','completion.json']}}
 print(sid,'PASS target; identified mechanical drops',len(dropped),'restorefiles',len(actual),'logical',reservation,flush=True)
report['semantic_assessments']={
 'p01':{'passed':True,'scope':'Proper partial, not unanswered fallback. Two historical financing spans answer bounded context while all seven umbrella residual facets remain explicit.','retained_facets':['operating cash flow','capex','debt balances and maturities','covenant terms AND compliance after June 30 through prediction time','tax-related cash obligations','prospective equity dilution','direct annual-report coverage unverified'],'period_and_units':'June 30/H1 observations, $50.1 million repurchase authorization distinct from $50.0 million revolving availability. Historical retirement does not answer prospective dilution.'},
 'p02':{'passed':True,'scope':'H1 compliance is answered; financial covenant terms and compliance after June 30 through cutoff remain separate unknowns. Later public availability is expressly not extended observation coverage.','residual_not_old_umbrella':True},
 'p03':{'passed':True,'scope':'Requested revolver availability at June 30 ($50.0 million) and compliance during the six months then ended are literally established by counter[3]. Full resolves only that narrow need, without requiring unrequested covenant terms or post-June coverage.','prior_routing_partial_not_actual_coverage_ceiling':True},
 'prediction_consumers':{'scope':'All three unlikely/medium/null first answers distinguish historical disclosures from cutoff conditions and neutral financing state from stock direction. OCF domain unavailability is retained as coverage, not economic absence or technical failure. No accuracy/benefit conclusion or labels used.'},
 'auxiliary_p01':{'target_semantic_pass_independent':True,'open_defect':'Token-set unavailable-topic guard removes an honest mixed belief containing insufficiency plus negation of economic absence; helper reproduced exact raw text, typed mechanical remove authority, and exact accepted difference. No model correction repairs or authors this deletion.'}}
report['completed_target_cases']=list(report['cases'])
report['target_passes_over_fixed_denominator']={'passed':len(report['cases']),'fixed_denominator':3}
report['physical_fresh_roles']=sum(len(x['trace']) for x in report['cases'].values())
report['total_logical_reservation']=sum(x['logical_reservation'] for x in report['cases'].values())
report['audit_bindings']={'script':bind(__file__)}
report['limitations']=['Target case semantic pass is separate from ancillary belief-drop defect; no whole F7/MVP closure.','Historical seed Signal batch is not fresh F6; no new Signal application.','Raw operations are not all persisted in p01: one mechanically removed belief is explicitly accounted for.','17 cards are final/Predictor-visible, not Reflect-visible. Source context remains partial with omissions.','Mirror correction not exercised; no accuracy, independent gain or host token/cost claim.','Snapshot/reopen and exact completed restore do not establish OS-crash recovery.','Old fresh p01 semantic 0/1 remains unchanged; these new controls retain their fixed denominator3.']
path=O/'actual-review.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('REVIEW',sha(path))
