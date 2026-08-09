import gzip
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data import (
    AlphaVantageClient,
    DataCapability,
    DataQuotaDeferred,
    DataSourceError,
    DocumentRecord,
    DocumentStore,
    FREE_DATA_SOURCES,
    FinnhubClient,
    FredClient,
    ManagedHttpTransport,
    MassiveClient,
    OpenFigiClient,
    PriceBar,
    RawCacheKey,
    RawDataCache,
    RequestLedger,
    RequestStatus,
    SecEdgarClient,
    SecurityListing,
    SourceBudget,
    SourceQuota,
    StooqClient,
    build_research_packet,
    chunk_document_text,
    company_profile_from_features,
    create_source,
    documents_as_of,
    documents_to_evidence,
    filing_to_evidence,
    latest_features_by_name,
    normalize_alpha_vantage_overview,
    normalize_price_features,
    normalize_sec_company_facts,
    registered_sources,
    select_source_for_capability,
    source_catalog_by_capability,
    source_plan_by_capability,
)
from stock_opportunity_agent.data.sources.core import decode_response_text
from stock_opportunity_agent.models import (
    Catalyst,
    CatalystStatus,
    CompanyProfile,
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    FeatureRecord,
    TickerRef,
    ValidationError,
    VersionStamp,
)


class FakeJsonTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_json(self, url, headers):
        self.calls.append((url, headers))
        return self.responses[url]


class FakeHttpTransport(FakeJsonTransport):
    def __init__(self, responses=None, text_responses=None, post_responses=None):
        super().__init__(responses or {})
        self.text_responses = text_responses or {}
        self.post_responses = post_responses or {}
        self.posts = []

    def get_text(self, url, headers):
        self.calls.append((url, headers))
        return self.text_responses[url]

    def post_json(self, url, headers, payload):
        self.posts.append((url, headers, payload))
        return self.post_responses[url]


class FakeClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def set(self, now):
        self.now = now


class FreeDataCatalogTests(TestCase):
    def test_catalog_covers_core_mvp_needs_without_single_vendor_lock_in(self) -> None:
        names = {source.name for source in FREE_DATA_SOURCES}

        self.assertIn("SEC EDGAR", names)
        self.assertIn("Massive", names)
        self.assertIn("Alpha Vantage", names)
        self.assertIn("FRED", names)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.PRICE_DAILY)), 2)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.FILINGS)), 1)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.NEWS)), 2)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.MACRO_SERIES)), 2)

    def test_capability_plan_selects_first_available_source(self) -> None:
        plan = source_plan_by_capability(DataCapability.PRICE_DAILY)

        self.assertEqual(plan.preferred_sources[0], "massive")
        self.assertEqual(
            select_source_for_capability(DataCapability.PRICE_DAILY, ["alpha_vantage", "stooq"]),
            "stooq",
        )


class HttpTransportTests(TestCase):
    def test_decode_response_text_handles_gzip_header(self) -> None:
        body = gzip.compress(b'{"ok": true}')

        self.assertEqual(decode_response_text(body, "gzip"), '{"ok": true}')

    def test_decode_response_text_detects_gzip_magic_bytes(self) -> None:
        body = gzip.compress(b"symbol,name\nAAPL,Apple Inc.\n")

        self.assertIn("AAPL", decode_response_text(body))


