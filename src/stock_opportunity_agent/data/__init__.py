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
from stock_opportunity_agent.data.documents import (
    DocumentChunk,
    DocumentRecord,
    DocumentStore,
    chunk_document_text,
    documents_as_of,
    documents_to_evidence,
)
from stock_opportunity_agent.data.point_in_time import (
    build_research_packet,
    catalysts_as_of,
    feature_records_as_of,
    features_to_evidence,
    latest_features_by_name,
)
from stock_opportunity_agent.data.sources.alpha_vantage import AlphaVantageClient
from stock_opportunity_agent.data.sources.finnhub import FinnhubClient
from stock_opportunity_agent.data.sources.fred import FredClient
from stock_opportunity_agent.data.sources.massive import MassiveClient
from stock_opportunity_agent.data.sources.openfigi import OpenFigiClient
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.data.sources.stooq import StooqClient
from stock_opportunity_agent.data.structured import (
    ALPHA_VANTAGE_OVERVIEW_FEATURES,
    PRICE_FEATURE_WINDOWS,
    SEC_COMPANY_FACT_FEATURE_TAGS,
    company_profile_from_features,
    normalize_alpha_vantage_overview,
    normalize_price_features,
    normalize_sec_company_facts,
)

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
    "DocumentChunk",
    "DocumentRecord",
    "DocumentStore",
    "FREE_DATA_SOURCES",
    "FinnhubClient",
    "FilingMetadata",
    "FreeDataSource",
    "FredClient",
    "JsonTransport",
    "ManagedHttpTransport",
    "MassiveClient",
    "OpenFigiClient",
    "PostJsonTransport",
    "PriceBar",
    "PRICE_FEATURE_WINDOWS",
    "RawCacheKey",
    "RawDataCache",
    "RequestLedger",
    "RequestLedgerEntry",
    "RequestStatus",
    "SecEdgarClient",
    "SecurityListing",
    "SEC_COMPANY_FACT_FEATURE_TAGS",
    "SourceBudget",
    "SourceQuota",
    "StooqClient",
    "TextTransport",
    "UrllibJsonTransport",
    "ALPHA_VANTAGE_OVERVIEW_FEATURES",
    "build_research_packet",
    "catalysts_as_of",
    "chunk_document_text",
    "company_profile_from_features",
    "create_source",
    "documents_as_of",
    "documents_to_evidence",
    "feature_records_as_of",
    "features_to_evidence",
    "filing_to_evidence",
    "get_source",
    "latest_features_by_name",
    "normalize_alpha_vantage_overview",
    "normalize_price_features",
    "normalize_sec_company_facts",
    "registered_sources",
    "select_source_for_capability",
    "source_catalog_by_capability",
    "source_plan_by_capability",
]
