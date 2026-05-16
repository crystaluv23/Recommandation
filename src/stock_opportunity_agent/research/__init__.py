"""LLM research boundaries."""

from stock_opportunity_agent.research.cold_start import (
    BlindCaseAnalysis,
    BlindCaseResearcher,
    HeuristicBlindCaseResearcher,
    OpenAIBlindCaseResearcher,
)
from stock_opportunity_agent.research.evidence_acquisition import (
    ContextCoverageGateResult,
    ContextCoverageReport,
    EvidenceAcquisitionRequest,
    EvidenceAcquisitionResult,
    OpenAIWebEvidenceResearcher,
    apply_context_coverage_gate,
    assess_context_coverage,
    build_web_context_queries,
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
    "ContextCoverageGateResult",
    "ContextCoverageReport",
    "EvidenceAcquisitionRequest",
    "EvidenceAcquisitionResult",
    "FactorInflectionResearcher",
    "HeuristicBlindCaseResearcher",
    "HeuristicInflectionResearcher",
    "HeuristicSurgePlaybookSynthesizer",
    "InflectionResearchResult",
    "InflectionResearcher",
    "OpenAIBlindCaseResearcher",
    "OpenAIWebEvidenceResearcher",
    "OpenAISurgePlaybookSynthesizer",
    "OpenAIWebInflectionResearcher",
    "PlaybookQuestion",
    "PlaybookReasoningStep",
    "SurgePlaybookSynthesis",
    "SurgePlaybookSynthesizer",
    "SurgeResearchPlaybook",
    "apply_context_coverage_gate",
    "assess_context_coverage",
    "build_web_context_queries",
]