class SecEdgarClientTests(TestCase):
    def test_company_tickers_exchange_are_normalized_for_universe(self) -> None:
        url = "https://www.sec.gov/files/company_tickers_exchange.json"
        transport = FakeJsonTransport(
            {
                url: {
                    "fields": ["cik", "name", "ticker", "exchange"],
                    "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
                }
            }
        )
        client = SecEdgarClient("test@example.com", transport=transport)

        listings = client.company_tickers_exchange()

        self.assertEqual(listings[0].symbol, "AAPL")
        self.assertEqual(listings[0].cik, "0000320193")
        self.assertEqual(listings[0].source, "sec_edgar")

    def test_recent_filings_are_filtered_as_of_date_and_have_source_urls(self) -> None:
        url = "https://data.sec.gov/submissions/CIK0000320193.json"
        transport = FakeJsonTransport(
            {
                url: {
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
                            "filingDate": ["2026-04-30", "2026-05-03"],
                            "reportDate": ["2026-03-31", "2026-06-30"],
                            "acceptanceDateTime": [
                                "2026-04-30T17:30:00-04:00",
                                "2026-05-03T12:00:00-04:00",
                            ],
                            "form": ["10-Q", "10-Q"],
                            "primaryDocument": ["aapl-20260331.htm", "aapl-20260630.htm"],
                        }
                    }
                }
            }
        )
        client = SecEdgarClient("test@example.com", transport=transport)

        filings = client.recent_filings_as_of("320193", date(2026, 5, 1))

        self.assertEqual(len(filings), 1)
        self.assertEqual(filings[0].cik, "0000320193")
        self.assertIn("000032019326000001", filings[0].source_url)
        self.assertEqual(
            filings[0].accepted_at.isoformat(), "2026-04-30T21:30:00+00:00"
        )
        self.assertEqual(transport.calls[0][1]["User-Agent"], "test@example.com")

    def test_historical_submissions_require_safe_exact_filename(self) -> None:
        filename = "CIK0000320193-submissions-001.json"
        url = f"https://data.sec.gov/submissions/{filename}"
        transport = FakeJsonTransport({url: {"accessionNumber": []}})
        client = SecEdgarClient("test@example.com", transport=transport)

        self.assertEqual(client.historical_submissions(filename), {"accessionNumber": []})
        with self.assertRaisesRegex(ValidationError, "unsafe"):
            client.historical_submissions("../secret.json")
        self.assertEqual(len(transport.calls), 1)

    def test_filing_metadata_becomes_source_linked_evidence(self) -> None:
        url = "https://data.sec.gov/submissions/CIK0000320193.json"
        transport = FakeJsonTransport(
            {
                url: {
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000320193-26-000001"],
                            "filingDate": ["2026-04-30"],
                            "reportDate": ["2026-03-31"],
                            "form": ["10-Q"],
                            "primaryDocument": ["aapl-20260331.htm"],
                        }
                    }
                }
            }
        )
        filing = SecEdgarClient("test@example.com", transport=transport).recent_filings_as_of(
            "320193", date(2026, 5, 1)
        )[0]

        item = filing_to_evidence(filing, date(2026, 5, 1))

        self.assertEqual(item.source_id, "sec:0000320193:0000320193-26-000001")
        self.assertEqual(item.published_date, date(2026, 4, 30))


