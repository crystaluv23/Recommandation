#!/usr/bin/env python3
"""One pure predicate trace on sealed raw; no native routing or author replay."""
from pathlib import Path
import hashlib
import json
import sys

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.research.evolution_research_validation import _shared_distinctive_phrase

REPO = Path(__file__).resolve().parents[4]
STAGE = REPO / 'runs/diagnostics/gpre_native_routing_20261021_v1/stage'
HERE = Path(__file__).resolve().parent
SOURCE = REPO / 'src/stock_opportunity_agent/research/evolution_research_validation.py'

def binding(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

before = [binding(p) for p in sorted(STAGE.rglob('*')) if p.is_file()]
source_before = binding(SOURCE)
raw_path = next((STAGE / 'exchange/outbox').glob('*.txt'))
raw = json.loads(raw_path.read_text())
row = next(item for item in raw['selections'] if item['signal_ref'] == 'order_confirmation_disclosed:v3')
target = json.loads((STAGE / 'inputs.json').read_text())['accepted_initial_step']['state']['next_information_needs'][1]
trace_result = []
keys = ('clauses', 'topical_clauses', 'scope_words', 'clause_words', 'unique_words',
        'residual_topics', 'answered', 'retained', 'left_words', 'right_words',
        'left_topic_words', 'right_topic_words')

def clean(value):
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value

def trace(frame, event, arg):
    if frame.f_code is _shared_distinctive_phrase.__code__ and event == 'return':
        trace_result.append({'return': arg, 'locals': {key: clean(frame.f_locals[key])
                             for key in keys if key in frame.f_locals}})
    return trace

sys.settrace(trace)
try:
    actual = _shared_distinctive_phrase(row['selection_reason'], row['residual_need'], target_need=target)
finally:
    sys.settrace(None)
after = [binding(p) for p in sorted(STAGE.rglob('*')) if p.is_file()]
if before != after or source_before != binding(SOURCE):
    raise RuntimeError('sealed stage or source changed')
result = {'scope': 'single pure helper call, not parser/model/native-stage replay',
          'source': source_before, 'raw': binding(raw_path), 'target': target,
          'reason': row['selection_reason'], 'residual': row['residual_need'],
          'actual_shared_phrase': actual, 'trace': trace_result,
          'completed_stage_files_before_equal_after': len(before),
          'source_before_equal_after': True, 'new_role_answers': 0,
          'new_native_routing_runs': 0, 'Signal_execution': 0, 'network': 0}
output = HERE / 'shared-product-predicate-result.json'
if output.exists():
    raise RuntimeError('pure probe result already exists')
atomic_write_json(output, result)
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
