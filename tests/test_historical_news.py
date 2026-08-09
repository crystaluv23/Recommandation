from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from stock_opportunity_agent.data.historical_news import (
    alpha_vantage_error_message,
    load_alpha_vantage_news_plan,
    preview_alpha_vantage_news_backfill,
    run_alpha_vantage_news_backfill,
    write_alpha_vantage_news_plan,
)
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.sources.alpha_vantage import AlphaVantageClient
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.state import (
    DataQuotaDeferred,
    ManagedHttpTransport,
    RawCacheKey,
    RawDataCache,
    RequestLedger,
    SourceBudget,
)
from stock_opportunity_agent.models import ValidationError


class FakeJsonTransport:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get_json(self, url, headers):
        self.calls.append(url)
        return self.responses[url]


class DeferredNewsClient:
    def news_sentiment(self, symbol, *, limit, time_from, time_to, sort):
        raise DataQuotaDeferred(
            "alpha_vantage",
            datetime(2026, 8, 10, tzinfo=timezone.utc),
            "daily_limit reached for alpha_vantage",
        )


class HistoricalNewsBackfillTests(unittest.TestCase):
    def test_plan_is_exact_label_free_and_zero_network_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope = _scope(root)
            plan_path = root / "news_plan.json"

            first = write_alpha_vantage_news_plan(
                acquisition_scope_path=scope,
                output_path=plan_path,
                lookback_days=9,
                limit=3,
            )
            second = write_alpha_vantage_news_plan(
                acquisition_scope_path=scope,
                output_path=plan_path,
                lookback_days=9,
                limit=3,
            )

            self.assertEqual(first, second)
            self.assertEqual(first["request_count"], 2)
            self.assertEqual(first["selection"]["start_at"], "2024-01-01T00:00:00+00:00")
            self.assertEqual(first["selection"]["end_at"], "2024-01-10T23:59:00+00:00")
            self.assertNotIn("apikey", json.dumps(first).casefold())
            self.assertNotIn("outcome_label", json.dumps(first).casefold())
            self.assertEqual(load_alpha_vantage_news_plan(plan_path), first)

            preview = preview_alpha_vantage_news_backfill(
                plan_path=plan_path,
                cache=RawDataCache(root / "cache"),
                progress_path=root / "progress.json",
                raw_info_root=root / "raw_info",
            )
            self.assertEqual(preview["pending_count"], 2)
            self.assertEqual(preview["maximum_new_network_requests"], 2)
            self.assertEqual(preview["provider_daily_limit"], 25)
            self.assertEqual(preview["external_calls"], 0)
            self.assertFalse((root / "progress.json").exists())

    def test_bounded_execution_filters_deduplicates_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "news_plan.json"
            write_alpha_vantage_news_plan(
                acquisition_scope_path=_scope(root),
                output_path=plan_path,
                lookback_days=9,
                limit=4,
            )
            responses = {
                _request_url("ABC", limit=4): {
                    "feed": [
                        _news_item(
                            "ABC",
                            "20240102T123456",
                            "Contract award",
                            "Short summary",
                            "https://publisher.example/abc-1",
                        ),
                        _news_item(
                            "ABC",
                            "20240102T123456",
                            "Contract award",
                            "A substantially longer provider summary for the same article",
                            "https://publisher.example/abc-1",
                        ),
                        _news_item(
                            "OTHER",
                            "20240103T010203",
                            "Unrelated company",
                            "Not about the requested ticker",
                            "https://publisher.example/other",
                        ),
                        _news_item(
                            "ABC",
                            "20240111T010203",
                            "Too late for the plan",
                            "This must not enter point-in-time Raw Info",
                            "https://publisher.example/abc-late",
                        ),
                    ]
                },
                _request_url("XYZ", limit=4): {"feed": []},
            }
            cache = RawDataCache(root / "cache")
            inner = FakeJsonTransport(responses)
            client = _managed_client(root, cache, inner)
            events = []

            first = run_alpha_vantage_news_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "progress.json",
                raw_info_root=root / "raw_info",
                client=client,
                max_network_requests=1,
                now=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc),
                on_progress=events.append,
            )

            self.assertEqual(first["status"], "paused_resumable")
            self.assertEqual(first["network_requests_this_run"], 1)
            self.assertEqual(first["documents_appended_this_run"], 1)
            self.assertEqual(first["excluded_feed_rows_this_run"], 3)
            self.assertEqual(first["provider_limit_reached_count"], 1)
            self.assertEqual(
                [event["status"] for event in events],
                ["starting", "completed", "paused_network_limit"],
            )
            stored = RawInfoStore(root / "raw_info").documents
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].published_at.isoformat(), "2024-01-02T12:34:56+00:00")
            self.assertEqual(stored[0].available_at, stored[0].published_at)
            self.assertIn("substantially longer", stored[0].content)
            self.assertEqual(stored[0].metadata["content_scope"], "provider_title_summary")
            self.assertEqual(stored[0].metadata["ticker_relevance_score"], "0.80")

            second = run_alpha_vantage_news_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "progress.json",
                raw_info_root=root / "raw_info",
                client=client,
                max_network_requests=1,
            )
            self.assertEqual(second["status"], "completed")
            self.assertEqual(second["network_requests_this_run"], 1)
            self.assertEqual(second["provider_limit_reached_count"], 1)
            self.assertEqual(len(inner.calls), 2)

            replay = run_alpha_vantage_news_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "progress.json",
                raw_info_root=root / "raw_info",
                client=client,
                max_network_requests=0,
            )
            self.assertEqual(replay["status"], "completed")
            self.assertEqual(replay["network_requests_this_run"], 0)
            self.assertEqual(len(inner.calls), 2)

    def test_provider_error_is_redacted_and_not_cached(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope = root / "scope.json"
            _write_json(
                scope,
                {
                    "schema_version": "expanded-case-acquisition-scope-v1",
                    "prediction_dates": ["2024-01-10"],
                    "company_count": 1,
                    "companies": [
                        {
                            "company_id": "abc",
                            "cik": None,
                            "symbol": "ABC",
                            "company_name": "ABC Corp",
                        }
                    ],
                    "outcome_fields_included": False,
                    "split_ownership_included": False,
                },
            )
            plan_path = root / "news_plan.json"
            plan = write_alpha_vantage_news_plan(
                acquisition_scope_path=scope,
                output_path=plan_path,
                lookback_days=9,
                limit=3,
            )
            api_key = "private-test-key"
            url = _request_url("ABC", limit=3, api_key=api_key)
            inner = FakeJsonTransport(
                {url: {"Note": f"quota reached for {api_key}"}}
            )
            cache = RawDataCache(root / "cache")
            client = _managed_client(root, cache, inner, api_key=api_key)

            result = run_alpha_vantage_news_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "progress.json",
                raw_info_root=root / "raw_info",
                client=client,
                max_network_requests=1,
            )

            self.assertEqual(result["status"], "paused_resumable")
            self.assertEqual(result["failures_this_run"], 1)
            progress_text = (root / "progress.json").read_text(encoding="utf-8")
            self.assertNotIn(api_key, progress_text)
            self.assertIn("<redacted>", progress_text)
            item = plan["items"][0]
            self.assertIsNone(cache.get_json(_cache_key(item)))

    def test_quota_pause_and_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "news_plan.json"
            write_alpha_vantage_news_plan(
                acquisition_scope_path=_scope(root),
                output_path=plan_path,
                lookback_days=9,
                limit=3,
            )
            paused = run_alpha_vantage_news_backfill(
                plan_path=plan_path,
                cache=RawDataCache(root / "cache"),
                progress_path=root / "progress.json",
                raw_info_root=root / "raw_info",
                client=DeferredNewsClient(),
                max_network_requests=1,
            )
            self.assertEqual(paused["status"], "paused_resumable")
            self.assertEqual(paused["last_stop"], "source_quota_deferred")
            self.assertEqual(paused["network_requests_this_run"], 0)
            progress = json.loads((root / "progress.json").read_text(encoding="utf-8"))
            self.assertEqual(
                progress["last_deferred"]["next_retry_at"],
                "2026-08-10T00:00:00+00:00",
            )

            tampered = json.loads(plan_path.read_text(encoding="utf-8"))
            tampered["items"][0]["symbol"] = "BAD"
            _write_json(plan_path, tampered)
            with self.assertRaisesRegex(ValidationError, "hash mismatch"):
                load_alpha_vantage_news_plan(plan_path)

    def test_scope_with_outcome_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope = _scope(root)
            value = json.loads(scope.read_text(encoding="utf-8"))
            value["companies"][0]["outcome_label"] = "winner"
            _write_json(scope, value)

            with self.assertRaisesRegex(ValidationError, "forbidden"):
                write_alpha_vantage_news_plan(
                    acquisition_scope_path=scope,
                    output_path=root / "plan.json",
                )


