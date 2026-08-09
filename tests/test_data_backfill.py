from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from stock_opportunity_agent.data.backfill import (
    audit_expanded_acquisition_coverage,
    audit_historical_data_coverage,
    load_sec_company_facts_backfill_plan,
    load_sec_filing_backfill_plan,
    load_sec_historical_submissions_plan,
    load_sec_submissions_backfill_plan,
    preview_sec_company_facts_backfill,
    preview_sec_filing_backfill,
    preview_sec_historical_submissions_backfill,
    preview_sec_submissions_backfill,
    run_sec_company_facts_backfill,
    run_sec_filing_backfill,
    run_sec_historical_submissions_backfill,
    run_sec_submissions_backfill,
    write_sec_company_facts_backfill_plan,
    write_sec_filing_backfill_plan,
    write_sec_filing_plan_from_submissions,
    write_sec_historical_submissions_plan,
    write_sec_submissions_backfill_plan,
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


class FakeSecJsonTransport:
    def __init__(self, body: dict[str, object]) -> None:
        self.body = body
        self.calls = 0

    def get_json(self, url, headers):
        self.calls += 1
        return self.body

    def get_text(self, url, headers):
        raise AssertionError("text was not expected")


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

    def test_label_free_scope_plans_and_resumes_exact_sec_submissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope = root / "acquisition_scope.json"
            plan_path = root / "submissions_plan.json"
            _write_json(
                scope,
                {
                    "schema_version": "expanded-case-acquisition-scope-v1",
                    "source_inventory_hash": "a" * 64,
                    "prediction_dates": ["2024-09-30", "2025-09-30"],
                    "company_count": 2,
                    "companies": [
                        {
                            "company_id": "cik_0000001234",
                            "cik": "1234",
                            "symbol": "ABC",
                            "company_name": "ABC Corp",
                        },
                        {
                            "company_id": "nocik",
                            "cik": None,
                            "symbol": "NCIK",
                            "company_name": "No CIK Corp",
                        },
                    ],
                    "outcome_fields_included": False,
                    "split_ownership_included": False,
                },
            )
            documents = root / "documents.json"
            _write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "ABC": [
                            _filing("ABC", "10-K", "2024-09-01", chars=1500),
                            _news("ABC", "2025-01-01"),
                        ],
                        "NCIK": [],
                    }
                },
            )
            coverage = audit_expanded_acquisition_coverage(
                acquisition_scope_path=scope,
                documents_path=documents,
            )
            self.assertEqual(coverage["company_count"], 2)
            self.assertEqual(coverage["case_observation_count"], 4)
            self.assertEqual(coverage["company_coverage"]["without_documents"], 1)
            self.assertEqual(
                coverage["point_in_time_observation_coverage"]["no_documents"], 2
            )
            self.assertEqual(coverage["missing_cik_count"], 1)
            self.assertFalse(coverage["outcome_fields_read"])
            self.assertEqual(coverage["external_calls"], 0)

            plan = write_sec_submissions_backfill_plan(
                acquisition_scope_path=scope,
                output_path=plan_path,
            )
            self.assertEqual(plan["request_count"], 1)
            self.assertEqual(plan["missing_cik_count"], 1)
            self.assertEqual(
                plan["items"][0]["source_url"],
                "https://data.sec.gov/submissions/CIK0000001234.json",
            )
            self.assertEqual(load_sec_submissions_backfill_plan(plan_path), plan)
            cache = RawDataCache(root / "cache")
            preview = preview_sec_submissions_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "submissions_progress.json",
            )
            self.assertEqual(preview["maximum_new_network_requests"], 1)
            self.assertEqual(preview["filing_bodies_completed"], 0)
            self.assertEqual(preview["external_calls"], 0)

            inner = FakeSecJsonTransport(
                {
                    "cik": "1234",
                    "filings": {
                        "recent": {"accessionNumber": []},
                        "files": [
                            {
                                "name": "CIK0000001234-submissions-001.json",
                                "filingCount": 10,
                                "filingFrom": "2020-01-01",
                                "filingTo": "2023-12-31",
                            }
                        ],
                    },
                }
            )
            client = _managed_submissions_client(root, cache, inner)
            progress_events = []
            result = run_sec_submissions_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "submissions_progress.json",
                client=client,
                max_network_requests=1,
                now=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc),
                on_progress=progress_events.append,
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["network_requests_this_run"], 1)
            self.assertEqual(result["filing_bodies_completed"], 0)
            self.assertEqual(inner.calls, 1)
            self.assertEqual(
                [event["status"] for event in progress_events],
                ["starting", "completed"],
            )
            self.assertEqual(progress_events[-1]["item_count"], 1)

            resumed = run_sec_submissions_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "submissions_progress.json",
                client=client,
                max_network_requests=0,
            )
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(resumed["network_requests_this_run"], 0)
            self.assertEqual(inner.calls, 1)

    def test_company_facts_plan_materializes_point_in_time_raw_info(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _one_company_submissions_plan(root)
            scope = root / "acquisition_scope.json"
            plan_path = root / "company_facts_plan.json"
            plan = write_sec_company_facts_backfill_plan(
                acquisition_scope_path=scope,
                output_path=plan_path,
            )
            self.assertEqual(plan["request_count"], 1)
            self.assertEqual(plan["missing_cik_count"], 0)
            self.assertEqual(
                plan["items"][0]["source_url"],
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0000001234.json",
            )
            self.assertIn("ifrs-full", plan["selection"]["taxonomy_allowlist"])
            self.assertEqual(load_sec_company_facts_backfill_plan(plan_path), plan)

            cache = RawDataCache(root / "cache")
            preview = preview_sec_company_facts_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "company_facts_progress.json",
            )
            self.assertEqual(preview["maximum_new_network_requests"], 1)
            self.assertEqual(preview["fact_document_count"], 0)
            self.assertEqual(preview["external_calls"], 0)

            valid_quarter = {
                "accn": "0000001234-24-000001",
                "filed": "2024-08-01",
                "form": "10-Q",
                "fy": 2024,
                "fp": "Q2",
                "start": "2024-04-01",
                "end": "2024-06-30",
                "val": 100,
            }
            response = {
                "cik": 1234,
                "entityName": "CURRENT NAME MUST NOT ENTER HISTORICAL CONTENT",
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "label": "Revenue",
                            "description": "Quarterly revenue.",
                            "units": {
                                "USD": [
                                    valid_quarter,
                                    {
                                        **valid_quarter,
                                        "accn": "0000001234-21-000001",
                                        "filed": "2021-02-01",
                                        "start": "2020-01-01",
                                        "end": "2020-12-31",
                                        "form": "10-K",
                                        "val": 1,
                                    },
                                    {
                                        **valid_quarter,
                                        "accn": "0000001234-25-000003",
                                        "filed": "2025-04-01",
                                        "end": "2025-03-31",
                                        "val": 999,
                                    },
                                    {
                                        **valid_quarter,
                                        "accn": "0000001234-25-000004",
                                        "filed": "2025-03-31",
                                        "end": "2024-12-31",
                                        "val": 998,
                                    },
                                    {
                                        **valid_quarter,
                                        "accn": "0001213900-24-000001",
                                        "val": 997,
                                    },
                                    {
                                        **valid_quarter,
                                        "accn": "not-an-accession",
                                        "val": 996,
                                    },
                                ]
                            },
                        },
                        "Assets": {
                            "label": "Assets",
                            "units": {
                                "USD": [
                                    {
                                        **valid_quarter,
                                        "start": None,
                                        "val": 500,
                                    }
                                ]
                            },
                        },
                    },
                    "ifrs-full": {
                        "Revenue": {
                            "label": "Revenue",
                            "units": {
                                "USD": [
                                    {
                                        "accn": "0000001234-25-000002",
                                        "filed": "2025-02-20",
                                        "form": "20-F",
                                        "fy": 2024,
                                        "fp": "FY",
                                        "start": "2024-01-01",
                                        "end": "2024-12-31",
                                        "val": 200,
                                    }
                                ]
                            },
                        }
                    },
                    "custom-company": {
                        "NonstandardMetric": {
                            "units": {"pure": [valid_quarter]},
                        }
                    },
                },
            }
            inner = FakeSecJsonTransport(response)
            client = _managed_company_facts_client(root, cache, inner)
            events = []
            result = run_sec_company_facts_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "company_facts_progress.json",
                raw_info_root=root / "raw_info",
                client=client,
                max_network_requests=1,
                now=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc),
                on_progress=events.append,
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["network_requests_this_run"], 1)
            self.assertEqual(result["fact_document_count"], 3)
            self.assertEqual(result["selected_fact_row_count"], 4)
            self.assertEqual(result["appended_documents_this_run"], 3)
            self.assertEqual([event["status"] for event in events], ["starting", "completed"])
            self.assertEqual(inner.calls, 1)

            stored = RawInfoStore(root / "raw_info").documents
            self.assertEqual(len(stored), 3)
            serialized = json.dumps([document.to_dict() for document in stored])
            self.assertNotIn("CURRENT NAME", serialized)
            self.assertNotIn("custom-company", serialized)
            selected_values = {
                fact["value"]
                for document in stored
                for fact in json.loads(document.content)["facts"]
            }
            self.assertEqual(selected_values, {100, 200, 500, 997})
            same_cik_accession = next(
                document
                for document in stored
                if document.metadata["accession_number"]
                == "0000001234-24-000001"
            )
            self.assertEqual(
                same_cik_accession.available_at,
                datetime(2024, 8, 2, tzinfo=timezone.utc),
            )
            self.assertEqual(same_cik_accession.metadata["fact_count"], 2)
            self.assertTrue(
                same_cik_accession.metadata["requires_primary_filing_audit"]
            )
            before_second = RawInfoStore(root / "raw_info").search(
                "cik_0000001234",
                as_of=datetime(2024, 9, 30, tzinfo=timezone.utc),
                source_types=("sec_company_facts",),
            )
            self.assertEqual(len(before_second), 2)

            recovered = run_sec_company_facts_backfill(
                plan_path=plan_path,
                cache=cache,
                progress_path=root / "recovered_progress.json",
                raw_info_root=root / "recovered_raw_info",
                client=client,
                max_network_requests=0,
            )
            self.assertEqual(recovered["status"], "completed")
            self.assertEqual(recovered["network_requests_this_run"], 0)
            self.assertEqual(recovered["cache_hits_this_run"], 1)
            self.assertEqual(inner.calls, 1)

            bad_cache = RawDataCache(root / "bad_cache")
            bad_inner = FakeSecJsonTransport({**response, "cik": 9999})
            bad_client = _managed_company_facts_client(root, bad_cache, bad_inner)
            rejected = run_sec_company_facts_backfill(
                plan_path=plan_path,
                cache=bad_cache,
                progress_path=root / "bad_progress.json",
                raw_info_root=root / "bad_raw_info",
                client=bad_client,
                max_network_requests=1,
            )
            self.assertEqual(rejected["status"], "paused_resumable")
            self.assertEqual(rejected["failures_this_run"], 1)
            self.assertEqual(rejected["fact_document_count"], 0)

            tampered = json.loads(plan_path.read_text(encoding="utf-8"))
            tampered["selection"]["period_end_from"] = "2024-01-01"
            _write_json(plan_path, tampered)
            with self.assertRaisesRegex(ValidationError, "hash mismatch"):
                load_sec_company_facts_backfill_plan(plan_path)

    def test_sec_history_and_body_plans_are_resumable_and_point_in_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary_path = _one_company_submissions_plan(root)
            history_path = root / "history_plan.json"
            body_path = root / "body_plan.json"
            cache = RawDataCache(root / "cache")

            with self.assertRaisesRegex(ValidationError, "primary submissions cache"):
                write_sec_historical_submissions_plan(
                    primary_plan_path=primary_path,
                    cache=cache,
                    output_path=history_path,
                )

            primary_plan = load_sec_submissions_backfill_plan(primary_path)
            primary_item = primary_plan["items"][0]
            primary_response = {
                "cik": "1234",
                "filings": {
                    "recent": _filing_table(
                        [
                            (
                                "0000001234-25-000001",
                                "2025-02-20",
                                "2024-12-31",
                                "2025-02-20T16:30:00-05:00",
                                "10-K",
                                "abc-20241231.htm",
                            ),
                            (
                                "0000001234-25-000002",
                                "2025-03-31",
                                "2025-03-31",
                                "2025-03-31T18:00:00Z",
                                "8-K",
                                "abc-20250331.htm",
                            ),
                            (
                                "0000001234-24-000003",
                                "2024-09-29",
                                "2024-06-30",
                                None,
                                "10-Q",
                                "abc-20240630.htm",
                            ),
                        ]
                    ),
                    "files": [
                        {
                            "name": "CIK0000001234-submissions-001.json",
                            "filingCount": 4,
                            "filingFrom": "2023-01-01",
                            "filingTo": "2024-09-30",
                        },
                        {
                            "name": "CIK0000001234-submissions-002.json",
                            "filingCount": 4,
                            "filingFrom": "2018-01-01",
                            "filingTo": "2020-12-31",
                        },
                    ],
                },
            }
            _cache_plan_item(cache, primary_item, primary_response)

            history_plan = write_sec_historical_submissions_plan(
                primary_plan_path=primary_path,
                cache=cache,
                output_path=history_path,
                metadata_lookback_days=550,
            )
            self.assertEqual(history_plan["request_count"], 1)
            self.assertEqual(
                history_plan["items"][0]["filename"],
                "CIK0000001234-submissions-001.json",
            )
            self.assertEqual(load_sec_historical_submissions_plan(history_path), history_plan)
            preview = preview_sec_historical_submissions_backfill(
                plan_path=history_path,
                cache=cache,
                progress_path=root / "history_progress.json",
            )
            self.assertEqual(preview["maximum_new_network_requests"], 1)
            self.assertEqual(preview["external_calls"], 0)

            with self.assertRaisesRegex(ValidationError, "metadata cache is incomplete"):
                write_sec_filing_plan_from_submissions(
                    primary_plan_path=primary_path,
                    historical_plan_path=history_path,
                    cache=cache,
                    output_path=body_path,
                )

            history_response = _filing_table(
                [
                    (
                        "0000001234-24-000003",
                        "2024-09-29",
                        "2024-06-30",
                        "2024-09-29T20:00:00Z",
                        "10-Q",
                        "abc-20240630.htm",
                    ),
                    (
                        "0000001234-23-000004",
                        "2023-03-01",
                        "2022-12-31",
                        None,
                        "10-K",
                        "abc-20221231.htm",
                    ),
                    (
                        "0000001234-24-000005",
                        "2024-09-01",
                        "2024-09-01",
                        "2024-09-01T12:00:00Z",
                        "8-K",
                        "abc-20240901.htm",
                    ),
                    (
                        "0000001234-25-000006",
                        "2025-04-01",
                        "2025-04-01",
                        "2025-04-01T12:00:00Z",
                        "8-K",
                        "abc-20250401.htm",
                    ),
                ]
            )
            inner = FakeSecJsonTransport(history_response)
            client = _managed_submissions_client(root, cache, inner)
            events = []
            executed = run_sec_historical_submissions_backfill(
                plan_path=history_path,
                cache=cache,
                progress_path=root / "history_progress.json",
                client=client,
                max_network_requests=1,
                now=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc),
                on_progress=events.append,
            )
            self.assertEqual(executed["status"], "completed")
            self.assertEqual(executed["network_requests_this_run"], 1)
            self.assertEqual([event["status"] for event in events], ["starting", "completed"])

            resumed = run_sec_historical_submissions_backfill(
                plan_path=history_path,
                cache=cache,
                progress_path=root / "history_progress.json",
                client=client,
                max_network_requests=0,
            )
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(resumed["network_requests_this_run"], 0)
            self.assertEqual(inner.calls, 1)

            body_plan = write_sec_filing_plan_from_submissions(
                primary_plan_path=primary_path,
                historical_plan_path=history_path,
                cache=cache,
                output_path=body_path,
                annual_per_as_of=1,
                quarterly_per_as_of=1,
                event_per_as_of=1,
                event_lookback_days=120,
            )
            self.assertEqual(load_sec_filing_backfill_plan(body_path), body_plan)
            accessions = {
                item["accession_number"]: item for item in body_plan["items"]
            }
            self.assertEqual(
                set(accessions),
                {
                    "0000001234-23-000004",
                    "0000001234-24-000003",
                    "0000001234-24-000005",
                    "0000001234-25-000001",
                },
            )
            self.assertNotIn("0000001234-25-000002", accessions)
            self.assertNotIn("0000001234-25-000006", accessions)
            duplicate = accessions["0000001234-24-000003"]
            self.assertEqual(
                duplicate["availability_policy"],
                "timezone_aware_sec_acceptance_datetime",
            )
            self.assertEqual(
                duplicate["metadata_sources"],
                ["CIK0000001234-submissions-001.json", "primary_submissions"],
            )
            self.assertEqual(
                accessions["0000001234-23-000004"]["availability_policy"],
                "next_utc_day_after_filing_date",
            )
            serialized = json.dumps(body_plan).casefold()
            self.assertNotIn("outcome_label", serialized)
            self.assertNotIn('"split"', serialized)

            for item in body_plan["items"]:
                key = RawCacheKey.from_request(
                    "sec_edgar",
                    DataCapability.FILING_DOCUMENTS,
                    "GET",
                    item["source_url"],
                )
                cache.set_text(
                    key,
                    "cached complete SEC filing body " * 100,
                    datetime(2026, 8, 9, tzinfo=timezone.utc),
                )
            body_inner = FakeSecTransport("must not be fetched")
            body_client = _managed_client(root, cache, body_inner)
            body_result = run_sec_filing_backfill(
                plan_path=body_path,
                raw_info_root=root / "raw_info",
                cache=cache,
                progress_path=root / "body_progress.json",
                client=body_client,
                max_network_requests=0,
            )
            self.assertEqual(body_result["status"], "completed")
            self.assertEqual(body_result["network_requests_this_run"], 0)
            self.assertEqual(body_result["cache_hits_this_run"], 4)
            self.assertEqual(body_inner.calls, 0)
            stored = RawInfoStore(root / "raw_info").documents
            self.assertEqual(len(stored), 4)
            self.assertTrue(all(row.metadata["metadata_sources"] for row in stored))
            self.assertTrue(
                all(row.metadata["required_as_of_dates"] for row in stored)
            )

    def test_sec_history_plan_rejects_unsafe_provider_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary_path = _one_company_submissions_plan(root)
            plan = load_sec_submissions_backfill_plan(primary_path)
            response = {
                "cik": "1234",
                "filings": {
                    "recent": _filing_table([]),
                    "files": [
                        {
                            "name": "../secret.json",
                            "filingCount": 1,
                            "filingFrom": "2024-01-01",
                            "filingTo": "2024-09-30",
                        }
                    ],
                },
            }
            cache = RawDataCache(root / "cache")
            _cache_plan_item(cache, plan["items"][0], response)

            with self.assertRaisesRegex(ValidationError, "unsafe"):
                write_sec_historical_submissions_plan(
                    primary_plan_path=primary_path,
                    cache=cache,
                    output_path=root / "history_plan.json",
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


def _managed_submissions_client(
    root: Path,
    cache: RawDataCache,
    inner: FakeSecJsonTransport,
) -> SecEdgarClient:
    ledger = RequestLedger(root / "submissions_ledger.jsonl")
    transport = ManagedHttpTransport(
        "sec_edgar",
        DataCapability.FILINGS,
        inner,
        cache,
        ledger,
        SourceBudget(ledger, {}),
    )
    return SecEdgarClient("test@example.test", transport=transport)


def _managed_company_facts_client(
    root: Path,
    cache: RawDataCache,
    inner: FakeSecJsonTransport,
) -> SecEdgarClient:
    ledger = RequestLedger(root / "company_facts_ledger.jsonl")
    transport = ManagedHttpTransport(
        "sec_edgar",
        DataCapability.FINANCIAL_STATEMENTS,
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


def _one_company_submissions_plan(root: Path) -> Path:
    scope = root / "acquisition_scope.json"
    plan = root / "submissions_plan.json"
    _write_json(
        scope,
        {
            "schema_version": "expanded-case-acquisition-scope-v1",
            "source_inventory_hash": "b" * 64,
            "prediction_dates": ["2024-09-30", "2025-03-31"],
            "company_count": 1,
            "companies": [
                {
                    "company_id": "cik_0000001234",
                    "cik": "1234",
                    "symbol": "ABC",
                    "company_name": "ABC Corp",
                }
            ],
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
    )
    write_sec_submissions_backfill_plan(
        acquisition_scope_path=scope,
        output_path=plan,
    )
    return plan


def _filing_table(
    rows: list[tuple[str, str, str, str | None, str, str]],
) -> dict[str, list[object]]:
    columns = list(zip(*rows)) if rows else [()] * 6
    return {
        "accessionNumber": list(columns[0]),
        "filingDate": list(columns[1]),
        "reportDate": list(columns[2]),
        "acceptanceDateTime": list(columns[3]),
        "form": list(columns[4]),
        "primaryDocument": list(columns[5]),
    }


def _cache_plan_item(
    cache: RawDataCache,
    item: dict[str, object],
    response: dict[str, object],
) -> None:
    key = RawCacheKey.from_request(
        "sec_edgar",
        DataCapability.FILINGS,
        "GET",
        str(item["source_url"]),
    )
    cache.set_json(key, response, datetime(2026, 8, 9, tzinfo=timezone.utc))


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
