#!/usr/bin/env python3
"""Audit deterministic financial Signals across the local Raw Info oracle.

Executes every deterministic financial Signal for every issuer that has
Company Facts in the oracle, at each issuer's own latest document availability
date, and reports per-Signal result/coverage distributions plus every
implausible value the plausibility gate downgraded. Use it to surface
measurement-basis regressions before a live Fast round; it is report-only and
never mutates a registry or run artifact.

Usage:
    scripts/audit_deterministic_signals.py [oracle_root]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stock_opportunity_agent.data.raw_info import RawInfoStore  # noqa: E402
from stock_opportunity_agent.signal_library import (  # noqa: E402
    FrozenSignalRegistry,
    SignalExecutor,
    SignalSpec,
)


def _load_financial_specs() -> tuple[SignalSpec, ...]:
    catalog = json.loads((PROJECT_ROOT / "configs/signals_v1.json").read_text())
    specs = tuple(
        SignalSpec.from_dict(item["spec"])
        for item in catalog["signals"]
        if item["spec"].get("execution", {}).get("type") == "deterministic"
        and item["spec"].get("category") == "financial"
    )
    if not specs:
        raise SystemExit("seed catalog contains no deterministic financial specs")
    return specs


def main() -> int:
    oracle = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_oracle()
    if not oracle.exists():
        raise SystemExit(f"oracle root does not exist: {oracle}")
    specs = _load_financial_specs()
    registry = FrozenSignalRegistry(
        version=1,
        registry_hash="audit-deterministic-signals",
        specs=specs,
        skills={},
    )
    store = RawInfoStore(str(oracle))
    refs = tuple(spec.ref for spec in specs)
    counts: Counter = Counter()
    flagged: list[tuple[str, str, str]] = []
    issuers = 0
    facts_root = oracle / "company_facts"
    for company_dir in sorted(facts_root.iterdir() if facts_root.exists() else ()):
        company_id = company_dir.name
        available = [
            datetime.fromisoformat(document["available_at"])
            for path in company_dir.glob("*.json")
            if (document := json.loads(path.read_text())).get("available_at")
        ]
        if not available:
            continue
        as_of = max(available)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        issuers += 1
        batch = SignalExecutor(registry, store).execute_batch(
            refs, company_id=company_id, as_of=as_of
        )
        for result in batch.results:
            counts[f"{result.signal_id}:{result.execution_status.value}"] += 1
            if "implausible_value" in result.interpretation:
                counts[f"{result.signal_id}:implausible_downgraded"] += 1
                flagged.append(
                    (company_id, result.signal_id, result.interpretation)
                )

    print(f"issuers audited: {issuers}")
    for spec in specs:
        signal_id = spec.signal_id
        row = {
            status: counts[f"{signal_id}:{status}"]
            for status in (
                "success",
                "domain_unavailable",
                "validation_failed",
                "implausible_downgraded",
            )
            if counts[f"{signal_id}:{status}"]
        }
        print(f"  {signal_id:34s} {row or {'success': 0}}")
    if flagged:
        print("\ndowngraded implausible values:")
        for company_id, signal_id, interpretation in flagged:
            print(f"  {company_id}  {signal_id}  {interpretation}")
    else:
        print("\ndowngraded implausible values: none")
    return 0


def _default_oracle() -> Path:
    candidates = sorted(
        (PROJECT_ROOT / "runs/cold_start").glob("data/global-raw-info-oracle-v*"),
        reverse=True,
    )
    if not candidates:
        raise SystemExit("no global-raw-info-oracle-v* found under runs/cold_start/data")
    return candidates[0]


if __name__ == "__main__":
    raise SystemExit(main())
