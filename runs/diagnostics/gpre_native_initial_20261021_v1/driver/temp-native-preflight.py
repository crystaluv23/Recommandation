#!/usr/bin/env python3
"""One temporary native initialize-to-pending connection, zero authored answers."""
import json
from pathlib import Path
import traceback
from unittest.mock import patch

import run_gpre_native_initial_stage as stage
from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'temp-native-preflight-v1'
FORMAL = stage.ROOT
if OUTPUT.exists() or FORMAL.exists():
    raise RuntimeError('temporary and formal destinations must both be new')
OUTPUT.mkdir()
expectation = OUTPUT / 'connection-scope.json'
atomic_write_json(expectation, {'scope': 'temporary native connection only; no semantic oracle or answer',
                               'expected_roles_authored': 0})
counts = {'receive': 0}
pre_egress = []
native_receive = stage.LocalRoleExchange.receive
native_project = StructuredRoleClient._request_identity_projection
# This observer delegates to the exact production identity projection unchanged.
def observe_project(self, aliases):
    projection = native_project(self, aliases)
    return projection

def counted_receive(self, *args, **kwargs):
    counts['receive'] += 1
    return native_receive(self, *args, **kwargs)

stage.ROOT = OUTPUT / 'stage'
try:
    with patch.object(stage.LocalRoleExchange, 'receive', counted_receive):
        prepared = stage.prepare(expectations=expectation)
        pending = stage.resume()
    if pending['status'] != 'pending' or counts['receive'] != 1:
        raise RuntimeError('native chain did not reach its first actual pending inbox')
    inbox = Path(pending['inbox_path'])
    outbox = Path(pending['outbox_path'])
    record = stage.read_json(inbox)
    journal = stage.read_json(stage.ROOT / 'requests' / (pending['request_hash'] + '.json'))
    bootstrap = stage.read_json(stage.ROOT / 'samples/h01/bootstrap.json')
    inputs = stage.read_json(stage.ROOT / 'inputs.json')
    messages = json.dumps(record['messages'], ensure_ascii=False)
    aliases = inputs['sample']['identity']['identity_aliases']
    leaks = [a for a in [*aliases, stage.COMPANY, '0001309402'] if a.casefold() in messages.casefold()]
    result = {'status': 'native_pending_connection_passed' if not leaks else 'native_pending_identity_failure',
              'formal_stage_exists': FORMAL.exists(), 'prepare': prepared, 'pending': pending,
              'inbox': stage.binding(inbox), 'journal': stage.binding(stage.ROOT / 'requests' / (pending['request_hash'] + '.json')),
              'outbox_parent_exists': outbox.parent.is_dir(), 'outbox_exists': outbox.exists(),
              'native_egress_identity_leaks': leaks,
              'bootstrap': stage.binding(stage.ROOT / 'samples/h01/bootstrap.json'),
              'model_requests': len(bootstrap['model_context']['requests']),
              'model_projections': sum(len(r.get('projections', [])) for r in bootstrap['model_context']['requests']),
              'bundle_statuses': [{'request_id': r['request']['request_id'], 'status': r['status'],
                                   'documents': len(r.get('document_ids', []))}
                                  for r in bootstrap['bundle']['requests']],
              'core_evaluation_anchor': bootstrap['evaluation_anchor'],
              'core_computed_metrics': bootstrap['computed_metrics'],
              'identity': inputs['sample']['identity'], 'identity_provenance': inputs['identity_provenance'],
              'author_responses': len(list((stage.ROOT / 'exchange/receipts').glob('*.json'))),
              'Signal_execution': 0, 'external_API': 0, 'network': 0, 'labels': 0,
              'counts': counts, 'script': stage.binding(Path(stage.__file__)), 'spec': stage.binding(stage.SPEC)}
    stage.verify()
    atomic_write_json(OUTPUT / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if leaks:
        raise RuntimeError('actual pending wire leaks a declared identity')
except BaseException as error:
    atomic_write_json(OUTPUT / 'preflight-error.json', {'error_type': type(error).__name__, 'error': str(error),
                                                       'traceback': traceback.format_exc(), 'counts': counts})
    raise
