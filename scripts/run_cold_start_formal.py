"""Run the formal universe-scanned cold-start workflow."""

from __future__ import annotations

import argparse
import json
import os
import json as _json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib import parse, request
from urllib.error import HTTPError, URLError

from stock_opportunity_agent.cases import (
    CaseOutcomeLabel,
    CaseSlicePlan,
    ControlMatchCriteria,
    HistoricalCandidate,
    HistoricalCandidateSelection,
    build_historical_cases_from_packets,
    default_outcome_definition,
    detect_price_inflections,
    eligible_common_stock_listings,
    label_price_outcome,
    matured_selection_window,
    select_historical_candidates,
)
from stock_opportunity_agent.config import AgentConfig, PromptConfig
from stock_opportunity_agent.data import (
    AlphaVantageClient,
    DataSourceError,
    DocumentRecord,
    FinnhubClient,
    MassiveClient,
    PriceBar,
    SecEdgarClient,
    SecurityListing,
    StooqClient,
    normalize_price_features,
)
from stock_opportunity_agent.llm.openrouter import OpenRouterChatClient
from stock_opportunity_agent.memory import FileSignalLibrary, FileThemeLibrary
from stock_opportunity_agent.models import (
    Catalyst,
    CatalystStatus,
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    FeatureRecord,
    VersionStamp,
)
from stock_opportunity_agent.orchestration import run_cold_start_case_learning
from stock_opportunity_agent.research import (
    CachedInflectionResearcher,
    CompositeInflectionResearcher,
    FactorInflectionResearcher,
    OpenAIBlindCaseResearcher,
    OpenAIWebInflectionResearcher,
)


@dataclass(frozen=True)
class PriceFetchResult:
    """Downloaded or failed price history for one symbol."""

    symbol: str
    bars: tuple[PriceBar, ...]
    error: str | None = None


@dataclass(frozen=True)
class ColdStartRunPaths:
    """Stage directories for one formal cold-start run."""

    root: Path
    universe_dir: Path
    prices_dir: Path
    selection_dir: Path
    documents_dir: Path
    packets_dir: Path
    research_dir: Path


@dataclass(frozen=True)
class ContextFetchResult:
    """Point-in-time unstructured evidence fetched for selected candidates."""

    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]]
    catalysts_by_symbol: dict[str, tuple[Catalyst, ...]]
    warnings: tuple[str, ...]


