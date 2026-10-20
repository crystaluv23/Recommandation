"""Actual bound GPRE response, temporary native profile; no actual source admission."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import hashlib,json,tempfile
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
from stock_opportunity_agent.data import reviewed_snapshot as r
from stock_opportunity_agent.data.raw_info import RawInfoStore,RawInfoDocument,RawInfoOracle
from stock_opportunity_agent.data.sec_company_facts import materialize_company_fact_documents,LEGACY_IDENTITY_POLICY,CAPTURE_IDENTITY_POLICY
ROOT=Path('/Users/l/Project/Recommandation');OUT=Path(__file__).resolve().parent
BASE=ROOT/'runs/diagnostics/reviewed_frozen_source_snapshot_20261020_v1/stage/cases/cik_0001309402:20250530'
N=BASE/'normalization.json';oldnorm=json.loads(N.read_text());PROFILE='sec_companyfacts_capture_filed_next_utc_day_v1'
def bh(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def readbind(b):assert bh(b['path'])==b;return json.loads(Path(b['path']).read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,sort_keys=True,ensure_ascii=False)+'\n');return bh(p)
assert bh(N)['sha256']=='ec8b8004b33fb651bf7d0c1ce4b026751267fdab1a2705e177a9bafed8488dc1'
cache=readbind(oldnorm['source_cache']);oldraw=readbind(oldnorm['raw_response'])
args={'item':oldnorm['item'],'selection':oldnorm['selection'],'provenance':oldnorm['provenance'],'retrieved_at':datetime.fromisoformat(oldnorm['normalized_at'])}
legacy,_=materialize_company_fact_documents(cache['body'],**args,identity_policy=LEGACY_IDENTITY_POLICY)
default,_=materialize_company_fact_documents(cache['body'],**args)
capture,_=materialize_company_fact_documents(cache['body'],**args,identity_policy=CAPTURE_IDENTITY_POLICY)
assert len(legacy)==len(capture)==57 and [d.to_dict() for d in legacy]==[d.to_dict() for d in default]
for x,y in zip(legacy,capture):
 frozen=json.loads((BASE/'products'/(x.document_id+'.json')).read_text())
 assert digest(x.to_dict())==digest(frozen)
 assert {k:v for k,v in x.to_dict().items() if k!='document_id'}=={k:v for k,v in y.to_dict().items() if k!='document_id'}
assert len({d.document_id for d in capture})==57 and not ({d.document_id for d in legacy}&{d.document_id for d in capture})
suffixes={'0001309402-24-000092:aa05ed7e72b76d79','0001309402-24-000114:b0c4c525055d1268','0001309402-24-000129:cedad9eff3b39e03','0001309402-25-000089:eab48ba69f5ebb47'}
pairs=[(x,y) for x,y in zip(legacy,capture) if ':'.join(x.document_id.split(':')[2:]) in suffixes];assert len(pairs)==4
inputs=[bh(N),oldnorm['source_cache'],oldnorm['raw_response']]
with tempfile.TemporaryDirectory() as td:
 t=Path(td).resolve();oracle=t/'oracle';RawInfoOracle.load_or_create(oracle);store=RawInfoStore(oracle)
 for d in capture:store.append(d)
 originals={}
 for path in oracle.rglob('*.json'):
  value=json.loads(path.read_text())
  if path.name=='oracle.json':oid=bh(path)
  elif 'document_id' in value:originals[value['document_id']]=bh(path)
 norm=deepcopy(oldnorm);norm.update(schema_version='sec-companyfacts-normalization-v2',normalizer_profile=PROFILE,identity_policy=CAPTURE_IDENTITY_POLICY,
  expected_products=[{'document_id':d.document_id,'content_hash':d.content_hash,'canonical_record_hash':digest(d.to_dict())} for d in capture])
 normal=t/'normalization.json';normalbind=write(normal,norm)
 proofs=[{'kind':k,'artifact':b} for k,b in [('sec_companyfacts_cache',oldnorm['source_cache']),('sec_companyfacts_raw_response',oldnorm['raw_response']),('sec_companyfacts_normalization',normalbind)]]
 rows=[{'document_id':d.document_id,'company_id':d.company_id,'content_hash':d.content_hash,'original_record':originals[d.document_id],
  'verdict':'admitted','reason':'Independent temporary full reconstruction control only.','proof_profile':PROFILE,
  'reviewed_available_at':d.available_at.isoformat(),'proofs':deepcopy(proofs)} for _,d in pairs]
 review={'schema_version':'reviewed-raw-info-snapshot-v1','oracle_identity':oid,'scope':{'as_of':norm['selection']['available_at_through'],
  'company_ids':[norm['item']['company_id']],'acquisition_allowed':False},'records':rows}
 def save(label):
  for row in review['records']:
   for proof in row['proofs']:
    if proof['kind']=='sec_companyfacts_normalization':proof['artifact']=bh(normal)
  review['manifest_hash']=digest({k:v for k,v in review.items() if k!='manifest_hash'});p=t/(label+'.json');write(p,review);return p
 positive=r.materialize_reviewed_snapshot(save('positive'),t/'view')
 first=r.open_raw_info_store(positive['root'],reviewed_snapshot=positive)
 assert len(first.documents)==4 and [d.to_dict() for d in first.documents]==sorted([d.to_dict() for _,d in pairs],key=lambda d:d['document_id'])
 assert first.snapshot().documents==first.documents and r.open_raw_info_store(positive['root'],reviewed_snapshot=positive).documents==first.documents
 assert all(first.append(d) is False for _,d in pairs)
 # Full denominator57 is mandatory even for the4-record admitted subset.
 reduced=deepcopy(norm);reduced['expected_products']=[e for e in norm['expected_products'] if e['document_id'] in {d.document_id for _,d in pairs}];write(normal,reduced)
 try:r.materialize_reviewed_snapshot(save('bad-subset-denominator'),t/'bad-subset')
 except r.ReviewedSourceRejected:denominator_rejected=True
 else:raise AssertionError('4-only expected set accepted')
 write(normal,norm)
 review['records'][0]['proof_profile']='sec_companyfacts_filed_next_utc_day_v1'
 try:r.materialize_reviewed_snapshot(save('bad-recipe'),t/'bad-recipe')
 except r.ReviewedSourceRejected:profile_memo_rejected=True
 else:raise AssertionError('legacy profile substituted capture recipe')
 review['records'][0]['proof_profile']=PROFILE
 # Recorded whole response remains a legacy ID; it is a proof only and is not in the admitted view.
 assert oldraw['document_id'].startswith('sec_edgar:') and oldraw['document_id'] not in {d.document_id for d in first.documents}
 # Actual4 original records remain canonical conflicts under legacy reconstruction, not silently washed.
 legacy_conflicts=[]
 proofmap={p['kind']:(p,readbind(p['artifact'])) for p in proofs}
 # Restore v2 norm binding before using independent explicit legacy proof maps.
 legacy_norm_proof={'kind':'sec_companyfacts_normalization','artifact':bh(N)}
 oldproofs={'sec_companyfacts_cache':({'artifact':oldnorm['source_cache']},cache),'sec_companyfacts_raw_response':({'artifact':oldnorm['raw_response']},oldraw),
  'sec_companyfacts_normalization':(legacy_norm_proof,oldnorm)}
 for legacy_product,captured in pairs:
  actualpath=ROOT/'runs/cold_start/data/global-raw-info-oracle-v1/sec_company_facts/cik_0001309402'/(legacy_product.document_id+'.json')
  actual=json.loads(actualpath.read_text());inputs.append(bh(actualpath))
  assert actual['content']==legacy_product.content and actual['published_at']==legacy_product.to_dict()['published_at'] and actual['available_at']==legacy_product.to_dict()['available_at']
  assert digest(actual)!=digest(legacy_product.to_dict())
  try:r._verify_companyfacts_document(RawInfoDocument.from_dict(actual),{'proof_profile':'sec_companyfacts_filed_next_utc_day_v1','reviewed_available_at':actual['available_at']},oldproofs,datetime.fromisoformat(norm['selection']['available_at_through']),{})
  except r.ReviewedSourceRejected:legacy_conflicts.append(legacy_product.document_id)
  else:raise AssertionError('old metadata conflict silently admitted')
 assert len(legacy_conflicts)==4
for b in inputs:assert bh(b['path'])==b
out={'verdict':'PASS_bounded_actual57_temp_profile','full_reconstructed_products':57,'legacy_default_and_explicit_exact_frozen57':True,'new_capture_same_record_except_ID':57,
 'admitted_temporary_subset':4,'complete_expected57_required_reduced4_rejected':denominator_rejected,'legacy_profile_capture_recipe_mix_rejected':profile_memo_rejected,
 'legacy_raw_response_proof_unchanged_no_repack':oldnorm['raw_response'],'temporary_materialize_restart_snapshot4_exact':True,'temporary_append_recorded_replay_false':True,
 'actual_old_4_metadata_conflicts_still_rejected':legacy_conflicts,'input_bindings_before_after_equal':inputs,
 'code_bindings':[bh(ROOT/'src/stock_opportunity_agent/data'/n) for n in ('raw_info.py','sec_company_facts.py','acquisition.py','backfill.py','reviewed_snapshot.py')],
 'scope':'Read-only actual GPRE cache/raw/57 original normalized products and4 old global records. All new records/normalization/view were temporary only. No actual source qualification/admission/global append, GET, models, labels, prepare or historical-stage resume.',
 'limits':['No independent fact/coverage/research gain from duplicate capture provenance.','This reader reconstruction is not source signature authentication or primary-filing audit.']}
(OUT/'profile-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
