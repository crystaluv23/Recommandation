"""Independent synthetic H1 existence controls and exact Fact-pair refactor comparison."""
import dataclasses
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
sys.dont_write_bytecode = True
ROOT = Path('/Users/l/Project/Recommandation')
HERE = Path(__file__).resolve().parent
OLD = ROOT/'runs/diagnostics/h1_measurable_period_coverage_20261021_v1/driver/before-mining_agent_tools.py'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(OLD) == 'f922cb684a0370ae006402ecf32b0799089bf5064294bd7e318e967e4126854b'
from stock_opportunity_agent.research import mining_agent_tools as candidate
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.data.raw_info import RawInfoDocument
spec = importlib.util.spec_from_file_location('independent_pre_h1_refactor_tools', OLD)
old = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = old
spec.loader.exec_module(old)
NOW = datetime(2025, 8, 2, tzinfo=timezone.utc)
TAG = 'IndependentOperatingCashFlow'
binding_paths = [Path(candidate.__file__), ROOT/'src/stock_opportunity_agent/research/signal_evolution.py',
                 ROOT/'src/stock_opportunity_agent/research/evolution_core.py', OLD]
before = {str(p):sha(p) for p in binding_paths}

def row(value, end='2025-06-30', start=None, unit='USD', taxonomy='ns-a'):
    r = {'taxonomy':taxonomy,'tag':TAG,'unit':unit,'value':value,'end':end}
    if start is not None: r['start'] = start
    return r

def doc(rows, issuer='synthetic-1', ident='d1'):
    body = json.dumps({'schema_version':'sec-company-facts-document-v1','filing_date':'2025-08-01','facts':rows}, sort_keys=True, separators=(',',':'))
    return RawInfoDocument.create(document_id=ident, company_id=issuer, source_type='sec_company_facts',
                                  published_at=NOW, available_at=NOW, content=body)

def projected(rows_by_doc):
    return candidate.project_facts_from_documents(tuple(doc(rows,ident='doc-'+str(i)) for i,rows in enumerate(rows_by_doc)), case_ref='synthetic-case')

def pair_equivalent(name, rows_by_doc, expected):
    facts = projected(rows_by_doc)
    # Both algorithms see the same immutable attribute tuples, including exact refs/spans.
    a = tuple(old.EvidenceFact(**dataclasses.asdict(f)) for f in facts)
    b = candidate.build_same_concept_relations(facts)
    aa = [dataclasses.asdict(r) for r in old.build_same_concept_relations(a)]
    bb = [dataclasses.asdict(r) for r in b]
    assert aa == bb, (name,aa,bb)
    assert len(bb) == expected, (name,bb)
    return {'pair_count':len(bb),'exact_relation_fields_order_equal':True}

pair_controls = {
 'instant':([[row(120),row(100,'2024-06-30')]],1),
 'duration_one_pair':([[row(120,start='2025-01-01'),row(60,start='2025-04-01'),row(50,'2024-06-30','2024-04-01')]],1),
 'current_conflict':([[row(120),row(121),row(100,'2024-06-30')]],0),
 'nearest_prior_conflict_no_older_substitute':([[row(120),row(100,'2024-06-30'),row(101,'2024-06-30'),row(90,'2023-06-30')]],0),
 'calendar_numeric_duplicates':([[row(120,start='2025-01-01'),row(120.0,'20250630','20250101'),row('100','2024-06-30','2024-01-01')]],1),
 'currencies':([[row(120),row(100,'2024-06-30'),row(90,unit='EUR'),row(80,'2024-06-30',unit='EUR')]],2),
 'typed_namespaces':([[row(120),row(100,'2024-06-30'),row(300,taxonomy='ns-b'),row(100,'2024-06-30',taxonomy='ns-b')]],2),
 'doc_local':([[row(120)],[row(100,'2024-06-30')]],0),
 'source_order_reversed':([[row(100,'2024-06-30'),row(120)]],1),
}
results = {'fact_pair_equivalence':{},'h1_catalog_controls':{}}
for name,(docs,n) in pair_controls.items():
    results['fact_pair_equivalence'][name] = pair_equivalent(name,docs,n)

h1_controls = {
 'same_end_no_prior':([[row(120,start='2025-01-01'),row(60,start='2025-04-01')]],0),
 'current_conflict':(pair_controls['current_conflict'][0],0),
 'valid_quarter_amid_unmatched_halfyear':(pair_controls['duration_one_pair'][0],2),
 'namespace_no_stitch':([[row(120),row(100,'2024-06-30',taxonomy='ns-b')]],0),
 'document_no_stitch':(pair_controls['doc_local'][0],0),
 'unit_no_stitch':([[row(120),row(100,'2024-06-30',unit='EUR')]],0),
 'equivalent_duplicates_count_cases_once':(pair_controls['calendar_numeric_duplicates'][0],2),
 'instant_positive':(pair_controls['instant'][0],2),
 'nearest_prior_conflict':(pair_controls['nearest_prior_conflict_no_older_substitute'][0],0),
 'future_prior_does_not_help':([[row(120),{**row(100,'2024-06-30'),'filed':'2026-01-01'}]],0),
}
for name,(docs,expected_max) in h1_controls.items():
    all_docs, cases = [], []
    for i in range(2):
        issuer = 'synthetic-'+str(i)
        cases.append(('case-'+str(i),SimpleNamespace(company_id=issuer,prediction_time=NOW)))
        all_docs.extend(doc(rows,issuer=issuer,ident=name+'-'+str(i)+'-'+str(j)) for j,rows in enumerate(docs))
    original_bytes = [d.content for d in all_docs]
    manifest = SignalEvolutionEngine._h1_measurable_evidence_manifest(SimpleNamespace(raw_info_store=SimpleNamespace(documents=tuple(all_docs))),cases)
    rows = manifest['structured_financial_concepts']
    assert manifest['cohort_case_count'] == 2 and rows, (name,manifest)
    assert max(r['cases_with_comparable_records'] for r in rows) == expected_max, (name,manifest)
    assert all(0 <= r['cases_with_comparable_records'] <= r['case_count'] <= 2 for r in rows)
    assert [d.content for d in all_docs] == original_bytes
    assert all(set(r) == {'taxonomy','concept','source_display_name','unit','case_count','cases_with_comparable_records'} for r in rows)
    results['h1_catalog_controls'][name] = rows
assert {str(p):sha(p) for p in binding_paths} == before
results.update({'source_bindings':before,'product_source_unchanged_during_run':True,
                'scope':'Only synthetic documents + label-free SimpleNamespace unbound H1 method; no Engine/store constructor, actual-source run, model, GET, Signal, LabelStore or stage.'})
(HERE/'h1-counter-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'fact_pair_controls':len(pair_controls),'h1_controls':len(h1_controls),'all_passed':True}))
