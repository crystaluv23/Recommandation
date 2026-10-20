from pathlib import Path
import hashlib,json,socket
from datetime import datetime,timezone
from collections import Counter
from urllib.parse import urlencode,urlsplit,parse_qsl
def forbidden_network(*a,**k): raise AssertionError('audit network forbidden')
socket.socket.connect=forbidden_network
socket.create_connection=forbidden_network
from stock_opportunity_agent.artifacts import canonical_json_hash as ch
from stock_opportunity_agent.data.sources.state import RawCacheKey
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import decode_response_text
ROOT=Path('/Users/l/Project/Recommandation')
BASE=ROOT/'runs/diagnostics/frozen40_source_proofs_20261020_v1'
PLAN=BASE/'final-plan-v2/request-plan.json'
OUT=BASE/'terminal-independent-review.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def bound(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def dt(v):
 d=datetime.fromisoformat(v.replace('Z','+00:00')); assert d.utcoffset() is not None
 return d
checks=Counter(); errors=[]
def check(ok,label):
 checks[label]+=1
 if not ok:errors.append(label)
p=json.loads(PLAN.read_text()); output=Path(p['output']); rp=output/'results.json'; r=json.loads(rp.read_text())
initial={str(x):sha(x) for x in [PLAN,rp,output/'native-ledger.jsonl',output/'market-request-records.json',output/'execution-start.json']}
check(ch({k:v for k,v in p.items() if k!='plan_hash'})==p['plan_hash'],'plan canonical hash')
check(r['plan_hash']==p['plan_hash'],'result plan binding')
check(r['terminal'] is True and r['status']=='completed','terminal completed')
for key in ['GET_attempts','HTTP_responses_retained','attempt_reservations','network_open_calls','max_GET_attempts']:
 check(type(r[key]) is int and r[key]==95,'95 counters '+key)
for key in ['automatic_retries','redirects_followed','global_appends','models']:
 check(type(r[key]) is int and r[key]==0,'zero reported '+key)
check(r['labels_loaded'] is False and r['source_admission'] is False,'reported no labels admission')
check(p['automatic_retries']==0 and p['redirects_followed']==0 and p['pagination_allowed'] is False and p['timeout_seconds']==30,'transport bounds')
allbindings=[*p['source_bindings'],*p['code_bindings'],p['request_source'],p['cache_lookup'],p['quota_state'],p['sec_user_agent_source'],r['market_request_record'],r['native_ledger']]
by_path={}; conflicts=[]; mismatches=[]
for b in allbindings:
 path=str(Path(b['path']).resolve()); expect=b['sha256']
 if path in by_path and by_path[path]!=expect:conflicts.append(path)
 by_path[path]=expect
for path,expect in by_path.items():
 actual=sha(path)
 if actual!=expect:mismatches.append({'path':path,'expected':expect,'actual':actual})
