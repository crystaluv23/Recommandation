"""Bounded fake-opener review; never execute the real frozen proof plan."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib,json,socket,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tests'))
import test_frozen40_source_proofs as T
from stock_opportunity_agent.data.reviewed_snapshot import _sec_response_text
C=T.collector
P=Path(__file__).resolve().parent
EXPECTED={'collector.py':'d4f928abaecff1a0fb36754fed5becb5f1f5f1c20d9a94dec47f6ab0ca771551','final-plan-v2/request-plan.json':'0c96abd8ae201b36eb50e2cb22974ada8975284be9dc9c4cc4ae5b2496a5b05f'}
for name,sha in EXPECTED.items():assert C.bound(P/name)['sha256']==sha
plan=json.loads((P/'final-plan-v2/request-plan.json').read_bytes());assert len(plan['requests'])==95 and plan['original_unique_requests']==92 and plan['max_GET_attempts']==95
assert plan['original_association_count']==1928 and len({C.canonical_json_hash([r['endpoint'],r['query']]) for r in plan['requests']})==95
assert not Path(plan['output']).exists()
checks=[]
def record(name,**details):checks.append({'name':name,'passed':True,**details})
class ProbeOpener(T.Opener):
 def open(self,request,timeout):
  if self.mode in ('http429','sec_failure'):
   result=json.loads((self.output/'results.json').read_bytes());assert result['attempt_reservations']>=len(self.calls)+1;assert result['GET_attempts']==result['network_open_calls']==len(self.calls)+1
   if self.mode=='http429' and 'api.massive.com' in request.full_url:
    self.calls.append(request.full_url);raise T.HTTPError(request.full_url,429,'test-runtime-secret',{},T.io.BytesIO(b'quota'))
   if self.mode=='sec_failure' and 'www.sec.gov' in request.full_url:
    self.calls.append(request.full_url);raise OSError('test-runtime-secret')
  return super().open(request,timeout)
with patch.object(socket.socket,'connect',side_effect=AssertionError('real network forbidden')):
 for mode in (None,'gzip_secret','escaped_secret','transport_secret','http429','sec_failure'):
  with TemporaryDirectory() as tmp,T.fixture(Path(tmp).resolve(),history=mode is None,daily=True,exhibits=True) as (fp,path):
   clock=T.Clock();op=ProbeOpener(Path(fp['output']),mode=mode)
   result=C.collect(path,C.bound(path)['sha256'],opener=op,clock=clock,sleep=clock.sleep,credential_loader=lambda:'test-runtime-secret')
   out=Path(fp['output']);assert result['terminal'] and result['GET_attempts']==len(op.calls)
   assert all(b'test-runtime-secret' not in f.read_bytes() for f in out.rglob('*') if f.is_file())
   if mode is None:
    assert result['status']=='completed' and len(op.calls)==6 and clock.waited>=60
    market=C.read_bound(result['market_request_record']);assert len(market)==3
    for row in market:C._market_response({'artifact':C.bound(out/row['raw_response']),'request_record':result['market_request_record'],'entry_name':row['name']},row['endpoint'],row['query'])
    for row in result['requests']:
     disp=next(x for x in result['dispositions'] if x['name']==row['name']);cache=C.read_bound(disp['native_cache'])
     if 'www.sec.gov' in row['url']:
      proof={'artifact':C.bound(out/'results.json'),'raw_response':{'path':row['raw_response'],'sha256':row['raw_sha256']},'entry_name':row['name'],'endpoint':row['url']}
      assert _sec_response_text(proof,result,row['url'],{})==cache['body']
     else:assert cache['payload_kind']=='json'
   elif mode=='sec_failure':
    assert [x['status'] for x in result['dispositions']]==['received','received','failed_typed','received','blocked_by_host_failure','blocked_by_host_failure']
   else:
    assert result['dispositions'][0]['status']=='failed_typed' and result['dispositions'][1]['status']=='blocked_by_host_failure'
    assert result['dispositions'][2]['status']=='received' and len(op.calls)==4
    assert not list((out/'cache/data/massive').rglob('*.json'))
   before={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}
   try:C.collect(path,C.bound(path)['sha256'],opener=op,clock=clock,sleep=clock.sleep,credential_loader=lambda:'test-runtime-secret')
   except ValueError as e:assert 'cannot reenter' in str(e)
   else:raise AssertionError('reentry accepted')
   assert before=={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}
   record(mode or 'success_gzip_native_profile_receipts_historical_pacing',opens=len(op.calls),waited_seconds=clock.waited,status=result['status'],reentry_rejected_immutable=True)
 for name,sha in EXPECTED.items():assert C.bound(P/name)['sha256']==sha
 assert not Path(plan['output']).exists()
result={'schema_version':'bounded-collector-independent-review-v1','bindings':[C.bound(P/x) for x in EXPECTED]+[C.bound(Path('spec/scripts/collect_frozen40_source_proofs.md')),C.bound(Path('tests/test_frozen40_source_proofs.py'))],'actual_plan':{'request_count':95,'original_requests':92,'original_associations':1928,'additional_requests':3,'all_planned_GET':all(r['disposition']=='planned_GET' for r in plan['requests'])},'checks':checks,'all_passed':True,'blocking_findings':[],'limits':['Fake-opener transport/cache/receipt/host-stop evidence only; zero real GETs or actual frozen collection.','No source admission, value correctness, complete semantic reading, matrix, model or research benefit claim.','Prior usage scope is only explicitly bound ledgers and old attempt timestamps; no worldwide account quota proof.'],'actual_collection_absent_before_after':True}
p=P/'collector-independent-review.json';p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'path':str(p),'sha256':C.bound(p)['sha256'],'checks':len(checks),'all_passed':True}))
