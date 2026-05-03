"""Historical case learning public API."""

from stock_opportunity_agent.cases.learning import (
    ColdStartLearningResult,
    HistoricalCase,
    PreSurgeSignalLogic,
    SignalCaseStats,
    learn_pre_surge_signal_logic,
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

__all__ = [
    "CaseOutcomeLabel",
    "CaseSlicePlan",
    "ColdStartLearningResult",
    "ControlMatchCriteria",
    "HistoricalCase",
    "MatchedControlSet",
    "OutcomeDefinition",
    "OutcomeObservation",
    "PreSurgeSignalLogic",
    "SignalCaseStats",
    "apply_matched_groups",
    "build_historical_cases_from_packets",
    "default_outcome_definition",
    "label_price_outcome",
    "learn_pre_surge_signal_logic",
    "match_controls",
    "observe_price_outcome",
]
