from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
from unittest import TestCase, mock

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm import RegisteredModel, get_model
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    DataAcquisitionPolicy,
    EvidenceResolver,
    RawInfoRequest,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research import evolution_runtime as evolution_runtime_module
from stock_opportunity_agent.research.evolution_runtime import (
    DecisionTokenScores,
    EvolutionRunContract,
    ExactResponseCache,
    ExternalAttemptLedger,
    ExternalBudgetExhausted,
    ExternalExecutionNotReady,
    ExternalRequestPending,
    HistoricalPlanSeedPool,
    LLMBlindPredictor,
    LLMInformationPlanProposer,
    LLMSignalMiningModel,
    LLMPlanCritic,
    LLMRoundReflector,
    LLMResearchController,
    LLMSignalRetrievalAgent,
    LLMSignalUpdateModel,
    StructuredLLMSignalRunner,
    StructuredOutputInvalid,
    StructuredRoleClient,
    approve_dataset_proposal,
    filter_case_price_history,
    inventory_local_evolution_inputs,
    build_historical_plan_seed_pool,
    load_approved_development_dataset,
    load_or_create_historical_plan_seed_pool,
    migrate_legacy_raw_info,
    prepare_dataset_proposal,
    prepare_expanded_dataset_proposal,
)
from stock_opportunity_agent.research.scheme_evolution import (
    BlindPrediction,
    CaseReflectionEvidence,
    CandidateExecutionRejected,
    CandidateProposalRejected,
    CandidateJudgment,
    ConfidenceLevel,
    EvaluationDatasetInfeasible,
    EvaluationDatasetManager,
    FitnessEligibility,
    GroundTruth,
    InformationPlan,
    MagnitudeClass,
    PlanMetaReflection,
    PlanMetrics,
    PlanEvaluationConfig,
    PlanReflection,
    PredictionSelfReflection,
    ResearchDecision,
    ResearchEvidenceRef,
    ResearchState,
    RoundMetaEntry,
    RuntimeStopReason,
    RuntimeBudgetExceeded,
    SignalSelectionDecision,
    _normalized_projection_text,
    project_basic_info_bundle,
    candidate_judgment_feedback,
    default_information_plan,
)
from stock_opportunity_agent.signal_library import (
    LLMSignalBatchInput,
    SignalBatchResult,
    SignalCoverage,
    SignalEvidence,
    SignalExecutor,
    SignalExecutionType,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def signal_selection(signal_ref: str) -> dict[str, Any]:
    return {
        "selections": [
            {
                "signal_ref": signal_ref,
                "reason_code": "answer_need",
                "selection_reason": "Answer the current information need.",
                "applicability_hypothesis": "The supplied evidence is applicable.",
                "expected_role": "primary",
                "context_tags": ["general"],
                "target_need_indices": [0],
                "answer_scope": "full",
                "residual_need": None,
            }
        ]
    }


def validation_error(call: Mapping[str, Any]) -> str:
    """Read validation feedback from stable-prefix and legacy role requests."""

    payload = call["payload"]
    feedback = payload.get("validation_feedback")
    if isinstance(feedback, Mapping):
        return str(feedback["validation_error"])
    return str(payload["validation_error"])


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
            "max_signals_per_round": 4,
            "max_llm_signals_per_round": 2,
            "max_llm_calls": 40,
            "max_tokens": 120_000,
            "finalization_token_reserve": 36_000,
            "basic_info_context_chars": 32_000,
            "signal_batch_context_chars": 32_000,
            "predictor_context_bytes": 24_000,
            "posthoc_context_chars": 24_000,
            "meta_context_chars": 48_000,
            "role_output_tokens": {
                "controller": 2_000,
                "routing": 2_000,
                "predictor": 2_000,
                "posthoc": 2_000,
                "h1": 2_000,
                "h2": 2_000,
                "proposer": 4_000,
                "critic": 4_000,
                "signal_batch": 4_000,
                "h3": 8_000,
                "update": 8_000,
            },
            "max_case_cost": 5.0,
            "max_agent_steps": 20,
            "evaluation": PlanEvaluationConfig().to_dict(),
        },
        max_external_attempts=2,
        max_total_cost=1.0,
    )


