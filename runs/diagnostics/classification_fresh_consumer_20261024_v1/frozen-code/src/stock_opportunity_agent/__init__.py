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
from stock_opportunity_agent.research import (
    InformationScheme,
    RalphLoopResult,
    SurgePlaybookSynthesis,
    SurgeResearchPlaybook,
)
from stock_opportunity_agent.themes import ThemeMapBuildResult, build_cold_start_theme_maps

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
    "InformationScheme",
    "RalphLoopResult",
    "ResearchPacket",
    "ReviewRecord",
    "ScoreCard",
    "SegmentAssessment",
    "SignalDefinition",
    "SurgePlaybookSynthesis",
    "SurgeResearchPlaybook",
    "Thesis",
    "ThemeMap",
    "ThemeMapBuildResult",
    "TickerRef",
    "VersionStamp",
    "WatchlistEntry",
    "build_cold_start_theme_maps",
    "load_config",
    "run_cold_start_case_learning",
]
