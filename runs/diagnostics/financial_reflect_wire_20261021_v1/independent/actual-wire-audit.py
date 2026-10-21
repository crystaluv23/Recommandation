"""Stdlib-only audit of saved native egress; no helper/capture or source mutation."""
from pathlib import Path
from datetime import datetime
import hashlib,json
R=Path('/Users/l/Project/Recommandation');B=R/'runs/diagnostics/financial_reflect_wire_20261021_v1';D=B/'driver';I=B/'independent';E=D/'execution-v3'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
canon=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'))
equal=lambda a,b:canon(a)==canon(b)
expectpath=I/'pre-capture-expectations.json';assert sha(expectpath)=='d23d09d8036575534d6d71dacfade8d4fe4be6c0726b816bb12d415531568754';gold=read(expectpath)
contract=read(D/'contract-v3.json');ready=read(E/'request-ready.json');result=read(E/'result.json')
assert sha(D/'capture-native-config.py')=='48b107515437e877fcb837ac4890e5b94720de707e87c99fb933b39ba9382093'
assert sha(D/'contract-v3.json')=='450f3e947181ffb186a6b99b365e17a82d3b47ca9690f90d747c5bddabc4a3ba'
journals=list((E/'requests').glob('*.json'));assert len(journals)==1
journal=read(journals[0]);wire=journal['request'];key=hashlib.sha256(canon(wire).encode()).hexdigest()
assert key==journal['request_hash']==ready['request_hash']==journals[0].stem
assert Path(ready['request_path']).resolve()==journals[0].resolve()
payload=read(E/'pre-egress.json')['payload'];actual=json.loads(next(m['content'] for m in wire['messages'] if m['role']=='user'))
assert equal(payload,actual)
assert wire['stage']=='research_controller_reflect' and wire['stage_contract']['allow_outcomes'] is False
assert actual['evaluation_context']['prediction_time']==gold['case']['prediction_time']
assert actual['research_state']==read(I/'explicit-carrier-amendment.json')['expected_state_carrier']
assert actual['executed_selection_intents']==[] and actual['need_transition_contract']['required_disposition_need_indices']==[]
assert actual['validation_feedback'] is None and actual['signal_research_status']=={}
rows=actual['signal_batch'];assert len(rows)==6 and [x['signal_ref'] for x in rows]==gold['fixed_scope']['supplied_order']
assert equal(actual['signal_evidence_ref_catalog'],[r['evidence_ref_catalog'] for r in gold['expected_rows']])
checked=[]
for row,expected in zip(rows,gold['expected_rows'],strict=True):
 assert set(row)=={'signal_ref','signal_id','version','state','evidence','status','exact_claim_if_adopted','measurement_context'}
 for keyname in ('signal_ref','signal_id','version','state','exact_claim_if_adopted'):assert equal(row[keyname],expected[keyname]),(expected['signal_ref'],keyname)
 assert row['status']=={'coverage':expected['coverage']}
 assert equal(row['evidence'],expected['wire_evidence'])
 context=row['measurement_context'];assert equal(context['numeric_measurement'],expected['numeric_measurement'])
 assert equal(context['source_observations'],expected['source_observations'])
 assert context['deferred_observation_count']==0 and context['categorical_value_is_not_stock_direction'] is True
 assert context['period_rule']==gold['native_projection_contract']['period_rule']
 assert set(context)=={'numeric_measurement','source_observations','deferred_observation_count','categorical_value_is_not_stock_direction','period_rule'}
 for group in ('supporting','counter'):
  for ev in row['evidence'][group]:assert set(ev)=={'available_at','evidence_index'} and datetime.fromisoformat(ev['available_at'])<=datetime.fromisoformat(gold['case']['prediction_time'])
 checked.append({'signal_ref':row['signal_ref'],'exact_field_match':True,'source_observations':len(context['source_observations'])})