def main() -> None:
    """Execute the formal cold-start workflow."""

    args = _parse_args()
    _load_local_env()
    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()
    args.run_id = args.run_id or _default_run_id(run_date, args.openrouter_model)
    created_at = datetime.now(timezone.utc)
    config = _openrouter_config(args.openrouter_model)
    definition = default_outcome_definition()
    output_dir = _resolve_output_dir(args)
    paths = _run_paths(output_dir)
    _ensure_run_dirs(paths)

    print(f"[formal-cold-start] run_id={args.run_id}")
    print(f"[formal-cold-start] run_date={run_date.isoformat()}")
    print(f"[formal-cold-start] run_dir={output_dir}")
    if args.selection_summary_path:
        selection = _load_selection_summary(Path(args.selection_summary_path))
        selected_symbols = [candidate.symbol for candidate in selection.selected_candidates]
        selected_listings = _listings_from_selection(selection, created_at)
        selected_listings, listing_context_warnings = _enrich_listings_with_sec_ciks(selected_listings, config)
        price_start = selection.selection_window_start - timedelta(days=max(CaseSlicePlan().offsets_days) + 160)
        print(f"[formal-cold-start] resuming from selection summary: {args.selection_summary_path}")
        print("[formal-cold-start] selected symbols: " + ", ".join(selected_symbols))
        print(
            "[formal-cold-start] fetching selected-symbol prices "
            f"{price_start.isoformat()}..{run_date.isoformat()}"
        )
        bars_by_symbol, price_warnings = _load_or_fetch_price_histories(
            args,
            selected_listings,
            price_start,
            run_date,
            paths=paths,
        )
        print(
            "[formal-cold-start] selected price histories "
            f"ok={len(bars_by_symbol)} skipped={len(selected_listings) - len(bars_by_symbol)}"
        )
    else:
        print("[formal-cold-start] loading active US listings from Alpha Vantage")
        listings = list(eligible_common_stock_listings(_active_listings(config)))
        listings, listing_context_warnings = _enrich_listings_with_sec_ciks(listings, config)
        if args.max_listings:
            listings = listings[: args.max_listings]
            print(f"[formal-cold-start] capped listings to {len(listings)} for this run")
        else:
            print(f"[formal-cold-start] loaded {len(listings)} active listing(s)")
        universe_path = paths.universe_dir / "eligible_listings.json"
        _write_json(
            universe_path,
            {
                "run_id": args.run_id,
                "created_at": created_at.isoformat(),
                "listing_count": len(listings),
                "context_warnings": listing_context_warnings,
                "listings": [_listing_to_dict(listing) for listing in listings],
            },
        )
        print(f"[formal-cold-start] wrote universe checkpoint: {universe_path}")

        window_start, window_end = matured_selection_window(run_date, definition)
        price_start = window_start - timedelta(days=max(CaseSlicePlan().offsets_days) + 160)
        print(
            "[formal-cold-start] scanning prices "
            f"{price_start.isoformat()}..{run_date.isoformat()} "
            f"for matured candidate anchors {window_start.isoformat()}..{window_end.isoformat()}"
        )
        bars_by_symbol, price_warnings = _load_or_fetch_price_histories(
            args,
            listings,
            price_start,
            run_date,
            paths=paths,
        )
        print(
            "[formal-cold-start] price histories "
            f"ok={len(bars_by_symbol)} skipped={len(listings) - len(bars_by_symbol)}"
        )

        rough_selection = select_historical_candidates(
            listings=listings,
            bars_by_symbol=bars_by_symbol,
            run_date=run_date,
            outcome_definition=definition,
            max_winners=args.max_winners,
            max_controls=args.max_controls,
            max_failures=args.max_failures,
        )
        print(
            "[formal-cold-start] rough selected "
            f"{len(rough_selection.selected_candidates)} candidate(s); labels={dict(rough_selection.label_counts)}"
        )
        inflection_dates = _inflection_dates_for_candidates(
            rough_selection.selected_candidates,
            bars_by_symbol,
            window_start=window_start,
            window_end=window_end,
        )
        selection = select_historical_candidates(
            listings=listings,
            bars_by_symbol=bars_by_symbol,
            run_date=run_date,
            outcome_definition=definition,
            max_winners=args.max_winners,
            max_controls=args.max_controls,
            max_failures=args.max_failures,
            inflection_dates_by_symbol=inflection_dates,
        )
        selected_symbols = [candidate.symbol for candidate in selection.selected_candidates]
        print("[formal-cold-start] selected symbols: " + ", ".join(selected_symbols))

        selected_listings = [listing for listing in listings if listing.symbol.upper() in set(selected_symbols)]
    context = _load_or_fetch_context_documents(
        args,
        selection.selected_candidates,
        selected_listings,
        config,
        created_at,
        paths=paths,
    )
    if listing_context_warnings or context.warnings:
        print(
            "[formal-cold-start] context warnings "
            f"listing={len(listing_context_warnings)} documents={len(context.warnings)}"
        )
    features_by_symbol = _features_for_candidates(selection.selected_candidates, bars_by_symbol, created_at)
    cases = build_historical_cases_from_packets(
        listings=selected_listings,
        bars_by_symbol=bars_by_symbol,
        features_by_symbol=features_by_symbol,
        version=_version(config),
        outcome_definition=definition,
        slice_plan=CaseSlicePlan(),
        inflection_dates_by_symbol={candidate.symbol: candidate.inflection_date for candidate in selection.selected_candidates},
        documents_by_symbol=context.documents_by_symbol,
        catalysts_by_symbol=context.catalysts_by_symbol,
    )
    if not cases:
        raise RuntimeError("formal cold start produced no historical cases after inflection-anchored packet build")
    print(f"[formal-cold-start] built {len(cases)} point-in-time case packet(s)")
    cases_path = paths.packets_dir / "historical_cases.json"
    _write_json(
        cases_path,
        {
            "run_id": args.run_id,
            "created_at": created_at.isoformat(),
            "case_count": len(cases),
            "cases": [_case_to_dict(case) for case in cases],
        },
    )
    print(f"[formal-cold-start] wrote case checkpoint: {cases_path}")

    if not args.selection_summary_path:
        selection_path = paths.selection_dir / "historical_candidate_selection.json"
        _write_json(
            selection_path,
            {
                "run_id": args.run_id,
                "created_at": created_at.isoformat(),
                "selection": selection.to_dict(),
                "price_warnings_sample": price_warnings[: args.warning_sample_size],
                "price_warning_count": len(price_warnings),
                "price_sources": list(_parse_price_sources(args)),
                "context_warning_count": len(listing_context_warnings) + len(context.warnings),
                "context_warnings_sample": (listing_context_warnings + list(context.warnings))[: args.warning_sample_size],
                "packet_anchor": "inflection_date",
                "slice_offsets_days": list(CaseSlicePlan().offsets_days),
                "point_in_time_note": (
                    "ResearchPacket as-of dates are built before each selected symbol's inflection_date. "
                    "Retrospective outcome labels and forward returns are excluded from blind packet evidence."
                ),
            },
        )
        print(f"[formal-cold-start] wrote selection summary: {selection_path}")

    client = OpenRouterChatClient(args.openrouter_model, _required_env("OPENROUTER_API_KEY"))
    factor_researcher = FactorInflectionResearcher(bars_by_symbol, min_forward_return=definition.winner_min_return)
    inflection_researchers = [factor_researcher]
    if args.web_inflection_mode == "cached":
        inflection_researchers.append(CachedInflectionResearcher(OpenAIWebInflectionResearcher(client)))
    output = run_cold_start_case_learning(
        cases,
        config=config,
        output_dir=paths.research_dir,
        run_id=args.run_id,
        created_at=created_at,
        signal_library=FileSignalLibrary(".agent_state/memory/signals"),
        theme_library=FileThemeLibrary(".agent_state/memory/themes"),
        control_match_criteria=ControlMatchCriteria(max_controls_per_winner=args.controls_per_winner),
        blind_researcher=OpenAIBlindCaseResearcher(client),
        inflection_researcher=CompositeInflectionResearcher(tuple(inflection_researchers)),
        research_max_workers=args.research_max_workers,
        progress=print if not args.quiet else None,
    )
    if args.quiet:
        print(output.manifest_path)


def _parse_args():
    parser = argparse.ArgumentParser(description="Run formal universe-scanned cold-start learning.")
    parser.add_argument("--run-date", default=None, help="Run date in YYYY-MM-DD; defaults to today.")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default="runs/cold_start")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--openrouter-model", default="openai/gpt-5.5")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--price-timeout", type=float, default=12.0)
    parser.add_argument("--price-source", choices=("massive", "alpaca", "stooq"), default=None)
    parser.add_argument("--price-sources", default="massive,alpaca,stooq")
    parser.add_argument("--price-history-path", default=None, help="Load an existing price-history checkpoint.")
    parser.add_argument("--max-listings", type=int, default=0, help="Optional scan cap for debugging; 0 scans all listings.")
    parser.add_argument("--selection-summary-path", default=None, help="Resume from an existing formal selection summary.")
    parser.add_argument("--max-winners", type=int, default=12)
    parser.add_argument("--max-controls", type=int, default=36)
    parser.add_argument("--max-failures", type=int, default=12)
    parser.add_argument("--controls-per-winner", type=int, default=5)
    parser.add_argument("--research-max-workers", type=int, default=1)
    parser.add_argument("--web-inflection-mode", choices=("cached", "off"), default="cached")
    parser.add_argument("--context-mode", choices=("provider", "off"), default="provider")
    parser.add_argument("--filing-forms", default="10-K,10-Q,8-K")
    parser.add_argument("--filing-lookback-days", type=int, default=540)
    parser.add_argument("--max-filings-per-symbol", type=int, default=6)
    parser.add_argument("--news-lookback-days", type=int, default=365)
    parser.add_argument("--max-news-per-symbol", type=int, default=12)
    parser.add_argument("--max-transcripts-per-symbol", type=int, default=2)
    parser.add_argument("--document-excerpt-chars", type=int, default=1500)
    parser.add_argument("--skip-filing-text", action="store_true")
    parser.add_argument("--warning-sample-size", type=int, default=50)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def _openrouter_config(model: str) -> AgentConfig:
    return AgentConfig(
        prompts=PromptConfig(
            model_version=model,
            openai_api_key_env_var="OPENROUTER_API_KEY",
            openai_base_url="https://openrouter.ai/api/v1",
        )
    )


