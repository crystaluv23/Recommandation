"""Capture the Update view before its outcome relation; never supply or read labels."""
import hashlib, json, runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
p=Path(__file__).resolve().parent
h=runpy.run_path(str(p/'counterexamples.py'))
s,reg,store=h['fixture']()
def actual(*args):
    """ACTUALLY INVOKED custom declaration: source-bound runway branch."""
    return h['default_deterministic_signal_functions']()[s.function](*args)
def uninvoked(*args):
    """UNINVOKED validator declaration must not be rebound to the executed result."""
    raise AssertionError('Not invoked')
actual=h['signal_parameter_names']('positive_runway_max_months','negative_runway_min_months')(actual)
ex=h['SignalExecutor'](reg,store,deterministic_functions={s.function:actual})
b=ex.execute_batch((s.ref,),company_id='cik_0000000001',as_of=h['ASOF'])
r=b.results[0]
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
captured={}
def intercept(result,*args,**kwargs):
    captured.update(kwargs['classification_contract'])
    raise Captured()
try:
    with patch.object(mod,'signal_result_model_view',side_effect=intercept):
        engine._signal_update_evidence_packet('synthetic-update-case',NoLabels(),spec=s,result=r,resolution=b.resolutions[0])
except Captured: pass
report={'scope':'No model calls, no outcome/label objects; stopped at Update result view before outcome relation.','actual_executed_contract':expected,'supplied_update_contract':captured,'preserves_actual_invoked_callable':captured.get('execution',{}).get('contract')==expected['execution']['contract'],'captured_before_label_access':bool(captured),'source_hash':hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest()}
(p/'update-binding-counterexample.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('actual_executed_contract','supplied_update_contract')},indent=2))
