from pathlib import Path
import tempfile,shutil,json,hashlib
from unittest.mock import patch
import run_reviewed_fast_prefix as h
from scripts.replay_incremental_reflection_memory import deny_network
repo=Path('/Users/l/Project/Recommandation');parent=repo/'runs/diagnostics/reviewed_fast_prefix_20261019_v1';out=repo/'runs/diagnostics/reviewed_fast_prefix_continuation_20261019_v1/independent';captured=[]
with tempfile.TemporaryDirectory(prefix='independent-final-input-') as td,deny_network() as network:
 root=Path(td).resolve();copy=root/'parent';shutil.copytree(parent,copy);child=root/'child';h.prepare(child,repo/'reports/reviewed-fast-prefix-expectations-20261019.json',parent_root=copy,parent_commit='1acfd2a4f1cd41c5837206211a911c5f32abc662')
 native=h.LocalRoleExchange.receive
 def capture_no_new(exchange,request,**kwargs):
  digest=h.canonical_json_hash(request)
  if not (exchange.root/'inbox'/f'{digest}.json').exists():
   captured.append({'request_hash':digest,'request':request});raise h.EvolutionControlFlow('independent input capture before new dispatch')
  return native(exchange,request,**kwargs)
 with patch.object(h.LocalRoleExchange,'receive',new=capture_no_new):result=h.resume(child)
 assert len(captured)==1 and captured[0]['request_hash']=='15441678ce55d53084a3f6639a45d7186f0cb08b24da654c2bdb212bfe62025f'
 assert len(list((child/'exchange/inbox').glob('*.json')))==len(list((child/'exchange/receipts').glob('*.json')))==2
 assert not (child/'prediction.json').exists() and not (child/'completion.json').exists()
 request=captured[0]['request'];payload=json.loads(request['messages'][-1]['content']);context=payload['final_context'];old=h.read_json(parent/'observations/initialize_00.json')['value']
 assert context['final_research_state']['next_information_needs']==old['next_information_needs']
 assert context['final_research_state']['decision']=='finalize'
 assert context['runtime_termination']=={'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':'budget_exhausted'}
 assert context['prediction_baseline']['mean_adjusted_close']==6.494 and context['prediction_baseline']['doubling_threshold']==12.988
 assert all(alias not in json.dumps(request['messages']) for alias in ('BMBL','Bumble','cik_0001830043'))
 assert len(context['state_evolution'])==1 and len(context['signal_rounds'])==1
 delta=context['state_evolution'][0]['delta'];assert delta['decision']=={'from':'continue','to':'finalize'} and delta['next_information_needs']=={'added':[],'removed':[]}
 assert all(not value for field,changes in delta.items() if field!='decision' for value in changes.values())
 cards=context['signal_rounds'][0]['batch']['results'];assert len(cards)==2
 assert all(row['execution']['status']=='budget_blocked' and 'Technical execution gap' in row['interpretation']['summary'] for row in cards)
 basic=context['basic_info'];index=basic['source_index'];filing=next(r for r in index if r['request_id']=='recent_annual_filing');market=next(r for r in index if r['request_id']=='recent_market_backbone')
 assert filing['available_projection_count']==23 and filing['visible_projection_count']==18 and filing['omitted_projection_count']==5
 assert filing['source_context_truncated'] is True and filing['projection_context_truncated'] is True and filing['effective_context_truncated'] is True
 assert market['source_context_truncated'] is True and market['projection_context_truncated'] is False and market['effective_context_truncated'] is True
 for p,v in [('predictor-final-request.json',captured[0]),('predictor-final-context.json',context)]:
  assert not (out/p).exists();(out/p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 review={'scope':'Pre-dispatch F8 final input only; historical exact role36/37 reuse in temporary child. No fresh role output, no new inbox or receipt, no sink/labels.','verdict':'narrow_input_preservation_pass','request_hash':captured[0]['request_hash'],'request_canonical_hash_verified':h.canonical_json_hash(request)==captured[0]['request_hash'],'four_needs_exactly_preserved':True,'controller_decision':context['final_research_state']['decision'],'runtime_termination':context['runtime_termination'],'signal_results':cards,'no_need_disposition_or_answered_closure':True,'decision_only_state_evolution':context['state_evolution'],'anchor':context['prediction_baseline'],'basic_info_source_index':index,'anonymous':True,'new_inboxes':0,'new_receipts':0,'new_model_answers':0,'network_attempts':network['network_attempts'],'pending_answer_not_predetermined':True,'notes':['Both unavailable-shaped results are technical budget failures with explicit execution status; neither is domain absence nor bearish evidence. Actual future Predictor adherence is still untested.','All4 needs remain open. State finalize is the existing deterministic must_finalize/all-unavailable Reflect fallback; runtime stop finalized still preserves independent budget_exhausted trigger. No fresh Reflect answer or complete research is asserted.','Partial filing18/23 and market upstream omission survive; earlier accepted evidence citations and baseline persist in packet. Full F2 coverage remains open.'],'bindings':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [repo/'scripts/run_reviewed_fast_prefix.py',repo/'spec/scripts/run_reviewed_fast_prefix.md',out/'predictor-final-request.json',out/'predictor-final-context.json']}}
 (out/'predictor-final-input-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in review.items() if k not in ('signal_results','basic_info_source_index')},indent=2))
