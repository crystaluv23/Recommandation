"""Universe-wide historical candidate selection for cold start."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.cases.outcomes import (
    CaseOutcomeLabel,
    OutcomeDefinition,
    OutcomeObservation,
    default_outcome_definition,
    observe_price_outcome,
)
from stock_opportunity_agent.data.sources.core import PriceBar, SecurityListing
from stock_opportunity_agent.models import ValidationError


@dataclass(frozen=True)
class HistoricalCandidate:
    """One selected retrospective cold-start candidate."""

    symbol: str
    company_name: str
    label: CaseOutcomeLabel
    outcome_anchor_date: date
    inflection_date: date
    inflection_method: str
    inflection_score: float
    outcome_end_date: date
    forward_return: float
    max_forward_return: float
    max_drawdown_from_start: float
    trading_days: int
    selection_rank: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible candidate record."""

        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "label": self.label.value,
            "outcome_anchor_date": self.outcome_anchor_date.isoformat(),
            "inflection_date": self.inflection_date.isoformat(),
            "inflection_method": self.inflection_method,
            "inflection_score": self.inflection_score,
            "outcome_end_date": self.outcome_end_date.isoformat(),
            "forward_return": self.forward_return,
            "max_forward_return": self.max_forward_return,
            "max_drawdown_from_start": self.max_drawdown_from_start,
            "trading_days": self.trading_days,
            "selection_rank": self.selection_rank,
        }


