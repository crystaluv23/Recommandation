"""Dataset inventory, migration, proposal, and approval for evolution runs."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.artifacts import (
    atomic_write_json as _atomic_write_json,
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.cases.selection import eligible_common_stock_listings
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoOracle, RawInfoStore
from stock_opportunity_agent.data.sources.core import SecurityListing
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import (
    EVALUATION_LABELS,
    EvaluationDatasetManager,
    EvolutionCase,
    GroundTruth,
)


_FORBIDDEN_OUTCOME_KEYS = frozenset(
    {
        "ground_truth",
        "outcome",
        "outcome_label",
        "label",
        "is_surge",
        "magnitude_class",
        "realized_return",
        "realized_max_multiple",
        "future_price",
        "future_return",
        "post_outcome",
    }
)


def _reject_outcome_fields(value: Any) -> None:
    """Reject retrospective labels from point-in-time identity decisions."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in _FORBIDDEN_OUTCOME_KEYS:
                raise ValidationError(
                    f"outcome field leaked into identity decision: {key}"
                )
            _reject_outcome_fields(nested)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_outcome_fields(item)


EXPANSION_STRATUM_ORDER = (
    "below_1_5x",
    "near_surge_1_5_to_2x",
    "surge_2_to_3x",
    "surge_3_to_10x",
    "surge_10x_plus",
)


DEFAULT_EXPANSION_STRATUM_WEIGHTS: dict[str, float] = {
    "below_1_5x": 0.30,
    "near_surge_1_5_to_2x": 0.25,
    "surge_2_to_3x": 0.25,
    "surge_3_to_10x": 0.15,
    "surge_10x_plus": 0.05,
}


NORMAL_STOCK_EXCHANGES = frozenset({"NASDAQ", "NYSE", "NYSE MKT", "AMEX"})


MIN_PRE_PREDICTION_DOLLAR_VOLUME = 1_000_000.0


MAX_ADJUSTED_CLOSE_STEP_UP = 4.0


MIN_ADJUSTED_CLOSE_STEP_DOWN = 0.25


_NON_OPERATING_ISSUER_MARKERS = (
    "acquisition",
    "blank check",
    "special purpose acquisition",
    "spac",
)


_SPAC_SERIES_NAME = re.compile(
    r"\b(?:corp(?:oration)?|holdings?)\s+(?:ii|iii|iv|v|vi|vii|viii|ix|x)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ArtifactSummary:
    """Secret-free identity and shape of one local input artifact."""

    path: str
    sha256: str
    size_bytes: int
    schema_version: str | None
    facts: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
            "facts": dict(self.facts),
        }


@dataclass(frozen=True)
class LocalEvolutionInventory:
    """Current local evidence for a future reviewed dataset migration."""

    cases: ArtifactSummary
    documents: ArtifactSummary
    adjusted_prices: ArtifactSummary
    compatible_case_count: int
    incompatible_label_reason: str
    migration_ready: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "local-evolution-inventory-v1",
            "cases": self.cases.to_dict(),
            "documents": self.documents.to_dict(),
            "adjusted_prices": self.adjusted_prices.to_dict(),
            "compatible_case_count": self.compatible_case_count,
            "legacy_labels_compatible": False,
            "incompatible_label_reason": self.incompatible_label_reason,
            "migration_ready": self.migration_ready,
            "blockers": list(self.blockers),
            "locked_test_accessed": False,
            "external_calls": 0,
        }

    @property
    def inventory_hash(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True)
class RawInfoMigrationReport:
    """Auditable outcome of a label-free legacy-to-RawInfo migration."""

    raw_info_root: str
    source_inventory_hash: str
    source_document_count: int
    migrated_source_documents: int
    migrated_market_snapshots: int
    appended_source_documents: int
    appended_market_snapshots: int
    skipped_empty_documents: int
    cases_without_price_history: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "legacy-raw-info-migration-v1",
            "raw_info_root": self.raw_info_root,
            "source_inventory_hash": self.source_inventory_hash,
            "source_document_count": self.source_document_count,
            "migrated_source_documents": self.migrated_source_documents,
            "migrated_market_snapshots": self.migrated_market_snapshots,
            "appended_source_documents": self.appended_source_documents,
            "appended_market_snapshots": self.appended_market_snapshots,
            "skipped_empty_documents": self.skipped_empty_documents,
            "cases_without_price_history": list(self.cases_without_price_history),
            "labels_migrated": False,
            "future_prices_migrated": False,
            "locked_test_accessed": False,
            "external_calls": 0,
        }


@dataclass(frozen=True)
class DatasetProposalReport:
    """Label/split proposal that remains inactive until exact human approval."""

    manifest_path: str
    manifest_hash: str
    eligible_case_count: int
    excluded_case_count: int
    split_case_counts: Mapping[str, int]
    split_issuer_counts: Mapping[str, int]
    split_surge_counts: Mapping[str, int]
    approval_status: str = "proposal_only_pending_human_review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "evolution-dataset-proposal-report-v1",
            "manifest_path": self.manifest_path,
            "manifest_hash": self.manifest_hash,
            "eligible_case_count": self.eligible_case_count,
            "excluded_case_count": self.excluded_case_count,
            "split_case_counts": dict(self.split_case_counts),
            "split_issuer_counts": dict(self.split_issuer_counts),
            "split_surge_counts": dict(self.split_surge_counts),
            "approval_status": self.approval_status,
            "locked_test_accessed": False,
            "external_calls": 0,
        }


@dataclass(frozen=True)
class ExpandedDatasetProposalReport:
    """Full-market fixed-date case proposal that remains inactive."""

    manifest_path: str
    manifest_hash: str
    universe_listing_count: int
    priced_symbol_count: int
    eligible_issuer_count: int
    selection_mode: str
    selected_issuer_count: int
    case_count: int
    available_stratum_counts: Mapping[str, int]
    selected_stratum_counts: Mapping[str, int]
    exclusion_reason_counts: Mapping[str, int]
    split_case_counts: Mapping[str, int]
    split_issuer_counts: Mapping[str, int]
    split_surge_counts: Mapping[str, int]
    approval_status: str = "proposal_only_pending_human_review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "expanded-evolution-dataset-proposal-report-v2",
            "manifest_path": self.manifest_path,
            "manifest_hash": self.manifest_hash,
            "universe_listing_count": self.universe_listing_count,
            "priced_symbol_count": self.priced_symbol_count,
            "eligible_issuer_count": self.eligible_issuer_count,
            "selection_mode": self.selection_mode,
            "selected_issuer_count": self.selected_issuer_count,
            "case_count": self.case_count,
            "available_stratum_counts": dict(self.available_stratum_counts),
            "selected_stratum_counts": dict(self.selected_stratum_counts),
            "exclusion_reason_counts": dict(self.exclusion_reason_counts),
            "split_case_counts": dict(self.split_case_counts),
            "split_issuer_counts": dict(self.split_issuer_counts),
            "split_surge_counts": dict(self.split_surge_counts),
            "approval_status": self.approval_status,
            "locked_test_accessed": False,
            "external_calls": 0,
        }


def filter_case_price_history(
    *,
    cases_path: str | Path,
    full_price_archive_path: str | Path,
    output_path: str | Path,
) -> ArtifactSummary:
    """Stream a large local archive and retain only historical-case symbols."""

    cases_data = _read_json(Path(cases_path))
    symbols = {
        symbol
        for row in cases_data.get("cases", ())
        if (symbol := _case_symbol(row)) is not None
    }
    if not symbols:
        raise ValidationError("historical cases contain no symbols")
    metadata, selected = _stream_selected_price_history(
        Path(full_price_archive_path), symbols
    )
    missing = sorted(symbols - set(selected))
    payload = {
        "schema_version": "scheme-evolution-adjusted-prices-v1",
        "source": metadata.get("source") or "massive",
        "start_date": metadata.get("start_date"),
        "end_date": metadata.get("end_date"),
        "requested_symbol_count": len(symbols),
        "priced_symbol_count": len(selected),
        "failed_symbols": {symbol: "missing_from_local_archive" for symbol in missing},
        "case_artifact": {
            "path": str(Path(cases_path).resolve()),
            "sha256": _sha256_file(Path(cases_path)),
        },
        "source_archive": {
            "path": str(Path(full_price_archive_path).resolve()),
            "sha256": _sha256_file(Path(full_price_archive_path)),
        },
        "bars_by_symbol": {symbol: selected[symbol] for symbol in sorted(selected)},
    }
    destination = Path(output_path)
    _write_or_verify_json(destination, payload)
    return ArtifactSummary(
        path=str(destination.resolve()),
        sha256=_sha256_file(destination),
        size_bytes=destination.stat().st_size,
        schema_version="scheme-evolution-adjusted-prices-v1",
        facts={
            "requested_symbol_count": len(symbols),
            "priced_symbol_count": len(selected),
            "failed_symbols": missing,
            "bar_count": sum(len(rows) for rows in selected.values()),
            "start_date": payload["start_date"],
            "end_date": payload["end_date"],
        },
    )


