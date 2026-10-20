"""Audit authorized committed artifacts using standard library; never run Slow."""
from pathlib import Path
import json,hashlib,collections,ast
ROOT=Path('/Users/l/Project/Recommandation');RUN=ROOT/'runs/cold_start/minimal_rounds_v182_integrated';OUT=ROOT/'runs/diagnostics/reviewed_slow_history_export_20261021_v1/oracle'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
canonical=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
reads={}
def read(p):
 p=Path(p).resolve();assert '/round-0002/' not in str(p) and '/LockedTest/' not in str(p) and '/labels' not in str(p)
 reads[str(p)]=sha(p);return json.loads(p.read_text())
state=read(RUN/'state.json');cycle=read(RUN/'cycle_state.json');contract=read(RUN/'run_contract.json');manifest=read(RUN/'slow_history/manifest.json')
assert canonical(contract['contract'])==contract['contract_hash']==cycle['run_contract_hash']
assert canonical(manifest['manifest'])==manifest['manifest_hash']==contract['contract']['slow_history_manifest_hash']
assert contract['contract']['locked_test_accessed'] is False
assert state['last_completed_round']==cycle['last_completed_round']==cycle['last_completed_cycle']==1 and cycle['active_cycle'] is None
checkpoint=read(Path(state['checkpoint_ref']));assert checkpoint['round_id']==1 and checkpoint['run_contract_hash']==contract['contract_hash']
meta=read(Path(checkpoint['meta_ref']));assert meta['round_id']==1
M=manifest['manifest'];namespace=M['source_namespace'];imported=[]
for binding in M['cycle_artifacts']:
 path=RUN/'slow_history'/namespace/binding['path'];assert sha(path)==binding['sha256'];read(path);imported.append({'path':str(path.resolve()),'sha256':binding['sha256']})
local={name:read(RUN/'experiments/cycles/cycle-0001'/name) for name in ('slow_input.json','slow_memory.json','slow_experiments.json','slow_loop_validation.json','slow_loop_result.json')}
i=local['slow_input.json'];mem=local['slow_memory.json'];assert i['contract_hash']==mem['contract_hash']==contract['contract_hash']
assert i['feedback_hash']==canonical({'feedback_rows':i['feedback_rows']})
refs=[row['feedback_ref'] for row in i['feedback_rows']];assert len(refs)==len(set(refs))==3518
assert set(mem['pending_feedback_refs'])==set(refs) and not mem['processed_feedback_refs'] and mem['status']=='failed'
assert len(mem['pending_feedback_refs'])==3518
assert {r['ref'] for r in i['source_manifest']}==set(refs)
# Verify each row's bound original payload, without executing its producer.
byref={r['feedback_ref']:r for r in i['feedback_rows']}
for entry in i['source_manifest']:
 row=byref[entry['ref']];assert entry['content_hash']==canonical(row.get('event',row.get('artifact'))),entry['ref']
plan_evidence=[];failures=[];gaps=[];domain=[];needs=[];knowledge=[]
for planid in checkpoint['plan_ids']:
 path=RUN/'plans'/planid/'record.json';record=read(path);assert record['round_id']==1 and record['plan_id']==planid
 assert record['case_ids']==[t['case_id'] for t in record['trajectories']]
 assert next(x for x in meta['plan_reflections'] if x['plan_id']==planid)['plan']==record['plan']
 digest=canonical(record);kp=RUN/'knowledge/observations'/f'{digest}.json';k=read(kp)
 assert k['record_hash']==digest and k['plan_id']==planid and k['round_id']==1 and k['contract_hash']==contract['contract_hash']
 assert len(k['rows'])==len(record['trajectories'])==24
 knowledge.append({'path':str(kp),'plan_id':planid,'record_hash':digest,'rows':len(k['rows']),'authored_experience_refs':record['plan'].get('experience_usage'),'meaning':'Declared exact-reference exposure/adoption derivative only; not independent benefit or proof of use-caused correctness.'})
 counts=collections.Counter()
 for ti,t in enumerate(record['trajectories']):
  base=f'/trajectories/{ti}'
  for qi,request in enumerate(t['basic_info_bundle']['requests']):
   if request.get('data_gap'):gaps.append({'path':str(path),'json_locator':base+f'/basic_info_bundle/requests/{qi}/data_gap','case_id':t['case_id'],'plan_id':planid,'source':request['data_gap']})
  for si,s in enumerate(t['signal_rounds']):
   for ri,result in enumerate(s['batch']['results']):
    execution=result['execution']['status'];counts[execution]+=1
    rec={'path':str(path),'json_locator':base+f'/signal_rounds/{si}/batch/results/{ri}','case_id':t['case_id'],'plan_id':planid,'signal_ref':result['signal_id']+':v'+str(result['version']),'source':result}
    if execution=='validation_failed':failures.append(rec)
    elif execution=='domain_unavailable':domain.append(rec)
  for ni,need in enumerate(t['final_state']['next_information_needs']):
   if 'book-to-bill' in need.casefold() or 'consensus' in need.casefold():needs.append({'path':str(path),'json_locator':base+f'/final_state/next_information_needs/{ni}','case_id':t['case_id'],'plan_id':planid,'need':need})
 plan_evidence.append({'plan_id':planid,'path':str(path),'record_hash':digest,'case_count':24,'unique_case_ids':len(set(record['case_ids'])),'signal_result_execution_counts':dict(counts),'unresolved_need_count':sum(len(t['final_state']['next_information_needs']) for t in record['trajectories']),'magnitude_diagnostics':next(x for x in meta['plan_reflections'] if x['plan_id']==planid)['magnitude_diagnostics']})
