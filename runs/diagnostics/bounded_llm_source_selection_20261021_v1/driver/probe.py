"""Fixed lexical candidate only: real bound inputs and synthetic counterexamples."""
import ssl
import socket
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from contextlib import ExitStack
from unittest.mock import patch
from time import monotonic
import subprocess

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedRawInfoStore
from stock_opportunity_agent.data.resolution import (
    RawInfoRequest, _rank_documents, _select_required_source_documents,
    _retrieval_contract_coverage, _matches_source_type, _deduplicate_documents,
)
from stock_opportunity_agent.signal_library import SignalSpec, SignalExecutor, SignalRegistry, LLMSignalBatchInput
from stock_opportunity_agent.research.evolution_signal_roles import (
    _single_llm_signal_projection, _LLM_SIGNAL_QUERY_STOP_WORDS, StructuredLLMSignalRunner,
)
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient

OUT = Path(__file__).resolve().parent
OLD = Path('runs/diagnostics/default_llm_financial_read_20261021_v1/driver').resolve()
read = lambda p: json.loads(Path(p).read_bytes())
bind = lambda p: {'path':str(Path(p).resolve()), 'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def write(name, value):
    (OUT/name).open('x').write(json.dumps(value,indent=2,sort_keys=True)+'\n')

# This is the one proposed lexical policy, not a production selector.
def candidate_rank(documents, request):
    terms = {t.casefold() for t in re.findall(r'[A-Za-z0-9]+',request.query or '')
             if len(t)>=3 and t.casefold() not in _LLM_SIGNAL_QUERY_STOP_WORDS}
    if not terms:
        return _rank_documents(documents,request)
    def key(document):
        words = re.findall(r'[A-Za-z0-9]+',document.content.casefold())
        return (-len(terms.intersection(words)),
                -sum(min(words.count(t),3) for t in terms),
                -document.available_at.timestamp(),document.document_id)
    return sorted(documents,key=key)

def candidate_select(documents,request):
    return _select_required_source_documents(candidate_rank(documents,request),request)

started=monotonic()
old=read(OLD/'result.json'); latest=read(OLD/'latest-facts.json')['rows']
source_root=Path(old['snapshot']['root'])
source_bindings=[b for b in old['bindings'] if Path(b['path']).parent == source_root/'documents']
assert len(source_bindings)==57 and all(bind(b['path'])==b for b in source_bindings)
manifest_binding={'path':str(source_root/'reviewed_snapshot.json'),'sha256':old['snapshot']['manifest_sha256']}
assert bind(manifest_binding['path'])==manifest_binding
prior_plan=read('runs/diagnostics/measurement_input_selection_20261021_v1/plan.json')
group=next(g for g in prior_plan['groups'] if g['name']=='default_v6')
ref='cash_to_current_liabilities_ratio:v1'
version_bindings=[b for b in group['definition_bindings'] if '/cash_to_current_liabilities_ratio/versions/v1/' in b['path']]
assert all(bind(b['path'])==b for b in version_bindings)
spec=SignalSpec.from_dict(read(next(b['path'] for b in version_bindings if b['path'].endswith('/spec.json'))))
skill=Path(next(b['path'] for b in version_bindings if b['path'].endswith('/skill.md'))).read_text()
request=RawInfoRequest.from_dict(old['request'])
cutoff=datetime.fromisoformat(old['case']['prediction_time'])
forbidden_calls=[]
def forbidden(*a,**k):
    forbidden_calls.append('forbidden');raise AssertionError('pure local lexical probe only')
with ExitStack() as guards:
    for owner,name in [(socket,'socket'),(socket,'create_connection'),(RawInfoStore,'__init__'),
                       (RawInfoStore,'append'),(ReviewedRawInfoStore,'append'),(SignalRegistry,'__init__'),
                       (SignalExecutor,'execute_batch'),(SignalExecutor,'prepare_inputs'),
                       (StructuredLLMSignalRunner,'execute'),(StructuredLLMSignalRunner,'execute_many'),
                       (LabelStore,'__init__'),(LabelStore,'load'),(LabelStore,'record'),
                       (StructuredRoleClient,'complete_json')]:
        guards.enter_context(patch.object(owner,name,side_effect=forbidden))
    documents=[RawInfoDocument.from_dict(read(b['path'])) for b in source_bindings]
    source_hash=canonical_json_hash([d.to_dict() for d in documents])
    assert all(d.company_id==old['case']['company_id'] and d.available_at<=cutoff
               and _matches_source_type(d,request.source_types) for d in documents)
    documents,duplicates=_deduplicate_documents(documents)
    assert len(documents)==57 and not duplicates
    native=_select_required_source_documents(_rank_documents(documents,request),request)
    assert [d.document_id for d in native]==old['native_selected_order']
    ranked=candidate_rank(documents,request);selected=candidate_select(documents,request)
    assert [d.document_id for d in selected]==old['counter_selected_order']
    projections,lineage=_single_llm_signal_projection((LLMSignalBatchInput(spec,tuple(selected),skill),))
    visibility=[{'tag':f['tag'],'period':f['end'],'unit':f['unit'],'document_id':f['document_id'],
        'whole_literal_projection_ids':[p['projection_id'] for p in projections
            if p['document_id']==f['document_id'] and f['exact_span'] in p['exact_text']]} for f in latest]
    assert all(f['whole_literal_projection_ids'] for f in visibility)
    real={'eligible':57,'selected':10,'old_order_exact':True,'candidate_order_matches_prior_fixed_counter':True,
          'selected_order':[d.document_id for d in selected],
          'q1_rank':next(i for i,d in enumerate(ranked,1) if d.document_id==latest[0]['document_id']),
          'coverage':_retrieval_contract_coverage(selected,request),
          'latest_literal_visibility':visibility,'projection_count':len(projections),
          'projection_characters':sum(len(p['exact_text']) for p in projections),
          'source_partial_disclosure':[{'document_id':p['document_id'],
              'source_context_partial':p.get('fact_context',{}).get('source_context_partial'),
              'omitted_concept_count':p.get('fact_context',{}).get('omitted_concept_count')} for p in projections],
          'not_an_actual_transmitted_model_request':True}
    write('real-projection.json',{'result':real,'rows':projections})

    def financial(document_id, end, available, notes='', source_type='financials'):
        at=datetime.fromisoformat(available)
        body={'schema_version':'sec-company-facts-document-v1','cik':'0000000001',
              'filing_date':at.date().isoformat(),'form':'10-Q','notes':notes,
              'facts':[{'taxonomy':'us-gaap','tag':tag,'unit':'USD','value':i+1,'start':None,'end':end}
                       for i,tag in enumerate(('CashAndCashEquivalentsAtCarryingValue','LiabilitiesCurrent'))]}
        return RawInfoDocument.create(document_id=document_id,company_id='synthetic_lexical_probe',
            source_type=source_type,published_at=at,available_at=at,
            content=json.dumps(body,sort_keys=True,separators=(',',':')),metadata={'cik':'0000000001'})
    def news(document_id,available):
        at=datetime.fromisoformat(available)
        return RawInfoDocument.create(document_id=document_id,company_id='synthetic_lexical_probe',
            source_type='news',published_at=at,available_at=at,content='An unrelated operational announcement.')
    short=financial('recent_basis','2025-03-31','2025-05-09T00:00:00+00:00',notes=request.query*3)
    long=financial('long_old_basis','2023-12-31','2024-02-10T00:00:00+00:00',notes=request.query*5000)
    one=RawInfoRequest('probe:one','Offline lexical control',('financials',),max_documents=1,query=request.query)
    assert _rank_documents([long,short],one)[0].document_id=='long_old_basis'
    assert candidate_select([long,short],one)[0].document_id=='recent_basis'
    unrelated=financial('new_irrelevant','2025-03-31','2025-05-20T00:00:00+00:00')
    payload=json.loads(unrelated.content);payload['facts']=[{'taxonomy':'us-gaap','tag':'Assets','unit':'EUR','value':7,'end':'2025-03-31'}]
    unrelated=RawInfoDocument.create(document_id='new_irrelevant',company_id=unrelated.company_id,
        source_type='financials',published_at=unrelated.published_at,available_at=unrelated.available_at,
        content=json.dumps(payload,sort_keys=True,separators=(',',':')))
    assert candidate_select([short,unrelated],one)[0].document_id=='recent_basis'
    group_request=RawInfoRequest('probe:groups','Offline source/period control',('financials','news'),max_documents=3,
        query=request.query,required_source_groups=(('financials',),('news',)),
        minimum_distinct_periods=2,minimum_period_span_days=330)
    prior=financial('low_rank_comparable','2024-03-31','2024-05-09T00:00:00+00:00')
    required_news=news('required_news','2025-05-29T00:00:00+00:00')
    grouped=candidate_select([short,prior,unrelated,required_news],group_request)
    coverage=_retrieval_contract_coverage(grouped,group_request)
    assert coverage['contract_satisfied'] and len(grouped)<=3
    assert 'required_news' in [d.document_id for d in grouped] and 'low_rank_comparable' in [d.document_id for d in grouped]
    queryless=RawInfoRequest('probe:noquery','Offline no-query fallback',('financials',),max_documents=1)
    assert candidate_select([long,short],queryless)==_select_required_source_documents(_rank_documents([long,short],queryless),queryless)
    controls={'synthetic_only_not_qualified_sources':True,
        'long_repetition':{'native_first':'long_old_basis','candidate_first':'recent_basis',
                           'old_characters':len(long.content),'recent_characters':len(short.content)},
        'newer_unrelated':{'candidate_first':candidate_select([short,unrelated],one)[0].document_id},
        'required_source_and_period':{'selected':[d.document_id for d in grouped],'coverage':coverage},
        'queryless_candidate_explicit_native_fallback':True,
        'unknown_runner':'Static future interface constraint only: do not install a callback for unknown/custom runners; no such production opt-in exists or was exercised here.'}
    write('representative-controls.json',controls)
    # Fixed falsifier, not a tuning exercise: lexically rich old valid pairs beat
    # a newer pair whose body has the facts but omits irrelevant query prose.
    latest_doc=financial('latest_pair_low_lexical','2025-03-31','2025-05-09T00:00:00+00:00')
    decoys=[financial(f'older_rich_{i:02d}',f'{2011+i}-03-31',f'{2011+i}-05-09T00:00:00+00:00',notes=request.query*3) for i in range(10)]
    counter_pool=[latest_doc,*decoys]
    counter_selected=candidate_select(counter_pool,request)
    counter_rank=candidate_rank(counter_pool,request)
    falsifier={'synthetic_only_not_qualified_sources':True,'pool':11,'cap':10,
        'latest_basis_doc':'latest_pair_low_lexical',
        'latest_basis_rank':next(i for i,d in enumerate(counter_rank,1) if d.document_id=='latest_pair_low_lexical'),
        'latest_basis_selected':latest_doc in counter_selected,
        'selected':[d.document_id for d in counter_selected],
        'generic_coverage':_retrieval_contract_coverage(counter_selected,request),
        'meaning':'Full pool has a current same-period USD pair. Ten older valid pairs carry more distinct query prose; lexical policy excludes the current pair. Coverage can still pass. Lexical policy alone cannot guarantee latest measurement basis or semantic/comparison witnesses.',
        'policy_tuned_after_counterexample':False}
    assert not falsifier['latest_basis_selected'] and falsifier['generic_coverage']['contract_satisfied']
    write('semantic-counterexample.json',falsifier)
    assert source_hash==canonical_json_hash([d.to_dict() for d in documents])
    assert all(bind(b['path'])==b for b in source_bindings+version_bindings+[manifest_binding])
    assert not forbidden_calls
    result={'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'real_basis_literals_both_visible':True,'real_selection_contract_preserved':True,
        'representative_controls_passed':True,'semantic_counterexample_fails_candidate_as_intended':True,
        'candidate_sufficient_for_general_latest_or_comparison_semantics':False,
        'source_records_unchanged':True,'source_bindings':source_bindings+version_bindings+[manifest_binding],
        'code_bindings':[bind(p) for p in [__file__,'src/stock_opportunity_agent/data/resolution.py',
            'src/stock_opportunity_agent/research/evolution_core.py','src/stock_opportunity_agent/research/evolution_signal_roles.py']],
        'forbidden_calls':forbidden_calls,'seconds':monotonic()-started,
        'scope':'Pure candidate/source projection only; no Store, model/Signal, GET, labels, append, Registry writes, fullprepare or completed-pipeline reentry.'}
    write('result.json',result)
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('_bindings')},indent=2))
