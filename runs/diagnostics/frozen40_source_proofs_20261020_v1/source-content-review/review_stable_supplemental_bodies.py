"""Capture stable per-request receipts and source locators, never run collection."""
from pathlib import Path
import hashlib,html,json,re,bisect,sys
from stock_opportunity_agent.data.sources.core import decode_response_text
from stock_opportunity_agent.data.markup import visible_html_ranges
P=Path(__file__).resolve().parent;collection=P.parent/'supplemental-v1/collection'
plan=json.loads((collection.parent/'request-plan.json').read_bytes());results=json.loads((collection/'results.json').read_bytes())
for name in sys.argv[1:]:
 entry=next(r for r in results['requests'] if r['name']==name);request=next(r for r in plan['requests'] if r['name']==name)
 assert entry['status']=='http_response_retained' and entry['http_status']==200
 raw=Path(entry['raw_response']).read_bytes();assert hashlib.sha256(raw).hexdigest()==entry['raw_sha256'] and len(raw)==entry['bytes']
 receipt={'automatic_retries':results['automatic_retries'],'redirects_followed':results['redirects_followed'],'requests':[entry],'plan_hash':results['plan_hash'],'source_request':request,'capture_scope':'Exact stable single request snapshot while wholecollection may still evolve; no terminalbatch assertion.'}
 dest=P/(name+'-receipt-snapshot.json')
 if dest.exists():assert json.loads(dest.read_bytes())==receipt
 else:dest.write_text(json.dumps(receipt,indent=2)+'\n')
 encoding=next((v for k,v in entry['response_headers'].items() if k.lower()=='content-encoding'),None);body=decode_response_text(raw,encoding)
 parts=[];offsets=[];raw_offsets=[];cursor=0
 for a,b in visible_html_ranges(body):
  s=' '.join(html.unescape(body[a:b]).split())
  if s:parts.append(s);offsets.append(cursor);raw_offsets.append((a,b));cursor+=len(s)+1
 txt=' '.join(parts)
 def window(start,n=850):
  end=min(len(txt),start+n);a=max(0,bisect.bisect_right(offsets,start)-1);b=max(a,bisect.bisect_left(offsets,end)-1)
  return {'visible_start':start,'visible_end':end,'raw_decoded_start':raw_offsets[a][0],'raw_decoded_end':raw_offsets[b][1],'text':txt[start:end]}
 sections={}
 for key,pattern in {'business':r'\b(?:Item\s*[14][.:]?\s*(?:Business|Information on the Company)|Business Overview|Overview of our business)\b','mda':r'\b(?:Item\s*[257][.:]?\s*(?:Management.{0,8}Discussion|Operating and Financial Review)|Management.{0,8}Discussion and Analysis)\b','risks':r'\bItem\s*1A[.:]?\s*Risk Factors\b','statements':r'\b(?:Condensed\s+)?Consolidated (?:Balance Sheets|Statements of (?:Income|Operations|Cash Flows|Financial Position))\b','segments':r'\b(?:reportable segments|operating segments)\b','units':r'\b(?:in (?:thousands|millions)|dollars in (?:thousands|millions))\b'}.items():
  ms=list(re.finditer(pattern,txt,re.I));chosen=ms[:1]+[m for m in ms if m.start()>len(txt)*.02][:2]+ms[-1:];uniq={m.start():m for m in chosen};sections[key]=[window(m.start()) for m in uniq.values()]
 value={'name':name,'source_request':request,'receipt_snapshot':{'path':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()},'raw_binding':{'path':entry['raw_response'],'sha256':entry['raw_sha256']},'decoded_body_sha256':hashlib.sha256(body.encode()).hexdigest(),'decoded_characters':len(body),'visible_characters':len(txt),'visible_text_sha256':hashlib.sha256(txt.encode()).hexdigest(),'head':window(0,1300),'tail':window(max(0,len(txt)-850)),'closing_html':bool(re.search(r'</html\s*>\s*$',body,re.I)),'section_locators':sections,'locator_only_not_automatic_semantic_admission':True}
 out=P/(name+'-body-locators.json')
 if out.exists():assert json.loads(out.read_bytes())==value
 else:out.write_text(json.dumps(value,indent=2)+'\n')
 print(json.dumps({'name':name,'head':value['head']['text'][:500],'visible_characters':len(txt),'closing_html':value['closing_html'],'sections':{k:[(s['visible_start'],s['text'][:230]) for s in v] for k,v in sections.items()},'tail':value['tail']['text'][-250:]}))
