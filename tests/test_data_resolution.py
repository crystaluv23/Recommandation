from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.data.acquisition import (
    AlphaVantageTranscriptAdapter,
    HistoricalPriceAdapter,
    HistoricalUnavailableAdapter,
    SecCompanyFactsAdapter,
    SecFilingAdapter,
    UnavailableProviderAdapter,
)
from stock_opportunity_agent.data.sources.core import PriceBar
from stock_opportunity_agent.data.raw_info import (
    RawInfoDocument,
    RawInfoOracle,
    RawInfoStore,
)
from stock_opportunity_agent.data.resolution import (
    AcquisitionFailure,
    AcquisitionResult,
    DataAcquisitionPolicy,
    DataGapReason,
    EvidenceResolver,
    RawInfoRequest,
    aggregate_capability_gaps,
    broad_research_data_policy_v1,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    SignalExecutionType,
    SignalExecutor,
    SignalSpec,
    SignalValue,
)


AS_OF = datetime(2025, 1, 15, 12, tzinfo=timezone.utc)


def document(
    document_id: str,
    content: str,
    *,
    source_type: str = "news",
    available_at: datetime = AS_OF - timedelta(days=1),
) -> RawInfoDocument:
    return RawInfoDocument.create(
        document_id=document_id,
        company_id="issuer_1",
        source_type=source_type,
        published_at=available_at,
        available_at=available_at,
        content=content,
    )


class FakeAdapter:
    provider = "fake_news"
    source_types = ("news",)
    capabilities = ("news",)

    def __init__(self, result: AcquisitionResult | None = None) -> None:
        self.calls = 0
        self.result = result or AcquisitionResult()

    def acquire(self, request, **kwargs):
        self.calls += 1
        return self.result


class FailingAdapter(FakeAdapter):
    def __init__(self, reason: DataGapReason) -> None:
        super().__init__()
        self.reason = reason

    def acquire(self, request, **kwargs):
        self.calls += 1
        raise AcquisitionFailure(self.reason, "bounded failure")


