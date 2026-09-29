"""Content-level tests for the three-layer Raw Info disclosure interface."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from stock_opportunity_agent.data.disclosure import (
    document_catalog,
    fetch_entry,
    read_provenance,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError


AS_OF = datetime(2025, 9, 30, tzinfo=timezone.utc)


def news_document(document_id: str, title: str, *, days_old: int = 1) -> RawInfoDocument:
    available = AS_OF - timedelta(days=days_old)
    return RawInfoDocument.create(
        document_id=document_id,
        company_id="issuer",
        source_type="news",
        published_at=available,
        available_at=available,
        content=json.dumps({"title": title, "summary": "Fixture body."}),
    )


def filing_document(document_id: str, content: str, *, form: str = "10-Q") -> RawInfoDocument:
    available = AS_OF - timedelta(days=3)
    return RawInfoDocument.create(
        document_id=document_id,
        company_id="issuer",
        source_type="filing",
        published_at=available,
        available_at=available,
        content=content,
        metadata={"form": form, "provider": "sec_edgar"},
    )


TEN_Q_BODY = (
    "<html><body>"
    "<h1>AXTI 10-Q</h1>"
    "<p>Item 1. Financial Statements.</p>"
    + "<p>Cash and equivalents discussion with numbered rows.</p>" * 80
    + "<p>Item 1A. Risk Factors.</p>"
    + "<p>Business risk and competition factors.</p>" * 80
    + "<p>Item 3. Legal Proceedings.</p>"
    + "<p>The shareholder class action remains in discovery.</p>" * 40
    + "</body></html>"
)


class DisclosureInterfaceTests(unittest.TestCase):
    def test_v145_catalog_cards_carry_deterministic_metadata_and_envelope(self):
        news = news_document(
            "news-sale",
            "US Ethanol Giant Faces Potential Sale After CEO Stepped Down",
        )
        filing = filing_document("filing-10q", TEN_Q_BODY, form="10-Q")
        future = news_document("news-future", "Tomorrow", days_old=-1)
        store = RawInfoStore(documents=(news, filing, future))

        catalog = document_catalog(store, company_id="issuer", as_of=AS_OF)

        self.assertEqual(catalog["counts"], {"eligible": 2, "included": 2, "omitted": 0})
        self.assertIsNone(catalog["next_cursor"])
        cards = {card["document_id"]: card for card in catalog["cards"]}
        # The future document never appears: point-in-time filtering.
        self.assertNotIn("news-future", cards)
        sale = cards["news-sale"]
        self.assertEqual(
            sale["title"],
            "US Ethanol Giant Faces Potential Sale After CEO Stepped Down",
        )
        quarterly = cards["filing-10q"]
        self.assertEqual(quarterly["form_type"], "10-Q")
        headings = [row["heading"] for row in quarterly["sections"]]
        self.assertTrue(
            any("Legal Proceedings" in heading for heading in headings),
            headings,
        )
        legal = next(
            row for row in quarterly["sections"] if "Legal" in row["heading"]
        )
        # Section offsets are raw and ordered.
        self.assertGreater(legal["raw_start"], 0)
        self.assertGreater(legal["raw_end"], legal["raw_start"])
        raw_positions = [row["raw_start"] for row in quarterly["sections"]]
        self.assertEqual(raw_positions, sorted(raw_positions))

    def test_v145_catalog_title_query_finds_buried_catalyst_headline(self):
        sale = news_document(
            "news-sale", "US Ethanol Giant Faces Potential Sale After CEO Departed"
        )
        other = news_document("news-other", "Quarterly dividend declared")
        store = RawInfoStore(documents=(sale, other))

        found = document_catalog(
            store, company_id="issuer", as_of=AS_OF, title_query="potential sale"
        )
        self.assertEqual(
            [card["document_id"] for card in found["cards"]], ["news-sale"]
        )

    def test_v145_catalog_pagination_discloses_omitted_tail(self):
        documents = tuple(
            news_document(f"news-{index:02d}", f"Fixture headline {index}")
            for index in range(8)
        )
        store = RawInfoStore(documents=documents)

        page = document_catalog(
            store, company_id="issuer", as_of=AS_OF, cursor=0, max_cards=5
        )
        self.assertEqual(page["counts"], {"eligible": 8, "included": 5, "omitted": 3})
        self.assertEqual(page["next_cursor"], 5)
        last = document_catalog(
            store, company_id="issuer", as_of=AS_OF, cursor=5, max_cards=5
        )
        self.assertEqual(last["counts"], {"eligible": 8, "included": 3, "omitted": 0})
        self.assertIsNone(last["next_cursor"])

    def test_v145_fetch_small_unit_is_verbatim_large_unit_discloses_omissions(self):
        small = news_document("news-small", "Small headline")
        big = filing_document(
            "filing-big",
            "<p>" + "Substantive operating discussion paragraph. " * 400 + "</p>",
        )
        store = RawInfoStore(documents=(small, big))

        verbatim = fetch_entry(store, "news-small", as_of=AS_OF)
        self.assertEqual(verbatim["kind"], "verbatim")
        self.assertIn("Small headline", verbatim["text"])
        self.assertEqual(verbatim["omitted_context_markers"], [])

        bounded = fetch_entry(store, "filing-big", as_of=AS_OF, budget_chars=2_000)
        self.assertEqual(bounded["kind"], "bounded")
        self.assertLess(bounded["delivered_chars"], bounded["visible_chars"])
        self.assertTrue(bounded["omitted_context_markers"])
        for marker in bounded["omitted_context_markers"]:
            self.assertNotIn("<", marker)
        # The provenance reference stays valid for exact original reads.
        provenance = read_provenance(store, bounded["reference"], as_of=AS_OF)
        self.assertIn("Substantive operating discussion", provenance["exact_text"])
        big_document = store.load("filing-big", as_of=AS_OF)
        self.assertEqual(
            provenance["exact_text"],
            big_document.content[
                provenance["raw_start"] : provenance["raw_end"]
            ],
        )

    def test_v145_fetch_by_section_returns_exact_verbatim_section(self):
        filing = filing_document("filing-10q", TEN_Q_BODY)
        store = RawInfoStore(documents=(filing,))
        catalog = document_catalog(store, company_id="issuer", as_of=AS_OF)
        legal = next(
            row
            for row in catalog["cards"][0]["sections"]
            if "Legal Proceedings" in row["heading"]
        )

        section_view = fetch_entry(
            store,
            "filing-10q",
            as_of=AS_OF,
            section_id=legal["section_id"],
            budget_chars=4_000,
        )
        self.assertEqual(section_view["kind"], "verbatim")
        self.assertIn("Legal Proceedings", section_view["text"])
        self.assertIn("class action remains in discovery", section_view["text"])
        self.assertNotIn("Risk Factors", section_view["text"])

        with self.assertRaises(ValidationError):
            fetch_entry(
                store, "filing-10q", as_of=AS_OF, section_id="sec99", budget_chars=4_000
            )

    def test_v145_provenance_rejects_hash_and_offset_mismatches(self):
        filing = filing_document("filing-10q", TEN_Q_BODY)
        store = RawInfoStore(documents=(filing,))
        good = {
            "document_id": "filing-10q",
            "content_hash": filing.content_hash,
            "raw_start": 0,
            "raw_end": 100,
        }
        provenance = read_provenance(store, good, as_of=AS_OF)
        self.assertEqual(provenance["exact_text"], filing.content[0:100])

        stale = dict(good, content_hash="0" * 64)
        with self.assertRaises(ValidationError):
            read_provenance(store, stale, as_of=AS_OF)

        bad_offsets = dict(good, raw_start=500, raw_end=100)
        with self.assertRaises(ValidationError):
            read_provenance(store, bad_offsets, as_of=AS_OF)

        future = dict(good)
        with self.assertRaises(ValidationError):
            read_provenance(store, future, as_of=AS_OF - timedelta(days=10))


if __name__ == "__main__":
    unittest.main()