def _default_run_id(run_date: date, model: str) -> str:
    model_slug = _slug(model.split("/")[-1])
    return f"cold-start-formal-{model_slug}-{run_date.isoformat()}"


def _resolve_output_dir(args) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    return Path(args.output_root) / "formal" / _slug(args.run_id)


def _run_paths(root: Path) -> ColdStartRunPaths:
    return ColdStartRunPaths(
        root=root,
        universe_dir=root / "01_universe",
        prices_dir=root / "02_prices",
        selection_dir=root / "03_selection",
        documents_dir=root / "04_documents",
        packets_dir=root / "05_packets",
        research_dir=root / "06_research",
    )


def _ensure_run_dirs(paths: ColdStartRunPaths) -> None:
    for path in (
        paths.root,
        paths.universe_dir,
        paths.prices_dir,
        paths.selection_dir,
        paths.documents_dir,
        paths.packets_dir,
        paths.research_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _slug(value: str) -> str:
    chars = [char.lower() if char.isalnum() else "-" for char in value]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "run"


def _active_listings(config: AgentConfig) -> list[SecurityListing]:
    client = AlphaVantageClient.from_config(config.data_sources)
    listings = client.listing_status(state="active")
    return [
        listing
        for listing in listings
        if (listing.exchange or "").upper() in {"NYSE", "NASDAQ", "NYSE ARCA", "NYSE MKT", "AMEX"}
    ]


def _load_selection_summary(path: Path) -> HistoricalCandidateSelection:
    data = json.loads(path.read_text(encoding="utf-8"))
    selection = data.get("selection")
    if not isinstance(selection, dict):
        raise RuntimeError("selection summary is missing selection object")
    candidates = tuple(
        _candidate_from_selection(item)
        for item in selection.get("selected_candidates", ())
        if isinstance(item, dict)
    )
    return HistoricalCandidateSelection(
        run_date=date.fromisoformat(str(selection["run_date"])),
        selection_window_start=date.fromisoformat(str(selection["selection_window_start"])),
        selection_window_end=date.fromisoformat(str(selection["selection_window_end"])),
        outcome_definition=default_outcome_definition(),
        input_listing_count=int(selection.get("input_listing_count", len(candidates))),
        eligible_listing_count=int(selection.get("eligible_listing_count", len(candidates))),
        priced_symbol_count=int(selection.get("priced_symbol_count", len(candidates))),
        skipped_symbol_count=int(selection.get("skipped_symbol_count", 0)),
        selected_candidates=candidates,
        label_counts=dict(selection.get("label_counts", {})),
        warnings=tuple(str(item) for item in selection.get("warnings", ())),
    )


def _candidate_from_selection(data: dict[str, object]) -> HistoricalCandidate:
    return HistoricalCandidate(
        symbol=str(data["symbol"]).upper(),
        company_name=str(data["company_name"]),
        label=CaseOutcomeLabel(str(data["label"])),
        outcome_anchor_date=date.fromisoformat(str(data["outcome_anchor_date"])),
        inflection_date=date.fromisoformat(str(data["inflection_date"])),
        inflection_method=str(data["inflection_method"]),
        inflection_score=float(data["inflection_score"]),
        outcome_end_date=date.fromisoformat(str(data["outcome_end_date"])),
        forward_return=float(data["forward_return"]),
        max_forward_return=float(data["max_forward_return"]),
        max_drawdown_from_start=float(data["max_drawdown_from_start"]),
        trading_days=int(data["trading_days"]),
        selection_rank=int(data["selection_rank"]),
    )


def _listings_from_selection(
    selection: HistoricalCandidateSelection,
    retrieved_at: datetime,
) -> list[SecurityListing]:
    return [
        SecurityListing(
            symbol=candidate.symbol,
            name=candidate.company_name,
            exchange=None,
            asset_type="stock",
            status="active",
            source="formal_cold_start_selection_summary",
            retrieved_at=retrieved_at,
        )
        for candidate in selection.selected_candidates
    ]


def _enrich_listings_with_sec_ciks(
    listings: Iterable[SecurityListing],
    config: AgentConfig,
) -> tuple[list[SecurityListing], list[str]]:
    listing_list = list(listings)
    missing = [listing for listing in listing_list if not listing.cik]
    if not missing:
        return listing_list, []
    warnings: list[str] = []
    try:
        sec_listings = SecEdgarClient.from_config(config.data_sources).company_tickers_exchange()
    except (DataSourceError, OSError) as exc:
        return listing_list, [f"sec_edgar: could not enrich CIKs for filings: {exc}"]
    cik_by_symbol = {listing.symbol.upper(): listing.cik for listing in sec_listings if listing.cik}
    enriched = [
        SecurityListing(
            symbol=listing.symbol,
            name=listing.name,
            exchange=listing.exchange,
            asset_type=listing.asset_type,
            status=listing.status,
            source=listing.source,
            retrieved_at=listing.retrieved_at,
            cik=listing.cik or cik_by_symbol.get(listing.symbol.upper()),
            ipo_date=listing.ipo_date,
            delisting_date=listing.delisting_date,
        )
        for listing in listing_list
    ]
    unresolved = sum(1 for listing in enriched if not listing.cik)
    if unresolved:
        warnings.append(f"sec_edgar: no CIK mapping for {unresolved} selected/listed symbol(s)")
    return enriched, warnings


def _load_or_fetch_context_documents(
    args,
    candidates: Iterable[HistoricalCandidate],
    listings: Iterable[SecurityListing],
    config: AgentConfig,
    created_at: datetime,
    *,
    paths: ColdStartRunPaths,
) -> ContextFetchResult:
    checkpoint_path = paths.documents_dir / "documents_and_catalysts.json"
    if args.context_mode == "off":
        result = ContextFetchResult({}, {}, ("context-mode=off; filings, news, transcripts, and catalysts were not fetched",))
        _write_context_documents(checkpoint_path, args.run_id, created_at, result)
        print(f"[formal-cold-start] wrote empty context checkpoint: {checkpoint_path}")
        return result
    if checkpoint_path.exists():
        result = _load_context_documents(checkpoint_path)
        print(f"[formal-cold-start] loaded context checkpoint: {checkpoint_path}")
        return result
    result = _fetch_context_documents(args, candidates, listings, config, created_at)
    _write_context_documents(checkpoint_path, args.run_id, created_at, result)
    document_count = sum(len(items) for items in result.documents_by_symbol.values())
    catalyst_count = sum(len(items) for items in result.catalysts_by_symbol.values())
    print(
        "[formal-cold-start] wrote context checkpoint: "
        f"{checkpoint_path} documents={document_count} catalysts={catalyst_count}"
    )
    return result


def _fetch_context_documents(
    args,
    candidates: Iterable[HistoricalCandidate],
    listings: Iterable[SecurityListing],
    config: AgentConfig,
    created_at: datetime,
) -> ContextFetchResult:
    listing_by_symbol = {listing.symbol.upper(): listing for listing in listings}
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]] = {}
    catalysts_by_symbol: dict[str, tuple[Catalyst, ...]] = {}
    warnings: list[str] = []
    sec_client = SecEdgarClient.from_config(config.data_sources)
    finnhub_client = _optional_finnhub_client(config, warnings)
    alpha_client = _optional_alpha_client(config, warnings)
    filing_forms = _parse_csv_values(args.filing_forms)
    for candidate in candidates:
        symbol = candidate.symbol.upper()
        as_of_dates = CaseSlicePlan().as_of_dates(candidate.inflection_date)
        if not as_of_dates:
            continue
        earliest_as_of = as_of_dates[0]
        context_start = earliest_as_of - timedelta(days=max(args.filing_lookback_days, args.news_lookback_days))
        documents: list[DocumentRecord] = []
        catalysts: list[Catalyst] = []
        listing = listing_by_symbol.get(symbol)
        if listing is not None and listing.cik:
            documents.extend(
                _filing_documents_for_candidate(
                    args,
                    sec_client,
                    candidate,
                    listing.cik,
                    context_start=context_start,
                    filing_forms=filing_forms,
                    created_at=created_at,
                    warnings=warnings,
                )
            )
        else:
            warnings.append(f"{symbol}: no SEC CIK available; filing documents skipped")
        news_docs = _news_documents_for_candidate(
            args,
            candidate,
            context_start=context_start,
            created_at=created_at,
            finnhub_client=finnhub_client,
            alpha_client=alpha_client,
            warnings=warnings,
        )
        documents.extend(news_docs)
        documents.extend(
            _transcript_documents_for_candidate(
                args,
                candidate,
                context_start=context_start,
                created_at=created_at,
                finnhub_client=finnhub_client,
                warnings=warnings,
            )
        )
        catalysts.extend(
            catalyst
            for catalyst in (_catalyst_from_news_document(document) for document in news_docs)
            if catalyst is not None
        )
        documents_by_symbol[symbol] = tuple(sorted(documents, key=lambda item: (item.available_date or item.published_date, item.document_id)))
        catalysts_by_symbol[symbol] = tuple(sorted(catalysts, key=lambda item: (item.expected_date, item.name)))
    return ContextFetchResult(documents_by_symbol, catalysts_by_symbol, tuple(warnings))