class AlphaVantageClientTests(TestCase):
    def test_listing_status_rows_are_normalized(self) -> None:
        base = "https://www.alphavantage.co/query"
        response_url = base + "?function=LISTING_STATUS&state=active&apikey=test-key"
        transport = FakeHttpTransport(
            text_responses={
                response_url: (
                    "symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
                    "IBM,International Business Machines Corp,NYSE,Stock,1915-11-11,null,Active\n"
                )
            }
        )
        client = AlphaVantageClient("test-key", transport=transport)

        listings = client.listing_status()

        self.assertEqual(listings[0].symbol, "IBM")
        self.assertEqual(listings[0].ipo_date, date(1915, 11, 11))
        self.assertEqual(listings[0].source, "alpha_vantage")

    def test_listing_status_rejects_non_csv_provider_response(self) -> None:
        base = "https://www.alphavantage.co/query"
        response_url = base + "?function=LISTING_STATUS&state=active&apikey=test-key"
        transport = FakeHttpTransport(text_responses={response_url: "{}"})
        client = AlphaVantageClient("test-key", transport=transport)

        with self.assertRaises(DataSourceError):
            client.listing_status()

    def test_daily_prices_are_normalized_and_sorted(self) -> None:
        base = "https://www.alphavantage.co/query"
        response_url = (
            base
            + "?function=TIME_SERIES_DAILY&symbol=IBM&outputsize=compact&apikey=test-key"
        )
        transport = FakeJsonTransport(
            {
                response_url: {
                    "Time Series (Daily)": {
                        "2026-05-02": {
                            "1. open": "10.0",
                            "2. high": "11.0",
                            "3. low": "9.5",
                            "4. close": "10.5",
                            "5. volume": "1000",
                        },
                        "2026-05-01": {
                            "1. open": "9.0",
                            "2. high": "10.0",
                            "3. low": "8.5",
                            "4. close": "9.5",
                            "5. volume": "900",
                        },
                    }
                }
            }
        )
        client = AlphaVantageClient("test-key", transport=transport)

        bars = client.daily_prices("ibm")

        self.assertEqual([bar.as_of_date for bar in bars], [date(2026, 5, 1), date(2026, 5, 2)])
        self.assertEqual(bars[0].symbol, "IBM")
        self.assertEqual(bars[1].volume, 1000)

    def test_news_sentiment_accepts_historical_time_window(self) -> None:
        base = "https://www.alphavantage.co/query"
        response_url = (
            base
            + "?function=NEWS_SENTIMENT&tickers=IBM&limit=12&sort=LATEST"
            + "&time_from=20250101T0000&time_to=20250131T2359&apikey=test-key"
        )
        transport = FakeJsonTransport({response_url: {"feed": []}})
        client = AlphaVantageClient("test-key", transport=transport)

        data = client.news_sentiment(
            "ibm",
            limit=12,
            time_from=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            time_to=datetime(2025, 1, 31, 23, 59, tzinfo=timezone.utc),
        )

        self.assertEqual(data, {"feed": []})
        self.assertEqual(transport.calls[0][0], response_url)

    def test_topic_news_sentiment_uses_provider_topic_filter(self) -> None:
        base = "https://www.alphavantage.co/query"
        response_url = (
            base
            + "?function=NEWS_SENTIMENT&topics=technology%2Cmanufacturing&limit=4&sort=LATEST"
            + "&time_from=20250101T0000&time_to=20250131T2359&apikey=test-key"
        )
        transport = FakeJsonTransport({response_url: {"feed": []}})
        client = AlphaVantageClient("test-key", transport=transport)

        data = client.topic_news_sentiment(
            ("technology", "manufacturing"),
            limit=4,
            time_from=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            time_to=datetime(2025, 1, 31, 23, 59, tzinfo=timezone.utc),
        )

        self.assertEqual(data, {"feed": []})
        self.assertEqual(transport.calls[0][0], response_url)

    def test_from_config_uses_named_key_env_var(self) -> None:
        client = create_source(
            "alpha_vantage",
            DataSourceConfig(alpha_vantage_api_key_env_var="CUSTOM_AV_KEY"),
            environ={"CUSTOM_AV_KEY": "demo"},
            transport=FakeJsonTransport({}),
        )

        self.assertEqual(client.api_key, "demo")
        self.assertIn("alpha_vantage", registered_sources())
        self.assertIn("sec_edgar", registered_sources())
        self.assertIn("massive", registered_sources())
        self.assertIn("stooq", registered_sources())
        self.assertIn("fred", registered_sources())
        self.assertIn("openfigi", registered_sources())
        self.assertIn("finnhub", registered_sources())

    def test_missing_alpha_vantage_key_is_explicit(self) -> None:
        with self.assertRaises(DataSourceError):
            AlphaVantageClient.from_config(DataSourceConfig(), environ={})

    def test_alpha_vantage_information_response_is_error_and_redacts_key(self) -> None:
        base = "https://www.alphavantage.co/query"
        response_url = base + "?function=OVERVIEW&symbol=IBM&apikey=test-key"
        transport = FakeJsonTransport({response_url: {"Information": "test-key rate limit reached"}})
        client = AlphaVantageClient("test-key", transport=transport)

        with self.assertRaises(DataSourceError) as ctx:
            client.company_overview("IBM")
        self.assertIn("<redacted>", str(ctx.exception))
        self.assertNotIn("test-key", str(ctx.exception))

    def test_raw_endpoint_helpers_use_expected_alpha_vantage_functions(self) -> None:
        base = "https://www.alphavantage.co/query"
        response_url = base + "?function=EARNINGS_ESTIMATES&symbol=IBM&apikey=test-key"
        transport = FakeHttpTransport({response_url: {"symbol": "IBM"}})
        client = AlphaVantageClient("test-key", transport=transport)

        self.assertEqual(client.earnings_estimates("ibm"), {"symbol": "IBM"})


class StooqClientTests(TestCase):
    def test_daily_prices_are_loaded_from_csv(self) -> None:
        url = "https://stooq.com/q/d/l/?s=ibm.us&i=d&d1=20260501&d2=20260502"
        transport = FakeHttpTransport(
            text_responses={
                url: (
                    "Date,Open,High,Low,Close,Volume\n"
                    "2026-05-01,9.0,10.0,8.5,9.5,900\n"
                    "2026-05-02,10.0,11.0,9.5,10.5,1000\n"
                )
            }
        )
        client = StooqClient(transport=transport)

        bars = client.daily_prices("ibm", start_date=date(2026, 5, 1), end_date=date(2026, 5, 2))

        self.assertEqual([bar.as_of_date for bar in bars], [date(2026, 5, 1), date(2026, 5, 2)])
        self.assertEqual(bars[0].source, "stooq")

    def test_from_config_appends_optional_csv_api_key(self) -> None:
        url = "https://stooq.com/q/d/l/?s=ibm.us&i=d&apikey=stooq-key&d1=20260501&d2=20260502"
        transport = FakeHttpTransport(
            text_responses={
                url: (
                    "Date,Open,High,Low,Close,Volume\n"
                    "2026-05-01,9.0,10.0,8.5,9.5,900\n"
                )
            }
        )
        client = create_source(
            "stooq",
            DataSourceConfig(stooq_api_key_env_var="CUSTOM_STOOQ_KEY"),
            environ={"CUSTOM_STOOQ_KEY": "stooq-key"},
            transport=transport,
        )

        bars = client.daily_prices("ibm", start_date=date(2026, 5, 1), end_date=date(2026, 5, 2))

        self.assertEqual(len(bars), 1)


