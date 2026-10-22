"""Same actual-vs-uninvoked-map counterexample under the revised packet API, before labels."""
import hashlib,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
p=Path(__file__).resolve().parent
h={'__file__':str(p/'counterexamples.py')}
exec((p/'counterexamples.py').read_text().split("check('same_positive_scalar_different_states_and_equal_boundary'")[0],h)
s,reg,store=h['fixture']()
def actual(*args):
    """ACTUALLY INVOKED custom declaration: source-bound runway branch."""
    return h['default_deterministic_signal_functions']()[s.function](*args)
def uninvoked(*args):
    """UNINVOKED validator declaration must not be rebound to the executed result."""
    raise AssertionError('Not invoked')
actual=h['signal_parameter_names']('positive_runway_max_months','negative_runway_min_months')(actual)
ex=h['SignalExecutor'](reg,store,deterministic_functions={s.function:actual})
b=ex.execute_batch((s.ref,),company_id='cik_0000000001',as_of=h['ASOF']);r=b.results[0]
expected=ex.classification_contracts_for((r,))[s.ref]
import stock_opportunity_agent.research.signal_evolution as mod
engine=object.__new__(mod.SignalEvolutionEngine)
engine.validator=SimpleNamespace(deterministic_functions={s.function:uninvoked})
engine.slow_role_identity_guards=()
engine.evidence_resolver=SimpleNamespace(load_documents=lambda resolution,**kwargs:tuple(store._documents.values()))
class NoLabels:
    prediction_time=h['ASOF']
    @property
    def ground_truth(self): raise AssertionError('Labels forbidden')
class Captured(Exception): pass
rows=[]
for name,value in (('actual_saved_execution_declaration',expected),('no_execution_declaration',None)):
    captured={}
    def intercept(result,*args,**kwargs):
        captured['supplied']=kwargs.get('classification_contract');raise Captured()
    try:
        with patch.object(mod,'signal_result_model_view',side_effect=intercept):
            engine._signal_update_evidence_packet('synthetic-update-case',NoLabels(),spec=s,classification_contract=value,result=r,resolution=b.resolutions[0])
    except Captured: pass
    rows.append({'case':name,'pass':captured.get('supplied')==value,'supplied_contract':captured.get('supplied'),'no_label_access':bool(captured)})
report={'scope':'Same actual-vs-validator-map counterexample, revised explicit per-case packet API. No labels or models.','checks':rows,'pass':all(r['pass'] and r['no_label_access'] for r in rows),'source_hash':hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest(),'additional_source_observation':'_run_one_signal_update captures sidecar immediately for each exact result and later passes only same case_id + result identity; missing declaration remains None; no validator-map reconstruction.'}
(p/'update-binding-recheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'pass':report['pass'],'source_hash':report['source_hash'],'cases':[{'case':r['case'],'pass':r['pass']} for r in rows]},indent=2))
