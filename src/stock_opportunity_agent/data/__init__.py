"""Data layer public API and registered data-source providers."""

from stock_opportunity_agent.data.sources import create as create_source
from stock_opportunity_agent.data.sources import get as get_source
from stock_opportunity_agent.data.sources import registered as registered_sources
from stock_opportunity_agent.data.sources.catalog import (
    FREE_DATA_SOURCES,
    DataCapability,
    FreeDataSource,
    source_catalog_by_capability,
)
from stock_opportunity_agent.data.sources.core import (
    DataSourceError,
    FilingMetadata,
    JsonTransport,
    PriceBar,
    UrllibJsonTransport,
    filing_to_evidence,
)
from stock_opportunity_agent.data.sources.alpha_vantage import AlphaVantageClient
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient

__all__ = [
    "AlphaVantageClient",
    "DataCapability",
    "DataSourceError",
    "FREE_DATA_SOURCES",
    "FilingMetadata",
    "FreeDataSource",
    "JsonTransport",
    "PriceBar",
    "SecEdgarClient",
    "UrllibJsonTransport",
    "create_source",
    "filing_to_evidence",
    "get_source",
    "registered_sources",
    "source_catalog_by_capability",
]