def _filing_documents_for_candidate(
    args,
    client: SecEdgarClient,
    candidate: HistoricalCandidate,
    cik: str,
    *,
    context_start: date,
    filing_forms: tuple[str, ...],
    created_at: datetime,
    warnings: list[str],
) -> list[DocumentRecord]:
    try:
        filings = client.recent_filings_as_of(cik, candidate.inflection_date)
    except (DataSourceError, OSError) as exc:
        warnings.append(f"{candidate.symbol}: SEC filing metadata unavailable: {exc}")
        return []
    selected = [
        filing
        for filing in filings
        if filing.filing_date >= context_start and filing.form.upper() in filing_forms
    ]
    selected = sorted(selected, key=lambda item: (item.filing_date, item.accession_number), reverse=True)[
        : args.max_filings_per_symbol
    ]
    documents: list[DocumentRecord] = []
    for filing in selected:
        text = f"{filing.form} filed on {filing.filing_date.isoformat()}."
        if not args.skip_filing_text:
            try:
                text = _excerpt(client.filing_document_text(filing), max_chars=args.document_excerpt_chars)
            except (DataSourceError, OSError) as exc:
                warnings.append(f"{candidate.symbol}: SEC filing text unavailable for {filing.accession_number}: {exc}")
        documents.append(
            DocumentRecord(
                document_id=f"sec:{filing.cik}:{filing.accession_number}",
                symbol=candidate.symbol,
                kind=EvidenceKind.FILING,
                title=f"{candidate.company_name} {filing.form} filed {filing.filing_date.isoformat()}",
                text=text,
                source_id=f"sec:{filing.cik}:{filing.accession_number}",
                source_url=filing.source_url,
                published_date=filing.filing_date,
                available_date=filing.filing_date,
                retrieved_at=filing.retrieved_at or created_at,
            )
        )
    return documents


