from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from stock_opportunity_agent.data.backfill import (
    audit_historical_data_coverage,
    load_sec_filing_backfill_plan,
    preview_sec_filing_backfill,
    run_sec_filing_backfill,
    write_sec_filing_backfill_plan,
)
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import DataSourceError
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.data.sources.state import (
    ManagedHttpTransport,
    RawCacheKey,
    RawDataCache,
    RequestLedger,
    SourceBudget,
)
from stock_opportunity_agent.models import ValidationError


class FakeSecTransport:
    def __init__(self, body: str, *, failures: int = 0) -> None:
        self.body = body
        self.failures = failures
        self.calls = 0

    def get_json(self, url, headers):
        raise AssertionError("JSON was not expected")

    def get_text(self, url, headers):
        self.calls += 1
        if self.calls <= self.failures:
            raise DataSourceError("temporary SEC failure")
        return self.body


class HistoricalDataBackfillTests(unittest.TestCase):
    def test_audit_measures_point_in_time_gaps_without_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / "cases.json"
            documents = root / "documents.json"
            _write_json(
                cases,
                {
                    "cases": [
                        _case("ABC", "2025-01-15", industry="Unknown"),
                        _case("ABC", "2025-02-15", industry="Technology"),
                        _case("XYZ", "2025-01-15", industry="Unknown"),
                    ]
                },
            )
            _write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "ABC": [
                            _filing("ABC", "10-K", "2025-01-20", chars=1500),
                            _news("ABC", "2025-02-01"),
                        ],
                        "XYZ": [],
                    }
                },
            )

            report = audit_historical_data_coverage(
                cases_path=cases,
                documents_path=documents,
            )

            self.assertEqual(report["case_count"], 3)
            self.assertEqual(report["symbol_count"], 2)
            self.assertEqual(report["case_coverage"]["no_documents"], 2)
            self.assertEqual(report["case_coverage"]["no_filing"], 2)
            self.assertEqual(report["case_coverage"]["no_news"], 2)
            self.assertEqual(report["symbol_form_family_coverage"]["annual"], 1)
            self.assertEqual(report["likely_truncated_sec_filing_count"], 1)
            self.assertEqual(report["transcript_count"], 0)
            self.assertNotIn("label", json.dumps(report).casefold())

    def test_plan_is_deterministic_exact_and_conservative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = root / "documents.json"
            plan_path = root / "plan.json"
            _write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "ABC": [
                            _filing("ABC", "8-K", "2025-02-01", chars=1500),
                            _filing("ABC", "10-K", "2025-01-20", chars=1500),
                            _news("ABC", "2025-02-01"),
                        ]
                    }
                },
            )

            first = write_sec_filing_backfill_plan(
                documents_path=documents,
                output_path=plan_path,
            )
            second = write_sec_filing_backfill_plan(
                documents_path=documents,
                output_path=plan_path,
            )

            self.assertEqual(first, second)
            self.assertEqual(first["request_count"], 2)
            self.assertEqual(first["items"][0]["form"], "10-K")
            self.assertEqual(first["items"][0]["available_at"], "2025-01-21T00:00:00+00:00")
            self.assertNotIn("outcome", json.dumps(first).casefold())
            self.assertEqual(load_sec_filing_backfill_plan(plan_path), first)

    def test_zero_network_preview_reports_exact_cache_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _one_item_plan(root)
            cache = RawDataCache(root / "cache")
            report = preview_sec_filing_backfill(
                plan_path=plan_path,
                raw_info_root=root / "raw_info",
                cache=cache,
                progress_path=root / "progress.json",
            )
            self.assertEqual(report["maximum_new_network_requests"], 1)
            self.assertEqual(report["external_calls"], 0)

    def test_bounded_execution_appends_complete_body_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _one_item_plan(root)
            cache = RawDataCache(root / "cache")
            inner = FakeSecTransport("<html>" + "complete filing body " * 200 + "</html>")
            client = _managed_client(root, cache, inner)

            result = run_sec_filing_backfill(
                plan_path=plan_path,
                raw_info_root=root / "raw_info",
                cache=cache,
                progress_path=root / "progress.json",
                client=client,
                max_network_requests=1,
                now=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc),
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["network_requests_this_run"], 1)
            self.assertEqual(inner.calls, 1)
            stored = RawInfoStore(root / "raw_info").documents
            self.assertEqual(len(stored), 1)
            self.assertGreater(len(stored[0].content), 1500)
            self.assertEqual(stored[0].available_at.isoformat(), "2025-01-21T00:00:00+00:00")
            self.assertEqual(stored[0].metadata["content_scope"], "complete_body")

            resumed = run_sec_filing_backfill(
                plan_path=plan_path,
                raw_info_root=root / "raw_info",
                cache=cache,
                progress_path=root / "progress.json",
                client=client,
                max_network_requests=0,
            )
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(resumed["network_requests_this_run"], 0)
            self.assertEqual(inner.calls, 1)

    def test_cached_body_recovers_before_any_new_network_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _one_item_plan(root)
            plan = load_sec_filing_backfill_plan(plan_path)
            item = plan["items"][0]
            cache = RawDataCache(root / "cache")
            key = RawCacheKey.from_request(
                "sec_edgar",
                DataCapability.FILING_DOCUMENTS,
                "GET",
                item["source_url"],
            )
            cache.set_text(
                key,
                "cached complete filing " * 200,
                datetime(2026, 8, 9, tzinfo=timezone.utc),
            )
            inner = FakeSecTransport("must not be fetched")
            client = _managed_client(root, cache, inner)

            result = run_sec_filing_backfill(
                plan_path=plan_path,
                raw_info_root=root / "raw_info",
                cache=cache,
                progress_path=root / "progress.json",
                client=client,
                max_network_requests=0,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["cache_hits_this_run"], 1)
            self.assertEqual(result["network_requests_this_run"], 0)
            self.assertEqual(inner.calls, 0)

    def test_transient_failure_remains_pending_and_retries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _one_item_plan(root)
            cache = RawDataCache(root / "cache")
            inner = FakeSecTransport("complete filing body " * 200, failures=1)
            client = _managed_client(root, cache, inner)

            failed = run_sec_filing_backfill(
                plan_path=plan_path,
                raw_info_root=root / "raw_info",
                cache=cache,
                progress_path=root / "progress.json",
                client=client,
                max_network_requests=1,
            )
            self.assertEqual(failed["status"], "paused_resumable")
            self.assertEqual(failed["pending_count"], 1)

            recovered = run_sec_filing_backfill(
                plan_path=plan_path,
                raw_info_root=root / "raw_info",
                cache=cache,
                progress_path=root / "progress.json",
                client=client,
                max_network_requests=1,
            )
            self.assertEqual(recovered["status"], "completed")
            self.assertEqual(inner.calls, 2)

    def test_tampered_plan_and_conflicting_progress_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _one_item_plan(root)
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            data["items"][0]["source_url"] = "https://example.com/not-sec"
            _write_json(plan_path, data)
            with self.assertRaisesRegex(ValidationError, "hash mismatch"):
                load_sec_filing_backfill_plan(plan_path)

            plan_path = _one_item_plan(root)
            _write_json(
                root / "progress.json",
                {
                    "schema_version": "sec-filing-backfill-progress-v1",
                    "plan_hash": "wrong",
                    "completed": {},
                    "failures": [],
                },
            )
            with self.assertRaisesRegex(ValidationError, "plan hash mismatch"):
                preview_sec_filing_backfill(
                    plan_path=plan_path,
                    raw_info_root=root / "raw_info",
                    cache=RawDataCache(root / "cache"),
                    progress_path=root / "progress.json",
                )


