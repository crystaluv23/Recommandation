"""Read-only offline routing scope diagnosis; no role/model or source execution."""
import sys
sys.dont_write_bytecode = True

import ast
import hashlib
import inspect
import json
import socket
import subprocess
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research import evolution_plan_roles as roles
from stock_opportunity_agent.research import evolution_research_validation as validation
from stock_opportunity_agent.research.evolution_core import ResearchState, RuntimeBudgetExceeded
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry, SignalExecutor, SignalRegistry, SignalSpec,
    default_deterministic_signal_functions,
)

REPO = Path('/Users/l/Project/Recommandation')
OUT = Path(__file__).resolve().parent
PRIOR = REPO / 'runs/diagnostics/routing_shared_object_repair_20261021_v1/independent'
STAGE = REPO / 'runs/diagnostics/gpre_native_routing_20261021_v1/stage'
READS = {}


def binding(path):
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def read(path):
    READS[str(path)] = binding(path)
    return json.loads(path.read_text())


def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def serial(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [serial(v) for v in value]
    return type(value).__name__


frozen = read(PRIOR / 'frozen-cases-v3.json')
positives = [deepcopy(c) for c in frozen['cases'] if c['case_id'].startswith(('p05_', 'p06_'))]
assert len(positives) == 2
cases = deepcopy(positives)


def variant(base, name, **changes):
    case = deepcopy(base)
    case.update(changes, case_id=name, expected_direct_partial=False)
    cases.append(case)


p05, p06 = positives
variant(p05, 'n_object_same', selection_reason=p05['selection_reason'].replace('Orion Data', 'Aurora Sensor'))
variant(p05, 'n_object_claims_both', selection_reason=p05['selection_reason'] + ' Also check Aurora Sensor binding offtake commitments.')
variant(p05, 'n_object_missing_answer_anchor', selection_reason='Check binding offtake commitments for named counterparties and delivery schedules.')
variant(p05, 'n_object_substring_anchor', selection_reason=p05['selection_reason'].replace('Orion Data', 'Orion Databases'))
variant(p06, 'n_window_same', selection_reason='Check still-effective binding offtake commitments for carbon capture module disclosed before the 180-day window.')
variant(p06, 'n_window_claims_both', selection_reason=p06['selection_reason'] + ' Also check still-effective binding offtake commitments disclosed before that window.')
variant(p06, 'n_window_missing_anchor', selection_reason='Check binding offtake commitments for carbon capture module.')
variant(p06, 'n_window_overlapping', residual_need=p06['residual_need'].replace('before the 180-day window', 'within the 90-day window ending at prediction time'))
variant(p06, 'n_window_unattached_other_sentence', selection_reason='Check binding offtake commitments for carbon capture module. Delivery schedules were disclosed within the 180-day window ending at prediction time.')
save('inputs.json', {'source_cases': binding(PRIOR / 'frozen-cases-v3.json'), 'cases': cases,
                     'negative_expectation_scope': 'Proposed safety counterexamples, not modified frozen gold or newly implemented policy.'})

context = read(STAGE / 'native-select-context.json')
raw = read(STAGE / 'exchange/outbox/6dd836684a001330e31e78797bfbb439f2d751fc1aa79a6364224836029aabf8.txt')
group = read(STAGE / 'inputs.json')['registry_group']
specs = []
for ref in group['refs']:
    sid, version = ref.split(':')
    matches = [Path(b['path']) for b in group['definition_bindings']
               if b['path'].endswith(f'/{sid}/versions/{version}/spec.json')]
    assert len(matches) == 1
    specs.append(SignalSpec.from_dict(read(matches[0])))
registry = FrozenSignalRegistry(group['version'], group['registry_hash'], tuple(specs), {})
assert len(specs) == 18

excerpts = {}
for fn in (validation._shared_distinctive_phrase, validation._coordinated_residual_facet_terms):
    excerpts[fn.__name__] = {'source': inspect.getsource(fn), 'line': inspect.getsourcelines(fn)[1]}
parser_lines = Path(roles.__file__).read_text().splitlines()
excerpts['routing_scope_caller'] = {'line': 1260, 'source': '\n'.join(parser_lines[1259:1610])}
save('function-sources.json', excerpts)

trips = []


def forbidden(*args, **kwargs):
    trips.append('forbidden_effect')
    raise AssertionError('Forbidden effect in offline diagnosis')


class Caller:
    max_structured_corrections = 1

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def complete_json(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if len(self.calls) == 1:
            return deepcopy(self.answer), AgentUsage(llm_calls=1, tokens=5, cost=0.0)
        raise RuntimeBudgetExceeded('Offline correction response intentionally absent; native fallback only')


def run(case):
    traces = []
    helper_locals = ('clauses', 'topical_clauses', 'topical_texts', 'clause_words', 'unique_words',
                     'answered', 'retained', 'arms', 'left_topic_words', 'right_topic_words')
    parser_locals = ('cosmetic_residual', 'coordinated_residual_terms', 'residual_retains_direct_phrase',
                     'residual_removes_complete_direct_facet', 'removed_content', 'residual_facet_candidates',
                     'conflicting_coordinated_terms', 'shared_residual_phrase')

    def trace(frame, event, arg):
        if frame.f_code is validation._shared_distinctive_phrase.__code__ and event == 'return':
            traces.append({'kind': 'helper_return', 'return': arg,
                           'locals': {k: serial(frame.f_locals[k]) for k in helper_locals if k in frame.f_locals}})
        if frame.f_code is validation._coordinated_residual_facet_terms.__code__ and event == 'return':
            traces.append({'kind': 'coordinated_return', 'return': serial(arg),
                           'locals': {k: serial(v) for k, v in frame.f_locals.items() if k in ('raw_tokens', 'retained', 'left', 'right')}})
        if frame.f_code.co_filename == roles.__file__ and event == 'line' and frame.f_lineno == 1584:
            traces.append({'kind': 'parser_conflict', 'line': frame.f_lineno,
                           'locals': {k: serial(frame.f_locals[k]) for k in parser_locals if k in frame.f_locals}})
        return trace

    answer = deepcopy(raw)
    answer['selections'][1].update(selection_reason=case['selection_reason'], residual_need=case['residual_need'])
    needs = list(context['information_needs'])
    needs[1] = case['target_need']
    state = deepcopy(context['research_state'])
    state['next_information_needs'] = needs
    caller = Caller(answer)
    agent = roles.LLMSignalRetrievalAgent(caller)
    agent.set_evaluation_context(datetime.fromisoformat('2025-05-30T00:00:00+00:00'))
    agent.set_deterministic_functions(default_deterministic_signal_functions())
    sys.settrace(trace)
    error = None
    selected = []
    try:
        phrase = validation._shared_distinctive_phrase(case['selection_reason'], case['residual_need'], target_need=case['target_need'])
        coordinated = validation._coordinated_residual_facet_terms(case['target_need'], case['residual_need'])
        result = agent.select(tuple(needs), registry, {}, research_state=ResearchState.from_dict(state),
                              eligible_signal_refs=tuple(group['refs']), prior_context_tags=())
        selected = [row.to_dict() for row in result.value]
    except Exception as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        sys.settrace(None)
    order = next((r for r in selected if r['signal_ref'] == 'order_confirmation_disclosed:v3'), None)
    siblings_exact = all(next((x for x in selected if x['signal_ref'] == row['signal_ref']), None)
                         == {k: v for k, v in row.items() if v is not None}
                         for row in (raw['selections'][0], raw['selections'][2]))
    return {'case_id': case['case_id'], 'helper_phrase': phrase, 'coordinated_terms': coordinated,
            'direct_partial': len(caller.calls) == 1 and order is not None and order.get('reason_code') == 'answer_need' and order.get('answer_scope') == 'partial',
            'offline_calls': len(caller.calls), 'scripted_answers': 1, 'error': error, 'order': order,
            'siblings_exact': siblings_exact, 'trace': traces,
            'correction_payloads': [c['payload'] for c in caller.calls[1:]]}


source_paths = [Path(validation.__file__), Path(roles.__file__), REPO / 'src/stock_opportunity_agent/research/evolution_output_validation.py',
                REPO / 'spec/src/stock_opportunity_agent/research/evolution_research_validation.md']
before = [binding(p) for p in source_paths]
with ExitStack() as stack:
    for owner, method in ((socket, 'socket'), (socket, 'create_connection'), (LabelStore, '__init__'),
                          (LabelStore, 'load'), (LabelStore, 'record'), (LabelStore, 'ground_truth'),
                          (RawInfoStore, '__init__'), (RawInfoStore, 'append'),
                          (SignalExecutor, 'execute_batch'), (SignalExecutor, 'prepare_inputs'),
                          (SignalRegistry, 'freeze'), (SignalRegistry, 'install_catalog')):
        stack.enter_context(patch.object(owner, method, forbidden))
    results = [run(c) for c in cases]
after = [binding(p) for p in source_paths]
assert before == after
assert all(binding(Path(k)) == v for k, v in READS.items())
assert not trips
save('result.json', {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
                     'code_before_after': before, 'source_bindings': list(READS.values()), 'results': results,
                     'forbidden_calls': trips, 'scope': 'Pure 18 definition snapshot; scripted offline parser replies, no model/Signal/RawStore or stage invocation.'})
print(json.dumps({'cases': len(results), 'outcomes': [{k: r[k] for k in ('case_id', 'helper_phrase', 'coordinated_terms', 'direct_partial', 'offline_calls', 'siblings_exact')} for r in results],
                  'result': binding(OUT / 'result.json'), 'forbidden_calls': trips}, indent=2))
