"""LLM research boundaries."""

from stock_opportunity_agent.research.cold_start import (
    BlindCaseAnalysis,
    BlindCaseResearcher,
    HeuristicBlindCaseResearcher,
    OpenAIBlindCaseResearcher,
)
from stock_opportunity_agent.research.inflection_discovery import (
    CachedInflectionResearcher,
    CompositeInflectionResearcher,
    FactorInflectionResearcher,
    HeuristicInflectionResearcher,
    InflectionResearchResult,
    InflectionResearcher,
    OpenAIWebInflectionResearcher,
)
from stock_opportunity_agent.research.playbooks import (
    HeuristicSurgePlaybookSynthesizer,
    OpenAISurgePlaybookSynthesizer,
    PlaybookQuestion,
    PlaybookReasoningStep,
    SurgePlaybookSynthesis,
    SurgePlaybookSynthesizer,
    SurgeResearchPlaybook,
)

__all__ = [
    "BlindCaseAnalysis",
    "BlindCaseResearcher",
    "CachedInflectionResearcher",
    "CompositeInflectionResearcher",
    "FactorInflectionResearcher",
    "HeuristicBlindCaseResearcher",
    "HeuristicInflectionResearcher",
    "HeuristicSurgePlaybookSynthesizer",
    "InflectionResearchResult",
    "InflectionResearcher",
    "OpenAIBlindCaseResearcher",
    "OpenAISurgePlaybookSynthesizer",
    "OpenAIWebInflectionResearcher",
    "PlaybookQuestion",
    "PlaybookReasoningStep",
    "SurgePlaybookSynthesis",
    "SurgePlaybookSynthesizer",
    "SurgeResearchPlaybook",
]
