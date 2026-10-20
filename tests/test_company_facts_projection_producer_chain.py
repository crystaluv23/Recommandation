"""Exercise SEC normalization through actual bounded model payload and citations.

These are offline format/lineage controls, not model-behavior acceptance.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
from unittest import TestCase

from stock_opportunity_agent.data.sec_company_facts import materialize_company_fact_documents
from stock_opportunity_agent.research.evolution_signal_roles import (
    StructuredLLMSignalRunner, _map_projected_signal_evidence,
    _shared_llm_signal_projection,
)
from stock_opportunity_agent.signal_library import (
    LLMSignalBatchInput, SignalExecutionType, SignalRetrievalPolicy, SignalSpec,
)


class CompanyFactsProjectionProducerChainTests(TestCase):
    def _produce(self):
        cutoff = datetime(2025, 5, 30, tzinfo=timezone.utc)
        response = {"cik": 1, "facts": {"us-gaap": {}}}
        for tag, label, value, prior in (
            ("CashAndCashEquivalentsAtCarryingValue", "Cash and cash equivalents", 120, 100),
            ("LiabilitiesCurrent", "Current liabilities", 300, 250),
        ):
            response["facts"]["us-gaap"][tag] = {
                "label": label, "description": 'Literal {braces} and "quotes" \\ remain.',
                "units": {"USD": [
                    {"accn": "0000000001-25-000001", "filed": "2025-05-08",
                     "form": "10-Q", "end": end, "val": amount,
                     "fy": 2025, "fp": "Q1"}
                    for end, amount in (("2024-03-31", prior), ("2025-03-31", value))
                ]},
            }
        original = deepcopy(response)
        documents, _report = materialize_company_fact_documents(
            response,
            item={"cik": "0000000001", "company_id": "cik_0000000001",
                  "source_url": "https://example.invalid/facts"},
            selection={"period_end_from": "2024-01-01", "period_end_through": "2025-05-30",
                       "available_at_through": cutoff.isoformat(),
                       "taxonomy_allowlist": ["us-gaap"], "form_allowlist": ["10-Q"]},
            provenance={}, retrieved_at=cutoff,
        )
        self.assertEqual(response, original)
        self.assertEqual(len(documents), 1)
        spec = SignalSpec(
            signal_id="liquidity_read_control", version=1, category="financial",
            description="Read cash and current liabilities without computing a ratio.",
            execution_type=SignalExecutionType.LLM, source_types=("sec_company_facts",),
            skill_file="skill.md", retrieval_policy=SignalRetrievalPolicy(
                query_terms=("cash current liabilities",)),
        )
        return cutoff, documents[0], LLMSignalBatchInput(spec, tuple(documents), "Read literal facts.")

    def test_native_producer_reaches_structured_payload_and_raw_citation(self):
        cutoff, document, item = self._produce()
        original = document.to_dict()
        rows, lineage = _shared_llm_signal_projection((item,))
        self.assertEqual(len(rows), 4)
        expected = {
            ("CashAndCashEquivalentsAtCarryingValue", "2025-03-31", 120, "latest"),
            ("CashAndCashEquivalentsAtCarryingValue", "2024-03-31", 100, "comparable_prior"),
            ("LiabilitiesCurrent", "2025-03-31", 300, "latest"),
            ("LiabilitiesCurrent", "2024-03-31", 250, "comparable_prior"),
        }
        actual = set()
        for row in rows:
            fact = json.loads(row["exact_text"])
            context = row["fact_context"]
            self.assertNotIn("val", fact)
            actual.add((context["concept"], fact["end"], fact["value"], context["record_selection"]))
            self.assertEqual(context["unit"], "USD")
            self.assertFalse(context["source_context_partial"])
            self.assertEqual(context["omitted_concept_count"], 0)
            mapped = _map_projected_signal_evidence({"evidence": {
                "supporting": [{"projection_id": row["projection_id"], "exact_text": row["exact_text"]}],
                "counter": [],
            }}, lineage)
            cite = mapped["evidence"]["supporting"][0]
            self.assertEqual(cite["exact_span"], row["exact_text"])
            self.assertIn(cite["exact_span"], document.content)
        self.assertEqual(actual, expected)
        payload = StructuredLLMSignalRunner(None)._batch_payload(
            (item,), rows, lineage, cutoff, budget_trimmed=False,
        )
        restored = json.loads(json.dumps(payload))
        self.assertEqual(restored["source_projection"], rows)
        self.assertEqual(set(restored["signals"][0]["eligible_projection_ids"]), set(lineage))
        self.assertEqual(document.to_dict(), original)

    def test_shared_payload_deduplicates_facts_and_retains_both_owners(self):
        cutoff, document, item = self._produce()
        from dataclasses import replace
        other = replace(item, spec=replace(item.spec, signal_id="other_liquidity_read"))
        rows, lineage = _shared_llm_signal_projection((item, other))
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(set(value.eligible_signal_refs) == {item.spec.ref, other.spec.ref}
                            for value in lineage.values()))
        payload = StructuredLLMSignalRunner(None)._batch_payload(
            (item, other), rows, lineage, cutoff, budget_trimmed=False,
        )
        self.assertTrue(all(set(signal["eligible_projection_ids"]) == set(lineage)
                            for signal in payload["signals"]))

    def test_request_budget_cannot_keep_only_one_conflicting_alternative(self):
        from dataclasses import replace
        from stock_opportunity_agent.data.raw_info import RawInfoDocument

        cutoff, document, item = self._produce()
        body = json.loads(document.content)
        body["facts"] = [fact for fact in body["facts"]
                         if fact["tag"] == "CashAndCashEquivalentsAtCarryingValue"]
        latest = next(fact for fact in body["facts"] if fact["end"] == "2025-03-31")
        body["facts"].append(dict(latest, value=125))
        conflict = RawInfoDocument.create(
            document_id="conflicting-cash", company_id=document.company_id,
            source_type=document.source_type, published_at=document.published_at,
            available_at=document.available_at, metadata=document.metadata,
            content=json.dumps(body, separators=(",", ":")),
        )
        item = replace(item, documents=(conflict,))
        rows, lineage = _shared_llm_signal_projection((item,))
        self.assertEqual(len(rows), 3)
        latest_rows = [row for row in rows if json.loads(row["exact_text"])["end"] == "2025-03-31"]
        self.assertEqual(len(latest_rows), 2)
        self.assertTrue(all(row["fact_context"]["record_selection"] == "latest"
                            for row in latest_rows))

        class CountRows:
            def estimate_json_request_tokens(self, **kwargs):
                return 100 + 100 * len(kwargs["payload"]["source_projection"])

        runner = StructuredLLMSignalRunner(CountRows())
        for budget in (200, 300, 400):
            with self.subTest(budget=budget):
                fitted, fitted_lineage, trimmed = runner._fit_projection_to_budget(
                    (item,), rows, lineage, cutoff, request_token_budget=budget,
                )
                self.assertIn(len(fitted), (0, 3))
                self.assertEqual(set(fitted_lineage), {row["projection_id"] for row in fitted})
                if budget < 400:
                    self.assertTrue(trimmed)
