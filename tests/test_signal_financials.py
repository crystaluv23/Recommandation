from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    default_deterministic_signal_functions,
    deterministic_signal_function_contracts,
    SignalCoverage,
    SignalExecutionType,
    SignalExecutor,
    SignalModality,
    SignalSpec,
    SignalValue,
)


AS_OF = datetime(2025, 2, 1, tzinfo=timezone.utc)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SecFinancialSignalTests(TestCase):
    def test_signal_modality_is_explicit_without_rewriting_legacy_specs(self) -> None:
        from stock_opportunity_agent.models import ValidationError

        structured = _spec(
            "cash_reserves", "financial.cash_reserves", 30.0, 10.0
        )
        self.assertEqual(structured.to_dict()["modality"], "structured")
        legacy = dict(structured.to_dict())
        legacy.pop("modality")
        self.assertIsNone(SignalSpec.from_dict(legacy).modality)
        self.assertNotIn("modality", SignalSpec.from_dict(legacy).to_dict())
        with self.assertRaisesRegex(ValidationError, "structured.*deterministic"):
            SignalSpec(
                signal_id="invalid_structured",
                version=1,
                category="financial",
                description="Invalid structured executor.",
                execution_type=SignalExecutionType.LLM,
                source_types=("financials",),
                modality=SignalModality.STRUCTURED,
                skill_file="skills/invalid.md",
            )

    def test_market_measurements_cite_actual_adjusted_price_anchors(self) -> None:
        from stock_opportunity_agent.signal_library import (
            _max_drawdown_signal, _price_momentum_signal,
        )
        from stock_opportunity_agent.models import ValidationError
        prices = [10.0, 20.0, 15.0, 5.0, 12.0]
        rows = [{"as_of_date": f"2025-01-0{i + 1}", "close": price * 2,
                 "adjusted_close": price} for i, price in enumerate(prices)]
        document = RawInfoDocument.create(
            document_id="market", company_id="issuer_1", source_type="market_data",
            published_at=AS_OF, available_at=AS_OF,
            content=json.dumps(rows, indent=2), metadata={"prices": prices},
        )
        spec = _spec("drawdown", "market.max_drawdown_1y", 0.0, -0.1)
        result = _max_drawdown_signal(spec, (document,), AS_OF)
        self.assertEqual(result.interpretation, "max_drawdown_1y=-0.75")
        self.assertEqual([json.loads(e.exact_span) for e in result.supporting_evidence],
                         [rows[i] for i in (0, 1, 3, 4)])
        from dataclasses import replace
        momentum = replace(spec, parameters={"lookback_observations": 2})
        result = _price_momentum_signal(momentum, (document,), AS_OF)
        self.assertEqual(result.interpretation, "price_momentum_2d=-0.2")
        self.assertEqual([json.loads(e.exact_span) for e in result.supporting_evidence], rows[2::2])
        for evidence in result.supporting_evidence:
            self.assertIn(evidence.exact_span, document.content)
        with self.assertRaisesRegex(ValidationError, "do not match"):
            _max_drawdown_signal(spec, (replace(document, metadata={"prices": list(reversed(prices))}),), AS_OF)
        for invalid in (float("nan"), float("inf"), True):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                _max_drawdown_signal(spec, (replace(document, metadata={"prices": [invalid]}),), AS_OF)

    def test_function_contracts_follow_actual_registry_overrides(self) -> None:
        functions = default_deterministic_signal_functions()
        contracts = deterministic_signal_function_contracts(functions)
        self.assertEqual(set(contracts), set(functions))
        self.assertTrue(all("No measurement description" not in row for row in contracts.values()))
        self.assertIn("positive revenue", contracts["financial.operating_cash_flow_margin"])

        def replacement(*args):
            """Measure a custom observable with its own inputs."""

        def undocumented(*args):
            pass

        supplied = {
            "financial.operating_cash_flow_margin": replacement,
            "custom.unknown": undocumented,
        }
        self.assertEqual(deterministic_signal_function_contracts(supplied), {
            "financial.operating_cash_flow_margin": replacement.__doc__,
            "custom.unknown": "No measurement description supplied.",
        })

    def test_ifrs_namespace_and_revenue_aliases_preserve_pit_gross_margin(self) -> None:
        for alias in ("RevenueFromContractsWithCustomers", "RevenueFromSaleOfGoods"):
            with self.subTest(alias=alias):
                original = json.loads(_scoped_company_facts_content())
                facts = original["facts"].pop("us-gaap")
                facts[alias] = facts.pop("Revenues")
                original["facts"]["ifrs-full"] = facts
                spec = _spec("gross_margin_change", "financial.gross_margin_change", 0.05, -0.05)
                content = json.dumps(original, sort_keys=True, separators=(",", ":"))
                result = SignalExecutor(
                    _snapshot((spec,)), RawInfoStore(documents=(_document("ifrs", content),))
                ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
                self.assertEqual(result.value, SignalValue.POSITIVE)
                self.assertEqual(result.interpretation, "gross_margin_change=0.1")
                for evidence in result.supporting_evidence:
                    self.assertIn(evidence.exact_span, content)
                    self.assertNotIn('"val":999', evidence.exact_span)

    def test_raw_financial_namespaces_are_not_mixed(self) -> None:
        payload = json.loads(_scoped_company_facts_content())
        payload["facts"]["ifrs-full"] = {
            "GrossProfit": payload["facts"]["us-gaap"].pop("GrossProfit")
        }
        spec = _spec("gross_margin_change", "financial.gross_margin_change", 0.05, -0.05)
        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document(
                "mixed", json.dumps(payload, sort_keys=True, separators=(",", ":"))
            ),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        self.assertEqual(result.value, SignalValue.UNAVAILABLE)

    def test_ifrs_cash_and_weighted_shares_aliases(self) -> None:
        payload = json.loads(_scoped_company_facts_content())
        facts = payload["facts"].pop("us-gaap")
        facts["CashAndCashEquivalents"] = facts.pop("CashAndCashEquivalentsAtCarryingValue")
        facts["WeightedAverageShares"] = facts.pop("WeightedAverageNumberOfSharesOutstandingBasic")
        payload["facts"]["ifrs-full"] = facts
        specs = (_spec("cash_reserves", "financial.cash_reserves", 30, 10),
                 _spec("net_share_retirement_yoy", "financial.net_share_retirement_yoy", 0.02, -0.05))
        result = SignalExecutor(_snapshot(specs), RawInfoStore(documents=(_document(
            "ifrs-aliases", json.dumps(payload, sort_keys=True, separators=(",", ":"))
        ),))).execute_batch([s.ref for s in specs], company_id="issuer_1", as_of=AS_OF)
        self.assertTrue(all(x.value is SignalValue.POSITIVE for x in result.results))

    def test_ratios_accept_same_currency_but_never_mix_currencies(self) -> None:
        payload = json.loads(_scoped_company_facts_content())
        facts = payload["facts"]["us-gaap"]
        for item in facts.values():
            if "USD" in item["units"]:
                item["units"]["CAD"] = item["units"].pop("USD")
        specs = (_spec("gross_margin_change", "financial.gross_margin_change", 0.05, -0.05),
                 _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.2, -0.1),
                 _spec("operating_cash_flow_margin", "financial.operating_cash_flow_margin", 0.1, 0))
        def execute():
            return SignalExecutor(_snapshot(specs), RawInfoStore(documents=(_document(
                "cad-ratios", json.dumps(payload, sort_keys=True, separators=(",", ":"))
            ),))).execute_batch([s.ref for s in specs], company_id="issuer_1", as_of=AS_OF)
        self.assertTrue(all(x.value is SignalValue.POSITIVE for x in execute().results))
        for name in ("GrossProfit", "NetCashProvidedByUsedInOperatingActivities"):
            units = facts[name]["units"]
            units["USD"] = units.pop("CAD")
        result = {x.signal_id: x for x in execute().results}
        self.assertEqual(result["gross_margin_change"].value, SignalValue.UNAVAILABLE)
        self.assertEqual(result["operating_cash_flow_margin"].value, SignalValue.UNAVAILABLE)

    def test_market_history_selection_is_order_independent_and_conflicts_fail(self) -> None:
        prices = [100.0 + index for index in range(127)]
        def document(name, values, end="2025-01-20"):
            return _document(name, json.dumps({"prices": values}), "market_data",
                             metadata={"prices": values, "end": end})
        full = document("full", prices)
        short = document("short", prices[-31:])
        spec = SignalSpec(signal_id="price_momentum_126d", version=1, category="market",
                          description="Momentum.", execution_type=SignalExecutionType.DETERMINISTIC,
                          function="market.price_momentum_126d", source_types=("market_data",),
                          parameters={"lookback_observations": 126, "positive_min": 0.2, "negative_max": -0.2})
        from stock_opportunity_agent.signal_library import _price_momentum_signal
        for docs in ((full, short), (short, full)):
            result = _price_momentum_signal(spec, docs, AS_OF)
            self.assertEqual(result.interpretation, "price_momentum_126d=1.26")
        from stock_opportunity_agent.models import ValidationError
        with self.assertRaisesRegex(ValidationError, "conflicting market series"):
            _price_momentum_signal(spec, (full, document("conflict", [999.0])), AS_OF)
        latest_short = document("latest", prices[-31:], "2025-01-21")
        result = _price_momentum_signal(spec, (full, latest_short), AS_OF)
        self.assertEqual(result.value, SignalValue.UNAVAILABLE)

    def test_v18_current_revenue_alias_wins_and_stale_fallback_is_unavailable(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/signal_financials/"
                "v18_wynn_revenue_alias_and_staleness.json"
            ).read_text()
        )
        as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        specs = (
            _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.2, 0.0),
            _spec(
                "operating_cash_flow_margin",
                "financial.operating_cash_flow_margin",
                0.1,
                0.0,
            ),
        )

        def execute(payload: object) -> tuple:
            document = _document(
                "wynn-facts",
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            )
            return SignalExecutor(
                _snapshot(specs), RawInfoStore(documents=(document,))
            ).execute_batch(
                tuple(spec.ref for spec in specs),
                company_id="issuer_1",
                as_of=as_of,
            ).results

        current = execute(fixture["current_payload"])
        self.assertEqual(current[0].interpretation, "revenue_growth_yoy=-0.0872356")
        self.assertEqual(
            current[1].interpretation, "operating_cash_flow_margin=0.0786722"
        )
        cited = " ".join(
            evidence.exact_span
            for result in current
            for evidence in result.supporting_evidence
        )
        self.assertIn('"end":"2025-03-31"', cited)
        self.assertNotIn('"end":"2018-12-31"', cited)

        stale = execute(fixture["stale_payload"])
        self.assertEqual(
            tuple(result.value for result in stale),
            (SignalValue.UNAVAILABLE, SignalValue.UNAVAILABLE),
        )
        self.assertTrue(all("stale" in result.interpretation for result in stale))
    def test_canonical_basis_excludes_same_period_partial_and_zero(self) -> None:
        # FEIM shape: the contract-revenue tag carries a tiny prior value and a
        # zero current value beside the Revenues total for the same periods.
        rows = {
            "Revenues": {"units": {"USD": [
                _row("2023-05-01", "2024-01-31", 400.0, "2024-03-18"),
                _row("2024-05-01", "2025-01-31", 500.0, "2025-01-20"),
            ]}},
            "RevenueFromContractWithCustomerIncludingAssessedTax": {"units": {"USD": [
                _row("2023-05-01", "2024-01-31", 0.089, "2024-03-18"),
                _row("2024-05-01", "2025-01-31", 0.0, "2025-01-20"),
            ]}},
        }
        spec = _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.2, 0.0)
        content = json.dumps({"cik": 1, "facts": {"us-gaap": rows}}, sort_keys=True, separators=(",", ":"))
        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("feim", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(result.interpretation, "revenue_growth_yoy=0.25")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.coverage, SignalCoverage.SUFFICIENT)
        for evidence in result.supporting_evidence:
            self.assertNotIn('"val":0.089', evidence.exact_span)
            self.assertNotIn('"val":0', evidence.exact_span)

    def test_canonical_basis_uses_total_for_cash_flow_margin(self) -> None:
        # Hertz shape: a nonzero partial slice must not become the denominator.
        rows = {
            "Revenues": {"units": {"USD": [
                _row("2024-04-01", "2024-09-30", 3206.598, "2024-11-06"),
            ]}},
            "RevenueFromContractWithCustomerIncludingAssessedTax": {"units": {"USD": [
                _row("2024-04-01", "2024-09-30", 19.081, "2024-11-06"),
            ]}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
                _row("2024-04-01", "2024-09-30", 984.278, "2024-11-06"),
            ]}},
        }
        spec = _spec("operating_cash_flow_margin", "financial.operating_cash_flow_margin", 0.1, 0.0)
        content = json.dumps({"cik": 1, "facts": {"us-gaap": rows}}, sort_keys=True, separators=(",", ":"))
        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("hertz", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(result.interpretation, "operating_cash_flow_margin=0.306954")
        cited = " ".join(e.exact_span for e in result.supporting_evidence)
        self.assertNotIn("19.081", cited)

    def test_restatement_crossover_keeps_the_ongoing_basis(self) -> None:
        # AMD shape: the legacy tag is larger during the crossover quarter, but
        # the contract tag is the issuer's continuing basis for later periods.
        rows = {
            "SalesRevenueNet": {"units": {"USD": [
                _row("2023-11-01", "2024-01-31", 1222.0, "2024-03-18"),
            ]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                _row("2023-11-01", "2024-01-31", 1151.0, "2025-01-20"),
                _row("2024-11-01", "2025-01-31", 1240.0, "2025-01-20"),
            ]}},
        }
        spec = _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.05, 0.0)
        content = json.dumps({"cik": 1, "facts": {"us-gaap": rows}}, sort_keys=True, separators=(",", ":"))
        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("amd", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(result.interpretation, "revenue_growth_yoy=0.0773241")
        cited = " ".join(e.exact_span for e in result.supporting_evidence)
        self.assertNotIn("1222", cited)

    def test_partial_tag_is_excluded_even_for_uncovered_periods(self) -> None:
        rows = {
            "Revenues": {"units": {"USD": [
                _row("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                _row("2024-01-01", "2024-12-31", 125.0, "2025-01-20"),
            ]}},
            "RevenueFromContractWithCustomerIncludingAssessedTax": {"units": {"USD": [
                _row("2022-01-01", "2022-12-31", 0.5, "2023-02-01"),
                _row("2023-01-01", "2023-12-31", 0.4, "2024-02-01"),
            ]}},
        }
        specs = (
            _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.2, 0.0),
            _spec("revenue_acceleration", "financial.revenue_acceleration", 0.05, -0.05),
        )
        content = json.dumps({"cik": 1, "facts": {"us-gaap": rows}}, sort_keys=True, separators=(",", ":"))
        results = SignalExecutor(
            _snapshot(specs), RawInfoStore(documents=(_document("partial", content),))
        ).execute_batch(
            tuple(spec.ref for spec in specs), company_id="issuer_1", as_of=AS_OF
        ).results
        self.assertEqual(results[0].value, SignalValue.POSITIVE)
        self.assertEqual(results[0].interpretation, "revenue_growth_yoy=0.25")
        self.assertEqual(results[1].value, SignalValue.UNAVAILABLE)
        self.assertIn("Two comparable", results[1].interpretation)

    def test_implausible_values_are_downgraded_not_deleted(self) -> None:
        rows = {
            "Revenues": {"units": {"USD": [
                _row("2023-11-01", "2024-01-31", 10.0, "2024-03-18"),
                _row("2024-11-01", "2025-01-31", 61.0, "2025-01-20"),
            ]}},
        }
        content = json.dumps({"cik": 1, "facts": {"us-gaap": rows}}, sort_keys=True, separators=(",", ":"))
        spec = _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.2, 0.0)
        gated = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("gate", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        self.assertEqual(gated.value, SignalValue.POSITIVE)
        self.assertEqual(gated.confidence, 0.5)
        self.assertEqual(gated.coverage, SignalCoverage.PARTIAL)
        self.assertEqual(gated.interpretation, "revenue_growth_yoy=5.1; implausible_value")

        from dataclasses import replace
        override = replace(
            spec, parameters={**spec.parameters, "plausible_abs_max": 6}
        )
        cleared = SignalExecutor(
            _snapshot((override,)), RawInfoStore(documents=(_document("gate2", content),))
        ).execute_batch((override.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        self.assertEqual(cleared.confidence, 1.0)
        self.assertEqual(cleared.coverage, SignalCoverage.SUFFICIENT)
        self.assertEqual(cleared.interpretation, "revenue_growth_yoy=5.1")

    def test_zero_cash_instant_cannot_displace_nonzero_balance(self) -> None:
        rows = {
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                _row(None, "2024-12-31", 0.0, "2025-01-20"),
            ]}},
            "CashAndCashEquivalents": {"units": {"USD": [
                _row(None, "2024-12-31", 40.0, "2025-01-20"),
            ]}},
        }
        spec = _spec("cash_reserves", "financial.cash_reserves", 30.0, 10.0)
        content = json.dumps({"cik": 1, "facts": {"us-gaap": rows}}, sort_keys=True, separators=(",", ":"))
        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("cash", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(result.interpretation, "cash_reserves=40")

    def test_scoped_sec_api_drives_six_financial_signals_and_excludes_future(self) -> None:
        content = _scoped_company_facts_content()
        document = _document("sec_scoped", content)
        specs = (
            _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.4, 0.0),
            _spec("revenue_acceleration", "financial.revenue_acceleration", 0.2, -0.1),
            _spec("gross_margin_change", "financial.gross_margin_change", 0.05, -0.05),
            _spec(
                "operating_cash_flow_margin",
                "financial.operating_cash_flow_margin",
                0.1,
                0.0,
            ),
            _spec(
                "net_share_retirement_yoy",
                "financial.net_share_retirement_yoy",
                0.02,
                -0.05,
            ),
            _spec("cash_reserves", "financial.cash_reserves", 30.0, 10.0),
        )
        executor = SignalExecutor(_snapshot(specs), RawInfoStore(documents=(document,)))

        batch = executor.execute_batch(
            tuple(spec.ref for spec in specs),
            company_id="issuer_1",
            as_of=AS_OF,
        )

        self.assertEqual([item.value for item in batch.results], [SignalValue.POSITIVE] * 6)
        self.assertNotIn("999", " ".join(item.interpretation for item in batch.results))
        for result in batch.results:
            self.assertTrue(result.supporting_evidence)
            for evidence in result.supporting_evidence:
                self.assertIn(evidence.exact_span, content)
                self.assertNotIn('"val":999', evidence.exact_span)

    def test_structured_liquidity_migrations_use_exact_sec_facts(self) -> None:
        rows = {
            "CashAndCashEquivalentsAtCarryingValue": {
                "units": {"USD": [_row(None, "2024-12-31", 40.0, "2025-01-20")]}
            },
            "LiabilitiesCurrent": {
                "units": {"USD": [_row(None, "2024-12-31", 20.0, "2025-01-20")]}
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "units": {
                    "USD": [
                        _row("2024-01-01", "2024-12-31", -30.0, "2025-01-20")
                    ]
                }
            },
        }
        content = json.dumps(
            {"cik": 1, "facts": {"us-gaap": rows}},
            sort_keys=True,
            separators=(",", ":"),
        )
        specs = (
            _spec(
                "cash_to_current_liabilities_ratio",
                "financial.cash_to_current_liabilities_ratio",
                1.0,
                1.0,
            ),
            SignalSpec(
                signal_id="cash_burn_rate_elevated",
                version=2,
                category="financial",
                description="Measure the structured cash burn rate.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                source_types=("financials",),
                modality=SignalModality.STRUCTURED,
                function="financial.cash_burn_rate_elevated",
                parameters={"burn_threshold": 0.1},
            ),
            SignalSpec(
                signal_id="liquidity_runway_months",
                version=2,
                category="financial",
                description="Measure structured liquidity runway months.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                source_types=("financials",),
                modality=SignalModality.STRUCTURED,
                function="financial.liquidity_runway_months",
                parameters={
                    "positive_runway_max_months": 6,
                    "negative_runway_min_months": 12,
                },
            ),
        )
        results = SignalExecutor(
            _snapshot(specs), RawInfoStore(documents=(_document("liquidity", content),))
        ).execute_batch(
            tuple(spec.ref for spec in specs),
            company_id="issuer_1",
            as_of=AS_OF,
        ).results

        self.assertEqual(
            [result.value for result in results],
            [SignalValue.POSITIVE, SignalValue.POSITIVE, SignalValue.NEGATIVE],
        )
        self.assertEqual(
            [result.interpretation for result in results],
            [
                "cash_to_current_liabilities_ratio=2",
                "cash_burn_rate_elevated=0.75",
                "liquidity_runway_months=16",
            ],
        )
        for result in results:
            self.assertEqual(result.confidence, 1.0)
            self.assertTrue(result.supporting_evidence)
            self.assertTrue(
                all(item.exact_span in content for item in result.supporting_evidence)
            )

        rows["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"][0][
            "val"
        ] = 30.0
        positive_cash_flow_content = json.dumps(
            {"cik": 1, "facts": {"us-gaap": rows}},
            sort_keys=True,
            separators=(",", ":"),
        )
        runway = specs[2]
        no_burn = SignalExecutor(
            _snapshot((runway,)),
            RawInfoStore(
                documents=(
                    _document("positive-cash-flow", positive_cash_flow_content),
                )
            ),
        ).execute_batch(
            (runway.ref,), company_id="issuer_1", as_of=AS_OF
        ).results[0]
        self.assertEqual(no_burn.value, SignalValue.NEGATIVE)
        self.assertIn("unbounded_nonnegative", no_burn.interpretation)

    def test_accession_scoped_schema_is_supported_with_literal_fact_evidence(self) -> None:
        facts = [
            _accession_fact("Revenues", "2023-01-01", "2023-12-31", 100.0),
            _accession_fact("Revenues", "2024-01-01", "2024-12-31", 130.0),
        ]
        content = json.dumps(
            {
                "schema_version": "sec-company-facts-document-v1",
                "cik": "1",
                "accession_number": "fixture",
                "filing_date": "2025-01-20",
                "form": "10-K",
                "facts": facts,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        spec = _spec("revenue_growth_yoy", "financial.revenue_growth_yoy", 0.2, 0.0)
        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("sec_accession", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(len(result.supporting_evidence), 2)
        self.assertTrue(
            all(item.exact_span in content for item in result.supporting_evidence)
        )

    def test_share_retirement_prefers_split_comparable_same_filing_facts(self) -> None:
        shares = [
            _row("2023-01-01", "2023-12-31", 50.0, "2024-02-01"),
            _row("2023-01-01", "2023-12-31", 120.0, "2025-01-20"),
            _row("2024-01-01", "2024-12-31", 110.0, "2025-01-20"),
        ]
        content = json.dumps(
            {
                "cik": 1,
                "facts": {
                    "us-gaap": {
                        "WeightedAverageNumberOfSharesOutstandingBasic": {
                            "units": {"shares": shares}
                        }
                    }
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        spec = _spec(
            "net_share_retirement_yoy",
            "financial.net_share_retirement_yoy",
            0.02,
            -0.05,
        )

        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("shares", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertIn("0.0833333", result.interpretation)
        cited = " ".join(item.exact_span for item in result.supporting_evidence)
        self.assertIn('"filed":"2025-01-20"', cited)
        self.assertNotIn('"val":50.0', cited)

    def test_share_dilution_is_negative(self) -> None:
        content = json.dumps(
            {
                "cik": 1,
                "facts": {
                    "us-gaap": {
                        "WeightedAverageNumberOfSharesOutstandingBasic": {
                            "units": {
                                "shares": [
                                    _row(
                                        "2023-01-01",
                                        "2023-12-31",
                                        100.0,
                                        "2025-01-20",
                                    ),
                                    _row(
                                        "2024-01-01",
                                        "2024-12-31",
                                        110.0,
                                        "2025-01-20",
                                    ),
                                ]
                            }
                        }
                    }
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        spec = _spec(
            "net_share_retirement_yoy",
            "financial.net_share_retirement_yoy",
            0.02,
            -0.05,
        )

        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("dilution", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(result.value, SignalValue.NEGATIVE)
        self.assertEqual(result.interpretation, "net_share_retirement_yoy=-0.1")

    def test_cash_flow_margin_requires_the_same_reported_duration(self) -> None:
        facts = [
            _accession_fact("Revenues", "2024-10-01", "2024-12-31", 100.0),
            _accession_fact(
                "NetCashProvidedByUsedInOperatingActivities",
                "2024-01-01",
                "2024-12-31",
                50.0,
            ),
        ]
        content = json.dumps(
            {
                "schema_version": "sec-company-facts-document-v1",
                "cik": "1",
                "accession_number": "fixture",
                "filing_date": "2025-01-20",
                "form": "10-K",
                "facts": facts,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        spec = _spec(
            "operating_cash_flow_margin",
            "financial.operating_cash_flow_margin",
            0.1,
            0.0,
        )

        result = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(_document("cash_flow", content),))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertIn("Matching SEC", result.interpretation)

    def test_price_momentum_uses_exact_observation_lookback_and_fails_closed(self) -> None:
        spec = SignalSpec(
            signal_id="price_momentum_126d",
            version=1,
            category="market",
            description="Fixture price momentum.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            function="market.price_momentum_126d",
            source_types=("market_data",),
            parameters={
                "lookback_observations": 126,
                "positive_min": 0.2,
                "negative_max": -0.2,
            },
        )
        enough = _document(
            "market_enough",
            "Point-in-time chronological adjusted prices.",
            "market_data",
            metadata={"prices": list(range(100, 227))},
        )
        short = _document(
            "market_short",
            "Short point-in-time chronological adjusted prices.",
            "market_data",
            metadata={"prices": list(range(100, 226))},
        )

        positive = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(enough,))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
        unavailable = SignalExecutor(
            _snapshot((spec,)), RawInfoStore(documents=(short,))
        ).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

        self.assertEqual(positive.value, SignalValue.POSITIVE)
        self.assertEqual(positive.interpretation, "price_momentum_126d=1.26")
        self.assertEqual(unavailable.value, SignalValue.UNAVAILABLE)
        self.assertIn("requires 127 observations", unavailable.interpretation)

    def test_unchanged_document_fingerprint_skips_repeat_then_oracle_growth_reexecutes(self) -> None:
        spec = SignalSpec(
            signal_id="negative_word_count",
            version=1,
            category="news",
            description="Count negative terms.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            function="news.negative_word_count",
            source_types=("news",),
            parameters={"negative_count_min": 1, "terms": ["risk"]},
        )
        store = RawInfoStore(documents=(_document("news_1", "risk increased", "news"),))
        executor = SignalExecutor(_snapshot((spec,)), store)
        first = executor.execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF)
        second = executor.execute_batch(
            (spec.ref,),
            company_id="issuer_1",
            as_of=AS_OF,
            prior_fingerprints=first.document_fingerprints,
        )
        self.assertEqual(second.signal_calls, 0)
        self.assertEqual(second.skipped_unchanged_refs, (spec.ref,))

        store.append(_document("news_2", "another risk", "news"))
        third = executor.execute_batch(
            (spec.ref,),
            company_id="issuer_1",
            as_of=AS_OF,
            prior_fingerprints=first.document_fingerprints,
        )
        self.assertEqual(third.signal_calls, 1)
        self.assertFalse(third.skipped_unchanged_refs)


def _spec(
    signal_id: str,
    function: str,
    positive_min: float,
    negative_max: float,
) -> SignalSpec:
    return SignalSpec(
        signal_id=signal_id,
        version=1,
        category="financial",
        description=f"Fixture {signal_id}.",
        execution_type=SignalExecutionType.DETERMINISTIC,
        modality=SignalModality.STRUCTURED,
        function=function,
        source_types=("sec_company_facts",),
        parameters={"positive_min": positive_min, "negative_max": negative_max},
    )


def _snapshot(specs: tuple[SignalSpec, ...]) -> FrozenSignalRegistry:
    payload = json.dumps([spec.to_dict() for spec in specs], sort_keys=True)
    return FrozenSignalRegistry(
        version=1,
        registry_hash=hashlib.sha256(payload.encode()).hexdigest(),
        specs=specs,
        skills={},
    )


def _document(
    document_id: str,
    content: str,
    source_type: str = "sec_company_facts",
    *,
    metadata: dict[str, object] | None = None,
) -> RawInfoDocument:
    return RawInfoDocument.create(
        document_id=document_id,
        company_id="issuer_1",
        source_type=source_type,
        published_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
        available_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
        content=content,
        metadata=metadata,
    )


def _row(start: str | None, end: str, value: float, filed: str) -> dict[str, object]:
    value_dict: dict[str, object] = {
        "end": end,
        "filed": filed,
        "form": "10-K",
        "val": value,
    }
    if start is not None:
        value_dict["start"] = start
    return value_dict


def _scoped_company_facts_content() -> str:
    revenue = [
        _row("2022-01-01", "2022-12-31", 80.0, "2023-02-01"),
        _row("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
        _row("2024-01-01", "2024-12-31", 150.0, "2025-01-20"),
        _row("2025-01-01", "2025-12-31", 999.0, "2026-01-20"),
    ]
    gross = [
        _row("2023-01-01", "2023-12-31", 50.0, "2024-02-01"),
        _row("2024-01-01", "2024-12-31", 90.0, "2025-01-20"),
    ]
    cash = [
        _row(None, "2023-12-31", 20.0, "2024-02-01"),
        _row(None, "2024-12-31", 40.0, "2025-01-20"),
    ]
    operating_cash_flow = [
        _row("2024-01-01", "2024-12-31", 30.0, "2025-01-20"),
        _row("2025-01-01", "2025-12-31", 999.0, "2026-01-20"),
    ]
    shares = [
        _row("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
        _row("2024-01-01", "2024-12-31", 90.0, "2025-01-20"),
        _row("2025-01-01", "2025-12-31", 1.0, "2026-01-20"),
    ]
    return json.dumps(
        {
            "cik": 1,
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": revenue}},
                    "GrossProfit": {"units": {"USD": gross}},
                    "CashAndCashEquivalentsAtCarryingValue": {
                        "units": {"USD": cash}
                    },
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "units": {"USD": operating_cash_flow}
                    },
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {"shares": shares}
                    },
                }
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _accession_fact(
    tag: str, start: str, end: str, value: float
) -> dict[str, object]:
    return {
        "taxonomy": "us-gaap",
        "tag": tag,
        "unit": "USD",
        "start": start,
        "end": end,
        "value": value,
    }
