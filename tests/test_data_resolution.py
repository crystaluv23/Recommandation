from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.data.acquisition import (
    AlphaVantageTranscriptAdapter,
    FinnhubNewsAdapter,
    HistoricalPriceAdapter,
    HistoricalUnavailableAdapter,
    SecCompanyFactsAdapter,
    SecFilingAdapter,
    UnavailableProviderAdapter,
)
from stock_opportunity_agent.data.sources.core import PriceBar
from stock_opportunity_agent.data.sources.state import DataQuotaDeferred
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
    SignalExecutionStatus,
    SignalExecutor,
    SignalRetrievalPolicy,
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
    def test_finnhub_news_fallback_preserves_window_identity_and_literal_content(self) -> None:
        valid = {"datetime": (AS_OF - timedelta(days=1)).timestamp(),
                 "related": "ABC", "headline": "ABC announces customer contract",
                 "summary": "Signed agreement.", "url": "https://example.test/article"}
        items = [valid,
                 {**valid, "datetime": (AS_OF + timedelta(seconds=1)).timestamp()},
                 {**valid, "datetime": (AS_OF - timedelta(days=40)).timestamp()},
                 {**valid, "related": "OTHER"}, {**valid, "datetime": "bad"}]
        calls = []
        def news(*args):
            calls.append(args)
            return items
        adapter = FinnhubNewsAdapter(SimpleNamespace(company_news=news))
        resolver = EvidenceResolver(
            RawInfoStore(), adapters=(FailingAdapter(DataGapReason.QUOTA_DEFERRED), adapter),
            policy=DataAcquisitionPolicy(enabled=True, allowed_providers=("*",),
                allowed_capabilities=("*",), allowed_source_types=("*",),
                max_requests_per_cycle=4, max_requests_per_run=4),
        )
        result = resolver.resolve(
            RawInfoRequest("news", "Find customer contract", ("news",), lookback_days=30),
            company_id="issuer", identity={"ticker": "ABC"}, as_of=AS_OF,
        )
        self.assertEqual(result.status, "resolved")
        documents = resolver.load_documents(result, as_of=AS_OF)
        self.assertEqual(len(documents), 1)
        self.assertEqual(json.loads(documents[0].content), valid)
        self.assertEqual(documents[0].metadata["title"], valid["headline"])
        self.assertEqual(calls, [("ABC", (AS_OF - timedelta(days=30)).date(), AS_OF.date())])
        self.assertTrue(any(event.details.get("reason") == "quota_deferred" for event in result.events))


    def test_retrieval_contract_preserves_required_sources_before_limit(self) -> None:
        filing = document(
            "filing",
            '{"end":"2024-12-31","topic":"risk"}',
            source_type="filing",
        )
        newest_news = document("newest_news", "risk update")
        other_news = document(
            "other_news",
            "risk update two",
            available_at=AS_OF - timedelta(days=2),
        )
        request = RawInfoRequest(
            "mixed",
            "Read both filing and news evidence.",
            ("filing", "news"),
            max_documents=2,
            query="risk",
            required_source_groups=(("filing",), ("news",)),
        )

        resolution = EvidenceResolver(
            RawInfoStore(documents=(newest_news, other_news, filing))
        ).resolve(request, company_id="issuer_1", identity={}, as_of=AS_OF)

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(
            {item.document_id for item in resolution.documents},
            {"filing", "newest_news"},
        )
        self.assertTrue(resolution.coverage.contract_satisfied)
        self.assertEqual(resolution.coverage.satisfied_source_group_count, 2)

    def test_incomplete_period_contract_continues_authorized_acquisition(self) -> None:
        local = document(
            "local_financials",
            '{"facts":[{"end":"2024-12-31","value":20}]}',
            source_type="financials",
        )
        prior = document(
            "prior_financials",
            '{"facts":[{"end":"2023-12-31","value":10}]}',
            source_type="financials",
            available_at=AS_OF - timedelta(days=2),
        )
        adapter = FakeAdapter(AcquisitionResult((prior,)))
        adapter.source_types = ("financials",)
        adapter.capabilities = ("financials",)
        request = RawInfoRequest(
            "financial_comparison",
            "Read two comparable financial periods.",
            ("financials",),
            minimum_distinct_periods=2,
            minimum_period_span_days=330,
        )
        resolver = EvidenceResolver(
            RawInfoStore(documents=(local,)),
            adapters=(adapter,),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=(adapter.provider,),
                allowed_capabilities=("financials",),
                allowed_source_types=("financials",),
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            ),
        )

        resolution = resolver.resolve(
            request, company_id="issuer_1", identity={}, as_of=AS_OF
        )

        self.assertEqual(adapter.calls, 1)
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.coverage.observed_distinct_period_count, 2)
        self.assertGreaterEqual(resolution.coverage.observed_period_span_days, 330)

    def test_retrieval_contract_preserves_old_comparison_period_before_limit(
        self,
    ) -> None:
        recent = tuple(
            document(
                f"recent_{index}",
                (
                    '{"facts":[{"end":"2024-12-31","value":'
                    f"{20 + index}" + "}]}"
                ),
                source_type="financials",
                available_at=AS_OF - timedelta(hours=index + 1),
            )
            for index in range(4)
        )
        prior = document(
            "prior_period",
            '{"facts":[{"end":"2023-12-31","value":10}]}',
            source_type="financials",
            available_at=AS_OF - timedelta(days=30),
        )
        request = RawInfoRequest(
            "comparison",
            "Read current and prior periods.",
            ("financials",),
            max_documents=2,
            minimum_distinct_periods=2,
            minimum_period_span_days=330,
        )

        resolution = EvidenceResolver(
            RawInfoStore(documents=(*recent, prior))
        ).resolve(request, company_id="issuer_1", identity={}, as_of=AS_OF)

        self.assertEqual(resolution.status, "resolved")
        self.assertIn(
            "prior_period", {item.document_id for item in resolution.documents}
        )
        self.assertTrue(resolution.coverage.selection_truncated)

    def test_partial_basic_info_is_visible_but_signal_does_not_execute(self) -> None:
        partial = document(
            "one_period",
            '{"facts":[{"end":"2024-12-31","value":20}]}',
            source_type="financials",
        )
        store = RawInfoStore(documents=(partial,))
        resolver = EvidenceResolver(store)
        request = RawInfoRequest(
            "comparison",
            "Read a comparison.",
            ("financials",),
            minimum_distinct_periods=2,
        )
        bundle = resolver.resolve_basic_info(
            (request,), company_id="issuer_1", identity={}, as_of=AS_OF
        )
        basic_resolution = bundle.requests[0]
        self.assertEqual(basic_resolution.status, "unresolved")
        self.assertEqual(
            basic_resolution.gap.reason,
            DataGapReason.REQUIRED_COVERAGE_INCOMPLETE,
        )
        self.assertEqual(basic_resolution.documents[0].document_id, "one_period")
        self.assertIn("2024-12-31", basic_resolution.context_spans[0].exact_text)
        self.assertFalse(basic_resolution.coverage.contract_satisfied)

        calls: list[str] = []

        def should_not_run(spec, documents, as_of):
            calls.append(spec.ref)
            raise AssertionError("incomplete retrieval contract must gate execution")

        spec = SignalSpec(
            signal_id="comparison_signal",
            version=1,
            category="financial",
            description="Compare two periods.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            source_types=("financials",),
            function="test.comparison",
            retrieval_policy=SignalRetrievalPolicy(
                query_terms=("comparison",), minimum_distinct_periods=2
            ),
        )
        batch = SignalExecutor(
            FrozenSignalRegistry(1, "a" * 64, (spec,), {}),
            store,
            resolver=resolver,
            deterministic_functions={"test.comparison": should_not_run},
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF)
        self.assertEqual(calls, [])
        self.assertEqual(batch.results[0].value, SignalValue.UNAVAILABLE)
        self.assertEqual(
            batch.document_fingerprints[spec.ref][0].split(":")[0],
            "one_period",
        )

    def test_retrieval_contract_round_trips_in_signal_spec(self) -> None:
        spec = SignalSpec(
            signal_id="period_signal",
            version=1,
            category="financial",
            description="Read a bounded period series.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            source_types=("financials", "filing"),
            function="test.period",
            retrieval_policy=SignalRetrievalPolicy(
                query_terms=("revenue",),
                comparison_requirement="Compare current with prior year.",
                required_source_groups=(("financials", "filing"),),
                minimum_distinct_periods=2,
                minimum_period_span_days=330,
                minimum_observations=2,
            ),
        )

        restored = SignalSpec.from_dict(spec.to_dict())

        self.assertEqual(restored, spec)
        request = RawInfoRequest.from_dict(
            {
                "request_id": "period",
                "description": "Read periods.",
                "source_types": ["financials", "filing"],
                **restored.retrieval_policy.to_dict(),
            }
        )
        self.assertEqual(request.required_source_groups, (("financials", "filing"),))
        self.assertEqual(request.minimum_distinct_periods, 2)
        with self.assertRaisesRegex(ValidationError, "outside source_types"):
            RawInfoRequest(
                "invalid_group",
                "Reject undeclared source aliases.",
                ("financials",),
                required_source_groups=(("financials", "invented_provider"),),
            )

    def test_signal_resolution_control_failure_is_not_domain_unavailable(self) -> None:
        adapter = FailingAdapter(DataGapReason.PROVIDER_ERROR)
        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(adapter,),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=(adapter.provider,),
                allowed_capabilities=("news",),
                allowed_source_types=("news",),
                max_requests_per_cycle=1,
                max_requests_per_run=1,
            ),
        )
        spec = SignalSpec(
            signal_id="news_signal",
            version=1,
            category="news",
            description="Read news.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            source_types=("news",),
            function="test.news",
        )
        batch = SignalExecutor(
            FrozenSignalRegistry(1, "a" * 64, (spec,), {}),
            RawInfoStore(),
            resolver=resolver,
            deterministic_functions={"test.news": lambda *_args: None},
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF)

        self.assertEqual(
            batch.results[0].execution_status,
            SignalExecutionStatus.TRANSPORT_FAILED,
        )
        self.assertEqual(
            batch.results[0].execution_error_code,
            DataGapReason.PROVIDER_ERROR.value,
        )

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

    def test_unknown_provider_errors_remain_retryable(self) -> None:
        adapter = FailingAdapter(DataGapReason.PROVIDER_ERROR)
        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(adapter,),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=("fake_news",),
                allowed_capabilities=("news",),
                allowed_source_types=("news",),
                max_requests_per_cycle=3,
                max_requests_per_run=3,
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

        self.assertEqual(adapter.calls, 2)
        self.assertEqual(first.gap.reason, DataGapReason.PROVIDER_ERROR)
        self.assertEqual(second.gap.reason, DataGapReason.PROVIDER_ERROR)
        self.assertNotIn(
            "acquisition_failure_reused",
            [event.kind for event in second.events],
        )

        distinct_topic = resolver.resolve(
            RawInfoRequest(
                "signal:three", "Read compatible news.", ("news",), query="margin"
            ),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )
        self.assertEqual(adapter.calls, 3)
        self.assertEqual(distinct_topic.gap.reason, DataGapReason.PROVIDER_ERROR)

    def test_quota_failure_reuse_preserves_unknown_retry_time(self) -> None:
        class QuotaAdapter(FakeAdapter):
            def acquire(self, request, **kwargs):
                self.calls += 1
                raise DataQuotaDeferred(
                    self.provider, None, "provider quota unavailable"
                )

        adapter = QuotaAdapter()
        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(adapter,),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=(adapter.provider,),
                allowed_capabilities=("news",),
                allowed_source_types=("news",),
                max_requests_per_cycle=2,
                max_requests_per_run=2,
            ),
        )
        request = RawInfoRequest("news", "Read news.", ("news",))

        first = resolver.resolve(
            request, company_id="issuer_1", identity={}, as_of=AS_OF
        )
        second = resolver.resolve(
            request, company_id="issuer_1", identity={}, as_of=AS_OF
        )

        self.assertEqual(adapter.calls, 1)
        self.assertEqual(first.gap.reason, DataGapReason.QUOTA_DEFERRED)
        reused = next(
            event
            for event in second.events
            if event.kind == "acquisition_failure_reused"
        )
        self.assertTrue(reused.details["retryable"])
        self.assertIsNone(reused.details["next_retry_at"])

    def test_quota_failure_retries_after_known_reset(self) -> None:
        class ExpiredQuotaAdapter(FakeAdapter):
            def acquire(self, request, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise DataQuotaDeferred(
                        self.provider,
                        datetime(2020, 1, 1, tzinfo=timezone.utc),
                        "old quota window",
                    )
                return AcquisitionResult((document("recovered", "fresh news"),))

        adapter = ExpiredQuotaAdapter()
        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(adapter,),
            policy=DataAcquisitionPolicy(
                enabled=True,
                allowed_providers=(adapter.provider,),
                allowed_capabilities=("news",),
                allowed_source_types=("news",),
                max_requests_per_cycle=2,
                max_requests_per_run=2,
            ),
        )
        request = RawInfoRequest("news", "Read news.", ("news",))
        first = resolver.resolve(
            request, company_id="issuer_1", identity={}, as_of=AS_OF
        )
        second = resolver.resolve(
            request, company_id="issuer_1", identity={}, as_of=AS_OF
        )

        self.assertEqual(first.gap.reason, DataGapReason.QUOTA_DEFERRED)
        self.assertEqual(second.status, "resolved")
        self.assertEqual(adapter.calls, 2)

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

    def test_sec_history_manifest_recovers_foreign_issuer_generic_filing(self) -> None:
        calls: list[str] = []

        class Client:
            transport = None

            def submissions(self, cik):
                return {
                    "filings": {
                        "recent": {"normalized": []},
                        "files": [
                            {
                                "name": "unrelated.json",
                                "filingFrom": "2010-01-01",
                                "filingTo": "2011-01-01",
                            },
                            {
                                "name": "target.json",
                                "filingFrom": "2024-01-01",
                                "filingTo": "2025-01-10",
                            },
                        ],
                    }
                }

            def filings_from_arrays_as_of(self, cik, arrays, as_of_date):
                return list(arrays["normalized"])

            def historical_submissions(self, filename):
                calls.append(filename)
                return {
                    "normalized": [
                        SimpleNamespace(
                            form="40-F",
                            accession_number="foreign-annual",
                            filing_date=date(2025, 1, 10),
                            accepted_at=datetime(
                                2025, 1, 10, 18, tzinfo=timezone.utc
                            ),
                            source_url="https://example.test/foreign-annual",
                        )
                    ]
                }

            def filing_document_text(self, filing):
                calls.append(filing.accession_number)
                return "Foreign issuer annual operating report."

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
        result = resolver.resolve(
            RawInfoRequest("risk", "Read issuer risk disclosures.", ("filing",)),
            company_id="cik_0000001234",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(calls, ["target.json", "foreign-annual"])
        loaded = resolver.load_documents(result, as_of=AS_OF)
        self.assertEqual(loaded[0].metadata["form"], "40-F")

    def test_sec_history_scan_deduplicates_accessions_before_body_fetch(self) -> None:
        body_calls: list[str] = []
        duplicate = SimpleNamespace(
            form="10-K",
            accession_number="same-accession",
            filing_date=date(2025, 1, 10),
            accepted_at=None,
            source_url="https://example.test/same-accession",
        )

        class Client:
            transport = None

            def submissions(self, cik):
                return {
                    "filings": {
                        "recent": {"normalized": [duplicate]},
                        "files": [
                            {
                                "name": "history.json",
                                "filingFrom": "2024-01-01",
                                "filingTo": "2025-01-10",
                            }
                        ],
                    }
                }

            def filings_from_arrays_as_of(self, cik, arrays, as_of_date):
                return list(arrays["normalized"])

            def historical_submissions(self, filename):
                return {"normalized": [duplicate]}

            def filing_document_text(self, filing):
                body_calls.append(filing.accession_number)
                return "Annual report body."

        result = SecFilingAdapter(Client()).acquire(
            RawInfoRequest("filing", "Read annual report.", ("filing",)),
            company_id="issuer_1",
            identity={"cik": "1234"},
            as_of=AS_OF,
        )

        self.assertEqual(len(result.documents), 1)
        self.assertEqual(body_calls, ["same-accession"])

    def test_sec_history_page_failure_and_cap_remain_auditable(self) -> None:
        requested: list[str] = []
        recovered = SimpleNamespace(
            form="6-K",
            accession_number="recovered-current-report",
            filing_date=date(2025, 1, 9),
            accepted_at=None,
            source_url="https://example.test/recovered-current-report",
        )

        class Client:
            transport = None

            def submissions(self, cik):
                return {
                    "filings": {
                        "recent": {"normalized": []},
                        "files": [
                            {
                                "name": f"page-{index}.json",
                                "filingFrom": "2024-01-01",
                                "filingTo": f"2025-01-{10 - index:02d}",
                            }
                            for index in range(4)
                        ],
                    }
                }

            def filings_from_arrays_as_of(self, cik, arrays, as_of_date):
                return list(arrays["normalized"])

            def historical_submissions(self, filename):
                requested.append(filename)
                if filename == "page-0.json":
                    raise RuntimeError("bounded page failure")
                return {
                    "normalized": (
                        [recovered] if filename == "page-1.json" else []
                    )
                }

            def filing_document_text(self, filing):
                return "Foreign issuer current operating report."

        result = SecFilingAdapter(Client()).acquire(
            RawInfoRequest("filing", "Read operating reports.", ("filing",)),
            company_id="issuer_1",
            identity={"cik": "1234"},
            as_of=AS_OF,
        )
        scan = next(event for event in result.events if event.kind == "sec_history_scan")

        self.assertEqual(requested, ["page-0.json", "page-1.json", "page-2.json"])
        self.assertTrue(scan.details["history_truncated"])
        self.assertEqual(scan.details["failed_file_count"], 1)
        self.assertEqual(result.documents[0].metadata["form"], "6-K")

    def test_truncated_history_without_body_is_coverage_incomplete(self) -> None:
        class Client:
            transport = None

            def submissions(self, cik):
                return {
                    "filings": {
                        "recent": {"normalized": []},
                        "files": [
                            {
                                "name": f"page-{index}.json",
                                "filingFrom": "2024-01-01",
                                "filingTo": f"2025-01-{10 - index:02d}",
                            }
                            for index in range(4)
                        ],
                    }
                }

            def filings_from_arrays_as_of(self, cik, arrays, as_of_date):
                return list(arrays["normalized"])

            def historical_submissions(self, filename):
                return {"normalized": []}

        with self.assertRaises(AcquisitionFailure) as ctx:
            SecFilingAdapter(Client()).acquire(
                RawInfoRequest("filing", "Read operating reports.", ("filing",)),
                company_id="issuer_1",
                identity={"cik": "1234"},
                as_of=AS_OF,
            )
        self.assertEqual(
            ctx.exception.reason,
            DataGapReason.REQUIRED_COVERAGE_INCOMPLETE,
        )

    def test_foreign_sec_forms_match_generic_but_not_other_exact_forms(self) -> None:
        foreign = RawInfoDocument.create(
            document_id="foreign_annual",
            company_id="issuer_1",
            source_type="40-f",
            published_at=AS_OF - timedelta(days=1),
            available_at=AS_OF - timedelta(days=1),
            content="Foreign annual report.",
            metadata={"form": "40-F"},
        )
        generic = EvidenceResolver(RawInfoStore(documents=(foreign,))).resolve(
            RawInfoRequest("generic", "Read an annual report.", ("filing",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )
        exact_wrong = EvidenceResolver(RawInfoStore(documents=(foreign,))).resolve(
            RawInfoRequest("domestic", "Read the exact 10-K.", ("10-k",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(generic.status, "resolved")
        self.assertEqual(exact_wrong.status, "unresolved")
        self.assertEqual(exact_wrong.documents, ())

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

    def test_resolution_reports_query_coverage_and_deduplicates_source_copies(
        self,
    ) -> None:
        duplicate_old = document(
            "duplicate-old",
            "Management raised annual guidance.",
            available_at=AS_OF - timedelta(days=3),
        )
        duplicate_new = document(
            "duplicate-new",
            "Management raised annual guidance.",
            available_at=AS_OF - timedelta(days=1),
        )
        irrelevant = document(
            "irrelevant",
            "Routine corporate administration.",
            available_at=AS_OF - timedelta(days=2),
        )

        resolution = EvidenceResolver(
            RawInfoStore(documents=(duplicate_new, duplicate_old, irrelevant))
        ).resolve(
            RawInfoRequest(
                "guidance",
                "Read guidance.",
                ("news",),
                max_documents=1,
                query="annual guidance",
            ),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )

        self.assertEqual(
            [item.document_id for item in resolution.documents],
            ["duplicate-old"],
        )
        self.assertEqual(resolution.coverage.eligible_document_count, 2)
        self.assertEqual(resolution.coverage.selected_document_count, 1)
        self.assertEqual(resolution.coverage.query_matched_document_count, 1)
        self.assertEqual(resolution.coverage.query_status, "matched")
        self.assertEqual(resolution.coverage.deduplicated_document_count, 1)
        self.assertTrue(resolution.coverage.selection_truncated)
        self.assertEqual(
            type(resolution).from_dict(resolution.to_dict()).coverage,
            resolution.coverage,
        )
        legacy = resolution.to_dict()
        legacy.pop("coverage")
        restored_legacy = type(resolution).from_dict(legacy)
        self.assertEqual(restored_legacy.coverage.query_status, "not_recorded")
        self.assertIsNone(restored_legacy.coverage.query_matched_document_count)

    def test_basic_info_context_budget_keeps_one_span_per_resolved_request(
        self,
    ) -> None:
        documents = tuple(
            document(
                f"document_{index}",
                f"request-{index} " + (f"evidence-{index} " * 2_000),
                source_type=f"source_{index}",
            )
            for index in range(4)
        )
        requests = tuple(
            RawInfoRequest(
                f"request_{index}",
                f"Read source {index}.",
                (f"source_{index}",),
                max_documents=1,
            )
            for index in range(4)
        )

        store = RawInfoStore(documents=documents)
        bundle = EvidenceResolver(store).resolve_basic_info(
            requests,
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
        )

        self.assertTrue(
            all(resolution.context_spans for resolution in bundle.requests)
        )
        self.assertLessEqual(
            sum(
                len(span.exact_text)
                for resolution in bundle.requests
                for span in resolution.context_spans
            ),
            48_000,
        )
        for resolution in bundle.requests:
            first = resolution.context_spans[0]
            self.assertEqual(first.document_id, resolution.documents[0].document_id)
            self.assertEqual(
                first.exact_text,
                store.load(first.document_id).content[first.start : first.end],
            )

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
        second = resolver.resolve(
            request, company_id="issuer_1", identity={}, as_of=AS_OF
        )
        self.assertEqual(second.documents[0].document_id, "fetched_news")
        self.assertEqual(adapter.calls, 1)

    def test_empty_local_selection_continues_to_authorized_acquisition(self) -> None:
        irrelevant = document("irrelevant", "routine legal boilerplate")
        relevant = document("relevant", "material guidance outlook discussion")
        adapter = FakeAdapter(AcquisitionResult((relevant,)))
        policy = DataAcquisitionPolicy(
            enabled=True,
            allowed_providers=("fake_news",),
            allowed_capabilities=("news",),
            allowed_source_types=("news",),
            max_requests_per_cycle=1,
            max_requests_per_run=1,
        )
        resolver = EvidenceResolver(
            RawInfoStore(documents=(irrelevant,)), adapters=(adapter,), policy=policy
        )

        resolution = resolver.resolve(
            RawInfoRequest("guidance", "Read guidance.", ("news",)),
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
            select_documents=lambda rows, _request: (
                row for row in rows if "guidance" in row.content
            ),
        )

        self.assertEqual(adapter.calls, 1)
        self.assertEqual(
            tuple(item.document_id for item in resolution.documents), ("relevant",)
        )
        self.assertEqual(
            tuple(item.document_id for item in resolution.appended_documents),
            ("relevant",),
        )

    def test_document_selector_falls_through_and_rejects_invented_documents(self) -> None:
        irrelevant = FakeAdapter(
            AcquisitionResult((document("primary", "routine boilerplate"),))
        )
        irrelevant.provider = "primary_news"
        relevant = FakeAdapter(
            AcquisitionResult((document("secondary", "guidance evidence"),))
        )
        relevant.provider = "secondary_news"
        policy = DataAcquisitionPolicy(
            enabled=True,
            allowed_providers=("primary_news", "secondary_news"),
            allowed_capabilities=("news",),
            allowed_source_types=("news",),
            max_requests_per_cycle=2,
            max_requests_per_run=2,
        )
        resolver = EvidenceResolver(
            RawInfoStore(), adapters=(irrelevant, relevant), policy=policy
        )
        request = RawInfoRequest("guidance", "Read guidance.", ("news",))

        resolution = resolver.resolve(
            request,
            company_id="issuer_1",
            identity={},
            as_of=AS_OF,
            select_documents=lambda rows, _request: (
                row for row in rows if "guidance" in row.content
            ),
        )

        self.assertEqual((irrelevant.calls, relevant.calls), (1, 1))
        self.assertEqual(resolution.documents[0].document_id, "secondary")
        with self.assertRaisesRegex(ValidationError, "unique unchanged eligible"):
            resolver.resolve(
                request,
                company_id="issuer_1",
                identity={},
                as_of=AS_OF,
                select_documents=lambda _rows, _request: (
                    document("invented", "guidance evidence"),
                ),
            )
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
        self.assertEqual(resolved["items"][0]["status"], "open")
        actual_resolution = {
            "case_id": "case_1",
            "basic_info_bundle": {
                "requests": [
                    {
                        "request": {
                            "request_id": "recent_news",
                            "description": "Recent news",
                            "source_types": ["news"],
                            "max_documents": 1,
                        },
                        "status": "resolved",
                        "data_gap": None,
                    }
                ]
            },
            "signal_rounds": [],
        }
        resolved = aggregate_capability_gaps((trajectory, actual_resolution))
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
            with_signal_need["schema_version"], "capability-gap-report-v3"
        )
        self.assertEqual(
            with_signal_need["signal_need_items"],
            [
                {
                    "kind": "unmatched_signal_need",
                    "need_ref": with_signal_need["signal_need_items"][0]["need_ref"],
                    "need": "latest analyst estimate revisions",
                    "sources": [],
                    "source_rounds": [],
                    "source_fingerprints": [],
                    "stop_reasons": ["no_signal_match"],
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
        self.assertEqual(reauthorized["items"][0]["status"], "open")

    def test_capability_backlog_separates_signal_technical_failures(self) -> None:
        trajectory = {
            "case_id": "case_technical",
            "basic_info_bundle": {"requests": []},
            "signal_rounds": [
                {
                    "batch": {
                        "resolutions": [],
                        "results": [
                            {
                                "signal_id": "guidance_change",
                                "version": 1,
                                "execution": {
                                    "status": "validation_failed",
                                    "error_code": "invalid_literal",
                                    "error_message": "citation was not literal",
                                },
                            },
                            {
                                "signal_id": "customer_order",
                                "version": 1,
                                "execution": {"status": "domain_unavailable"},
                            },
                        ],
                    }
                }
            ],
        }

        report = aggregate_capability_gaps((trajectory,))

        self.assertEqual(report["signal_need_items"], [])
        self.assertEqual(
            report["technical_failures"],
            [
                {
                    "case_id": "case_technical",
                    "signal_ref": "guidance_change:v1",
                    "status": "validation_failed",
                    "error_code": "invalid_literal",
                    "error_message": "citation was not literal",
                }
            ],
        )