class MassiveClientTests(TestCase):
    def test_from_config_uses_named_key_env_var(self) -> None:
        client = MassiveClient.from_config(
            DataSourceConfig(massive_api_key_env_var="CUSTOM_MASSIVE_KEY"),
            environ={"CUSTOM_MASSIVE_KEY": "massive-key"},
            transport=FakeJsonTransport({}),
        )

        self.assertEqual(client.api_key, "massive-key")

    def test_missing_massive_key_is_explicit(self) -> None:
        with self.assertRaises(DataSourceError):
            MassiveClient.from_config(DataSourceConfig(), environ={})

    def test_daily_prices_are_loaded_from_aggregate_bars(self) -> None:
        url = (
            "https://api.massive.com/v2/aggs/ticker/IBM/range/1/day/2026-05-01/2026-05-02"
            "?adjusted=true&sort=asc&limit=50000&apiKey=massive-key"
        )
        transport = FakeJsonTransport(
            {
                url: {
                    "ticker": "IBM",
                    "status": "OK",
                    "results": [
                        {"t": 1777593600000, "o": 9.0, "h": 10.0, "l": 8.5, "c": 9.5, "v": 900},
                        {"t": 1777680000000, "o": 10.0, "h": 11.0, "l": 9.5, "c": 10.5, "v": 1000},
                    ],
                }
            }
        )
        client = MassiveClient("massive-key", transport=transport)

        bars = client.daily_prices("ibm", start_date=date(2026, 5, 1), end_date=date(2026, 5, 2))

        self.assertEqual([bar.as_of_date for bar in bars], [date(2026, 5, 1), date(2026, 5, 2)])
        self.assertEqual(bars[0].source, "massive")
        self.assertEqual(bars[0].adjusted_close, 9.5)


class FredClientTests(TestCase):
    def test_from_config_uses_named_key_env_var_and_vintage_params(self) -> None:
        url = (
            "https://api.stlouisfed.org/fred/series/observations?"
            "series_id=CPIAUCSL&observation_start=2026-01-01&realtime_end=2026-05-01"
            "&api_key=fred-key&file_type=json"
        )
        transport = FakeJsonTransport({url: {"observations": []}})
        client = FredClient.from_config(
            DataSourceConfig(fred_api_key_env_var="CUSTOM_FRED_KEY"),
            environ={"CUSTOM_FRED_KEY": "fred-key"},
            transport=transport,
        )

        data = client.series_observations(
            "cpiaucsl",
            observation_start=date(2026, 1, 1),
            realtime_end=date(2026, 5, 1),
        )

        self.assertEqual(data, {"observations": []})


class FinnhubClientTests(TestCase):
    def test_company_news_uses_symbol_and_date_window(self) -> None:
        url = "https://finnhub.io/api/v1/company-news?symbol=AAPL&from=2026-05-01&to=2026-05-02&token=fh-key"
        transport = FakeJsonTransport({url: [{"headline": "news"}]})
        client = FinnhubClient("fh-key", transport=transport)

        data = client.company_news("aapl", date(2026, 5, 1), date(2026, 5, 2))

        self.assertEqual(data, [{"headline": "news"}])


class OpenFigiClientTests(TestCase):
    def test_map_tickers_posts_mapping_jobs_with_optional_key(self) -> None:
        url = "https://api.openfigi.com/v3/mapping"
        transport = FakeHttpTransport(post_responses={url: [{"data": [{"ticker": "AAPL"}]}]})
        client = OpenFigiClient("figi-key", transport=transport)

        data = client.map_tickers(["aapl"])

        self.assertEqual(data, [{"data": [{"ticker": "AAPL"}]}])
        self.assertEqual(transport.posts[0][1]["X-OPENFIGI-APIKEY"], "figi-key")
        self.assertEqual(transport.posts[0][2][0]["idValue"], "AAPL")