def inventory_local_evolution_inputs(
    *,
    cases_path: str | Path,
    documents_path: str | Path,
    adjusted_prices_path: str | Path,
) -> LocalEvolutionInventory:
    """Inspect actual local point-in-time artifacts without opening Locked Test."""

    case_path = Path(cases_path)
    document_path = Path(documents_path)
    price_path = Path(adjusted_prices_path)
    cases_data = _read_json(case_path)
    documents_data = _read_json(document_path)
    prices_data = _read_json(price_path)

    cases = cases_data.get("cases", ())
    if not isinstance(cases, list):
        raise ValidationError("historical case artifact cases must be a list")
    case_symbols: set[str] = set()
    as_of_dates: list[str] = []
    for row in cases:
        if not isinstance(row, Mapping):
            raise ValidationError("historical case row must be an object")
        packet = row.get("packet", {})
        company = packet.get("company", {}) if isinstance(packet, Mapping) else {}
        ticker = company.get("ticker", {}) if isinstance(company, Mapping) else {}
        symbol = ticker.get("symbol") if isinstance(ticker, Mapping) else None
        if symbol:
            case_symbols.add(str(symbol))
        as_of = packet.get("as_of", {}) if isinstance(packet, Mapping) else {}
        as_of_date = as_of.get("as_of_date") if isinstance(as_of, Mapping) else None
        if as_of_date:
            as_of_dates.append(str(as_of_date))

    documents_by_symbol = documents_data.get("documents_by_symbol", {})
    if not isinstance(documents_by_symbol, Mapping):
        raise ValidationError("document artifact documents_by_symbol must be an object")
    document_count = sum(
        len(rows) for rows in documents_by_symbol.values() if isinstance(rows, list)
    )
    available_dates = [
        str(document.get("available_date"))
        for rows in documents_by_symbol.values()
        if isinstance(rows, list)
        for document in rows
        if isinstance(document, Mapping) and document.get("available_date")
    ]

    bars_by_symbol = prices_data.get("bars_by_symbol", {})
    if not isinstance(bars_by_symbol, Mapping):
        raise ValidationError("price artifact bars_by_symbol must be an object")
    priced_symbols = {str(symbol) for symbol, rows in bars_by_symbol.items() if rows}
    compatible_symbols = case_symbols & priced_symbols
    compatible_case_count = sum(
        1
        for row in cases
        if _case_symbol(row) in compatible_symbols
    )
    failed_symbols = prices_data.get("failed_symbols", {})

    case_summary = ArtifactSummary(
        path=str(case_path.resolve()),
        sha256=_sha256_file(case_path),
        size_bytes=case_path.stat().st_size,
        schema_version=_optional_string(cases_data.get("schema_version")),
        facts={
            "case_count": len(cases),
            "symbol_count": len(case_symbols),
            "as_of_min": min(as_of_dates) if as_of_dates else None,
            "as_of_max": max(as_of_dates) if as_of_dates else None,
            "legacy_outcome_definition_ids": sorted(
                {
                    str(row.get("outcome_definition_id"))
                    for row in cases
                    if isinstance(row, Mapping) and row.get("outcome_definition_id")
                }
            ),
        },
    )
    document_summary = ArtifactSummary(
        path=str(document_path.resolve()),
        sha256=_sha256_file(document_path),
        size_bytes=document_path.stat().st_size,
        schema_version=_optional_string(documents_data.get("schema_version")),
        facts={
            "document_count": document_count,
            "symbol_count": len(documents_by_symbol),
            "available_date_min": min(available_dates) if available_dates else None,
            "available_date_max": max(available_dates) if available_dates else None,
        },
    )
    price_summary = ArtifactSummary(
        path=str(price_path.resolve()),
        sha256=_sha256_file(price_path),
        size_bytes=price_path.stat().st_size,
        schema_version=_optional_string(prices_data.get("schema_version")),
        facts={
            "source": prices_data.get("source"),
            "start_date": prices_data.get("start_date"),
            "end_date": prices_data.get("end_date"),
            "requested_symbol_count": prices_data.get("requested_symbol_count"),
            "priced_symbol_count": len(priced_symbols),
            "bar_count": sum(
                len(rows) for rows in bars_by_symbol.values() if isinstance(rows, list)
            ),
            "failed_symbols": dict(failed_symbols) if isinstance(failed_symbols, Mapping) else {},
            "case_symbol_overlap": len(compatible_symbols),
        },
    )
    blockers = (
        "approve the exact six-month baseline and five-day smoothing boundary",
        "approve an issuer-disjoint Discovery/Evolution-Validation/Locked-Test split manifest",
        "recompute labels; legacy terminal-return labels are incompatible",
    )
    return LocalEvolutionInventory(
        cases=case_summary,
        documents=document_summary,
        adjusted_prices=price_summary,
        compatible_case_count=compatible_case_count,
        incompatible_label_reason=(
            "legacy cases use terminal-return winner/failure labels, while the active "
            "contract uses six-month realized_max_multiple"
        ),
        migration_ready=False,
        blockers=blockers,
    )


def migrate_legacy_raw_info(
    *,
    cases_path: str | Path,
    documents_path: str | Path,
    adjusted_prices_path: str | Path,
    raw_info_root: str | Path,
) -> RawInfoMigrationReport:
    """Convert only point-in-time source facts; labels/future outcomes stay out."""

    RawInfoOracle.load_or_create(raw_info_root)
    inventory = inventory_local_evolution_inputs(
        cases_path=cases_path,
        documents_path=documents_path,
        adjusted_prices_path=adjusted_prices_path,
    )
    case_data = _read_json(Path(cases_path))
    document_data = _read_json(Path(documents_path))
    price_data = _read_json(Path(adjusted_prices_path))
    store = RawInfoStore(raw_info_root)

    migrated_documents = 0
    appended_documents = 0
    skipped_empty = 0
    documents_by_symbol = document_data.get("documents_by_symbol", {})
    for symbol, rows in sorted(documents_by_symbol.items()):
        if not isinstance(rows, list):
            continue
        company_id = _company_id_from_symbol(str(symbol))
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            content = str(row.get("text", "")).strip()
            if not content:
                skipped_empty += 1
                continue
            published_at = _date_at_utc(row.get("published_date"), "published_date")
            available_at = _date_at_utc(row.get("available_date"), "available_date")
            source_type = str(row.get("kind", "news")).casefold()
            if source_type not in {"filing", "news"}:
                raise ValidationError(f"unsupported legacy document kind: {source_type}")
            original_id = str(row.get("document_id") or row.get("source_id") or "")
            stable_seed = json.dumps(
                {
                    "symbol": symbol,
                    "original_id": original_id,
                    "available_at": available_at.isoformat(),
                    "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                },
                sort_keys=True,
            )
            document_id = "legacydoc_" + hashlib.sha256(
                stable_seed.encode("utf-8")
            ).hexdigest()[:24]
            appended = store.append(
                RawInfoDocument.create(
                    document_id=document_id,
                    company_id=company_id,
                    source_type=source_type,
                    published_at=published_at,
                    available_at=available_at,
                    content=content,
                    metadata={
                        "original_document_id": original_id,
                        "source_id": row.get("source_id"),
                        "source_url": row.get("source_url"),
                        "title": row.get("title"),
                        "symbol": str(symbol),
                    },
                )
            )
            migrated_documents += 1
            appended_documents += int(appended)

    bars_by_symbol = price_data.get("bars_by_symbol", {})
    cases_without_prices: list[str] = []
    migrated_market = 0
    appended_market = 0
    for row in case_data.get("cases", ()):
        symbol = _case_symbol(row)
        case_id = str(row.get("case_id", "")) if isinstance(row, Mapping) else ""
        prediction_date = _case_as_of_date(row)
        if symbol is None or prediction_date is None:
            cases_without_prices.append(case_id or "unknown-case")
            continue
        bars = bars_by_symbol.get(symbol, ())
        if not isinstance(bars, list):
            bars = ()
        historical_bars = [
            bar
            for bar in bars
            if isinstance(bar, Mapping)
            and bar.get("as_of_date")
            and str(bar["as_of_date"]) < prediction_date
            and bar.get("adjusted_close") is not None
        ][-252:]
        prices = [float(bar["adjusted_close"]) for bar in historical_bars]
        if not prices:
            cases_without_prices.append(case_id or f"{symbol}:{prediction_date}")
            continue
        company_id = _company_id_from_symbol(symbol)
        prediction_time = _date_at_utc(prediction_date, "case as_of_date")
        document_id = (
            "market_"
            + hashlib.sha256(f"{symbol}:{prediction_date}".encode("utf-8")).hexdigest()[:24]
        )
        content = (
            f"Adjusted close history through {historical_bars[-1]['as_of_date']}; "
            f"{len(prices)} observations; latest adjusted close {prices[-1]:.8g}."
        )
        appended = store.append(
            RawInfoDocument.create(
                document_id=document_id,
                company_id=company_id,
                source_type="market_data",
                published_at=prediction_time,
                available_at=prediction_time,
                content=content,
                metadata={
                    "symbol": symbol,
                    "prices": prices,
                    "last_bar_date": historical_bars[-1]["as_of_date"],
                    "price_source": price_data.get("source"),
                    "prediction_date": prediction_date,
                },
            )
        )
        migrated_market += 1
        appended_market += int(appended)

    return RawInfoMigrationReport(
        raw_info_root=str(Path(raw_info_root).resolve()),
        source_inventory_hash=inventory.inventory_hash,
        source_document_count=int(inventory.documents.facts["document_count"]),
        migrated_source_documents=migrated_documents,
        migrated_market_snapshots=migrated_market,
        appended_source_documents=appended_documents,
        appended_market_snapshots=appended_market,
        skipped_empty_documents=skipped_empty,
        cases_without_price_history=tuple(cases_without_prices),
    )


def _surge_label_contract() -> dict[str, Any]:
    """Return the shared six-month surge label contract."""

    return {
        "horizon": "six_calendar_months",
        "baseline": "mean_last_5_complete_adjusted_closes_strictly_before_as_of",
        "future_peak": "max_mean_5_consecutive_adjusted_closes_after_as_of",
        "binary_threshold": 2.0,
        "magnitude_classes": ["2-3x", "3-10x", "10x+"],
    }


def prepare_dataset_proposal(
    *,
    cases_path: str | Path,
    documents_path: str | Path,
    adjusted_prices_path: str | Path,
    output_root: str | Path,
    split_seed: str = "information-plan-evolution-v1",
) -> DatasetProposalReport:
    """Recompute the approved label semantics and propose issuer-disjoint splits."""

    inventory = inventory_local_evolution_inputs(
        cases_path=cases_path,
        documents_path=documents_path,
        adjusted_prices_path=adjusted_prices_path,
    )
    case_data = _read_json(Path(cases_path))
    price_data = _read_json(Path(adjusted_prices_path))
    bars_by_symbol = price_data.get("bars_by_symbol", {})
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    seen_case_ids: set[str] = set()
    for legacy_case in case_data.get("cases", ()):
        if not isinstance(legacy_case, Mapping):
            continue
        symbol = _case_symbol(legacy_case)
        prediction_date_text = _case_as_of_date(legacy_case)
        legacy_ref = str(legacy_case.get("case_id", "unknown-case"))
        if symbol is None or prediction_date_text is None:
            excluded.append({"legacy_case_ref": legacy_ref, "reason": "missing_case_identity"})
            continue
        try:
            prediction_date = date.fromisoformat(prediction_date_text)
            label = _six_month_smoothed_multiple(
                bars_by_symbol.get(symbol, ()), prediction_date
            )
        except ValidationError as exc:
            excluded.append({"legacy_case_ref": legacy_ref, "reason": str(exc)})
            continue
        company_id = _company_id_from_symbol(symbol)
        case_id = f"{company_id}:{prediction_date.strftime('%Y%m%d')}"
        if case_id in seen_case_ids:
            excluded.append({"legacy_case_ref": legacy_ref, "reason": "duplicate_case_id"})
            continue
        seen_case_ids.add(case_id)
        packet = legacy_case.get("packet", {})
        company = packet.get("company", {}) if isinstance(packet, Mapping) else {}
        ticker = company.get("ticker", {}) if isinstance(company, Mapping) else {}
        company_name = ticker.get("company_name") if isinstance(ticker, Mapping) else None
        basic_info = {
            "company_name": company_name or symbol,
            "ticker": symbol,
            "market_cap": company.get("market_cap_usd") if isinstance(company, Mapping) else None,
            "industry": company.get("industry") if isinstance(company, Mapping) else None,
            "business_description": None,
            "revenue_segments": [],
            "development_stage": None,
            "identity_aliases": [item for item in (symbol, company_name) if item],
        }
        eligible.append(
            {
                "case_id": case_id,
                "company_id": company_id,
                "prediction_time": datetime.combine(
                    prediction_date, datetime.min.time(), tzinfo=timezone.utc
                ).isoformat(),
                "basic_info": basic_info,
                "ground_truth": {
                    "realized_max_multiple": label["realized_max_multiple"],
                    "is_surge": label["is_surge"],
                    "magnitude": label["magnitude"],
                },
                "label_provenance": {
                    "baseline_mean": label["baseline_mean"],
                    "future_peak_mean": label["future_peak_mean"],
                    "baseline_dates": label["baseline_dates"],
                    "future_peak_dates": label["future_peak_dates"],
                    "horizon_end": label["horizon_end"],
                    "legacy_case_ref_hash": hashlib.sha256(
                        legacy_ref.encode("utf-8")
                    ).hexdigest(),
                },
            }
        )
    if not eligible:
        raise ValidationError("no local cases satisfy the active label contract")

    splits = _propose_issuer_splits(eligible, seed=split_seed)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}
    for split_name, rows in splits.items():
        path = root / f"{split_name}.json"
        payload = {
            "schema_version": "evolution-dataset-split-v1",
            "split": split_name,
            "case_count": len(rows),
            "cases": rows,
        }
        _write_or_verify_json(path, payload)
        artifacts[split_name] = {
            "path": str(path.resolve()),
            "sha256": _sha256_file(path),
            "case_count": len(rows),
            "issuer_count": len({row["company_id"] for row in rows}),
            "surge_count": sum(bool(row["ground_truth"]["is_surge"]) for row in rows),
        }
    excluded_path = root / "excluded_cases.json"
    _write_or_verify_json(
        excluded_path,
        {
            "schema_version": "evolution-dataset-exclusions-v1",
            "excluded_case_count": len(excluded),
            "cases": excluded,
        },
    )
    manifest = {
        "schema_version": "evolution-dataset-manifest-proposal-v1",
        "approval_status": "proposal_only_pending_human_review",
        "split_seed": split_seed,
        "split_policy": {
            "unit": "issuer",
            "strata": "issuer_has_any_surge_case",
            "target_ratios": {
                "discovery": 0.60,
                "evolution_validation": 0.25,
                "locked_test": 0.15,
            },
        },
        "label_contract": _surge_label_contract(),
        "source_inventory_hash": inventory.inventory_hash,
        "eligible_case_count": len(eligible),
        "excluded_case_count": len(excluded),
        "artifacts": artifacts,
        "excluded_cases": {
            "path": str(excluded_path.resolve()),
            "sha256": _sha256_file(excluded_path),
        },
        "locked_test_sealed": True,
        "locked_test_accessed": False,
    }
    manifest_path = root / "dataset_manifest.proposal.json"
    _write_or_verify_json(manifest_path, manifest)
    return DatasetProposalReport(
        manifest_path=str(manifest_path.resolve()),
        manifest_hash=_sha256_file(manifest_path),
        eligible_case_count=len(eligible),
        excluded_case_count=len(excluded),
        split_case_counts={name: len(rows) for name, rows in splits.items()},
        split_issuer_counts={
            name: len({row["company_id"] for row in rows})
            for name, rows in splits.items()
        },
        split_surge_counts={
            name: sum(bool(row["ground_truth"]["is_surge"]) for row in rows)
            for name, rows in splits.items()
        },
    )