class IdentityBoundaryPerformanceTests(TestCase):
    def test_identity_scan_compiles_aliases_once_per_payload_traversal(self) -> None:
        aliases = tuple(f"Example Holdings {index}" for index in range(80))
        real_compile = re.compile

        def compile_count(value: object) -> int:
            with mock.patch.object(
                evolution_runtime_module.re,
                "compile",
                side_effect=real_compile,
            ) as compile_mock:
                evolution_runtime_module._scan_payload(
                    value,
                    allow_outcomes=True,
                    anonymous_aliases=aliases,
                )
            return compile_mock.call_count

        one_leaf = compile_count({"value": "ordinary reflection"})
        many_leaves = compile_count(
            {f"value_{index}": "ordinary reflection" for index in range(180)}
        )

        self.assertEqual(many_leaves, one_leaf)


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
    def test_signal_h1_rejects_empty_portfolio_with_unmet_signal_demand(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {"hypotheses": []},
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "analyst_estimate_revision_gap",
                            "statement": (
                                "Analyst estimate revisions distinguish the fixed "
                                "Discovery groups."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases show stronger analyst estimate "
                                "revisions than control cases."
                            ),
                            "source_types": ["news"],
                            "query": "analyst estimate revision",
                            "falsifiers": [
                                "Positive and control groups show overlapping or "
                                "reversed estimate revisions."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need": "How have analyst estimate revisions changed?"}
                    ]
                },
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "analyst_estimate_revision_gap")
        self.assertIn(
            "must return at least one grounded hypothesis",
            validation_error(caller.calls[1]),
        )

    def test_signal_h1_corrects_hypothesis_unrelated_to_bootstrap_need(self) -> None:
        ungrounded = {
            "hypotheses": [
                {
                    "hypothesis_id": "large_order_confirmation",
                    "statement": "Material order confirmation precedes repricing.",
                    "applicability": "Project-driven companies.",
                    "expected_positive_pattern": (
                        "Positive cases confirm more orders than control cases."
                    ),
                    "source_types": ["news"],
                    "query": "material order customer award",
                    "falsifiers": ["Controls confirm orders equally often."],
                    "lookback_days": 365,
                }
            ]
        }
        grounded = {
            "hypotheses": [
                {
                    "hypothesis_id": "production_cost_guidance_gap",
                    "statement": (
                        "Production volume and cost-per-ounce guidance gaps may "
                        "precede repricing."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "Positive cases beat production and unit-cost guidance more "
                        "often than control cases."
                    ),
                    "source_types": ["news"],
                    "query": "production volume cost ounce guidance",
                    "falsifiers": [
                        "Positive cases and control cases beat the same guidance "
                        "equally often."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        caller = ScriptedRoleCaller([ungrounded, grounded])
        model = LLMSignalMiningModel(caller)

        result = model.propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
                "capability_backlog": {
                    "signal_need_items": [
                        {
                            "need": (
                                "What are recent production volumes and cost per "
                                "ounce, and how do they compare to guidance?"
                            )
                        }
                    ]
                },
            }
        )

        self.assertEqual(
            caller.stages,
            ["signal_mining_hypotheses", "signal_mining_hypotheses_correction"],
        )
        self.assertIn("at least two", validation_error(caller.calls[1]))
        self.assertEqual(result.value[0].hypothesis_id, "production_cost_guidance_gap")

    def test_signal_h1_corrects_renamed_existing_stable_signal(self) -> None:
        duplicate = {
            "hypotheses": [
                {
                    "hypothesis_id": "revenue_growth_trajectory_shift",
                    "statement": (
                        "Accelerating year-over-year revenue growth precedes repricing."
                    ),
                    "applicability": "Companies with quarterly revenue history.",
                    "expected_positive_pattern": (
                        "Positive cases show stronger revenue acceleration than "
                        "control cases."
                    ),
                    "source_types": ["10-q"],
                    "query": "revenue growth acceleration",
                    "falsifiers": ["Controls accelerate equally often."],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {"hypotheses": []}
        caller = ScriptedRoleCaller([duplicate, corrected])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-q"],
                "registered_deterministic_functions": [
                    "financial.revenue_acceleration"
                ],
                "stable_signal_cards": [
                    {
                        "signal_id": "revenue_acceleration",
                        "signal_ref": "revenue_acceleration:v1",
                    }
                ],
            }
        )

        self.assertEqual(result.value, ())
        self.assertIn("restate", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.stages,
            ["signal_mining_hypotheses", "signal_mining_hypotheses_correction"],
        )

    def test_signal_h1_allows_gap_parenthesis_and_downstream_stable_metric(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "production_volume_cost_gap",
                            "statement": (
                                "A production gap (volume versus guidance) is "
                                "associated with revenue acceleration."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases show larger production beats and "
                                "lower unit costs than control cases."
                            ),
                            "source_types": ["10-q"],
                            "query": "production volume cost ounce guidance",
                            "falsifiers": [
                                "Positive cases and control cases show equal or "
                                "reversed production and cost gaps."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-q"],
                "registered_deterministic_functions": [
                    "financial.revenue_acceleration"
                ],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "production_volume_cost_gap")
        self.assertEqual(caller.stages, ["signal_mining_hypotheses"])

    def test_signal_h1_preserves_yoy_in_stable_signal_identity(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": (
                                "revenue_growth_composition_core_vs_nonoperating"
                            ),
                            "statement": (
                                "Core operating contribution distinguishes the "
                                "composition of recent revenue growth."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases show more core-driven revenue growth "
                                "than control cases."
                            ),
                            "source_types": ["10-q"],
                            "query": (
                                "core vs non-operating revenue growth segment drivers"
                            ),
                            "falsifiers": [
                                "Positive cases and control cases have equal or "
                                "reversed core operating contribution."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-q"],
                "registered_deterministic_functions": [
                    "financial.revenue_growth_yoy"
                ],
            }
        )

        self.assertEqual(
            result.value[0].hypothesis_id,
            "revenue_growth_composition_core_vs_nonoperating",
        )
        self.assertEqual(caller.stages, ["signal_mining_hypotheses"])

    def test_signal_h1_corrects_alternate_outcome_with_stable_feedback(self) -> None:
        invalid = {
            "hypotheses": [
                {
                    "hypothesis_id": "production_guidance_gap",
                    "statement": (
                        "Production above guidance predicts revenue growth in the "
                        "next quarter."
                    ),
                    "applicability": "Commodity producers with guidance.",
                    "expected_positive_pattern": (
                        "Production beats lead to faster growth in the next quarter."
                    ),
                    "source_types": ["10-q"],
                    "query": "production volume cost ounce guidance",
                    "falsifiers": [
                        "The next quarter has the same growth after a miss."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {
            "hypotheses": [
                {
                    **invalid["hypotheses"][0],
                    "statement": (
                        "Prediction-date production and guidance gaps distinguish "
                        "the fixed Discovery groups."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "Positive cases show larger production beats and lower unit "
                        "costs than control cases."
                    ),
                    "falsifiers": [
                        "Positive cases and control cases show equal or reversed "
                        "production beats."
                    ],
                }
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-q"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "production_guidance_gap")
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        error = validation_error(caller.calls[1])
        self.assertIn("alternate horizon", error)
        self.assertIn("both positive and control groups", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        must_change_paths = {
            path
            for obligation in feedback["obligations"]
            for path in obligation["must_change_paths"]
        }
        self.assertIn("hypotheses[0].statement", must_change_paths)
        self.assertIn(
            "hypotheses[0].expected_positive_pattern", must_change_paths
        )
        self.assertIn("hypotheses[0].falsifiers[0]", must_change_paths)
        self.assertNotIn(
            "delete every listed quantity", caller.calls[1]["system_prompt"]
        )
        self.assertIn(
            "preserve every hypothesis whose hypothesis_id is not named",
            caller.calls[1]["system_prompt"],
        )

    def test_signal_h1_combines_identity_and_semantic_feedback_without_echo(
        self,
    ) -> None:
        invalid = {
            "hypotheses": [
                {
                    "hypothesis_id": "estimate_gap",
                    "statement": (
                        "Match Group estimate beats cause a price reaction within "
                        "5 days."
                    ),
                    "applicability": "Companies with analyst coverage.",
                    "expected_positive_pattern": (
                        "Positive group case [CASE_POSITIVE_A] beats estimates."
                    ),
                    "source_types": ["news"],
                    "query": "analyst estimate gap",
                    "falsifiers": ["No short-term price increase."],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {
            "hypotheses": [
                {
                    **invalid["hypotheses"][0],
                    "statement": (
                        "Prediction-date analyst estimate gaps distinguish the "
                        "fixed Discovery groups."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "The positive group shows larger estimate beats than the "
                        "control cases."
                    ),
                    "falsifiers": [
                        "The positive group and control group show equal or reversed "
                        "estimate beats."
                    ],
                }
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("Match Group",))

        result = model.propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "estimate_gap")
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        error = feedback["validation_error"]
        self.assertIn("identity alias leaked", error)
        self.assertIn("alternate horizon", error)
        self.assertIn("must not invent opaque case refs", error)
        self.assertIn("both positive and control groups", error)
        self.assertNotIn("Match Group", json.dumps(feedback))

    def test_signal_h1_rejects_data_readiness_and_raw_absolute_scale(self) -> None:
        invalid = {
            "hypotheses": [
                {
                    "hypothesis_id": "consensus_revenue_surprise",
                    "statement": (
                        "Quarterly revenue and earnings figures are available in "
                        "point-in-time filings."
                    ),
                    "applicability": "Companies with analyst consensus estimates.",
                    "expected_positive_pattern": (
                        "Positive cases (companies with higher absolute revenue) have "
                        "higher absolute revenue and earnings figures than control "
                        "cases."
                    ),
                    "source_types": ["news"],
                    "query": (
                        "Find companies where revenue surprise is more than 5% over "
                        "the last 30 days."
                    ),
                    "falsifiers": [
                        "Control cases have equal case-local consensus surprises."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {
            "hypotheses": [
                {
                    **invalid["hypotheses"][0],
                    "statement": (
                        "Case-local quarterly revenue surprise relative to consensus "
                        "distinguishes the fixed Discovery groups."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "The positive group has more positive revenue surprise versus "
                        "its own consensus baseline than the control cases."
                    ),
                    "query": "revenue earnings consensus surprise",
                    "falsifiers": [
                        "The positive and control groups show equal or reversed "
                        "case-local consensus surprise."
                    ],
                }
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "consensus_revenue_surprise")
        error = validation_error(caller.calls[1])
        self.assertIn("measurable group feature", error)
        self.assertIn("normalize raw absolute scale", error)
        self.assertIn("one canonical rule", error)
        self.assertIn("positive/control group non-separation", error)
        self.assertIn("must not redefine fixed Discovery groups", error)
        self.assertIn("concise 2-8 term retrieval topic", error)
        prompt = caller.calls[0]["system_prompt"]
        self.assertIn("not merely say data are available", prompt)
        self.assertIn("Never compare raw absolute", prompt)
        self.assertIn("applicability must be exactly one non-conjunctive", prompt)
        self.assertIn("Never redefine either fixed group", prompt)
        self.assertIn("concise 2-8 term retrieval topic", prompt)

    def test_signal_h1_requires_one_rule_from_actual_h2_field_inventory(
        self,
    ) -> None:
        base = {
            "hypothesis_id": "estimate_revision_gap",
            "statement": "Estimate revisions distinguish the fixed Discovery groups.",
            "expected_positive_pattern": (
                "Positive cases show stronger revisions than control cases."
            ),
            "source_types": ["news"],
            "query": "analyst estimate revision",
            "falsifiers": [
                "Positive and control groups show overlapping or reversed revisions."
            ],
            "lookback_days": 365,
        }
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            **base,
                            "applicability": (
                                "Issuers on major exchanges with market data coverage."
                            ),
                        }
                    ]
                },
                {
                    "hypotheses": [
                        {**base, "applicability": "exchange_values:NYSE|NASDAQ"}
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
                "h2_applicability_contract": {
                    "observed_values": {
                        "exchange_values": ["NASDAQ", "NYSE"],
                        "industry_values": [],
                    }
                },
            }
        )

        self.assertEqual(result.value[0].applicability, "exchange_values:NYSE|NASDAQ")
        error = validation_error(caller.calls[1])
        self.assertIn("one canonical rule", error)
        self.assertIn("actual H2 profile contract", error)
        self.assertNotIn("market data coverage", caller.calls[1]["system_prompt"])

    def test_signal_h1_rejects_membership_style_group_redefinition(self) -> None:
        base = {
            "hypothesis_id": "consensus_revenue_gap",
            "statement": (
                "Case-local quarterly revenue surprise distinguishes the fixed "
                "Discovery groups."
            ),
            "applicability": "all_ready_issuers",
            "source_types": ["news"],
            "query": "quarterly revenue consensus gap",
            "falsifiers": [
                "The positive and control groups show overlapping or reversed "
                "case-local consensus gaps."
            ],
            "lookback_days": 365,
        }
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            **base,
                            "expected_positive_pattern": (
                                "Positive cases are issuers classified in the "
                                "Discovery positive group as beating consensus; "
                                "control cases are issuers classified in the "
                                "Discovery control group as missing consensus."
                            ),
                        }
                    ]
                },
                {
                    "hypotheses": [
                        {
                            **base,
                            "expected_positive_pattern": (
                                "The fixed Discovery positive group should show a "
                                "more positive case-local consensus gap than the "
                                "fixed Discovery control group."
                            ),
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "consensus_revenue_gap")
        error = validation_error(caller.calls[1])
        self.assertIn("must not redefine fixed Discovery groups", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 1)
        self.assertEqual(
            feedback["obligations"][0]["must_change_paths"],
            ["hypotheses[0].expected_positive_pattern"],
        )
        self.assertIn("membership clause", caller.calls[0]["system_prompt"])

    def test_signal_h1_allows_parenthetical_same_group_alias(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "revenue_composition_gap",
                            "statement": (
                                "Revenue composition distinguishes the fixed "
                                "Discovery groups."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases (the Discovery positive group) show "
                                "more granular revenue composition than control cases "
                                "(the Discovery control group)."
                            ),
                            "source_types": ["10-k"],
                            "query": "revenue growth composition",
                            "falsifiers": [
                                "The positive and control groups show overlapping or "
                                "reversed revenue composition."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-k"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "revenue_composition_gap")
        self.assertEqual(len(caller.calls), 1)

    def test_signal_h1_allows_fixed_discovery_group_alias(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "estimate_revision_gap",
                            "statement": (
                                "Estimate revisions distinguish the fixed Discovery "
                                "groups."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases (fixed Discovery group) show more "
                                "upward revisions than control cases (fixed Discovery "
                                "group)."
                            ),
                            "source_types": ["news"],
                            "query": "analyst estimate revision",
                            "falsifiers": [
                                "The positive and control groups show overlapping or "
                                "reversed estimate revisions."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "estimate_revision_gap")
        self.assertEqual(len(caller.calls), 1)

    def test_signal_h1_rejects_unobserved_canonical_applicability_value(
        self,
    ) -> None:
        base = {
            "hypothesis_id": "production_cost_gap",
            "statement": "Production cost gaps distinguish the fixed Discovery groups.",
            "expected_positive_pattern": (
                "Positive cases show better production cost gaps than control cases."
            ),
            "source_types": ["10-k"],
            "query": "production cost guidance gap",
            "falsifiers": [
                "Positive and control groups show overlapping or reversed gaps."
            ],
            "lookback_days": 365,
        }
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {**base, "applicability": "industry_values:Metals & Mining"}
                    ]
                },
                {
                    "hypotheses": [
                        {
                            **base,
                            "applicability": (
                                "business_description_topics:mining|mineral|extraction"
                            ),
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-k"],
                "h2_applicability_contract": {
                    "observed_values": {"industry_values": []}
                },
            }
        )

        self.assertEqual(
            result.value[0].applicability,
            "business_description_topics:mining|mineral|extraction",
        )
        self.assertIn("unsupported: Metals & Mining", validation_error(caller.calls[1]))

    def test_signal_h2_enforces_bounded_unpadded_shortlist_and_allows_empty(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "mining_operations",
                            "cases": [
                                {
                                    "case_ref": case_ref,
                                    "profile_evidence": "irrelevant",
                                    "applicability_reason": "irrelevant",
                                }
                                for case_ref in ("case-001", "case-002", "case-003")
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "mining_operations",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "mining_operations"}],
                "case_briefs": [
                    {"case_ref": "case-001"},
                    {"case_ref": "case-002"},
                    {"case_ref": "case-003"},
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["mining_operations"], ())
        self.assertIn("exceeds", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.stages,
            [
                "signal_mining_case_ranking",
                "signal_mining_case_ranking_correction",
            ],
        )

    def test_signal_h2_rejects_empty_when_canonical_visible_rule_matches(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {"hypothesis_id": "broad_estimates", "cases": []}
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "broad_estimates",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "aerospace services",
                                    "applicability_reason": (
                                        "The canonical rule covers every ready issuer."
                                    ),
                                }
                            ],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [
                    {
                        "hypothesis_id": "broad_estimates",
                        "applicability": "all_ready_issuers",
                    }
                ],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "aerospace services",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 1},
            }
        )

        self.assertEqual(result.value["broad_estimates"], ("case-001",))
        self.assertIn(
            "cannot return an empty ranking",
            validation_error(caller.calls[1]),
        )

    def test_signal_h2_rejects_case_outside_canonical_visible_rule(self) -> None:
        def ranking(case_ref: str, evidence: str) -> dict[str, object]:
            return {
                "rankings": [
                    {
                        "hypothesis_id": "exchange_screen",
                        "cases": [
                            {
                                "case_ref": case_ref,
                                "profile_evidence": evidence,
                                "applicability_reason": (
                                    "The visible exchange satisfies the canonical rule."
                                ),
                            }
                        ],
                    }
                ]
            }

        caller = ScriptedRoleCaller(
            [ranking("case-002", "NASDAQ"), ranking("case-001", "NYSE")]
        )
        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [
                    {
                        "hypothesis_id": "exchange_screen",
                        "applicability": "exchange_values:NYSE",
                    }
                ],
                "case_briefs": [
                    {"case_ref": "case-001", "exchange": "NYSE"},
                    {"case_ref": "case-002", "exchange": "NASDAQ"},
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["exchange_screen"], ("case-001",))
        self.assertIn(
            "must satisfy the canonical visible applicability rule",
            validation_error(caller.calls[1]),
        )

    def test_signal_h2_requires_literal_profile_evidence_for_each_case(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "production_guidance",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "operates gold mines",
                                    "applicability_reason": (
                                        "A mine operator can report production guidance."
                                    ),
                                }
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "production_guidance",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "production_guidance"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "Provides aviation repair services.",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["production_guidance"], ())
        self.assertIn("exact contiguous span", validation_error(caller.calls[1]))

    def test_signal_h2_rejects_self_disqualifying_reason_with_stable_feedback(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "expanded service offerings",
                                    "applicability_reason": (
                                        "The profile mentions growth, but no analyst "
                                        "estimate data are provided and the evidence is "
                                        "too generic to confirm applicability."
                                    ),
                                }
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "expanded service offerings",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        self.assertIn(
            "cannot disclaim applicability", validation_error(caller.calls[1])
        )
        prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn("1-160 characters", prompt)
        self.assertIn("1-240 characters", prompt)
        self.assertNotIn("project-driven engineering services", prompt)

    def test_signal_h2_aggregates_inference_and_span_errors_without_echo(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "AI platform leadership",
                                    "applicability_reason": (
                                        "AI platform leadership suggests likely analyst "
                                        "coverage."
                                    ),
                                },
                                {
                                    "case_ref": "case-002",
                                    "profile_evidence": "analyst estimates",
                                    "applicability_reason": (
                                        "The profile lacks visible estimates and cannot "
                                        "confirm applicability."
                                    ),
                                },
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                },
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("AI",))

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "AI platform leadership",
                    },
                    {
                        "case_ref": "case-002",
                        "business_description": "expanded service offerings",
                    },
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        error = feedback["validation_error"]
        self.assertIn("must not infer missing profile facts", error)
        self.assertIn("cannot disclaim applicability", error)
        self.assertIn("exact contiguous span", error)
        self.assertNotIn("identity alias leaked", error)

    def test_identity_guard_requires_context_for_two_character_ticker(self) -> None:
        evolution_runtime_module._scan_payload(
            {"summary": "AI platform leadership"},
            allow_outcomes=True,
            anonymous_aliases=("AI",),
        )

        for value in ("ticker AI", "$AI", "NASDAQ: AI"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValidationError, "identity alias leaked"
            ):
                evolution_runtime_module._scan_payload(
                    {"summary": value},
                    allow_outcomes=True,
                    anonymous_aliases=("AI",),
                )

    def test_signal_h2_malformed_text_feedback_does_not_echo_raw_output(self) -> None:
        class MalformedThenValidCaller(ScriptedRoleCaller):
            def complete_json(self, **kwargs):
                self.stages.append(str(kwargs["stage"]))
                self.calls.append(dict(kwargs))
                if len(self.calls) == 1:
                    raise StructuredOutputInvalid(
                        "provider returned invalid structured output: Extra data",
                        '{"rankings":[]} Vornado Realty Trust',
                        AgentUsage(llm_calls=1, tokens=5, cost=0.01),
                    )
                return self.outputs.pop(0), AgentUsage(
                    llm_calls=1, tokens=5, cost=0.01
                )

        caller = MalformedThenValidCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                }
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("Vornado Realty Trust",))

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [{"case_ref": "case-001"}],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        self.assertIn("Extra data", feedback["validation_error"])
        self.assertNotIn("identity alias", feedback["validation_error"])
        self.assertNotIn("Vornado", json.dumps(caller.calls[1]["payload"]))

    def test_signal_h3_repairs_missing_evidence_rejection_to_inconclusive(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "decisions": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "disposition": "rejected",
                            "rationale": [
                                "The packets do not contain analyst estimate data."
                            ],
                            "candidate": None,
                        }
                    ]
                },
                {
                    "decisions": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "disposition": "inconclusive",
                            "rationale": [
                                "The packets do not contain analyst estimate data."
                            ],
                            "candidate": None,
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).contrast(
            {
                "comparisons": [
                    {"hypothesis": {"hypothesis_id": "estimate_gap"}}
                ],
                "rules": {
                    "decisions": [
                        "supported",
                        "refine",
                        "rejected",
                        "inconclusive",
                    ]
                },
            }
        )

        self.assertEqual(result.value[0].disposition, "inconclusive")
        self.assertIn(
            "evidence absence must use inconclusive",
            validation_error(caller.calls[1]),
        )

    def test_signal_h1_preserves_real_structured_context_with_brand_collisions(
        self,
    ) -> None:
        output = {
            "hypotheses": [
                {
                    "hypothesis_id": "estimate_revision_dispersion",
                    "statement": "Estimate revisions may precede repricing.",
                    "applicability": "raw_info_source_type_values:news",
                    "expected_positive_pattern": (
                        "Positive cases show stronger upward revisions than controls."
                    ),
                    "source_types": ["news"],
                    "query": "analyst estimate revision",
                    "falsifiers": [
                        "Positive cases and control cases revise upward equally often."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        caller = ScriptedRoleCaller([output])
        model = LLMSignalMiningModel(caller, creative_temperature=1.0)
        model.set_identity_guard_aliases(
            (
                "OPEN",
                "Match Group",
                "News Corp",
                "Alpha Metallurgical Resources",
            )
        )
        payload = {
            "track": "hypothesis",
            "limits": {"hypothesis_limit": 3},
            "available_raw_source_types": [
                "alpha_vantage_earnings_raw_response",
                "company_facts",
                "market_data",
                "news",
                "price_history",
            ],
            "h2_applicability_contract": {
                "observed_values": {"raw_info_source_type_values": ["news"]}
            },
            "capability_backlog": {
                "status": "open",
                "signal_need_items": [
                    {
                        "status": "open",
                        "stop_reason": "no_signal_match",
                        "need": (
                            "Compare analyst estimate revisions against prior "
                            "expectations."
                        ),
                    }
                ],
            },
            "registered_deterministic_functions": ["news.negative_word_count"],
            "stable_signal_cards": [
                {
                    "signal_id": "negative_word_count",
                    "signal_ref": "negative_word_count:v1",
                    "category": "news",
                    "description": "Count negative terms in company news.",
                }
            ],
        }

        hypotheses = model.propose_hypotheses(payload)

        self.assertEqual(
            caller.calls[0]["payload"], {**payload, "validation_feedback": None}
        )
        self.assertNotIn("MASKED_COMPANY", json.dumps(caller.calls[0]["payload"]))
        self.assertEqual(hypotheses.value[0].source_types, ("news",))

    def test_signal_h1_rejects_identity_output_without_echoing_it(self) -> None:
        leaking = {
            "hypotheses": [
                {
                    "hypothesis_id": "named_issuer",
                    "statement": "Match Group shows a reusable pattern.",
                    "applicability": "Companies with estimate revisions.",
                    "expected_positive_pattern": (
                        "Positive cases show stronger upward revisions than control "
                        "cases."
                    ),
                    "source_types": ["news"],
                    "query": "estimate revision",
                    "falsifiers": ["Controls revise equally often."],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {
            "hypotheses": [
                {
                    **leaking["hypotheses"][0],
                    "statement": "Upward estimate revisions may precede repricing.",
                    "applicability": "all_ready_issuers",
                    "falsifiers": [
                        "Positive cases and control cases revise upward equally often."
                    ],
                }
            ]
        }
        caller = ScriptedRoleCaller([leaking, corrected])
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("Match Group",))

        result = model.propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(
            caller.stages,
            ["signal_mining_hypotheses", "signal_mining_hypotheses_correction"],
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        self.assertIn(
            "identity alias leaked into structured role output",
            feedback["validation_error"],
        )
        self.assertNotIn("Match Group", json.dumps(caller.calls[1]["payload"]))
        self.assertEqual(
            result.value[0].statement,
            "Upward estimate revisions may precede repricing.",
        )

    def test_signal_h2_trusts_case_local_masking_without_global_alias_rescan(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "operating_profile",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "leases commercial properties",
                                    "applicability_reason": (
                                        "The profile identifies an externally managed REIT."
                                    ),
                                },
                                {
                                    "case_ref": "case-002",
                                    "profile_evidence": "drug candidate",
                                    "applicability_reason": (
                                        "The profile identifies a clinical-stage drug developer."
                                    ),
                                },
                            ],
                        }
                    ]
                }
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(
            ("Vornado Realty Trust", "VNO", "LX")
        )

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "operating_profile"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": (
                            "The masked target is managed by Vornado Realty Trust "
                            "(NYSE: VNO) and leases commercial properties."
                        ),
                    },
                    {
                        "case_ref": "case-002",
                        "business_description": (
                            "The masked target develops the LX 9211 drug candidate."
                        ),
                    },
                ],
            }
        )

        self.assertEqual(
            result.value["operating_profile"],
            ("case-001", "case-002"),
        )
        self.assertEqual(caller.calls[0]["anonymous_aliases"], ())

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
                                },
                                {
                                    "request_id": "recent_market_backbone",
                                    "description": "Read recent market data.",
                                    "source_types": ["market_data"],
                                    "lookback_days": 45,
                                    "max_documents": 1,
                                }
                            ]
                        },
                        "H_init": (
                            "Form an initial source-backed hypothesis and list "
                            "unresolved information needs."
                        ),
                        "H_reflect": (
                            "Reflect over all returned Signal evidence, then continue "
                            "for the next need or finalize."
                        ),
                        "H_analyse": (
                            "Organize and weigh supporting and counter evidence while "
                            "preserving uncertainty."
                        ),
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

    def test_plan_proposer_corrects_missing_market_backbone(self) -> None:
        missing = {
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
            "H_init": (
                "Form an initial source-backed hypothesis and list unresolved "
                "information needs."
            ),
            "H_reflect": (
                "Reflect over all returned Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while preserving "
                "uncertainty."
            ),
        }
        corrected = json.loads(json.dumps(missing))
        corrected["B"]["requests"].append(
            {
                "request_id": "recent_market_backbone",
                "description": "Read recent point-in-time price and volume.",
                "source_types": ["market_data"],
                "lookback_days": 45,
                "max_documents": 1,
            }
        )
        caller = ScriptedRoleCaller([missing, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(
            plan.basic_info_policy.requests[-1].request_id,
            "recent_market_backbone",
        )
        self.assertEqual(
            [call["stage"] for call in caller.calls],
            ["information_plan_propose", "information_plan_propose_correction"],
        )
        self.assertIn("market_data", str(caller.calls[0]["system_prompt"]))

    def test_v81_plan_proposer_corrects_cross_issuer_request_scope(self) -> None:
        invalid = {
            "B": {
                "requests": [
                    {
                        "request_id": "recent_company_news",
                        "description": "Read recent company news.",
                        "source_types": ["news"],
                        "lookback_days": 180,
                        "max_documents": 5,
                    },
                    {
                        "request_id": "recent_market_backbone",
                        "description": "Read recent market data.",
                        "source_types": ["market_data"],
                        "lookback_days": 45,
                        "max_documents": 1,
                    },
                    {
                        "request_id": "competitor_actions",
                        "description": (
                            "Competitor actions that could affect the company's "
                            "market position."
                        ),
                        "source_types": ["news"],
                        "lookback_days": 180,
                        "query": "competitor product launch market share",
                        "max_documents": 3,
                    },
                ]
            },
            "H_init": (
                "Form an initial source-backed hypothesis and list unresolved "
                "information needs."
            ),
            "H_reflect": (
                "Reflect over all returned Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while preserving "
                "uncertainty."
            ),
        }
        corrected = json.loads(json.dumps(invalid))
        corrected_request = corrected["B"]["requests"][2]
        corrected_request["description"] = (
            "Read the target issuer's own disclosures about competitive position."
        )
        corrected_request["query"] = "competitive position"
        caller = ScriptedRoleCaller([invalid, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        error = caller.calls[1]["payload"]["validation_feedback"][
            "validation_error"
        ]
        self.assertIn("B.requests[2].description", error)
        self.assertIn("B.requests[2].query", error)
        self.assertIn("target-company-scoped Basic Info resolver", error)
        self.assertIn("target company_id", caller.calls[0]["system_prompt"])
        self.assertEqual(
            plan.basic_info_policy.requests[2].description,
            corrected_request["description"],
        )

    def test_v19_plan_proposer_corrects_placeholder_example_echo(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v19_proposer_placeholder_echo.json"
            ).read_text(encoding="utf-8")
        )
        caller = ScriptedRoleCaller(
            [fixture["invalid_output"], fixture["corrected_output"]]
        )

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=3,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(
            plan.initial_research_skill,
            fixture["corrected_output"]["H_init"],
        )
        self.assertEqual(
            caller.stages,
            ["information_plan_propose", "information_plan_propose_correction"],
        )
        initial = caller.calls[0]
        correction = caller.calls[1]
        self.assertIsNone(initial["payload"]["validation_feedback"])
        feedback = correction["payload"]["validation_feedback"]
        validation_error = feedback["validation_error"]
        self.assertIn("H_init is a placeholder", validation_error)
        self.assertIn("H_reflect is a placeholder", validation_error)
        self.assertIn("H_analyse is a placeholder", validation_error)
        self.assertEqual(feedback["invalid_output"], fixture["invalid_output"])
        self.assertEqual(
            initial["payload"]["proposal_context"],
            correction["payload"]["proposal_context"],
        )
        self.assertEqual(initial["system_prompt"], correction["system_prompt"])
        stable_prefix = json.dumps(
            {"proposal_context": initial["payload"]["proposal_context"]},
            sort_keys=True,
            separators=(",", ":"),
        )[:-1] + ',"validation_feedback":'
        for call in (initial, correction):
            rendered = json.dumps(
                call["payload"], sort_keys=True, separators=(",", ":")
            )
            self.assertTrue(rendered.startswith(stable_prefix))
        self.assertIn(
            "returning the same rejected field is not a correction",
            correction["system_prompt"],
        )
        self.assertNotIn(
            "complete initialization instructions",
            caller.calls[0]["system_prompt"],
        )
        example_skills = (
            evolution_runtime_module._LEGACY_INFORMATION_PLAN_EXAMPLE_SKILLS
        )
        for example in example_skills.values():
            self.assertNotIn(example, initial["system_prompt"])
        example_echo = InformationPlan(
            plan_id="example_echo",
            parent_ids=(),
            basic_info_policy=default_information_plan().basic_info_policy,
            initial_research_skill=example_skills["H_init"],
            reflection_skill=example_skills["H_reflect"],
            analysis_prompt=example_skills["H_analyse"],
        )
        with self.assertRaisesRegex(ValidationError, "output-contract example echo"):
            evolution_runtime_module._validate_proposed_plan_skills(example_echo)

    def test_default_information_plan_has_compact_market_backbone(self) -> None:
        plan = default_information_plan()
        request = plan.basic_info_policy.requests[-1]

        self.assertEqual(request.source_types, ("market_data",))
        self.assertEqual(request.lookback_days, 45)
        self.assertEqual(request.max_documents, 1)
        model_catalog = set(
            evolution_runtime_module._model_available_source_types(
                ("filing", "financials", "market_data", "news")
            )
        )
        self.assertTrue(
            {
                source_type
                for item in plan.basic_info_policy.requests
                for source_type in item.source_types
            }.issubset(model_catalog)
        )
        self.assertIn("10-k", model_catalog)
        self.assertIn("sec_company_facts", model_catalog)
        self.assertNotIn("earnings_call", model_catalog)

    def test_signal_update_role_returns_one_exact_semantic_decision(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "signal_ref": "revenue_growth_yoy:v1",
                    "disposition": "defer",
                    "problem_type": "routing_applicability_unclear",
                    "rationale": ["The evidence does not isolate a Signal defect."],
                    "candidate": None,
                }
            ]
        )
        model = LLMSignalUpdateModel(caller)

        step = model.update(
            {
                "target": {"signal_ref": "revenue_growth_yoy:v1"},
                "induction_cases": [],
                "candidate_contract": {},
            }
        )

        self.assertEqual(step.value.disposition, "defer")
        system_prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn("routing/applicability mistake", system_prompt)
        self.assertIn('"no_change"', system_prompt)

    def test_signal_mining_roles_parse_hypotheses_and_rank_only_allowed_refs(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "order_confirmation",
                            "statement": "Confirmed orders precede repricing.",
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases confirm more orders than control cases."
                            ),
                            "source_types": ["filings"],
                            "query": "material order",
                            "falsifiers": [
                                "Positive cases and control cases confirm orders "
                                "equally often."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                },
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "order_confirmation",
                            "statement": "Confirmed orders precede repricing.",
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases confirm more orders than control cases."
                            ),
                            "source_types": ["filing"],
                            "query": "material order",
                            "falsifiers": [
                                "Positive cases and control cases confirm orders "
                                "equally often."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "order_confirmation",
                            "cases": [
                                {
                                    "case_ref": "case-002",
                                    "profile_evidence": "project-driven hardware",
                                    "applicability_reason": (
                                        "The profile directly identifies project-driven "
                                        "operations."
                                    ),
                                },
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "project-driven hardware",
                                    "applicability_reason": (
                                        "The profile directly identifies project-driven "
                                        "operations."
                                    ),
                                },
                            ],
                        }
                    ]
                },
            ]
        )
        model = LLMSignalMiningModel(caller, creative_temperature=1.0)

        hypotheses = model.propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "meta_info": [],
                "available_raw_source_types": ["news", "filing"],
            }
        )
        rankings = model.rank_cases(
            {
                "hypotheses": [item.to_dict() for item in hypotheses.value],
                "case_briefs": [
                    {"case_ref": "case-001", "industry": "project-driven hardware"},
                    {"case_ref": "case-002", "industry": "project-driven hardware"},
                ],
            }
        )

        self.assertEqual(hypotheses.value[0].hypothesis_id, "order_confirmation")
        self.assertEqual(
            rankings.value["order_confirmation"],
            ("case-002", "case-001"),
        )
        self.assertEqual(
            caller.stages,
            [
                "signal_mining_hypotheses",
                "signal_mining_hypotheses_correction",
                "signal_mining_case_ranking",
            ],
        )
        self.assertEqual(caller.calls[0]["temperature"], 1.0)
        self.assertEqual(caller.calls[1]["temperature"], 1.0)
        self.assertNotIn("large_order_confirmation", caller.calls[0]["system_prompt"])
        self.assertNotIn(
            "material order contract customer award",
            caller.calls[0]["system_prompt"],
        )
        self.assertIn(
            "validation_error", caller.calls[1]["payload"]["validation_feedback"]
        )
        self.assertEqual(caller.calls[2]["temperature"], 0.0)
        self.assertFalse(caller.calls[2]["allow_outcomes"])

    def test_signal_update_role_repairs_wrong_target_once(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "signal_ref": "other_signal:v1",
                    "disposition": "no_change",
                    "problem_type": "routing",
                    "rationale": ["No definition change is justified."],
                    "candidate": None,
                },
                {
                    "signal_ref": "price_momentum_126d:v1",
                    "disposition": "no_change",
                    "problem_type": "routing",
                    "rationale": ["The observed issue belongs to Plan routing."],
                    "candidate": None,
                },
            ]
        )

        step = LLMSignalUpdateModel(caller).update(
            {
                "target": {"signal_ref": "price_momentum_126d:v1"},
                "induction_cases": [],
                "candidate_contract": {},
            }
        )

        self.assertEqual(step.value.signal_ref, "price_momentum_126d:v1")
        self.assertEqual(step.usage.llm_calls, 2)
        self.assertEqual(
            caller.stages,
            ["signal_update_decision", "signal_update_decision_correction"],
        )
        self.assertIn("validation_error", caller.calls[1]["payload"])

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
                    signal_selection("revenue_growth_yoy:v1"),
                ]
            )
            routing_state = ResearchState(
                hypotheses=("A mature operator may benefit from stronger pricing.",),
                current_beliefs=("The issuer operates established mature mines.",),
                supporting_evidence=(
                    ResearchEvidenceRef(
                        kind="basic_info",
                        claim="The issuer operates established mature mines.",
                        projection_id="projection_mature",
                        exact_text="Literal mature-operation source text.",
                    ),
                ),
                contradictions=("No pre-commercial product is currently evidenced.",),
                resolved_questions=("The operating stage is established.",),
                open_questions=("Can production grow further?",),
                next_information_needs=("revenue growth",),
            )
            selection = LLMSignalRetrievalAgent(selector_caller).select(
                ("revenue growth",),
                registry.freeze(),
                {"cash_reserves:v1": ("opaque-document-hash",)},
                research_state=routing_state,
            )
            self.assertEqual(
                tuple(item.signal_ref for item in selection.value),
                ("revenue_growth_yoy:v1",),
            )
            self.assertEqual(
                selector_caller.stages,
                ["signal_retrieval_cards"],
            )
            payload = selector_caller.calls[0]["payload"]
            cards = payload["available_signal_cards"]
            self.assertEqual(len(cards), 14)
            self.assertIn("category", cards[0])
            self.assertNotIn("learned_profile", cards[0])
            self.assertEqual(
                payload["learned_profile_default"],
                "no committed observations",
            )
            self.assertNotIn(
                "previous_signal_document_fingerprints",
                payload,
            )
            self.assertEqual(
                payload["research_context"],
                {
                    "hypotheses": list(routing_state.hypotheses),
                    "current_beliefs": list(routing_state.current_beliefs),
                    "contradictions": list(routing_state.contradictions),
                    "resolved_questions": list(routing_state.resolved_questions),
                    "open_questions": list(routing_state.open_questions),
                    "evidence_claims": [
                        "The issuer operates established mature mines."
                    ],
                },
            )
            self.assertNotIn("projection_mature", json.dumps(payload["research_context"]))
            self.assertNotIn(
                "Literal mature-operation source text.",
                json.dumps(payload["research_context"]),
            )
            self.assertIn(
                "use it only to test Signal applicability",
                selector_caller.calls[0]["system_prompt"],
            )
            self.assertTrue(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).startswith(
                    '{"available_signal_cards":'
                )
            )

    def test_signal_selector_repairs_invalid_refs_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    signal_selection("unknown:v1"),
                    signal_selection("revenue_growth_yoy:v1"),
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",), registry.freeze(), {}
            )

            self.assertEqual(
                tuple(item.signal_ref for item in selection.value),
                ("revenue_growth_yoy:v1",),
            )
            self.assertEqual(selection.usage.llm_calls, 2)
            self.assertIn("outside supplied cards", validation_error(caller.calls[1]))

    def test_signal_selector_fails_closed_after_invalid_correction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    signal_selection("unknown:v1"),
                    {"selections": "still-not-an-array"},
                ]
            )

            with self.assertRaisesRegex(
                CandidateExecutionRejected,
                "failed validation after one correction",
            ) as context:
                LLMSignalRetrievalAgent(caller).select(
                    ("revenue growth",), registry.freeze(), {}
                )

            self.assertEqual(context.exception.usage.llm_calls, 2)
            self.assertEqual(
                caller.stages,
                [
                    "signal_retrieval_cards",
                    "signal_retrieval_cards_correction",
                ],
            )

    def test_signal_selector_repairs_non_array_containers_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    {"selections": "revenue_growth_yoy:v1"},
                    signal_selection("revenue_growth_yoy:v1"),
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",), registry.freeze(), {}
            )

            self.assertEqual(
                tuple(item.signal_ref for item in selection.value),
                ("revenue_growth_yoy:v1",),
            )
            self.assertEqual(selection.usage.llm_calls, 2)

    def test_signal_selector_accepts_empty_no_match_without_correction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller([{"selections": []}])

            selection = LLMSignalRetrievalAgent(caller).select(
                ("unmatched need",), registry.freeze(), {}
            )

            self.assertEqual(selection.value, ())
            self.assertEqual(selection.usage.llm_calls, 1)
            self.assertEqual(
                caller.stages,
                ["signal_retrieval_cards"],
            )

    def test_v16_signal_selector_corrects_explicit_term_matched_empty(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/v16_empty_signal_routing.json"
            ).read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    fixture["invalid_output"],
                    signal_selection(fixture["corrected_signal_ref"]),
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                tuple(fixture["information_needs"]), registry.freeze(), {}
            )

            self.assertEqual(
                tuple(item.signal_ref for item in selection.value),
                (fixture["corrected_signal_ref"],),
            )
            self.assertEqual(selection.usage.llm_calls, 2)
            self.assertIn(
                fixture["corrected_signal_ref"],
                validation_error(caller.calls[1]),
            )
            self.assertIn(
                "Returning the same rejected content",
                caller.calls[1]["system_prompt"],
            )

    def test_v21_signal_selector_corrects_version_owned_guidance_empty(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/v21_empty_guidance_routing.json"
            ).read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    fixture["invalid_output"],
                    signal_selection(fixture["corrected_signal_ref"]),
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                tuple(fixture["information_needs"]), registry.freeze(), {}
            )

        self.assertEqual(
            tuple(item.signal_ref for item in selection.value),
            (fixture["corrected_signal_ref"],),
        )
        guidance_card = next(
            item
            for item in caller.calls[0]["payload"]["available_signal_cards"]
            if item["signal_ref"] == fixture["corrected_signal_ref"]
        )
        self.assertEqual(guidance_card["routing_need_phrases"], ["guidance"])
        self.assertIn(
            "version-owned information-need phrase",
            validation_error(caller.calls[1]),
        )
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        stable_context = {
            key: value
            for key, value in caller.calls[0]["payload"].items()
            if key != "validation_feedback"
        }
        self.assertEqual(
            stable_context,
            {
                key: value
                for key, value in caller.calls[1]["payload"].items()
                if key != "validation_feedback"
            },
        )
        stable_prefix = json.dumps(
            stable_context, sort_keys=True, separators=(",", ":")
        )[:-1] + ',"validation_feedback":'
        for call in caller.calls:
            rendered = json.dumps(
                call["payload"], sort_keys=True, separators=(",", ":")
            )
            self.assertTrue(rendered.startswith(stable_prefix))

    def test_signal_selector_corrects_version_owned_excluded_context_tag(self) -> None:
        incompatible = signal_selection("commercialization_status:v1")
        item = incompatible["selections"][0]
        item["applicability_hypothesis"] = (
            "This mature gold producer reflects ordinary operations."
        )
        item["context_tags"] = ["mature_operations", "materials"]
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([incompatible, {"selections": []}])

            selection = LLMSignalRetrievalAgent(caller).select(
                ("Clarify production status for the mature producer.",),
                snapshot,
                {},
            )
            applicable_caller = ScriptedRoleCaller(
                [signal_selection("commercialization_status:v1")]
            )
            applicable = LLMSignalRetrievalAgent(applicable_caller).select(
                ("Check a new product's commercial transition.",),
                snapshot,
                {},
            )
            omitted_prior_tag = signal_selection("commercialization_status:v1")
            omitted_prior_tag["selections"][0]["context_tags"] = ["general"]
            prior_caller = ScriptedRoleCaller(
                [omitted_prior_tag, {"selections": []}]
            )
            prior_classified = LLMSignalRetrievalAgent(prior_caller).select(
                ("Check whether a distinct new product became commercial.",),
                snapshot,
                {},
                prior_context_tags=("mature_operations",),
            )

        self.assertEqual(selection.value, ())
        self.assertEqual(selection.usage.llm_calls, 2)
        card = next(
            card
            for card in caller.calls[0]["payload"]["available_signal_cards"]
            if card["signal_ref"] == "commercialization_status:v1"
        )
        self.assertEqual(
            card["routing_excluded_context_tags"], ["mature_operations"]
        )
        self.assertIn(
            "version-owned routing exclusion", validation_error(caller.calls[1])
        )
        self.assertIn("mature_operations", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertEqual(
            tuple(item.signal_ref for item in applicable.value),
            ("commercialization_status:v1",),
        )
        self.assertEqual(applicable.usage.llm_calls, 1)
        self.assertEqual(prior_classified.value, ())
        self.assertEqual(
            prior_caller.calls[0]["payload"]["previous_context_tags"],
            ["mature_operations"],
        )
        self.assertIn(
            "earlier accepted case classification",
            validation_error(prior_caller.calls[1]),
        )

    def test_v63_order_quality_cannot_relabel_a_share_sale_as_an_order(self) -> None:
        invalid = signal_selection("order_quality:v1")
        invalid_item = invalid["selections"][0]
        invalid_item["reason_code"] = "assess_applicability"
        invalid_item["target_need_indices"] = []
        invalid_item["answer_scope"] = None
        invalid_item["residual_need"] = None
        invalid_item["selection_reason"] = (
            "Assess whether the Asante share-sale terms are binding and material."
        )
        invalid_item["applicability_hypothesis"] = (
            "The sale may be evaluated as a binding transaction."
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([invalid, {"selections": []}])

            rejected_analogy = LLMSignalRetrievalAgent(caller).select(
                (
                    "What are the specific terms and potential impact of the Asante "
                    "Gold share sale on the company's financial position?",
                ),
                snapshot,
                {},
                research_state=ResearchState(
                    hypotheses=("Gold prices may support further repricing.",),
                    next_information_needs=(
                        "Clarify the financial impact of the share sale.",
                    ),
                ),
            )
            applicable_caller = ScriptedRoleCaller(
                [signal_selection("order_quality:v1")]
            )
            applicable = LLMSignalRetrievalAgent(applicable_caller).select(
                (
                    "Are the disclosed customer purchase orders binding and likely "
                    "to convert to revenue?",
                ),
                snapshot,
                {},
            )

        self.assertEqual(rejected_analogy.value, ())
        self.assertEqual(rejected_analogy.usage.llm_calls, 2)
        order_card = next(
            card
            for card in caller.calls[0]["payload"]["available_signal_cards"]
            if card["signal_ref"] == "order_quality:v1"
        )
        self.assertIn(
            "purchase order",
            order_card["routing_required_research_phrases"],
        )
        error = validation_error(caller.calls[1])
        self.assertIn("version-owned required research context", error)
        self.assertIn("order_quality:v1", error)
        self.assertIn("new analogy", error)
        self.assertEqual(
            tuple(item.signal_ref for item in applicable.value),
            ("order_quality:v1",),
        )
        self.assertEqual(applicable.usage.llm_calls, 1)
        self.assertIn(
            "Use reason_code=answer_need only when the card description directly",
            caller.calls[0]["system_prompt"],
        )

    def test_v66_mining_project_is_not_a_product_commercialization(self) -> None:
        invalid = signal_selection("commercialization_status:v1")
        invalid_item = invalid["selections"][0]
        invalid_item["reason_code"] = "combine_evidence"
        invalid_item["target_need_indices"] = []
        invalid_item["answer_scope"] = None
        invalid_item["residual_need"] = None
        invalid_item["selection_reason"] = (
            "Use updates on Tasiast and Lobo-Marte as commercialization evidence."
        )
        invalid_item["applicability_hypothesis"] = (
            "Major mining projects may represent commercialization milestones."
        )
        invalid_item["context_tags"] = ["general", "project_driven"]
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([invalid, {"selections": []}])

            rejected_project = LLMSignalRetrievalAgent(caller).select(
                (
                    "What are the latest updates on major mining projects like "
                    "Tasiast and Lobo-Marte?",
                ),
                snapshot,
                {},
            )
            applicable_caller = ScriptedRoleCaller(
                [signal_selection("commercialization_status:v1")]
            )
            applicable = LLMSignalRetrievalAgent(applicable_caller).select(
                (
                    "Has the prototype technology become a sellable repeatable "
                    "product?",
                ),
                snapshot,
                {},
            )

        self.assertEqual(rejected_project.value, ())
        self.assertEqual(rejected_project.usage.llm_calls, 2)
        card = next(
            card
            for card in caller.calls[0]["payload"]["available_signal_cards"]
            if card["signal_ref"] == "commercialization_status:v1"
        )
        self.assertIn("technology", card["routing_required_research_phrases"])
        error = validation_error(caller.calls[1])
        self.assertIn("version-owned required research context", error)
        self.assertIn("commercialization_status:v1", error)
        self.assertEqual(
            tuple(item.signal_ref for item in applicable.value),
            ("commercialization_status:v1",),
        )
        self.assertEqual(applicable.usage.llm_calls, 1)

    def test_v68_customer_concentration_requires_an_existing_customer_object(
        self,
    ) -> None:
        invalid = signal_selection("customer_concentration:v1")
        invalid_item = invalid["selections"][0]
        invalid_item["reason_code"] = "combine_evidence"
        invalid_item["target_need_indices"] = []
        invalid_item["answer_scope"] = None
        invalid_item["residual_need"] = None
        invalid_item["selection_reason"] = (
            "Use operating diversification as customer concentration context."
        )
        invalid_item["applicability_hypothesis"] = (
            "Multiple mines may imply a diversified customer base."
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([invalid, {"selections": []}])

            rejected_analogy = LLMSignalRetrievalAgent(caller).select(
                (
                    "What is the gold price outlook and its effect on revenue and "
                    "profitability?",
                ),
                snapshot,
                {},
            )
            applicable_caller = ScriptedRoleCaller(
                [signal_selection("customer_concentration:v1")]
            )
            applicable = LLMSignalRetrievalAgent(applicable_caller).select(
                (
                    "Does one customer program account for most backlog and revenue?",
                ),
                snapshot,
                {},
            )

        self.assertEqual(rejected_analogy.value, ())
        self.assertEqual(rejected_analogy.usage.llm_calls, 2)
        card = next(
            card
            for card in caller.calls[0]["payload"]["available_signal_cards"]
            if card["signal_ref"] == "customer_concentration:v1"
        )
        self.assertIn("customer", card["routing_required_research_phrases"])
        error = validation_error(caller.calls[1])
        self.assertIn("version-owned required research context", error)
        self.assertIn("customer_concentration:v1", error)
        self.assertEqual(
            tuple(item.signal_ref for item in applicable.value),
            ("customer_concentration:v1",),
        )
        self.assertEqual(applicable.usage.llm_calls, 1)

    def test_v70_customer_contract_need_is_not_concentration_answer_need(
        self,
    ) -> None:
        invalid = signal_selection("customer_concentration:v1")
        invalid_item = invalid["selections"][0]
        invalid_item["selection_reason"] = (
            "Directly assesses announced customer contracts and revenue significance."
        )
        invalid_item["applicability_hypothesis"] = (
            "Recent announcements may reveal customer concentration."
        )
        corrected = json.loads(json.dumps(invalid))
        corrected_item = corrected["selections"][0]
        corrected_item["reason_code"] = "combine_evidence"
        corrected_item["target_need_indices"] = []
        corrected_item["answer_scope"] = None
        corrected_item["residual_need"] = None
        corrected_item["selection_reason"] = (
            "Adds customer-dependence context but does not enumerate contracts."
        )
        corrected_item["expected_role"] = "confirmation"
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([invalid, corrected])

            contextual = LLMSignalRetrievalAgent(caller).select(
                (
                    "What specific customer contracts or partnerships has the "
                    "company announced in the last six months that could "
                    "significantly increase revenue?",
                ),
                snapshot,
                {},
            )
            direct_caller = ScriptedRoleCaller(
                [signal_selection("customer_concentration:v1")]
            )
            direct = LLMSignalRetrievalAgent(direct_caller).select(
                ("Does one customer account for most revenue?",),
                snapshot,
                {},
            )

        self.assertEqual(contextual.usage.llm_calls, 2)
        self.assertEqual(contextual.value[0].reason_code, "combine_evidence")
        error = validation_error(caller.calls[1])
        self.assertIn("reason_code=answer_need", error)
        self.assertIn("version-owned direct-need phrase", error)
        self.assertIn("combine_evidence", error)
        card = next(
            item
            for item in caller.calls[0]["payload"]["available_signal_cards"]
            if item["signal_ref"] == "customer_concentration:v1"
        )
        self.assertIn("one customer", card["routing_answer_need_phrases"])
        self.assertEqual(direct.value[0].reason_code, "answer_need")
        self.assertEqual(direct.usage.llm_calls, 1)

    def test_v71_routing_aggregates_target_and_applicability_errors(self) -> None:
        customer = signal_selection("customer_concentration:v1")["selections"][0]
        customer["reason_code"] = "combine_evidence"
        customer["target_need_indices"] = [1]
        customer["answer_scope"] = None
        customer["residual_need"] = None
        customer["selection_reason"] = (
            "Use customer concentration as context for revenue shortfall risk."
        )
        customer["applicability_hypothesis"] = (
            "Concentration may explain revenue volatility."
        )
        financing = signal_selection("financing_listing_action:v1")["selections"][0]
        financing["reason_code"] = "combine_evidence"
        financing["target_need_indices"] = [2]
        financing["answer_scope"] = None
        financing["residual_need"] = None
        financing["selection_reason"] = (
            "Use financing actions to assess capital expenditure funding."
        )
        financing["applicability_hypothesis"] = (
            "Financing may reveal how capital expenditure is funded."
        )
        revenue = signal_selection("revenue_growth_yoy:v1")["selections"][0]
        revenue["target_need_indices"] = [9]
        corrected_financing = json.loads(json.dumps(financing))
        invalid = {"selections": [customer, financing, revenue]}
        corrected = {"selections": [corrected_financing]}
        information_needs = (
            "What is the current membership count and quarterly growth rate?",
            "What are revenue projections and possible shortfall factors?",
            "What is capital expenditure and how is it funded?",
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([invalid, corrected])

            selection = LLMSignalRetrievalAgent(caller).select(
                information_needs,
                snapshot,
                {},
                research_state=ResearchState(
                    current_beliefs=("Revenue growth remains uncertain.",),
                    next_information_needs=information_needs,
                ),
            )

        error = validation_error(caller.calls[1])
        self.assertNotIn("non-answer reason_code requires an empty", error)
        self.assertIn("selections[2].target_need_indices", error)
        self.assertIn("outside the supplied information_needs", error)
        self.assertIn("version-owned required research context", error)
        self.assertIn("customer_concentration:v1", error)
        self.assertEqual(selection.usage.llm_calls, 2)
        self.assertEqual(
            tuple(item.signal_ref for item in selection.value),
            ("financing_listing_action:v1",),
        )
        self.assertEqual(selection.value[0].target_need_indices, (2,))
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )

    def test_v74_routing_persists_partial_answer_residual(self) -> None:
        target_need = (
            "What is the current cash position and what share-buyback or strategic "
            "funding plans remain?"
        )
        residual_need = "What share-buyback or strategic funding plans remain?"
        output = signal_selection("cash_reserves:v1")
        item = output["selections"][0]
        item["selection_reason"] = "Answer only the current cash-position facet."
        item["answer_scope"] = "partial"
        item["residual_need"] = residual_need
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            caller = ScriptedRoleCaller([output])

            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,),
                registry.freeze(),
                {},
            )

        self.assertEqual(selection.value[0].answer_scope, "partial")
        self.assertEqual(selection.value[0].residual_need, residual_need)
        self.assertIn("answer_scope=full only", caller.calls[0]["system_prompt"])
        self.assertIn("at most one answer_need selection per target", caller.calls[0]["system_prompt"])

    def test_v77_routing_aggregates_semantics_behind_missing_tags(self) -> None:
        information_needs = (
            "What are the latest analyst earnings estimates and revisions?",
            "What is the current gold price trend and forecast?",
            "Are there recent insider or institutional purchases?",
            "What is the current production guidance and any updates on project "
            "timelines?",
            "What are the key operational risks, such as geopolitical issues or "
            "cost inflation?",
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance.pop("context_tags")
        guidance["target_need_indices"] = [3]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = information_needs[0]
        guidance["selection_reason"] = (
            "Answer the production-guidance facet and retain project timelines."
        )
        customer = signal_selection("customer_concentration:v1")["selections"][0]
        customer.pop("context_tags")
        customer["target_need_indices"] = [4]
        customer["answer_scope"] = "partial"
        customer["residual_need"] = information_needs[4]
        customer["selection_reason"] = (
            "Treat customer concentration as a general operational risk."
        )
        corrected_guidance = json.loads(json.dumps(guidance))
        corrected_guidance["context_tags"] = ["general"]
        corrected_guidance["residual_need"] = (
            "What updates are there on project timelines?"
        )
        caller = ScriptedRoleCaller(
            [
                {"selections": [guidance, customer]},
                {"selections": [corrected_guidance]},
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                information_needs,
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=information_needs
                ),
            )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        error = feedback["validation_error"]
        self.assertIn("selections[0] requires exactly", error)
        self.assertIn("selections[0].residual_need must be grounded", error)
        self.assertIn("selections[1] requires exactly", error)
        self.assertIn("selections[1].residual_need must remove", error)
        self.assertIn("version-owned required research context", error)
        self.assertIn("version-owned direct-need phrase", error)
        must_change_paths = {
            path
            for obligation in feedback["obligations"]
            for path in obligation["must_change_paths"]
        }
        self.assertIn("selections[0].residual_need", must_change_paths)
        self.assertIn("selections[1].residual_need", must_change_paths)
        self.assertEqual(selection.value[0].signal_ref, "guidance_acceleration:v1")
        self.assertEqual(
            selection.value[0].residual_need,
            "What updates are there on project timelines?",
        )

    def test_v78_empty_routing_feedback_names_target_before_bad_correction(
        self,
    ) -> None:
        information_needs = (
            "What regulatory milestones are required for the resort?",
            "What is current construction progress and cost?",
            "What is expected customer traffic and revenue contribution?",
            "Are there earnings guidance projections for first-year revenue?",
        )
        bad_guidance = signal_selection("guidance_acceleration:v1")[
            "selections"
        ][0]
        bad_guidance.pop("context_tags")
        bad_guidance["target_need_indices"] = [3]
        bad_guidance["answer_scope"] = "partial"
        bad_guidance["residual_need"] = information_needs[2]
        caller = ScriptedRoleCaller(
            [{"selections": []}, {"selections": [bad_guidance]}]
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            with self.assertRaises(CandidateExecutionRejected) as raised:
                LLMSignalRetrievalAgent(caller).select(
                    information_needs,
                    registry.freeze(),
                    {},
                )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 1)
        self.assertEqual(
            feedback["obligations"][0]["must_change_paths"], ["selections"]
        )
        self.assertIn("'target_need_index': 3", feedback["validation_error"])
        self.assertIn("'matched_phrases': ['guidance']", feedback["validation_error"])
        self.assertIn(
            "must not copy a different information_needs item",
            caller.calls[0]["system_prompt"],
        )
        self.assertIn("missing=['context_tags']", str(raised.exception))
        self.assertIn("residual_need must be grounded", str(raised.exception))

    def test_v78_partial_reason_cannot_claim_the_residual_facet(self) -> None:
        target_need = (
            "What are the latest production and cost guidance for 2025-2027, and "
            "any updates on Tasiast mill restart?"
        )
        invalid = signal_selection("guidance_acceleration:v1")
        invalid_item = invalid["selections"][0]
        invalid_item["answer_scope"] = "partial"
        invalid_item["residual_need"] = (
            "What are the latest Tasiast mill restart timeline updates and their "
            "impact on production?"
        )
        invalid_item["selection_reason"] = (
            "Covers production and cost guidance, including Tasiast mill restart "
            "impact."
        )
        corrected = json.loads(json.dumps(invalid))
        corrected["selections"][0]["selection_reason"] = (
            "Covers only the production and cost guidance facet."
        )
        caller = ScriptedRoleCaller([invalid, corrected])
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selected = LLMSignalRetrievalAgent(caller).select(
                (target_need,), registry.freeze(), {}
            )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn(
            "selections[0].selection_reason claims a facet retained",
            feedback["validation_error"],
        )
        self.assertIn("'tasiast mill restart'", feedback["validation_error"])
        self.assertIn(
            "selections[0].selection_reason",
            {
                path
                for obligation in feedback["obligations"]
                for path in obligation["must_change_paths"]
            },
        )
        self.assertEqual(selected.value[0].selection_reason, corrected["selections"][0]["selection_reason"])

    def test_signal_selector_exposes_only_eligible_unexecuted_cards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller([{"selections": []}])
            prior_result = {
                "signal_id": "cash_reserves",
                "version": 1,
                "state": {"value": "positive", "confidence": 0.8},
            }

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",),
                registry.freeze(),
                {"cash_reserves:v1": ("doc:hash",)},
                {"cash_reserves:v1": prior_result},
                ("revenue_growth_yoy:v1",),
            )

            self.assertEqual(selection.value, ())
            self.assertEqual(selection.usage.llm_calls, 1)
            payload = caller.calls[0]["payload"]
            self.assertEqual(
                [
                    card["signal_ref"]
                    for card in payload["available_signal_cards"]
                ],
                ["revenue_growth_yoy:v1"],
            )
            self.assertEqual(
                payload["previous_signal_results"]["cash_reserves:v1"],
                prior_result,
            )

    def test_signal_selector_skips_model_when_no_eligible_cards_remain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller([])

            selection = LLMSignalRetrievalAgent(caller).select(
                ("anything new",),
                registry.freeze(),
                {},
                {},
                (),
            )

            self.assertEqual(selection.value, ())
            self.assertEqual(selection.usage.llm_calls, 0)
            self.assertEqual(caller.stages, [])

    def test_soft_signal_apply_chain_retrieves_executes_and_reflects_once(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-guidance-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Management raised full-year revenue guidance to 40 percent growth.",
        )
        signal_output = {
            "signal_id": "guidance_acceleration",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.9},
            "interpretation": {"summary": "Management materially raised guidance."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": document.document_id,
                        "exact_span": document.content,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        reflected_state = {
            "hypotheses": ["guidance is accelerating"],
            "current_beliefs": ["the source supports acceleration"],
            "supporting_evidence": [
                {
                    "kind": "signal",
                    "claim": "Management materially raised guidance.",
                    "signal_ref": "guidance_acceleration",
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                    "projection_id": document.document_id,
                    "exact_text": document.content,
                }
            ],
            "contradictions": [],
            "resolved_questions": ["did management raise guidance"],
            "open_questions": [],
            "next_information_needs": [],
            "decision": "finalize",
        }

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            snapshot = registry.freeze()
            selector_caller = ScriptedRoleCaller(
                [signal_selection("guidance_acceleration:v1")]
            )
            signal_caller = ScriptedRoleCaller([signal_output])
            controller_caller = ScriptedRoleCaller([reflected_state])

            selected = LLMSignalRetrievalAgent(selector_caller).select(
                ("did management raise guidance",),
                snapshot,
                {},
                {},
                ("guidance_acceleration:v1",),
            )
            batch = SignalExecutor(
                snapshot,
                RawInfoStore(documents=(document,)),
                llm_runner=StructuredLLMSignalRunner(signal_caller),
            ).execute_batch(
                tuple(item.signal_ref for item in selected.value),
                company_id="issuer-1",
                as_of=as_of,
            )
            reflected = LLMResearchController(controller_caller).reflect(
                default_information_plan(),
                ResearchState(
                    hypotheses=("guidance may be accelerating",),
                    next_information_needs=("did management raise guidance",),
                ),
                batch,
            )

            self.assertEqual(selector_caller.stages, ["signal_retrieval_cards"])
            self.assertEqual(signal_caller.stages, ["llm_signal_batch_execute"])
            self.assertEqual(
                controller_caller.stages,
                ["research_controller_reflect"],
            )
            self.assertEqual(batch.signal_calls, 1)
            self.assertEqual(batch.results[0].value, SignalValue.POSITIVE)
            self.assertEqual(
                batch.results[0].supporting_evidence[0].exact_span,
                document.content,
            )
            self.assertEqual(reflected.value.decision, ResearchDecision.FINALIZE)
            self.assertEqual(
                set(reflected.value.to_dict()["supporting_evidence"][0]),
                {
                    "kind",
                    "claim",
                    "signal_ref",
                    "evidence_group",
                    "evidence_index",
                },
            )
            self.assertEqual(
                reflected.value.to_dict()["supporting_evidence"][0]["signal_ref"],
                "guidance_acceleration:v1",
            )
            self.assertEqual(
                controller_caller.calls[0]["payload"]["signal_batch"][0][
                    "signal_ref"
                ],
                "guidance_acceleration:v1",
            )

    def test_reflect_correction_names_exact_valid_signal_evidence_indices(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "evolution_runtime"
                / "v4_reflect_unknown_signal_evidence_index.json"
            ).read_text(encoding="utf-8")
        )
        invalid_output = fixture["invalid_output"]
        corrected_output = json.loads(json.dumps(invalid_output))
        corrected_output["supporting_evidence"][1]["evidence_index"] = 0
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        evidence = SignalEvidence(
            document_id="market-data-1",
            exact_span="price_momentum_126d=0.951161; max_drawdown_1y=-0.16",
            timestamp=timestamp,
        )
        batch = SignalBatchResult(
            results=(
                SignalResult(
                    signal_id="max_drawdown_1y",
                    version=1,
                    value=SignalValue.POSITIVE,
                    confidence=1.0,
                    interpretation="max_drawdown_1y=-0.16",
                    supporting_evidence=(evidence,),
                ),
                SignalResult(
                    signal_id="price_momentum_126d",
                    version=1,
                    value=SignalValue.POSITIVE,
                    confidence=1.0,
                    interpretation="price_momentum_126d=0.951161",
                    supporting_evidence=(evidence,),
                ),
            ),
            signal_calls=2,
        )
        caller = ScriptedRoleCaller([invalid_output, corrected_output])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            ResearchState(next_information_needs=("confirm sustainability",)),
            batch,
        )

        expected_catalog = [
            {
                "signal_ref": "max_drawdown_1y:v1",
                "supporting_evidence_indices": [0],
                "counter_evidence_indices": [],
            },
            {
                "signal_ref": "price_momentum_126d:v1",
                "supporting_evidence_indices": [0],
                "counter_evidence_indices": [],
            },
        ]
        self.assertEqual(
            caller.stages,
            ["research_controller_reflect", "research_controller_reflect_correction"],
        )
        self.assertEqual(
            caller.calls[0]["payload"]["signal_evidence_ref_catalog"],
            expected_catalog,
        )
        correction_payload = caller.calls[1]["payload"]
        self.assertEqual(
            correction_payload["signal_evidence_ref_catalog"], expected_catalog
        )
        error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[1]", error)
        self.assertIn("max_drawdown_1y:v1", error)
        self.assertIn("evidence_index=1", error)
        self.assertIn("valid_evidence_indices=[0]", error)
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        self.assertNotIn("validation_error", correction_payload)
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertEqual(
            reflected.value.supporting_evidence[1].evidence_index,
            0,
        )

        failing_caller = ScriptedRoleCaller([invalid_output, invalid_output])
        with self.assertRaises(CandidateExecutionRejected):
            LLMResearchController(failing_caller).reflect(
                default_information_plan(),
                ResearchState(next_information_needs=("confirm sustainability",)),
                batch,
            )
        self.assertEqual(
            failing_caller.stages,
            ["research_controller_reflect", "research_controller_reflect_correction"],
        )

    def test_reflect_correction_names_malformed_retained_basic_ref_fields(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "evolution_runtime"
                / "v5_reflect_malformed_retained_basic_ref.json"
            ).read_text(encoding="utf-8")
        )
        invalid_output = fixture["invalid_output"]
        corrected_output = json.loads(json.dumps(invalid_output))
        corrected_output["supporting_evidence"] = [fixture["prior_evidence_ref"]]
        previous = ResearchState(
            supporting_evidence=(
                ResearchEvidenceRef.from_dict(fixture["prior_evidence_ref"]),
            ),
            next_information_needs=("clarify revenue",),
        )
        batch = SignalBatchResult(
            results=(
                SignalResult(
                    signal_id="revenue_growth_yoy",
                    version=1,
                    value=SignalValue.UNAVAILABLE,
                    confidence=0.0,
                    interpretation="Revenue inputs are unavailable.",
                    coverage=SignalCoverage.UNAVAILABLE,
                ),
                SignalResult(
                    signal_id="operating_cash_flow_margin",
                    version=1,
                    value=SignalValue.UNAVAILABLE,
                    confidence=0.0,
                    interpretation="Cash-flow inputs are unavailable.",
                    coverage=SignalCoverage.UNAVAILABLE,
                ),
            ),
            signal_calls=2,
        )
        caller = ScriptedRoleCaller([invalid_output, corrected_output])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(), previous, batch
        )

        correction_payload = caller.calls[1]["payload"]
        error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[0]", error)
        self.assertIn("missing_fields=['exact_text']", error)
        self.assertIn(
            "unexpected_fields=['evidence_group', 'evidence_index']", error
        )
        self.assertIn("research_state.supporting_evidence", error)
        self.assertEqual(
            correction_payload["research_state"]["supporting_evidence"][0],
            fixture["prior_evidence_ref"],
        )
        self.assertEqual(
            reflected.value.supporting_evidence[0].exact_text,
            fixture["prior_evidence_ref"]["exact_text"],
        )

        failing_caller = ScriptedRoleCaller([invalid_output, invalid_output])
        with self.assertRaises(CandidateExecutionRejected):
            LLMResearchController(failing_caller).reflect(
                default_information_plan(), previous, batch
            )
        self.assertEqual(
            failing_caller.stages,
            ["research_controller_reflect", "research_controller_reflect_correction"],
        )

    def test_blind_predictor_parses_two_stage_schema(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "candidate_judgment": "possible",
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
        self.assertIn(
            'candidate_judgment must be "likely", "possible", "unlikely", or',
            prompt,
        )
        self.assertIn("Possible is a screening judgment", prompt)
        self.assertIn("does not require a quantified valuation bridge", prompt)
        self.assertIn("early market confirmation can support possible", prompt)
        self.assertIn("Do not require a guarantee", prompt)
        self.assertIn("outcome-stratified", prompt)
        self.assertIn("do not predict false merely because 2x moves are rare", prompt)
        self.assertIn("need not be more than 50% probable", prompt)
        self.assertNotIn("is_surge", prompt)

    def test_v78_blind_predictor_corrects_stale_price_labeled_current(self) -> None:
        invalid = {
            "candidate_judgment": "unlikely",
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": [
                "Current price $19.38 is far below the defined doubling threshold."
            ],
            "uncertainties": [],
            "session_id": "fixture-session",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["key_reasons"] = [
            "The prediction-time baseline price is $23.98, while visible catalyst "
            "evidence remains limited."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        prediction = LLMBlindPredictor(caller).predict(
            {
                "prediction_baseline": {
                    "status": "available",
                    "method": "mean_last_5_complete_adjusted_closes",
                    "mean_adjusted_close": 23.982,
                    "trading_dates": [],
                },
                "final_research_state": {},
            }
        )

        self.assertEqual(prediction.usage.llm_calls, 2)
        self.assertEqual(
            caller.stages,
            ["blind_predictor_predict", "blind_predictor_predict_correction"],
        )
        self.assertIn(
            "key_reasons[0] labels 19.38",
            caller.calls[1]["payload"]["validation_error"],
        )
        self.assertIn(
            "final_context.prediction_baseline", caller.calls[0]["system_prompt"]
        )
        self.assertIn("$23.98", prediction.value.key_reasons[0])

    def test_blind_predictor_repairs_legacy_binary_shape(self) -> None:
        valid = {
            "candidate_judgment": "unlikely",
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": ["limited source-backed evidence"],
            "uncertainties": [],
            "session_id": "fixture-session",
        }
        legacy = dict(valid)
        legacy.pop("candidate_judgment")
        legacy["decision"] = "NO"
        caller = ScriptedRoleCaller([legacy, valid])

        prediction = LLMBlindPredictor(caller).predict(
            {"basic_info": {"industry": "fixture"}}
        )

        self.assertFalse(prediction.value.is_surge)
        self.assertEqual(
            caller.stages,
            ["blind_predictor_predict", "blind_predictor_predict_correction"],
        )
        self.assertIn("validation_error", caller.calls[1]["payload"])

    def test_blind_predictor_maps_four_way_candidate_judgment(self) -> None:
        class FourWayRoleCaller(ScriptedRoleCaller):
            def complete_binary_token_with_scores(self, **kwargs):
                raise AssertionError("four-way Predictor must not request token scores")

        expected = {
            "likely": True,
            "possible": True,
            "unlikely": False,
            "insufficient_information": False,
        }
        for judgment, is_surge in expected.items():
            with self.subTest(judgment=judgment):
                caller = FourWayRoleCaller(
                    [
                        {
                            "candidate_judgment": judgment,
                            "magnitude": "2-3x" if is_surge else None,
                            "confidence": {"level": "low"},
                            "key_reasons": ["source-backed assessment"],
                            "uncertainties": [],
                            "session_id": "fixture-session",
                        }
                    ]
                )
                prediction = LLMBlindPredictor(caller).predict(
                    {"basic_info": {"industry": "fixture"}}
                )
                self.assertEqual(prediction.value.is_surge, is_surge)
                self.assertEqual(
                    prediction.value.candidate_judgment.value,
                    judgment,
                )
                self.assertEqual(caller.stages, ["blind_predictor_predict"])

    def test_posthoc_reflection_does_not_rescan_low_confidence_as_ticker(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "prediction_outcome": {"correct": False},
                    "decision_drivers": [
                        "Limited supplied evidence supported the negative judgment."
                    ],
                    "why_prediction_failed": [],
                    "misleading_signals": [],
                    "ignored_evidence": [],
                    "missing_information": [],
                    "plan_issues": [],
                }
            ]
        )
        predictor = LLMBlindPredictor(caller, anonymous_aliases=("LOW",))

        reflection = predictor.reflect(
            {"summary": "anonymous evidence"},
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.UNLIKELY,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("limited evidence",),
                uncertainties=(),
                session_id="anonymous-session",
            ),
            GroundTruth(1.2),
        )

        self.assertEqual(caller.calls[0]["anonymous_aliases"], ())
        self.assertNotIn(
            "decision_confidence_feedback", caller.calls[0]["payload"]
        )
        feedback = caller.calls[0]["payload"]["candidate_judgment_feedback"]
        self.assertEqual(feedback["assessment"], "strong_correct_negative")
        self.assertTrue(feedback["binary_correct"])
        self.assertTrue(reflection.value.correct)
        self.assertTrue(
            caller.calls[0]["payload"]["framework_prediction_correct"]
        )
        self.assertNotIn("token probability", caller.calls[0]["system_prompt"])
        self.assertIn(
            "candidate_judgment_feedback",
            caller.calls[0]["system_prompt"],
        )

    def test_posthoc_reflection_still_scans_original_context(self) -> None:
        predictor = LLMBlindPredictor(
            ScriptedRoleCaller([]), anonymous_aliases=("LEAKME",)
        )

        with self.assertRaisesRegex(ValidationError, "identity alias leaked"):
            predictor.reflect(
                {"summary": "LEAKME disclosed"},
                BlindPrediction(
                    is_surge=False,
                    candidate_judgment=CandidateJudgment.UNLIKELY,
                    magnitude=None,
                    confidence=ConfidenceLevel.LOW,
                    key_reasons=("limited evidence",),
                    uncertainties=(),
                    session_id="anonymous-session",
                ),
                GroundTruth(1.2),
            )

    def test_v12_correct_posthoc_requires_specific_decision_driver(self) -> None:
        empty = {
            "prediction_outcome": {"correct": True},
            "decision_drivers": [],
            "why_prediction_failed": [],
            "misleading_signals": [],
            "ignored_evidence": [],
            "missing_information": [],
            "plan_issues": [],
        }
        corrected = json.loads(json.dumps(empty))
        corrected["decision_drivers"] = [
            "No expectation-changing catalyst was present in the supplied evidence."
        ]
        caller = ScriptedRoleCaller([empty, corrected])
        predictor = LLMBlindPredictor(caller)

        reflection = predictor.reflect(
            {"summary": "No expectation-changing catalyst was present."},
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.UNLIKELY,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("no catalyst",),
                uncertainties=(),
                session_id="anonymous-session",
            ),
            GroundTruth(1.2),
        )

        self.assertEqual(
            caller.stages,
            [
                "blind_predictor_posthoc_reflect",
                "blind_predictor_posthoc_reflect_correction",
            ],
        )
        self.assertIn(
            "all-empty correct reflection",
            caller.calls[1]["payload"]["validation_error"],
        )
        self.assertEqual(reflection.value.decision_drivers, tuple(corrected["decision_drivers"]))

    def test_v30_incorrect_posthoc_requires_specific_failure_attribution(self) -> None:
        empty = {
            "prediction_outcome": {"correct": False},
            "decision_drivers": [],
            "why_prediction_failed": [],
            "misleading_signals": [],
            "ignored_evidence": [],
            "missing_information": [],
            "plan_issues": [],
        }
        corrected = json.loads(json.dumps(empty))
        corrected["misleading_signals"] = [
            "The 52-week high and low drawdown were momentum evidence, not a "
            "source-backed catalyst for a six-month doubling."
        ]
        caller = ScriptedRoleCaller([empty, corrected])
        predictor = LLMBlindPredictor(caller)

        reflection = predictor.reflect(
            {"summary": "Momentum was positive but no doubling catalyst was supplied."},
            BlindPrediction(
                is_surge=True,
                candidate_judgment=CandidateJudgment.POSSIBLE,
                magnitude=MagnitudeClass.TWO_TO_THREE,
                confidence=ConfidenceLevel.MEDIUM,
                key_reasons=("strong momentum",),
                uncertainties=("no catalyst",),
                session_id="anonymous-session",
            ),
            GroundTruth(1.5),
        )

        self.assertEqual(
            caller.stages,
            [
                "blind_predictor_posthoc_reflect",
                "blind_predictor_posthoc_reflect_correction",
            ],
        )
        self.assertIn(
            "all-empty incorrect reflection",
            caller.calls[1]["payload"]["validation_error"],
        )
        self.assertEqual(
            reflection.value.misleading_signals,
            tuple(corrected["misleading_signals"]),
        )
        self.assertIn(
            "at least one of why_prediction_failed",
            caller.calls[0]["system_prompt"],
        )

    def test_plan_critic_receives_compact_anonymous_trajectories(self) -> None:
        class Artifact:
            def __init__(self, value):
                self.value = value

            def to_dict(self):
                return self.value

        caller = ScriptedRoleCaller(
            [
                {
                    "successful_patterns": ["well grounded judgment"],
                    "failed_patterns": [],
                    "repeated_failure_modes": [],
                    "misleading_signals": [],
                    "missing_information_needs": [],
                    "next_explorations": [],
                }
            ]
        )

        reflection = LLMPlanCritic(caller).critique(
            plan=default_information_plan(),
            trajectories=(
                Artifact(
                    {
                        "case_id": "cik_0000000001:20250101",
                        "company_id": "identity-must-not-reach-critic",
                        "basic_info_bundle": {
                            "exact_text": "raw-info-must-not-reach-critic"
                        },
                        "final_context": {
                            "exact_span": "source-span-must-not-reach-critic"
                        },
                        "prediction": {
                            "is_surge": True,
                            "candidate_judgment": "possible",
                        },
                        "ground_truth": {
                            "is_surge": True,
                            "realized_max_multiple": 2.2,
                        },
                        "candidate_judgment_feedback": {
                            "candidate_judgment": "possible",
                            "predicted_binary_label": "surge",
                            "true_binary_label": "surge",
                            "binary_correct": True,
                            "assessment": "correct_positive_conservative",
                            "reflection_guidance": "inspect underweighted evidence",
                        },
                        "signal_rounds": [
                            {
                                "information_needs": ["growth durability"],
                                "selected_signals": ["revenue_growth_yoy:v1"],
                                "batch": {
                                    "results": [
                                        {
                                            "signal_id": "revenue_growth_yoy",
                                            "version": 1,
                                            "state": {"value": "positive"},
                                            "interpretation": {"summary": "accelerating"},
                                            "status": {"coverage": "sufficient"},
                                            "evidence": {
                                                "supporting": [
                                                    {"exact_span": "must be omitted"}
                                                ],
                                                "counter": [],
                                            },
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ),
            ),
            metrics=Artifact({"binary_f1": 0.75}),
            parent_comparisons=(
                {
                    "source_scope": "historical_seed",
                    "same_evaluation_snapshot": True,
                    "plan_diff": {
                        "basic_info_requests_removed": [
                            {"request_id": "recent_annual_filing"}
                        ]
                    },
                    "metric_delta": {
                        "binary_f1": -0.19,
                        "confusion": {
                            "true_positive": -3,
                            "false_negative": 3,
                        },
                    },
                },
            ),
        )

        self.assertEqual(
            reflection.successful_patterns, ("well grounded judgment",)
        )
        prompt = caller.calls[0]["system_prompt"]
        self.assertIn("saved predictions", prompt)
        self.assertNotIn("token probability", prompt)
        trajectories = caller.calls[0]["payload"]["trajectories"]
        self.assertNotIn("decision_confidence_feedback", trajectories[0])
        self.assertEqual(
            trajectories[0]["candidate_judgment_feedback"]["assessment"],
            "correct_positive_conservative",
        )
        self.assertIn("Combined Binary F1", prompt)
        self.assertIn("same_evaluation_snapshot", prompt)
        comparisons = caller.calls[0]["payload"]["parent_comparisons"]
        self.assertEqual(
            comparisons[0]["plan_diff"]["basic_info_requests_removed"][0][
                "request_id"
            ],
            "recent_annual_filing",
        )
        self.assertNotIn("company_id", json.dumps(comparisons))
        self.assertNotIn("ground_truth", json.dumps(comparisons))
        self.assertEqual(trajectories[0]["case_index"], 1)
        self.assertNotIn("case_id", trajectories[0])
        self.assertNotIn("company_id", trajectories[0])
        self.assertNotIn("basic_info_bundle", trajectories[0])
        self.assertNotIn("final_context", trajectories[0])
        self.assertEqual(
            trajectories[0]["signal_rounds"][0]["signal_results"][0][
                "evidence_counts"
            ],
            {"supporting": 1, "counter": 0},
        )
        rendered = json.dumps(trajectories)
        self.assertNotIn("raw-info-must-not-reach-critic", rendered)
        self.assertNotIn("source-span-must-not-reach-critic", rendered)
        self.assertNotIn("must be omitted", rendered)

    def test_round_reflector_receives_compact_records_and_parent_comparisons(
        self,
    ) -> None:
        class Artifact:
            def __init__(self, value):
                self.value = value

            def to_dict(self):
                return self.value

        class Evaluation:
            evaluation_stage = "round"
            n_cases = 24
            dataset_snapshot_ids = (SHA_A,)
            metrics_by_cohort = {
                "combined": Artifact({"binary_f1": 0.5})
            }

        class Record:
            round_id = 1
            metrics = Artifact({"binary_f1": 0.5})
            reflection = Artifact({"failed_patterns": ["lost financial evidence"]})
            signal_usage = {"revenue_growth_yoy:v1": {"retrieved": 24}}
            fitness = Artifact({"eligible": True})
            evaluation = Evaluation()

            def __init__(self, plan_id):
                self.plan_id = plan_id
                self.plan = InformationPlan(
                    plan_id=plan_id,
                    parent_ids=("historical_seed_parent",),
                    basic_info_policy=default_information_plan().basic_info_policy,
                    initial_research_skill="fixture init",
                    reflection_skill="fixture reflect",
                    analysis_prompt="fixture analyse",
                )

            def to_dict(self):
                return {
                    "trajectories": [
                        {
                            "company_id": "identity-must-not-reach-round-reflector",
                            "ground_truth": {"is_surge": True},
                            "basic_info_bundle": "raw-info-must-not-reach-round-reflector",
                        }
                    ]
                }

        caller = ScriptedRoleCaller(
            [
                {
                    "round_id": 1,
                    "plan_level": {
                        "successful_patterns": [],
                        "failed_patterns": ["financial evidence was removed"],
                    },
                    "prediction_errors": {
                        "false_positive": [],
                        "false_negative": ["positive recall regressed"],
                    },
                    "signal_observations": {
                        "useful": [],
                        "suspicious": [],
                        "missing_capabilities": [],
                    },
                    "search_implications": ["restore financial evidence"],
                    "evidence_refs": ["child_plan"],
                }
            ]
        )

        result = LLMRoundReflector(caller).reflect(
            round_id=1,
            records=(Record("child_plan"), Record("sibling_plan")),
            prior="reflect over the round",
            parent_comparisons_by_plan_id={
                "child_plan": (
                    {
                        "same_evaluation_snapshot": True,
                        "plan_diff": {
                            "basic_info_requests_removed": [
                                {"request_id": "recent_annual_filing"}
                            ]
                        },
                        "metric_delta": {"binary_f1": -0.19},
                    },
                )
            },
        )

        self.assertEqual(result.evidence_refs, ("child_plan",))
        self.assertIn("horizontal insight", caller.calls[0]["system_prompt"])
        payload = caller.calls[0]["payload"]
        self.assertIn("parent_comparisons_by_plan_id", payload)
        self.assertNotIn("trajectories", payload["records"][0])
        self.assertNotIn("case_ids", json.dumps(payload["records"]))
        rendered = json.dumps(payload)
        self.assertNotIn("identity-must-not-reach-round-reflector", rendered)
        self.assertNotIn("raw-info-must-not-reach-round-reflector", rendered)

    def test_round_reflector_skips_single_record_horizontal_paraphrase(self) -> None:
        record = SimpleNamespace(plan_id="only_plan")
        caller = ScriptedRoleCaller([])

        result = LLMRoundReflector(caller).reflect(
            round_id=1,
            records=(record,),
            prior="reflect over the round",
            parent_comparisons_by_plan_id={"only_plan": ()},
        )

        self.assertEqual(result.round_id, 1)
        self.assertEqual(result.evidence_refs, ("only_plan",))
        self.assertEqual(result.plan_reflections, ())
        self.assertEqual(caller.calls, [])

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
                            "requests": [
                                {
                                    "request_id": "recent_market_backbone",
                                    "description": "Read recent point-in-time price and volume.",
                                    "source_types": ["market_data"],
                                    "lookback_days": 45,
                                    "max_documents": 1,
                                }
                            ]
                        },
                        "initial_research_skill": (
                            "Form a falsifiable hypothesis and list unresolved "
                            "information needs."
                        ),
                    },
                    "H_reflect": {
                        "reflection_skill": (
                            "Track support and contradiction, then continue for the "
                            "next need or finalize."
                        )
                    },
                    "H_analyse": {
                        "analysis_prompt": (
                            "Weigh supporting and counter evidence while exposing "
                            "uncertainty."
                        )
                    },
                    "fixed_prior": "echoed input",
                    "meta_info": [],
                },
                {
                    "plan_id": "plan_manual_v2_slot_2",
                    "parent_ids": ["another_invented_parent"],
                    "basic_info_policy": {
                        "requests": [
                            {
                                "request_id": "recent_market_backbone",
                                "description": "Read recent point-in-time price and volume.",
                                "source_types": ["market_data"],
                                "lookback_days": 45,
                                "max_documents": 1,
                            }
                        ]
                    },
                    "initial_research_skill": (
                        "Test a distinct hypothesis and list unresolved information "
                        "needs."
                    ),
                    "reflection_skill": (
                        "Track disconfirming evidence first, then continue for the "
                        "next need or finalize."
                    ),
                    "analysis_prompt": (
                        "Weigh counter evidence while preserving uncertainty."
                    ),
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
            "recent_market_backbone",
        )
        self.assertEqual(first.parent_ids, ("plan_manual_v1",))
        self.assertEqual(caller.calls[0]["temperature"], 1.0)
        self.assertIn(
            "four top-level keys: B, H_init, H_reflect, and H_analyse",
            str(caller.calls[0]["system_prompt"]),
        )
        self.assertEqual(
            caller.calls[0]["payload"]["proposal_context"]["proposal_slot"],
            {
                "round_id": 1,
                "candidate_index": 1,
                "candidate_count": 2,
                "proposal_attempt": 1,
            },
        )
        self.assertEqual(
            caller.calls[1]["payload"]["proposal_context"]["proposal_slot"],
            {
                "round_id": 1,
                "candidate_index": 2,
                "candidate_count": 2,
                "proposal_attempt": 1,
            },
        )
        self.assertIn(
            "four top-level keys: B, H_init, H_reflect, and H_analyse",
            str(caller.calls[1]["system_prompt"]),
        )
        self.assertNotIn("forbidden_plan_ids", str(caller.calls[1]["system_prompt"]))
        self.assertEqual(second.plan_id, "plan_r0001_c02")

    def test_plan_proposer_repairs_exact_parent_copy_with_change_focus(self) -> None:
        parent = default_information_plan()
        duplicate = {
            "B": parent.basic_info_policy.to_dict(),
            "H_init": parent.initial_research_skill,
            "H_reflect": parent.reflection_skill,
            "H_analyse": parent.analysis_prompt,
        }
        repaired = json.loads(json.dumps(duplicate))
        repaired["H_reflect"] = (
            "Test the strongest disconfirming evidence, then continue for the next "
            "need or finalize."
        )
        caller = ScriptedRoleCaller([duplicate, repaired])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=2,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(plan.reflection_skill, repaired["H_reflect"])
        self.assertEqual(
            caller.stages,
            ["information_plan_propose", "information_plan_propose_correction"],
        )
        constraints = caller.calls[0]["payload"]["proposal_context"][
            "proposal_constraints"
        ]
        self.assertTrue(constraints["must_differ_from_every_parent"])
        self.assertIn("H_reflect", constraints["required_change_focus"])
        correction = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("exactly duplicates", correction["validation_error"])
        self.assertEqual(correction["invalid_output"], duplicate)

    def test_v10_proposer_allows_explicit_probability_prohibition(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v10_proposer_semantics_and_focus.json"
            ).read_text(encoding="utf-8")
        )
        parent = default_information_plan()
        for analysis_prompt in fixture["false_positive_analysis_prompts"]:
            output = {
                "B": parent.basic_info_policy.to_dict(),
                "H_init": parent.initial_research_skill,
                "H_reflect": parent.reflection_skill,
                "H_analyse": analysis_prompt,
            }
            caller = ScriptedRoleCaller([output])

            plan = LLMInformationPlanProposer(caller).propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=3,
                forbidden_plan_ids=(),
                parents=(parent,),
                meta_info=(),
                prior="fixed H_P",
            )

            self.assertEqual(plan.analysis_prompt, analysis_prompt)
            self.assertEqual(caller.stages, ["information_plan_propose"])

    def test_v14_fixed_threshold_reference_is_not_a_semantics_redefinition(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v14_fixed_threshold_reference.json"
            ).read_text(encoding="utf-8")
        )

        for text_value in fixture["allowed"]:
            with self.subTest(allowed=text_value):
                self.assertEqual(
                    evolution_runtime_module._reject_fixed_semantics_redefinition(
                        {"decision_drivers": [text_value]}
                    ),
                    {"decision_drivers": [text_value]},
                )
        for text_value in fixture["rejected"]:
            with self.subTest(rejected=text_value):
                with self.assertRaisesRegex(
                    ValidationError, "redefine fixed Predictor semantics"
                ):
                    evolution_runtime_module._reject_fixed_semantics_redefinition(
                        {"decision_drivers": [text_value]}
                    )

    def test_v10_proposer_corrects_change_outside_required_focus(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v10_proposer_semantics_and_focus.json"
            ).read_text(encoding="utf-8")
        )
        unchanged = fixture["unchanged_focus_fields"]
        parent = InformationPlan.from_dict(
            {
                "plan_id": "historical_parent",
                "parent_ids": [],
                "basic_info_policy": unchanged["B"],
                "initial_research_skill": unchanged["H_init"],
                "reflection_skill": default_information_plan().reflection_skill,
                "analysis_prompt": fixture["parent_analysis_prompt"],
            }
        )
        wrong_focus = {
            "B": unchanged["B"],
            "H_init": unchanged["H_init"],
            "H_reflect": parent.reflection_skill,
            "H_analyse": fixture["wrong_focus_analysis_prompt"],
        }
        corrected = json.loads(json.dumps(wrong_focus))
        corrected["H_init"] += " Identify the strongest unsupported assumption."
        caller = ScriptedRoleCaller([wrong_focus, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(plan.initial_research_skill, corrected["H_init"])
        self.assertIn(
            "B/H_init is unchanged",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )

    def test_plan_proposer_receives_complete_additive_outcome_aware_fifo_entry(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "basic_info_policy": {
                        "requests": [
                            {
                                "request_id": "recent_market_backbone",
                                "description": "Read recent price and volume.",
                                "source_types": ["market_data"],
                                "lookback_days": 45,
                                "max_documents": 1,
                            }
                        ]
                    },
                    "initial_research_skill": (
                        "Test the preserved hypothesis and list unresolved "
                        "information needs."
                    ),
                    "reflection_skill": (
                        "Inspect contradiction before finalizing or continuing for "
                        "the next need."
                    ),
                    "analysis_prompt": (
                        "Weigh supporting and counter evidence while preserving "
                        "uncertainty."
                    ),
                }
            ]
        )
        parent = default_information_plan()
        metrics = PlanMetrics(
            binary_precision=1.0,
            binary_recall=1.0,
            binary_f1=1.0,
            magnitude_accuracy=1.0,
            magnitude_macro_f1=1 / 3,
            true_positive=1,
            false_positive=0,
            true_negative=0,
            false_negative=0,
            sample_count=1,
        )
        case_reflection = CaseReflectionEvidence(
            case_index=1,
            stop_reason=RuntimeStopReason.FINALIZED,
            termination_trigger=None,
            candidate_judgment_feedback=candidate_judgment_feedback(
                BlindPrediction(
                    is_surge=True,
                    candidate_judgment=CandidateJudgment.POSSIBLE,
                    magnitude=MagnitudeClass.TWO_TO_THREE,
                    confidence=ConfidenceLevel.MEDIUM,
                    key_reasons=("source-backed opportunity",),
                    uncertainties=("magnitude remains uncertain",),
                    session_id="anonymous-session",
                ),
                GroundTruth(2.2),
            ),
            self_reflection=PredictionSelfReflection(
                correct=True,
                ignored_evidence=("annual filing evidence was underweighted",),
            ),
        )
        plan_reflection = PlanMetaReflection(
            plan=parent,
            metrics=metrics,
            metrics_by_cohort={},
            evaluation_snapshot_ids=(),
            fitness=FitnessEligibility(
                eligible=True,
                reasons=(),
                expected_case_count=1,
                valid_case_count=1,
                evidence_covered_count=1,
                predicted_positive_count=1,
                true_positive_count=1,
            ),
            signal_usage={},
            original_case_reflections=(case_reflection,),
            vertical_plan_reflection=PlanReflection(
                next_explorations=("restore annual filing evidence",),
            ),
        )
        meta_entry = RoundMetaEntry(
            round_id=1,
            plan_reflections=(plan_reflection,),
            search_implications=("compare restored filing evidence",),
            evidence_refs=(parent.plan_id,),
        )

        proposed = LLMInformationPlanProposer(caller).propose(
            round_id=2,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(meta_entry,),
            prior="fixed H_P",
        )

        self.assertEqual(proposed.plan_id, "plan_r0002_c01")
        meta_payload = caller.calls[0]["payload"]["proposal_context"]["meta_info"][
            0
        ]
        original = meta_payload["representative_details"][0][
            "representative_cases"
        ][0]
        self.assertEqual(original["assessment"], "correct_positive_conservative")
        self.assertEqual(
            original["self_reflection"]["ignored_evidence"],
            ["annual filing evidence was underweighted"],
        )
        self.assertEqual(
            meta_payload["representative_details"][0]["vertical"][
                "next_explorations"
            ],
            ["restore annual filing evidence"],
        )
        self.assertEqual(
            meta_payload["aggregate"]["search_implications"],
            ["compare restored filing evidence"],
        )
        rendered = json.dumps(meta_payload)
        self.assertNotIn('"case_id"', rendered)
        self.assertNotIn('"company_id"', rendered)
        self.assertIn("as a replacement", caller.calls[0]["system_prompt"])

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

    def test_llm_signal_batch_repairs_versioned_inner_identity_with_exact_mapping(
        self,
    ) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v8_signal_batch_versioned_inner_identity.json"
            ).read_text(encoding="utf-8")
        )
        invalid = {
            "results": [
                {
                    "signal_ref": fixture["signal_ref"],
                    "result": fixture["invalid_result"],
                }
            ]
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["results"][0]["result"]["signal_id"] = fixture[
            "expected_signal_id"
        ]
        caller = ScriptedRoleCaller([invalid, corrected])
        spec = SignalSpec(
            signal_id=fixture["expected_signal_id"],
            version=fixture["expected_version"],
            category="management",
            description="Detect explicit management-guidance acceleration.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="guidance_acceleration.md",
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (),
            "Compare current with prior explicit guidance.",
            datetime(2025, 9, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(result.signal_id, fixture["expected_signal_id"])
        self.assertEqual(usage.llm_calls, 2)
        self.assertIn(
            "Output contract for SignalBatchResult",
            caller.calls[0]["system_prompt"],
        )
        self.assertNotIn(
            "Output contract for SignalResult:",
            caller.calls[0]["system_prompt"],
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertEqual(
            feedback["expected_result_identity"],
            {
                "signal_id": fixture["expected_signal_id"],
                "version": fixture["expected_version"],
            },
        )
        self.assertIn("without a version suffix", feedback["required_action"])
        self.assertIn("returned result.signal_id", feedback["validation_error"])

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
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("supporting evidence[0] exact span", feedback["validation_error"])
        self.assertNotIn("failed_output", feedback)
        self.assertIn("smallest set of unique quotes", feedback["required_action"])
        self.assertIn("multiple current/prior", feedback["required_action"])
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        initial_payload = json.dumps(
            caller.calls[0]["payload"], sort_keys=True, separators=(",", ":")
        )
        correction_payload = json.dumps(
            caller.calls[1]["payload"], sort_keys=True, separators=(",", ":")
        )
        self.assertTrue(correction_payload.startswith(initial_payload[:-1] + ","))
        self.assertNotIn("validation_feedback", caller.calls[0]["payload"])
        self.assertEqual(usage.llm_calls, 2)
        self.assertAlmostEqual(usage.cost, 0.02)

    def test_v69_guidance_signal_rejects_unrelated_sale_leaseback_evidence(
        self,
    ) -> None:
        as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        exact_span = (
            "In December 2022, the Company completed the sale-leaseback of "
            "Encore Boston Harbor for $1.70 billion and recorded a $182 million gain."
        )
        document = RawInfoDocument.create(
            document_id="filing-sale-leaseback",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content=exact_span,
        )
        invalid = {
            "signal_id": "guidance_acceleration",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {
                "summary": "The transaction materially strengthened guidance."
            },
            "evidence": {
                "supporting": [
                    {
                        "document_id": document.document_id,
                        "exact_span": exact_span,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        corrected = {
            "signal_id": "guidance_acceleration",
            "version": 1,
            "state": {"value": "unavailable", "confidence": 0.0},
            "interpretation": {
                "summary": "Visible evidence did not name management guidance."
            },
            "evidence": {"supporting": [], "counter": []},
            "status": {"coverage": "unavailable"},
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        spec = SignalSpec(
            signal_id="guidance_acceleration",
            version=1,
            category="management",
            description="Detect explicit management-guidance acceleration.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="guidance_acceleration.md",
            parameters={
                "result_required_evidence_phrases": [
                    "guidance",
                    "outlook",
                    "forecast",
                    "we expect",
                ]
            },
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Compare current with prior explicit guidance.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("guidance_acceleration:v1", feedback["validation_error"])
        self.assertIn(
            "result_required_evidence_phrases", feedback["validation_error"]
        )
        self.assertIn("Return unavailable", feedback["validation_error"])

    def test_v69_guidance_signal_accepts_explicit_guidance_evidence(self) -> None:
        as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        exact_span = (
            "Management raised 2025 production guidance and now expects all-in "
            "sustaining cost of $1,500 per ounce."
        )
        document = RawInfoDocument.create(
            document_id="filing-guidance",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content=exact_span,
        )
        value = {
            "signal_id": "guidance_acceleration",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "Management raised 2025 guidance."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": document.document_id,
                        "exact_span": exact_span,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        caller = ScriptedRoleCaller([value])
        spec = SignalSpec(
            signal_id="guidance_acceleration",
            version=1,
            category="management",
            description="Detect explicit management-guidance acceleration.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="guidance_acceleration.md",
            parameters={"result_required_evidence_phrases": ["guidance"]},
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Compare current with prior explicit guidance.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(usage.llm_calls, 1)

    def test_v70_customer_signal_rejects_distribution_channels_as_customers(
        self,
    ) -> None:
        as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        exact_span = (
            "For NNA, we have strength in all three channels. It is not just "
            "one channel."
        )
        document = RawInfoDocument.create(
            document_id="transcript-channels",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=as_of,
            available_at=as_of,
            content=exact_span,
        )
        invalid = {
            "signal_id": "customer_concentration",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {
                "summary": "Strength across three channels proves diversified customers."
            },
            "evidence": {
                "supporting": [
                    {
                        "document_id": document.document_id,
                        "exact_span": exact_span,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        corrected = {
            "signal_id": "customer_concentration",
            "version": 1,
            "state": {"value": "unavailable", "confidence": 0.0},
            "interpretation": {
                "summary": "The cited excerpt names channels, not customers."
            },
            "evidence": {"supporting": [], "counter": []},
            "status": {"coverage": "unavailable"},
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        spec = SignalSpec(
            signal_id="customer_concentration",
            version=1,
            category="risks",
            description="Judge dependence on one customer.",
            execution_type=SignalExecutionType.LLM,
            source_types=("earnings_call",),
            skill_file="customer_concentration.md",
            parameters={
                "result_required_evidence_phrases": [
                    "customer",
                    "client",
                    "buyer",
                    "offtake",
                    "backlog",
                    "order",
                    "account",
                    "program",
                ]
            },
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Measure customer concentration, not channel mix.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("customer_concentration:v1", feedback["validation_error"])
        self.assertIn(
            "result_required_evidence_phrases", feedback["validation_error"]
        )

    def test_llm_signal_runner_repairs_unavailable_with_placeholder_evidence(
        self,
    ) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Routine filing cover-page text.",
        )
        invalid_result = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "unavailable", "confidence": 0.5},
            "interpretation": {"summary": "No usable source evidence."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-1",
                        "exact_span": "Routine filing cover-page text.",
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "unavailable"},
        }
        corrected = json.loads(json.dumps(invalid_result))
        corrected["evidence"]["supporting"] = []
        caller = ScriptedRoleCaller([invalid_result, corrected])
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
        self.assertEqual(result.supporting_evidence, ())
        self.assertEqual(len(caller.calls), 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("cannot carry evidence", feedback["validation_error"])
        self.assertIn("corrected result", feedback["required_action"])
        self.assertIn("only correction attempt", caller.calls[0]["system_prompt"])
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertEqual(usage.llm_calls, 2)

    def test_llm_signal_runner_canonicalizes_unique_case_only_span(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="The customer entered volume deployment.",
        )
        value = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "The pilot reached volume deployment."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-1",
                        "exact_span": "the customer entered volume deployment.",
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        caller = ScriptedRoleCaller([value])
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

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            result.supporting_evidence[0].exact_span,
            "The customer entered volume deployment.",
        )
        self.assertEqual(usage.llm_calls, 1)

    def test_llm_signal_runner_projects_large_raw_info_to_exact_bounded_spans(
        self,
    ) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        target = "The customer entered repeatable scaled volume deployment."
        first = RawInfoDocument.create(
            document_id="filing-large",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content=("Routine governance disclosure. " * 8_000) + target,
        )
        second = RawInfoDocument.create(
            document_id="announcement-large",
            company_id="issuer-1",
            source_type="company_announcement",
            published_at=as_of,
            available_at=as_of,
            content="Certification roadmap update. " * 8_000,
        )
        value = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "Commercial deployment is evidenced."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-large",
                        "exact_span": target,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        caller = ScriptedRoleCaller([value])
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing", "company_announcement"),
            skill_file="pilot_to_volume.md",
        )

        result, _usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (first, second),
            "Find repeatable scaled sales and volume deployment evidence.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.POSITIVE)
        payload = caller.calls[0]["payload"]
        projected = payload["source_projection"]
        self.assertIn("filing-large", {item["document_id"] for item in projected})
        self.assertLess(len(json.dumps(payload)), 48_000)
        self.assertLessEqual(
            sum(len(item["exact_text"]) for item in projected),
            evolution_runtime_module.MAX_LLM_SIGNAL_CONTEXT_CHARS,
        )
        visible_text = ""
        for item in projected:
            self.assertNotIn("content", item)
            self.assertNotIn("metadata", item)
            self.assertIn("projection_id", item)
            visible_text += item["exact_text"]
        self.assertIn(target, visible_text)

    def test_llm_signal_runner_budget_trims_without_losing_each_signal_minimum(
        self,
    ) -> None:
        class BudgetAwareCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def estimate_json_request_tokens(self, **kwargs) -> int:
                source_characters = sum(
                    len(item["exact_text"])
                    for item in kwargs["payload"]["source_projection"]
                )
                return int(kwargs["max_output_tokens"]) + 500 + source_characters

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                return (
                    {
                        "results": [
                            {
                                "signal_ref": item["signal_ref"],
                                "result": {
                                    "signal_id": item["signal_spec"]["signal_id"],
                                    "version": item["signal_spec"]["version"],
                                    "state": {
                                        "value": "unavailable",
                                        "confidence": 0.0,
                                    },
                                    "interpretation": {
                                        "summary": "Visible evidence was insufficient."
                                    },
                                    "evidence": {"supporting": [], "counter": []},
                                    "status": {"coverage": "unavailable"},
                                },
                            }
                            for item in kwargs["payload"]["signals"]
                        ]
                    },
                    AgentUsage(llm_calls=1, tokens=50, cost=0.01),
                )

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        inputs = tuple(
            LLMSignalBatchInput(
                SignalSpec(
                    signal_id=signal_id,
                    version=1,
                    category="catalysts",
                    description=description,
                    execution_type=SignalExecutionType.LLM,
                    source_types=("filing",),
                    skill_file=f"{signal_id}.md",
                ),
                (
                    RawInfoDocument.create(
                        document_id=f"{signal_id}-document",
                        company_id="issuer-1",
                        source_type="filing",
                        published_at=as_of,
                        available_at=as_of,
                        content=target + (" Routine disclosure." * 1_500),
                    ),
                ),
                f"Extract {description}",
            )
            for signal_id, description, target in (
                (
                    "guidance_change",
                    "management guidance change",
                    "Management raised annual guidance.",
                ),
                (
                    "customer_order",
                    "customer order quality",
                    "A customer signed a repeat production order.",
                ),
            )
        )
        caller = BudgetAwareCaller()
        runner = StructuredLLMSignalRunner(caller)
        runner.set_request_token_budget(8_500)

        results, usage = runner.execute_many(inputs, as_of)

        self.assertEqual(set(results), {"guidance_change:v1", "customer_order:v1"})
        self.assertEqual(usage.llm_calls, 1)
        payload = caller.calls[0]["payload"]
        self.assertTrue(payload["context_contract"]["budget_trimmed"])
        self.assertLess(
            payload["context_contract"]["visible_source_characters"],
            evolution_runtime_module.MAX_LLM_SIGNAL_CONTEXT_CHARS,
        )
        self.assertTrue(
            all(item["eligible_projection_ids"] for item in payload["signals"])
        )
        visible = "\n".join(
            item["exact_text"] for item in payload["source_projection"]
        )
        self.assertIn("Management raised annual guidance.", visible)
        self.assertIn("A customer signed a repeat production order.", visible)
        self.assertLessEqual(
            caller.estimate_json_request_tokens(
                system_prompt=caller.calls[0]["system_prompt"],
                payload=payload,
                allow_outcomes=False,
                max_output_tokens=4_000,
            ),
            8_500,
        )

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

    def test_v6_routing_normalizes_format_and_caps_four_with_two_llm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            snapshot = registry.freeze()
            raw = []
            for spec in snapshot.specs:
                raw.append(
                    {
                        "signal_ref": spec.ref,
                        "reason_code": "combine_evidence",
                        "selection_reason": "x" * 400,
                        "applicability_hypothesis": "y" * 400,
                        "expected_role": "primary",
                        "context_tags": [
                            "News Rich",
                            "news_rich",
                            "General",
                            "Scaling",
                            "Small Cap",
                        ],
                        "target_need_indices": [],
                        "answer_scope": None,
                        "residual_need": None,
                    }
                )
            caller = ScriptedRoleCaller([{"selections": raw}])

            selected = LLMSignalRetrievalAgent(caller).select(
                ("inspect everything",), snapshot, {}
            ).value

            self.assertLessEqual(len(selected), 4)
            by_ref = {spec.ref: spec for spec in snapshot.specs}
            self.assertLessEqual(
                sum(
                    by_ref[item.signal_ref].execution_type
                    is SignalExecutionType.LLM
                    for item in selected
                ),
                2,
            )
            self.assertTrue(all(len(item.selection_reason) == 240 for item in selected))
            self.assertTrue(all(len(item.context_tags) <= 4 for item in selected))
            self.assertTrue(all(len(set(item.context_tags)) == len(item.context_tags) for item in selected))

    def test_v17_routing_drops_visible_categories_used_as_context_tags(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/v17_signal_category_tags.json"
            ).read_text()
        )
        for item in fixture["selections"]:
            item["answer_scope"] = None
            item["residual_need"] = None
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller([fixture])

            selected = LLMSignalRetrievalAgent(caller).select(
                ("identify catalysts and risks",), registry.freeze(), {}
            ).value

            self.assertEqual(len(caller.calls), 1)
            self.assertEqual(
                tuple(item.signal_ref for item in selected),
                ("financing_listing_action:v1",),
            )
            self.assertEqual(
                selected[0].context_tags,
                ("capital_intensive", "mature_operations", "large_cap"),
            )

    def test_v6_initialize_canonicalizes_unique_basic_projection_reference(self) -> None:
        def state(projection_id: str) -> dict[str, Any]:
            return {
                "hypotheses": ["growth may accelerate"],
                "current_beliefs": [],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": "Revenue guidance increased.",
                        "projection_id": projection_id,
                        "exact_text": "guidance increased",
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["confirm customer demand"],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller([state("projection_unknown")])
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": "projection_ok",
                            "exact_text": "Management said guidance increased this year.",
                        }
                    ]
                }
            ]
        }

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            initialized.value.to_dict()["supporting_evidence"][0]["projection_id"],
            "projection_ok",
        )

    def test_v6_initialize_corrects_non_contiguous_basic_literal_once(self) -> None:
        def state(exact_text: str) -> dict[str, Any]:
            return {
                "hypotheses": ["growth may accelerate"],
                "current_beliefs": [],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": "Revenue increased.",
                        "projection_id": "projection_market",
                        "exact_text": exact_text,
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["confirm customer demand"],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller(
            [
                state('{"close":21.46}...{"close":24.37}'),
                state('{"close":21.46}'),
            ]
        )
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": "projection_market",
                            "exact_text": (
                                '[{"close":21.46},{"close":22.00},'
                                '{"close":24.37}]'
                            ),
                        }
                    ]
                }
            ]
        }

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(caller.calls), 2)
        correction_error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[0]", correction_error)
        self.assertIn("contiguous literal substring", correction_error)
        self.assertIn("without ellipses", correction_error)
        self.assertEqual(
            initialized.value.to_dict()["supporting_evidence"][0]["exact_text"],
            '{"close":21.46}',
        )

    def test_v15_initialize_explains_market_rows_and_requires_real_correction(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v15_initialize_market_citation.json"
            ).read_text()
        )

        def state(exact_text: str) -> dict[str, Any]:
            return {
                "hypotheses": ["repricing depends on issuer-specific evidence"],
                "current_beliefs": [],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": fixture["claim"],
                        "projection_id": fixture["projection_id"],
                        "exact_text": exact_text,
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["confirm issuer-specific catalysts"],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller(
            [
                state(fixture["invalid_exact_text"]),
                state(fixture["valid_exact_text"]),
            ]
        )
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": fixture["projection_id"],
                            "exact_text": fixture["projection_text"],
                        }
                    ]
                }
            ]
        }

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(caller.calls), 2)
        initial_prompt = caller.calls[0]["system_prompt"]
        correction_prompt = caller.calls[1]["system_prompt"]
        self.assertEqual(initial_prompt, correction_prompt)
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        self.assertEqual(
            caller.calls[0]["payload"]["basic_info"],
            caller.calls[1]["payload"]["basic_info"],
        )
        self.assertEqual(
            caller.calls[0]["payload"]["initial_research_skill"],
            caller.calls[1]["payload"]["initial_research_skill"],
        )
        stable_prefix = json.dumps(
            {
                "basic_info": caller.calls[0]["payload"]["basic_info"],
                "initial_research_skill": caller.calls[0]["payload"][
                    "initial_research_skill"
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )[:-1] + ',"validation_feedback":'
        for call in caller.calls:
            rendered = json.dumps(
                call["payload"], sort_keys=True, separators=(",", ":")
            )
            self.assertTrue(rendered.startswith(stable_prefix))
        self.assertIn("evaluation definition, not an issuer statement", initial_prompt)
        self.assertIn("baseline date, or baseline price", initial_prompt)
        self.assertIn("future operating event outside the six-month horizon", initial_prompt)
        self.assertIn("within-horizon evidence or milestone", initial_prompt)
        self.assertIn("complete visible row", initial_prompt)
        self.assertIn("Returning the same rejected content", correction_prompt)
        self.assertIn(
            "contiguous literal substring",
            validation_error(caller.calls[1]),
        )
        self.assertEqual(
            initialized.value.supporting_evidence[0].exact_text,
            fixture["valid_exact_text"],
        )

    def test_v74_initialize_names_closest_visible_literal_window(self) -> None:
        projection_text = (
            "SFIX Q1 Loss Narrower Than Expected, Active Clients Decline Y/Y "
            "Stitch Fix, Inc. (SFIX) reported first-quarter fiscal 2025 results, "
            "with both top and bottom lines beating consensus estimates, despite "
            "a year-over-year decline in active clients and revenue. The company's "
            "adjusted loss narrowed significantly."
        )
        invalid_literal = (
            "SFIX reported first-quarter fiscal 2025 results, with both top and "
            "bottom lines beating consensus estimates, despite a year-over-year "
            "decline in active clients and revenue."
        )
        corrected_literal = (
            "Stitch Fix, Inc. (SFIX) reported first-quarter fiscal 2025 results, "
            "with both top and bottom lines beating consensus estimates, despite "
            "a year-over-year decline in active clients and revenue."
        )

        def state(literal: str) -> dict[str, Any]:
            return {
                "hypotheses": ["Revenue stabilization remains uncertain."],
                "current_beliefs": [literal],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": literal,
                        "projection_id": "projection_sfix",
                        "exact_text": literal,
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["Confirm active-client stabilization."],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller(
            [state(invalid_literal), state(corrected_literal)]
        )
        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_sfix",
                                "exact_text": projection_text,
                            }
                        ]
                    }
                ]
            },
        )

        error = validation_error(caller.calls[1])
        self.assertIn(f"invalid_exact_text={invalid_literal!r}", error)
        self.assertIn("occurrences_in_named_projection=0", error)
        self.assertIn("closest_visible_projection_window=", error)
        self.assertIn("Stitch Fix, Inc. (SFIX) reported", error)
        self.assertEqual(
            initialized.value.supporting_evidence[0].exact_text,
            corrected_literal,
        )

    def test_v20_initialize_aggregates_shape_and_quantity_feedback(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v20_initialize_layered_feedback.json"
            ).read_text(encoding="utf-8")
        )
        caller = ScriptedRoleCaller(
            [fixture["invalid_output"], fixture["corrected_output"]]
        )
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": fixture["projection_id"],
                            "exact_text": fixture["projection_text"],
                        }
                    ]
                }
            ]
        }

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(caller.calls), 2)
        error = validation_error(caller.calls[1])
        self.assertIn("unknown kind None", error)
        self.assertIn("numeric quantities", error)
        self.assertIn("42", error)
        self.assertIn("2027", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertGreaterEqual(feedback["obligation_count"], 2)
        obligations = feedback["obligations"]
        self.assertEqual(
            obligations[0]["must_change_paths"],
            ["supporting_evidence[0].kind"],
        )
        self.assertTrue(
            any(
                "supporting_evidence[0].claim" in item["must_change_paths"]
                for item in obligations
            )
        )
        self.assertIn(
            "Satisfy every validation_feedback.obligations row",
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(
            initialized.value.supporting_evidence[0].claim,
            fixture["corrected_claim"],
        )

    def test_v29_initialize_binds_quantitative_belief_to_exact_evidence_claim(self) -> None:
        cash_text = (
            "The company delivered record free cash flow in the second quarter "
            "of almost $650 million."
        )
        market_text = '{"as_of_date":"2025-09-29","adjusted_close":24.37}'
        cash_claim = "The company delivered almost $650 million of free cash flow in Q2."
        unsupported_belief = (
            "The company delivered almost $650 million of free cash flow in Q2 2025 "
            "and expects net cash by Q3 2025."
        )
        invalid = {
            "hypotheses": ["Cash generation may support the repricing thesis."],
            "current_beliefs": [unsupported_belief],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": cash_claim,
                    "projection_id": "projection_cash",
                    "exact_text": cash_text,
                },
                {
                    "kind": "basic_info",
                    "claim": "The adjusted close was $24.37 on 2025-09-29.",
                    "projection_id": "projection_market",
                    "exact_text": market_text,
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": ["Will cash generation persist?"],
            "next_information_needs": ["Check the balance-sheet outlook."],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [cash_claim]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_cash",
                                "exact_text": cash_text,
                            },
                            {
                                "projection_id": "projection_market",
                                "exact_text": market_text,
                            },
                        ]
                    }
                ]
            },
        )

        error = validation_error(caller.calls[1])
        self.assertIn("quantitative ResearchState assertions", error)
        self.assertIn("Numbers from unrelated claims do not count", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertTrue(
            all(item["must_change_paths"] for item in feedback["obligations"])
        )
        self.assertEqual(initialized.value.current_beliefs, (cash_claim,))
        self.assertIn(
            "must copy one accepted supporting_evidence claim byte-for-byte",
            caller.calls[0]["system_prompt"],
        )

    def test_v62_initialize_correction_keeps_precise_semantic_paths(self) -> None:
        claim = (
            "Kinross Gold reported strong Q2 2025 results with record operating "
            "margins and free cash flow."
        )
        corrected_claim = (
            "Kinross Gold reported strong second-quarter results with record "
            "operating margins and free cash flow."
        )
        exact_text = (
            "Our production in the second quarter was on plan, delivering 513,000 "
            "ounces at a cost of sales of $1,074 per ounce. Our strong production "
            "and cost management, combined with the gold price, resulted in record "
            "operating margins. As a result, we also delivered record free cash "
            "flow in the second quarter of almost $650 million and a first half "
            "total of just over $1 billion."
        )
        invalid = {
            "hypotheses": ["Strong operations may support a further repricing."],
            "current_beliefs": [claim],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": claim,
                    "projection_id": "projection_21113038b3f46eedb508d711",
                    "exact_text": exact_text,
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["Check the durability of operating margins."],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [corrected_claim]
        corrected["supporting_evidence"][0]["claim"] = corrected_claim
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": (
                                    "projection_21113038b3f46eedb508d711"
                                ),
                                "exact_text": exact_text,
                            }
                        ]
                    }
                ]
            },
        )

        error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[0]", error)
        self.assertIn('missing_quantity_groups=["2025"]', error)
        self.assertIn("linked_assertions=['current_beliefs[0]']", error)
        self.assertNotIn("returned invalid JSON fields", error)
        self.assertIn(
            "Preserve unrelated valid fields and items byte-for-byte",
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(initialized.value.current_beliefs, (corrected_claim,))
        self.assertEqual(
            initialized.value.supporting_evidence[0].claim,
            corrected_claim,
        )

    def test_v69_reflect_correction_names_overlong_claim_and_linked_belief(
        self,
    ) -> None:
        prior_claim = "The resort construction timeline remains the key uncertainty."
        prior_ref = ResearchEvidenceRef(
            kind="basic_info",
            claim=prior_claim,
            projection_id="projection-resort",
            exact_text="The resort remains under construction.",
        )
        previous = ResearchState(
            hypotheses=("The resort opening may support repricing.",),
            current_beliefs=(prior_claim,),
            supporting_evidence=(prior_ref,),
            open_questions=("Will construction remain on schedule?",),
            next_information_needs=("Check construction and funding updates.",),
        )
        overlong_claim = (
            "The 2022 sale-leaseback changed historical financing but does not "
            "by itself establish a current management-guidance revision. "
            + "This distinction must remain explicit in the active research state. "
            * 6
        )
        self.assertGreater(len(overlong_claim), 400)
        invalid = {
            "hypotheses": list(previous.hypotheses),
            "current_beliefs": [prior_claim, overlong_claim],
            "supporting_evidence": [
                prior_ref.to_dict(),
                {
                    "kind": "signal",
                    "claim": overlong_claim,
                    "signal_ref": "guidance_acceleration:v1",
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": list(previous.open_questions),
            "next_information_needs": list(previous.next_information_needs),
            "decision": "continue",
        }
        corrected_claim = (
            "The cited filing discusses a historical sale-leaseback, not a current "
            "management-guidance revision."
        )
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"][1] = corrected_claim
        corrected["supporting_evidence"][1]["claim"] = corrected_claim
        caller = ScriptedRoleCaller([invalid, corrected])
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=0.6,
            interpretation="The filing contains historical financing context.",
            supporting_evidence=(
                SignalEvidence(
                    document_id="filing-1",
                    exact_span="The Company completed a sale-leaseback in 2022.",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[1].claim", error)
        self.assertIn(f"length={len(overlong_claim)}", error)
        self.assertIn("linked_assertions=['current_beliefs[1]']", error)
        self.assertIn("at most 400 characters", error)
        self.assertIn(
            "Every supporting_evidence claim must contain 1-400 characters",
            caller.calls[0]["system_prompt"],
        )
        self.assertEqual(reflected.value.current_beliefs[1], corrected_claim)
        self.assertEqual(
            reflected.value.supporting_evidence[1].claim,
            corrected_claim,
        )

    def test_v72_initialize_aggregates_decision_frontier_limits(self) -> None:
        invalid = {
            "hypotheses": ["One material catalyst may support repricing."],
            "current_beliefs": [
                (
                    f"Source-summary item {index} repeats one visible projection "
                    "instead of retaining only a decision-relevant belief."
                )
                for index in range(52)
            ],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                f"Resolved source-summary question {index}." for index in range(5)
            ],
            "open_questions": [
                f"Open source-summary question {index}." for index in range(10)
            ],
            "next_information_needs": [
                f"Check one distinct material uncertainty {index}." for index in range(10)
            ],
            "decision": "continue",
        }
        corrected = {
            "hypotheses": ["One material catalyst may support repricing."],
            "current_beliefs": ["The catalyst remains unconfirmed."],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": ["Will the catalyst occur within six months?"],
            "next_information_needs": ["Check issuer evidence for the catalyst."],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        error = validation_error(caller.calls[1])
        self.assertIn("current_beliefs count=52", error)
        self.assertIn("open_questions count=10", error)
        self.assertIn("next_information_needs count=10", error)
        self.assertIn("combined ResearchState array count=", error)
        self.assertIn("ResearchState compact JSON size_bytes=", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        beliefs_obligation = next(
            item
            for item in feedback["obligations"]
            if "current_beliefs count=52" in item["instruction"]
        )
        self.assertEqual(
            beliefs_obligation["must_change_paths"], ["current_beliefs"]
        )
        total_obligation = next(
            item
            for item in feedback["obligations"]
            if "combined ResearchState array count=" in item["instruction"]
        )
        self.assertEqual(total_obligation["minimum_removed_items"], 54)
        self.assertEqual(total_obligation["current_total_items"], 78)
        self.assertEqual(total_obligation["maximum_total_items"], 24)
        self.assertEqual(
            total_obligation["must_reduce_any_of_paths"],
            [
                "hypotheses",
                "current_beliefs",
                "resolved_questions",
                "open_questions",
                "next_information_needs",
            ],
        )
        self.assertIn(
            "sum the lengths of every returned array",
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(
            caller.calls[0]["system_prompt"],
            caller.calls[1]["system_prompt"],
        )
        self.assertIn(
            "compact decision frontier, not a summary",
            caller.calls[0]["system_prompt"],
        )
        self.assertIn(
            "all arrays combined contain at most 24 items",
            caller.calls[0]["system_prompt"],
        )
        self.assertEqual(
            initialized.value.current_beliefs,
            ("The catalyst remains unconfirmed.",),
        )

    def test_v79_initialize_aggregates_visible_answers_before_compaction(
        self,
    ) -> None:
        analyst_need = (
            "What are the latest analyst price targets and ratings for Kinross "
            "Gold, and have they been revised upward recently?"
        )
        construction_need = (
            "What is the current construction progress and expected opening timeline?"
        )
        invalid = {
            "hypotheses": ["A material catalyst may support repricing."],
            "current_beliefs": [
                f"Redundant source-summary belief {index}." for index in range(25)
            ],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": ["What is the current construction progress?"],
            "open_questions": [],
            "next_information_needs": [
                analyst_need,
                construction_need,
                "What issuer operating milestone could change expectations?",
            ],
            "decision": "continue",
        }
        corrected = {
            "hypotheses": ["A material catalyst may support repricing."],
            "current_beliefs": ["The catalyst remains unconfirmed."],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": ["What is the current construction progress?"],
            "open_questions": [],
            "next_information_needs": [
                "What issuer operating milestone could change expectations?"
            ],
            "decision": "continue",
        }
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": "projection_analyst",
                            "exact_text": (
                                "UBS analyst recently increased Kinross Gold's price "
                                "target to $27 from $20 while reiterating a Buy rating."
                            ),
                        }
                    ]
                }
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            basic_info,
        )

        error = validation_error(caller.calls[1])
        self.assertIn("current_beliefs count=25", error)
        self.assertIn("already answered by visible Basic Info", error)
        self.assertIn("matching_projection_id='projection_analyst'", error)
        self.assertIn("next_information_needs[0]", error)
        self.assertIn("contradicted its own resolved question", error)
        self.assertIn("next_information_needs[1]", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        visible_obligation = next(
            item
            for item in feedback["obligations"]
            if "already answered by visible Basic Info" in item["instruction"]
        )
        self.assertIn(
            "next_information_needs[0]",
            visible_obligation["must_change_paths"],
        )
        self.assertEqual(
            initialized.value.next_information_needs,
            ("What issuer operating milestone could change expectations?",),
        )

    def test_v79_initialize_abstains_on_partial_basic_info_overlap(self) -> None:
        state = {
            "hypotheses": ["A material catalyst may support repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "How could an analyst price target affect customer demand and "
                "operating margins?"
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_analyst",
                                "exact_text": (
                                    "An analyst increased the price target and kept "
                                    "a Buy rating."
                                ),
                            }
                        ]
                    }
                ]
            },
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            initialized.value.next_information_needs,
            tuple(state["next_information_needs"]),
        )

    def test_v80_initialize_does_not_treat_issuer_name_as_resolved_topic(
        self,
    ) -> None:
        needs = [
            "What are Kinross Gold's recent quarterly earnings results and forward "
            "guidance for production and costs?",
            "Are there any regulatory approvals for Kinross Gold's major projects?",
            "How does Kinross Gold's valuation compare with mining peers?",
        ]
        state = {
            "hypotheses": ["An issuer catalyst may support repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                "What is Kinross Gold's recent stock price performance?"
            ],
            "open_questions": [],
            "next_information_needs": needs,
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, tuple(needs))

    def test_v83_initialize_does_not_treat_period_as_resolved_topic(self) -> None:
        need = (
            "What is the current gold price outlook and how does it compare to the "
            "average realized price in Q2 2025?"
        )
        state = {
            "hypotheses": ["Gold-price strength may support further repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                "What was the issuer's production and cost performance in Q2 2025?"
            ],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v84_initialize_does_not_treat_entity_metric_as_resolved_topic(
        self,
    ) -> None:
        need = (
            "What are the latest gold price forecasts and how do they impact "
            "Kinross's revenue and profitability?"
        )
        state = {
            "hypotheses": ["Gold-price strength may support further repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": ["What was Kinross's revenue in 2024?"],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v85_initialize_does_not_treat_generic_subject_as_topic(self) -> None:
        need = (
            "What are the company's revenue and EBITDA figures for Q1 compared to "
            "the prior year, and what trends did management identify?"
        )
        state = {
            "hypotheses": ["Revenue momentum may support further repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": ["What is the company's recent revenue?"],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))
        self.assertIn(
            "downstream Predictor receives this compact ResearchState",
            caller.calls[0]["system_prompt"],
        )

    def test_v85_initialize_keeps_unknown_kind_feedback_in_one_obligation(
        self,
    ) -> None:
        claim = "A direct issuer catalyst may change expectations."
        exact_text = "A direct issuer catalyst may change expectations."
        invalid = {
            "hypotheses": ["The catalyst may support further repricing."],
            "current_beliefs": [claim],
            "supporting_evidence": [
                {
                    "kind": "news",
                    "claim": claim,
                    "projection_id": "projection_news",
                    "exact_text": exact_text,
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["Check whether the catalyst is durable."],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["supporting_evidence"][0]["kind"] = "basic_info"
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_news",
                                "exact_text": exact_text,
                            }
                        ]
                    }
                ]
            },
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 1)
        self.assertEqual(
            feedback["obligations"][0]["must_change_paths"],
            ["supporting_evidence[0].kind"],
        )
        self.assertIn(
            "expected 'basic_info' or 'signal'",
            feedback["obligations"][0]["instruction"],
        )
        self.assertEqual(initialized.value.supporting_evidence[0].kind, "basic_info")

    def test_v81_initialize_aggregates_runtime_baseline_and_total_limit(
        self,
    ) -> None:
        invalid = {
            "hypotheses": [
                f"Material issuer hypothesis {letter}." for letter in "ABC"
            ],
            "current_beliefs": [
                f"Decision-relevant issuer belief {letter}." for letter in "ABCDEFGH"
            ],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                f"Resolved issuer question {letter}." for letter in "ABCD"
            ],
            "open_questions": [
                "What is the exact baseline date and price for the six-month "
                "evaluation outcome?",
                "Could an operating disruption impair the active thesis?",
                "Could capital allocation strengthen the active thesis?",
                "Could a regulatory event impair the active thesis?",
            ],
            "next_information_needs": [
                f"Check unresolved issuer uncertainty {letter}." for letter in "ABCDEF"
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["open_questions"] = corrected["open_questions"][1:]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        error = validation_error(caller.calls[1])
        self.assertIn("runtime-owned evaluation input", error)
        self.assertIn("invalid_field='open_questions[0]'", error)
        self.assertIn("combined ResearchState array count=25", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        total_obligation = next(
            item
            for item in feedback["obligations"]
            if "combined ResearchState array count=25" in item["instruction"]
        )
        self.assertEqual(total_obligation["current_total_items"], 25)
        self.assertEqual(total_obligation["maximum_total_items"], 24)
        self.assertEqual(total_obligation["minimum_removed_items"], 1)
        baseline_obligation = next(
            item
            for item in feedback["obligations"]
            if "runtime-owned evaluation input" in item["instruction"]
        )
        self.assertEqual(
            baseline_obligation["must_change_paths"], ["open_questions[0]"]
        )
        self.assertEqual(
            initialized.value.open_questions,
            tuple(corrected["open_questions"]),
        )

    def test_v86_total_limit_suggests_structurally_duplicate_open_question(
        self,
    ) -> None:
        repeated_question = "Is the customer renewal still pending?"
        invalid = {
            "hypotheses": [
                f"Material hypothesis {letter}." for letter in "ABC"
            ],
            "current_beliefs": [
                f"Distinct qualitative belief {letter}." for letter in "ABCDEFGH"
            ],
            "supporting_evidence": [],
            "contradictions": [
                f"Distinct qualitative contradiction {letter}." for letter in "ABCD"
            ],
            "resolved_questions": [],
            "open_questions": [
                repeated_question,
                "Could financing delay deployment?",
                "Could costs impair adoption?",
                "Could regulation delay adoption?",
            ],
            "next_information_needs": [
                repeated_question,
                "Check renewal disclosure.",
                "Check financing disclosure.",
                "Check deployment evidence.",
                "Check cost disclosure.",
                "Check regulatory disclosure.",
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["open_questions"] = corrected["open_questions"][1:]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        total_obligation = next(
            item
            for item in feedback["obligations"]
            if "combined ResearchState array count=25" in item["instruction"]
        )
        self.assertEqual(total_obligation["minimum_removed_items"], 1)
        self.assertEqual(
            total_obligation["structurally_redundant_remove_paths"],
            ["open_questions[0]"],
        )
        self.assertIn(
            "remove those byte-identical duplicate items first",
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(
            initialized.value.open_questions,
            tuple(corrected["open_questions"]),
        )

    def test_v82_initialize_supplies_exact_claim_copy_candidates(self) -> None:
        exact_claim = (
            "Kinross's adjusted share price reached $24.37 on 2025-09-29."
        )
        invalid = {
            "hypotheses": ["Recent momentum may support further repricing."],
            "current_beliefs": [
                "Kinross Gold's adjusted share price reached $24.37 on 2025-09-29."
            ],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": exact_claim,
                    "projection_id": "projection_market",
                    "exact_text": (
                        '{"adjusted_close":24.37,"as_of_date":"2025-09-29"}'
                    ),
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "Check whether operating evidence confirms recent momentum."
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [exact_claim]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_market",
                                "exact_text": (
                                    '{"adjusted_close":24.37,'
                                    '"as_of_date":"2025-09-29"}'
                                ),
                            }
                        ]
                    }
                ]
            },
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        obligation = next(
            item
            for item in feedback["obligations"]
            if "quantitative ResearchState assertions" in item["instruction"]
        )
        self.assertEqual(
            obligation["copy_candidates_by_path"],
            {
                "current_beliefs[0]": [
                    {
                        "source_path": "supporting_evidence[0].claim",
                        "exact_claim": exact_claim,
                    }
                ]
            },
        )
        self.assertIn(
            "do not restate, expand, or change issuer words",
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(initialized.value.current_beliefs, (exact_claim,))

    def test_v72_malformed_full_token_output_gets_truncation_feedback(self) -> None:
        corrected = {
            "hypotheses": ["One material catalyst may support repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": ["Is the catalyst issuer-confirmed?"],
            "next_information_needs": ["Check issuer evidence for the catalyst."],
            "decision": "continue",
        }

        class TruncatedThenValidCaller(ScriptedRoleCaller):
            def complete_json(self, **kwargs):
                self.stages.append(str(kwargs["stage"]))
                self.calls.append(dict(kwargs))
                if len(self.calls) == 1:
                    raise StructuredOutputInvalid(
                        "provider returned invalid structured output",
                        '{"hypotheses":["unfinished output",',
                        AgentUsage(llm_calls=1, tokens=2_500, cost=0.01),
                        output_tokens=2_000,
                        output_token_limit=2_000,
                    )
                return self.outputs.pop(0), AgentUsage(
                    llm_calls=1,
                    tokens=500,
                    cost=0.01,
                )

        caller = TruncatedThenValidCaller([corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        self.assertIn("reached max_output_tokens=2000", feedback["validation_error"])
        self.assertIn("output-ceiling truncation", feedback["validation_error"])
        self.assertEqual(
            caller.calls[0]["system_prompt"],
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(initialized.value, ResearchState.from_dict(corrected))

    def test_v72_reflect_preserves_legacy_over_limit_state_without_growth(self) -> None:
        legacy_beliefs = tuple(
            f"Legacy belief {chr(65 + index)}: " + "material issuer context " * 15
            for index in range(9)
        )
        self.assertTrue(all(len(item) > 300 for item in legacy_beliefs))
        previous = ResearchState(
            hypotheses=("One catalyst may support repricing.",),
            current_beliefs=legacy_beliefs,
            next_information_needs=("Check whether the catalyst remains feasible.",),
        )
        finalized = replace(previous, decision=ResearchDecision.FINALIZE)
        caller = ScriptedRoleCaller([finalized.to_dict()])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(),
            must_finalize=True,
            termination_trigger=RuntimeStopReason.MAX_SIGNAL_ROUNDS,
        )
        unavailable = SignalResult(
            signal_id="legacy_coverage",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.0,
            interpretation="No current evidence is available.",
            coverage=SignalCoverage.UNAVAILABLE,
        )

        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(unavailable,), signal_calls=1),
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(reflected.value, finalized)
        self.assertIn(
            "already exceeds a default count or byte ceiling",
            caller.calls[0]["system_prompt"],
        )

    def test_v64_initialize_aggregates_all_decidable_numeric_repairs(self) -> None:
        cash_claim = "Kinross Gold has $1.1 billion in cash and $2.8 billion in liquidity."
        market_claim = (
            "Kinross Gold's adjusted share price rose from $16.21 on 2025-08-01 "
            "to $24.37 on 2025-09-29."
        )
        free_cash_flow_claim = (
            "Kinross Gold delivered almost $650 million in Q2 2025 and over "
            "$1 billion in the first half of 2025."
        )
        net_cash_claim = (
            "Kinross Gold expects net cash in Q3 2025 and plans to repay its "
            "$500 million 2027 notes."
        )
        projections = {
            "projection_cash": (
                "Kinross Gold has $1.1 billion in cash and $2.8 billion in liquidity"
            ),
            "projection_market_start": (
                '{"adjusted_close":16.21,"as_of_date":"2025-08-01"}'
            ),
            "projection_market_end": (
                '{"adjusted_close":24.37,"as_of_date":"2025-09-29"}'
            ),
            "projection_free_cash_flow": (
                "delivered almost $650 million in the second quarter and over "
                "$1 billion in the first half"
            ),
            "projection_net_cash": (
                "expect net cash in Q3 and plan to repay our $500 million 2027 notes"
            ),
        }
        invalid = {
            "hypotheses": ["Cash generation may support further repricing."],
            "current_beliefs": [
                "Kinross Gold holds $1.1 billion cash and $2.8 billion liquidity.",
                "Adjusted price increased from $16.21 on 2025-08-01 to $24.37 on 2025-09-29.",
                free_cash_flow_claim,
                net_cash_claim,
            ],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": cash_claim,
                    "projection_id": "projection_cash",
                    "exact_text": projections["projection_cash"],
                },
                {
                    "kind": "basic_info",
                    "claim": market_claim,
                    "projection_id": "projection_market_start",
                    "exact_text": projections["projection_market_start"],
                },
                {
                    "kind": "basic_info",
                    "claim": market_claim,
                    "projection_id": "projection_market_end",
                    "exact_text": projections["projection_market_end"],
                },
                {
                    "kind": "basic_info",
                    "claim": free_cash_flow_claim,
                    "projection_id": "projection_free_cash_flow",
                    "exact_text": projections["projection_free_cash_flow"],
                },
                {
                    "kind": "basic_info",
                    "claim": net_cash_claim,
                    "projection_id": "projection_net_cash",
                    "exact_text": projections["projection_net_cash"],
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["Check the durability of cash generation."],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected_free_cash_flow_claim = (
            "Kinross Gold delivered almost $650 million in Q2 and over $1 billion "
            "in the first half."
        )
        corrected_net_cash_claim = (
            "Kinross Gold expects net cash in Q3 and plans to repay its "
            "$500 million 2027 notes."
        )
        corrected["current_beliefs"] = [
            cash_claim,
            market_claim,
            corrected_free_cash_flow_claim,
            corrected_net_cash_claim,
        ]
        corrected["supporting_evidence"][3]["claim"] = (
            corrected_free_cash_flow_claim
        )
        corrected["supporting_evidence"][4]["claim"] = corrected_net_cash_claim
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": projection_id,
                                "exact_text": exact_text,
                            }
                            for projection_id, exact_text in projections.items()
                        ]
                    }
                ]
            },
        )

        error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[3]", error)
        self.assertIn("supporting_evidence[4]", error)
        self.assertIn("invalid_fields=['current_beliefs[0]'", error)
        self.assertIn("'current_beliefs[1]']", error)
        numeric_obligation = next(
            item
            for item in caller.calls[1]["payload"]["validation_feedback"][
                "obligations"
            ]
            if "quantitative ResearchState assertions" in item["instruction"]
        )
        self.assertEqual(
            numeric_obligation["must_change_paths"],
            ["current_beliefs[0]", "current_beliefs[1]"],
        )
        self.assertEqual(
            numeric_obligation["copy_candidates_by_path"]["current_beliefs[0]"][0],
            {
                "source_path": "supporting_evidence[0].claim",
                "exact_claim": cash_claim,
            },
        )
        self.assertEqual(
            numeric_obligation["copy_candidates_by_path"]["current_beliefs[1]"][0],
            {
                "source_path": "supporting_evidence[1].claim",
                "exact_claim": market_claim,
            },
        )
        self.assertIn("linked_assertions=['current_beliefs[2]']", error)
        self.assertIn("linked_assertions=['current_beliefs[3]']", error)
        self.assertIn("delete every listed quantity", caller.calls[1]["system_prompt"])
        self.assertIn(
            "Every next_information_needs item must contain only facts absent",
            caller.calls[0]["system_prompt"],
        )
        self.assertEqual(
            initialized.value.current_beliefs,
            tuple(corrected["current_beliefs"]),
        )

    def test_v83_initialize_names_every_invalid_same_claim_evidence_path(
        self,
    ) -> None:
        invalid_market_claim = (
            "The adjusted close rose from 19.38 on 2025-08-18 to 24.37 on "
            "2025-09-29, a 25.7% increase."
        )
        corrected_market_claim = (
            "The adjusted close rose from 19.38 on 2025-08-18 to 24.37 on "
            "2025-09-29."
        )
        valid_news_claim = "UBS raised its price target to $27 from $20."
        projections = {
            "projection_start": (
                '{"adjusted_close":19.38,"as_of_date":"2025-08-18"}'
            ),
            "projection_end": (
                '{"adjusted_close":24.37,"as_of_date":"2025-09-29"}'
            ),
            "projection_news": "UBS raised its price target to $27 from $20.",
        }
        invalid = {
            "hypotheses": ["Recent momentum may support further repricing."],
            "current_beliefs": [
                invalid_market_claim + " This indicates strong momentum."
            ],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": invalid_market_claim,
                    "projection_id": "projection_start",
                    "exact_text": projections["projection_start"],
                },
                {
                    "kind": "basic_info",
                    "claim": invalid_market_claim,
                    "projection_id": "projection_end",
                    "exact_text": projections["projection_end"],
                },
                {
                    "kind": "basic_info",
                    "claim": valid_news_claim,
                    "projection_id": "projection_news",
                    "exact_text": projections["projection_news"],
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "Check whether operating evidence confirms the momentum."
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [corrected_market_claim]
        corrected["supporting_evidence"][0]["claim"] = corrected_market_claim
        corrected["supporting_evidence"][1]["claim"] = corrected_market_claim
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": projection_id,
                                "exact_text": exact_text,
                            }
                            for projection_id, exact_text in projections.items()
                        ]
                    }
                ]
            },
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        quantity_obligation = next(
            item
            for item in feedback["obligations"]
            if "missing_quantity_groups" in item
        )
        self.assertEqual(quantity_obligation["missing_quantity_groups"], ["25.7"])
        self.assertEqual(quantity_obligation["missing_quantity_literals"], ["25.7"])
        self.assertEqual(
            quantity_obligation["same_claim_evidence_paths"],
            [
                "supporting_evidence[0].claim",
                "supporting_evidence[1].claim",
            ],
        )
        self.assertEqual(
            quantity_obligation["must_change_paths"],
            [
                "supporting_evidence[0].claim",
                "supporting_evidence[1].claim",
            ],
        )
        quantitative_obligation = next(
            item
            for item in feedback["obligations"]
            if "quantitative ResearchState assertions" in item["instruction"]
        )
        candidates = quantitative_obligation["copy_candidates_by_path"][
            "current_beliefs[0]"
        ]
        self.assertEqual(
            candidates,
            [
                {
                    "source_path": "supporting_evidence[2].claim",
                    "exact_claim": valid_news_claim,
                }
            ],
        )
        self.assertIn(
            "change or remove every listed evidence path",
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(
            initialized.value.current_beliefs,
            (corrected_market_claim,),
        )

    def test_basic_info_projection_removes_html_and_repetitive_market_metadata(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        filing = RawInfoDocument.create(
            document_id="filing-html",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="<html><body><h1>Item 1</h1><p>Useful business text.</p></body></html>",
        )
        market = RawInfoDocument.create(
            document_id="market-json",
            company_id="issuer-1",
            source_type="market_data",
            published_at=as_of,
            available_at=as_of,
            content=json.dumps(
                [
                    {
                        "adjusted_close": 12.5 + offset,
                        "as_of_date": (as_of.date() - timedelta(days=offset)).isoformat(),
                        "close": 12.5 + offset,
                        "retrieved_at": "2026-08-16T08:41:17.052061+00:00",
                        "source": "fixture",
                        "symbol": "AAA",
                        "volume": 1_000 + offset,
                    }
                    for offset in range(45, -1, -1)
                ],
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        quarterly = RawInfoDocument.create(
            document_id="quarterly-long-tag",
            company_id="issuer-1",
            source_type="10-q",
            published_at=as_of,
            available_at=as_of,
            content=(
                '<html><body><table><td style="'
                + ("color:#000000;" * 180)
                + '">Cash flow debt liquidity improved to 2,165,476.</td>'
                "<td><xbrli:unit id=\"usd\">Readable filing evidence.</xbrli:unit>"
                "</td></table></body></html>"
            ),
        )
        resolver = EvidenceResolver(
            RawInfoStore(documents=(filing, market, quarterly))
        )
        bundle = resolver.resolve_basic_info(
            (
                RawInfoRequest("filing", "business", ("filing",), max_documents=1),
                RawInfoRequest(
                    "market",
                    "market",
                    ("market_data",),
                    lookback_days=45,
                    max_documents=1,
                ),
                RawInfoRequest(
                    "quarterly",
                    "cash flow debt liquidity",
                    ("10-q",),
                    query="cash flow debt liquidity",
                    max_documents=1,
                ),
            ),
            company_id="issuer-1",
            identity={},
            as_of=as_of,
        )

        model_view, audit = project_basic_info_bundle(bundle)
        rendered = json.dumps(model_view)
        self.assertNotIn("<html", rendered)
        self.assertNotIn("<body", rendered)
        self.assertNotIn("retrieved_at", rendered)
        self.assertNotIn('"symbol"', rendered)
        self.assertNotIn('"source"', rendered)
        self.assertNotIn("08:41:17.052061", rendered)
        self.assertNotIn("style=", rendered)
        self.assertNotIn("<xbrli", rendered)
        self.assertIn("Cash flow debt liquidity improved", rendered)
        self.assertTrue(audit["entries"])
        self.assertTrue(all(item["raw_offset_runs"] for item in audit["entries"]))
        self.assertLessEqual(
            sum(
                len(span["exact_text"])
                for request in model_view["requests"]
                for span in request["projections"]
            ),
            32_000,
        )

    def test_v79_basic_projection_preserves_each_resolved_request_boundary(
        self,
    ) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        documents = tuple(
            RawInfoDocument.create(
                document_id=f"document-{index}",
                company_id="issuer-1",
                source_type=f"source_{index}",
                published_at=as_of,
                available_at=as_of,
                content=f"request-{index} " + (f"evidence-{index} " * 2_000),
            )
            for index in range(4)
        )
        bundle = EvidenceResolver(
            RawInfoStore(documents=documents)
        ).resolve_basic_info(
            tuple(
                RawInfoRequest(
                    f"request_{index}",
                    f"Read source {index}.",
                    (f"source_{index}",),
                    max_documents=1,
                )
                for index in range(4)
            ),
            company_id="issuer-1",
            identity={},
            as_of=as_of,
        )

        model_view, _audit = project_basic_info_bundle(bundle)

        self.assertTrue(
            all(request["projections"] for request in model_view["requests"])
        )
        self.assertTrue(
            all(
                request["visible_projection_count"] >= 1
                and request["available_projection_count"]
                >= request["visible_projection_count"]
                and request["omitted_projection_count"]
                == request["available_projection_count"]
                - request["visible_projection_count"]
                for request in model_view["requests"]
            )
        )
        self.assertTrue(
            any(
                request["projection_status"] == "partial_context_budget"
                for request in model_view["requests"]
            )
        )
        self.assertLessEqual(
            sum(
                len(projection["exact_text"])
                for request in model_view["requests"]
                for projection in request["projections"]
            ),
            32_000,
        )

    def test_v11_markup_fragments_are_removed_from_model_projection(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v11_basic_markup_and_claim_support.json"
            ).read_text(encoding="utf-8")
        )

        for fragment in fixture["markup_fragments"]:
            normalized, _runs = _normalized_projection_text(fragment)
            self.assertNotIn("style=", normalized)
            self.assertNotIn("scale=", normalized)
            self.assertNotIn("<", normalized)
            self.assertNotIn(">", normalized)
        entity_text, _runs = _normalized_projection_text(fixture["entity_text"])
        self.assertEqual(entity_text, "Cash Company’s liquidity")

    def test_v11_basic_claim_requires_all_quantities_across_literal_refs(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v11_basic_markup_and_claim_support.json"
            ).read_text(encoding="utf-8")
        )
        cash = fixture["unsupported_cash_claim"]
        ending_text = "Balance, end of period 2,165,476 &#160;"
        invalid = {
            "hypotheses": ["liquidity may be tightening"],
            "current_beliefs": [],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": cash["claim"],
                    "projection_id": "projection_beginning",
                    "exact_text": cash["exact_text"],
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["confirm ending liquidity"],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["supporting_evidence"].append(
            {
                "kind": "basic_info",
                "claim": cash["claim"],
                "projection_id": "projection_ending",
                "exact_text": ending_text,
            }
        )
        caller = ScriptedRoleCaller([invalid, corrected])
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": "projection_beginning",
                            "exact_text": cash["exact_text"],
                        },
                        {
                            "projection_id": "projection_ending",
                            "exact_text": ending_text,
                        },
                    ]
                }
            ]
        }

        state = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(state.value.supporting_evidence), 2)
        self.assertIn(
            "numeric quantities",
            validation_error(caller.calls[1]),
        )
        self.assertIn("2165476", validation_error(caller.calls[1]))

        market = fixture["multi_span_market_claim"]
        market_output = json.loads(json.dumps(corrected))
        market_output["supporting_evidence"] = [
            {
                "kind": "basic_info",
                "claim": market["claim"],
                "projection_id": f"projection_market_{index}",
                "exact_text": exact_text,
            }
            for index, exact_text in enumerate(market["exact_texts"])
        ]
        market_caller = ScriptedRoleCaller([market_output])
        market_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": f"projection_market_{index}",
                            "exact_text": exact_text,
                        }
                        for index, exact_text in enumerate(market["exact_texts"])
                    ]
                }
            ]
        }
        market_state = LLMResearchController(market_caller).initialize(
            default_information_plan(), market_info
        )
        self.assertEqual(len(market_state.value.supporting_evidence), 2)

    def test_v14_basic_claim_accepts_exact_explicit_unit_scaling(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v14_scaled_financial_claim.json"
            ).read_text(encoding="utf-8")
        )

        def output(claim: str) -> dict[str, Any]:
            return {
                "hypotheses": ["Cash generation may be improving."],
                "current_beliefs": [claim],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": claim,
                        "projection_id": f"projection_financial_{index}",
                        "exact_text": exact_text,
                    }
                    for index, exact_text in enumerate(fixture["exact_texts"])
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["Confirm cash-flow durability."],
                "decision": "continue",
            }

        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": f"projection_financial_{index}",
                            "exact_text": exact_text,
                        }
                        for index, exact_text in enumerate(fixture["exact_texts"])
                    ]
                }
            ]
        }
        valid_caller = ScriptedRoleCaller([output(fixture["claim"])])

        state = LLMResearchController(valid_caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(state.value.supporting_evidence), 2)
        self.assertEqual(valid_caller.stages, ["research_controller_initialize"])

        invalid = output(fixture["unsupported_claim"])
        invalid_caller = ScriptedRoleCaller([invalid, invalid])
        with self.assertRaises(CandidateExecutionRejected):
            LLMResearchController(invalid_caller).initialize(
                default_information_plan(), basic_info
            )
        self.assertIn(
            "1605400000",
            validation_error(invalid_caller.calls[1]),
        )

    def test_v12_reflect_rejects_signal_claim_quantities_absent_from_evidence(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v12_reflect_signal_claim_support.json"
            ).read_text(encoding="utf-8")
        )
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        results = tuple(
            SignalResult(
                signal_id=item["signal_id"],
                version=item["version"],
                value=SignalValue(item["value"]),
                confidence=item["confidence"],
                interpretation=item["interpretation"],
                supporting_evidence=(
                    SignalEvidence(
                        document_id=f"{item['signal_id']}-document",
                        exact_span=item["supporting_exact_span"],
                        timestamp=timestamp,
                    ),
                ),
            )
            for item in fixture["signal_results"]
        )
        corrected_reflection = json.loads(
            json.dumps(fixture["corrected_reflection"])
        )
        corrected_reflection["next_information_needs"] = [
            "Check the remaining mine-disruption risk."
        ]
        caller = ScriptedRoleCaller(
            [fixture["invalid_reflection"], corrected_reflection]
        )

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            ResearchState(next_information_needs=("Confirm the production outlook.",)),
            SignalBatchResult(results=results, signal_calls=2),
        )

        error = validation_error(caller.calls[1])
        self.assertIn("referenced Signal evidence", error)
        self.assertIn("513000", error)
        self.assertIn("2200", error)
        self.assertEqual(len(reflected.value.supporting_evidence), 2)
        self.assertIn(
            "Every numeric quantity in a new Signal claim",
            caller.calls[0]["system_prompt"],
        )

    def test_v20_reflect_compacts_signal_evidence_and_preserves_exact_need(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v20_reflect_adaptive_progress.json"
            ).read_text(encoding="utf-8")
        )
        canonical_span = fixture["canonical_evidence_prefix"] + (" detail" * 500)
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=0.8,
            interpretation="Guidance was reaffirmed without an upward revision.",
            supporting_evidence=(
                SignalEvidence(
                    document_id="canonical-raw-document",
                    exact_span=canonical_span,
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        previous = ResearchState(
            hypotheses=("Guidance acceleration may support the thesis.",),
            open_questions=("Did management change guidance?",),
            next_information_needs=(fixture["previous_need"],),
        )
        caller = ScriptedRoleCaller([fixture["invalid_reflection"]])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        self.assertEqual(
            reflected.value.next_information_needs,
            (fixture["previous_need"],),
        )
        self.assertEqual(caller.stages, ["research_controller_reflect"])
        model_evidence = caller.calls[0]["payload"]["signal_batch"][0][
            "evidence"
        ]["supporting"][0]
        self.assertEqual(model_evidence["evidence_index"], 0)
        self.assertLessEqual(
            len(model_evidence["model_evidence_text"]),
            evolution_runtime_module.MAX_REFLECT_SIGNAL_EVIDENCE_CHARS,
        )
        for omitted in (
            "document_id",
            "exact_span",
            "retrieved_at",
            '"source"',
            '"symbol"',
            "<p>",
        ):
            self.assertNotIn(omitted, json.dumps(model_evidence))
        self.assertEqual(result.supporting_evidence[0].exact_span, canonical_span)

        cosmetic = json.loads(json.dumps(fixture["invalid_reflection"]))
        cosmetic["next_information_needs"] = [
            fixture["previous_need"] + " given the available evidence"
        ]
        cosmetic_caller = ScriptedRoleCaller(
            [cosmetic, fixture["corrected_reflection"]]
        )
        corrected = LLMResearchController(cosmetic_caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )
        self.assertEqual(
            corrected.value.next_information_needs,
            (fixture["narrowed_need"],),
        )
        error = validation_error(cosmetic_caller.calls[1])
        self.assertIn("cosmetically changed", error)
        self.assertIn("Keep an unanswered need byte-for-byte", error)

        deterministic = SignalResult(
            signal_id="max_drawdown_1y",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            interpretation="max_drawdown_1y=-0.16",
            supporting_evidence=(
                SignalEvidence(
                    document_id="canonical-market-document",
                    exact_span=(
                        '[{"adjusted_close":9.36,"retrieved_at":"later",'
                        '"source":"massive","symbol":"KGC"}]'
                    ),
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        deterministic_view = evolution_runtime_module._signal_batch_model_view(
            SignalBatchResult(results=(deterministic,), signal_calls=1)
        )[0]
        self.assertEqual(
            deterministic_view["evidence"]["supporting"][0],
            {
                "evidence_index": 0,
                "available_at": "2025-07-31T00:00:00+00:00",
            },
        )
        self.assertEqual(
            deterministic_view["exact_claim_if_adopted"],
            "max_drawdown_1y=-0.16",
        )
        self.assertNotIn("interpretation", deterministic_view)

        no_adoption = fixture["invalid_reflection"] | {"supporting_evidence": []}
        unchanged = LLMResearchController(ScriptedRoleCaller([no_adoption])).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )
        self.assertEqual(
            unchanged.value.next_information_needs,
            previous.next_information_needs,
        )

    def test_v21_reflect_rejects_cosmetic_progress_and_hides_unavailable_claim(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v21_unavailable_cosmetic_reflect.json"
            ).read_text(encoding="utf-8")
        )
        unavailable = SignalResult(
            signal_id="customer_concentration",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.5,
            interpretation=fixture["unsafe_unavailable_interpretation"],
            coverage=SignalCoverage.UNAVAILABLE,
        )
        available = SignalResult(
            signal_id="negative_word_count",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=1.0,
            interpretation="negative_word_count=0",
            supporting_evidence=(
                SignalEvidence(
                    document_id="news-document",
                    exact_span="No configured negative terms occurred.",
                    timestamp=datetime(2025, 9, 24, tzinfo=timezone.utc),
                ),
            ),
        )
        caller = ScriptedRoleCaller(
            [fixture["unchanged_output"], fixture["cosmetic_correction"]]
        )

        with self.assertRaisesRegex(
            CandidateExecutionRejected,
            "cosmetically changed",
        ):
            LLMResearchController(caller).reflect(
                default_information_plan(),
                ResearchState(
                    open_questions=("Is customer concentration known?",),
                    next_information_needs=(fixture["previous_need"],),
                ),
                SignalBatchResult(
                    results=(unavailable, available), signal_calls=2
                ),
            )

        unavailable_view = caller.calls[0]["payload"]["signal_batch"][0]
        summary = unavailable_view["interpretation"]["summary"]
        self.assertNotIn(fixture["unsafe_unavailable_interpretation"], summary)
        self.assertIn("not evidence", summary)
        self.assertEqual(
            unavailable_view["evidence"], {"supporting": [], "counter": []}
        )
        self.assertIn("not evidence of absence", caller.calls[0]["system_prompt"])
        self.assertIn(
            "treated an unavailable Signal as a finding",
            validation_error(caller.calls[1]),
        )

        compact_posthoc = evolution_runtime_module._compact_posthoc_context(
            {
                "basic_info": {},
                "final_research_state": {},
                "signal_rounds": [
                    {"batch": {"results": [unavailable.to_dict()]}}
                ],
            }
        )
        posthoc_summary = compact_posthoc["signal_results"][0]["interpretation"][
            "summary"
        ]
        self.assertIn("not evidence", posthoc_summary)

    def test_v22_reflect_aggregates_quantity_and_stale_resolved_need(self) -> None:
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=0.8,
            interpretation="Guidance was reaffirmed without an upward revision.",
            supporting_evidence=(
                SignalEvidence(
                    document_id="guidance-document",
                    exact_span="Production and cost guidance was reaffirmed.",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        prior_need = (
            "What are the specific production and cost guidance figures and risks?"
        )
        previous = ResearchState(next_information_needs=(prior_need,))
        invalid = {
            "contradictions": [],
            "current_beliefs": ["Management reaffirmed guidance."],
            "decision": "continue",
            "hypotheses": ["Execution now determines the thesis."],
            "next_information_needs": [prior_need],
            "open_questions": [],
            "resolved_questions": [
                "Management resolved the production and cost guidance outlook."
            ],
            "supporting_evidence": [
                {
                    "claim": "Management reaffirmed 2025 production and cost guidance.",
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                    "kind": "signal",
                    "signal_ref": "guidance_acceleration:v1",
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["next_information_needs"] = [
            "What operating disruption could prevent delivery?"
        ]
        corrected["supporting_evidence"][0]["claim"] = (
            "Production and cost guidance was reaffirmed."
        )
        caller = ScriptedRoleCaller([invalid, corrected])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        error = validation_error(caller.calls[1])
        self.assertIn("numeric quantities", error)
        self.assertIn("newly resolved a question", error)
        self.assertIn("production cost guidance", error)
        self.assertEqual(
            reflected.value.next_information_needs,
            ("What operating disruption could prevent delivery?",),
        )

    def test_v23_answer_need_evidence_requires_real_need_progress(self) -> None:
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=0.8,
            interpretation="Guidance was reaffirmed without an upward revision.",
            supporting_evidence=(
                SignalEvidence(
                    document_id="guidance-document",
                    exact_span="Production and cost guidance was reaffirmed.",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        prior_need = "What is the current production guidance and cost outlook?"
        other_need = "What operating disruption could prevent delivery?"
        previous = ResearchState(
            next_information_needs=(prior_need, other_need),
        )
        evidence_ref = {
            "claim": "Production and cost guidance was reaffirmed.",
            "evidence_group": "supporting",
            "evidence_index": 0,
            "kind": "signal",
            "signal_ref": "guidance_acceleration:v1",
        }
        unchanged = {
            "contradictions": [],
            "current_beliefs": ["Production and cost guidance was reaffirmed."],
            "decision": "continue",
            "hypotheses": ["Execution now determines the thesis."],
            "next_information_needs": [prior_need, other_need],
            "open_questions": [],
            "resolved_questions": [],
            "supporting_evidence": [evidence_ref],
        }
        corrected = json.loads(json.dumps(unchanged))
        corrected["next_information_needs"] = [other_need]
        corrected["resolved_questions"] = [
            "Management disclosed the current production and cost guidance."
        ]
        caller = ScriptedRoleCaller([unchanged, corrected])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="guidance_acceleration:v1",
                    reason_code="answer_need",
                    selection_reason=(
                        "Directly answer the production-guidance and cost-outlook need."
                    ),
                    applicability_hypothesis="Current guidance is visible.",
                    expected_role="primary",
                    context_tags=("mature_operations",),
                ),
            ),
            must_finalize=False,
            termination_trigger=None,
        )

        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        error = validation_error(caller.calls[1])
        self.assertIn("reason_code='answer_need'", error)
        self.assertIn("exact same set", error)
        self.assertIn("invalid_field='next_information_needs'", error)
        self.assertIn("next_information_needs[0]", error)
        self.assertIn(prior_need, error)
        self.assertIn("next_information_needs[1]", error)
        self.assertEqual(reflected.value.next_information_needs, (other_need,))
        self.assertEqual(
            caller.calls[0]["payload"]["executed_selection_intents"][0][
                "selection_reason"
            ],
            "Directly answer the production-guidance and cost-outlook need.",
        )

    def test_v70_reflect_changes_targeted_need_not_an_unrelated_need(self) -> None:
        result = SignalResult(
            signal_id="cash_reserves",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            interpretation="cash_reserves=2.07009e+09",
            supporting_evidence=(
                SignalEvidence(
                    document_id="cash-document",
                    exact_span="cash_reserves=2.07009e+09",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        unrelated_need = (
            "What were Q2 revenue and earnings per share versus analyst expectations?"
        )
        targeted_need = (
            "What is the current debt level and liquidity position, and are there "
            "upcoming debt maturities or refinancing plans?"
        )
        narrowed_need = (
            "What is the current debt level, and are there upcoming debt maturities "
            "or refinancing plans?"
        )
        previous = ResearchState(
            next_information_needs=(unrelated_need, targeted_need),
        )
        evidence_ref = {
            "claim": "cash_reserves=2.07009e+09",
            "evidence_group": "supporting",
            "evidence_index": 0,
            "kind": "signal",
            "signal_ref": "cash_reserves:v1",
        }
        for decision, must_finalize in (("continue", False), ("finalize", True)):
            with self.subTest(decision=decision):
                invalid = {
                    "contradictions": [],
                    "current_beliefs": ["cash_reserves=2.07009e+09"],
                    "decision": decision,
                    "hypotheses": ["Liquidity may support execution."],
                    "next_information_needs": [targeted_need],
                    "open_questions": [],
                    "resolved_questions": [],
                    "supporting_evidence": [evidence_ref],
                }
                corrected = json.loads(json.dumps(invalid))
                corrected["next_information_needs"] = [
                    unrelated_need,
                    narrowed_need,
                ]
                caller = ScriptedRoleCaller([invalid, corrected])
                controller = LLMResearchController(caller)
                controller.set_reflection_runtime_context(
                    selections=(
                        SignalSelectionDecision(
                            signal_ref="cash_reserves:v1",
                            reason_code="answer_need",
                            selection_reason="Answer the liquidity facet only.",
                            applicability_hypothesis=(
                                "A current cash balance is visible."
                            ),
                            expected_role="primary",
                            target_need_indices=(1,),
                        ),
                    ),
                    must_finalize=must_finalize,
                    termination_trigger=None,
                )

                reflected = controller.reflect(
                    default_information_plan(),
                    previous,
                    SignalBatchResult(results=(result,), signal_calls=1),
                )

                error = validation_error(caller.calls[1])
                self.assertIn("next_information_needs[0]", error)
                self.assertIn("untargeted need changed or was removed", error)
                self.assertIn("next_information_needs[1]", error)
                self.assertIn("targeted need remained byte-for-byte", error)
                self.assertEqual(
                    reflected.value.next_information_needs,
                    (unrelated_need, narrowed_need),
                )
                selection_intent = caller.calls[0]["payload"][
                    "executed_selection_intents"
                ][0]
                self.assertEqual(selection_intent["target_need_indices"], [1])
                self.assertEqual(
                    set(selection_intent),
                    {
                        "signal_ref",
                        "reason_code",
                        "selection_reason",
                        "target_need_indices",
                    },
                )
                need_rules = caller.calls[0]["payload"][
                    "need_transition_contract"
                ]["need_rules"]
                self.assertEqual(need_rules[0]["required_transition"], "preserve_exactly")
                self.assertEqual(
                    need_rules[1]["available_answer_signal_refs"],
                    ["cash_reserves:v1"],
                )
                self.assertIn("remove_or_genuinely_narrow", need_rules[1]["required_transition"])
                self.assertIn(
                    "need_transition_contract as the sole need-ownership map",
                    caller.calls[0]["system_prompt"],
                )

    def test_v73_reflect_receives_result_aware_need_transition_contract(self) -> None:
        revenue = SignalResult(
            signal_id="revenue_growth_yoy",
            version=1,
            value=SignalValue.NEGATIVE,
            confidence=1.0,
            interpretation="revenue_growth_yoy=-0.0872356",
            supporting_evidence=(
                SignalEvidence(
                    document_id="revenue-document",
                    exact_span="revenue_growth_yoy=-0.0872356",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        guidance = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.0,
            interpretation="No visible management guidance was found.",
            coverage=SignalCoverage.UNAVAILABLE,
        )
        cash = SignalResult(
            signal_id="cash_reserves",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            interpretation="cash_reserves=2.07009e+09",
            supporting_evidence=(
                SignalEvidence(
                    document_id="cash-document",
                    exact_span='{"cash_and_equivalents":2070090000}',
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        financing = SignalResult(
            signal_id="financing_activity",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.0,
            interpretation="No visible financing event was found.",
            coverage=SignalCoverage.UNAVAILABLE,
        )
        revenue_need = "What is the current revenue growth trajectory and run-rate?"
        guidance_need = "What guidance or outlook has management provided?"
        liquidity_need = (
            "What is the current balance sheet, debt, liquidity, and financing position?"
        )
        narrowed_liquidity_need = (
            "What are the current debt obligations and upcoming maturities?"
        )
        previous = ResearchState(
            next_information_needs=(revenue_need, guidance_need, liquidity_need),
        )
        rounded_claim = "Wynn Resorts' cash reserves are approximately $2.07 billion."
        invalid = {
            "contradictions": [],
            "current_beliefs": [rounded_claim],
            "decision": "continue",
            "hypotheses": ["Liquidity may support continued execution."],
            "next_information_needs": [guidance_need, liquidity_need],
            "open_questions": [guidance_need],
            "resolved_questions": ["The current cash balance is now known."],
            "supporting_evidence": [
                {
                    "claim": rounded_claim,
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                    "kind": "signal",
                    "signal_ref": "cash_reserves:v1",
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = ["cash_reserves=2.07009e+09"]
        corrected["supporting_evidence"][0]["claim"] = "cash_reserves=2.07009e+09"
        corrected["next_information_needs"] = [
            revenue_need,
            guidance_need,
            narrowed_liquidity_need,
        ]
        caller = ScriptedRoleCaller([invalid, corrected])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="revenue_growth_yoy:v1",
                    reason_code="combine_evidence",
                    selection_reason="Provide context for the revenue trajectory.",
                    applicability_hypothesis="Revenue facts are visible.",
                    expected_role="confirmation",
                    target_need_indices=(0,),
                ),
                SignalSelectionDecision(
                    signal_ref="guidance_acceleration:v1",
                    reason_code="answer_need",
                    selection_reason="Answer the management-guidance need.",
                    applicability_hypothesis="Guidance may be visible.",
                    expected_role="primary",
                    target_need_indices=(1,),
                ),
                SignalSelectionDecision(
                    signal_ref="cash_reserves:v1",
                    reason_code="answer_need",
                    selection_reason="Answer the liquidity facet.",
                    applicability_hypothesis="A current cash balance is visible.",
                    expected_role="primary",
                    target_need_indices=(2,),
                ),
                SignalSelectionDecision(
                    signal_ref="financing_activity:v1",
                    reason_code="combine_evidence",
                    selection_reason="Provide financing context.",
                    applicability_hypothesis="Financing facts may be visible.",
                    expected_role="confirmation",
                    target_need_indices=(2,),
                ),
            ),
            must_finalize=False,
            termination_trigger=None,
        )

        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(
                results=(revenue, guidance, cash, financing),
                signal_calls=4,
            ),
        )

        payload = caller.calls[0]["payload"]
        cash_view = payload["signal_batch"][2]
        self.assertEqual(
            cash_view["exact_claim_if_adopted"],
            "cash_reserves=2.07009e+09",
        )
        self.assertNotIn("interpretation", cash_view)
        self.assertNotIn(
            "canonical_interpretation",
            cash_view["evidence"]["supporting"][0],
        )
        rules = payload["need_transition_contract"]["need_rules"]
        self.assertEqual(rules[0]["context_only_signal_refs"], ["revenue_growth_yoy:v1"])
        self.assertEqual(rules[0]["required_transition"], "preserve_exactly")
        self.assertEqual(
            rules[1]["unavailable_answer_signal_refs"],
            ["guidance_acceleration:v1"],
        )
        self.assertEqual(rules[1]["required_transition"], "preserve_exactly")
        self.assertEqual(rules[2]["available_answer_signal_refs"], ["cash_reserves:v1"])
        self.assertEqual(rules[2]["context_only_signal_refs"], ["financing_activity:v1"])
        self.assertEqual(
            payload["signal_evidence_ref_catalog"][1]["supporting_evidence_indices"],
            [],
        )
        error = validation_error(caller.calls[1])
        self.assertIn("2.07", error)
        self.assertIn("next_information_needs[0]", error)
        self.assertIn("untargeted need changed or was removed", error)
        self.assertIn("next_information_needs[2]", error)
        self.assertIn("targeted need remained byte-for-byte", error)
        self.assertEqual(
            reflected.value.next_information_needs,
            (revenue_need, guidance_need, narrowed_liquidity_need),
        )

    def test_v74_reflect_requires_exact_partial_answer_residual(self) -> None:
        result = SignalResult(
            signal_id="cash_reserves",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            interpretation="cash_reserves=2.61739e+08",
            supporting_evidence=(
                SignalEvidence(
                    document_id="cash-document",
                    exact_span='{"cash_and_equivalents":261739000}',
                    timestamp=datetime(2025, 8, 7, tzinfo=timezone.utc),
                ),
            ),
        )
        target_need = (
            "What is the current cash position and what share-buyback or strategic "
            "funding plans remain?"
        )
        residual_need = "What share-buyback or strategic funding plans remain?"
        unrelated_need = "What competitive product launches are planned?"
        evidence_ref = {
            "claim": "cash_reserves=2.61739e+08",
            "evidence_group": "supporting",
            "evidence_index": 0,
            "kind": "signal",
            "signal_ref": "cash_reserves:v1",
        }
        invalid = {
            "contradictions": [],
            "current_beliefs": ["cash_reserves=2.61739e+08"],
            "decision": "continue",
            "hypotheses": ["Liquidity may support execution."],
            "next_information_needs": [unrelated_need],
            "open_questions": [],
            "resolved_questions": ["The current cash position is known."],
            "supporting_evidence": [evidence_ref],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["next_information_needs"] = [residual_need, unrelated_need]
        caller = ScriptedRoleCaller([invalid, corrected])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="cash_reserves:v1",
                    reason_code="answer_need",
                    selection_reason="Answer only the current cash-position facet.",
                    applicability_hypothesis="A current cash balance is visible.",
                    expected_role="primary",
                    target_need_indices=(0,),
                    answer_scope="partial",
                    residual_need=residual_need,
                ),
            ),
            must_finalize=False,
            termination_trigger=None,
        )

        reflected = controller.reflect(
            default_information_plan(),
            ResearchState(next_information_needs=(target_need, unrelated_need)),
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        action = caller.calls[0]["payload"]["need_transition_contract"][
            "need_rules"
        ][0]["available_answer_actions"][0]
        self.assertEqual(action["answer_scope"], "partial")
        self.assertEqual(action["residual_need"], residual_need)
        error = validation_error(caller.calls[1])
        self.assertIn("partial-answer target omitted its exact residual", error)
        self.assertIn(residual_need, error)
        self.assertEqual(
            reflected.value.next_information_needs,
            (residual_need, unrelated_need),
        )

    def test_v23_terminal_reflection_requires_model_authored_finalize(self) -> None:
        result = SignalResult(
            signal_id="negative_word_count",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=1.0,
            interpretation="negative_word_count=0",
            supporting_evidence=(
                SignalEvidence(
                    document_id="news-document",
                    exact_span="No configured negative terms occurred.",
                    timestamp=datetime(2025, 9, 24, tzinfo=timezone.utc),
                ),
            ),
        )
        need = "What additional catalyst evidence is available?"
        continuing = {
            "contradictions": [],
            "current_beliefs": [],
            "decision": "continue",
            "hypotheses": ["A catalyst may still emerge."],
            "next_information_needs": [need],
            "open_questions": [need],
            "resolved_questions": [],
            "supporting_evidence": [],
        }
        finalized = json.loads(json.dumps(continuing))
        finalized["decision"] = "finalize"
        caller = ScriptedRoleCaller([continuing, finalized])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="negative_word_count:v1",
                    reason_code="combine_evidence",
                    selection_reason="Add a bounded sentiment diagnostic.",
                    applicability_hypothesis="Current news is visible.",
                    expected_role="confirmation",
                    context_tags=("news_rich",),
                ),
            ),
            must_finalize=True,
            termination_trigger=RuntimeStopReason.BUDGET_EXHAUSTED,
        )

        reflected = controller.reflect(
            default_information_plan(),
            ResearchState(next_information_needs=(need,)),
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        self.assertEqual(reflected.value.decision, ResearchDecision.FINALIZE)
        self.assertEqual(reflected.value.next_information_needs, (need,))
        self.assertIn("last executable evidence batch", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.calls[0]["payload"]["reflection_runtime"],
            {
                "must_finalize": True,
                "termination_trigger": "budget_exhausted",
            },
        )

    def test_v63_unavailable_terminal_reflection_changes_only_decision(self) -> None:
        need = "What additional customer-order evidence is available?"
        previous = ResearchState(
            hypotheses=("Binding customer orders may support growth.",),
            open_questions=(need,),
            next_information_needs=(need,),
        )
        invalid = replace(
            previous,
            hypotheses=("Unavailable data weakens the order thesis.",),
            decision=ResearchDecision.FINALIZE,
        ).to_dict()
        corrected = replace(
            previous,
            decision=ResearchDecision.FINALIZE,
        ).to_dict()
        caller = ScriptedRoleCaller([invalid, corrected])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="revenue_growth_yoy:v1",
                    reason_code="answer_need",
                    selection_reason="Try the available financial periods.",
                    applicability_hypothesis="Comparable periods may be available.",
                    expected_role="coverage",
                ),
            ),
            must_finalize=True,
            termination_trigger=RuntimeStopReason.BUDGET_EXHAUSTED,
        )
        unavailable = SignalResult(
            signal_id="revenue_growth_yoy",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.0,
            interpretation="Revenue periods are unavailable.",
            coverage=SignalCoverage.UNAVAILABLE,
        )

        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(unavailable,), signal_calls=1),
        )

        error = validation_error(caller.calls[1])
        self.assertIn("all-unavailable terminal batch", error)
        self.assertIn("change only decision", error)
        self.assertEqual(
            reflected.value,
            replace(previous, decision=ResearchDecision.FINALIZE),
        )
        self.assertIn(
            "If every current-batch Signal is unavailable",
            caller.calls[0]["system_prompt"],
        )

    def test_v18_reflect_accepts_exact_deterministic_interpretation_not_rounding(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v18_deterministic_interpretation_claim.json"
            ).read_text()
        )
        timestamp = datetime(2025, 7, 31, tzinfo=timezone.utc)
        result = SignalResult(
            signal_id="revenue_growth_yoy",
            version=1,
            value=SignalValue.NEGATIVE,
            confidence=1.0,
            interpretation=fixture["interpretation"],
            supporting_evidence=(
                SignalEvidence(
                    document_id="wynn-facts",
                    exact_span=fixture["evidence_span"],
                    timestamp=timestamp,
                ),
            ),
        )

        def reflection(claim: str) -> dict[str, Any]:
            return {
                "hypotheses": ["Recent revenue may be weakening."],
                "current_beliefs": [claim],
                "supporting_evidence": [
                    {
                        "kind": "signal",
                        "claim": claim,
                        "signal_ref": "revenue_growth_yoy:v1",
                        "evidence_group": "supporting",
                        "evidence_index": 0,
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["Check a current catalyst."],
                "decision": "continue",
            }

        exact_caller = ScriptedRoleCaller([reflection(fixture["exact_claim"])])
        reflected = LLMResearchController(exact_caller).reflect(
            default_information_plan(),
            ResearchState(next_information_needs=("Check revenue.",)),
            SignalBatchResult(results=(result,), signal_calls=1),
        )
        self.assertEqual(
            reflected.value.supporting_evidence[0].claim, fixture["exact_claim"]
        )
        self.assertIn("do not round it", exact_caller.calls[0]["system_prompt"])

        rounded_caller = ScriptedRoleCaller(
            [reflection(fixture["rounded_claim"]), reflection(fixture["rounded_claim"])]
        )
        with self.assertRaises(CandidateExecutionRejected):
            LLMResearchController(rounded_caller).reflect(
                default_information_plan(),
                ResearchState(next_information_needs=("Check revenue.",)),
                SignalBatchResult(results=(result,), signal_calls=1),
            )
        self.assertIn(
            "Do not round or convert",
            validation_error(rounded_caller.calls[1]),
        )

    def test_v12_reflect_preserves_retained_signal_claim_without_old_batch(self) -> None:
        prior_claim = "Management reaffirmed rather than raised guidance."
        prior_ref = ResearchEvidenceRef(
            kind="signal",
            claim=prior_claim,
            signal_ref="guidance_acceleration:v1",
            evidence_group="supporting",
            evidence_index=0,
        )
        previous = ResearchState(
            hypotheses=("Guidance is not accelerating.",),
            supporting_evidence=(prior_ref,),
            next_information_needs=("Check a separate risk.",),
        )
        invalid = previous.to_dict()
        invalid["supporting_evidence"][0]["claim"] = (
            "Management raised guidance materially."
        )
        corrected = previous.to_dict()
        caller = ScriptedRoleCaller([invalid, corrected])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(), signal_calls=0),
        )

        error = validation_error(caller.calls[1])
        self.assertIn("retained Signal claim changed", error)
        self.assertIn("backing Signal batch is no longer visible", error)
        self.assertEqual(reflected.value.supporting_evidence[0].claim, prior_claim)

    def test_v12_signal_evidence_rejects_internal_projection_edge_fragment(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v12_reflect_signal_claim_support.json"
            ).read_text(encoding="utf-8")
        )
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        prefix = "Earlier transcript context. "
        projection_text = prefix + fixture["guidance_truncated_projection"]
        raw_prefix = "x" * 100
        document = RawInfoDocument.create(
            document_id="guidance-transcript",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=timestamp,
            available_at=timestamp,
            content=raw_prefix + projection_text + "500 per ounce. Later context.",
        )
        lineage = evolution_runtime_module._SignalProjectionLineage(
            document=document,
            projection_text=projection_text,
            raw_offset_runs=((0, len(projection_text), 100, 100 + len(projection_text)),),
            normalized_start=100,
            normalized_end=100 + len(projection_text),
            normalized_source_length=len(document.content),
        )
        overlap_start = lineage.normalized_end - 80
        overlap_text = document.content[overlap_start:]
        overlap_lineage = evolution_runtime_module._SignalProjectionLineage(
            document=document,
            projection_text=overlap_text,
            raw_offset_runs=(
                (
                    0,
                    len(overlap_text),
                    overlap_start,
                    len(document.content),
                ),
            ),
            normalized_start=overlap_start,
            normalized_end=len(document.content),
            normalized_source_length=len(document.content),
        )
        result = {
            "evidence": {
                "supporting": [
                    {
                        "projection_id": "projection_truncated",
                        "exact_text": fixture["guidance_truncated_projection"],
                    }
                ],
                "counter": [],
            }
        }

        with self.assertRaisesRegex(
            ValidationError, "touches internal projection edge"
        ) as context:
            evolution_runtime_module._map_projected_signal_evidence(
                result,
                {
                    "projection_truncated": lineage,
                    "projection_overlap": overlap_lineage,
                },
            )
        error = str(context.exception)
        self.assertIn("supporting evidence[0]", error)
        self.assertIn("projection_truncated", error)
        self.assertIn("edge=['end']", error)
        self.assertIn("projection_overlap", error)

    def test_v13_signal_evidence_relocates_unique_quote_from_wrong_overlap(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v13_signal_projection_relocation.json"
            ).read_text(encoding="utf-8")
        )
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        unique_text = (
            fixture["unique_projection_prefix"]
            + fixture["exact_text"]
            + fixture["unique_projection_suffix"]
        )
        document = RawInfoDocument.create(
            document_id="guidance-transcript",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=timestamp,
            available_at=timestamp,
            content=unique_text,
        )

        def lineage(text_value: str, *, start: int, source_length: int):
            return evolution_runtime_module._SignalProjectionLineage(
                document=document,
                projection_text=text_value,
                raw_offset_runs=((0, len(text_value), 0, len(text_value)),),
                normalized_start=start,
                normalized_end=start + len(text_value),
                normalized_source_length=source_length,
            )

        mapped = evolution_runtime_module._map_projected_signal_evidence(
            {
                "evidence": {
                    "supporting": [
                        {
                            "projection_id": fixture["wrong_projection_id"],
                            "exact_text": fixture["exact_text"],
                        }
                    ],
                    "counter": [],
                }
            },
            {
                fixture["wrong_projection_id"]: lineage(
                    fixture["wrong_projection_text"],
                    start=100,
                    source_length=100 + len(fixture["wrong_projection_text"]) + 50,
                ),
                fixture["unique_projection_id"]: lineage(
                    unique_text, start=0, source_length=len(unique_text)
                ),
            },
        )

        self.assertIn(
            fixture["exact_text"],
            mapped["evidence"]["supporting"][0]["exact_span"],
        )

    def test_v12_posthoc_preserves_predictor_basic_source_index(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v12_reflect_signal_claim_support.json"
            ).read_text(encoding="utf-8")
        )
        original_context = {
            "basic_info": fixture["predictor_basic_info"],
            "final_research_state": fixture["corrected_reflection"],
            "signal_rounds": [],
            "prediction_baseline": {
                "status": "available",
                "mean_adjusted_close": 23.982,
            },
        }

        compact = evolution_runtime_module._compact_posthoc_context(original_context)

        self.assertEqual(
            compact["basic_info_source_index"],
            fixture["predictor_basic_info"]["source_index"],
        )
        self.assertEqual(compact["data_gaps"], [])
        self.assertEqual(
            compact["prediction_baseline"]["mean_adjusted_close"], 23.982
        )
        serialized = json.dumps(compact, ensure_ascii=False)
        self.assertNotIn("source_projection", serialized)
        self.assertNotIn("guidance_source", serialized)

    def test_two_soft_signals_share_one_projection_call_and_map_to_raw(self) -> None:
        class ProjectionBatchCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                projection = kwargs["payload"]["source_projection"][0]
                first_ref, second_ref = kwargs["payload"]["batch_signal_refs"]
                first_id, first_version = first_ref.split(":v")
                second_id, second_version = second_ref.split(":v")
                return (
                    {
                        "results": [
                            {
                                "signal_ref": first_ref,
                                "result": {
                                    "signal_id": first_id,
                                    "version": int(first_version),
                                    "state": {"value": "positive", "confidence": 0.8},
                                    "interpretation": {"summary": "Guidance improved."},
                                    "evidence": {
                                        "supporting": [
                                            {
                                                "projection_id": projection["projection_id"],
                                                "exact_text": "Management raised guidance.",
                                            }
                                        ],
                                        "counter": [],
                                    },
                                    "status": {"coverage": "sufficient"},
                                },
                            },
                            {
                                "signal_ref": second_ref,
                                "result": {
                                    "signal_id": second_id,
                                    "version": int(second_version),
                                    "state": {"value": "unavailable", "confidence": 0.0},
                                    "interpretation": {"summary": "No visible evidence."},
                                    "evidence": {"supporting": [], "counter": []},
                                    "status": {"coverage": "unavailable"},
                                },
                            },
                        ]
                    },
                    AgentUsage(llm_calls=1, tokens=50, cost=0.01),
                )

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-html",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="<p>Management <b>raised</b> guidance.</p>",
        )
        inputs = tuple(
            LLMSignalBatchInput(
                SignalSpec(
                    signal_id=signal_id,
                    version=1,
                    category="catalysts",
                    description="Inspect management guidance.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("filing",),
                    skill_file=f"{signal_id}.md",
                ),
                (document,),
                "Extract source-grounded guidance evidence.",
            )
            for signal_id in ("guidance_a", "guidance_b")
        )
        caller = ProjectionBatchCaller()

        results, usage = StructuredLLMSignalRunner(caller).execute_many(inputs, as_of)

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(usage.llm_calls, 1)
        self.assertEqual(set(results), {"guidance_a:v1", "guidance_b:v1"})
        self.assertEqual(
            results["guidance_a:v1"].supporting_evidence[0].exact_span,
            "Management <b>raised</b> guidance.",
        )
        rendered = json.dumps(caller.calls[0]["payload"])
        self.assertNotIn("<p>", rendered)
        self.assertNotIn("<b>", rendered)
        identities = [
            (item["document_id"], item["content_hash"])
            for item in caller.calls[0]["payload"]["source_projection"]
        ]
        self.assertEqual(len(identities), len(set(identities)))

    def test_v68_correction_budget_preserves_valid_soft_signal_sibling(self) -> None:
        class CorrectionBudgetCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 2:
                    raise RuntimeBudgetExceeded(
                        "correction reservation exceeds remaining case budget"
                    )
                payload = kwargs["payload"]
                projections = {
                    item["projection_id"]: item
                    for item in payload["source_projection"]
                }
                rows = []
                for item in payload["signals"]:
                    signal_ref = item["signal_ref"]
                    projection = projections[item["eligible_projection_ids"][0]]
                    exact_text = projection["exact_text"]
                    if signal_ref == "customer_concentration:v1":
                        exact_text = exact_text.replace("One customer", "one customer")
                    signal_id, version = signal_ref.split(":v")
                    rows.append(
                        {
                            "signal_ref": signal_ref,
                            "result": {
                                "signal_id": signal_id,
                                "version": int(version),
                                "state": {
                                    "value": (
                                        "negative"
                                        if signal_id == "customer_concentration"
                                        else "positive"
                                    ),
                                    "confidence": 0.8,
                                },
                                "interpretation": {
                                    "summary": f"{signal_id} was source-backed."
                                },
                                "evidence": {
                                    "supporting": [
                                        {
                                            "projection_id": projection[
                                                "projection_id"
                                            ],
                                            "exact_text": exact_text,
                                        }
                                    ],
                                    "counter": [],
                                },
                                "status": {"coverage": "sufficient"},
                            },
                        }
                    )
                return (
                    {"results": rows},
                    AgentUsage(llm_calls=1, tokens=50, cost=0.01),
                )

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        guidance = RawInfoDocument.create(
            document_id="guidance-document",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Management raised annual guidance.",
        )
        concentration = RawInfoDocument.create(
            document_id="concentration-document",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="One customer represented 72 percent of revenue.",
        )
        inputs = tuple(
            LLMSignalBatchInput(
                SignalSpec(
                    signal_id=signal_id,
                    version=1,
                    category="catalysts",
                    description="Inspect the supplied disclosure.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("filing",),
                    skill_file=f"{signal_id}.md",
                ),
                (document,),
                "Extract one literal source-backed conclusion.",
            )
            for signal_id, document in (
                ("guidance_change", guidance),
                ("customer_concentration", concentration),
            )
        )
        caller = CorrectionBudgetCaller()
        runner = StructuredLLMSignalRunner(caller)
        runner.set_request_token_budget(100)

        results, usage = runner.execute_many(inputs, as_of)

        self.assertEqual(usage, AgentUsage(llm_calls=1, tokens=50, cost=0.01))
        self.assertEqual(results["guidance_change:v1"].value, SignalValue.POSITIVE)
        concentration_result = results["customer_concentration:v1"]
        self.assertEqual(concentration_result.value, SignalValue.UNAVAILABLE)
        self.assertIn("correction request was not sent", concentration_result.interpretation)
        self.assertEqual(len(caller.calls), 2)
        error = caller.calls[1]["payload"]["validation_feedback"][0][
            "validation_error"
        ]
        self.assertIn("Signal supporting evidence[0]", error)
        self.assertIn("supplied_occurrences=0", error)
        self.assertIn("visible_occurrences=0", error)
        self.assertIn("matching_projection_ids=[]", error)

    def test_v30_shared_soft_projection_preserves_per_signal_document_scope(self) -> None:
        class CrossScopeCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                payload = kwargs["payload"]
                if len(self.calls) == 1:
                    scopes = {
                        item["signal_ref"]: item["eligible_projection_ids"]
                        for item in payload["signals"]
                    }
                    return (
                        {
                            "results": [
                                {
                                    "signal_ref": "scope_a:v1",
                                    "result": {
                                        "signal_id": "scope_a",
                                        "version": 1,
                                        "state": {
                                            "value": "positive",
                                            "confidence": 0.8,
                                        },
                                        "interpretation": {
                                            "summary": "Peer evidence was cited."
                                        },
                                        "evidence": {
                                            "supporting": [
                                                {
                                                    "projection_id": scopes[
                                                        "scope_b:v1"
                                                    ][0],
                                                    "exact_text": (
                                                        "Customer B signed a contract."
                                                    ),
                                                }
                                            ],
                                            "counter": [],
                                        },
                                        "status": {"coverage": "sufficient"},
                                    },
                                },
                                {
                                    "signal_ref": "scope_b:v1",
                                    "result": {
                                        "signal_id": "scope_b",
                                        "version": 1,
                                        "state": {
                                            "value": "unavailable",
                                            "confidence": 0.0,
                                        },
                                        "interpretation": {
                                            "summary": "No conclusion."
                                        },
                                        "evidence": {
                                            "supporting": [],
                                            "counter": [],
                                        },
                                        "status": {"coverage": "unavailable"},
                                    },
                                },
                            ]
                        },
                        AgentUsage(llm_calls=1, tokens=50, cost=0.01),
                    )
                return (
                    {
                        "results": [
                            {
                                "signal_ref": "scope_a:v1",
                                "result": {
                                    "signal_id": "scope_a",
                                    "version": 1,
                                    "state": {
                                        "value": "unavailable",
                                        "confidence": 0.0,
                                    },
                                    "interpretation": {"summary": "No conclusion."},
                                    "evidence": {"supporting": [], "counter": []},
                                    "status": {"coverage": "unavailable"},
                                },
                            }
                        ]
                    },
                    AgentUsage(llm_calls=1, tokens=20, cost=0.005),
                )

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document_a = RawInfoDocument.create(
            document_id="document-a",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Issuer A raised guidance.",
        )
        document_b = RawInfoDocument.create(
            document_id="document-b",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Customer B signed a contract.",
        )
        inputs = tuple(
            LLMSignalBatchInput(
                SignalSpec(
                    signal_id=signal_id,
                    version=1,
                    category="catalysts",
                    description="Inspect one bounded filing.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("filing",),
                    skill_file=f"{signal_id}.md",
                ),
                (document,),
                "Extract source-grounded evidence.",
            )
            for signal_id, document in (
                ("scope_a", document_a),
                ("scope_b", document_b),
            )
        )
        caller = CrossScopeCaller()

        results, usage = StructuredLLMSignalRunner(caller).execute_many(inputs, as_of)

        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(results["scope_a:v1"].value, SignalValue.UNAVAILABLE)
        first_scopes = {
            item["signal_ref"]: item["eligible_projection_ids"]
            for item in caller.calls[0]["payload"]["signals"]
        }
        self.assertTrue(first_scopes["scope_a:v1"])
        self.assertTrue(first_scopes["scope_b:v1"])
        self.assertTrue(
            set(first_scopes["scope_a:v1"]).isdisjoint(
                first_scopes["scope_b:v1"]
            )
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("outside this Signal's eligible_projection_ids", feedback["validation_error"])
        self.assertIn("unchanged eligible_projection_ids", feedback["required_action"])
        self.assertIn(
            "Each Signal may cite only projection ids",
            caller.calls[0]["system_prompt"],
        )

    def test_proposer_corrects_unsupported_source_then_rejects_stale_probability(self) -> None:
        parent = default_information_plan()
        unsupported = {
            "B": {
                "requests": [
                    {
                        "request_id": "market",
                        "description": "market",
                        "source_types": ["market_data"],
                        "lookback_days": 30,
                        "max_documents": 1,
                    },
                    {
                        "request_id": "unsupported",
                        "description": "unsupported",
                        "source_types": ["social_firehose"],
                        "max_documents": 1,
                    },
                ]
            },
            "H_init": "form needs",
            "H_reflect": "reflect on evidence",
            "H_analyse": "organize evidence",
        }
        stale = json.loads(json.dumps(unsupported))
        stale["B"]["requests"] = stale["B"]["requests"][:1]
        stale["H_analyse"] = "Compute P(surge) and apply a 0.55 probability threshold."
        caller = ScriptedRoleCaller([unsupported, stale])

        with self.assertRaises(CandidateProposalRejected):
            LLMInformationPlanProposer(
                caller,
                available_source_types=("market_data", "filing"),
            ).propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(parent,),
                meta_info=(),
                prior="fixed H_P",
            )

        self.assertEqual(len(caller.calls), 2)
        self.assertIn(
            "unsupported source types",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )
        self.assertEqual(
            caller.calls[0]["payload"]["proposal_context"][
                "available_source_types"
            ],
            ["filing", "market_data"],
        )

    def test_v30_proposer_rejects_controller_owned_prediction_ontology(self) -> None:
        parent = default_information_plan()
        invalid = {
            "B": {
                "requests": [
                    {
                        "request_id": "market",
                        "description": "compact market evidence",
                        "source_types": ["market_data"],
                        "lookback_days": 30,
                        "max_documents": 1,
                    }
                ]
            },
            "H_init": (
                "Form a falsifiable hypothesis and list unresolved information "
                "needs and questions."
            ),
            "H_reflect": (
                "Reflect on supporting and contradictory evidence, then finalize "
                "the four-way judgment (strong up, up, down, strong down) or "
                "continue to the next information need."
            ),
            "H_analyse": (
                "Organize and weight supporting and counter-evidence while "
                "preserving uncertainty."
            ),
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["H_reflect"] = (
            "Reflect on supporting and contradictory evidence to update beliefs, "
            "then continue with the next information need or finalize evidence "
            "collection while keeping the four-way judgment intact and without "
            "altering the Predictor class ontology."
        )
        caller = ScriptedRoleCaller([invalid, corrected])

        plan = LLMInformationPlanProposer(
            caller,
            available_source_types=("market_data",),
        ).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(plan.reflection_skill, corrected["H_reflect"])
        self.assertIn(
            "cannot define or finalize a replacement Predictor class ontology",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )
        self.assertIn(
            "must not define, name, or finalize a replacement Predictor class ontology",
            caller.calls[0]["system_prompt"],
        )

    def test_posthoc_uses_compact_view_not_full_original_context(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "prediction_outcome": {"correct": True},
                    "decision_drivers": [
                        "The bounded evidence supported the negative judgment."
                    ],
                    "why_prediction_failed": [],
                    "misleading_signals": [],
                    "ignored_evidence": [],
                    "missing_information": [],
                    "plan_issues": [],
                }
            ]
        )
        predictor = LLMBlindPredictor(caller)
        prediction = BlindPrediction(
            is_surge=False,
            candidate_judgment=CandidateJudgment.UNLIKELY,
            magnitude=None,
            confidence=ConfidenceLevel.LOW,
            key_reasons=("bounded evidence",),
            uncertainties=(),
            session_id="fixture",
        )
        original = {
            "basic_info": {"requests": []},
            "signal_rounds": [],
            "final_research_state": ResearchState(
                decision=ResearchDecision.FINALIZE
            ).to_dict(),
            "full_original_marker": "do-not-send-" + "x" * 30_000,
        }

        predictor.reflect(original, prediction, GroundTruth(1.1))

        payload = caller.calls[0]["payload"]
        self.assertIn("compact_context", payload)
        self.assertNotIn("original_context", payload)
        self.assertNotIn("do-not-send", json.dumps(payload))
        self.assertLess(len(json.dumps(payload["compact_context"])), 24_000)

    def test_critic_masks_identity_in_accepted_output_before_meta(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "successful_patterns": [],
                    "failed_patterns": [],
                    "repeated_failure_modes": [],
                    "misleading_signals": [],
                    "missing_information_needs": [
                        "Research Acme Systems Corp customer concentration."
                    ],
                    "next_explorations": [],
                }
            ]
        )
        critic = LLMPlanCritic(caller)
        critic.set_anonymous_aliases(("Acme Systems Corp", "Acme Systems"))
        metrics = PlanMetrics(
            binary_precision=1.0,
            binary_recall=1.0,
            binary_f1=1.0,
            magnitude_accuracy=1.0,
            magnitude_macro_f1=1.0,
            true_positive=1,
            false_positive=0,
            true_negative=1,
            false_negative=0,
            sample_count=2,
        )

        reflection = critic.critique(
            plan=default_information_plan(),
            trajectories=(),
            metrics=metrics,
        )

        rendered = json.dumps(reflection.to_dict())
        self.assertNotIn("Acme", rendered)
        self.assertIn("MASKED_COMPANY", rendered)