assert len(failures)==6 and len(gaps)==4 and len({x['case_id'] for x in gaps})==2
# Keep source versions and complete locators; do not recast source text as economic truth.
(OUT/'source-evidence.json').write_text(json.dumps({'status':'preflight_original_material_only','committed_plans':plan_evidence,'signal_validation_failures':failures,'provider_gaps':gaps,'domain_unavailable_examples':domain[:2],'new_measurement_need_candidates':needs,'knowledge_references':knowledge,'historical_slow_failure':{'path':str(RUN/'experiments/cycles/cycle-0001/slow_memory.json'),'status':mem['status'],'failure_ref':mem['failure_ref'],'processed':0,'pending':3518,'selected_refs':mem['model_view_manifest']['included_refs'],'included_count':mem['model_view_manifest']['included_count'],'deferred_count':mem['model_view_manifest']['deferred_count']},'approved_import':{'manifest_hash':manifest['manifest_hash'],'namespace':namespace,'committed_fast_round':M['committed_fast_round'],'committed_slow_cycle':M['committed_slow_cycle'],'cycle_artifacts':imported,'imported_fast_meta_entries':len(M['fast_context']['meta_entries']),'capability_backlog':{'open_count':M['fast_context']['capability_backlog_seed']['open_count'],'ordinary_items':len(M['fast_context']['capability_backlog_seed']['items']),'signal_need_items':len(M['fast_context']['capability_backlog_seed']['signal_need_items'])}},'denominator':{'feedback_units':len(refs),'kind_counts':dict(collections.Counter(r['kind'] for r in i['feedback_rows'])),'feedback_hash':i['feedback_hash'],'sorted_ref_set_hash':canonical(sorted(refs)),'processed_ref_set_hash':canonical(sorted(mem['processed_feedback_refs'])),'pending_ref_set_hash':canonical(sorted(mem['pending_feedback_refs'])),'source_manifest_count':len(i['source_manifest']),'note':'This is the historical committed cycle1 universe. The not-yet-executed new export/input may add the newly imported local cycle units; its own denominator must be derived/frozen from actual export, never guessed as3518 or reduced to3 selected items.'}},ensure_ascii=False,indent=2)+'\n')
codefiles=['research/evolution_control.py','research/signal_evolution.py','research/evolution_signal_roles.py','research/mining_controller.py','research/plan_evolution.py','memory/knowledge.py']
codebase=ROOT/'src/stock_opportunity_agent'
for p in [codebase/f for f in codefiles]:reads[str(p)]=sha(p)
for p in [ROOT/'spec/engineering-mvp.md',ROOT/'spec/src/stock_opportunity_agent/research/signal_evolution.md',ROOT/'spec/src/stock_opportunity_agent/research/evolution_reflection_memory.md']:reads[str(p)]=sha(p)
for path,expected in reads.items():assert sha(path)==expected,path
(OUT/'read-bindings.json').write_text(json.dumps({'status':'preflight_verified_before_after','bindings':[{'path':p,'sha256':h} for p,h in sorted(reads.items())],'product_imports':0,'Slow_executions':0,'model_calls':0,'GET':0,'global_LabelStore_reads':0,'LockedTest_reads':0,'round2_reads':0,'source_mutations':0},indent=2)+'\n')
print(json.dumps({'status':'preflight','source_bindings':len(reads),'feedback_denominator':len(refs),'processed':0,'pending':3518,'Signal_technical_failures':len(failures),'provider_gap_occurrences':len(gaps),'distinct_provider_gap_cases':len({x['case_id'] for x in gaps}),'new_need_candidates':len(needs)}))
