"""Frozen run, external-call, cache, ledger, and local-data preflight controls."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from stock_opportunity_agent.config import load_config
from stock_opportunity_agent.data.acquisition import (
    AlphaVantageNewsAdapter,
    HistoricalPriceAdapter,
    HistoricalUnavailableAdapter,
    SecCompanyFactsAdapter,
    SecFilingAdapter,
    UnavailableProviderAdapter,
)
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    DataAcquisitionBudget,
    DataAcquisitionPolicy,
    EvidenceResolver,
)
from stock_opportunity_agent.data.sources.alpha_vantage import AlphaVantageClient
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import UrllibJsonTransport
from stock_opportunity_agent.data.sources.massive import MassiveClient
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.data.sources.state import (
    ManagedHttpTransport,
    RawDataCache,
    RequestLedger,
    SourceBudget,
)
from stock_opportunity_agent.data.sources.stooq import StooqClient
from stock_opportunity_agent.llm import ModelClientSettings, RegisteredModel, get_model
from stock_opportunity_agent.llm.agent import (
    AgentModel,
    AgentRequest,
    AgentTurn,
    AgentUsage,
    GenericAgent,
    ToolCall,
)
from stock_opportunity_agent.llm.openai import ChatMessage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import (
    AgentStep,
    BlindPrediction,
    CandidateProposalRejected,
    DEFAULT_EVOLUTION_PRIORS,
    DualLoopEvolutionEngine,
    DualLoopResult,
    EvolutionCase,
    EvolutionWorkspace,
    GroundTruth,
    InformationPlan,
    PlanMetrics,
    PlanArchive,
    PlanEvolutionEngine,
    PlanMetaMemory,
    PlanRecord,
    PlanReflection,
    ProgressCallback,
    PredictionSelfReflection,
    ResearchState,
    RoundMetaEntry,
    RuntimeLimits,
    RuntimePlanEvaluator,
    SlowLoopResult,
    SignalEvolutionEngine,
    default_information_plan,
)
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    SignalRegistry,
    SignalBatchResult,
    SignalCoverage,
    SignalResult,
    SignalSpec,
    SignalValue,
    validate_signal_result,
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
            "schema_version": "expanded-evolution-dataset-proposal-report-v1",
            "manifest_path": self.manifest_path,
            "manifest_hash": self.manifest_hash,
            "universe_listing_count": self.universe_listing_count,
            "priced_symbol_count": self.priced_symbol_count,
            "eligible_issuer_count": self.eligible_issuer_count,
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
        "label_contract": {
            "horizon": "six_calendar_months",
            "baseline": "mean_last_5_complete_adjusted_closes_strictly_before_as_of",
            "future_peak": "max_mean_5_consecutive_adjusted_closes_after_as_of",
            "binary_threshold": 2.0,
            "magnitude_classes": ["2-3x", "3-10x", "10x+"],
        },
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


def prepare_expanded_dataset_proposal(
    *,
    universe_path: str | Path,
    full_price_archive_path: str | Path,
    output_root: str | Path,
    prediction_dates: Iterable[date],
    target_issuers: int = 240,
    stratum_weights: Mapping[str, float] | None = None,
    split_seed: str = "expanded-information-plan-evolution-v1",
    identity_decisions_path: str | Path | None = None,
) -> ExpandedDatasetProposalReport:
    """Build a zero-network fixed-date case-library proposal from local prices."""

    if target_issuers < 6:
        raise ValidationError("expanded dataset target_issuers must be at least 6")
    dates = tuple(sorted(set(prediction_dates)))
    if not dates:
        raise ValidationError("expanded dataset requires prediction dates")
    weights = _validate_expansion_weights(
        DEFAULT_EXPANSION_STRATUM_WEIGHTS if stratum_weights is None else stratum_weights
    )
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

    price_metadata, candidates, exclusions, priced_symbol_count = (
        _stream_expansion_candidates(
            price_file,
            listings=active_listings,
            prediction_dates=dates,
        )
    )
    exclusions.extend(identity_exclusions)
    deduplicated, duplicate_exclusions = _deduplicate_expansion_candidates(
        candidates,
        seed=split_seed,
    )
    exclusions.extend(duplicate_exclusions)
    if target_issuers > len(deduplicated):
        raise ValidationError(
            "expanded dataset target exceeds eligible deduplicated issuers"
        )

    available_counts = {
        stratum: sum(
            candidate["selection_stratum"] == stratum
            for candidate in deduplicated
        )
        for stratum in EXPANSION_STRATUM_ORDER
    }
    allocations = _allocate_expansion_strata(
        available_counts,
        target_issuers=target_issuers,
        weights=weights,
    )
    selected: list[dict[str, Any]] = []
    for stratum in EXPANSION_STRATUM_ORDER:
        pool = [
            candidate
            for candidate in deduplicated
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
    if len(selected) != target_issuers:
        raise ValidationError("expanded dataset selector returned wrong issuer count")
    split_candidates = _propose_expanded_issuer_splits(selected, seed=split_seed)

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    universe_identity = _artifact_file_identity(universe_file)
    price_identity = _artifact_file_identity(price_file)
    source_inputs: dict[str, Any] = {
        "universe": universe_identity,
        "adjusted_prices": price_identity,
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
            "schema_version": "expanded-case-candidate-inventory-v1",
            "source_inventory_hash": source_inventory_hash,
            "prediction_dates": [value.isoformat() for value in dates],
            "eligible_issuer_count": len(deduplicated),
            "available_stratum_counts": available_counts,
            "candidates": sorted(
                deduplicated,
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
            "schema_version": "expanded-case-selected-issuers-v1",
            "selection_seed": split_seed,
            "target_issuer_count": target_issuers,
            "selection_weights": weights,
            "selected_stratum_counts": allocations,
            "issuers": selected,
        },
    )
    acquisition_scope_path = root / "acquisition_scope.json"
    _write_or_verify_json(
        acquisition_scope_path,
        {
            "schema_version": "expanded-case-acquisition-scope-v1",
            "source_inventory_hash": source_inventory_hash,
            "prediction_dates": [value.isoformat() for value in dates],
            "company_count": len(selected),
            "companies": [
                {
                    "company_id": item["company_id"],
                    "cik": item["cik"],
                    "symbol": item["symbol"],
                    "company_name": item["company_name"],
                }
                for item in selected
            ],
            "outcome_fields_included": False,
            "split_ownership_included": False,
        },
    )

    artifacts: dict[str, dict[str, Any]] = {}
    split_case_counts: dict[str, int] = {}
    split_issuer_counts: dict[str, int] = {}
    split_surge_counts: dict[str, int] = {}
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
        "schema_version": "expanded-evolution-dataset-manifest-proposal-v1",
        "approval_status": "proposal_only_pending_human_review",
        "approval_blockers": [
            "validate historical registrant/ticker identity for every selected issuer",
            "resolve companies without CIK or record a reviewed exclusion",
            "classify and review non-operating securities such as funds, notes, preferred shares, and SPACs",
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
            "kind": "shared_fixed_calendar_panel",
            "prediction_dates": [value.isoformat() for value in dates],
            "required_cases_per_issuer": len(dates),
            "eligibility": "complete_active_label_at_every_prediction_date",
            "issuer_identity": "zero_padded_cik_else_symbol",
        },
        "selection": {
            "target_issuer_count": target_issuers,
            "available_issuer_count": len(deduplicated),
            "stratum_order": list(EXPANSION_STRATUM_ORDER),
            "stratum_definition": "maximum_realized_multiple_across_prediction_dates",
            "weights": weights,
            "available_stratum_counts": available_counts,
            "selected_stratum_counts": selected_counts,
            "diversity_rotation": ["exchange", "ipo_age_bucket", "dollar_liquidity_bucket"],
            "seed": split_seed,
            "sampling_boundary": (
                "Outcome and near-threshold strata are enriched for controlled learning; "
                "unweighted metrics do not estimate live market prevalence or returns."
            ),
        },
        "split_policy": {
            "unit": "issuer",
            "strata": "selection_stratum",
            "target_ratios": {
                "discovery": 0.60,
                "evolution_validation": 0.25,
                "locked_test": 0.15,
            },
        },
        "label_contract": {
            "horizon": "six_calendar_months",
            "baseline": "mean_last_5_complete_adjusted_closes_strictly_before_as_of",
            "future_peak": "max_mean_5_consecutive_adjusted_closes_after_as_of",
            "binary_threshold": 2.0,
            "magnitude_classes": ["2-3x", "3-10x", "10x+"],
        },
        "counts": {
            "universe_listings": source_listing_count,
            "identity_eligible_universe_listings": len(active_listings),
            "priced_symbols": priced_symbol_count,
            "eligible_issuers": len(deduplicated),
            "selected_issuers": len(selected),
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
        eligible_issuer_count=len(deduplicated),
        selected_issuer_count=len(selected),
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


@dataclass(frozen=True)
class EvolutionRunContract:
    """Secret-free immutable identity for one bounded evolution run."""

    run_id: str
    created_at: str
    dataset_manifest_hash: str
    raw_info_inventory_hash: str
    signal_registry_version: int
    signal_registry_hash: str
    priors_hash: str
    models: Mapping[str, Mapping[str, Any]]
    code_revision: str
    python_runtime: str
    limits: Mapping[str, Any]
    max_external_attempts: int
    max_total_cost: float
    locked_test_accessed: bool = False
    data_acquisition: DataAcquisitionPolicy = DataAcquisitionPolicy()
    schema_version: str = "evolution-run-contract-v2"

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValidationError("evolution run_id is required")
        for name in (
            "dataset_manifest_hash",
            "raw_info_inventory_hash",
            "signal_registry_hash",
            "priors_hash",
        ):
            value = str(getattr(self, name))
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValidationError(f"{name} must be a SHA-256 hex digest")
        if self.signal_registry_version < 1:
            raise ValidationError("signal registry version must be positive")
        if self.max_external_attempts < 1 or self.max_total_cost <= 0:
            raise ValidationError("external attempt and cost ceilings must be positive")
        if self.locked_test_accessed:
            raise ValidationError("ordinary evolution contract cannot open Locked Test")
        object.__setattr__(
            self,
            "models",
            {str(role): dict(metadata) for role, metadata in self.models.items()},
        )
        object.__setattr__(self, "limits", dict(self.limits))
        if self.schema_version not in {
            "evolution-run-contract-v1",
            "evolution-run-contract-v2",
        }:
            raise ValidationError("unsupported evolution run contract schema")

    def to_dict(self) -> dict[str, Any]:
        value = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "raw_info_inventory_hash": self.raw_info_inventory_hash,
            "signal_registry_version": self.signal_registry_version,
            "signal_registry_hash": self.signal_registry_hash,
            "priors_hash": self.priors_hash,
            "models": {role: dict(value) for role, value in self.models.items()},
            "code_revision": self.code_revision,
            "python_runtime": self.python_runtime,
            "limits": dict(self.limits),
            "max_external_attempts": self.max_external_attempts,
            "max_total_cost": self.max_total_cost,
            "locked_test_accessed": False,
        }
        if self.schema_version != "evolution-run-contract-v1":
            value["data_acquisition"] = self.data_acquisition.to_dict()
        return value

    @property
    def contract_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def freeze(self, path: str | Path) -> None:
        _write_or_verify_json(
            Path(path),
            {"contract_hash": self.contract_hash, "contract": self.to_dict()},
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvolutionRunContract":
        return cls(
            run_id=str(value["run_id"]),
            created_at=str(value["created_at"]),
            dataset_manifest_hash=str(value["dataset_manifest_hash"]),
            raw_info_inventory_hash=str(value["raw_info_inventory_hash"]),
            signal_registry_version=int(value["signal_registry_version"]),
            signal_registry_hash=str(value["signal_registry_hash"]),
            priors_hash=str(value["priors_hash"]),
            models={
                str(role): dict(metadata)
                for role, metadata in dict(value["models"]).items()
            },
            code_revision=str(value["code_revision"]),
            python_runtime=str(value["python_runtime"]),
            limits=dict(value["limits"]),
            max_external_attempts=int(value["max_external_attempts"]),
            max_total_cost=float(value["max_total_cost"]),
            locked_test_accessed=bool(value.get("locked_test_accessed", False)),
            data_acquisition=DataAcquisitionPolicy.from_dict(
                dict(value.get("data_acquisition", {}))
            ),
            schema_version=str(
                value.get("schema_version", "evolution-run-contract-v1")
            ),
        )

    @classmethod
    def load_frozen(cls, path: str | Path) -> "EvolutionRunContract":
        envelope = _read_json(Path(path))
        contract = cls.from_dict(dict(envelope["contract"]))
        if envelope.get("contract_hash") != contract.contract_hash:
            raise ValidationError("frozen evolution run contract hash mismatch")
        return contract


@dataclass(frozen=True)
class ApprovedDevelopmentDataset:
    """Ordinary loop inputs with Locked Test represented only by a sealed hash."""

    discovery: tuple[EvolutionCase, ...]
    evolution_validation: tuple[EvolutionCase, ...]
    locked_test_hash: str
    approved_manifest_hash: str


def load_approved_development_dataset(
    manifest_path: str | Path,
) -> ApprovedDevelopmentDataset:
    """Load Discovery/Validation only; never deserialize Locked Test cases."""

    path = Path(manifest_path)
    manifest = _read_json(path)
    if manifest.get("approval_status") != "human_approved":
        raise ValidationError("development dataset manifest is not human-approved")
    if manifest.get("locked_test_sealed") is not True:
        raise ValidationError("development dataset does not seal Locked Test")
    artifacts = dict(manifest.get("artifacts", {}))
    loaded: dict[str, tuple[EvolutionCase, ...]] = {}
    for split_name in ("discovery", "evolution_validation"):
        metadata = dict(artifacts[split_name])
        split_path = Path(str(metadata["path"]))
        if _sha256_file(split_path) != metadata.get("sha256"):
            raise ValidationError(f"dataset split hash mismatch: {split_name}")
        split = _read_json(split_path)
        if split.get("split") != split_name:
            raise ValidationError(f"dataset split identity mismatch: {split_name}")
        loaded[split_name] = tuple(
            EvolutionCase(
                case_id=str(row["case_id"]),
                company_id=str(row["company_id"]),
                prediction_time=datetime.fromisoformat(str(row["prediction_time"])),
                basic_info=dict(row["basic_info"]),
                ground_truth=GroundTruth.from_dict(dict(row["ground_truth"])),
            )
            for row in split.get("cases", ())
        )
    locked_metadata = dict(artifacts["locked_test"])
    return ApprovedDevelopmentDataset(
        discovery=loaded["discovery"],
        evolution_validation=loaded["evolution_validation"],
        locked_test_hash=str(locked_metadata["sha256"]),
        approved_manifest_hash=_sha256_file(path),
    )


def current_code_revision(project_root: str | Path) -> str:
    """Return HEAD only when tracked/runtime source state is reproducible."""

    root = Path(project_root)
    tracked = subprocess.run(
        ["git", "diff", "--quiet"],
        cwd=root,
        check=False,
    )
    if tracked.returncode != 0:
        raise ValidationError("freeze-run requires committed tracked project changes")
    untracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "src",
            "scripts",
            "configs",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if untracked.stdout.strip():
        raise ValidationError("freeze-run requires committed runtime source files")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def public_model_contract(
    role_aliases: Mapping[str, str], *, environ: Mapping[str, str] | None = None
) -> dict[str, dict[str, Any]]:
    """Resolve registered models and record only public metadata/key presence."""

    env = os.environ if environ is None else environ
    result: dict[str, dict[str, Any]] = {}
    for role, alias in role_aliases.items():
        registry_role = "evolution" if role in {"proposer", "mining", "update"} else "judge"
        registration = get_model(alias, role=registry_role)
        metadata = registration.to_public_dict()
        metadata["api_key_available"] = bool(env.get(registration.api_key_env_var))
        result[str(role)] = metadata
    return result


class ExternalRequestPending(ValidationError):
    """Raised after a no-network preflight has persisted one exact request."""

    def __init__(self, request_hash: str, request_path: Path) -> None:
        super().__init__(f"external request requires approval: {request_hash}")
        self.request_hash = request_hash
        self.request_path = request_path


class ExactResponseCache:
    """Exact response reuse keyed only by canonical request hash."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self, request_hash: str) -> dict[str, Any] | None:
        path = self.root / f"{request_hash}.json"
        return _read_json(path) if path.exists() else None

    def store(self, request_hash: str, response: Mapping[str, Any]) -> None:
        _write_or_verify_json(
            self.root / f"{request_hash}.json",
            {"request_hash": request_hash, **dict(response)},
        )


