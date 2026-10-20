"""Bounded pure/temp control-set/authority/budget/semantic-feasibility review."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime
from unittest.mock import patch
import ast,hashlib,json,sys,tempfile,types
import run_reviewed_owned_partial_stage as s
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState,SignalRound,RuntimeBudgetExceeded
from stock_opportunity_agent.research.evolution_research_validation import validate_need_dispositions
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/reviewed_owned_temporal_preflight_20261021_v1';ORACLE=R/'runs/diagnostics/owned_partial_three_controls_20261021_v1/expectations.json';REVIEW=ORACLE.with_name('oracle-review.json')
read=lambda p:json.loads(Path(p).read_text())
b=lambda p:{'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
expected_sources={'scripts/run_reviewed_owned_partial_stage.py':'01c058eb996805c86bc12e1e27b4005b82d0ab19e5b8f7c517d5544c59001d16','spec/scripts/run_reviewed_owned_partial_stage.md':'17cecbe427230c0ab6a189f9b79709e41d85bb79daffb697b7089438eb7fce47','tests/test_reviewed_owned_partial_stage.py':'d60c9abf14ed0cbe0566341f8dececdae7d996c972b33cccb33e9fd125e87d12'}
for p,h in expected_sources.items():assert b(R/p)['sha256']==h
assert b(ORACLE)['sha256']=='a5d5d3049ce6efaa1bc2609824d277ed29d55e074160bd4c89d97617097714d8'
e=read(ORACLE);gold=read(REVIEW);controls=[]
for case in s.CONTROL_NEEDS:
 result=s._control_set(e,Path(e['stage_roots'][case]),case,s.CAPTURE_SOURCE_PROFILE,s.CAPTURE_SOURCE_COMMIT)
 assert result['total_limits']=={'max_local_calls':18,'max_case_tokens':1536000}
 controls.append({'case':'fixed_root_positive_'+case,'accepted':True})
oldpath=O/'driver/pre-fixed-root-original.py';oldcounter=read(O/'driver/rename-original-counterexample.json')
assert b(oldpath)['sha256']==oldcounter['source_sha256']=='939a3c80cda3f4e4621255cbcc26a22f6569bd9853ee896e788039ade31d8e25'
old=types.ModuleType('_independent_owned_temporal_before_fixedroot');old.__file__=s.__file__;sys.modules[old.__name__]=old;exec(compile(oldpath.read_text(),str(oldpath),'exec'),old.__dict__)
renamed=oldcounter['coherent_renamed_oracle'];root=Path(renamed['stage_roots']['p01'])
assert old._control_set(renamed,root,'p01',old.CAPTURE_SOURCE_PROFILE,old.CAPTURE_SOURCE_COMMIT)['stage_roots']==renamed['stage_roots']
try:s._control_set(renamed,root,'p01',s.CAPTURE_SOURCE_PROFILE,s.CAPTURE_SOURCE_COMMIT)
except ValidationError:pass
else:raise AssertionError('Coherent rename still resets budget')
controls.append({'case':'same_original_coherent_rename','original_accepted':True,'current_accepted':False})
mutations={
 'wrong_profile':lambda x:x.update(profile='owned_partial_historical_seed'),
 'missing_case':lambda x:x['stage_roots'].pop('p03'),
 'duplicate_root':lambda x:x['stage_roots'].update(p02=x['stage_roots']['p01']),
 'changed_question':lambda x:x['questions'].update(p01='A different question?'),
 'case_calls7':lambda x:x['limits'].update(max_local_calls=7),
 'case_tokens_more':lambda x:x['limits'].update(max_case_tokens=512001),
 'perrequest_more':lambda x:x['limits'].update(max_request_tokens=131073),
 'reserve_changed':lambda x:x['limits'].update(finalization_reserve=0),
 'total_calls19':lambda x:x['total_limits'].update(max_local_calls=19),
 'total_tokens_more':lambda x:x['total_limits'].update(max_case_tokens=1536001),
 'denominator_true':lambda x:x.update(fixed_denominator=True),
 'denominator1':lambda x:x.update(fixed_denominator=1),
}
for label,mutate in mutations.items():
 wrong=deepcopy(e);mutate(wrong)
 try:s._control_set(wrong,Path(e['stage_roots']['p01']),'p01',s.CAPTURE_SOURCE_PROFILE,s.CAPTURE_SOURCE_COMMIT)
 except ValidationError:pass
 else:raise AssertionError(label)
 controls.append({'case':label,'rejected':True})
for label,root,case,profile,commit in [
 ('case_root_mismatch',Path(e['stage_roots']['p01']),'p02',s.CAPTURE_SOURCE_PROFILE,s.CAPTURE_SOURCE_COMMIT),
 ('unknown_case',Path(e['stage_roots']['p01']),'p04',s.CAPTURE_SOURCE_PROFILE,s.CAPTURE_SOURCE_COMMIT),
 ('wrong_sourceprofile',Path(e['stage_roots']['p01']),'p01','wrong',s.CAPTURE_SOURCE_COMMIT),
 ('omitted_sourceprofile',Path(e['stage_roots']['p01']),'p01',None,s.CAPTURE_SOURCE_COMMIT),
 ('wrong_sourcecommit',Path(e['stage_roots']['p01']),'p01',s.CAPTURE_SOURCE_PROFILE,'a'*40)]:
 try:s._control_set(e,root,case,profile,commit)
 except ValidationError:pass
 else:raise AssertionError(label)
 controls.append({'case':label,'rejected':True})
try:s._capture_source(Path('/must-not-be-read'), 'a'*40)
except ValidationError:pass
else:raise AssertionError('Arbitrary historical commit accepted')
controls.append({'case':'capture_wrong_commit_pre_read','rejected':True})
# Loader logic exactly equals the already actual-read version: no second116/source scan.
def fn(text,name):return next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name==name)
assert ast.dump(fn(oldpath.read_text(),'_capture_source'),include_attributes=False)==ast.dump(fn(Path(s.__file__).read_text(),'_capture_source'),include_attributes=False)
with tempfile.TemporaryDirectory(prefix='independent-owned-temporal-') as tmp:
 tmp=Path(tmp).resolve();wrong=deepcopy(e);wrong['stage_roots']={k:str(tmp/'stages'/k) for k in s.CONTROL_NEEDS};op=tmp/'oracle.json';op.write_text(json.dumps(wrong))
 with patch.object(s,'CONTROL_STAGE_ROOT',tmp/'stages'),patch.object(s,'_seed',side_effect=AssertionError('seed must not run')):
  try:s.prepare(Path(wrong['stage_roots']['p01']),op,tmp/'not-read.json','b'*40,sample_id='p01',source_profile=s.CAPTURE_SOURCE_PROFILE,source_commit=s.CAPTURE_SOURCE_COMMIT)
  except ValidationError:pass
  else:raise AssertionError('Wrong seed commit accepted')
 assert not (tmp/'stages').exists()
 controls.append({'case':'wrong_seed_commit_rejected_before_seed_or_stage_write','rejected':True})
 # Native request_ready counter, using only temp request journals; no transport.
 def journal(name,stage,output):
  p=tmp/name;p.write_text(json.dumps({'request':{'stage':stage,'messages':[{'role':'user','content':'fixture'}],'max_output_tokens':output}}));return {'event_type':'request_ready','request_path':str(p)}
 budget=s._Budget({'limits':s.LIMITS});small=journal('small.json','blind_predictor_predict',1000)
 for _ in range(6):budget(small)
 try:budget(small)
 except RuntimeBudgetExceeded:pass
 else:raise AssertionError('Seventh request accepted')
 assert budget.calls==6
 oversize=journal('oversize.json','blind_predictor_predict',131073)
 try:s._Budget({'limits':s.LIMITS})(oversize)
 except RuntimeBudgetExceeded:pass
 else:raise AssertionError('Oversize accepted')
 tokens=s._Budget({'limits':s.LIMITS});large=journal('large.json','blind_predictor_predict',100000)
 for _ in range(5):tokens(large)
 try:tokens(large)
 except RuntimeBudgetExceeded:pass
 else:raise AssertionError('Case token ceiling exceeded')
 controls.append({'case':'native_budget6calls_perrequest131072_case512k','rejected_excesses':3})
# Proper partial/full are mechanically feasible from actual old accepted evidence;
# this creates no role answer and the private witness is never sent to transport.
p=R/'runs/diagnostics/reviewed_owned_partial_stage_20261020_v1';sample=read(p/'inputs.json')['sample'];saved=read(p/'reflect.json')
feasibility=[]
for case in s.CONTROL_NEEDS:
 prior_dict=deepcopy(sample['prior_state']);prior_dict['next_information_needs'][4]=s.CONTROL_NEEDS[case];prior=ResearchState.from_dict(prior_dict)
 round_=SignalRound.from_dict({'information_needs':list(prior.next_information_needs),'selections':sample['selections'],'batch':{'results':sample['results'],'signal_calls':2}})
 state_dict=deepcopy(saved['state']);row={k:v for k,v in saved['metadata']['need_dispositions']['items'][0].items() if k!='prior_need'}
 if case=='p03':scope='full';residual=None;state_dict['next_information_needs']=list(prior.next_information_needs[:4])
 else:
  scope='partial';residual=(gold['contract_feasibility']['private_feasibility_witness'] if case=='p01' else 'By prediction time, what financial covenant terms and compliance after June 30, 2025 had been disclosed?')
  state_dict['next_information_needs']=list(prior.next_information_needs[:4])+[residual]
 row.update(answer_scope=scope,residual_need=residual)
 valid=validate_need_dispositions([row],previous_state=prior,state=ResearchState.from_dict(state_dict),selections=round_.selections,batch=round_.batch,evaluation_context={'prediction_time':sample['prediction_time']})
 assert valid and valid[0]['answer_scope']==scope
 feasibility.append({'case':case,'routing_scope':'partial','native_actual_disposition_scope_accepted':scope,'private_witness_not_in_role_request':True,'scope':'Mechanical feasibility only; future actual model answer still independently judged.'})
for p,h in expected_sources.items():assert b(R/p)['sha256']==h
out={'verdict':'PASS_bounded_three_control_prefreeze_review','stable_sources':[b(R/p) for p in expected_sources],'oracle':b(ORACLE),'oracle_review':b(REVIEW),'controls':controls,'feasibility':feasibility,'original_rename_source':b(oldpath),'original_rename_evidence':b(O/'driver/rename-original-counterexample.json'),
 'native_capture_loader_initial_read':{'passed':True,'historical_commit':s.CAPTURE_SOURCE_COMMIT,'historical_code_bindings':116,'data_source_bindings_returned':7660,'four_current_drift_paths_not_in_data_current_checks':True,'final_loader_AST_exact_original_read_logic':True,'note':'One actual source loader read was completed during preflight before final code binding additions; current loader function AST is identical. No repeated5869 source scan or Store call.'},
 'semantic_limits':['p01 and p02 require proper partial, p03 requires full based on literal counter[3]; unanswered can be safe but is not capability success. Original p01 semantic0/1 remains unchanged.','Reflect actual visible input is prior6quotes plus2Signals/4financingcounter spans, not17 BasicInfo cards. Those17 belong to finalcontext/Predictor preservation.','No new routing, H_init, F6 or model compliance has been tested; no forced long residual or fresh mirror correction.','Three fixed roots keep percase6/512k and aggregate18/1536k; no arbitrarysourcecommit/legacy profile route or coherent oracle/root rename accepted.','Temporary native validator witnesses only establish legal representation, not a suggested model answer. Oracle/private witness remains separate from actual inputs.'],
 'forbidden_activity':{'formal_prepare_resume_role_dispatch':0,'GET_Store_Signalapply_labels':0,'production_or_frozen_edits':0},'audit_script':b(__file__)}
(O/'independent-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'verdict':out['verdict'],'controls':len(controls),'feasibility':feasibility,'review':b(O/'independent-review.json')},indent=2))
