"""Independent zero-answer Posthoc wire/restore probes; no full archive reads."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,tempfile,shutil
import run_reviewed_posthoc_stage as stage
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_core import BlindPrediction,GroundTruth,candidate_judgment_feedback,magnitude_feedback
from scripts.replay_incremental_reflection_memory import deny_network
REPO=Path('/Users/l/Project/Recommandation'); OUT=Path(__file__).resolve().parent
parent=REPO/'runs/diagnostics/reviewed_fast_prefix_20261019_v2'
wirefile=OUT.parent/'actual-pending-inbox.json'; wire=json.loads(wirefile.read_text());payload=json.loads(wire['messages'][-1]['content'])
saved=json.loads((parent/'prediction.json').read_text());oracle=json.loads((REPO/'reports/reviewed-posthoc-stage-expectations-20261020.json').read_text())
checks=[]
def test(name,fn):
 try:value=fn();checks.append({'case':name,'pass':True,'result':value})
 except Exception as e:checks.append({'case':name,'pass':False,'error_type':type(e).__name__,'error':str(e)})
def assertion(value):assert value;return True
def reject(fn):
 try:fn()
 except Exception as e:return {'rejected':True,'error_type':type(e).__name__,'error':str(e)[:220]}
 raise AssertionError('Expected fail-closed rejection')
def sourcebinding(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
with deny_network() as net:
 test('parent_prediction_exact_before_truth',lambda:assertion(sourcebinding(parent/'prediction.json')['sha256']==oracle['parent']['prediction_sha256']))
 test('inbox_identity_matches_driver_pending',lambda:assertion(wire['request_hash']==json.loads((OUT.parent/'preflight-result.json').read_text())['temporary_prepare_and_actual_native_pending']['pending'][0]['request_hash']))
 test('compact_context_exact_native_projection',lambda:assertion(payload['compact_context']==_compact_posthoc_context(saved['final_context'])))
 test('original_prediction_exact',lambda:assertion(payload['original_prediction']==saved['prediction']))
 pred=BlindPrediction.from_dict(saved['prediction']); truth=GroundTruth.from_dict(payload['revealed_ground_truth'])
 test('native_deterministic_feedback',lambda:assertion(payload['candidate_judgment_feedback']==candidate_judgment_feedback(pred,truth) and payload['magnitude_feedback']==magnitude_feedback(pred,truth) and payload['framework_prediction_correct']==(pred.is_surge==truth.is_surge and (not truth.is_surge or pred.magnitude is truth.magnitude))))
 context=payload['compact_context'];state=context['final_research_state'];baseline=context['prediction_baseline']
 test('four_needs_retained_exact',lambda:assertion(len(state['next_information_needs'])==4 and state['next_information_needs']==saved['final_context']['final_research_state']['next_information_needs']))
 test('two_technical_budget_gaps_and_runtime_trigger',lambda:assertion(len(context['signal_results'])==2 and all(x['execution']['status']=='budget_blocked' and x['state']['value']=='unavailable' and not any(x['evidence'].values()) for x in context['signal_results']) and context['runtime_termination']=={'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':'budget_exhausted'}))
 test('market_anchor_and_distinct_periods',lambda:assertion(baseline['mean_adjusted_close']==6.494 and baseline['recent_close']==6.3 and baseline['doubling_threshold']==12.988 and context['computed_metrics'][0]['values']['window_trading_days']==180 and context['computed_metrics'][0]['params']['window_days']==180))
 idx=context['basic_info_source_index']; filing=next(x for x in idx if x['request_id']=='recent_annual_filing')
 test('partial_18_of_23_and_gap_index',lambda:assertion(filing['visible_projection_count']==18 and filing['available_projection_count']==23 and filing['source_context_truncated'] and filing['projection_context_truncated'] and filing['effective_context_truncated'] and len(context['data_gaps'])==2))
 catalog=payload['source_catalog'];cat=catalog[0]
 test('canonical_case_catalog_legal_scope_and_outcome',lambda:assertion(len(catalog)==1 and cat['source_kind']=='canonical_case_facts' and cat['canonical_outcomes']=={'binary':True,'magnitude':None,'technical_exclusion':False} and len(cat['case_refs'])==1 and not cat['plan_refs'] and cat['source_ref'].startswith('reflection_source:')))
 aliases=json.loads((parent/'inputs.json').read_text())['sample']['identity']['identity_aliases']
 test('whole_wire_anonymous',lambda:assertion(all(a.lower() not in wirefile.read_text().lower() for a in aliases)))
 reservation=len(json.dumps(wire['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+wire['max_output_tokens']
 test('input_plus_output_reservation_below_131072',lambda:assertion(reservation<=131072 and wire['max_output_tokens']==8000))
 test('actual_completed_parent_and_historical_code_verified',lambda: {'manifest_hash':stage._parent_snapshot(parent,stage.PARENT_COMMIT)['manifest_hash']})
 test('historical_commit_not_full_SHA_rejected',lambda:reject(lambda:stage._historical_code_check([],stage.PARENT_COMMIT[:8])))
 test('historical_code_binding_tamper_rejected',lambda:reject(lambda:stage._historical_code_check([{'path':str(REPO/'scripts/run_reviewed_fast_prefix.py'),'sha256':'0'*64}],stage.PARENT_COMMIT)))
 # Restore unit fixture uses only exact already-reviewed parent responses; never submits answers.
 for name,mut,rebind,expected in [('legal_three_answered_two_journal_only',None,False,'accept'),('raw_changed',lambda r:(next((r/'exchange/outbox').glob('*.txt'))).write_text('{}'),True,'reject'),('receipt_changed',lambda r:(next((r/'exchange/receipts').glob('*.json'))).write_text('{}'),True,'reject'),('cache_changed',lambda r:(next((r/'cache/responses').glob('*.json'))).write_text('{}'),True,'reject'),('missing_receipt',lambda r:next((r/'exchange/receipts').glob('*.json')).unlink(),True,'reject'),('extra_orphan_cache',lambda r:(r/'cache/responses'/('f'*64+'.json')).write_text('{}'),True,'reject'),('feedback_changed_no_rebind',lambda r:(r/'feedback.json').write_text('{}'),False,'reject'),('unknown_extra_artifact',lambda r:(r/'new-unbound.json').write_text('{}'),False,'reject')]:
  with tempfile.TemporaryDirectory(prefix='independent-posthoc-restore-') as td:
   root=Path(td)/'stage';root.mkdir()
   for sub in ['requests','exchange','cache']:shutil.copytree(parent/sub,root/sub)
   (root/'feedback.json').write_text(json.dumps({'synthetic_restore_fixture':True,'value':'not model feedback'}))
   completion={'manifest_hash':'synthetic-manifest','result':{'synthetic_restore_fixture':True},'immutable_artifacts':stage._files(root,runtime=True)}
   completion['completion_hash']=canonical_json_hash(completion);(root/'completion.json').write_text(json.dumps(completion))
   if mut:mut(root)
   if rebind:
    completion.pop('completion_hash');completion['immutable_artifacts']=stage._files(root,runtime=True);completion['completion_hash']=canonical_json_hash(completion);(root/'completion.json').write_text(json.dumps(completion))
   before=stage._files(root)
   fn=lambda:stage._completed_restore(root,'synthetic-manifest',{'max_local_calls':32})
   if expected=='reject':test('completed_restore_'+name,lambda:reject(fn))
   else:test('completed_restore_'+name,lambda:assertion(fn()['restored_without_execution']))
   test('restore_no_writes_'+name,lambda:assertion(before==stage._files(root)))
paths=['scripts/run_reviewed_posthoc_stage.py','spec/scripts/run_reviewed_posthoc_stage.md','reports/reviewed-posthoc-stage-expectations-20261020.json','src/stock_opportunity_agent/research/evolution_plan_roles.py','src/stock_opportunity_agent/research/evolution_output_validation.py','src/stock_opportunity_agent/cases/label_store.py','src/stock_opportunity_agent/data/json_stream.py']
out={'scope':'Real pending inspected, zero model answers/submit/role creation. Historical parent only read/verified; tiny temporary restore fixtures reuse already-approved response bytes, do not prove new feedback behavior. No 903MB archive or actual LabelStore loading in this probe.','checks':checks,'all_passed':all(x['pass'] for x in checks),'request_hash':wire['request_hash'],'request_reservation_bytes_plus_output_tokens':reservation,'inbox_sha256':hashlib.sha256(wirefile.read_bytes()).hexdigest(),'network_attempts':net['network_attempts'],'bindings':{p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in paths}}
p=OUT/'preflight-results.json';assert not p.exists();p.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'checks':len(checks),'all_passed':out['all_passed'],'failures':[x for x in checks if not x['pass']],'request_reservation':reservation,'network_attempts':out['network_attempts']},indent=2))