def _news_documents_for_candidate(
    args,
    candidate: HistoricalCandidate,
    *,
    context_start: date,
    created_at: datetime,
    finnhub_client: FinnhubClient | None,
    alpha_client: AlphaVantageClient | None,
    warnings: list[str],
) -> list[DocumentRecord]:
    documents: list[DocumentRecord] = []
    news_start = max(context_start, candidate.inflection_date - timedelta(days=args.news_lookback_days))
    if finnhub_client is not None:
        try:
            raw = finnhub_client.company_news(candidate.symbol, news_start, candidate.inflection_date)
            if isinstance(raw, list):
                documents.extend(
                    document
                    for document in (
                        _finnhub_news_document(candidate.symbol, item, created_at)
                        for item in raw[: args.max_news_per_symbol]
                    )
                    if document is not None
                )
        except (DataSourceError, OSError) as exc:
            warnings.append(f"{candidate.symbol}: Finnhub news unavailable: {exc}")
    if len(documents) < args.max_news_per_symbol and alpha_client is not None:
        try:
            raw = alpha_client.news_sentiment(candidate.symbol, limit=args.max_news_per_symbol)
            feed = raw.get("feed") if isinstance(raw, dict) else None
            if isinstance(feed, list):
                for item in feed:
                    document = _alpha_vantage_news_document(candidate.symbol, item, created_at)
                    if document is None:
                        continue
                    if news_start <= document.published_date <= candidate.inflection_date:
                        documents.append(document)
                    if len(documents) >= args.max_news_per_symbol:
                        break
        except (DataSourceError, OSError) as exc:
            warnings.append(f"{candidate.symbol}: Alpha Vantage news unavailable: {exc}")
    return sorted({document.document_id: document for document in documents}.values(), key=lambda item: item.published_date)[
        : args.max_news_per_symbol
    ]


def _transcript_documents_for_candidate(
    args,
    candidate: HistoricalCandidate,
    *,
    context_start: date,
    created_at: datetime,
    finnhub_client: FinnhubClient | None,
    warnings: list[str],
) -> list[DocumentRecord]:
    if args.max_transcripts_per_symbol < 1 or finnhub_client is None:
        return []
    try:
        raw_list = finnhub_client.transcript_list(candidate.symbol)
    except (DataSourceError, OSError) as exc:
        warnings.append(f"{candidate.symbol}: Finnhub transcript list unavailable: {exc}")
        return []
    items = _transcript_items(raw_list)
    documents: list[DocumentRecord] = []
    for item in items:
        transcript_id = _non_empty_text(item.get("id") or item.get("transcriptId"))
        published = _transcript_published_date(item)
        if transcript_id is None or published is None:
            continue
        if not context_start <= published <= candidate.inflection_date:
            continue
        try:
            raw_transcript = finnhub_client.transcript(transcript_id)
        except (DataSourceError, OSError) as exc:
            warnings.append(f"{candidate.symbol}: Finnhub transcript unavailable for {transcript_id}: {exc}")
            continue
        text = _transcript_text(raw_transcript)
        if text is None:
            warnings.append(f"{candidate.symbol}: transcript {transcript_id} had no text")
            continue
        title = _non_empty_text(item.get("title")) or f"{candidate.symbol} earnings transcript {transcript_id}"
        source_id = f"finnhub:{candidate.symbol.upper()}:transcript:{transcript_id}"
        documents.append(
            DocumentRecord(
                document_id=_document_id(source_id),
                symbol=candidate.symbol,
                kind=EvidenceKind.TRANSCRIPT,
                title=title,
                text=_excerpt(text, max_chars=args.document_excerpt_chars),
                source_id=source_id,
                source_url=str(item.get("url") or f"urn:{source_id}"),
                published_date=published,
                available_date=published,
                retrieved_at=created_at,
            )
        )
        if len(documents) >= args.max_transcripts_per_symbol:
            break
    return documents