def _scope(root: Path) -> Path:
    path = root / "scope.json"
    _write_json(
        path,
        {
            "schema_version": "expanded-case-acquisition-scope-v1",
            "prediction_dates": ["2024-01-10"],
            "company_count": 2,
            "companies": [
                {
                    "company_id": "abc",
                    "cik": "1234",
                    "symbol": "ABC",
                    "company_name": "ABC Corp",
                },
                {
                    "company_id": "xyz",
                    "cik": None,
                    "symbol": "XYZ",
                    "company_name": "XYZ Corp",
                },
            ],
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
    )
    return path


def _news_item(
    symbol: str,
    published: str,
    title: str,
    summary: str,
    url: str,
) -> dict[str, object]:
    return {
        "time_published": published,
        "title": title,
        "summary": summary,
        "url": url,
        "source": "Example Publisher",
        "authors": ["Reporter"],
        "topics": [{"topic": "Technology", "relevance_score": "0.50"}],
        "overall_sentiment_score": "0.10",
        "overall_sentiment_label": "Neutral",
        "ticker_sentiment": [
            {
                "ticker": symbol,
                "relevance_score": "0.80",
                "ticker_sentiment_score": "0.20",
                "ticker_sentiment_label": "Somewhat-Bullish",
            }
        ],
    }


def _request_url(
    symbol: str,
    *,
    limit: int,
    api_key: str = "test-key",
) -> str:
    return (
        "https://www.alphavantage.co/query?function=NEWS_SENTIMENT"
        f"&tickers={symbol}&limit={limit}&sort=LATEST"
        "&time_from=20240101T0000&time_to=20240110T2359"
        f"&apikey={api_key}"
    )


def _cache_key(item: dict[str, object]) -> RawCacheKey:
    parameters = item["request_parameters"]
    assert isinstance(parameters, dict)
    query = "&".join(
        [*(f"{key}={value}" for key, value in parameters.items()), "apikey=ignored"]
    )
    return RawCacheKey.from_request(
        "alpha_vantage",
        DataCapability.NEWS,
        "GET",
        f"{item['source_endpoint']}?{query}",
    )


def _managed_client(
    root: Path,
    cache: RawDataCache,
    inner: FakeJsonTransport,
    *,
    api_key: str = "test-key",
) -> AlphaVantageClient:
    ledger = RequestLedger(root / "ledger.jsonl")

    def detector(payload: object) -> str | None:
        message = alpha_vantage_error_message(payload)
        return message.replace(api_key, "<redacted>") if message else None

    transport = ManagedHttpTransport(
        "alpha_vantage",
        DataCapability.NEWS,
        inner,
        cache,
        ledger,
        SourceBudget(ledger, {}),
        json_error_detector=detector,
    )
    return AlphaVantageClient(api_key, transport=transport)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
