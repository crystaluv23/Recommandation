import json,hashlib,math
from pathlib import Path
from datetime import datetime
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_core import _normalized_projection_text
import run_reviewed_fast_prefix as harness
repo=Path('/Users/l/Project/Recommandation');r=repo/'runs/diagnostics/reviewed_fast_prefix_20261019_v2';parent=repo/'runs/diagnostics/reviewed_fast_prefix_20261019_v1';h='15441678ce55d53084a3f6639a45d7186f0cb08b24da654c2bdb212bfe62025f'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
request=read(r/'requests'/f'{h}.json')['request'];wire=read(r/'exchange/inbox'/f'{h}.json');rawpath=r/'exchange/outbox'/f'{h}.txt';raw=read(rawpath);receipt=read(r/'exchange/receipts'/f'{h}.json');cache=read(r/'cache/responses'/f'{h}.json');obs=read(r/'observations/prediction_00.json');sink=read(r/'prediction.json');completion=read(r/'completion.json');manifest=read(r/'manifest.json');contract=read(r/'contract.json');expect=read(r/'expectations.json');inputs=read(r/'inputs.json');summary=read(r/'execution_summary.json');context=json.loads(request['messages'][-1]['content'])['final_context']
assert canonical_json_hash(request)==h and wire['messages']==request['messages']
assert receipt['agent_id']=='/root/role_38' and receipt['request_hash']==h and receipt['inbox_sha256']==sha(r/'exchange/inbox'/f'{h}.json') and receipt['raw_output_sha256']==sha(rawpath)
assert cache['raw_output']==rawpath.read_text() and cache['json_output']==raw
assert obs['request_hashes']==[h] and obs['value']==sink['prediction']
assert obs['value']=={**raw,'is_surge':False}
assert sink['final_context']==context and context==read(repo/'runs/diagnostics/reviewed_fast_prefix_continuation_20261019_v1/independent/predictor-final-context.json')
assert canonical_json_hash(contract)==manifest['contract_hash'] and canonical_json_hash(inputs)==contract['input_hash'] and canonical_json_hash(expect)==contract['expectations_hash'] and canonical_json_hash(read(r/'preflight.json'))==contract['preflight_hash']
assert expect==read(parent/'expectations.json') and inputs==read(parent/'inputs.json') and contract==read(parent/'contract.json')
for row in manifest['code_files']+manifest['originals']+manifest['registry_files']:assert sha(Path(row['path']))==row['sha256']
lineage=manifest['continuation'];assert harness._immutable_artifacts(parent)==lineage['parent_files'];assert len(lineage['inherited_request_hashes'])==2 and lineage['total_request_ceiling']==32 and lineage['maximum_new_requests']==30
for row in lineage['copied_files']:assert sha(r/row['relative_path'])==row['sha256']==sha(Path(row['path']))
cm={k:v for k,v in completion.items() if k!='completion_hash'};assert canonical_json_hash(cm)==completion['completion_hash'] and completion['manifest_hash']==manifest['manifest_hash'] and completion['immutable_artifacts']==harness._immutable_artifacts(r)
assert summary['before_file_hashes']==summary['after_file_hashes'] and len(summary['before_file_hashes'])==32
for path,digest in summary['after_file_hashes'].items():assert sha(r/path)==digest
assert summary['new_inboxes_on_completed_restore']==summary['new_receipts_on_completed_restore']==0 and summary['restored']['restored_without_execution'] is True
assert summary['ground_truth_reads']==0 and summary['restored']['ground_truth_reads']==0
# All formal exchanges: 3 answered, 2 journal-only; no correction or hidden apply/reflection response.
answered=[];journal=[]
for p in (r/'requests').glob('*.json'):
 d=read(p);q=d['request_hash'];assert canonical_json_hash(d['request'])==q==p.stem
 presence=[(r/base/f'{q}.{suffix}').exists() for base,suffix in [('exchange/inbox','json'),('exchange/outbox','txt'),('exchange/receipts','json'),('cache/responses','json')]]
 assert all(presence) or not any(presence)
 (answered if all(presence) else journal).append({'hash':q,'stage':d['request']['stage']})
assert len(answered)==3 and len(journal)==2 and all('correction' not in x['stage'] for x in answered+journal)
assert len(list((r/'exchange/receipts').glob('*.json')))==3
old=read(parent/'observations/initialize_00.json')['value'];final=context['final_research_state'];assert final['next_information_needs']==old['next_information_needs'] and len(final['next_information_needs'])==4
assert final['decision']=='finalize' and context['runtime_termination']=={'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':'budget_exhausted'}
reflect=read(r/'observations/reflect_00.json');assert reflect['request_hashes']==[] and reflect['usage']['llm_calls']==0
for field in old:
 if field not in ('decision','supporting_evidence'):assert final[field]==old[field]
