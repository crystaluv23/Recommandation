"""Exercise real validator concept gates using isolated synthetic Registry and fixture bodies."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import ast,hashlib,json
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.signal_library import SignalSpec,SignalExecutionType,SignalModality,SignalRetrievalPolicy,SignalRegistry
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator,signal_description_concept_contracts
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
expected={'src/stock_opportunity_agent/signal_library.py':'2dd6278b4c7162aa7a11b355792214557aa7d6871910e6530a0f5aeb56def494','src/stock_opportunity_agent/research/signal_evolution.py':'2d79e35a090966c3f5e38384b5332cc40822cce56af6fc8e5d482b78145e8578'}
for path,digest in expected.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
registry=SignalRegistry(OUT/'candidate-validator-registry/signals',candidate_root=OUT/'candidate-validator-registry/candidates')
v=SignalCandidateValidator(registry,llm_runner=None);rows=[]
windows=[('2025-01-01','2025-03-31',150),('2024-01-01','2024-03-31',100),('2024-10-01','2024-12-31',120),('2023-10-01','2023-12-31',100)]
facts=[dict(tag='Revenues',start=s,end=e,value=value,unit='USD') for s,e,value in windows]+[dict(tag='GrossProfit',start='2025-01-01',end='2025-03-31',value=30,unit='USD'),dict(tag='GrossProfit',start='2024-01-01',end='2024-03-31',value=10,unit='USD')]
content=json.dumps(dict(schema_version='sec-company-facts-document-v1',cik='0000000001',filing_date='2025-05-08',form='10-Q',accession_number='synthetic',facts=facts),sort_keys=True,separators=(',',':'))
fixture=dict(name='independent-synthetic-concept-control',company_id='cik_0000000001',as_of='2025-05-30T00:00:00+00:00',expected='positive',documents=[dict(document_id='synthetic-facts',source_type='sec_company_facts',published_at='2025-05-08T00:00:00+00:00',available_at='2025-05-09T00:00:00+00:00',content=content,metadata={'cik':'0000000001'})])
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 for function,description in [('financial.gross_margin_change_yoy','Measure same-window gross margin change.'),('financial.revenue_acceleration_adjacent','Measure immediately adjacent revenue acceleration.')]:
  spec=SignalSpec(signal_id='independent_'+function.rsplit('.',1)[1],version=1,category='financial',description=description,execution_type=SignalExecutionType.DETERMINISTIC,function=function,source_types=('financials',),modality=SignalModality.STRUCTURED,retrieval_policy=SignalRetrievalPolicy(query_terms=('revenue sales gross profit',)))
  positive=v.validate(spec,skill=None,tests=[fixture]);assert positive.accepted and positive.executed_tests==1,positive
  negative=v.validate(replace(spec,description='Measure cash reserve changes.'),skill=None,tests=[fixture]);assert not negative.accepted and negative.executed_tests==0 and any('definition-to-implementation mismatch' in s for s in negative.reasons)
  rows.append(dict(function=function,positive=dict(accepted=positive.accepted,reasons=list(positive.reasons),executed=positive.executed_tests),negative=dict(accepted=negative.accepted,reasons=list(negative.reasons),executed=negative.executed_tests)))
 contracts=signal_description_concept_contracts(v.deterministic_functions)
 assert contracts['financial.gross_margin_change_yoy']==contracts['financial.gross_margin_change']
 assert contracts['financial.revenue_acceleration_adjacent']==contracts['financial.revenue_acceleration']
(OUT/'candidate-concept-review.json').write_text(json.dumps(dict(status='passed',code_bindings=expected,rows=rows,old_new_concept_aliases_equal=True,real_gpre_execute_calls=0,synthetic_fixture_execute_calls=2,synthetic_wrong_concept_pre_execution_rejections=2,models=0,network_calls=0),indent=2)+'\n')
print(json.dumps(dict(status='passed',positive=2,wrong_concept_rejected=2)))