class ExternalAttemptLedger:
    """Durable fail-closed reservation of attempts and conservative cost."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_attempts: int,
        max_total_cost: float,
    ) -> None:
        if max_attempts < 1 or max_total_cost <= 0:
            raise ValidationError("ledger ceilings must be positive")
        self.path = Path(path)
        self.max_attempts = max_attempts
        self.max_total_cost = max_total_cost
        if not self.path.exists():
            _atomic_write_json(
                self.path,
                {
                    "schema_version": "evolution-attempt-ledger-v1",
                    "max_attempts": max_attempts,
                    "max_total_cost": max_total_cost,
                    "attempts": [],
                },
            )
        else:
            data = _read_json(self.path)
            if (
                int(data.get("max_attempts", 0)) != max_attempts
                or float(data.get("max_total_cost", 0.0)) != max_total_cost
            ):
                raise ValidationError("attempt ledger ceilings conflict with frozen run")

    def reserve(self, request_hash: str, *, reserved_cost: float) -> int:
        if reserved_cost <= 0:
            raise ValidationError("reserved request cost must be positive")
        data = _read_json(self.path)
        attempts = list(data.get("attempts", ()))
        if len(attempts) >= self.max_attempts:
            raise ValidationError("external attempt ceiling exhausted")
        committed_cost = sum(float(item.get("reserved_cost", 0.0)) for item in attempts)
        if committed_cost + reserved_cost > self.max_total_cost + 1e-12:
            raise ValidationError("external cumulative cost ceiling would be exceeded")
        attempt_id = len(attempts) + 1
        attempts.append(
            {
                "attempt_id": attempt_id,
                "request_hash": request_hash,
                "reserved_cost": reserved_cost,
                "status": "in_progress",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        data["attempts"] = attempts
        _atomic_write_json(self.path, data)
        return attempt_id

    def finalize(
        self,
        attempt_id: int,
        *,
        status: str,
        actual_cost: float,
        response_hash: str | None = None,
        error_type: str | None = None,
    ) -> None:
        if status not in {"completed", "failed"} or actual_cost < 0:
            raise ValidationError("invalid attempt completion")
        data = _read_json(self.path)
        attempts = list(data.get("attempts", ()))
        try:
            attempt = attempts[attempt_id - 1]
        except IndexError as exc:
            raise ValidationError("unknown external attempt id") from exc
        if attempt.get("attempt_id") != attempt_id or attempt.get("status") != "in_progress":
            raise ValidationError("external attempt is not pending")
        attempt["status"] = status
        attempt["actual_cost"] = actual_cost
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        if response_hash is not None:
            attempt["response_hash"] = response_hash
        if error_type is not None:
            attempt["error_type"] = error_type
        data["attempts"] = attempts
        _atomic_write_json(self.path, data)

    @property
    def summary(self) -> dict[str, Any]:
        data = _read_json(self.path)
        attempts = list(data.get("attempts", ()))
        return {
            "attempt_count": len(attempts),
            "in_progress": sum(item.get("status") == "in_progress" for item in attempts),
            "reserved_cost": sum(float(item.get("reserved_cost", 0.0)) for item in attempts),
            "actual_cost": sum(float(item.get("actual_cost", 0.0)) for item in attempts),
        }


class StructuredRoleClient:
    """Registered JSON role client guarded by request disclosure/cache/ledger."""

    def __init__(
        self,
        *,
        registration: RegisteredModel,
        contract: EvolutionRunContract,
        workspace: str | Path,
        ledger: ExternalAttemptLedger,
        allow_external: bool = False,
        acknowledged_contract_hash: str | None = None,
        environ: Mapping[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.registration = registration
        self.contract = contract
        self.workspace = Path(workspace)
        self.requests_root = self.workspace / "requests"
        self.requests_root.mkdir(parents=True, exist_ok=True)
        self.cache = ExactResponseCache(self.workspace / "cache" / "responses")
        self.ledger = ledger
        self.allow_external = allow_external
        self.acknowledged_contract_hash = acknowledged_contract_hash
        self.environ = environ
        self.on_progress = on_progress

    def complete_json(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        anonymous_aliases: Iterable[str] = (),
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], AgentUsage]:
        """Persist and validate an exact request, then preview/cache/execute it."""

        if not 0 <= temperature <= 1:
            raise ValidationError("role temperature must be between 0 and 1")
        _scan_payload(
            payload,
            allow_outcomes=allow_outcomes,
            anonymous_aliases=anonymous_aliases,
        )
        structured_system_prompt = (
            "Return exactly one JSON object and no non-JSON text. " + system_prompt
        )
        output_limit = max_output_tokens or self.registration.default_max_output_tokens
        request = {
            "schema_version": "evolution-exact-request-v1",
            "contract_hash": self.contract.contract_hash,
            "stage": stage,
            "model": self.registration.to_public_dict(),
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "max_http_attempts": 1,
            "max_output_tokens": output_limit,
            "messages": [
                {"role": "system", "content": structured_system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(payload, sort_keys=True, separators=(",", ":")),
                },
            ],
        }
        request_hash = _canonical_hash(request)
        request_path = self.requests_root / f"{request_hash}.json"
        _write_or_verify_json(
            request_path,
            {"request_hash": request_hash, "request": request},
        )
        _emit_runtime_progress(
            self.on_progress,
            "request_ready",
            stage=stage,
            model_alias=self.registration.alias,
            request_hash=request_hash,
            request_path=str(request_path),
        )
        cached = self.cache.load(request_hash)
        if cached is not None:
            _emit_runtime_progress(
                self.on_progress,
                "request_cache_hit",
                stage=stage,
                model_alias=self.registration.alias,
                request_hash=request_hash,
            )
            return dict(cached["json_output"]), _usage_from_cache(cached)
        if not self.allow_external:
            _emit_runtime_progress(
                self.on_progress,
                "request_pending_external_approval",
                stage=stage,
                model_alias=self.registration.alias,
                request_hash=request_hash,
                request_path=str(request_path),
            )
            raise ExternalRequestPending(request_hash, request_path)
        if self.acknowledged_contract_hash != self.contract.contract_hash:
            raise ValidationError("external execution requires exact run-contract acknowledgement")
        if not (self.environ or os.environ).get(self.registration.api_key_env_var):
            raise ValidationError(
                f"required API key is unavailable: {self.registration.api_key_env_var}"
            )

        estimated_input_tokens = max(
            1,
            len(json.dumps(request["messages"], ensure_ascii=False).encode("utf-8")),
        )
        reserved_cost = _model_cost(
            self.registration,
            input_tokens=estimated_input_tokens,
            output_tokens=output_limit,
        )
        attempt_id = self.ledger.reserve(request_hash, reserved_cost=reserved_cost)
        _emit_runtime_progress(
            self.on_progress,
            "external_call_started",
            stage=stage,
            model_alias=self.registration.alias,
            request_hash=request_hash,
            attempt_id=attempt_id,
            reserved_cost=reserved_cost,
        )
        client = self.registration.create_client(
            ModelClientSettings(
                preview_only=False,
                temperature=temperature,
                max_http_attempts=1,
                environ=self.environ,
            )
        )
        messages = [
            ChatMessage("system", structured_system_prompt),
            ChatMessage("user", json.dumps(payload, sort_keys=True)),
        ]
        kwargs: dict[str, Any] = {"max_output_tokens": output_limit}
        kwargs["response_format"] = {"type": "json_object"}
        if self.registration.default_reasoning_effort:
            kwargs["reasoning"] = {
                "effort": self.registration.default_reasoning_effort
            }
        try:
            response = client.complete(messages, **kwargs)
            parsed = _parse_json_object(response.output_text)
            usage_data = response.raw.get("usage", {})
            input_tokens = int(usage_data.get("input_tokens", estimated_input_tokens))
            output_tokens = int(usage_data.get("output_tokens", 0))
            actual_cost = _model_cost(
                self.registration,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            response_record = {
                "response_id": response.response_id,
                "model": response.model,
                "json_output": parsed,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": actual_cost,
                },
            }
            self.cache.store(request_hash, response_record)
            response_hash = _canonical_hash(response_record)
            self.ledger.finalize(
                attempt_id,
                status="completed",
                actual_cost=actual_cost,
                response_hash=response_hash,
            )
            _emit_runtime_progress(
                self.on_progress,
                "external_call_completed",
                stage=stage,
                model_alias=self.registration.alias,
                request_hash=request_hash,
                attempt_id=attempt_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_cost=actual_cost,
            )
            return parsed, AgentUsage(
                llm_calls=1,
                tokens=input_tokens + output_tokens,
                cost=actual_cost,
            )
        except Exception as exc:
            self.ledger.finalize(
                attempt_id,
                status="failed",
                actual_cost=0.0,
                error_type=type(exc).__name__,
            )
            _emit_runtime_progress(
                self.on_progress,
                "external_call_failed",
                stage=stage,
                model_alias=self.registration.alias,
                request_hash=request_hash,
                attempt_id=attempt_id,
                error_type=type(exc).__name__,
            )
            raise


class JSONRoleCaller(Protocol):
    """Small injectable boundary shared by concrete role adapters and tests."""

    def complete_json(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        anonymous_aliases: Iterable[str] = (),
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], AgentUsage]:
        """Return one validated structured role response and usage."""


def _output_contract(name: str, example: Mapping[str, Any]) -> str:
    """Render one literal provider-facing JSON contract without Python names."""

    return (
        f" Output contract for {name}: return exactly one JSON object shaped like "
        f"{json.dumps(dict(example), sort_keys=True, separators=(',', ':'))}. "
        "Replace example values with grounded values, keep the exact key names and "
        "JSON types, do not add wrapper keys, and do not use Markdown."
    )


_RESEARCH_STATE_OUTPUT = _output_contract(
    "ResearchState",
    {
        "hypotheses": ["one falsifiable hypothesis"],
        "current_beliefs": [],
        "supporting_evidence": [],
        "contradictions": [],
        "resolved_questions": [],
        "open_questions": [],
        "next_information_needs": ["one natural-language need"],
        "decision": "continue",
    },
) + ' Decision must be "continue" or "finalize"; continue requires at least one need.'

_BLIND_PREDICTION_OUTPUT = _output_contract(
    "BlindPrediction",
    {
        "is_surge": False,
        "magnitude": None,
        "confidence": {"level": "low"},
        "key_reasons": ["one source-grounded reason"],
        "uncertainties": [],
        "session_id": "anonymous-session-id",
    },
) + (
    ' confidence.level must be "low", "medium", or "high". When is_surge is '
    'true, magnitude must be "2-3x", "3-10x", or "10x+"; otherwise it must be null.'
)

_PREDICTION_REFLECTION_OUTPUT = _output_contract(
    "PredictionSelfReflection",
    {
        "prediction_outcome": {"correct": False},
        "why_prediction_failed": [],
        "misleading_signals": [],
        "ignored_evidence": [],
        "missing_information": [],
        "plan_issues": [],
    },
)

_PLAN_REFLECTION_OUTPUT = _output_contract(
    "PlanReflection",
    {
        "successful_patterns": [],
        "failed_patterns": [],
        "repeated_failure_modes": [],
        "misleading_signals": [],
        "missing_information_needs": [],
        "next_explorations": [],
    },
)

_ROUND_META_OUTPUT = _output_contract(
    "RoundMetaEntry",
    {
        "round_id": 1,
        "plan_level": {"successful_patterns": [], "failed_patterns": []},
        "prediction_errors": {"false_positive": [], "false_negative": []},
        "signal_observations": {
            "useful": [],
            "suspicious": [],
            "missing_capabilities": [],
        },
        "search_implications": [],
        "evidence_refs": ["one supplied plan_id"],
    },
)

_SIGNAL_RESULT_OUTPUT = _output_contract(
    "SignalResult",
    {
        "signal_id": "requested_signal_id",
        "version": 1,
        "state": {"value": "neutral", "confidence": 0.5},
        "interpretation": {"summary": "grounded interpretation"},
        "evidence": {"supporting": [], "counter": []},
        "status": {"coverage": "partial"},
    },
) + (
    ' state.value must be "positive", "neutral", "negative", or "unavailable"; '
    'status.coverage must be "sufficient", "partial", or "unavailable". Each '
    'evidence item must contain document_id, exact_span, and ISO-8601 timestamp. '
    'When state.value is "unavailable", status.coverage must also be "unavailable".'
)

_INFORMATION_PLAN_OUTPUT = _output_contract(
    "InformationPlanContent",
    {
        "B": {
            "requests": [
                {
                    "request_id": "recent_company_news",
                    "description": "Recent company-specific news that may change expectations",
                    "source_types": ["news"],
                    "lookback_days": 180,
                    "max_documents": 5,
                    "query": "regulatory customer financing product",
                }
            ]
        },
        "H_init": "complete initialization instructions",
        "H_reflect": "complete reflection instructions",
        "H_analyse": "complete final analysis instructions",
    },
) + " Do not return plan_id or parent_ids; runtime owns structural metadata."


def _parse_role_output(stage: str, value: Mapping[str, Any], parser: Any) -> Any:
    """Convert provider JSON into a domain object with a stage-specific error."""

    try:
        return parser(value)
    except (KeyError, TypeError, ValueError) as exc:
        keys = ", ".join(sorted(str(key) for key in value))
        raise ValidationError(
            f"{stage} returned invalid JSON fields [{keys}]: {type(exc).__name__}: {exc}"
        ) from exc


def _normalize_information_plan_output(
    value: Mapping[str, Any],
    *,
    plan_id: str,
    parent_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Normalize the observed semantic B/H_* provider shape at the role boundary."""

    if "basic_info_policy" in value:
        normalized = dict(value)
    elif isinstance(value.get("B"), Mapping) and all(
        isinstance(value.get(key), str)
        for key in ("H_init", "H_reflect", "H_analyse")
    ):
        normalized = {
            "basic_info_policy": dict(value["B"]),
            "initial_research_skill": value["H_init"],
            "reflection_skill": value["H_reflect"],
            "analysis_prompt": value["H_analyse"],
        }
    else:
        h_init_value = value.get("H_init")
        h_reflect_value = value.get("H_reflect")
        h_analyse_value = value.get("H_analyse", value.get("H_analyze"))
        if not all(
            isinstance(item, Mapping)
            for item in (h_init_value, h_reflect_value, h_analyse_value)
        ):
            field_types = ", ".join(
                f"{key}={type(item).__name__}"
                for key, item in (
                    ("H_init", h_init_value),
                    ("H_reflect", h_reflect_value),
                    ("H_analyse", h_analyse_value),
                )
            )
            raise ValidationError(
                "information_plan_propose returned incompatible semantic fields: "
                + field_types
            )
        h_init = dict(h_init_value)
        h_reflect = dict(h_reflect_value)
        h_analyse = dict(h_analyse_value)
        policy = h_init.get("basic_info_policy")
        if not isinstance(policy, Mapping):
            basic = value.get("B", {})
            if isinstance(basic, Mapping):
                policy = (
                    dict(basic)
                    if "fields" in basic or "requests" in basic
                    else {"fields": [str(key) for key in basic]}
                )
        normalized = {
            "basic_info_policy": policy,
            "initial_research_skill": h_init.get("initial_research_skill"),
            "reflection_skill": h_reflect.get("reflection_skill"),
            "analysis_prompt": h_analyse.get("analysis_prompt"),
        }
    normalized["plan_id"] = plan_id
    normalized["parent_ids"] = list(parent_ids)
    required_strings = (
        "initial_research_skill",
        "reflection_skill",
        "analysis_prompt",
    )
    if any(
        not isinstance(normalized.get(key), str) or not normalized[key].strip()
        for key in required_strings
    ):
        raise ValidationError(
            "information_plan_propose returned missing or non-string Plan fields"
        )
    if not isinstance(normalized.get("basic_info_policy"), Mapping):
        raise ValidationError(
            "information_plan_propose returned invalid basic_info_policy"
        )
    return normalized


