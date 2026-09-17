import json
import tempfile
import unittest
from pathlib import Path

from tests.scheme_evolution_test_support import (  # noqa: F403
    NOW,
    RawInfoDocument,
    RawInfoStore,
    make_case,
)

from stock_opportunity_agent.research.mining_replay import (
    assert_view_masked,
    load_historical_hypotheses,
    measure_arrival,
    verify_replay_invariants,
)

FACTS_TWO_RECORDS = json.dumps(
    {
        "facts": {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "label": "Cash and Cash Equivalents at Carrying Value",
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 1000, "filed": "2021-02-01"},
                            {"end": "2019-12-31", "val": 800, "filed": "2020-02-01"},
                        ]
                    },
                }
            }
        }
    }
)
FACTS_ONE_RECORD = json.dumps(
    {
        "facts": {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "label": "Cash and Cash Equivalents at Carrying Value",
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 500, "filed": "2021-02-01"}
                        ]
                    },
                }
            }
        }
    }
)


def _store():
    case_full = make_case("replay_full", 4.0)
    case_thin = make_case("replay_thin", 1.1)
    documents = (
        RawInfoDocument.create(
            document_id="replay-facts-full",
            company_id=case_full.company_id,
            source_type="company_facts",
            published_at=NOW,
            available_at=NOW,
            content=FACTS_TWO_RECORDS,
        ),
        RawInfoDocument.create(
            document_id="replay-8k-full",
            company_id=case_full.company_id,
            source_type="8-k",
            published_at=NOW,
            available_at=NOW,
            content="Acme Holdings announced a material agreement.",
        ),
        RawInfoDocument.create(
            document_id="replay-facts-thin",
            company_id=case_thin.company_id,
            source_type="company_facts",
            published_at=NOW,
            available_at=NOW,
            content=FACTS_ONE_RECORD,
        ),
    )
    return (case_full, case_thin), RawInfoStore(documents=documents)


def _hypothesis():
    return {
        "proposal_ref": "h1-c0001-s01",
        "measurement": {
            "observable": "cash_runway_from_cash_and_cash_equivalents",
            "value_kind": "numeric",
            "normalization": (
                "Cash and Cash Equivalents at Carrying Value divided by "
                "operating burn"
            ),
        },
        "retrieval_intent": {
            "source_types": ["company_facts", "8-k"],
            "query": "cash",
        },
    }


class MiningReplayTests(unittest.TestCase):
    def test_arrival_measures_family_and_concept_pair_coverage(self) -> None:
        cases, store = _store()

        report = measure_arrival(store, list(cases), [_hypothesis()])

        self.assertEqual(report["cohort_case_count"], 2)
        row = report["hypotheses"][0]
        families = {item["family"]: item for item in row["family_inputs"]}
        self.assertEqual(families["company_facts"]["cases_with_documents"], 2)
        self.assertEqual(families["8-k"]["cases_with_documents"], 1)
        self.assertAlmostEqual(families["8-k"]["coverage"], 0.5)
        concept = row["concept_inputs"][0]
        self.assertEqual(concept["concept"], "CashAndCashEquivalentsAtCarryingValue")
        self.assertEqual(concept["cases_with_latest"], 2)
        self.assertEqual(concept["cases_with_comparable_pair"], 1)
        self.assertAlmostEqual(concept["pair_coverage"], 0.5)
        self.assertEqual(row["input_count"], 3)
        self.assertAlmostEqual(
            row["mean_input_coverage"], (1.0 + 0.5 + 0.5) / 3, places=3
        )

    def test_hypothesis_without_named_concepts_reports_families_only(self) -> None:
        cases, store = _store()
        hypothesis = _hypothesis()
        hypothesis["measurement"] = {
            "observable": "backlog_share",
            "value_kind": "numeric",
            "normalization": "order backlog over revenue",
        }

        report = measure_arrival(store, list(cases), [hypothesis])

        row = report["hypotheses"][0]
        self.assertEqual(row["concept_inputs"], [])
        self.assertEqual(row["input_count"], 2)

    def test_load_historical_hypotheses_takes_final_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requests").mkdir(parents=True)
            (root / "cache" / "responses").mkdir(parents=True)
            (root / "experiments").mkdir(parents=True)
            for request_hash, stage, rows in (
                (
                    "aaa1",
                    "signal_mining_hypotheses",
                    [{"proposal_ref": "old"}],
                ),
                (
                    "bbb2",
                    "signal_mining_hypotheses_correction",
                    [{"proposal_ref": "final"}],
                ),
            ):
                (root / "requests" / f"{request_hash}.json").write_text(
                    json.dumps(
                        {
                            "request_hash": request_hash,
                            "request": {"stage": stage, "messages": []},
                        }
                    ),
                    encoding="utf-8",
                )
                (root / "cache" / "responses" / f"{request_hash}.json").write_text(
                    json.dumps({"json_output": {"hypotheses": rows}}),
                    encoding="utf-8",
                )
            (root / "experiments" / "trajectory.jsonl").write_text(
                "\n".join(
                    json.dumps(
                        {
                            "event_type": "external_call_completed",
                            "stage": stage,
                            "request_hash": request_hash,
                        }
                    )
                    for request_hash, stage in (
                        ("aaa1", "signal_mining_hypotheses"),
                        ("bbb2", "signal_mining_hypotheses_correction"),
                    )
                ),
                encoding="utf-8",
            )

            hypotheses = load_historical_hypotheses(root)

            self.assertEqual(
                [row["proposal_ref"] for row in hypotheses], ["final"]
            )

    def test_view_masking_assertion_flags_leaked_alias(self) -> None:
        with self.assertRaises(AssertionError):
            assert_view_masked(
                {"label_map": {"case-001": "positive"}, "note": "Acme Holdings"},
                ["Acme Holdings"],
            )
        assert_view_masked(
            {"label_map": {"case-001": "positive"}, "note": "masked company"},
            ["Acme Holdings"],
        )

    def test_invariants_verify_traceability_pit_ledger_and_masking(self) -> None:
        cases, store = _store()
        report = measure_arrival(store, list(cases), [_hypothesis()])
        self.assertTrue(report["hypotheses"])
        documents_by_hash = {
            document.content_hash: document for document in store.documents
        }
        facts = []
        for case in cases:
            from stock_opportunity_agent.research.mining_agent_tools import (
                project_case_facts,
            )

            facts.extend(project_case_facts(store, case, case_ref=case.case_id))
        self.assertTrue(facts)

        result = verify_replay_invariants(
            facts=facts,
            documents_by_content_hash=documents_by_hash,
            ledger_ids=[1, 2, 3],
            model_views=[{"label_map": {}, "note": "opaque"}],
            identity_aliases=["Acme Holdings"],
        )

        self.assertTrue(result["all_passed"], result)
        self.assertEqual(result["evidence_traceability_failures"], [])
        self.assertEqual(result["pit_failures"], [])
        self.assertTrue(result["ledger_append_only"])

        broken = verify_replay_invariants(
            facts=facts,
            documents_by_content_hash=documents_by_hash,
            ledger_ids=[1, 3],
            model_views=[{"note": "Acme Holdings filing"}],
            identity_aliases=["Acme Holdings"],
        )
        self.assertFalse(broken["all_passed"])
        self.assertFalse(broken["ledger_append_only"])
        self.assertEqual(len(broken["identity_masking_failures"]), 1)


if __name__ == "__main__":
    unittest.main()
