PYTHONPATH=.:src:scripts /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 - <<'PY'
from dataclasses import replace
import json
from pathlib import Path
from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState,SignalSelectionDecision
from stock_opportunity_agent.research.evolution_research_validation import _validate_research_state_refs
from stock_opportunity_agent.signal_library import SignalBatchResult,SignalResult
sample=json.loads(Path('runs/diagnostics/reviewed_owned_temporal_stage_20261021_v1/p01/inputs.json').read_text())['sample']
prior=ResearchState.from_dict(sample['prior_state']);batch=SignalBatchResult(tuple(SignalResult.from_dict(row) for row in sample['results']),signal_calls=2)
selections=tuple(SignalSelectionDecision.from_dict(row) for row in sample['selections'])
row={'need_index':4,'answer_scope':'unanswered','residual_need':None,'evidence_refs':[],'reason':'The unavailable measurement does not resolve the compound financial need.'}
for text in ['Operating cash flow margin is weak.','Operating cash flow margin is 0%.']:
 state=replace(prior,current_beliefs=prior.current_beliefs+(text,))
 try:
  _validate_research_state_refs(state,phase='reflect',previous_state=prior,batch=batch,selections=selections,need_dispositions=[row],evaluation_context={'prediction_time':sample['prediction_time']})
  print(json.dumps({'synthetic_appended_belief_on_actual_frozen_seed':text,'complete_state_parser':'accepted','new_evidence_added':False}))
 except StructuredValidationError as e:
  print(json.dumps({'synthetic_appended_belief_on_actual_frozen_seed':text,'complete_state_parser':'rejected','issues':[i.code for i in e.issues]}))
PY
