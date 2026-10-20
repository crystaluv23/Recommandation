"""Run only the requested 34 runtime controls with external-operation tripwires."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

import run_minimal_rounds
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient

OUT = Path(__file__).resolve().parent
TEST = Path('tests/test_information_plan_engine.py')
before = TEST.read_bytes()
original = (OUT/'original-test-source.py').read_bytes()
binding_line = b'metadata={"cik": "0000000001"},'
filtered = b''.join(line for line in before.splitlines(keepends=True)
                    if line.strip() != binding_line)
assert filtered == original, 'Only the two constructor metadata bindings may change'
assert sum(line.strip() == binding_line for line in before.splitlines()) == 2
counts = {key: 0 for key in ('network', 'model', 'labels', 'real_store', 'fullprepare')}
def deny(kind):
    def reject(*args, **kwargs):
        counts[kind] += 1
        raise AssertionError(kind+' forbidden')
    return reject
original_init = RawInfoStore.__init__
def store_init(self, root=None, *args, **kwargs):
    if root is not None and Path(root).resolve().is_relative_to(Path.cwd()):
        return deny('real_store')()
    return original_init(self, root, *args, **kwargs)
selector = 'tests.test_information_plan_engine.InformationPlanRuntimeTests'
with ExitStack() as guards:
    for obj, name, kind in ((socket,'socket','network'), (socket,'create_connection','network'),
                           (LabelStore,'__init__','labels'), (LabelStore,'load','labels'),
                           (LabelStore,'record','labels'), (run_minimal_rounds,'prepare','fullprepare')):
        guards.enter_context(patch.object(obj,name,deny(kind)))
    for method in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):
        guards.enter_context(patch.object(StructuredRoleClient,method,deny('model')))
    guards.enter_context(patch.object(RawInfoStore,'__init__',store_init))
    with (OUT/'final-runtime-tests.log').open('x') as log:
        result = unittest.TextTestRunner(stream=log,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromName(selector))
assert TEST.read_bytes() == before
summary = {'selector':selector,'tests':result.testsRun,'success':result.wasSuccessful(),
           'failures':len(result.failures),'errors':len(result.errors),'tripwires':counts,
           'original_source_sha256':hashlib.sha256(original).hexdigest(),
           'current_source_sha256':hashlib.sha256(before).hexdigest(),
           'only_two_explicit_metadata_bindings_added':filtered==original,
           'existing_body_cik':1,'body_bytes_and_numeric_values_periods_clocks_assertions_unchanged':True,
           'original_native_failure_results':str(OUT/'original-cause-results.json')}
with (OUT/'summary.json').open('x') as handle:
    json.dump(summary,handle,indent=2);handle.write('\n')
print(json.dumps(summary,indent=2))
raise SystemExit(not result.wasSuccessful() or any(counts.values()))
