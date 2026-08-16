from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.llm.agent import AgentRequest, AgentUsage
from stock_opportunity_agent.llm import RegisteredModel
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import DataAcquisitionPolicy
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research import evolution_runtime as evolution_runtime_module
from stock_opportunity_agent.research.evolution_runtime import (
    EvolutionRunContract,
    ExactResponseCache,
    ExternalAttemptLedger,
    ExternalBudgetExhausted,
    ExternalExecutionNotReady,
    ExternalRequestPending,
    LLMBlindPredictor,
    LLMInformationPlanProposer,
    LLMResearchController,
    LLMSignalRetrievalAgent,
    StructuredLLMSignalRunner,
    StructuredAgentModel,
    StructuredOutputInvalid,
    StructuredRoleClient,
    approve_dataset_proposal,
    filter_case_price_history,
    inventory_local_evolution_inputs,
    load_approved_development_dataset,
    migrate_legacy_raw_info,
    prepare_dataset_proposal,
    prepare_expanded_dataset_proposal,
)
from stock_opportunity_agent.research.scheme_evolution import (
    BlindPrediction,
    ConfidenceLevel,
    EvaluationDatasetInfeasible,
    EvaluationDatasetManager,
    GroundTruth,
    PlanEvaluationConfig,
    default_information_plan,
)
from stock_opportunity_agent.signal_library import (
    SignalCoverage,
    SignalExecutionType,
    SignalRegistry,
    SignalSpec,
    SignalValue,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _label_bars(
    multiple: float,
    *,
    volume: int = 100_000,
    complete_horizon: bool = True,
) -> list[dict[str, object]]:
    bars = [
        {
            "as_of_date": f"2024-12-{day:02d}",
            "adjusted_close": 10.0,
            "volume": volume,
        }
        for day in range(10, 30)
    ]
    future_multiples = [
        min(multiple, 3.0),
        min(multiple, 9.0),
        multiple,
        multiple,
        multiple,
        multiple,
        multiple,
    ]
    bars.extend(
        {
            "as_of_date": f"2025-01-{day:02d}",
            "adjusted_close": 10.0 * future_multiple,
            "volume": volume,
        }
        for day, future_multiple in zip(range(10, 17), future_multiples)
    )
    if complete_horizon:
        bars.append(
            {
                "as_of_date": "2025-07-10",
                "adjusted_close": 10.0 * multiple,
                "volume": volume,
            }
        )
    return bars


def write_anchor_spec(
    path: Path, positive_cases: list[tuple[str, str]]
) -> None:
    payload = {
        "schema_version": "information-plan-anchor-spec-v1",
        "anchor_id": "fixture-anchor-v1",
        "review_basis": "fixture",
        "positive_cases": [
            {
                "symbol": symbol,
                "prediction_date": "2025-01-10",
                "expected_label": label,
                "match_control": index < 7,
                "rationale": "fixture",
            }
            for index, (symbol, label) in enumerate(positive_cases)
        ],
    }
    payload["spec_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(path, payload)


def make_contract() -> EvolutionRunContract:
    return EvolutionRunContract(
        run_id="fixture-run",
        created_at="2026-08-09T00:00:00+00:00",
        dataset_manifest_hash=SHA_A,
        raw_info_oracle_id="raw-info-fixture",
        raw_info_inventory_hash=SHA_B,
        initial_signal_registry_version=1,
        initial_signal_registry_hash=SHA_C,
        priors_hash=SHA_D,
        models={
            "judge": {
                "alias": "fixture-judge",
                "provider": "fixture",
                "model": "fixture-judge-model",
            },
            "proposer": {
                "alias": "fixture-proposer",
                "provider": "fixture",
                "model": "fixture-proposer-model",
            },
        },
        code_revision="deadbeef",
        python_runtime="3.12.0",
        limits={
            "plan_rounds_per_signal_cycle": 1,
            "candidates_per_round": 1,
            "top_k": 3,
            "random_k": 2,
            "similarity_threshold": 0.9,
            "parent_selection_seed": 42,
            "plan_proposal_temperature": 1.0,
            "judge_temperature": 0.0,
            "max_signal_rounds": 5,
            "max_signal_calls": 20,
            "max_llm_calls": 40,
            "max_tokens": 120_000,
            "max_case_cost": 5.0,
            "max_agent_steps": 20,
            "evaluation": PlanEvaluationConfig().to_dict(),
        },
        max_external_attempts=2,
        max_total_cost=1.0,
    )


class LocalInventoryTests(TestCase):
    def test_expansion_split_keeps_two_validation_issuers_when_capacity_allows(self) -> None:
        candidates = [
            {
                "company_id": f"issuer_{index}",
                "selection_stratum": "surge_10x_plus",
            }
            for index in range(5)
        ]

        splits = evolution_runtime_module._propose_expanded_issuer_splits(
            candidates,
            seed="rare-class-rotation",
        )

        self.assertEqual(len(splits["discovery"]), 2)
        self.assertEqual(len(splits["evolution_validation"]), 2)
        self.assertEqual(len(splits["locked_test"]), 1)

    def test_expansion_keeps_later_eligible_case_when_earlier_date_precedes_ipo(self) -> None:
        listing = {
            "symbol": "LATE",
            "name": "Later Listing Corp",
            "cik": "123456",
            "exchange": "NASDAQ",
            "ipo_date": "2025-02-01",
        }
        bars = [
            {
                "as_of_date": f"2025-02-{day:02d}",
                "adjusted_close": 10.0,
                "volume": 200_000,
            }
            for day in range(10, 29)
        ]
        bars.extend(
            {
                "as_of_date": f"2025-03-{day:02d}",
                "adjusted_close": 12.0,
                "volume": 200_000,
            }
            for day in range(10, 15)
        )
        bars.append(
            {
                "as_of_date": "2025-09-10",
                "adjusted_close": 12.0,
                "volume": 200_000,
            }
        )

        candidate, exclusions = evolution_runtime_module._expansion_candidate(
            listing,
            bars,
            prediction_dates=(date(2025, 1, 10), date(2025, 3, 10)),
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(
            [case["prediction_time"][:10] for case in candidate["cases"]],
            ["2025-03-10"],
        )
        self.assertEqual(
            [item["reason"] for item in exclusions],
            ["prediction_before_listing_ipo_date"],
        )

    def test_legacy_53_case_dataset_fails_v5_anchor_preflight_without_calls(self) -> None:
        manifest = (
            PROJECT_ROOT
            / "runs"
            / "cold_start"
            / "evolution"
            / "deepseek-v4-flash-overnight-v3"
            / "dataset_proposal"
            / "dataset_manifest.approved.json"
        )
        with self.assertRaisesRegex(ValidationError, "missing anchor split"):
            load_approved_development_dataset(manifest)

    def test_inventory_hashes_current_local_shapes_without_reusing_legacy_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / "cases.json"
            documents = root / "documents.json"
            prices = root / "prices.json"
            write_json(
                cases,
                {
                    "cases": [
                        {
                            "outcome_definition_id": "legacy-terminal-return",
                            "packet": {
                                "as_of": {"as_of_date": "2025-01-01"},
                                "company": {"ticker": {"symbol": "AAA"}},
                            },
                        },
                        {
                            "outcome_definition_id": "legacy-terminal-return",
                            "packet": {
                                "as_of": {"as_of_date": "2025-02-01"},
                                "company": {"ticker": {"symbol": "BBB"}},
                            },
                        },
                    ]
                },
            )
            write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "AAA": [
                            {
                                "available_date": "2024-12-31",
                                "text": "public evidence",
                            }
                        ]
                    }
                },
            )
            write_json(
                prices,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2024-12-01",
                    "end_date": "2025-08-01",
                    "requested_symbol_count": 2,
                    "bars_by_symbol": {
                        "AAA": [{"as_of_date": "2025-01-02", "adjusted_close": 10}],
                    },
                    "failed_symbols": {"BBB": "missing"},
                },
            )
            inventory = inventory_local_evolution_inputs(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
            )
            self.assertEqual(inventory.compatible_case_count, 1)
            self.assertFalse(inventory.migration_ready)
            self.assertEqual(len(inventory.inventory_hash), 64)
            self.assertIn("terminal-return", inventory.incompatible_label_reason)
            self.assertFalse(inventory.to_dict()["locked_test_accessed"])

    def test_raw_info_migration_excludes_labels_and_future_prices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / "cases.json"
            documents = root / "documents.json"
            prices = root / "prices.json"
            raw_info = root / "raw_info"
            write_json(
                cases,
                {
                    "cases": [
                        {
                            "case_id": "AAA:2025-01-10:winner",
                            "label": "winner",
                            "outcome_return": 8.0,
                            "packet": {
                                "as_of": {"as_of_date": "2025-01-10"},
                                "company": {"ticker": {"symbol": "AAA"}},
                            },
                        }
                    ]
                },
            )
            write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "AAA": [
                            {
                                "document_id": "sec:aaa:1",
                                "source_id": "sec:aaa:1",
                                "source_url": "https://example.test/filing",
                                "kind": "filing",
                                "published_date": "2025-01-05",
                                "available_date": "2025-01-05",
                                "title": "Filed report",
                                "text": "Revenue was reported before prediction time.",
                            }
                        ]
                    }
                },
            )
            write_json(
                prices,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2025-01-01",
                    "end_date": "2025-07-10",
                    "requested_symbol_count": 1,
                    "bars_by_symbol": {
                        "AAA": [
                            {"as_of_date": "2025-01-09", "adjusted_close": 10},
                            {"as_of_date": "2025-01-10", "adjusted_close": 20},
                            {"as_of_date": "2025-02-01", "adjusted_close": 80},
                        ]
                    },
                    "failed_symbols": {},
                },
            )
            filtered = filter_case_price_history(
                cases_path=cases,
                full_price_archive_path=prices,
                output_path=root / "filtered_prices.json",
            )
            self.assertEqual(filtered.facts["priced_symbol_count"], 1)
            report = migrate_legacy_raw_info(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
                raw_info_root=raw_info,
            )
            self.assertEqual(report.migrated_source_documents, 1)
            self.assertEqual(report.migrated_market_snapshots, 1)
            replay = migrate_legacy_raw_info(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
                raw_info_root=raw_info,
            )
            self.assertEqual(replay.migrated_source_documents, 1)
            self.assertEqual(replay.appended_source_documents, 0)
            store = RawInfoStore(raw_info)
            serialized = json.dumps([item.to_dict() for item in store.documents])
            self.assertNotIn("winner", serialized)
            self.assertNotIn("outcome_return", serialized)
            market = next(
                item for item in store.documents if item.source_type == "market_data"
            )
            self.assertEqual(market.metadata["prices"], [10.0])

    def test_dataset_proposal_recomputes_two_x_label_and_needs_exact_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases_path = root / "cases.json"
            documents_path = root / "documents.json"
            prices_path = root / "prices.json"
            symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
            cases = []
            bars_by_symbol = {}
            for index, symbol in enumerate(symbols):
                cases.append(
                    {
                        "case_id": f"{symbol}:legacy",
                        "label": "legacy-value-must-not-be-reused",
                        "packet": {
                            "as_of": {"as_of_date": "2025-01-10"},
                            "company": {
                                "ticker": {
                                    "symbol": symbol,
                                    "company_name": f"{symbol} Corp",
                                },
                                "industry": "fixture",
                            },
                        },
                    }
                )
                future_price = 25.0 if index < 3 else 12.0
                bars_by_symbol[symbol] = [
                    *[
                        {
                            "as_of_date": f"2025-01-0{day}",
                            "adjusted_close": 10.0,
                        }
                        for day in range(5, 10)
                    ],
                    *[
                        {
                            "as_of_date": f"2025-01-{day:02d}",
                            "adjusted_close": future_price,
                        }
                        for day in range(10, 15)
                    ],
                    {"as_of_date": "2025-07-10", "adjusted_close": future_price},
                ]
            write_json(cases_path, {"cases": cases})
            write_json(
                documents_path,
                {"documents_by_symbol": {symbol: [] for symbol in symbols}},
            )
            write_json(
                prices_path,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2025-01-05",
                    "end_date": "2025-07-10",
                    "requested_symbol_count": 6,
                    "bars_by_symbol": bars_by_symbol,
                    "failed_symbols": {},
                },
            )
            report = prepare_dataset_proposal(
                cases_path=cases_path,
                documents_path=documents_path,
                adjusted_prices_path=prices_path,
                output_root=root / "proposal",
            )
            self.assertEqual(report.eligible_case_count, 6)
            self.assertEqual(report.split_surge_counts, {
                "discovery": 1,
                "evolution_validation": 1,
                "locked_test": 1,
            })
            with self.assertRaisesRegex(ValidationError, "hash"):
                approve_dataset_proposal(
                    proposal_manifest_path=report.manifest_path,
                    expected_proposal_hash="0" * 64,
                    approved_by="reviewer",
                )
            with self.assertRaisesRegex(
                ValidationError,
                "expanded proposal with Anchor",
            ):
                approve_dataset_proposal(
                    proposal_manifest_path=report.manifest_path,
                    expected_proposal_hash=report.manifest_hash,
                    approved_by="reviewer",
                )

    def test_full_market_expansion_is_fixed_date_deduplicated_and_proposal_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            universe_path = root / "universe.json"
            prices_path = root / "prices.json"
            anchors_path = root / "anchors.json"
            multiples = (1.2, 1.7, 2.5, 4.0, 12.0)
            issuer_counts = (10, 10, 9, 7, 4)
            listings = []
            bars_by_symbol = {}
            for stratum_index, multiple in enumerate(multiples):
                for issuer_index in range(issuer_counts[stratum_index]):
                    symbol = f"S{stratum_index}{issuer_index}"
                    cik = str(1000 + stratum_index * 10 + issuer_index)
                    listings.append(
                        {
                            "symbol": symbol,
                            "name": f"{symbol} Corp",
                            "cik": cik,
                            "exchange": "NASDAQ" if issuer_index % 2 else "NYSE",
                            "ipo_date": f"20{10 + issuer_index}-01-01",
                            "asset_type": "Stock",
                            "status": "Active",
                            "source": "fixture",
                            "retrieved_at": "2026-01-01T00:00:00+00:00",
                            "delisting_date": None,
                        }
                    )
                    bars_by_symbol[symbol] = _label_bars(
                        multiple,
                        volume=100_000 * (issuer_index + 1),
                    )
            listings.append(
                {
                    "symbol": "DUP",
                    "name": "Duplicate Share Class",
                    "cik": "1000",
                    "exchange": "NYSE",
                    "ipo_date": "2010-01-01",
                    "asset_type": "Stock",
                    "status": "Active",
                    "source": "fixture",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "delisting_date": None,
                }
            )
            bars_by_symbol["DUP"] = _label_bars(1.2, volume=10_000_000)
            listings.append(
                {
                    "symbol": "SHRT",
                    "name": "Short History Corp",
                    "cik": "9999",
                    "exchange": "NASDAQ",
                    "ipo_date": "2024-01-01",
                    "asset_type": "Stock",
                    "status": "Active",
                    "source": "fixture",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "delisting_date": None,
                }
            )
            bars_by_symbol["SHRT"] = _label_bars(1.2, complete_horizon=False)
            listings.append(
                {
                    "symbol": "PIPO",
                    "name": "Future Listing Corp",
                    "cik": "9998",
                    "exchange": "NASDAQ",
                    "ipo_date": "2025-02-01",
                    "asset_type": "Stock",
                    "status": "Active",
                    "source": "fixture",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "delisting_date": None,
                }
            )
            bars_by_symbol["PIPO"] = _label_bars(1.2)
            abnormal_listings = [
                ("SPACX", "Example Acquisition V Corp", "9100"),
                ("ROMX", "Example Holdings X Inc - Class A", "9104"),
                ("NOCIK", "No CIK Operating Corp", None),
                ("ILLA", "Illiquid Operating Corp", "9102"),
                ("SPLT", "Split Artifact Corp", "9103"),
            ]
            for symbol, name, cik in abnormal_listings:
                listings.append(
                    {
                        "symbol": symbol,
                        "name": name,
                        "cik": cik,
                        "exchange": "NASDAQ",
                        "ipo_date": "2010-01-01",
                        "asset_type": "Stock",
                        "status": "Active",
                        "source": "fixture",
                        "retrieved_at": "2026-01-01T00:00:00+00:00",
                        "delisting_date": None,
                    }
                )
            bars_by_symbol["SPACX"] = _label_bars(1.2)
            bars_by_symbol["NOCIK"] = _label_bars(1.2)
            bars_by_symbol["ILLA"] = _label_bars(1.2, volume=10_000)
            bars_by_symbol["SPLT"] = _label_bars(1.2)
            bars_by_symbol["SPLT"][20]["adjusted_close"] = 50.0
            write_json(universe_path, {"listing_count": len(listings), "listings": listings})
            write_json(
                prices_path,
                {
                    "schema_version": "fixture-prices-v1",
                    "bars_by_symbol": bars_by_symbol,
                    "warning_count": 0,
                },
            )
            write_anchor_spec(
                anchors_path,
                [
                    *((f"S2{index}", "2_3x") for index in range(5)),
                    *((f"S3{index}", "3_10x") for index in range(3)),
                    ("S40", "10x_plus"),
                ],
            )

            report = prepare_expanded_dataset_proposal(
                universe_path=universe_path,
                full_price_archive_path=prices_path,
                output_root=root / "proposal",
                prediction_dates=[date(2025, 1, 10)],
                split_seed="fixture-expansion",
                anchor_cases_path=anchors_path,
            )

            self.assertEqual(report.universe_listing_count, 48)
            self.assertEqual(report.priced_symbol_count, 45)
            self.assertEqual(report.eligible_issuer_count, 40)
            self.assertEqual(report.selection_mode, "all_eligible")
            self.assertEqual(report.selected_issuer_count, 40)
            self.assertEqual(report.case_count, 40)
            self.assertEqual(
                report.selected_stratum_counts,
                report.available_stratum_counts,
            )
            self.assertEqual(report.split_issuer_counts["anchor"], 16)
            self.assertEqual(report.split_surge_counts["anchor"], 9)
            self.assertEqual(report.exclusion_reason_counts["duplicate_issuer_identity"], 1)
            self.assertEqual(report.exclusion_reason_counts["incomplete_six_month_price_horizon"], 1)
            self.assertEqual(report.exclusion_reason_counts["prediction_before_listing_ipo_date"], 1)
            self.assertEqual(
                report.exclusion_reason_counts["non_operating_or_spac_issuer"], 2
            )
            self.assertEqual(report.exclusion_reason_counts["missing_reviewed_cik"], 1)
            self.assertEqual(
                report.exclusion_reason_counts[
                    "below_minimum_pre_prediction_dollar_volume"
                ],
                1,
            )
            self.assertEqual(
                report.exclusion_reason_counts[
                    "extreme_adjusted_price_discontinuity"
                ],
                1,
            )
            self.assertFalse(report.to_dict()["locked_test_accessed"])
            self.assertEqual(report.to_dict()["external_calls"], 0)

            manifest = json.loads(Path(report.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["case_generation"]["eligibility"],
                "each_case_independently_passes_point_in_time_normality_gate",
            )
            self.assertEqual(
                manifest["case_generation"]["issuer_retention"],
                "at_least_one_eligible_case",
            )
            self.assertEqual(manifest["selection"]["mode"], "all_eligible")
            self.assertIsNone(manifest["selection"]["requested_issuer_cap"])
            self.assertIsNone(manifest["selection"]["weights"])
            self.assertTrue(manifest["approval_blockers"])
            acquisition_path = Path(
                manifest["audit_artifacts"]["acquisition_scope"]["path"]
            )
            acquisition_text = acquisition_path.read_text(encoding="utf-8")
            acquisition = json.loads(acquisition_text)
            self.assertEqual(acquisition["company_count"], 40)
            self.assertFalse(acquisition["outcome_fields_included"])
            self.assertFalse(acquisition["split_ownership_included"])
            self.assertNotIn("ground_truth", acquisition_text)
            self.assertNotIn("selection_stratum", acquisition_text)
            self.assertNotIn("locked_test", acquisition_text)
            issuer_sets = []
            for split_name in ("discovery", "evolution_validation", "locked_test"):
                split = json.loads(
                    Path(manifest["artifacts"][split_name]["path"]).read_text(encoding="utf-8")
                )
                issuer_sets.append({row["company_id"] for row in split["cases"]})
            self.assertFalse(issuer_sets[0] & issuer_sets[1])
            self.assertFalse(issuer_sets[0] & issuer_sets[2])
            self.assertFalse(issuer_sets[1] & issuer_sets[2])

            approved = approve_dataset_proposal(
                proposal_manifest_path=report.manifest_path,
                expected_proposal_hash=report.manifest_hash,
                approved_by="reviewer",
            )
            development = load_approved_development_dataset(approved)
            self.assertEqual(len(development.anchor), 16)
            self.assertEqual(len(development.evolution_validation), 9)

            replay = prepare_expanded_dataset_proposal(
                universe_path=universe_path,
                full_price_archive_path=prices_path,
                output_root=root / "proposal",
                prediction_dates=[date(2025, 1, 10)],
                split_seed="fixture-expansion",
                anchor_cases_path=anchors_path,
            )
            self.assertEqual(replay.to_dict(), report.to_dict())

            decisions_path = root / "identity_decisions.json"
            decisions = {
                "schema_version": "expanded-case-identity-decisions-v1",
                "review_status": "agent_proposed_pending_human_review",
                "decision_count": 2,
                "decisions": [
                    {
                        "decision_id": "fixture-set-cik",
                        "symbol": "S00",
                        "action": "set_cik",
                        "cik": "8000",
                        "applies_from": "2025-01-10",
                        "applies_to": "2025-01-10",
                        "rationale": "official filing identifies the issuer",
                        "evidence": [
                            {
                                "source_url": (
                                    "https://www.sec.gov/Archives/edgar/data/8000/fixture.htm"
                                ),
                                "filing_date": "2025-01-01",
                                "observed_fact": "The filing identifies S00 under CIK 8000.",
                            }
                        ],
                    },
                    {
                        "decision_id": "fixture-exclude-preipo",
                        "symbol": "PIPO",
                        "action": "exclude",
                        "applies_from": "2025-01-10",
                        "applies_to": "2025-01-10",
                        "rationale": "the symbol is not valid at the prediction date",
                        "evidence": [
                            {
                                "source_url": (
                                    "https://www.sec.gov/Archives/edgar/data/9998/fixture.htm"
                                ),
                                "filing_date": "2025-01-01",
                                "observed_fact": "The filing proves a different valid period.",
                            }
                        ],
                    },
                ],
            }
            decisions["decision_hash"] = hashlib.sha256(
                json.dumps(
                    decisions, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            write_json(decisions_path, decisions)
            identity_report = prepare_expanded_dataset_proposal(
                universe_path=universe_path,
                full_price_archive_path=prices_path,
                output_root=root / "proposal-identity",
                prediction_dates=[date(2025, 1, 10)],
                target_issuers=15,
                stratum_weights={key: 1.0 for key in report.selected_stratum_counts},
                split_seed="fixture-expansion",
                identity_decisions_path=decisions_path,
                anchor_cases_path=anchors_path,
            )
            self.assertEqual(identity_report.universe_listing_count, 48)
            self.assertEqual(identity_report.eligible_issuer_count, 41)
            self.assertEqual(identity_report.selection_mode, "stratified_cap")
            self.assertEqual(identity_report.selected_issuer_count, 31)
            self.assertEqual(
                identity_report.exclusion_reason_counts["identity_decision_exclude"],
                1,
            )
            identity_manifest = json.loads(
                Path(identity_report.manifest_path).read_text(encoding="utf-8")
            )
            self.assertEqual(identity_manifest["identity_decisions"]["decision_count"], 2)
            self.assertEqual(identity_manifest["identity_decisions"]["cik_update_count"], 1)
            self.assertEqual(identity_manifest["identity_decisions"]["exclusion_count"], 1)
            self.assertEqual(
                identity_manifest["counts"]["identity_eligible_universe_listings"],
                47,
            )
            self.assertIn(
                "human-review the exact applied identity-decision artifact",
                identity_manifest["approval_blockers"],
            )
            inventory = json.loads(
                Path(
                    identity_manifest["audit_artifacts"]["candidate_inventory"]["path"]
                ).read_text(encoding="utf-8")
            )
            inventory_company_ids = {
                row["company_id"] for row in inventory["candidates"]
            } | {row["company_id"] for row in inventory["anchor_cases"]}
            self.assertIn("cik_0000008000", inventory_company_ids)
            identity_replay = prepare_expanded_dataset_proposal(
                universe_path=universe_path,
                full_price_archive_path=prices_path,
                output_root=root / "proposal-identity",
                prediction_dates=[date(2025, 1, 10)],
                target_issuers=15,
                stratum_weights={key: 1.0 for key in report.selected_stratum_counts},
                split_seed="fixture-expansion",
                identity_decisions_path=decisions_path,
                anchor_cases_path=anchors_path,
            )
            self.assertEqual(identity_replay.to_dict(), identity_report.to_dict())

            invalid_evidence = json.loads(json.dumps(decisions))
            invalid_evidence["decisions"][0]["evidence"][0]["source_url"] = (
                "https://example.com/not-sec.htm"
            )
            invalid_evidence.pop("decision_hash")
            invalid_evidence["decision_hash"] = hashlib.sha256(
                json.dumps(
                    invalid_evidence, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            write_json(decisions_path, invalid_evidence)
            with self.assertRaisesRegex(ValidationError, "official SEC"):
                prepare_expanded_dataset_proposal(
                    universe_path=universe_path,
                    full_price_archive_path=prices_path,
                    output_root=root / "invalid-evidence-proposal",
                    prediction_dates=[date(2025, 1, 10)],
                    target_issuers=15,
                    identity_decisions_path=decisions_path,
                    anchor_cases_path=anchors_path,
                )

            future_evidence = json.loads(json.dumps(decisions))
            future_evidence["decisions"][0]["evidence"][0]["filing_date"] = (
                "2025-01-11"
            )
            future_evidence.pop("decision_hash")
            future_evidence["decision_hash"] = hashlib.sha256(
                json.dumps(
                    future_evidence, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            write_json(decisions_path, future_evidence)
            with self.assertRaisesRegex(ValidationError, "postdates"):
                prepare_expanded_dataset_proposal(
                    universe_path=universe_path,
                    full_price_archive_path=prices_path,
                    output_root=root / "future-evidence-proposal",
                    prediction_dates=[date(2025, 1, 10)],
                    target_issuers=15,
                    identity_decisions_path=decisions_path,
                    anchor_cases_path=anchors_path,
                )

            tampered = dict(decisions)
            tampered["review_status"] = "human_reviewed"
            write_json(decisions_path, tampered)
            with self.assertRaisesRegex(ValidationError, "hash mismatch"):
                prepare_expanded_dataset_proposal(
                    universe_path=universe_path,
                    full_price_archive_path=prices_path,
                    output_root=root / "tampered-proposal",
                    prediction_dates=[date(2025, 1, 10)],
                    target_issuers=15,
                    identity_decisions_path=decisions_path,
                    anchor_cases_path=anchors_path,
                )


class ScriptedRoleCaller:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = list(outputs)
        self.stages: list[str] = []
        self.calls: list[dict[str, object]] = []

    def complete_json(self, **kwargs):
        self.stages.append(str(kwargs["stage"]))
        self.calls.append(dict(kwargs))
        return self.outputs.pop(0), AgentUsage(llm_calls=1, tokens=5, cost=0.01)


class ConcreteRoleAdapterTests(TestCase):
    def test_plan_proposer_repairs_malformed_provider_json_once(self) -> None:
        class MalformedThenValidCaller:
            def __init__(self) -> None:
                self.stages: list[str] = []

            def complete_json(self, **kwargs):
                self.stages.append(str(kwargs["stage"]))
                if len(self.stages) == 1:
                    raise StructuredOutputInvalid(
                        "provider returned two JSON objects",
                        '{"B":{}}\n{"extra":true}',
                        AgentUsage(llm_calls=1, tokens=20, cost=0.01),
                    )
                return (
                    {
                        "B": {
                            "requests": [
                                {
                                    "request_id": "recent_news",
                                    "description": "Read recent company news.",
                                    "source_types": ["news"],
                                    "lookback_days": 180,
                                    "max_documents": 5,
                                }
                            ]
                        },
                        "H_init": "Form an initial source-backed hypothesis.",
                        "H_reflect": "Reflect over all returned Signal evidence.",
                        "H_analyse": "Make the final two-stage blind forecast.",
                    },
                    AgentUsage(llm_calls=1, tokens=20, cost=0.01),
                )

        caller = MalformedThenValidCaller()
        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=3,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed prior",
        )

        self.assertEqual(plan.plan_id, "plan_r0001_c01")
        self.assertEqual(
            caller.stages,
            ["information_plan_propose", "information_plan_propose_correction"],
        )

    def test_slow_agent_role_states_exact_final_output_contract(self) -> None:
        caller = ScriptedRoleCaller(
            [{"action": "final", "output": {"candidate_refs": []}}]
        )
        model = StructuredAgentModel(
            caller,
            stage="signal_mining_agent",
            allow_outcomes=True,
            final_output_example={"candidate_refs": ["candidate_signal:v1"]},
        )

        turn = model.respond(
            AgentRequest(
                prompt="Mine one candidate.",
                tool_cards=(),
                workspace={},
                observations=(),
            )
        )

        self.assertEqual(turn.final_output, {"candidate_refs": []})
        system_prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn('"candidate_refs": ["candidate_signal:v1"]', system_prompt)
        self.assertIn("successful staging tool call", system_prompt)

    def test_controller_and_progressive_signal_selector_use_structured_roles(self) -> None:
        controller_caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": ["commercialization may accelerate"],
                    "current_beliefs": [],
                    "supporting_evidence": [],
                    "contradictions": [],
                    "resolved_questions": [],
                    "open_questions": [],
                    "next_information_needs": ["revenue growth"],
                    "decision": "continue",
                }
            ]
        )
        state = LLMResearchController(controller_caller).initialize(
            default_information_plan(), {"industry": "fixture"}
        )
        self.assertEqual(state.value.next_information_needs, ("revenue growth",))
        self.assertEqual(controller_caller.stages, ["research_controller_initialize"])
        self.assertIn(
            '"next_information_needs"',
            str(controller_caller.calls[0]["system_prompt"]),
        )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            selector_caller = ScriptedRoleCaller(
                [
                    {"categories": ["financial"]},
                    {"signal_refs": ["revenue_growth_yoy:v1"]},
                ]
            )
            selection = LLMSignalRetrievalAgent(selector_caller).select(
                ("revenue growth",), registry.freeze(), {}
            )
            self.assertEqual(selection.value, ("revenue_growth_yoy:v1",))
            self.assertEqual(
                selector_caller.stages,
                ["signal_retrieval_categories", "signal_retrieval_cards"],
            )

    def test_signal_selector_repairs_invalid_categories_and_refs_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    {"categories": ["unknown"]},
                    {"categories": ["financial"]},
                    {"signal_refs": ["unknown:v1"]},
                    {"signal_refs": ["revenue_growth_yoy:v1"]},
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",), registry.freeze(), {}
            )

            self.assertEqual(selection.value, ("revenue_growth_yoy:v1",))
            self.assertEqual(selection.usage.llm_calls, 4)
            self.assertIn("validation_feedback", caller.calls[1]["payload"])
            self.assertIn("validation_feedback", caller.calls[3]["payload"])

    def test_signal_selector_repairs_non_array_containers_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    {"categories": "financial"},
                    {"categories": ["financial"]},
                    {"signal_refs": "revenue_growth_yoy:v1"},
                    {"signal_refs": ["revenue_growth_yoy:v1"]},
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",), registry.freeze(), {}
            )

            self.assertEqual(selection.value, ("revenue_growth_yoy:v1",))
            self.assertEqual(selection.usage.llm_calls, 4)

    def test_signal_selector_returns_empty_after_failed_category_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [{"categories": []}, {"categories": ["unknown"]}]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                ("unmatched need",), registry.freeze(), {}
            )

            self.assertEqual(selection.value, ())
            self.assertEqual(selection.usage.llm_calls, 2)
            self.assertEqual(
                caller.stages,
                ["signal_retrieval_categories", "signal_retrieval_categories"],
            )

    def test_blind_predictor_parses_two_stage_schema(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "is_surge": True,
                    "magnitude": "2-3x",
                    "confidence": {"level": "medium"},
                    "key_reasons": ["source-backed evidence"],
                    "uncertainties": [],
                    "session_id": "fixture-session",
                }
            ]
        )
        prediction = LLMBlindPredictor(caller).predict(
            {"basic_info": {"industry": "fixture"}}
        )
        self.assertTrue(prediction.value.is_surge)
        self.assertEqual(prediction.value.magnitude.value, "2-3x")
        prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn('"session_id"', prompt)
        self.assertIn("adjusted share price", prompt)
        self.assertIn("last five complete trading days", prompt)
        self.assertIn("not a requirement that revenue", prompt)
        self.assertIn("forecast under uncertainty, not a proof task", prompt)
        self.assertIn("concrete, credible path", prompt)
        self.assertIn("Do not require a guarantee", prompt)
        self.assertIn("outcome-stratified", prompt)
        self.assertIn("do not predict false merely because 2x moves are rare", prompt)

    def test_blind_predictor_repairs_string_boolean_instead_of_using_truthiness(self) -> None:
        valid = {
            "is_surge": False,
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": ["limited source-backed evidence"],
            "uncertainties": [],
            "session_id": "fixture-session",
        }
        caller = ScriptedRoleCaller([{**valid, "is_surge": "false"}, valid])

        prediction = LLMBlindPredictor(caller).predict(
            {"basic_info": {"industry": "fixture"}}
        )

        self.assertFalse(prediction.value.is_surge)
        self.assertEqual(
            caller.stages,
            ["blind_predictor_predict", "blind_predictor_predict_correction"],
        )
        self.assertIn("validation_error", caller.calls[1]["payload"])

    def test_posthoc_reflection_does_not_rescan_low_confidence_as_ticker(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "prediction_outcome": {"correct": False},
                    "why_prediction_failed": [],
                    "misleading_signals": [],
                    "ignored_evidence": [],
                    "missing_information": [],
                    "plan_issues": [],
                }
            ]
        )
        predictor = LLMBlindPredictor(caller, anonymous_aliases=("LOW",))

        predictor.reflect(
            {"summary": "anonymous evidence"},
            BlindPrediction(
                is_surge=False,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("limited evidence",),
                uncertainties=(),
                session_id="anonymous-session",
            ),
            GroundTruth(1.2),
        )

        self.assertEqual(caller.calls[0]["anonymous_aliases"], ())

    def test_posthoc_reflection_still_scans_original_context(self) -> None:
        predictor = LLMBlindPredictor(
            ScriptedRoleCaller([]), anonymous_aliases=("LEAKME",)
        )

        with self.assertRaisesRegex(ValidationError, "identity alias leaked"):
            predictor.reflect(
                {"summary": "LEAKME disclosed"},
                BlindPrediction(
                    is_surge=False,
                    magnitude=None,
                    confidence=ConfidenceLevel.LOW,
                    key_reasons=("limited evidence",),
                    uncertainties=(),
                    session_id="anonymous-session",
                ),
                GroundTruth(1.2),
            )

    def test_plan_proposer_normalizes_observed_deepseek_shape_and_slots_children(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "plan_id": "plan_manual_v2",
                    "parent_ids": ["invented_parent"],
                    "B": {
                        "company_name": "placeholder",
                        "ticker": "PLACEHOLDER",
                    },
                    "H_init": {
                        "basic_info_policy": {
                            "fields": ["company_name", "ticker", "industry"]
                        },
                        "initial_research_skill": "Form a falsifiable hypothesis.",
                    },
                    "H_reflect": {
                        "reflection_skill": "Track support and contradiction."
                    },
                    "H_analyse": {
                        "analysis_prompt": "Weigh supporting and counter evidence."
                    },
                    "fixed_prior": "echoed input",
                    "meta_info": [],
                },
                {
                    "plan_id": "plan_manual_v2_slot_2",
                    "parent_ids": ["another_invented_parent"],
                    "basic_info_policy": {
                        "fields": ["company_name", "ticker", "industry"]
                    },
                    "initial_research_skill": "Test a distinct hypothesis.",
                    "reflection_skill": "Track disconfirming evidence first.",
                    "analysis_prompt": "Weigh both sides.",
                },
            ]
        )
        proposer = LLMInformationPlanProposer(caller)
        parent = default_information_plan()

        first = proposer.propose(
            round_id=1,
            candidate_index=1,
            candidate_count=2,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )
        second = proposer.propose(
            round_id=1,
            candidate_index=2,
            candidate_count=2,
            proposal_attempt=1,
            forbidden_plan_ids=(first.plan_id,),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(first.plan_id, "plan_r0001_c01")
        self.assertEqual(
            first.basic_info_policy.requests[-1].request_id,
            "legacy_industry",
        )
        self.assertEqual(first.parent_ids, ("plan_manual_v1",))
        self.assertEqual(caller.calls[0]["temperature"], 1.0)
        self.assertIn(
            '"B"', str(caller.calls[0]["system_prompt"])
        )
        self.assertEqual(
            caller.calls[0]["payload"]["proposal_slot"],
            {
                "round_id": 1,
                "candidate_index": 1,
                "candidate_count": 2,
                "proposal_attempt": 1,
            },
        )
        self.assertEqual(
            caller.calls[1]["payload"]["proposal_slot"],
            {
                "round_id": 1,
                "candidate_index": 2,
                "candidate_count": 2,
                "proposal_attempt": 1,
            },
        )
        self.assertIn(
            '"B"', str(caller.calls[1]["system_prompt"])
        )
        self.assertNotIn("forbidden_plan_ids", str(caller.calls[1]["system_prompt"]))
        self.assertEqual(second.plan_id, "plan_r0001_c02")

    def test_plan_proposer_reports_invalid_shape_as_validation_error(self) -> None:
        proposer = LLMInformationPlanProposer(
            ScriptedRoleCaller([{"unexpected": True}, {"unexpected": True}])
        )

        with self.assertRaisesRegex(
            ValidationError, "information_plan_propose returned"
        ):
            proposer.propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(),
                prior="fixed H_P",
            )

    def test_plan_proposer_rejects_deepseek_evidence_arrays_cleanly(self) -> None:
        proposer = LLMInformationPlanProposer(
            ScriptedRoleCaller(
                [
                    {
                        "B": {"purpose": "not a Basic Info policy"},
                        "H_init": [{"statement": "one"}],
                        "H_reflect": [{"statement": "two"}],
                        "H_analyse": [{"statement": "three"}],
                    },
                    {
                        "B": {"purpose": "still invalid"},
                        "H_init": [{"statement": "one"}],
                        "H_reflect": [{"statement": "two"}],
                        "H_analyse": [{"statement": "three"}],
                    },
                ]
            )
        )

        with self.assertRaisesRegex(
            ValidationError,
            "information_plan_propose returned incompatible semantic fields",
        ):
            proposer.propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(),
                prior="fixed H_P",
            )

    def test_llm_signal_runner_conservatively_normalizes_unavailable_coverage(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "signal_id": "pilot_to_volume",
                    "version": 1,
                    "state": {"value": "unavailable", "confidence": 0.5},
                    "interpretation": {"summary": "No usable source evidence."},
                    "evidence": {"supporting": [], "counter": []},
                    "status": {"coverage": "partial"},
                }
            ]
        )
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )

        result, _usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (),
            "Extract only source-grounded transitions.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(result.coverage, SignalCoverage.UNAVAILABLE)

    def test_llm_signal_runner_repairs_invalid_exact_span_once(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="The customer entered volume deployment.",
        )
        base_result = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "The pilot reached volume deployment."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-1",
                        "exact_span": "not a literal source span",
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        corrected = json.loads(json.dumps(base_result))
        corrected["evidence"]["supporting"][0]["exact_span"] = (
            "The customer entered volume deployment."
        )
        caller = ScriptedRoleCaller([base_result, corrected])
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Extract only source-grounded transitions.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(len(caller.calls), 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("exact span", feedback["validation_error"])
        self.assertEqual(usage.llm_calls, 2)
        self.assertAlmostEqual(usage.cost, 0.02)

    def test_llm_signal_runner_falls_back_unavailable_after_failed_repair(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="The customer entered volume deployment.",
        )
        invalid_result = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "Unsupported interpretation."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-1",
                        "exact_span": "not a literal source span",
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        caller = ScriptedRoleCaller([invalid_result, invalid_result])
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Extract only source-grounded transitions.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(result.coverage, SignalCoverage.UNAVAILABLE)
        self.assertEqual(result.supporting_evidence, ())
        self.assertIn("failed strict validation", result.interpretation)
        self.assertEqual(usage.llm_calls, 2)


class RunControlTests(TestCase):
    def test_malformed_paid_json_is_audited_costed_and_not_cached(self) -> None:
        class MalformedClient:
            def complete(self, _messages, **_kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                return ChatResponse(
                    response_id="response-malformed",
                    model="fixture-model",
                    output_text='{"ok":true}\n{"extra":false}',
                    raw={"usage": {"input_tokens": 3, "output_tokens": 2}},
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: MalformedClient(),
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            with self.assertRaisesRegex(StructuredOutputInvalid, "invalid structured"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                )

            attempt = json.loads((root / "attempts.json").read_text())["attempts"][0]
            self.assertEqual(attempt["status"], "failed")
            self.assertGreater(attempt["actual_cost"], 0)
            failure_paths = tuple((root / "failed_responses").glob("*.json"))
            self.assertEqual(len(failure_paths), 1)
            failure = json.loads(failure_paths[0].read_text())
            self.assertIn('{"extra":false}', failure["raw_output"])
            self.assertEqual(tuple((root / "cache" / "responses").glob("*.json")), ())

    def test_v3_contract_rejects_missing_behavioral_defaults(self) -> None:
        contract = make_contract()
        incomplete_limits = dict(contract.limits)
        incomplete_limits.pop("parent_selection_seed")
        with self.assertRaisesRegex(ValidationError, "parent_selection_seed"):
            EvolutionRunContract(
                **{**contract.__dict__, "limits": incomplete_limits}
            )
        with self.assertRaisesRegex(ValidationError, "code revision"):
            EvolutionRunContract(
                **{**contract.__dict__, "code_revision": ""}
            )

    def test_contract_separates_data_acquisition_from_llm_external_scope(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("sec_edgar", "alpha_vantage"),
                    allowed_capabilities=("filings", "news"),
                    allowed_source_types=("10-k", "news"),
                    max_requests_per_cycle=10,
                    max_requests_per_run=50,
                ),
            }
        )
        value = contract.to_dict()
        self.assertTrue(value["data_acquisition"]["enabled"])
        self.assertNotIn("allow_external", value["data_acquisition"])
        self.assertIn("initial_signal_registry_hash", value)
        self.assertNotIn("signal_registry_hash", value)
        restored = EvolutionRunContract.from_dict(value)
        self.assertEqual(restored.data_acquisition, contract.data_acquisition)

        legacy_v3 = {
            **value,
            "schema_version": "evolution-run-contract-v3",
            "signal_registry_version": value["initial_signal_registry_version"],
            "signal_registry_hash": value["initial_signal_registry_hash"],
        }
        legacy_v3.pop("initial_signal_registry_version")
        legacy_v3.pop("initial_signal_registry_hash")
        self.assertFalse(EvolutionRunContract.from_dict(legacy_v3).executable)

        legacy = {**value, "schema_version": "evolution-run-contract-v1"}
        legacy.pop("data_acquisition")
        restored_legacy = EvolutionRunContract.from_dict(legacy)
        self.assertFalse(restored_legacy.data_acquisition.enabled)
        self.assertNotIn("data_acquisition", restored_legacy.to_dict())
        self.assertFalse(restored_legacy.executable)
        self.assertTrue(contract.executable)

    def test_runtime_orders_available_price_adapters_by_catalog_priority(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("massive", "stooq", "alpha_vantage"),
                    allowed_capabilities=("price_daily",),
                    allowed_source_types=("market_data",),
                    max_requests_per_cycle=10,
                    max_requests_per_run=50,
                ),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            resolver = evolution_runtime_module._build_evidence_resolver(
                Path(directory),
                RawInfoStore(),
                contract=contract,
                allow_data_external=True,
                environ={
                    "MASSIVE_API_KEY": "massive-test-key",
                    "STOOQ_API_KEY": "stooq-test-key",
                    "ALPHA_VANTAGE_API_KEY": "alpha-test-key",
                },
                cycle_id=1,
            )

        price_providers = [
            adapter.provider
            for adapter in resolver.adapters
            if "market_data" in adapter.source_types
        ]
        self.assertEqual(
            price_providers,
            ["massive", "stooq", "alpha_vantage"],
        )

    def test_frozen_data_policy_stays_disabled_without_invocation_authorization(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("massive",),
                    allowed_capabilities=("price_daily",),
                    allowed_source_types=("market_data",),
                    max_requests_per_cycle=10,
                    max_requests_per_run=50,
                ),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            resolver = evolution_runtime_module._build_evidence_resolver(
                Path(directory),
                RawInfoStore(),
                contract=contract,
                allow_data_external=False,
                environ={"MASSIVE_API_KEY": "massive-test-key"},
                cycle_id=1,
            )

        self.assertFalse(resolver.policy.enabled)
        self.assertEqual(resolver.policy.allowed_providers, ())
        self.assertEqual(resolver.budget.run_requests, 0)

    def test_contract_freeze_is_exact_and_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run_contract.json"
            contract = make_contract()
            contract.freeze(path)
            contract.freeze(path)
            serialized = path.read_text(encoding="utf-8")
            self.assertNotIn("api-key", serialized)
            conflicting = EvolutionRunContract(
                **{**contract.__dict__, "run_id": "other-run"}
            )
            with self.assertRaisesRegex(ValidationError, "conflicting immutable"):
                conflicting.freeze(path)

    def test_attempt_ledger_reserves_before_calls_and_counts_stale_in_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = ExternalAttemptLedger(
                Path(directory) / "attempts.json",
                max_attempts=2,
                max_total_cost=0.5,
            )
            first = ledger.reserve(SHA_A, reserved_cost=0.2)
            self.assertEqual(ledger.summary["in_progress"], 1)
            ledger.finalize(first, status="failed", actual_cost=0.0, error_type="Fixture")
            ledger.reserve(SHA_B, reserved_cost=0.2)
            with self.assertRaisesRegex(ExternalBudgetExhausted, "attempt ceiling"):
                ledger.reserve(SHA_C, reserved_cost=0.01)

    def test_structured_client_preflight_scans_and_never_calls_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: (_ for _ in ()).throw(
                    AssertionError("network client must not be built during preflight")
                ),
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=False,
                environ={},
            )
            with self.assertRaisesRegex(ValidationError, "outcome field"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"ground_truth": 4.0},
                    allow_outcomes=False,
                )
            with self.assertRaisesRegex(ValidationError, "identity alias"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "AAA has evidence"},
                    allow_outcomes=False,
                    anonymous_aliases=("AAA",),
                )
            with self.assertRaisesRegex(ExternalRequestPending, "requires approval"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "or an artifact with low liquidity"},
                    allow_outcomes=False,
                    anonymous_aliases=("AN", "LOW"),
                )
            with self.assertRaisesRegex(ValidationError, "identity alias"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "AN identity disclosed"},
                    allow_outcomes=False,
                    anonymous_aliases=("AN",),
                )
            try:
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                    temperature=1.0,
                )
            except ExternalRequestPending as pending:
                self.assertTrue(pending.request_path.is_file())
                request_hash = pending.request_hash
                request_path = pending.request_path
            else:
                self.fail("preview should stop after persisting the exact request")
            self.assertEqual(ledger.summary["attempt_count"], 0)
            request = json.loads(request_path.read_text(encoding="utf-8"))[
                "request"
            ]
            self.assertEqual(request["temperature"], 1.0)
            self.assertEqual(request["response_format"], {"type": "json_object"})
            self.assertIn("JSON", request["messages"][0]["content"])

            ExactResponseCache(root / "cache" / "responses").store(
                request_hash,
                {
                    "json_output": {"ok": True},
                    "usage": {"input_tokens": 3, "output_tokens": 2, "cost": 0.1},
                },
            )
            value, usage = client.complete_json(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
                temperature=1.0,
            )
            self.assertEqual(value, {"ok": True})
            self.assertEqual(usage.llm_calls, 0)

    def test_missing_api_key_is_control_plane_pause_without_attempt_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: (_ for _ in ()).throw(
                    AssertionError("client must not be built without readiness")
                ),
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={},
            )

            with self.assertRaisesRegex(
                ExternalExecutionNotReady, "API key is unavailable"
            ):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                )

            self.assertEqual(ledger.summary["attempt_count"], 0)

    def test_structured_client_enforces_json_response_format_on_provider_call(self) -> None:
        class RecordingClient:
            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def complete(self, _messages, **kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                self.kwargs = dict(kwargs)
                return ChatResponse(
                    response_id="response-1",
                    model="fixture-model",
                    output_text='{"ok":true}',
                    raw={"usage": {"input_tokens": 3, "output_tokens": 2}},
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording_client = RecordingClient()
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: recording_client,
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            value, usage = client.complete_json(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
            )

            self.assertEqual(value, {"ok": True})
            self.assertEqual(usage.llm_calls, 1)
            self.assertEqual(
                recording_client.kwargs["response_format"],
                {"type": "json_object"},
            )