class SourceStateTests(TestCase):
    def test_raw_cache_key_strips_credential_query_params(self) -> None:
        key = RawCacheKey.from_request(
            "alpha_vantage",
            DataCapability.NEWS,
            "GET",
            "https://www.alphavantage.co/query?function=NEWS_SENTIMENT&symbol=IBM&apikey=secret",
        )

        self.assertNotIn("apikey", dict(key.params))
        self.assertEqual(dict(key.params)["function"], "NEWS_SENTIMENT")

    def test_managed_transport_caches_json_and_records_cache_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            clock = FakeClock(datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc))
            url = "https://www.alphavantage.co/query?function=OVERVIEW&symbol=IBM&apikey=secret"
            inner = FakeJsonTransport({url: {"Symbol": "IBM"}})
            ledger = RequestLedger(Path(tmpdir) / "ledger.jsonl")
            transport = ManagedHttpTransport(
                "alpha_vantage",
                DataCapability.COMPANY_PROFILE,
                inner,
                RawDataCache(Path(tmpdir) / "cache"),
                ledger,
                SourceBudget(ledger, quotas={"alpha_vantage": SourceQuota("alpha_vantage", daily_limit=25)}),
                clock=clock,
            )

            first = transport.get_json(url, {})
            second = transport.get_json(url, {})

            self.assertEqual(first, {"Symbol": "IBM"})
            self.assertEqual(second, {"Symbol": "IBM"})
            self.assertEqual(len(inner.calls), 1)
            self.assertEqual([entry.status for entry in ledger.entries()], [RequestStatus.FETCHED, RequestStatus.CACHE_HIT])

    def test_managed_transport_defers_when_daily_quota_is_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            clock = FakeClock(datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc))
            ledger = RequestLedger(Path(tmpdir) / "ledger.jsonl")
            transport = ManagedHttpTransport(
                "alpha_vantage",
                DataCapability.NEWS,
                FakeJsonTransport(
                    {
                        "https://www.alphavantage.co/query?function=NEWS_SENTIMENT&symbol=IBM&apikey=secret": {
                            "feed": []
                        },
                        "https://www.alphavantage.co/query?function=NEWS_SENTIMENT&symbol=MSFT&apikey=secret": {
                            "feed": []
                        },
                    }
                ),
                RawDataCache(Path(tmpdir) / "cache"),
                ledger,
                SourceBudget(ledger, quotas={"alpha_vantage": SourceQuota("alpha_vantage", daily_limit=1)}),
                clock=clock,
            )

            transport.get_json("https://www.alphavantage.co/query?function=NEWS_SENTIMENT&symbol=IBM&apikey=secret", {})
            with self.assertRaises(DataQuotaDeferred) as ctx:
                transport.get_json(
                    "https://www.alphavantage.co/query?function=NEWS_SENTIMENT&symbol=MSFT&apikey=secret",
                    {},
                )

            self.assertEqual(ctx.exception.next_retry_at, datetime(2026, 5, 3, tzinfo=timezone.utc))
            self.assertEqual([entry.status for entry in ledger.entries()], [RequestStatus.FETCHED, RequestStatus.QUOTA_DEFERRED])

    def test_managed_transport_records_errors_that_count_against_quota(self) -> None:
        class FailingTransport:
            def get_json(self, url, headers):
                raise DataSourceError("upstream failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            clock = FakeClock(datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc))
            ledger = RequestLedger(Path(tmpdir) / "ledger.jsonl")
            transport = ManagedHttpTransport(
                "finnhub",
                DataCapability.NEWS,
                FailingTransport(),
                RawDataCache(Path(tmpdir) / "cache"),
                ledger,
                SourceBudget(ledger, quotas={"finnhub": SourceQuota("finnhub", daily_limit=1)}),
                clock=clock,
            )

            with self.assertRaises(DataSourceError):
                transport.get_json("https://finnhub.io/api/v1/company-news?symbol=AAPL&token=secret", {})
            with self.assertRaises(DataQuotaDeferred):
                transport.get_json("https://finnhub.io/api/v1/company-news?symbol=MSFT&token=secret", {})

            self.assertEqual([entry.status for entry in ledger.entries()], [RequestStatus.ERROR, RequestStatus.QUOTA_DEFERRED])

    def test_managed_transport_does_not_cache_detected_provider_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            clock = FakeClock(datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc))
            url = "https://www.alphavantage.co/query?function=OVERVIEW&symbol=IBM&apikey=secret"
            inner = FakeJsonTransport({url: {"Note": "daily API limit reached"}})
            ledger = RequestLedger(Path(tmpdir) / "ledger.jsonl")
            transport = ManagedHttpTransport(
                "alpha_vantage",
                DataCapability.COMPANY_PROFILE,
                inner,
                RawDataCache(Path(tmpdir) / "cache"),
                ledger,
                SourceBudget(ledger, quotas={"alpha_vantage": SourceQuota("alpha_vantage", daily_limit=25)}),
                clock=clock,
                json_error_detector=lambda body: body.get("Note") if isinstance(body, dict) else None,
            )

            with self.assertRaises(DataSourceError):
                transport.get_json(url, {})
            with self.assertRaises(DataSourceError):
                transport.get_json(url, {})

            self.assertEqual(len(inner.calls), 2)
            self.assertEqual([entry.status for entry in ledger.entries()], [RequestStatus.ERROR, RequestStatus.ERROR])


