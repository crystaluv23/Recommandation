"""Synthetic source-only confirmation that actual critic memory cannot recover omitted metadata."""
import json,hashlib
from pathlib import Path
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
p=Path(__file__).resolve().parent
row={'case_index':1,'stop_reason':'finalized','termination_trigger':None,'self_reflection':{}}
index=ReflectionMemoryIndex.from_case_rows((row,),owner_ref='reflection_plan:'+'f'*64)
contents=[s['content'] for s in index._sources.values()]
report={'scope':'Synthetic no-outcome source row, no business labels or model calls.','input_source_row':row,'registered_source_contents':contents,'classification_contract_anywhere':any('classification_contract' in json.dumps(x) for x in contents),'source_count':len(contents),'source_confirmed_chain':['CaseReflectionEvidence fields/from_trajectory/to_dict do not copy final_context or classification declarations.','Actual LLMPlanCritic builds helper summary, then replaces trajectories with trajectories_view omitting signal_rounds.','Memory._cases registers only _FACT_FIELDS outcome snapshot and supplied CaseReflectionEvidence row.','Slow original_case_reflections serializes this same CaseReflectionEvidence schema, so no saved declaration is available for original-source reads.'],'conclusion':'T10 actual critic/Slow preservation fails for the new metadata despite helper/posthoc retention; no canonical mutation is authorized by this audit.'}
report['source_hashes']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (Path('src/stock_opportunity_agent/research/evolution_core.py'),Path('src/stock_opportunity_agent/research/evolution_plan_roles.py'),Path('src/stock_opportunity_agent/research/evolution_reflection_memory.py'))}
(p/'critic-slow-gap.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'source_count':len(contents),'classification_contract_anywhere':report['classification_contract_anywhere'],'conclusion':report['conclusion']},indent=2))