class RunControlTests(TestCase):
    def test_slow_bootstrap_manifest_masks_identity_and_binds_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source_registry = SignalRegistry(source / "signals")
            source_registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            target_registry = SignalRegistry(target / "signals")
            target_registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            snapshot = target_registry.freeze()
            self.assertEqual(source_registry.freeze().registry_hash, snapshot.registry_hash)
            case = evolution_runtime_module.EvolutionCase(
                case_id="case_kgc",
                company_id="issuer_kgc",
                prediction_time=datetime(2025, 9, 30, tzinfo=timezone.utc),
                basic_info={
                    "company_name": "Kinross Gold Corporation",
                    "ticker": "KGC",
                    "identity_aliases": ["Kinross Gold"],
                },
                ground_truth=GroundTruth(2.5),
            )
            dataset = evolution_runtime_module.ApprovedDevelopmentDataset(
                discovery=(),
                anchor=(),
                evolution_validation=(case,),
                locked_test_hash=SHA_B,
                approved_manifest_hash=SHA_A,
            )
            source_contract = EvolutionRunContract(
                **{
                    **make_contract().__dict__,
                    "run_id": "source-run",
                    "initial_signal_registry_version": snapshot.version,
                    "initial_signal_registry_hash": snapshot.registry_hash,
                }
            )
            source.mkdir(parents=True, exist_ok=True)
            source_contract.freeze(source / "run_contract.json")
            write_json(source / "state.json", {"last_completed_round": 0})
            rejected_path = source / "experiments" / "round-0001" / "rejected.json"
            rejected_path.parent.mkdir(parents=True)
            write_json(
                rejected_path,
                {
                    "schema_version": "plan-round-rejected-v1",
                    "round_id": 1,
                    "last_completed_round": 0,
                    "reason": "no fitness-eligible candidate",
                    "attempts": [
                        {
                            "trajectories": [
                                {
                                    "case_id": case.case_id,
                                    "stop_reason": "no_signal_match",
                                    "termination_trigger": "no_signal_match",
                                    "final_state": {
                                        "decision": "continue",
                                        "next_information_needs": [
                                            "What are Kinross Gold's latest analyst estimate revisions?"
                                        ],
                                    },
                                    "prediction": {"is_surge": True},
                                    "ground_truth": {"realized_max_multiple": 2.5},
                                }
                            ]
                        }
                    ],
                },
            )

            manifest_hash = evolution_runtime_module.build_slow_bootstrap_manifest(
                workspace=target,
                source_workspaces=(source,),
                dataset=dataset,
                signal_snapshot=snapshot,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            envelope = json.loads(
                (target / "slow_bootstrap" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            serialized = json.dumps(envelope)
            self.assertIn("[MASKED_COMPANY]", serialized)
            self.assertNotIn("Kinross", serialized)
            self.assertNotIn("case_kgc", serialized)
            self.assertNotIn("ground_truth", serialized)
            self.assertEqual(
                envelope["manifest"]["sources"][0]["rejected_hash"],
                hashlib.sha256(rejected_path.read_bytes()).hexdigest(),
            )
            bootstrap_contract = EvolutionRunContract(
                **{
                    **make_contract().__dict__,
                    "initial_signal_registry_version": snapshot.version,
                    "initial_signal_registry_hash": snapshot.registry_hash,
                    "limits": {
                        **make_contract().limits,
                        "plan_rounds_per_signal_cycle": 0,
                    },
                    "cycle_mode": "slow_bootstrap",
                    "slow_bootstrap_manifest_hash": manifest_hash,
                }
            )
            validated = evolution_runtime_module.validate_slow_bootstrap_manifest(
                workspace=target,
                contract=bootstrap_contract,
                signal_snapshot=snapshot,
            )
            self.assertEqual(validated["schema_version"], "slow-bootstrap-manifest-v1")

    def _seed_candidate(
        self,
        *,
        run_id: str,
        suffix: str,
        binary_f1: float,
        embedding: tuple[float, ...],
        random_prefix: str | None = None,
    ):
        base = default_information_plan()
        plan = InformationPlan(
            plan_id=f"source_{suffix}",
            parent_ids=(),
            basic_info_policy=base.basic_info_policy,
            initial_research_skill=f"{base.initial_research_skill} {suffix}",
            reflection_skill=base.reflection_skill,
            analysis_prompt=base.analysis_prompt,
        )

        def metrics(sample_count: int) -> PlanMetrics:
            return PlanMetrics(
                binary_precision=binary_f1,
                binary_recall=binary_f1,
                binary_f1=binary_f1,
                magnitude_accuracy=0.0,
                magnitude_macro_f1=0.0,
                true_positive=1,
                false_positive=0,
                true_negative=sample_count - 1,
                false_negative=0,
                sample_count=sample_count,
            )

        content_hash = evolution_runtime_module._canonical_hash(
            plan.canonical_dict()
        )
        return evolution_runtime_module.HistoricalPlanSeed(
            source_workspace=run_id,
            source_run_id=run_id,
            source_run_family_id=run_id,
            source_contract_hash=SHA_A,
            source_checkpoint_ref=f"{run_id}/checkpoint.json",
            source_record_hash=SHA_B,
            source_round_id=1,
            source_plan_id=plan.plan_id,
            plan_content_hash=content_hash,
            plan=plan,
            embedding=embedding,
            metrics_by_cohort={
                "anchor": metrics(16),
                "random": metrics(8),
                "combined": metrics(24),
            },
            random_case_ids=tuple(
                f"{random_prefix or run_id}_random_{index}" for index in range(8)
            ),
            source_dataset_snapshot_id=SHA_C,
        )

    def test_historical_seed_selection_requires_source_and_semantic_diversity(self) -> None:
        champion = self._seed_candidate(
            run_id="run-a",
            suffix="champion",
            binary_f1=0.70,
            embedding=(1.0, 0.0),
        )
        same_run = self._seed_candidate(
            run_id="run-a",
            suffix="same-run",
            binary_f1=0.69,
            embedding=(0.0, 1.0),
        )
        near_duplicate = self._seed_candidate(
            run_id="run-c",
            suffix="near-duplicate",
            binary_f1=0.68,
            embedding=(0.999, 0.01),
        )
        diverse = self._seed_candidate(
            run_id="run-b",
            suffix="diverse",
            binary_f1=0.65,
            embedding=(0.0, 1.0),
        )

        selected = evolution_runtime_module._select_historical_plan_seed_candidates(
            (same_run, diverse, near_duplicate, champion)
        )

        self.assertEqual(
            [item.source_plan_id for item in selected],
            [champion.source_plan_id, diverse.source_plan_id],
        )

    def test_historical_seed_selection_underfills_below_quality_floor(self) -> None:
        champion = self._seed_candidate(
            run_id="run-a",
            suffix="champion",
            binary_f1=0.70,
            embedding=(1.0, 0.0),
        )
        weak = self._seed_candidate(
            run_id="run-b",
            suffix="weak",
            binary_f1=0.50,
            embedding=(0.0, 1.0),
        )

        selected = evolution_runtime_module._select_historical_plan_seed_candidates(
            (champion, weak)
        )

        self.assertEqual(selected, (champion,))

    def test_first_workspace_freezes_empty_seed_pool_and_reuses_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "first-run"
            pool = load_or_create_historical_plan_seed_pool(
                workspace=workspace,
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            self.assertEqual(pool.entries, ())
            self.assertTrue((workspace / "seed_pool" / "manifest.json").is_file())

            staged_source = Path(directory) / "staged-run"
            staged_source.mkdir()
            EvolutionRunContract(
                **{**make_contract().__dict__, "run_id": "staged-run"}
            ).freeze(staged_source / "run_contract.json")
            write_json(staged_source / "state.json", {"last_completed_round": 0})
            attempt = staged_source / "experiments" / "round-0001" / "attempts"
            attempt.mkdir(parents=True)
            write_json(attempt / "plan.json", {"metrics": {"binary_f1": 1.0}})

            reused = load_or_create_historical_plan_seed_pool(
                workspace=workspace,
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            self.assertEqual(reused.manifest_hash, pool.manifest_hash)
            self.assertEqual(reused.scanned_workspace_count, 0)

            fresh = build_historical_plan_seed_pool(
                search_root=Path(directory),
                target_workspace=Path(directory) / "second-run",
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            self.assertEqual(fresh.entries, ())
            self.assertEqual(fresh.scanned_workspace_count, 1)
            self.assertEqual(fresh.compatible_workspace_count, 1)

    def test_historical_seed_pool_rejects_manifest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            pool = HistoricalPlanSeedPool(
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            pool.freeze(path)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["manifest"]["scan_summary"]["scanned_workspace_count"] = 1
            write_json(path, envelope)
            with self.assertRaisesRegex(ValidationError, "hash mismatch"):
                HistoricalPlanSeedPool.load_frozen(path)

    def test_contract_round_trips_seed_pool_manifest_hash(self) -> None:
        contract = EvolutionRunContract(
            **{**make_contract().__dict__, "seed_pool_manifest_hash": SHA_A}
        )
        value = contract.to_dict()
        self.assertEqual(value["seed_pool_manifest_hash"], SHA_A)
        self.assertEqual(
            EvolutionRunContract.from_dict(value).seed_pool_manifest_hash,
            SHA_A,
        )
        self.assertNotIn("seed_pool_manifest_hash", make_contract().to_dict())

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

    def test_runtime_exposes_authorized_transcript_adapter(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("alpha_vantage",),
                    allowed_capabilities=("transcripts",),
                    allowed_source_types=("earnings_call",),
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
                environ={"ALPHA_VANTAGE_API_KEY": "alpha-test-key"},
                cycle_id=1,
            )

        self.assertIn("earnings_call", resolver.available_source_types)
        self.assertIn(
            "alpha_vantage",
            [
                adapter.provider
                for adapter in resolver.adapters
                if "earnings_call" in adapter.source_types
            ],
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

    def test_enabled_data_contract_pauses_before_snapshot_without_authorization(self) -> None:
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
            workspace = Path(directory) / "workspace"

            with self.assertRaises(ExternalExecutionNotReady) as context:
                evolution_runtime_module.run_bounded_evolution_cycle(
                    workspace_path=workspace,
                    raw_info_root=Path(directory) / "raw-info",
                    approved_dataset_manifest=Path(directory) / "dataset.json",
                    contract=contract,
                    allow_external=False,
                    allow_data_external=False,
                )

            self.assertEqual(
                context.exception.status,
                "data_external_approval_required",
            )
            self.assertFalse((workspace / "cycle_state.json").exists())
            self.assertFalse((workspace / "evaluation").exists())

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
                    payload={"context": "ticker AN identity disclosed"},
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

    def test_request_token_reservation_fails_before_attempt_and_network(self) -> None:
        class NeverCompleteClient:
            called = False

            def complete(self, _messages, **_kwargs):
                self.called = True
                raise AssertionError("token preflight must run before network")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transport = NeverCompleteClient()
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: transport,
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

            reservation = client.estimate_json_request_tokens(
                system_prompt="Return JSON.",
                payload={"context": "x" * 1_000},
                allow_outcomes=False,
                max_output_tokens=2_000,
            )

            with self.assertRaisesRegex(
                RuntimeBudgetExceeded,
                f"required={reservation}, remaining={reservation - 1}",
            ):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "x" * 1_000},
                    allow_outcomes=False,
                    max_output_tokens=2_000,
                    max_request_tokens=reservation - 1,
                )

            self.assertFalse(transport.called)
            self.assertEqual(ledger.summary["attempt_count"], 0)

    def test_predictor_context_byte_cap_fits_terminal_reserve_on_exact_wire(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "evolution_runtime"
                / "v6_predictor_terminal_reserve_overflow.json"
            ).read_text(encoding="utf-8")
        )
        self.assertGreater(fixture["failure"]["required_tokens"], 36_000)
        compact_context = {
            "context_contract": {
                "kind": "bounded_prediction_projection",
                "max_utf8_bytes": 24_000,
                "complete_trajectory_retained_locally": True,
            },
            "basic_info": {"source_index": [], "data_gaps": []},
            "signal_rounds": [],
            "cited_signal_evidence": [],
            "final_research_state": ResearchState(
                decision=ResearchDecision.FINALIZE
            ).to_dict(),
            "analysis_prompt": "a" * 20_000,
        }
        self.assertLessEqual(
            len(
                json.dumps(
                    compact_context,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ),
            24_000,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = StructuredRoleClient(
                registration=get_model("deepseek-v4-flash"),
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=False,
                environ={},
            )
            predictor = LLMBlindPredictor(client)
            predictor.set_request_token_budget(36_000)

            with self.assertRaises(ExternalRequestPending) as pending:
                predictor.predict(compact_context)

            request = json.loads(
                pending.exception.request_path.read_text(encoding="utf-8")
            )["request"]
            self.assertLessEqual(
                request["wire_request"]["body_bytes"]
                + request["max_output_tokens"],
                36_000,
            )

    def test_structured_client_persists_canonical_production_wire_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = StructuredRoleClient(
                registration=get_model("deepseek-v4-flash"),
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=False,
                environ={},
            )
            payload = {"nested": {"b": 2, "a": 1}, "context": "匿名证据"}

            try:
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload=payload,
                    allow_outcomes=False,
                )
            except ExternalRequestPending as pending:
                envelope = json.loads(pending.request_path.read_text(encoding="utf-8"))
            else:
                self.fail("preview should persist an exact production wire request")

            request = envelope["request"]
            wire = request["wire_request"]
            body = wire["body_utf8"].encode("utf-8")
            self.assertEqual(wire["body_bytes"], len(body))
            self.assertEqual(wire["body_sha256"], hashlib.sha256(body).hexdigest())
            provider_payload = json.loads(wire["body_utf8"])
            provider_user_text = provider_payload["input"][1]["content"][0]["text"]
            self.assertEqual(provider_user_text, request["messages"][1]["content"])
            self.assertEqual(
                provider_user_text,
                '{"context":"匿名证据","nested":{"a":1,"b":2}}',
            )

    def test_structured_client_rejects_wire_drift_before_attempt_reservation(self) -> None:
        from stock_opportunity_agent.llm.openai import PreparedJsonRequest

        class DriftClient:
            def __init__(self, marker: str) -> None:
                self.marker = marker

            def prepare_request(self, messages, **kwargs):
                return PreparedJsonRequest(
                    "https://api.example.test/responses",
                    {
                        "marker": self.marker,
                        "messages": [message.content for message in messages],
                        "kwargs": dict(kwargs),
                    },
                )

            def complete(self, _messages, **_kwargs):
                raise AssertionError("wire drift must fail before network execution")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="drifting-provider",
                provider="openai",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline drift fixture",
                client_factory=lambda settings: DriftClient(
                    "preview" if settings.preview_only else "actual"
                ),
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

            with self.assertRaisesRegex(
                ExternalExecutionNotReady,
                "request bytes changed",
            ):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                )

            self.assertEqual(ledger.summary["attempt_count"], 0)

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
                    raw={
                        "usage": {
                            "input_tokens": 3,
                            "output_tokens": 2,
                            "prompt_cache_hit_tokens": 2,
                            "prompt_cache_miss_tokens": 1,
                        }
                    },
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
            cached = json.loads(
                next((root / "cache" / "responses").glob("*.json")).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(cached["usage"]["prompt_cache_hit_tokens"], 2)
            self.assertEqual(cached["usage"]["prompt_cache_miss_tokens"], 1)

    def test_provider_usage_normalizes_responses_cached_tokens(self) -> None:
        usage = evolution_runtime_module._provider_usage_record(
            {
                "input_tokens": 100,
                "output_tokens": 5,
                "input_tokens_details": {"cached_tokens": 64},
            },
            input_tokens=100,
            output_tokens=5,
            cost=0.01,
        )

        self.assertEqual(usage["prompt_cache_hit_tokens"], 64)
        self.assertEqual(usage["prompt_cache_miss_tokens"], 36)

    def test_structured_client_records_optional_binary_token_scores(self) -> None:
        class RecordingClient:
            supports_token_logprobs = True

            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def complete(self, _messages, **kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                self.kwargs = dict(kwargs)
                return ChatResponse(
                    response_id="response-logprobs",
                    model="fixture-model",
                    output_text='{"decision":"YES"}',
                    raw={
                        "choices": [
                            {
                                "logprobs": {
                                    "content": [
                                        {
                                            "token": '"YES"',
                                            "logprob": math.log(0.6),
                                            "top_logprobs": [
                                                {
                                                    "token": '"YES"',
                                                    "logprob": math.log(0.6),
                                                },
                                                {
                                                    "token": '"NO"',
                                                    "logprob": math.log(0.3),
                                                },
                                            ],
                                        }
                                    ]
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                    },
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

            value, usage, scores = client.complete_json_with_token_scores(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
                decision_field="decision",
                decision_tokens=("YES", "NO"),
            )

            self.assertEqual(value, {"decision": "YES"})
            self.assertEqual(usage.llm_calls, 1)
            self.assertIsNotNone(scores)
            assert scores is not None
            self.assertAlmostEqual(scores.yes_token_probability, 0.6)
            self.assertAlmostEqual(scores.no_token_probability, 0.3)
            self.assertAlmostEqual(scores.decision_margin, 2 / 3)
            self.assertTrue(recording_client.kwargs["logprobs"])
            self.assertEqual(recording_client.kwargs["top_logprobs"], 20)

            _value, cached_usage, cached_scores = (
                client.complete_json_with_token_scores(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                    decision_field="decision",
                    decision_tokens=("YES", "NO"),
                )
            )
            self.assertEqual(cached_usage.llm_calls, 0)
            self.assertEqual(cached_scores, scores)

    def test_structured_client_scores_exact_canonical_binary_token(self) -> None:
        class RecordingClient:
            supports_token_logprobs = True

            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def complete(self, _messages, **kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                self.kwargs = dict(kwargs)
                return ChatResponse(
                    response_id="response-binary-token",
                    model="fixture-model",
                    output_text="NO",
                    raw={
                        "choices": [
                            {
                                "logprobs": {
                                    "content": [
                                        {
                                            "token": "NO",
                                            "logprob": -0.2,
                                            "top_logprobs": [
                                                {"token": "NO", "logprob": -0.2},
                                                {"token": "No", "logprob": -9999.0},
                                                {"token": "YES", "logprob": -1.7},
                                                {"token": "yes", "logprob": -9999.0},
                                            ],
                                        }
                                    ]
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                    },
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

            token, usage, scores = client.complete_binary_token_with_scores(
                stage="blind_predictor_score",
                system_prompt="Return exactly YES or NO.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
                decision_field="decision",
                decision_tokens=("YES", "NO"),
                temperature=1.0,
            )

            self.assertEqual(token, "NO")
            self.assertEqual(usage.llm_calls, 1)
            self.assertIsNotNone(scores)
            assert scores is not None
            self.assertAlmostEqual(scores.yes_token_probability, math.exp(-1.7))
            self.assertAlmostEqual(scores.no_token_probability, math.exp(-0.2))
            self.assertAlmostEqual(
                scores.decision_margin,
                1.0 / (1.0 + math.exp(1.5)),
            )
            self.assertNotIn("response_format", recording_client.kwargs)

    def test_binary_token_scores_reject_provider_sentinel(self) -> None:
        raw = {
            "choices": [
                {
                    "logprobs": {
                        "content": [
                            {
                                "token": "NO",
                                "logprob": 0.0,
                                "top_logprobs": [
                                    {"token": "NO", "logprob": 0.0},
                                    {"token": "YES", "logprob": -9999.0},
                                ],
                            }
                        ]
                    }
                }
            ]
        }

        scores = evolution_runtime_module._extract_decision_token_scores(
            raw,
            parsed={"decision": "NO"},
            decision_field="decision",
            decision_tokens=("YES", "NO"),
        )

        self.assertIsNone(scores)

    def test_structured_client_degrades_when_provider_has_no_logprobs(self) -> None:
        class RecordingClient:
            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def complete(self, _messages, **kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                self.kwargs = dict(kwargs)
                return ChatResponse(
                    response_id="response-no-logprobs",
                    model="fixture-model",
                    output_text='{"decision":"NO"}',
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

            value, _usage, scores = client.complete_json_with_token_scores(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
                decision_field="decision",
                decision_tokens=("YES", "NO"),
            )

            self.assertEqual(value, {"decision": "NO"})
            self.assertIsNone(scores)
            self.assertNotIn("logprobs", recording_client.kwargs)
            self.assertNotIn("top_logprobs", recording_client.kwargs)

            token, binary_usage, binary_scores = (
                client.complete_binary_token_with_scores(
                    stage="blind_predictor_score",
                    system_prompt="Return exactly YES or NO.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                    decision_field="decision",
                    decision_tokens=("YES", "NO"),
                    temperature=1.0,
                )
            )
            self.assertEqual(token, "")
            self.assertEqual(binary_usage.llm_calls, 0)
            self.assertIsNone(binary_scores)
