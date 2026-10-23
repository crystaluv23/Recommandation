"""Exact query selection origins reach charged reads without evidence authority."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research import evolution_core as core
from stock_opportunity_agent.research.mining_agent_tools import fetch_case_evidence
from stock_opportunity_agent.research.mining_controller import InvalidMiningAction
from stock_opportunity_agent.research.stage_contracts import json_bytes
from tests.scheme_evolution_test_support import make_case, NOW
from tests.test_mining_controller import _controller

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'runs/diagnostics/mining_query_navigation_20261023_v1'


def document(content, *, kind='filing', title='', number='source', company=None):
    """Build a source-only fixture with explicit clocks and no outcome records."""
    return RawInfoDocument.create(document_id=number, company_id=company or make_case('nav', 1.1).company_id,
        source_type=kind, published_at=NOW, available_at=NOW, content=content, metadata={'title': title})


def legacy():
    """Use exact pre-repair shared helpers as the behavior-preservation control."""
    namespace = dict(vars(core))
    exec(compile((BASE / 'prior-shared-selection.py.txt').read_text(), 'frozen-previous-selection', 'exec'), namespace)
    return namespace['_query_relevant_excerpt']


class MiningQueryNavigationTests(TestCase):
    def origins(self, doc, query='controls procedures', limit=600):
        excerpt, clipped, result = core._query_relevant_excerpt_with_origins(doc, query=query, max_chars=limit)
        self.assertEqual((excerpt, clipped), legacy()(doc, query=query, max_chars=limit))
        self.assertEqual((excerpt, clipped), core._query_relevant_excerpt(doc, query=query, max_chars=limit))
        for row in result['fragments']:
            self.assertTrue(0 <= row['raw_start'] < row['raw_end'] <= len(doc.content))
            self.assertLessEqual(row['raw_end'] - row['raw_start'], 4000)
            self.assertTrue(row['projection_start'] < row['projection_end'])
        return result

    def controller(self, docs):
        case = make_case('nav', 1.1)
        return _controller(RawInfoStore(documents=docs), [case], object(), seed='discovery',
            heavy_action_limit=40, browse_limit=40, light_action_limit=20)

    def fetch(self, controller, query='controls procedures', maximum=20):
        controller._execute_fetch({'action': 'fetch_evidence', 'case_refs': ['case-001'],
            'source_families': list(controller.available_source_families), 'max_documents': maximum,
            'query': query, 'rationale': ['Locate actual source text.']})

    def test_legacy_excerpt_and_clipped_unchanged_across_formats_and_query_branches(self):
        bodies = ['<script>controls procedures</script><p>Visible controls procedures.</p>',
            'header ' * 200 + ' internal control financial reporting material weakness ' + 'body ' * 200,
            json.dumps({'title': 'title', 'summary': 'summary', 'body': '<b>controls</b> &amp; procedures'}),
            '{"body":"old", "\\u0062ody":"controls procedures"}',
            '{"body":12,"summary":["controls", "procedures"]}',
            '{"body":"controls procedures"} trailing', '["controls procedures"]',
            '{"date":"2024-01-01","value":1} ' * 30, 'x' * 1000, '<p></p>']
        for body in bodies:
            for kind in ('filing', 'company_news', 'earnings_call'):
                for query in (None, '', 'controls procedures', 'unmatched-token'):
                    for size in (30, 600):
                        with self.subTest(body=body[:25], kind=kind, query=query, size=size):
                            self.origins(document(body, kind=kind, title='metadata controls'), query, size)

    def test_metadata_and_hidden_repetitions_do_not_reanchor_selected_body(self):
        body = '<script>' + 'controls procedures ' * 500 + '</script><p>BODY controls procedures.</p>'
        doc = document(body, title='controls procedures')
        result = self.origins(doc)
        self.assertGreater(result['unmapped_nonspace_chars'], 0)
        self.assertEqual(len(result['fragments']), 1)
        self.assertEqual(body[result['fragments'][0]['raw_start']:result['fragments'][0]['raw_end']],
                         'BODY controls procedures.')
        hidden = self.origins(document('<script>controls procedures</script>'))
        self.assertFalse(hidden['fragments'])

    def test_large_hidden_gap_synthetic_space_and_dense_entities_are_not_read_anchors(self):
        body = '<p>controls</p><script>' + 'x' * 20000 + '</script><p>procedures</p>'
        result = self.origins(document(body))
        self.assertEqual(len(result['fragments']), 2)
        self.assertEqual([body[r['raw_start']:r['raw_end']] for r in result['fragments']], ['controls', 'procedures'])
        self.assertTrue(all(body[r['raw_start']] != '<' for r in result['fragments']))
        escaped = document('{"body":"' + '\\ud834\\udd1e' * 590 + ' controls procedures"}', kind='company_news')
        result = self.origins(escaped)
        self.assertGreaterEqual(len(result['fragments']), 2)

    def test_news_reverse_fields_duplicate_keys_nested_decoys_and_escapes(self):
        body = ('{"body":"WRONG controls procedures","nested":{"body":"DECOY"},'
                '"\\u0062ody":"BODY \\ud834\\udd1e \\u2003 controls \\"quote\\" \\\\u0041 procedures",'
                '"title":"TITLE controls procedures"}')
        doc = document(body, kind='company_news')
        result = self.origins(doc)
        fragments = [body[r['raw_start']:r['raw_end']] for r in result['fragments']]
        self.assertEqual(len(fragments), 2)
        self.assertTrue(fragments[0].startswith('TITLE'))
        self.assertTrue(fragments[1].startswith('BODY'))
        self.assertNotIn('WRONG', ''.join(fragments))
        self.assertNotIn('DECOY', ''.join(fragments))
        self.assertGreater(result['fragments'][0]['raw_start'], result['fragments'][1]['raw_start'])
        self.assertTrue(result['mapping_complete'])
        nonstring = self.origins(document('{"body":{"fact_ref":"controls procedures"}}', kind='company_news'))
        self.assertFalse(nonstring['fragments'])
        self.assertGreater(nonstring['unmapped_nonspace_chars'], 0)

    def test_fetch_hints_persist_across_actions_with_no_reads_or_materialization(self):
        doc = document('<p>Our controls procedures are described here.</p>')
        controller = self.controller([doc]); self.fetch(controller)
        before = deepcopy(controller.ledger.to_dict())
        page = controller._model_view()['query_navigation']; row = page['items'][0]
        self.assertEqual(controller._heavy_used, 1)
        self.assertEqual(controller._narrative_reads, 0)
        self.assertEqual(controller.materialization_evidence(), {})
        self.assertTrue(row['source_snapshot_matches'])
        self.assertTrue(row['discovery_only'])
        self.assertFalse(row['source_read_completed'])
        self.assertFalse(row['candidate_citable'])
        self.assertNotIn(row['navigation_ref'], controller.ledger.evidence_refs())
        controller._execute('inspect_manifest', {'action': 'inspect_manifest', 'rationale': ['Inspect contract.']})
        self.assertEqual(controller._model_view()['query_navigation']['items'], page['items'])
        raw = doc.content[row['raw_start']:row['raw_end']]
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), row['raw_span_sha256'])
        controller._execute_read_span({'action': 'read_span', 'document_ref': row['document_ref'],
            'offset': row['raw_start'], 'length': row['read_length'], 'rationale': ['Read actual selected source.']})
        self.assertEqual(controller._browse_used, 1)
        self.assertEqual(controller._narrative_reads, 1)
        self.assertIn(row['document_ref'], controller.materialization_evidence())
        self.assertEqual(controller._model_view()['query_navigation']['items'], page['items'])
        self.assertEqual(controller.ledger.to_dict()['entries'][:1], before['entries'])

    def test_hint_does_not_satisfy_citation_gate_and_case_event_reads_stay_scoped(self):
        doc = document('controls procedures remain under review')
        case = make_case('nav', 1.1)
        other = SimpleNamespace(case_id='same-owner-second', company_id=case.company_id,
            prediction_time=case.prediction_time, ground_truth=case.ground_truth)
        controller = _controller(RawInfoStore(documents=[doc]), [case, other], object(), seed='discovery')
        controller._execute_fetch({'action': 'fetch_evidence', 'case_refs': ['case-001', 'case-002'],
            'source_families': ['filing'], 'max_documents': 1, 'query': 'controls procedures',
            'rationale': ['Find source coordinates for both scoped cases.']})
        rows = controller._model_view()['query_navigation']['items']
        self.assertEqual({r['case_ref'] for r in rows}, {'case-001', 'case-002'})
        events = {event.case_ref: ref for ref, event in controller._events.items()}
        predicate = {'modality': 'narrative', 'source_families': ['filing'], 'semantic_condition': 'Controls assessment.'}
        for event in events.values():
            with self.assertRaisesRegex(InvalidMiningAction, 'executed readable window'):
                controller._validate_narrative_predicate(predicate, {event})
        row = rows[0]
        controller._execute_read_span({'action': 'read_span', 'event_ref': events[row['case_ref']],
            'offset': row['raw_start'], 'length': row['read_length'], 'rationale': ['Read one case-scoped event.']})
        controller._validate_narrative_predicate(predicate, {events[row['case_ref']]})
        untouched = next(ref for case_ref, ref in events.items() if case_ref != row['case_ref'])
        with self.assertRaisesRegex(InvalidMiningAction, 'executed readable window'):
            controller._validate_narrative_predicate(predicate, {untouched})

    def test_changed_current_document_binding_marks_historical_navigation(self):
        doc = document('controls procedures old source')
        controller = self.controller([doc]); self.fetch(controller)
        original = deepcopy(controller._model_view()['query_navigation']['items'])
        replacement = document('controls procedures new source', number=doc.document_id)
        # Replace only the fixture resolver bindings. Historical originals and
        # ledger snapshots stay byte-identical, while a current read differs.
        old_result = next(iter(controller._documents.values()))
        controller._documents = {'document-' + doc.document_id: replace(old_result, documents=(replacement,))}
        rows = controller._model_view()['query_navigation']['items']
        self.assertFalse(rows[0]['source_snapshot_matches'])
        self.assertEqual(rows[0]['content_hash'], original[0]['content_hash'])
        self.assertEqual(rows[0]['raw_span_sha256'], original[0]['raw_span_sha256'])

    def test_empty_queries_noquery_payload_and_canonical_events_are_unchanged(self):
        doc = document('controls procedures ' * 50)
        case = make_case('nav', 1.1); store = RawInfoStore(documents=[doc])
        for query in (None, '', '   '):
            result = fetch_case_evidence(store, case, source_families=['filing'], max_documents=1, query=query)
            self.assertFalse(result.query_navigation)
        normal = fetch_case_evidence(store, case, source_families=['filing'], max_documents=1, query='controls')
        self.assertEqual(normal.narrative_events[0].excerpt, legacy()(doc, query='controls', max_chars=600)[0])
        controller = self.controller([doc]); self.fetch(controller, None)
        self.assertNotIn('query_navigation', controller._model_view())

    def test_wrong_owner_future_sources_and_future_published_clock_have_no_coordinates(self):
        case = make_case('nav', 1.1)
        wrong = document('controls procedures', company='foreign')
        future = replace(document('controls procedures', number='future'), available_at=case.prediction_time + timedelta(days=1))
        with self.assertRaises(ValidationError):
            replace(document('controls procedures', number='bad-clock'), published_at=case.prediction_time + timedelta(days=1))
        result = fetch_case_evidence(RawInfoStore(documents=[wrong, future]), case,
            source_families=['filing'], max_documents=3, query='controls')
        self.assertFalse(result.documents)
        self.assertFalse(result.query_navigation)

    def test_repeated_fetch_deduplicates_queries_do_not_overwrite_and_whole_page_omits(self):
        docs = [document('controls procedures liquidity ' + str(i), number=f'doc-{i}') for i in range(20)]
        controller = self.controller(docs); self.fetch(controller)
        first = controller._model_view()['query_navigation']
        self.assertEqual(first['counts']['available'], 20)
        self.assertLessEqual(len(first['items']), 12)
        self.assertLessEqual(json_bytes(first['items']), 8000)
        self.assertFalse(first['selection_is_exhaustive'])
        self.fetch(controller)
        self.assertEqual(controller._model_view()['query_navigation']['counts']['available'], 20)
        self.fetch(controller, 'liquidity')
        self.assertEqual(controller._model_view()['query_navigation']['counts']['available'], 40)
        self.assertEqual(controller._heavy_used, 3)
        self.assertEqual(controller._narrative_reads, 0)

    def test_actual_annual_quarter_query_origins_and_old_toc_misanchor_remain_distinct(self):
        for number in (1506, 1507):
            doc = RawInfoDocument.from_dict(json.loads((ROOT / f'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/{number}.json').read_text()))
            for query in ('internal control financial reporting material weakness', 'controls procedures'):
                with self.subTest(number=number, query=query):
                    result = self.origins(doc, query)
                    self.assertTrue(result['fragments'])
                    self.assertTrue(result['mapping_complete'])
                    if number == 1507 and query == 'controls procedures':
                        # Exact TOC origin is retained; never relocate repeated
                        # opening words to a later, semantically different body.
                        self.assertLess(result['fragments'][0]['raw_start'], 300000)
