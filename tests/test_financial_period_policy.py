"""Approved reported-window policies through actual execution and bounded input reads."""
from dataclasses import replace
import json
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.signal_library import SignalResult, SignalValue, signal_result_model_view
from tests.test_signal_measurement_input_selection import AS_OF, COMPANY, document, executor, fact, noise, spec


ACCEL = 'financial.revenue_acceleration_adjacent'
MARGIN = 'financial.gross_margin_change_yoy'
WINDOWS = (('2025-01-01', '2025-03-31', 150), ('2024-01-01', '2024-03-31', 100),
           ('2024-10-01', '2024-12-31', 120), ('2023-10-01', '2023-12-31', 100))


def revenues(windows=WINDOWS):
    return [fact('Revenues', end, value, start) for start, end, value in windows]


def specification(function):
    policies = {ACCEL: ('financial.revenue_acceleration', 'adjacent_yoy'),
                MARGIN: ('financial.gross_margin_change', 'same_window_yoy')}
    actual, policy = policies.get(function, (function, None))
    parameters = {} if policy is None else {'period_policy': policy}
    return replace(spec(actual, query=('revenue sales gross profit',)),
        parameters={'positive_min': .08 if function == MARGIN else .05,
                    'negative_max': -.02 if function == MARGIN else -.05,
                    **parameters})


def run(function, rows, *, extra=()):
    s = specification(function)
    ex = executor(s, (document('reported-windows', rows), *extra))
    batch = ex.execute_batch((s.ref,), company_id=COMPANY, as_of=AS_OF)
    return ex, batch.results[0]


