"""Catalog and selection rules for free or free-key data sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class DataCapability(str, Enum):
    """Data needs that can be served by external or public data sources."""

    UNIVERSE = "universe"
    PRICE_DAILY = "price_daily"
    COMPANY_PROFILE = "company_profile"
    FINANCIAL_STATEMENTS = "financial_statements"
    VALUATION = "valuation"
    FILINGS = "filings"
    FILING_DOCUMENTS = "filing_documents"
    NEWS = "news"
    TRANSCRIPTS = "transcripts"
    ANALYST_ESTIMATES = "analyst_estimates"
    EARNINGS_CALENDAR = "earnings_calendar"
    CORPORATE_ACTIONS = "corporate_actions"
    SECTOR_BENCHMARK = "sector_benchmark"
    MACRO_SERIES = "macro_series"
    IDENTIFIER_MAPPING = "identifier_mapping"


@dataclass(frozen=True)
class CapabilityPlan:
    """Preferred source order and caveat for one data capability."""

    capability: DataCapability
    preferred_sources: tuple[str, ...]
    reason: str
    caveat: str


@dataclass(frozen=True)
class FreeDataSource:
    """Current candidate source and what it can cover in the MVP."""

    key: str
    name: str
    base_url: str
    authentication: str
    capabilities: tuple[DataCapability, ...]
    primary_for: tuple[DataCapability, ...]
    mvp_role: str
    caveat: str
    request_limit: str = "unknown"
    adapter_status: str = "candidate"


FREE_DATA_SOURCES: tuple[FreeDataSource, ...] = (
    FreeDataSource(
        key="sec_edgar",
        name="SEC EDGAR",
        base_url="https://data.sec.gov and https://www.sec.gov",
        authentication="none",
        capabilities=(
            DataCapability.UNIVERSE,
            DataCapability.COMPANY_PROFILE,
            DataCapability.FINANCIAL_STATEMENTS,
            DataCapability.FILINGS,
            DataCapability.FILING_DOCUMENTS,
        ),
        primary_for=(
            DataCapability.UNIVERSE,
            DataCapability.COMPANY_PROFILE,
            DataCapability.FINANCIAL_STATEMENTS,
            DataCapability.FILINGS,
            DataCapability.FILING_DOCUMENTS,
        ),
        mvp_role="Authority source for CIK/ticker mappings, public-company filings, and XBRL company facts.",
        caveat="Requires compliant user-agent; no prices, news, transcripts, analyst estimates, or market sentiment.",
        request_limit="10 requests/second fair-access ceiling",
        adapter_status="implemented",
    ),
    FreeDataSource(
        key="stooq",
        name="Stooq",
        base_url="https://stooq.com/q/d/l/",
        authentication="none",
        capabilities=(DataCapability.PRICE_DAILY,),
        primary_for=(DataCapability.PRICE_DAILY,),
        mvp_role="No-key fallback for longer daily OHLCV history when licensed real-time data is unnecessary.",
        caveat="CSV download source rather than a formal vendor API; use for research/backtest inputs with provenance.",
        request_limit="not published",
        adapter_status="implemented",
    ),
    FreeDataSource(
        key="alpha_vantage",
        name="Alpha Vantage",
        base_url="https://www.alphavantage.co/query",
        authentication="free API key",
        capabilities=(
            DataCapability.UNIVERSE,
            DataCapability.PRICE_DAILY,
            DataCapability.COMPANY_PROFILE,
            DataCapability.FINANCIAL_STATEMENTS,
            DataCapability.VALUATION,
            DataCapability.NEWS,
            DataCapability.TRANSCRIPTS,
            DataCapability.ANALYST_ESTIMATES,
            DataCapability.EARNINGS_CALENDAR,
            DataCapability.CORPORATE_ACTIONS,
            DataCapability.SECTOR_BENCHMARK,
            DataCapability.MACRO_SERIES,
        ),
        primary_for=(
            DataCapability.VALUATION,
            DataCapability.NEWS,
            DataCapability.TRANSCRIPTS,
            DataCapability.ANALYST_ESTIMATES,
            DataCapability.EARNINGS_CALENDAR,
            DataCapability.CORPORATE_ACTIONS,
            DataCapability.SECTOR_BENCHMARK,
        ),
        mvp_role="Broad free-key source for compact price, profile, valuation, news, transcripts, estimates, and events.",
        caveat="Free tier is too small for broad scans; use only behind caching and prefer authority sources where available.",
        request_limit="25 requests/day on standard free key",
        adapter_status="implemented",
    ),
    FreeDataSource(
        key="fred",
        name="FRED",
        base_url="https://api.stlouisfed.org/fred",
        authentication="free API key",
        capabilities=(DataCapability.MACRO_SERIES, DataCapability.SECTOR_BENCHMARK),
        primary_for=(DataCapability.MACRO_SERIES,),
        mvp_role="Authority source for macro, rates, inflation, industrial, and other economic context series.",
        caveat="Not company-specific; requires explicit series IDs and vintage discipline for historical research.",
        request_limit="key required; provider-published endpoint limits should be observed",
        adapter_status="implemented",
    ),
    FreeDataSource(
        key="openfigi",
        name="OpenFIGI",
        base_url="https://api.openfigi.com",
        authentication="none or free API key",
        capabilities=(DataCapability.IDENTIFIER_MAPPING,),
        primary_for=(DataCapability.IDENTIFIER_MAPPING,),
        mvp_role="Identifier hygiene for ticker, FIGI, exchange, and security-type mapping.",
        caveat="Identifier mapping only; not a source of financial, price, or thesis evidence.",
        request_limit="25/min without key; higher with free key",
        adapter_status="implemented",
    ),
    FreeDataSource(
        key="finnhub",
        name="Finnhub",
        base_url="https://finnhub.io/api/v1",
        authentication="free API key",
        capabilities=(
            DataCapability.PRICE_DAILY,
            DataCapability.COMPANY_PROFILE,
            DataCapability.FINANCIAL_STATEMENTS,
            DataCapability.VALUATION,
            DataCapability.FILINGS,
            DataCapability.NEWS,
            DataCapability.TRANSCRIPTS,
            DataCapability.ANALYST_ESTIMATES,
            DataCapability.EARNINGS_CALENDAR,
        ),
        primary_for=(),
        mvp_role="Fallback source for company news, metrics, estimates, and transcripts when Alpha Vantage is exhausted.",
        caveat="Free endpoint availability can vary; keep raw responses behind adapter and cache aggressively.",
        request_limit="free-key tier; verify current account limits before broad scans",
        adapter_status="implemented",
    ),
    FreeDataSource(
        key="fmp",
        name="Financial Modeling Prep",
        base_url="https://financialmodelingprep.com",
        authentication="free API key",
        capabilities=(
            DataCapability.PRICE_DAILY,
            DataCapability.COMPANY_PROFILE,
            DataCapability.FINANCIAL_STATEMENTS,
            DataCapability.VALUATION,
            DataCapability.NEWS,
            DataCapability.EARNINGS_CALENDAR,
        ),
        primary_for=(),
        mvp_role="Candidate fallback if Alpha Vantage coverage is insufficient.",
        caveat="Free plan and redistribution terms should be checked before depending on it in reports.",
        request_limit="free plan currently advertises 250 calls/day",
    ),
    FreeDataSource(
        key="marketstack",
        name="Marketstack",
        base_url="https://api.marketstack.com",
        authentication="free API key",
        capabilities=(DataCapability.PRICE_DAILY, DataCapability.COMPANY_PROFILE),
        primary_for=(),
        mvp_role="Candidate fallback for end-of-day prices and ticker metadata.",
        caveat="Free plan has low monthly request volume and limited history.",
        request_limit="free plan currently advertises 100 monthly requests",
    ),
    FreeDataSource(
        key="nasdaq_data_link",
        name="Nasdaq Data Link",
        base_url="https://data.nasdaq.com",
        authentication="free API key",
        capabilities=(DataCapability.MACRO_SERIES, DataCapability.SECTOR_BENCHMARK),
        primary_for=(),
        mvp_role="Candidate for open economic and alternative datasets not covered by FRED.",
        caveat="Most market datasets are premium; do not assume US equity fundamentals are free.",
        request_limit="dataset-dependent",
    ),
)


DATA_CAPABILITY_PLAN: tuple[CapabilityPlan, ...] = (
    CapabilityPlan(
        DataCapability.UNIVERSE,
        ("sec_edgar", "alpha_vantage", "openfigi"),
        "Use SEC ticker/exchange mappings as the authority source; Alpha Vantage listing status can add active/delisted state.",
        "SEC mappings include filers, not every tradable share class or ETF.",
    ),
    CapabilityPlan(
        DataCapability.PRICE_DAILY,
        ("stooq", "alpha_vantage", "finnhub", "fmp", "marketstack"),
        "Use no-key historical daily data first, then free-key APIs for recent or vendor-confirmed bars.",
        "Real-time and delayed exchange data often require licensed paid access.",
    ),
    CapabilityPlan(
        DataCapability.COMPANY_PROFILE,
        ("sec_edgar", "alpha_vantage", "finnhub", "fmp"),
        "Use SEC for identity and filings context; use free-key APIs for sector, industry, market cap, and ratios.",
        "Provider sector/industry taxonomies differ and must be normalized later.",
    ),
    CapabilityPlan(
        DataCapability.FINANCIAL_STATEMENTS,
        ("sec_edgar", "alpha_vantage", "finnhub", "fmp"),
        "Use SEC XBRL company facts as authority; vendor statements are convenience fallbacks.",
        "XBRL facts need normalization before scanner/scoring consumption.",
    ),
    CapabilityPlan(
        DataCapability.VALUATION,
        ("alpha_vantage", "finnhub", "fmp"),
        "Use vendor overview/metrics as raw valuation inputs until structured feature normalization exists.",
        "Valuation ratios are derived and may not be point-in-time unless cached at retrieval.",
    ),
    CapabilityPlan(
        DataCapability.FILINGS,
        ("sec_edgar", "finnhub"),
        "Use SEC filings metadata as authority and other providers only as convenience mirrors.",
        "Historical filing availability must be filtered by filing date and retrieval metadata.",
    ),
    CapabilityPlan(
        DataCapability.FILING_DOCUMENTS,
        ("sec_edgar",),
        "Use direct SEC archive URLs for source documents.",
        "Document parsing/chunking belongs in the document layer, not in vendor clients.",
    ),
    CapabilityPlan(
        DataCapability.NEWS,
        ("alpha_vantage", "finnhub", "fmp"),
        "Use Alpha Vantage and Finnhub as source-linked company news feeds for research packets.",
        "News licensing and redistribution terms must be respected in reports.",
    ),
    CapabilityPlan(
        DataCapability.TRANSCRIPTS,
        ("alpha_vantage", "finnhub"),
        "Use free-key transcript endpoints when available and cache by symbol/quarter.",
        "Coverage varies by provider and may change by plan.",
    ),
    CapabilityPlan(
        DataCapability.ANALYST_ESTIMATES,
        ("alpha_vantage", "finnhub"),
        "Use estimates only when explicitly available; missing estimates are not neutral evidence.",
        "Estimate histories can be plan-limited and require as-of snapshots.",
    ),
    CapabilityPlan(
        DataCapability.EARNINGS_CALENDAR,
        ("alpha_vantage", "finnhub", "fmp"),
        "Use calendar endpoints for near-term catalyst scheduling.",
        "Dates can change; cache retrieval time and refresh during daily monitor runs.",
    ),
    CapabilityPlan(
        DataCapability.CORPORATE_ACTIONS,
        ("alpha_vantage", "fmp"),
        "Use dividends and splits to adjust price/valuation features later.",
        "Corporate action handling must be explicit before adjusted-return features are used.",
    ),
    CapabilityPlan(
        DataCapability.SECTOR_BENCHMARK,
        ("alpha_vantage", "fred", "nasdaq_data_link"),
        "Use ETF/sector benchmark holdings and macro context to frame industry-chain moves.",
        "Benchmark selection is a research-design choice and should be confirmed before scoring.",
    ),
    CapabilityPlan(
        DataCapability.MACRO_SERIES,
        ("fred", "alpha_vantage", "nasdaq_data_link"),
        "Use FRED as the authority source for macro and rates series.",
        "Historical research should prefer vintage-aware series when revisions matter.",
    ),
    CapabilityPlan(
        DataCapability.IDENTIFIER_MAPPING,
        ("openfigi", "sec_edgar"),
        "Use OpenFIGI for FIGI/exchange/security-type hygiene and SEC for CIK mapping.",
        "Identifier matches can be one-to-many and need human-reviewable provenance.",
    ),
)


def source_catalog_by_capability(capability: DataCapability) -> tuple[FreeDataSource, ...]:
    """Return candidate free sources that advertise a capability."""

    return tuple(source for source in FREE_DATA_SOURCES if capability in source.capabilities)


def source_plan_by_capability(capability: DataCapability) -> CapabilityPlan:
    """Return the preferred source order for a capability."""

    for plan in DATA_CAPABILITY_PLAN:
        if plan.capability is capability:
            return plan
    raise ValueError(f"missing data capability plan: {capability.value}")


def select_source_for_capability(capability: DataCapability, available_sources: Iterable[str]) -> str:
    """Return the first available source key for a capability using the canonical preference order."""

    available = set(available_sources)
    for source_key in source_plan_by_capability(capability).preferred_sources:
        if source_key in available:
            return source_key
    raise ValueError(f"no available source for capability: {capability.value}")
