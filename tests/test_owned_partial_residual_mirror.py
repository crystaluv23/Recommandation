"""Offline regression of owned residual/mirror repair authority; no model calls."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from unittest import TestCase

from stock_opportunity_agent.models import StructuredValidationError, ValidationError
from stock_opportunity_agent.research.evolution_core import (
    InformationPlan, ResearchState, SignalSelectionDecision, SignalRound,
    _assemble_final_context,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController, LLMBlindPredictor
from stock_opportunity_agent.research.evolution_research_validation import (
    _validate_research_state_refs, raw_need_disposition_issues, validate_need_dispositions,
)
from stock_opportunity_agent.research.evolution_output_validation import _validation_obligations
from stock_opportunity_agent.research.evolution_state_patch import apply_state_patch, state_patch_contract
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalResult
from tests.test_evolution_state_patch import PatchCaller, patch


FIXTURE = Path(__file__).parent / 'fixtures/owned_partial_residual_mirror.json'
NOW = datetime(2025, 9, 30, tzinfo=timezone.utc)


class OwnedPartialResidualMirrorTests(TestCase):
    """Keep exact historical replies separate from an authorized scripted repair."""

    def setUp(self):
        self.data = json.loads(FIXTURE.read_text())
        self.prior = ResearchState.from_dict(self.data['prior'])
        self.plan = InformationPlan.from_dict(self.data['plan'])
        self.selections = tuple(SignalSelectionDecision.from_dict(x) for x in self.data['selections'])
        self.batch = SignalBatchResult(results=tuple(SignalResult.from_dict(x) for x in self.data['results']), signal_calls=2)
        self.long = self.data['raw49']['operations'][3]['value']
        self.short = self.data['raw50']['operations'][0]['value']
        self.row = deepcopy(self.data['raw49']['operations'][4]['value'])
        refs = self.data['raw49']['operations'][:2]
        base = self.prior.to_dict()
        base['supporting_evidence'].extend(deepcopy(x['value']) for x in refs)
        base['next_information_needs'][4] = self.long
        self.current = ResearchState.from_dict(base)

    def controller(self, caller):
        value = LLMResearchController(caller)
        value.set_evaluation_context(NOW)
        value.set_reflection_runtime_context(selections=self.selections, must_finalize=False, termination_trigger=None)
        return value

    def envelope(self, current=None, rows=None):
        return {**(current or self.current).to_dict(), 'need_dispositions': deepcopy(rows if rows is not None else [self.row])}

    def repair_contract(self, *, current=None, prior=None, rows=None, selections=None):
        current = current or self.current
        rows = deepcopy(rows if rows is not None else [self.row])
        with self.assertRaises(StructuredValidationError) as caught:
            validate_need_dispositions(rows, previous_state=prior or self.prior, state=current,
                selections=self.selections if selections is None else selections, batch=self.batch)
        base = self.envelope(current, rows)
        feedback = _validation_obligations(caught.exception, base)
        return base, state_patch_contract(base, mode='correction', obligations=feedback['obligations'])

    def test_exact_historical_49_50_replay_retains_the_original_surplus(self):
        # Rebind only transport snapshot hashes: recorded bytes/operations remain untouched.
        def historical(raw):
            def reply(call):
                return {**deepcopy(raw), 'base_hash': call['payload']['output_patch_contract']['base_hash']}
            return reply
        caller = PatchCaller(historical(self.data['raw49']), historical(self.data['raw50']))
        caller.max_structured_corrections = 1
        result = self.controller(caller).reflect(self.plan, self.prior, self.batch)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.value.next_information_needs, (*self.prior.next_information_needs[:4], self.long, self.short))
        self.assertEqual(result.metadata['need_dispositions']['items'][0]['residual_need'], self.short)
        self.assertEqual(self.data['raw50']['operations'], [{'op': 'replace', 'path': 'need_dispositions[0].residual_need', 'value': self.short}])

    def test_unique_owned_mirror_gets_only_replace_dependency(self):
        base, contract = self.repair_contract()
        permissions = contract['allowed_operations']
        self.assertIn({'op': 'replace', 'path': 'next_information_needs[4]', 'descendants': False}, permissions)
        self.assertFalse(any(x['path'] == 'next_information_needs' or x['path'].startswith('next_information_needs[0]') for x in permissions))
        fixed = apply_state_patch(base, patch(contract,
            {'op': 'replace', 'path': 'need_dispositions[0].residual_need', 'value': self.short},
            {'op': 'replace', 'path': 'next_information_needs[4]', 'value': self.short}), contract=contract)
        self.assertEqual(fixed['next_information_needs'], [*self.prior.next_information_needs[:4], self.short])

    def test_scripted_authorized_sync_survives_native_parse_persistence_and_next_consumer(self):
        def first(call):
            return {**deepcopy(self.data['raw49']), 'base_hash': call['payload']['output_patch_contract']['base_hash']}
        def synchronized(call):
            contract = call['payload']['output_patch_contract']
            self.assertIn({'op': 'replace', 'path': 'next_information_needs[4]', 'descendants': False}, contract['allowed_operations'])
            self.assertEqual(call['payload']['validation_feedback']['invalid_output']['next_information_needs'],
                [*self.prior.next_information_needs[:4], self.long])
            return patch(contract,
                {'op': 'replace', 'path': 'need_dispositions[0].residual_need', 'value': self.short},
                {'op': 'replace', 'path': 'next_information_needs[4]', 'value': self.short})
        caller = PatchCaller(first, synchronized)
        caller.max_structured_corrections = 1
        result = self.controller(caller).reflect(self.plan, self.prior, self.batch)
        expected = (*self.prior.next_information_needs[:4], self.short)
        self.assertEqual(result.value.next_information_needs, expected)
        self.assertIn('prospective net equity dilution', expected[-1])
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'accepted.json'
            p.write_text(json.dumps({'value': result.value.to_dict(), 'metadata': result.metadata}))
            saved = json.loads(p.read_text())
            state = ResearchState.from_dict(saved['value'])
            final = _assemble_final_context(plan=self.plan, company_id='anonymous-test', additional_identity_aliases=(),
                basic_info={}, state=state, rounds=(SignalRound(information_needs=self.prior.next_information_needs,
                    selections=self.selections, batch=self.batch),), prediction_time=NOW,
                state_deltas=({'round': 1, 'need_dispositions': saved['metadata']['need_dispositions']},))
            capture = PatchCaller(RuntimeError('offline consumer capture'))
            with self.assertRaisesRegex(RuntimeError, 'offline consumer capture'):
                LLMBlindPredictor(capture).predict(final)
            wire = capture.calls[0]['payload']['final_context']
            self.assertEqual(wire['final_research_state']['next_information_needs'], list(expected))
            self.assertEqual(wire['state_evolution'][0]['need_dispositions'], saved['metadata']['need_dispositions'])

    def test_ambiguous_or_missing_mirrors_do_not_grant_state_edits(self):
        for needs in ((*self.prior.next_information_needs[:4], self.long, self.long), self.prior.next_information_needs):
            with self.subTest(needs=needs):
                _, contract = self.repair_contract(current=replace(self.current, next_information_needs=needs))
                self.assertFalse(any(x['path'].startswith('next_information_needs') for x in contract['allowed_operations']))

    def test_foreign_row_no_owner_and_invalid_refs_do_not_grant_mirror(self):
        variants = [(None, ()), ([{**self.row, 'need_index': 0}], None),
                    ([{**self.row, 'evidence_refs': [{**self.row['evidence_refs'][0], 'evidence_index': 99}]}], None),
                    ([{**self.row, 'reason': ''}], None), ([self.row, deepcopy(self.row)], None)]
        for rows, selections in variants:
            with self.subTest(rows=rows, selections=selections):
                _, contract = self.repair_contract(rows=rows, selections=selections)
                self.assertFalse(any(x['path'].startswith('next_information_needs') for x in contract['allowed_operations']))

    def test_duplicate_prior_preserves_unowned_occurrence(self):
        prior = replace(self.prior, next_information_needs=(*self.prior.next_information_needs, self.prior.next_information_needs[4]))
        current = replace(self.current, next_information_needs=(*self.current.next_information_needs, prior.next_information_needs[5]))
        base, contract = self.repair_contract(current=current, prior=prior)
        fixed = apply_state_patch(base, patch(contract,
            {'op': 'replace', 'path': 'need_dispositions[0].residual_need', 'value': self.short},
            {'op': 'replace', 'path': 'next_information_needs[4]', 'value': self.short}), contract=contract)
        self.assertEqual(fixed['next_information_needs'][5], prior.next_information_needs[5])
        self.assertEqual(fixed['next_information_needs'][:4], list(prior.next_information_needs[:4]))

    def test_scope_rejects_other_need_whole_array_and_belief_edits(self):
        base, contract = self.repair_contract()
        for operation in ({'op':'replace','path':'next_information_needs[0]','value':self.short},
                          {'op':'replace','path':'next_information_needs','value':[self.short]},
                          {'op':'append','path':'next_information_needs','value':self.short},
                          {'op':'replace','path':'current_beliefs[0]','value':'Changed meaning.'},
                          {'op':'remove','path':'next_information_needs[4]'}):
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                apply_state_patch(base, patch(contract, operation), contract=contract)

    def test_raw_diagnostic_without_state_never_grants_mirror_authority(self):
        issues = raw_need_disposition_issues([self.row], previous_state=self.prior,
            selections=self.selections, batch=self.batch)
        self.assertTrue(issues)
        self.assertFalse(any(path.startswith('next_information_needs')
            for issue in issues for path in issue.dependent_paths))

    def test_two_owned_rows_sharing_residual_do_not_grant_unique_state_slot(self):
        second = replace(self.selections[0], target_need_indices=(3,))
        rows = [self.row, {**deepcopy(self.row), 'need_index': 3}]
        _, contract = self.repair_contract(rows=rows, selections=(*self.selections, second))
        self.assertFalse(any(x['path'].startswith('next_information_needs')
            for x in contract['allowed_operations']))

    def test_residual_equal_to_any_prior_need_is_not_a_repairable_mirror(self):
        row = {**deepcopy(self.row), 'residual_need': self.prior.next_information_needs[4]}
        current = replace(self.current, next_information_needs=self.prior.next_information_needs)
        _, contract = self.repair_contract(current=current, rows=[row])
        self.assertFalse(any(x['path'].startswith('next_information_needs')
            for x in contract['allowed_operations']))

    def test_unique_mirror_slot_is_bound_by_exact_value_not_owned_index(self):
        current = replace(self.current, next_information_needs=(
            *self.prior.next_information_needs[:4], 'Which other disclosed fact is still missing?', self.long))
        base, contract = self.repair_contract(current=current)
        self.assertIn({'op': 'replace', 'path': 'next_information_needs[5]', 'descendants': False},
            contract['allowed_operations'])
        self.assertFalse(any(x['path'] == 'next_information_needs[4]' for x in contract['allowed_operations']))
        fixed = apply_state_patch(base, patch(contract,
            {'op': 'replace', 'path': 'need_dispositions[0].residual_need', 'value': self.short},
            {'op': 'replace', 'path': 'next_information_needs[5]', 'value': self.short}), contract=contract)
        self.assertEqual(fixed['next_information_needs'][4], current.next_information_needs[4])

    def test_already_adopted_evidence_does_not_grant_mirror_authority(self):
        prior = replace(self.prior, supporting_evidence=self.current.supporting_evidence)
        _, contract = self.repair_contract(prior=prior)
        self.assertFalse(any(x['path'].startswith('next_information_needs')
            for x in contract['allowed_operations']))

    def test_owned_pending_residual_does_not_defer_other_need_restoration(self):
        current = replace(self.current, next_information_needs=(*self.current.next_information_needs[1:],))
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_research_state_refs(current, phase='reflect', previous_state=self.prior,
                selections=self.selections, batch=self.batch, need_dispositions=[self.row])
        restored = [issue.repair_context.get('prior_need') for issue in caught.exception.issues
            if issue.code == 'research_need_transition_invalid'
            and issue.repair_context.get('required_action') == 'restore_exactly']
        self.assertIn(self.prior.next_information_needs[0], restored)
        self.assertNotIn(self.prior.next_information_needs[4], restored)

    def test_invalid_evidence_keeps_owner_prior_restoration_obligation(self):
        row = {**deepcopy(self.row), 'evidence_refs': [
            {**self.row['evidence_refs'][0], 'evidence_index': 99}]}
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_research_state_refs(self.current, phase='reflect', previous_state=self.prior,
                selections=self.selections, batch=self.batch, need_dispositions=[row])
        self.assertTrue(any(issue.code == 'research_need_transition_invalid'
            and issue.repair_context.get('prior_need') == self.prior.next_information_needs[4]
            and issue.repair_context.get('required_action') == 'restore_exactly'
            for issue in caught.exception.issues))
