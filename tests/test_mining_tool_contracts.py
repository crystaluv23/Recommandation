"""Tool disclosure and arithmetic failure must preserve bounded incremental work."""
from dataclasses import replace
import json
import unittest

from tests.test_mining_controller import _controller, _fixture_store, ScriptedMiningDecisionModel
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.mining_agent_tools import COMPUTE_RULES, compute_statistic
from stock_opportunity_agent.research.stage_contracts import budget_claim_issues


class MiningToolContractTests(unittest.TestCase):
    def test_actual_model_view_exposes_supported_rules_and_read_argument_names(self):
        cases, store = _fixture_store()
        tool = _controller(store, cases, None, seed='discovery')
        view = tool._model_view()
        self.assertEqual(set(view['tool_contracts']['compute_statistic']['rules']), COMPUTE_RULES)
        self.assertEqual(view['tool_contracts']['read_span']['target_count'], 1)
        self.assertEqual(view['tool_contracts']['read_span']['budget_by_target']['event_ref'], 'browse')
        tool._execute_fetch({'case_refs': ['case-001'], 'source_families': ['financial'], 'max_documents': 1})
        refs = [fact.fact_ref for fact in tool._facts.values()][:2]
        with self.assertRaisesRegex(ValidationError, 'allowed:'):
            tool._execute_compute({'rule': 'median', 'fact_refs': refs})
        self.assertEqual(tool._heavy_used, 1)

    def test_numeric_domain_errors_are_typed_without_creating_invalid_results(self):
        cases, store = _fixture_store()
        tool = _controller(store, cases, None, seed='discovery')
        tool._execute_fetch({'case_refs': ['case-001'], 'source_families': ['financial'], 'max_documents': 1})
        first, second = list(tool._facts.values())[:2]
        for rule in ('latest_over_latest', 'latest_over_comparable_prior'):
            with self.subTest(rule=rule):
                with self.assertRaisesRegex(ValidationError, 'non-zero'):
                    compute_statistic(rule, [first.fact_ref, second.fact_ref],
                                      facts=[first, replace(second, value='0')])
        for value in ('nan', 'inf', '-inf', '1e9999'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, 'finite'):
                    compute_statistic('latest_over_latest', [first.fact_ref, second.fact_ref],
                                      facts=[replace(first, value=value), second])
        with self.assertRaisesRegex(ValidationError, 'result must be finite'):
            compute_statistic('latest_minus_comparable_prior', [first.fact_ref, second.fact_ref],
                              facts=[replace(first, value='1e308'), replace(second, value='-1e308')])
        difference = compute_statistic('latest_minus_comparable_prior', [first.fact_ref, second.fact_ref],
                                      facts=[replace(first, value='5'), replace(second, value='0')])
        self.assertEqual(float(difference.value), 5.0)

    def test_zero_denominator_recovery_keeps_saved_need_and_valid_source_state(self):
        cases, original = _fixture_store()
        docs = []
        for doc in original.documents:
            content = json.loads(doc.content)
            content['facts']['us-gaap']['CashAndCashEquivalentsAtCarryingValue']['units']['USD'][1]['val'] = 0
            docs.append(RawInfoDocument.create(document_id=doc.document_id, company_id=doc.company_id,
                source_type=doc.source_type, published_at=doc.published_at, available_at=doc.available_at,
                content=json.dumps(content)))
        saved = []
        def stage(view):
            return {'action': 'record_need_dispositions', 'base_hash': view['need_disposition_contract']['base_hash'],
                'need_dispositions': [{'need_refs': ['need-1'], 'disposition': 'deferred_measurement',
                    'signal_refs': [], 'rationale': ['Retain this measurement need.']}], 'rationale': ['Save a valid independent row.']}
        def invalid(view):
            refs = [fact.fact_ref for fact in tool._facts.values() if fact.case_ref == 'case-001']
            return {'action': 'compute_statistic', 'rule': 'latest_over_comparable_prior',
                    'fact_refs': refs, 'rationale': ['Compute the source-backed ratio.']}
        def corrected(view):
            self.assertIn('non-zero', view['last_invalid_action']['issue'])
            self.assertEqual(view['budget']['heavy_remaining'], 11)
            self.assertEqual(view['need_disposition_contract']['pending_count'], 0)
            return {'action': 'record_no_pattern', 'coverage': {
                    'explored_families': view['evidence_digest']['families_fetched']},
                    'rationale': ['The ratio is undefined for the zero denominator; no replacement measurement was inferred.']}
        model = ScriptedMiningDecisionModel([stage,
            {'action': 'fetch_evidence', 'case_refs': ['case-001'], 'source_families': ['financial'],
             'max_documents': 1, 'rationale': ['Fetch actual fixture source values.']}, invalid, corrected])
        tool = _controller(RawInfoStore(documents=tuple(docs)), cases, model, seed='hypothesis',
                           backlog_needs=[{'need_ref': 'need-1', 'need': 'a new measurement'}],
                           need_progress_sink=lambda unit: saved.append(unit))
        result = tool.run()
        self.assertEqual(result.terminal_kind, 'no_pattern_with_coverage')
        self.assertEqual(result.pending_need_refs, ())
        self.assertEqual(len(saved), 1)
        self.assertEqual(result.need_dispositions[0]['need_refs'], ['need-1'])
        failed = [entry for entry in result.ledger if entry.action == 'compute_statistic']
        self.assertEqual(len(failed), 1)
        self.assertIn('invalid_action', failed[0].note)
        self.assertFalse(failed[0].evidence_refs)

    def test_direct_positive_and_literal_counts_use_the_actual_dimension(self):
        budget = {'heavy_remaining': 26, 'browse_remaining': 0, 'light_remaining': 0}
        for text in ('Browse budget is positive and this is the cheapest way.',
                     'Browse budget remains available.', 'Heavy budget is 0.', 'light budget: 4'):
            with self.subTest(text=text):
                self.assertTrue(budget_claim_issues([('rationale[0]', text)], budget))
        for text in ('Heavy budget is positive.', 'browse budget is 0.',
                     'If browse budget is positive, read.', 'Previous browse budget is 24.',
                     'It is false that browse budget is positive.'):
            with self.subTest(text=text):
                self.assertEqual(budget_claim_issues([('rationale[0]', text)], budget), [])

    def test_inadmissible_budget_action_precedes_its_false_budget_rationale(self):
        cases, store = _fixture_store()
        action = {'action': 'read_span', 'event_ref': 'not-yet-produced', 'length': 100,
                  'rationale': ['Browse budget is positive and permits this read.']}
        model = ScriptedMiningDecisionModel([action, action])
        tool = _controller(store, cases, model, seed='discovery', browse_limit=0)
        result = tool.run()
        self.assertEqual(result.terminal_kind, 'deferred_budget')
        self.assertEqual(result.model_calls, 2)
        self.assertFalse(result.candidates)
        self.assertEqual(tool._browse_used, 0)

    def test_supported_domain_terminal_remains_available_after_heavy_exhaustion(self):
        cases, store = _fixture_store()
        def terminal(view):
            self.assertEqual(view['budget']['heavy_remaining'], 0)
            self.assertIn('record_no_pattern', view['available_actions'])
            return {'action': 'record_no_pattern', 'coverage': {
                    'explored_families': view['evidence_digest']['families_fetched']},
                    'rationale': ['No supported recurring contrast was established by this evidence.']}
        model = ScriptedMiningDecisionModel([
            {'action': 'fetch_evidence', 'case_refs': ['case-001'], 'source_families': ['financial'],
             'max_documents': 1, 'rationale': ['Inspect available structured source.']}, terminal])
        result = _controller(store, cases, model, seed='discovery', heavy_action_limit=1).run()
        self.assertEqual(result.terminal_kind, 'no_pattern_with_coverage')