def version() -> VersionStamp:
    return VersionStamp(
        prompt_version="prompt-v0.1",
        scoring_version="scoring-v0.1",
        signal_version="signals-v0.1",
        model_version="model-v0.1",
        data_pipeline_version="data-v0.1",
        config_version="config-v0.1",
    )


def price_bar(day: date, close: float, volume: int) -> PriceBar:
    return PriceBar(
        symbol="NVDA",
        as_of_date=day,
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=volume,
        source="stooq",
        retrieved_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
    )


class StructuredFeatureTests(TestCase):
    def test_price_features_ignore_future_bars_and_mark_short_windows_missing(self) -> None:
        features = normalize_price_features(
            [
                price_bar(date(2026, 5, 1), 10.0, 100),
                price_bar(date(2026, 5, 2), 12.0, 200),
                price_bar(date(2026, 5, 3), 99.0, 999),
            ],
            date(2026, 5, 2),
            windows=(1, 2),
        )
        by_name = {feature.name: feature for feature in features}

        self.assertEqual(by_name["price.latest_close"].value, 12.0)
        self.assertEqual(by_name["price.average_daily_dollar_volume_1d"].value, 2400.0)
        self.assertAlmostEqual(by_name["price.return_1d"].value, 0.2)
        self.assertEqual(by_name["price.return_2d"].data_quality, DataQuality.MISSING)

    def test_alpha_vantage_overview_normalizes_values_and_missing_fields(self) -> None:
        retrieved_at = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        features = normalize_alpha_vantage_overview(
            {"Symbol": "IBM", "Sector": "Technology", "Industry": "Software", "PERatio": "None"},
            date(2026, 5, 2),
            retrieved_at,
        )
        by_name = {feature.name: feature for feature in features}

        self.assertEqual(by_name["profile.sector"].value, "Technology")
        self.assertEqual(by_name["valuation.pe_ratio"].data_quality, DataQuality.MISSING)
        self.assertEqual(by_name["valuation.market_cap_usd"].unavailable_reason, "MarketCapitalization unavailable")

    def test_sec_company_facts_use_filing_date_as_availability_cutoff(self) -> None:
        retrieved_at = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        features = normalize_sec_company_facts(
            {
                "cik": "0000320193",
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "units": {
                                "USD": [
                                    {
                                        "filed": "2026-04-30",
                                        "end": "2026-03-31",
                                        "val": 100,
                                        "accn": "old",
                                    },
                                    {
                                        "filed": "2026-05-03",
                                        "end": "2026-03-31",
                                        "val": 200,
                                        "accn": "future",
                                    },
                                ]
                            }
                        }
                    }
                },
            },
            date(2026, 5, 2),
            retrieved_at,
            feature_tags={"financial.revenue_usd": ("Revenues",)},
        )

        self.assertEqual(features[0].value, 100)
        self.assertEqual(features[0].as_of_date, date(2026, 4, 30))
        self.assertIn("old", features[0].source_id)

    def test_company_profile_uses_listing_plus_normalized_features(self) -> None:
        retrieved_at = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        listing = SecurityListing(
            symbol="nvda",
            name="NVIDIA Corporation",
            exchange="NASDAQ",
            asset_type="Stock",
            status="active",
            source="sec_edgar",
            retrieved_at=retrieved_at,
            cik="0001045810",
        )
        features = [
            FeatureRecord(
                "profile.sector",
                "Semiconductors",
                date(2026, 5, 2),
                "alpha_vantage",
                retrieved_at,
            ),
            FeatureRecord(
                "profile.industry",
                "Accelerators",
                date(2026, 5, 2),
                "alpha_vantage",
                retrieved_at,
            ),
            FeatureRecord(
                "valuation.market_cap_usd",
                1_000_000_000_000,
                date(2026, 5, 2),
                "alpha_vantage",
                retrieved_at,
            ),
            FeatureRecord(
                "price.average_daily_dollar_volume_20d",
                5_000_000_000,
                date(2026, 5, 2),
                "stooq",
                retrieved_at,
            ),
        ]

        profile = company_profile_from_features(listing, features, date(2026, 5, 2))

        self.assertEqual(profile.ticker.symbol, "NVDA")
        self.assertEqual(profile.sector, "Semiconductors")
        self.assertEqual(profile.average_daily_dollar_volume, 5_000_000_000)


