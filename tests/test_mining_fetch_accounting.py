"""Fetch receipts retain whole-action coverage and distinguish new graph nodes."""

from datetime import timedelta
import unittest

from tests.scheme_evolution_test_support import NOW, RawInfoDocument, RawInfoStore
from tests.test_mining_controller import _controller, _fixture_store


def _narrative_fixture():
    cases, store = _fixture_store()
    documents = list(store.documents)
    for document_id, case_index, content, available_at in (
        ("expansion-a", 0, "Expansion plans continue.", NOW),
        ("expansion-b", 0, "Expansion orders are disclosed.", NOW),
        ("margin-a", 1, "Margin improvements are disclosed.", NOW),
        ("future-margin", 0, "Margin improvements followed.", NOW + timedelta(days=1)),
    ):
        documents.append(RawInfoDocument.create(
            document_id=document_id,
            company_id=cases[case_index].company_id,
            source_type="news",
            published_at=available_at,
            available_at=available_at,
            content=content,
        ))
    return cases, RawInfoStore(documents=tuple(documents))


def _fetch(refs, *, families=None, query="expansion margin", limit=1):
    return {
        "action": "fetch_evidence",
        "case_refs": refs,
        "source_families": families or ["news"],
        "query": query,
        "max_documents": limit,
    }


class MiningFetchAccountingTests(unittest.TestCase):
    def test_whole_action_coverage_is_order_independent_and_pit_bound(self):
        cases, store = _narrative_fixture()
        receipts = []
        for refs in (["case-001", "case-002"], ["case-002", "case-001"]):
            controller = _controller(store, cases, None, seed="discovery")
            controller._execute_fetch(_fetch(refs))
            entry = controller.ledger.entries[-1]
            self.assertEqual(entry.coverage["query_coverage"], {
                "matched_terms": ["expansion", "margin"], "sufficient": True,
            })
            self.assertTrue(entry.coverage["unread_same_source"])
            self.assertEqual(entry.omitted_coverage["excluded_document_ids"], ["expansion-b"])
            self.assertNotIn("document-future-margin", controller._documents)
            self.assertEqual(controller._model_view()["last_action_result"]["excluded_document_ids"], 1)
            receipts.append((entry.coverage, entry.omitted_coverage, set(entry.evidence_refs)))
        self.assertEqual(receipts[0], receipts[1])

    def test_one_unmatched_case_cannot_be_hidden_by_the_final_case(self):
        cases, store = _narrative_fixture()
        for refs in (["case-001", "case-002"], ["case-002", "case-001"]):
            controller = _controller(store, cases, None, seed="discovery")
            controller._execute_fetch(_fetch(refs, query="expansion", limit=10))
            entry = controller.ledger.entries[-1]
            self.assertEqual(entry.coverage["query_coverage"], {
                "matched_terms": ["expansion"], "sufficient": False,
            })
            self.assertFalse(entry.coverage["unread_same_source"])
            self.assertEqual(entry.omitted_coverage["excluded_document_ids"], [])

    def test_narrative_events_are_not_new_numeric_facts(self):
        cases, store = _narrative_fixture()
        controller = _controller(store, cases, None, seed="discovery")
        controller._execute_fetch(_fetch(["case-001", "case-002"], limit=10))
        receipt = controller._model_view()["last_action_result"]
        self.assertEqual(receipt["total_events"], 3)
        self.assertEqual(receipt["new_facts"], 0)
        self.assertEqual(receipt["total_facts"], 0)
        self.assertEqual(receipt["new_relations"], 0)
        self.assertEqual(len(controller.ledger.entries[-1].evidence_refs), 3)

    def test_repeated_fetch_preserves_evidence_and_cost_without_false_novelty(self):
        cases, store = _narrative_fixture()
        controller = _controller(store, cases, None, seed="discovery")
        action = _fetch(["case-001", "case-002"], families=["news", "company_facts"], query=None, limit=10)
        controller._execute_fetch(action)
        first = controller._model_view()
        self.assertGreater(first["last_action_result"]["new_facts"], 0)
        self.assertEqual(first["last_action_result"]["new_facts"], len(first["known_fact_refs"]))
        self.assertGreater(first["last_action_result"]["new_relations"], 0)
        controller._execute_fetch(action)
        repeated = controller._model_view()
        for field in ("known_fact_refs", "known_event_refs", "known_relation_refs"):
            self.assertEqual(first[field], repeated[field])
        self.assertEqual(repeated["last_action_result"]["new_facts"], 0)
        self.assertEqual(repeated["last_action_result"]["new_relations"], 0)
        self.assertEqual(repeated["last_action_result"]["total_events"], 3)
        self.assertEqual(controller.ledger.fetch_count(), 2)
        self.assertEqual(controller._heavy_used, 2)
        self.assertEqual(controller.ledger.entries[0].evidence_refs, controller.ledger.entries[1].evidence_refs)


if __name__ == "__main__":
    unittest.main()
