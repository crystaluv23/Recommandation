"""Read-only exact actual orientation answer/source/receipt/restore checks."""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import hashlib,json
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_state_patch import apply_state_patch
from stock_opportunity_agent.research.evolution_core import InformationPlan,BasicInfoPolicy,_normalized_projection_text
from stock_opportunity_agent.research.evolution_output_validation import _validate_fixed_plan_semantics,_RESEARCH_CONTROLLER_DIRECTION_DECISION,_RESEARCH_CONTROLLER_ONTOLOGY_GUARD,_PLAN_PROHIBITION_GUARD
from stock_opportunity_agent.research.evolution_transport import _parse_json_object_envelope
import run_reviewed_orientation_stage as stage
REPO=Path('/Users/l/Project/Recommandation');ROOT=REPO/'runs/diagnostics/reviewed_orientation_stage_20261020_v1';OUT=Path(__file__).resolve().parent
roles={'p01_first':('570bd086906c5c8afbd51c1eb28a8fb9b82f581f7f8e58e6df0accc65ffa07b1','/root/role_41'),'p01_correction':('80f2abfe277fe56b5d696f67ac1c8de1971a2e87118d689c68ba2f34971d58c3','/root/role_44'),'h01':('d9d5f42a958f07afb4429f9d5715d626a96a8f9a507b55ac2fcf753db74de32e','/root/role_45'),'h02':('7fd41b71494c0a1e7822d6da02a45a390a65efcf7aec2a39434b82d4144b5160','/root/role_42'),'h03':('94d7186975de472ce726d0ff977706f31d08b58f4a284fb8b35e15108f506ffa','/root/role_43')}
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs=read(ROOT/'inputs.json');manifest=read(ROOT/'manifest.json');contract=read(ROOT/'contract.json');progress=read(ROOT/'progress.json');summary=read(ROOT/'execution_summary.json');completion=read(ROOT/'completion.json');raws={};payloads={};role_checks=[]
for key,(digest,agent) in roles.items():
 journal=read(ROOT/'requests'/f'{digest}.json');q=journal['request'];assert canonical_json_hash(q)==digest==journal['request_hash'];assert q['contract_hash']==canonical_json_hash(contract);inbox=read(ROOT/'exchange/inbox'/f'{digest}.json');receipt=read(ROOT/'exchange/receipts'/f'{digest}.json');rawpath=ROOT/'exchange/outbox'/f'{digest}.txt';rawtext=rawpath.read_bytes().decode();parsed,norm=_parse_json_object_envelope(rawtext);raws[key]=parsed;payloads[key]=json.loads(q['messages'][-1]['content']);assert receipt['agent_id']==agent and receipt['request_hash']==digest and receipt['inbox_sha256']==sha(ROOT/'exchange/inbox'/f'{digest}.json') and receipt['raw_output_sha256']==sha(rawpath);assert q['messages']==inbox['messages']
 reservation=len(json.dumps(q['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+q['max_output_tokens'];assert reservation<=131072
 usage={**receipt,'accounting_tokens':reservation,'cost':0.0,'cost_basis':'zero_external_api_cost_internal_unknown','token_usage':None,'internal_agent_cost':None};expected={'request_hash':digest,'response_id':'local-'+digest,'model':'independent-subagent','json_output':parsed,'usage':usage,'raw_output':rawtext,'decision_token_scores':None}
 if norm is not None:expected['structured_output_normalization']=norm
 assert read(ROOT/'cache/responses'/f'{digest}.json')==expected
 role_checks.append({'key':key,'request_hash':digest,'agent_id':agent,'raw_sha256':sha(rawpath),'reservation_units':reservation})
feedback=payloads['p01_correction']['validation_feedback'];assert feedback['invalid_output']==raws['p01_first'];assert feedback['required_change_paths']==['H_reflect'] and feedback['permitted_dependency_paths']==[];assert len(feedback['obligations'])==1 and feedback['obligations'][0]['issue_code']=='controller_decides_price_direction'
patch=raws['p01_correction'];assert len(patch['operations'])==1 and patch['operations'][0]['op']=='replace' and patch['operations'][0]['path']=='H_reflect';corrected=apply_state_patch(raws['p01_first'],patch,contract=payloads['p01_correction']['output_patch_contract'])
for key in ['B','H_init','H_analyse','used_experience_refs']:assert corrected[key]==raws['p01_first'][key]
plan=read(ROOT/'samples/p01/plan.json');p=plan['plan'];assert p['basic_info_policy']==corrected['B'] and p['initial_research_skill']==corrected['H_init'] and p['reflection_skill']==corrected['H_reflect'] and p['analysis_prompt']==corrected['H_analyse'];assert p['experience_usage']['item_refs']==[] and corrected['used_experience_refs']==[];assert plan['request_hashes']==[roles['p01_first'][0],roles['p01_correction'][0]]
probe=InformationPlan(plan_id='readonly_probe',parent_ids=(),basic_info_policy=BasicInfoPolicy.from_dict(raws['p01_first']['B']),initial_research_skill=raws['p01_first']['H_init'],reflection_skill=raws['p01_first']['H_reflect'],analysis_prompt=raws['p01_first']['H_analyse']);guard=[]
for name,text,expected in [('original_without_deciding',probe.reflection_skill,'reject'),('explicit_prohibition',probe.reflection_skill.replace('without deciding price direction','must not decide price direction'),'accept'),('affirmative_control',probe.reflection_skill.replace('without deciding price direction','decide price direction'),'reject')]:
 scrubbed=_PLAN_PROHIBITION_GUARD.sub('',_RESEARCH_CONTROLLER_ONTOLOGY_GUARD.sub('',text));match=_RESEARCH_CONTROLLER_DIRECTION_DECISION.search(scrubbed)
 try:_validate_fixed_plan_semantics(replace(probe,reflection_skill=text));actual='accept'
 except Exception:actual='reject'
 assert actual==expected;guard.append({'case':name,'actual':actual,'matched':match.group(0) if match else None})
# Read only the four filing bodies actually cited, through their materialized bindings.
source_documents={}
for binding in inputs['sources'].values():
 view=Path(binding['root']);sm=read(view/'reviewed_snapshot.json')
 for row in sm['documents']:source_documents[row['document_id']]=(view/row['path'],row['sha256'])
normalized={};quote_checks=[];sample_checks=[]
for sid in ['h01','h02','h03']:
 sample=next(s for s in inputs['samples'] if s['sample_id']==sid);bootstrap=read(ROOT/'samples'/sid/'bootstrap.json');accepted=read(ROOT/'samples'/sid/'initial_state.json');parsed=read(ROOT/'samples'/sid/'parsed_step.json');raw=raws[sid];payload=payloads[sid]
 assert accepted['state']==parsed['state'] and accepted['metadata']==parsed['metadata']=={} and accepted['usage']==parsed['usage']==accepted['native_budget_usage'];assert accepted['request_hashes']==[roles[sid][0]];assert all(v==accepted['state'][k] for k,v in raw.items() if k!='supporting_evidence');assert len(raw['supporting_evidence'])==len(accepted['state']['supporting_evidence'])
 if sid=='h01':assert bootstrap['plan']==p and bootstrap['evaluation_anchor']==payload['evaluation_anchor']==payload['evaluation_context']['evaluation_anchor'];assert bootstrap['evaluation_anchor']['mean_adjusted_close']==6.494 and bootstrap['evaluation_anchor']['doubling_threshold']==12.988 and bootstrap['evaluation_anchor']['recent_close']==6.3;assert bootstrap['computed_metrics']==payload['computed_metrics']
 else:assert bootstrap['plan']==sample['plan'] and bootstrap['evaluation_anchor'] is None and bootstrap['computed_metrics']==[] and 'evaluation_anchor' not in payload
 assert bootstrap['document_channel_set_by_core'];visible={row['projection_id']:row for request in payload['basic_info']['requests'] for row in request.get('projections',[])};lineage={row['projection_id']:row for row in bootstrap['projection_lineage']['entries']}
 for initial,evidence in zip(raw['supporting_evidence'],accepted['state']['supporting_evidence'],strict=True):
  pid=evidence['projection_id'];assert initial['projection_id']==pid and initial['claim']==evidence['claim'];assert initial['exact_text'] in visible[pid]['exact_text'];entry=lineage[pid];assert evidence['exact_text'] in entry['projection_text'];docid=entry['document_id']
  if docid not in normalized:
   path,expectedsha=source_documents[docid];assert sha(path)==expectedsha;doc=read(path);assert hashlib.sha256(doc['content'].encode()).hexdigest()==doc['content_hash'];normalized[docid]=(doc,_normalized_projection_text(doc['content'])[0])
  doc,text=normalized[docid];assert evidence['exact_text'] in text and doc['content_hash']==entry['content_hash'];assert datetime.fromisoformat(doc['available_at'])<=datetime.fromisoformat(sample['prediction_time']);quote_checks.append({'sample_id':sid,'projection_id':pid,'document_id':docid,'quote_sha256':hashlib.sha256(evidence['exact_text'].encode()).hexdigest(),'literal_in_actual_wire_and_canonical':True,'source_available_at':doc['available_at']})
 assert all(alias.lower() not in json.dumps(payload,ensure_ascii=False).lower() for alias in sample['identity']['identity_aliases'])
 sample_checks.append({'sample_id':sid,'state_fields_verbatim_except_native_evidence_unmasking':True,'evidence_count':len(raw['supporting_evidence']),'needs_count':len(raw['next_information_needs']),'request_trace':accepted['request_hashes'],'usage':accepted['usage'],'source_visibility':[{k:req[k] for k in ['projection_status','visible_projection_count','available_projection_count','source_context_truncated','projection_context_truncated','effective_context_truncated'] if k in req} for req in payload['basic_info']['requests']]})
assert read(ROOT/'validation_events.json')==[];assert progress['pending']==[] and progress['independent_receipts']==5;assert len(list((ROOT/'requests').glob('*.json')))==len(list((ROOT/'exchange/inbox').glob('*.json')))==len(list((ROOT/'exchange/receipts').glob('*.json')))==5
restore=summary['completed_restore'];assert restore['before']==restore['after'] and restore['all_hashes_equal'] and restore['file_count']==42 and restore['counts_before']==restore['counts_after'] and restore['new_inbox']==restore['new_receipts']==0
for row in restore['after']:assert sha(Path(row['path']))==row['sha256']
completion_hash=completion.pop('completion_hash');assert canonical_json_hash(completion)==completion_hash;assert completion['immutable_artifacts']==stage._files(ROOT,runtime=True)
for row in manifest['code_files']:assert sha(Path(row['path']))==row['sha256']
out={'all_passed':True,'scope':'Read-only actual five-role artifacts/parser/claim-source/PIT/restore checks. No formal resume/submit, no new API/model/labels/large price archive access. Semantic judgment is separately written.','role_checks':role_checks,'p01_first_native_rejected_but_semantic_false_positive':guard,'p01_native_correction_only_H_reflect':True,'other_authored_plan_fields_exact':True,'p01_exact_accepted_plan_consumed_h01':True,'sample_checks':sample_checks,'all18_evidence_quotes_bound_to_actual_wire_lineage_and_canonical_source':quote_checks,'native_validation_events':[],'fallback_note':'Empty events are not treated as evidence of no correction. Actual p01 correction journal/receipt/patch is explicit; each H_init final state equals its first answer after only native evidence-source unmasking. No state row salvage or Plan fallback replaced content.','actual_completed_restore':{'file_count':42,'before_after_and_current_equal':True,'new_inbox':0,'new_receipts':0,'full_restore_map':restore['after']},'summary_snapshot_sha256_at_audit':sha(ROOT/'execution_summary.json'),'formal_manifest_hash':progress['manifest_hash'],'bindings':{str(path):sha(path) for path in [ROOT/'completion.json',ROOT/'samples/p01/plan.json',ROOT/'samples/h01/initial_state.json',ROOT/'samples/h02/initial_state.json',ROOT/'samples/h03/initial_state.json',ROOT/'expectations.json',Path(__file__)]}}
p=OUT/'actual-orientation-checks.json';assert not p.exists();p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'all_passed':True,'roles':len(role_checks),'quotes':len(quote_checks),'restore_files':42,'guard_probe':guard,'output':str(p),'output_sha256':sha(p)},indent=2))
