"""Replay original proposals through the actual adapter with original parent/meta context."""
import sys,json
from pathlib import Path
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R))
from tests.evolution_runtime_test_support import ScriptedRoleCaller
from stock_opportunity_agent.research.evolution_plan_roles import LLMInformationPlanProposer
from stock_opportunity_agent.research.scheme_evolution import InformationPlan,RoundMetaEntry
rows={x['attempt_id']:x for x in json.loads((R/'.delegation/fast-slow-20260919/v125/proposal-rejections.json').read_text())}
results=[]
for n in (1,3,5):
 p=rows[n]['payload']['proposal_context'];caller=ScriptedRoleCaller([rows[n]['output']]);agent=LLMInformationPlanProposer(caller,available_source_types=p['available_source_types']);parents=tuple(InformationPlan.from_dict(x) for x in p['parents']);meta=tuple(RoundMetaEntry.from_dict(x) for x in p['meta_info'])
 plan=agent.propose(**p['proposal_slot'],forbidden_plan_ids=(),parents=parents,meta_info=meta,prior=p['fixed_prior'])
 actual=caller.calls[0]['payload']['proposal_context'];diff=[k for k in p if p[k]!=actual.get(k)]
 assert not diff,diff
 assert len(caller.calls)==1
 results.append({'attempt':n,'calls':1,'exact_original_proposal_context':True,'parents':len(parents),'meta_entries':len(meta),'requests':len(plan.basic_info_policy.requests),'status':'accepted'})
print(json.dumps(results,indent=2))
