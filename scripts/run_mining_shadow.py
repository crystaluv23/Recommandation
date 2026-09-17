#!/usr/bin/env python
"""Run one live shadow cycle of the label-aware mining controller.

Reads the same frozen inputs as the production Slow cycle (sampling manifest,
capability backlog, registry, oracle) from a frozen workspace, drives the
LabelAwareMiningController with the real DeepSeek role caller through a
separate shadow workspace/ledger, and writes an auditable JSON result without
touching any production artifact. Usage:

PYTHONPATH=src python3 scripts/run_mining_shadow.py \
  --workspace runs/cold_start/evolution/<v91> \
  --raw-info-root runs/cold_start/data/global-raw-info-oracle-v1 \
  --approved-dataset <approved manifest> \
  --output reports/cold_start/v91-shadow.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_control import (
    EvolutionRunContract,
    load_approved_development_dataset,
)
from stock_opportunity_agent.research.evolution_runtime import EvolutionWorkspace
from stock_opportunity_agent.research.evolution_core import _mask_identity_values
from stock_opportunity_agent.research.evolution_transport import (
    ExternalAttemptLedger,
    StructuredRoleClient,
)
from stock_opportunity_agent.research.mining_controller import (
    LabelAwareMiningController,
)
from stock_opportunity_agent.research.mining_replay import (
    assert_view_masked,
    verify_replay_invariants,
)
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalRegistry


class _ViewRecordingModel:
    def __init__(self, inner):
        self.inner = inner
        self.views: list[dict] = []

    def next_action(self, view):
        self.views.append(dict(view))
        return self.inner.next_action(view)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--raw-info-root", type=Path, required=True)
    parser.add_argument("--approved-dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", choices=("hypothesis", "discovery"), default="hypothesis")
    parser.add_argument("--heavy-action-limit", type=int, default=12)
    parser.add_argument("--light-action-limit", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=40)
    parser.add_argument("--max-cost", type=float, default=2.0)
    args = parser.parse_args()

    workspace_root = args.workspace.resolve()
    slow_input_path = (
        workspace_root / "experiments" / "cycles" / "cycle-0001" / "slow_input.json"
    )
    slow_input = json.loads(slow_input_path.read_text(encoding="utf-8"))
    dev_case_ids = list(slow_input["sampling_manifest"]["dev_case_ids"])

    dataset = load_approved_development_dataset(args.approved_dataset)
    by_id = {case.case_id: case for case in dataset.discovery}
    dev_cases = [by_id[case_id] for case_id in dev_case_ids if case_id in by_id]
    opaque = {
        case.case_id: f"case-{index:03d}"
        for index, case in enumerate(dev_cases, start=1)
    }

    store = RawInfoStore(args.raw_info_root)
    workspace = EvolutionWorkspace(workspace_root)
    registry = SignalRegistry(
        workspace_root / "signals",
        candidate_root=workspace_root / "signals_candidates",
    )
    engine = SignalEvolutionEngine(
        registry=registry,
        raw_info_store=store,
        discovery_cases=dataset.discovery,
        meta_memory=workspace.restore_meta(),
        workspace=workspace,
        mining_model=None,
        update_model=None,
        llm_signal_runner=None,
        identity_cases=(
            *dataset.discovery,
            *dataset.anchor,
            *dataset.evolution_validation,
        ),
    )
    context = engine._mining_context(cycle_id=1)  # noqa: SLF001 - shadow context
    manifest = _mask_identity_values(
        engine._h1_measurable_evidence_manifest(  # noqa: SLF001
            [(opaque[case.case_id], case) for case in dev_cases]
        ),
        engine.slow_role_identity_guards,
        expand_aliases=False,
    )
    backlog_needs = [
        dict(row)
        for row in dict(context.get("capability_backlog", {})).get(
            "signal_need_items", ()
        )
        if isinstance(row, dict) and row.get("need_ref")
    ]
    catalog = [
        {"signal_ref": card.get("signal_ref", ""), "description": card.get("description", "")}
        for card in context.get("stable_signal_cards", ())
        if isinstance(card, dict)
    ]

    shadow_root = workspace_root.parent / (workspace_root.name + "-shadow")
    shadow_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        workspace_root / "run_contract.json", shadow_root / "run_contract.json"
    )
    contract = EvolutionRunContract.load_frozen(shadow_root / "run_contract.json")
    ledger = ExternalAttemptLedger(
        shadow_root / "attempts.json",
        max_attempts=args.max_attempts,
        max_total_cost=args.max_cost,
    )
    caller = StructuredRoleClient(
        registration=get_model(
            str(contract.models["proposer"]["alias"]), role="evolution"
        ),
        contract=contract,
        workspace=shadow_root,
        ledger=ledger,
        allow_external=True,
        acknowledged_contract_hash=contract.contract_hash,
        environ=os.environ,
    )

    candidates: list[dict] = []

    def sink(candidate):
        candidates.append(dict(candidate))
        return {"status": "validated", "shadow_recorded": True}

    inner = MiningAgentRoleModel(caller)
    model = _ViewRecordingModel(inner)
    controller = LabelAwareMiningController(
        store=store,
        model=model,
        case_pairs=[(opaque[case.case_id], case) for case in dev_cases],
        measurable_evidence_manifest=manifest,
        signal_catalog=catalog,
        seed=args.seed,
        backlog_needs=backlog_needs if args.seed == "hypothesis" else (),
        heavy_action_limit=args.heavy_action_limit,
        light_action_limit=args.light_action_limit,
        validation_sink=sink,
    )
    result = controller.run()

    aliases = sorted(
        {
            str(case.basic_info.get("company_name", ""))
            for case in dev_cases
            if case.basic_info.get("company_name")
        }
        | {
            str(case.basic_info.get("ticker", ""))
            for case in dev_cases
            if case.basic_info.get("ticker")
        }
    )
    masking_failures = []
    for index, view in enumerate(model.views):
        try:
            assert_view_masked(view, aliases)
        except AssertionError as exc:
            masking_failures.append(f"view[{index}]: {exc}")

    documents_by_hash = {
        document.content_hash: document for document in store.documents
    }
    invariants = verify_replay_invariants(
        facts=list(controller._facts.values()),  # noqa: SLF001
        documents_by_content_hash=documents_by_hash,
        ledger_ids=[entry.action_id for entry in result.ledger],
        model_views=model.views,
        identity_aliases=aliases,
    )
    invariants["identity_masking_failures"] = (
        list(invariants["identity_masking_failures"]) + masking_failures
        if masking_failures
        else list(invariants["identity_masking_failures"])
    )
    invariants["all_passed"] = (
        invariants["all_passed"] and not masking_failures
    )

    payload = {
        "schema_version": "mining-shadow-result-v1",
        "workspace": str(workspace_root.name),
        "seed": args.seed,
        "terminal_kind": result.terminal_kind,
        "candidates": candidates,
        "need_dispositions": [dict(row) for row in result.need_dispositions],
        "ledger": controller.ledger.to_dict(),
        "usage": {
            "llm_calls": inner.usage.llm_calls,
            "tokens": inner.usage.tokens,
            "cost": inner.usage.cost,
            "model_calls": result.model_calls,
        },
        "request_hashes": list(inner.requests),
        "invariants": invariants,
        "budgets": {
            "heavy_used": controller._heavy_used,  # noqa: SLF001
            "light_used": controller._light_used,  # noqa: SLF001
            "heavy_limit": args.heavy_action_limit,
            "light_limit": args.light_action_limit,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"shadow: terminal={result.terminal_kind} candidates={len(candidates)} "
        f"calls={result.model_calls} cost={inner.usage.cost:.4f} "
        f"invariants={invariants['all_passed']}"
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
