"""Read actual FTI origin and test supplemental transport only in temporary roots."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import gzip,hashlib,importlib.util,json,socket
import collect_frozen40_supplemental_source_proofs as C
from stock_opportunity_agent.data.reviewed_snapshot import _sec_response_text
from stock_opportunity_agent.data.raw_info import RawInfoDocument
P=Path(__file__).resolve().parent;planpath=P/'supplemental-v1/request-plan.json'
B={'scripts/collect_frozen40_supplemental_source_proofs.py':'3572de21dad9e301f9ab06126df3c35d4969c9c4c3483ce407d43985cccc1744','spec/scripts/collect_frozen40_supplemental_source_proofs.md':'c39803b87bbfb3762e1f97419954fd5e4ec40de56092e10c1c1d5e75ce5782ec',str(planpath):'8252e2c299a52c474020c7c07fd83dc791db3fb2a3b7d04fdfc2a29a2c79a239'}
for p,s in B.items():assert C.shared.bound(p)['sha256']==s
plan=C.shared.read_bound(C.shared.bound(planpath));assert plan['plan_hash']=='3071110b573f0af4e68be924b7a0884877d35959192edb884d9dd8eead56d99e'
assert len(plan['requests'])==7 and plan['max_GET_attempts']==7 and not Path(plan['output']).exists()
origin=plan['origin'];doc=C.shared.read_bound(origin['original_record']);cache=C.shared.read_bound(origin['cache']);bars=json.loads(doc['content'])
requests=C.origin_requests(origin)
assert requests==[{'purpose':r['kind'],'endpoint':r['endpoint'],'query':r['query']} for r in plan['requests'][:2]]
assert len(bars)==151 and bars[0]['as_of_date']=='2024-10-21' and bars[-1]['as_of_date']=='2025-05-29'
normalized=datetime.fromisoformat(bars[0]['retrieved_at']);assert normalized>=datetime.fromisoformat(cache['retrieved_at']);assert doc['available_at']=='2025-05-30T00:00:00+00:00'
checks=[{'name':'actual_FTI_full_native_reconstruction','passed':True,'bar_count':151,'first':'2024-10-21','last':'2025-05-29','requested_start':doc['metadata']['start'],'requested_end':doc['metadata']['end'],'normalized_at':normalized.isoformat(),'cache_retrieved_at':cache['retrieved_at'],'available_at':doc['available_at'],'native_derived_requests':requests}]
def save(path,value):path.write_text(json.dumps(value));return C.shared.bound(path)
class Clock:
 def __init__(self):self.value=datetime(2026,10,20,1,tzinfo=timezone.utc);self.waited=0
 def __call__(self):return self.value
 def sleep(self,s):self.waited+=s;self.value+=timedelta(seconds=s)
class Response:
 def __init__(self,url,raw):self.url=url;self.raw=gzip.compress(raw);self.status=200;self.headers={'Content-Encoding':'gzip'}
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def read(self):return self.raw
 def geturl(self):return self.url
class Opener:
 def __init__(self,out,mode):self.out=out;self.mode=mode;self.calls=[]
 def open(self,req,timeout):
  r=json.loads((self.out/'results.json').read_bytes());assert r['attempt_reservations']>=len(self.calls)+1 and r['GET_attempts']==r['network_open_calls']==len(self.calls)+1;assert timeout==30;self.calls.append(req.full_url)
  if 'massive.com' in req.full_url:
   if self.mode=='secret':raw=b'{"echo":"\\u006fffline-review-secret"}'
   else:raw=json.dumps({'status':'OK','results':[] if '/splits?' in req.full_url else {'ticker':'FTI','cik':'1681459'}}).encode()
  else:raw=b'<html>Offline exact static body.</html>'
  return Response(req.full_url,raw)
with patch.object(socket.socket,'connect',side_effect=AssertionError('real GET forbidden')):
 with TemporaryDirectory() as tmp:
  root=Path(tmp).resolve()
  bad=deepcopy(origin);bad['case']['company_id']='cik_0000000001'
  try:C.origin_requests(bad)
  except Exception:pass
  else:raise AssertionError('wrong company accepted')
  checks.append({'name':'actual_origin_wrong_case_issuer_rejected','passed':True})
  bad=deepcopy(origin);bad['case']['prediction_time']='2025-05-29T23:59:59+00:00'
  try:C.origin_requests(bad)
  except Exception:pass
  else:raise AssertionError('early cutoff accepted')
  checks.append({'name':'actual_origin_early_cutoff_rejected','passed':True})
  changed=deepcopy(doc);bb=json.loads(changed['content']);early=(datetime.fromisoformat(cache['retrieved_at'])-timedelta(microseconds=1)).isoformat()
  for b in bb:b['retrieved_at']=early
  newcontent=json.dumps(bb,sort_keys=True,separators=(',',':'));changed['content']=newcontent;changed['content_hash']=hashlib.sha256(newcontent.encode()).hexdigest()
  bad=deepcopy(origin);bad['original_record']=save(root/'retimed.json',changed)
  try:C.origin_requests(bad)
  except Exception as e:assert 'normalization' in str(e)
  else:raise AssertionError('precache normalization accepted')
  checks.append({'name':'rehashed_actual_origin_pre_cache_normalization_rejected','passed':True})
 for mode in ['success','secret','source_drift','code_drift','url_drift']:
  with TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();fp=deepcopy(plan);fp['output']=str(root/'collection')
   # Native actual origin reconstruction remains unmocked. Trim binding list only
   # for this temporary transport fixture, never claim real-plan fullhash review.
   boundsource=root/'bound-source.txt';boundsource.write_text('source')
   boundcode=root/'bound-code.txt';boundcode.write_text('code')
   hist=root/'history.jsonl';hist.write_text(''.join(json.dumps({'source_key':'massive','capability':'price_daily','endpoint':'https://api.massive.com/old','cache_key':str(i),'status':'fetched','requested_at':'2026-10-20T01:00:00+00:00'})+'\n' for i in range(5)))
   fp['native_ledger_paths']=[*plan['native_ledger_paths'],str(hist)]
   fp['source_bindings']=[origin['original_record'],origin['cache'],fp['additional_sec'],C.shared.bound(boundsource),C.shared.bound(hist)]
   fp['code_bindings']=[C.shared.bound(C.__file__),C.shared.bound(C.COLLECTOR),C.shared.bound(boundcode)]
   if mode=='url_drift':fp['requests'][2]['endpoint']=fp['requests'][2]['endpoint'].replace('20241031','20251031')
   fp['plan_hash']=C.canonical_json_hash({k:v for k,v in fp.items() if k!='plan_hash'});path=root/'plan.json';save(path,fp)
   if mode=='source_drift':boundsource.write_text('changed')
   if mode=='code_drift':boundcode.write_text('changed')
   clock=Clock();op=Opener(root/'collection',mode)
   if mode.endswith('_drift'):
    try:C.collect(path,C.shared.bound(path)['sha256'],opener=op,clock=clock,sleep=clock.sleep,credential_loader=lambda:'offline-review-secret')
    except ValueError:pass
    else:raise AssertionError('drift accepted')
    assert not op.calls and not (root/'collection').exists();checks.append({'name':mode+'_rejected_before_output_open','passed':True});continue
   history_before=hist.read_bytes();r=C.collect(path,C.shared.bound(path)['sha256'],opener=op,clock=clock,sleep=clock.sleep,credential_loader=lambda:'offline-review-secret')
   assert r['terminal'] and hist.read_bytes()==history_before and clock.waited>=60
   if mode=='success':
    assert r['GET_attempts']==7 and len(op.calls)==7 and r['status']=='completed', (r['GET_attempts'],r['status'],(root/'collection/native-ledger.jsonl').read_text())
    for e in r['requests']:
     if 'sec.gov' in e['url']:
      proof={'artifact':C.shared.bound(root/'collection/results.json'),'entry_name':e['name'],'endpoint':e['url'],'raw_response':{'path':e['raw_response'],'sha256':e['raw_sha256']}}
      assert _sec_response_text(proof,r,e['url'],{})=='<html>Offline exact static body.</html>'
    assert len(C.shared.read_bound(r['market_request_record']))==2
   else:
    assert [d['status'] for d in r['dispositions']]==['failed_typed','blocked_by_host_failure']+['received']*5
    assert len(op.calls)==6 and not list((root/'collection/cache/data/massive').rglob('*.json'))
   assert all(b'offline-review-secret' not in f.read_bytes() for f in (root/'collection').rglob('*') if f.is_file())
   before={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (root/'collection').rglob('*') if f.is_file()}
   try:C.collect(path,C.shared.bound(path)['sha256'],opener=op,clock=clock,sleep=clock.sleep,credential_loader=lambda:'offline-review-secret')
   except FileExistsError:pass
   else:raise AssertionError('reentry accepted')
   assert before=={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (root/'collection').rglob('*') if f.is_file()}
   checks.append({'name':mode+'_native_plumbing_pacing_no_reentry','passed':True,'opens':len(op.calls),'waited_seconds':clock.waited})
for p,s in B.items():assert C.shared.bound(p)['sha256']==s
assert not Path(plan['output']).exists()
out={'schema_version':'bounded-supplemental-independent-review-v1','bindings':[C.shared.bound(p) for p in B],'actual_origin_bindings':origin,'actual_plan_requests':plan['requests'],'actual_plan_source_binding_count':len(plan['source_bindings']),'actual_plan_code_binding_count':len(plan['code_bindings']),'checks':checks,'all_passed':True,'blocking_findings':[],'limits':['400-day request is not 400-day observed coverage: actual151bars begin2024-10-21.','ActualFTI native reconstruction does not qualify issuer/split basis before the two real responses exist.','First positive fixture failed from uncanonicalized macOS /var versus /private/var path alias in reviewer fixture; preserved logs are excluded as product failures.','Temporary transport fixtures trim binding lists and add a synthetic historical ledger; no claim of independently rehashing all858 actual source bindings.','0actualGET/Store/prepare/globalappend/Labels/model; actual supplemental collection remains absent.']}
p=P/'supplemental-independent-review.json';p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'path':str(p),'sha256':C.shared.bound(p)['sha256'],'checks':len(checks),'all_passed':True}))
