"""Read completed fixed15 input-only artifacts; never execute acquisition/apply/labels."""
import hashlib,json,socket,ssl
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.data.sec_company_facts import materialize_company_fact_documents,validate_company_facts_response
from stock_opportunity_agent.signal_library import SignalSpec
D=Path(__file__).resolve().parent;S=D.parent/'stage'
def forbidden(*a,**kw):raise RuntimeError('Independent review forbids network')
socket.socket=forbidden;socket.create_connection=forbidden

def read(p):return json.loads(Path(p).read_bytes())
def hashfile(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(b):
    assert hashfile(b['path'])==b['sha256'],b['path']
    return read(b['path'])
def instant(t):return datetime.fromisoformat(t.replace('Z','+00:00'))
def productkey(d):return {'document_id':d.document_id,'content_hash':d.content_hash,'canonical_record_hash':canonical_json_hash(d.to_dict())}
def research_periods(d,payload):
    result=set()
    def visit(v,key=''):
        if isinstance(v,dict):
            for k,x in v.items():visit(x,k.casefold())
        elif isinstance(v,list):
            for x in v:visit(x,key)
        elif key in {'as_of_date','date','end','fiscaldateending','fiscal_date_ending','period_end'} and isinstance(v,str):
            try:result.add(instant(v).replace(tzinfo=None))
            except ValueError:pass
    visit(d.metadata);visit(payload);return result

def observation_count(d,payload):
    counts=[]
    def visit(v,key=''):
        if isinstance(v,dict):
            for k,x in v.items():visit(x,k.casefold())
        elif isinstance(v,list):
            if key in {'prices','observations','rows','series'} or (v and all(isinstance(x,dict) and any(k.casefold() in {'date','timestamp'} for k in x) for x in v)):
                counts.append(len(v))
            for x in v:visit(x,key)
    visit(d.metadata);visit(payload);return max(counts,default=0)

def main():
    assert (S/'result.json').is_file(),'Wait for driver completed result; do not inspect building stage'
    result=read(S/'result.json');plan=read(S/'plan.json');inputs=read(S/'input_manifest.json');app=read(S/'append-inventory.json')
    assert plan['plan_hash']=='567c7db62347538dbb654735fddf6369a5b2ec02082d9dbdf8e557e8e60f5409'
    assert canonical_json_hash({k:v for k,v in plan.items() if k!='plan_hash'})==plan['plan_hash']
    assert canonical_json_hash(inputs)==result['input_manifest_hash']
    for key in ('source_bindings','old_view_bindings','registry_bindings','code_bindings'):
        for b in plan[key]:assert hashfile(b['path'])==b['sha256'],b['path']
    inventory=check(plan['inventory']);oldreview=check(plan['old_source_review']);review=check(inputs['source_review']);oracle=check(plan['oracle_identity'])
    cases=inventory['cases'];caseids={c['case_id'] for c in cases};refs=plan['registry_refs']
    assert len(cases)==len(caseids)==15 and len(refs)==len(set(refs))==18
    assert plan['registry_version']==inputs['registry_version']==12
    assert inputs['registry_refs']==refs
    oldcount=len(oldreview['records']);assert oldcount==48
    assert canonical_json_hash(review['records'][:oldcount])==canonical_json_hash(oldreview['records'])
    source=check(plan['registry_source_inputs']);specs=[];skills={}
    for ref in refs:
        sid,version=ref.split(':');paths=list(Path(source['registry_root']).glob('*/'+sid+'/versions/'+version+'/spec.json'));assert len(paths)==1
        spec=SignalSpec.from_dict(read(paths[0]));assert spec.ref==ref;specs.append(spec.to_dict())
        if spec.execution_type.value=='llm':skills[ref]=(paths[0].parent/'skill.md').read_text()
    rh=hashlib.sha256(json.dumps({'version':12,'specs':specs,'skills':skills},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert rh==plan['registry_hash']==inputs['registry_hash']==source['registry_hash']
    append_by_id={r['document_id']:r for r in app['receipts']};assert len(append_by_id)==len(app['receipts'])
    normalizations={b['path']:check(b) for b in inputs['normalizations']};derived={};sourcechecks=[]
    ftaicontrol={}
    for case,case_derivation in zip(cases,inputs['case_derivations'],strict=True):
        assert case_derivation['case_id']==case['case_id']
        cache=check(case['exact_cache']['binding']);raw=RawInfoDocument.from_dict(check(case['original_raw_proof']['binding']))
        norm=check(case_derivation['normalization']);cik=case['company_id'].removeprefix('cik_');endpoint='https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik+'.json'
        assert cache['endpoint']==endpoint and cache['params']==[['method','GET']] and cache['source_key']=='sec_edgar' and cache['capability']=='financial_statements' and cache['payload_kind']=='json'
        validate_company_facts_response(cache['body'],cik)
        assert raw.company_id==case['company_id'] and raw.content==json.dumps(cache['body'],sort_keys=True,separators=(',',':'),ensure_ascii=False)
        assert instant(cache['retrieved_at'])<=raw.available_at<=instant(norm['normalized_at']) and raw.available_at==raw.published_at
        assert instant(norm['selection']['available_at_through'])==instant(case['cutoff'])
        products,stats=materialize_company_fact_documents(cache['body'],item=norm['item'],selection=norm['selection'],provenance=norm['provenance'],retrieved_at=instant(norm['normalized_at']))
        assert {x['document_id']:x for x in norm['expected_products']}=={d.document_id:productkey(d) for d in products}
        cutoff=instant(case['cutoff']);rows=0
        for d in products:
            saved=RawInfoDocument.from_dict(check(append_by_id[d.document_id]['original_record']))
            assert canonical_json_hash(saved.to_dict())==canonical_json_hash(d.to_dict());assert d.available_at<=cutoff
            payload=json.loads(d.content);assert payload['cik']==cik and 'entityName' not in payload
            assert instant(payload['filing_date']).replace(tzinfo=timezone.utc)+timedelta(days=1)==d.available_at
            assert all(datetime.fromisoformat(f['end']).date()<=cutoff.astimezone(timezone.utc).date() for f in payload['facts'])
            rows+=len(payload['facts']);derived[d.document_id]=productkey(d)
        if case['ticker']=='FTAI':
            raw_same=sum(1 for tax in cache['body']['facts'].values() if isinstance(tax,dict) for concept in tax.values() if isinstance(concept,dict) for vals in concept.get('units',{}).values() if isinstance(vals,list) for row in vals if isinstance(row,dict) and row.get('filed')=='2025-07-31')
            excluded=sum(len(json.loads(d.content)['facts']) for d in products if json.loads(d.content)['filing_date']=='2025-07-31')
            assert raw_same==364 and excluded==0;ftaicontrol={'raw_same_day_rows':raw_same,'admitted_same_day_rows':excluded}
        sourcechecks.append({'case_id':case['case_id'],'products':len(products),'facts':rows,'exact_cache_request_and_body':True,'complete_actual_normalizer_reconstruction':True})
    assert len(derived)==inputs['new_product_denominator']==result['new_product_denominator']
    financialrows=review['records'][oldcount:];assert {r['document_id'] for r in financialrows}==set(derived)
    assert all(r['proof_profile']=='sec_companyfacts_filed_next_utc_day_v1' for r in financialrows)
    # No global store construction/refresh: hash the frozen pre-existing paths only.
    before=read(S/'global-originals-before.json');before_paths={b['path'] for b in before}
    assert all(hashfile(b['path'])==b['sha256'] for b in before)
    root=Path(plan['oracle_identity']['path']).parent
    now={str(p.resolve()) for p in root.rglob('*') if p.is_file()}
    additions=now-before_paths;declared={b['path'] for b in result['global_new_files']}
    assert additions==declared=={b['path'] for b in app['global_new_files']}
    permitted={r['original_record']['path'] for r in app['receipts']}|{str(root/'.raw-info-append.lock')}
    assert additions<=permitted and all(hashfile(b['path'])==b['sha256'] for b in result['global_new_files'])
    store=open_raw_info_store(inputs['reviewed_source_snapshot']['root'],reviewed_snapshot=inputs['reviewed_source_snapshot']);worker=store.snapshot()
    canonical=lambda ds:canonical_json_hash([d.to_dict() for d in ds])
    assert canonical(store.documents)==canonical(worker.documents)
    restart=open_raw_info_store(inputs['reviewed_source_snapshot']['root'],reviewed_snapshot=inputs['reviewed_source_snapshot']);assert canonical(restart.documents)==canonical(store.documents)
    assert not any(d.source_type in {'financials','sec_company_facts_raw_response'} for d in store.documents)
    rawids={c['original_raw_proof']['document_id'] for c in cases};assert not rawids&{d.document_id for d in store.documents}
    docmap={d.document_id:d for d in worker.documents};payloads={}
    totals=Counter();per_ref={r:Counter() for r in refs};all_resolutions=[];summary=[]
    for c in cases:
        saved=read(S/'cases'/(c['case_id']+'.json'));assert saved['case']==c
        exact=saved['exact_signal_input_resolutions'];assert [x['signal_ref'] for x in exact]==refs
        counts=Counter()
        for x in exact:
            resolution=x['resolution'];status=resolution['status'];counts[status]+=1;totals[status]+=1;per_ref[x['signal_ref']][status]+=1
            docs=[];periods=set()
            for ref in resolution['documents']:
                d=worker.load(ref['document_id'],as_of=instant(c['cutoff']));assert d.company_id==c['company_id'] and d.content_hash==ref['content_hash'] and d.available_at==instant(ref['available_at'])
                assert d.source_type!='sec_company_facts_raw_response'
                if d.document_id not in payloads:
                    try:payloads[d.document_id]=json.loads(d.content)
                    except ValueError:payloads[d.document_id]=None
                periods|=research_periods(d,payloads[d.document_id]);docs.append(d)
            coverage=resolution['coverage'];span=(max(periods)-min(periods)).days if len(periods)>=2 else None
            assert coverage['selected_document_count']==len(docs)
            assert coverage['observed_observation_count']==max((observation_count(d,payloads[d.document_id]) for d in docs),default=0)
            assert coverage['observed_distinct_period_count']==len(periods) and coverage['observed_period_span_days']==span
            if status=='resolved':assert docs and coverage['contract_satisfied']
            all_resolutions.append({'case_id':c['case_id'],'signal_ref':x['signal_ref'],'status':status,'document_ids':[d.document_id for d in docs],'period_count':len(periods),'period_span_days':span,'missing_requirements':coverage['missing_requirements']})
        expected={'case_id':c['case_id'],'resolved_signal_inputs':counts['resolved'],'signal_ref_denominator':18,'resolved_fraction':counts['resolved']/18,'meets_existing_0_8_signal_input_fraction':counts['resolved']/18>=.8}
        assert saved['summary']==expected;summary.append(expected)
    assert len(all_resolutions)==270 and result['cases']==summary
    assert result['cases_meeting_existing_0_8']==sum(x['meets_existing_0_8_signal_input_fraction'] for x in summary)
    assert all(result[k] is False for k in ['labels_loaded','signal_apply_executed','full_prepare_executed','full48_readiness_proven','engineering_mvp_closed'])
    assert result['network_requests']==result['external_llm_calls']==0
    out={'scope':'Independent completed-artifact read-only review; no acquisition/model/Signalapply/labels/fullprepare/globalstore writes or refresh.','plan_hash':plan['plan_hash'],'input_manifest_hash':canonical_json_hash(inputs),'fixed_cases':15,'exact_registry_version':12,'registry_hash_recomputed':rh,'exact_ref_denominator':18,'resolution_denominator':270,'status_counts':dict(totals),'per_ref_status_counts':{k:dict(v) for k,v in per_ref.items()},'source_proof_checks':sourcechecks,'new_financial_products':len(derived),'FTAI':ftaicontrol,'old_operating_review_rows_preserved':oldcount,'old_global_file_bindings_unchanged':len(before),'allowed_new_files':len(additions),'all_old_oracle_bytes_unchanged':True,'reviewed_view_restart_worker_canonical_equal':True,'whole_raw_and_legacy_aggregates_not_visible':True,'case_summaries':summary,'all270_saved_resolutions_read_and_sources_periods_checked':all_resolutions,'limits':['SEC authority current extraction plus conservative filed-nextUTCday policy, not APIvintage/primaryfiling numerical audit.','Resolved source/period coverage is not tag/unit/comparable-period semantic measurement or all9financialSignals readiness.','Only fixed15 data-only preparation; not full48,MVP,model behavior or research benefit.']}
    (D/'final-source-review.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in {'all270_saved_resolutions_read_and_sources_periods_checked','source_proof_checks','per_ref_status_counts'}},indent=2))
if __name__=='__main__':main()
