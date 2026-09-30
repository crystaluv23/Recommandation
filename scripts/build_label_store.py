#!/usr/bin/env python3
"""Build the global outcome label store from the frozen price archive.

Collects every (company_id, as_of_date) case key that any evolution artifact
has ever recorded, recomputes the six-month smoothed multiple from the frozen
full-market adjusted-price archive with the shared calculator, reconciles the
result against every realized-multiple value recorded next to those case keys,
and writes one immutable label-store version.

The script is report-heavy by design: reconciliation mismatches and implausible
multiples are printed, never silently dropped. Usage:

    PYTHONPATH=src python scripts/build_label_store.py \
        [--archive runs/cold_start/formal/.../price_histories.json] \
        [--output runs/cold_start/data/outcome-label-store-v1]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stock_opportunity_agent.cases.label_store import (  # noqa: E402
    build_label_records,
    file_sha256,
    write_label_store,
)
from stock_opportunity_agent.models import ValidationError  # noqa: E402

DEFAULT_ARCHIVE = (
    PROJECT_ROOT
    / "runs/cold_start/formal/cold-start-formal-openrouter-2026-05-13"
    / "02_prices/price_histories.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "runs/cold_start/data/outcome-label-store-v1"
EVOLUTION_ROOT = PROJECT_ROOT / "runs/cold_start/evolution"
ORACLE_MARKET = (
    PROJECT_ROOT / "runs/cold_start/data/global-raw-info-oracle-v1/market_data"
)
IMPLAUSIBLE_MULTIPLE = 50.0
RECONCILE_TOLERANCE = 0.01


def _collect_pairs_and_recorded() -> dict[tuple[str, str], float]:
    """Union every case key ever recorded with its nearest realized multiple."""

    recorded: dict[tuple[str, str], float] = {}
    printed_conflicts: set[tuple[tuple[str, str], float, float]] = set()
    case_pattern = re.compile(r'"case_id":\s*"(cik_\d+):(\d{8})')
    for path in sorted(EVOLUTION_ROOT.rglob("*.json")):
        try:
            raw = path.read_text()
        except OSError:
            continue
        for match in case_pattern.finditer(raw):
            segment = raw[match.start() : match.start() + 900]
            value = re.search(
                r'"realized_max_multiple":\s*([0-9.]+)', segment
            )
            if not value:
                continue
            key = (
                match.group(1),
                f"{match.group(2)[:4]}-{match.group(2)[4:6]}-{match.group(2)[6:]}",
            )
            try:
                multiple = float(value.group(1))
            except ValueError:
                continue
            previous = recorded.get(key)
            if previous is None:
                recorded[key] = multiple
            elif abs(previous - multiple) > 1e-9:
                conflict = (key, previous, multiple)
                if conflict not in printed_conflicts:
                    printed_conflicts.add(conflict)
                    print(
                        f"  WARNING conflicting recorded multiples for {key}: "
                        f"{previous} vs {multiple} (keeping first)"
                    )
    return recorded


def _symbol_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not ORACLE_MARKET.exists():
        return mapping
    for company_dir in sorted(ORACLE_MARKET.iterdir()):
        for path in sorted(company_dir.glob("*.json")):
            try:
                metadata = json.loads(path.read_text()).get("metadata", {})
            except (OSError, json.JSONDecodeError):
                continue
            symbol = metadata.get("symbol")
            if symbol:
                mapping.setdefault(company_dir.name, str(symbol))
                break
    return mapping


def _harness_pairs() -> list[tuple[str, str]]:
    """Read the minimal-rounds harness case boundaries (never duplicate them)."""

    spec = importlib.util.spec_from_file_location(
        "run_minimal_rounds", PROJECT_ROOT / "scripts/run_minimal_rounds.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return sorted(
        (company_id, as_of)
        for company_id, as_of in module.CASE_PREDICTION_DATES.items()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.archive.is_file():
        raise SystemExit(f"price archive not found: {args.archive}")
    if args.output.exists():
        raise SystemExit(f"label store already exists: {args.output}")

    archive = json.loads(args.archive.read_text())
    bars_by_symbol = archive.get("bars_by_symbol", {})
    symbol_by_company = _symbol_map()
    recorded = _collect_pairs_and_recorded()
    pairs = sorted(set(recorded) | set(_harness_pairs()))
    print(f"archive symbols: {len(bars_by_symbol)}")
    print(f"symbol mappings from oracle: {len(symbol_by_company)}")
    print(f"recorded (company, as_of) keys: {len(recorded)}")
    print(f"pairs incl. harness boundaries: {len(pairs)}")

    records, exclusions = build_label_records(
        bars_by_symbol,
        pairs,
        symbol_by_company,
    )
    print(f"derived records: {len(records)}; exclusions: {len(exclusions)}")
    by_reason: dict[str, int] = {}
    for row in exclusions:
        by_reason[row["reason"]] = by_reason.get(row["reason"], 0) + 1
    for reason, count in sorted(by_reason.items()):
        print(f"  exclusion [{reason}]: {count}")

    reconciled = exact = within_tolerance = binary_mismatch = 0
    worst: list[tuple[float, tuple[str, str], float, float]] = []
    for record in records:
        prior = recorded.get(record.key)
        if prior is None:
            continue
        reconciled += 1
        delta = abs(record.realized_max_multiple - prior)
        if delta <= 1e-9:
            exact += 1
        if delta <= RECONCILE_TOLERANCE:
            within_tolerance += 1
        else:
            worst.append((delta, record.key, prior, record.realized_max_multiple))
        if (prior >= 2.0) != record.is_surge:
            binary_mismatch += 1
            print(
                f"  BINARY MISMATCH {record.key}: recorded {prior} vs "
                f"derived {record.realized_max_multiple}"
            )
    worst.sort(reverse=True)
    print(
        f"reconciliation: {reconciled} comparable, {exact} exact, "
        f"{within_tolerance} within {RECONCILE_TOLERANCE}, "
        f"{binary_mismatch} binary mismatches"
    )
    for delta, key, prior, derived in worst[:10]:
        print(f"  delta {delta:.4f}  {key}  recorded {prior} vs derived {derived}")

    implausible = [
        record for record in records if record.realized_max_multiple > IMPLAUSIBLE_MULTIPLE
    ]
    for record in implausible:
        print(
            f"  IMPLAUSIBLE multiple {record.realized_max_multiple:.2f} at "
            f"{record.key} ({record.symbol}) — review before trusting"
        )

    write_label_store(
        args.output,
        records=records,
        archive_path=args.archive,
        archive_sha256=file_sha256(args.archive),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    print(f"label store written: {args.output} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"label store build failed: {exc}")