def _normalize_signal_result_output(value: Mapping[str, Any]) -> dict[str, Any]:
    """Conservatively align DeepSeek's unavailable state and coverage fields."""

    normalized = dict(value)
    state_value = normalized.get("state")
    status_value = normalized.get("status")
    if isinstance(state_value, Mapping) and isinstance(status_value, Mapping):
        state = dict(state_value)
        status = dict(status_value)
        if state.get("value") == "unavailable":
            status["coverage"] = "unavailable"
            normalized["state"] = state
            normalized["status"] = status
    return normalized


class LLMResearchController:
    """Concrete H_init/H_reflect adapter backed by a guarded JSON role client."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller

    def initialize(
        self, plan: InformationPlan, basic_info: Mapping[str, Any]
    ) -> AgentStep[ResearchState]:
        value, usage = self.caller.complete_json(
            stage="research_controller_initialize",
            system_prompt=(
                "Apply H_init to Basic Info only. Return one ResearchState JSON object; "
                "information needs must be natural language, not Signal ids."
                + _RESEARCH_STATE_OUTPUT
            ),
            payload={
                "initial_research_skill": plan.initial_research_skill,
                "basic_info": dict(basic_info),
            },
            allow_outcomes=False,
        )
        return AgentStep(
            _parse_role_output(
                "research_controller_initialize", value, ResearchState.from_dict
            ),
            usage,
        )

    def reflect(
        self,
        plan: InformationPlan,
        state: ResearchState,
        batch: SignalBatchResult,
    ) -> AgentStep[ResearchState]:
        value, usage = self.caller.complete_json(
            stage="research_controller_reflect",
            system_prompt=(
                "Apply H_reflect once to the complete Signal batch. Return one "
                "ResearchState JSON object with continue/finalize decision."
                + _RESEARCH_STATE_OUTPUT
            ),
            payload={
                "reflection_skill": plan.reflection_skill,
                "research_state": state.to_dict(),
                "signal_batch": [item.to_dict() for item in batch.results],
            },
            allow_outcomes=False,
        )
        return AgentStep(
            _parse_role_output(
                "research_controller_reflect", value, ResearchState.from_dict
            ),
            usage,
        )


class LLMSignalRetrievalAgent:
    """Two-step progressive category/card selector for one frozen Registry."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller

    def select(
        self,
        information_needs: tuple[str, ...],
        signal_registry: FrozenSignalRegistry,
    ) -> AgentStep[tuple[str, ...]]:
        categories = sorted({spec.category for spec in signal_registry.specs})
        category_usage = AgentUsage()
        selected_categories: tuple[str, ...] = ()
        category_payload: dict[str, Any] = {
            "information_needs": list(information_needs),
            "available_categories": categories,
        }
        for attempt in range(2):
            if attempt:
                category_payload["validation_feedback"] = (
                    "The previous categories were empty or outside "
                    "available_categories. Return a non-empty subset only."
                )
            category_value, step_usage = self.caller.complete_json(
                stage="signal_retrieval_categories",
                system_prompt=(
                    "Choose only relevant category names for the information needs. "
                    "Return {\"categories\": [...]}."
                ),
                payload=category_payload,
                allow_outcomes=False,
            )
            category_usage = category_usage + step_usage
            selected_categories = tuple(
                str(item) for item in category_value.get("categories", ())
            )
            if selected_categories and set(selected_categories).issubset(categories):
                break
        else:
            return AgentStep((), category_usage)

        cards = [
            {
                "signal_ref": spec.ref,
                "category": spec.category,
                "description": spec.description,
                "execution_type": spec.execution_type.value,
            }
            for spec in signal_registry.specs
            if spec.category in selected_categories
        ]
        selection_usage = AgentUsage()
        refs: tuple[str, ...] = ()
        selection_payload: dict[str, Any] = {
                "information_needs": list(information_needs),
                "signal_cards": cards,
        }
        allowed = {card["signal_ref"] for card in cards}
        for attempt in range(2):
            if attempt:
                selection_payload["validation_feedback"] = (
                    "The previous signal_refs were empty, duplicated, or outside "
                    "the supplied signal_cards. Return a non-empty unique subset only."
                )
            selection_value, step_usage = self.caller.complete_json(
                stage="signal_retrieval_cards",
                system_prompt=(
                    "Choose the smallest unique Signal batch that answers the needs. "
                    "Return {\"signal_refs\": [...]}."
                ),
                payload=selection_payload,
                allow_outcomes=False,
            )
            selection_usage = selection_usage + step_usage
            refs = tuple(
                str(item) for item in selection_value.get("signal_refs", ())
            )
            if refs and len(set(refs)) == len(refs) and set(refs).issubset(allowed):
                break
        else:
            return AgentStep((), category_usage + selection_usage)
        return AgentStep(refs, category_usage + selection_usage)


