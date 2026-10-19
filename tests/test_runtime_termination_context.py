"""Native core stopping decisions must survive into actual pending role messages."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase

from tests.scheme_evolution_test_support import (
    NOW, OneBatchController, OneSignalSelector, ResearchState, ResearchDecision,
    AgentStep, AgentUsage, RuntimeLimits, SignalExecutor, default_information_plan,
    execute_information_plan, make_trajectory,
)
import tests.test_information_plan_engine as engine_tests
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_core import _assemble_final_context
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context


class RuntimeTerminationTests(TestCase):
    def test_actual_core_prediction_wire_and_reservation_keep_distinct_stop_combinations(self):
        for case, expected_stop, expected_trigger in (
            ('initialize_finalized','finalized',None),
            ('no_match','finalized','no_signal_match'),
            ('max_round','finalized','max_signal_rounds'),
            ('terminal_budget','finalized','budget_exhausted'),
            ('hard_budget','budget_exhausted','budget_exhausted'),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry,store = engine_tests.InformationPlanRuntimeTests._registry_and_store(None,directory)
                class Controller(OneBatchController):
                    reflection_calls=0
                    def initialize(self,plan,basic):
                        return AgentStep(ResearchState(next_information_needs=('Which material need remains unanswered?',),
                            decision=ResearchDecision.FINALIZE if case=='initialize_finalized' else ResearchDecision.CONTINUE),
                            AgentUsage(llm_calls=1,tokens=20))
                    def reflect(self,plan,state,batch):
                        self.reflection_calls+=1
                        return AgentStep(replace(state,decision=ResearchDecision.FINALIZE),AgentUsage(llm_calls=1,tokens=20))
                class Selector(OneSignalSelector):
                    def select(self,*args,**kwargs):
                        if case=='no_match': return AgentStep((),AgentUsage(llm_calls=1,tokens=10))
                        return super().select(*args,**kwargs)
                contract=SimpleNamespace(contract_hash='a'*64,limits={'max_local_role_calls':2,'max_structured_corrections':1})
                caller=StructuredRoleClient(registration=get_model('independent-subagent'),contract=contract,
                    workspace=root/'roles',ledger=ExternalAttemptLedger(root/'attempts.json',max_attempts=1,max_total_cost=1),
                    allow_external=False,environ={})
                class Predictor(LLMBlindPredictor):
                    def __init__(self): super().__init__(caller); self.reservations=[]
                    def estimate_prediction_tokens(self,context):
                        self.reservations.append(deepcopy(context))
                        return super().estimate_prediction_tokens(context)
                predictor=Predictor(); controller=Controller()
                limits=RuntimeLimits(max_signal_rounds=1 if case=='max_round' else 2,
                    max_llm_calls=3 if case=='hard_budget' else 6 if case=='terminal_budget' else 30)
                with self.assertRaises(LocalRoleRequestPending) as raised:
                    with caller.anonymous_case(aliases=('winner_1',),company_id='winner_1'):
                        execute_information_plan(plan=default_information_plan(),company_id='winner_1',
                            company_basic_source={},prediction_time=NOW,signal_registry=registry.freeze(),
                            signal_executor=SignalExecutor(registry.freeze(),store),controller=controller,
                            signal_agent=Selector(),predictor=predictor,limits=limits,
                            prediction_sink=lambda *_: self.fail('no prediction answer'),
                            ground_truth_provider=lambda *_: self.fail('no label access'))
                inbox=json.loads(Path(raised.exception.pending['inbox_path']).read_text())
                context=json.loads(inbox['messages'][-1]['content'])['final_context']
                self.assertEqual(context['runtime_termination'],{'phase':'prediction_ready',
                    'stop_reason':expected_stop,'termination_trigger':expected_trigger})
                self.assertEqual(context['final_research_state']['next_information_needs'],['Which material need remains unanswered?'])
                for reservation in predictor.reservations:
                    self.assertEqual(reservation['runtime_termination'],{'phase':'research_in_progress',
                        'stop_reason':None,'termination_trigger':None})
                if case!='initialize_finalized': self.assertTrue(predictor.reservations)
                self.assertEqual(controller.reflection_calls,1 if case in ('max_round','terminal_budget') else 0)

    def test_modern_posthoc_actual_wire_retains_block_and_legacy_keeps_it_absent(self):
        fixture=make_trajectory('fixture',1.1,False,None)
        for block in (None,{'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':'no_signal_match'}):
            context={'prediction_time':NOW.isoformat(),'basic_info':{'requests':[]},'signal_rounds':[],
                     'final_research_state':fixture.final_state.to_dict()}
            if block is not None: context['runtime_termination']=block
            compact=_compact_posthoc_context(context)
            if block is None: self.assertNotIn('runtime_termination',compact)
            else: self.assertEqual(compact['runtime_termination'],block)
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                caller=StructuredRoleClient(registration=get_model('independent-subagent'),
                    contract=SimpleNamespace(contract_hash='a'*64,limits={'max_local_role_calls':1,'max_structured_corrections':1}),
                    workspace=root,ledger=ExternalAttemptLedger(root/'attempts.json',max_attempts=1,max_total_cost=1),
                    allow_external=False,environ={})
                with self.assertRaises(LocalRoleRequestPending) as raised:
                    LLMBlindPredictor(caller).reflect(context,fixture.prediction,fixture.ground_truth)
                inbox=json.loads(Path(raised.exception.pending['inbox_path']).read_text())
                sent=json.loads(inbox['messages'][-1]['content'])['compact_context']
                if block is None: self.assertNotIn('runtime_termination',sent)
                else: self.assertEqual(sent['runtime_termination'],block)

    def test_explicit_progress_and_malformed_blocks_fail_closed_before_dispatch(self):
        from stock_opportunity_agent.research.evolution_core import RuntimeTerminationInputRejected, EvolutionControlFlow
        fixture=make_trajectory('fixture',1.1,False,None)
        progress={'phase':'research_in_progress','stop_reason':None,'termination_trigger':None}
        ready={'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':None}
        blocks=(progress,None,{},False,{**ready,'phase':'unknown'},
                {**ready,'stop_reason':None},{**ready,'stop_reason':'invented'},
                {**ready,'termination_trigger':'invented'},{**ready,'extra':1},
                {**progress,'stop_reason':'finalized'})
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            caller=StructuredRoleClient(registration=get_model('independent-subagent'),
                contract=SimpleNamespace(contract_hash='a'*64,limits={'max_local_role_calls':1,'max_structured_corrections':1}),
                workspace=root,ledger=ExternalAttemptLedger(root/'attempts.json',max_attempts=1,max_total_cost=1),
                allow_external=False,environ={})
            predictor=LLMBlindPredictor(caller)
            context={'prediction_time':NOW.isoformat(),'basic_info':{'requests':[]},'signal_rounds':[],
                     'final_research_state':fixture.final_state.to_dict(),'runtime_termination':progress}
            self.assertGreater(predictor.estimate_prediction_tokens(context),0)
            for block in blocks:
                context['runtime_termination']=block
                for action in (lambda:predictor.predict(context),
                    lambda:predictor.reflect(context,fixture.prediction,fixture.ground_truth),
                    lambda:_compact_posthoc_context(context)):
                    with self.subTest(block=block), self.assertRaises(RuntimeTerminationInputRejected) as raised:
                        action()
                    self.assertIsInstance(raised.exception,EvolutionControlFlow)
            self.assertFalse(list((root/'local_roles/inbox').glob('*.json')))
