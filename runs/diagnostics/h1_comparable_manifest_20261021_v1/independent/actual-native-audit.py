"""Stdlib-only final audit; never imports product or reruns the native catalog."""
import hashlib
import json
from pathlib import Path
REPO = Path('/Users/l/Project/Recommandation')
BASE = REPO/'runs/diagnostics/h1_comparable_manifest_20261021_v1'
HERE = BASE/'independent'
sha = lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p:json.loads(Path(p).read_text())
script=BASE/'root/native_catalog.py'; planpath=BASE/'root/native-bindings.json'; resultpath=BASE/'root/native/result.json'
assert sha(script)=='6c9d2dae7c22db66ab099954c658646166ad3a96e3d57ed7ccbec17863fb8a75'
assert sha(planpath)=='7e52a97d8d33a914678f43e613040a3bce919085ad01b6901a7fbeb63d9d775a'
plan=read(planpath); result=read(resultpath)
assert len(plan['bindings'])==1789
assert result['bindings_before']==result['bindings_after']==plan['bindings']
assert all(sha(path)==digest for path,digest in plan['bindings'].items())
assert read(BASE/'root/native/started.json')=={'script_sha256':sha(script)}
assert {p.name for p in (BASE/'root/native').iterdir()}=={'started.json','result.json'}
assert result['status']=='completed_native_value_free_catalog_observation' and result['forbidden_calls']==0
inventory=read(REPO/'runs/diagnostics/mining_positive_frontier_20261021_v1/oracle/static-inventory.json')
metadata=[{k:row[k] for k in ('case_id','case_ref','cutoff')} for row in inventory['dev8']]
assert len(metadata)==8 and result['case_metadata']==metadata
assert len({r['case_ref'] for r in metadata})==len({r['case_id'] for r in metadata})==8
assert result['old_catalog']==inventory['actual_native_measurable_manifest']
old,new=result['old_catalog'],result['new_catalog']
key=lambda r:tuple(r[x] for x in ('taxonomy','concept','source_display_name','unit'))
assert old['cohort_case_count']==new['cohort_case_count']==8
assert len(old['structured_financial_concepts'])==len(new['structured_financial_concepts'])==24
oldrows={key(r):r for r in old['structured_financial_concepts']};newrows={key(r):r for r in new['structured_financial_concepts']}
assert len(oldrows)==len(newrows)==24 and oldrows==newrows
assert [key(r) for r in old['structured_financial_concepts']]==[key(r) for r in new['structured_financial_concepts']]
assert {k:v for k,v in old.items() if k!='coverage_note'}=={k:v for k,v in new.items() if k!='coverage_note'}
assert old['coverage_note']!=new['coverage_note']
allowed={'taxonomy','concept','source_display_name','unit','case_count','cases_with_comparable_records'}
for row in newrows.values():
 assert set(row)==allowed
 assert type(row['case_count']) is type(row['cases_with_comparable_records']) is int
 assert 0<=row['cases_with_comparable_records']<=row['case_count']<=8
serialized=json.dumps(new)
for row in metadata:
 assert row['case_id'] not in serialized and row['case_id'].split(':')[0] not in serialized and row['case_ref'] not in serialized
review={
 'status':'PASS_ACTUAL_SINGLE_NATIVE_DETERMINISTIC_CATALOG_CONNECTION_NO_OBSERVED_COUNT_GAIN',
 'bindings_verified_current':1789,
 'actual_metadata_count':8,
 'catalog_comparison':{'key_fields':['taxonomy','concept','source_display_name','unit'],'members':24,'same_members':True,'same_order':True,'all_case_and_comparable_counts_unchanged':True,'only_top_level_change':'coverage_note','narrative_and_price_counts_unchanged':True},
 'privacy':'Runtime receiver used label-free case_id/ref/cutoff whitelist; no issuer/ref in value-free output catalog. Local audit metadata intentionally retains authorized identity fields; no outcome-bearing inputs or LabelStore were opened by this audit.',
 'evidence':{'script_sha256':sha(script),'plan_sha256':sha(planpath),'result_sha256':sha(resultpath),'started_sha256':sha(BASE/'root/native/started.json'),'audit_sha256':sha(Path(__file__))},
 'scope':'This audit uses only stdlib JSON/hash reads. No helper, Store/Engine constructor, role, model, GET, Signal, source write or native rerun. Native script records forbidden_calls=0 and exactly one unbound call in reviewed source.',
 'limits':['Actual dev8 catalog membership and all counts did not increase; synthetic counters establish repaired distinctions, not an observed corpus capability gain.','No fresh LLM catalog consumption, complete Mining, unique scalar measurement or independent research benefit is established.','Legacy EvidenceFact namespace falsepair remains open pending explicit user design decision.','1789 direct frozen records remain exact; recursive source qualification was performed by existing native reviewed reader, not independently rebuilt here.']}
p=HERE/'actual-native-review.json';p.write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps({'status':review['status'],'review_sha256':sha(p),'bindings':1789,'metadata':8,'rows':24,'changed_counts':0}))