class LLMBlindPredictor:
    """No-web two-stage Predictor plus explicitly post-hoc reflection adapter."""

    def __init__(
        self,
        caller: JSONRoleCaller,
        *,
        anonymous_aliases: Iterable[str] = (),
    ) -> None:
        registration = getattr(caller, "registration", None)
        if registration is not None and registration.web_tools_allowed:
            raise ValidationError("Blind Predictor model registration must be no-web")
        self.caller = caller
        self.anonymous_aliases = tuple(anonymous_aliases)

    def predict(self, final_context: Mapping[str, Any]) -> AgentStep[BlindPrediction]:
        value, usage = self.caller.complete_json(
            stage="blind_predictor_predict",
            system_prompt=(
                "Using only the anonymous supplied context, predict whether the next "
                "six months reach at least 2x. If yes choose 2-3x, 3-10x, or 10x+. "
                "Do not use web tools."
                + _BLIND_PREDICTION_OUTPUT
            ),
            payload={"final_context": dict(final_context)},
            allow_outcomes=False,
            anonymous_aliases=self.anonymous_aliases,
        )
        return AgentStep(
            _parse_role_output(
                "blind_predictor_predict", value, BlindPrediction.from_dict
            ),
            usage,
        )

    def reflect(
        self,
        original_context: Mapping[str, Any],
        original_prediction: BlindPrediction,
        ground_truth: GroundTruth,
    ) -> AgentStep[PredictionSelfReflection]:
        _scan_payload(
            {"original_context": dict(original_context)},
            allow_outcomes=False,
            anonymous_aliases=self.anonymous_aliases,
        )
        value, usage = self.caller.complete_json(
            stage="blind_predictor_posthoc_reflect",
            system_prompt=(
                "The saved prediction is immutable. Given its original anonymous "
                "context and newly revealed truth, reflect on the prediction."
                + _PREDICTION_REFLECTION_OUTPUT
            ),
            payload={
                "original_context": dict(original_context),
                "original_prediction": original_prediction.to_dict(),
                "revealed_ground_truth": ground_truth.to_dict(),
            },
            allow_outcomes=True,
            # The context was scanned above. Validated prediction enums may equal
            # common ticker aliases, for example confidence "low" and ticker LOW.
            anonymous_aliases=(),
        )
        return AgentStep(
            _parse_role_output(
                "blind_predictor_posthoc_reflect",
                value,
                PredictionSelfReflection.from_dict,
            ),
            usage,
        )


