"""Daily UTC windows and two-stage visibility use actual saved input shapes."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.data.acquisition import HistoricalPriceAdapter
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import BasicInfoBundle, RawInfoRequest, _structured_market_context_ranges
from stock_opportunity_agent.data.sources.massive import _price_bar_from_result
from stock_opportunity_agent.research.compute_tools import compute_metric
from stock_opportunity_agent.research.evolution_core import (
    ResearchState, RuntimeStopReason, default_information_plan, project_basic_info_bundle,
    _assemble_final_context, _prediction_baseline_from_market_documents,
)
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_plan_roles import _plan_critic_trajectory

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'runs/diagnostics/reviewed_market_snapshot_20261019_v2/basic_info.json'
BOUNDARY = ROOT / 'runs/diagnostics/market_baseline_timezone_boundary_20261019_v1/consumer-chain.json'
UTC = datetime.fromisoformat('2025-09-30T00:00:00+00:00')


def original_market():
    return RawInfoDocument.from_dict(json.loads(Path(json.loads(BOUNDARY.read_text())['source']['path']).read_text()))


def final_view(model):
    return _assemble_final_context(plan=default_information_plan(), company_id='cik_0001830043',
        additional_identity_aliases=(), basic_info=model,
        state=ResearchState(next_information_needs=('What operating evidence remains missing?',)),
        rounds=(), prediction_time=UTC)


def critic_view(model, final):
    data = {'basic_info_bundle': model, 'final_context': final, 'signal_rounds': []}
    item = SimpleNamespace(prediction_time=UTC, signal_rounds=(), state_deltas=(),
        stop_reason=RuntimeStopReason.NO_SIGNAL_MATCH, termination_trigger=None,
        to_dict=lambda: data)
    return _plan_critic_trajectory(item, case_index=0)


class DailyUTCWindowTests(TestCase):
    def test_equivalent_instants_keep_all_four_native_windows(self):
        doc = original_market()
        cache = json.loads(Path(json.loads(BOUNDARY.read_text())['raw_cache']['path']).read_text())
        clock = datetime.fromisoformat(json.loads(doc.content)[0]['retrieved_at'])
        bars = tuple(_price_bar_from_result('BMBL', row, clock, adjusted=True) for row in cache['body']['results'])
        request = RawInfoRequest('market', 'recent daily observations', ('market_data',), lookback_days=45)
        outputs = []
        for cutoff in (UTC, UTC.astimezone(timezone(timedelta(hours=-4))),
                       UTC.astimezone(timezone(timedelta(hours=14))),
                       UTC+timedelta(hours=18), (UTC+timedelta(hours=18)).astimezone(timezone(timedelta(hours=14)))):
            calls = []
            def fetch(symbol, start, end):
                calls.append((symbol, start.isoformat(), end.isoformat()))
                return [bar for bar in bars if start <= bar.as_of_date <= end]
            acquired = HistoricalPriceAdapter('massive', fetch).acquire(request, company_id=doc.company_id, identity={'ticker':'BMBL'}, as_of=cutoff)
            metric = compute_metric('price_shape', {'window_days':30}, documents=(doc,), as_of=cutoff)
            outputs.append({'request':calls, 'acquired':acquired.documents[0].to_dict(),
                'ranges':_structured_market_context_ranges(doc, request, cutoff),
                'baseline':_prediction_baseline_from_market_documents((doc,), cutoff),
                'metric':{key:metric[key] for key in ('values','labels','literal_refs')}})
        self.assertEqual(outputs[0], outputs[1])
        self.assertTrue(all(output==outputs[0] for output in outputs[1:]))

    def test_adjacent_utc_day_keeps_distinct_strict_computation_boundary(self):
        doc = RawInfoDocument.create(document_id='row-guard-fixture', company_id='issuer',
            source_type='market_data', published_at=UTC-timedelta(days=10), available_at=UTC-timedelta(days=10),
            content=json.dumps([{'as_of_date':f'2025-09-{day:02}', 'adjusted_close':float(day)} for day in range(20,31)]))
        earlier = UTC - timedelta(seconds=1)
        self.assertNotEqual(_prediction_baseline_from_market_documents((doc,), UTC),
                            _prediction_baseline_from_market_documents((doc,), earlier))

    def test_direct_naive_cutoffs_reject_without_host_timezone_guess(self):
        doc = original_market()
        cutoff = UTC.replace(tzinfo=None)
        request = RawInfoRequest('daily', 'daily observations', ('market_data',), lookback_days=1)
        for action in (
            lambda: HistoricalPriceAdapter('massive', lambda *_: self.fail('fetch before aware guard')).acquire(
                request, company_id='issuer', identity={'ticker':'BMBL'}, as_of=cutoff),
            lambda: _structured_market_context_ranges(doc, request, cutoff),
            lambda: compute_metric('price_shape', {'window_days':30}, documents=(doc,), as_of=cutoff),
            lambda: _prediction_baseline_from_market_documents((doc,), cutoff),
        ):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                action()

    def test_reader_retains_its_inclusive_upper_day(self):
        rows = [{'as_of_date':day, 'adjusted_close':1} for day in ('2025-09-29','2025-09-30','2025-10-01')]
        doc = RawInfoDocument.create(document_id='days', company_id='issuer', source_type='market_data',
            published_at=UTC, available_at=UTC, content=json.dumps(rows))
        request = RawInfoRequest('daily', 'daily observations', ('market_data',), lookback_days=1)
        ranges = _structured_market_context_ranges(doc, request, UTC.astimezone(timezone(timedelta(hours=-4))))
        exposed = ' '.join(doc.content[start:end] for start,end in ranges)
        self.assertIn('2025-09-29', exposed)
        self.assertIn('2025-09-30', exposed)
        self.assertNotIn('2025-10-01', exposed)


class BasicInfoVisibilityTests(TestCase):
    def test_actual_upstream_omission_reaches_all_consumers(self):
        source = json.loads(SOURCE.read_text())
        model, _ = project_basic_info_bundle(BasicInfoBundle.from_dict(source['bundle']))
        row = next(row for row in model['requests'] if row['request']['request_id']=='recent_market_backbone')
        self.assertEqual(row['projection_status'], 'partial_context_budget')
        self.assertIs(row['source_context_truncated'], True)
        self.assertIs(row['projection_context_truncated'], False)
        self.assertIs(row['effective_context_truncated'], True)
        self.assertEqual(row['omitted_projection_count'], 0)
        final = final_view(model)
        contexts = [final['basic_info']['source_index'],
                    _compact_posthoc_context(final)['basic_info_source_index'],
                    _compact_posthoc_context({'basic_info':model})['basic_info_source_index'],
                    critic_view(model, final)['basic_info_source_index']]
        for index in contexts:
            saved = next(item for item in index if item['request_id']=='recent_market_backbone')
            for field in ('source_context_truncated','projection_context_truncated','effective_context_truncated',
                          'omitted_context_markers','projection_status','omitted_projection_count'):
                self.assertEqual(saved[field], row[field])

    def test_both_budget_layers_and_unknown_legacy(self):
        source = json.loads(SOURCE.read_text())
        model, _ = project_basic_info_bundle(BasicInfoBundle.from_dict(source['bundle']), max_chars=2000)
        partial = [r for r in model['requests'] if r['omitted_projection_count']]
        self.assertTrue(partial)
        self.assertTrue(all(r['projection_context_truncated'] is True for r in partial))
        legacy = {'request':{'request_id':'old','source_types':['filing']}, 'status':'resolved',
                  'projection_status':'complete', 'available_projection_count':1,
                  'visible_projection_count':1, 'omitted_projection_count':0, 'projections':[]}
        for markers in ([], ['some text omitted']):
            row = dict(legacy, omitted_context_markers=markers)
            saved = _compact_posthoc_context({'basic_info':{'requests':[row]}})['basic_info_source_index'][0]
            self.assertIsNone(saved['source_context_truncated'])
            self.assertIsNone(saved['projection_context_truncated'])
            self.assertIs(saved['effective_context_truncated'], True if markers else None)
            self.assertEqual(saved['projection_status'], 'partial_context_budget' if markers else 'visibility_unknown')

    def test_critic_fallback_preserves_saved_model_visibility(self):
        model = json.loads(SOURCE.read_text())['model_context']
        compact = critic_view(model, {})
        market = next(row for row in compact['basic_info_source_index'] if row['request_id']=='recent_market_backbone')
        self.assertTrue(market['omitted_context_markers'])
        self.assertIs(market['effective_context_truncated'], True)
        self.assertIsNone(market['source_context_truncated'])

    def test_summary_preserves_known_complete_unknown_and_masking(self):
        from stock_opportunity_agent.research.basic_info_visibility import basic_info_source_index
        from stock_opportunity_agent.research.evolution_core import _mask_identity_values
        row = {'request':{'request_id':'scope', 'source_types':['filing']}, 'status':'resolved',
               'projection_status':'complete', 'source_context_truncated':False,
               'projection_context_truncated':False, 'omitted_context_markers':[],
               'available_projection_count':1, 'visible_projection_count':1, 'omitted_projection_count':0}
        full = basic_info_source_index({'requests':[row]})[0]
        self.assertIs(full['effective_context_truncated'], False)
        self.assertEqual(full['projection_status'], 'complete')
        row['omitted_context_markers'] = ['BMBL issuer material omitted']
        masked = _mask_identity_values(basic_info_source_index({'requests':[row]}), ('BMBL',))
        self.assertNotIn('BMBL', json.dumps(masked))
        self.assertTrue(masked[0]['omitted_context_markers'])
        self.assertIs(masked[0]['effective_context_truncated'], True)
        self.assertNotIn('supporting_evidence', masked[0])

    def test_legacy_known_omission_is_not_erased_or_assigned_to_a_guessed_layer(self):
        from stock_opportunity_agent.research.basic_info_visibility import basic_info_visibility
        for values in ({'projection_status':'partial_context_budget'},
                       {'projection_status':'omitted_context_budget'},
                       {'effective_context_truncated':True}, {'omitted_projection_count':2}):
            with self.subTest(values=values):
                summary = basic_info_visibility(values)
                self.assertIs(summary['effective_context_truncated'], True)
                self.assertIsNone(summary['source_context_truncated'])
                self.assertIsNone(summary['projection_context_truncated'])

    def test_legacy_final_restores_known_upstream_without_cross_request_inference(self):
        source = json.loads(SOURCE.read_text())
        old_final = json.loads((ROOT/'runs/diagnostics/basic_info_visibility_boundary_20261019_v1/final_context.json').read_text())
        item = SimpleNamespace(prediction_time=UTC, signal_rounds=(), state_deltas=(),
            stop_reason=RuntimeStopReason.NO_SIGNAL_MATCH, termination_trigger=None,
            to_dict=lambda:{'basic_info_bundle':source['bundle'], 'final_context':old_final})
        compact = _plan_critic_trajectory(item, case_index=0)
        post = _compact_posthoc_context({**old_final, 'basic_info_bundle':source['bundle']})
        for index in (compact['basic_info_source_index'],post['basic_info_source_index']):
            market = next(row for row in index if row['request_id']=='recent_market_backbone')
            self.assertIs(market['source_context_truncated'], True)
            self.assertIsNone(market['projection_context_truncated'])
            self.assertTrue(market['omitted_context_markers'])
            self.assertEqual(market['omitted_projection_count'],0)
            self.assertEqual(market['projection_status'],'partial_context_budget')
        from copy import deepcopy
        wrong = deepcopy(source['bundle'])
        for row in wrong['requests']:
            row['request']['request_id'] += '-different'
        post = _compact_posthoc_context({**old_final, 'basic_info_bundle':wrong})
        market = next(row for row in post['basic_info_source_index'] if row['request_id']=='recent_market_backbone')
        self.assertIsNone(market['source_context_truncated'])
        self.assertIsNone(market['effective_context_truncated'])
        self.assertEqual(market['omitted_context_markers'],[])

    def test_actual_critic_and_posthoc_pending_wires_keep_compact_visibility(self):
        from dataclasses import replace
        import tempfile
        from stock_opportunity_agent.llm import get_model
        from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
        from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
        from stock_opportunity_agent.research.evolution_plan_roles import LLMPlanCritic, LLMBlindPredictor
        from tests.scheme_evolution_test_support import make_trajectory, make_record
        source = json.loads(SOURCE.read_text())
        model, _ = project_basic_info_bundle(BasicInfoBundle.from_dict(source['bundle']))
        final = final_view(model)
        trajectory = replace(make_trajectory('anonymous_fixture',1.1,False,None),
            prediction_time=UTC,basic_info=source['bundle'],final_context=final)
        for stage in ('critic','posthoc'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                contract = SimpleNamespace(contract_hash='a'*64,limits={'max_local_role_calls':2,'max_structured_corrections':1})
                caller = StructuredRoleClient(registration=get_model('independent-subagent'),contract=contract,
                    workspace=root,ledger=ExternalAttemptLedger(root/'attempts.json',max_attempts=1,max_total_cost=1),
                    allow_external=False,environ={})
                with self.assertRaises(LocalRoleRequestPending) as raised:
                    if stage=='critic':
                        critic = LLMPlanCritic(caller)
                        critic.set_anonymous_aliases(('BMBL',))
                        critic.critique(plan=default_information_plan(),trajectories=(trajectory,),
                            metrics=make_record('metrics',0.5,(1.0,)).metrics)
                    else:
                        LLMBlindPredictor(caller).reflect(final,trajectory.prediction,trajectory.ground_truth)
                inbox = json.loads(Path(raised.exception.pending['inbox_path']).read_text())
                payload = json.loads(inbox['messages'][-1]['content'])
                index = (expanded_critic_index(payload) if stage=='critic'
                         else payload['compact_context']['basic_info_source_index'])
                market = next(row for row in index if row['request_id']=='recent_market_backbone')
                self.assertIs(market['source_context_truncated'],True)
                self.assertTrue(market['omitted_context_markers'])
                self.assertEqual(market['projection_status'],'partial_context_budget')
                self.assertNotIn('exact_text',json.dumps(index))
                self.assertNotIn('BMBL',json.dumps(payload))
                self.assertFalse(list((root/'local_roles/receipts').glob('*.json')))

    def test_payload_profiles_reconstruct_exact_rows_and_keep_null_false_markers_distinct(self):
        from stock_opportunity_agent.research.basic_info_visibility import pack_critic_visibility
        rows = [{'request_id':'same','source_types':['filing'],'source_context_truncated':v,
                 'projection_context_truncated':None,'effective_context_truncated':None,
                 'omitted_context_markers':markers,'projection_ids':[str(i)]}
                for i,(v,markers) in enumerate(((None,[]),(False,[]),(None,['different']),
                                               (None,[]))) ]
        rows.append({**rows[0],'request_id':'different'})
        rows.append({'request_id':'no-ids','source_context_truncated':None})
        packed,profiles = pack_critic_visibility([{'case_index':1,'basic_info_source_index':rows}])
        payload = {'trajectories':packed,'basic_info_visibility_profiles':profiles}
        self.assertEqual(expanded_critic_index(payload),rows)
        refs = [row['profile_ref'] for row in packed[0]['basic_info_source_index']]
        self.assertEqual(refs[0],refs[3])
        self.assertEqual(len(set(refs)),5)
        self.assertEqual(rows[0]['projection_ids'],['0'])


def expanded_critic_index(payload, case=0):
    """Test-side exact decoding of the presentation-only final wire."""
    profiles = payload['basic_info_visibility_profiles']
    return [{**profiles[row['profile_ref']],
             **({'projection_ids':row['projection_ids']} if 'projection_ids' in row else {})}
            for row in payload['trajectories'][case]['basic_info_source_index']]
