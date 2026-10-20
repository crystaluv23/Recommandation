"""Verify the same six actual exhibits with final reader; no stores or acquisition."""
from pathlib import Path
from datetime import datetime
import hashlib,json
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data import reviewed_snapshot as reader
from stock_opportunity_agent.data.reviewed_snapshot import _read_bound,_read_bound_bytes
from diagnose_reviewed_frozen_source_completion import _semantic
P=Path(__file__).resolve().parent
EXPECTED='12fcc4307e7252d88377ec5b0f3b3c185502a44081058cea90e746e9bdd25f84'
def bound(path):return {'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
assert bound(Path(reader.__file__))['sha256']==EXPECTED
initial_path=P/'exhibit-six-native-initial-probe.json';draft=json.loads(initial_path.read_bytes());checks=[]
for candidate,prior in zip(draft['candidate_drafts'],draft['native_checks'],strict=True):
 doc=RawInfoDocument.from_dict(_read_bound(candidate['document'])[1]);proofs={p['kind']:(p,_read_bound(p['artifact'])[1]) for p in candidate['proofs']}
 reader._verify_sec_response_document(doc,{'reviewed_available_at':doc.available_at.isoformat()},proofs,datetime.fromisoformat(prior['actual_cutoff']),{},{},exhibit=True)
 _semantic(candidate,doc,candidate['semantic_target']['case_id'])
 checks.append({'receipt_name':prior['receipt_name'],'document_id':doc.document_id,'native_profile':'passed','thin_semantic_body_target':'passed','available_at':doc.available_at.isoformat(),'actual_cutoff':prior['actual_cutoff']})
prior_fragments=json.loads((P/'source-final-candidate-fragments.json').read_bytes());evidence={}
def add(binding):
 path=Path(binding['path']);assert bound(path)==binding;evidence[binding['path']]=binding
for b in prior_fragments['evidence_bindings']:add(b)
for path in P.glob('*.json'):
 if path.name!='supplemental-six-exhibit-candidate-fragments.json':add(bound(path))
for relative,expected in [('supplemental-v1/collection/results.json','078245c8df70c0d72fe600b9ef3d128e323fca958b62ab37eaeeb4213b51294c')]:
 path=P.parent/relative;assert bound(path)['sha256']==expected;add(bound(path));terminal=json.loads(path.read_bytes());assert terminal['terminal'] is True and terminal['GET_attempts']==7
add(bound(P.parent/'supplemental-v1/request-plan.json'))
for name in ['supplement-003','supplement-004','supplement-005','supplement-006','supplement-007']:
 snap=json.loads((P/(name+'-receipt-snapshot.json')).read_bytes());entry=snap['requests'][0];assert entry==next(r for r in terminal['requests'] if r['name']==name)
 add({'path':entry['raw_response'],'sha256':entry['raw_sha256']});disp=next(d for d in terminal['dispositions'] if d['name']==name);assert disp['status']=='received';add(disp['native_cache'])
 cached=_read_bound(disp['native_cache'])[1];loc=json.loads((P/(name+'-body-locators.json')).read_bytes());assert hashlib.sha256(cached['body'].encode()).hexdigest()==loc['decoded_body_sha256']
for candidate in draft['candidate_drafts']:
 add(candidate['document']);add(candidate['semantic_review'])
 for proof in candidate['proofs']:
  add(proof['artifact'])
  if 'raw_response' in proof:add(proof['raw_response'])
assert bound(Path(reader.__file__))['sha256']==EXPECTED
out={'schema_version':'explicit-operating-candidate-fragments-v1','candidates':draft['candidate_drafts'],'native_verification':checks,'native_reader_binding':bound(Path(reader.__file__)),'evidence_bindings':list(evidence.values()),'all_six_native_profiles_and_semantic_bridges_passed':True,'source_admissions':0,'target_scope':'Six exhibit IDs map to only the existing HITI/TGB/SLF40-F case/accession operating targets, two exhibits each; no new targets.','limitations':['HITI literal AIFDateJan29,2024 remains inconsistent with FYOct2024/parentacceptedJan2025; publicationtime does not rewrite withintext fact dates.','HITI parent/index/internal exhibit numbering conflict is retained; native roles use actual parent index cells.','TGB/SLFprimarywrapper unknown evidence remains bound; source qualification applies to these six separate whole exhibit bodies.','Old346655 reader rejected same two TGB records; initial37d0 intermediate candidate passed six; final12fcc reader now passes six with unchanged source/ID/clock.','No global-ID collision scan, append, materialization, actualprepare or model/label/GET by reviewer.','Only source-body scope and native proof/semantic bridge; not full factual/model reading, Signal readiness or MVP closure.']}
p=P/'supplemental-six-exhibit-candidate-fragments.json'
with p.open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({'path':str(p),'sha256':bound(p)['sha256'],'candidates':len(checks),'evidence_bindings':len(evidence)}))
