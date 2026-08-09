#!/usr/bin/env python3
"""Audit and repair historical point-in-time data under explicit request bounds."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from stock_opportunity_agent.data.backfill import (
    audit_historical_data_coverage,
    preview_sec_filing_backfill,
    run_sec_filing_backfill,
    write_sec_filing_backfill_plan,
)
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import UrllibJsonTransport
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.data.sources.state import (
    ManagedHttpTransport,
    RawDataCache,
    RequestLedger,
    SourceBudget,
)
from stock_opportunity_agent.models import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FORMAL_RUN = (
    PROJECT_ROOT
    / "runs"
    / "cold_start"
    / "formal"
    / "cold-start-formal-openrouter-2026-05-13-clean-universe"
)
DEFAULT_CASES = DEFAULT_FORMAL_RUN / "05_packets" / "historical_cases.json"
DEFAULT_DOCUMENTS = DEFAULT_FORMAL_RUN / "04_documents" / "documents_and_catalysts.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit local historical coverage and run bounded, resumable source backfills. "
            "All commands are zero-network unless run-sec-filings receives a positive "
            "--max-network-requests value."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="audit actual point-in-time coverage")
    audit.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    audit.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    audit.add_argument("--output", type=Path)

    plan = subparsers.add_parser(
        "plan-sec-filings",
        help="write an exact zero-network plan for upgrading saved SEC excerpts",
    )
    plan.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument(
        "--forms",
        nargs="*",
        default=(),
        help="optional exact form allow-list, for example 10-K 20-F 40-F",
    )

    run = subparsers.add_parser(
        "run-sec-filings",
        help="preview or execute a bounded SEC primary-document backfill",
    )
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--raw-info-root", type=Path, required=True)
    run.add_argument("--max-network-requests", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "audit":
        result = audit_historical_data_coverage(
            cases_path=args.cases,
            documents_path=args.documents,
        )
        if args.output:
            _write_json(args.output, result)
    elif args.command == "plan-sec-filings":
        result = write_sec_filing_backfill_plan(
            documents_path=args.documents,
            output_path=args.output,
            forms=args.forms,
        )
    else:
        if args.max_network_requests < 0:
            raise ValidationError("--max-network-requests must be non-negative")
        cache = RawDataCache(args.workspace / "raw_cache")
        progress_path = args.workspace / "sec_filing_backfill_progress.json"
        if args.max_network_requests == 0:
            result = preview_sec_filing_backfill(
                plan_path=args.plan,
                raw_info_root=args.raw_info_root,
                cache=cache,
                progress_path=progress_path,
            )
        else:
            _load_local_env(PROJECT_ROOT / ".env.local")
            user_agent = os.environ.get("SOA_SEC_USER_AGENT", "").strip()
            if not user_agent or "contact@example.com" in user_agent.casefold():
                raise ValidationError(
                    "positive SEC execution requires SOA_SEC_USER_AGENT with a real "
                    "application/contact identity"
                )
            ledger = RequestLedger(args.workspace / "request_ledger.jsonl")
            budget = SourceBudget(ledger)
            transport = ManagedHttpTransport(
                "sec_edgar",
                DataCapability.FILING_DOCUMENTS,
                UrllibJsonTransport(),
                cache,
                ledger,
                budget,
            )
            result = run_sec_filing_backfill(
                plan_path=args.plan,
                raw_info_root=args.raw_info_root,
                cache=cache,
                progress_path=progress_path,
                client=SecEdgarClient(user_agent, transport=transport),
                max_network_requests=args.max_network_requests,
            )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _load_local_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
