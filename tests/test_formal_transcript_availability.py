"""Formal transcript collection rejects unproved public-content clocks."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
import unittest

from scripts import run_cold_start_formal as formal
from stock_opportunity_agent.data import DataSourceError


class TranscriptClient:
    """Local provider substitute exposing date clues and an incomplete body."""

    def __init__(self, item=None, body=None, fail=False):
        self.item = item or {"id": "provider-date", "date": "2025-04-29"}
        self.body = body or {"transcript": "Prepared remarks only; no Q&A or closing."}
        self.fail = fail
        self.calls = []

    def transcript_list(self, symbol):
        self.calls.append(("transcript_list", symbol))
        if self.fail:
            raise DataSourceError("fixture provider is unavailable")
        return {"transcripts": [self.item]}

    def transcript(self, transcript_id):
        self.calls.append(("transcript", transcript_id))
        return self.body


class FormalTranscriptAvailabilityTests(unittest.TestCase):
    """Exercise the actual formal producer without external acquisition."""

    def collect(self, client, *, limit=1, warnings=None):
        actual_warnings = [] if warnings is None else warnings
        result = formal._transcript_documents_for_candidate(
            SimpleNamespace(max_transcripts_per_symbol=limit),
            SimpleNamespace(symbol="SYNTH", inflection_date=date(2025, 5, 31)),
            context_start=date(2025, 1, 1),
            created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
            finnhub_client=client,
            warnings=actual_warnings,
        )
        return result, actual_warnings

    def assert_unproved_skipped(self, client):
        result, warnings = self.collect(client)
        self.assertEqual(result, [])
        self.assertEqual(client.calls, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("SYNTH", warnings[0])
        self.assertIn("historical_data_unavailable", warnings[0])
        self.assertIn("complete", warnings[0].lower())
        self.assertIn("public", warnings[0].lower())
        self.assertIn("proof", warnings[0].lower())

    def test_provider_date_and_partial_body_are_not_publication_proof(self):
        self.assert_unproved_skipped(TranscriptClient())

    def test_quarter_end_fallback_and_partial_body_are_not_proof(self):
        self.assert_unproved_skipped(TranscriptClient(item={"id": "quarter-only", "year": 2025, "quarter": 1}))

    def test_complete_looking_body_without_reviewed_time_proof_stays_unavailable(self):
        self.assert_unproved_skipped(TranscriptClient(body={"transcript": "Welcome. Prepared remarks. Questions and answers. This concludes the call."}))

    def test_guard_runs_before_even_the_list_provider_call(self):
        self.assert_unproved_skipped(TranscriptClient(fail=True))

    def test_disabled_request_does_not_warn_or_call_provider(self):
        for limit in (0, -1):
            with self.subTest(limit=limit):
                client = TranscriptClient(fail=True)
                result, warnings = self.collect(client, limit=limit)
                self.assertEqual((result, warnings, client.calls), ([], [], []))

    def test_missing_client_does_not_claim_a_proof_failure(self):
        result, warnings = self.collect(None)
        self.assertEqual((result, warnings), ([], []))

    def test_existing_warnings_are_preserved(self):
        warnings = ["existing filing warning"]
        client = TranscriptClient()
        result, actual = self.collect(client, warnings=warnings)
        self.assertIs(actual, warnings)
        self.assertEqual(result, [])
        self.assertEqual(warnings[0], "existing filing warning")
        self.assertEqual(len(warnings), 2)
        self.assertIn("historical_data_unavailable", warnings[1])
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
