"""Audit actual source document handle masking at native request-ready, zero inbox/answers."""
import hashlib,json,sys
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0,'/Users/l/Project/Recommandation/scripts')
import run_mining_taxonomy_consumer_stage as stage
from stock_opportunity_agent.research.evolution_transport import _CaseIdentityProjection
BASE=Path('/Users/l/Project/Recommandation/runs/diagnostics/mining_taxonomy_consumer_20261023_v1')
root=BASE/'independent/identity-wire-capture';assert not root.exists();root.mkdir()
ref=json.loads((BASE/'reference/source-reference.json').read_text());positive=ref['positive_source_control']
inv=json.loads(stage.INVENTORY.read_text());sample={'case_id':'cik_0000800457:20250731','case_ref':'case-008','company_id':'cik_0000800457','cutoff':positive['case_cutoff'],'label':positive['opaque_group'],'concept':'NetCashProvidedByUsedInOperatingActivities','snapshot':inv['sources']['reviewed_snapshot']}
with stage.guards():
 client=stage.make_client(root,sample,{'limits':stage.LIMITS},input_only=True)
 controller=stage.build_controller(root,sample,client)
 facts=sorted((f for f in controller._facts.values() if f.concept==sample['concept']),key=lambda f:f.period['end'])
 assert len(facts)==2 and all(f.content_hash==positive['content_sha256'] for f in facts)
 for f in facts:
  action={'action':'read_span','fact_ref':f.fact_ref,'rationale':['Controlled identity-boundary audit, not a model answer.']}
  controller._validate_action_shape(action);controller._execute('read_span',action)
 controller._execute_compare({'action':'compare_groups','concepts':[sample['concept']],'rationale':['Controlled input capture only.']})
 local=controller._model_view()
 try:controller.model.next_action(local)
 except stage.InputCaptured:pass
 else:raise AssertionError('Crossed model receive')
requests=list((root/'requests').glob('*.json'));assert len(requests)==1
request=json.loads(requests[0].read_text())['request']
wire='\n'.join(m['content'] for m in request['messages']);view=json.loads(next(m['content'] for m in request['messages'] if m['role']=='user'))
local_handles=[x['document_ref'] for x in local['structured_read_progress']['items']]
wire_handles=[x['document_ref'] for x in view['structured_read_progress']['items']]
identifiers=[sample['case_id'],sample['company_id'],'0000800457','DGICA']
leaks={s:s in wire for s in identifiers}
assert not any(leaks.values())
assert local_handles!=wire_handles
projection=_CaseIdentityProjection((sample['case_id'],sample['company_id']),'','',expand_aliases=False)
projected,tokens=projection.project({'payload':local})
assert projection.restore(projected,tokens)=={'payload':local}
report={'schema':'independent-mining-identity-boundary-addendum-v1','disposition':'actual_native_wire_masks_known_cik_handle_no_wire_identity_violation_established','current_stage_sha256':hashlib.sha256(Path(stage.__file__).read_bytes()).hexdigest(),'request_path':str(requests[0]),'request_file_sha256':hashlib.sha256(requests[0].read_bytes()).hexdigest(),'request_reservation':stage.request_reservation(requests[0]),'original_source_identity':'The canonical Fact/read receipt contains the known CIK as local provenance; it is not opaque by itself. Existing whole-request reversible projection is the egress anonymity authority.','local_canonical_document_refs':local_handles,'actual_wire_document_refs':wire_handles,'known_identifiers_present_in_actual_wire':leaks,'existing_policy_mechanism':'_CaseIdentityProjection derives numeric CIK patterns from cik_<digits> aliases even with expand_aliases=False, and tokenizes the complete source handle at egress. No per-case alias or product modification was needed.','full1780_source_selection_matches_reference':True,'selected_fact_refs':[f.fact_ref for f in facts],'local_projection_inverse_equal':True,'production_inboxes':len(list(root.rglob('inbox/*.json'))),'fresh_model_answers':0,'external_API':0,'qualification':'The actual persisted native request proves egress masking for this source/handle. Pure existing projection.restore roundtrip was checked; no fresh/cached real model response roundtrip or broad anonymity-family closure is claimed.','reviewer_correction':'The reviewer initially called raw receipt CIK a proven wire leak before inspecting the actual whole-request projection. That conclusion was premature and corrected before any product/reference modification. Earlier final-review did not establish anonymity; this source-bound native evidence is the supplemental determination.'}
p=BASE/'independent/identity-boundary-addendum.json'
with p.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('local_canonical_document_refs','actual_wire_document_refs')},indent=2))
