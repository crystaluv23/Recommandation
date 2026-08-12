from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    SignalExecutionType,
    SignalExecutor,
    SignalSpec,
    SignalValue,
)


AS_OF = datetime(2025, 2, 1, tzinfo=timezone.utc)


class SecFinancialSignalTests(TestCase):
    def test_scoped_sec_api_drives_four_financial_signals_and_excludes_future(self) -> None:
        content = _scoped_company_facts_content()
        document = _document("sec_scoped", content)
        specs = (
            _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.4, 0.0),
            _spec("revenue_acceleration", "financial.revenue_acceleration", 0.2, -0.1),
            _spec("gross_margin_change", "financial.gross_margin_change", 0.05, -0.05),
            _spec("cash_reserves", "financial.cash_reserves", 30.0, 10.0),
        )
        executor = SignalExecutor(_snapshot(specs), RawInfoStore(documents=(document,)))

        batch = executor.execute_batch(
            tuple(spec.ref for spec in specs),
            company_id="issuer_1",
            as_of=AS_OF,
        )

        self.assertEqual([item.value for item in batch.results], [SignalValue.POSITIVE] * 4)
        self.assertNotIn("999", " ".join(item.interpretation for item in batch.results))
        for result in batch.results:
            self.assertTrue(result.supporting_evidence)
            for evidence in result.supporting_evidence:
                self.assertIn(evidence.exact_span, content)
                self.assertNotIn('"val":999', evidence.exact_span)

    def test_accession_scoped_schema_is_supported_with_literal_fact_evidence(self) -> None:
        facts = [
            _accession_fact("Revenues", "2023-01-01", "2023-12-31", 100.0),
            _accession_fact("Revenues", "2024-01-01", "2024-12-31", 130.0),
        ]
        content = json.dumps(
            {
                "schema_version": "sec-company-facts-document-v1",
                "cik": "1",
                "accession_number": "fixture",
                "filing_date": "2025-01-20",
                "form": "10-K",
                "facts": facts,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        spec = _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.2, 0.0)
        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("sec_accession", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(len(result.supporting_evidence), 2)
        self.assertTrue(
            all(item.exact_span in content for item in result.supporting_evidence)
        )

    def test_unchanged_document_fingerprint_skips_repeat_then_oracle_growth_reexecutes(self) -> None:
        spec = SignalSpec(
            signal_id="negative_word_count",
            version=1,
            category="news",
            description="Count negative terms.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            function="news.negative_word_count",
            source_types=("news",),
            parameters={"negative_count_min": 1, "terms": ["risk"]},
        )
        store = RawInfoStore(documents=(_document("news_1", "risk increased", "news"),))
        executor = SignalExecutor(_snapshot((spec,)), store)
        first = executor.execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF)
        second = executor.execute_batch(
            (spec.ref,),
            company_id="issuer_1",
            as_of=AS_OF,
            prior_fingerprints=first.document_fingerprints,
        )
        self.assertEqual(second.signal_calls, 0)
        self.assertEqual(second.skipped_unchanged_refs, (spec.ref,))

        store.append(_document("news_2", "another risk", "news"))
        third = executor.execute_batch(
            (spec.ref,),
            company_id="issuer_1",
            as_of=AS_OF,
            prior_fingerprints=first.document_fingerprints,
        )
        self.assertEqual(third.signal_calls, 1)
        self.assertFalse(third.skipped_unchanged_refs)


def _spec(
    signal_id: str,
    function: str,
    positive_min: float,
    negative_max: float,
) -> SignalSpec:
    return SignalSpec(
        signal_id=signal_id,
        version=1,
        category="financial",
        description=f"Fixture {signal_id}.",
        execution_type=SignalExecutionType.DETERMINISTIC,
        function=function,
        source_types=("sec_company_facts",),
        parameters={"positive_min": positive_min, "negative_max": negative_max},
    )


def _snapshot(specs: tuple[SignalSpec, ...]) -> FrozenSignalRegistry:
    payload = json.dumps([spec.to_dict() for spec in specs], sort_keys=True)
    return FrozenSignalRegistry(
        version=1,
        registry_hash=hashlib.sha256(payload.encode()).hexdigest(),
        specs=specs,
        skills={},
    )


def _document(
    document_id: str, content: str, source_type: str = "sec_company_facts"
) -> RawInfoDocument:
    return RawInfoDocument.create(
        document_id=document_id,
        company_id="issuer_1",
        source_type=source_type,
        published_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
        available_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
        content=content,
    )


def _row(start: str | None, end: str, value: float, filed: str) -> dict[str, object]:
    value_dict: dict[str, object] = {
        "end": end,
        "filed": filed,
        "form": "10-K",
        "val": value,
    }
    if start is not None:
        value_dict["start"] = start
    return value_dict


def _scoped_company_facts_content() -> str:
    revenue = [
        _row("2022-01-01", "2022-12-31", 80.0, "2023-02-01"),
        _row("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
        _row("2024-01-01", "2024-12-31", 150.0, "2025-01-20"),
        _row("2025-01-01", "2025-12-31", 999.0, "2026-01-20"),
    ]
    gross = [
        _row("2023-01-01", "2023-12-31", 50.0, "2024-02-01"),
        _row("2024-01-01", "2024-12-31", 90.0, "2025-01-20"),
    ]
    cash = [
        _row(None, "2023-12-31", 20.0, "2024-02-01"),
        _row(None, "2024-12-31", 40.0, "2025-01-20"),
    ]
    return json.dumps(
        {
            "cik": 1,
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": revenue}},
                    "GrossProfit": {"units": {"USD": gross}},
                    "CashAndCashEquivalentsAtCarryingValue": {
                        "units": {"USD": cash}
                    },
                }
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _accession_fact(
    tag: str, start: str, end: str, value: float
) -> dict[str, object]:
    return {
        "taxonomy": "us-gaap",
        "tag": tag,
        "unit": "USD",
        "start": start,
        "end": end,
        "value": value,
    }
