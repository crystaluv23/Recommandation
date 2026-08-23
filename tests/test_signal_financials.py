from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
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
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SecFinancialSignalTests(TestCase):
    def test_v18_current_revenue_alias_wins_and_stale_fallback_is_unavailable(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/signal_financials/"
                "v18_wynn_revenue_alias_and_staleness.json"
            ).read_text()
        )
        as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        specs = (
            _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.2, 0.0),
            _spec(
                "operating_cash_flow_margin",
                "financial.operating_cash_flow_margin",
                0.1,
                0.0,
            ),
        )

        def execute(payload: object) -> tuple:
            document = _document(
                "wynn-facts",
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            )
            return SignalExecutor(
                _snapshot(specs), RawInfoStore(documents=(document,))
            ).execute_batch(
                tuple(spec.ref for spec in specs),
                company_id="issuer_1",
                as_of=as_of,
            ).results

        current = execute(fixture["current_payload"])
        self.assertEqual(current[0].interpretation, "revenue_growth_yoy=-0.0872356")
        self.assertEqual(
            current[1].interpretation, "operating_cash_flow_margin=0.0786722"
        )
        cited = " ".join(
            evidence.exact_span
            for result in current
            for evidence in result.supporting_evidence
        )
        self.assertIn('"end":"2025-03-31"', cited)
        self.assertNotIn('"end":"2018-12-31"', cited)

        stale = execute(fixture["stale_payload"])
        self.assertEqual(
            tuple(result.value for result in stale),
            (SignalValue.UNAVAILABLE, SignalValue.UNAVAILABLE),
        )
        self.assertTrue(all("stale" in result.interpretation for result in stale))
    def test_scoped_sec_api_drives_six_financial_signals_and_excludes_future(self) -> None:
        content = _scoped_company_facts_content()
        document = _document("sec_scoped", content)
        specs = (
            _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.4, 0.0),
            _spec("revenue_acceleration", "financial.revenue_acceleration", 0.2, -0.1),
            _spec("gross_margin_change", "financial.gross_margin_change", 0.05, -0.05),
            _spec(
                "operating_cash_flow_margin",
                "financial.operating_cash_flow_margin",
                0.1,
                0.0,
            ),
            _spec(
                "net_share_retirement_yoy",
                "financial.net_share_retirement_yoy",
                0.02,
                -0.05,
            ),
            _spec("cash_reserves", "financial.cash_reserves", 30.0, 10.0),
        )
        executor = SignalExecutor(_snapshot(specs), RawInfoStore(documents=(document,)))

        batch = executor.execute_batch(
            tuple(spec.ref for spec in specs),
            company_id="issuer_1",
            as_of=AS_OF,
        )

        self.assertEqual([item.value for item in batch.results], [SignalValue.POSITIVE] * 6)
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

    def test_share_retirement_prefers_split_comparable_same_filing_facts(self) -> None:
        shares = [
            _row("2023-01-01", "2023-12-31", 50.0, "2024-02-01"),
            _row("2023-01-01", "2023-12-31", 120.0, "2025-01-20"),
            _row("2024-01-01", "2024-12-31", 110.0, "2025-01-20"),
        ]
        content = json.dumps(
            {
                "cik": 1,
                "facts": {
                    "us-gaap": {
                        "WeightedAverageNumberOfSharesOutstandingBasic": {
                            "units": {"shares": shares}
                        }
                    }
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        spec = _spec(
            "net_share_retirement_yoy",
            "financial.net_share_retirement_yoy",
            0.02,
            -0.05,
        )

        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("shares", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertIn("0.0833333", result.interpretation)
        cited = " ".join(item.exact_span for item in result.supporting_evidence)
        self.assertIn('"filed":"2025-01-20"', cited)
        self.assertNotIn('"val":50.0', cited)

    def test_share_dilution_is_negative(self) -> None:
        content = json.dumps(
            {
                "cik": 1,
                "facts": {
                    "us-gaap": {
                        "WeightedAverageNumberOfSharesOutstandingBasic": {
                            "units": {
                                "shares": [
                                    _row(
                                        "2023-01-01",
                                        "2023-12-31",
                                        100.0,
                                        "2025-01-20",
                                    ),
                                    _row(
                                        "2024-01-01",
                                        "2024-12-31",
                                        110.0,
                                        "2025-01-20",
                                    ),
                                ]
                            }
                        }
                    }
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        spec = _spec(
            "net_share_retirement_yoy",
            "financial.net_share_retirement_yoy",
            0.02,
            -0.05,
        )

        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("dilution", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(result.value, SignalValue.NEGATIVE)
        self.assertEqual(result.interpretation, "net_share_retirement_yoy=-0.1")

    def test_cash_flow_margin_requires_the_same_reported_duration(self) -> None:
        facts = [
            _accession_fact("Revenues", "2024-10-01", "2024-12-31", 100.0),
            _accession_fact(
                "NetCashProvidedByUsedInOperatingActivities",
                "2024-01-01",
                "2024-12-31",
                50.0,
            ),
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
        spec = _spec(
            "operating_cash_flow_margin",
            "financial.operating_cash_flow_margin",
            0.1,
            0.0,
        )

        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("cash_flow", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertIn("Matching SEC", result.interpretation)

    def test_price_momentum_uses_exact_observation_lookback_and_fails_closed(self) -> None:
        spec = SignalSpec(
            signal_id="price_momentum_126d",
            version=1,
            category="market",
            description="Fixture price momentum.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            function="market.price_momentum_126d",
            source_types=("market_data",),
            parameters={
                "lookback_observations": 126,
                "positive_min": 0.2,
                "negative_max": -0.2,
            },
        )
        enough = _document(
            "market_enough",
            "Point-in-time chronological adjusted prices.",
            "market_data",
            metadata={"prices": list(range(100, 227))},
        )
        short = _document(
            "market_short",
            "Short point-in-time chronological adjusted prices.",
            "market_data",
            metadata={"prices": list(range(100, 226))},
        )

        positive = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(enough,))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        unavailable = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(short,))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(positive.value, SignalValue.POSITIVE)
        self.assertEqual(positive.interpretation, "price_momentum_126d=1.26")
        self.assertEqual(unavailable.value, SignalValue.UNAVAILABLE)
        self.assertIn("requires 127 observations", unavailable.interpretation)

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
    document_id: str,
    content: str,
    source_type: str = "sec_company_facts",
    *,
    metadata: dict[str, object] | None = None,
) -> RawInfoDocument:
    return RawInfoDocument.create(
        document_id=document_id,
        company_id="issuer_1",
        source_type=source_type,
        published_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
        available_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
        content=content,
        metadata=metadata,
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
    operating_cash_flow = [
        _row("2024-01-01", "2024-12-31", 30.0, "2025-01-20"),
        _row("2025-01-01", "2025-12-31", 999.0, "2026-01-20"),
    ]
    shares = [
        _row("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
        _row("2024-01-01", "2024-12-31", 90.0, "2025-01-20"),
        _row("2025-01-01", "2025-12-31", 1.0, "2026-01-20"),
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
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "units": {"USD": operating_cash_flow}
                    },
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {"shares": shares}
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
