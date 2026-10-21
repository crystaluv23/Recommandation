#!/usr/bin/env python3
"""Read sealed raw through native routing parser, with pure definitions and zero Signals.

This is offline parser replay, not a stage resume, fresh author or measurement.
"""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests.evolution_runtime_test_support import ScriptedRoleCaller
from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_core import ResearchState, SignalSelectionDecision
from stock_opportunity_agent.research.evolution_plan_roles import LLMSignalRetrievalAgent
import stock_opportunity_agent.research.evolution_plan_roles as roles
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry
from diagnose_executed_answer_scope import binding
from datetime import datetime

REPO = Path.cwd()
HERE = Path(__file__).resolve().parent
STAGE = REPO / 'runs/diagnostics/gpre_native_routing_20261021_v1/stage'
OUTPUT = HERE / 'original-portfolio-replay.json'
if OUTPUT.exists():
    raise RuntimeError('offline result already exists')

def files(root):
    return [binding(p) for p in sorted(root.rglob('*')) if p.is_file()]

before = files(STAGE)
inputs = json.loads((STAGE / 'inputs.json').read_text())
raw_path = next((STAGE / 'exchange/outbox').glob('*.txt'))
raw = json.loads(raw_path.read_text())
accepted = inputs['accepted_initial_step']['state']
expected = [SignalSelectionDecision.from_dict(row).to_dict() for row in raw['selections']]
group = inputs['registry_group']
registry_before = files(Path(group['root']))
source = HERE / 'original-evolution_research_validation.py.txt'
spec = importlib.util.spec_from_loader('stock_opportunity_agent.research._portfolio_old_validation', loader=None)
module = importlib.util.module_from_spec(spec)
module.__file__ = str(source)
sys.modules[spec.name] = module
exec(compile(source.read_text(), str(source), 'exec'), module.__dict__)
forbidden_calls = []
def forbidden(*args, **kwargs):
    forbidden_calls.append('forbidden')
    raise AssertionError('no Signal/freeze/network/label/source append in offline parser replay')

results = []
with ExitStack() as stack, TemporaryDirectory() as directory:
    for owner, name in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'__init__'),
            (LabelStore,'load'),(LabelStore,'record'),(LabelStore,'ground_truth'),
            (SignalExecutor,'execute_batch'),(SignalExecutor,'prepare_inputs'),
            (SignalRegistry,'freeze'),(RawInfoStore,'append')):
        stack.enter_context(patch.object(owner, name, forbidden))
    registry = SignalRegistry(group['root'], candidate_root=Path(directory))
    frozen = registry.snapshot_from_refs(group['version'], tuple(group['refs']))
    if frozen.registry_hash != group['registry_hash']:
        raise RuntimeError('actual original18 Registry identity differs')
    functions = SignalExecutor(frozen, raw_info_store=RawInfoStore()).deterministic_functions
    current = roles._shared_distinctive_phrase
    for old in (True, False):
        caller = ScriptedRoleCaller([raw, raw])
        agent = LLMSignalRetrievalAgent(caller)
        agent.set_deterministic_functions(functions)
        agent.set_evaluation_context(datetime.fromisoformat(inputs['sample']['prediction_time']))
        with patch.object(roles, '_shared_distinctive_phrase', module._shared_distinctive_phrase if old else current):
            step = agent.select(tuple(accepted['next_information_needs']), frozen, {}, {},
                eligible_signal_refs=tuple(group['refs']), research_state=ResearchState.from_dict(accepted), prior_context_tags=())
        rows = [row.to_dict() for row in step.value]
        results.append({'old_saved_helper':old, 'offline_scripted_parser_calls':len(caller.calls),
            'selections':rows, 'canonical_original_raw_rows':expected,
            'all_rows_exact_original_raw':rows == expected,
            'finance_and_liquidity_siblings_exact':rows[0] == expected[0] and rows[2] == expected[2],
            'new_model_calls':0, 'validation_feedback':caller.calls[1]['payload'].get('validation_feedback') if len(caller.calls)>1 else None})
if files(STAGE) != before or files(Path(group['root'])) != registry_before or forbidden_calls:
    raise RuntimeError('sealed sources changed or forbidden effect reached')
if results[0]['all_rows_exact_original_raw'] or not results[1]['all_rows_exact_original_raw']:
    raise RuntimeError('expected isolated old red / candidate preservation did not hold')
atomic_write_json(OUTPUT, {'scope':'offline unchanged parser with saved/current helper; no stage execution or fresh author',
    'raw':binding(raw_path), 'saved_old_helper':binding(source), 'current_helper':binding(Path(roles._shared_distinctive_phrase.__code__.co_filename)),
    'registry_ref_count':len(group['refs']), 'registry_hash':frozen.registry_hash,
    'results':results, 'sealed_stage_files_equal':len(before), 'Registry_files_equal':len(registry_before),
    'forbidden_calls':forbidden_calls,'Signal_execution':0,'network':0,'labels':0,
    'historical_portfolio_verdict':'unchanged strict0/1; replay is not a fresh routing pass'})
print(json.dumps({'old_scripted_calls':results[0]['offline_scripted_parser_calls'],
    'candidate_scripted_calls':results[1]['offline_scripted_parser_calls'],
    'candidate_all_original_rows_exact':results[1]['all_rows_exact_original_raw'],
    'result':binding(OUTPUT)},sort_keys=True))