class FinancialPeriodPolicyTests(TestCase):
    def setUp(self):
        guard = patch('socket.socket', side_effect=AssertionError('network forbidden'))
        guard.start(); self.addCleanup(guard.stop)

    def test_quarter_acceleration_uses_immediate_quarter_not_same_window_year_change(self):
        ex, result = run(ACCEL, revenues()+revenues((('2023-01-01','2023-03-31',80),)))
        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertAlmostEqual(result.measurement.value, .3)
        self.assertNotAlmostEqual(result.measurement.value, .25)
        self.assertEqual(result.measurement.period_end, '2025-03-31')
        self.assertEqual(result.measurement.unit, 'fraction_difference')
        self.assertEqual(len(result.supporting_evidence), 4)
        saved = SignalResult.from_dict(json.loads(json.dumps(result.to_dict())))
        self.assertEqual(saved.to_dict(), result.to_dict())
        view = signal_result_model_view(result, classification_contract=ex.classification_contracts_for((result,))[result.ref])
        self.assertIn('immediately previous', str(view))
        self.assertAlmostEqual(view['interpretation']['measurement_context']['numeric_measurement']['value'], .3)

    def test_margin_is_same_window_yoy_with_prior_quarter_as_counterexample(self):
        rows = revenues()+[fact('GrossProfit','2025-03-31',22.5,'2025-01-01'),
            fact('GrossProfit','2024-03-31',10,'2024-01-01'),
            fact('GrossProfit','2024-12-31',30,'2024-10-01')]
        _, result = run(MARGIN, rows)
        self.assertAlmostEqual(result.measurement.value, .05)
        self.assertEqual(result.value, SignalValue.NEUTRAL)
        _, legacy = run('financial.gross_margin_change', rows)
        self.assertAlmostEqual(legacy.measurement.value, -.1)

    def test_exact_default_thresholds_and_nearby_values_do_not_use_an_epsilon(self):
        for current, expected in ((135, SignalValue.NEGATIVE), (135.0001, SignalValue.NEUTRAL),
                                  (134.9999, SignalValue.NEGATIVE)):
            windows = ((WINDOWS[0][0],WINDOWS[0][1],current), WINDOWS[1],
                       (WINDOWS[2][0],WINDOWS[2][1],140), WINDOWS[3])
            _, result = run(ACCEL, revenues(windows))
            self.assertEqual(result.value, expected)
        for profit, expected in ((18, SignalValue.POSITIVE), (17.9999, SignalValue.NEUTRAL),
                                 (18.0001, SignalValue.POSITIVE)):
            rows = revenues(((WINDOWS[0][0],WINDOWS[0][1],100),WINDOWS[1]))+[
                fact('GrossProfit','2025-03-31',profit,'2025-01-01'),
                fact('GrossProfit','2024-03-31',10,'2024-01-01')]
            _, result = run(MARGIN, rows)
            self.assertEqual(result.value, expected)

    def test_missing_immediate_quarter_never_skips_to_an_earlier_supported_pair(self):
        rows = revenues((WINDOWS[0], WINDOWS[1], ('2024-07-01','2024-09-30',120),
                         ('2023-07-01','2023-09-30',100)))
        _, result = run(ACCEL, rows)
        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertIn('no older-pair fallback', result.interpretation)
        _, legacy = run('financial.revenue_acceleration', rows)
        self.assertIsNotNone(legacy.measurement)

    def test_missing_latest_yoy_or_profit_never_uses_an_older_complete_anchor(self):
        for function, rows in ((ACCEL, revenues((WINDOWS[0], WINDOWS[2], WINDOWS[3],
                ('2022-10-01','2022-12-31',80)))),
                (MARGIN, revenues()+[fact('GrossProfit','2024-12-31',30,'2024-10-01'),
                    fact('GrossProfit','2023-12-31',20,'2023-10-01')])):
            with self.subTest(function=function):
                _, result = run(function, rows)
                self.assertEqual(result.value, SignalValue.UNAVAILABLE)
                self.assertIsNone(result.measurement)

    def test_annual_adjacent_growth_uses_three_windows_and_never_mixes_with_quarters(self):
        annual = revenues((('2024-01-01','2024-12-31',150), ('2023-01-01','2023-12-31',100),
                           ('2022-01-01','2022-12-31',80)))
        _, result = run(ACCEL, annual)
        self.assertAlmostEqual(result.measurement.value, .25)
        self.assertEqual(len(result.supporting_evidence), 3)
        _, mixed = run(ACCEL, annual+revenues((WINDOWS[0], WINDOWS[1])))
        self.assertEqual(mixed.value, SignalValue.UNAVAILABLE)

    def test_fiscal_month_boundaries_and_leap_day_require_exact_shifts(self):
        for windows in ((('2025-02-01','2025-04-30',150), ('2024-02-01','2024-04-30',100),
                         ('2024-11-01','2025-01-31',120), ('2023-11-01','2024-01-31',100)),
                        (('2024-12-01','2025-02-28',150), ('2023-12-01','2024-02-29',100),
                         ('2024-09-01','2024-11-30',120), ('2023-09-01','2023-11-30',100))):
            with self.subTest(windows=windows):
                _, result = run(ACCEL, revenues(windows))
                self.assertAlmostEqual(result.measurement.value, .3)

    def test_ytd_margin_supported_but_acceleration_never_derives_standalone_quarters(self):
        windows = (('2024-07-01','2024-12-31',150), ('2023-07-01','2023-12-31',100))
        rows = revenues(windows)+[fact('GrossProfit','2024-12-31',30,'2024-07-01'),
                                 fact('GrossProfit','2023-12-31',10,'2023-07-01')]
        _, margin = run(MARGIN, rows)
        self.assertAlmostEqual(margin.measurement.value, .1)
        _, acceleration = run(ACCEL, rows)
        self.assertEqual(acceleration.value, SignalValue.UNAVAILABLE)

    def test_same_end_standalone_quarter_precedes_ytd_without_formula_fallback(self):
        annual = revenues((('2024-01-01','2024-12-31',150), ('2023-01-01','2023-12-31',100),
                           ('2022-01-01','2022-12-31',80)))
        _, result = run(ACCEL, annual+revenues((('2024-10-01','2024-12-31',120),)))
        self.assertEqual(result.value, SignalValue.UNAVAILABLE)

    def test_unsupported_week_calendar_and_stub_remain_unknown(self):
        for start, end in (('2025-01-15','2025-03-31'), ('2024-12-30','2025-03-30')):
            for function in (ACCEL, MARGIN):
                with self.subTest(start=start, function=function):
                    _, result = run(function, revenues(((start,end,150), *WINDOWS[1:])))
                    self.assertEqual(result.value, SignalValue.UNAVAILABLE)
                    self.assertIn('calendar proof', result.interpretation)

    def test_conflicts_and_latest_anchor_survive_actual_ten_document_selection(self):
        current = document('latest', revenues((WINDOWS[0],)))
        comparison = document('comparisons', revenues(WINDOWS[1:]))
        conflict = document('conflict', revenues((('2024-01-01','2024-03-31',110),)))
        for extra, fragment in (((conflict,), 'Conflicting'), ((), None)):
            s = specification(ACCEL)
            ex = executor(s, (*noise(), current, comparison, *extra))
            resolution = ex.prepare_inputs((s.ref,), company_id=COMPANY, as_of=AS_OF)[0]
            chosen = {ref.document_id for ref in resolution.documents}
            self.assertTrue({'latest','comparisons'} <= chosen)
            self.assertLessEqual(len(chosen), 10)
            result = ex.execute_batch((s.ref,), company_id=COMPANY, as_of=AS_OF).results[0]
            if fragment:
                self.assertIn('conflict', chosen)
                self.assertEqual(result.value, SignalValue.UNAVAILABLE)
                self.assertIn(fragment, result.interpretation)
            else:
                self.assertAlmostEqual(result.measurement.value, .3)
