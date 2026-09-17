#!/usr/bin/env python
"""Replay historical mining hypotheses over frozen workspaces (zero calls).

Measures the v2.1 information-arrival definition on committed history and
writes a deterministic JSON report. Usage:

PYTHONPATH=src python3 scripts/run_mining_replay.py \
  --workspace runs/cold_start/evolution/information-evolution-slow-self-evolution-20260913-v89 \
  --raw-info-root runs/cold_start/data/global-raw-info-oracle-v1 \
  --approved-dataset <approved manifest> \
  --output reports/cold_start/mining-replay.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_control import (
    load_approved_development_dataset,
)
from stock_opportunity_agent.research.mining_controller import (
    LabelAwareMiningController,
)
from stock_opportunity_agent.research.mining_replay import (
    load_historical_hypotheses,
    measure_arrival,
    verify_replay_invariants,
)


def _dev_cohort(workspace: Path, discovery) -> list:
    slow_input = workspace / "experiments" / "cycles" / "cycle-0001" / "slow_input.json"
    payload = json.loads(slow_input.read_text(encoding="utf-8"))
    dev_ids = list(payload["sampling_manifest"]["dev_case_ids"])
    by_id = {case.case_id: case for case in discovery}
    return [by_id[case_id] for case_id in dev_ids if case_id in by_id]


class _ReplayDecisionModel:
    """Zero-call scripted decisions derived from one historical hypothesis."""

    def __init__(self, case_refs, families, query):
        self._case_refs = case_refs
        self._families = families
        self._query = query
        self.views = []

    def next_action(self, view):
        self.views.append(dict(view))
        if self._case_refs:
            refs, self._case_refs = self._case_refs, []
            return {
                "action": "fetch_evidence",
                "rationale": [
                    "Deterministic replay of the historical retrieval intent."
                ],
                "case_refs": refs,
                "source_families": self._families,
                "max_documents": 2,
                "query": self._query,
            }
        return {
            "action": "record_deferred",
            "rationale": ["Zero-call replay stops after one fetch."],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", action="append", required=True)
    parser.add_argument("--raw-info-root", type=Path, required=True)
    parser.add_argument("--approved-dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--demo-cohort-limit", type=int, default=8)
    args = parser.parse_args()

    dataset = load_approved_development_dataset(args.approved_dataset)
    discovery = list(dataset.discovery)
    store = RawInfoStore(args.raw_info_root)
    documents_by_hash = {
        document.content_hash: document for document in store.documents
    }

    reports = []
    invariants = []
    for workspace_arg in args.workspace:
        workspace = Path(workspace_arg)
        hypotheses = load_historical_hypotheses(workspace)
        cohort = _dev_cohort(workspace, discovery)
        report = measure_arrival(
            store,
            cohort,
            hypotheses,
            workspace_label=str(workspace.name),
        )
        reports.append(report)
        print(
            f"{workspace.name}: {len(hypotheses)} hypotheses, "
            f"cohort={report['cohort_case_count']}, "
            f"catalog={report['concept_catalog_size']}"
        )
        for row in report["hypotheses"]:
            print(
                f"  {row['hypothesis_id']}: inputs={row['input_count']} "
                f"mean_coverage={row['mean_input_coverage']} "
                f"observables={row['observable'][:60]}"
            )

        demo = cohort[: args.demo_cohort_limit]
        if hypotheses and demo:
            hypothesis = hypotheses[0]
            retrieval = dict(hypothesis.get("retrieval_intent", {}))
            model = _ReplayDecisionModel(
                [case.case_id for case in demo],
                [str(item) for item in retrieval.get("source_types", ())] or ["filing"],
                retrieval.get("query"),
            )
            controller = LabelAwareMiningController(
                store=store,
                model=model,
                case_pairs=[(case.case_id, case) for case in demo],
                measurable_evidence_manifest={},
                signal_catalog=[],
                seed="hypothesis",
            )
            result = controller.run()
            aliases = sorted(
                {
                    str(case.basic_info.get("company_name", ""))
                    for case in demo
                    if case.basic_info.get("company_name")
                }
            )
            invariants.append(
                {
                    "workspace": str(workspace.name),
                    **verify_replay_invariants(
                        facts=list(controller_facts(controller)),
                        documents_by_content_hash=documents_by_hash,
                        ledger_ids=[entry.action_id for entry in result.ledger],
                        model_views=model.views,
                        identity_aliases=aliases,
                    ),
                    "terminal_kind": result.terminal_kind,
                    "ledger_entries": len(result.ledger),
                }
            )
            print(
                f"  replay controller: terminal={result.terminal_kind}, "
                f"ledger={len(result.ledger)}, "
                f"invariants={invariants[-1]['all_passed']}"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"reports": reports, "invariants": invariants},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.output}")


def controller_facts(controller):
    yield from controller._facts.values()  # noqa: SLF001 - replay introspection


if __name__ == "__main__":
    main()
