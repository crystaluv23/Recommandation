"""Native local regression, with real network and label-loading tripwires."""
import sys
sys.dont_write_bytecode=True
import hashlib,json,socket,ssl,time,unittest
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.cases.label_store import LabelStore
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
paths=[REPO/'src/stock_opportunity_agent/research'/n for n in ('stage_contracts.py','mining_controller.py','mining_role_model.py')]+[REPO/'spec/src/stock_opportunity_agent/research'/n for n in ('stage_contracts.md','signal_mining_agent.md')]+[REPO/'tests/test_need_row_authoring_contract.py']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p):sha(p) for p in paths}
selectors=['tests.test_need_row_authoring_contract','tests.test_mining_controller','tests.test_mining_role_model','tests.test_mining_tool_contracts','tests.test_stage_contracts','tests.test_assigned_slow_target_stage','tests.test_reviewed_slow_feedback_stage']
suite=unittest.defaultTestLoader.loadTestsFromNames(selectors);counts={'network':0,'LabelStore.load':0}
def deny(kind):
 def call(*a,**kw):counts[kind]+=1;raise AssertionError(kind+' forbidden')
 return call
start=time.monotonic()
with (HERE/'connected-tests.log').open('x') as log:
 with patch.object(socket,'socket',deny('network')),patch.object(socket,'create_connection',deny('network')),patch.object(LabelStore,'load',deny('LabelStore.load')):
  result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
after={str(p):sha(p) for p in paths}
record={'selectors':selectors,'tests':result.testsRun,'failures':[{'selector':t.id(),'traceback':trace} for t,trace in result.failures],'errors':[{'selector':t.id(),'traceback':trace} for t,trace in result.errors],'passed':result.wasSuccessful(),'seconds':time.monotonic()-start,'tripwires':counts,'bindings_before':before,'bindings_after':after,'unchanged':before==after}
with (HERE/'connected-result.json').open('x') as out:json.dump(record,out,indent=2,sort_keys=True);out.write('\n')
print(json.dumps({k:record[k] for k in ('tests','passed','seconds','tripwires','unchanged')}))
raise SystemExit(0 if result.wasSuccessful() and before==after and not any(counts.values()) else 1)
