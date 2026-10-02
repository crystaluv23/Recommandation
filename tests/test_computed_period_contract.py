"""Owner-bound observed return periods across State, Predictor and Posthoc."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.compute_tools import compute_metric, format_computed_card_readable
from stock_opportunity_agent.research.evolution_core import (
    GroundTruth, ResearchState, _DocumentChannelProvider, default_information_plan,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _blind_prediction_from_role, _computed_period_issues, _exact_value_fallback,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor, LLMResearchController
from stock_opportunity_agent.research.evolution_research_validation import _normalize_research_state_output
from stock_opportunity_agent.signal_library import SignalBatchResult
from tests.test_evolution_state_patch import PatchCaller, patch

AS_OF = datetime(2025, 9, 30, tzinfo=timezone.utc)
WRONG = 'The price shape showed only a 14.35% six-month return; coverage remains partial.'
CORRECT = WRONG.replace('six-month', '180-trading-day')


def price_document():
    """Generate 180 observed sessions for the production price calculator."""
    day = AS_OF.date() - timedelta(days=1)
    dates = []
    while len(dates) < 180:
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day -= timedelta(days=1)
    rows = [{'as_of_date': value, 'adjusted_close': 43.48 if index < 179 else 49.72}
            for index, value in enumerate(reversed(dates))]
    return RawInfoDocument.create(document_id='market', company_id='issuer', source_type='market_data',
        available_at=AS_OF, published_at=AS_OF, content=json.dumps({'rows': rows}))


def price_card():
    return compute_metric('price_shape', {'window_days': 180}, documents=(price_document(),), as_of=AS_OF)


def prediction():
    return {'candidate_judgment': 'unlikely', 'magnitude': None, 'confidence': {'level': 'medium'},
            'session_id': 'anonymous', 'key_reasons': [WRONG, 'Source-backed operating uncertainty.'],
            'uncertainties': ['Retain this uncertainty.']}


class ComputedPeriodContractTests(TestCase):
    def test_readable_retains_runtime_endpoint_dates_and_numeric_card(self):
        card = price_card(); original = deepcopy(card)
        readable = format_computed_card_readable(card)
        for ref in card['literal_refs']:
            self.assertIn(ref['as_of_date'], readable)
        self.assertIn('window trading days 180', readable)
        self.assertEqual(card, original)

    def test_rounding_signed_returns_and_both_label_orders_have_local_authority(self):
        card = price_card()
        for text in (WRONG, 'The six-month price return was 14.35%.',
                     'The price shows a six-month uptrend with a computed return_pct of 14.35%.',
                     'The observed 6 month return of 14.3514% was modest.'):
            with self.subTest(text=text):
                issues = _computed_period_issues((('key_reasons[0]', text),), (card,))
                self.assertEqual(len(issues), 1)
                issue = issues[0]
                self.assertEqual(issue.paths, ('key_reasons[0]',))
                repaired, actions = _exact_value_fallback(
                    {'key_reasons': [text, 'unchanged']}, StructuredValidationError(issues))
                self.assertEqual(repaired['key_reasons'][1], 'unchanged')
                self.assertIn('180-trading-day', repaired['key_reasons'][0])
                self.assertEqual(actions, {'replace_observed_period': ('key_reasons[0]',)})
                self.assertEqual(_computed_period_issues((('text', repaired['key_reasons'][0]),), (card,)), [])
        negative = deepcopy(card); negative['values']['return_pct'] = -14.3514
        self.assertEqual(len(_computed_period_issues((('text', 'A -14.35% six-month return.'),), (negative,))), 1)

    def test_forecasts_denials_business_returns_other_numbers_and_approximation_are_not_rewritten(self):
        safe = (
            'The stock could achieve a 14.35% six-month return.',
            'The forecast is a six-month return of 14.35%.',
            'This is not a 14.35% six-month return.',
            'A 14.35% six-month return is incorrect.',
            'Revenue six-month return of 14.35%.',
            'A 114.35% six-month return.',
            'A 14.35% sixteen-month return.',
            'A 14.35% roughly six-month return.',
            'A 14.35% return. The six-month horizon remains uncertain.',
            CORRECT,
        )
        for text in safe:
            with self.subTest(text=text):
                self.assertEqual(_computed_period_issues((('text', text),), (price_card(),)), [])

    def test_unique_window_and_calendar_boundaries_not_session_guessing(self):
        card = price_card(); calendar = deepcopy(card)
        calendar['literal_refs'][0]['as_of_date'] = '2025-03-31'
        self.assertEqual(_computed_period_issues((('text', WRONG),), (calendar,)), [])
        self.assertEqual(_computed_period_issues((('text', WRONG),), (card, calendar)), [])
        self.assertEqual(len(_computed_period_issues((('text', WRONG),), (card, deepcopy(card)))), 1)
        end_month = deepcopy(card)
        end_month['literal_refs'] = [{'as_of_date': '2025-02-28'}, {'as_of_date': '2025-08-31'}]
        self.assertEqual(_computed_period_issues((('text', WRONG),), (end_month,)), [])
        missing = deepcopy(card); missing.pop('literal_refs')
        self.assertEqual(_computed_period_issues((('text', WRONG),), (missing,)), [])
        # Date-owning return_between cards have no price_shape session count.
        between = deepcopy(card); between['metric'] = 'return_between'; between['values'].pop('window_trading_days')
        issue = _computed_period_issues((('text', WRONG),), (between,))[0]
        self.assertIn(between['literal_refs'][0]['as_of_date'], issue.repair_context['required_text'])

    def test_state_period_and_temporal_errors_join_first_frontier(self):
        state = ResearchState(resolved_questions=(WRONG,),
            next_information_needs=('What actual revenue results will be reported in 2026?',)).to_dict()
        with self.assertRaises(StructuredValidationError) as caught:
            _normalize_research_state_output(state, initialize=True, basic_info={'requests': []},
                evaluation_context={'prediction_time': AS_OF.isoformat()}, computed_metric_cards=(price_card(),))
        self.assertIn('future_information_unavailable', [i.code for i in caught.exception.issues])
        self.assertIn('computed_metric_period_invalid', [i.code for i in caught.exception.issues])

    def test_initialize_and_predictor_repair_without_extra_model_call_and_preserve_siblings(self):
        card = price_card(); saved = ResearchState(resolved_questions=(WRONG, 'Retain this sibling.'), next_information_needs=('Which customer contracts were disclosed?',)).to_dict()
        caller = PatchCaller(saved); controller = LLMResearchController(caller)
        controller.set_evaluation_context(AS_OF); controller.set_computed_metrics([card])
        # Mutating the caller's card must not change the runtime validation copy.
        card['literal_refs'][0]['as_of_date'] = '2025-03-31'
        state = controller.initialize(default_information_plan(), {'requests': []}).value
        self.assertEqual(state.resolved_questions, (CORRECT, 'Retain this sibling.'))
        self.assertEqual(len(caller.calls), 1)
        self.assertIn('trading sessions', caller.calls[0]['system_prompt'])
        raw = prediction(); caller = PatchCaller(raw)
        result = LLMBlindPredictor(caller).predict({'computed_metrics': [price_card()]}).value
        self.assertEqual(result.key_reasons, (CORRECT, raw['key_reasons'][1]))
        self.assertEqual(result.uncertainties, tuple(raw['uncertainties']))
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(raw['key_reasons'][0], WRONG)

    def test_in_loop_compute_is_validated_then_retained_and_reset(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as root:
            store = RawInfoStore(root)
            provider = _DocumentChannelProvider(store, company_id='issuer', as_of=AS_OF,
                market_documents=(price_document(),))
            state = ResearchState(resolved_questions=('Retain this sibling.',), next_information_needs=('Which customer contracts were disclosed?',))
            def response(call):
                return patch(call['payload']['output_patch_contract'],
                    {'op': 'append', 'path': 'resolved_questions', 'value': WRONG})
            caller = PatchCaller({'compute': [{'metric': 'price_shape', 'params': {'window_days': 180}}]}, response)
            controller = LLMResearchController(caller); controller.set_document_channel(provider)
            controller.set_evaluation_context(AS_OF)
            result = controller.reflect(default_information_plan(), state, SignalBatchResult((), 0)).value
            self.assertEqual(result.resolved_questions, ('Retain this sibling.', CORRECT))
            self.assertEqual(len(caller.calls), 2)
            self.assertEqual(len(controller.computed_metric_cards), 1)
            self.assertEqual(controller.computed_metric_cards[0], provider.computed_metrics[0])
            controller.set_computed_metrics([])
            self.assertEqual(controller.computed_metric_cards, ())
            self.assertEqual(controller.computed_metrics, [])

    def test_posthoc_repairs_brief_and_detail_preserving_sources_and_other_rows(self):
        saved = {}
        def response(call):
            source = call['payload']['source_catalog'][0]
            row = {'category': 'missing_information', 'kind': 'hypothesis', 'brief': WRONG, 'detail': WRONG,
                   'scope': {'case_refs': source['case_refs'], 'plan_refs': source['plan_refs'],
                             'conditions': 'The runtime price window was supplied.'},
                   'limitations': ['Historical returns do not establish the future outcome.'],
                   'source_refs': [source['source_ref']], 'counter_refs': [], 'outcome_claims': []}
            sibling = {**deepcopy(row), 'brief': 'Coverage remains partial.', 'detail': 'Retain this uncertainty.'}
            saved.update(reflection_items=[row, sibling], selected_reflection_refs=[], no_findings_reason=None)
            return saved
        caller = PatchCaller(response)
        raw = prediction(); raw['key_reasons'][0] = CORRECT
        original = _blind_prediction_from_role(raw)
        result = LLMBlindPredictor(caller).reflect({'computed_metrics': [price_card()]}, original, GroundTruth(1.1)).value
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(result.reflection_items[0].brief, CORRECT)
        self.assertEqual(result.reflection_items[0].detail, CORRECT)
        self.assertEqual(result.reflection_items[0].source_refs, tuple(saved['reflection_items'][0]['source_refs']))
        self.assertEqual(result.reflection_items[1].detail, saved['reflection_items'][1]['detail'])
        self.assertEqual(saved['reflection_items'][0]['brief'], WRONG)
        self.assertEqual(original.to_dict(), _blind_prediction_from_role(raw).to_dict())