class DocumentLayerTests(TestCase):
    def test_documents_are_filtered_by_public_availability(self) -> None:
        retrieved_at = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        old = DocumentRecord(
            document_id="aapl-10q",
            symbol="aapl",
            kind=EvidenceKind.FILING,
            title="AAPL 10-Q",
            text="Revenue improved and services margin expanded.",
            source_id="sec:0000320193:10q",
            source_url="https://www.sec.gov/example",
            published_date=date(2026, 4, 30),
            retrieved_at=retrieved_at,
        )
        future = DocumentRecord(
            document_id="aapl-8k",
            symbol="aapl",
            kind=EvidenceKind.FILING,
            title="AAPL 8-K",
            text="Future catalyst.",
            source_id="sec:0000320193:8k",
            source_url="https://www.sec.gov/future",
            published_date=date(2026, 5, 3),
            retrieved_at=retrieved_at,
        )
        store = DocumentStore([future, old])

        docs = store.documents_as_of("AAPL", date(2026, 5, 2))

        self.assertEqual([document.document_id for document in docs], ["aapl-10q"])
        self.assertEqual(documents_as_of([old, future], "AAPL", date(2026, 5, 2)), docs)

    def test_document_chunking_preserves_source_metadata(self) -> None:
        document = DocumentRecord(
            document_id="nvda-transcript",
            symbol="NVDA",
            kind=EvidenceKind.TRANSCRIPT,
            title="NVDA earnings call",
            text="0123456789abcdefghij",
            source_id="av:NVDA:2026Q1",
            source_url="https://example.com/transcript",
            published_date=date(2026, 5, 1),
            retrieved_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        )

        chunks = chunk_document_text(document, max_chars=10, overlap_chars=2)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].source_id, "av:NVDA:2026Q1")
        self.assertEqual(chunks[1].text[:2], "89")

    def test_research_report_and_theme_context_documents_convert_to_evidence(self) -> None:
        retrieved_at = datetime(2026, 5, 2, tzinfo=timezone.utc)
        documents = [
            DocumentRecord(
                document_id="report-1",
                symbol="AAPL",
                kind=EvidenceKind.RESEARCH_REPORT,
                title="Analyst research note",
                text="The note discussed demand, estimates, and valuation risk.",
                source_id="web:report",
                source_url="https://example.com/report",
                published_date=date(2026, 5, 1),
                retrieved_at=retrieved_at,
            ),
            DocumentRecord(
                document_id="theme-1",
                symbol="AAPL",
                kind=EvidenceKind.THEME_CONTEXT,
                title="AI infrastructure trend",
                text="The theme summary linked data center capex to upstream suppliers.",
                source_id="web:theme",
                source_url="https://example.com/theme",
                published_date=date(2026, 5, 1),
                retrieved_at=retrieved_at,
            ),
        ]

        evidence = documents_to_evidence(documents, date(2026, 5, 2))

        self.assertEqual([item.kind for item in evidence], [EvidenceKind.RESEARCH_REPORT, EvidenceKind.THEME_CONTEXT])
        self.assertTrue(all(item.source_url for item in evidence))

    def test_filing_document_excerpt_prefers_meaningful_item_text(self) -> None:
        document = DocumentRecord(
            document_id="issuer-8k",
            symbol="ABC",
            kind=EvidenceKind.FILING,
            title="ABC 8-K",
            text=(
                "<?xml version='1.0'?><html xmlns:xbrli='http://www.xbrl.org'>"
                "<!-- Field: Set; Name: xdx; ID: xdx_06D_USDPShares -->"
                "<head><title>Inline XBRL Viewer</title></head>"
                "<body><p>Item 1.01 Entry into a Material Definitive Agreement.</p>"
                "<p>The issuer signed a customer supply agreement for AI data center cooling systems.</p>"
                "</body></html>"
            ),
            source_id="sec:abc:8k",
            source_url="https://www.sec.gov/example",
            published_date=date(2026, 5, 1),
            retrieved_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        )

        evidence = documents_to_evidence([document], date(2026, 5, 2))

        self.assertIn("Item 1.01", evidence[0].summary)
        self.assertIn("customer supply agreement", evidence[0].summary)
        self.assertNotIn("Field: Set", evidence[0].summary)
        self.assertNotIn("xbrli", evidence[0].summary)


