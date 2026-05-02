from datetime import date
from unittest import TestCase

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data import (
    AlphaVantageClient,
    DataCapability,
    DataSourceError,
    FREE_DATA_SOURCES,
    SecEdgarClient,
    create_source,
    filing_to_evidence,
    registered_sources,
    source_catalog_by_capability,
)


class FakeJsonTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_json(self, url, headers):
        self.calls.append((url, headers))
        return self.responses[url]


class FreeDataCatalogTests(TestCase):
    def test_catalog_covers_core_mvp_needs_without_single_vendor_lock_in(self) -> None:
        names = {source.name for source in FREE_DATA_SOURCES}

        self.assertIn("SEC EDGAR", names)
        self.assertIn("Alpha Vantage", names)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.PRICE_DAILY)), 2)
        self.assertGreaterEqual(len(source_catalog_by_capability(DataCapability.FILINGS)), 1)


class SecEdgarClientTests(TestCase):
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

    def test_missing_alpha_vantage_key_is_explicit(self) -> None:
        with self.assertRaises(DataSourceError):
            AlphaVantageClient.from_config(DataSourceConfig(), environ={})
