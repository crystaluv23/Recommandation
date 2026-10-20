"""Independent read-only canonical/membership audit; never open a source store."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
P=Path(__file__).resolve().parent;BP=P/'assembly/bundle.json';EXPECTED='47406a0dd8e31eb35ae7ae6bfe7660f0669f8cbddcfe40b3cac171744d01a345'
def sha(raw):return hashlib.sha256(raw).hexdigest()
assert sha(BP.read_bytes())==EXPECTED
memo={};read_bindings={}
def read(b):
 path=Path(b['path']).resolve();key=(str(path),b['sha256'])
 assert not(path.name=='input_manifest.json' and 'minimal_rounds_v182_integrated' in str(path))
 if key not in memo:
  raw=path.read_bytes();assert sha(raw)==b['sha256'],str(path);memo[key]=json.loads(raw);read_bindings[str(path)]=b
 return memo[key]
B=json.loads(BP.read_bytes());stage=read(B['preappend_result']);projection=read(B['projection']);cases={r['case_id']:r for r in projection['cases']};base=read(B['base_inputs']);old=read(base['source_review']);root=Path(old['oracle_identity']['path']).resolve().parent
assert len(cases)==40 and len(old['records'])==658 and sum(r['verdict']=='admitted' for r in old['records'])==653
old_ids={r['document_id'] for r in old['records']}
T={};financial_expected={};retained_market=defaultdict(set)
for c in stage['outcomes']['financial']:
 normal=read(c['normalization']);ee={r['document_id']:r for r in normal['expected_products']};assert len(ee)==len(normal['expected_products'])
 assert set(ee)=={r['document_id'] for r in c['products']}
 for product in c['products']:
  key='financial|'+c['case_id']+'|'+product['document_id'];T[key]=('financial',c['case_id'],product);financial_expected[key]=ee[product['document_id']]
for c in stage['outcomes']['market']:
 T['market|'+c['case_id']+'|*']=('market',c['case_id'],c)
 for v in c['variants']:
  if v.get('complete_canonical_reconstruction'):retained_market[c['case_id']].add((v['original_record']['path'],v['original_record']['sha256']))
for c in stage['outcomes']['operating']:
 for t in c['targets']:T['operating|'+c['case_id']+'|'+t['accession']]=('operating',c['case_id'],t)
assert len(T)==907 and Counter(x[0] for x in T.values())=={'financial':842,'market':24,'operating':41}
assert set(T)==set(B['target_dispositions'])
links={k:set() for k in T};ids=set();family=Counter();profile=Counter();existing=Counter();insert=Counter();expected_paths=[];collisions=[];old_overlap=[];market_records=Counter();opkind=Counter()
namespaces=[p for p in root.iterdir() if p.is_dir()]
for candidate in B['candidates']:
 raw=read(candidate['document']);doc=RawInfoDocument.from_dict(raw);assert canonical_json_hash(doc.to_dict())==canonical_json_hash(raw)
 assert doc.document_id not in ids;ids.add(doc.document_id)
 if doc.document_id in old_ids:old_overlap.append(doc.document_id)
 keys=candidate['target_keys'];assert keys and len(keys)==len(set(keys));fams={T[k][0] for k in keys};sids={T[k][1] for k in keys};assert len(fams)==len(sids)==1;fam=next(iter(fams));sid=next(iter(sids));case=cases[sid]
 assert doc.company_id==case['company_id'] and doc.available_at<=__import__('datetime').datetime.fromisoformat(case['prediction_time'])
 family[fam]+=1;profile[candidate['proof_profile']]+=1
 for key in keys:links[key].add(doc.document_id)
 if fam=='financial':
  assert len(keys)==1;product=T[keys[0]][2];expected=financial_expected[keys[0]];assert not product['collision'] and product['profile_preverified']
  assert canonical_json_hash(raw)==expected['canonical_record_hash'] and doc.content_hash==expected['content_hash'] and candidate['document']==product['product']
  assert next(p['artifact'] for p in candidate['proofs'] if p['kind']=='sec_companyfacts_normalization')==next(c['normalization'] for c in stage['outcomes']['financial'] if c['case_id']==sid)
 elif fam=='market':
  marker=(candidate['document']['path'],candidate['document']['sha256'])
  if marker in retained_market[sid]:market_records['retained_exact_original']+=1
  else:assert candidate['document'] in B['additional_market_products'] and doc.company_id=='cik_0001681459';market_records['explicit_new_FTI']+=1
 else:
  assert all(T[k][2]['accession']==doc.metadata['accession_number'] for k in keys)
  selector=candidate['semantic_target'];assert selector['case_id']==sid and selector['accession']==doc.metadata['accession_number']
  if candidate['proof_profile']=='sec_filing_exhibit_response_v1':opkind['exhibit']+=1
  elif candidate['proof_profile']=='sec_filing_response_acceptance_v1':opkind['new_primary']+=1
  else:opkind['retained_original']+=1
 expected_path=root/doc.source_type/doc.company_id/(doc.document_id+'.json');assert expected_path.resolve().is_relative_to(root)
 expected_paths.append(str(expected_path))
 matches=[n/doc.company_id/(doc.document_id+'.json') for n in namespaces if (n/doc.company_id/(doc.document_id+'.json')).is_file()]
 if matches:
  existing[fam]+=1
  for path in matches:
   value=json.loads(path.read_bytes())
   if canonical_json_hash(value)!=canonical_json_hash(raw):collisions.append(str(path))
  assert expected_path in matches
 else:insert[fam]+=1
for key,disp in B['target_dispositions'].items():
 assert disp['reason'] and len(disp['candidate_ids'])==len(set(disp['candidate_ids'])) and set(disp['candidate_ids'])==links[key]
assert not old_overlap and not collisions and len(expected_paths)==len(set(expected_paths))==1123
assert family=={'financial':838,'market':242,'operating':43} and opkind=={'retained_original':29,'new_primary':8,'exhibit':6}
unknown={k:d for k,d in B['target_dispositions'].items() if not d['candidate_ids']};assert len(unknown)==6
assert Counter(T[k][0] for k in unknown)=={'financial':4,'market':1,'operating':1}
# Validate candidate proof artifacts and all actual evidence bindings, not historical code nested inside them.
for candidate in B['candidates']:
 for proof in candidate['proofs']:
  read(proof['artifact'])
  if 'raw_response' in proof:
   b=proof['raw_response'];raw=Path(b['path']).read_bytes();assert sha(raw)==b['sha256'];read_bindings[b['path']]=b
 if 'semantic_review' in candidate:read(candidate['semantic_review'])
for b in B['evidence_bindings']:
 raw=Path(b['path']).read_bytes();assert sha(raw)==b['sha256'];read_bindings[b['path']]=b
assert sha(BP.read_bytes())==EXPECTED and not (P/'stage').exists()
result={'schema_version':'bounded-actual-bundle-preappend-independent-review-v1','bundle':{'path':str(BP),'sha256':EXPECTED},'fixed_cases':40,'target_counts':dict(Counter(x[0] for x in T.values())),'candidate_counts':dict(family),'profiles':dict(profile),'operating_candidate_roles':dict(opkind),'market_candidate_origin':dict(market_records),'old_base_rows':658,'old_base_admitted':653,'old_base_id_overlap':old_overlap,'same_id_canonical_conflicts':collisions,'existing_exact_canonical_candidates':dict(existing),'predicted_new_global_originals':dict(insert),'predicted_total_new_originals':sum(insert.values()),'expected_canonical_insert_paths_count':len(expected_paths),'expected_canonical_insert_path_set_sha256':canonical_json_hash(sorted(expected_paths)),'unknown_dispositions':unknown,'checked_actual_source_artifact_bindings':len(read_bindings),'source_artifact_inventory_sha256':canonical_json_hash(sorted(read_bindings.values(),key=lambda b:b['path'])),'blocking_findings':[],'actual_stage_absent':True,'limits':['Pure read-only artifact/canonical/PIT/membership/path check; no native materializer/prepare/execute/Store/GET or global mutation.','Assembly previous _qualify is its actual producer evidence; independent checks here do not claim a second whole native-profile execution.','Historical code hashes inside completed artifacts are retained provenance, not compared against current source.','Remaining GPRE4 metadata conflicts, one nonempty-split market family and wrongtypedFTIinterim remain unknown; no negative observations or denominator deletion.','Oldbase preservation and exact append/view/worker/2x720/40BasicInfo are future execution obligations, not established by bundle presence.']}
p=P/'actual-bundle-preappend-review.json';p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'path':str(p),'sha256':sha(p.read_bytes()),'candidates':dict(family),'existing':dict(existing),'new':dict(insert),'source_bindings_checked':len(read_bindings),'all_passed':True}))
