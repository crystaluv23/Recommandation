"""No-answer native prepare/pending probe. Temporary artifacts are not a frozen run."""
import hashlib,json
from pathlib import Path
import tempfile
from unittest.mock import patch
import run_reviewed_fast_prefix as prefix
from stock_opportunity_agent.artifacts import canonical_json_hash

def main():
 with patch('socket.socket',side_effect=AssertionError('network forbidden')),tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp)/'prefix'
  prepared=prefix.prepare(root,Path('reports/reviewed-fast-prefix-expectations-20261019.json'))
  first,second=prefix.resume(root),prefix.resume(root)
  inbox=json.loads(Path(first['pending'][0]['inbox_path']).read_text())
  messages=json.dumps(inbox['messages'],ensure_ascii=False)
  payload=json.loads(inbox['messages'][-1]['content'])
  return {'scope':'temporary native no-answer preflight; not formal freeze or fresh model behavior',
   'prepared':prepared,'first_status':first['status'],'stage':first['pending'][0]['stage'],
   'request_hash':first['pending'][0]['request_hash'],'repeat_equal':first==second,
   'inboxes':len(list((root/'exchange/inbox').glob('*.json'))),'receipts':first['independent_receipts'],
   'runtime_limits':prefix.LIMITS.to_dict(),'max_local_calls':32,
   'masked_identity':not any(term in messages for term in ('Bumble','BMBL','cik_0001830043')),
   'oracle_not_in_request':'acceptance_rules' not in messages and 'predeclared' not in messages,
   'evaluation_anchor_present':'evaluation_anchor' in payload,
   'external_llm_calls':0,'readonly_data_requests':0,'role_answers':0,
   'code':[{'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
    for p in ('scripts/run_reviewed_fast_prefix.py','src/stock_opportunity_agent/research/evolution_core.py',
     'src/stock_opportunity_agent/research/evolution_plan_roles.py','src/stock_opportunity_agent/research/evolution_output_validation.py')]}
if __name__=='__main__': print(json.dumps(main(),indent=2))