assert sum(x['source_observations'] for x in checked)==11
batchpath=R/'runs/diagnostics/current_financial_apply_20261021_v1/native/stage/native-batch.json';batch=read(batchpath)
assert sha(batchpath)=='ad71e66be7ba9c1572b31d79c9cf272f2d8d50fe8f72fd425562d2775350b769'
for row in gold['expected_rows']:assert equal(batch['document_fingerprints'][row['signal_ref']],row['source_document_fingerprints'])
snapshot=Path(contract['snapshot']['root']);manifest=read(snapshot/'reviewed_snapshot.json');assert sha(snapshot/'reviewed_snapshot.json')==contract['snapshot']['manifest_sha256']
source_index={x['document_id']:x for x in manifest['documents']};loaded={}
def source(ident):
 if ident not in loaded:
  s=source_index[ident];p=(snapshot/s['path']).resolve();assert p.is_relative_to(snapshot.resolve()) and sha(p)==s['sha256']
  doc=read(p);assert doc['document_id']==ident and hashlib.sha256(doc['content'].encode()).hexdigest()==doc['content_hash']
  assert doc['company_id']==gold['case']['company_id'] and datetime.fromisoformat(doc['available_at'])<=datetime.fromisoformat(gold['case']['prediction_time'])
  loaded[ident]=(doc,p)
 return loaded[ident]
# Fingerprints denote whole selected source set, not extra wire fields or extra evidence counts.
for expected in gold['expected_rows']:
 for fp in expected['source_document_fingerprints']:
  ident,h=fp.rsplit(':',1);doc,p=source(ident);assert doc['content_hash']==h
mapping=read(E/'mapping.json')['all_nine_operand_mapping'];by_tuple={(x['signal_ref'],x['evidence_group'],x['evidence_index']):x for x in mapping};assert len(by_tuple)==len(mapping)==21
actual_evidence=0;selected_evidence=0
for result_index,raw in enumerate(batch['results']):
 ref=raw['signal_id']+':v'+str(raw['version'])
 for group in ('supporting','counter'):
  for index,e in enumerate(raw['evidence'][group]):
   doc,p=source(e['document_id']);literal=e['exact_span'];offset=doc['content'].find(literal);assert offset>=0
   assert datetime.fromisoformat(e['timestamp'])==datetime.fromisoformat(doc['available_at'])
   m=by_tuple[(ref,group,index)]
   assert m['document_id']==doc['document_id'] and m['content_hash']==doc['content_hash'] and m['file_sha256']==sha(p)
   assert m['offset']==offset and m['literal_sha256']==hashlib.sha256(literal.encode()).hexdigest()
   assert m['in_selected_six']==(result_index in gold['fixed_scope']['selected_original_indices'])
   assert all(m[k] is True for k in ('whole_literal_reachable','source_file_binding_equal','company_equal','available_by_cutoff','evidence_timestamp_by_cutoff','evidence_timestamp_equals_source'))
   actual_evidence+=1;selected_evidence+=int(m['in_selected_six'])
assert (actual_evidence,selected_evidence)==(21,11)
original_result=read(R/'runs/diagnostics/current_financial_apply_20261021_v1/native/stage/result.json')
assert original_result['fixed_denominator']==9 and original_result['passed_unique']==6 and original_result['period_policy_ambiguous']==2 and original_result['status']=='completed_acceptance_failed'
revgrowth=next(r for r in original_result['comparisons'] if r['signal_ref']=='revenue_growth_yoy:v3')
assert revgrowth['passed'] is False and revgrowth['checks']['whole_operand_literals'] is False
wire_text=json.dumps(wire,ensure_ascii=False)
for token in contract['identity'].values():assert token not in wire_text
for token in (str(expectpath),sha(expectpath),'expected_rows','sufficient_unique','passed_unique','whole_operand_literals','period_policy_ambiguous','pre-capture-expectations.json'):
 assert token not in wire_text,token
