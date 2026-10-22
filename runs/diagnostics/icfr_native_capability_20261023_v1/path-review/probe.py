"""Zero-author exact native two-seed input probe; no domain answers or dispatch."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import patch
import hashlib
import json
import shutil
import socket
import sys

REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO / 'src'), str(REPO / 'scripts')]
from diagnose_executed_answer_scope import StageContract
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_control import _historical_registry_snapshot, _rebased_history_meta_entries
from stock_opportunity_agent.research.evolution_core import PlanMetaMemory, RoundMetaEntry
from stock_opportunity_agent.research.evolution_signal_roles import LLMSignalMiningModel, LLMSignalUpdateModel
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalRegistry

ROOT = Path(__file__).resolve().parent
PARENT = REPO / 'runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1'
MATERIAL = REPO / 'runs/diagnostics/mining_capability_frontier_20261023_v1/independent'
ASSIGNMENT = (' Prospective bounded capability assignment: investigate a reusable narrative measurement '
    'in the public ICFR disclosure family. Independently choose and verify the measurement from '
    'authorized point-in-time material using the full existing catalog, backlog and tools. '
    'This assignment supplies no candidate, source locator, class mapping, supporting answer, '
    'or claim about stock direction or magnitude. Preserve unsupported or ambiguous conclusions '
    'as unknown. Retain every original action, exploration, evidence and disposition obligation.')

def read(path):
    return json.loads(Path(path).read_text())

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    if path.exists() and path.read_text() != text:
        raise AssertionError('immutable preflight output differs: ' + str(path))
    path.write_text(text)

def binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def forbidden(*args, **kwargs):
    raise AssertionError('zero-author preflight blocked forbidden effect')

class Captured(Exception):
    pass

ob = read(MATERIAL / 'material-obligations-frozen.json')
source_bindings = ob['source_document_bindings']
assert len(source_bindings) == 263
for row in source_bindings:
    assert binding(row['path'])['sha256'] == row['sha256']
for row in ob['definition_bindings']:
    # Binding record may carry separate spec/skill fields; retain whole original below.
    pass
code = [REPO / name for name in (
    'AGENTS.md', 'progress/status.md', 'spec/engineering-mvp.md', 'spec/agent-workflow.md',
    'spec/src/stock_opportunity_agent/research/signal_mining_agent.md',
    'spec/src/stock_opportunity_agent/research/signal_evolution.md',
    'src/stock_opportunity_agent/research/signal_evolution.py',
    'src/stock_opportunity_agent/research/mining_controller.py',
    'src/stock_opportunity_agent/research/mining_role_model.py',
    'src/stock_opportunity_agent/research/mining_agent_tools.py',
    'src/stock_opportunity_agent/research/evolution_control.py',
    'src/stock_opportunity_agent/research/evolution_transport.py',
    'src/stock_opportunity_agent/research/evolution_output_validation.py',
    'src/stock_opportunity_agent/research/evolution_signal_roles.py',
    'src/stock_opportunity_agent/research/evolution_core.py',
    'src/stock_opportunity_agent/signal_library.py',
    'src/stock_opportunity_agent/research/signal_source_reading.py',
    'src/stock_opportunity_agent/research/local_role_exchange.py')]
freeze = {'schema_version': 'icfr-native-zero-author-path-obligations-v1',
    'scope': {'network': 0, 'external_llm_api': 0, 'fresh_authors': 0, 'dispatch': 0,
        'new_label_store_reads': 0, 'check_cases': 0, 'locked_test': 0, 'candidate_answers': 0,
        'source_documents': 263, 'opaque_dev_cases': 8, 'exact_stable_specs': 18},
    'obligations': ['Use original dev8 cutoff/group map; do not deserialize any GroundTruth.',
        'Preserve complete accepted 265-row hypothesis backlog and six original disclosures; discovery retains native empty backlog.',
        'Use actual dual-seed axis, factory, model adapter and exact transport serialization; stop at request_ready before cache/receive.',
        'No candidate, Signal, fixture, domain answer or source-selection answer is manufactured.',
        'Original stages, completed pointers and all products are immutable.',
        'Only assignment scope may be added; no measurement definition, source ref or oracle to authors.',
        'S5, fixture, S7 and Fast costs remain conditional on future candidate; freeze explicit independent host limits before author dispatch.'],
    'source_oracle': binding(MATERIAL / 'material-obligations-frozen.json'),
    'source_documents': source_bindings, 'definition_bindings': ob['definition_bindings'],
    'prefix': [binding(PARENT / name) for name in ('factory-input.json', 'approved_cases.json',
        'workspace/slow_history/manifest.json', 'workspace/experiments/cycles/cycle-0001/slow_input.json',
        'workspace/experiments/cycles/cycle-0001/slow_memory.json')],
    'code': [binding(p) for p in code] + [binding(__file__)]}
save(ROOT / 'obligations-frozen.json', freeze)

# Identity-only projection from approved metadata; GroundTruth is never constructed or inspected.
approved = read(PARENT / 'approved_cases.json')
by_id = {row['case_id']: {k: row[k] for k in ('case_id','company_id','prediction_time','basic_info')}
    for rows in approved['splits'].values() for row in rows}
identities = tuple(SimpleNamespace(**{**row, 'prediction_time': datetime.fromisoformat(row['prediction_time'])})
    for row in by_id.values())
groups = ob['authorized_original_group_map']
dev = []
for row in ob['dev8']:
    identity = by_id[row['case_id']]
    assert identity['prediction_time'] == row['cutoff']
    dev.append(SimpleNamespace(**{**identity, 'prediction_time': datetime.fromisoformat(row['cutoff']),
        'ground_truth': SimpleNamespace(is_surge=groups[row['case_ref']] == 'positive')}))
factory = read(PARENT / 'factory-input.json')
assert factory['label_map'] == groups and len(factory['backlog_needs']) == 265

for variant, suffix in (('native', ''), ('icfr-scope-assignment', ASSIGNMENT)):
    root = ROOT / variant
    if root.exists():
        raise AssertionError('single-entry probe already exists')
    root.mkdir()
    shutil.copytree(PARENT / 'workspace', root / 'workspace')
    work = root / 'workspace'
    store = RawInfoStore(documents=[RawInfoDocument.from_dict(read(row['path'])) for row in source_bindings])
    registry = SignalRegistry(work / 'signals', candidate_root=work / 'signals_candidates')
    snapshot = _historical_registry_snapshot(registry)
    assert len(snapshot.specs) == 18
    hist = read(work / 'slow_history/manifest.json')['manifest']
    meta = PlanMetaMemory(entries=_rebased_history_meta_entries(
        RoundMetaEntry.from_dict(row) for row in hist['fast_context']['meta_entries']))
    records = []
    def on_progress(event):
        if event.get('event_type') != 'request_ready':
            return
        request = read(event['request_path'])['request']
        payload = json.loads(next(m['content'] for m in request['messages'] if m['role'] == 'user'))
        cost = len(json.dumps(request['messages'], ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode()) + request['max_output_tokens']
        records.append({'seed': payload['seed'], 'reservation': cost, 'request': binding(event['request_path']),
            'output_allowance': request['max_output_tokens'], 'backlog_page_count': len(payload.get('backlog_needs', [])),
            'backlog_disclosure': payload.get('backlog_disclosure'), 'catalog_page_count': len(payload['signal_catalog'])})
        raise Captured('zero-author native input captured before cache/receive')
    class Client(StructuredRoleClient):
        def estimate_json_request_tokens(self, **kw):
            kw['system_prompt'] += suffix
            return super().estimate_json_request_tokens(**kw)
        def complete_json(self, **kw):
            kw['system_prompt'] += suffix
            return super().complete_json(**kw)
    client = Client(registration=get_model('independent-subagent'),
        contract=StageContract({'limits': {'max_local_role_calls': 1, 'max_structured_corrections': 1,
            'structured_reasoning_token_reserve': 0}}), workspace=root / 'transport',
        ledger=ExternalAttemptLedger(root / 'unused_external.json', max_attempts=1, max_total_cost=.01),
        local_role_exchange=LocalRoleExchange(root / 'exchange', max_calls=1),
        allow_external=False, environ={}, on_progress=on_progress)
    engine = SignalEvolutionEngine(registry=registry, raw_info_store=store, discovery_cases=tuple(dev),
        identity_cases=identities, workspace=EvolutionWorkspace(work), meta_memory=meta,
        mining_model=LLMSignalMiningModel(client), update_model=LLMSignalUpdateModel(client), llm_signal_runner=None)
    engine._active_slow_input = read(work / 'experiments/cycles/cycle-0001/slow_input.json')
    engine._active_slow_memory = read(work / 'experiments/cycles/cycle-0001/slow_memory.json')
    engine._active_sampling_manifest = engine._active_slow_input['sampling_manifest']
    engine._mining_memory_index = engine._controller_memory_index()
    # Exact accepted factory prefix; no repeat S1/S2 or source-selection answer.
    context = {'stable_signal_cards': [{'signal_ref': s.ref, 'description': s.description} for s in snapshot.specs],
        'capability_backlog': {'signal_need_items': factory['backlog_needs']},
        'prior_modality_footprints': factory['prior_modality_footprints'], 'meta_info': factory['meta_memory_briefs'],
        'slow_method_memory': factory['slow_method_memory'], 'meta_memory_disclosures': factory['meta_memory_disclosures']}
    engine._mining_context = MethodType(lambda self, **kw: context, engine)
    with ExitStack() as stack:
        for owner, name in ((socket, 'create_connection'), (socket.socket, 'connect'),
            (socket.socket, 'connect_ex'), (LabelStore, '__init__'), (LabelStore, 'load'),
            (LabelStore, 'ground_truth'), (LabelStore, 'record'), (LocalRoleExchange, 'receive'),
            (ExternalAttemptLedger, 'reserve')):
            stack.enter_context(patch.object(owner, name, forbidden))
        audit = engine._run_controller_mining_axis(cycle_id=1, axis_id='surge_direction',
            research_axis=factory['research_axis'], dev_cases=tuple(dev), check_cases=(),
            labels_by_case_id={r['case_id']: groups[r['case_ref']] for r in ob['dev8']})
    assert len(records) == 2 and {r['seed'] for r in records} == {'hypothesis','discovery'}
    assert not audit['candidate_refs']
    assert not list((root / 'exchange').rglob('inbox/*.json'))
    save(root / 'result.json', {'inputs': records, 'author_calls': 0, 'dispatch': 0,
        'candidate_count': 0, 'source_count': len(store.documents), 'stable_refs': [s.ref for s in snapshot.specs],
        'assignment': suffix, 'factory_binding': binding(PARENT / 'factory-input.json'),
        'note': 'Captured exceptions are preflight stops, not fresh failed role observations.'})
print(json.dumps({v: read(ROOT / v / 'result.json')['inputs'] for v in ('native','icfr-scope-assignment')}, indent=2))
