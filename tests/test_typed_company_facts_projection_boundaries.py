"""Independent, synthetic source-format controls; no execution or source admission."""

import copy
import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.research.evolution_core import _company_facts_context
from stock_opportunity_agent.research.evolution_signal_roles import (
    _map_projected_signal_evidence,
    _shared_llm_signal_projection,
    _single_llm_signal_projection,
)
from stock_opportunity_agent.signal_library import (
    LLMSignalBatchInput,
    SignalExecutionType,
    SignalRetrievalPolicy,
    SignalSpec,
)


CASH = "CashAndCashEquivalentsAtCarryingValue"
LIABILITIES = "LiabilitiesCurrent"
REVENUE = "Revenues"


class TypedCompanyFactsProjectionBoundariesTests(TestCase):
    """Assert the owning spec's literal/group/PIT rules independently of helpers."""

    available = datetime(2025, 5, 10, tzinfo=timezone.utc)

    def fact(self, tag=CASH, value=110, end="2025-03-31", **changes):
        """Make an explicitly synthetic typed fact, keeping source fields literal."""
        return {
            "taxonomy": "us-gaap", "tag": tag, "label": tag,
            "unit": "USD", "value": value, "start": None, "end": end,
            **changes,
        }

    def document(self, rows, *, identifier="synthetic-facts", **parent):
        """Create a memory-only source document with a valid parent filing."""
        body = {
            "schema_version": "sec-company-facts-document-v1", "cik": "0000000001",
            "filing_date": "2025-05-09", "form": "10-Q", "facts": rows,
            **parent,
        }
        return RawInfoDocument.create(
            document_id=identifier, company_id="cik_0000000001",
            source_type="sec_company_facts", published_at=self.available,
            available_at=self.available, content=json.dumps(body, ensure_ascii=False, indent=2),
            metadata={"cik": "0000000001", "provider": "sec_edgar"},
        )

    def item(self, document, name="cash", query="cash liabilities revenue"):
        """Build a version-owned read request without a model or runner."""
        spec = SignalSpec(
            signal_id=name, version=1, category="financial", description="Read source facts.",
            execution_type=SignalExecutionType.LLM, source_types=("sec_company_facts",),
            skill_file="skill.md", retrieval_policy=SignalRetrievalPolicy(query_terms=(query,)),
        )
        return LLMSignalBatchInput(spec, (document,), "Use only literal available records.")

    def context(self, document, budget=32_000):
        """Require structured recognition, distinguishing it from generic fallback."""
        context = _company_facts_context(document, max_content_chars=budget, query="cash liabilities revenue")
        self.assertIsNotNone(context, "supported typed facts list must use the structured path")
        self.assertLessEqual(len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))), budget)
        return context

    def decoded(self, context):
        """Check every literal and raw offset before returning source rows."""
        return [json.loads(record["exact_span"]) for group in context["concepts"] for record in group["records"]]

    def assert_literals(self, document, context):
        """No wrapper or synthetic record may replace a raw source object."""
        for group in context["concepts"]:
            for record in group["records"]:
                self.assertEqual(document.content[record["start"]:record["end"]], record["exact_span"])
                parsed = json.loads(record["exact_span"])
                self.assertIn(parsed, json.loads(document.content)["facts"])
                self.assertEqual((group["taxonomy"], group["concept"], group["unit"]),
                                 (parsed["taxonomy"], parsed["tag"], parsed["unit"]))
                self.assertNotIn("val", parsed)

    def test_latest_cash_and_liabilities_use_complete_typed_literals(self):
        rows = [self.fact(value=90, end="2023-12-31"), self.fact(value=110),
                self.fact(LIABILITIES, 200, "2024-12-31"), self.fact(LIABILITIES, 220)]
        document = self.document(rows)
        context = self.context(document)
        self.assert_literals(document, context)
        for tag, latest in ((CASH, 110), (LIABILITIES, 220)):
            group = next(group for group in context["concepts"] if group["concept"] == tag)
            self.assertEqual(json.loads(group["records"][0]["exact_span"])["value"], latest)

    def test_latest_same_end_conflicts_and_distinct_durations_survive(self):
        rows = [self.fact(REVENUE, 110, start="2025-01-01"),
                self.fact(REVENUE, 115, start="2025-01-01"),
                self.fact(REVENUE, 210, start="2024-10-01"),
                self.fact(REVENUE, 100, "2024-03-31", start="2024-01-01"),
                self.fact(REVENUE, 190, "2024-03-31", start="2023-10-01")]
        context = self.context(self.document(rows))
        self.assertCountEqual(self.decoded(context), rows)

    def test_nearest_comparable_prior_per_latest_duration_not_nearest_end_only(self):
        rows = [self.fact(REVENUE, 110, start="2025-01-01"),
                self.fact(REVENUE, 210, start="2024-10-01"),
                self.fact(REVENUE, 80, "2024-12-31", start="2024-01-01"),
                self.fact(REVENUE, 100, "2024-03-31", start="2024-01-01"),
                self.fact(REVENUE, 190, "2024-03-31", start="2023-10-01"),
                self.fact(REVENUE, 70, "2023-03-31", start="2023-01-01")]
        context = self.context(self.document(rows))
        self.assertCountEqual(self.decoded(context), [rows[i] for i in (0, 1, 3, 4)])
        self.assertTrue(context["partial"], "excluded historical records remain disclosed")

    def test_units_are_separate_groups_not_a_currency_preference(self):
        rows = [self.fact(value=110), self.fact(value=120, unit="CAD"),
                self.fact(value=100, end="2024-03-31"),
                self.fact(value=105, end="2024-03-31", unit="CAD")]
        context = self.context(self.document(rows))
        self.assertCountEqual(self.decoded(context), rows)
        self.assertEqual({group["unit"] for group in context["concepts"]}, {"USD", "CAD"})

    def test_future_or_invalid_parent_is_empty_partial_not_generic(self):
        for filed in ("2025-05-11", "not-a-date", None, True):
            with self.subTest(filing_date=filed):
                document = self.document([self.fact()], filing_date=filed)
                context = self.context(document)
                self.assertEqual(context["concepts"], [])
                self.assertTrue(context["partial"])
                self.assertEqual(_single_llm_signal_projection(self.item(document))[0], [])

    def test_future_and_invalid_rows_cannot_borrow_valid_parent(self):
        good = self.fact()
        bad = [self.fact(value=999, end="2025-06-30"),
               self.fact(value=998, filed="2025-05-11"),
               self.fact(value=997, end="invalid"),
               self.fact(value=True), self.fact(value=None),
               self.fact(value=996, start="2025-04-01", end="2025-03-31")]
        document = self.document([good, *bad])
        context = self.context(document)
        self.assertEqual(self.decoded(context), [good])
        self.assertTrue(context["partial"])
        projected, _ = _single_llm_signal_projection(self.item(document))
        self.assertEqual([json.loads(row["exact_text"]) for row in projected], [good])

    def test_producer_supported_numeric_string_is_retained_verbatim(self):
        row = self.fact(value="110.00")
        document = self.document([row])
        context = self.context(document)
        self.assertEqual(self.decoded(context), [row])
        self.assert_literals(document, context)
        projected, _ = _single_llm_signal_projection(self.item(document))
        self.assertEqual(len(projected), 1)
        self.assertIsInstance(json.loads(projected[0]["exact_text"])["value"], str)
        self.assertEqual(json.loads(projected[0]["exact_text"])["value"], "110.00")

    def test_braces_quotes_escapes_and_unicode_preserve_exact_offsets(self):
        row = self.fact(description='literal {outer} and \\"quote\\" slash \\ newline\n 零',
                        label='Cash {not an object} "caption"')
        document = self.document([row])
        context = self.context(document)
        self.assertEqual(self.decoded(context), [row])
        self.assert_literals(document, context)
        projected, lineage = _single_llm_signal_projection(self.item(document))
        self.assertEqual(len(projected), 1)
        mapped = _map_projected_signal_evidence({"evidence": {"supporting": [{
            "projection_id": projected[0]["projection_id"], "exact_text": projected[0]["exact_text"],
        }], "counter": []}}, lineage)
        self.assertEqual(mapped["evidence"]["supporting"][0]["exact_span"],
                         context["concepts"][0]["records"][0]["exact_span"])

    def test_small_budget_omits_complete_conflicting_group_and_discloses_partial(self):
        rows = [self.fact(REVENUE, 110, description="x" * 900),
                self.fact(REVENUE, 120, description="y" * 900), self.fact()]
        document = self.document(rows)
        context = self.context(document, budget=800)
        self.assertEqual(self.decoded(context), [rows[2]])
        self.assertTrue(context["partial"])
        self.assertEqual(context["omitted_concept_count"], 1)

    def test_projection_latest_labels_disclosures_and_shared_ownership(self):
        rows = [self.fact(REVENUE, 110, start="2025-01-01"),
                self.fact(REVENUE, 115, start="2025-01-01"),
                self.fact(REVENUE, 100, "2024-03-31", start="2024-01-01"),
                self.fact(REVENUE, 80, "2023-03-31", start="2023-01-01")]
        document = self.document(rows)
        first, second = self.item(document, "first"), self.item(document, "second")
        single, _ = _single_llm_signal_projection(first)
        shared, lineage = _shared_llm_signal_projection((second, first))
        self.assertEqual(shared, single)
        self.assertEqual(len(shared), 3)
        for projected in shared:
            row = json.loads(projected["exact_text"])
            info = projected["fact_context"]
            self.assertEqual(info["record_selection"],
                             "latest" if row["end"] == "2025-03-31" else "comparable_prior")
            self.assertTrue(info["source_context_partial"])
            self.assertEqual(info["omitted_concept_count"], 0)
            self.assertEqual(set(lineage[projected["projection_id"]].eligible_signal_refs),
                             {first.spec.ref, second.spec.ref})

    def test_projection_character_cap_does_not_split_an_alternative_group(self):
        first_rows = [self.fact(value=110, description="a" * 250),
                      self.fact(value=115, description="b" * 250)]
        second_rows = [self.fact(value=210, description="c" * 250),
                       self.fact(value=215, description="d" * 250)]
        first, second = self.document(first_rows, identifier="a"), self.document(second_rows, identifier="b")
        item = self.item(first)
        item = LLMSignalBatchInput(item.spec, (first, second), item.skill)
        with patch("stock_opportunity_agent.research.evolution_signal_roles.MAX_LLM_SIGNAL_CONTEXT_CHARS", 1800):
            projected, _ = _single_llm_signal_projection(item)
        self.assertTrue(projected, "budget fits one complete alternative group")
        self.assertLessEqual(sum(len(row["exact_text"]) for row in projected), 1800)
        for document in (first, second):
            selected = [json.loads(row["exact_text"]) for row in projected
                        if row["document_id"] == document.document_id]
            self.assertIn(len(selected), (0, 2), "later global trimming cannot isolate one conflict")

    def test_unknown_array_schema_keeps_generic_path_without_fact_authority(self):
        document = self.document([self.fact()], schema_version="unsupported-company-facts-v99")
        self.assertIsNone(_company_facts_context(document, max_content_chars=32_000, query="cash"))
        projected, lineage = _single_llm_signal_projection(self.item(document))
        self.assertTrue(projected)
        self.assertTrue(all("fact_context" not in row for row in projected))
        self.assertTrue(all(item.document == document for item in lineage.values()))

    def test_structured_read_never_mutates_raw_identity_or_records(self):
        document = self.document([self.fact(), self.fact(value=105)]).as_capture()
        before = copy.deepcopy(document.to_dict())
        self.context(document)
        _single_llm_signal_projection(self.item(document))
        _shared_llm_signal_projection((self.item(document, "a"), self.item(document, "b")))
        self.assertEqual(document.to_dict(), before)
        self.assertEqual(RawInfoDocument.from_dict(before).to_dict(), before)
