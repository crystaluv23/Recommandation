"""Independent synthetic offline codec controls; no production stages or sources."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.mining_role_model import _MiningReferenceHandles
from stock_opportunity_agent.research.evolution_transport import _CaseIdentityProjection

ROOT = Path(__file__).resolve().parent
CODE = Path('src/stock_opportunity_agent/research/mining_role_model.py')

def graph(offset=0):
    return {'known_fact_refs': [f'fact-{i + offset:016x}' for i in range(400)],
            'known_relation_refs': [f'relation-{i + offset:016x}' for i in range(100)]}

results=[]
def run(name, fn):
    try:
        fn()
    except Exception as exc:
        results.append({'case':name,'passed':False,'error_type':type(exc).__name__,'error':str(exc)})
    else:
        results.append({'case':name,'passed':True})

def equal(a,b):
    assert a == b, f'expected={b!r}; actual={a!r}'

with patch('socket.socket.connect', side_effect=AssertionError('network prohibited')):
    v=graph(); f=v['known_fact_refs'][0]; r=v['known_relation_refs'][0]
    c=_MiningReferenceHandles(v); fa=c.forward[f]; ra=c.forward[r]
    def opaque(key,original):
        view={**v,key:original}; codec=_MiningReferenceHandles(view)
        equal(codec.payload(view)[key],original)
    run('memory_original_content_reference_fields_unchanged',lambda: opaque('meta_memory_disclosures',[{'content':{'fact_ref':f,'relation_refs':[r],'ref':f}}]))
    run('retained_catalog_memory_original_unchanged',lambda: opaque('catalog_observations',{'items':[{'result':{'items':[{'content':{'fact_ref':f}}]}}]}))
    run('signal_spec_original_reference_key_unchanged',lambda: opaque('signal_catalog',[{'original':{'spec':{'definition':{'fact_ref':f}}}}]))
    run('structured_literal_value_unchanged',lambda: equal(c.payload({**v,'computed_statistics':{'items':[{'operands':[{'fact_ref':f,'value':{'fact_ref':f}}]}]}})['computed_statistics']['items'][0]['operands'][0]['value'],{'fact_ref':f}))
    run('semantic_threshold_value_unchanged',lambda: opaque('candidate',{'measurement':{'predicate':{'threshold':{'field':'fact_ref','value':f}}}}))
    run('all_scalar_literal_fields_unchanged',lambda: opaque('literal',{'value':f,'body':f,'rationale':[f],'raw_span':f,'readable_text':f,'exact_span':f,'description':f,'semantic_condition':f}))
    run('ordinary_nested_reference_roundtrip',lambda: equal(c.transform(c.transform({'relation':{'relation_ref':r,'fact_refs':[f]},'fact_ref':f}),restore=True),{'relation':{'relation_ref':r,'fact_refs':[f]},'fact_ref':f}))
    run('typed_patch_reference_and_prose_distinguished',lambda: equal(c.transform({'operations':[{'op':'replace','path':'candidate.evidence_refs[0]','value':fa},{'op':'replace','path':'rationale[0]','value':fa}]},restore=True),{'operations':[{'op':'replace','path':'candidate.evidence_refs[0]','value':f},{'op':'replace','path':'rationale[0]','value':fa}]}))
    run('typed_patch_reference_exact_permissions',lambda: equal(c.transform(c.transform({'identity_guards':[{'field':'fact_ref','value':f}],'allowed_operations':[{'path':'candidate.evidence_refs','exact_value':f}],'exact_append_limits':{'candidate.evidence_refs':{f:1}}}),restore=True),{'identity_guards':[{'field':'fact_ref','value':f}],'allowed_operations':[{'path':'candidate.evidence_refs','exact_value':f}],'exact_append_limits':{'candidate.evidence_refs':{f:1}}}))
    def rejects(value):
        try:c.transform(value,restore=True)
        except ValidationError:return
        raise AssertionError('accepted invalid alias')
    run('unknown_alias_rejected',lambda: rejects({'fact_ref':c.prefix+'f99999'}))
    run('wrong_kind_alias_rejected',lambda: rejects({'fact_ref':ra}))
    run('duplicate_decoded_dictionary_key_rejected',lambda: rejects({'evidence_refs':{fa:1,f:2}}))
    other=_MiningReferenceHandles(graph(10000))
    run('same_shape_distinct_graph_cache_discriminator',lambda: equal(c.scope_hash != other.scope_hash,True))
    def identity_roundtrip():
        payload=c.payload(v)
        projection=_CaseIdentityProjection((c.prefix.rstrip(':'),),'','',expand_aliases=False)
        projected,tokens=projection.project(payload)
        alias=projected['known_fact_refs'][0]
        raw={'fact_ref':alias,'rationale':['preserve']}
        restored=projection.restore(raw,tokens)
        equal(c.transform(restored,restore=True),{'fact_ref':f,'rationale':['preserve']})
    run('native_identity_projection_then_handle_inverse',identity_roundtrip)
    def no_prefix_assumption():
        view={'known_fact_refs':['opaque-fact-'+f'{i:016x}' for i in range(400)],'known_relation_refs':[]}
        codec=_MiningReferenceHandles(view); ref=view['known_fact_refs'][0]
        equal(codec.transform({'fact_ref':codec.forward[ref]},restore=True),{'fact_ref':ref})
    run('typed_index_membership_not_identifier_spelling',no_prefix_assumption)

# Extended independent controls retain both first-result files.
with patch('socket.socket.connect', side_effect=AssertionError('network prohibited')):
    run('arbitrary_semantic_field_value_is_literal',lambda: equal(c.transform({'semantic_payload':{'field':'fact_ref','value':f}}),{'semantic_payload':{'field':'fact_ref','value':f}}))
    run('nested_fact_value_keeps_all_reference_keys',lambda: equal(c.transform({'operands':[{'fact_ref':f,'value':{'fact_ref':f,'evidence_refs':[r],'nested':{'ref':f}}}]})['operands'][0]['value'],{'fact_ref':f,'evidence_refs':[r],'nested':{'ref':f}}))
    measurement={'predicate':{'threshold':{'field':'fact_ref','value':fa},'evidence_refs':[fa]},'nested':{'fact_ref':fa}}
    run('typed_patch_measurement_object_stays_literal',lambda: equal(c.transform({'operations':[{'op':'replace','path':'candidate.measurement','value':measurement}]},restore=True)['operations'][0]['value'],measurement))
    run('typed_patch_candidate_restores_citations_preserves_measurement',lambda: equal(c.transform({'operations':[{'op':'replace','path':'candidate','value':{'evidence_refs':[fa,ra],'measurement':measurement}}]},restore=True)['operations'][0]['value'],{'evidence_refs':[f,r],'measurement':measurement}))
    for scope in ('memory','signals','backlog'):
        result={'sources':[{'snapshot':{'fact_ref':f,'relation_ref':r,'evidence_refs':[f,r]},'ref':f}],'arbitrary':{'fact_refs':[f]}}
        run('catalog_'+scope+'_noncontent_original_fields_preserved',lambda scope=scope,result=result: equal(c.payload({**v,'last_action_result':{'action':'inspect_catalog','scope':scope,'result':result}})['last_action_result']['result'],result))
    result={'items':[{'capability_contract':{'fact_ref':f,'relation_refs':[r]}}]}
    run('default_signal_catalog_none_scope_preserves_original_card',lambda: equal(c.payload({**v,'last_action_result':{'action':'inspect_catalog','scope':None,'result':result}})['last_action_result']['result'],result))
    manifest={'source_contract':{'fact_ref':f,'relation_ref':r}}
    run('inspect_manifest_last_result_preserves_semantic_contract',lambda: equal(c.payload({**v,'last_action_result':{'action':'inspect_manifest','scope':None,'result':manifest}})['last_action_result']['result'],manifest))

report={'code_sha256':hashlib.sha256(CODE.read_bytes()).hexdigest(),'passed':sum(x['passed'] for x in results),'failed':sum(not x['passed'] for x in results),'results':results,'network':'socket connect prohibited','production_mutations':0,'production_stage_reentry':0}
name='retest-'+report['code_sha256'][:12]+'.json'
assert not (ROOT/name).exists(), 'never overwrite earlier independent results'
(ROOT/name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
