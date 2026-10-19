"""Collect at most three authorized read-only market source responses."""
import hashlib
import json
import os
import shlex
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/Users/l/Project/Recommandation')
OUT = ROOT / 'runs/diagnostics/bmbl_market_readonly_proof_20261019'
if OUT.exists():
    raise SystemExit('proof directory exists; do not repeat requests')
key = os.environ.get('MASSIVE_API_KEY')
if not key:
    for line in (ROOT / '.env.local').read_text().splitlines():
        name, sep, value = line.partition('=')
        if sep and name.strip().removeprefix('export ').strip() == 'MASSIVE_API_KEY':
            parts = shlex.split(value, comments=True)
            key = parts[0] if len(parts) == 1 else None
            break
if not key:
    raise SystemExit('configured market credential unavailable; no requests sent')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = urllib.request.build_opener(NoRedirect())
requests = [
    ('splits', '/stocks/v1/splits', {'ticker':'BMBL', 'execution_date.gte':'2025-09-30', 'execution_date.lte':'2026-08-16', 'sort':'execution_date.asc', 'limit':'1000'}),
    ('unadjusted_daily', '/v2/aggs/ticker/BMBL/range/1/day/2024-09-30/2025-09-29', {'adjusted':'false', 'sort':'asc', 'limit':'50000'}),
    ('historical_identity', '/v3/reference/tickers/BMBL', {'date':'2025-09-29'}),
]
OUT.mkdir(parents=True)
(OUT/'collector.py').write_bytes(Path(__file__).read_bytes())
plan = {'schema_version':'read-only-market-proof-v1','purpose':'source review only; not admission or active stage input',
        'max_http_attempts':3,'max_attempts_per_request':1,'external_llm_calls':0,
        'authorization':'user permits read-only source queries; no external LLM APIs',
        'requests':[{'name':name,'endpoint':'https://api.massive.com'+path,'query':query} for name,path,query in requests]}
(OUT/'request_plan.json').write_text(json.dumps(plan, indent=2)+'\n')
records=[]
for name, path, query in requests:
    endpoint='https://api.massive.com'+path
    url=endpoint+'?'+urllib.parse.urlencode(query)
    req=urllib.request.Request(url, headers={'Authorization':'Bearer '+key,'Accept':'application/json','User-Agent':'SourceReview/1.0'})
    stamp=datetime.now(timezone.utc).isoformat()
    try:
        response=opener.open(req, timeout=20)
        status=response.status
        raw=response.read()
        headers={name:response.headers.get(name) for name in ('Date','Content-Type','Cache-Control')}
    except urllib.error.HTTPError as exc:
        status=exc.code
        raw=exc.read()
        headers={name:exc.headers.get(name) for name in ('Date','Content-Type','Cache-Control')}
    except Exception as exc:
        records.append({'name':name,'endpoint':endpoint,'query':query,'retrieved_at':stamp,'status':'transport_failed','error_type':type(exc).__name__})
        (OUT/'results.json').write_text(json.dumps(records,indent=2)+'\n')
        continue
    if key.encode() in raw:
        records.append({'name':name,'endpoint':endpoint,'query':query,'retrieved_at':stamp,'http_status':status,'status':'response_contains_credential_not_persisted'})
        (OUT/'results.json').write_text(json.dumps(records,indent=2)+'\n')
        continue
    filename=name+'.response.json'
    (OUT/filename).write_bytes(raw)
    record={'name':name,'endpoint':endpoint,'query':query,'retrieved_at':stamp,'http_status':status,'headers':headers,
            'raw_response':filename,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    try:
        data=json.loads(raw)
        record.update(provider_status=data.get('status'),next_page_present=bool(data.get('next_url')))
        value=data.get('results')
        if isinstance(value,list):
            record['result_count']=len(value)
        elif isinstance(value,dict):
            record['identity']={k:value.get(k) for k in ('ticker','name','cik','primary_exchange','type','active','currency_name')}
        if name=='unadjusted_daily':
            record['adjusted']=data.get('adjusted')
    except (ValueError,TypeError,AttributeError):
        record['json_shape']='not_expected_object'
    records.append(record)
    (OUT/'results.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps({'proof_root':str(OUT),'http_attempts':len(records),'external_llm_calls':0,'results':records},indent=2))
