"""One root-authorized actual-source temporary frontier check, with no dispatch."""
import sys
sys.dont_write_bytecode=True
import hashlib,json,time
from pathlib import Path
from unittest.mock import patch
from scripts import run_assigned_slow_target_stage as stage
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
HERE=Path(__file__).resolve().parent
ROOT=HERE/'temp-native-preflight'
assert not ROOT.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[Path(stage.__file__), stage.SPEC,stage.REPO/'src/stock_opportunity_agent/research/signal_evolution.py',stage.REPO/'tests/test_assigned_slow_target_stage.py']
before={str(p):sha(p) for p in paths}
counts={'exchange_receive':0}
def deny(*args,**kwargs):
    counts['exchange_receive']+=1
    raise AssertionError('preflight cannot receive or dispatch')
start=time.monotonic()
with patch.object(stage,'ROOT',ROOT),patch.object(LocalRoleExchange,'receive',deny):
    result=stage.prepare(ROOT)
after={str(p):sha(p) for p in paths}
record={'result':result,'seconds':time.monotonic()-start,'counts':counts,'before':before,'after':after,'unchanged':before==after,'scope':'One temporary real-source native prepare; no raw answer, no dispatch, no formal stage; first failure retained without rerun.'}
with (HERE/'temp-native-preflight-result.json').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(record))
raise SystemExit(0 if result['status']=='prepared_not_dispatched' and before==after and not counts['exchange_receive'] else 1)
