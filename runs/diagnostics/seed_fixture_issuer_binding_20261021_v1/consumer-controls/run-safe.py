"""Run only two consumer modules with temporary-store and no external readers."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
import run_minimal_rounds as minimal

OUT=Path(__file__).resolve().parent
ROOT=Path.cwd()
selectors=['tests.test_numeric_measurement_contract','tests.test_signal_card_measurement_scope']
watched=[ROOT/'tests/test_numeric_measurement_contract.py',ROOT/'tests/test_signal_card_measurement_scope.py',
 ROOT/'tests/test_signal_financials.py',ROOT/'src/stock_opportunity_agent/data/sec_company_facts.py',
 ROOT/'src/stock_opportunity_agent/signal_library.py',ROOT/'configs/signals_v1.json']
def bindings():
 return [{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in watched]
before=bindings()
counts={'network':0,'model':0,'labels':0,'real_store':0,'fullprepare':0}
def forbidden(kind):
 def fail(*args,**kwargs):
  counts[kind]+=1
  raise AssertionError('forbidden '+kind)
 return fail
initial=RawInfoStore.__init__
def only_temp(self,root=None,*args,**kwargs):
 if root is not None and not Path(root).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
  return forbidden('real_store')()
 return initial(self,root,*args,**kwargs)
with ExitStack() as stack:
 for obj,name,kind in ((socket,'socket','network'),(socket,'create_connection','network'),
  (LabelStore,'load','labels'),(LabelStore,'record','labels'),(LabelStore,'ground_truth','labels'),
  (minimal,'prepare','fullprepare'),
  *[(StructuredRoleClient,name,'model') for name in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores')]):
  stack.enter_context(patch.object(obj,name,forbidden(kind)))
 stack.enter_context(patch.object(minimal,'LABELS',Path('/forbidden-unreadable-label-store')))
 stack.enter_context(patch.object(RawInfoStore,'__init__',only_temp))
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(selectors))
summary={'selectors':selectors,'tests':result.testsRun,'success':result.wasSuccessful(),
 'failures':len(result.failures),'errors':len(result.errors),'tripwires':counts,
 'bindings_before':before,'bindings_after':bindings()}
with (OUT/'candidate-result.json').open('x') as handle:
 json.dump(summary,handle,indent=2);handle.write('\n')
print(json.dumps({k:v for k,v in summary.items() if not k.startswith('bindings_')}))
sys.exit(not result.wasSuccessful())
