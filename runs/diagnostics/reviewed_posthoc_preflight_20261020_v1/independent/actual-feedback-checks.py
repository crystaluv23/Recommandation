"""Read-only actual Posthoc output/patch/source/restore verification. No resume."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,date
import hashlib,json
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_state_patch import apply_state_patch
from stock_opportunity_agent.research.evolution_plan_roles import _structured_reflection_items
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from stock_opportunity_agent.research.evolution_core import PredictionSelfReflection,_normalized_projection_text
from stock_opportunity_agent.research.evolution_transport import _parse_json_object_envelope
import run_reviewed_posthoc_stage as stage
REPO=Path('/Users/l/Project/Recommandation');root=REPO/'runs/diagnostics/reviewed_posthoc_stage_20261020_v1';OUT=Path(__file__).resolve().parent
first='beba78080ab4e2d68a1bfd55ea99550f45c5a02d1be4ad75799952f3ad58049d';second='95508c049373663b7564166f34f5e5862bffb93508e7f203f9179e9564b9044c'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs=read(root/'inputs.json');contract=read(root/'contract.json');feedback=read(root/'feedback.json');summ=read(root/'execution_summary.json');completion=read(root/'completion.json');oracle=read(root/'expectations.json');manifest=read(root/'manifest.json')
roles=[];total_reservation=0
for digest,agent in [(first,'/root/role_39'),(second,'/root/role_40')]:
 journal=read(root/'requests'/f'{digest}.json');request=journal['request'];assert canonical_json_hash(request)==digest==journal['request_hash'];inbox=read(root/'exchange/inbox'/f'{digest}.json');receipt=read(root/'exchange/receipts'/f'{digest}.json');cache=read(root/'cache/responses'/f'{digest}.json');rawpath=root/'exchange/outbox'/f'{digest}.txt';raw=rawpath.read_bytes().decode()
 assert receipt['agent_id']==agent and receipt['request_hash']==digest and receipt['raw_output_sha256']==sha(rawpath) and receipt['inbox_sha256']==sha(root/'exchange/inbox'/f'{digest}.json')
 assert inbox['messages']==request['messages'] and inbox['max_output_tokens']==request['max_output_tokens']
 parsed,norm=_parse_json_object_envelope(raw);reservation=len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+request['max_output_tokens'];total_reservation+=reservation
 local_usage={**receipt,'accounting_tokens':reservation,'cost':0.0,'cost_basis':'zero_external_api_cost_internal_unknown','token_usage':None,'internal_agent_cost':None}
 expected={'request_hash':digest,'response_id':'local-'+digest,'model':'independent-subagent','json_output':parsed,'usage':local_usage,'raw_output':raw,'decision_token_scores':None}
 if norm is not None:expected['structured_output_normalization']=norm
 assert cache==expected
 roles.append({'request_hash':digest,'stage':request['stage'],'agent_id':agent,'raw_sha256':sha(rawpath),'inbox_sha256':receipt['inbox_sha256'],'reservation':reservation})
first_raw=read(root/'exchange/outbox'/f'{first}.txt');patch=read(root/'exchange/outbox'/f'{second}.txt');second_payload=json.loads(read(root/'requests'/f'{second}.json')['request']['messages'][-1]['content']);payload=json.loads(read(root/'exchange/inbox'/f'{first}.json')['messages'][-1]['content'])
assert second_payload['invalid_output']==first_raw
assert patch=={'base_hash':second_payload['output_patch_contract']['base_hash'],'operations':[{'op':'remove','path':'reflection_items[1].related_signal_refs[0]'},{'op':'remove','path':'reflection_items[1].related_signal_refs[1]'}]}
assembled=apply_state_patch(first_raw,patch,contract=second_payload['output_patch_contract']);expected_assembled=deepcopy(first_raw);expected_assembled['reflection_items'][1]['related_signal_refs']=[];assert assembled==expected_assembled
value=feedback['value'];snapshot=value['source_snapshot'];assert snapshot=={'source_identity':value['source_identity'],'candidate_judgment_feedback':payload['candidate_judgment_feedback'],'magnitude_feedback':payload['magnitude_feedback']}
identity='case:'+canonical_json_hash({'context':payload['compact_context'],'prediction':payload['original_prediction'],'judgment_feedback':payload['candidate_judgment_feedback'],'magnitude_feedback':payload['magnitude_feedback']});assert identity==value['source_identity']
index=ReflectionMemoryIndex.from_case_rows([snapshot],owner_ref=identity);assert index.source_catalog()==payload['source_catalog'];items,selected,projection=_structured_reflection_items(assembled,index=index,level='case',owner_ref=identity)
expected_value=PredictionSelfReflection(correct=payload['framework_prediction_correct'],**projection,reflection_items=items,source_identity=identity,source_snapshot=snapshot).to_dict();assert value==expected_value
for rawrow,accepted in zip(first_raw['reflection_items'],value['reflection_items'],strict=True):
 for key,item in rawrow.items():
  if key!='related_signal_refs':assert accepted[key]==item,(key,item)
 assert 'related_signal_refs' not in accepted
assert feedback['request_hashes']==[first,second] and [x['request_hash'] for x in feedback['request_trace']]==[first,second];assert feedback['usage']=={'llm_calls':2,'tokens':total_reservation,'cost':0.0};assert not feedback['native_validation_fallback'] and feedback['native_validation_fallback_events']==[] and feedback['validation_events']==[]
assert len(list((root/'exchange/receipts').glob('*.json')))==2 and len(list((root/'exchange/inbox').glob('*.json')))==2
ch=completion.pop('completion_hash');assert canonical_json_hash(completion)==ch;assert completion['immutable_artifacts']==stage._files(root,runtime=True)
assert summ['before']==summ['after'] and summ['artifact_count']==19 and len(summ['after'])==19 and summ['before_counts']==summ['after_counts']=={'inbox':2,'receipts':2,'journals':2};assert summ['new_dispatches']==summ['new_receipts']==0 and summ['result']['restored_without_execution']
for path,h in summ['after'].items():assert sha(Path(path))==h,path
assert stage._files(Path(inputs['parent']['root']))==inputs['parent']['files'];assert sha(Path(inputs['prediction_file']['path']))==inputs['prediction_file']['sha256']==oracle['parent']['prediction_sha256']
for row in manifest['code_files']+manifest['originals']+inputs['qualification']['label_files']:assert sha(Path(row['path']))==row['sha256'],row['path']
qualification=inputs['qualification'];record=qualification['record'];assert record['future_peak_mean']/record['baseline_mean']==record['realized_max_multiple']==payload['revealed_ground_truth']['realized_max_multiple'];assert record['baseline_mean']==6.494 and record['future_peak_mean']==5.986 and record['horizon_end']=='2026-03-30';assert all(date.fromisoformat(x)<date(2025,9,30) for x in record['baseline_dates']);assert all(date(2025,9,30)<=date.fromisoformat(x)<=date(2026,3,30) for x in record['future_peak_dates']);assert not record['is_surge'] and record['magnitude'] is None
canonical=REPO/'runs/cold_start/data/global-raw-info-oracle-v1/filing/cik_0001830043/sec:cik_0001830043:000162828025038861.json';doc=read(canonical);assert hashlib.sha256(doc['content'].encode()).hexdigest()==doc['content_hash'];text=_normalized_projection_text(doc['content'])[0];quotes=[]
for evidence in payload['compact_context']['final_research_state']['supporting_evidence'][1:]:
 assert evidence['exact_text'] in text
 quotes.append({'projection_id':evidence['projection_id'],'quote_sha256':hashlib.sha256(evidence['exact_text'].encode()).hexdigest(),'canonical_normalized_offset':text.index(evidence['exact_text'])})
assert datetime.fromisoformat(doc['available_at'])<datetime.fromisoformat(payload['compact_context']['prediction_time'])
out={'all_passed':True,'scope':'Read-only exact original/correction/parser identity, source quotes and actual driver restore evidence verification. No formal resume/submit, no new model/network calls, no large price archive scan. Semantic review is separately authored.','roles':roles,'typed_corrections':1,'first_answer_native_rejected':True,'sole_first_answer_obligation':second_payload['required_change_paths'],'patch_only_two_reference_removals':True,'all_other_authored_fields_verbatim':True,'accepted_value_exact_original_parser_reconstruction':True,'runtime_ids_and_source_relations_exact':True,'request_trace_original_order':True,'logical_calls':2,'reservation_tokens':total_reservation,'fallback':False,'validation_events':[],'validation_event_note':'This normal exact patch acceptance emitted no progress event in the current native parser; correction occurrence is established by its exact request/receipt/patch, not by absence of events.','actual_restore':{'artifact_count':19,'before_equals_after_and_current':True,'zero_new_dispatch_and_receipt':True,'restored_without_execution':True,'driver_execution_summary_sha256':sha(root/'execution_summary.json')},'parent_unchanged':True,'label_qualification':{'frozen_record_and_wire_truth_exact':True,'baseline_mean':record['baseline_mean'],'future_peak_mean':record['future_peak_mean'],'horizon_end':record['horizon_end'],'archive_consistency_not_global_provider_or_issuer_authentication':True,'archive_not_reread':True},'canonical_sec':{'path':str(canonical),'sha256':sha(canonical),'content_hash':doc['content_hash'],'available_at':doc['available_at'],'verified_quotes':quotes},'artifact_bindings':{str(p):sha(p) for p in [root/'feedback.json',root/'completion.json',root/'inputs.json',root/'expectations.json',root/'manifest.json']},'script_sha256':sha(Path(__file__))}
p=OUT/'actual-feedback-checks.json';assert not p.exists();p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('canonical_sec','artifact_bindings','roles')},indent=2))
