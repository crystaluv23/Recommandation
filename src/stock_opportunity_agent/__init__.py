"""Stock opportunity discovery agent core package."""

from stock_opportunity_agent.config import AgentConfig, load_config
from stock_opportunity_agent.cases import CaseOutcomeLabel, HistoricalCase
from stock_opportunity_agent.models import (
    AsOfContext,
    Catalyst,
    CompanyProfile,
    DecisionRecord,
    EvidenceItem,
    ExperimentRecord,
    FeatureRecord,
    ResearchPacket,
    ReviewRecord,
    ScoreCard,
    SegmentAssessment,
    SignalDefinition,
    Thesis,
    ThemeMap,
    TickerRef,
    VersionStamp,
    WatchlistEntry,
)
from stock_opportunity_agent.orchestration import ColdStartRunOutput, run_cold_start_case_learning

__all__ = [
    "AgentConfig",
    "AsOfContext",
    "Catalyst",
    "CaseOutcomeLabel",
    "CompanyProfile",
    "ColdStartRunOutput",
    "DecisionRecord",
    "EvidenceItem",
    "ExperimentRecord",
    "FeatureRecord",
    "HistoricalCase",
    "ResearchPacket",
    "ReviewRecord",
    "ScoreCard",
    "SegmentAssessment",
    "SignalDefinition",
    "Thesis",
    "ThemeMap",
    "TickerRef",
    "VersionStamp",
    "WatchlistEntry",
    "load_config",
    "run_cold_start_case_learning",
]
