"""Offline independent per-filing source selection probes; no real GET/store."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import hashlib,json,socket
from stock_opportunity_agent.data.acquisition import SecFilingAdapter
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.data.resolution import RawInfoRequest
from stock_opportunity_agent.data.reviewed_snapshot import _verify_sec_document,ReviewedSourceRejected
from stock_opportunity_agent.data.raw_info import RawInfoDocument
P=Path(__file__).resolve().parent;checks=[];cutoff=datetime(2025,7,31,tzinfo=timezone.utc);company='cik_0000000001'
def forbidden(*a,**k):raise AssertionError('network forbidden')
socket.socket=forbidden;socket.create_connection=forbidden
class Client(SecEdgarClient):
 def __init__(self):
  super().__init__('Independent offline producer',transport=object());self.body_calls=[];self.fail=set();self.arrays={'accessionNumber':['0000000002-25-00000'+str(i) for i in range(1,5)],'filingDate':['2025-05-0'+str(i) for i in range(1,5)],'form':['10-K','10-Q','8-K','6-K'],'primaryDocument':['r'+str(i)+'.htm' for i in range(1,5)],'reportDate':['2024-12-31','2025-03-31','2025-05-03','2025-05-04'],'acceptanceDateTime':['2025-05-0'+str(i)+'T20:00:00Z' for i in range(1,5)]}
 def submissions(self,cik):return {'cik':1,'filings':{'recent':deepcopy(self.arrays),'files':[]}}
 def filing_document_text(self,f):
  self.body_calls.append(f.accession_number)
  if f.accession_number in self.fail:raise RuntimeError('synthetic body failure')
  return '<html>Independent '+f.form+' whole synthetic source.</html>'
def run(sources,maximum=4,client=None,asof=cutoff):
 c=client or Client();value=SecFilingAdapter(c).acquire(RawInfoRequest('read','Offline source',sources,lookback_days=730,max_documents=maximum),company_id=company,identity={'cik':'0000000001'},as_of=asof);return value,c
sources=('10-k','10-q','8-k','6-k');a,c=run(sources);b,c2=run(tuple(reversed(sources)));assert [x.to_dict() for x in a.documents]==[x.to_dict() for x in b.documents] and c.body_calls==c2.body_calls
assert [(x.metadata['form'],x.source_type) for x in a.documents]==[('6-K','6-k'),('8-K','8-k'),('10-Q','10-q'),('10-K','10-k')];checks.append({'case':'mixedfour exactforms and reversedrequest order','passed':True,'types':[x.source_type for x in a.documents]})
for requested,expected in [(('sec_filing','filing_body','filing'),['sec_filing']*4),(('filing_body','sec_filing'),['filing_body']*4),(('10-k','filing_body','10-q','8-k','6-k'),['filing_body','filing_body','filing_body','10-k'])]:
 r,_=run(requested);assert [x.source_type for x in r.documents]==expected;checks.append({'case':'first compatible requestpriority','request':requested,'actual':expected})
for alias in ('10-k','10-q','8-k','6-k'):
 r,c=run((alias,));assert len(r.documents)==len(c.body_calls)==1 and r.documents[0].source_type==alias;checks.append({'case':'single exact filter before body','alias':alias,'body_calls':1})
for requested in (('news',),('filing_summary','10-k-summary'),('40-f',)):
 r,c=run(requested);assert not r.documents and not c.body_calls;checks.append({'case':'no supported compatiblebody','request':requested,'body_calls':0})
r,c=run(('10-k','10-q'),maximum=1);assert len(c.body_calls)==len(r.documents)==1
c=Client();c.fail.add('0000000002-25-000002');r,c=run(('10-k','10-q'),maximum=1,client=c);assert len(c.body_calls)==2 and [d.source_type for d in r.documents]==['10-k'];checks.append({'case':'maxdocument and failedbody fallback retained','passed':True})
for d in a.documents:
 i=Client().arrays['accessionNumber'].index(d.metadata['accession_number']);assert d.document_id=='sec:'+company+':'+d.metadata['accession_number'].replace('-','') and d.available_at==d.published_at==datetime.fromisoformat(Client().arrays['acceptanceDateTime'][i])
 proof={'sec_static_archive_body':({'endpoint':d.metadata['source_url'],'expected_content_hash':d.content_hash},{'endpoint':d.metadata['source_url'],'body':d.content}),'sec_submissions_acceptance':({'issuer_cik':'0000000001','accession_number':d.metadata['accession_number'],'form':d.metadata['form'],'primary_document':Client().arrays['primaryDocument'][i],'accepted_at':d.available_at.isoformat()},{'endpoint':'https://data.sec.gov/submissions/CIK0000000001.json','body':Client().submissions('1')})}
 _verify_sec_document(d,{'reviewed_available_at':d.available_at.isoformat()},proof,cutoff)
 if d.metadata['form']=='10-Q':
  wrong=d.to_dict();wrong['source_type']='10-k'
  try:_verify_sec_document(RawInfoDocument.from_dict(wrong),{'reviewed_available_at':d.available_at.isoformat()},proof,cutoff);raise AssertionError('old badshape accepted')
  except ReviewedSourceRejected:pass
at=datetime(2025,5,2,20,tzinfo=timezone.utc);early,_=run(('10-q',),asof=at-timedelta(microseconds=1));exact,_=run(('10-q',),asof=at);assert not early.documents and len(exact.documents)==1;checks.append({'case':'producedID/clock/nativequalification and oldwrongtype/PIT reject','passed':True})
paths={'src/stock_opportunity_agent/data/acquisition.py':'a6e54ffdc9eeb69eb381aaed311165bcc35c7e438f135aaf25bbaae31d175904','spec/src/stock_opportunity_agent/data/sources.md':'16882b954126f8622ebd0405e0f8df84495f8dc9eff625d76356619c14411c9d','tests/test_sec_filing_source_types.py':'2cad1e0350418c596613292f87d660fa3244426985d749f01c5b3fde7153bdda'};sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();assert all(sha(p)==h for p,h in paths.items())
report={'scope':'Independent new fakeclient using native SEC arrayparser only; no real GET/globalstore/labels/LockedTest/prepare/oldstage reread/source admission.','bindings':[{'path':str(Path(p).resolve()),'sha256':h} for p,h in paths.items()],'checks':checks,'all_passed':True,'conclusion':'Future per-filing source selection now matches actual proved form while retaining first compatible requested generic priority, limits/IDs/publicclocks. Old wrongtype originals remain rejected; no persisted original is relabeled.','limitations':['Offline producer/nativequalifier wiring only, no fresh model or materialized realsource admission.','Completed3e67e166 source diagnosis and previous reviews were not reverified or reexecuted under this new revision.']}
out=P/'producer-source-type-independent-review.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'all_passed':True,'checks':len(checks),'sha256':sha(out)}))
