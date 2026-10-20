"""Temporary offline authors exercise native roles; no fresh model claim."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_reviewed_owned_partial_stage as stage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import BlindPrediction, RuntimeBudgetExceeded
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange


class ReviewedOwnedPartialStageTests(TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name).resolve()
        self.data=json.loads((Path(__file__).parent/'fixtures/owned_partial_residual_mirror.json').read_text())
        self.sample={'sample_id':'p01','company_id':'cik_0001830043','identity':{'ticker':'BMBL','identity_aliases':['BMBL','Bumble Inc.']},
            'prediction_time':'2025-09-30T00:00:00+00:00','plan':self.data['plan'],'prior_state':self.data['prior'],
            'selections':self.data['selections'],'results':self.data['results'],'basic_info':{},
            'prediction_baseline':None,'computed_metrics':[],'evaluation_anchor':None,'signal_research_status':{}}
        self.oracle=self.base/'oracle.json';self.write(self.oracle,{'profile':'owned_partial_historical_seed','fixed_denominator':1,
            'sample_id':'p01','limits':{'max_local_calls':6,**stage.LIMITS},'assertions':{'secret':'ORACLE_NOT_FOR_ROLE'}})
        self.source=self.base/'completed-source/result.json';self.write(self.source,{'fixture':'no actual source stage'})
        self.code=self.base/'code.py';self.code.write_text('# frozen test dependency\n')
        self.seed=self.base/'historical-seed'
        self.write(self.seed/'inputs.json',{'temporary_seed':'inputs'})
        self.write(self.seed/'completion.json',{'temporary_seed':'completion'})
        expected=json.loads(self.oracle.read_text());expected['bindings']={
            'completed_source_result':stage.binding(self.source),
            'historical_prefix_inputs':stage.binding(self.seed/'inputs.json'),
            'historical_prefix_completion':stage.binding(self.seed/'completion.json')}
        self.write(self.oracle,expected)

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value));return stage.binding(path)

    def prepare(self,name='stage'):
        root=self.base/name
        with patch.object(stage,'SEED',self.seed),patch.object(stage,'_seed',return_value=(deepcopy(self.sample),[stage.binding(self.source)])), \
                patch.object(stage,'_source',return_value=({'root':str(self.base/'not-opened-view')},[stage.binding(self.source)])), \
                patch.object(stage,'_preflight',return_value={'temporary_qualification_fixture':True}), \
                patch.object(stage.prefix,'_code_bindings',return_value=[stage.binding(self.code)]):
            stage.prepare(root,self.oracle,self.source,'a'*40)
        self.assertFalse((root/'exchange').exists())
        return root

    def author(self,pending):
        inbox=json.loads(Path(pending['inbox_path']).read_text())
        payload=json.loads(inbox['messages'][1]['content']);text=json.dumps(payload)
        self.assertNotIn('ORACLE_NOT_FOR_ROLE',text)
        self.assertNotIn('raw49',text);self.assertNotIn('raw50',text)
        if pending['stage']=='research_controller_reflect':
            contract=payload['output_patch_contract']
            if payload['reflection_runtime']['must_finalize']:
                operations=[{'op':'replace','path':'decision','value':'finalize'}]
            else:
                row=deepcopy(self.data['raw49']['operations'][4]['value'])
                row['residual_need']=self.data['raw49']['operations'][3]['value'] if getattr(self,'overlong',False) else self.data['raw50']['operations'][0]['value']
                operations=deepcopy(self.data['raw49']['operations'][:2])+[
                    {'op':'replace','path':'next_information_needs[4]','value':row['residual_need']},
                    {'op':'append','path':'need_dispositions','value':row}]
            raw={'base_hash':contract['base_hash'],'operations':operations}
        elif pending['stage']=='research_controller_reflect_correction':
            contract=payload['output_patch_contract']
            self.assertIn({'op':'replace','path':'next_information_needs[4]','descendants':False},contract['allowed_operations'])
            short=self.data['raw50']['operations'][0]['value']
            raw={'base_hash':contract['base_hash'],'operations':[
                {'op':'replace','path':'need_dispositions[0].residual_need','value':short},
                {'op':'replace','path':'next_information_needs[4]','value':short}]}
        elif pending['stage']=='blind_predictor_predict':
            raw=BlindPrediction(False,'insufficient_information',None,'low',
                ('The supplied historical financing facts do not establish prospective business acceleration.',),
                ('Cash generation and prospective dilution remain unresolved.',),'offline-test').to_dict()
        else: self.fail('Unexpected correction in ordinary valid offline author: '+pending['stage'])
        if pending['stage']=='blind_predictor_predict':raw.pop('is_surge',None)
        Path(pending['outbox_path']).write_text(json.dumps(raw))
        LocalRoleExchange(Path(pending['inbox_path']).parents[1],max_calls=6).submit(pending['request_hash'],agent_id='offline-fixture-not-model')

    def complete(self,root):
        for _ in range(6):
            result=stage.resume(root)
            if result['status']=='pending_independent_role':self.author(result['pending'])
            else:return result
        self.fail('Too many requests')

    def test_native_reflect_closure_predictor_sink_and_exact_completed_restore(self):
        root=self.prepare();result=self.complete(root)
        self.assertEqual(result['status'],'prediction_persisted_requires_independent_review')
        self.assertEqual(result['independent_receipts'],3)
        self.assertEqual(result['mirror_correction_branch'],'not_exercised')
        saved=json.loads((root/'prediction.json').read_text())
        self.assertEqual(saved['final_context'],json.loads((root/'final-context.json').read_text()))
        needs=saved['final_context']['final_research_state']['next_information_needs']
        self.assertEqual(needs[:4],self.sample['prior_state']['next_information_needs'][:4])
        self.assertEqual(len(needs),5)
        before=stage._files(root)
        with patch.object(stage,'_reflect',side_effect=AssertionError('completed restore must not execute')):
            restored=stage.resume(root)
        self.assertTrue(restored['restored_without_execution']);self.assertEqual(stage._files(root),before)
        (root/'nested').mkdir();(root/'nested/progress.json').write_text('{}')
        with self.assertRaisesRegex(ValidationError,'completed owned partial artifacts'):stage.resume(root)

    def test_offline_overlength_fixture_exercises_native_mirror_correction_not_claimed_fresh(self):
        self.overlong=True
        root=self.prepare();result=self.complete(root)
        self.assertEqual(result['status'],'prediction_persisted_requires_independent_review')
        self.assertEqual(result['independent_receipts'],4)
        self.assertEqual(result['mirror_correction_branch'],'exercised_requires_independent_review')
        context=json.loads((root/'prediction.json').read_text())['final_context']
        self.assertEqual(len(context['final_research_state']['next_information_needs']),5)
        self.assertEqual(context['final_research_state']['next_information_needs'][-1],self.data['raw50']['operations'][0]['value'])

    def test_invocation_budget_is_remaining_while_callback_enforces_each_request(self):
        from types import SimpleNamespace
        from stock_opportunity_agent.research.evolution_core import ResearchState
        from stock_opportunity_agent.signal_library import SignalBatchResult
        budget=stage._Budget({'limits':stage.LIMITS});budget.tokens=123
        with patch.object(stage,'LLMResearchController') as factory:
            factory.return_value.reflect.return_value=SimpleNamespace(value='not an actual model reply')
            stage._reflect(None,self.sample,ResearchState.from_dict(self.sample['prior_state']),SignalBatchResult(results=(),signal_calls=0),False,budget)
            factory.return_value.set_request_token_budget.assert_called_once_with(512000-64000-123)

    def test_actual_canonical_bootstrap_keeps_all17_cards_and_visibility_at_native_assembly(self):
        from dataclasses import replace
        from datetime import datetime
        from stock_opportunity_agent.research.evolution_core import (
            InformationPlan,ResearchState,ResearchDecision,_assemble_final_context,_mask_identity_values,
        )
        actual=Path(__file__).resolve().parents[1]/'runs/diagnostics/reviewed_fast_prefix_20261020_v1'
        bootstrap_file=actual/'preflight.json'
        self.assertEqual(stage.binding(bootstrap_file)['sha256'],'b89e499bfeb4d07a5464c152d675f1ad80040345c7122e85ada38db1db3615c6')
        bootstrap=json.loads(bootstrap_file.read_text())['model_context']
        with patch.object(stage,'SEED',actual),patch.object(stage,'_parent_snapshot',return_value={'files':[],'external_files':[]}):
            sample,_=stage._seed('a'*40)
        self.assertEqual(sample['basic_info'],bootstrap)
        self.assertEqual([len(row['projections']) for row in bootstrap['requests']],[16,1])
        self.assertNotIn('[ANON_',json.dumps(bootstrap))
        kwargs={'plan':InformationPlan.from_dict(sample['plan']),'company_id':sample['company_id'],
            'additional_identity_aliases':tuple(sample['identity']['identity_aliases']),
            'state':replace(ResearchState.from_dict(sample['prior_state']),decision=ResearchDecision.FINALIZE),
            'rounds':(),'prediction_time':datetime.fromisoformat(sample['prediction_time'])}
        final=_assemble_final_context(basic_info=sample['basic_info'],**kwargs)['basic_info']
        expected=[{'request_id':row['request']['request_id'],**{k:p[k] for k in ('projection_id','document_id','available_at','exact_text')},
            'truncated':False} for row in bootstrap['requests'] for p in row['projections']]
        aliases=(sample['company_id'],*sample['identity']['identity_aliases'])
        self.assertEqual(final['projection_cards'],_mask_identity_values(expected,aliases))
        self.assertEqual(len(final['projection_cards']),17)
        for row,index in zip(bootstrap['requests'],final['source_index']):
            for key in ('available_projection_count','visible_projection_count','omitted_projection_count','projection_status',
                'effective_context_truncated','projection_context_truncated','source_context_truncated','omitted_context_markers'):
                self.assertEqual(index[key],_mask_identity_values(row[key],aliases))
        # Exact old wrong-shape counterexample: 17 already-assembled cards are
        # not bootstrap requests, so passing that shape back produces zero.
        wrong=_assemble_final_context(basic_info=final,**kwargs)['basic_info']
        self.assertEqual(len(wrong['projection_cards']),0)

    def test_source_code_or_oracle_drift_rejects_before_transport(self):
        for index,which in enumerate(('source','code','oracle')):
            root=self.prepare(str(index));path={'source':self.source,'code':self.code,'oracle':self.oracle}[which];old=path.read_bytes()
            path.write_bytes(old+b' ')
            with patch.object(stage,'_run',side_effect=AssertionError('must reject before transport')):
                with self.assertRaises(ValidationError):stage.resume(root)
            path.write_bytes(old)

    def test_budget_guard_runs_before_any_receive_and_counts_replayed_logical_requests(self):
        callback=stage._Budget({'limits':stage.LIMITS})
        path=self.base/'request.json'
        self.write(path,{'request':{'stage':'research_controller_reflect','messages':[{'content':'x'*131073}],'max_output_tokens':1}})
        with self.assertRaises(RuntimeBudgetExceeded):callback({'event_type':'request_ready','request_path':str(path)})
        self.assertEqual(callback.calls,0)
        self.write(path,{'request':{'stage':'blind_predictor_predict','messages':[{'content':'x'}],'max_output_tokens':2000}})
        for _ in range(6):callback({'event_type':'request_ready','request_path':str(path)})
        with self.assertRaises(RuntimeBudgetExceeded):callback({'event_type':'request_ready','request_path':str(path)})
        self.assertEqual(callback.calls,6)

    def test_oracle_authorities_reject_other_source_path_before_seed_or_transport(self):
        other=self.base/'other-result.json';other.write_bytes(self.source.read_bytes())
        with patch.object(stage,'SEED',self.seed),patch.object(stage,'_seed',side_effect=AssertionError('authority check first')):
            with self.assertRaisesRegex(ValidationError,'source/seed authority differs'):
                stage.prepare(self.base/'wrong',self.oracle,other,'a'*40)
        self.assertFalse((self.base/'wrong').exists())

    def test_frozen_destination_cannot_be_copied_to_reset_stage(self):
        import shutil
        root=self.prepare();copy=self.base/'relocated';shutil.copytree(root,copy)
        with patch.object(stage,'_run',side_effect=AssertionError('relocation must reject before transport')):
            with self.assertRaises(ValidationError):stage.resume(copy)

    def source_metadata_chain(self):
        parent=self.source.parent;proof=parent/'raw-proof.json';self.write(proof,{'source':'temporary raw evidence'})
        plan=parent/'plan.json';plan_binding=self.write(plan,{'plan_hash':'temporary-plan',
            'source_bindings':[stage.binding(proof)],'code_bindings':[]})
        oracle=parent/'oracle.json';self.write(oracle,{'oracle_id':'temporary-metadata-only'})
        review=parent/'source-review.json';review_binding=self.write(review,{'oracle_identity':stage.binding(oracle),'records':[]})
        view_root=parent/'snapshot';view_root.mkdir()
        marker=self.write(view_root/'reviewed_snapshot.json',{'temporary_metadata_only':True})
        view={'root':str(view_root),'store_type':'reviewed','manifest_sha256':marker['sha256']}
        self.write(parent/'input_manifest.json',{'plan':plan_binding,'source_review':review_binding,'reviewed_source_snapshot':view})
        self.write(self.source,{'status':'completed','fixed_cases':40,'per_group_inputs':720,'labels':False,'models':0,'GETs':0,
            'plan_hash':'temporary-plan','reviewed_source_snapshot':view,'source_review':review_binding})
        expected=json.loads(self.oracle.read_text());expected['bindings']['completed_source_result']=stage.binding(self.source)
        self.write(self.oracle,expected)
        return view,plan,review,proof

    def test_real_source_metadata_reader_accepts_serialized_plan_and_review_paths(self):
        view,plan,review,proof=self.source_metadata_chain()
        self.assertIsInstance(json.loads((self.source.parent/'input_manifest.json').read_text())['plan']['path'],str)
        self.assertIsInstance(json.loads(self.source.read_text())['source_review']['path'],str)
        actual,bindings=stage._source(self.source)
        self.assertEqual(actual,view)
        for path in (plan,review,proof):self.assertIn(stage.binding(path),bindings)
        stage._check(bindings)
        self.assertEqual(stage.read(str(plan)),json.loads(plan.read_text()))
        self.assertEqual(stage.read(review),json.loads(review.read_text()))

    def test_real_serialized_source_chain_freezes_and_drift_rejects_before_transport(self):
        view,plan,review,proof=self.source_metadata_chain();root=self.base/'real-chain-stage'
        # Only source admission is a temporary fixture; _source and read are real.
        with patch.object(stage,'SEED',self.seed),patch.object(stage,'_seed',return_value=(deepcopy(self.sample),[])), \
                patch.object(stage,'_preflight',return_value={'temporary_admission_only':True}), \
                patch.object(stage.prefix,'_code_bindings',return_value=[stage.binding(self.code)]):
            stage.prepare(root,self.oracle,str(self.source),'a'*40)
        self.assertFalse((root/'exchange').exists())
        for path in (plan,review,proof):
            with self.subTest(path=path.name):
                original=path.read_bytes();path.write_bytes(original+b' ')
                with patch.object(stage,'_run',side_effect=AssertionError('must reject before transport')):
                    with self.assertRaisesRegex(ValidationError,'bound stage source/code changed'):stage.resume(root)
                path.write_bytes(original)

    def test_terminal_failure_cannot_restart_or_replace_ceiling(self):
        for index,error in enumerate((ValidationError('offline fixture terminal fault'),RuntimeBudgetExceeded('frozen budget'))):
            root=self.prepare('failure'+str(index))
            with patch.object(stage,'_reflect',side_effect=error):result=stage.resume(root)
            self.assertEqual(result['status'],'control_budget_stopped' if index else 'terminal_failed')
            with self.assertRaisesRegex(ValidationError,'terminal owned partial failure'):stage.resume(root)

    def test_seed_exports_only_accepted_first_round_and_allowlisted_context(self):
        seed=self.base/'historical';context={k:self.sample[k] for k in ('basic_info','prediction_baseline','computed_metrics')}
        context.update(final_research_state={'secret':'OLD_FINAL_STATE'},future_material='FUTURE_SECRET')
        self.write(seed/'inputs.json',{'sample':{k:self.sample[k] for k in ('company_id','identity','prediction_time','plan')}})
        self.write(seed/'prediction.json',{'final_context':context,'prediction':{'secret':'OLD_PREDICTION'}})
        self.write(seed/'preflight.json',{'model_context':self.sample['basic_info']})
        self.write(seed/'observations/initialize_00.json',{'value':self.sample['prior_state']})
        self.write(seed/'observations/routing_00.json',{'value':self.sample['selections']})
        for name,result in zip(('signal_group_00.json','signal_group_01.json'),reversed(self.sample['results'])):
            self.write(seed/'observations'/name,{'results':[result]})
        self.write(seed/'observations/reflect_00.json',{'request_hashes':['a'*64]})
        self.write(seed/'requests'/('a'*64+'.json'),{'request':{'messages':[{}, {'content':json.dumps({
            'evaluation_anchor':self.sample['prediction_baseline'],'signal_research_status':{},'raw49':'OLD_RAW_ANSWER'})}]}})
        with patch.object(stage,'SEED',seed),patch.object(stage,'_parent_snapshot',return_value={'files':[], 'external_files':[]}):
            exported,_=stage._seed('a'*40)
        self.assertEqual(exported,self.sample)
        for secret in ('OLD_FINAL_STATE','FUTURE_SECRET','OLD_PREDICTION','OLD_RAW_ANSWER'):
            self.assertNotIn(secret,json.dumps(exported))
