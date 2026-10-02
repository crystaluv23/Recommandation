"""Runtime budget facts cannot become false terminal or need-disposition reasons."""
import unittest
from tests.test_mining_controller import _controller, _fixture_store, ScriptedMiningDecisionModel
from stock_opportunity_agent.research.stage_contracts import budget_claim_issues


class RuntimeBudgetClaimsTests(unittest.TestCase):
    def test_named_counts_and_exhaustion_use_each_independent_dimension(self):
        budget = {'heavy_remaining': 26, 'light_remaining': 0, 'browse_remaining': 0}
        for text in ['heavy_remaining=0', 'heavy_remaining=0.', 'heavy remaining is 26.5.',
                     'No admissible heavy budget for new fetches or statistics.',
                     'The heavy budget is exhausted.', 'Out of heavy budget.']:
            with self.subTest(text=text):
                issues = budget_claim_issues([('rationale[0]', text)], budget)
                self.assertEqual(len(issues), 1)
                self.assertEqual(issues[0].paths, ('rationale[0]',))
                self.assertEqual(issues[0].repair_context['budget'], budget)
        self.assertEqual(budget_claim_issues([('rationale[0]',
            'heavy_remaining=26, light_remaining=0, browse_remaining=0. '
            'No remaining light budget; browse budget is exhausted.')], budget), [])
        issues = budget_claim_issues([('rationale[0]',
            'No heavy budget and no remaining light budget.')],
            {'heavy_remaining': 26, 'light_remaining': 3})
        self.assertEqual({issue.repair_context['counter'] for issue in issues},
                         {'heavy_remaining', 'light_remaining'})

    def test_conditional_previous_denied_and_unspecified_future_costs_are_not_inferred(self):
        for text in ['If heavy budget is exhausted, stop.',
                     'When heavy_remaining=0, stop.', 'Previous heavy_remaining=0.',
                     'It is false that the heavy budget is exhausted.',
                     'The heavy budget is not exhausted.',
                     'The next heavy_remaining=0 would stop this run.',
                     'The heavy budget may not cover all planned future work.',
                     'No heavy budget spent yet; light_remaining=0.',
                     'Browse budget remains positive; no heavy budget spent.',
                     'No heavy budget is required to read this card.',
                     'No supported recurring factor was found; heavy_remaining=26.']:
            with self.subTest(text=text):
                self.assertEqual(budget_claim_issues([('rationale[0]', text)],
                                 {'heavy_remaining': 26}), [])
        self.assertEqual(budget_claim_issues([('rationale[0]', 'No heavy budget.')],
                         {'heavy_remaining': 0}), [])

    def test_terminal_correction_preserves_evidence_and_does_not_force_research(self):
        cases, store = _fixture_store()
        views = []
        def invalid(view):
            views.append(view)
            return {'action': 'record_no_pattern',
                    'coverage': {'explored_families': list(view['evidence_digest']['families_fetched'])},
                    'rationale': ['No remaining backlog needs and no admissible heavy budget for new fetches or statistics; narrative and structured modalities already explored.']}
        def corrected(view):
            views.append(view)
            self.assertIn('rationale[0]', view['last_invalid_action']['issue'])
            self.assertIn('heavy_remaining=11', view['last_invalid_action']['issue'])
            self.assertEqual(view['known_fact_refs'], views[0]['known_fact_refs'])
            self.assertEqual(view['budget'], views[0]['budget'])
            return {'action': 'record_no_pattern',
                    'coverage': {'explored_families': list(view['evidence_digest']['families_fetched'])},
                    'rationale': ['No recurring supported factor was identified; heavy_remaining=11.']}
        model = ScriptedMiningDecisionModel([
            {'action': 'fetch_evidence', 'rationale': ['Fetch sources.'],
             'case_refs': ['case-001', 'case-002'], 'source_families': ['financial'],
             'max_documents': 2}, invalid, corrected])
        controller = _controller(store, cases, model, seed='discovery')
        result = controller.run()
        self.assertEqual(result.terminal_kind, 'no_pattern_with_coverage')
        self.assertEqual(len([e for e in result.ledger if e.action == 'record_no_pattern' and e.terminal_disposition]), 1)
        self.assertEqual(len(views), 2)
        self.assertEqual(controller._heavy_used, 1)

    def test_invalid_need_reason_leaves_only_its_owner_unresolved(self):
        cases, store = _fixture_store()
        controller = _controller(store, cases, None, seed='hypothesis',
            backlog_needs=[{'need_ref': 'need-a', 'need': 'A'},
                           {'need_ref': 'need-b', 'need': 'B'}])
        controller._record_need_dispositions({
            'base_hash': controller._need_state_hash(),
            'need_dispositions': [
                {'need_refs': ['need-a'], 'disposition': 'deferred_measurement',
                 'signal_refs': [], 'rationale': ['Necessary raw narrative is not read yet; heavy_remaining=12.']},
                {'need_refs': ['need-b'], 'disposition': 'deferred_measurement',
                 'signal_refs': [], 'rationale': ['No heavy budget.']},
            ],
        })
        self.assertEqual(controller._pending_need_refs(), ['need-b'])
        staged = tuple(controller._staged_need_dispositions)
        controller._heavy_used += 1
        controller._record_need_dispositions({
            'base_hash': controller._need_state_hash(),
            'need_dispositions': [{'need_refs': ['need-b'], 'disposition': 'deferred_measurement',
                                  'signal_refs': [], 'rationale': ['Necessary raw narrative is not read yet.']}],
        })
        self.assertEqual(controller._pending_need_refs(), [])
        self.assertEqual(controller._staged_need_dispositions[0], staged[0])
        # Prior claims belong to their original action snapshot, not today's counter.
        self.assertEqual(controller._validate_need_dispositions({'need_dispositions': []})[0], staged[0])
