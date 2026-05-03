"""Matched-control construction for historical case learning."""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable

from stock_opportunity_agent.cases.learning import HistoricalCase
from stock_opportunity_agent.cases.outcomes import CaseOutcomeLabel
from stock_opportunity_agent.models import DataQuality, FeatureRecord, ValidationError


@dataclass(frozen=True)
class ControlMatchCriteria:
    """Versioned criteria for matching winner cases to controls.

    The defaults are intentionally conservative and transparent. They can be
    replaced by a future user-confirmed definition without changing cold-start
    learning or LLM analysis.
    """

    criteria_id: str = "control-match-v0.1"
    same_sector_required: bool = True
    max_market_cap_log_gap: float = 1.25
    max_prior_return_gap: float = 0.35
    max_controls_per_winner: int = 3

    def __post_init__(self) -> None:
        if not self.criteria_id.strip():
            raise ValidationError("criteria_id must not be empty")
        if self.max_market_cap_log_gap < 0:
            raise ValidationError("max_market_cap_log_gap cannot be negative")
        if self.max_prior_return_gap < 0:
            raise ValidationError("max_prior_return_gap cannot be negative")
        if self.max_controls_per_winner < 1:
            raise ValidationError("max_controls_per_winner must be at least 1")


@dataclass(frozen=True)
class MatchedControlSet:
    """Controls selected for one winner case."""

    winner_case_id: str
    control_case_ids: tuple[str, ...]
    criteria_id: str
    warnings: tuple[str, ...]


def match_controls(
    cases: Iterable[HistoricalCase],
    criteria: ControlMatchCriteria | None = None,
) -> tuple[MatchedControlSet, ...]:
    """Match each winner to neutral controls using point-in-time packet fields."""

    active_criteria = criteria or ControlMatchCriteria()
    case_list = list(cases)
    winners = [case for case in case_list if case.label is CaseOutcomeLabel.WINNER]
    controls = [case for case in case_list if case.label is CaseOutcomeLabel.CONTROL]
    matched: list[MatchedControlSet] = []
    for winner in winners:
        ranked = sorted(
            (
                (_match_distance(winner, control, active_criteria), control)
                for control in controls
                if _eligible_control(winner, control, active_criteria)
            ),
            key=lambda item: (item[0], item[1].case_id),
        )
        selected = tuple(control.case_id for _distance, control in ranked[: active_criteria.max_controls_per_winner])
        warnings: list[str] = []
        if not selected:
            warnings.append(f"No matched controls found for {winner.case_id}.")
        matched.append(
            MatchedControlSet(
                winner_case_id=winner.case_id,
                control_case_ids=selected,
                criteria_id=active_criteria.criteria_id,
                warnings=tuple(warnings),
            )
        )
    return tuple(matched)


def apply_matched_groups(
    cases: Iterable[HistoricalCase],
    matches: Iterable[MatchedControlSet],
) -> tuple[HistoricalCase, ...]:
    """Return cases with matched group ids derived from control matches."""

    case_by_id = {case.case_id: case for case in cases}
    group_by_case: dict[str, str] = {}
    for match in matches:
        group_id = f"match:{match.winner_case_id}"
        group_by_case[match.winner_case_id] = group_id
        for control_id in match.control_case_ids:
            group_by_case.setdefault(control_id, group_id)
    return tuple(
        HistoricalCase(
            case_id=case.case_id,
            label=case.label,
            packet=case.packet,
            outcome_start_date=case.outcome_start_date,
            outcome_end_date=case.outcome_end_date,
            outcome_return=case.outcome_return,
            matched_group_id=group_by_case.get(case.case_id, case.matched_group_id),
            hidden_outcome_summary=case.hidden_outcome_summary,
            outcome_definition_id=case.outcome_definition_id,
        )
        for case in case_by_id.values()
    )


def _eligible_control(
    winner: HistoricalCase,
    control: HistoricalCase,
    criteria: ControlMatchCriteria,
) -> bool:
    if criteria.same_sector_required and winner.packet.company.sector != control.packet.company.sector:
        return False
    market_cap_gap = _abs_log_gap(
        winner.packet.company.market_cap_usd,
        control.packet.company.market_cap_usd,
    )
    if market_cap_gap is not None and market_cap_gap > criteria.max_market_cap_log_gap:
        return False
    prior_gap = _abs_feature_gap(winner.packet.features, control.packet.features, "price.return_120d")
    if prior_gap is not None and prior_gap > criteria.max_prior_return_gap:
        return False
    return True


def _match_distance(
    winner: HistoricalCase,
    control: HistoricalCase,
    criteria: ControlMatchCriteria,
) -> float:
    distance = 0.0
    if criteria.same_sector_required and winner.packet.company.industry != control.packet.company.industry:
        distance += 0.25
    distance += _abs_log_gap(winner.packet.company.market_cap_usd, control.packet.company.market_cap_usd) or 0.5
    distance += _abs_feature_gap(winner.packet.features, control.packet.features, "price.return_120d") or 0.25
    distance += 0.5 * (_abs_feature_gap(winner.packet.features, control.packet.features, "valuation.pe_ratio") or 0.25)
    return distance


def _feature_value(features: list[FeatureRecord], name: str) -> float | None:
    selected = [
        feature
        for feature in features
        if feature.name == name and feature.data_quality is not DataQuality.MISSING and isinstance(feature.value, (int, float))
    ]
    if not selected:
        return None
    return float(max(selected, key=lambda feature: feature.as_of_date).value)


def _abs_feature_gap(
    left_features: list[FeatureRecord],
    right_features: list[FeatureRecord],
    name: str,
) -> float | None:
    left = _feature_value(left_features, name)
    right = _feature_value(right_features, name)
    if left is None or right is None:
        return None
    return abs(left - right)


def _abs_log_gap(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or left <= 0 or right <= 0:
        return None
    return abs(log(left) - log(right))
