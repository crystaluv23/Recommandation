"""Targeted tests with real no-network/no-real-label tripwires; synthetic data only."""
from contextlib import ExitStack
from pathlib import Path
import json
import socket
import ssl
import unittest
from unittest.mock import patch
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.artifacts import atomic_write_json

counts={'forbidden':0}
def forbidden(*a,**kw):counts['forbidden']+=1;raise AssertionError('forbidden HTTP/model/real LabelStore')
names=['tests.test_historical_registry_definition_reads']+[ 'tests.test_evolution_control.RunControlTests.'+name for name in (
    'test_slow_history_preserves_imported_learning_events',
    'test_slow_history_import_uses_only_committed_source_pointer',
    'test_slow_bootstrap_manifest_masks_identity_and_binds_rejection',
    'test_slow_bootstrap_reconstructs_one_committed_fast_boundary')]
with ExitStack()as stack:
    for owner,name in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'__init__'),
        (LabelStore,'load'),(LabelStore,'record'),(LabelStore,'ground_truth')):
        stack.enter_context(patch.object(owner,name,forbidden))
    for name in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):
        stack.enter_context(patch.object(StructuredRoleClient,name,forbidden))
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'forbidden_calls':counts['forbidden'],
    'selectors':names,'scope':'No real source export/stage; all Registry/workspace sources synthetic temporary trees.'}
path=Path(__file__).with_name('guarded-final-result.json')
with path.open('x')as handle:json.dump(summary,handle,indent=2);handle.write('\n')
raise SystemExit(0 if result.wasSuccessful()and counts['forbidden']==0 else 1)
