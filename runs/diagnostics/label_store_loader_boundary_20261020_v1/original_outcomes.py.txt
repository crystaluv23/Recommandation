"""Versioned outcome definitions for historical case labeling."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.data.sources.core import PriceBar
from stock_opportunity_agent.models import ValidationError


class CaseOutcomeLabel(str, Enum):
    """Retrospective case label used after the outcome window is known."""

    WINNER = "winner"
    CONTROL = "control"
    FAILURE = "failure"
    UNLABELED = "unlabeled"


@dataclass(frozen=True)
class OutcomeDefinition:
    """Versioned rule for labeling surge, neutral, and failure outcomes.

    This record is deliberately separate from cold-start learning so future
    runs can compare alternative definitions without rewriting the learning
    pipeline.
    """

    definition_id: str
    version: str
    horizon_days: int
    winner_min_return: float
    control_min_return: float
    control_max_return: float
    failure_max_return: float
    min_trading_days: int

    def __post_init__(self) -> None:
        _require_non_empty(self.definition_id, "definition_id")
        _require_non_empty(self.version, "version")
        if self.horizon_days < 1:
            raise ValidationError("horizon_days must be positive")
        if self.min_trading_days < 1:
            raise ValidationError("min_trading_days must be positive")
        if self.control_max_return < self.control_min_return:
            raise ValidationError("control_max_return must be at least control_min_return")
        if self.winner_min_return <= self.control_max_return:
            raise ValidationError("winner_min_return must be above control_max_return")
        if self.failure_max_return >= self.control_min_return:
            raise ValidationError("failure_max_return must be below control_min_return")

    def label_return(self, forward_return: float, *, trading_days: int | None = None) -> CaseOutcomeLabel:
        """Label a realized forward return under this definition."""

        if trading_days is not None and trading_days < self.min_trading_days:
            return CaseOutcomeLabel.UNLABELED
        if forward_return >= self.winner_min_return:
            return CaseOutcomeLabel.WINNER
        if forward_return <= self.failure_max_return:
            return CaseOutcomeLabel.FAILURE
        if self.control_min_return <= forward_return <= self.control_max_return:
            return CaseOutcomeLabel.CONTROL
        return CaseOutcomeLabel.UNLABELED

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible definition record."""

        return {
            "definition_id": self.definition_id,
            "version": self.version,
            "horizon_days": self.horizon_days,
            "winner_min_return": self.winner_min_return,
            "control_min_return": self.control_min_return,
            "control_max_return": self.control_max_return,
            "failure_max_return": self.failure_max_return,
            "min_trading_days": self.min_trading_days,
        }


