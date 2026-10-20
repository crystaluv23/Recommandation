"""Only new bootstrap consumer method; prior methods are not repeated."""
from contextlib import ExitStack
from pathlib import Path
import json
import socket
import ssl
import unittest
from unittest.mock import patch
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
counts={'forbidden':0}
def forbidden(*a,**kw):counts['forbidden']+=1;raise AssertionError('forbidden HTTP/model/real labels')
selector='tests.test_historical_registry_definition_reads.HistoricalRegistryDefinitionReadsTests.test_bootstrap_validator_rejects_typed_identity_drift_after_coherent_rehash'
with ExitStack()as stack:
    for owner,name in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'__init__'),(LabelStore,'load'),(LabelStore,'record'),(LabelStore,'ground_truth')):
        stack.enter_context(patch.object(owner,name,forbidden))
    for name in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):
        stack.enter_context(patch.object(StructuredRoleClient,name,forbidden))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(selector))
summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'forbidden_calls':counts['forbidden'],'selector':selector}
with Path(__file__).with_name('consumer-version-result.json').open('x')as handle:json.dump(summary,handle,indent=2);handle.write('\n')
raise SystemExit(0 if result.wasSuccessful()and counts['forbidden']==0 else 1)
