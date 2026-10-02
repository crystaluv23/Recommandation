"""Shared authored-inference boundaries and immutable legacy disclosure."""

from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import StructuredValidationError, ValidationError
from stock_opportunity_agent.research.evolution_core import GroundTruth
from stock_opportunity_agent.research.evolution_output_validation import _blind_prediction_from_role
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor, _structured_reflection_items
from stock_opportunity_agent.research.evolution_reflection_memory import (
    ReflectionMemoryIndex, reflection_fact_inference_fields,
)
from stock_opportunity_agent.research.evolution_signal_roles import LLMSignalMiningModel
from stock_opportunity_agent.research.signal_evolution import (
    AgentStep, SignalEvolutionEngine, project_slow_method_memory,
    read_slow_sources, slow_method_memory_sources, validate_slow_memory,
)
from tests.test_evolution_reflection_memory import authored, case
from tests.test_evolution_state_patch import PatchCaller, patch

WEIGHT = 'The prediction acknowledged but underweighted the negative fundamental signals.'
SUFFICIENT = 'The source-backed guidance acceleration and financing actions were sufficient to identify the outcome class and scale.'
FACT = 'The saved prediction was positive and the revealed outcome was negative.'


class ReflectionInferenceContractTests(TestCase):
    def test_fact_detector_keeps_business_facts_negations_and_hypotheses(self):
        invalid = (WEIGHT, SUFFICIENT,
                   'A correct outcome does not prove the label was calibrated, yet the evidence was underweighted.',
                   'The conservative label did not reflect the weight of the positive evidence.')
        safe = (FACT, 'The cash balance was sufficient to cover operating expenses.',
                'The signal has sufficient coverage and the outcome was a surge.',
                'One outcome does not prove the evidence was underweighted.',
                'It is unverified whether the evidence was underweighted.',
                'The analyst maintained an Underweight rating.',
                'The model recorded an overweight rating for the stock.')
        for text in invalid + safe:
            with self.subTest(text=text):
                self.assertEqual(reflection_fact_inference_fields({'kind':'fact','brief':text}),
                                 ('brief',) if text in invalid else ())
                self.assertEqual(reflection_fact_inference_fields({'kind':'hypothesis','brief':text}), ())

    def test_same_guard_at_each_level_has_only_text_and_kind_authority(self):
        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref='case:a')
        source = index.source_catalog()[0]
        for level, category in (('case','misleading_signals'),('plan','misleading_signals'),('round','suspicious_signals')):
            row = authored(source, category=category);row.update(kind='fact',brief=WEIGHT,detail=SUFFICIENT)
            with self.subTest(level=level), self.assertRaises(StructuredValidationError) as caught:
                _structured_reflection_items({'reflection_items':[row], 'selected_reflection_refs':[]},
                    index=index,level=level,owner_ref='owner')
            self.assertEqual([x.paths for x in caught.exception.issues],
                             [('reflection_items[0].brief',),('reflection_items[0].detail',)])
            for issue in caught.exception.issues:
                self.assertEqual(issue.dependent_paths, ('reflection_items[0].kind',))
                self.assertEqual(issue.allowed_repairs, ('replace',))
            with self.assertRaises(ValidationError):index.create_items([row],level=level,owner_ref='owner')

    def _run(self, repair):
        saved = {}
        def initial(call):
            source = call['payload']['source_catalog'][0]
            row = authored(source,category='misleading_signals')
            row.update(kind='fact',brief=WEIGHT,detail=SUFFICIENT)
            sibling = deepcopy(row);sibling.update(brief=FACT,detail=FACT)
            saved.update({'reflection_items':[row,sibling], 'selected_reflection_refs':[]})
            return saved
        caller = PatchCaller(initial, lambda call: repair(call,saved))
        caller.max_structured_corrections = 1
        prediction = _blind_prediction_from_role({'candidate_judgment':'possible','magnitude':'2-3x',
            'confidence':{'level':'low'},'session_id':'anonymous','key_reasons':['Source-backed acceleration supports a repricing candidate.'],
            'uncertainties':['The outcome remains uncertain.']})
        result = LLMBlindPredictor(caller).reflect({},prediction,GroundTruth(1.1)).value
        return result,caller,saved

    def test_native_kind_correction_preserves_observations_sources_and_sibling(self):
        def repair(call,saved):
            self.assertEqual(call['payload']['required_change_paths'],
                             ['reflection_items[0].brief','reflection_items[0].detail'])
            return patch(call['payload']['output_patch_contract'],
                         {'op':'replace','path':'reflection_items[0].kind','value':'hypothesis'})
        result,caller,saved = self._run(repair)
        self.assertIn('under/overweighting',caller.calls[0]['system_prompt'])
        self.assertEqual(result.reflection_items[0].kind,'hypothesis')
        for k,v in saved['reflection_items'][0].items():
            if k!='kind':self.assertEqual(result.reflection_items[0].to_dict()[k],v)
        for k,v in saved['reflection_items'][1].items():self.assertEqual(result.reflection_items[1].to_dict()[k],v)

    def test_inference_and_independent_outcome_issue_share_first_frontier(self):
        index = ReflectionMemoryIndex.from_case_rows([case(correct=True)], owner_ref='case:a')
        source = index.source_catalog()[0]
        inference = authored(source)
        inference.update(kind='fact', brief=WEIGHT, detail=SUFFICIENT)
        incorrect_category = authored(source, category='why_prediction_failed')
        incorrect_category['outcome_claims'] = [
            {'source_ref': source['source_ref'], 'axis': 'binary', 'correct': True},
        ]
        raw = {'reflection_items': [inference, incorrect_category], 'selected_reflection_refs': []}
        original = deepcopy(raw)
        with self.assertRaises(StructuredValidationError) as caught:
            _structured_reflection_items(raw, index=index, level='case', owner_ref='case:a')
        self.assertEqual([issue.paths for issue in caught.exception.issues], [
            ('reflection_items[0].brief',), ('reflection_items[0].detail',),
            ('reflection_items[1].category',),
        ])
        self.assertEqual(raw, original)
        self.assertEqual(index.brief_view()['items'], [])

    def test_native_text_correction_retains_fact_kind(self):
        def repair(call,saved):
            return patch(call['payload']['output_patch_contract'],
                         {'op':'replace','path':'reflection_items[0].brief','value':FACT},
                         {'op':'replace','path':'reflection_items[0].detail','value':FACT})
        result,_,saved = self._run(repair)
        self.assertEqual(result.reflection_items[0].kind,'fact')
        self.assertEqual(result.reflection_items[0].source_refs,tuple(saved['reflection_items'][0]['source_refs']))
        self.assertEqual(result.reflection_items[1].detail,saved['reflection_items'][1]['detail'])

    def test_failed_correction_salvages_only_valid_sibling(self):
        def repair(call,saved):
            return patch(call['payload']['output_patch_contract'],
                         {'op':'replace','path':'reflection_items[0].brief','value':WEIGHT+' Keep this interpretation.'})
        result,_,saved = self._run(repair)
        self.assertEqual(len(result.reflection_items),1)
        self.assertEqual(result.reflection_items[0].detail,saved['reflection_items'][1]['detail'])

    def test_legacy_layer_keeps_hash_original_and_discloses_inference_on_all_views(self):
        snapshot = case()
        index = ReflectionMemoryIndex.from_case_rows([snapshot],owner_ref='case:a')
        row = authored(index.source_catalog()[0]);row.update(kind='fact',brief=WEIGHT,detail=SUFFICIENT)
        # Construct an immutable pre-contract record with its original hash.
        item = index._create_items([row],level='case',owner_ref='case:a',check_inferences=False)[0]
        original = item.to_dict()
        imported = ReflectionMemoryIndex.from_case_rows([{**snapshot,'self_reflection':{'reflection_items':[original]}}],owner_ref='case:a')
        for view in (imported.brief_view(),imported.directory()):
            entry = next(x for x in view['items'] if x['item_ref']==item.item_ref)
            self.assertEqual(entry['inference_status'],'legacy_inference_unchecked')
            self.assertEqual(entry['kind'],'fact')
        entry = next(x for x in imported.source_catalog() if x['source_ref']==item.item_ref)
        self.assertEqual(entry['inference_status'],'legacy_inference_unchecked')
        self.assertEqual(imported.select_items([item.item_ref])[0].to_dict(),original)
        self.assertEqual(item.to_dict(),original)

    def test_new_proof_guard_preserves_readable_legacy_action_and_original_hash(self):
        snapshot = case()
        index = ReflectionMemoryIndex.from_case_rows([snapshot], owner_ref='case:a')
        row = authored(index.source_catalog()[0])
        row['brief'] = 'Require a forward projection tied to the doubling threshold before a surge judgment.'
        with self.assertRaises(ValidationError):
            index.create_items([row], level='case', owner_ref='case:a')
        item = index._create_items([row], level='case', owner_ref='case:a', check_proof_policy=False)[0]
        original = item.to_dict()
        imported = ReflectionMemoryIndex.from_case_rows([
            {**snapshot, 'self_reflection': {'reflection_items': [original]}},
        ], owner_ref='case:a')
        for view in (imported.brief_view(), imported.directory()):
            entry = next(x for x in view['items'] if x['item_ref'] == item.item_ref)
            self.assertEqual(entry['policy_status'], 'legacy_proof_policy_unchecked')
        source = next(x for x in imported.source_catalog() if x['source_ref'] == item.item_ref)
        self.assertEqual(source['policy_status'], 'legacy_proof_policy_unchecked')
        self.assertEqual(imported.select_items([item.item_ref])[0].to_dict(), original)


