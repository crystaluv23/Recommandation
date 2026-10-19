"""Offline collector boundaries; no real credential, socket, label or run."""
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from scripts import collect_reviewed_market_proofs as collector

INVENTORY = Path(__file__).resolve().parents[1] / 'runs/diagnostics/market_source_qualification_20261020_v1/inventory.json'


class FakeClock:
    def __init__(self):
        self.value = 1800000000.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeResponse:
    def __init__(self, raw=b'{"status":"OK","results":[]}', code=200):
        self.raw, self.code = raw, code

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.raw


class CollectorTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root, self.clock = Path(self.temp.name), FakeClock()
        self.output = self.root / 'proofs'
        self.calls = []

    def opener(self, response=None, error=None):
        owner = self
        class FakeOpener:
            def open(self, request, timeout):
                # Reservation and frozen plan must precede the actual send.
                ledger = json.loads((owner.output / 'attempts.json').read_text())
                owner.assertEqual(ledger[-1]['state'], 'attempted')
                owner.assertTrue((owner.output / 'plan.json').is_file())
                owner.assertEqual(timeout, 30)
                owner.assertNotIn('offline-test-key', request.full_url)
                owner.calls.append((request, owner.clock.now()))
                if error:
                    raise error
                return response or FakeResponse()
        return FakeOpener()

    def collect(self, count, **kwargs):
        return collector.collect(INVENTORY, self.output, count,
            opener=kwargs.pop('opener', self.opener()), now=self.clock.now,
            sleep=self.clock.sleep, credential_loader=lambda: 'offline-test-key', **kwargs)

    def test_fixed_plan_two_then_twenty_eight_resume_and_rolling_throttle(self):
        self.assertEqual(self.collect(2), {'received': 2, 'pending': 28})
        plan = (self.output / 'plan.json').read_bytes()
        self.assertEqual(self.collect(28), {'received': 30, 'pending': 0})
        self.assertEqual(len(self.calls), 30)
        self.assertEqual((self.output / 'plan.json').read_bytes(), plan)
        for index in range(5, 30):
            self.assertGreaterEqual(self.calls[index][1] - self.calls[index - 5][1], 60)
        self.assertEqual(self.collect(1), {'received': 30, 'pending': 0})
        self.assertEqual(len(self.calls), 30)
        for path in self.output.iterdir():
            if path.is_file():
                self.assertNotIn(b'offline-test-key', path.read_bytes())

    def test_bad_budget_inventory_binding_and_request_whitelist_precede_credentials(self):
        loader = lambda: self.fail('credential loading forbidden')
        with self.assertRaises(ValueError):
            collector.collect(INVENTORY, self.output, 31, credential_loader=loader)
        bad = self.root / 'changed.json'
        value = json.loads(INVENTORY.read_text())
        value['proposed_readonly_proof_requests'][0]['endpoint'] = 'https://example.invalid/redirect'
        bad.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'inventory binding'):
            collector.collect(bad, self.output, 1, credential_loader=loader)
        with patch.object(collector, 'INVENTORY_SHA256', collector._sha(bad)):
            with self.assertRaisesRegex(ValueError, 'whitelist'):
                collector.collect(bad, self.output, 1, credential_loader=loader)
        self.assertFalse(self.output.exists())

    def test_bound_original_drift_and_duplicate_ids_reject_before_credentials(self):
        for mutation in ('binding', 'duplicate'):
            value = json.loads(INVENTORY.read_text())
            if mutation == 'binding':
                value['input_bindings_before'][0]['sha256'] = '0' * 64
                value['input_bindings_after'][0]['sha256'] = '0' * 64
            else:
                value['proposed_readonly_proof_requests'][1]['proof_id'] = value['proposed_readonly_proof_requests'][0]['proof_id']
            bad = self.root / (mutation + '.json')
            bad.write_text(json.dumps(value))
            with patch.object(collector, 'INVENTORY_SHA256', collector._sha(bad)):
                with self.assertRaises(ValueError):
                    collector.collect(bad, self.output, 1,
                        credential_loader=lambda: self.fail('must reject before credentials'))

    def test_failure_timeout_and_credential_echo_stop_without_retry(self):
        for kind in ('http', 'provider', 'pagination', 'timeout', 'credential'):
            self.output = self.root / kind
            response = {'http': FakeResponse(code=429),
                'provider': FakeResponse(b'{"status":"ERROR"}'),
                'pagination': FakeResponse(b'{"status":"OK","next_url":"later"}'),
                'credential': FakeResponse(b'{"status":"OK","echo":"offline-test-key"}')}.get(kind)
            opener = self.opener(response=response,
                                 error=TimeoutError() if kind == 'timeout' else None)
            before = len(self.calls)
            with self.assertRaisesRegex(ValueError, 'no retry'):
                self.collect(2, opener=opener)
            self.assertEqual(len(self.calls) - before, 1)
            if kind == 'credential':
                self.assertEqual(list(self.output.glob('*.response.json')), [])
            with self.assertRaises(ValueError):
                self.collect(1, opener=opener)
            self.assertEqual(len(self.calls) - before, 1)

    def test_receipt_tamper_interrupted_attempt_and_plan_drift_forbid_resume(self):
        self.collect(1)
        body = next(self.output.glob('*.response.json'))
        body.write_bytes(body.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'receipt binding'):
            self.collect(1)
        self.output = self.root / 'interrupted'
        self.collect(1)
        ledger = json.loads((self.output / 'attempts.json').read_text())
        ledger[0]['state'] = 'attempted'
        collector.atomic_write_json(self.output / 'attempts.json', ledger)
        with self.assertRaisesRegex(ValueError, 'new authorization'):
            self.collect(1)
        self.output = self.root / 'plan-drift'
        self.collect(1)
        plan = json.loads((self.output / 'plan.json').read_text())
        plan['max_cumulative_attempts'] = 31
        collector.atomic_write_json(self.output / 'plan.json', plan)
        with self.assertRaisesRegex(ValueError, 'plan differs'):
            self.collect(1)

    def test_redirect_handler_refuses_redirect(self):
        self.assertIsNone(collector._NoRedirect().redirect_request(
            None, None, 302, 'redirect', {}, 'https://example.invalid'))
