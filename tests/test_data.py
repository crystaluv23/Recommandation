from datetime import date
from unittest import TestCase

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data import (
    AlphaVantageClient,
    DataCapability,
    DataSourceError,
    FREE_DATA_SOURCES,
    FinnhubClient,
    FredClient,
    OpenFigiClient,
    SecEdgarClient,
    StooqClient,
    create_source,
    filing_to_evidence,
    registered_sources,
    select_source_for_capability,
    source_catalog_by_capability,
    source_plan_by_capability,
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


class FreeDataCatalogTests(TestCase):
    def test_catalog_covers_core_mvp_needs_without_single_vendor_lock_in(self) -> None:
        names = {source.name for source in FREE_DATA_SOURCES}

        self.assertIn("SEC EDGAR", names)
        self.assertIn("Alpha Vantage", names)
        self.assertIn("FRED", names)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.PRICE_DAILY)), 2)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.FILINGS)), 1)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.NEWS)), 2)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.MACRO_SERIES)), 2)

    def test_capability_plan_selects_first_available_source(self) -> None:
        plan = source_plan_by_capability(DataCapability.PRICE_DAILY)

        self.assertEqual(plan.preferred_sources[0], "stooq")
        self.assertEqual(
            select_source_for_capability(DataCapability.PRICE_DAILY, ["alpha_vantage", "stooq"]),
            "stooq",
        )


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
        self.assertEqual(transport.calls[0][1]["User-Agent"], "test@example.com")

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
        self.assertIn("stooq", registered_sources())
        self.assertIn("fred", registered_sources())
        self.assertIn("openfigi", registered_sources())
        self.assertIn("finnhub", registered_sources())

    def test_missing_alpha_vantage_key_is_explicit(self) -> None:
        with self.assertRaises(DataSourceError):
            AlphaVantageClient.from_config(DataSourceConfig(), environ={})

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
