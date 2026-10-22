"""Build explicit pending-operation fixtures; never reenter original terminals."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import shutil
import run_mining_taxonomy_consumer_stage as stage
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
BASE=stage.BASE
ORIGINAL=stage.ROOT
OUTPUT=BASE/'cache-reconstruction.json'
if OUTPUT.exists():raise AssertionError('single-entry verification output')
def files(root):
 return {str(p.relative_to(root)):stage.binding(p)['sha256'] for p in sorted(root.rglob('*')) if p.is_file() and p.name!='.dispatch.lock'}
before=files(ORIGINAL)
results=[]
with TemporaryDirectory(prefix='mining-cache-fixture-') as directory:
 fixture=Path(directory).resolve()/'stage'
 shutil.copytree(ORIGINAL,fixture)
 # These are explicitly synthetic pending fixtures from completed snapshots,
 # not restored business completion markers or an actual interrupted process.
 removed=[]
 for key,name in [('actual','failure'),('namespace','completion')]:
  (fixture/key/(name+'.json')).unlink();removed.append(key+'/'+name+'.json')
  artifact=fixture/key/('failed-controller.json' if key=='actual' else 'boundary.json')
  artifact.unlink();removed.append(str(artifact.relative_to(fixture)))
 # Reconstruct the failed operation immediately before its blocked preparation.
 # It will recreate that exact journal and stop again at the original cap.
 blocked=[]
 for p in (fixture/'actual/requests').glob('*.json'):
  if not (fixture/'actual/exchange/receipts'/p.name).is_file():
   blocked.append(p.name);p.unlink();removed.append('actual/requests/'+p.name)
 assert len(blocked)==1
 native_receive=LocalRoleExchange.receive
 received=[]
 def cached_only(self,request,*,accounting_tokens,allow_dispatch=True):
  assert allow_dispatch is False, 'reconstruction attempted a new handoff'
  received.append(request['stage'])
  return native_receive(self,request,accounting_tokens=accounting_tokens,allow_dispatch=False)
 with patch.object(stage,'ROOT',fixture),patch.object(LocalRoleExchange,'receive',cached_only):
  for key in stage.SAMPLES:
   result=stage.advance(key)
   assert result['state']==('terminal_module_failure' if key=='actual' else 'completed_module_boundary')
   expected=before[key+('/failed-controller.json' if key=='actual' else '/boundary.json')]
   artifact=fixture/key/('failed-controller.json' if key=='actual' else 'boundary.json')
   assert stage.binding(artifact)['sha256']==expected
   native_count=len(list((fixture/key/'exchange/receipts').glob('*.json')))
   results.append({'sample':key,'state':result['state'],'original_receipts':native_count,
     'assembled_artifact_exact_equal':True,'domain_terminal_executed':False})
  after=files(fixture)
  # Fixture terminal seals intentionally contain its temporary absolute paths.
  compared={p:h for p,h in before.items() if p not in ('actual/failure.json','namespace/completion.json')}
  assert all(after.get(p)==h for p,h in compared.items())
  assert set(after)==set(before)
  assert files(ORIGINAL)==before
  stage.save(BASE,'cache-reconstruction',{'scope':'Explicit throwaway pending-operation fixtures from sealed copies; no original terminal reentry, no OS/process-kill or whole-loop recovery claim.',
   'samples':results,'removed_fixture_files':removed,'blocked_journal_recreated':blocked,
   'nonterminal_files_equal':len(compared),'cached_receive_calls':len(received),'new_dispatches':0,
   'original_all_files_unchanged':len(before),'original_root':str(ORIGINAL),'verification_script':stage.binding(Path(__file__))})
print('two cached operation fixtures reconstruct exact business artifacts; original terminals unchanged')
