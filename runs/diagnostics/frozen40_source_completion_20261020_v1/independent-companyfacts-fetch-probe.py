"""Independent fake-opener checks only; never call a real opener."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import contextlib,gzip,hashlib,importlib.util,json,socket,tempfile
P=Path(__file__).resolve().parent;C=P/'companyfacts-fetch-v1';sha=lambda b:hashlib.sha256(b).hexdigest()
source=C/'collector.py';spec=importlib.util.spec_from_file_location('independent_single_collector',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=json.loads((C/'request-plan.json').read_text());before={str(p):sha(p.read_bytes()) for p in (source,C/'request-plan.json')};checks=[]
def no_network(*a,**kw):raise AssertionError('real network forbidden')
socket.socket=no_network;socket.create_connection=no_network
SECRET='INDEPENDENT-NONPERSIST-SECRET'
class Response:
 status=200
 def __init__(self,mode):
  self.mode=mode;self.headers={'Content-Type':'application/json','Set-Cookie':SECRET,'Authorization':SECRET,'X-Token':SECRET,'Content-Encoding':'gzip' if mode in ('gzip','truncated') else 'identity'}
 def read(self):
  if self.mode=='read_failure':raise ValueError(SECRET)
  payload={'cik':('not-a-cik0001309402' if self.mode=='malformed_cik' else 1309402),'facts':{},'entityName':'Synthetic probe'}
  data=json.dumps(payload).encode();return gzip.compress(data)[:-5] if self.mode=='truncated' else gzip.compress(data) if self.mode=='gzip' else data
 def geturl(self):return 'https://example.invalid/wrong' if self.mode=='wrong_response_url' else m.ENDPOINT
 def __enter__(self):return self
 def __exit__(self,*a):return False
class Opener:
 def __init__(self,mode):self.mode=mode;self.calls=0;self.requests=[]
 def open(self,request,timeout):
  self.calls+=1;assert request.full_url==m.ENDPOINT and request.get_method()=='GET' and timeout==30
  self.requests.append(dict(request.header_items()));return Response(self.mode)
class Clock:
 def __init__(self):self.i=0
 def __call__(self):self.i+=1;return datetime(2026,10,20,tzinfo=timezone.utc)+timedelta(seconds=self.i)
with tempfile.TemporaryDirectory() as temp:
 for mode in ('gzip','truncated','malformed_cik','wrong_response_url','read_failure'):
  root=Path(temp)/mode;root.mkdir();plan={**original,'output_directory':str(root)};pp=root/'request-plan.json';raw=json.dumps(plan).encode();pp.write_bytes(raw);opener=Opener(mode)
  try:result=m.collect(pp,sha(raw),opener=opener,clock=Clock());success=True
  except Exception:result=json.loads((root/'results.json').read_text());success=False
  assert success==(mode=='gzip') and opener.calls==1 and result['terminal'] is True
  assert result['GET_attempts']==result['network_open_calls']==1 and result['automatic_retries']==result['redirects_followed']==0
  files=[p for p in root.rglob('*') if p.is_file()];assert all(SECRET.encode() not in p.read_bytes() for p in files)
  cache=list((root/'cache').rglob('*.json')) if (root/'cache').exists() else []
  if success:
   assert len(cache)==1;cached=json.loads(cache[0].read_text());proof=json.loads((root/'raw-response-proof.json').read_text())
   assert cached['source_key']=='sec_edgar' and cached['capability']=='financial_statements' and cached['payload_kind']=='json' and cached['endpoint']==m.ENDPOINT and cached['params']==[['method','GET']]
   assert json.loads(proof['content'])==cached['body'] and datetime.fromisoformat(result['requests'][0]['retrieved_at_utc'])<=datetime.fromisoformat(cached['retrieved_at'])<=datetime.fromisoformat(proof['available_at'])==datetime.fromisoformat(proof['published_at'])
   assert proof['source_type']=='sec_company_facts_raw_response' and proof['company_id']=='cik_0001309402'
   assert result['source_appends']==result['typed_products_materialized']==0
  else:assert not cache and not (root/'raw-response-proof.json').exists()
  try:m.collect(pp,sha(raw),opener=opener,clock=Clock());raise AssertionError('reentry accepted')
  except RuntimeError as e:assert 'reentry' in str(e)
  assert opener.calls==1
  checks.append({'case':mode,'fake_GET_calls':opener.calls,'status':result['status'],'native_cache_written':bool(cache),'secret_absent':True,'terminal_reentry_rejected':True})
assert m.NoRedirect().redirect_request(None,None,302,'test',{},'https://example.invalid/') is None
assert all(sha(Path(p).read_bytes())==h for p,h in before.items())
assert not any((C/n).exists() for n in ('.attempt.json','results.json','cache','request-ledger.jsonl','gpre-companyfacts.response.raw','raw-response-proof.json'))
report={'scope':'Independent five temporary fake-opener cases, no real GET/oracle append/typed normalization/model/labels; source and candidate real output untouched.','candidate_bindings':before,'checks':checks,'NoRedirect_returns_None':True,'actual_GETs':0,'actual_task_attempt_artifacts_absent':True,'bounded_conclusion':'No blocker found for exact1GPRE attempt, native cache/raw proof identity and actual clock ordering, sanitized error/header persistence, no automatic redirect/retry and terminal attempt reentry rejection. This is offline wiring, not proof of real response or admission.','limitations':['Initial preflight refusal has no attempted GET; durable marker makes any reserved/started/failed/interrupted attempt terminal.','Collector produces whole-response proof only, not peracc normalized/admitted data or source readiness.']}
out=P/'independent-companyfacts-fetch-review.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'review_sha256':sha(out.read_bytes()),'checks':len(checks),'all_passed':True}))
