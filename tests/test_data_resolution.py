from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.data.acquisition import (
    HistoricalUnavailableAdapter,
    SecCompanyFactsAdapter,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    AcquisitionFailure,
    AcquisitionResult,
    DataAcquisitionPolicy,
    DataGapReason,
    EvidenceResolver,
    RawInfoRequest,
)
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
    def test_company_facts_archives_full_response_but_exposes_only_as_of_subset(self) -> None:
        class Client:
            transport = None

            def company_facts(self, cik):
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
            company_id="issuer_1",
            identity={"cik": "1234"},
            as_of=AS_OF,
        )
        scoped = store.load(resolution.documents[0].document_id, as_of=AS_OF)
        self.assertIn("2024-12-31", scoped.content)
        self.assertNotIn("2026-01-01", scoped.content)
        archived = [
            item
            for item in store.search(
                "issuer_1", as_of=AS_OF + timedelta(days=1_000)
            )
            if item.source_type == "sec_company_facts_raw_response"
        ]
        self.assertEqual(len(archived), 1)
        self.assertIn("2026-01-01", archived[0].content)

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
            quota.resolve(request, company_id="issuer_1", identity={}, as_of=AS_OF).gap.reason,
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
            policy=quota_policy,
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

    def test_file_backed_oracle_growth_does_not_create_evolution_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = RawInfoStore(root / "raw_info")
            store.append(document("one", "source fact"))
            self.assertFalse((root / "state.json").exists())
            self.assertFalse((root / "cycle_state.json").exists())
