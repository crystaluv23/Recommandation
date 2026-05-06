"""Historical case learning public API."""

from stock_opportunity_agent.cases.learning import (
    ColdStartLearningResult,
    HistoricalCase,
    PreSurgeSignalLogic,
    SignalCaseStats,
    learn_pre_surge_signal_logic,
)
from stock_opportunity_agent.cases.inflections import (
    InflectionCandidate,
    detect_price_inflections,
    fallback_inflection_from_case,
)
from stock_opportunity_agent.cases.matching import (
    ControlMatchCriteria,
    MatchedControlSet,
    apply_matched_groups,
    match_controls,
)
from stock_opportunity_agent.cases.outcomes import (
    CaseOutcomeLabel,
    OutcomeDefinition,
    OutcomeObservation,
    default_outcome_definition,
    label_price_outcome,
    observe_price_outcome,
)
from stock_opportunity_agent.cases.packets import CaseSlicePlan, build_historical_cases_from_packets
from stock_opportunity_agent.cases.selection import (
    HistoricalCandidate,
    HistoricalCandidateSelection,
    eligible_common_stock_listings,
    matured_selection_window,
    select_historical_candidates,
)

__all__ = [
    "CaseOutcomeLabel",
    "CaseSlicePlan",
    "ColdStartLearningResult",
    "ControlMatchCriteria",
    "HistoricalCase",
    "HistoricalCandidate",
    "HistoricalCandidateSelection",
    "InflectionCandidate",
    "MatchedControlSet",
    "OutcomeDefinition",
    "OutcomeObservation",
    "PreSurgeSignalLogic",
    "SignalCaseStats",
    "apply_matched_groups",
    "build_historical_cases_from_packets",
    "default_outcome_definition",
    "detect_price_inflections",
    "eligible_common_stock_listings",
    "fallback_inflection_from_case",
    "label_price_outcome",
    "learn_pre_surge_signal_logic",
    "match_controls",
    "matured_selection_window",
    "observe_price_outcome",
    "select_historical_candidates",
]
