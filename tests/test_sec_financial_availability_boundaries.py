"""Independent PIT checks against two hash-bound retained SEC responses.

These tests establish local normalization/consumer boundaries, not source admission
or new research results. The expected dates come from retained raw rows and the
filed-plus-one-UTC-day contract, never from the normalizer under test.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest import TestCase, SkipTest

from stock_opportunity_agent.data.acquisition import SecCompanyFactsAdapter
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import RawInfoRequest
from stock_opportunity_agent.data.sources.core import DataSourceError
from stock_opportunity_agent.signal_library import _sec_facts


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "runs/diagnostics/financial_source_qualification_20261020_v1/inventory.json"
INVENTORY_SHA = "4da1faff57f64bcb1e5571d3b3b7bd4d006ad8b5ac427da59a76a5b279d63f8b"
TAG = "CashAndCashEquivalentsAtCarryingValue"
COMPANY = "cik_0001590364"
REQUEST = RawInfoRequest(
    request_id="financial-boundary", description="Reported financial facts",
    source_types=("financials",), max_documents=10,
)


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value)


class _OfflineClient:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def company_facts(self, cik):
        self.calls.append(cik)
        return copy.deepcopy(self.body)


class SecFinancialAvailabilityBoundaryTests(TestCase):
    """Exercise real acquisition, append-only storage and Signal fact parsing."""

    @classmethod
    def setUpClass(cls):
        if not INVENTORY.is_file():
            raise SkipTest("retained financial qualification inventory is absent")
        assert hashlib.sha256(INVENTORY.read_bytes()).hexdigest() == INVENTORY_SHA
        inventory = json.loads(INVENTORY.read_bytes())
        cls.cases = {row["ticker"]: row for row in inventory["cases"] if row["ticker"] in ("FTAI", "ENB")}
        cls.source_bindings = [INVENTORY]
        cls.bodies = {}
        for ticker, case in cls.cases.items():
            for kind in ("exact_cache", "original_financial"):
                binding = case[kind]["binding"]
                path = Path(binding["path"])
                if not path.is_file():
                    raise SkipTest(f"retained source is absent: {path}")
                assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
                cls.source_bindings.append(path)
            cls.bodies[ticker] = json.loads(Path(case["exact_cache"]["binding"]["path"]).read_bytes())["body"]
        rows = cls.bodies["FTAI"]["facts"]["us-gaap"][TAG]["units"]["USD"]
        # Explicit original raw-row identities, independent of normalization.
        cls.target = copy.deepcopy(rows[111])
        cls.prior = copy.deepcopy(rows[110])
        assert (cls.target["accn"], cls.target["filed"], cls.target["end"], cls.target["form"]) == (
            "0001590364-25-000023", "2025-07-31", "2025-06-30", "10-Q")
        assert (cls.prior["accn"], cls.prior["filed"], cls.prior["end"]) == (
            "0001590364-25-000011", "2025-05-05", "2025-03-31")
        cls.source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.source_bindings}
        cls.legacy = RawInfoDocument.from_dict(json.loads(Path(cls.cases["FTAI"]["original_financial"]["binding"]["path"]).read_bytes()))

    @classmethod
    def tearDownClass(cls):
        assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.source_bindings} == cls.source_hashes

    def _acquire(self, as_of, *, body=None, company=COMPANY, cik="0001590364"):
        client = _OfflineClient(self.bodies["FTAI"] if body is None else body)
        result = SecCompanyFactsAdapter(client).acquire(
            REQUEST, company_id=company, identity={"cik": cik}, as_of=as_of)
        self.assertEqual(client.calls, [cik])
        return result.documents

    def _visible_facts(self, documents, as_of):
        with tempfile.TemporaryDirectory() as temporary:
            store = RawInfoStore(root=Path(temporary), documents=documents)
            restored = RawInfoStore(root=Path(temporary))
            self.assertEqual([d.to_dict() for d in store.documents], [d.to_dict() for d in restored.documents])
            visible = tuple(restored.search(COMPANY, as_of=as_of,
                                           source_types=("financials", "sec_company_facts")))
            return visible, _sec_facts(visible, as_of)

    def _matches(self, facts, row):
        return [fact for fact in facts if (fact.tag, fact.unit, fact.filed, fact.end, fact.value) ==
                (TAG, "USD", row["filed"], row["end"], float(row["val"]))]

    def test_filing_day_midnight_excludes_same_day_facts(self):
        cutoff = _instant("2025-07-31T00:00:00+00:00")
        documents = self._acquire(cutoff)
        _, facts = self._visible_facts(documents, cutoff)
        self.assertFalse(any(f.filed == "2025-07-31" for f in facts))
        self.assertTrue(self._matches(facts, self.prior))

    def test_filing_day_last_second_still_excludes_same_day_facts(self):
        cutoff = _instant("2025-07-31T23:59:59+00:00")
        _, facts = self._visible_facts(self._acquire(cutoff), cutoff)
        self.assertFalse(any(f.filed == "2025-07-31" for f in facts))
        self.assertTrue(self._matches(facts, self.prior))

    def test_next_midnight_includes_exact_raw_fact_with_typed_lineage(self):
        cutoff = _instant("2025-08-01T00:00:00+00:00")
        documents, facts = self._visible_facts(self._acquire(cutoff), cutoff)
        matched = self._matches(facts, self.target)
        self.assertTrue(matched)
        fact = matched[0]
        payload = json.loads(fact.document.content)
        self.assertEqual(payload["schema_version"], "sec-company-facts-document-v1")
        self.assertEqual(payload["accession_number"], self.target["accn"])
        self.assertEqual(fact.document.available_at, cutoff)
        self.assertIn(fact.exact_span, fact.document.content)
        self.assertEqual(fact.start, self.target.get("start"))
        self.assertTrue(all(d.source_type == "sec_company_facts" for d in documents))
        self.assertNotIn("entityName", payload)

    def test_equivalent_offset_instants_select_identical_source_products(self):
        for representations in (("2025-08-01T00:00:00+00:00", "2025-07-31T20:00:00-04:00", "2025-08-01T14:00:00+14:00"),
                                ("2025-07-31T23:59:59+00:00", "2025-08-01T13:59:59+14:00")):
            signatures = []
            for raw in representations:
                cutoff = _instant(raw)
                documents, facts = self._visible_facts(self._acquire(cutoff), cutoff)
                signatures.append(([(d.document_id, d.content_hash, d.available_at) for d in documents],
                                   sorted((f.tag, f.unit, f.filed, f.end, f.value) for f in facts)))
            self.assertTrue(all(value == signatures[0] for value in signatures[1:]))

    def test_prior_filed_positive_retains_raw_value_and_original_period(self):
        cutoff = _instant("2025-07-31T00:00:00+00:00")
        _, facts = self._visible_facts(self._acquire(cutoff), cutoff)
        matches = self._matches(facts, self.prior)
        self.assertTrue(matches)
        self.assertEqual(matches[0].value, self.prior["val"])
        self.assertEqual(matches[0].end, "2025-03-31")

    def test_wrong_response_issuer_rejected_before_mislabeled_products(self):
        with self.assertRaises(DataSourceError):
            self._acquire(_instant("2025-08-01T00:00:00+00:00"), body=self.bodies["ENB"],
                          company="cik_0000895421", cik="0000895421")

    def test_new_ids_coexist_without_rewriting_legacy_unsafe_clock(self):
        cutoff = _instant("2025-08-01T00:00:00+00:00")
        original = self.legacy.to_dict()
        with tempfile.TemporaryDirectory() as temporary:
            store = RawInfoStore(root=Path(temporary), documents=(self.legacy,))
            self.assertFalse(store.append(RawInfoDocument.from_dict(original)))
            # A refetch with the same identity/content cannot repair the clock
            # of an append-only legacy object, even when its new clock is safer.
            retimed = replace(self.legacy, available_at=cutoff)
            self.assertFalse(store.append(retimed))
            self.assertEqual(store.load(self.legacy.document_id).to_dict(), original)
            self.assertEqual(store.load(self.legacy.document_id).available_at,
                             _instant("2025-07-31T00:00:00+00:00"))
            derived = [d for d in self._acquire(cutoff) if d.source_type != "sec_company_facts_raw_response"]
            self.assertTrue(derived)
            self.assertTrue(all(d.document_id.startswith("secfacts:0001590364:") for d in derived))
            self.assertTrue(all(d.document_id != self.legacy.document_id for d in derived))
            for document in derived:
                self.assertTrue(store.append(document))
            restored = RawInfoStore(root=Path(temporary))
            self.assertEqual(restored.load(self.legacy.document_id).to_dict(), original)
            self.assertEqual(len(restored.documents), len(derived) + 1)

    def test_signal_consumer_independently_guards_legacy_same_day_clock(self):
        original = self.legacy.to_dict()
        for cutoff in ("2025-07-31T00:00:00+00:00", "2025-07-31T23:59:59+00:00"):
            facts = _sec_facts((self.legacy,), _instant(cutoff))
            self.assertFalse(any(f.filed == "2025-07-31" for f in facts))
            self.assertTrue(self._matches(facts, self.prior))
        facts = _sec_facts((self.legacy,), _instant("2025-08-01T00:00:00+00:00"))
        self.assertTrue(self._matches(facts, self.target))
        self.assertEqual(self.legacy.to_dict(), original)
