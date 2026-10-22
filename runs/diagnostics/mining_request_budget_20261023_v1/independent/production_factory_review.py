"""Execute production role construction with an empty synthetic host; stop at controller factory.

No business cases/labels/checks, controller actions or model calls are executed.
"""
from pathlib import Path
exec(Path(__file__).with_name('native_review_v3.py').read_text().split("with patch.object(socket,")[0])
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
class Captured(EvolutionControlFlow):pass
captured=[]
def factory(**kwargs):
 m=kwargs['model'];captured.append({'request_limits':m.request_limits,'reserved_calls':m.reserved_calls,'reserved_tokens':m.reserved_tokens,'seed':kwargs['seed']});raise Captured()
c=client('factory');host=SimpleNamespace(mining_model=SimpleNamespace(caller=c,request_token_budget=32768),slow_role_identity_guards=(),_discovery_cases_by_id={},raw_info_store=SimpleNamespace(documents=()),mining_heavy_action_limit=None,_mining_context=lambda **k:{'capability_backlog':{},'stable_signal_cards':[]},_h1_measurable_evidence_manifest=lambda pairs:{},_new_mining_controller=factory)
try:SignalEvolutionEngine._run_controller_mining_axis(host,cycle_id=1,axis_id='synthetic-no-business-axis',research_axis={'axis_id':'synthetic-no-business-axis'},dev_cases=(),check_cases=(),labels_by_case_id={})
except Captured:pass
else:raise AssertionError('did not reach actual production controller factory')
assert len(captured)==1 and captured[0]['request_limits']=={'single_limit':32768}
assert not list(c.local_role_exchange.root.glob('inbox/*.json'))
p=R/'src/stock_opportunity_agent/research/signal_evolution.py'
save('production-factory-result',{'pass':True,'actual_method':'SignalEvolutionEngine._run_controller_mining_axis','captured':captured,'source_binding':{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()},'scope':'executed production role construction until synthetic sentinel at controller factory; no controller run/no model/no business cases; does not establish full production semantic execution','external_API':0,'new_business_labels':0,'check_LockedTest':0})
print(json.dumps(captured))