class EvidenceResolverTests(TestCase):
    def test_can_acquire_is_side_effect_free_and_honors_availability_and_policy(
        self,
    ) -> None:
        request = RawInfoRequest("profile", "Read profile.", ("news",))
        adapter = FakeAdapter()
        disabled = EvidenceResolver(RawInfoStore(), adapters=(adapter,))

        self.assertFalse(disabled.can_acquire(request))
        self.assertEqual(
            disabled.acquisition_unavailability_reason(request),
            "external_not_authorized",
        )
        self.assertEqual(adapter.calls, 0)

        enabled = EvidenceResolver(
            RawInfoStore(),
            adapters=(adapter,),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=("fake_news",),
                allowed_capabilities=("news",),
                allowed_source_types=("news",),
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            ),
        )
        self.assertTrue(enabled.can_acquire(request))
        self.assertIsNone(enabled.acquisition_unavailability_reason(request))
        self.assertFalse(
            enabled.can_acquire(
                RawInfoRequest("filing", "Read filing.", ("filing",))
            )
        )
        self.assertEqual(
            enabled.acquisition_unavailability_reason(
                RawInfoRequest("missing", "Read filing.", ("filing",))
            ),
            "adapter_missing",
        )
        adapter.available = False
        self.assertFalse(enabled.can_acquire(request))
        self.assertEqual(
            enabled.acquisition_unavailability_reason(request),
            "provider_unavailable",
        )
        self.assertEqual(adapter.calls, 0)

        configured_gap = EvidenceResolver(
            RawInfoStore(),
            adapters=(
                UnavailableProviderAdapter(
                    "fake_news",
                    ("news",),
                    ("news",),
                    "Configuration is absent.",
                    unavailability_reason="test_configuration_unavailable",
                ),
            ),
            policy=enabled.policy,
        )
        self.assertEqual(
            configured_gap.acquisition_unavailability_reason(request),
            "test_configuration_unavailable",
        )

    def test_transcript_adapter_maps_fiscal_quarters_and_excludes_future_reports(
        self,
    ) -> None:
        calls: list[str] = []

        class Client:
            transport = None

            def earnings(self, symbol):
                self.symbol = symbol
                return {
                    "symbol": symbol,
                    "annualEarnings": [
                        {"fiscalDateEnding": "2024-01-31"},
                        {"fiscalDateEnding": "2025-01-31"},
                    ],
                    "quarterlyEarnings": [
                        {
                            "fiscalDateEnding": "2024-04-30",
                            "reportedDate": "2024-05-16",
                        },
                        {
                            "fiscalDateEnding": "2024-07-31",
                            "reportedDate": "2024-08-15",
                        },
                        {
                            "fiscalDateEnding": "2024-10-31",
                            "reportedDate": "2024-11-19",
                        },
                        {
                            "fiscalDateEnding": "2025-01-31",
                            "reportedDate": "2025-02-20",
                        },
                    ],
                }

            def earnings_call_transcript(self, symbol, quarter):
                calls.append(quarter)
                return {
                    "symbol": symbol,
                    "quarter": quarter,
                    "transcript": [
                        {
                            "speaker": "CEO",
                            "content": f"Substantive management remarks for {quarter}.",
                        }
                    ],
                }

        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(AlphaVantageTranscriptAdapter(Client()),),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=("alpha_vantage",),
                allowed_capabilities=("transcripts",),
                allowed_source_types=("transcript",),
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            ),
        )
        resolution = resolver.resolve(
            RawInfoRequest(
                "calls",
                "Read recent earnings calls.",
                ("earnings_call",),
                lookback_days=365,
                max_documents=2,
            ),
            company_id="issuer_1",
            identity={"ticker": "WMT"},
            as_of=AS_OF,
        )

        self.assertEqual(calls, ["2025Q3", "2025Q2"])
        self.assertEqual(resolution.status, "resolved")
        loaded = resolver.load_documents(resolution, as_of=AS_OF)
        self.assertEqual(
            [item.metadata["quarter"] for item in loaded],
            ["2025Q3", "2025Q2"],
        )
        self.assertEqual(
            loaded[0].available_at,
            datetime(2024, 11, 20, tzinfo=timezone.utc),
        )
        self.assertIn("earnings_call", resolver.available_source_types)

    def test_compatible_signal_requests_reuse_one_acquisition_failure(self) -> None:
        adapter = FailingAdapter(DataGapReason.PROVIDER_ERROR)
        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(adapter,),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=("fake_news",),
                allowed_capabilities=("news",),
                allowed_source_types=("news",),
                max_requests_per_cycle=2,
                max_requests_per_run=2,
            ),
        )

        first = resolver.resolve(
            RawInfoRequest("signal:one", "Read news.", ("news",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )
        second = resolver.resolve(
            RawInfoRequest("signal:two", "Read compatible news.", ("news",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(adapter.calls, 1)
        self.assertEqual(first.gap.reason, DataGapReason.PROVIDER_ERROR)
        self.assertEqual(second.gap.reason, DataGapReason.PROVIDER_ERROR)
        self.assertIn(
            "acquisition_failure_reused",
            [event.kind for event in second.events],
        )

    def test_enabled_policy_requires_explicit_allowlists_and_real_boolean(self) -> None:
        with self.assertRaisesRegex(ValidationError, "explicit provider"):
            DataAcquisitionPolicy(
                enabled=True,
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            )
        with self.assertRaisesRegex(ValidationError, "must be a boolean"):
            DataAcquisitionPolicy.from_dict({"enabled": "false"})
        with self.assertRaisesRegex(ValidationError, "disabled data acquisition"):
            DataAcquisitionPolicy(allowed_providers=("sec_edgar",))
        with self.assertRaisesRegex(ValidationError, "wildcard must be the only"):
            DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=("*", "sec_edgar"),
                allowed_capabilities=("*",),
                allowed_source_types=("*",),
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            )

    def test_broad_research_policy_covers_every_historical_signal_route(self) -> None:
        policy = broad_research_data_policy_v1()

        self.assertTrue(policy.enabled)
        self.assertEqual(policy.allowed_providers, ("*",))
        self.assertEqual(policy.allowed_capabilities, ("*",))
        self.assertEqual(policy.allowed_source_types, ("*",))
        self.assertEqual(policy.max_requests_per_cycle, 1_000)
        self.assertEqual(policy.max_requests_per_run, 10_000)

    def test_broad_research_policy_accepts_a_future_registered_data_type(self) -> None:
        class FutureAdapter:
            provider = "future_provider"
            source_types = ("satellite_imagery",)
            capabilities = ("alternative_data",)

            def acquire(self, request, **kwargs):
                return AcquisitionResult(
                    documents=(
                        document(
                            "future-source",
                            "Point-in-time registered alternative evidence.",
                            source_type="satellite_imagery",
                        ),
                    )
                )

        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(FutureAdapter(),),
            policy=broad_research_data_policy_v1(),
        )
        resolution = resolver.resolve(
            RawInfoRequest(
                "future-signal",
                "Read a newly registered source type.",
                ("satellite_imagery",),
            ),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertIn("satellite_imagery", resolver.available_source_types)

    def test_canonical_cik_routes_company_facts_and_archives_as_of_subset(self) -> None:
        observed_ciks: list[str] = []

        class Client:
            transport = None

            def company_facts(self, cik):
                observed_ciks.append(cik)
                return {
                    "cik": cik,
                    "facts": {
                        "us-gaap": {
                            "Revenue": {
                                "label": "Revenue",
                                "units": {
                                    "USD": [
                                        {"filed": "2024-12-31", "val": 10},
                                        {"filed": "2026-01-01", "val": 99},
                                    ]
                                },
                            }
                        }
                    },
                }

        policy = DataAcquisitionPolicy(
            enabled=True,
            allowed_providers=("sec_edgar",),
            allowed_capabilities=("financial_statements",),
            allowed_source_types=("sec_company_facts",),
            max_requests_per_cycle=1,
            max_requests_per_run=1,
        )
        store = RawInfoStore()
        request = RawInfoRequest(
            "facts", "Read filed company facts.", ("sec_company_facts",)
        )
        resolution = EvidenceResolver(
            store,
            adapters=(SecCompanyFactsAdapter(Client()),),
            policy=policy,
        ).resolve(
            request,
            company_id="cik_0000001234",
            identity={},
            as_of=AS_OF,
        )
        self.assertEqual(observed_ciks, ["0000001234"])
        scoped = store.load(resolution.documents[0].document_id, as_of=AS_OF)
        self.assertIn("2024-12-31", scoped.content)
        self.assertNotIn("2026-01-01", scoped.content)
        archived = [
            item
            for item in store.search(
                "cik_0000001234", as_of=AS_OF + timedelta(days=1_000)
            )
            if item.source_type == "sec_company_facts_raw_response"
        ]
        self.assertEqual(len(archived), 1)
        self.assertIn("2026-01-01", archived[0].content)

    def test_source_alias_authorization_matches_signal_request_semantics(self) -> None:
        class Client:
            transport = None

            def company_facts(self, cik):
                return {
                    "cik": cik,
                    "facts": {
                        "us-gaap": {
                            "Revenue": {
                                "units": {
                                    "USD": [
                                        {"filed": "2025-01-10", "val": 10}
                                    ]
                                }
                            }
                        }
                    },
                }

        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(SecCompanyFactsAdapter(Client()),),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=("sec_edgar",),
                allowed_capabilities=("financial_statements",),
                allowed_source_types=("sec_company_facts",),
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            ),
        )

        resolution = resolver.resolve(
            RawInfoRequest(
                "signal:revenue_growth_yoy:v1",
                "Measure revenue growth.",
                ("financials",),
            ),
            company_id="cik_0000001234",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertIn("financials", resolver.available_source_types)

    def test_generic_filing_request_prefers_core_forms_and_skips_failed_body(self) -> None:
        attempted: list[str] = []

        class Client:
            transport = None

            def recent_filings_as_of(self, cik, as_of_date):
                def filing(form, accession, day):
                    return SimpleNamespace(
                        form=form,
                        accession_number=accession,
                        filing_date=day,
                        accepted_at=None,
                        source_url=f"https://example.test/{accession}",
                    )

                return [
                    filing("SD", "sd", date(2025, 1, 14)),
                    filing("4", "four", date(2025, 1, 13)),
                    filing("8-K", "bad-8k", date(2025, 1, 12)),
                    filing("10-Q", "good-10q", date(2025, 1, 11)),
                    filing("10-K", "good-10k", date(2025, 1, 10)),
                ]

            def filing_document_text(self, filing):
                attempted.append(filing.form)
                if filing.accession_number == "bad-8k":
                    raise RuntimeError("one archive object is unavailable")
                return f"{filing.form} point-in-time body"

        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(SecFilingAdapter(Client()),),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=("sec_edgar",),
                allowed_capabilities=("filing_documents",),
                allowed_source_types=("filing",),
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            ),
        )
        resolution = resolver.resolve(
            RawInfoRequest(
                "filings",
                "Read decision-relevant filings.",
                ("filing",),
                max_documents=2,
            ),
            company_id="cik_0000001234",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(attempted, ["8-K", "10-Q", "10-K"])
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(
            [
                resolver.store.load(item.document_id, as_of=AS_OF).metadata["form"]
                for item in resolution.documents
            ],
            ["10-Q", "10-K"],
        )

    def test_stable_signal_source_aliases_route_and_materialize_price_metadata(self) -> None:
        self.assertIn("financials", SecCompanyFactsAdapter.source_types)

        bars = tuple(
            PriceBar(
                symbol="ISSUER",
                as_of_date=date(2024, 7, 1) + timedelta(days=index),
                open=100.0 + index,
                high=101.0 + index,
                low=99.0 + index,
                close=100.0 + index,
                volume=1_000,
                source="massive",
                retrieved_at=AS_OF,
                adjusted_close=100.0 + index,
            )
            for index in range(130)
        )
        policy = DataAcquisitionPolicy(
            enabled=True,
            allowed_providers=("massive",),
            allowed_capabilities=("price_daily",),
            allowed_source_types=("market_data",),
            max_requests_per_cycle=1,
            max_requests_per_run=1,
        )
        store = RawInfoStore()
        resolution = EvidenceResolver(
            store,
            adapters=(HistoricalPriceAdapter("massive", lambda *_: bars),),
            policy=policy,
        ).resolve(
            RawInfoRequest(
                "prices",
                "Read point-in-time prices.",
                ("market_data",),
                lookback_days=365,
            ),
            company_id="issuer_1",
            identity={"ticker": "ISSUER"},
            as_of=AS_OF,
        )

        self.assertIsNone(resolution.gap)
        materialized = store.load(resolution.documents[0].document_id, as_of=AS_OF)
        self.assertEqual(materialized.source_type, "market_data")
        self.assertEqual(len(materialized.metadata["prices"]), 130)
        self.assertEqual(materialized.metadata["prices"][-1], 229.0)

        spec = SignalSpec(
            signal_id="price_momentum_126d",
            version=1,
            category="market",
            description="Measure point-in-time price momentum.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            source_types=("market_data",),
            function="market.price_momentum_126d",
            parameters={
                "lookback_observations": 126,
                "positive_min": 0.2,
                "negative_max": -0.2,
            },
        )
        snapshot = FrozenSignalRegistry(1, "a" * 64, (spec,), {})
        result = SignalExecutor(snapshot, store).execute_batch(
            (spec.ref,), company_id="issuer_1", as_of=AS_OF
        )
        self.assertEqual(result.results[0].value, SignalValue.POSITIVE)

    def test_exact_original_spans_are_deterministic_and_never_rewritten(self) -> None:
        first = document("news_old", "ordinary " * 300, available_at=AS_OF - timedelta(days=3))
        second = document(
            "news_relevant",
            ("risk customer delay " * 180) + ("tail " * 500),
            available_at=AS_OF - timedelta(days=2),
        )
        store = RawInfoStore(documents=(first, second))
        request = RawInfoRequest(
            request_id="recent_news",
            description="Read recent company news.",
            source_types=("news",),
            lookback_days=30,
            max_documents=2,
            query="risk delay",
        )

        bundle = EvidenceResolver(store).resolve_basic_info(
            (request,), company_id="issuer_1", identity={}, as_of=AS_OF
        )
        resolution = bundle.requests[0]

        self.assertEqual(resolution.documents[0].document_id, "news_relevant")
        self.assertEqual(resolution.context_spans[0].document_id, "news_relevant")
        self.assertLessEqual(
            sum(len(item.exact_text) for item in resolution.context_spans), 48_000
        )
        for span in resolution.context_spans:
            raw = store.load(span.document_id)
            self.assertEqual(span.exact_text, raw.content[span.start : span.end])
            self.assertLessEqual(len(span.exact_text), 2_000)
        model_context = bundle.to_model_context_dict()
        self.assertNotIn("events", model_context["requests"][0])
        self.assertNotIn("summary", str(model_context).casefold())

    def test_filing_markup_uses_readable_query_windows_with_raw_lineage(self) -> None:
        raw = document(
            "quarterly_markup",
            (
                '<html><body><table><td style="'
                + ("color:#000000;" * 180)
                + '">Cash flow debt liquidity improved.</td>'
                "<td><xbrli:unit id=\"usd\">Operating cash flow remained positive."
                "</xbrli:unit></td></table></body></html>"
            ),
            source_type="10-q",
        )
        store = RawInfoStore(documents=(raw,))

        resolution = EvidenceResolver(store).resolve_basic_info(
            (
                RawInfoRequest(
                    "quarterly",
                    "Read cash flow and debt.",
                    ("10-q",),
                    query="cash flow debt liquidity",
                    max_documents=1,
                ),
            ),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        ).requests[0]

        self.assertTrue(resolution.context_spans)
        self.assertIn("Cash flow debt liquidity", resolution.context_spans[0].exact_text)
        for span in resolution.context_spans:
            self.assertEqual(span.exact_text, raw.content[span.start : span.end])
            self.assertFalse(span.exact_text.startswith("style="))
            before_start = raw.content[: span.start]
            self.assertLessEqual(before_start.rfind("<"), before_start.rfind(">"))

    def test_provider_ticker_news_requires_visible_issuer_match(self) -> None:
        target = document(
            "news_target",
            "Micron Technology announced HBM4 samples for customers.",
        )
        associated_only = document(
            "news_wrong_company",
            "ASP Isotopes began commercial Silicon-28 production.",
        )
        resolver = EvidenceResolver(
            RawInfoStore(documents=(associated_only, target))
        )
        request = RawInfoRequest(
            request_id="recent_company_news",
            description="Read company-specific product news.",
            source_types=("news",),
            lookback_days=30,
            max_documents=5,
            query="product",
        )

        resolution = resolver.resolve_basic_info(
            (request,),
            company_id="issuer_1",
            identity={
                "company_name": "Micron Technology Inc / MICRON TECHNOLOGY INC",
                "ticker": "MU",
                "identity_aliases": [
                    "MU",
                    "Micron Technology Inc / MICRON TECHNOLOGY INC",
                ],
            },
            as_of=AS_OF,
        ).requests[0]

        self.assertEqual(
            [item.document_id for item in resolution.documents],
            ["news_target"],
        )
        filter_event = next(
            item
            for item in resolution.events
            if item.kind == "news_documents_filtered"
        )
        self.assertEqual(
            filter_event.details["filtered_document_ids"],
            ["news_wrong_company"],
        )

    def test_legacy_news_json_ignores_secondary_ticker_association(self) -> None:
        unrelated = document(
            "news_secondary_ticker",
            json.dumps(
                {
                    "title": "Salesforce raises full-year guidance",
                    "summary": "Salesforce reported stronger subscription revenue.",
                    "ticker_sentiment": [
                        {"ticker": "AMD", "relevance_score": "0.62"}
                    ],
                }
            ),
        )
        relevant = document(
            "news_visible_issuer",
            json.dumps(
                {
                    "title": "AMD expands data-center product line",
                    "summary": "AMD described new accelerator availability.",
                    "ticker_sentiment": [
                        {"ticker": "AMD", "relevance_score": "1.0"}
                    ],
                }
            ),
        )
        resolution = EvidenceResolver(
            RawInfoStore(documents=(unrelated, relevant))
        ).resolve(
            RawInfoRequest("company_news", "Read issuer news.", ("news",)),
            company_id="issuer_1",
            identity={"company_name": "Advanced Micro Devices", "ticker": "AMD"},
            as_of=AS_OF,
        )

        self.assertEqual(
            [item.document_id for item in resolution.documents],
            ["news_visible_issuer"],
        )
        filter_events = [
            event
            for event in resolution.events
            if event.kind == "news_documents_filtered"
        ]
        self.assertEqual(
            filter_events[0].details["filtered_document_ids"],
            ["news_secondary_ticker"],
        )

    def test_specific_sec_forms_do_not_substitute_for_each_other(self) -> None:
        annual = document("annual", "Annual filing.", source_type="10-k")
        quarterly = document("quarterly", "Quarterly filing.", source_type="10-q")
        resolver = EvidenceResolver(RawInfoStore(documents=(annual, quarterly)))

        resolution = resolver.resolve(
            RawInfoRequest("quarter", "Read the quarterly filing.", ("10-q",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(
            [item.document_id for item in resolution.documents],
            ["quarterly"],
        )
        annual_only = EvidenceResolver(RawInfoStore(documents=(annual,))).resolve(
            RawInfoRequest("quarter", "Read the quarterly filing.", ("10-q",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )
        self.assertEqual(annual_only.status, "unresolved")
        self.assertEqual(annual_only.documents, ())
        mixed = EvidenceResolver(
            RawInfoStore(documents=(annual, document("issuer_news", "Issuer news.")))
        ).resolve(
            RawInfoRequest(
                "mixed",
                "Read quarterly filings or company news.",
                ("10-q", "company_news"),
            ),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )
        self.assertEqual(
            [item.document_id for item in mixed.documents],
            ["issuer_news"],
        )

    def test_visible_issuer_match_is_case_insensitive_for_name_derived_brand(self) -> None:
        target = document(
            "news_target",
            "Ciena announced that its CFO will present at an investor conference.",
        )
        resolver = EvidenceResolver(RawInfoStore(documents=(target,)))

        resolution = resolver.resolve_basic_info(
            (
                RawInfoRequest(
                    request_id="recent_company_news",
                    description="Read company-specific news.",
                    source_types=("news",),
                    lookback_days=30,
                    max_documents=5,
                    query="conference",
                ),
            ),
            company_id="issuer_1",
            identity={
                "company_name": "CIENA Corp / CIENA CORP",
                "ticker": "CIEN",
            },
            as_of=AS_OF,
        ).requests[0]

        self.assertEqual(
            [item.document_id for item in resolution.documents],
            ["news_target"],
        )

    def test_cached_market_context_projects_rows_to_requested_lookback(self) -> None:
        rows = [
            {
                "as_of_date": (AS_OF.date() - timedelta(days=offset)).isoformat(),
                "adjusted_close": float(100 - offset),
                "volume": 1_000 + offset,
            }
            for offset in range(90, -1, -1)
        ]
        raw = document(
            "cached_market",
            json.dumps(rows, sort_keys=True, separators=(",", ":")),
            source_type="market_data",
            available_at=AS_OF,
        )
        store = RawInfoStore(documents=(raw,))
        request = RawInfoRequest(
            request_id="recent_market",
            description="Read recent market confirmation.",
            source_types=("market_data",),
            lookback_days=30,
            max_documents=1,
        )

        resolution = EvidenceResolver(store).resolve_basic_info(
            (request,), company_id="issuer_1", identity={}, as_of=AS_OF
        ).requests[0]

        context = "".join(span.exact_text for span in resolution.context_spans)
        self.assertIn((AS_OF.date() - timedelta(days=30)).isoformat(), context)
        self.assertIn(AS_OF.date().isoformat(), context)
        self.assertNotIn((AS_OF.date() - timedelta(days=31)).isoformat(), context)
        self.assertLess(len(context), len(raw.content) / 2)
        for span in resolution.context_spans:
            self.assertEqual(span.exact_text, raw.content[span.start : span.end])

    def test_local_hit_skips_api_and_miss_appends_for_same_and_later_execution(self) -> None:
        cached = document("cached_news", "cached company news")
        adapter = FakeAdapter(AcquisitionResult((document("fetched_news", "risk delay"),)))
        policy = DataAcquisitionPolicy(
            enabled=True,
            allowed_providers=("fake_news",),
            allowed_capabilities=("news",),
            allowed_source_types=("news",),
            max_requests_per_cycle=2,
            max_requests_per_run=2,
        )
        local = EvidenceResolver(
            RawInfoStore(documents=(cached,)), adapters=(adapter,), policy=policy
        )
        request = RawInfoRequest("news", "Read news.", ("news",), max_documents=5)
        self.assertEqual(
            local.resolve(
                request, company_id="issuer_1", identity={}, as_of=AS_OF
            ).documents[0].document_id,
            "cached_news",
        )
        self.assertEqual(adapter.calls, 0)

        store = RawInfoStore()
        resolver = EvidenceResolver(store, adapters=(adapter,), policy=policy)
        first = resolver.resolve(request, company_id="issuer_1", identity={}, as_of=AS_OF)
        self.assertEqual(first.documents[0].document_id, "fetched_news")
        self.assertEqual(first.appended_documents[0].document_id, "fetched_news")
        self.assertEqual(adapter.calls, 1)
        second = resolver.resolve(request, company_id="issuer_1", identity={}, as_of=AS_OF)
        self.assertEqual(second.documents[0].document_id, "fetched_news")
        self.assertEqual(adapter.calls, 1)

    def test_provider_miss_falls_through_to_next_authorized_adapter(self) -> None:
        first = FailingAdapter(DataGapReason.PROVIDER_NO_DATA)
        first.provider = "primary_news"
        second = FakeAdapter(
            AcquisitionResult((document("fallback_news", "fallback evidence"),))
        )
        second.provider = "secondary_news"
        policy = DataAcquisitionPolicy(
            enabled=True,
            allowed_providers=("primary_news", "secondary_news"),
            allowed_capabilities=("news",),
            allowed_source_types=("news",),
            max_requests_per_cycle=2,
            max_requests_per_run=2,
        )

        resolution = EvidenceResolver(
            RawInfoStore(),
            adapters=(first, second),
            policy=policy,
        ).resolve(
            RawInfoRequest("news", "Read news.", ("news",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.documents[0].document_id, "fallback_news")
        self.assertEqual((first.calls, second.calls), (1, 1))
        self.assertEqual(
            [
                event.details["provider"]
                for event in resolution.events
                if event.kind == "acquisition_started"
            ],
            ["primary_news", "secondary_news"],
        )

    def test_unknown_unauthorized_quota_provider_and_historical_gaps(self) -> None:
        request = RawInfoRequest("news", "Read news.", ("news",))
        unknown = EvidenceResolver(RawInfoStore()).resolve(
            RawInfoRequest("unknown", "Unknown source.", ("new_oracle",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )
        self.assertEqual(unknown.gap.reason, DataGapReason.ADAPTER_MISSING)

        adapter = FakeAdapter()
        unauthorized = EvidenceResolver(RawInfoStore(), adapters=(adapter,)).resolve(
            request, company_id="issuer_1", identity={}, as_of=AS_OF
        )
        self.assertEqual(
            unauthorized.gap.reason, DataGapReason.EXTERNAL_NOT_AUTHORIZED
        )

        quota_policy = DataAcquisitionPolicy(
            enabled=True,
            allowed_providers=("fake_news",),
            allowed_capabilities=("news",),
            allowed_source_types=("news",),
            max_requests_per_cycle=1,
            max_requests_per_run=1,
        )
        quota = EvidenceResolver(
            RawInfoStore(), adapters=(adapter,), policy=quota_policy
        )
        self.assertEqual(
            quota.resolve(request, company_id="issuer_1", identity={}, as_of=AS_OF).gap.reason,
            DataGapReason.PROVIDER_NO_DATA,
        )
        self.assertEqual(
            quota.resolve(
                request,
                company_id="issuer_1",
                identity={},
                as_of=AS_OF + timedelta(days=1),
            ).gap.reason,
            DataGapReason.QUOTA_DEFERRED,
        )

        failure = FailingAdapter(DataGapReason.PROVIDER_ERROR)
        failed = EvidenceResolver(
            RawInfoStore(), adapters=(failure,), policy=quota_policy
        ).resolve(request, company_id="issuer_1", identity={}, as_of=AS_OF)
        self.assertEqual(failed.gap.reason, DataGapReason.PROVIDER_ERROR)

        for reason in (
            DataGapReason.MISSING_IDENTIFIER,
            DataGapReason.MATERIALIZATION_FAILED,
        ):
            typed = EvidenceResolver(
                RawInfoStore(),
                adapters=(FailingAdapter(reason),),
                policy=quota_policy,
            ).resolve(request, company_id="issuer_1", identity={}, as_of=AS_OF)
            self.assertEqual(typed.gap.reason, reason)

        outside_window = document(
            "stale_news",
            "stale source",
            available_at=AS_OF - timedelta(days=100),
        )
        no_match = EvidenceResolver(
            RawInfoStore(),
            adapters=(FakeAdapter(AcquisitionResult((outside_window,))),),
            policy=quota_policy,
        ).resolve(
            RawInfoRequest(
                "fresh_news", "Read fresh news.", ("news",), lookback_days=10
            ),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )
        self.assertEqual(no_match.gap.reason, DataGapReason.NO_MATCHING_DOCUMENTS)

        historical_request = RawInfoRequest(
            "profile", "Read historical profile.", ("company_profile",)
        )
        historical = EvidenceResolver(
            RawInfoStore(),
            adapters=(HistoricalUnavailableAdapter("vendor", ("company_profile",)),),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=("vendor",),
                allowed_capabilities=("company_profile",),
                allowed_source_types=("company_profile",),
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            ),
        ).resolve(
            historical_request,
            company_id="issuer_1",
            identity={"ticker": "TEST"},
            as_of=AS_OF,
        )
        self.assertEqual(
            historical.gap.reason, DataGapReason.HISTORICAL_DATA_UNAVAILABLE
        )

    def test_signal_computes_negative_word_count_while_basic_info_stays_raw(self) -> None:
        raw = document("news_negative", "Risk of loss and another delay. No summary.")
        store = RawInfoStore(documents=(raw,))
        resolver = EvidenceResolver(store)
        request = RawInfoRequest("news", "Read news.", ("news",), query="risk delay")
        bundle = resolver.resolve_basic_info(
            (request,), company_id="issuer_1", identity={}, as_of=AS_OF
        )
        self.assertIn("Risk of loss", bundle.requests[0].context_spans[0].exact_text)
        self.assertNotIn("negative_word_count", str(bundle.to_dict()))

        spec = SignalSpec(
            signal_id="negative_word_count",
            version=1,
            category="news",
            description="Count negative news terms.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            source_types=("news",),
            function="news.negative_word_count",
            parameters={"terms": ["risk", "loss", "delay"], "negative_count_min": 2},
        )
        snapshot = FrozenSignalRegistry(1, "a" * 64, (spec,), {})
        batch = SignalExecutor(snapshot, store, resolver=resolver).execute_batch(
            (spec.ref,), company_id="issuer_1", as_of=AS_OF
        )
        self.assertEqual(batch.results[0].value, SignalValue.NEGATIVE)
        self.assertEqual(batch.results[0].interpretation, "negative_word_count=3")
        self.assertEqual(batch.resolutions[0].documents[0].content_hash, raw.content_hash)

        older = document(
            "older_negative",
            "A material loss was reported.",
            available_at=AS_OF - timedelta(days=2),
        )
        latest = document(
            "latest_neutral",
            "Operations continued normally.",
            available_at=AS_OF - timedelta(days=1),
        )
        grounded = SignalExecutor(
            snapshot,
            RawInfoStore(documents=(latest, older)),
            resolver=EvidenceResolver(RawInfoStore(documents=(latest, older))),
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF)
        evidence = grounded.results[0].supporting_evidence
        self.assertEqual([item.document_id for item in evidence], ["older_negative"])
        self.assertIn("loss", evidence[0].exact_span)

    def test_file_backed_oracle_growth_does_not_create_evolution_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            oracle = RawInfoOracle.load_or_create(root / "raw_info")
            self.assertEqual(
                RawInfoOracle.load_or_create(root / "raw_info").oracle_id,
                oracle.oracle_id,
            )
            store = RawInfoStore(root / "raw_info")
            store.append(document("one", "source fact"))
            self.assertFalse((root / "state.json").exists())
            self.assertFalse((root / "cycle_state.json").exists())

    def test_capability_backlog_aggregates_gaps_and_marks_added_adapter_resolved(self) -> None:
        trajectory = {
            "case_id": "case_1",
            "basic_info_bundle": {
                "requests": [
                    {
                        "data_gap": {
                            "request_id": "recent_news",
                            "reason": "adapter_missing",
                            "message": "missing",
                            "source_types": ["news"],
                            "provider": None,
                        }
                    }
                ]
            },
            "signal_rounds": [],
        }
        open_report = aggregate_capability_gaps((trajectory, trajectory))
        self.assertEqual(open_report["items"][0]["occurrences"], 2)
        self.assertEqual(open_report["items"][0]["affected_case_ids"], ["case_1"])
        self.assertEqual(open_report["open_count"], 1)

        resolved = aggregate_capability_gaps(
            (trajectory,), available_source_types=("news",)
        )
        self.assertEqual(resolved["items"][0]["status"], "resolved")

        with_signal_need = aggregate_capability_gaps(
            (),
            signal_need_items=(
                {
                    "need": "  latest analyst estimate revisions  ",
                    "occurrences": 2,
                    "source_count": 2,
                },
            ),
        )
        self.assertEqual(
            with_signal_need["schema_version"], "capability-gap-report-v2"
        )
        self.assertEqual(
            with_signal_need["signal_need_items"],
            [
                {
                    "kind": "unmatched_signal_need",
                    "need": "latest analyst estimate revisions",
                    "stop_reason": "no_signal_match",
                    "occurrences": 2,
                    "source_count": 2,
                    "status": "open",
                }
            ],
        )
        self.assertEqual(with_signal_need["open_count"], 1)

        trajectory["basic_info_bundle"]["requests"][0]["data_gap"].update(
            {
                "reason": "external_not_authorized",
                "source_types": ["financials"],
                "provider": "sec_edgar",
            }
        )
        reauthorized = aggregate_capability_gaps(
            (trajectory,), available_source_types=("sec_company_facts",)
        )
        self.assertEqual(reauthorized["items"][0]["status"], "resolved")
