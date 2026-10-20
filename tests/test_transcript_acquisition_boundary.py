"""Synthetic/offline checks of the unsupported historical transcript producer.

Local-first positives prove existing store mechanics only, not reviewed transcript
proof or completion of the substantive transcript capability.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.data.acquisition import AlphaVantageTranscriptAdapter
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    AcquisitionFailure,
    AcquisitionResult,
    DataAcquisitionBudget,
    DataAcquisitionPolicy,
    DataGapReason,
    EvidenceResolver,
    RawInfoRequest,
    RawInfoResolution,
)
from stock_opportunity_agent.data.sources.alpha_vantage import AlphaVantageClient
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.state import (
    ManagedHttpTransport,
    RawDataCache,
    RequestLedger,
    SourceBudget,
)

AS_OF = datetime(2025, 1, 1, tzinfo=timezone.utc)
ALIASES = ('earnings_call', 'transcript', 'earnings_transcript')


class CalendarAndEchoClient:
    """A complete provider calendar/quarter echo is not public-time proof."""

    transport = None

    def __init__(self):
        self.calls = []

    def earnings(self, symbol):
        self.calls.append(('earnings', symbol))
        return {
            'symbol': symbol,
            'annualEarnings': [
                {'fiscalDateEnding': '2024-01-31'},
                {'fiscalDateEnding': '2025-01-31'},
            ],
            'quarterlyEarnings': [
                {'fiscalDateEnding': end, 'reportedDate': reported}
                for end, reported in (
                    ('2024-04-30', '2024-05-16'),
                    ('2024-07-31', '2024-08-15'),
                    ('2024-10-31', '2024-11-19'),
                    ('2025-01-31', '2025-02-20'),
                )
            ],
        }

    def earnings_call_transcript(self, symbol, quarter):
        self.calls.append(('transcript', symbol, quarter))
        return {
            'symbol': symbol,
            'quarter': quarter,
            'transcript': [
                {
                    'speaker': 'CEO',
                    'content': 'Complete-looking remarks and closing statement.',
                }
            ],
        }


def policy():
    return DataAcquisitionPolicy(
        enabled=True,
        allowed_providers=('alpha_vantage', 'sec_edgar'),
        allowed_capabilities=('transcripts', 'filings'),
        allowed_source_types=ALIASES + ('filing',),
        max_requests_per_cycle=10,
        max_requests_per_run=10,
    )


def request(alias='earnings_call'):
    return RawInfoRequest(
        'transcript',
        'Read historical conference content.',
        (alias,),
        lookback_days=365,
        max_documents=1,
    )


def local_document(source_type='earnings_call'):
    return RawInfoDocument.create(
        document_id='synthetic-local',
        company_id='issuer',
        source_type=source_type,
        published_at=AS_OF,
        available_at=AS_OF,
        content='Synthetic already-local source; this is not an admission proof.',
    )


class TranscriptAcquisitionBoundaryTests(TestCase):
    def test_calendar_and_provider_quarter_echo_do_not_admit_any_alias(self):
        for alias in ALIASES:
            with self.subTest(alias=alias):
                client = CalendarAndEchoClient()
                with self.assertRaises(AcquisitionFailure) as caught:
                    AlphaVantageTranscriptAdapter(client).acquire(
                        request(alias),
                        company_id='issuer',
                        identity={'ticker': 'TEST'},
                        as_of=AS_OF,
                    )
                self.assertEqual(
                    caught.exception.reason, DataGapReason.HISTORICAL_DATA_UNAVAILABLE
                )
                self.assertIn('proof', str(caught.exception).casefold())
                self.assertEqual(client.calls, [])

    def test_none_client_never_becomes_a_provider_error(self):
        with self.assertRaises(AcquisitionFailure) as caught:
            AlphaVantageTranscriptAdapter(None).acquire(
                request(), company_id='issuer', identity={}, as_of=AS_OF
            )
        self.assertEqual(
            caught.exception.reason, DataGapReason.HISTORICAL_DATA_UNAVAILABLE
        )

    def test_capability_probe_reports_historical_limitation_without_provider_io(self):
        client = CalendarAndEchoClient()
        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(AlphaVantageTranscriptAdapter(client),),
            policy=policy(),
        )
        self.assertFalse(resolver.can_acquire(request()))
        self.assertEqual(
            resolver.acquisition_unavailability_reason(request()),
            'historical_data_unavailable',
        )
        self.assertNotIn('earnings_call', resolver.available_source_types)
        self.assertEqual(client.calls, [])
        self.assertEqual(resolver.budget.run_requests, 0)

    def test_real_resolver_gap_roundtrip_and_repeat_memo_preserve_empty_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RawInfoStore(root / 'oracle')
            client = CalendarAndEchoClient()
            resolver = EvidenceResolver(
                store,
                adapters=(AlphaVantageTranscriptAdapter(client),),
                policy=policy(),
                budget=DataAcquisitionBudget(
                    ledger_path=root / 'budget.jsonl', cycle_id=1
                ),
            )
            result = resolver.resolve(
                request(), company_id='issuer', identity={'ticker': 'TEST'}, as_of=AS_OF
            )
            self.assertEqual(result.status, 'unresolved')
            self.assertEqual(result.gap.reason, DataGapReason.HISTORICAL_DATA_UNAVAILABLE)
            self.assertEqual(result.appended_documents, ())
            self.assertEqual(store.documents, ())
            path = root / 'resolution.json'
            path.write_text(json.dumps(result.to_dict()))
            restored = RawInfoResolution.from_dict(json.loads(path.read_text()))
            self.assertEqual(restored.to_dict(), result.to_dict())
            again = resolver.resolve(
                request(), company_id='issuer', identity={'ticker': 'TEST'}, as_of=AS_OF
            )
            self.assertEqual(again.gap.reason, DataGapReason.HISTORICAL_DATA_UNAVAILABLE)
            self.assertIn('acquisition_failure_reused', [event.kind for event in again.events])
            # One adapter reservation, zero provider requests.
            self.assertEqual(resolver.budget.run_requests, 1)
            self.assertEqual(RawInfoStore(root / 'oracle').documents, ())
            self.assertEqual(client.calls, [])

    def test_local_first_read_is_unchanged_without_endorsing_its_public_time(self):
        for alias in ALIASES:
            with self.subTest(alias=alias):
                doc = local_document(alias)
                client = CalendarAndEchoClient()
                resolver = EvidenceResolver(
                    RawInfoStore(documents=(doc,)),
                    adapters=(AlphaVantageTranscriptAdapter(client),),
                    policy=policy(),
                )
                result = resolver.resolve(
                    request(alias), company_id='issuer', identity={}, as_of=AS_OF
                )
                self.assertEqual(result.status, 'resolved')
                self.assertEqual(resolver.load_documents(result, as_of=AS_OF), (doc,))
                self.assertEqual(resolver.budget.run_requests, 0)
                self.assertEqual(client.calls, [])

    def test_independent_fallback_source_continues_after_transcript_failure(self):
        doc = local_document('filing')

        class FilingAdapter:
            provider = 'sec_edgar'
            source_types = ('filing',)
            capabilities = ('filings',)

            def __init__(self):
                self.calls = 0

            def acquire(self, *args, **kwargs):
                self.calls += 1
                return AcquisitionResult(documents=(doc,))

        client = CalendarAndEchoClient()
        filing = FilingAdapter()
        resolver = EvidenceResolver(
            RawInfoStore(),
            adapters=(AlphaVantageTranscriptAdapter(client), filing),
            policy=policy(),
        )
        result = resolver.resolve(
            RawInfoRequest(
                'mixed', 'Read a reachable source.', ('earnings_call', 'filing'),
                max_documents=1,
            ),
            company_id='issuer',
            identity={'ticker': 'TEST'},
            as_of=AS_OF,
        )
        self.assertEqual(result.status, 'resolved')
        self.assertEqual(
            [ref.document_id for ref in result.documents], [doc.document_id]
        )
        self.assertEqual(filing.calls, 1)
        self.assertEqual(client.calls, [])
        failed = [
            event.details for event in result.events if event.kind == 'acquisition_failed'
        ]
        self.assertEqual(failed[0]['reason'], 'historical_data_unavailable')

    def test_disabled_policy_remains_unauthorized_and_does_not_call_provider(self):
        client = CalendarAndEchoClient()
        resolver = EvidenceResolver(
            RawInfoStore(), adapters=(AlphaVantageTranscriptAdapter(client),)
        )
        result = resolver.resolve(
            request(), company_id='issuer', identity={'ticker': 'TEST'}, as_of=AS_OF
        )
        self.assertEqual(result.gap.reason, DataGapReason.EXTERNAL_NOT_AUTHORIZED)
        self.assertEqual(client.calls, [])

    def test_raw_client_and_managed_cache_remain_available_without_pit_materialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = RequestLedger(root / 'requests.jsonl')
            response = {
                'symbol': 'TEST',
                'quarter': '2024Q3',
                'transcript': [
                    {'content': 'Provider raw response, not reviewed availability proof.'}
                ],
            }

            class Inner:
                def __init__(self):
                    self.calls = 0

                def get_json(self, url, headers):
                    self.calls += 1
                    return response

            inner = Inner()
            cache = RawDataCache(root / 'cache')
            transport = ManagedHttpTransport(
                'alpha_vantage', DataCapability.TRANSCRIPTS, inner, cache, ledger,
                SourceBudget(ledger), clock=lambda: AS_OF,
            )
            client = AlphaVantageClient('synthetic-test-key', transport=transport)
            self.assertEqual(client.earnings_call_transcript('TEST', '2024Q3'), response)
            self.assertEqual(client.earnings_call_transcript('TEST', '2024Q3'), response)
            self.assertEqual(inner.calls, 1)
            self.assertEqual(
                [entry.status.value for entry in ledger.entries()],
                ['fetched', 'cache_hit'],
            )
            self.assertEqual(len(list((root / 'cache').rglob('*.json'))), 1)
