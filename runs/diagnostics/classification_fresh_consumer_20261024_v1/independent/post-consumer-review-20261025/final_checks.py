"""Verify actual persisted consumer chain without dispatching a role or label read."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import run_classification_consumer_stage as s
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_transport import _CaseIdentityProjection

p=s.ROOT;out=s.BASE/'independent/post-consumer-review-20261025';o=s.read_json(s.ORACLE)
inputs,c=s.verify();manifest=s.read_json(p/'manifest.json');pre=s.read_json(s.REVIEW)
s.initial.check(pre['code_files']+[pre['authorization'],pre['oracle']])
checks=[]
def check(name,value):
 assert value,name
 checks.append({'check':name,'passed':True})
reflect_hash='1b331edf090e1d8650275ba3251dfd50ac60c1cc6e160cab9c1c12bd94e4f662'
predict_hash='e75f08fab7ee6f8110152ad8302a689a0c72c84113a32f8a42f8249cc5d12614'
completion=s.read_json(p/'completion.json');sink=s.read_json(p/'prediction-sink.json');s.initial.check([completion['prediction_sink']])
check('Pointer is stage completion with exact durable sink hash',completion['state']=='completed')
check('Original bootstrap preserved complete',s.read_json(p/'bootstrap.json')==o['bootstrap_gate']['original_bootstrap'])
check('No extra role responses/correction stage',len(list((p/'exchange/receipts').glob('*.json')))==2 and len(list((p/'exchange/inbox').glob('*.json')))==2)
raws={};wires={};receipt_agents=[];recomputed_units=0
for digest in (reflect_hash,predict_hash):
 raw=(p/f'exchange/outbox/{digest}.txt').read_bytes();receipt=s.read_json(p/f'exchange/receipts/{digest}.json');wire=s.read_json(p/f'exchange/inbox/{digest}.json');request=s.read_json(p/f'requests/{digest}.json')['request']
 check('Receipt raw/inbox/request binding '+digest[:8],receipt['raw_output_sha256']==hashlib.sha256(raw).hexdigest() and receipt['inbox_sha256']==hashlib.sha256((p/f'exchange/inbox/{digest}.json').read_bytes()).hexdigest() and receipt['request_hash']==digest==canonical_json_hash(request))
 check('Inbox equals actual native message payload '+digest[:8],wire['messages']==request['messages'] and wire['max_output_tokens']==request['max_output_tokens'])
 unit=len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+request['max_output_tokens'];recomputed_units+=unit
 reservation=s.read_json(p/f'reservations/{digest}.json');check('Complete native message-byte/output reservation '+digest[:8],reservation['reservation']==unit and reservation['request_hash']==digest)
 raws[digest]=json.loads(raw);wires[digest]=wire;receipt_agents.append(receipt['agent_id'])
check('Fresh distinct Reflect/Predictor author receipts',len(set(receipt_agents))==2 and set(receipt_agents)=={'/root/classification_fresh_reflect','/root/classification_fresh_predictor'})
reflect=s.read_json(p/'accepted-reflect.json');original=deepcopy(inputs['accepted_initial_step']['state'])
for operation in raws[reflect_hash]['operations']:
 if operation['op']=='append': original[operation['path']].append(operation['value'])
 elif operation['op']=='replace': original[operation['path']]=operation['value']
 else:raise AssertionError('unexpected raw operation')
check('Accepted Reflect state exactly applies original raw operations',original==reflect['state'])
check('All five exact unresolved needs retained with no answered ownership',reflect['state']['next_information_needs']==o['F7_needs']['exact_original_needs'] and reflect['state']['resolved_questions']==[] and reflect['metadata']['need_dispositions']['items']==[])
actual=s.read_json(p/'actual-batch.json');decl=actual['classification_contracts'][s.REF];result=actual['results'][0]
check('Actual new measurement equals frozen original complete result',result==o['source_measurement']['expected_legacy_result'])
check('Declaration binds exact actual result/version/consumed parameters',decl['result_hash']==canonical_json_hash(result) and decl['signal_ref']==s.REF and decl['execution']['configured_parameters']==o['classification']['expected_consumed_parameters'])
local=sink['context'];anonymous=json.loads(wires[predict_hash]['messages'][1]['content'])['final_context'];identity=inputs['sample']['identity']
projected,_=_CaseIdentityProjection(identity['identity_aliases'],inputs['sample']['company_id'],identity['ticker']).project(local)
check('Entire actual anonymous final request equals identity projection of persisted sink context',anonymous==projected)
check('Predictor input exactly equals sink complete local context',s.read_json(p/'predictor-input.json')['context']==local)
check('Final state equals accepted Reflect state',local['final_research_state']==reflect['state'])
check('Actual stop cause retained',local['runtime_termination']=={'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':'max_signal_rounds'})
mc=anonymous['signal_rounds'][0]['batch']['results'][0]['interpretation']['measurement_context']
check('Complete actual declaration reaches final anonymous wire',mc['classification_contract']==decl)
check('Numeric sign and category remain independently explicit',mc['numeric_measurement']['numeric_sign']=='positive' and mc['numeric_measurement']['categorical_state']=='positive')
check('Exact measurement/formula/period/unit reaches final consumer',mc['numeric_measurement']['value']==5.374720662778656 and mc['numeric_measurement']['unit']=='months' and mc['numeric_measurement']['formula']==result['measurement']['formula'] and mc['numeric_measurement']['period']==result['measurement']['period'])
check('Both complete literal operand sources reach final consumer',[v['evidence'] for v in anonymous['cited_signal_evidence']]==result['evidence']['supporting'])
accepted=s.read_json(p/'accepted-prediction.json');acceptedraw={k:v for k,v in accepted['prediction'].items() if k!='is_surge'}
check('Predictor accepted exactly original raw fields with native derived is_surge',acceptedraw==raws[predict_hash] and accepted['prediction']['is_surge'] is False)
check('Durable prediction equals accepted original answer',sink['prediction']==accepted['prediction'])
usage=s.read_json(p/'request-reservations.json')
check('Exact newly reserved logical units128731',recomputed_units==usage['total']==128731 and usage['requests'][0]['reservation']==59446 and usage['requests'][1]['reservation']==69285)
check('Native prior-inclusive usage239763/4 preserved',sink['combined_case_usage']=={'cost':0.0,'llm_calls':4,'tokens':239763} and 239763<=256000)
check('Historical debt cumulative364582/6 below380819/7',sink['historical_cumulative_usage']=={'cost':0.0,'llm_calls':6,'tokens':364582} and 364582<=380819 and 128731<=144968)
check('Completed stage has no failure and no labels',not (p/'failure.json').exists() and sink['labels']==completion['labels']==0)
check('Old consumer still terminal old235851/4 unchanged',s.read_json(s.historical.ROOT/'completion.json')['state']=='completed' and s.read_json(s.historical.ROOT/'prediction-sink.json')['combined_case_usage']=={'cost':0.0,'llm_calls':4,'tokens':235851})
check('No oracle/review text in either evaluated inbox',all(not any(token in m['content'] for token in ['conditional-classification-consumer-oracle-v1','approved-review-20261025','post-consumer-review-20261025']) for w in wires.values() for m in w['messages']))
# Factual cross-checks for every numerical/source claim in the final raw answer.
baseline=anonymous['prediction_baseline'];metric=anonymous['computed_metrics'][0];cards={r['projection_id']:r for r in anonymous['basic_info']['projection_cards']}
check('Predictor baseline numbers correctly round actual inputs',round(baseline['mean_adjusted_close'],2)==4.28 and round(baseline['doubling_threshold'],2)==8.56)
margin=cards['projection_01fe85919029e3da1c7a0940']['exact_text'];check('Predictor margin numbers/units/comparison shown in source card',all(v in margin for v in ['in thousands','Three Months Ended March 31, 2025 2024','5,692','2,643','3,039','8,367']))
check('Predictor price change/endpoints/window agree with metric',metric['literal_refs']==[{'adjusted_close':12.93,'as_of_date':'2024-09-23'},{'adjusted_close':4.14,'as_of_date':'2025-05-29'}] and metric['values']['return_pct']==-67.9814 and metric['values']['window_trading_days']==171)
check('Predictor truncation/news limits agree with actual packet',all(r['effective_context_truncated'] for r in anonymous['basic_info']['source_index'] if r['request_id'] in ('orientation.v1.operating_report','orientation.v1.financial_facts')) and anonymous['basic_info']['data_gaps'][0]['reason']=='no_matching_documents')
(out/'final-checks.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'production_roles':0,'external_API':0,'labels':0},indent=2)+'\n')
print(json.dumps({'passed':len(checks),'source_bindings_reverified':len(manifest['source_files']),'code_bindings_reverified':len(manifest['code_files']),'new_units':128731,'native_usage':239763,'historical_usage':364582,'new_responses':2,'corrections':0},indent=2))