check(not conflicts and not mismatches,'all frozen and output binding hashes')
original=json.loads(Path(p['request_source']['path']).read_text())
check(ch(original)==ch(p['original_requests']),'original92 exact rows')
check(len(original)==92 and sum(len(x['associations']) for x in original)==1928,'original92 associations1928')
for a,b in zip(original,p['requests']):check(ch(a)==ch({k:b[k] for k in ('endpoint','query','associations')}),'original request prefix')
check(len(p['requests'])==len(r['requests'])==len(r['dispositions'])==95,'95 row denominators')
check(len({(x['endpoint'],ch(x['query'])) for x in p['requests']})==95,'95 unique exact endpoints queries')
check([x['name'] for x in p['requests']]==[x['name'] for x in r['requests']]==[x['name'] for x in r['dispositions']],'ordered names one to one')
check(all(x['disposition']=='planned_GET' for x in p['requests']),'all95 planned GET')
ledger=[json.loads(x) for x in (output/'native-ledger.jsonl').read_text().splitlines() if x.strip()]
records=json.loads((output/'market-request-records.json').read_text()); mr={x['name']:x for x in records}
check(len(ledger)==95 and all(x['status']=='fetched' for x in ledger),'95 fetched ledger')
check(len(records)==len(mr)==83,'83 unique market records')
check(set(mr)=={x['name'] for x in p['requests'] if x['source']=='massive'},'market record exact name set')
capmap={'all_type_splits':DataCapability.CORPORATE_ACTIONS,'historical_issuer':DataCapability.COMPANY_PROFILE,'additional_daily_origin':DataCapability.PRICE_DAILY,'additional_exhibit':DataCapability.FILING_DOCUMENTS,'exact_static_primary_body':DataCapability.FILING_DOCUMENTS}
percall=[]; unsupported=[]; expectedraw=set(); expectedjson=set(); expectedcache=set(); times={'massive':[],'sec_edgar':[]}; native_times={'massive':[],'sec_edgar':[]}
for row,req,disp,led in zip(p['requests'],r['requests'],r['dispositions'],ledger):
 name=row['name']; url=row['endpoint']+('?' + urlencode(row['query']) if row['query'] else '')
 check(req['method']=='GET' and req['url']==req['response_url']==url and req['http_status']==200 and type(req['http_status']) is int,'receipt GET identity status')
 check(req['status']=='http_response_retained','all responses retained')
 check(not any(k.lower() in {'apikey','api_key','token','access_key','key','authorization'} for k,v in parse_qsl(urlsplit(url).query)),'no credential query fields')
 check(all(not any(t in k.lower() for t in ('auth','cookie','key','token','secret','password')) for k in req['response_headers']),'sanitized header names')
 start,retrieved,reserved=dt(req['started_at_utc']),dt(req['retrieved_at_utc']),dt(disp['reserved_at_utc'])
 check(reserved<=start<=retrieved<=dt(r['finished_at_utc']),'aware reservation response order')
 rawpath=Path(req['raw_response']); expectedraw.add(rawpath.resolve())
 raw=rawpath.read_bytes(); check(sha(rawpath)==req['raw_sha256'] and len(raw)==req['bytes'],'raw exact bytes hash length')
 check(rawpath.resolve()==(output/'responses'/f'{name}.response.raw').resolve(),'raw exact output path')
 enc=[v for k,v in req['response_headers'].items() if k.lower()=='content-encoding']; check(len(enc)<=1,'encoding unique')
 text=decode_response_text(raw,enc[0] if enc else None)
 ismarket=row['source']=='massive'; body=json.loads(text) if ismarket else text
 cap=capmap[row['kind']]; key=RawCacheKey.from_request(row['source'],cap,'GET',url)
 cp=Path(disp['native_cache']['path']); expectedcache.add(cp.resolve()); cache=json.loads(cp.read_text()); cache_at=dt(cache['retrieved_at'])
 check(sha(cp)==disp['native_cache']['sha256'],'native cache bound hash')
 check(cp.resolve()==(output/'cache/data'/row['source']/cap.value/(key.digest+'.json')).resolve(),'native cache exact path digest')
 check(cache['source_key']==row['source'] and cache['capability']==cap.value and cache['endpoint']==key.endpoint and cache['params']==[list(x) for x in key.params],'native cache request identity')
 check(cache['payload_kind']==('json' if ismarket else 'text') and ch(cache['body'])==ch(body),'native decoded whole body exact')
 check(retrieved<=cache_at and cache_at==dt(disp['cache_retrieved_at'])==dt(led['requested_at']),'native actual retrieval order')
 check(led['source_key']==row['source'] and led['capability']==cap.value and led['endpoint']==key.endpoint and led['cache_key']==key.digest and led['message'] is None and led['next_retry_at'] is None,'ledger exact cache request identity')
 check(disp['source']==row['source'] and disp['kind']==row['kind'],'disposition identity')
 if ismarket:
  rec=mr[name]; dp=output/rec['raw_response']; expectedjson.add(dp.resolve())
  check(rec['endpoint']==row['endpoint'] and ch(rec['query'])==ch(row['query']) and rec['http_status']==200 and rec['retrieved_at']==req['retrieved_at_utc'],'market compatible receipt identity')
  check(ch(rec['raw_HTTP_response'])==ch({'path':str(rawpath),'sha256':req['raw_sha256']}),'market raw HTTP binding')
  check(dp.resolve()==(output/'responses'/f'{name}.response.json').resolve() and bound(dp)==req['decoded_response'] and sha(dp)==rec['sha256'],'decoded proof exact path hash')
  check(dp.read_text()==text and ch(json.loads(dp.read_text()))==ch(body),'decoded proof exact text and JSON')
  check(rec['provider_status']==body['status']=='OK' and rec['next_page_present'] is False and not body.get('next_url'),'complete provider page status')
  if row['kind']=='historical_issuer':check(isinstance(body.get('results'),dict),'issuer object result')
  elif row['kind']=='all_type_splits':check(isinstance(body.get('results'),list),'splits array result')
  if row['kind']=='all_type_splits' and body['results']:
   check(disp['status']=='received_unsupported_nonempty_split_ledger','unsupported explicit disposition')
   unsupported.append({'name':name,'kind':row['kind'],'endpoint':row['endpoint'],'query':row['query'],'case_ids':sorted({x['case_id'] for x in row['associations']}),'result_count':len(body['results']),'results':body['results'],'raw_response':bound(rawpath),'native_cache':disp['native_cache'],'source_admission':False})
  else:check(disp['status']=='received','received status')
 else:check(disp['status']=='received','SEC received status')
 times[row['source']].append(start.timestamp());native_times[row['source']].append(cache_at.timestamp())
 percall.append({'name':name,'source':row['source'],'kind':row['kind'],'raw_sha256':req['raw_sha256'],'native_cache_sha256':disp['native_cache']['sha256'],'native_cache_key':key.digest,'status':disp['status']})
