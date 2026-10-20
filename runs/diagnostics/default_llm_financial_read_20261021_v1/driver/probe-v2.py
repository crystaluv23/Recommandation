"""Read-only reconstruction of one frozen default-v6 LLM financial request."""
import ssl
import socket
import json
import hashlib
import re
import subprocess
from pathlib import Path
from datetime import datetime
from contextlib import ExitStack
from unittest.mock import patch
from time import monotonic

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedRawInfoStore, open_raw_info_store
from stock_opportunity_agent.data.resolution import (
    EvidenceResolver, RawInfoRequest, _matches_source_type,
    _deduplicate_documents, _rank_documents, _request_query_tokens,
    _document_query_hit_count, _select_required_source_documents,
)
from stock_opportunity_agent.signal_library import SignalSpec, SignalExecutor, LLMSignalBatchInput, _sec_facts
from stock_opportunity_agent.research.evolution_signal_roles import (
    StructuredLLMSignalRunner, _single_llm_signal_projection, _LLM_SIGNAL_QUERY_STOP_WORDS,
)
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient

OUT = Path(__file__).resolve().parent
ORIGIN = Path('runs/diagnostics/measurement_input_selection_20261021_v1').resolve()
REF = 'cash_to_current_liabilities_ratio:v1'
TAGS = ('CashAndCashEquivalentsAtCarryingValue', 'LiabilitiesCurrent')

def read(path):
    return json.loads(Path(path).read_bytes())

def bind(path):
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

def write(name, value):
    (OUT/name).open('x').write(json.dumps(value, indent=2, sort_keys=True)+'\n')

started = monotonic()
plan = read(ORIGIN/'plan.json')
old = next(r for r in read(ORIGIN/'default_v6.json')['rows'] if r['signal_ref'] == REF)
group = next(g for g in plan['groups'] if g['name'] == 'default_v6')
bound = [b for b in group['definition_bindings']
         if '/cash_to_current_liabilities_ratio/versions/v1/' in b['path']]
assert len(bound) == 2 and all(bind(b['path']) == b for b in bound)
spec = SignalSpec.from_dict(read(next(b['path'] for b in bound if b['path'].endswith('/spec.json'))))
skill = Path(next(b['path'] for b in bound if b['path'].endswith('/skill.md'))).read_text()
request = RawInfoRequest(request_id='signal:'+spec.ref, description=spec.description,
    source_types=spec.source_types, lookback_days=spec.retrieval_policy.lookback_days,
    max_documents=10, query=spec.retrieval_policy.query,
    required_source_groups=spec.retrieval_policy.required_source_groups,
    minimum_distinct_periods=spec.retrieval_policy.minimum_distinct_periods,
    minimum_period_span_days=spec.retrieval_policy.minimum_period_span_days,
    minimum_observations=spec.retrieval_policy.minimum_observations)
assert request.to_dict() == old['resolution']['request']
cutoff = datetime.fromisoformat(plan['case']['prediction_time'])
company = plan['case']['company_id']
manifest_path = Path(plan['reviewed_source_snapshot']['root'])/'reviewed_snapshot.json'
# The native reviewed reader verifies all source proofs; only this case is queried.
manifest = read(manifest_path)
initial_bindings = [bind(ORIGIN/'plan.json'), bind(ORIGIN/'default_v6.json'),
                    bind(manifest_path), *bound, bind(__file__)]
code_paths = ['src/stock_opportunity_agent/data/resolution.py',
              'src/stock_opportunity_agent/data/raw_info.py',
              'src/stock_opportunity_agent/data/reviewed_snapshot.py',
              'src/stock_opportunity_agent/data/sec_company_facts.py',
              'src/stock_opportunity_agent/signal_library.py',
              'src/stock_opportunity_agent/research/evolution_signal_roles.py']
initial_bindings += [bind(p) for p in code_paths]
forbidden_calls = []
def forbidden(*args, **kwargs):
    forbidden_calls.append('forbidden')
    raise AssertionError('read-only single-request inspection')

