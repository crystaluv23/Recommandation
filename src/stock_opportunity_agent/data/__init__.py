"""Data layer public API and registered data-source providers."""

from stock_opportunity_agent.data.sources import create as create_source
from stock_opportunity_agent.data.sources import get as get_source
from stock_opportunity_agent.data.sources import registered as registered_sources
from stock_opportunity_agent.data.sources.catalog import (
    DATA_CAPABILITY_PLAN,
    FREE_DATA_SOURCES,
    CapabilityPlan,
    DataCapability,
    FreeDataSource,
    select_source_for_capability,
    source_catalog_by_capability,
    source_plan_by_capability,
)
from stock_opportunity_agent.data.sources.core import (
    DataSourceError,
    FilingMetadata,
    JsonTransport,
    PostJsonTransport,
    PriceBar,
    SecurityListing,
    TextTransport,
    UrllibJsonTransport,
    filing_to_evidence,
)
from stock_opportunity_agent.data.sources.state import (
    DEFAULT_SOURCE_QUOTAS,
    BudgetDecision,
    CachedRawResponse,
    DataQuotaDeferred,
    ManagedHttpTransport,
    RawCacheKey,
    RawDataCache,
    RequestLedger,
    RequestLedgerEntry,
    RequestStatus,
    SourceBudget,
    SourceQuota,
)
from stock_opportunity_agent.data.sources.alpha_vantage import AlphaVantageClient
from stock_opportunity_agent.data.sources.finnhub import FinnhubClient
from stock_opportunity_agent.data.sources.fred import FredClient
from stock_opportunity_agent.data.sources.openfigi import OpenFigiClient
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.data.sources.stooq import StooqClient

__all__ = [
    "AlphaVantageClient",
    "CapabilityPlan",
    "DATA_CAPABILITY_PLAN",
    "DEFAULT_SOURCE_QUOTAS",
    "BudgetDecision",
    "CachedRawResponse",
    "DataCapability",
    "DataQuotaDeferred",
    "DataSourceError",
    "FREE_DATA_SOURCES",
    "FinnhubClient",
    "FilingMetadata",
    "FreeDataSource",
    "FredClient",
    "JsonTransport",
    "ManagedHttpTransport",
    "OpenFigiClient",
    "PostJsonTransport",
    "PriceBar",
    "RawCacheKey",
    "RawDataCache",
    "RequestLedger",
    "RequestLedgerEntry",
    "RequestStatus",
    "SecEdgarClient",
    "SecurityListing",
    "SourceBudget",
    "SourceQuota",
    "StooqClient",
    "TextTransport",
    "UrllibJsonTransport",
    "create_source",
    "filing_to_evidence",
    "get_source",
    "registered_sources",
    "select_source_for_capability",
    "source_catalog_by_capability",
    "source_plan_by_capability",
]