cards=context['signal_rounds'][0]['batch']['results'];assert all(c['execution']['status']=='budget_blocked' and 'Technical execution gap' in c['interpretation']['summary'] for c in cards)
assert context['state_evolution'][0]['delta']['next_information_needs']=={'added':[],'removed':[]} and all('need_dispositions' not in x for x in context['state_evolution'])
assert all(alias not in json.dumps(request['messages']) for alias in ('BMBL','Bumble','cik_0001830043'))
# Financial original: verify the actual displayed full-column source excerpts, not merely citations/hashes.
filingpath=repo/'runs/cold_start/data/global-raw-info-oracle-v1/filing/cik_0001830043/sec:cik_0001830043:000162828025038861.json';filing=read(filingpath);normalized=_normalized_projection_text(filing['content'])[0]
required=['Revenue $ 248,229 $ 268,615 $ 495,330 $ 536,390','Selling and marketing expense 32,092 67,562 91,826 131,179','Product development expense 32,510 15,705 67,014 51,722','Impairment loss 404,855 — 408,486 —','Cash and cash equivalents $ 261,739 $ 204,319','Long-term debt, net 609,418 611,346','Payable to related parties pursuant to a tax receivable agreement 399,740 400,926']
visible='\n'.join(card['exact_text'] for card in context['basic_info']['projection_cards'])
for text in required:assert text in normalized and text in visible,text
# Independent original-series measurement of the actual 180-trading-session card and baseline.
marketpath=repo/'runs/cold_start/data/global-raw-info-oracle-v1/market_data/cik_0001830043/massive:cik_0001830043:market_data:c48ddf33f63755eb0e12623e.json';market=read(marketpath);rows=[x for x in json.loads(market['content']) if x['as_of_date']<'2025-09-30'];assert len(rows)==250
rows=sorted(rows,key=lambda x:x['as_of_date']);tail=rows[-180:];closes=[x['adjusted_close'] for x in tail];ret=closes[-1]/closes[0]-1;peak=closes[0];mdd=0
for x in closes:peak=max(peak,x);mdd=min(mdd,x/peak-1)
rs=[b/a-1 for a,b in zip(closes,closes[1:])];mu=sum(rs)/len(rs);vol=math.sqrt(sum((x-mu)**2 for x in rs)/len(rs));metric=context['computed_metrics'][0]
values={'window_trading_days':180,'first_close':closes[0],'last_close':closes[-1],'high':max(closes),'low':min(closes),'return_pct':round(ret*100,4),'max_drawdown_pct':round(mdd*100,4),'daily_volatility_pct':round(vol*100,4)}
assert metric['values']==values and metric['labels']=={'trend':'range'} and -.2<ret<.2
assert tail[0]['as_of_date']=='2025-01-10' and tail[-1]['as_of_date']=='2025-09-29'
base=sum(x['adjusted_close'] for x in rows[-5:])/5;assert abs(base-6.494)<1e-12 and context['prediction_baseline']['mean_adjusted_close']==6.494 and context['prediction_baseline']['doubling_threshold']==12.988 and context['prediction_baseline']['recent_close']==6.3
index=context['basic_info']['source_index'];filing_index=next(x for x in index if x['request_id']=='recent_annual_filing');assert filing_index['visible_projection_count']==18 and filing_index['available_projection_count']==23 and filing_index['source_context_truncated'] and filing_index['projection_context_truncated']
assert len(context['basic_info']['projection_cards'])==19 and context['basic_info']['projection_card_counts']=={'available_projections':19,'deferred_projections':0,'included_cards':19}
out={'scope':'Read-only exact formal v2 Predictor/sink/completed-restore evidence audit; no formal resume or new role answer.','request_hash':h,'receipt_agent':receipt['agent_id'],'first_answer_accepted_no_correction':True,'parser_delta_only_is_surge_projection':True,'sink_context_exactly_equals_actual_wire_and_predeclared_F8_input':True,'sink_prediction_exactly_equals_accepted_observation':True,'all_freeze_code_original_registry_bindings_match':True,'code_count':len(manifest['code_files']),'registry_file_count':len(manifest['registry_files']),'inherited_2_response_bytes_exact':True,'v1_all_immutable_original_bytes_unchanged':True,'completion_hash_inventory_match':True,'actual_completed_restore_driver_hashmaps':{'before_after_equal':True,'bound_files':32,'all_current_file_hashes_match':True,'new_inbox':0,'new_receipt':0,'restored_without_execution':True},'answered':answered,'journal_only':journal,'physical_roles':{'historical':2,'new_predictor':1,'total':3,'apply_model':0,'reflect_model':0},'runtime_termination':context['runtime_termination'],'four_needs_preserved':True,'deterministic_reflect_only':True,'canonical_financial_excerpts_verified':required,'metric_definition':'Trailing180 PIT trading sessions, endpoint return%; trend range is endpoint return strictly between -20% and +20%, not a claim of low volatility or the six-calendar-month outcome horizon.','independently_recomputed_metric':{'first_date':tail[0]['as_of_date'],'last_date':tail[-1]['as_of_date'],**values},'baseline':context['prediction_baseline'],'identity_oracle_label_boundary':'Actual request anonymous; frozen oracle never in role messages; sink saved/readback checked in frozen code before dedicated pre-label provider boundary. Driver actual boundary reached with GroundTruth reads0.','forecast_correctness_or_benefit_evaluated':False,'source_bindings':{str(p.relative_to(repo)):sha(p) for p in [filingpath,marketpath]},'formal_artifact_bindings':{str(p.relative_to(r)):sha(p) for p in [r/'expectations.json',r/'inputs.json',r/'contract.json',r/'manifest.json',r/'completion.json',r/'prediction.json',r/'observations/prediction_00.json',r/'requests'/f'{h}.json',r/'exchange/inbox'/f'{h}.json',rawpath,r/'exchange/receipts'/f'{h}.json',r/'cache/responses'/f'{h}.json']}}
Path('/tmp/independent-formal-v2-predictor-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('canonical_financial_excerpts_verified','formal_artifact_bindings','answered','journal_only')},indent=2))
