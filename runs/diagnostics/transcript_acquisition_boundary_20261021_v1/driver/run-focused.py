"""Offline adapter/resolver/cache controls, with real network/label tripwires."""
import hashlib
import json
import ssl
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.request
from stock_opportunity_agent.cases.label_store import LabelStore

ROOT = Path(__file__).resolve().parent
SELECTORS = (
    'tests.test_transcript_acquisition_boundary',
    'tests.test_data_resolution.EvidenceResolverTests.test_transcript_adapter_rejects_calendar_as_public_content_proof',
    'tests.test_evolution_control.RunControlTests.test_runtime_exposes_authorized_transcript_adapter',
)
suite = unittest.defaultTestLoader.loadTestsFromNames(SELECTORS)
forbidden=[]
def denied(*args, **kwargs):
    forbidden.append('network_or_labels')
    raise AssertionError('real network/labels forbidden in this focused control')
with patch.object(socket,'create_connection',denied), patch.object(socket.socket,'connect',denied), patch.object(urllib.request,'urlopen',denied), patch.object(LabelStore,'__init__',denied):
    result = unittest.TextTestRunner(verbosity=2).run(suite)
files = ('src/stock_opportunity_agent/data/acquisition.py', 'tests/test_data_resolution.py',
         'tests/test_evolution_control.py', 'tests/test_transcript_acquisition_boundary.py')
summary={'command':sys.argv,'selectors':SELECTORS,'tests_run':result.testsRun,
         'failures':len(result.failures),'errors':len(result.errors),'forbidden':forbidden,
         'bindings':[{'path':name,'sha256':hashlib.sha256(Path(name).read_bytes()).hexdigest()}for name in files],
         'limits':'Only unsafe automatic production blocked; raw client cache/local reads are not public-time admission proof. 26 unknown originals unchanged. Proof-backed transcript capability remains open.'}
with (ROOT/'focused-final-summary.json').open('x') as handle:
    json.dump(summary,handle,indent=2);handle.write('\n')
print(json.dumps(summary,indent=2))
sys.exit(0 if result.wasSuccessful() and not forbidden else 1)
