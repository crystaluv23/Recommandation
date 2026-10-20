"""Bounded original candidate validation and three named offline controls."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_minimal_rounds
from tests.scheme_evolution_test_support import candidate_growth_fixture
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator
from stock_opportunity_agent.signal_library import (
    SignalRegistry, SignalSpec, SignalExecutionType, SignalModality,
)

OUT = Path(__file__).resolve().parent
phase = sys.argv[1]
assert phase in ('original','final')
counts = {key: 0 for key in ('network','model','labels','real_store','fullprepare')}
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
prefix = 'tests.test_signal_evolution_engine.SignalEvolutionTests.'
selectors = [prefix+'test_candidate_identity_guard_preserves_ticker_case']
if phase == 'final':
    selectors += [prefix+'test_fixture_unavailable_does_not_hide_technical_failure',
                  prefix+'test_fixture_failure_reports_pre_execution_coverage_gap']
with ExitStack() as guards:
    for obj,name,kind in ((socket,'socket','network'),(socket,'create_connection','network'),
                         (LabelStore,'__init__','labels'),(LabelStore,'load','labels'),
                         (LabelStore,'record','labels'),(run_minimal_rounds,'prepare','fullprepare')):
        guards.enter_context(patch.object(obj,name,deny(kind)))
    for method in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):
        guards.enter_context(patch.object(StructuredRoleClient,method,deny('model')))
    guards.enter_context(patch.object(RawInfoStore,'__init__',store_init))
    with tempfile.TemporaryDirectory() as directory:
        registry = SignalRegistry(Path(directory)/'signals')
        spec = SignalSpec(signal_id='case_sensitive_probe',version=1,category='financial',
            description='Measure year-over-year revenue growth while checking five customers and cash for the next period.',
            execution_type=SignalExecutionType.DETERMINISTIC,modality=SignalModality.STRUCTURED,
            function='financial.revenue_growth_yoy',source_types=('financials',))
        validated = SignalCandidateValidator(registry,llm_runner=None,
            forbidden_identity_terms=('FIVE','CASH','NEXT')).validate(
                spec,skill=None,tests=(candidate_growth_fixture(),))
    with (OUT/(phase+'-tests.log')).open('x') as log:
        result = unittest.TextTestRunner(stream=log,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromNames(selectors))
fixture = candidate_growth_fixture()
with (OUT/(phase+'-fixture.json')).open('x') as handle:
    json.dump(fixture,handle,indent=2);handle.write('\n')
summary = {'phase':phase,'selectors':selectors,'tests':result.testsRun,
    'success':result.wasSuccessful(),'errors':len(result.errors),'failures':len(result.failures),
    'native_validator':{'accepted':validated.accepted,'reasons':list(validated.reasons),
                        'executed_tests':validated.executed_tests},
    'tripwires':counts,'support_source_sha256':hashlib.sha256(
        Path('tests/scheme_evolution_test_support.py').read_bytes()).hexdigest(),
    'fresh_model_following_demonstrated':False}
with (OUT/(phase+'-results.json')).open('x') as handle:
    json.dump(summary,handle,indent=2);handle.write('\n')
print(json.dumps(summary,indent=2))
raise SystemExit(not result.wasSuccessful() or any(counts.values()))
