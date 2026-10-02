"""Exercise whole Signal reads and case-scoped source views at production tools."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.scheme_evolution_test_support import (
    NOW, SEED_CATALOG, RawInfoDocument, RawInfoStore, SignalRegistry, make_case,
)
from tests.test_mining_controller import FACTS_CONTENT
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import _opaque_slow_case_ref
from stock_opportunity_agent.research.mining_agent_tools import fetch_case_evidence, project_attributes
from stock_opportunity_agent.research.mining_controller import InvalidMiningAction, LabelAwareMiningController
from stock_opportunity_agent.research.stage_contracts import json_bytes, read_whole_entries, validate_stage_input


def controller(cases=(), store=None, **kwargs):
    """Construct the actual tool controller with an empty default catalog."""
    return LabelAwareMiningController(
        store=store or RawInfoStore(documents=()), model=None,
        case_pairs=[(f'case-{i:03d}', case) for i, case in enumerate(cases, 1)],
        measurable_evidence_manifest={}, signal_catalog=kwargs.pop('signal_catalog', []),
        seed='hypothesis', **kwargs,
    )


class MiningContextProvenanceTests(unittest.TestCase):
    def test_registry_original_read_matches_exact_version_without_source_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory)); registry.install_catalog(SEED_CATALOG)
            ref = 'revenue_growth_yoy:v1'
            bundle = {'spec': registry.load_spec(ref).to_dict(), 'skill': registry.load_skill(ref)}
            bundle['spec']['definition']['description'] += ' IssuerPrivateName'
            before = deepcopy(bundle)
            tool = controller(signal_catalog=[{'signal_ref': ref, 'description': 'old brief'}],
                              signal_originals={ref: bundle}, identity_aliases=('IssuerPrivateName',))
            view = tool._model_view()
            validate_stage_input('mining_controller_step', view, allow_outcomes=True)
            for key in ('case_refs', 'case_prediction_times', 'signal_catalog_disclosure', 'tool_contracts'):
                incomplete = dict(view); incomplete.pop(key)
                with self.assertRaisesRegex(ValidationError, 'dependency missing'):
                    validate_stage_input('mining_controller_step', incomplete, allow_outcomes=True)
            card = view['signal_catalog'][0]
            self.assertTrue(card['original_available'])
            self.assertEqual(card['source_hash'], canonical_json_hash(before))
            self.assertEqual(card['capability_contract']['raw_retrieval'], before['spec']['raw_retrieval'])
            self.assertNotIn('IssuerPrivateName', str(card))
            tool._execute('inspect_catalog', {'action': 'inspect_catalog', 'scope': 'signals',
                'item_refs': [ref, ref], 'rationale': ['Read exact extraction rules.']})
            read = tool._model_view()['last_action_result']['result']
            self.assertEqual(read['included_refs'], [ref])
            self.assertEqual(read['read_bytes'], json_bytes(read['items']))
            item = read['items'][0]
            self.assertEqual(item['source_hash'], canonical_json_hash(before))
            self.assertEqual(item['content']['spec']['raw_retrieval'], before['spec']['raw_retrieval'])
            self.assertNotIn('IssuerPrivateName', str(item))
            self.assertEqual(tool._light_used, 1)
            self.assertEqual(bundle, before)
            self.assertNotIn('IssuerPrivateName', registry.load_spec(ref).description)
            with self.assertRaises(InvalidMiningAction):
                tool._signal_view(item_refs=['revenue_growth_yoy:v999'])
            tool._signal_originals[ref]['spec']['parameters']['positive_min'] = 0.99
            with self.assertRaisesRegex(InvalidMiningAction, 'snapshot changed'):
                tool._signal_view(item_refs=[ref])

    def test_whole_entry_limit_and_oversized_catalog_handle_are_explicit(self):
        original = {'spec': {'signal_id': 'large', 'version': 1,
                            'definition': {'description': 'x' * 17_000}}, 'skill': None}
        tool = controller(signal_catalog=[{'signal_ref': 'large:v1'}], signal_originals={'large:v1': original})
        page = tool._signal_view()
        self.assertEqual(page['items'], [])
        self.assertEqual(page['oversized_entries'][0]['signal_ref'], 'large:v1')
        with self.assertRaises(InvalidMiningAction):
            tool._signal_view(item_refs=['large:v1'])
        entries = {'a': {'text': 'alpha'}, 'b': {'text': 'beta'}}
        selected = read_whole_entries(entries, ['a', 'a'], max_bytes=100)
        self.assertEqual(selected['included_refs'], ['a'])
        self.assertEqual(selected['read_bytes'], json_bytes([entries['a']]))
        selected['items'][0]['text'] = 'changed'
        self.assertEqual(entries['a']['text'], 'alpha')
        for refs in ([], ['missing'], 'a', [False]):
            with self.assertRaises(ValidationError):
                read_whole_entries(entries, refs, max_bytes=100)
        with self.assertRaises(ValidationError):
            read_whole_entries(entries, ['a', 'b'], max_bytes=10)

    def test_need_origin_relation_and_prediction_times_survive_bounded_cards(self):
        case = make_case('source_case', 4.0)
        refs = [_opaque_slow_case_ref(case.case_id), 'case-outside']
        needs = [
            {'need_ref': 'overlap', 'need': 'actual versus forecast', 'sources': [
                {'source_case_ref': refs[0], 'source_prediction_time': case.prediction_time.isoformat()}]},
            {'need_ref': 'outside', 'need': 'future commitments', 'sources': [
                {'source_case_ref': refs[1], 'source_prediction_time': '2024-01-01T00:00:00+00:00'}]},
            {'need_ref': 'unknown', 'need': 'missing source'},
            {'need_ref': 'mixed', 'need': 'compound need', 'sources': [
                {'source_case_ref': refs[0]}, {'source_case_ref': refs[1]}, {}]},
        ]
        tool = controller([case], backlog_needs=needs)
        view = tool._model_view()
        cards = {row['need_ref']: row for row in view['backlog_needs']}
        self.assertEqual(cards['overlap']['source_scope']['relation'], 'overlapping')
        self.assertEqual(cards['overlap']['source_scope']['current_dev_case_refs'], ['case-001'])
        self.assertEqual(cards['outside']['source_scope']['relation'], 'outside_current_dev')
        self.assertEqual(cards['unknown']['source_scope']['relation'], 'unknown')
        self.assertEqual(cards['mixed']['source_scope']['relation'], 'mixed')
        self.assertEqual(cards['mixed']['source_scope']['unknown_source_count'], 1)
        self.assertEqual(cards['mixed']['source_scope']['unknown_source_time_count'], 3)
        self.assertEqual(view['case_prediction_times'], {'case-001': case.prediction_time.isoformat()})
        self.assertNotIn(case.case_id, str(view))
        self.assertEqual(tool._backlog_view(item_refs=['outside'])['items'], [needs[1]])
        row = {'sources': [{'source_case_ref': refs[1], 'source_prediction_time': str(i)} for i in range(6)]}
        self.assertEqual(tool._need_source_scope(row)['omitted_prediction_times'], 2)

    def test_shared_issuer_multiple_cutoffs_retain_facts_events_reads_and_pit(self):
        early = make_case('early_cutoff', 1.1)
        late = replace(early, case_id='late_cutoff', prediction_time=early.prediction_time + timedelta(days=30))
        shared = RawInfoDocument.create(document_id='shared-news', company_id=early.company_id,
            source_type='company_news', published_at=NOW, available_at=NOW,
            content='Issuer announced a purchase agreement for $120 million.')
        later = RawInfoDocument.create(document_id='later-news', company_id=early.company_id,
            source_type='company_news', published_at=NOW + timedelta(days=15), available_at=NOW + timedelta(days=15),
            content='Issuer signed a supply agreement for $300 million.')
        facts = RawInfoDocument.create(document_id='shared-facts', company_id=early.company_id,
            source_type='company_facts', published_at=NOW, available_at=NOW, content=FACTS_CONTENT)
        store = RawInfoStore(documents=(shared, later, facts))
        original_documents = store.documents
        tool = controller([early, late], store, attribute_vocabulary={
            'attributes': [{'name': 'order_confirmation_disclosed'}]},
            label_map={'case-001': 'control', 'case-002': 'positive'})
        tool._execute('fetch_evidence', {'action': 'fetch_evidence', 'case_refs': ['case-001', 'case-002'],
            'source_families': ['news', 'financial'], 'max_documents': 3, 'rationale': ['Read eligible sources.']})
        case1 = {f.fact_ref for f in tool._facts.values() if f.case_ref == 'case-001'}
        case2 = {f.fact_ref for f in tool._facts.values() if f.case_ref == 'case-002'}
        self.assertTrue(case1 and case2)
        self.assertTrue(case1.isdisjoint(case2))
        for refs in (case1, case2):
            ref = next(iter(refs)); fact = tool._facts[ref]
            tool._execute('read_span', {'action': 'read_span', 'fact_ref': ref,
                'rationale': ['Read the selected case observation.']})
            self.assertEqual(tool._last_action_result['case_refs'], [fact.case_ref])
            self.assertEqual(tool._last_action_result['content_hash'], facts.content_hash)
            self.assertEqual(tool._last_action_result['document_ref'], 'document-shared-facts')
            self.assertEqual(tool.ledger.entries[-1].case_refs, (fact.case_ref,))
        events = [e for e in tool._events.values() if e.document_ref == 'document-shared-news']
        self.assertEqual({e.case_ref for e in events}, {'case-001', 'case-002'})
        self.assertEqual(len({e.event_ref for e in events}), 2)
        self.assertEqual({e.case_ref for e in tool._events.values() if e.document_ref == 'document-later-news'}, {'case-002'})
        catalog = tool._evidence_catalog_view()
        self.assertIn('case_bindings', str(catalog))
        for event in events:
            self.assertIn(event.event_ref, str(catalog))
            tool._execute('read_span', {'action': 'read_span', 'event_ref': event.event_ref,
                'length': 100, 'rationale': ['Read exact source.']})
            self.assertEqual(tool._last_action_result['case_refs'], [event.case_ref])
            self.assertEqual(tool.ledger.entries[-1].case_refs, (event.case_ref,))
        receipt = next(iter(tool._read_progress.values()))
        self.assertEqual(receipt['case_refs'], ['case-001', 'case-002'])
        tool._execute('read_span', {'action': 'read_span', 'document_ref': 'document-shared-news',
            'length': 100, 'rationale': ['Read the shared source.']})
        self.assertEqual(tool._last_action_result['case_refs'], ['case-001', 'case-002'])
        with patch('stock_opportunity_agent.research.mining_controller.project_attributes', wraps=project_attributes) as scan:
            digest = tool._model_view()['evidence_digest']['attribute_case_coverage']
            self.assertEqual(digest['order_confirmation_disclosed']['hits'], 3)
            self.assertEqual(scan.call_count, 3)
            self.assertEqual(tool._model_view()['evidence_digest']['attribute_case_coverage'], digest)
            self.assertEqual(scan.call_count, 3)
        tool._attribute_rows.clear()
        self.assertEqual(tool._model_view()['evidence_digest']['attribute_case_coverage'], digest)
        self.assertEqual(store.documents, original_documents)

    def test_event_identity_is_independent_of_query_excerpt(self):
        case = make_case('query_stability', 4.0)
        content = 'Introductory text. ' * 60 + 'Issuer announced a purchase agreement for $120 million.'
        doc = RawInfoDocument.create(document_id='query-doc', company_id=case.company_id,
            source_type='company_news', published_at=NOW, available_at=NOW, content=content)
        store = RawInfoStore(documents=(doc,))
        first = fetch_case_evidence(store, case, source_families=['news'], max_documents=1, case_ref='case-001')
        queried = fetch_case_evidence(store, case, source_families=['news'], query='purchase agreement',
                                      max_documents=1, case_ref='case-001')
        self.assertNotEqual(first.narrative_events[0].exact_span, queried.narrative_events[0].exact_span)
        self.assertEqual(first.narrative_events[0].event_ref, queried.narrative_events[0].event_ref)
