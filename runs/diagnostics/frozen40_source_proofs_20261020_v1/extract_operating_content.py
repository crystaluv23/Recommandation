"""Read only fixed stage-bound operating bodies; emit locatable review excerpts, never verdicts."""
from pathlib import Path
import argparse,bisect,hashlib,html,json,re
from stock_opportunity_agent.data.markup import visible_html_ranges

REPO=Path(__file__).resolve().parents[3]
STAGE=REPO/'runs/diagnostics/reviewed_frozen_source_snapshot_20261020_v1/stage/result.json'
STAGE_SHA='ac71fbcbf40526e04446c0cca25e568d02b0fd9df06ffd28463d03fcc90369ec'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def read(binding):
    path=Path(binding['path']);raw=path.read_bytes()
    if digest(raw)!=binding['sha256']:raise RuntimeError('bound source changed: '+str(path))
    return json.loads(raw)
def extract(body, *, starts=()):
    parts=[];offsets=[];raw_offsets=[];cursor=0
    for start,end in visible_html_ranges(body):
        value=' '.join(html.unescape(body[start:end]).split())
        if value:
            offsets.append(cursor);raw_offsets.append((start,end));parts.append(value);cursor+=len(value)+1
    text=' '.join(parts)
    def window(start,length=600):
        end=min(len(text),start+length)
        a=max(0,bisect.bisect_right(offsets,start)-1);b=max(a,bisect.bisect_left(offsets,end)-1)
        return {'visible_start':start,'visible_end':end,'raw_start':raw_offsets[a][0],'raw_end':raw_offsets[b][1],'text':text[start:end]}
    patterns={'business':r'\b(?:item\s*1[.:]?\s*(?:business|description of business)|item\s*4[.:]?\s*information on the company|business overview|our business|we (?:are|operate)|the company (?:is|operates))\b',
        'risks':r'\b(?:item\s*1a[.:]?\s*risk factors|item\s*3[.:]?\s*key information|risk factors)\b',
        'mda':r'\b(?:management[’\x27]?s? discussion|operating and financial review|results of operations)\b',
        'segments':r'\b(?:reportable segments?|operating segments?|business segments?)\b',
        'financial_statements':r'\b(?:consolidated (?:balance sheets|statements of (?:operations|income|cash flows|financial position))|condensed consolidated)\b',
        'incorporation':r'\b(?:incorporated (?:herein )?by reference|annual information form|management[’\x27]?s? discussion and analysis|exhibit\s*99)\b'}
    sections={}
    for name,pattern in patterns.items():
        matches=list(re.finditer(pattern,text,re.I))
        # Locators only, never auto-admission: reviewer must read actual windows.
        chosen=matches[:2]+matches[-2:] if len(matches)>4 else matches
        sections[name]={'locator_count':len(matches),'windows':[window(max(0,m.start()-80),650) for m in chosen]}
    heading_patterns={'business':r'item\s*(?:1[.:]?\s*(?:business|description of business)|4[.:]?\s*information on the company)',
        'mda':r'item\s*(?:7|2)[.:]?\s*management[’\x27]?s?\s*discussion|item\s*5[.:]?\s*operating and financial review',
        'risks':r'item\s*1a[.:]?\s*risk factors',
        'statements':r'(?:consolidated|condensed consolidated)\s+(?:balance sheets|statements of (?:operations|income|cash flows|financial position))'}
    report_sections={}
    for name,pattern in heading_patterns.items():
        matches=list(re.finditer(pattern,text,re.I))
        # Retrieval heuristics only: prefer a later heading outside the cover/TOC,
        # retaining its locator for the reviewer's substantive inspection.
        candidates=[m for m in matches if m.start()>len(text)*(.10 if name=='mda' else .015)]
        chosen=candidates[:2] or matches[:2]
        report_sections[name]=[window(m.start(),1000) for m in chosen]
    return {'selected_manual_windows':[window(start,1000) for start in starts], 'raw_tail':body[-180:],'has_closing_html_tag':bool(re.search(r'</html\s*>\s*$',body,re.I)), 'report_sections':report_sections,'html_characters':len(body),'visible_characters':len(text),'visible_text_sha256':digest(text.encode()),'head':window(0,1000),'tail':window(max(0,len(text)-700),700),'sections':sections}
def collect():
    stage=read({'path':str(STAGE),'sha256':STAGE_SHA});results=[];memo={};allbindings={}
    for case in stage['outcomes']['operating']:
        for target in case['targets']:
            variants=target.get('body_variants',[]);groups={}
            for variant in variants:
                cb=variant['cache'];envelope=read(cb);allbindings[cb['path']]=cb
                body=envelope['body'];bodyhash=digest(body.encode());g=groups.setdefault(bodyhash,{'cache_bindings':[],'variants':[]})
                g['cache_bindings'].append(cb);g['variants'].append(variant)
                if bodyhash not in memo:memo[bodyhash]=extract(body)
                for key in ('candidate_original_record',):
                    binding=variant.get(key)
                    if binding:
                        original=read(binding);allbindings[binding['path']]=binding
                        if original['content']!=body:raise RuntimeError('original differs from body')
            results.append({'case_id':case['case_id'],'ticker':case['retained_selection']['ticker'],
                'cutoff':case['retained_selection']['prediction_time'],'accession':target['accession'],
                'form':target['form'],'period':target['report_period'],'accepted_at':target['accepted_at'],
                'primary_url':target['primary_url'],'body_variants':variants,
                'groups':[{'content_sha256':h,**group,'extraction':memo[h]} for h,group in groups.items()],
                'missing_body_GET':target.get('exact_missing_GET'),'existing_same_id_originals':target.get('existing_same_id_originals',[])})
    return {'stage':{'path':str(STAGE),'sha256':STAGE_SHA},'helper_sha256':digest(Path(__file__).read_bytes()),'native_markup':{'path':str(REPO/'src/stock_opportunity_agent/data/markup.py'),'sha256':digest((REPO/'src/stock_opportunity_agent/data/markup.py').read_bytes())},'scope':'All bound full HTML parsed; excerpts are locators only. No automated semantic classification or admission.','targets':results,'all_body_and_original_bindings':list(allbindings.values())}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=collect()
    with args.output.open('x') as handle:json.dump(report,handle,ensure_ascii=False,indent=2);handle.write('\n')
    print(json.dumps({'output':str(args.output),'sha256':digest(args.output.read_bytes()),'targets':len(report['targets']),'body_targets':sum(bool(t['groups']) for t in report['targets'])}))
