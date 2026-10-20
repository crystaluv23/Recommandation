"""Native H1 capability-count controls, no Engine instance, labels or model.

Baseline explicitly loads saved native core then saved native engine module;
asserts the unbound method and its actual context-selector global use snapshots.
Other transitive imports are not claimed to be an isolated old whole Engine.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest

parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');parser.add_argument('--result',required=True);opts=parser.parse_args()
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
def forbidden(*args,**kwargs):raise AssertionError('no network/model permitted')
socket.create_connection=forbidden;socket.socket.connect=forbidden
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore
import stock_opportunity_agent.research as research_package

def load_native(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
if opts.baseline:
    core=load_native('stock_opportunity_agent.research.evolution_core',HERE/'baseline-modules/evolution_core.py')
    research_package.evolution_core=core
    native=load_native('independent_h1_baseline_native',HERE/'baseline-modules/signal_evolution.py')
else:
    from stock_opportunity_agent.research import signal_evolution as native
method=native.SignalEvolutionEngine._h1_measurable_evidence_manifest
selector=method.__globals__['_company_facts_context']
if opts.baseline:
    assert Path(method.__code__.co_filename).resolve()==(HERE/'baseline-modules/signal_evolution.py').resolve()
    assert Path(selector.__code__.co_filename).resolve()==(HERE/'baseline-modules/evolution_core.py').resolve()
NOW=datetime(2025,8,2,tzinfo=timezone.utc);TAG='NetCashProvidedByUsedInOperatingActivities';OBS={}

def row(value,start='2025-01-01',end='2025-06-30',unit='USD',taxonomy='us-gaap',**extra):
    return {'taxonomy':taxonomy,'tag':TAG,'label':'Operating Cash Flow','unit':unit,'start':start,'end':end,'value':value,**extra}

def manifest(groups,*,legacy=False,available=None,large_label=False):
    docs=[];pairs=[]
    for n in (1,2):
        company=f'h1-synthetic-{n}';pairs.append((f'synthetic-case-{n}',SimpleNamespace(company_id=company,prediction_time=NOW)))
        for group_index,rows in enumerate(groups):
            if large_label:rows=[{**r,'label':'L'*15000} for r in rows]
            if legacy:
                facts={}
                for r in rows:
                    leaf={k:r[k] for k in ('start','end') if r.get(k) is not None};leaf['val']=r['value']
                    concept=facts.setdefault(r['taxonomy'],{}).setdefault(TAG,{'label':'Operating Cash Flow','units':{}})
                    concept['units'].setdefault(r['unit'],[]).append(leaf)
                payload={'facts':facts}
            else:payload={'schema_version':'sec-company-facts-document-v1','filing_date':'2025-08-01','facts':rows}
            doc=RawInfoDocument.create(document_id=f'h1-doc-{n}-{group_index}',company_id=company,source_type='sec_company_facts',
                published_at=datetime(2025,8,1,tzinfo=timezone.utc),available_at=(available or {}).get(group_index,NOW),
                content=json.dumps(payload,sort_keys=True,separators=(',',':')))
            docs.append(doc)
    # Actual unbound native method; only existing raw_info_store dependency supplied.
    result=method(SimpleNamespace(raw_info_store=RawInfoStore(documents=docs)),pairs)
    OBS[unittest.util.strclass(H1Catalog) if False else str(len(OBS))]={'manifest':result,'doc_ids':[d.document_id for d in docs]}
    return result

def counts(result):
    return {(r['taxonomy'],r['unit']):(r['case_count'],r['cases_with_comparable_records']) for r in result['structured_financial_concepts']}

class H1Catalog(unittest.TestCase):
    def test_unique_typed_and_legacy_pair(self):
        rows=[row(150),row(100,'2024-01-01','2024-06-30')]
        for legacy in (False,True):self.assertEqual(counts(manifest([rows],legacy=legacy)),{('us-gaap','USD'):(2,2)})

    def test_same_end_two_durations_is_not_pair(self):
        rows=[row(150),row(75,'2025-04-01')]
        for legacy in (False,True):self.assertEqual(counts(manifest([rows],legacy=legacy)),{('us-gaap','USD'):(2,0)})

    def test_two_valid_duration_pairs_count_each_case_once(self):
        rows=[row(150),row(75,'2025-04-01'),row(100,'2024-01-01','2024-06-30'),row(50,'2024-04-01','2024-06-30')]
        self.assertEqual(counts(manifest([rows])),{('us-gaap','USD'):(2,2)})

    def test_one_conflicted_branch_other_valid_remains_capability(self):
        rows=[row(150),row(151),row(75,'2025-04-01'),row(100,'2024-01-01','2024-06-30'),row(50,'2024-04-01','2024-06-30')]
        for legacy in (False,True):self.assertEqual(counts(manifest([rows],legacy=legacy)),{('us-gaap','USD'):(2,2)})

    def test_all_current_branches_conflicted(self):
        rows=[row(150),row(151),row(100,'2024-01-01','2024-06-30')]
        for legacy in (False,True):self.assertEqual(counts(manifest([rows],legacy=legacy)),{('us-gaap','USD'):(2,0)})

    def test_nearest_prior_conflict_no_fallback_to_older(self):
        rows=[row(150),row(100,'2024-01-01','2024-06-30'),row(101,'2024-01-01','2024-06-30'),row(80,'2023-01-01','2023-06-30')]
        self.assertEqual(counts(manifest([rows])),{('us-gaap','USD'):(2,0)})

    def test_no_cross_document_pair(self):
        self.assertEqual(counts(manifest([[row(150)],[row(100,'2024-01-01','2024-06-30')]])),{('us-gaap','USD'):(2,0)})

    def test_no_cross_namespace_or_unit_pair(self):
        rows=[row(150,taxonomy='namespace-a'),row(100,'2024-01-01','2024-06-30',taxonomy='namespace-b'),row(900,unit='EUR'),row(800,'2024-01-01','2024-06-30',unit='GBP')]
        for legacy in (False,True):
            c=counts(manifest([rows],legacy=legacy));self.assertEqual(len(c),4);self.assertTrue(all(value==(2,0) for value in c.values()))

    def test_available_pair_does_not_require_nonzero_ratio_denominator(self):
        self.assertEqual(counts(manifest([[row(150),row(0,'2024-01-01','2024-06-30')]])),{('us-gaap','USD'):(2,2)})

    def test_PIT_future_doc_cannot_supply_prior(self):
        self.assertEqual(counts(manifest([[row(150)],[row(100,'2024-01-01','2024-06-30')]],available={1:datetime(2025,8,3,tzinfo=timezone.utc)})),{('us-gaap','USD'):(2,0)})

    def test_numeric_spellings_not_conflicting_values(self):
        self.assertEqual(counts(manifest([[row('150.0'),row(150),row(100,'2024-01-01','2024-06-30')]])),{('us-gaap','USD'):(2,2)})

    def test_bounded_projection_and_value_free_output(self):
        self.assertEqual(manifest([[row(150),row(100,'2024-01-01','2024-06-30')]],large_label=True)['structured_financial_concepts'],[])
        result=manifest([[row(150),row(100,'2024-01-01','2024-06-30')]])
        forbidden_keys={'value','val','records','record_values','company_id','label_map','ground_truth'}
        def check(x):
            if isinstance(x,dict):
                self.assertFalse(forbidden_keys.intersection(x))
                for v in x.values():check(v)
            elif isinstance(x,list):
                for v in x:check(v)
        check(result);self.assertEqual(result['cohort_case_count'],2)

class Results(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
    def addSuccess(self,t):super().addSuccess(t);self.rows.append({'test':t.id(),'status':'PASS'})
    def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'test':t.id(),'status':'FAIL','detail':self._exc_info_to_string(e,t)})
    def addError(self,t,e):super().addError(t,e);self.rows.append({'test':t.id(),'status':'ERROR','detail':self._exc_info_to_string(e,t)})

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(H1Catalog))
    bound={}
    for label,obj in [('H1_unbound_method',method),('actual_context_selector_global',selector),('actual_typed_context_selector',selector.__globals__['_typed_company_facts_context'])]:
        f=Path(obj.__code__.co_filename).resolve();bound[label]={'function':obj.__qualname__,'file':str(f),'file_sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
    data={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'records':result.rows,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'baseline':opts.baseline,'actual_callable_bindings':bound,
        'observations':OBS,'scope':'Unbound native H1 method + minimal self.raw_info_store; two synthetic cases per control. No Engine/Workspace instance, labels/GroundTruth, model/role, network, fullstage, Signal or old-stage entry. Not fresh-role behavior proof.'}
    Path(opts.result).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');sys.exit(0 if result.wasSuccessful() else 1)
