"""Read-only independent actual-source/caller controls; no production role answers."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_core import (
    CaseReflectionEvidence, PlanMetrics, PlanMetaMemory, PlanMetaReflection,
    ResearchDecision, ResearchState, RoundMetaEntry, SignalRound,
    SignalSelectionDecision, _assemble_final_context, default_information_plan,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMPlanCritic
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry
from tests.scheme_evolution_test_support import make_case, make_record, make_trajectory
from tests.test_signal_classification_contract import inputs
from tests.test_signal_financials import AS_OF

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PRODUCT = [ROOT / 'src/stock_opportunity_agent/research' / name for name in
           ('evolution_core.py', 'evolution_reflection_memory.py', 'evolution_plan_roles.py', 'signal_evolution.py')]


def bindings():
    return [{'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in PRODUCT]


network = []
def forbidden(*args, **kwargs):
    network.append('attempt')
    raise AssertionError('Network forbidden in independent review')
socket.create_connection = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden


def trajectory(number):
    """Use distinct issuer-bound synthetic SEC facts and actual executor products."""
    company = f'cik_{number + 101:010d}'
    rounds, declarations = [], []
    for step in (0, 1):
        spec, registry, original = inputs(cash_flow=-60-number-step*100)
        raw = original.documents[0]
        content = json.loads(raw.content)
        content['cik'] = number + 101
        source = RawInfoDocument.create(document_id=f'independent-source-{number}-{step}',
            company_id=company, source_type=raw.source_type,
            published_at=raw.published_at, available_at=raw.available_at,
            content=json.dumps(content, sort_keys=True, separators=(',', ':')),
            metadata={'cik': number + 101})
        executor = SignalExecutor(registry, RawInfoStore(documents=(source,)))
        batch = executor.execute_batch((spec.ref,), company_id=company, as_of=AS_OF)
        assert batch.results[0].value.value != 'unavailable'
        choice = SignalSelectionDecision(signal_ref=spec.ref, selection_reason='Synthetic source scope.',
            expected_role='coverage', reason_code='combine_evidence',
            applicability_hypothesis='Retain a measurable control.', context_tags=('capital_intensive',))
        rounds.append(SignalRound((), (choice,), batch))
        declarations.append(executor.classification_contracts_for(batch.results))
    context = _assemble_final_context(plan=default_information_plan(), company_id=company,
        additional_identity_aliases=(), basic_info={'requests': []},
        state=ResearchState(decision=ResearchDecision.FINALIZE), rounds=tuple(rounds),
        prediction_time=AS_OF, signal_classification_contracts=tuple(declarations))
    return replace(make_trajectory(company, 1.1, False, None), prediction_time=AS_OF,
                   final_context=context, signal_rounds=tuple(rounds))


def references(value):
    if isinstance(value, dict):
        return set().union(*(references(v) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(references(v) for v in value)) if value else set()
    return {value} if isinstance(value, str) and value.startswith('reflection_source:') else set()


before = bindings()
(OUT/'source-hashes-current.json').write_text(json.dumps(before, indent=2)+'\n')
cases = tuple(trajectory(i) for i in range(24))
plan = default_information_plan()
owner = 'reflection_plan:' + canonical_json_hash(plan.canonical_dict())
rows = [CaseReflectionEvidence.from_trajectory(t, case_index=i+1).to_model_dict() for i,t in enumerate(cases)]
index = ReflectionMemoryIndex.from_case_rows(rows, owner_ref=owner)
full = {r['source_ref'] for r in index.source_catalog() if r['source_kind'] == 'runtime_signal_classification'}
assert len(full) == 48
metrics = PlanMetrics(0, 0, 0, 0, 0, 0, 0, 24, 0, 24)


class Caller:
    max_structured_corrections = 1
    def __init__(self):
        self.calls = []
    def complete_json(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if len(self.calls) == 1:
            return {'browse_memory': {'cursor': 0, 'level': 'case', 'signal_ref': next(iter(rows[0]['signal_classification_context']))['signal_ref']}}, AgentUsage(llm_calls=1)
        return {'reflection_items': [], 'selected_reflection_refs': [], 'no_findings_reason': 'Independent transport control, no research conclusion.'}, AgentUsage(llm_calls=1)


caller = Caller()
LLMPlanCritic(caller).critique(plan=plan, trajectories=cases, metrics=metrics)
assert len(caller.calls) == 2
initial = caller.calls[0]['payload']
after_browse = caller.calls[1]['payload']
(OUT/'critic-requests-current.json').write_text(json.dumps(caller.calls, indent=2, default=str)+'\n')
visible = references(initial) & full
discovered = references(after_browse) & full
known_ref = next(iter(full - visible)) if full-visible else next(iter(full))
assert index.read_refs([known_ref], role='plan_critic', max_bytes=48_000)['sources'][0]['source_ref'] == known_ref

record = replace(make_record('independent_meta_plan', 0, (1.0,)), trajectories=cases, metrics=metrics, evaluation=None, fitness=None)
entry = RoundMetaEntry(round_id=1, plan_reflections=(PlanMetaReflection.from_record(record),), evidence_refs=(record.plan.plan_id,))
restored = RoundMetaEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
memory = PlanMetaMemory(entries=(restored,))
class Selector:
    def __init__(self): self.calls = []
    def request_slow_sources(self, payload):
        self.calls.append(deepcopy(payload))
        return SimpleNamespace(value=(), metadata={}, usage=AgentUsage())
selector = Selector()
with TemporaryDirectory() as temporary:
    engine = SignalEvolutionEngine(registry=SignalRegistry(Path(temporary)/'signals'),
        raw_info_store=RawInfoStore(), discovery_cases=(make_case('independent_discovery', 1.1),), meta_memory=memory,
        workspace=EvolutionWorkspace(Path(temporary)/'workspace'), mining_model=selector,
        update_model=SimpleNamespace(), llm_signal_runner=None)
    slow_index = engine._controller_memory_index()
    slow_full = {r['source_ref'] for r in slow_index.source_catalog() if r['source_kind']=='runtime_signal_classification'}
    slow_visible = references(slow_index.catalog_view(max_bytes=16_000)) & slow_full
    h1_context = engine._mining_context(cycle_id=1)
    assert len(selector.calls) == 1
    h1_selector_visible = references(selector.calls[0]) & slow_full

result = {
    'kind': 'independent_offline_counterexample_not_live_model',
    'cases': 24, 'executed_declarations': len(full),
    'critic_initial_disclosed': len(visible), 'critic_after_native_browse_disclosed': len(discovered),
    'critic_unaddressed_declarations': len(full-discovered),
    'critic_source_coverage': initial['source_coverage'],
    'native_browse_disclosure': after_browse['memory_disclosures'],
    'known_private_ref_readable_only_if_externally_supplied': known_ref,
    'round_meta_save_restore_equal': entry.to_dict()==restored.to_dict(),
    'slow_native_index_declarations': len(slow_full), 'slow_initial_catalog_declarations': len(slow_visible),
    'slow_visible_refs_filter_excludes': len(slow_full-slow_visible),
    'actual_h1_selector_runtime_declarations': len(h1_selector_visible),
    'actual_h1_source_selector': selector.calls[0],
    'actual_h1_initial_context_runtime_declarations': len(references(h1_context) & slow_full),
    'source_hashes_before': before, 'source_hashes_after': bindings(),
    'source_hashes_stable': before==bindings(), 'network_attempts': len(network),
}
(OUT/'counterreview-result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('source_hashes_before','source_hashes_after','native_browse_disclosure')}, indent=2))