def _managed_client(root: Path, cache: RawDataCache, inner: FakeSecTransport) -> SecEdgarClient:
    ledger = RequestLedger(root / "ledger.jsonl")
    transport = ManagedHttpTransport(
        "sec_edgar",
        DataCapability.FILING_DOCUMENTS,
        inner,
        cache,
        ledger,
        SourceBudget(ledger, {}),
    )
    return SecEdgarClient("test@example.test", transport=transport)


def _one_item_plan(root: Path) -> Path:
    documents = root / "documents.json"
    plan = root / "plan.json"
    _write_json(
        documents,
        {"documents_by_symbol": {"ABC": [_filing("ABC", "10-K", "2025-01-20", chars=1500)]}},
    )
    write_sec_filing_backfill_plan(documents_path=documents, output_path=plan)
    return plan


def _case(symbol: str, as_of_date: str, *, industry: str) -> dict[str, object]:
    return {
        "hidden_outcome_summary": "must never be read by coverage audit",
        "packet": {
            "as_of": {"as_of_date": as_of_date},
            "company": {
                "industry": industry,
                "ticker": {"symbol": symbol},
            },
        },
    }


def _filing(symbol: str, form: str, published_date: str, *, chars: int) -> dict[str, object]:
    cik = "0000320193"
    accession = "0000320193-25-000001"
    return {
        "document_id": f"sec:{cik}:{accession}",
        "kind": "filing",
        "title": f"{symbol} {form} filed {published_date}",
        "text": "x" * chars,
        "source_id": f"sec:{cik}:{accession}",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019325000001/abc-20250120.htm"
        ),
        "published_date": published_date,
        "available_date": published_date,
    }


def _news(symbol: str, published_date: str) -> dict[str, object]:
    return {
        "document_id": f"news:{symbol}:{published_date}",
        "kind": "news",
        "title": f"{symbol} news",
        "text": "company news",
        "source_id": f"news:{symbol}:{published_date}",
        "source_url": "https://example.com/news",
        "published_date": published_date,
        "available_date": published_date,
    }


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
