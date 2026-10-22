"""Classification definition provenance and consumers; scripted replies are wiring only."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, EvolutionControlFlow, ExecutionTrajectory, ResearchDecision, ResearchState,
    RuntimeLimits, SignalRound, SignalSelectionDecision, default_information_plan, execute_information_plan,
    _assemble_final_context,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController, _plan_critic_trajectory
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context, _require_context_signal_pit
from stock_opportunity_agent.research.evolution_research_validation import _signal_batch_model_view
from stock_opportunity_agent.signal_library import (
    SignalBatchResult, SignalExecutionType, SignalExecutor, SignalResult, SignalValue,
    default_deterministic_signal_functions, saved_signal_classification_contracts,
    signal_classification_contract, signal_parameter_names, signal_result_model_view,
)
from tests.evolution_runtime_test_support import ScriptedRoleCaller
from tests.scheme_evolution_test_support import make_trajectory
from tests.test_signal_financials import AS_OF, _spec, _snapshot, _document, _row


def inputs(positive=6, negative=12, cash_flow=-60):
    spec = replace(_spec('runway_control', 'financial.liquidity_runway_months', 0, 0),
        parameters={'positive_runway_max_months': positive, 'negative_runway_min_months': negative})
    content = json.dumps({'cik': 1, 'facts': {'us-gaap': {
        'CashAndCashEquivalentsAtCarryingValue': {'units': {'USD': [_row(None, '2024-12-31', 100, '2025-01-20')]}},
        'NetCashProvidedByUsedInOperatingActivities': {'units': {'USD': [_row('2024-10-01', '2024-12-31', cash_flow, '2025-01-20')]}},
    }}}, sort_keys=True, separators=(',', ':'))
    snapshot = _snapshot((spec,))
    return spec, snapshot, RawInfoStore(documents=(_document('classification-source', content),))


class SignalClassificationContractTests(TestCase):
    def setUp(self):
        network = patch('socket.socket', side_effect=AssertionError('network forbidden'))
        network.start(); self.addCleanup(network.stop)

    def test_real_same_positive_scalar_has_three_different_states_and_exact_parameters(self):
        for pos, neg, state in ((6,12,'positive'), (4,12,'neutral'), (3,4,'negative'), (5,5,'positive')):
            with self.subTest(pos=pos, neg=neg):
                spec, frozen, store = inputs(pos, neg)
                executor = SignalExecutor(frozen, store)
                result = executor.execute_batch((spec.ref,), company_id='issuer_1', as_of=AS_OF).results[0]
                original = result.to_dict()
                contracts = executor.classification_contracts_for((result,))
                view = signal_result_model_view(result, classification_contract=contracts[spec.ref])
                context = view['interpretation']['measurement_context']
                self.assertEqual(context['numeric_measurement']['value'], 5)
                self.assertEqual(context['numeric_measurement']['numeric_sign'], 'positive')
                self.assertEqual(context['numeric_measurement']['categorical_state'], state)
                declaration = context['classification_contract']
                self.assertTrue(declaration['declaration_available'])
                self.assertEqual(declaration['execution']['configured_parameters'], dict(spec.parameters))
                self.assertIn('positive branch is checked first', declaration['execution']['contract'])
                self.assertEqual(result.to_dict(), original)
                self.assertNotIn('classification_contract', original['interpretation'])
                self.assertEqual(executor.classification_contracts_for((SignalResult.from_dict(original),)), {})

    def test_unbounded_is_available_definition_without_numeric_and_missing_is_status_only(self):
        spec, frozen, store = inputs(cash_flow=0)
        executor = SignalExecutor(frozen, store)
        result = executor.execute_batch((spec.ref,), company_id='issuer_1', as_of=AS_OF).results[0]
        self.assertEqual(result.value, SignalValue.NEGATIVE)
        contract = executor.classification_contracts_for((result,))[spec.ref]
        view = signal_result_model_view(result, classification_contract=contract)
        self.assertIn('Non-negative operating cash flow', view['interpretation']['measurement_context']['classification_contract']['execution']['contract'])
        self.assertNotIn('numeric_measurement', view['interpretation']['measurement_context'])
        empty = SignalExecutor(frozen, RawInfoStore())
        missing = empty.execute_batch((spec.ref,), company_id='issuer_1', as_of=AS_OF).results[0]
        self.assertEqual(empty.classification_contracts_for((missing,)), {})
        self.assertNotIn('measurement_context', signal_result_model_view(missing, classification_contract=contract)['interpretation'])

    def test_negative_scalar_can_be_positive_category(self):
        spec = _spec('margin_control','financial.operating_cash_flow_margin',-0.2,-0.3)
        facts = {tag:{'units':{'USD':[_row('2024-01-01','2024-12-31',value,'2025-01-20')]}}
                 for tag,value in (('Revenues',100),('NetCashProvidedByUsedInOperatingActivities',-10))}
        store = RawInfoStore(documents=(_document('negative-margin',json.dumps({'cik':1,'facts':{'us-gaap':facts}},sort_keys=True,separators=(',',':'))),))
        executor = SignalExecutor(_snapshot((spec,)),store)
        result = executor.execute_batch((spec.ref,),company_id='issuer_1',as_of=AS_OF).results[0]
        contract = executor.classification_contracts_for((result,))[spec.ref]
        context = signal_result_model_view(result,classification_contract=contract)['interpretation']['measurement_context']
        self.assertEqual(context['numeric_measurement']['numeric_sign'],'negative')
        self.assertEqual(context['numeric_measurement']['categorical_state'],'positive')
        self.assertEqual(contract['execution']['configured_parameters']['positive_min'],-0.2)

    def test_actual_invoked_override_is_captured_before_mutation_and_noop_clears_products(self):
        spec,frozen,store = inputs()
        default = default_deterministic_signal_functions()[spec.function]
        def later(*_args):
            """Later mapping is not the executed declaration."""
            raise AssertionError('must not run')
        @signal_parameter_names('positive_runway_max_months','negative_runway_min_months')
        def invoked(*args):
            """Actual invoked override delegates the unchanged runway branches."""
            executor.deterministic_functions[spec.function]=later
            return default(*args)
        executor=SignalExecutor(frozen,store,deterministic_functions={spec.function:invoked})
        batch=executor.execute_batch((spec.ref,),company_id='issuer_1',as_of=AS_OF)
        contract=executor.classification_contracts_for(batch.results)[spec.ref]
        self.assertEqual(contract['execution']['contract'],invoked.__doc__)
        contract['execution']['configured_parameters']['positive_runway_max_months']=999
        self.assertEqual(executor.classification_contracts_for(batch.results)[spec.ref]['execution']['configured_parameters']['positive_runway_max_months'],6)
        skipped=executor.execute_batch((spec.ref,),company_id='issuer_1',as_of=AS_OF,prior_fingerprints=batch.document_fingerprints)
        self.assertEqual(skipped.results,())
        self.assertEqual(executor.classification_contracts_for(batch.results),{})

    def test_override_unknown_and_full_frozen_skill_are_not_guessed(self):
        spec, _, _ = inputs()
        @signal_parameter_names('positive_runway_max_months')
        def override(*args):
            """Only this actual override declaration is available; no default threshold rule."""
            raise AssertionError('declaration does not execute')
        declaration = signal_classification_contract(spec, deterministic_functions={spec.function: override})
        self.assertEqual(declaration['execution']['contract'], override.__doc__)
        self.assertEqual(declaration['execution']['configured_parameters'], {'positive_runway_max_months':6})
        self.assertFalse(signal_classification_contract(spec)['declaration_available'])
        llm = replace(spec, execution_type=SignalExecutionType.LLM, function=None,
            modality=None, skill_file='skill.md', parameters={'materiality':7})
        text = 'Complete frozen skill. Positive requires the stated predicate. ' * 150
        skill = signal_classification_contract(llm, skill=text)
        self.assertEqual(skill['execution']['contract'], text)
        self.assertEqual(skill['execution']['configured_parameters'], {'materiality':7})

    def test_wrong_version_hash_conflicts_and_forged_input_projection_reject_or_stay_unknown(self):
        spec, frozen, store = inputs()
        executor = SignalExecutor(frozen, store)
        batch = executor.execute_batch((spec.ref,), company_id='issuer_1', as_of=AS_OF)
        result = batch.results[0]; contract = executor.classification_contracts_for(batch.results)[spec.ref]
        for changed in ({**contract, 'signal_ref':'runway_control:v2'}, {**contract, 'definition':'changed'}):
            with self.assertRaises(ValidationError):
                signal_result_model_view(result, classification_contract=changed)
        forged = result.to_dict(); forged['interpretation']['measurement_context']={'classification_contract':contract}
        self.assertNotIn('classification_contract', signal_result_model_view(forged)['interpretation']['measurement_context'])
        card = signal_result_model_view(result, classification_contract=contract)
        context = {'prediction_time':AS_OF.isoformat(), 'signal_results':[card]}
        _require_context_signal_pit(context)
        card['interpretation']['measurement_context']['classification_contract']['definition']='tampered'
        with self.assertRaises(ValidationError): _require_context_signal_pit(context)
        other=signal_classification_contract(replace(spec,description='Another current declaration'),
            deterministic_functions=default_deterministic_signal_functions(),result=result)
        a=signal_result_model_view(result,classification_contract=contract)
        b=signal_result_model_view(result,classification_contract=other)
        with self.assertRaisesRegex(ValidationError,'conflicting'):
            saved_signal_classification_contracts({'signal_rounds':[{'batch':{'results':[a,b]}}]},round_index=0)

    def test_core_to_real_reflect_final_persistence_posthoc_and_critic_reuses_only_saved_declaration(self):
        spec, frozen, store = inputs()
        original = ResearchState(next_information_needs=('What funding obligations remain unknown?',))
        final = replace(original, decision=ResearchDecision.FINALIZE)
        caller = ScriptedRoleCaller([{**final.to_dict(), 'need_dispositions':[]}])
        class Controller(LLMResearchController):
            def initialize(self, *_args): return AgentStep(original, AgentUsage())
        class Stop(EvolutionControlFlow): pass
        saved = {}
        def sink(_company, _time, context, prediction):
            saved['context']=context
            raise Stop()
        intent = SignalSelectionDecision(spec.ref, reason_code='combine_evidence',
            selection_reason='Add a historical financing benchmark.', expected_role='coverage',
            applicability_hypothesis='Historical context only, with funding still unknown.',
            context_tags=('capital_intensive',))
        executor = SignalExecutor(frozen, store)
        predictor = SimpleNamespace(predict=lambda _context:AgentStep(make_trajectory('unit',1.1,False,None).prediction,AgentUsage()))
        with self.assertRaises(Stop):
            execute_information_plan(plan=default_information_plan(), company_id='issuer_1', company_basic_source={},
                prediction_time=AS_OF, signal_registry=frozen, signal_executor=executor,
                controller=Controller(caller), signal_agent=SimpleNamespace(select=lambda *_a,**_k:AgentStep((intent,),AgentUsage())),
                predictor=predictor, prediction_sink=sink, ground_truth_provider=lambda *_:self.fail('no truth'),
                limits=RuntimeLimits(max_signal_rounds=1))
        reflected = caller.calls[0]['payload']['signal_batch'][0]['measurement_context']['classification_contract']
        context = json.loads(json.dumps(saved['context']))
        contracts = saved_signal_classification_contracts(context,round_index=0)
        self.assertEqual(contracts[spec.ref], reflected)
        self.assertEqual(context['final_research_state']['next_information_needs'], list(original.next_information_needs))
        compact = _compact_posthoc_context(context)
        self.assertEqual(compact['signal_results'][0]['interpretation']['measurement_context']['classification_contract'],reflected)
        result = executor._classification_products[spec.ref][0]
        trajectory = replace(make_trajectory('unit',1.1,False,None), prediction_time=AS_OF,
            final_context=context, signal_rounds=(SignalRound(original.next_information_needs, (intent,),
                SignalBatchResult((result,),1)),))
        restored = ExecutionTrajectory.from_dict(json.loads(json.dumps(trajectory.to_dict())))
        critic = _plan_critic_trajectory(restored, case_index=1)
        self.assertEqual(critic['signal_rounds'][0]['signal_results'][0]['interpretation']['measurement_context']['classification_contract'],reflected)
        legacy = deepcopy(context)
        legacy['signal_rounds'][0]['batch']['results'][0]['interpretation']['measurement_context'].pop('classification_contract')
        self.assertEqual(saved_signal_classification_contracts(legacy,round_index=0),{})
        legacy_critic = _plan_critic_trajectory(replace(restored,final_context=legacy),case_index=1)
        self.assertNotIn('classification_contract',legacy_critic['signal_rounds'][0]['signal_results'][0]['interpretation']['measurement_context'])

    def test_same_ref_in_different_rounds_cannot_fill_unknown_or_rebind_another_result(self):
        spec,frozen,store=inputs()
        executor=SignalExecutor(frozen,store)
        live=executor.execute_batch((spec.ref,),company_id='issuer_1',as_of=AS_OF).results[0]
        imported=SignalResult.from_dict(live.to_dict())
        declaration=executor.classification_contracts_for((live,))
        state=ResearchState(next_information_needs=('What remains unknown?',),decision=ResearchDecision.FINALIZE)
        intent=SignalSelectionDecision(signal_ref=spec.ref,selection_reason='Historical context.',
            expected_role='coverage',reason_code='combine_evidence',
            applicability_hypothesis='No question answered.',context_tags=('capital_intensive',))
        for results,contracts,known in (((imported,live),({},declaration),1),((live,imported),(declaration,{}),0)):
            rounds=tuple(SignalRound(state.next_information_needs,(intent,),SignalBatchResult((r,),1)) for r in results)
            context=_assemble_final_context(plan=default_information_plan(),company_id='issuer_1',additional_identity_aliases=(),
                basic_info={'requests':[]},state=state,rounds=rounds,prediction_time=AS_OF,signal_classification_contracts=contracts)
            for i in (0,1):
                self.assertEqual(bool(saved_signal_classification_contracts(context,round_index=i)),i==known)
            trajectory=replace(make_trajectory('unit',1.1,False,None),prediction_time=AS_OF,final_context=context,signal_rounds=rounds)
            critic=_plan_critic_trajectory(trajectory,case_index=1)
            for i,row in enumerate(critic['signal_rounds']):
                metadata=row['signal_results'][0]['interpretation']['measurement_context']
                self.assertEqual('classification_contract' in metadata,i==known)
        changed=replace(live,measurement=replace(live.measurement,value=5.1),interpretation='liquidity_runway_months=5.1')
        with self.assertRaisesRegex(ValidationError,'result binding'):
            signal_result_model_view(changed,classification_contract=declaration[spec.ref])

    def test_identity_projection_keeps_source_binding_and_valid_anonymous_view(self):
        spec,frozen,store=inputs()
        spec=replace(spec,description='Private Issuer Inc. classification fixture.')
        frozen=_snapshot((spec,))
        default=default_deterministic_signal_functions()[spec.function]
        @signal_parameter_names('positive_runway_max_months','negative_runway_min_months')
        def override(*args):
            """Private Issuer Inc. is control text, not an issuer quote; use existing runway branches."""
            return default(*args)
        executor=SignalExecutor(frozen,store,deterministic_functions={spec.function:override})
        batch=executor.execute_batch((spec.ref,),company_id='issuer_1',as_of=AS_OF)
        declarations=executor.classification_contracts_for(batch.results)
        original=deepcopy(declarations[spec.ref])
        intent=SignalSelectionDecision(signal_ref=spec.ref,selection_reason='Context.',expected_role='coverage',
            reason_code='combine_evidence',applicability_hypothesis='Funding is unknown.',context_tags=('capital_intensive',))
        context=_assemble_final_context(plan=default_information_plan(),company_id='issuer_1',
            additional_identity_aliases=('Private Issuer Inc.',),basic_info={'requests':[]},
            state=ResearchState(decision=ResearchDecision.FINALIZE),rounds=(SignalRound((),(intent,),batch),),
            prediction_time=AS_OF,signal_classification_contracts=(declarations,))
        _require_context_signal_pit(context)
        projected=saved_signal_classification_contracts(context,round_index=0)[spec.ref]
        self.assertNotIn('Private Issuer',str(context))
        self.assertEqual(projected['source_contract_hash'],original['contract_hash'])
        self.assertNotEqual(projected['contract_hash'],original['contract_hash'])
        self.assertEqual(projected['result_hash'],original['result_hash'])
        self.assertEqual(declarations[spec.ref],original)
        signal_result_model_view(batch.results[0],classification_contract=projected)