def _load_anchor_case_spec(path: Path) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    payload = _read_json(path)
    if payload.get("schema_version") != "information-plan-anchor-spec-v1":
        raise ValidationError("unsupported Information Plan Anchor spec schema")
    unhashed = dict(payload)
    expected_hash = str(unhashed.pop("spec_hash", ""))
    if not expected_hash or _canonical_hash(unhashed) != expected_hash:
        raise ValidationError("Information Plan Anchor spec hash mismatch")
    raw_cases = payload.get("positive_cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != 9:
        raise ValidationError("Anchor spec requires exactly nine positive cases")
    cases: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    label_counts = {label: 0 for label in EVALUATION_LABELS[1:]}
    control_targets = 0
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            raise ValidationError("Anchor positive case must be an object")
        symbol = str(raw.get("symbol", "")).strip().upper()
        prediction_date = str(raw.get("prediction_date", ""))
        expected_label = str(raw.get("expected_label", ""))
        try:
            date.fromisoformat(prediction_date)
        except ValueError as exc:
            raise ValidationError("Anchor prediction date is invalid") from exc
        if not symbol or (symbol, prediction_date) in seen:
            raise ValidationError("Anchor positive symbol/date must be unique")
        if expected_label not in label_counts:
            raise ValidationError("Anchor positive label is invalid")
        match_control = raw.get("match_control", False)
        if type(match_control) is not bool:
            raise ValidationError("Anchor match_control must be a JSON boolean")
        control_targets += int(match_control)
        label_counts[expected_label] += 1
        seen.add((symbol, prediction_date))
        cases.append(
            {
                "symbol": symbol,
                "prediction_date": prediction_date,
                "expected_label": expected_label,
                "match_control": match_control,
                "rationale": str(raw.get("rationale", "")).strip(),
            }
        )
    if label_counts != {"2_3x": 5, "3_10x": 3, "10x_plus": 1}:
        raise ValidationError("Anchor positive cases must have exact 5/3/1 counts")
    if control_targets != 7:
        raise ValidationError("Anchor spec requires exactly seven control targets")
    return payload, tuple(cases)


def prepare_expanded_dataset_proposal(
    *,
    universe_path: str | Path,
    full_price_archive_path: str | Path,
    output_root: str | Path,
    prediction_dates: Iterable[date],
    target_issuers: int | None = None,
    stratum_weights: Mapping[str, float] | None = None,
    split_seed: str = "expanded-information-plan-evolution-v1",
    identity_decisions_path: str | Path | None = None,
    anchor_cases_path: str | Path,
) -> ExpandedDatasetProposalReport:
    """Build a zero-network fixed-date case-library proposal from local prices.

    All eligible deduplicated issuers are included by default. ``target_issuers``
    remains available only for explicitly bounded fixture or diagnostic proposals.
    """

    if target_issuers is not None and target_issuers < 6:
        raise ValidationError("expanded dataset target_issuers must be at least 6")
    if target_issuers is None and stratum_weights is not None:
        raise ValidationError(
            "expanded dataset stratum_weights require an explicit target_issuers cap"
        )
    dates = tuple(sorted(set(prediction_dates)))
    if not dates:
        raise ValidationError("expanded dataset requires prediction dates")
    anchor_path = Path(anchor_cases_path)
    anchor_spec, positive_anchor_specs = _load_anchor_case_spec(anchor_path)
    if not {
        date.fromisoformat(item["prediction_date"])
        for item in positive_anchor_specs
    }.issubset(set(dates)):
        raise ValidationError("Anchor dates must be included in prediction_dates")
    universe_file = Path(universe_path)
    price_file = Path(full_price_archive_path)
    universe = _read_json(universe_file)
    raw_listings = universe.get("listings", ())
    if not isinstance(raw_listings, list):
        raise ValidationError("clean-universe artifact listings must be a list")
    listings: dict[str, dict[str, Any]] = {}
    for raw_listing in raw_listings:
        if not isinstance(raw_listing, Mapping) or not raw_listing.get("symbol"):
            raise ValidationError("clean-universe listing is missing symbol")
        symbol = str(raw_listing["symbol"]).upper()
        listing = dict(raw_listing)
        existing = listings.get(symbol)
        if existing is not None and existing != listing:
            raise ValidationError(f"conflicting clean-universe listing: {symbol}")
        listings[symbol] = listing
    if not listings:
        raise ValidationError("clean-universe artifact has no listings")
    source_listing_count = len(listings)
    identity_decisions: dict[str, dict[str, Any]] = {}
    identity_artifact: dict[str, Any] | None = None
    identity_review_status: str | None = None
    if identity_decisions_path is not None:
        identity_path = Path(identity_decisions_path)
        identity_payload, identity_decisions = _load_expansion_identity_decisions(
            identity_path,
            prediction_dates=dates,
            listings=listings,
        )
        identity_artifact = _artifact_file_identity(identity_path)
        identity_review_status = str(identity_payload["review_status"])
    identity_exclusions: list[dict[str, str]] = []
    active_listings: dict[str, dict[str, Any]] = {}
    cik_update_count = 0
    for symbol, listing in listings.items():
        decision = identity_decisions.get(symbol)
        if decision is not None and decision["action"] == "exclude":
            identity_exclusions.append(
                {
                    "symbol": symbol,
                    "company_id": _expansion_company_id(listing),
                    "reason": "identity_decision_exclude",
                    "decision_id": str(decision["decision_id"]),
                }
            )
            continue
        resolved_listing = dict(listing)
        if decision is not None and decision["action"] == "set_cik":
            resolved_listing["cik"] = str(decision["cik"])
            cik_update_count += 1
        active_listings[symbol] = resolved_listing

    normal_listings, security_exclusions = _filter_normal_stock_listings(
        active_listings
    )
    (
        price_metadata,
        candidates,
        price_exclusions,
        priced_symbol_count,
        exact_anchor_candidates,
    ) = (
        _stream_expansion_candidates(
            price_file,
            listings=normal_listings,
            prediction_dates=dates,
            positive_anchor_specs=positive_anchor_specs,
        )
    )
    exclusions = [*security_exclusions, *price_exclusions]
    exclusions.extend(identity_exclusions)
    deduplicated, duplicate_exclusions = _deduplicate_expansion_candidates(
        candidates,
        seed=split_seed,
    )
    exclusions.extend(duplicate_exclusions)
    anchor_cases, anchor_company_ids = _resolve_anchor_cases(
        positive_specs=positive_anchor_specs,
        exact_candidates=exact_anchor_candidates,
        candidates=deduplicated,
        seed=f"{split_seed}:anchor-controls",
    )
    random_library_candidates = [
        candidate
        for candidate in deduplicated
        if str(candidate["company_id"]) not in anchor_company_ids
    ]
    available_counts = {
        stratum: sum(
            candidate["selection_stratum"] == stratum
            for candidate in random_library_candidates
        )
        for stratum in EXPANSION_STRATUM_ORDER
    }
    if not random_library_candidates:
        raise ValidationError("expanded dataset has no eligible deduplicated issuers")
    if target_issuers is None:
        selection_mode = "all_eligible"
        requested_issuer_cap = None
        selection_weights: dict[str, float] | None = None
        allocations = dict(available_counts)
        selected = list(random_library_candidates)
    else:
        if target_issuers > len(random_library_candidates):
            raise ValidationError(
                "expanded dataset target exceeds eligible deduplicated issuers"
            )
        selection_mode = "stratified_cap"
        requested_issuer_cap = target_issuers
        selection_weights = _validate_expansion_weights(
            DEFAULT_EXPANSION_STRATUM_WEIGHTS
            if stratum_weights is None
            else stratum_weights
        )
        allocations = _allocate_expansion_strata(
            available_counts,
            target_issuers=target_issuers,
            weights=selection_weights,
        )
        selected = []
        for stratum in EXPANSION_STRATUM_ORDER:
            pool = [
                candidate
                for candidate in random_library_candidates
                if candidate["selection_stratum"] == stratum
            ]
            selected.extend(
                _select_diverse_expansion_issuers(
                    pool,
                    count=allocations[stratum],
                    seed=f"{split_seed}:{stratum}",
                )
            )
    selected.sort(key=lambda item: str(item["company_id"]))
    if len(selected) != sum(allocations.values()):
        raise ValidationError("expanded dataset selector returned wrong issuer count")
    split_candidates = _propose_expanded_issuer_splits(selected, seed=split_seed)

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    universe_identity = _artifact_file_identity(universe_file)
    price_identity = _artifact_file_identity(price_file)
    source_inputs: dict[str, Any] = {
        "universe": universe_identity,
        "adjusted_prices": price_identity,
        "anchor_spec": _artifact_file_identity(anchor_path),
    }
    if identity_artifact is not None:
        source_inputs["identity_decisions"] = identity_artifact
    source_inventory_hash = _canonical_hash(
        source_inputs
    )
    exclusion_reason_counts: dict[str, int] = {}
    for item in exclusions:
        reason = str(item["reason"])
        exclusion_reason_counts[reason] = exclusion_reason_counts.get(reason, 0) + 1

    inventory_path = root / "candidate_inventory.json"
    _write_or_verify_json(
        inventory_path,
        {
            "schema_version": "expanded-case-candidate-inventory-v2",
            "source_inventory_hash": source_inventory_hash,
            "prediction_dates": [value.isoformat() for value in dates],
            "eligible_issuer_count": len(random_library_candidates)
            + len(anchor_company_ids),
            "available_stratum_counts": available_counts,
            "integrity_policy": {
                "normal_stock_exchanges": sorted(NORMAL_STOCK_EXCHANGES),
                "minimum_pre_prediction_average_dollar_volume": (
                    MIN_PRE_PREDICTION_DOLLAR_VOLUME
                ),
                "maximum_adjusted_close_step_up": MAX_ADJUSTED_CLOSE_STEP_UP,
                "minimum_adjusted_close_step_down": MIN_ADJUSTED_CLOSE_STEP_DOWN,
                "resolved_cik_required": True,
                "operating_common_stock_required": True,
            },
            "anchor_cases": anchor_cases,
            "candidates": sorted(
                random_library_candidates,
                key=lambda item: (str(item["selection_stratum"]), str(item["company_id"])),
            ),
        },
    )
    exclusions_path = root / "excluded_issuers.json"
    _write_or_verify_json(
        exclusions_path,
        {
            "schema_version": "expanded-case-exclusions-v1",
            "excluded_record_count": len(exclusions),
            "reason_counts": dict(sorted(exclusion_reason_counts.items())),
            "records": sorted(
                exclusions,
                key=lambda item: (str(item["reason"]), str(item.get("symbol", ""))),
            ),
        },
    )
    selected_path = root / "selected_issuers.json"
    _write_or_verify_json(
        selected_path,
        {
            "schema_version": "expanded-case-selected-issuers-v2",
            "selection_seed": split_seed,
            "selection_mode": selection_mode,
            "requested_issuer_cap": requested_issuer_cap,
            "selection_weights": selection_weights,
            "selected_stratum_counts": allocations,
            "issuers": selected,
        },
    )
    anchor_scope_companies: dict[str, dict[str, Any]] = {}
    for case in anchor_cases:
        symbol = str(case["label_provenance"]["source_symbol"])
        listing = normal_listings[symbol]
        company_id = str(case["company_id"])
        anchor_scope_companies[company_id] = {
            "company_id": company_id,
            "cik": _normalized_cik(listing.get("cik")),
            "symbol": symbol,
            "company_name": str(listing.get("name") or symbol),
        }
    acquisition_companies = {
        str(item["company_id"]): {
            "company_id": item["company_id"],
            "cik": item["cik"],
            "symbol": item["symbol"],
            "company_name": item["company_name"],
        }
        for item in selected
    }
    acquisition_companies.update(anchor_scope_companies)
    acquisition_scope_path = root / "acquisition_scope.json"
    _write_or_verify_json(
        acquisition_scope_path,
        {
            "schema_version": "expanded-case-acquisition-scope-v1",
            "source_inventory_hash": source_inventory_hash,
            "prediction_dates": [value.isoformat() for value in dates],
            "company_count": len(acquisition_companies),
            "companies": [
                acquisition_companies[company_id]
                for company_id in sorted(acquisition_companies)
            ],
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
    )

    artifacts: dict[str, dict[str, Any]] = {}
    split_case_counts: dict[str, int] = {}
    split_issuer_counts: dict[str, int] = {}
    split_surge_counts: dict[str, int] = {}
    anchor_split_path = root / "anchor.json"
    _write_or_verify_json(
        anchor_split_path,
        {
            "schema_version": "evolution-dataset-split-v1",
            "split": "anchor",
            "case_count": len(anchor_cases),
            "cases": anchor_cases,
        },
    )
    split_case_counts["anchor"] = len(anchor_cases)
    split_issuer_counts["anchor"] = len(anchor_company_ids)
    split_surge_counts["anchor"] = sum(
        bool(case["ground_truth"]["is_surge"]) for case in anchor_cases
    )
    artifacts["anchor"] = {
        "path": str(anchor_split_path.resolve()),
        "sha256": _sha256_file(anchor_split_path),
        "case_count": len(anchor_cases),
        "issuer_count": len(anchor_company_ids),
        "surge_count": split_surge_counts["anchor"],
    }
    for split_name, issuer_rows in split_candidates.items():
        cases = sorted(
            (
                case
                for issuer in issuer_rows
                for case in issuer["cases"]
            ),
            key=lambda item: str(item["case_id"]),
        )
        path = root / f"{split_name}.json"
        _write_or_verify_json(
            path,
            {
                "schema_version": "evolution-dataset-split-v1",
                "split": split_name,
                "case_count": len(cases),
                "cases": cases,
            },
        )
        issuer_count = len(issuer_rows)
        surge_count = sum(bool(case["ground_truth"]["is_surge"]) for case in cases)
        split_case_counts[split_name] = len(cases)
        split_issuer_counts[split_name] = issuer_count
        split_surge_counts[split_name] = surge_count
        artifacts[split_name] = {
            "path": str(path.resolve()),
            "sha256": _sha256_file(path),
            "case_count": len(cases),
            "issuer_count": issuer_count,
            "surge_count": surge_count,
        }

    selected_counts = {
        stratum: sum(item["selection_stratum"] == stratum for item in selected)
        for stratum in EXPANSION_STRATUM_ORDER
    }
    manifest = {
        "schema_version": "expanded-evolution-dataset-manifest-proposal-v3",
        "approval_status": "proposal_only_pending_human_review",
        "approval_blockers": [
            "acquire and audit point-in-time filings, profiles, news, and other required Raw Info",
            *(
                ["human-review the exact applied identity-decision artifact"]
                if identity_review_status == "agent_proposed_pending_human_review"
                else []
            ),
        ],
        "source_inventory_hash": source_inventory_hash,
        "sources": {
            "clean_universe": universe_identity,
            "adjusted_prices": price_identity,
            "anchor_spec": _artifact_file_identity(anchor_path),
            "identity_decisions": identity_artifact,
            "price_metadata": price_metadata,
        },
        "identity_decisions": {
            "applied": identity_artifact is not None,
            "review_status": identity_review_status,
            "decision_count": len(identity_decisions),
            "cik_update_count": cik_update_count,
            "exclusion_count": len(identity_exclusions),
        },
        "case_generation": {
            "kind": "shared_fixed_calendar_case_opportunities",
            "prediction_dates": [value.isoformat() for value in dates],
            "maximum_cases_per_issuer": len(dates),
            "eligibility": "each_case_independently_passes_point_in_time_normality_gate",
            "issuer_retention": "at_least_one_eligible_case",
            "issuer_identity": "required_zero_padded_cik",
            "normal_stock_gate": {
                "status": "machine_verified",
                "supported_exchanges": sorted(NORMAL_STOCK_EXCHANGES),
                "minimum_pre_prediction_average_dollar_volume": (
                    MIN_PRE_PREDICTION_DOLLAR_VOLUME
                ),
                "adjusted_price_step_bounds": [
                    MIN_ADJUSTED_CLOSE_STEP_DOWN,
                    MAX_ADJUSTED_CLOSE_STEP_UP,
                ],
            },
        },
        "anchor_evaluation": {
            "spec_id": str(anchor_spec["anchor_id"]),
            "spec_hash": str(anchor_spec["spec_hash"]),
            "case_count": len(anchor_cases),
            "label_counts": {
                label: sum(
                    _serialized_evaluation_label(case) == label
                    for case in anchor_cases
                )
                for label in EVALUATION_LABELS
            },
            "positive_selection": "reviewed_symbol_prediction_date",
            "negative_selection": "deterministic_matched_controls",
            "issuer_removed_before_other_splits": True,
        },
        "selection": {
            "mode": selection_mode,
            "requested_issuer_cap": requested_issuer_cap,
            "available_issuer_count": len(random_library_candidates),
            "stratum_order": list(EXPANSION_STRATUM_ORDER),
            "stratum_definition": "maximum_realized_multiple_across_eligible_prediction_dates",
            "weights": selection_weights,
            "available_stratum_counts": available_counts,
            "selected_stratum_counts": selected_counts,
            "diversity_rotation": (
                ["exchange", "ipo_age_bucket", "dollar_liquidity_bucket"]
                if selection_mode == "stratified_cap"
                else []
            ),
            "seed": split_seed,
            "sampling_boundary": (
                "All normal eligible non-Anchor issuers are included before the issuer-level "
                "split; controlled label balancing occurs only in fixed Anchor and Fast-loop Random snapshots."
                if selection_mode == "all_eligible"
                else "An explicit diagnostic cap outcome-enriches the selected library; "
                "unweighted metrics do not estimate live market prevalence or returns."
            ),
        },
        "split_policy": {
            "unit": "issuer",
            "strata": "selection_stratum",
            "anchor_issuers_assigned_first": True,
            "minimum_validation_issuers_per_stratum": (
                "two_when_at_least_four_are_available_otherwise_one"
            ),
            "target_ratios": {
                "discovery": 0.60,
                "evolution_validation": 0.25,
                "locked_test": 0.15,
            },
        },
        "label_contract": _surge_label_contract(),
        "counts": {
            "universe_listings": source_listing_count,
            "identity_eligible_universe_listings": len(active_listings),
            "normal_stock_universe_listings": len(normal_listings),
            "priced_symbols": priced_symbol_count,
            "eligible_issuers": len(random_library_candidates)
            + len(anchor_company_ids),
            "anchor_issuers": len(anchor_company_ids),
            "random_library_issuers": len(random_library_candidates),
            "selected_issuers": len(selected) + len(anchor_company_ids),
            "selected_cases": sum(split_case_counts.values()),
            "exclusion_records": len(exclusions),
        },
        "audit_artifacts": {
            "candidate_inventory": {
                "path": str(inventory_path.resolve()),
                "sha256": _sha256_file(inventory_path),
            },
            "excluded_issuers": {
                "path": str(exclusions_path.resolve()),
                "sha256": _sha256_file(exclusions_path),
            },
            "selected_issuers": {
                "path": str(selected_path.resolve()),
                "sha256": _sha256_file(selected_path),
            },
            "acquisition_scope": {
                "path": str(acquisition_scope_path.resolve()),
                "sha256": _sha256_file(acquisition_scope_path),
            },
            "anchor_spec": _artifact_file_identity(anchor_path),
        },
        "artifacts": artifacts,
        "locked_test_sealed": True,
        "locked_test_accessed": False,
        "external_calls": 0,
    }
    manifest_path = root / "dataset_manifest.proposal.json"
    _write_or_verify_json(manifest_path, manifest)
    return ExpandedDatasetProposalReport(
        manifest_path=str(manifest_path.resolve()),
        manifest_hash=_sha256_file(manifest_path),
        universe_listing_count=source_listing_count,
        priced_symbol_count=priced_symbol_count,
        eligible_issuer_count=len(random_library_candidates) + len(anchor_company_ids),
        selection_mode=selection_mode,
        selected_issuer_count=len(selected) + len(anchor_company_ids),
        case_count=sum(split_case_counts.values()),
        available_stratum_counts=available_counts,
        selected_stratum_counts=selected_counts,
        exclusion_reason_counts=dict(sorted(exclusion_reason_counts.items())),
        split_case_counts=split_case_counts,
        split_issuer_counts=split_issuer_counts,
        split_surge_counts=split_surge_counts,
    )


def approve_dataset_proposal(
    *,
    proposal_manifest_path: str | Path,
    expected_proposal_hash: str,
    approved_by: str,
) -> Path:
    """Create a distinct approved manifest bound to the exact reviewed proposal."""

    if not approved_by.strip():
        raise ValidationError("dataset approval requires reviewer identity")
    proposal_path = Path(proposal_manifest_path)
    actual_hash = _sha256_file(proposal_path)
    if actual_hash != expected_proposal_hash:
        raise ValidationError("dataset proposal hash does not match reviewed content")
    proposal = _read_json(proposal_path)
    if proposal.get("approval_status") != "proposal_only_pending_human_review":
        raise ValidationError("dataset proposal is not pending human review")
    _validate_v5_dataset_proposal_for_approval(proposal)
    approved = {
        **proposal,
        "schema_version": "evolution-dataset-manifest-v1",
        "approval_status": "human_approved",
        "approved_by": approved_by.strip(),
        "approved_proposal_hash": actual_hash,
    }
    approved_path = proposal_path.with_name("dataset_manifest.approved.json")
    _write_or_verify_json(approved_path, approved)
    return approved_path


def _validate_v5_dataset_proposal_for_approval(
    proposal: Mapping[str, Any],
) -> None:
    if proposal.get("schema_version") != "expanded-evolution-dataset-manifest-proposal-v3":
        raise ValidationError(
            "v5 dataset approval requires an expanded proposal with Anchor"
        )
    generation = dict(proposal.get("case_generation", {}))
    normal_gate = dict(generation.get("normal_stock_gate", {}))
    if (
        generation.get("eligibility")
        != "each_case_independently_passes_point_in_time_normality_gate"
        or normal_gate.get("status") != "machine_verified"
    ):
        raise ValidationError("v5 dataset proposal is missing the normal-stock gate")
    artifacts = dict(proposal.get("artifacts", {}))
    if (
        proposal.get("locked_test_sealed") is not True
        or proposal.get("locked_test_accessed") is not False
    ):
        raise ValidationError("v5 dataset proposal must keep Locked Test sealed")
    loaded: dict[str, tuple[EvolutionCase, ...]] = {}
    for split_name in (
        "discovery",
        "anchor",
        "evolution_validation",
        "locked_test",
    ):
        metadata = dict(artifacts.get(split_name, {}))
        if not metadata:
            raise ValidationError(
                f"v5 dataset proposal is missing {split_name} split"
            )
        split_path = Path(str(metadata.get("path", "")))
        if not split_path.is_file() or _sha256_file(split_path) != metadata.get(
            "sha256"
        ):
            raise ValidationError(f"dataset split hash mismatch: {split_name}")
        if split_name not in {"anchor", "evolution_validation"}:
            continue
        split = _read_json(split_path)
        if split.get("split") != split_name:
            raise ValidationError(f"dataset split identity mismatch: {split_name}")
        rows = split.get("cases", ())
        if not isinstance(rows, list):
            raise ValidationError(f"dataset split cases are invalid: {split_name}")
        if int(metadata.get("case_count", -1)) != len(rows):
            raise ValidationError(f"dataset split case count mismatch: {split_name}")
        loaded[split_name] = tuple(
            EvolutionCase(
                case_id=str(row["case_id"]),
                company_id=str(row["company_id"]),
                prediction_time=datetime.fromisoformat(str(row["prediction_time"])),
                basic_info=dict(row["basic_info"]),
                ground_truth=GroundTruth.from_dict(dict(row["ground_truth"])),
            )
            for row in rows
        )
    with tempfile.TemporaryDirectory() as directory:
        EvaluationDatasetManager(
            directory,
            pool=loaded["evolution_validation"],
            anchor_cases=loaded["anchor"],
        )


def _six_month_smoothed_multiple(
    raw_bars: Any, prediction_date: date
) -> dict[str, Any]:
    if not isinstance(raw_bars, (list, tuple)):
        raise ValidationError("missing adjusted price history")
    parsed: list[tuple[date, float]] = []
    for bar in raw_bars:
        if not isinstance(bar, Mapping) or not bar.get("as_of_date"):
            continue
        adjusted_close = bar.get("adjusted_close")
        if adjusted_close is None:
            continue
        value = float(adjusted_close)
        if value <= 0:
            continue
        parsed.append((date.fromisoformat(str(bar["as_of_date"])), value))
    parsed.sort(key=lambda item: item[0])
    baseline_rows = [item for item in parsed if item[0] < prediction_date][-5:]
    if len(baseline_rows) < 5:
        raise ValidationError("fewer_than_5_baseline_bars")
    horizon_end = _add_months(prediction_date, 6)
    future_rows = [
        item for item in parsed if prediction_date <= item[0] <= horizon_end
    ]
    if len(future_rows) < 5:
        raise ValidationError("fewer_than_5_future_bars")
    if future_rows[-1][0] < horizon_end - timedelta(days=7):
        raise ValidationError("incomplete_six_month_price_horizon")
    baseline_mean = sum(value for _, value in baseline_rows) / 5
    windows = [future_rows[index : index + 5] for index in range(len(future_rows) - 4)]
    peak_window = max(
        windows,
        key=lambda rows: sum(value for _, value in rows) / len(rows),
    )
    future_peak_mean = sum(value for _, value in peak_window) / 5
    multiple = future_peak_mean / baseline_mean
    if multiple < 2.0:
        magnitude = None
    elif multiple < 3.0:
        magnitude = "2-3x"
    elif multiple < 10.0:
        magnitude = "3-10x"
    else:
        magnitude = "10x+"
    return {
        "realized_max_multiple": multiple,
        "is_surge": multiple >= 2.0,
        "magnitude": magnitude,
        "baseline_mean": baseline_mean,
        "future_peak_mean": future_peak_mean,
        "baseline_dates": [item[0].isoformat() for item in baseline_rows],
        "future_peak_dates": [item[0].isoformat() for item in peak_window],
        "horizon_end": horizon_end.isoformat(),
    }


def _add_months(value: date, months: int) -> date:
    total_month = value.month - 1 + months
    year = value.year + total_month // 12
    month = total_month % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _propose_issuer_splits(
    cases: list[dict[str, Any]], *, seed: str
) -> dict[str, list[dict[str, Any]]]:
    by_issuer: dict[str, list[dict[str, Any]]] = {}
    for row in cases:
        by_issuer.setdefault(str(row["company_id"]), []).append(row)
    strata: dict[bool, list[str]] = {False: [], True: []}
    for company_id, rows in by_issuer.items():
        strata[any(bool(row["ground_truth"]["is_surge"]) for row in rows)].append(
            company_id
        )
    issuer_split: dict[str, str] = {}
    for has_surge, issuer_ids in strata.items():
        if len(issuer_ids) < 3:
            raise ValidationError(
                "dataset requires at least three issuers in each surge-presence stratum"
            )
        ordered = sorted(
            issuer_ids,
            key=lambda company_id: hashlib.sha256(
                f"{seed}:{has_surge}:{company_id}".encode("utf-8")
            ).hexdigest(),
        )
        discovery_count, evolution_count, _ = _three_way_counts(len(ordered))
        for index, company_id in enumerate(ordered):
            if index < discovery_count:
                split = "discovery"
            elif index < discovery_count + evolution_count:
                split = "evolution_validation"
            else:
                split = "locked_test"
            issuer_split[company_id] = split
    result = {"discovery": [], "evolution_validation": [], "locked_test": []}
    for row in sorted(cases, key=lambda item: item["case_id"]):
        result[issuer_split[str(row["company_id"])]].append(row)
    return result


def _three_way_counts(total: int) -> tuple[int, int, int]:
    discovery = max(1, round(total * 0.60))
    evolution = max(1, round(total * 0.25))
    locked = total - discovery - evolution
    if locked < 1:
        discovery = max(1, discovery - (1 - locked))
        locked = total - discovery - evolution
    if min(discovery, evolution, locked) < 1:
        raise ValidationError("issuer stratum cannot support three non-empty splits")
    return discovery, evolution, locked


def _validate_expansion_weights(weights: Mapping[str, float]) -> dict[str, float]:
    if set(weights) != set(EXPANSION_STRATUM_ORDER):
        raise ValidationError("expanded dataset weights must name every fixed stratum")
    normalized = {key: float(weights[key]) for key in EXPANSION_STRATUM_ORDER}
    if any(value < 0 for value in normalized.values()) or sum(normalized.values()) <= 0:
        raise ValidationError("expanded dataset weights must be non-negative and non-zero")
    total = sum(normalized.values())
    return {key: normalized[key] / total for key in EXPANSION_STRATUM_ORDER}


def _load_expansion_identity_decisions(
    path: Path,
    *,
    prediction_dates: tuple[date, ...],
    listings: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    payload = _read_json(path)
    if payload.get("schema_version") != "expanded-case-identity-decisions-v1":
        raise ValidationError("unsupported expanded identity-decision schema")
    supplied_hash = str(payload.get("decision_hash") or "")
    without_hash = dict(payload)
    without_hash.pop("decision_hash", None)
    if supplied_hash != _canonical_hash(without_hash):
        raise ValidationError("expanded identity-decision hash mismatch")
    _reject_outcome_fields(payload)
    review_status = str(payload.get("review_status") or "")
    if review_status not in {
        "agent_proposed_pending_human_review",
        "human_reviewed",
    }:
        raise ValidationError("expanded identity-decision review status is invalid")
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise ValidationError("expanded identity decisions must be a list")
    if int(payload.get("decision_count", -1)) != len(decisions):
        raise ValidationError("expanded identity-decision count mismatch")
    by_symbol: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for raw in decisions:
        if not isinstance(raw, Mapping):
            raise ValidationError("expanded identity decision must be an object")
        decision = dict(raw)
        decision_id = str(decision.get("decision_id") or "").strip()
        symbol = str(decision.get("symbol") or "").strip().upper()
        action = str(decision.get("action") or "")
        if not decision_id or decision_id in seen_ids:
            raise ValidationError("expanded identity decision ids must be unique")
        if not symbol or symbol in by_symbol:
            raise ValidationError("expanded identity decision symbols must be unique")
        if symbol not in listings:
            raise ValidationError(
                f"expanded identity decision symbol is not in universe: {symbol}"
            )
        if action not in {"exclude", "set_cik"}:
            raise ValidationError("expanded identity decision action is invalid")
        applies_from = _parse_identity_date(
            decision.get("applies_from"), "applies_from"
        )
        applies_to = _parse_identity_date(
            decision.get("applies_to"), "applies_to"
        )
        if applies_to < applies_from:
            raise ValidationError("expanded identity decision date range is reversed")
        if prediction_dates[0] < applies_from or prediction_dates[-1] > applies_to:
            raise ValidationError(
                f"expanded identity decision does not cover prediction dates: {symbol}"
            )
        evidence = decision.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValidationError("expanded identity decision requires SEC evidence")
        normalized_cik: str | None = None
        if action == "set_cik":
            raw_cik = str(decision.get("cik") or "")
            if not re.fullmatch(r"\d{1,10}", raw_cik):
                raise ValidationError("expanded identity decision CIK is invalid")
            normalized_cik = raw_cik.zfill(10)
            decision["cik"] = normalized_cik
        for item in evidence:
            if not isinstance(item, Mapping):
                raise ValidationError("expanded identity evidence must be an object")
            source_url = str(item.get("source_url") or "")
            match = re.fullmatch(
                r"https://www\.sec\.gov/Archives/edgar/data/(\d+)/[^\s]+",
                source_url,
            )
            if match is None:
                raise ValidationError(
                    "expanded identity evidence must be an official SEC filing URL"
                )
            if normalized_cik is not None and match.group(1).zfill(10) != normalized_cik:
                raise ValidationError("expanded identity evidence CIK mismatch")
            filing_date = _parse_identity_date(
                item.get("filing_date"), "evidence filing_date"
            )
            if filing_date > prediction_dates[0]:
                raise ValidationError(
                    "expanded identity evidence postdates the earliest prediction date"
                )
            if not str(item.get("observed_fact") or "").strip():
                raise ValidationError(
                    "expanded identity evidence observed_fact is missing"
                )
        seen_ids.add(decision_id)
        by_symbol[symbol] = decision
    return payload, by_symbol


def _parse_identity_date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"invalid expanded identity {label}: {value}") from exc


def _filter_normal_stock_listings(
    listings: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    normalized: list[SecurityListing] = []
    parse_failures: dict[str, str] = {}
    for symbol, listing in listings.items():
        try:
            retrieved_at = datetime.fromisoformat(
                str(
                    listing.get("retrieved_at")
                    or datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
                )
            )
            ipo_date = (
                date.fromisoformat(str(listing["ipo_date"]))
                if listing.get("ipo_date")
                else None
            )
            delisting_date = (
                date.fromisoformat(str(listing["delisting_date"]))
                if listing.get("delisting_date")
                else None
            )
            normalized.append(
                SecurityListing(
                    symbol=symbol,
                    name=str(listing.get("name") or symbol),
                    exchange=str(listing.get("exchange") or ""),
                    asset_type=str(listing.get("asset_type") or ""),
                    status=str(listing.get("status") or ""),
                    source=str(listing.get("source") or "unknown"),
                    retrieved_at=retrieved_at,
                    cik=_normalized_cik(listing.get("cik")),
                    ipo_date=ipo_date,
                    delisting_date=delisting_date,
                )
            )
        except (TypeError, ValueError) as exc:
            parse_failures[symbol] = type(exc).__name__
    common_symbols = {
        listing.symbol for listing in eligible_common_stock_listings(normalized)
    }
    accepted: dict[str, dict[str, Any]] = {}
    exclusions: list[dict[str, str]] = []
    for symbol, listing in listings.items():
        reason: str | None = None
        if symbol in parse_failures:
            reason = "invalid_listing_metadata"
        elif symbol not in common_symbols:
            reason = "not_normal_common_stock"
        elif _normalized_cik(listing.get("cik")) is None:
            reason = "missing_reviewed_cik"
        elif str(listing.get("exchange") or "").upper() not in NORMAL_STOCK_EXCHANGES:
            reason = "unsupported_stock_exchange"
        elif not listing.get("ipo_date"):
            reason = "missing_listing_ipo_date"
        elif _looks_like_non_operating_issuer(
            str(listing.get("name") or "")
        ):
            reason = "non_operating_or_spac_issuer"
        elif listing.get("delisting_date"):
            reason = "delisted_security"
        if reason is None:
            accepted[symbol] = dict(listing)
        else:
            exclusions.append(
                {
                    "symbol": symbol,
                    "company_id": _expansion_company_id(listing),
                    "reason": reason,
                }
            )
    return accepted, exclusions


def _looks_like_non_operating_issuer(name: str) -> bool:
    normalized = name.casefold()
    return any(
        marker in normalized for marker in _NON_OPERATING_ISSUER_MARKERS
    ) or _SPAC_SERIES_NAME.search(name) is not None


def _stream_expansion_candidates(
    path: Path,
    *,
    listings: Mapping[str, Mapping[str, Any]],
    prediction_dates: tuple[date, ...],
    positive_anchor_specs: tuple[dict[str, Any], ...],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, str]],
    int,
    dict[tuple[str, str], dict[str, Any]],
]:
    if not path.is_file():
        raise ValidationError(f"large local price archive is missing: {path}")
    reader = _StreamingJSONReader(path)
    metadata: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    exact_anchor_candidates: dict[tuple[str, str], dict[str, Any]] = {}
    anchor_specs_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for spec in positive_anchor_specs:
        anchor_specs_by_symbol.setdefault(str(spec["symbol"]), []).append(spec)
    seen_symbols: set[str] = set()
    priced_symbol_count = 0
    try:
        reader.consume("{")
        while reader.peek() != "}":
            key = reader.decode()
            if not isinstance(key, str):
                raise ValidationError("large price archive top-level key is invalid")
            reader.consume(":")
            if key == "bars_by_symbol":
                reader.consume("{")
                while reader.peek() != "}":
                    raw_symbol = reader.decode()
                    if not isinstance(raw_symbol, str):
                        raise ValidationError("large price archive symbol key is invalid")
                    reader.consume(":")
                    raw_bars = reader.decode()
                    symbol = raw_symbol.upper()
                    listing = listings.get(symbol)
                    if listing is not None:
                        seen_symbols.add(symbol)
                        if not isinstance(raw_bars, list):
                            raise ValidationError("large price archive bars must be a list")
                        if raw_bars:
                            priced_symbol_count += 1
                        candidate, candidate_exclusions = _expansion_candidate(
                            listing,
                            raw_bars,
                            prediction_dates=prediction_dates,
                        )
                        if candidate is not None:
                            candidates.append(candidate)
                        exclusions.extend(candidate_exclusions)
                        for anchor_spec in anchor_specs_by_symbol.get(symbol, ()):
                            anchor_date = date.fromisoformat(
                                str(anchor_spec["prediction_date"])
                            )
                            exact_candidate, anchor_exclusions = _expansion_candidate(
                                listing,
                                raw_bars,
                                prediction_dates=(anchor_date,),
                            )
                            key = (symbol, anchor_date.isoformat())
                            if exact_candidate is not None:
                                exact_anchor_candidates[key] = exact_candidate
                            else:
                                exclusions.extend(
                                    {
                                        **anchor_exclusion,
                                        "reason": "anchor_"
                                        + str(anchor_exclusion["reason"]),
                                    }
                                    for anchor_exclusion in anchor_exclusions
                                )
                    if reader.peek() == ",":
                        reader.consume(",")
                    else:
                        break
                reader.consume("}")
            else:
                value = reader.decode()
                if key == "warnings" and isinstance(value, Mapping):
                    metadata["warning_count"] = len(value)
                elif key not in {"listings", "bars_by_symbol"}:
                    metadata[key] = value
            if reader.peek() == ",":
                reader.consume(",")
            else:
                break
        reader.consume("}")
    finally:
        reader.close()
    for symbol, listing in listings.items():
        if symbol not in seen_symbols:
            exclusions.append(
                {
                    "symbol": symbol,
                    "company_id": _expansion_company_id(listing),
                    "reason": "missing_price_history",
                }
            )
    return (
        metadata,
        candidates,
        exclusions,
        priced_symbol_count,
        exact_anchor_candidates,
    )


def _expansion_candidate(
    listing: Mapping[str, Any],
    raw_bars: list[Any],
    *,
    prediction_dates: tuple[date, ...],
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    symbol = str(listing["symbol"]).upper()
    company_id = _expansion_company_id(listing)
    ipo_date = str(listing.get("ipo_date") or "") or None
    if ipo_date:
        try:
            parsed_ipo_date = date.fromisoformat(ipo_date)
        except ValueError:
            return None, [
                {
                    "symbol": symbol,
                    "company_id": company_id,
                    "reason": "invalid_listing_ipo_date",
                }
            ]
    if not raw_bars:
        return None, [
            {
                "symbol": symbol,
                "company_id": company_id,
                "reason": "empty_price_history",
            }
        ]
    labels: list[tuple[date, dict[str, Any]]] = []
    liquidity_by_date: dict[date, float] = {}
    exclusions: list[dict[str, str]] = []
    for prediction_date in prediction_dates:
        if ipo_date and prediction_date < parsed_ipo_date:
            exclusions.append(
                {
                    "symbol": symbol,
                    "company_id": company_id,
                    "prediction_date": prediction_date.isoformat(),
                    "ipo_date": ipo_date,
                    "reason": "prediction_before_listing_ipo_date",
                }
            )
            continue
        integrity_reason = _adjusted_price_integrity_reason(
            raw_bars, prediction_date
        )
        if integrity_reason is not None:
            exclusions.append(
                {
                    "symbol": symbol,
                    "company_id": company_id,
                    "prediction_date": prediction_date.isoformat(),
                    "reason": integrity_reason,
                }
            )
            continue
        liquidity = _pre_prediction_average_dollar_volume(
            raw_bars, prediction_date
        )
        if liquidity is None:
            exclusions.append(
                {
                    "symbol": symbol,
                    "company_id": company_id,
                    "prediction_date": prediction_date.isoformat(),
                    "reason": "insufficient_pre_prediction_liquidity_history",
                }
            )
            continue
        if liquidity < MIN_PRE_PREDICTION_DOLLAR_VOLUME:
            exclusions.append(
                {
                    "symbol": symbol,
                    "company_id": company_id,
                    "prediction_date": prediction_date.isoformat(),
                    "reason": "below_minimum_pre_prediction_dollar_volume",
                }
            )
            continue
        try:
            label = _six_month_smoothed_multiple(raw_bars, prediction_date)
        except (TypeError, ValueError, ValidationError) as exc:
            exclusions.append(
                {
                    "symbol": symbol,
                    "company_id": company_id,
                    "prediction_date": prediction_date.isoformat(),
                    "reason": str(exc),
                }
            )
            continue
        labels.append((prediction_date, label))
        liquidity_by_date[prediction_date] = liquidity
    if not labels:
        return None, exclusions
    liquidity_values = tuple(liquidity_by_date.values())
    liquidity = sum(liquidity_values) / len(liquidity_values)
    company_name = str(listing.get("name") or symbol)
    cik = _normalized_cik(listing.get("cik"))
    exchange = str(listing.get("exchange") or "unknown").upper()
    max_multiple = max(float(label["realized_max_multiple"]) for _, label in labels)
    stratum = _expansion_stratum(max_multiple)
    diversity = {
        "exchange": exchange,
        "ipo_age_bucket": _ipo_age_bucket(ipo_date, labels[0][0]),
        "dollar_liquidity_bucket": _dollar_liquidity_bucket(liquidity),
        "pre_prediction_average_dollar_volume": liquidity,
        "minimum_pre_prediction_average_dollar_volume": min(liquidity_values),
    }
    cases: list[dict[str, Any]] = []
    for prediction_date, label in labels:
        cases.append(
            {
                "case_id": f"{company_id}:{prediction_date.strftime('%Y%m%d')}",
                "company_id": company_id,
                "prediction_time": datetime.combine(
                    prediction_date,
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ).isoformat(),
                "basic_info": {
                    "company_name": company_name,
                    "ticker": symbol,
                    "market_cap": None,
                    "industry": None,
                    "business_description": None,
                    "revenue_segments": [],
                    "development_stage": None,
                    "exchange": exchange,
                    "ipo_date": ipo_date,
                    "identity_aliases": [symbol, company_name],
                },
                "ground_truth": {
                    "realized_max_multiple": label["realized_max_multiple"],
                    "is_surge": label["is_surge"],
                    "magnitude": label["magnitude"],
                },
                "label_provenance": {
                    "baseline_mean": label["baseline_mean"],
                    "future_peak_mean": label["future_peak_mean"],
                    "baseline_dates": label["baseline_dates"],
                    "future_peak_dates": label["future_peak_dates"],
                    "horizon_end": label["horizon_end"],
                    "source_symbol": symbol,
                    "pre_prediction_average_dollar_volume": liquidity_by_date[
                        prediction_date
                    ],
                },
            }
        )
    return (
        {
            "company_id": company_id,
            "cik": cik,
            "symbol": symbol,
            "company_name": company_name,
            "selection_stratum": stratum,
            "maximum_realized_multiple": max_multiple,
            "diversity": diversity,
            "cases": cases,
        },
        exclusions,
    )


def _deduplicate_expansion_candidates(
    candidates: Iterable[dict[str, Any]],
    *,
    seed: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    by_company: dict[str, dict[str, Any]] = {}
    exclusions: list[dict[str, str]] = []
    for candidate in candidates:
        company_id = str(candidate["company_id"])
        existing = by_company.get(company_id)
        if existing is None:
            by_company[company_id] = candidate
            continue
        ranked = sorted(
            (existing, candidate),
            key=lambda item: (
                -float(
                    item["diversity"].get("pre_prediction_average_dollar_volume")
                    or 0.0
                ),
                hashlib.sha256(
                    f"{seed}:{company_id}:{item['symbol']}".encode("utf-8")
                ).hexdigest(),
            ),
        )
        kept, dropped = ranked
        by_company[company_id] = kept
        exclusions.append(
            {
                "symbol": str(dropped["symbol"]),
                "company_id": company_id,
                "reason": "duplicate_issuer_identity",
                "kept_symbol": str(kept["symbol"]),
            }
        )
    return list(by_company.values()), exclusions


def _serialized_evaluation_label(case: Mapping[str, Any]) -> str:
    truth = dict(case["ground_truth"])
    if not bool(truth["is_surge"]):
        return "non_surge"
    return {
        "2-3x": "2_3x",
        "3-10x": "3_10x",
        "10x+": "10x_plus",
    }[str(truth["magnitude"])]


def _resolve_anchor_cases(
    *,
    positive_specs: tuple[dict[str, Any], ...],
    exact_candidates: Mapping[tuple[str, str], dict[str, Any]],
    candidates: Iterable[dict[str, Any]],
    seed: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    positives: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    used_companies: set[str] = set()
    for spec in positive_specs:
        key = (str(spec["symbol"]), str(spec["prediction_date"]))
        candidate = exact_candidates.get(key)
        if candidate is None:
            raise ValidationError(
                "approved positive Anchor case is unavailable: " + ":".join(key)
            )
        case = dict(candidate["cases"][0])
        actual_label = _serialized_evaluation_label(case)
        if actual_label != spec["expected_label"]:
            raise ValidationError(
                f"positive Anchor label mismatch for {key[0]}@{key[1]}: "
                f"expected {spec['expected_label']}, got {actual_label}"
            )
        company_id = str(case["company_id"])
        if company_id in used_companies:
            raise ValidationError("positive Anchor cases must use distinct issuers")
        used_companies.add(company_id)
        positives.append((spec, candidate, case))

    controls: list[dict[str, Any]] = []
    candidate_rows = tuple(candidates)
    for spec, _positive_candidate, positive_case in positives:
        if not bool(spec["match_control"]):
            continue
        target_date = str(spec["prediction_date"])
        target_exchange = str(positive_case["basic_info"].get("exchange") or "")
        target_ipo_bucket = _ipo_age_bucket(
            positive_case["basic_info"].get("ipo_date"),
            date.fromisoformat(target_date),
        )
        target_liquidity = float(
            positive_case["label_provenance"][
                "pre_prediction_average_dollar_volume"
            ]
        )
        options: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        for candidate in candidate_rows:
            company_id = str(candidate["company_id"])
            if company_id in used_companies:
                continue
            for raw_case in candidate["cases"]:
                if not str(raw_case["prediction_time"]).startswith(target_date):
                    continue
                if _serialized_evaluation_label(raw_case) != "non_surge":
                    continue
                case = dict(raw_case)
                liquidity = float(
                    case["label_provenance"][
                        "pre_prediction_average_dollar_volume"
                    ]
                )
                exchange = str(case["basic_info"].get("exchange") or "")
                ipo_bucket = _ipo_age_bucket(
                    case["basic_info"].get("ipo_date"),
                    date.fromisoformat(target_date),
                )
                score = (
                    int(
                        _dollar_liquidity_bucket(liquidity)
                        != _dollar_liquidity_bucket(target_liquidity)
                    ),
                    int(exchange != target_exchange),
                    int(ipo_bucket != target_ipo_bucket),
                    abs(math.log(liquidity) - math.log(target_liquidity)),
                    hashlib.sha256(
                        f"{seed}:{spec['symbol']}:{case['case_id']}".encode(
                            "utf-8"
                        )
                    ).hexdigest(),
                )
                options.append((score, case))
        if not options:
            raise ValidationError(
                f"no normal non-surge Anchor control for {spec['symbol']}@{target_date}"
            )
        _score, control = min(options, key=lambda item: item[0])
        used_companies.add(str(control["company_id"]))
        control["anchor_metadata"] = {
            "role": "matched_non_surge_control",
            "matched_positive_symbol": spec["symbol"],
            "matching_fields": [
                "prediction_date",
                "dollar_liquidity_bucket",
                "exchange",
                "ipo_age_bucket",
            ],
        }
        controls.append(control)

    positive_cases: list[dict[str, Any]] = []
    for spec, _candidate, case in positives:
        case["anchor_metadata"] = {
            "role": "reviewed_positive",
            "symbol": spec["symbol"],
            "expected_label": spec["expected_label"],
            "rationale": spec["rationale"],
        }
        positive_cases.append(case)
    anchor_cases = [*controls, *positive_cases]
    counts = {label: 0 for label in EVALUATION_LABELS}
    for case in anchor_cases:
        counts[_serialized_evaluation_label(case)] += 1
    if counts != {"non_surge": 7, "2_3x": 5, "3_10x": 3, "10x_plus": 1}:
        raise ValidationError("resolved Anchor cases do not satisfy exact 7/5/3/1")
    return anchor_cases, used_companies


def _allocate_expansion_strata(
    available: Mapping[str, int],
    *,
    target_issuers: int,
    weights: Mapping[str, float],
) -> dict[str, int]:
    if sum(int(available.get(key, 0)) for key in EXPANSION_STRATUM_ORDER) < target_issuers:
        raise ValidationError("expanded dataset target exceeds available strata")
    allocations = {
        key: min(int(available.get(key, 0)), int(target_issuers * weights[key]))
        for key in EXPANSION_STRATUM_ORDER
    }
    while sum(allocations.values()) < target_issuers:
        options = [
            key
            for key in EXPANSION_STRATUM_ORDER
            if allocations[key] < int(available.get(key, 0))
        ]
        if not options:
            raise ValidationError("expanded dataset cannot fill target allocation")
        selected = max(
            options,
            key=lambda key: (
                target_issuers * weights[key] - allocations[key],
                weights[key],
                -EXPANSION_STRATUM_ORDER.index(key),
            ),
        )
        allocations[selected] += 1
    undersized = [key for key, count in allocations.items() if 0 < count < 3]
    if undersized:
        raise ValidationError(
            "expanded dataset selected strata need at least three issuers for sealed splits: "
            + ", ".join(undersized)
        )
    return allocations


def _select_diverse_expansion_issuers(
    candidates: Iterable[dict[str, Any]],
    *,
    count: int,
    seed: str,
) -> list[dict[str, Any]]:
    if count == 0:
        return []
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        diversity = dict(candidate["diversity"])
        bucket = (
            str(diversity["exchange"]),
            str(diversity["ipo_age_bucket"]),
            str(diversity["dollar_liquidity_bucket"]),
        )
        buckets.setdefault(bucket, []).append(candidate)
    for bucket, rows in buckets.items():
        rows.sort(
            key=lambda item: hashlib.sha256(
                f"{seed}:{bucket}:{item['company_id']}".encode("utf-8")
            ).hexdigest()
        )
    bucket_order = sorted(
        buckets,
        key=lambda bucket: hashlib.sha256(
            f"{seed}:{bucket}".encode("utf-8")
        ).hexdigest(),
    )
    selected: list[dict[str, Any]] = []
    positions = {bucket: 0 for bucket in bucket_order}
    while len(selected) < count:
        progressed = False
        for bucket in bucket_order:
            position = positions[bucket]
            rows = buckets[bucket]
            if position >= len(rows):
                continue
            selected.append(rows[position])
            positions[bucket] += 1
            progressed = True
            if len(selected) == count:
                break
        if not progressed:
            raise ValidationError("expanded dataset diversity selector exhausted early")
    return selected


def _propose_expanded_issuer_splits(
    candidates: Iterable[dict[str, Any]],
    *,
    seed: str,
) -> dict[str, list[dict[str, Any]]]:
    by_stratum: dict[str, list[dict[str, Any]]] = {
        key: [] for key in EXPANSION_STRATUM_ORDER
    }
    for candidate in candidates:
        by_stratum[str(candidate["selection_stratum"])].append(candidate)
    result: dict[str, list[dict[str, Any]]] = {
        "discovery": [],
        "evolution_validation": [],
        "locked_test": [],
    }
    for stratum in EXPANSION_STRATUM_ORDER:
        rows = by_stratum[stratum]
        if not rows:
            continue
        if len(rows) < 3:
            raise ValidationError(
                f"expanded dataset stratum cannot support three splits: {stratum}"
            )
        ordered = sorted(
            rows,
            key=lambda item: hashlib.sha256(
                f"{seed}:{stratum}:{item['company_id']}".encode("utf-8")
            ).hexdigest(),
        )
        discovery_count, validation_count, _ = _three_way_counts(len(ordered))
        if len(ordered) >= 4 and validation_count < 2:
            discovery_count -= 1
            validation_count += 1
        result["discovery"].extend(ordered[:discovery_count])
        result["evolution_validation"].extend(
            ordered[discovery_count : discovery_count + validation_count]
        )
        result["locked_test"].extend(
            ordered[discovery_count + validation_count :]
        )
    for rows in result.values():
        rows.sort(key=lambda item: str(item["company_id"]))
    return result


def _expansion_company_id(listing: Mapping[str, Any]) -> str:
    cik = _normalized_cik(listing.get("cik"))
    if cik is not None:
        return f"cik_{cik}"
    return _company_id_from_symbol(str(listing["symbol"]))


def _normalized_cik(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits.zfill(10) if digits else None


def _expansion_stratum(maximum_multiple: float) -> str:
    if maximum_multiple < 1.5:
        return "below_1_5x"
    if maximum_multiple < 2.0:
        return "near_surge_1_5_to_2x"
    if maximum_multiple < 3.0:
        return "surge_2_to_3x"
    if maximum_multiple < 10.0:
        return "surge_3_to_10x"
    return "surge_10x_plus"


def _pre_prediction_average_dollar_volume(
    raw_bars: Iterable[Any], prediction_date: date
) -> float | None:
    parsed: list[tuple[date, float]] = []
    for bar in raw_bars:
        if not isinstance(bar, Mapping) or not bar.get("as_of_date"):
            continue
        adjusted_close = bar.get("adjusted_close")
        volume = bar.get("volume")
        if adjusted_close is None or volume is None:
            continue
        value = float(adjusted_close) * float(volume)
        if value > 0:
            parsed.append((date.fromisoformat(str(bar["as_of_date"])), value))
    values = [value for bar_date, value in parsed if bar_date < prediction_date][-20:]
    if len(values) < 15:
        return None
    return sum(values) / len(values)


def _adjusted_price_integrity_reason(
    raw_bars: Iterable[Any], prediction_date: date
) -> str | None:
    parsed: list[tuple[date, float]] = []
    for bar in raw_bars:
        if not isinstance(bar, Mapping) or not bar.get("as_of_date"):
            continue
        adjusted_close = bar.get("adjusted_close")
        if adjusted_close is None:
            continue
        value = float(adjusted_close)
        if value <= 0 or not math.isfinite(value):
            return "invalid_adjusted_price"
        parsed.append((date.fromisoformat(str(bar["as_of_date"])), value))
    parsed.sort(key=lambda item: item[0])
    if len({bar_date for bar_date, _ in parsed}) != len(parsed):
        return "duplicate_adjusted_price_date"
    baseline = [item for item in parsed if item[0] < prediction_date][-10:]
    future = [
        item
        for item in parsed
        if prediction_date <= item[0] <= _add_months(prediction_date, 6)
    ]
    relevant = (*baseline, *future)
    for (_prior_date, prior), (_current_date, current) in zip(
        relevant, relevant[1:]
    ):
        ratio = current / prior
        if ratio >= MAX_ADJUSTED_CLOSE_STEP_UP or ratio <= MIN_ADJUSTED_CLOSE_STEP_DOWN:
            return "extreme_adjusted_price_discontinuity"
    return None


def _dollar_liquidity_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 1_000_000:
        return "below_1m"
    if value < 10_000_000:
        return "1m_to_10m"
    if value < 100_000_000:
        return "10m_to_100m"
    return "100m_plus"


def _ipo_age_bucket(value: str | None, prediction_date: date) -> str:
    if not value:
        return "unknown"
    try:
        ipo_date = date.fromisoformat(value)
    except ValueError:
        return "unknown"
    age_days = (prediction_date - ipo_date).days
    if age_days < 0:
        return "pre_ipo"
    if age_days < 2 * 365:
        return "under_2y"
    if age_days < 5 * 365:
        return "2y_to_5y"
    if age_days < 10 * 365:
        return "5y_to_10y"
    return "10y_plus"


def _artifact_file_identity(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"required local artifact is missing: {path}")
    return {
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


class _StreamingJSONReader:
    """Incremental JSON decoder used for multi-hundred-megabyte local archives."""

    def __init__(self, path: Path, *, chunk_size: int = 1024 * 1024) -> None:
        self.handle = path.open("r", encoding="utf-8")
        self.chunk_size = chunk_size
        self.buffer = ""
        self.position = 0
        self.eof = False
        self.decoder = json.JSONDecoder()

    def close(self) -> None:
        self.handle.close()

    def peek(self) -> str:
        self._skip_whitespace()
        self._ensure_available()
        return self.buffer[self.position]

    def consume(self, expected: str) -> None:
        actual = self.peek()
        if actual != expected:
            raise ValidationError(
                f"large price archive expected {expected!r}, received {actual!r}"
            )
        self.position += 1
        self._compact()

    def decode(self) -> Any:
        self._skip_whitespace()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
            except json.JSONDecodeError as exc:
                if self.eof:
                    raise ValidationError("large price archive contains invalid JSON") from exc
                self._fill()
                continue
            self.position = end
            self._compact()
            return value

    def _skip_whitespace(self) -> None:
        while True:
            while self.position < len(self.buffer) and self.buffer[
                self.position
            ].isspace():
                self.position += 1
            if self.position < len(self.buffer) or self.eof:
                return
            self._fill()

    def _ensure_available(self) -> None:
        if self.position >= len(self.buffer) and not self.eof:
            self._fill()
        if self.position >= len(self.buffer):
            raise ValidationError("large price archive ended unexpectedly")

    def _fill(self) -> None:
        chunk = self.handle.read(self.chunk_size)
        if not chunk:
            self.eof = True
            return
        if self.position:
            self.buffer = self.buffer[self.position :] + chunk
            self.position = 0
        else:
            self.buffer += chunk

    def _compact(self) -> None:
        if self.position > self.chunk_size:
            self.buffer = self.buffer[self.position :]
            self.position = 0


def _stream_selected_price_history(
    path: Path, symbols: set[str]
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    if not path.is_file():
        raise ValidationError(f"large local price archive is missing: {path}")
    reader = _StreamingJSONReader(path)
    metadata: dict[str, Any] = {}
    selected: dict[str, list[dict[str, Any]]] = {}
    try:
        reader.consume("{")
        while reader.peek() != "}":
            key = reader.decode()
            if not isinstance(key, str):
                raise ValidationError("large price archive top-level key is invalid")
            reader.consume(":")
            if key == "bars_by_symbol":
                reader.consume("{")
                while reader.peek() != "}":
                    symbol = reader.decode()
                    if not isinstance(symbol, str):
                        raise ValidationError("large price archive symbol key is invalid")
                    reader.consume(":")
                    bars = reader.decode()
                    if symbol in symbols:
                        if not isinstance(bars, list):
                            raise ValidationError("large price archive bars must be a list")
                        selected[symbol] = [
                            dict(bar) for bar in bars if isinstance(bar, Mapping)
                        ]
                    if reader.peek() == ",":
                        reader.consume(",")
                    else:
                        break
                reader.consume("}")
            else:
                metadata[key] = reader.decode()
            if reader.peek() == ",":
                reader.consume(",")
            else:
                break
        reader.consume("}")
    finally:
        reader.close()
    return metadata, selected


def _case_symbol(row: Any) -> str | None:
    if not isinstance(row, Mapping):
        return None
    packet = row.get("packet", {})
    if not isinstance(packet, Mapping):
        return None
    company = packet.get("company", {})
    if not isinstance(company, Mapping):
        return None
    ticker = company.get("ticker", {})
    return str(ticker.get("symbol")) if isinstance(ticker, Mapping) and ticker.get("symbol") else None


def _case_as_of_date(row: Any) -> str | None:
    if not isinstance(row, Mapping):
        return None
    packet = row.get("packet", {})
    if not isinstance(packet, Mapping):
        return None
    as_of = packet.get("as_of", {})
    if not isinstance(as_of, Mapping) or not as_of.get("as_of_date"):
        return None
    return str(as_of["as_of_date"])


def _company_id_from_symbol(symbol: str) -> str:
    value = re.sub(r"[^a-z0-9_.:-]+", "_", symbol.casefold()).strip("_")
    if not value:
        raise ValidationError(f"cannot derive company_id from symbol: {symbol!r}")
    return value


def _date_at_utc(value: Any, name: str) -> datetime:
    if not value:
        raise ValidationError(f"legacy artifact is missing {name}")
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"required local artifact is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValidationError(f"JSON root must be an object: {path}")
    return value


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    expected = json.loads(json.dumps(dict(value), sort_keys=True))
    if path.exists():
        if _read_json(path) != expected:
            raise ValidationError(f"immutable artifact conflict: {path}")
        return
    _atomic_write_json(path, value)
