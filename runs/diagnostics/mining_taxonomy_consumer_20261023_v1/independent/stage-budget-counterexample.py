"""Capture oversized actual native request before receive, in an isolated local diagnostic."""
import hashlib,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path('/Users/l/Project/Recommandation/scripts')))
import run_mining_taxonomy_consumer_stage as stage
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
base=Path('/Users/l/Project/Recommandation/runs/diagnostics/mining_taxonomy_consumer_20261023_v1')
request=json.loads((base/'baseline/requests/eabb9371dcb7384e46adbf7845d178d281bd9842cbd1d8dbb1294d7ef98df95b.json').read_text())['request']
view=json.loads(next(m['content'] for m in request['messages'] if m['role']=='user'))
view['last_action_result']['masked']='X'*30000  # Synthetic already-returned context, no new source/answer claim.
with tempfile.TemporaryDirectory(dir=base/'independent/tmp') as td:
 root=Path(td);report={'scope':'Isolated native input-only oversized context; no receive, inbox, model or external API.','source_sha256':hashlib.sha256(Path(stage.__file__).read_bytes()).hexdigest()}
 with stage.guards():
  client=stage.make_client(root,{'concept':'NetCashProvidedByUsedInOperatingActivities'},{'limits':stage.LIMITS},input_only=True)
  try:MiningAgentRoleModel(client,max_output_tokens=2000).next_action(view)
  except BaseException as exc:report.update(stopped_type=type(exc).__name__,stopped_message=str(exc))
 records=list((root/'requests').glob('*.json'))
 report.update(request_count=len(records),inboxes=len(list(root.rglob('inbox/*.json'))))
 if records:
  report['reservation']=stage.request_reservation(records[0]);report['max_request_tokens']=stage.LIMITS['max_request_tokens'];report['max_case_tokens']=stage.LIMITS['max_case_tokens']
 report['oversize_accepted_as_input_ready']=report.get('stopped_type')=='InputCaptured' and report.get('reservation',0)>stage.LIMITS['max_request_tokens']
 (base/'independent/stage-budget-counterexample.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