class LLMInformationPlanProposer:
    """Concrete fixed-H_P candidate proposer; it may change only four Plan fields."""

    def __init__(self, caller: JSONRoleCaller, *, temperature: float = 1.0) -> None:
        if not 0 < temperature <= 1:
            raise ValidationError("Plan proposal temperature must be in (0, 1]")
        self.caller = caller
        self.temperature = temperature

    def propose(
        self,
        *,
        round_id: int,
        candidate_index: int,
        candidate_count: int,
        forbidden_plan_ids: tuple[str, ...],
        parents: tuple[InformationPlan, ...],
        meta_info: tuple[RoundMetaEntry, ...],
        prior: str,
    ) -> InformationPlan:
        payload: dict[str, Any] = {
            "fixed_prior": prior,
            "parents": [item.to_dict() for item in parents],
            "meta_info": [item.to_dict() for item in meta_info],
        }
        payload["proposal_slot"] = {
            "round_id": round_id,
            "candidate_index": candidate_index,
            "candidate_count": candidate_count,
        }
        system_prompt = (
            "Apply the fixed H_P prior. Return only evolvable Plan content: "
            "B, H_init, H_reflect, and H_analyse. B is an analyst-style source "
            "retrieval plan, not a fixed company profile or computed Signal."
            + _INFORMATION_PLAN_OUTPUT
        )
        plan_id = f"plan_r{round_id:04d}_c{candidate_index:02d}"
        parent_ids = tuple(item.plan_id for item in parents)
        failed_value: Mapping[str, Any] | None = None
        failure: ValidationError | None = None
        for attempt in range(2):
            stage = (
                "information_plan_propose"
                if attempt == 0
                else "information_plan_propose_correction"
            )
            request_payload = dict(payload)
            prompt = system_prompt
            if attempt:
                request_payload["invalid_output"] = dict(failed_value or {})
                request_payload["validation_error"] = str(failure)
                prompt += " Correct the invalid content once; return the exact contract only."
            value, _usage = self.caller.complete_json(
                stage=stage,
                system_prompt=prompt,
                payload=request_payload,
                allow_outcomes=False,
                temperature=self.temperature,
            )
            try:
                normalized = _normalize_information_plan_output(
                    value,
                    plan_id=plan_id,
                    parent_ids=parent_ids,
                )
                return _parse_role_output(stage, normalized, InformationPlan.from_dict)
            except ValidationError as exc:
                failed_value = value
                failure = exc
        raise CandidateProposalRejected(
            f"information_plan_propose rejected after one correction: {failure}"
        )


class LLMPlanCritic:
    """Plan-level critic over the complete saved validation batch."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller

    def critique(
        self,
        *,
        plan: InformationPlan,
        trajectories: tuple[Any, ...],
        metrics: PlanMetrics,
    ) -> PlanReflection:
        value, _usage = self.caller.complete_json(
            stage="plan_critic",
            system_prompt=(
                "Ground the reflection only in the supplied batch."
                + _PLAN_REFLECTION_OUTPUT
            ),
            payload={
                "plan": plan.to_dict(),
                "metrics": metrics.to_dict(),
                "trajectories": [item.to_dict() for item in trajectories],
            },
            allow_outcomes=True,
        )
        return _parse_role_output("plan_critic", value, PlanReflection.from_dict)


class LLMRoundReflector:
    """Concrete fixed-H_R reflector over newly completed round records only."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller

    def reflect(
        self,
        *,
        round_id: int,
        records: tuple[PlanRecord, ...],
        prior: str,
    ) -> RoundMetaEntry:
        value, _usage = self.caller.complete_json(
            stage="round_reflect",
            system_prompt=(
                "Apply fixed H_R only to these new records; evidence_refs must cite "
                "supplied plan ids."
                + _ROUND_META_OUTPUT
            ),
            payload={
                "round_id": round_id,
                "fixed_prior": prior,
                "records": [item.to_dict() for item in records],
            },
            allow_outcomes=True,
        )
        return _parse_role_output("round_reflect", value, RoundMetaEntry.from_dict)