class PointInTimePacketTests(TestCase):
    def test_latest_features_by_name_respects_as_of_date_and_source_priority(self) -> None:
        retrieved_at = datetime(2026, 5, 2, tzinfo=timezone.utc)
        stooq = FeatureRecord("price.latest_close", 10.0, date(2026, 5, 1), "stooq", retrieved_at)
        vendor = FeatureRecord("price.latest_close", 10.5, date(2026, 5, 1), "alpha_vantage", retrieved_at)
        future = FeatureRecord("price.latest_close", 99.0, date(2026, 5, 3), "stooq", retrieved_at)

        selected = latest_features_by_name(
            [future, vendor, stooq],
            date(2026, 5, 2),
            source_priority=("stooq", "alpha_vantage"),
        )

        self.assertEqual(selected["price.latest_close"].value, 10.0)

    def test_research_packet_builder_excludes_future_features_and_documents(self) -> None:
        retrieved_at = datetime(2026, 5, 2, tzinfo=timezone.utc)
        profile = CompanyProfile(
            ticker=TickerRef("AAPL", exchange="NASDAQ", company_name="Apple Inc."),
            sector="Technology",
            industry="Consumer Electronics",
            market_cap_usd=1_000_000_000_000,
            average_daily_dollar_volume=1_000_000_000,
        )
        current_feature = FeatureRecord(
            "valuation.pe_ratio",
            25.0,
            date(2026, 5, 1),
            "alpha_vantage",
            retrieved_at,
            source_id="av:AAPL:pe",
        )
        future_feature = FeatureRecord(
            "valuation.pe_ratio",
            30.0,
            date(2026, 5, 3),
            "alpha_vantage",
            retrieved_at,
            source_id="av:AAPL:pe:future",
        )
        current_doc = DocumentRecord(
            document_id="aapl-10q",
            symbol="AAPL",
            kind=EvidenceKind.FILING,
            title="AAPL 10-Q",
            text="Quarterly filing.",
            source_id="sec:0000320193:10q",
            source_url="https://www.sec.gov/example",
            published_date=date(2026, 4, 30),
            retrieved_at=retrieved_at,
        )
        future_doc = DocumentRecord(
            document_id="aapl-8k",
            symbol="AAPL",
            kind=EvidenceKind.FILING,
            title="AAPL 8-K",
            text="Future filing.",
            source_id="sec:0000320193:8k",
            source_url="https://www.sec.gov/future",
            published_date=date(2026, 5, 3),
            retrieved_at=retrieved_at,
        )
        current_catalyst = Catalyst(
            name="Known product event",
            expected_date=date(2026, 6, 1),
            status=CatalystStatus.EXPECTED,
            evidence=[
                EvidenceItem(
                    kind=EvidenceKind.NEWS,
                    summary="Known before packet.",
                    as_of_date=date(2026, 5, 2),
                    source_id="news:current",
                    published_date=date(2026, 5, 2),
                )
            ],
        )
        future_catalyst = Catalyst(
            name="Future order",
            expected_date=date(2026, 6, 15),
            status=CatalystStatus.CONFIRMED,
            evidence=[
                EvidenceItem(
                    kind=EvidenceKind.NEWS,
                    summary="Future article.",
                    as_of_date=date(2026, 5, 3),
                    source_id="news:future",
                    published_date=date(2026, 5, 3),
                )
            ],
        )

        packet = build_research_packet(
            symbol="AAPL",
            as_of_date=date(2026, 5, 2),
            company=profile,
            features=[future_feature, current_feature],
            documents=[future_doc, current_doc],
            catalysts=[future_catalyst, current_catalyst],
            version=version(),
            created_at=retrieved_at,
        )

        self.assertEqual([feature.source_id for feature in packet.features], ["av:AAPL:pe"])
        self.assertTrue(any(item.source_id == "sec:0000320193:10q" for item in packet.evidence))
        self.assertTrue(any("Quarterly filing" in item.summary for item in packet.evidence))
        self.assertFalse(any(item.source_id == "sec:0000320193:8k" for item in packet.evidence))
        self.assertEqual([catalyst.name for catalyst in packet.catalysts], ["Known product event"])
