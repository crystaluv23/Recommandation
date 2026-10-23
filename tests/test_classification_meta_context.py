"""Actual execution to saved meta and native retrospective reads; no live models."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, CaseReflectionEvidence, PlanMetaMemory, PlanMetaReflection, PlanMetrics, ResearchDecision, ResearchState, RoundMetaEntry,
    SignalRound, SignalSelectionDecision, _assemble_final_context,
    default_information_plan,
    score_predictions,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMPlanCritic
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from stock_opportunity_agent.signal_library import (
    SignalExecutor, SignalRegistry, default_deterministic_signal_functions, signal_parameter_names,
    validate_signal_classification_contract,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from tests.scheme_evolution_test_support import make_case, make_record, make_trajectory
from tests.test_evolution_state_patch import PatchCaller
from tests.test_signal_classification_contract import inputs
from tests.test_signal_financials import AS_OF


def executed_trajectory(*, flows=(-60, -240), thresholds=None, private_declaration=False, declaration_repeat=0, missing_rounds=(), case_number=None):
    """Execute synthetic source variations before assembling saved round cards."""
    rounds, declarations = [], []
    company = 'issuer_1' if case_number is None else f'cik_{case_number:010d}'
    for position, flow in enumerate(flows):
        positive, negative = thresholds[position] if thresholds else (6, 12)
        spec, frozen, store = inputs(positive=positive, negative=negative, cash_flow=flow)
        if case_number is not None:
            original = store.documents[0]
            content = json.loads(original.content)
            content['cik'] = case_number
            store = RawInfoStore(documents=(RawInfoDocument.create(document_id=f'synthetic-{case_number}-{position}',
                company_id=company, source_type=original.source_type, published_at=original.published_at,
                available_at=original.available_at, content=json.dumps(content, sort_keys=True, separators=(',', ':')), metadata={'cik': case_number}),))
        if position in missing_rounds:
            store = RawInfoStore()
        functions = None
        if private_declaration or declaration_repeat:
            default = default_deterministic_signal_functions()[spec.function]
            @signal_parameter_names('positive_runway_max_months', 'negative_runway_min_months')
            def override(*args):
                """Private Issuer Inc. override uses the unchanged runway classification branches."""
                return default(*args)
            override.__doc__ += ' Complete immutable declaration text.' * declaration_repeat
            functions = {spec.function: override}
        executor = SignalExecutor(frozen, store, deterministic_functions=functions)
        batch = executor.execute_batch((spec.ref,), company_id=company, as_of=AS_OF)
        choice = SignalSelectionDecision(signal_ref=spec.ref, selection_reason='Funding context.',
            expected_role='coverage', reason_code='combine_evidence',
            applicability_hypothesis='Funding remains unresolved.', context_tags=('capital_intensive',))
        rounds.append(SignalRound((), (choice,), batch))
        declarations.append(executor.classification_contracts_for(batch.results))
    context = _assemble_final_context(plan=default_information_plan(), company_id=company,
        additional_identity_aliases=(), basic_info={'requests': []},
        state=ResearchState(decision=ResearchDecision.FINALIZE), rounds=tuple(rounds),
        prediction_time=AS_OF, signal_classification_contracts=tuple(declarations))
    return replace(make_trajectory(company, 1.1, False, None), prediction_time=AS_OF,
                   final_context=context, signal_rounds=tuple(rounds))


class ClassificationMetaContextTests(TestCase):
    def test_deferred_declaration_headers_remain_paged_and_exact_version_filtered(self):
        rows = [CaseReflectionEvidence.from_trajectory(executed_trajectory(flows=(-60-i, -240-i), case_number=i+101),
            case_index=i+1).to_dict() for i in range(24)]
        index = ReflectionMemoryIndex.from_case_rows(rows, owner_ref='plan:many')
        declarations = [r for r in index.source_catalog() if r['source_kind'] == 'runtime_signal_classification']
        self.assertEqual(len(declarations), 48)
        initial = {r['source_ref'] for r in index.catalog_view()['sources']}
        self.assertTrue(set(r['source_ref'] for r in declarations) - initial)
        cursor, seen = 0, []
        while cursor is not None:
            page = index.directory(cursor=cursor, level='case', signal_ref=declarations[0]['signal_ref'], max_bytes=1800)
            self.assertLessEqual(len(json.dumps(page, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()), 1800)
            self.assertFalse(page['items'])
            seen.extend(r['source_ref'] for r in page['sources'])
            next_cursor = page['next_cursor']
            self.assertTrue(next_cursor is None or next_cursor > cursor)
            cursor = next_cursor
        self.assertEqual(seen, [r['source_ref'] for r in declarations])
        self.assertEqual(index.directory(signal_ref='unknown:v1')['total'], 0)
        self.assertEqual(index.directory(level='plan')['total'], 0)
        legacy_rows = [{k: v for k, v in row.items() if k != 'signal_classification_context'} for row in rows]
        legacy = ReflectionMemoryIndex.from_case_rows(legacy_rows, owner_ref='plan:many')
        self.assertNotIn('sources', legacy.directory())

    def test_actual_h1_selector_can_read_a_declaration_deferred_by_initial_catalog(self):
        trajectories = tuple(executed_trajectory(flows=(-60-i, -240-i), case_number=i+101) for i in range(24))
        record = replace(make_record('meta_control', 0.0, (1.0,)), trajectories=trajectories,
            evaluation=None, fitness=None, metrics=score_predictions(trajectories))
        entry = RoundMetaEntry(round_id=1, plan_reflections=(PlanMetaReflection.from_record(record),),
                              evidence_refs=(record.plan_id,))
        memory = PlanMetaMemory(entries=(RoundMetaEntry.from_dict(json.loads(json.dumps(entry.to_dict()))),))
        observed = {}
        class Selector:
            def request_slow_sources(self, payload):
                offered = [r for r in payload['available_sources'] if r.get('source_kind') == 'runtime_signal_classification']
                observed['payload'] = payload
                observed['ref'] = next(r['ref'] for r in offered if r['ref'] not in observed['initial'])
                return AgentStep((observed['ref'],))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = SignalEvolutionEngine(registry=SignalRegistry(root/'signals'), raw_info_store=RawInfoStore(),
                discovery_cases=(make_case('issuer_1', 1.1),), meta_memory=memory, workspace=EvolutionWorkspace(root),
                mining_model=Selector(), update_model=None, llm_signal_runner=None)
            index = engine._controller_memory_index()
            observed['initial'] = {r['source_ref'] for r in index.catalog_view()['sources']}
            context = engine._mining_context(cycle_id=1)
            disclosed = next(s['content'] for s in context['meta_memory_disclosures'] if s['ref'] == observed['ref'])
            self.assertEqual(disclosed['content'], index.read_refs([observed['ref']], role='signal_mining')['sources'][0]['content'])
            self.assertLessEqual(len(json.dumps(observed['payload'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()), 32000)
            self.assertNotIn('execution', str(observed['payload']))

    def test_real_categories_unbounded_and_missing_keep_their_actual_declarations(self):
        for positive, negative, state in ((6, 12, 'positive'), (4, 12, 'neutral'), (3, 4, 'negative'), (5, 5, 'positive')):
            with self.subTest(positive=positive, negative=negative):
                trajectory = executed_trajectory(flows=(-60,), thresholds=((positive, negative),))
                self.assertEqual(trajectory.signal_rounds[0].batch.results[0].value.value, state)
                row = CaseReflectionEvidence.from_trajectory(trajectory, case_index=1).signal_classification_context[0]
                self.assertEqual(row['contract']['execution']['configured_parameters'],
                    {'positive_runway_max_months': positive, 'negative_runway_min_months': negative})
        unbounded = executed_trajectory(flows=(0,))
        self.assertIn('Non-negative operating cash flow', CaseReflectionEvidence.from_trajectory(
            unbounded, case_index=1).signal_classification_context[0]['contract']['execution']['contract'])
        mixed = executed_trajectory(missing_rounds=(1,))
        self.assertEqual([r['signal_round'] for r in CaseReflectionEvidence.from_trajectory(
            mixed, case_index=1).signal_classification_context], [1])
        empty = executed_trajectory(flows=(-60,), missing_rounds=(0,))
        self.assertIsNone(CaseReflectionEvidence.from_trajectory(empty, case_index=1).signal_classification_context)

    def test_actual_results_survive_meta_save_and_individually_scoped_source_reads(self):
        trajectory = executed_trajectory()
        meta = CaseReflectionEvidence.from_trajectory(trajectory, case_index=1)
        saved = json.loads(json.dumps(meta.to_dict()))
        self.assertEqual(CaseReflectionEvidence.from_dict(saved).to_dict(), saved)
        rows = saved['signal_classification_context']
        self.assertEqual([r['signal_round'] for r in rows], [1, 2])
        self.assertEqual(rows[0]['signal_ref'], rows[1]['signal_ref'])
        self.assertNotEqual(rows[0]['contract']['result_hash'], rows[1]['contract']['result_hash'])
        index = ReflectionMemoryIndex.from_case_rows([saved], owner_ref='plan:meta')
        catalog = [r for r in index.source_catalog() if r['source_kind'] == 'runtime_signal_classification']
        self.assertEqual(len(catalog), 2)
        for row in catalog:
            self.assertEqual(row['plan_refs'], ['plan:meta'])
            self.assertNotIn('execution', str(row))
            packet = index.read_refs([row['source_ref']], role='signal_mining', max_bytes=row['read_bytes'])
            self.assertEqual(packet['byte_count'], row['read_bytes'])
            source = packet['sources'][0]
            self.assertEqual(source['canonical_outcomes'], {})
            self.assertEqual(source['content']['contract'], rows[row['signal_round'] - 1]['contract'])
            with self.assertRaises(ValidationError):
                index.read_refs([row['source_ref']], role='blind_predictor', max_bytes=100_000)
            with self.assertRaises(ValidationError):
                index.read_refs([row['source_ref']], role='signal_mining', max_bytes=row['read_bytes'] - 1)

    def test_legacy_and_missing_round_are_not_reconstructed_from_another_result(self):
        trajectory = executed_trajectory()
        legacy = deepcopy(trajectory.final_context)
        for row in legacy['signal_rounds']:
            row['batch']['results'][0]['interpretation']['measurement_context'].pop('classification_contract')
        old = CaseReflectionEvidence.from_trajectory(replace(trajectory, final_context=legacy), case_index=1)
        raw = old.to_dict()
        self.assertNotIn('signal_classification_context', raw)
        index = ReflectionMemoryIndex.from_case_rows([raw], owner_ref='plan:legacy')
        before = index.source_catalog()
        restored = CaseReflectionEvidence.from_dict(json.loads(json.dumps(raw)))
        self.assertEqual(canonical_json_hash(restored.to_dict()), canonical_json_hash(raw))
        self.assertEqual(ReflectionMemoryIndex.from_case_rows([restored.to_dict()], owner_ref='plan:legacy').source_catalog(), before)
        missing = deepcopy(trajectory.final_context)
        missing['signal_rounds'][0]['batch']['results'][0]['interpretation']['measurement_context'].pop('classification_contract')
        actual = CaseReflectionEvidence.from_trajectory(replace(trajectory, final_context=missing), case_index=1)
        self.assertEqual([r['signal_round'] for r in actual.signal_classification_context], [2])

    def test_wrong_round_result_and_extra_or_wrong_version_owners_reject(self):
        trajectory = executed_trajectory()
        for mutation in ('swap_result', 'extra_round', 'wrong_ref'):
            context = deepcopy(trajectory.final_context)
            card = context['signal_rounds'][0]['batch']['results'][0]
            if mutation == 'swap_result':
                card['interpretation']['measurement_context']['classification_contract'] = deepcopy(
                    context['signal_rounds'][1]['batch']['results'][0]['interpretation']['measurement_context']['classification_contract'])
            elif mutation == 'extra_round':
                context['signal_rounds'].append(deepcopy(context['signal_rounds'][0]))
            else:
                card['signal_ref'] = 'runway_control:v99'
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                CaseReflectionEvidence.from_trajectory(replace(trajectory, final_context=context), case_index=1)

    def test_duplicate_malformed_and_null_meta_reject_but_explicit_empty_roundtrips(self):
        raw = CaseReflectionEvidence.from_trajectory(executed_trajectory(), case_index=1).to_dict()
        for value in (None, {}, [raw['signal_classification_context'][0]] * 2,
                      [{**raw['signal_classification_context'][0], 'signal_round': True}]):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                CaseReflectionEvidence.from_dict({**raw, 'signal_classification_context': value})
        explicit = {**raw, 'signal_classification_context': []}
        self.assertEqual(CaseReflectionEvidence.from_dict(explicit).to_dict(), explicit)

    def test_real_critic_initial_catalog_then_actual_source_read_preserves_anonymous_hash(self):
        trajectory = executed_trajectory(flows=(-60,), private_declaration=True)
        canonical = CaseReflectionEvidence.from_trajectory(trajectory, case_index=1).to_dict()
        original = canonical['signal_classification_context'][0]['contract']
        observed = {}
        def initial(request):
            payload = request['payload']
            self.assertNotIn('Private Issuer', str(payload))
            self.assertNotIn('signal_classification_context', payload['trajectories'][0])
            rows = [r for r in payload['source_catalog'] if r['source_kind'] == 'runtime_signal_classification']
            self.assertEqual(len(rows), 1)
            self.assertNotIn('definition', rows[0])
            observed['ref'] = rows[0]['source_ref']
            return {'read_refs': [observed['ref']]}
        def after_read(request):
            self.assertNotIn('Private Issuer', str(request['payload']))
            source = request['payload']['memory_disclosures'][0]['sources'][0]
            self.assertEqual(source['source_ref'], observed['ref'])
            projected = source['content']['contract']
            validate_signal_classification_contract(projected, signal_ref=projected['signal_ref'])
            self.assertEqual(projected['source_contract_hash'], original['contract_hash'])
            self.assertNotEqual(projected['contract_hash'], original['contract_hash'])
            self.assertEqual(projected['result_hash'], original['result_hash'])
            return {'reflection_items': [], 'selected_reflection_refs': [], 'no_findings_reason': 'No research conclusion in this wiring control.'}
        caller = PatchCaller(initial, after_read)
        critic = LLMPlanCritic(caller)
        critic.set_anonymous_aliases(('Private Issuer Inc.',))
        critic.critique(plan=default_information_plan(), trajectories=(trajectory,),
                        metrics=PlanMetrics(0, 0, 0, 0, 0, 0, 0, 1, 0, 1))
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(CaseReflectionEvidence.from_trajectory(trajectory, case_index=1).to_dict(), canonical)

    def test_complete_long_declaration_remains_visible_but_native_read_fails_its_budget(self):
        trajectory = executed_trajectory(flows=(-60,), declaration_repeat=1800)
        raw = CaseReflectionEvidence.from_trajectory(trajectory, case_index=1).to_dict()
        full = raw['signal_classification_context'][0]['contract']['execution']['contract']
        self.assertGreater(len(full), 48_000)
        index = ReflectionMemoryIndex.from_case_rows([raw], owner_ref='plan:long')
        row = next(r for r in index.catalog_view()['sources'] if r['source_kind'] == 'runtime_signal_classification')
        self.assertGreater(row['read_bytes'], 48_000)
        packet = index.read_refs([row['source_ref']], role='signal_mining', max_bytes=row['read_bytes'])
        self.assertEqual(packet['sources'][0]['content']['contract']['execution']['contract'], full)
        caller = PatchCaller(lambda request: {'read_refs': [next(r['source_ref'] for r in request['payload']['source_catalog']
            if r['source_kind'] == 'runtime_signal_classification')]})
        reflection = LLMPlanCritic(caller).critique(plan=default_information_plan(), trajectories=(trajectory,),
            metrics=PlanMetrics(0, 0, 0, 0, 0, 0, 0, 1, 0, 1))
        self.assertEqual(len(caller.calls), 1)
        self.assertIn('read byte budget', reflection.no_findings_reason)
        self.assertEqual(CaseReflectionEvidence.from_dict(raw).to_dict(), raw)

    def test_round_meta_roundtrip_reaches_actual_slow_memory_index_without_definition_lookup(self):
        trajectory = executed_trajectory()
        record = replace(make_record('meta_control', 0.0, (1.0,)), trajectories=(trajectory,),
            evaluation=None, fitness=None, metrics=score_predictions((trajectory,)))
        entry = RoundMetaEntry(round_id=1, plan_reflections=(PlanMetaReflection.from_record(record),),
                              evidence_refs=(record.plan_id,))
        raw = json.loads(json.dumps(entry.to_dict()))
        restored = RoundMetaEntry.from_dict(raw)
        self.assertEqual(restored.to_dict(), raw)
        memory = PlanMetaMemory(entries=(restored,))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = SignalEvolutionEngine(registry=SignalRegistry(root/'signals'), raw_info_store=RawInfoStore(),
                discovery_cases=(make_case('issuer_1', 1.1),), meta_memory=memory, workspace=EvolutionWorkspace(root),
                mining_model=None, update_model=None, llm_signal_runner=None)
            index = engine._controller_memory_index()
            rows = [r for r in index.source_catalog() if r['source_kind'] == 'runtime_signal_classification']
            self.assertEqual(len(rows), 2)
            packet = index.read_refs([r['source_ref'] for r in rows], role='signal_mining', max_bytes=48_000)
            self.assertEqual([s['content']['contract'] for s in packet['sources']],
                [r['contract'] for r in CaseReflectionEvidence.from_trajectory(trajectory, case_index=1).signal_classification_context])
