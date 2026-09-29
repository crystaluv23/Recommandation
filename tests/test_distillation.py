"""Content-level tests for the Raw Info distillation subagent."""

import unittest
from datetime import datetime, timedelta, timezone

from tests.evolution_runtime_test_support import *  # noqa: F403

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.distillation import (
    RawInfoDistiller,
    quoted_fact_refs,
)


AS_OF = datetime(2025, 9, 30, tzinfo=timezone.utc)

DOCUMENT_BODY = (
    "AXT, Inc. Announces Receipt of Export Permits. The subsidiary was "
    "informed that it has satisfied the applicable requirements for a "
    "permit to export indium phosphide and has received export permits "
    "from the Ministry of Commerce to resume shipping indium phosphide "
    "substrates to certain additional customers. The company believes "
    "this will result in several million dollars in revenue that was not "
    "included in prior quarterly guidance."
)


def fixture_store() -> RawInfoStore:
    document = RawInfoDocument.create(
        document_id="news-export-permit",
        company_id="issuer",
        source_type="news",
        published_at=AS_OF - timedelta(days=1),
        available_at=AS_OF - timedelta(days=1),
        content=DOCUMENT_BODY,
    )
    return RawInfoStore(documents=(document,))


GOOD_CARD = {
    "event_summary": (
        "The issuer's subsidiary received export permits to resume "
        "indium phosphide shipments; management expects revenue of "
        "several million dollars beyond prior guidance."
    ),
    "quantified_facts": [
        {
            "quote": (
                "received export permits from the Ministry of Commerce to "
                "resume shipping indium phosphide substrates to certain "
                "additional customers"
            )
        },
        {
            "quote": (
                "several million dollars in revenue that was not included "
                "in prior quarterly guidance"
            )
        },
    ],
    "source_character": "issuer_disclosure",
    "limitations": ["Single-source news summary."],
}


class RawInfoDistillerTests(TestCase):
    def reference(self, store: RawInfoStore) -> dict:
        document = store.load("news-export-permit", as_of=AS_OF)
        return {
            "document_id": document.document_id,
            "content_hash": document.content_hash,
            "raw_start": 0,
            "raw_end": len(document.content),
        }

    def test_v145_good_card_persists_with_located_quote_offsets(self):
        store = fixture_store()
        caller = ScriptedRoleCaller([GOOD_CARD])
        step = RawInfoDistiller(caller).distill(
            store, self.reference(store), as_of=AS_OF, focus="export permits"
        )
        card = step.value
        self.assertEqual(card["schema_version"], "raw-info-distillation-card-v1")
        self.assertEqual(card["source_character"], "issuer_disclosure")
        self.assertEqual(len(card["quantified_facts"]), 2)
        for fact in card["quantified_facts"]:
            self.assertEqual(
                DOCUMENT_BODY[fact["raw_start"] : fact["raw_end"]],
                fact["quote"],
                "runtime-located offsets must reproduce the quote exactly",
            )
        self.assertTrue(quoted_fact_refs(card))
        # The complete original entered the subagent context verbatim.
        payload = caller.calls[0]["payload"]
        self.assertEqual(payload["document_text"], DOCUMENT_BODY)
        self.assertEqual(payload["focus"], "export permits")

    def test_v145_non_verbatim_quote_is_corrected_then_rejected(self):
        store = fixture_store()
        bad = dict(GOOD_CARD)
        bad = {
            **GOOD_CARD,
            "quantified_facts": [
                {"quote": "received export licenses from the Commerce Ministry"}
            ],
        }
        caller = ScriptedRoleCaller([bad, GOOD_CARD])
        step = RawInfoDistiller(caller).distill(
            store, self.reference(store), as_of=AS_OF
        )
        self.assertEqual(len(card_facts(step.value)), 2)
        correction_payload = caller.calls[1]["payload"]
        self.assertIn(
            "verbatim substring", correction_payload["validation_error"]
        )

        exhausted = ScriptedRoleCaller([bad, bad])
        with self.assertRaises(Exception) as caught:
            RawInfoDistiller(exhausted).distill(
                store, self.reference(store), as_of=AS_OF
            )
        self.assertIn("distillation", str(caught.exception))

    def test_v145_summary_numbers_must_come_from_quotes(self):
        store = fixture_store()
        derived = {
            **GOOD_CARD,
            "event_summary": (
                "Management expects about 25 million dollars of new revenue."
            ),
        }
        caller = ScriptedRoleCaller([derived, GOOD_CARD])
        step = RawInfoDistiller(caller).distill(
            store, self.reference(store), as_of=AS_OF
        )
        self.assertEqual(
            step.value["event_summary"], GOOD_CARD["event_summary"]
        )
        correction_payload = caller.calls[1]["payload"]
        self.assertIn(
            "restates numbers absent", correction_payload["validation_error"]
        )

    def test_v145_reference_hash_and_future_cutoff_fail_closed(self):
        store = fixture_store()
        document = store.load("news-export-permit", as_of=AS_OF)
        stale = {
            "document_id": document.document_id,
            "content_hash": "0" * 64,
        }
        with self.assertRaises(ValidationError):
            RawInfoDistiller(ScriptedRoleCaller([])).distill(
                store, stale, as_of=AS_OF
            )
        future = {
            "document_id": document.document_id,
            "content_hash": document.content_hash,
        }
        with self.assertRaises(ValidationError):
            RawInfoDistiller(ScriptedRoleCaller([])).distill(
                store, future, as_of=AS_OF - timedelta(days=5)
            )


def card_facts(card: dict) -> list:
    return card["quantified_facts"]


if __name__ == "__main__":
    unittest.main()
