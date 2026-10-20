import contextlib, hashlib, json, socket, sys, unittest
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
import run_minimal_rounds as minimal
selectors = ['tests.test_companyfacts_capture_identity', 'tests.test_reviewed_companyfacts_profile', 'tests.test_data_backfill.HistoricalDataBackfillTests.test_company_facts_plan_materializes_point_in_time_raw_info', 'tests.test_sec_financial_availability_boundaries']
tripwires = {'socket':0,'labels':0,'fullprepare':0,'non_temporary_store':0}
def blocked(kind):
 def fail(*args, **kwargs):
  tripwires[kind] += 1
  raise AssertionError('forbidden ' + kind)
 return fail
original_init = RawInfoStore.__init__
def temporary_only(self, root=None, *args, **kwargs):
 if root is not None and not Path(root).resolve().is_relative_to(Path('/tmp').resolve()):
  # macOS TemporaryDirectory uses /var/folders; accept only the actual temp root.
  import tempfile
  if not Path(root).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
   return blocked('non_temporary_store')()
 return original_init(self, root, *args, **kwargs)
with contextlib.ExitStack() as stack:
 stack.enter_context(patch.object(socket, 'socket', blocked('socket')))
 for name in ('load','record','ground_truth'):
  stack.enter_context(patch.object(LabelStore, name, blocked('labels')))
 stack.enter_context(patch.object(minimal, 'prepare', blocked('fullprepare')))
 stack.enter_context(patch.object(minimal, 'LABELS', Path('/forbidden-unreadable-label-store')))
 stack.enter_context(patch.object(RawInfoStore, '__init__', temporary_only))
 suite = unittest.defaultTestLoader.loadTestsFromNames(selectors)
 result = unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'selectors':selectors,'tests':result.testsRun,'success':result.wasSuccessful(),'tripwires':tripwires},sort_keys=True))
sys.exit(not result.wasSuccessful())