check(set((output/'responses').glob('*.response.raw'))==expectedraw,'no extra retained raw file')
check(set((output/'responses').glob('*.response.json'))==expectedjson,'no extra decoded JSON file')
check(set((output/'cache/data').glob('*/*/*.json'))==expectedcache,'no extra native cache file')
# Independently reconstruct retained native network history from the exact frozen paths.
historical={'massive':[],'sec_edgar':[]}; latest_any={}; historical_count=Counter()
for path in p['native_ledger_paths']:
 for line in Path(path).read_text().splitlines():
  if not line.strip():continue
  e=json.loads(line)
  if e['source_key'] in historical:
   source=e['source_key']; latest_any[source]=max(latest_any.get(source,dt(e['requested_at'])),dt(e['requested_at']))
  if e['source_key'] in historical and e['status'] in ('fetched','error'):
   historical[e['source_key']].append(dt(e['requested_at']).timestamp());historical_count[e['source_key']]+=1
quota=json.loads(Path(p['quota_state']['path']).read_text())
for source in historical:
 check(len(historical[source])==quota[source]['retained_native_network_entries'],'historical retained count')
 check(latest_any[source]==dt(quota[source]['latest_native_event']),'historical latest event')
def roll(current,prior,seconds):
 combined=sorted(prior+current); peak=0; witness=None
 for t in current:
  window=[x for x in combined if t-seconds<=x<=t]
  if len(window)>peak:peak=len(window);witness=t
 return {'window_seconds':seconds,'maximum_inclusive_count_at_new_start':peak,'witness_utc':datetime.fromtimestamp(witness,timezone.utc).isoformat(),'current_count':len(current),'prior_count':len(prior),'prior_overlapping_first_new_window':sum(current[0]-seconds<=x<=current[0] for x in prior)}
rolling={}
for source in times:
 prior=historical[source]+(p['prior_market_attempt_epochs'] if source=='massive' else [])
 seconds,limit=(60,5) if source=='massive' else (1,10)
 rolling[source]={'reservation_start_clock':roll(times[source],prior,seconds),'native_completion_ledger_clock':roll(native_times[source],prior,seconds),'limit':limit}
 check(rolling[source]['reservation_start_clock']['maximum_inclusive_count_at_new_start']<=limit,'rolling actual reservation start quota '+source)
 check(rolling[source]['native_completion_ledger_clock']['maximum_inclusive_count_at_new_start']<=limit,'rolling native ledger quota '+source)
 check(all(a<=b for a,b in zip(times[source],times[source][1:])),'per host chronological requests')
