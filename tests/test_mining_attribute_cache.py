"""Attribute indexing must survive repeated actions without rescanning or inflation."""
from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from tests.scheme_evolution_test_support import NOW, RawInfoDocument, RawInfoStore, make_case
from stock_opportunity_agent.research.mining_agent_tools import project_attributes
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController


class MiningAttributeCacheTests(unittest.TestCase):
    def _controller(self, model=None):
        cases = [make_case('cache_positive', 4.0), make_case('cache_control', 1.1)]
        documents = tuple(RawInfoDocument.create(
            document_id=f'cache-news-{i}', company_id=case.company_id,
            source_type='company_news', published_at=NOW, available_at=NOW,
            content='Issuer announced a purchase agreement for $120 million.',
        ) for i, case in enumerate(cases))
        return LabelAwareMiningController(
            store=RawInfoStore(documents=documents), model=model,
            case_pairs=[(f'case-{i:03d}', case) for i, case in enumerate(cases, 1)],
            measurable_evidence_manifest={}, signal_catalog=[], seed='discovery',
            attribute_vocabulary={'attributes': [{'name': 'order_confirmation_disclosed'}]},
        )

    def _fetch(self, controller):
        controller._execute('fetch_evidence', {
            'action': 'fetch_evidence', 'rationale': ['Read both sources.'],
            'case_refs': ['case-001', 'case-002'], 'source_families': ['news'],
            'max_documents': 2,
        })

    def _coverage(self, controller):
        return controller._model_view()['evidence_digest']['attribute_case_coverage']

    def test_repeated_production_fetches_keep_hits_and_charge_each_action(self):
        controller = self._controller()
        self._fetch(controller)
        with patch('stock_opportunity_agent.research.mining_controller.project_attributes',
                   wraps=project_attributes) as scanner:
            first = controller._model_view()
            expected = first['evidence_digest']['attribute_case_coverage']
            self.assertEqual(expected['order_confirmation_disclosed']['hits'], 2)
            self.assertEqual(scanner.call_count, 2)
            ledger_before = len(controller.ledger.entries)
            self._fetch(controller)
            second = controller._model_view()
            self.assertEqual(second['evidence_digest']['attribute_case_coverage'], expected)
            self.assertEqual(scanner.call_count, 2)
            self.assertGreater(len(controller.ledger.entries), ledger_before)
            self.assertLess(second['budget']['heavy_remaining'], first['budget']['heavy_remaining'])
            self.assertEqual(second['known_event_refs'], first['known_event_refs'])
            for ref in second['known_event_refs']:
                self.assertIn(ref, controller._documents)
            expanded = [doc for result in controller._documents.values() for doc in result.documents]
            rows = project_attributes(expanded, controller._events.values(),
                                      vocabulary=controller.attribute_vocabulary)
            self.assertEqual(len(rows['order_confirmation_disclosed']), 2)

    def test_case_ownership_vocabulary_and_labels_do_not_reuse_stale_aggregates(self):
        controller = self._controller()
        self._fetch(controller)
        with patch('stock_opportunity_agent.research.mining_controller.project_attributes',
                   wraps=project_attributes) as scanner:
            self._coverage(controller)
            for ref, event in controller._events.items():
                if event.case_ref == 'case-001':
                    controller._events[ref] = replace(event, case_ref='case-002')
            row = self._coverage(controller)['order_confirmation_disclosed']
            self.assertEqual((row['positive_cases'], row['control_cases']), (0, 1))
            self.assertEqual(scanner.call_count, 3)
            controller._label_map['case-002'] = 'positive'
            row = self._coverage(controller)['order_confirmation_disclosed']
            self.assertEqual((row['positive_cases'], row['control_cases']), (1, 0))
            self.assertEqual(scanner.call_count, 3)
            original_vocabulary = deepcopy(controller.attribute_vocabulary)
            controller.attribute_vocabulary['attributes'] = []
            self.assertNotIn('attribute_case_coverage', controller._model_view()['evidence_digest'])
            controller.attribute_vocabulary = original_vocabulary
            self.assertEqual(self._coverage(controller)['order_confirmation_disclosed'], row)
            self.assertEqual(scanner.call_count, 5)

    def test_changed_document_snapshot_and_recovery_match_fresh_projection(self):
        controller = self._controller()
        self._fetch(controller)
        self._coverage(controller)
        # A new immutable snapshot, even with the same document id, is a new input.
        old = controller.store.documents[0]
        changed = RawInfoDocument.create(
            document_id=old.document_id, company_id=old.company_id,
            source_type=old.source_type, published_at=NOW, available_at=NOW,
            content='Issuer signed a supply agreement for $300 million.',
        )
        for ref, result in controller._documents.items():
            controller._documents[ref] = replace(result, documents=tuple(
                changed if doc.document_id == changed.document_id else doc
                for doc in result.documents))
        with patch('stock_opportunity_agent.research.mining_controller.project_attributes',
                   wraps=project_attributes) as scanner:
            coverage = self._coverage(controller)
            self.assertEqual(scanner.call_count, 1)
            self.assertEqual(coverage['order_confirmation_disclosed']['amount_usd_median'], 300_000_000)
            rows = controller._projected_attributes()
            self.assertEqual(scanner.call_count, 1)
            authoritative = project_attributes(
                [changed, controller.store.documents[1]], controller._events.values(),
                vocabulary=controller.attribute_vocabulary)
            self.assertEqual(rows, authoritative)
            # Cache is disposable: restart/resume recomputation gives identical view.
            controller._attribute_rows.clear()
            self.assertEqual(self._coverage(controller), coverage)
            self.assertEqual(scanner.call_count, 3)