@dataclass(frozen=True)
class OutcomeObservation:
    """Retrospective price outcome measured after the as-of date."""

    symbol: str
    as_of_date: date
    outcome_start_date: date
    outcome_end_date: date
    start_close: float
    end_close: float
    max_close: float
    min_close: float
    trading_days: int
    forward_return: float
    max_forward_return: float
    max_drawdown_from_start: float

    def __post_init__(self) -> None:
        _require_non_empty(self.symbol, "symbol")
        if self.outcome_start_date <= self.as_of_date:
            raise ValidationError("outcome_start_date must be after as_of_date")
        if self.outcome_end_date < self.outcome_start_date:
            raise ValidationError("outcome_end_date must be on or after outcome_start_date")
        if min(self.start_close, self.end_close, self.max_close, self.min_close) <= 0:
            raise ValidationError("outcome closes must be positive")
        if self.trading_days < 1:
            raise ValidationError("trading_days must be positive")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible outcome observation."""

        return {
            "symbol": self.symbol,
            "as_of_date": self.as_of_date.isoformat(),
            "outcome_start_date": self.outcome_start_date.isoformat(),
            "outcome_end_date": self.outcome_end_date.isoformat(),
            "start_close": self.start_close,
            "end_close": self.end_close,
            "max_close": self.max_close,
            "min_close": self.min_close,
            "trading_days": self.trading_days,
            "forward_return": self.forward_return,
            "max_forward_return": self.max_forward_return,
            "max_drawdown_from_start": self.max_drawdown_from_start,
        }


def default_outcome_definition() -> OutcomeDefinition:
    """Return the conservative MVP surge definition."""

    return OutcomeDefinition(
        definition_id="surge-close-return-v0.1",
        version="0.1",
        horizon_days=180,
        winner_min_return=0.80,
        control_min_return=-0.10,
        control_max_return=0.20,
        failure_max_return=-0.20,
        min_trading_days=60,
    )


def observe_price_outcome(
    symbol: str,
    bars: Iterable[PriceBar],
    as_of_date: date,
    definition: OutcomeDefinition,
) -> OutcomeObservation:
    """Measure a retrospective price outcome from daily bars."""

    if not symbol.strip():
        raise ValidationError("symbol must not be empty")
    window_end = as_of_date.toordinal() + definition.horizon_days
    future_bars = sorted(
        (
            bar
            for bar in bars
            if bar.symbol.upper() == symbol.upper()
            and bar.as_of_date > as_of_date
            and bar.as_of_date.toordinal() <= window_end
        ),
        key=lambda bar: bar.as_of_date,
    )
    if len(future_bars) < definition.min_trading_days:
        raise ValidationError("not enough future bars to observe outcome under definition")
    start = future_bars[0]
    end = future_bars[-1]
    max_close = max(bar.close for bar in future_bars)
    min_close = min(bar.close for bar in future_bars)
    return OutcomeObservation(
        symbol=symbol.upper(),
        as_of_date=as_of_date,
        outcome_start_date=start.as_of_date,
        outcome_end_date=end.as_of_date,
        start_close=start.close,
        end_close=end.close,
        max_close=max_close,
        min_close=min_close,
        trading_days=len(future_bars),
        forward_return=(end.close / start.close) - 1,
        max_forward_return=(max_close / start.close) - 1,
        max_drawdown_from_start=(min_close / start.close) - 1,
    )


def label_price_outcome(
    symbol: str,
    bars: Iterable[PriceBar],
    as_of_date: date,
    definition: OutcomeDefinition | None = None,
) -> tuple[CaseOutcomeLabel, OutcomeObservation]:
    """Observe and label a retrospective price outcome."""

    active_definition = definition or default_outcome_definition()
    observation = observe_price_outcome(symbol, bars, as_of_date, active_definition)
    return active_definition.label_return(
        observation.forward_return,
        trading_days=observation.trading_days,
    ), observation


def six_month_smoothed_multiple(
    raw_bars: Any, prediction_date: date
) -> dict[str, Any]:
    """Measure the canonical six-month surge label from adjusted close bars.

    The baseline is the mean of the last five complete adjusted closes strictly
    before ``prediction_date``; the future peak is the maximum mean of any five
    consecutive adjusted closes inside the six-calendar-month window starting at
    ``prediction_date``. Returns the observation (baseline/peak means and
    dates, horizon end) plus the derived ``realized_max_multiple``,
    ``is_surge`` (>= 2.0) and magnitude class. Raises ``ValidationError`` when
    fewer than five baseline bars, fewer than five future bars, or an
    incomplete horizon would make the measurement uncomparable.
    """

    if not isinstance(raw_bars, (list, tuple)):
        raise ValidationError("missing adjusted price history")
    parsed: list[tuple[date, float]] = []
    for bar in raw_bars:
        if not isinstance(bar, Mapping) or not bar.get("as_of_date"):
            continue
        adjusted_close = bar.get("adjusted_close")
        if adjusted_close is None:
            continue
        value = float(adjusted_close)
        if value <= 0:
            continue
        parsed.append((date.fromisoformat(str(bar["as_of_date"])), value))
    parsed.sort(key=lambda item: item[0])
    baseline_rows = [item for item in parsed if item[0] < prediction_date][-5:]
    if len(baseline_rows) < 5:
        raise ValidationError("fewer_than_5_baseline_bars")
    horizon_end = add_months(prediction_date, 6)
    future_rows = [
        item for item in parsed if prediction_date <= item[0] <= horizon_end
    ]
    if len(future_rows) < 5:
        raise ValidationError("fewer_than_5_future_bars")
    if future_rows[-1][0] < horizon_end - timedelta(days=7):
        raise ValidationError("incomplete_six_month_price_horizon")
    baseline_mean = sum(value for _, value in baseline_rows) / 5
    windows = [future_rows[index : index + 5] for index in range(len(future_rows) - 4)]
    peak_window = max(
        windows,
        key=lambda rows: sum(value for _, value in rows) / len(rows),
    )
    future_peak_mean = sum(value for _, value in peak_window) / 5
    multiple = future_peak_mean / baseline_mean
    if multiple < 2.0:
        magnitude = None
    elif multiple < 3.0:
        magnitude = "2-3x"
    elif multiple < 10.0:
        magnitude = "3-10x"
    else:
        magnitude = "10x+"
    return {
        "realized_max_multiple": multiple,
        "is_surge": multiple >= 2.0,
        "magnitude": magnitude,
        "baseline_mean": baseline_mean,
        "future_peak_mean": future_peak_mean,
        "baseline_dates": [item[0].isoformat() for item in baseline_rows],
        "future_peak_dates": [item[0].isoformat() for item in peak_window],
        "horizon_end": horizon_end.isoformat(),
    }


SURGE_LABEL_CONTRACT: dict[str, Any] = {
    "horizon": "six_calendar_months",
    "baseline": "mean_last_5_complete_adjusted_closes_strictly_before_as_of",
    "future_peak": "max_mean_5_consecutive_adjusted_closes_after_as_of",
    "binary_threshold": 2.0,
    "magnitude_classes": ["2-3x", "3-10x", "10x+"],
}


def add_months(value: date, months: int) -> date:
    """Add calendar months, clamping the day to the target month length."""

    total_month = value.month - 1 + months
    year = value.year + total_month // 12
    month = total_month % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValidationError(f"{name} must not be empty")