with ExitStack() as guards:
    for target, name in [(socket, 'socket'), (socket, 'create_connection'),
                         (RawInfoStore, 'append'), (ReviewedRawInfoStore, 'append'),
                         (SignalExecutor, 'execute_batch'), (SignalExecutor, 'prepare_inputs'),
                         (StructuredLLMSignalRunner, 'execute'), (StructuredLLMSignalRunner, 'execute_many'),
                         (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'record'),
                         (StructuredRoleClient, 'complete_json'),
                         (StructuredRoleClient, 'complete_json_with_token_scores'),
                         (StructuredRoleClient, 'complete_binary_token_with_scores')]:
        guards.enter_context(patch.object(target, name, side_effect=forbidden))
    store = open_raw_info_store(plan['reviewed_source_snapshot']['root'],
                                reviewed_snapshot=plan['reviewed_source_snapshot'])
    assert len(store.documents) == 1780
    before_records = canonical_json_hash([d.to_dict() for d in store.documents])
    pit = store.search(company, as_of=cutoff)
    source_filtered = [d for d in pit if _matches_source_type(d, request.source_types)]
    assert request.lookback_days is None
    deduped, duplicate_ids = _deduplicate_documents(source_filtered)
    ranked = _rank_documents(deduped, request)
    selected = _select_required_source_documents(ranked, request)
    resolver = EvidenceResolver(store)
    native = resolver.resolve(request, company_id=company, identity=plan['identity'], as_of=cutoff)
    assert [d.document_id for d in selected] == [r.document_id for r in native.documents]
    assert native.to_dict() == old['resolution']
    assert len(ranked) == 57 and len(selected) == 10
    query_tokens = _request_query_tokens(request)
    terms = {t.casefold() for t in re.findall(r'[A-Za-z0-9]+', request.query or '')
             if len(t) >= 3 and t.casefold() not in _LLM_SIGNAL_QUERY_STOP_WORDS}
    def lexical_scores(document):
        tokens = re.findall(r'[A-Za-z0-9]+', document.content.casefold())
        return {'distinct': len(terms.intersection(tokens)),
                'bounded_frequency': sum(min(tokens.count(t), 3) for t in terms)}
    def counter_key(document):
        score = lexical_scores(document)
        return (-score['distinct'], -score['bounded_frequency'],
                -document.available_at.timestamp(), document.document_id)
    counter_ranked = sorted(deduped, key=counter_key)
    counter_selected = _select_required_source_documents(counter_ranked, request)
    counter_ids = [d.document_id for d in counter_selected]
    def counter_selector(eligible, _request):
        by_id = {d.document_id: d for d in eligible}
        return tuple(by_id[i] for i in counter_ids)
    counter_native = resolver.resolve(request, company_id=company, identity=plan['identity'],
                                     as_of=cutoff, select_documents=counter_selector)
    assert [r.document_id for r in counter_native.documents] == counter_ids
    target_facts = [f for f in _sec_facts(tuple(deduped), cutoff) if f.tag in TAGS and f.start is None]
    latest_end = {tag: max((f.end for f in target_facts if f.tag == tag), default=None) for tag in TAGS}
    def fact_row(f):
        return {'tag': f.tag, 'unit': f.unit, 'value': f.value, 'start': f.start, 'end': f.end,
                'filed': f.filed, 'form': f.form, 'exact_span': f.exact_span,
                'document_id': f.document.document_id, 'content_hash': f.document.content_hash,
                'company_id': f.document.company_id, 'body_cik': read_content(f.document).get('cik'),
                'metadata_cik': f.document.metadata.get('cik'),
                'available_at': f.document.available_at.isoformat(),
                'exact_span_in_content': f.exact_span in f.document.content}
    def read_content(document):
        return json.loads(document.content)
    latest_rows = [fact_row(f) for f in target_facts if f.end == latest_end[f.tag]]
    rank_rows = []
    for i, document in enumerate(ranked, 1):
        rank_rows.append({'document_id': document.document_id, 'content_hash': document.content_hash,
                         'source_type': document.source_type, 'available_at': document.available_at.isoformat(),
                         'content_characters': len(document.content), 'native_rank': i,
                         'counter_rank': counter_ranked.index(document)+1,
                         'raw_substring_hit_count': _document_query_hit_count(document, query_tokens),
                         'per_native_token_counts': {t:document.content.casefold().count(t) for t in query_tokens},
                         'bounded_lexical': lexical_scores(document),
                         'native_selected': document in selected, 'counter_selected': document in counter_selected})
    def projection_inspection(documents):
        item = LLMSignalBatchInput(spec=spec, documents=tuple(documents), skill=skill)
        projections, lineage = _single_llm_signal_projection(item)
        facts = [f for f in _sec_facts(tuple(documents), cutoff) if f.tag in TAGS and f.start is None]
        return {'document_ids': [d.document_id for d in documents],
                'latest_periods_in_selected_documents': {tag:max((f.end for f in facts if f.tag==tag),default=None) for tag in TAGS},
                'native_projection_rows': projections,
                'projection_document_ids': sorted({p.document.document_id for p in lineage.values()}),
                'latest_exact_fact_projection_matches': [dict(row,
                    projection_ids=[p['projection_id'] for p in projections if p['document_id']==row['document_id']
                                    and p['exact_text']==row['exact_span']]) for row in latest_rows],
                'not_a_transmitted_prompt': True}
    old_projection = projection_inspection(selected)
    counter_projection = projection_inspection(counter_selected)
    materialized_by_id = {r['document_id']: r for r in manifest['documents']}
    used_bindings = [bind(Path(plan['reviewed_source_snapshot']['root'])/materialized_by_id[d.document_id]['path']) for d in deduped]
    assert all(bind(b['path']) == b for b in initial_bindings+used_bindings)
    assert before_records == canonical_json_hash([d.to_dict() for d in store.documents])
    assert not forbidden_calls
    write('native-resolution.json', native.to_dict())
    write('counterfactual-resolution.json', counter_native.to_dict())
    write('ranked-documents.json', rank_rows)
    write('latest-facts.json', {'latest_periods':latest_end, 'rows':latest_rows,
                              'all_target_instant_facts':[fact_row(f) for f in target_facts]})
    write('native-projection.json', old_projection)
    write('counterfactual-projection.json', counter_projection)
    result = {'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'signal_ref':REF,'case':plan['case'],'snapshot':plan['reviewed_source_snapshot'],
              'snapshot_documents':1780,'pit_company_documents':len(pit),'source_filtered':len(source_filtered),
              'deduplicated':len(deduped),'duplicate_ids':list(duplicate_ids),'ranked':len(ranked),'selected':len(selected),
              'request':request.to_dict(),'native_resolution_exact_saved_matrix':True,
              'native_selected_order':[d.document_id for d in selected], 'counter_selected_order':counter_ids,
              'native_coverage':native.coverage.to_dict(),'counter_coverage':counter_native.coverage.to_dict(),
              'latest_periods_in_qualified_pool':latest_end,
              'native_latest_periods':old_projection['latest_periods_in_selected_documents'],
              'counter_latest_periods':counter_projection['latest_periods_in_selected_documents'],
              'counter_policy':'Only diagnostic: full-document word tokens; projection policy distinct coverage, per-term min(count,3), available_at desc, ID; unchanged required-source/period selector. No production rank changed.',
              'counter_terms':sorted(terms),'bindings':initial_bindings+used_bindings,
              'bindings_unchanged':True,'view_records_unchanged':True,'forbidden_calls':forbidden_calls,
              'elapsed_seconds':monotonic()-started,
              'limits':'No ratio/Signal execution, model, GET, labels, append, Registry writes, fullprepare or old stage reentry.'}
    write('result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('bindings','native_selected_order','counter_selected_order')},indent=2))
