PYTHONPATH=.:src:scripts /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 - <<'PY'
from dataclasses import replace
from datetime import datetime,timezone
import json
from tests.test_unavailable_finding_repair import UnavailableFindingRepairTests as T
from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState,ResearchEvidenceRef
from stock_opportunity_agent.research.evolution_research_validation import _validate_research_state_refs
from stock_opportunity_agent.signal_library import SignalResult,SignalValue,SignalEvidence,SignalBatchResult
f=T();rows=[]
def inspect(name,prior,state,batch):
 try:_validate_research_state_refs(state,phase='reflect',previous_state=prior,batch=batch,need_dispositions=[]);issues=[]
 except StructuredValidationError as e:issues=[{'code':i.code,'paths':i.paths,'mechanical_action':i.repair_context.get('mechanical_action')} for i in e.issues]
 rows.append({'control':name,'issues':issues})
for text in ['Customer concentration is weak.','Customer concentration is 0%.','Customer concentration is unknown, but customer concentration is weak.']:
 prior=f.prior();inspect(text,prior,replace(prior,current_beliefs=prior.current_beliefs+(text,)),f.batch())
claim='Customer concentration was not high in the reported period.'
ref=ResearchEvidenceRef(kind='signal',signal_ref='customer_concentration:v2',evidence_group='supporting',evidence_index=0,claim=claim)
source=SignalResult(signal_id='customer_concentration',version=2,value=SignalValue.NEUTRAL,confidence=.5,interpretation=claim,supporting_evidence=(SignalEvidence('native-offline-source',claim,datetime(2025,9,1,tzinfo=timezone.utc)),))
prior=f.prior();inspect('same-topic success exact adopted claim',prior,replace(prior,current_beliefs=prior.current_beliefs+(claim,),supporting_evidence=prior.supporting_evidence+(ref,)),SignalBatchResult(f.batch().results+(source,),signal_calls=3))
prior=replace(f.prior(),supporting_evidence=f.prior().supporting_evidence+(ResearchEvidenceRef(kind='basic_info',projection_id='prior-concentration',claim=claim,exact_text=claim),))
inspect('same-topic retained exact BasicInfo claim',prior,replace(prior,current_beliefs=prior.current_beliefs+(claim,)),f.batch())
print(json.dumps(rows,indent=2))
PY