class SlowReflectionInferenceTests(TestCase):
    """Exercise fresh ingestion, immutable history and pending feedback together."""

    def _output(self):
        episode = {
            'episode_ref': 'episode-1', 'source_refs': ['feedback-1'],
            'reflection': SUFFICIENT, 'unresolved_questions': ['Is the explanation repeatable?'],
            'kind': 'fact', 'brief': WEIGHT,
        }
        lesson = {
            'lesson_id': 'lesson-1', 'guidance': SUFFICIENT,
            'applicable_scope': 'The same disclosed cohort.',
            'support_refs': ['episode-1'], 'counterevidence_refs': ['feedback-1'],
            'limitations': 'This explanation has not been tested.',
            'qualifies_refs': [], 'challenges_refs': [], 'kind': 'fact', 'brief': WEIGHT,
        }
        sibling = {**deepcopy(episode), 'episode_ref': 'episode-2', 'brief': FACT, 'reflection': FACT}
        return {'episode_reflections': [episode, sibling], 'lesson_additions': [lesson]}

    def _memory(self, output):
        return {
            'schema_version': 'slow-memory-v1', 'cycle_id': 1, 'contract_hash': 'contract',
            'input_hash': 'input', 'parent_memory_hash': 'parent', 'reflection_work_hash': 'work',
            'status': 'appended', 'processed_feedback_refs': ['feedback-1'], 'pending_feedback_refs': [],
            'model_view_manifest': {}, 'usage_ref': 'usage', 'failure_ref': None, **output,
        }

    def test_native_kind_deltas_keep_slots_sources_and_valid_sibling(self):
        output = self._output()
        def repair(call):
            feedback = call['payload']['validation_feedback']
            self.assertEqual(feedback['required_change_paths'], [
                'episode_reflections[0].brief', 'episode_reflections[0].reflection',
                'lesson_additions[0].brief', 'lesson_additions[0].guidance',
            ])
            return patch(call['payload']['output_patch_contract'],
                {'op': 'replace', 'path': 'episode_reflections[0].kind', 'value': 'hypothesis'},
                {'op': 'replace', 'path': 'lesson_additions[0].kind', 'value': 'hypothesis'},
            )
        caller = PatchCaller(output, repair)
        result = LLMSignalMiningModel(caller).reflect_feedback({
            'episode_slots': ['episode-1', 'episode-2'], 'lesson_slots': ['lesson-1'],
            'feedback_units': [{'feedback_ref': 'feedback-1'}],
        }).value
        expected = deepcopy(output)
        expected['episode_reflections'][0]['kind'] = 'hypothesis'
        expected['lesson_additions'][0]['kind'] = 'hypothesis'
        self.assertEqual(result, expected)
        self.assertIn('under/overweighting', caller.calls[0]['system_prompt'])
        memory = self._memory(result)
        self.assertEqual(validate_slow_memory(memory, available_feedback_refs=['feedback-1'],
            available_source_refs=['feedback-1'], check_inferences=True), memory)

    def test_history_remains_resolvable_while_fresh_inferences_are_rejected(self):
        output = self._output()
        memory = self._memory(output)
        original = deepcopy(memory)
        self.assertEqual(validate_slow_memory(memory, available_feedback_refs=['feedback-1'],
            available_source_refs=['feedback-1']), original)
        for field in ('episode_reflections', 'lesson_additions'):
            candidate = deepcopy(memory)
            other = 'lesson_additions' if field == 'episode_reflections' else 'episode_reflections'
            for row in candidate[other]:
                row['kind'] = 'hypothesis'
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_slow_memory(candidate, available_feedback_refs=['feedback-1'],
                    available_source_refs=['feedback-1'], check_inferences=True)
        view = project_slow_method_memory([memory], budget_bytes=8000)['memory_deltas'][0]
        catalog = slow_method_memory_sources([memory])
        for field in ('episode_reflections', 'lesson_additions'):
            projected = view[field][0]
            self.assertEqual(projected['inference_status'], 'legacy_inference_unchecked')
            self.assertEqual(projected['original_hash'], canonical_json_hash(output[field][0]))
            original_entries, _ = read_slow_sources([projected['original_ref']], role_scope='H1',
                source_catalog=catalog, budget_bytes=8000)
            self.assertEqual(original_entries[0]['content'], output[field][0])
        self.assertNotIn('inference_status', view['episode_reflections'][1])
        self.assertEqual(memory, original)

    def test_engine_rejection_preserves_feedback_as_pending(self):
        staged = []
        engine = object.__new__(SignalEvolutionEngine)
        engine.workspace = SimpleNamespace(
            committed_slow_artifacts=lambda: [], load_slow_memory=lambda cycle_id: None,
            stage_slow_memory=lambda **kwargs: staged.append(kwargs),
        )
        engine.mining_config = SimpleNamespace(reflection_feedback_limit=12)
        def reflect(payload):
            episode = self._output()['episode_reflections'][0]
            episode['episode_ref'] = payload['episode_slots'][0]
            return AgentStep({'episode_reflections': [episode], 'lesson_additions': []})
        engine.mining_model = SimpleNamespace(reflect_feedback=reflect)
        memory = engine._prepare_slow_memory(cycle_id=1, slow_input={
            'contract_hash': 'contract', 'previous_memory_head': None,
            'feedback_rows': [{'feedback_ref': 'feedback-1', 'result': 'A completed evaluation.'}],
            'source_manifest': [{'ref': 'feedback-1'}],
        })
        self.assertEqual(memory['status'], 'failed')
        self.assertEqual(memory['processed_feedback_refs'], [])
        self.assertEqual(memory['pending_feedback_refs'], ['feedback-1'])
        self.assertEqual(memory['episode_reflections'], [])
        self.assertIn('misclassifies an explanation as fact', memory['failure_ref'])
        self.assertEqual(staged[0]['slow_memory'], memory)
