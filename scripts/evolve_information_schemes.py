#!/usr/bin/env python3
"""Preflight and govern the v1 Information Plan / Signal evolution workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.scheme_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.scheme_evolution import DEFAULT_EVOLUTION_PRIORS
from stock_opportunity_agent.research.evolution_runtime import (
    EvolutionRunContract,
    ExternalRequestPending,
    approve_dataset_proposal,
    build_run_contract,
    filter_case_price_history,
    inventory_local_evolution_inputs,
    migrate_legacy_raw_info,
    prepare_dataset_proposal,
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
    initialize.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)

    validate = subparsers.add_parser(
        "validate-catalog", help="materialize and validate the seed Signal catalog"
    )
    validate.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)

    status = subparsers.add_parser("status", help="show committed workspace state")
    status.add_argument("--workspace", type=Path, required=True)

    preflight = subparsers.add_parser(
        "preflight-local",
        help="inventory local point-in-time inputs and registered API routes",
    )
    preflight.add_argument("--workspace", type=Path, required=True)
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
    freeze.add_argument("--approved-dataset", type=Path, required=True)
    freeze.add_argument("--run-id", required=True)
    freeze.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    freeze.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    freeze.add_argument("--adjusted-prices", type=Path, default=DEFAULT_ADJUSTED_PRICES)
    freeze.add_argument("--judge-model", default="kimi-k3-together")
    freeze.add_argument("--evolution-model", default="openrouter-fusion")
    freeze.add_argument("--plan-rounds", type=int, default=1)
    freeze.add_argument("--candidates-per-round", type=int, default=1)
    freeze.add_argument("--max-external-attempts", type=int, default=500)
    freeze.add_argument("--max-total-cost", type=float, default=100.0)

    run_cycle = subparsers.add_parser(
        "run-cycle",
        help="preflight or execute one frozen bounded Fast/Slow cycle",
    )
    run_cycle.add_argument("--workspace", type=Path, required=True)
    run_cycle.add_argument("--approved-dataset", type=Path, required=True)
    run_cycle.add_argument("--external", action="store_true")
    run_cycle.add_argument("--acknowledge-contract-hash")

    approve = subparsers.add_parser(
        "approve-signals",
        help="human-approve and promote exact validated Signal candidate hashes",
    )
    approve.add_argument("--workspace", type=Path, required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument(
        "--candidate",
        action="append",
        required=True,
        metavar="SIGNAL_REF=SHA256",
    )
    return parser


def initialize_workspace(workspace_path: Path, catalog_path: Path) -> dict[str, object]:
    workspace = EvolutionWorkspace(workspace_path)
    RawInfoStore(workspace_path / "raw_info")
    registry = SignalRegistry(
        workspace_path / "signals",
        candidate_root=workspace_path / "signals_candidates",
    )
    installed = registry.install_catalog(catalog_path)
    snapshot = registry.freeze()
    return {
        "workspace": str(workspace.root),
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
    return {
        "workspace": str(workspace.root),
        "last_completed_round": workspace.last_completed_round,
        "committed_plan_count": len(workspace.restore_archive().records),
        "meta_entries": len(workspace.restore_meta().entries),
        "registry_version": registry.version,
        "stable_signal_count": len(registry.list_signal_cards()),
        "locked_test_accessed": False,
    }


def preflight_local(
    *,
    workspace_path: Path,
    catalog_path: Path,
    cases_path: Path,
    documents_path: Path,
    adjusted_prices_path: Path,
    judge_model: str,
    evolution_model: str,
) -> dict[str, object]:
    """Write a no-network evidence bundle for local data and model readiness."""

    _load_local_env(PROJECT_ROOT / ".env.local")
    workspace_state = initialize_workspace(workspace_path, catalog_path)
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
    preflight_root = workspace_path / "preflight"
    preflight_root.mkdir(parents=True, exist_ok=True)
    inventory_path = preflight_root / "local_inventory.json"
    models_path = preflight_root / "model_availability.json"
    inventory_path.write_text(
        json.dumps(inventory.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    models_path.write_text(
        json.dumps(models, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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


def approve_signals(
    *,
    workspace_path: Path,
    approved_by: str,
    candidate_args: list[str],
) -> dict[str, object]:
    """Apply one explicit exact-hash human promotion batch."""

    registry = SignalRegistry(
        workspace_path / "signals",
        candidate_root=workspace_path / "signals_candidates",
    )
    approvals: list[tuple[str, str]] = []
    for value in candidate_args:
        signal_ref, separator, candidate_hash = value.partition("=")
        if not separator or len(candidate_hash) != 64:
            raise ValueError("--candidate must be SIGNAL_REF=SHA256")
        approvals.append((signal_ref, candidate_hash))
    promoted: list[str] = []
    for signal_ref, candidate_hash in approvals:
        registry.approve_candidate(
            signal_ref,
            expected_candidate_hash=candidate_hash,
            approved_by=approved_by,
        )
        registry.promote_candidate(signal_ref)
        promoted.append(signal_ref)
    if promoted:
        registry.bump_version()
    return {
        "workspace": str(workspace_path),
        "approved_by": approved_by,
        "promoted": promoted,
        "registry_version": registry.version,
    }


def migrate_raw_info(
    *,
    workspace_path: Path,
    cases_path: Path,
    documents_path: Path,
    adjusted_prices_path: Path,
) -> dict[str, object]:
    report = migrate_legacy_raw_info(
        cases_path=cases_path,
        documents_path=documents_path,
        adjusted_prices_path=adjusted_prices_path,
        raw_info_root=workspace_path / "raw_info",
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


def freeze_run(
    *,
    workspace_path: Path,
    approved_dataset_path: Path,
    run_id: str,
    cases_path: Path,
    documents_path: Path,
    adjusted_prices_path: Path,
    judge_model: str,
    evolution_model: str,
    plan_rounds: int,
    candidates_per_round: int,
    max_external_attempts: int,
    max_total_cost: float,
) -> dict[str, object]:
    _load_local_env(PROJECT_ROOT / ".env.local")
    contract_path = workspace_path / "run_contract.json"
    if contract_path.exists():
        contract = EvolutionRunContract.load_frozen(contract_path)
        expected_dataset_hash = hashlib.sha256(
            approved_dataset_path.read_bytes()
        ).hexdigest()
        if (
            contract.run_id != run_id
            or contract.dataset_manifest_hash != expected_dataset_hash
            or contract.models["judge"]["alias"] != judge_model
            or contract.models["proposer"]["alias"] != evolution_model
            or contract.max_external_attempts != max_external_attempts
            or contract.max_total_cost != max_total_cost
        ):
            raise ValueError("existing run contract conflicts with requested freeze scope")
    else:
        inventory = inventory_local_evolution_inputs(
            cases_path=cases_path,
            documents_path=documents_path,
            adjusted_prices_path=adjusted_prices_path,
        )
        registry = SignalRegistry(
            workspace_path / "signals",
            candidate_root=workspace_path / "signals_candidates",
        )
        snapshot = registry.freeze()
        contract = build_run_contract(
            run_id=run_id,
            dataset_manifest_path=approved_dataset_path,
            inventory=inventory,
            signal_registry_version=registry.version,
            signal_registry_hash=snapshot.registry_hash,
            priors={
                "reflect_round": DEFAULT_EVOLUTION_PRIORS.reflect_round,
                "propose_plan": DEFAULT_EVOLUTION_PRIORS.propose_plan,
                "mine_signal": DEFAULT_EVOLUTION_PRIORS.mine_signal,
                "update_signal": DEFAULT_EVOLUTION_PRIORS.update_signal,
            },
            role_aliases={"judge": judge_model, "proposer": evolution_model},
            project_root=PROJECT_ROOT,
            limits={
                "plan_rounds_per_signal_cycle": plan_rounds,
                "candidates_per_round": candidates_per_round,
                "top_k": 3,
                "random_k": 2,
                "similarity_threshold": 0.9,
                "max_signal_rounds": 5,
                "max_signal_calls": 20,
                "max_llm_calls": 40,
                "max_tokens": 120_000,
                "max_case_cost": 5.0,
                "max_agent_steps": 20,
            },
            max_external_attempts=max_external_attempts,
            max_total_cost=max_total_cost,
        )
        contract.freeze(contract_path)
    return {
        "run_contract": str(contract_path),
        "contract_hash": contract.contract_hash,
        "run_id": contract.run_id,
        "dataset_manifest_hash": contract.dataset_manifest_hash,
        "signal_registry_hash": contract.signal_registry_hash,
        "models": contract.models,
        "max_external_attempts": contract.max_external_attempts,
        "max_total_cost": contract.max_total_cost,
        "locked_test_accessed": False,
        "external_calls": 0,
    }


def run_cycle_command(
    *,
    workspace_path: Path,
    approved_dataset_path: Path,
    external: bool,
    acknowledged_contract_hash: str | None,
) -> dict[str, object]:
    _load_local_env(PROJECT_ROOT / ".env.local")
    contract = EvolutionRunContract.load_frozen(workspace_path / "run_contract.json")
    try:
        result = run_bounded_evolution_cycle(
            workspace_path=workspace_path,
            approved_dataset_manifest=approved_dataset_path,
            contract=contract,
            allow_external=external,
            acknowledged_contract_hash=acknowledged_contract_hash,
        )
    except ExternalRequestPending as pending:
        return {
            "status": "exact_request_pending_external_approval",
            "request_hash": pending.request_hash,
            "request_path": str(pending.request_path),
            "contract_hash": contract.contract_hash,
            "external_calls": 0,
            "locked_test_accessed": False,
        }
    return {
        "status": "cycle_completed",
        "contract_hash": contract.contract_hash,
        "completed_plan_rounds": [item.round_id for item in result.plan_rounds],
        "signal_candidates_pending_approval": dict(
            result.signal_evolution.validated_pending_approval
        ),
        "promoted_signals": list(result.signal_evolution.promoted),
        "registry_version": result.signal_evolution.registry_version,
        "locked_test_accessed": False,
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


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "init":
        result = initialize_workspace(args.workspace, args.catalog)
    elif args.command == "validate-catalog":
        result = validate_catalog(args.catalog)
    elif args.command == "preflight-local":
        result = preflight_local(
            workspace_path=args.workspace,
            catalog_path=args.catalog,
            cases_path=args.cases,
            documents_path=args.documents,
            adjusted_prices_path=args.adjusted_prices,
            judge_model=args.judge_model,
            evolution_model=args.evolution_model,
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
    elif args.command == "approve-dataset":
        approved_path = approve_dataset_proposal(
            proposal_manifest_path=args.proposal,
            expected_proposal_hash=args.proposal_hash,
            approved_by=args.approved_by,
        )
        result = {
            "approved_manifest": str(approved_path),
            "approved_manifest_hash": hashlib.sha256(approved_path.read_bytes()).hexdigest(),
            "approval_status": "human_approved",
        }
    elif args.command == "freeze-run":
        result = freeze_run(
            workspace_path=args.workspace,
            approved_dataset_path=args.approved_dataset,
            run_id=args.run_id,
            cases_path=args.cases,
            documents_path=args.documents,
            adjusted_prices_path=args.adjusted_prices,
            judge_model=args.judge_model,
            evolution_model=args.evolution_model,
            plan_rounds=args.plan_rounds,
            candidates_per_round=args.candidates_per_round,
            max_external_attempts=args.max_external_attempts,
            max_total_cost=args.max_total_cost,
        )
    elif args.command == "run-cycle":
        result = run_cycle_command(
            workspace_path=args.workspace,
            approved_dataset_path=args.approved_dataset,
            external=args.external,
            acknowledged_contract_hash=args.acknowledge_contract_hash,
        )
    elif args.command == "approve-signals":
        result = approve_signals(
            workspace_path=args.workspace,
            approved_by=args.approved_by,
            candidate_args=args.candidate,
        )
    else:
        result = workspace_status(args.workspace)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