@dataclass(frozen=True)
class HistoricalCandidateSelection:
    """Result of a universe-wide historical candidate scan."""

    run_date: date
    selection_window_start: date
    selection_window_end: date
    outcome_definition: OutcomeDefinition
    input_listing_count: int
    eligible_listing_count: int
    priced_symbol_count: int
    skipped_symbol_count: int
    selected_candidates: tuple[HistoricalCandidate, ...]
    label_counts: Mapping[str, int]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible scan result."""

        return {
            "run_date": self.run_date.isoformat(),
            "selection_window_start": self.selection_window_start.isoformat(),
            "selection_window_end": self.selection_window_end.isoformat(),
            "outcome_definition": self.outcome_definition.to_dict(),
            "input_listing_count": self.input_listing_count,
            "eligible_listing_count": self.eligible_listing_count,
            "priced_symbol_count": self.priced_symbol_count,
            "skipped_symbol_count": self.skipped_symbol_count,
            "label_counts": dict(self.label_counts),
            "selected_candidates": [candidate.to_dict() for candidate in self.selected_candidates],
            "warnings": list(self.warnings),
        }


def eligible_common_stock_listings(listings: Iterable[SecurityListing]) -> tuple[SecurityListing, ...]:
    """Filter raw listings to likely US common-stock symbols."""

    eligible: list[SecurityListing] = []
    for listing in listings:
        symbol = listing.symbol.upper()
        name = listing.name.lower()
        asset_type = (listing.asset_type or "").lower()
        status = listing.status.lower()
        if status != "active":
            continue
        if asset_type and asset_type not in {"stock", "common stock", "common_stock"}:
            continue
        if any(marker in name for marker in ("warrant", "right", "unit", "preferred", "depositary")):
            continue
        if any(marker in symbol for marker in ("-", "/", "^", " ", "$")):
            continue
        if len(symbol) > 5:
            continue
        eligible.append(listing)
    return tuple(sorted(eligible, key=lambda item: item.symbol))


def matured_selection_window(
    run_date: date,
    outcome_definition: OutcomeDefinition | None = None,
    *,
    selection_window_days: int = 365,
) -> tuple[date, date]:
    """Return the latest one-year anchor window with matured forward outcomes."""

    if selection_window_days < 1:
        raise ValidationError("selection_window_days must be positive")
    definition = outcome_definition or default_outcome_definition()
    end = run_date - timedelta(days=definition.horizon_days)
    start = end - timedelta(days=selection_window_days)
    return start, end


def select_historical_candidates(
    *,
    listings: Iterable[SecurityListing],
    bars_by_symbol: Mapping[str, Iterable[PriceBar]],
    run_date: date,
    outcome_definition: OutcomeDefinition | None = None,
    selection_window_days: int = 365,
    max_winners: int = 12,
    max_controls: int = 36,
    max_failures: int = 12,
    inflection_dates_by_symbol: Mapping[str, date] | None = None,
) -> HistoricalCandidateSelection:
    """Select cold-start candidates from a universe-wide price scan."""

    if max_winners < 1:
        raise ValidationError("max_winners must be at least 1")
    if max_controls < 1:
        raise ValidationError("max_controls must be at least 1")
    if max_failures < 0:
        raise ValidationError("max_failures cannot be negative")
    definition = outcome_definition or default_outcome_definition()
    listing_list = list(listings)
    eligible = eligible_common_stock_listings(listing_list)
    listing_by_symbol = {listing.symbol.upper(): listing for listing in eligible}
    window_start, window_end = matured_selection_window(
        run_date,
        definition,
        selection_window_days=selection_window_days,
    )
    per_label: dict[CaseOutcomeLabel, list[tuple[OutcomeObservation, SecurityListing]]] = {
        CaseOutcomeLabel.WINNER: [],
        CaseOutcomeLabel.CONTROL: [],
        CaseOutcomeLabel.FAILURE: [],
    }
    priced_symbols = 0
    skipped_symbols = 0
    for symbol, listing in listing_by_symbol.items():
        bars = list(bars_by_symbol.get(symbol, ()))
        if not bars:
            skipped_symbols += 1
            continue
        selected = _select_symbol_observation(symbol, bars, window_start, window_end, definition)
        if selected is None:
            skipped_symbols += 1
            continue
        priced_symbols += 1
        label, observation = selected
        if label in per_label:
            per_label[label].append((observation, listing))

    winners = sorted(per_label[CaseOutcomeLabel.WINNER], key=lambda item: (-item[0].forward_return, item[1].symbol))
    controls = sorted(
        per_label[CaseOutcomeLabel.CONTROL],
        key=lambda item: (abs(item[0].forward_return - _control_midpoint(definition)), item[1].symbol),
    )
    failures = sorted(per_label[CaseOutcomeLabel.FAILURE], key=lambda item: (item[0].forward_return, item[1].symbol))
    selected_pairs = (
        [(CaseOutcomeLabel.WINNER, item) for item in winners[:max_winners]]
        + [(CaseOutcomeLabel.CONTROL, item) for item in controls[:max_controls]]
        + [(CaseOutcomeLabel.FAILURE, item) for item in failures[:max_failures]]
    )
    selected_candidates = tuple(
        _candidate(
            label,
            observation,
            listing,
            rank=index + 1,
            inflection_date=(inflection_dates_by_symbol or {}).get(listing.symbol.upper()),
        )
        for index, (label, (observation, listing)) in enumerate(selected_pairs)
    )
    label_counts = {
        label.value: len(items)
        for label, items in per_label.items()
    }
    warnings: list[str] = []
    if not winners:
        warnings.append("No winner candidates found under the active outcome definition.")
    if not controls:
        warnings.append("No neutral control candidates found under the active outcome definition.")
    if not failures:
        warnings.append("No failure candidates found under the active outcome definition.")
    return HistoricalCandidateSelection(
        run_date=run_date,
        selection_window_start=window_start,
        selection_window_end=window_end,
        outcome_definition=definition,
        input_listing_count=len(listing_list),
        eligible_listing_count=len(eligible),
        priced_symbol_count=priced_symbols,
        skipped_symbol_count=skipped_symbols,
        selected_candidates=selected_candidates,
        label_counts=label_counts,
        warnings=tuple(warnings),
    )


def _select_symbol_observation(
    symbol: str,
    bars: list[PriceBar],
    window_start: date,
    window_end: date,
    definition: OutcomeDefinition,
) -> tuple[CaseOutcomeLabel, OutcomeObservation] | None:
    observations: dict[CaseOutcomeLabel, list[OutcomeObservation]] = {
        CaseOutcomeLabel.WINNER: [],
        CaseOutcomeLabel.CONTROL: [],
        CaseOutcomeLabel.FAILURE: [],
    }
    for bar in sorted(bars, key=lambda item: item.as_of_date):
        if not window_start <= bar.as_of_date <= window_end:
            continue
        try:
            observation = observe_price_outcome(symbol, bars, bar.as_of_date, definition)
        except ValidationError:
            continue
        label = definition.label_return(observation.forward_return, trading_days=observation.trading_days)
        if label in observations:
            observations[label].append(observation)
    if observations[CaseOutcomeLabel.WINNER]:
        return CaseOutcomeLabel.WINNER, max(observations[CaseOutcomeLabel.WINNER], key=lambda item: item.forward_return)
    if observations[CaseOutcomeLabel.FAILURE]:
        return CaseOutcomeLabel.FAILURE, min(observations[CaseOutcomeLabel.FAILURE], key=lambda item: item.forward_return)
    if observations[CaseOutcomeLabel.CONTROL]:
        midpoint = _control_midpoint(definition)
        return CaseOutcomeLabel.CONTROL, min(
            observations[CaseOutcomeLabel.CONTROL],
            key=lambda item: abs(item.forward_return - midpoint),
        )
    return None


def _candidate(
    label: CaseOutcomeLabel,
    observation: OutcomeObservation,
    listing: SecurityListing,
    *,
    rank: int,
    inflection_date: date | None,
) -> HistoricalCandidate:
    selected_inflection = inflection_date or observation.as_of_date
    return HistoricalCandidate(
        symbol=listing.symbol.upper(),
        company_name=listing.name,
        label=label,
        outcome_anchor_date=observation.as_of_date,
        inflection_date=selected_inflection,
        inflection_method="price_volume_factor" if inflection_date is not None else "outcome_anchor_fallback",
        inflection_score=0.75 if inflection_date is not None else 0.25,
        outcome_end_date=observation.outcome_end_date,
        forward_return=observation.forward_return,
        max_forward_return=observation.max_forward_return,
        max_drawdown_from_start=observation.max_drawdown_from_start,
        trading_days=observation.trading_days,
        selection_rank=rank,
    )


def _control_midpoint(definition: OutcomeDefinition) -> float:
    return (definition.control_min_return + definition.control_max_return) / 2