class StructuredAgentModel(AgentModel):
    """Concrete GenericAgent model adapter for Mining/Update tool loops."""

    def __init__(
        self,
        caller: JSONRoleCaller,
        *,
        stage: str,
        allow_outcomes: bool,
        final_output_example: Mapping[str, Any],
    ) -> None:
        self.caller = caller
        self.stage = stage
        self.allow_outcomes = allow_outcomes
        self.final_output_example = dict(final_output_example)

    def respond(self, request: AgentRequest) -> AgentTurn:
        value, usage = self.caller.complete_json(
            stage=self.stage,
            system_prompt=(
                "Use only the named domain tools. Return either "
                "{\"action\":\"tool\",\"tool_name\":...,\"arguments\":{...}} "
                "or {\"action\":\"final\",\"output\":...}. The final output "
                "must be an object shaped exactly like "
                f"{json.dumps(self.final_output_example, sort_keys=True)}. "
                "Return candidate refs only after a successful staging tool call; "
                "if no valid candidate was staged, return an empty candidate_refs "
                "list. Never return a diagnosis or proposed Signal directly as the "
                "final output."
            ),
            payload={
                "task_prompt": request.prompt,
                "tool_cards": list(request.tool_cards),
                "workspace": dict(request.workspace),
                "observations": [
                    {
                        "name": item.name,
                        "arguments": dict(item.arguments),
                        "result": item.result,
                    }
                    for item in request.observations
                ],
            },
            allow_outcomes=self.allow_outcomes,
        )
        action = value.get("action")
        if action == "tool":
            return AgentTurn(
                tool_call=ToolCall(
                    str(value.get("tool_name", "")),
                    dict(value.get("arguments", {})),
                ),
                usage=usage,
            )
        if action == "final":
            return AgentTurn(final_output=value.get("output"), usage=usage)
        raise ValidationError("Generic Agent model returned an unknown action")


