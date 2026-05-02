"""Catalog of currently viable free or free-key market data sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DataCapability(str, Enum):
    """Data needs that can be served by external APIs."""

    PRICE_DAILY = "price_daily"
    COMPANY_PROFILE = "company_profile"
    FINANCIAL_STATEMENTS = "financial_statements"
    FILINGS = "filings"
    NEWS = "news"
    TRANSCRIPTS = "transcripts"
    ANALYST_ESTIMATES = "analyst_estimates"


@dataclass(frozen=True)
class FreeDataSource:
    """Current candidate source and what it can cover in the MVP."""

    name: str
    base_url: str
    authentication: str
    capabilities: tuple[DataCapability, ...]
    mvp_role: str
    caveat: str


FREE_DATA_SOURCES: tuple[FreeDataSource, ...] = (
    FreeDataSource(
        name="SEC EDGAR",
        base_url="https://data.sec.gov",
        authentication="none",
        capabilities=(DataCapability.FILINGS, DataCapability.FINANCIAL_STATEMENTS, DataCapability.COMPANY_PROFILE),
        mvp_role="Primary free source for filings metadata and XBRL company facts.",
        caveat="Requires compliant user-agent; no prices, news, transcripts, or analyst estimates.",
    ),
    FreeDataSource(
        name="Alpha Vantage",
        base_url="https://www.alphavantage.co/query",
        authentication="free API key",
        capabilities=(
            DataCapability.PRICE_DAILY,
            DataCapability.COMPANY_PROFILE,
            DataCapability.FINANCIAL_STATEMENTS,
            DataCapability.NEWS,
            DataCapability.TRANSCRIPTS,
            DataCapability.ANALYST_ESTIMATES,
        ),
        mvp_role="Primary free-key source for compact price, overview, news, and selected fundamentals.",
        caveat="Free tier has limits and some history/depth is premium; cache responses before broad scans.",
    ),
    FreeDataSource(
        name="Financial Modeling Prep",
        base_url="https://financialmodelingprep.com",
        authentication="free API key",
        capabilities=(
            DataCapability.PRICE_DAILY,
            DataCapability.COMPANY_PROFILE,
            DataCapability.FINANCIAL_STATEMENTS,
            DataCapability.NEWS,
        ),
        mvp_role="Candidate fallback if Alpha Vantage coverage is insufficient.",
        caveat="Free plan is limited and licensing/display terms should be checked before report distribution.",
    ),
    FreeDataSource(
        name="Marketstack",
        base_url="https://api.marketstack.com",
        authentication="free API key",
        capabilities=(DataCapability.PRICE_DAILY, DataCapability.COMPANY_PROFILE),
        mvp_role="Candidate fallback for end-of-day prices and ticker metadata.",
        caveat="Free plan has low monthly request volume and limited history.",
    ),
    FreeDataSource(
        name="Finnhub",
        base_url="https://finnhub.io",
        authentication="free API key",
        capabilities=(
            DataCapability.PRICE_DAILY,
            DataCapability.COMPANY_PROFILE,
            DataCapability.NEWS,
            DataCapability.FINANCIAL_STATEMENTS,
            DataCapability.ANALYST_ESTIMATES,
            DataCapability.TRANSCRIPTS,
        ),
        mvp_role="Candidate fallback for real-time-ish market data, news, estimates, and transcripts.",
        caveat="Free endpoints and rate limits can differ by account; keep behind an adapter.",
    ),
)


def source_catalog_by_capability(capability: DataCapability) -> tuple[FreeDataSource, ...]:
    """Return candidate free sources that advertise a capability."""

    return tuple(source for source in FREE_DATA_SOURCES if capability in source.capabilities)