def _transcript_items(raw: object) -> list[dict[str, object]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("transcripts", "data", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _transcript_published_date(item: dict[str, object]) -> date | None:
    direct = _date_from_unix_or_iso(item.get("datetime") or item.get("time") or item.get("date") or item.get("publishedDate"))
    if direct is not None:
        return direct
    year = _int_value(item.get("year"))
    quarter = _int_value(item.get("quarter"))
    if isinstance(year, int) and isinstance(quarter, int):
        return _quarter_end_date(year, quarter)
    return None


def _transcript_text(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw
    if not isinstance(raw, dict):
        return None
    for key in ("transcript", "content", "text"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list):
            pieces = []
            for item in value:
                if isinstance(item, str):
                    pieces.append(item)
                elif isinstance(item, dict):
                    speech = item.get("speech") or item.get("content") or item.get("text")
                    if isinstance(speech, str):
                        speaker = item.get("name") or item.get("speaker")
                        prefix = f"{speaker}: " if isinstance(speaker, str) and speaker.strip() else ""
                        pieces.append(prefix + speech)
            joined = "\n".join(piece for piece in pieces if piece.strip())
            if joined.strip():
                return joined
    return None


def _quarter_end_date(year: int, quarter: int) -> date | None:
    month_by_quarter = {1: 3, 2: 6, 3: 9, 4: 12}
    month = month_by_quarter.get(quarter)
    if month is None:
        return None
    day = 31 if month in {3, 12} else 30
    return date(year, month, day)


def _optional_finnhub_client(config: AgentConfig, warnings: list[str]) -> FinnhubClient | None:
    try:
        return FinnhubClient.from_config(config.data_sources)
    except (DataSourceError, OSError) as exc:
        warnings.append(f"finnhub: news source unavailable: {exc}")
        return None


def _optional_alpha_client(config: AgentConfig, warnings: list[str]) -> AlphaVantageClient | None:
    try:
        return AlphaVantageClient.from_config(config.data_sources)
    except (DataSourceError, OSError) as exc:
        warnings.append(f"alpha_vantage: fallback news source unavailable: {exc}")
        return None


def _load_or_fetch_price_histories(
    args,
    listings: Iterable[SecurityListing],
    start_date: date,
    end_date: date,
    *,
    paths: ColdStartRunPaths,
) -> tuple[dict[str, tuple[PriceBar, ...]], list[str]]:
    checkpoint_path = Path(args.price_history_path) if args.price_history_path else paths.prices_dir / "price_histories.json"
    if checkpoint_path.exists():
        bars_by_symbol = _load_price_histories(checkpoint_path)
        print(f"[formal-cold-start] loaded price checkpoint: {checkpoint_path}")
        return bars_by_symbol, []
    price_sources = _parse_price_sources(args)
    print("[formal-cold-start] price source order: " + " -> ".join(price_sources))
    bars_by_symbol, warnings = _fetch_price_histories(
        listings,
        start_date=start_date,
        end_date=end_date,
        max_workers=args.max_workers,
        timeout_seconds=args.price_timeout,
        price_sources=price_sources,
    )
    _write_price_histories(
        checkpoint_path,
        run_id=args.run_id,
        price_sources=price_sources,
        start_date=start_date,
        end_date=end_date,
        bars_by_symbol=bars_by_symbol,
        warnings=warnings,
    )
    print(f"[formal-cold-start] wrote price checkpoint: {checkpoint_path}")
    return bars_by_symbol, warnings


def _fetch_price_histories(
    listings: Iterable[SecurityListing],
    *,
    start_date: date,
    end_date: date,
    max_workers: int,
    timeout_seconds: float,
    price_sources: tuple[str, ...],
) -> tuple[dict[str, tuple[PriceBar, ...]], list[str]]:
    clients = []
    warnings: list[str] = []
    for source in price_sources:
        try:
            clients.append((source, _price_client(source, timeout_seconds)))
        except (DataSourceError, RuntimeError) as exc:
            warnings.append(f"{source}: price source unavailable during initialization: {exc}")
    if not clients:
        raise RuntimeError("no configured price sources are available")
    listing_list = list(listings)
    bars_by_symbol: dict[str, tuple[PriceBar, ...]] = {}
    completed = 0
    client_chain = tuple(clients)
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        futures = {
            executor.submit(_fetch_prices, client_chain, listing.symbol, start_date, end_date): listing.symbol
            for listing in listing_list
        }
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            if result.bars:
                bars_by_symbol[result.symbol] = result.bars
            elif result.error:
                warnings.append(f"{result.symbol}: {result.error}")
            if completed % 25 == 0:
                print(f"[formal-cold-start] price scan progress {completed}/{len(listing_list)}")
    return bars_by_symbol, warnings


def _fetch_prices(
    clients: tuple[tuple[str, object], ...],
    symbol: str,
    start_date: date,
    end_date: date,
) -> PriceFetchResult:
    errors = []
    for source, client in clients:
        try:
            bars = client.daily_prices(symbol, start_date=start_date, end_date=end_date)
        except (DataSourceError, TimeoutError, OSError) as exc:
            errors.append(f"{source}: {exc}")
            continue
        return PriceFetchResult(symbol.upper(), tuple(bars))
    return PriceFetchResult(symbol.upper(), (), "; ".join(errors))


def _price_client(price_source: str, timeout_seconds: float):
    if price_source == "massive":
        return MassiveClient.from_config(AgentConfig().data_sources, transport=TimeoutTextTransport(timeout_seconds))
    if price_source == "stooq":
        return StooqClient.from_config(AgentConfig().data_sources, transport=TimeoutTextTransport(timeout_seconds))
    if price_source == "alpaca":
        return AlpacaPriceClient.from_env(timeout_seconds=timeout_seconds)
    raise RuntimeError(f"unsupported price source: {price_source}")


def _parse_price_sources(args) -> tuple[str, ...]:
    raw = args.price_source or args.price_sources
    sources = tuple(source.strip().lower() for source in raw.split(",") if source.strip())
    allowed = {"massive", "alpaca", "stooq"}
    unknown = [source for source in sources if source not in allowed]
    if unknown:
        raise RuntimeError(f"unsupported price source(s): {', '.join(unknown)}")
    if not sources:
        raise RuntimeError("at least one price source is required")
    return sources


class AlpacaPriceClient:
    """Small Alpaca historical daily-bar adapter used by the formal runner."""

    def __init__(self, key_id: str, secret_key: str, *, timeout_seconds: float) -> None:
        self.key_id = key_id
        self.secret_key = secret_key
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls, *, timeout_seconds: float) -> "AlpacaPriceClient":
        return cls(
            _required_env("ALPACA_API_KEY_ID"),
            _required_env("ALPACA_API_SECRET_KEY"),
            timeout_seconds=timeout_seconds,
        )

    def daily_prices(
        self,
        symbol: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[PriceBar]:
        params = parse.urlencode(
            {
                "timeframe": "1Day",
                "start": f"{start_date.isoformat()}T00:00:00Z",
                "end": f"{end_date.isoformat()}T00:00:00Z",
                "adjustment": "all",
                "limit": "10000",
            }
        )
        url = f"https://data.alpaca.markets/v2/stocks/{parse.quote(symbol.upper(), safe='')}/bars?{params}"
        headers = {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
        }
        data = TimeoutTextTransport(self.timeout_seconds).get_json(url, headers)
        bars = data.get("bars") if isinstance(data, dict) else None
        if not isinstance(bars, list) or not bars:
            raise DataSourceError(f"Alpaca returned no daily prices for {symbol.upper()}")
        retrieved_at = datetime.now(timezone.utc)
        return [_alpaca_bar(symbol, row, retrieved_at) for row in bars if isinstance(row, dict)]


def _alpaca_bar(symbol: str, row: dict[str, object], retrieved_at: datetime) -> PriceBar:
    try:
        close = float(row["c"])
        return PriceBar(
            symbol=symbol.upper(),
            as_of_date=datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00")).date(),
            open=float(row["o"]),
            high=float(row["h"]),
            low=float(row["l"]),
            close=close,
            volume=int(float(row["v"])),
            source="alpaca",
            retrieved_at=retrieved_at,
            adjusted_close=close,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DataSourceError("Alpaca bar contains invalid price data") from exc


class TimeoutTextTransport:
    """Small URL transport with an explicit per-request timeout."""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds

    def get_text(self, url: str, headers: dict[str, str]) -> str:
        req = request.Request(url, headers=dict(headers), method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DataSourceError(f"data source returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise DataSourceError(f"data source request failed: {exc.reason}") from exc

    def get_json(self, url: str, headers: dict[str, str]):
        return _json.loads(self.get_text(url, headers))


def _inflection_dates_for_candidates(
    candidates: Iterable[HistoricalCandidate],
    bars_by_symbol: dict[str, tuple[PriceBar, ...]],
    *,
    window_start: date,
    window_end: date,
) -> dict[str, date]:
    dates: dict[str, date] = {}
    definition = default_outcome_definition()
    for candidate in candidates:
        bars = bars_by_symbol.get(candidate.symbol, ())
        selected = candidate.outcome_anchor_date
        if candidate.label is CaseOutcomeLabel.WINNER:
            for inflection in detect_price_inflections(
                candidate.symbol,
                bars,
                window_start=window_start,
                window_end=window_end,
                min_forward_return=definition.winner_min_return,
            ):
                try:
                    label, _observation = label_price_outcome(candidate.symbol, bars, inflection.inflection_date, definition)
                except Exception:
                    continue
                if label is CaseOutcomeLabel.WINNER:
                    selected = inflection.inflection_date
                    break
        dates[candidate.symbol] = selected
    return dates


def _features_for_candidates(
    candidates: Iterable[HistoricalCandidate],
    bars_by_symbol: dict[str, tuple[PriceBar, ...]],
    created_at: datetime,
) -> dict[str, list[FeatureRecord]]:
    features_by_symbol: dict[str, list[FeatureRecord]] = {}
    plan = CaseSlicePlan()
    for candidate in candidates:
        bars = bars_by_symbol.get(candidate.symbol, ())
        features: list[FeatureRecord] = []
        for as_of_date in plan.as_of_dates(candidate.inflection_date):
            features.extend(normalize_price_features(bars, as_of_date, retrieved_at=created_at))
            features.extend(_classification_proxy_features(candidate.symbol, as_of_date, created_at))
        features_by_symbol[candidate.symbol] = features
    return features_by_symbol


def _classification_proxy_features(symbol: str, as_of_date: date, retrieved_at: datetime) -> list[FeatureRecord]:
    return [
        FeatureRecord(
            name="profile.sector",
            value=None,
            as_of_date=as_of_date,
            source="formal_cold_start_price_scan",
            retrieved_at=retrieved_at,
            data_quality=DataQuality.MISSING,
            source_id=f"formal_cold_start:{symbol}:profile.sector:{as_of_date.isoformat()}",
            unavailable_reason="historical point-in-time sector classification is not available in the current data layer",
        ),
        FeatureRecord(
            name="profile.industry",
            value=None,
            as_of_date=as_of_date,
            source="formal_cold_start_price_scan",
            retrieved_at=retrieved_at,
            data_quality=DataQuality.MISSING,
            source_id=f"formal_cold_start:{symbol}:profile.industry:{as_of_date.isoformat()}",
            unavailable_reason="historical point-in-time industry classification is not available in the current data layer",
        ),
    ]


def _version(config: AgentConfig) -> VersionStamp:
    return VersionStamp(
        prompt_version=config.prompts.prompt_version,
        scoring_version=config.scoring.scoring_version,
        signal_version=config.meta_learning.signal_version,
        model_version=config.prompts.model_version,
        data_pipeline_version=config.pipeline.data_pipeline_version,
        config_version=config.config_version,
    )


def _price_bar_to_dict(bar: PriceBar) -> dict[str, object]:
    return {
        "symbol": bar.symbol,
        "as_of_date": bar.as_of_date.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "source": bar.source,
        "retrieved_at": bar.retrieved_at.isoformat(),
        "adjusted_close": bar.adjusted_close,
    }


def _listing_to_dict(listing: SecurityListing) -> dict[str, object]:
    return {
        "symbol": listing.symbol,
        "name": listing.name,
        "exchange": listing.exchange,
        "asset_type": listing.asset_type,
        "status": listing.status,
        "source": listing.source,
        "retrieved_at": listing.retrieved_at.isoformat(),
        "cik": listing.cik,
        "ipo_date": listing.ipo_date.isoformat() if listing.ipo_date else None,
        "delisting_date": listing.delisting_date.isoformat() if listing.delisting_date else None,
    }


def _price_bar_from_dict(data: dict[str, object]) -> PriceBar:
    return PriceBar(
        symbol=str(data["symbol"]),
        as_of_date=date.fromisoformat(str(data["as_of_date"])),
        open=float(data["open"]),
        high=float(data["high"]),
        low=float(data["low"]),
        close=float(data["close"]),
        volume=int(data["volume"]),
        source=str(data["source"]),
        retrieved_at=datetime.fromisoformat(str(data["retrieved_at"])),
        adjusted_close=float(data["adjusted_close"]) if data.get("adjusted_close") is not None else None,
    )


def _write_price_histories(
    path: Path,
    *,
    run_id: str,
    price_sources: tuple[str, ...],
    start_date: date,
    end_date: date,
    bars_by_symbol: dict[str, tuple[PriceBar, ...]],
    warnings: list[str],
) -> None:
    _write_json(
        path,
        {
            "run_id": run_id,
            "price_sources": list(price_sources),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "priced_symbol_count": len(bars_by_symbol),
            "price_warning_count": len(warnings),
            "warnings": warnings,
            "bars_by_symbol": {
                symbol: [_price_bar_to_dict(bar) for bar in bars]
                for symbol, bars in sorted(bars_by_symbol.items())
            },
        },
    )


def _load_price_histories(path: Path) -> dict[str, tuple[PriceBar, ...]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("bars_by_symbol")
    if not isinstance(raw, dict):
        raise RuntimeError("price checkpoint is missing bars_by_symbol")
    return {
        str(symbol).upper(): tuple(
            _price_bar_from_dict(item)
            for item in bars
            if isinstance(item, dict)
        )
        for symbol, bars in raw.items()
        if isinstance(bars, list)
    }


def _write_context_documents(
    path: Path,
    run_id: str,
    created_at: datetime,
    result: ContextFetchResult,
) -> None:
    _write_json(
        path,
        {
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "document_count": sum(len(items) for items in result.documents_by_symbol.values()),
            "catalyst_count": sum(len(items) for items in result.catalysts_by_symbol.values()),
            "warnings": list(result.warnings),
            "documents_by_symbol": {
                symbol: [_document_to_dict(document) for document in documents]
                for symbol, documents in sorted(result.documents_by_symbol.items())
            },
            "catalysts_by_symbol": {
                symbol: [catalyst.to_dict() for catalyst in catalysts]
                for symbol, catalysts in sorted(result.catalysts_by_symbol.items())
            },
        },
    )


def _load_context_documents(path: Path) -> ContextFetchResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_documents = data.get("documents_by_symbol")
    raw_catalysts = data.get("catalysts_by_symbol")
    if not isinstance(raw_documents, dict) or not isinstance(raw_catalysts, dict):
        raise RuntimeError("context checkpoint is missing document or catalyst maps")
    return ContextFetchResult(
        {
            str(symbol).upper(): tuple(_document_from_dict(item) for item in documents if isinstance(item, dict))
            for symbol, documents in raw_documents.items()
            if isinstance(documents, list)
        },
        {
            str(symbol).upper(): tuple(Catalyst.from_dict(item) for item in catalysts if isinstance(item, dict))
            for symbol, catalysts in raw_catalysts.items()
            if isinstance(catalysts, list)
        },
        tuple(str(item) for item in data.get("warnings", ()) if isinstance(item, str)),
    )


def _document_to_dict(document: DocumentRecord) -> dict[str, object]:
    return {
        "document_id": document.document_id,
        "symbol": document.symbol,
        "kind": document.kind.value,
        "title": document.title,
        "text": document.text,
        "source_id": document.source_id,
        "source_url": document.source_url,
        "published_date": document.published_date.isoformat(),
        "retrieved_at": document.retrieved_at.isoformat(),
        "available_date": document.available_date.isoformat() if document.available_date else None,
    }


def _document_from_dict(data: dict[str, object]) -> DocumentRecord:
    return DocumentRecord(
        document_id=str(data["document_id"]),
        symbol=str(data["symbol"]),
        kind=EvidenceKind(str(data["kind"])),
        title=str(data["title"]),
        text=str(data["text"]),
        source_id=str(data["source_id"]),
        source_url=str(data["source_url"]),
        published_date=date.fromisoformat(str(data["published_date"])),
        retrieved_at=datetime.fromisoformat(str(data["retrieved_at"])),
        available_date=date.fromisoformat(str(data["available_date"])) if data.get("available_date") else None,
    )


def _finnhub_news_document(symbol: str, item: object, retrieved_at: datetime) -> DocumentRecord | None:
    if not isinstance(item, dict):
        return None
    published = _date_from_unix_or_iso(item.get("datetime") or item.get("time"))
    headline = _non_empty(item.get("headline") or item.get("title"))
    if published is None or headline is None:
        return None
    summary = _non_empty(item.get("summary")) or ""
    source_id = f"finnhub:{symbol.upper()}:{item.get('id') or headline[:80]}"
    return DocumentRecord(
        document_id=_document_id(source_id),
        symbol=symbol,
        kind=EvidenceKind.NEWS,
        title=headline,
        text=_excerpt(f"{headline}. {summary}", max_chars=1500),
        source_id=source_id,
        source_url=str(item.get("url") or f"urn:{source_id}"),
        published_date=published,
        available_date=published,
        retrieved_at=retrieved_at,
    )


def _alpha_vantage_news_document(symbol: str, item: object, retrieved_at: datetime) -> DocumentRecord | None:
    if not isinstance(item, dict):
        return None
    published = _date_from_alpha_vantage_time(item.get("time_published"))
    title = _non_empty(item.get("title"))
    if published is None or title is None:
        return None
    summary = _non_empty(item.get("summary")) or ""
    source_id = f"alpha_vantage:{symbol.upper()}:{item.get('url') or title[:80]}"
    return DocumentRecord(
        document_id=_document_id(source_id),
        symbol=symbol,
        kind=EvidenceKind.NEWS,
        title=title,
        text=_excerpt(f"{title}. {summary}", max_chars=1500),
        source_id=source_id,
        source_url=str(item.get("url") or f"urn:{source_id}"),
        published_date=published,
        available_date=published,
        retrieved_at=retrieved_at,
    )


def _catalyst_from_news_document(document: DocumentRecord) -> Catalyst | None:
    text = f"{document.title} {document.text}".lower()
    keywords = (
        "order",
        "contract",
        "customer",
        "backlog",
        "award",
        "supply agreement",
        "partnership",
        "launch",
        "approval",
        "guidance",
    )
    if not any(keyword in text for keyword in keywords):
        return None
    return Catalyst(
        name=document.title[:120],
        expected_date=document.published_date,
        status=CatalystStatus.CONFIRMED,
        evidence=[
            EvidenceItem(
                kind=EvidenceKind.NEWS,
                summary=f"Potential catalyst news: {document.title}",
                as_of_date=document.published_date,
                source_id=document.source_id,
                source_url=document.source_url,
                published_date=document.published_date,
            )
        ],
        actual_date=document.published_date,
    )


def _parse_csv_values(raw: str) -> tuple[str, ...]:
    return tuple(value.strip().upper() for value in raw.split(",") if value.strip())


def _date_from_unix_or_iso(value: object) -> date | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date()
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _date_from_alpha_vantage_time(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 8:
        return None
    try:
        return date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:8]}")
    except ValueError:
        return None


def _int_value(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _non_empty_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _non_empty(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _document_id(source_id: str) -> str:
    return "".join(char if char.isalnum() or char in ".:-_" else "-" for char in source_id)[:180]


def _excerpt(text: str, *, max_chars: int) -> str:
    collapsed = " ".join(str(text).split())
    if max_chars < 20:
        max_chars = 20
    if len(collapsed) <= max_chars:
        return collapsed or "No text available."
    return collapsed[: max_chars - 3].rstrip() + "..."


def _case_to_dict(case) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "label": case.label.value,
        "packet": case.packet.to_dict(),
        "outcome_start_date": case.outcome_start_date.isoformat(),
        "outcome_end_date": case.outcome_end_date.isoformat(),
        "outcome_return": case.outcome_return,
        "matched_group_id": case.matched_group_id,
        "hidden_outcome_summary": case.hidden_outcome_summary,
        "outcome_definition_id": case.outcome_definition_id,
    }


def _load_local_env(path: str = ".env.local") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