class StructuredLLMSignalRunner:
    """No-label extraction-skill runner for one Signal and its exact documents."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller

    def execute(
        self,
        spec: SignalSpec,
        documents: tuple[RawInfoDocument, ...],
        skill: str,
        as_of: datetime,
    ) -> tuple[SignalResult, AgentUsage]:
        base_payload = {
            "signal_spec": spec.to_dict(),
            "skill": skill,
            "as_of": as_of.isoformat(),
            "documents": [item.to_dict() for item in documents],
        }
        usage = AgentUsage()
        validation_feedback: dict[str, Any] | None = None
        last_validation_error = "unknown validation failure"

        for _attempt in range(2):
            payload = dict(base_payload)
            if validation_feedback is not None:
                payload["validation_feedback"] = validation_feedback
            value, step_usage = self.caller.complete_json(
                stage="llm_signal_execute",
                system_prompt=(
                    "Apply the versioned extraction skill to only these point-in-time "
                    "documents and use literal evidence spans. If an exact literal "
                    "span cannot be cited, return unavailable with no evidence. When "
                    "validation_feedback is supplied, correct the failed JSON output."
                    + _SIGNAL_RESULT_OUTPUT
                ),
                payload=payload,
                allow_outcomes=False,
            )
            usage = usage + step_usage
            normalized = _normalize_signal_result_output(value)
            try:
                result = _parse_role_output(
                    "llm_signal_execute", normalized, SignalResult.from_dict
                )
                validate_signal_result(spec, result, documents, as_of=as_of)
            except ValidationError as exc:
                last_validation_error = str(exc)
                validation_feedback = {
                    "validation_error": last_validation_error,
                    "failed_output": normalized,
                    "required_action": (
                        "Return corrected JSON grounded only in literal input-document "
                        "spans, or return unavailable with empty evidence."
                    ),
                }
                continue
            return result, usage

        return (
            SignalResult(
                signal_id=spec.signal_id,
                version=spec.version,
                value=SignalValue.UNAVAILABLE,
                confidence=0.0,
                interpretation=(
                    "LLM Signal output failed strict validation after one correction: "
                    f"{last_validation_error}"
                ),
                coverage=SignalCoverage.UNAVAILABLE,
            ),
            usage,
        )


def run_bounded_evolution_cycle(
    *,
    workspace_path: str | Path,
    approved_dataset_manifest: str | Path,
    contract: EvolutionRunContract,
    allow_external: bool,
    acknowledged_contract_hash: str | None = None,
    allow_data_external: bool = False,
    environ: Mapping[str, str] | None = None,
    on_progress: ProgressCallback | None = None,
) -> DualLoopResult:
    """Run/resume one frozen finite Fast group and one validation-only Slow cycle."""

    workspace_root = Path(workspace_path)
    dataset = load_approved_development_dataset(approved_dataset_manifest)
    if dataset.approved_manifest_hash != contract.dataset_manifest_hash:
        raise ValidationError("approved dataset differs from frozen run contract")
    registry = SignalRegistry(
        workspace_root / "signals",
        candidate_root=workspace_root / "signals_candidates",
    )
    snapshot = registry.freeze()
    if (
        registry.version != contract.signal_registry_version
        or snapshot.registry_hash != contract.signal_registry_hash
    ):
        raise ValidationError("stable Signal Registry differs from frozen run contract")
    if _canonical_hash(_default_priors_dict()) != contract.priors_hash:
        raise ValidationError("fixed evolution priors differ from frozen run contract")

    limits = dict(contract.limits)
    target_plan_rounds = int(limits.get("plan_rounds_per_signal_cycle", 5))
    evolution_workspace = EvolutionWorkspace(workspace_root)
    cycle = evolution_workspace.start_or_resume_cycle(
        run_contract_hash=contract.contract_hash,
        target_plan_rounds=target_plan_rounds,
    )
    cycle_id = int(cycle["cycle_id"])

    def emit(event: Mapping[str, Any]) -> None:
        event_type = str(event.get("event_type") or "runtime_progress")
        details = {
            key: value for key, value in event.items() if key != "event_type"
        }
        details.setdefault("cycle_id", cycle_id)
        if event_type == "round_committed":
            evolution_workspace.mark_cycle_phase("fast_loop")
        elif event_type == "slow_loop_started":
            evolution_workspace.mark_cycle_phase("slow_loop")
        stored = evolution_workspace.append_event(event_type, details)
        if on_progress is not None:
            on_progress(stored)

    emit(
        {
            "event_type": "cycle_resumed" if cycle["resumed"] else "cycle_started",
            "start_round": int(cycle["start_round"]),
            "completed_plan_rounds": int(cycle["completed_plan_rounds"]),
            "target_plan_rounds": target_plan_rounds,
            "phase": str(cycle["phase"]),
        }
    )
    completed_plan_rounds = int(cycle["completed_plan_rounds"])
    staged_slow = evolution_workspace.staged_slow_result(cycle_id)
    if staged_slow is not None:
        if completed_plan_rounds != target_plan_rounds:
            raise ValidationError("staged Slow result exists before Fast loop completion")
        signal_result = SlowLoopResult.from_dict(staged_slow)
        emit(
            {
                "event_type": "slow_loop_result_reused",
                "validated_pending_approval": dict(
                    signal_result.validated_pending_approval
                ),
                "registry_version": signal_result.registry_version,
            }
        )
        evolution_workspace.complete_cycle(cycle_id=cycle_id)
        emit(
            {
                "event_type": "cycle_committed",
                "last_completed_round": evolution_workspace.last_completed_round,
                "last_completed_cycle": evolution_workspace.last_completed_cycle,
            }
        )
        return DualLoopResult(plan_rounds=(), signal_evolution=signal_result)

    ledger = ExternalAttemptLedger(
        workspace_root / "attempts.json",
        max_attempts=contract.max_external_attempts,
        max_total_cost=contract.max_total_cost,
    )
    judge_alias = str(contract.models["judge"]["alias"])
    evolution_alias = str(contract.models["proposer"]["alias"])
    judge_caller = StructuredRoleClient(
        registration=get_model(judge_alias, role="judge"),
        contract=contract,
        workspace=workspace_root,
        ledger=ledger,
        allow_external=allow_external,
        acknowledged_contract_hash=acknowledged_contract_hash,
        environ=environ,
        on_progress=emit,
    )
    evolution_caller = StructuredRoleClient(
        registration=get_model(evolution_alias, role="evolution"),
        contract=contract,
        workspace=workspace_root,
        ledger=ledger,
        allow_external=allow_external,
        acknowledged_contract_hash=acknowledged_contract_hash,
        environ=environ,
        on_progress=emit,
    )
    raw_info_store = RawInfoStore(workspace_root / "raw_info")
    evidence_resolver = _build_evidence_resolver(
        workspace_root,
        raw_info_store,
        contract=contract,
        allow_data_external=allow_data_external,
        environ=environ,
        cycle_id=cycle_id,
    )
    aliases = _dataset_identity_aliases(dataset)
    runtime_limits = RuntimeLimits(
        max_signal_rounds=int(limits.get("max_signal_rounds", 5)),
        max_signal_calls=int(limits.get("max_signal_calls", 20)),
        max_llm_calls=int(limits.get("max_llm_calls", 40)),
        max_tokens=int(limits.get("max_tokens", 120_000)),
        max_cost=float(limits.get("max_case_cost", 5.0)),
    )
    archive = evolution_workspace.restore_archive(
        expected_run_contract_hash=contract.contract_hash
    )
    meta_memory = evolution_workspace.restore_meta()
    signal_runner = StructuredLLMSignalRunner(judge_caller)
    evaluator = RuntimePlanEvaluator(
        raw_info_store=raw_info_store,
        evidence_resolver=evidence_resolver,
        controller=LLMResearchController(judge_caller),
        signal_agent=LLMSignalRetrievalAgent(judge_caller),
        predictor=LLMBlindPredictor(
            judge_caller,
            anonymous_aliases=aliases,
        ),
        prediction_root=workspace_root / "predictions",
        trajectory_root=evolution_workspace.trajectory_root,
        limits=runtime_limits,
        llm_signal_runner=signal_runner,
        on_progress=emit,
    )
    plan_engine = PlanEvolutionEngine(
        archive=archive,
        meta_memory=meta_memory,
        signal_registry=registry,
        evaluator=evaluator,
        proposer=LLMInformationPlanProposer(
            evolution_caller,
            temperature=float(limits.get("plan_proposal_temperature", 1.0)),
        ),
        critic=LLMPlanCritic(judge_caller),
        round_reflector=LLMRoundReflector(judge_caller),
        workspace=evolution_workspace,
        seed_plans=(default_information_plan(),),
        candidates_per_round=int(limits.get("candidates_per_round", 3)),
        top_k=int(limits.get("top_k", 3)),
        random_k=int(limits.get("random_k", 2)),
        similarity_threshold=float(limits.get("similarity_threshold", 0.9)),
        run_contract_hash=contract.contract_hash,
        on_progress=emit,
    )
    signal_engine = SignalEvolutionEngine(
        registry=registry,
        raw_info_store=raw_info_store,
        discovery_cases=dataset.discovery,
        meta_memory=meta_memory,
        workspace=evolution_workspace,
        mining_agent=GenericAgent(
            StructuredAgentModel(
                evolution_caller,
                stage="signal_mining_agent",
                allow_outcomes=True,
                final_output_example={"candidate_refs": ["candidate_signal:v1"]},
            )
        ),
        update_agent=GenericAgent(
            StructuredAgentModel(
                evolution_caller,
                stage="signal_update_agent",
                allow_outcomes=True,
                final_output_example={"candidate_refs": ["candidate_signal:v2"]},
            )
        ),
        llm_signal_runner=signal_runner,
        max_agent_steps=int(limits.get("max_agent_steps", 20)),
    )
    result = DualLoopEvolutionEngine(
        plan_engine=plan_engine,
        signal_engine=signal_engine,
        signal_registry=registry,
        dataset=dataset,  # type: ignore[arg-type]
        plan_rounds_per_signal_cycle=int(
            limits.get("plan_rounds_per_signal_cycle", 5)
        ),
        on_progress=emit,
    ).run_cycle(completed_plan_rounds=completed_plan_rounds)
    slow_result_path = evolution_workspace.stage_slow_result(
        cycle_id=cycle_id,
        result=result.signal_evolution.to_dict(),
    )
    emit(
        {
            "event_type": "slow_loop_result_staged",
            "slow_result_path": str(slow_result_path),
        }
    )
    evolution_workspace.complete_cycle(cycle_id=cycle_id)
    emit(
        {
            "event_type": "cycle_committed",
            "last_completed_round": evolution_workspace.last_completed_round,
            "last_completed_cycle": evolution_workspace.last_completed_cycle,
        }
    )
    return result


def build_run_contract(
    *,
    run_id: str,
    dataset_manifest_path: str | Path,
    inventory: LocalEvolutionInventory,
    signal_registry_version: int,
    signal_registry_hash: str,
    priors: Mapping[str, str],
    role_aliases: Mapping[str, str],
    project_root: str | Path,
    limits: Mapping[str, Any],
    max_external_attempts: int,
    max_total_cost: float,
    data_acquisition: DataAcquisitionPolicy = DataAcquisitionPolicy(),
    environ: Mapping[str, str] | None = None,
) -> EvolutionRunContract:
    """Build one bounded contract from reviewed, hashed local inputs."""

    manifest_path = Path(dataset_manifest_path)
    manifest = _read_json(manifest_path)
    if manifest.get("approval_status") != "human_approved":
        raise ValidationError("dataset split manifest is not human-approved")
    if manifest.get("locked_test_sealed") is not True:
        raise ValidationError("dataset split manifest must seal Locked Test")
    return EvolutionRunContract(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        dataset_manifest_hash=_sha256_file(manifest_path),
        raw_info_inventory_hash=inventory.inventory_hash,
        signal_registry_version=signal_registry_version,
        signal_registry_hash=signal_registry_hash,
        priors_hash=_canonical_hash(dict(priors)),
        models=public_model_contract(role_aliases, environ=environ),
        code_revision=current_code_revision(project_root),
        python_runtime=platform.python_version(),
        limits=dict(limits),
        max_external_attempts=max_external_attempts,
        max_total_cost=max_total_cost,
        data_acquisition=data_acquisition,
    )


def _build_evidence_resolver(
    workspace_root: Path,
    store: RawInfoStore,
    *,
    contract: EvolutionRunContract,
    allow_data_external: bool,
    environ: Mapping[str, str] | None,
    cycle_id: int,
) -> EvidenceResolver:
    """Build production adapters over the existing cache/ledger/quota boundary."""

    configured = contract.data_acquisition
    effective_policy = DataAcquisitionPolicy(
        enabled=configured.enabled and allow_data_external,
        allowed_providers=configured.allowed_providers,
        allowed_capabilities=configured.allowed_capabilities,
        allowed_source_types=configured.allowed_source_types,
        max_requests_per_cycle=configured.max_requests_per_cycle,
        max_requests_per_run=configured.max_requests_per_run,
    )
    adapters: list[Any] = []
    env = os.environ if environ is None else environ
    config = load_config(environ=env).data_sources
    if effective_policy.enabled:
        cache = RawDataCache(workspace_root / "cache" / "data")
        ledger = RequestLedger(workspace_root / "data_requests.jsonl")
        source_budget = SourceBudget(ledger)

        def managed(source: str, capability: DataCapability) -> ManagedHttpTransport:
            return ManagedHttpTransport(
                source,
                capability,
                UrllibJsonTransport(),
                cache,
                ledger,
                source_budget,
            )

        sec_user_agent = str(env.get("SOA_SEC_USER_AGENT", "")).strip()
        if sec_user_agent:
            sec_facts_client = SecEdgarClient(
                sec_user_agent,
                transport=managed(
                    "sec_edgar", DataCapability.FINANCIAL_STATEMENTS
                ),
            )
            sec_filing_client = SecEdgarClient(
                sec_user_agent,
                transport=managed("sec_edgar", DataCapability.FILING_DOCUMENTS),
            )
            adapters.extend(
                [
                    SecCompanyFactsAdapter(sec_facts_client),
                    SecFilingAdapter(sec_filing_client),
                ]
            )
        else:
            adapters.extend(
                [
                    UnavailableProviderAdapter(
                        "sec_edgar",
                        SecCompanyFactsAdapter.source_types,
                        SecCompanyFactsAdapter.capabilities,
                        "SOA_SEC_USER_AGENT is not configured.",
                    ),
                    UnavailableProviderAdapter(
                        "sec_edgar",
                        SecFilingAdapter.source_types,
                        SecFilingAdapter.capabilities,
                        "SOA_SEC_USER_AGENT is not configured.",
                    ),
                ]
            )
        alpha_key = env.get(config.alpha_vantage_api_key_env_var)
        if alpha_key:
            alpha_news = AlphaVantageClient(
                alpha_key,
                transport=managed("alpha_vantage", DataCapability.NEWS),
            )
            alpha_prices = AlphaVantageClient(
                alpha_key,
                transport=managed("alpha_vantage", DataCapability.PRICE_DAILY),
            )
            adapters.extend(
                [
                    AlphaVantageNewsAdapter(alpha_news),
                    HistoricalPriceAdapter(
                        "alpha_vantage",
                        lambda symbol, _start, _end: alpha_prices.daily_prices(
                            symbol, outputsize="full"
                        ),
                        event_source=alpha_prices,
                    ),
                ]
            )
        else:
            adapters.extend(
                [
                    UnavailableProviderAdapter(
                        "alpha_vantage",
                        ("news", "company_news"),
                        ("news",),
                        f"{config.alpha_vantage_api_key_env_var} is not configured.",
                    ),
                    UnavailableProviderAdapter(
                        "alpha_vantage",
                        ("price_daily", "historical_price", "prices"),
                        ("price_daily",),
                        f"{config.alpha_vantage_api_key_env_var} is not configured.",
                    ),
                ]
            )
        massive_key = env.get(config.massive_api_key_env_var)
        if massive_key:
            massive = MassiveClient(
                massive_key,
                transport=managed("massive", DataCapability.PRICE_DAILY),
            )
            adapters.append(
                HistoricalPriceAdapter(
                    "massive",
                    lambda symbol, start, end: massive.daily_prices(
                        symbol, start_date=start, end_date=end
                    ),
                    event_source=massive,
                )
            )
        else:
            adapters.append(
                UnavailableProviderAdapter(
                    "massive",
                    ("price_daily", "historical_price", "prices"),
                    ("price_daily",),
                    f"{config.massive_api_key_env_var} is not configured.",
                )
            )
        stooq = StooqClient(
            api_key=env.get(config.stooq_api_key_env_var),
            transport=managed("stooq", DataCapability.PRICE_DAILY),
        )
        adapters.append(
            HistoricalPriceAdapter(
                "stooq",
                lambda symbol, start, end: stooq.daily_prices(
                    symbol, start_date=start, end_date=end
                ),
                event_source=stooq,
            )
        )
    else:
        # Adapter descriptors are still present so a local miss is correctly
        # classified as unauthorized rather than as an unknown capability.
        adapters.extend(
            [
                SecCompanyFactsAdapter(None),
                SecFilingAdapter(None),
                AlphaVantageNewsAdapter(None),
                HistoricalPriceAdapter("massive", lambda *_: ()),
            ]
        )
    adapters.append(
        HistoricalUnavailableAdapter(
            "alpha_vantage",
            ("company_profile", "company_overview"),
        )
    )
    return EvidenceResolver(
        store,
        adapters=adapters,
        policy=effective_policy,
        budget=DataAcquisitionBudget(
            ledger_path=workspace_root / "data_acquisition_requests.jsonl",
            cycle_id=cycle_id,
        ),
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


def _default_priors_dict() -> dict[str, str]:
    return {
        "reflect_round": DEFAULT_EVOLUTION_PRIORS.reflect_round,
        "propose_plan": DEFAULT_EVOLUTION_PRIORS.propose_plan,
        "mine_signal": DEFAULT_EVOLUTION_PRIORS.mine_signal,
        "update_signal": DEFAULT_EVOLUTION_PRIORS.update_signal,
    }


def _dataset_identity_aliases(dataset: ApprovedDevelopmentDataset) -> tuple[str, ...]:
    aliases: set[str] = set()
    for case in (*dataset.discovery, *dataset.evolution_validation):
        for key in ("company_name", "ticker", "symbol", "identity_aliases"):
            value = case.basic_info.get(key)
            if isinstance(value, str):
                aliases.add(value)
            elif isinstance(value, (list, tuple)):
                aliases.update(str(item) for item in value)
    return tuple(sorted((item for item in aliases if item.strip()), key=len, reverse=True))


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
    _scan_payload(payload, allow_outcomes=False, anonymous_aliases=())
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


def _stream_expansion_candidates(
    path: Path,
    *,
    listings: Mapping[str, Mapping[str, Any]],
    prediction_dates: tuple[date, ...],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, str]],
    int,
]:
    if not path.is_file():
        raise ValidationError(f"large local price archive is missing: {path}")
    reader = _StreamingJSONReader(path)
    metadata: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
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
                        candidate, exclusion = _expansion_candidate(
                            listing,
                            raw_bars,
                            prediction_dates=prediction_dates,
                        )
                        if candidate is not None:
                            candidates.append(candidate)
                        elif exclusion is not None:
                            exclusions.append(exclusion)
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
    return metadata, candidates, exclusions, priced_symbol_count


def _expansion_candidate(
    listing: Mapping[str, Any],
    raw_bars: list[Any],
    *,
    prediction_dates: tuple[date, ...],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    symbol = str(listing["symbol"]).upper()
    company_id = _expansion_company_id(listing)
    ipo_date = str(listing.get("ipo_date") or "") or None
    if ipo_date:
        try:
            parsed_ipo_date = date.fromisoformat(ipo_date)
        except ValueError:
            return None, {
                "symbol": symbol,
                "company_id": company_id,
                "reason": "invalid_listing_ipo_date",
            }
        if prediction_dates[0] < parsed_ipo_date:
            return None, {
                "symbol": symbol,
                "company_id": company_id,
                "prediction_date": prediction_dates[0].isoformat(),
                "ipo_date": ipo_date,
                "reason": "prediction_before_listing_ipo_date",
            }
    if not raw_bars:
        return None, {
            "symbol": symbol,
            "company_id": company_id,
            "reason": "empty_price_history",
        }
    labels: list[tuple[date, dict[str, Any]]] = []
    for prediction_date in prediction_dates:
        try:
            label = _six_month_smoothed_multiple(raw_bars, prediction_date)
        except (TypeError, ValueError, ValidationError) as exc:
            return None, {
                "symbol": symbol,
                "company_id": company_id,
                "prediction_date": prediction_date.isoformat(),
                "reason": str(exc),
            }
        labels.append((prediction_date, label))
    liquidity = _historical_dollar_liquidity(raw_bars, prediction_dates)
    company_name = str(listing.get("name") or symbol)
    cik = _normalized_cik(listing.get("cik"))
    exchange = str(listing.get("exchange") or "unknown").upper()
    max_multiple = max(float(label["realized_max_multiple"]) for _, label in labels)
    stratum = _expansion_stratum(max_multiple)
    diversity = {
        "exchange": exchange,
        "ipo_age_bucket": _ipo_age_bucket(ipo_date, prediction_dates[0]),
        "dollar_liquidity_bucket": _dollar_liquidity_bucket(liquidity),
        "pre_prediction_average_dollar_volume": liquidity,
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
        None,
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


def _historical_dollar_liquidity(
    raw_bars: Iterable[Any], prediction_dates: tuple[date, ...]
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
        if value >= 0:
            parsed.append((date.fromisoformat(str(bar["as_of_date"])), value))
    means: list[float] = []
    for prediction_date in prediction_dates:
        values = [value for bar_date, value in parsed if bar_date < prediction_date][-20:]
        if values:
            means.append(sum(values) / len(values))
    if not means:
        return None
    ordered = sorted(means)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


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


def _scan_payload(
    value: Any,
    *,
    allow_outcomes: bool,
    anonymous_aliases: Iterable[str],
) -> None:
    aliases = tuple(
        sorted(
            {str(item).strip() for item in anonymous_aliases if str(item).strip()},
            key=len,
            reverse=True,
        )
    )

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                normalized = _normalize_field(str(key))
                if not allow_outcomes and _is_outcome_field(normalized):
                    raise ValidationError(f"outcome field leaked into request: {path}.{key}")
                visit(nested, f"{path}.{key}")
            return
        if isinstance(item, (list, tuple)):
            for index, nested in enumerate(item):
                visit(nested, f"{path}[{index}]")
            return
        if isinstance(item, str):
            for alias in aliases:
                ticker_like = alias.isalnum() and alias.isupper() and len(alias) <= 5
                haystack = item if ticker_like else item.casefold()
                needle = alias if ticker_like else alias.casefold()
                if re.search(
                    rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])",
                    haystack,
                ):
                    raise ValidationError(f"identity alias leaked into anonymous request: {path}")

    visit(value, "payload")


def _model_cost(
    registration: RegisteredModel, *, input_tokens: int, output_tokens: int
) -> float:
    return (
        input_tokens * registration.default_input_cost_per_million_tokens
        + output_tokens * registration.default_output_cost_per_million_tokens
    ) / 1_000_000


def _usage_from_cache(data: Mapping[str, Any]) -> AgentUsage:
    usage = data.get("usage", {})
    return AgentUsage(
        llm_calls=0,
        tokens=int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
        cost=0.0,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValidationError("structured model response must be a JSON object")
    return value


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


def _normalize_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _is_outcome_field(normalized: str) -> bool:
    return normalized in _FORBIDDEN_OUTCOME_KEYS or any(
        normalized.startswith(f"{field}_") or normalized.endswith(f"_{field}")
        for field in _FORBIDDEN_OUTCOME_KEYS
    )


def _emit_runtime_progress(
    callback: ProgressCallback | None,
    event_type: str,
    **details: Any,
) -> None:
    if callback is not None:
        callback({"event_type": event_type, **details})


def _canonical_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"required local artifact is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"required JSON artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON artifact must contain an object: {path}")
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    expected = json.loads(json.dumps(dict(value), sort_keys=True))
    if path.exists():
        if _read_json(path) != expected:
            raise ValidationError(f"conflicting immutable evolution artifact: {path}")
        return
    _atomic_write_json(path, expected)
