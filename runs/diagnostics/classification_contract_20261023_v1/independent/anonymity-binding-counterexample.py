"""Check anonymous final assembly with a literal alias in the actual callable declaration."""
import hashlib,json,runpy
from pathlib import Path
p=Path(__file__).resolve().parent
h=runpy.run_path(str(p/'counterexamples.py'))
s,reg,store=h['fixture'](); default=h['default_deterministic_signal_functions']()[s.function]
@h['signal_parameter_names']('positive_runway_max_months','negative_runway_min_months')
def actual(*args):
    """Private Issuer Inc. is example text; actual predicate remains the source-bound runway branches."""
    return default(*args)
ex=h['SignalExecutor'](reg,store,deterministic_functions={s.function:actual})
b=ex.execute_batch((s.ref,),company_id='cik_0000000001',as_of=h['ASOF']);r=b.results[0]
d=ex.classification_contracts_for((r,))
rounds=(h['SignalRound'](h['NEEDS'],(h['intent'](s.ref),),b),)
c=h['_assemble_final_context'](plan=h['default_information_plan'](),company_id='cik_0000000001',additional_identity_aliases=('Private Issuer Inc.',),basic_info={'requests':[]},state=h['STATE'],rounds=rounds,prediction_time=h['ASOF'],signal_classification_contracts=(d,))
projected=h['metadata'](c['signal_rounds'][0]['batch']['results'][0])['classification_contract']
report={'scope':'Synthetic actual invoked override; no labels/models/network; final assembly with existing alias masking.','input_declaration':d[s.ref],'saved_projected_declaration':projected,'alias_removed': 'Private Issuer Inc.' not in json.dumps(c),'saved_view_accepted':None}
try:
    h['_require_context_signal_pit'](c)
    report['saved_view_accepted']=True
except Exception as e:
    report.update(saved_view_accepted=False,error_type=type(e).__name__,error=str(e))
(p/'anonymity-binding-counterexample.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('input_declaration','saved_projected_declaration')},indent=2))
