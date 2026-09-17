import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tests.scheme_evolution_test_support import (  # noqa: F403
    NOW,
    RawInfoDocument,
    RawInfoStore,
    make_case,
)

from stock_opportunity_agent.research.mining_agent_tools import (
    build_case_co_occurrence_relations,
    build_same_concept_relations,
    compute_statistic,
    fetch_case_evidence,
    project_case_facts,
)


FACTS_CONTENT = json.dumps(
    {
        "facts": {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "label": "Cash and Cash Equivalents at Carrying Value",
                    "units": {
                        "USD": [
                            {
                                "end": "2020-12-31",
                                "val": 1000,
                                "filed": "2021-02-01",
                            },
                            {
                                "end": "2019-12-31",
                                "val": 800,
                                "filed": "2020-02-01",
                            },
                        ]
                    },
                },
                "Revenues": {
                    "label": "Revenues",
                    "units": {
                        "USD": [
                            {
                                "start": "2020-01-01",
                                "end": "2020-12-31",
                                "val": 5000,
                                "filed": "2021-02-01",
                            },
                            {
                                "start": "2019-01-01",
                                "end": "2019-12-31",
                                "val": 4200,
                                "filed": "2020-02-01",
                            },
                        ]
                    },
                }
            }
        }
    }
)


def _facts_document(company_id: str, index: int) -> RawInfoDocument:
    return RawInfoDocument.create(
        document_id=f"tools-facts-{index}",
        company_id=company_id,
        source_type="company_facts",
        published_at=NOW,
        available_at=NOW,
        content=FACTS_CONTENT,
    )


class MiningAgentToolsTests(unittest.TestCase):
    def test_project_case_facts_binds_concept_unit_period_value_and_span(self) -> None:
        case = make_case("tools_a", 4.0)
        store = RawInfoStore(documents=(_facts_document(case.company_id, 1),))

        facts = project_case_facts(store, case)

        self.assertEqual(len(facts), 4)
        cash = [
            fact
            for fact in facts
            if fact.concept == "CashAndCashEquivalentsAtCarryingValue"
        ]
        self.assertEqual(
            {fact.record_selection for fact in cash},
            {"latest", "comparable_prior"},
        )
        latest = next(fact for fact in cash if fact.record_selection == "latest")
        self.assertEqual(latest.unit, "USD")
        self.assertEqual(latest.period["end"], "2020-12-31")
        self.assertEqual(str(latest.value), "1000")
        self.assertIn('"val": 1000', latest.exact_span)
        self.assertTrue(latest.document_ref)
        self.assertTrue(latest.content_hash)
        self.assertLessEqual(
            datetime.fromisoformat(latest.available_at),
            case.prediction_time,
        )

    def test_project_case_facts_enforces_point_in_time(self) -> None:
        case = make_case("tools_b", 4.0)
        future = RawInfoDocument.create(
            document_id="tools-future",
            company_id=case.company_id,
            source_type="company_facts",
            published_at=NOW + timedelta(days=30),
            available_at=NOW + timedelta(days=30),
            content=FACTS_CONTENT,
        )
        store = RawInfoStore(documents=(future,))

        facts = project_case_facts(store, case)

        self.assertEqual(facts, ())

    def test_same_concept_relations_pair_latest_with_comparable_prior(self) -> None:
        case = make_case("tools_c", 4.0)
        store = RawInfoStore(documents=(_facts_document(case.company_id, 1),))
        facts = project_case_facts(store, case)

        relations = build_same_concept_relations(facts)

        self.assertEqual(len(relations), 2)
        for relation in relations:
            self.assertEqual(relation.kind, "same_concept_period_pair")
            self.assertEqual(len(relation.fact_refs), 2)
            self.assertEqual(relation.case_ref, facts[0].case_ref)

    def test_compute_statistic_builds_ratio_with_lineage_only_on_request(self) -> None:
        case = make_case("tools_d", 4.0)
        store = RawInfoStore(documents=(_facts_document(case.company_id, 1),))
        facts = project_case_facts(store, case)
        cash = {
            fact.record_selection: fact
            for fact in facts
            if fact.concept == "CashAndCashEquivalentsAtCarryingValue"
        }

        relation = compute_statistic(
            "latest_over_comparable_prior",
            [cash["latest"].fact_ref, cash["comparable_prior"].fact_ref],
            facts=facts,
        )

        self.assertEqual(relation.kind, "numerator_denominator")
        self.assertEqual(relation.rule, "latest_over_comparable_prior")
        self.assertAlmostEqual(float(relation.value), 1000 / 800)
        self.assertEqual(
            list(relation.fact_refs),
            [cash["latest"].fact_ref, cash["comparable_prior"].fact_ref],
        )

    def test_co_occurrence_relations_stay_within_one_case_and_documents(self) -> None:
        case_a = make_case("tools_e1", 4.0)
        case_b = make_case("tools_e2", 1.1)
        docs = (
            _facts_document(case_a.company_id, 1),
            _facts_document(case_a.company_id, 2),
            _facts_document(case_b.company_id, 3),
        )
        store = RawInfoStore(documents=docs)
        facts_a = project_case_facts(store, case_a)
        facts_b = project_case_facts(store, case_b)
        refs_a = {fact.fact_ref for fact in facts_a}

        relations = build_case_co_occurrence_relations(
            [*facts_a, *facts_b], limit=64
        )

        self.assertTrue(relations)
        for relation in relations:
            self.assertEqual(relation.kind, "case_co_occurrence")
            owners = {
                fact.case_ref
                for fact in [*facts_a, *facts_b]
                if fact.fact_ref in relation.fact_refs
            }
            self.assertEqual(len(owners), 1)
            documents = {
                fact.document_ref
                for fact in [*facts_a, *facts_b]
                if fact.fact_ref in relation.fact_refs
            }
            self.assertEqual(len(documents), 2)
            self.assertTrue(set(relation.fact_refs) <= refs_a)

    def test_fetch_case_evidence_reports_coverage_and_limits(self) -> None:
        case = make_case("tools_f", 4.0)
        docs = tuple(
            RawInfoDocument.create(
                document_id=f"tools-8k-{index}",
                company_id=case.company_id,
                source_type="8-k",
                published_at=NOW,
                available_at=NOW,
                content=(
                    f"{case.basic_info['company_name']} announced a material "
                    f"agreement number {index}."
                ),
            )
            for index in range(4)
        )
        store = RawInfoStore(documents=(*docs, _facts_document(case.company_id, 1)))

        result = fetch_case_evidence(
            store,
            case,
            source_families=("8-k",),
            query="material agreement",
            max_documents=2,
        )

        self.assertEqual(len(result.documents), 2)
        self.assertEqual(len(result.excluded_by_limits), 2)
        self.assertTrue(result.query_coverage["matched_terms"])
        self.assertTrue(result.unread_same_source)
        for item in (*result.facts, *result.narrative_events):
            self.assertTrue(item.content_hash)
            self.assertLessEqual(
                datetime.fromisoformat(item.available_at),
                case.prediction_time,
            )


if __name__ == "__main__":
    unittest.main()
