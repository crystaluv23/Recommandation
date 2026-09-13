#!/usr/bin/env python3
"""Preflight and govern the v1 Information Plan / Signal evolution workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from stock_opportunity_agent.data.raw_info import RawInfoOracle, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    DataAcquisitionPolicy,
    broad_research_data_policy_v1,
)
from stock_opportunity_agent.llm.openai import RetryableOpenAIClientError
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import (
    EvolutionWorkspace,
    EvaluationDatasetInfeasible,
    EvaluationDatasetManager,
    PlanEvaluationConfig,
    RoundPaused,
    RuntimeLimits,
    SharedEvaluationDataUnavailable,
    SlowLoopDataUnavailable,
)
from stock_opportunity_agent.research.scheme_evolution import DEFAULT_EVOLUTION_PRIORS
from stock_opportunity_agent.research.evolution_dashboard import (
    write_evolution_dashboard_bundle,
)
from stock_opportunity_agent.research.evolution_settings import (
    ROLE_OUTPUT_TOKEN_LIMITS,
)
from stock_opportunity_agent.research.evolution_runtime import (
    EvolutionRunContract,
    ExternalExecutionPaused,
    ExternalRequestPending,
    approve_dataset_proposal,
    build_run_contract,
    build_slow_bootstrap_manifest,
    build_slow_history_manifest,
    apply_slow_history_manifest,
    filter_case_price_history,
    inventory_local_evolution_inputs,
    HistoricalPlanSeedPool,
    load_approved_development_dataset,
    load_or_create_historical_plan_seed_pool,
    migrate_legacy_raw_info,
    prepare_dataset_proposal,
    prepare_expanded_dataset_proposal,
    public_model_contract,
    run_bounded_evolution_cycle,
)
from stock_opportunity_agent.signal_library import SignalRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = PROJECT_ROOT / "configs" / "signals_v1.json"
DEFAULT_LOCAL_RUN = (
    PROJECT_ROOT
    / "runs"
    / "cold_start"
    / "formal"
    / "cold-start-formal-openrouter-2026-05-13-clean-universe"
)
DEFAULT_CASES = DEFAULT_LOCAL_RUN / "05_packets" / "historical_cases.json"
DEFAULT_DOCUMENTS = (
    DEFAULT_LOCAL_RUN / "04_documents" / "documents_and_catalysts.json"
)
DEFAULT_ADJUSTED_PRICES = (
    PROJECT_ROOT
    / "runs"
    / "cold_start"
    / "evolution"
    / "input"
    / "abc_adjusted_price_histories_2026-08-02.json"
)
DEFAULT_FULL_PRICE_ARCHIVE = (
    PROJECT_ROOT
    / "runs"
    / "cold_start"
    / "formal"
    / "cold-start-formal-openrouter-2026-05-13"
    / "02_prices"
    / "price_histories.json"
)
DEFAULT_CLEAN_UNIVERSE = (
    DEFAULT_LOCAL_RUN / "01_universe" / "eligible_listings.json"
)
DEFAULT_EVOLUTION_ROOT = PROJECT_ROOT / "runs" / "cold_start" / "evolution"
DEFAULT_EXPANSION_PREDICTION_DATES = (
    "2025-01-31",
    "2025-03-31",
    "2025-05-30",
    "2025-07-31",
    "2025-09-30",
)
DEFAULT_ANCHOR_CASES = PROJECT_ROOT / "configs" / "information_plan_anchor_cases_v1.json"
DEFAULT_FINALIZATION_TOKEN_RESERVE = RuntimeLimits().finalization_token_reserve
DEFAULT_CASE_TOKEN_BUDGET = RuntimeLimits().max_tokens
DEFAULT_MAX_CONSECUTIVE_NO_CANDIDATE_CYCLES = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap, preflight, or govern the bounded dual-loop workspace. "
            "Preflight never performs external calls or opens Locked Test."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init", help="initialize a workspace")
    initialize.add_argument("--workspace", type=Path, required=True)
    initialize.add_argument("--raw-info-root", type=Path, required=True)
    initialize.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    initialize.add_argument(
        "--dashboard-root", type=Path, default=DEFAULT_EVOLUTION_ROOT
    )

    validate = subparsers.add_parser(
        "validate-catalog", help="materialize and validate the seed Signal catalog"
    )
    validate.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)

    status = subparsers.add_parser("status", help="show committed workspace state")
    status.add_argument("--workspace", type=Path, required=True)
    status.add_argument(
        "--dashboard-root", type=Path, default=DEFAULT_EVOLUTION_ROOT
    )

    preflight = subparsers.add_parser(
        "preflight-local",
        help="inventory local point-in-time inputs and registered API routes",
    )
    preflight.add_argument("--workspace", type=Path, required=True)
    preflight.add_argument("--raw-info-root", type=Path, required=True)
    preflight.add_argument("--approved-dataset", type=Path)
    preflight.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    preflight.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    preflight.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    preflight.add_argument(
        "--adjusted-prices", type=Path, default=DEFAULT_ADJUSTED_PRICES
    )
    preflight.add_argument("--judge-model", default="kimi-k3-together")
    preflight.add_argument("--evolution-model", default="openrouter-fusion")

    filter_prices = subparsers.add_parser(
        "filter-local-prices",
        help="stream the large local archive and retain only historical-case symbols",
    )
    filter_prices.add_argument("--workspace", type=Path, required=True)
    filter_prices.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    filter_prices.add_argument(
        "--full-price-archive", type=Path, default=DEFAULT_FULL_PRICE_ARCHIVE
    )

    migrate = subparsers.add_parser(
        "migrate-raw-info",
        help="convert label-free legacy sources into the append-only Raw Info Store",
    )
    migrate.add_argument("--workspace", type=Path, required=True)
    migrate.add_argument("--raw-info-root", type=Path, required=True)
    migrate.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    migrate.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    migrate.add_argument(
        "--adjusted-prices", type=Path, default=DEFAULT_ADJUSTED_PRICES
    )

    prepare_dataset = subparsers.add_parser(
        "prepare-dataset",
        help="recompute six-month labels and write an issuer-disjoint split proposal",
    )
    prepare_dataset.add_argument("--workspace", type=Path, required=True)
    prepare_dataset.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    prepare_dataset.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    prepare_dataset.add_argument(
        "--adjusted-prices", type=Path, default=DEFAULT_ADJUSTED_PRICES
    )
    prepare_dataset.add_argument(
        "--split-seed", default="information-plan-evolution-v1"
    )

    prepare_expanded = subparsers.add_parser(
        "prepare-expanded-dataset",
        help="stream saved full-market prices into a review-only expanded case proposal",
    )
    prepare_expanded.add_argument("--workspace", type=Path, required=True)
    prepare_expanded.add_argument(
        "--universe", type=Path, default=DEFAULT_CLEAN_UNIVERSE
    )
    prepare_expanded.add_argument(
        "--full-price-archive", type=Path, default=DEFAULT_FULL_PRICE_ARCHIVE
    )
    prepare_expanded.add_argument(
        "--prediction-dates",
        nargs="+",
        default=DEFAULT_EXPANSION_PREDICTION_DATES,
        help="shared YYYY-MM-DD case dates; each admitted case must pass its date-local gates",
    )
    prepare_expanded.add_argument(
        "--split-seed", default="expanded-information-plan-evolution-v1"
    )
    prepare_expanded.add_argument(
        "--identity-decisions",
        type=Path,
        help="optional hashed SEC-evidenced CIK corrections/exclusions for a new proposal",
    )
    prepare_expanded.add_argument(
        "--anchor-cases", type=Path, default=DEFAULT_ANCHOR_CASES
    )

    approve_dataset = subparsers.add_parser(
        "approve-dataset",
        help="human-approve one exact reviewed dataset proposal manifest",
    )
    approve_dataset.add_argument("--proposal", type=Path, required=True)
    approve_dataset.add_argument("--proposal-hash", required=True)
    approve_dataset.add_argument("--approved-by", required=True)

    freeze = subparsers.add_parser(
        "freeze-run",
        help="freeze an approved dataset, Signal snapshot, models, limits, and budget",
    )
    freeze.add_argument("--workspace", type=Path, required=True)
    freeze.add_argument("--raw-info-root", type=Path, required=True)
    freeze.add_argument("--approved-dataset", type=Path, required=True)
    freeze.add_argument("--run-id", required=True)
    freeze.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    freeze.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    freeze.add_argument("--adjusted-prices", type=Path, default=DEFAULT_ADJUSTED_PRICES)
    freeze.add_argument("--judge-model", default="kimi-k3-together")
    freeze.add_argument("--evolution-model", default="openrouter-fusion")
    freeze.add_argument("--plan-rounds", type=int, default=2)
    freeze.add_argument(
        "--slow-bootstrap-from",
        type=Path,
        action="append",
        default=[],
        help=(
            "freeze a zero-Fast Slow bootstrap from compatible rejected "
            "workspaces, or from exactly one compatible committed Fast "
            "workspace whose Slow loop has not started"
        ),
    )
    freeze.add_argument(
        "--cycle-mode",
        choices=("fast_then_slow", "slow_bootstrap", "slow_only"),
        help="explicit v8 cycle mode; inferred from the selected history option",
    )
    freeze.add_argument(
        "--slow-history-from",
        type=Path,
        help="one committed source workspace for finite slow_only execution",
    )
    freeze.add_argument("--max-slow-cycles", type=int, default=1)
    freeze.add_argument("--min-new-signals-per-cycle", type=int, default=1)
    freeze.add_argument("--candidates-per-round", type=int, default=3)
    freeze.add_argument("--parent-selection-seed", type=int, default=42)
    freeze.add_argument("--max-external-attempts", type=int, default=2500)
    freeze.add_argument("--max-total-cost", type=float, default=100.0)
    freeze.add_argument(
        "--h1-request-budget", type=int, default=512_000,
        help="H1 canonical request bytes plus output-token reservation",
    )
    freeze.add_argument(
        "--data-external",
        action="store_true",
        help="authorize bounded source-data API acquisition in this frozen run",
    )
    freeze.add_argument("--data-provider", action="append", default=[])
    freeze.add_argument("--data-capability", action="append", default=[])
    freeze.add_argument("--data-source-type", action="append", default=[])
    freeze.add_argument("--max-data-requests-per-cycle", type=int, default=0)
    freeze.add_argument("--max-data-requests-per-run", type=int, default=0)

    run_cycle = subparsers.add_parser(
        "run-cycle",
        help="preflight or execute one frozen bounded Fast/Slow cycle",
    )
    run_cycle.add_argument("--workspace", type=Path, required=True)
    run_cycle.add_argument("--raw-info-root", type=Path, required=True)
    run_cycle.add_argument("--approved-dataset", type=Path, required=True)
    run_cycle.add_argument("--external", action="store_true")
    run_cycle.add_argument("--data-external", action="store_true")
    run_cycle.add_argument("--acknowledge-contract-hash")
    run_cycle.add_argument(
        "--dashboard-root", type=Path, default=DEFAULT_EVOLUTION_ROOT
    )

    run_loop = subparsers.add_parser(
        "run-loop",
        help="continuously start bounded cycles until Ctrl+C or --max-cycles",
    )
    run_loop.add_argument("--workspace", type=Path, required=True)
    run_loop.add_argument("--raw-info-root", type=Path, required=True)
    run_loop.add_argument("--approved-dataset", type=Path, required=True)
    run_loop.add_argument("--external", action="store_true")
    run_loop.add_argument("--data-external", action="store_true")
    run_loop.add_argument("--acknowledge-contract-hash")
    run_loop.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="0 continues until Ctrl+C; positive values stop after that many cycles",
    )
    run_loop.add_argument(
        "--max-consecutive-no-candidate-cycles",
        type=int,
        default=DEFAULT_MAX_CONSECUTIVE_NO_CANDIDATE_CYCLES,
        help=(
            "stop after this many consecutive committed cycles produce no "
            "Mining or Update candidate"
        ),
    )
    run_loop.add_argument(
        "--dashboard-root", type=Path, default=DEFAULT_EVOLUTION_ROOT
    )

    dashboard = subparsers.add_parser(
        "refresh-dashboard",
        help="rebuild the single local evolution dashboard bundle",
    )
    dashboard.add_argument(
        "--dashboard-root", type=Path, default=DEFAULT_EVOLUTION_ROOT
    )

    return parser


def initialize_workspace(
    workspace_path: Path,
    catalog_path: Path,
    raw_info_root: Path,
) -> dict[str, object]:
    workspace = EvolutionWorkspace(workspace_path)
    oracle = RawInfoOracle.load_or_create(raw_info_root)
    raw_info = RawInfoStore(raw_info_root)
    registry = SignalRegistry(
        workspace_path / "signals",
        candidate_root=workspace_path / "signals_candidates",
    )
    installed = registry.install_catalog(catalog_path)
    snapshot = registry.freeze()
    return {
        "workspace": str(workspace.root),
        "raw_info_root": str(raw_info_root),
        "raw_info_oracle_id": oracle.oracle_id,
        "raw_info_inventory_hash": raw_info.inventory_hash,
        "last_completed_round": workspace.last_completed_round,
        "registry_version": registry.version,
        "registry_hash": snapshot.registry_hash,
        "stable_signal_count": len(snapshot.specs),
        "installed_now": installed,
        "categories": list(registry.list_categories()),
        "locked_test_accessed": False,
    }


def validate_catalog(catalog_path: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="signal-catalog-") as directory:
        registry = SignalRegistry(Path(directory) / "signals")
        installed = registry.install_catalog(catalog_path)
        snapshot = registry.freeze()
        if not 10 <= len(snapshot.specs) <= 20:
            raise ValueError("v1 seed catalog must contain 10 to 20 Signals")
        return {
            "catalog": str(catalog_path),
            "valid": True,
            "signal_count": len(snapshot.specs),
            "installed": installed,
            "categories": list(registry.list_categories()),
            "registry_hash": snapshot.registry_hash,
        }


def workspace_status(workspace_path: Path) -> dict[str, object]:
    workspace = EvolutionWorkspace(workspace_path)
    registry_root = workspace_path / "signals"
    registry = SignalRegistry(
        registry_root,
        candidate_root=workspace_path / "signals_candidates",
    )
    archive = workspace.restore_archive()
    contract_path = workspace_path / "run_contract.json"
    if contract_path.is_file():
        contract = EvolutionRunContract.load_frozen(contract_path)
        top_k = int(contract.limits.get("top_k", 3))
        similarity_threshold = float(
            contract.limits.get("similarity_threshold", 0.9)
        )
    else:
        contract = None
        top_k = 3
        similarity_threshold = 0.9
    selected = archive.select_parents(
        top_k=top_k,
        random_k=0,
        similarity_threshold=similarity_threshold,
    ).top
    cycle_state = (
        json.loads(workspace.cycle_state_path.read_text(encoding="utf-8"))
        if workspace.cycle_state_path.is_file()
        else {"last_completed_cycle": 0, "active_cycle": None}
    )
    events = workspace.load_events()
    seed_pool_path = workspace_path / "seed_pool" / "manifest.json"
    seed_pool = (
        HistoricalPlanSeedPool.load_frozen(seed_pool_path)
        if seed_pool_path.is_file()
        else None
    )
    return {
        "workspace": str(workspace.root),
        "last_completed_round": workspace.last_completed_round,
        "last_completed_cycle": int(cycle_state.get("last_completed_cycle", 0)),
        "active_cycle": cycle_state.get("active_cycle"),
        "committed_plan_count": len(archive.records),
        "meta_entries": len(workspace.restore_meta().entries),
        "current_top_k": [
            {
                "plan_id": record.plan_id,
                "binary_f1": record.metrics.binary_f1,
            }
            for record in selected
        ],
        "historical_seed_pool": {
            "manifest_hash": seed_pool.manifest_hash if seed_pool else None,
            "contract_bound": bool(
                seed_pool
                and contract
                and contract.seed_pool_manifest_hash == seed_pool.manifest_hash
            ),
            "seed_count": len(seed_pool.entries) if seed_pool else 0,
            "seed_ids": [entry.seed_id for entry in seed_pool.entries]
            if seed_pool
            else [],
            "source_run_ids": [entry.source_run_id for entry in seed_pool.entries]
            if seed_pool
            else [],
        },
        "trajectory_event_count": len(events),
        "interruption_count": sum(
            event.get("event_type") == "run_interrupted" for event in events
        ),
        "trajectory_path": str(workspace.trajectory_events_path),
        "registry_version": registry.version,
        "stable_signal_count": len(registry.list_signal_cards()),
        "locked_test_accessed": False,
    }


def preflight_local(
    *,
    workspace_path: Path,
    raw_info_root: Path,
    catalog_path: Path,
    cases_path: Path,
    documents_path: Path,
    adjusted_prices_path: Path,
    judge_model: str,
    evolution_model: str,
    approved_dataset_path: Path | None = None,
) -> dict[str, object]:
    """Write a no-network evidence bundle for local data and model readiness."""

    _load_local_env(PROJECT_ROOT / ".env.local")
    workspace_state = initialize_workspace(
        workspace_path, catalog_path, raw_info_root
    )
    inventory = inventory_local_evolution_inputs(
        cases_path=cases_path,
        documents_path=documents_path,
        adjusted_prices_path=adjusted_prices_path,
    )
    models = public_model_contract(
        {
            "judge": judge_model,
            "proposer": evolution_model,
        }
    )
    approved_dataset_summary: dict[str, object] | None = None
    if approved_dataset_path is not None:
        approved_dataset = load_approved_development_dataset(
            approved_dataset_path
        )
        EvaluationDatasetManager(
            workspace_path / "evaluation",
            approved_dataset.evolution_validation,
            approved_dataset.anchor,
            PlanEvaluationConfig(),
        ).validate_feasibility()
        approved_dataset_summary = {
            "manifest_path": str(approved_dataset_path),
            "manifest_hash": hashlib.sha256(
                approved_dataset_path.read_bytes()
            ).hexdigest(),
            "discovery_case_count": len(approved_dataset.discovery),
            "anchor_case_count": len(approved_dataset.anchor),
            "evolution_validation_case_count": len(
                approved_dataset.evolution_validation
            ),
            "locked_test_hash": approved_dataset.locked_test_hash,
            "locked_test_accessed": False,
            "feasible": True,
        }
    preflight_root = workspace_path / "preflight"
    preflight_root.mkdir(parents=True, exist_ok=True)
    inventory_path = preflight_root / "local_inventory.json"
    models_path = preflight_root / "model_availability.json"
    approved_dataset_summary_path = preflight_root / "approved_dataset.json"
    inventory_path.write_text(
        json.dumps(inventory.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    models_path.write_text(
        json.dumps(models, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if approved_dataset_summary is not None:
        approved_dataset_summary_path.write_text(
            json.dumps(approved_dataset_summary, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    keys_available = all(
        bool(value["api_key_available"]) for value in models.values()
    )
    return {
        **workspace_state,
        "inventory_path": str(inventory_path),
        "inventory_hash": inventory.inventory_hash,
        "compatible_case_count": inventory.compatible_case_count,
        "legacy_labels_compatible": False,
        "migration_ready": inventory.migration_ready,
        "migration_blockers": list(inventory.blockers),
        "model_availability_path": str(models_path),
        "api_key_available": {
            role: bool(value["api_key_available"])
            for role, value in models.items()
        },
        "approved_dataset": approved_dataset_summary,
        "approved_dataset_path": (
            str(approved_dataset_summary_path)
            if approved_dataset_summary is not None
            else None
        ),
        "ready_for_freeze": bool(approved_dataset_summary) and keys_available,
        "external_calls": 0,
        "locked_test_accessed": False,
        "ready_for_external_run": False,
    }


def filter_local_prices(
    *,
    workspace_path: Path,
    cases_path: Path,
    full_price_archive_path: Path,
) -> dict[str, object]:
    summary = filter_case_price_history(
        cases_path=cases_path,
        full_price_archive_path=full_price_archive_path,
        output_path=workspace_path / "input" / "case_adjusted_prices.json",
    )
    return summary.to_dict()


def migrate_raw_info(
    *,
    workspace_path: Path,
    raw_info_root: Path,
    cases_path: Path,
    documents_path: Path,
    adjusted_prices_path: Path,
) -> dict[str, object]:
    report = migrate_legacy_raw_info(
        cases_path=cases_path,
        documents_path=documents_path,
        adjusted_prices_path=adjusted_prices_path,
        raw_info_root=raw_info_root,
    )
    preflight_root = workspace_path / "preflight"
    preflight_root.mkdir(parents=True, exist_ok=True)
    report_path = preflight_root / "raw_info_migration.json"
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {**report.to_dict(), "report_path": str(report_path)}


def prepare_dataset(
    *,
    workspace_path: Path,
    cases_path: Path,
    documents_path: Path,
    adjusted_prices_path: Path,
    split_seed: str,
) -> dict[str, object]:
    report = prepare_dataset_proposal(
        cases_path=cases_path,
        documents_path=documents_path,
        adjusted_prices_path=adjusted_prices_path,
        output_root=workspace_path / "dataset_proposal",
        split_seed=split_seed,
    )
    return report.to_dict()


def prepare_expanded_dataset(
    *,
    workspace_path: Path,
    universe_path: Path,
    full_price_archive_path: Path,
    prediction_dates: list[str] | tuple[str, ...],
    split_seed: str,
    identity_decisions_path: Path | None = None,
    anchor_cases_path: Path = DEFAULT_ANCHOR_CASES,
) -> dict[str, object]:
    report = prepare_expanded_dataset_proposal(
        universe_path=universe_path,
        full_price_archive_path=full_price_archive_path,
        output_root=workspace_path / "expanded_dataset_proposal",
        prediction_dates=[date.fromisoformat(value) for value in prediction_dates],
        split_seed=split_seed,
        identity_decisions_path=identity_decisions_path,
        anchor_cases_path=anchor_cases_path,
    )
    return report.to_dict()


def _resolve_data_acquisition_policy(
    *,
    data_external: bool,
    data_providers: tuple[str, ...],
    data_capabilities: tuple[str, ...],
    data_source_types: tuple[str, ...],
    max_data_requests_per_cycle: int,
    max_data_requests_per_run: int,
) -> DataAcquisitionPolicy:
    """Resolve the one-flag broad profile or one complete custom policy."""

    custom_values = any(
        (
            data_providers,
            data_capabilities,
            data_source_types,
            max_data_requests_per_cycle,
            max_data_requests_per_run,
        )
    )
    if data_external and not custom_values:
        return broad_research_data_policy_v1()
    return DataAcquisitionPolicy(
        enabled=data_external,
        allowed_providers=data_providers,
        allowed_capabilities=data_capabilities,
        allowed_source_types=data_source_types,
        max_requests_per_cycle=max_data_requests_per_cycle,
        max_requests_per_run=max_data_requests_per_run,
    )


def freeze_run(
    *,
    workspace_path: Path,
    raw_info_root: Path,
    approved_dataset_path: Path,
    run_id: str,
    cases_path: Path,
    documents_path: Path,
    adjusted_prices_path: Path,
    judge_model: str,
    evolution_model: str,
    plan_rounds: int,
    candidates_per_round: int,
    parent_selection_seed: int,
    max_external_attempts: int,
    max_total_cost: float,
    h1_request_budget: int = 512_000,
    slow_bootstrap_sources: tuple[Path, ...] = (),
    cycle_mode: str | None = None,
    slow_history_from: Path | None = None,
    max_slow_cycles: int = 1,
    min_new_signals_per_cycle: int = 1,
    data_external: bool = False,
    data_providers: tuple[str, ...] = (),
    data_capabilities: tuple[str, ...] = (),
    data_source_types: tuple[str, ...] = (),
    max_data_requests_per_cycle: int = 0,
    max_data_requests_per_run: int = 0,
) -> dict[str, object]:
    if h1_request_budget < 1:
        raise ValueError("H1 request budget must be positive")
    _load_local_env(PROJECT_ROOT / ".env.local")
    oracle = RawInfoOracle.load_or_create(raw_info_root)
    raw_info_store = RawInfoStore(raw_info_root)
    approved_dataset = load_approved_development_dataset(approved_dataset_path)
    requested_data_policy = _resolve_data_acquisition_policy(
        data_external=data_external,
        data_providers=data_providers,
        data_capabilities=data_capabilities,
        data_source_types=data_source_types,
        max_data_requests_per_cycle=max_data_requests_per_cycle,
        max_data_requests_per_run=max_data_requests_per_run,
    )
    if slow_bootstrap_sources and slow_history_from is not None:
        raise ValueError("Slow bootstrap and slow-only history are mutually exclusive")
    inferred_mode = (
        "slow_bootstrap"
        if slow_bootstrap_sources
        else "slow_only"
        if slow_history_from is not None
        else "fast_then_slow"
    )
    resolved_cycle_mode = cycle_mode or inferred_mode
    if resolved_cycle_mode != inferred_mode:
        raise ValueError("cycle mode conflicts with the selected Slow history option")
    effective_plan_rounds = (
        plan_rounds if resolved_cycle_mode == "fast_then_slow" else 0
    )
    EvaluationDatasetManager(
        workspace_path / "evaluation",
        approved_dataset.evolution_validation,
        approved_dataset.anchor,
        PlanEvaluationConfig(),
    ).validate_feasibility()
    contract_path = workspace_path / "run_contract.json"
    if contract_path.exists():
        contract = EvolutionRunContract.load_frozen(contract_path)
        expected_dataset_hash = hashlib.sha256(
            approved_dataset_path.read_bytes()
        ).hexdigest()
        requested_history_hash = None
        if slow_history_from is not None:
            history_path = workspace_path / "slow_history" / "manifest.json"
            if not history_path.is_file():
                raise ValueError(
                    "existing Slow-only workspace is missing history manifest"
                )
            requested_history_hash = str(
                json.loads(history_path.read_text(encoding="utf-8")).get(
                    "manifest_hash", ""
                )
            )
        if (
            contract.run_id != run_id
            or contract.dataset_manifest_hash != expected_dataset_hash
            or contract.models["judge"]["alias"] != judge_model
            or contract.models["proposer"]["alias"] != evolution_model
            or int(contract.limits["plan_rounds_per_signal_cycle"])
            != effective_plan_rounds
            or contract.cycle_mode != resolved_cycle_mode
            or int(contract.limits["candidates_per_round"])
            != candidates_per_round
            or int(contract.limits["parent_selection_seed"])
            != parent_selection_seed
            or contract.max_external_attempts != max_external_attempts
            or contract.max_total_cost != max_total_cost
            or contract.raw_info_oracle_id != oracle.oracle_id
            or contract.data_acquisition != requested_data_policy
            or contract.max_slow_cycles != max_slow_cycles
            or contract.min_new_signals_per_cycle
            != min_new_signals_per_cycle
            or contract.slow_history_manifest_hash != requested_history_hash
        ):
            raise ValueError("existing run contract conflicts with requested freeze scope")
    else:
        inventory = inventory_local_evolution_inputs(
            cases_path=cases_path,
            documents_path=documents_path,
            adjusted_prices_path=adjusted_prices_path,
        )
        dataset_manifest_hash = hashlib.sha256(
            approved_dataset_path.read_bytes()
        ).hexdigest()
        slow_history_manifest_hash = None
        if slow_history_from is not None:
            slow_history_manifest_hash = build_slow_history_manifest(
                workspace=workspace_path,
                source_workspace=slow_history_from,
                dataset_manifest_hash=dataset_manifest_hash,
            )
            history_envelope = json.loads(
                (workspace_path / "slow_history" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            apply_slow_history_manifest(
                workspace=workspace_path,
                manifest=dict(history_envelope["manifest"]),
            )
        registry = SignalRegistry(
            workspace_path / "signals",
            candidate_root=workspace_path / "signals_candidates",
        )
        snapshot = registry.freeze()
        evaluation_contract = PlanEvaluationConfig().to_dict()
        seed_pool = load_or_create_historical_plan_seed_pool(
            workspace=workspace_path,
            dataset_manifest_hash=dataset_manifest_hash,
            evaluation_contract=evaluation_contract,
        )
        slow_bootstrap_manifest_hash = None
        if slow_bootstrap_sources:
            slow_bootstrap_manifest_hash = build_slow_bootstrap_manifest(
                workspace=workspace_path,
                source_workspaces=slow_bootstrap_sources,
                dataset=approved_dataset,
                signal_snapshot=snapshot,
                evaluation_contract=evaluation_contract,
            )
        contract = build_run_contract(
            run_id=run_id,
            dataset_manifest_path=approved_dataset_path,
            inventory=inventory,
            raw_info_oracle=oracle,
            raw_info_inventory_hash=raw_info_store.inventory_hash,
            initial_signal_registry_version=registry.version,
            initial_signal_registry_hash=snapshot.registry_hash,
            priors={
                "reflect_round": DEFAULT_EVOLUTION_PRIORS.reflect_round,
                "propose_plan": DEFAULT_EVOLUTION_PRIORS.propose_plan,
                "mine_signal": DEFAULT_EVOLUTION_PRIORS.mine_signal,
                "update_signal": DEFAULT_EVOLUTION_PRIORS.update_signal,
            },
            role_aliases={"judge": judge_model, "proposer": evolution_model},
            project_root=PROJECT_ROOT,
            limits={
                "plan_rounds_per_signal_cycle": effective_plan_rounds,
                "candidates_per_round": candidates_per_round,
                "top_k": 3,
                "random_k": 2,
                "similarity_threshold": 0.9,
                "parent_selection_seed": parent_selection_seed,
                "plan_proposal_temperature": 1.0,
                "judge_temperature": 0.0,
                "max_signal_rounds": 5,
                "max_signal_calls": 20,
                "max_signals_per_round": 4,
                "max_llm_signals_per_round": 2,
                "max_llm_calls": 40,
                "max_tokens": DEFAULT_CASE_TOKEN_BUDGET,
                "h1_request_budget": h1_request_budget,
                "finalization_token_reserve": DEFAULT_FINALIZATION_TOKEN_RESERVE,
                "basic_info_context_chars": 32_000,
                "signal_batch_context_chars": 32_000,
                "predictor_context_bytes": 24_000,
                "posthoc_context_chars": 24_000,
                "meta_context_chars": 48_000,
                "role_output_tokens": {
                    **ROLE_OUTPUT_TOKEN_LIMITS,
                    "controller": 2_000,
                },
                "max_case_cost": 5.0,
                "max_agent_steps": 20,
                "max_structured_corrections": 2,
                "evaluation": evaluation_contract,
            },
            max_external_attempts=max_external_attempts,
            max_total_cost=max_total_cost,
            seed_pool_manifest_hash=seed_pool.manifest_hash,
            cycle_mode=resolved_cycle_mode,
            slow_bootstrap_manifest_hash=slow_bootstrap_manifest_hash,
            slow_history_manifest_hash=slow_history_manifest_hash,
            max_slow_cycles=max_slow_cycles,
            min_new_signals_per_cycle=min_new_signals_per_cycle,
            data_acquisition=requested_data_policy,
        )
        contract.freeze(contract_path)
    seed_pool = None
    if contract.seed_pool_manifest_hash is not None:
        seed_pool = HistoricalPlanSeedPool.load_frozen(
            workspace_path / "seed_pool" / "manifest.json"
        )
        if seed_pool.manifest_hash != contract.seed_pool_manifest_hash:
            raise ValueError("historical Plan seed pool differs from frozen contract")
    return {
        "run_contract": str(contract_path),
        "contract_hash": contract.contract_hash,
        "run_id": contract.run_id,
        "dataset_manifest_hash": contract.dataset_manifest_hash,
        "raw_info_oracle_id": contract.raw_info_oracle_id,
        "raw_info_inventory_hash": contract.raw_info_inventory_hash,
        "initial_signal_registry_hash": contract.initial_signal_registry_hash,
        "models": contract.models,
        "max_external_attempts": contract.max_external_attempts,
        "max_total_cost": contract.max_total_cost,
        "cycle_mode": contract.cycle_mode,
        "slow_bootstrap_manifest_hash": contract.slow_bootstrap_manifest_hash,
        "slow_history_manifest_hash": contract.slow_history_manifest_hash,
        "max_slow_cycles": contract.max_slow_cycles,
        "min_new_signals_per_cycle": contract.min_new_signals_per_cycle,
        "historical_seed_pool": {
            "manifest_hash": contract.seed_pool_manifest_hash,
            "seed_count": len(seed_pool.entries) if seed_pool else 0,
            "source_run_ids": [entry.source_run_id for entry in seed_pool.entries]
            if seed_pool
            else [],
        },
        "data_acquisition": contract.data_acquisition.to_dict(),
        "locked_test_accessed": False,
        "external_calls": 0,
    }


def run_cycle_command(
    *,
    workspace_path: Path,
    raw_info_root: Path,
    approved_dataset_path: Path,
    external: bool,
    acknowledged_contract_hash: str | None,
    data_external: bool = False,
    on_progress=None,
) -> dict[str, object]:
    _load_local_env(PROJECT_ROOT / ".env.local")
    contract = EvolutionRunContract.load_frozen(workspace_path / "run_contract.json")
    if not contract.executable:
        return {
            "status": "legacy_contract_read_only",
            "contract_hash": contract.contract_hash,
            "schema_version": contract.schema_version,
            "external_calls": 0,
            "locked_test_accessed": False,
        }
    try:
        result = run_bounded_evolution_cycle(
            workspace_path=workspace_path,
            raw_info_root=raw_info_root,
            approved_dataset_manifest=approved_dataset_path,
            contract=contract,
            allow_external=external,
            allow_data_external=data_external,
            acknowledged_contract_hash=acknowledged_contract_hash,
            on_progress=on_progress,
        )
    except ExternalRequestPending as pending:
        workspace = EvolutionWorkspace(workspace_path)
        pause_event = workspace.append_event(
            "cycle_paused",
            {
                "reason": "exact_request_pending_external_approval",
                "request_hash": pending.request_hash,
                "last_completed_round": workspace.last_completed_round,
                "last_completed_cycle": workspace.last_completed_cycle,
            },
        )
        if on_progress is not None:
            on_progress(pause_event)
        return {
            "status": "exact_request_pending_external_approval",
            "request_hash": pending.request_hash,
            "request_path": str(pending.request_path),
            "contract_hash": contract.contract_hash,
            "external_calls": 0,
            "locked_test_accessed": False,
            "last_completed_round": workspace.last_completed_round,
            "last_completed_cycle": workspace.last_completed_cycle,
            "trajectory_path": str(workspace.trajectory_events_path),
        }
    except ExternalExecutionPaused as paused:
        workspace = EvolutionWorkspace(workspace_path)
        pause_event = workspace.append_event(
            "cycle_paused",
            {
                "reason": paused.status,
                "message": paused.message,
                "last_completed_round": workspace.last_completed_round,
                "last_completed_cycle": workspace.last_completed_cycle,
            },
        )
        if on_progress is not None:
            on_progress(pause_event)
        return {
            **paused.to_dict(),
            "contract_hash": contract.contract_hash,
            "external_calls": 0,
            "locked_test_accessed": False,
            "last_completed_round": workspace.last_completed_round,
            "last_completed_cycle": workspace.last_completed_cycle,
            "trajectory_path": str(workspace.trajectory_events_path),
        }
    except EvaluationDatasetInfeasible as infeasible:
        return {
            **infeasible.to_dict(),
            "contract_hash": contract.contract_hash,
            "external_calls": 0,
            "locked_test_accessed": False,
        }
    except RoundPaused as paused:
        workspace = EvolutionWorkspace(workspace_path)
        return {
            "status": "round_rejected",
            "round_id": paused.round_id,
            "reason": paused.reason,
            "checkpoint_ref": paused.checkpoint_ref,
            "last_completed_round": workspace.last_completed_round,
            "last_completed_cycle": workspace.last_completed_cycle,
            "locked_test_accessed": False,
        }
    workspace = EvolutionWorkspace(workspace_path)
    return {
        "status": "cycle_completed",
        "contract_hash": contract.contract_hash,
        "completed_plan_rounds": [item.round_id for item in result.plan_rounds],
        "validated_signal_candidates": dict(
            result.signal_evolution.validated_candidates
        ),
        "mined_signal_candidates": list(
            result.signal_evolution.mined_candidates
        ),
        "updated_signal_candidates": list(
            result.signal_evolution.updated_candidates
        ),
        "promoted_signals": list(result.signal_evolution.promoted),
        "new_candidate_count": result.signal_evolution.new_candidate_count,
        "new_validated_signal_count": (
            result.signal_evolution.new_validated_signal_count
        ),
        "new_promoted_signal_count": (
            result.signal_evolution.new_promoted_signal_count
        ),
        "updated_signal_count": result.signal_evolution.updated_signal_count,
        "signal_goal_status": result.signal_evolution.signal_goal_status,
        "search_input_fingerprint": (
            result.signal_evolution.search_input_fingerprint
        ),
        "input_registry_version": result.signal_evolution.input_registry_version,
        "input_registry_hash": result.signal_evolution.input_registry_hash,
        "output_registry_version": result.signal_evolution.output_registry_version,
        "output_registry_hash": result.signal_evolution.output_registry_hash,
        "last_completed_round": workspace.last_completed_round,
        "last_completed_cycle": workspace.last_completed_cycle,
        "trajectory_path": str(workspace.trajectory_events_path),
        "locked_test_accessed": False,
    }


def _no_candidate_cycle_category(validation: dict[str, object]) -> list[str]:
    """Classify one committed no-candidate Slow result without changing state."""

    categories: set[str] = set()
    rejected = validation.get("rejected", {})
    if isinstance(rejected, dict) and any(
        str(key).startswith("slow_loop:") for key in rejected
    ):
        categories.add("technical_failure")
    audits = validation.get("agent_audits", {})
    mining = audits.get("mining_pipeline", {}) if isinstance(audits, dict) else {}
    if isinstance(mining, dict):
        hypothesis = (
            mining.get("hypothesis", {})
            if mining.get("track") == "hypothesis_then_exploration_fallback"
            else mining
        )
        statuses = {
            str(item.get("status", ""))
            for item in (mining, hypothesis, mining.get("exploration", {}))
            if isinstance(item, dict)
        }
        if "no_testable_hypothesis" in statuses:
            categories.add("no_testable_hypothesis")
        if "unchanged_h1_work_suppressed" in statuses:
            categories.add("unchanged_work")
        if any("failed" in status for status in statuses):
            categories.add("technical_failure")
        if isinstance(hypothesis, dict) and hypothesis.get("evidence_unavailable"):
            categories.add("evidence_unavailable")
        work_rows = (
            hypothesis.get("hypothesis_work", ())
            if isinstance(hypothesis, dict)
            else ()
        )
        if isinstance(work_rows, list) and any(
            isinstance(item, dict)
            and item.get("status") == "unchanged_work_suppressed"
            for item in work_rows
        ):
            categories.add("unchanged_work")
    if validation.get("refined_hypotheses"):
        categories.add("refinement_without_candidate")
    update = audits.get("update_pipeline", {}) if isinstance(audits, dict) else {}
    if isinstance(update, dict) and update.get("disposition") == "no_actionable_target":
        categories.add("no_actionable_update")
    return sorted(categories or {"no_candidate"})


def _committed_no_candidate_diagnosis(
    workspace_path: Path,
) -> dict[str, object]:
    """Describe the latest committed run of cycles that produced no candidate."""

    workspace = EvolutionWorkspace(workspace_path)
    rows: list[dict[str, object]] = []
    unmet_rows: list[int] = []
    for cycle_id in range(workspace.last_completed_cycle, 0, -1):
        path = (
            workspace.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_validation.json"
        )
        if not path.is_file():
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(
                f"cannot read committed Slow validation: {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValidationError(
                f"committed Slow validation must be an object: {path}"
            )
        validation = payload.get("validation", {})
        if not isinstance(validation, dict):
            raise ValidationError(
                f"committed Slow validation must be an object: {path}"
            )
        mined_refs = validation.get("mined_candidates", [])
        input_refs = validation.get("input_signal_refs", [])
        if not isinstance(mined_refs, list):
            raise ValidationError(
                f"mined_candidates must be an array: {path}"
            )
        if not isinstance(input_refs, list):
            raise ValidationError(
                f"input_signal_refs must be an array: {path}"
            )
        input_ids = {str(ref).rsplit(":v", 1)[0] for ref in input_refs}
        new_candidate_count = int(
            validation.get(
                "new_candidate_count",
                sum(
                    str(ref).rsplit(":v", 1)[0] not in input_ids
                    for ref in mined_refs
                ),
            )
        )
        if new_candidate_count > 0:
            break
        rows.append(
            {
                "cycle_id": cycle_id,
                "search_input_fingerprint": str(
                    validation.get("search_input_fingerprint", "")
                ),
                "categories": _no_candidate_cycle_category(validation),
            }
        )
    rows.reverse()
    for cycle_id in range(workspace.last_completed_cycle, 0, -1):
        result_path = (
            workspace.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_result.json"
        )
        result_payload = (
            json.loads(result_path.read_text(encoding="utf-8"))
            if result_path.is_file()
            else {}
        )
        result = result_payload.get("result", {})
        goal_status = (
            str(result.get("signal_goal_status", "unmet"))
            if isinstance(result, dict)
            else "unmet"
        )
        if goal_status != "unmet":
            break
        unmet_rows.append(cycle_id)
    fingerprints = [
        str(row["search_input_fingerprint"])
        for row in rows
        if row["search_input_fingerprint"]
    ]
    return {
        "consecutive_no_candidate_cycles": len(rows),
        "consecutive_signal_goal_unmet_cycles": len(unmet_rows),
        "signal_goal_unmet_cycle_ids": list(reversed(unmet_rows)),
        "cycle_ids": [int(row["cycle_id"]) for row in rows],
        "search_input_fingerprints": fingerprints,
        "search_input_changed_within_streak": len(set(fingerprints)) > 1,
        "categories": sorted(
            {
                str(category)
                for row in rows
                for category in row["categories"]
            }
        ),
    }


def _no_candidate_limit_result(
    *,
    workspace_path: Path,
    diagnosis: dict[str, object],
    limit: int,
    completed_cycles: list[int],
    on_progress=None,
) -> dict[str, object]:
    """Persist and return one supervisor stop without moving cycle pointers."""

    workspace = EvolutionWorkspace(workspace_path)
    limit_basis = (
        "signal_goal_unmet"
        if int(diagnosis.get("consecutive_signal_goal_unmet_cycles", 0)) >= limit
        else "no_new_candidate"
    )
    event = workspace.append_event(
        "no_candidate_search_limit_reached",
        {
            **diagnosis,
            "limit": limit,
            "limit_basis": limit_basis,
            "last_completed_round": workspace.last_completed_round,
            "last_completed_cycle": workspace.last_completed_cycle,
        },
    )
    if on_progress is not None:
        on_progress(event)
    return {
        "status": "no_candidate_search_limit_reached",
        "supervisor_status": "stopped_for_diagnosis",
        "completed_cycles_this_invocation": completed_cycles,
        "limit_basis": limit_basis,
        "no_candidate_diagnosis": diagnosis,
        **workspace_status(workspace_path),
    }


def run_loop_command(
    *,
    workspace_path: Path,
    raw_info_root: Path,
    approved_dataset_path: Path,
    external: bool,
    acknowledged_contract_hash: str | None,
    max_cycles: int,
    max_consecutive_no_candidate_cycles: int = (
        DEFAULT_MAX_CONSECUTIVE_NO_CANDIDATE_CYCLES
    ),
    data_external: bool = False,
    on_progress=None,
) -> dict[str, object]:
    """Run bounded cycles until an operator or no-candidate limit is reached."""

    if max_cycles < 0:
        raise ValueError("--max-cycles must be non-negative")
    if max_consecutive_no_candidate_cycles < 1:
        raise ValueError(
            "--max-consecutive-no-candidate-cycles must be positive"
        )
    completed: list[int] = []
    diagnosis = _committed_no_candidate_diagnosis(workspace_path)
    if max(
        int(diagnosis["consecutive_no_candidate_cycles"]),
        int(diagnosis.get("consecutive_signal_goal_unmet_cycles", 0)),
    ) >= max_consecutive_no_candidate_cycles:
        return _no_candidate_limit_result(
            workspace_path=workspace_path,
            diagnosis=diagnosis,
            limit=max_consecutive_no_candidate_cycles,
            completed_cycles=completed,
            on_progress=on_progress,
        )
    while max_cycles == 0 or len(completed) < max_cycles:
        result = run_cycle_command(
            workspace_path=workspace_path,
            raw_info_root=raw_info_root,
            approved_dataset_path=approved_dataset_path,
            external=external,
            data_external=data_external,
            acknowledged_contract_hash=acknowledged_contract_hash,
            on_progress=on_progress,
        )
        if result["status"] != "cycle_completed":
            return {
                **result,
                "supervisor_status": "paused",
                "completed_cycles_this_invocation": completed,
            }
        completed.append(int(result["last_completed_cycle"]))
        diagnosis = _committed_no_candidate_diagnosis(workspace_path)
        if max(
            int(diagnosis["consecutive_no_candidate_cycles"]),
            int(diagnosis.get("consecutive_signal_goal_unmet_cycles", 0)),
        ) >= max_consecutive_no_candidate_cycles:
            return _no_candidate_limit_result(
                workspace_path=workspace_path,
                diagnosis=diagnosis,
                limit=max_consecutive_no_candidate_cycles,
                completed_cycles=completed,
                on_progress=on_progress,
            )
    final = workspace_status(workspace_path)
    return {
        "status": "loop_limit_reached",
        "supervisor_status": "completed_requested_cycles",
        "completed_cycles_this_invocation": completed,
        **final,
    }


def _load_local_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def refresh_dashboard(dashboard_root: Path) -> dict[str, object]:
    bundle = write_evolution_dashboard_bundle(dashboard_root)
    return {
        "dashboard": str(dashboard_root / "evolution_dashboard.html"),
        "dashboard_run_count": len(bundle["runs"]),
        "dashboard_skipped_run_count": len(bundle["skipped_runs"]),
    }


def _print_progress(event: dict[str, object], *, stream=None) -> None:
    """Render one secret-free progress event immediately for a human operator."""

    output = stream or sys.stderr
    at = str(event.get("at") or "")
    clock = at[11:19] if len(at) >= 19 else "--:--:--"
    event_type = str(event.get("event_type") or "progress")
    cycle = event.get("cycle_id")
    round_id = event.get("round_id")
    scope = []
    if cycle is not None:
        scope.append(f"cycle {cycle}")
    if round_id is not None:
        scope.append(f"round {round_id}")
    prefix = f"[{clock}]" + (f" [{' / '.join(scope)}]" if scope else "")

    if event_type in {"cycle_started", "cycle_resumed"}:
        verb = "恢复" if event_type == "cycle_resumed" else "开始"
        message = (
            f"{verb} cycle：Fast 已完成 "
            f"{event.get('completed_plan_rounds', 0)}/"
            f"{event.get('target_plan_rounds', 0)}，阶段 {event.get('phase')}"
        )
    elif event_type == "parents_selected":
        message = (
            f"父方案 Top-K={event.get('top_parent_ids', [])}，"
            f"随机探索={event.get('random_parent_ids', [])}，"
            f"seed={event.get('seed_parent_ids', [])}"
        )
    elif event_type == "candidate_proposed":
        summary = dict(event.get("plan_summary") or {})
        message = (
            f"采样方案 {event.get('candidate_index')}/"
            f"{event.get('candidate_count')}：{event.get('plan_id')}；"
            "Basic Info="
            f"{summary.get('basic_info_requests', summary.get('basic_info_fields', []))}；"
            f"H_init={summary.get('initial_research', '')}"
        )
    elif event_type in {"case_started", "case_completed", "case_trajectory_reused"}:
        action = {
            "case_started": "开始 case",
            "case_completed": "完成 case",
            "case_trajectory_reused": "恢复已完成 case",
        }[event_type]
        message = (
            f"{action} {event.get('case_index')}/{event.get('case_count')} "
            f"{event.get('case_id')} · Plan {event.get('plan_id')}"
        )
        if event_type == "case_completed":
            message += (
                f" · stop={event.get('stop_reason')} · "
                f"LLM calls={event.get('llm_calls')}"
            )
    elif event_type == "candidate_scored":
        metrics = dict(event.get("metrics") or {})
        message = (
            f"候选评分 {event.get('plan_id')}："
            f"F1={float(metrics.get('binary_f1', 0.0)):.3f}，"
            f"precision={float(metrics.get('binary_precision', 0.0)):.3f}，"
            f"recall={float(metrics.get('binary_recall', 0.0)):.3f}"
        )
    elif event_type == "round_committed":
        message = (
            f"轮次 checkpoint 已提交；候选={event.get('candidate_scores', [])}；"
            f"当前 Top-K={event.get('top_k', [])}"
        )
    elif event_type in {
        "request_ready",
        "request_cache_hit",
        "request_pending_external_approval",
        "external_call_started",
        "external_call_completed",
        "external_call_failed",
    }:
        message = (
            f"{event_type} · stage={event.get('stage')} · "
            f"model={event.get('model_alias')}"
        )
        if event.get("attempt_id") is not None:
            message += f" · attempt={event.get('attempt_id')}"
    elif event_type == "slow_loop_started":
        message = event_type
    elif event_type in {
        "slow_loop_completed",
        "slow_loop_result_reused",
        "slow_loop_result_staged",
    }:
        message = (
            f"{event_type} · validated="
            f"{event.get('validated_candidates', {})} · "
            f"promoted={event.get('promoted', [])}"
        )
    elif event_type in {"cycle_committed", "cycle_paused", "run_interrupted"}:
        message = (
            f"{event_type} · committed round="
            f"{event.get('last_completed_round')} · committed cycle="
            f"{event.get('last_completed_cycle')}"
        )
    else:
        message = event_type
    print(f"{prefix} {message}", file=output, flush=True)


def _progress_handler(dashboard_root: Path, *, stream=None):
    """Print every event and refresh the derived dashboard at durable boundaries."""

    refresh_events = {
        "round_committed",
        "cycle_committed",
        "cycle_paused",
        "run_interrupted",
    }

    def handle(event: dict[str, object]) -> None:
        _print_progress(event, stream=stream)
        if event.get("event_type") not in refresh_events:
            return
        try:
            refresh_dashboard(dashboard_root)
        except (OSError, ValueError, ValidationError) as exc:
            print(
                f"[dashboard] refresh failed: {type(exc).__name__}: {exc}",
                file=stream or sys.stderr,
                flush=True,
            )

    return handle


def _interrupt_result(workspace_path: Path, *, on_progress=None) -> dict[str, object]:
    workspace = EvolutionWorkspace(workspace_path)
    cycle_state = (
        json.loads(workspace.cycle_state_path.read_text(encoding="utf-8"))
        if workspace.cycle_state_path.is_file()
        else {"last_completed_cycle": 0, "active_cycle": None}
    )
    event = workspace.append_event(
        "run_interrupted",
        {
            "last_completed_round": workspace.last_completed_round,
            "last_completed_cycle": int(
                cycle_state.get("last_completed_cycle", 0)
            ),
            "active_cycle": cycle_state.get("active_cycle"),
            "resume_command": "rerun the same command with the same contract",
        },
    )
    if on_progress is not None:
        on_progress(event)
    return {
        "status": "interrupted_resumable",
        "workspace": str(workspace_path),
        "last_completed_round": workspace.last_completed_round,
        "last_completed_cycle": int(cycle_state.get("last_completed_cycle", 0)),
        "active_cycle": cycle_state.get("active_cycle"),
        "trajectory_path": str(workspace.trajectory_events_path),
        "resume": "rerun the same command with the same frozen contract",
        "locked_test_accessed": False,
    }


def _retryable_external_error_result(
    workspace_path: Path,
    error: RetryableOpenAIClientError,
    *,
    on_progress=None,
) -> dict[str, object]:
    """Record a temporary provider failure for exact process-level resume."""

    workspace = EvolutionWorkspace(workspace_path)
    event = workspace.append_event(
        "retryable_external_error",
        {
            "error_type": type(error).__name__,
            "message": str(error),
            "resume": "rerun the same command with the same frozen contract",
        },
    )
    if on_progress is not None:
        on_progress(event)
    return {
        "status": "retryable_external_error",
        "workspace": str(workspace_path),
        "error_type": type(error).__name__,
        "message": str(error),
        "resume": "rerun the same command with the same frozen contract",
        "locked_test_accessed": False,
    }


def _shared_evaluation_data_result(
    workspace_path: Path,
    unavailable: SharedEvaluationDataUnavailable,
    *,
    on_progress=None,
) -> dict[str, object]:
    """Record a non-fitness shared-data pause at the process boundary."""

    workspace = EvolutionWorkspace(workspace_path)
    event = workspace.append_event(
        "cycle_paused",
        {
            "reason": "shared_evaluation_data_unavailable",
            "round_id": unavailable.round_id,
            "case_reasons": dict(unavailable.case_reasons),
            "retryable": unavailable.retryable,
            "checkpoint_ref": unavailable.checkpoint_ref,
            "last_completed_round": workspace.last_completed_round,
            "last_completed_cycle": workspace.last_completed_cycle,
        },
    )
    if on_progress is not None:
        on_progress(event)
    return {
        **unavailable.to_dict(),
        "workspace": str(workspace_path),
        "last_completed_round": workspace.last_completed_round,
        "last_completed_cycle": workspace.last_completed_cycle,
        "resume": "rerun the same command with the same frozen contract",
        "locked_test_accessed": False,
    }


def _slow_loop_data_result(
    workspace_path: Path,
    unavailable: SlowLoopDataUnavailable,
    *,
    on_progress=None,
) -> dict[str, object]:
    """Record a retryable Slow data pause without candidate semantics."""

    workspace = EvolutionWorkspace(workspace_path)
    event = workspace.append_event(
        "cycle_paused",
        {
            "reason": "slow_loop_data_unavailable",
            "case_ref": unavailable.case_ref,
            "provider_reason": unavailable.reason,
            "retryable": True,
            "last_completed_round": workspace.last_completed_round,
            "last_completed_cycle": workspace.last_completed_cycle,
        },
    )
    if on_progress is not None:
        on_progress(event)
    return {
        "status": "slow_loop_data_unavailable",
        "workspace": str(workspace_path),
        "case_ref": unavailable.case_ref,
        "provider_reason": unavailable.reason,
        "retryable": True,
        "last_completed_round": workspace.last_completed_round,
        "last_completed_cycle": workspace.last_completed_cycle,
        "resume": "rerun the same command with the same frozen contract",
        "locked_test_accessed": False,
    }


def main() -> int:
    args = build_parser().parse_args()
    exit_code = 0
    progress = (
        _progress_handler(args.dashboard_root)
        if args.command in {"run-cycle", "run-loop"}
        else None
    )
    try:
        if args.command == "init":
            result = initialize_workspace(
                args.workspace, args.catalog, args.raw_info_root
            )
        elif args.command == "validate-catalog":
            result = validate_catalog(args.catalog)
        elif args.command == "preflight-local":
            result = preflight_local(
                workspace_path=args.workspace,
                raw_info_root=args.raw_info_root,
                catalog_path=args.catalog,
                cases_path=args.cases,
                documents_path=args.documents,
                adjusted_prices_path=args.adjusted_prices,
                judge_model=args.judge_model,
                evolution_model=args.evolution_model,
                approved_dataset_path=args.approved_dataset,
            )
        elif args.command == "filter-local-prices":
            result = filter_local_prices(
                workspace_path=args.workspace,
                cases_path=args.cases,
                full_price_archive_path=args.full_price_archive,
            )
        elif args.command == "migrate-raw-info":
            result = migrate_raw_info(
                workspace_path=args.workspace,
                raw_info_root=args.raw_info_root,
                cases_path=args.cases,
                documents_path=args.documents,
                adjusted_prices_path=args.adjusted_prices,
            )
        elif args.command == "prepare-dataset":
            result = prepare_dataset(
                workspace_path=args.workspace,
                cases_path=args.cases,
                documents_path=args.documents,
                adjusted_prices_path=args.adjusted_prices,
                split_seed=args.split_seed,
            )
        elif args.command == "prepare-expanded-dataset":
            result = prepare_expanded_dataset(
                workspace_path=args.workspace,
                universe_path=args.universe,
                full_price_archive_path=args.full_price_archive,
                prediction_dates=args.prediction_dates,
                split_seed=args.split_seed,
                identity_decisions_path=args.identity_decisions,
                anchor_cases_path=args.anchor_cases,
            )
        elif args.command == "approve-dataset":
            approved_path = approve_dataset_proposal(
                proposal_manifest_path=args.proposal,
                expected_proposal_hash=args.proposal_hash,
                approved_by=args.approved_by,
            )
            result = {
                "approved_manifest": str(approved_path),
                "approved_manifest_hash": hashlib.sha256(
                    approved_path.read_bytes()
                ).hexdigest(),
                "approval_status": "human_approved",
            }
        elif args.command == "freeze-run":
            result = freeze_run(
                workspace_path=args.workspace,
                raw_info_root=args.raw_info_root,
                approved_dataset_path=args.approved_dataset,
                run_id=args.run_id,
                cases_path=args.cases,
                documents_path=args.documents,
                adjusted_prices_path=args.adjusted_prices,
                judge_model=args.judge_model,
                evolution_model=args.evolution_model,
                plan_rounds=args.plan_rounds,
                candidates_per_round=args.candidates_per_round,
                parent_selection_seed=args.parent_selection_seed,
                max_external_attempts=args.max_external_attempts,
                max_total_cost=args.max_total_cost,
                h1_request_budget=args.h1_request_budget,
                slow_bootstrap_sources=tuple(args.slow_bootstrap_from),
                cycle_mode=args.cycle_mode,
                slow_history_from=args.slow_history_from,
                max_slow_cycles=args.max_slow_cycles,
                min_new_signals_per_cycle=args.min_new_signals_per_cycle,
                data_external=args.data_external,
                data_providers=tuple(args.data_provider),
                data_capabilities=tuple(args.data_capability),
                data_source_types=tuple(args.data_source_type),
                max_data_requests_per_cycle=args.max_data_requests_per_cycle,
                max_data_requests_per_run=args.max_data_requests_per_run,
            )
        elif args.command == "run-cycle":
            result = run_cycle_command(
                workspace_path=args.workspace,
                raw_info_root=args.raw_info_root,
                approved_dataset_path=args.approved_dataset,
                external=args.external,
                data_external=args.data_external,
                acknowledged_contract_hash=args.acknowledge_contract_hash,
                on_progress=progress,
            )
        elif args.command == "run-loop":
            result = run_loop_command(
                workspace_path=args.workspace,
                raw_info_root=args.raw_info_root,
                approved_dataset_path=args.approved_dataset,
                external=args.external,
                data_external=args.data_external,
                acknowledged_contract_hash=args.acknowledge_contract_hash,
                max_cycles=args.max_cycles,
                max_consecutive_no_candidate_cycles=(
                    args.max_consecutive_no_candidate_cycles
                ),
                on_progress=progress,
            )
        elif args.command == "refresh-dashboard":
            result = refresh_dashboard(args.dashboard_root)
        else:
            result = workspace_status(args.workspace)
    except KeyboardInterrupt:
        if args.command not in {"run-cycle", "run-loop"}:
            raise
        result = _interrupt_result(args.workspace, on_progress=progress)
        exit_code = 130
    except EvaluationDatasetInfeasible as infeasible:
        result = {
            **infeasible.to_dict(),
            "external_calls": 0,
            "locked_test_accessed": False,
        }
        exit_code = 2
    except SharedEvaluationDataUnavailable as unavailable:
        if args.command not in {"run-cycle", "run-loop"}:
            raise
        result = _shared_evaluation_data_result(
            args.workspace,
            unavailable,
            on_progress=progress,
        )
        exit_code = 75 if unavailable.retryable else 2
    except SlowLoopDataUnavailable as unavailable:
        if args.command not in {"run-cycle", "run-loop"}:
            raise
        result = _slow_loop_data_result(
            args.workspace,
            unavailable,
            on_progress=progress,
        )
        exit_code = 75
    except RetryableOpenAIClientError as exc:
        if args.command not in {"run-cycle", "run-loop"}:
            raise
        result = _retryable_external_error_result(
            args.workspace,
            exc,
            on_progress=progress,
        )
        exit_code = 75
    except (ValidationError, ValueError) as exc:
        result = {
            "status": "validation_error",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "external_calls": 0,
            "locked_test_accessed": False,
        }
        exit_code = 2

    if args.command in {"init", "status", "run-cycle", "run-loop"}:
        result.update(refresh_dashboard(args.dashboard_root))
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
