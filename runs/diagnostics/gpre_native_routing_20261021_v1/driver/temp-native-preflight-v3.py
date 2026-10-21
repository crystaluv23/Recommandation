#!/usr/bin/env python3
"""Actual parent/source/core/select/client connection to first pending; no answer."""
from pathlib import Path
import json
import traceback
from unittest.mock import patch

import run_gpre_native_routing_stage as route
from stock_opportunity_agent.artifacts import atomic_write_json

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'temp-native-preflight-v3'
FORMAL = route.ROOT
if OUTPUT.exists() or FORMAL.exists():
    raise RuntimeError('temporary/formal destinations must be new')
OUTPUT.mkdir()
expectation = OUTPUT / 'connection-only-scope.json'
atomic_write_json(expectation, {'scope': 'native connection only, not a source-matching oracle',
                               'author_answers': 0, 'Signal_calculations': 0})
parent_before = route.initial.files(route.PARENT)
counts = {'receive': 0}
native_receive = route.LocalRoleExchange.receive

def receive(self, *args, **kwargs):
    counts['receive'] += 1
    return native_receive(self, *args, **kwargs)

route.ROOT = OUTPUT / 'stage'
try:
    with patch.object(route.LocalRoleExchange, 'receive', receive):
        prepared = route.prepare(expectations=expectation)
        pending = route.resume()
    route.verify()
    if pending['status'] != 'pending' or counts['receive'] != 1:
        raise RuntimeError('native selection chain did not stop at its first pending inbox')
    inbox, outbox = Path(pending['inbox_path']), Path(pending['outbox_path'])
    journal_path = route.ROOT / 'requests' / (pending['request_hash'] + '.json')
    request = route.read_json(journal_path)['request']
    wire = route.read_json(inbox)
    payload = json.loads(request['messages'][1]['content'])
    context = route.read_json(route.ROOT / 'native-select-context.json')
    inputs = route.read_json(route.ROOT / 'inputs.json')
    bootstrap = route.read_json(route.ROOT / 'recomputed-bootstrap.json')
    identity = inputs['sample']['identity']
    rendered = json.dumps(wire['messages'], ensure_ascii=False).casefold()
    leaks = [value for value in [*identity['identity_aliases'], inputs['sample']['company_id'], identity['cik']]
             if value.casefold() in rendered]
    if parent_before != route.initial.files(route.PARENT):
        raise RuntimeError('completed parent file membership or bytes changed')
    result = {'status': 'native_routing_pending_connection_passed' if not leaks else 'native_identity_failure',
        'scope': 'temporary metadata/core/client preflight; no routing answer or semantic acceptance',
        'prepare': prepared, 'pending': pending, 'counts': counts,
        'context': route.binding(route.ROOT / 'native-select-context.json'),
        'bootstrap': route.binding(route.ROOT / 'recomputed-bootstrap.json'),
        'bootstrap_exact_parent_equal': bootstrap == inputs['bootstrap'],
        'accepted_state_exact': context['research_state'] == inputs['accepted_initial_step']['state'],
        'five_original_needs_exact': context['information_needs'] == inputs['accepted_initial_step']['state']['next_information_needs'],
        'native_selection_budget': context['native_request_token_budget'],
        'native_predictor_reservation': context['native_predictor_reservation'],
        'budget_composition': context['budget_composition'],
        'predictor_reservation_record': route.binding(route.ROOT / 'native-predictor-reservation.json'),
        'core_post_select_caps': context['post_select_core_caps'],
        'native_eligible_refs': context['eligible_signal_refs'],
        'native_visible_card_refs': [r['signal_ref'] for r in payload['available_signal_cards']],
        'card_count': len(payload['available_signal_cards']),
        'actual_selection_caps': payload['selection_caps'],
        'request': route.binding(journal_path), 'inbox': route.binding(inbox),
        'outbox_parent_exists': outbox.parent.is_dir(), 'outbox_exists': outbox.exists(),
        'wire_declared_identity_leaks': leaks, 'parent_files_preserved': len(parent_before),
        'source_files': prepared['source_bindings'], 'code_files': prepared['code_bindings'],
        'all_bindings_rechecked_equal': True, 'formal_stage_exists': FORMAL.exists(),
        'new_author_answers': 0, 'Signal_calculations': 0, 'executor_entry_attempts': 0,
        'H_init_model_calls': 0, 'Reflect': 0, 'Predictor': 0, 'GET': 0, 'labels': 0,
        'script': route.binding(Path(route.__file__)), 'spec': route.binding(route.SPEC)}
    atomic_write_json(OUTPUT / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if leaks:
        raise RuntimeError('actual outgoing request contains declared identity')
except BaseException as exc:
    atomic_write_json(OUTPUT / 'preflight-error.json', {'error_type': type(exc).__name__, 'error': str(exc),
        'traceback': traceback.format_exc(), 'counts': counts})
    raise