for ref in gold['fixed_scope']['not_supplied_refs']:assert ref not in wire_text
assert not any(k in actual for k in ('oracle','comparisons','expected','witness','basic_info'))
message_bytes=len(json.dumps(wire['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
assert message_bytes==ready['messages_utf8_bytes']==28318
assert wire['max_output_tokens']==ready['output_reservation']==8000
assert message_bytes+wire['max_output_tokens']==ready['logical_reservation']==36318<=ready['request_limit']==131072
beforeafter=read(E/'bindings-before-after.json');bound={b['path']:b['sha256'] for b in contract['source_bindings']+contract['code_bindings']};assert len(bound)==60 and beforeafter['before']==beforeafter['after']==bound
assert all(sha(path)==digest for path,digest in bound.items())
for b in gold['source_bindings']:assert sha(b['path'])==b['sha256']
preflight=read(I/'third-candidate-preflight-review.json')
for f in preflight['first_two_failures']:
 root=Path(f['root']);files=[{'path':str(p),'sha256':sha(p)} for p in sorted(root.rglob('*')) if p.is_file()];assert files==f['files'];assert not list((root/'requests').glob('*.json'))
assert result['counts']=={'pre_egress_calls':1,'request_ready':1} and result['forbidden_calls']==[]
assert result['model_calls']==result['responses']==result['role_dispatches']==0
assert not any(p for p in E.rglob('*') if p.is_file() and any(part in {'inbox','outbox','receipts','responses','response_cache'} for part in p.parts))
assert result['source_denominator']==9 and result['selected_results']==6 and result['operand_rows']==21
report={'status':'PASS_ACTUAL_SIX_RESULT_NATIVE_MASKED_REFLECT_WIRE_ONLY','source_expectations_sha256':sha(expectpath),'native_request_hash':journal['request_hash'],'six_row_checks':checked,'selected_operands':11,'all_original_operand_literals_reachable':21,'selected_fingerprint_documents_verified':len(loaded),'canonical_budget':{'messages_utf8_bytes':message_bytes,'output_reservation':8000,'total':36318,'limit':131072},'boundary':{'source_attempts':3,'first_two_harness_failures_retained':True,'source_request_journals_total':1,'pre_egress':1,'request_ready':1,'responses':0,'models':0,'dispatches':0,'forbidden':0,'synthetic_temporary_controls_not_counted_as_actual_source_journals':True},'privacy':{'identity_tokens_absent':True,'private_expectations_or_verdict_absent':True,'excluded3_refs_not_supplied':True,'noBasicInfo_or_acceptedprior_claim':True},'frozen_bindings_current_equal':60,'original_nine_acceptance_unchanged':{'strict_passes':6,'sufficient_unique':7,'fixed_denominator':9,'period_unknown':2,'revenue_growth_prior_literal_allowlist_failure':True,'status':'completed_acceptance_failed'},'scope':'All audit operations are stdlib reads/hashes/parsing. No capture rerun, native helper, Store/Engine, model, GET, labels, source append, H_init, F7 semantic acceptance or Predictor. Native batch intentionally substitutes canonical claim/measurement_context for whole-literal text; source observations preserve all11 operand identities. Literal reachability of21 is provenance, not relaxation of the frozen oracle prior literal allowlist.','evidence_bindings':[{'path':str(p),'sha256':sha(p)} for p in (expectpath,I/'explicit-carrier-amendment.json',I/'third-candidate-preflight-review.json',D/'contract-v3.json',D/'capture-native-config.py',E/'result.json',E/'pre-egress.json',E/'request-ready.json',E/'mapping.json',E/'bindings-before-after.json',journals[0],Path(__file__))]}
p=I/'actual-wire-review.json';p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'review_sha256':sha(p),'six_rows':6,'source_observations':11,'original_literals':21,'frozen_bindings':60,'logical_reservation':36318,'status':report['status']}))
