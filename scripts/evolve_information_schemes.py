#!/usr/bin/env python3
"""Initialize and inspect the v1 Information Plan / Signal evolution workspace."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.scheme_evolution import EvolutionWorkspace
from stock_opportunity_agent.signal_library import SignalRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = PROJECT_ROOT / "configs" / "signals_v1.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap or inspect the bounded dual-loop evolution workspace. "
            "Actual Plan/Signal agents are injected through the Python API."
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


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "init":
        result = initialize_workspace(args.workspace, args.catalog)
    elif args.command == "validate-catalog":
        result = validate_catalog(args.catalog)
    else:
        result = workspace_status(args.workspace)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