# Source bindings were read at audit start; rehash all at end, without decoding or constructing stores.
end_mismatches=[]
for path,expect in by_path.items():
 if sha(path)!=expect:end_mismatches.append(path)
check(not end_mismatches,'frozen hashes stable audit end')
check(all(sha(path)==expect for path,expect in initial.items()),'terminal packet stable audit end')
review={'scope':'independent local read-only terminal acquisition audit; no admission or consumer execution','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'verdict':'pass' if not errors else 'fail','input_bindings':{'plan':bound(PLAN),'results':bound(rp),'ledger':bound(output/'native-ledger.jsonl'),'market_records':bound(output/'market-request-records.json'),'execution_start':bound(output/'execution-start.json')},'plan_hash':p['plan_hash'],'finished_at_utc':r['finished_at_utc'],'counts':{'planned':95,'original_requests':len(original),'original_associations':sum(len(x['associations']) for x in original),'additional':3,'kind_counts':dict(Counter(x['kind'] for x in p['requests'])),'source_counts':dict(Counter(x['source'] for x in p['requests'])),'raw_receipts':len(expectedraw),'decoded_market_records':len(records),'native_caches':len(expectedcache),'ledger_fetched':len(ledger),'received':sum(x['status']=='received' for x in r['dispositions']),'unsupported':len(unsupported),'source_binding_rows':len(p['source_bindings']),'code_binding_rows':len(p['code_bindings']),'distinct_rehashed_paths_including_outputs':len(by_path),'historical_network_entries':dict(historical_count)},'all_original92_rows_and1928_associations_exact':True,'binding_conflicts':conflicts,'binding_mismatches':mismatches,'binding_end_mismatches':end_mismatches,'frozen_bindings_canonical_sha256':ch([{'path':k,'sha256':v} for k,v in sorted(by_path.items())]),'per_call_correspondence_canonical_sha256':ch(percall),'rolling':rolling,'unsupported':unsupported,'checks':dict(checks),'errors':errors,'evidence_limits':['Request started_at is the persisted pre-opener boundary; an exact socket-open timestamp and historical intermediate fsync states are not recoverable from the terminal receipt. Collector source writes reservations and open-count updates before calling opener; final clocks are consistent with that order.','NoRedirect handler returns None; final receipts all have response_url equal to exact planned URL, 95 opens/95 retained responses/95 native fetched rows and no extra retained raw/cache files. This is artifact and code evidence, not independent wire capture.','global_appends=0/models=0/labels_loaded=false are terminal counters corroborated by bounded collector code, whose only writes target the new output. This audit did not load labels, construct any RawInfoStore, read the full global oracle before/after, or monitor unrelated processes; it does not prove machine-wide absence of external activity.','All 635 frozen source/code binding rows were independently rehashed at audit start and end; this does not extend source trust or admission, body semantics, issuer identity, split compatibility, or downstream readiness.','All 95 HTTP200 acquisitions are retained; BURU nonempty split ledger remains unsupported by the present empty-ledger profile and candidate-only. Other source semantic dispositions remain for their owning reviews.'],'initial_audit_check_correction':{'artifact':bound(BASE/'terminal-independent-review-initial-check.json'),'explanation':'Initial local audit incorrectly compared quota latest_native_event with only fetched/error events. Quota latest_native_event includes cache_hit. Corrected to the latest event of all statuses; preserved initial result. Rolling checks still use fetched/error only.'},'audit_actions':{'network_GET':0,'store_construction':0,'global_appends':0,'prepare':0,'model':0,'LabelStore':0,'production_src_or_spec_edits':0}}
if OUT.exists():raise RuntimeError('review output already exists; refuse overwrite')
with OUT.open('x') as f:json.dump(review,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'output':str(OUT),'sha256':sha(OUT),'verdict':review['verdict'],'counts':review['counts'],'rolling':rolling,'errors':errors},indent=2))
