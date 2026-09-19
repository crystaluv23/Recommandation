"""Replay exact V124 attempts 3/4/5 through the actual initialize adapter."""
import sys,json
from pathlib import Path
from datetime import datetime
from dataclasses import replace
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R))
from tests.evolution_runtime_test_support import ScriptedRoleCaller
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.scheme_evolution import default_information_plan
rows={x['attempt_id']:x for x in json.loads((R/'.delegation/fast-slow-20260919/v124/c01-case1-rejection.json').read_text())}
p=rows[3]['payload'];caller=ScriptedRoleCaller([rows[n]['output'] for n in (3,4,5)]);caller.max_structured_corrections=2
controller=LLMResearchController(caller);controller.set_evaluation_context(datetime.fromisoformat(p['evaluation_context']['prediction_time']))
plan=replace(default_information_plan(),initial_research_skill=p['initial_research_skill'])
out=controller.initialize(plan,p['basic_info']).value
assert caller.calls[0]['payload']==p
original=rows[3]['output']['next_information_needs'];expected=list(original);expected[3]=rows[5]['output']['next_information_needs'][3]
assert list(out.next_information_needs)==expected
assert len(out.supporting_evidence)==8
assert len(caller.calls)==3
print(json.dumps({'calls':len(caller.calls),'exact_original_payload':True,'final_needs':list(out.next_information_needs),'supporting_evidence':len(out.supporting_evidence)},indent=2))
