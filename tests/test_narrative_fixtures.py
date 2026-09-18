"""Narrative fixture family (action plan v2, Phase 5, offline half).

Eight fixed content classes from the plan — confirmed order, mere proposal,
cancellation, below-threshold, paraphrase, lookalike, post-cutoff, and
evidence-insufficient — exercised deterministically through the controller
interface (fetch projection, read_span, predicate grounding). The
materialization-executed variants of these fixtures are authored by the
materializer per its prompt and validated in the shadow phase.
"""

import json
import unittest

from tests.scheme_evolution_test_support import (  # noqa: F403
    NOW,
    RawInfoDocument,
    RawInfoStore,
    make_case,
)

from stock_opportunity_agent.research.mining_agent_tools import (
    fetch_case_evidence,
)
from stock_opportunity_agent.research.mining_controller import (
    LabelAwareMiningController,
)


def _news_doc(doc_id, company_id, summary, *, available_at=None):
    return RawInfoDocument.create(
        document_id=doc_id,
        company_id=company_id,
        source_type="company_news",
        published_at=available_at or NOW,
        available_at=available_at or NOW,
        content=json.dumps(
            {"title": "Masked Corp update", "summary": summary}
        ),
    )


FIXTURE_CLASSES = {
    "confirmed_order": (
        "Masked Corp announced a definitive purchase agreement valued at "
        "approximately $120 million with a regional utility."
    ),
    "mere_proposal": (
        "Masked Corp entered a non-binding memorandum of understanding "
        "to explore a potential future collaboration."
    ),
    "cancellation": (
        "Masked Corp announced the cancellation of its previously "
        "disclosed supply agreement effective immediately."
    ),
    "below_threshold": (
        "Masked Corp received a purchase order valued at $2 million."
    ),
    "paraphrase": (
        "A binding commercial contract was secured by Masked Corp, "
        "worth about one hundred twenty million dollars."
    ),
    "lookalike": (
        "Masked Corp confirmed the orderly wind-down of its legacy "
        "ordering platform as part of routine maintenance."
    ),
}


class NarrativeFixtureFamilyTests(unittest.TestCase):
    def _case_and_store(self, summary=None, *, available_at=None, empty=False):
        case = make_case("nfix", 4.0)
        documents = []
        if not empty and summary is not None:
            documents.append(
                _news_doc("nfix-1", case.company_id, summary,
                          available_at=available_at)
            )
        return case, RawInfoStore(documents=tuple(documents))

    def test_readable_classes_project_and_read(self):
        """Classes 1-6 stay readable: excerpt, verbatim window, family."""

        for name, summary in FIXTURE_CLASSES.items():
            with self.subTest(class_name=name):
                case, store = self._case_and_store(summary)
                result = fetch_case_evidence(
                    store,
                    case,
                    source_families=("news",),
                    query=None,
                    max_documents=2,
                    case_ref="case-001",
                )
                self.assertEqual(len(result.narrative_events), 1)
                event = result.narrative_events[0]
                self.assertEqual(event.source_family, "news")
                self.assertTrue(event.title)
                self.assertTrue(event.excerpt.strip())
                self.assertTrue(event.exact_span.strip())

    def test_post_cutoff_document_is_invisible(self):
        """Class 7: documents after prediction time never project."""

        from datetime import timedelta

        future = NOW + timedelta(days=30)
        case, store = self._case_and_store(
            FIXTURE_CLASSES["confirmed_order"], available_at=future
        )
        result = fetch_case_evidence(
            store,
            case,
            source_families=("news",),
            query=None,
            max_documents=2,
            case_ref="case-001",
        )
        self.assertEqual(result.narrative_events, ())
        self.assertEqual(result.documents, ())

    def test_insufficient_evidence_is_typed_not_negative(self):
        """Class 8: no narrative corpus yields empty events, not a claim."""

        case, store = self._case_and_store(empty=True)
        result = fetch_case_evidence(
            store,
            case,
            source_families=("news",),
            query=None,
            max_documents=2,
            case_ref="case-001",
        )
        self.assertEqual(result.narrative_events, ())
        self.assertEqual(result.unread_same_source, False)

    def test_predicate_grounding_on_confirmed_order(self):
        """A narrative predicate grounds on the confirmed-order class."""

        case, store = self._case_and_store(FIXTURE_CLASSES["confirmed_order"])
        proposed = {}

        def propose(view):
            ref = sorted(view["known_event_refs"])[0]
            proposed["ref"] = ref
            return {
                "action": "propose_candidate",
                "rationale": ["Narrative predicate."],
                "candidate": {
                    "measurement": {
                        "observable": "large_order_confirmations",
                        "value_kind": "boolean",
                        "normalization": "window-level existence",
                        "predicate": {
                            "modality": "narrative",
                            "source_families": ["news"],
                            "lookback_days": 90,
                            "semantic_condition": (
                                "confirmed commercial order or purchase "
                                "commitment"
                            ),
                            "threshold": {
                                "field": "amount_usd",
                                "operator": ">=",
                                "value": 50000000,
                            },
                        },
                    },
                    "falsifiers": [
                        {
                            "condition": "Only a proposal or memorandum.",
                            "expected_observation": "unavailable or negative",
                        }
                    ],
                    "evidence_refs": [ref],
                },
            }

        class Model:
            def __init__(self):
                self.actions = [
                    {
                        "action": "fetch_evidence",
                        "rationale": ["Fetch."],
                        "case_refs": ["case-001"],
                        "source_families": ["news"],
                        "max_documents": 2,
                    },
                    propose,
                ]

            def next_action(self, view):
                item = self.actions.pop(0)
                return item(view) if callable(item) else item

        controller = LabelAwareMiningController(
            store=store,
            model=Model(),
            case_pairs=[("case-001", case)],
            measurable_evidence_manifest={"schema_version": "m"},
            signal_catalog=[],
            seed="discovery",
        )
        result = controller.run()
        self.assertEqual(result.terminal_kind, "candidate")
        self.assertTrue(proposed["ref"].startswith("event-"))


if __name__ == "__main__":
    unittest.main()
