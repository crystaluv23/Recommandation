"""Retrospective inflection-point detection for surge cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from stock_opportunity_agent.data.sources.core import PriceBar
from stock_opportunity_agent.models import ValidationError


@dataclass(frozen=True)
class InflectionCandidate:
    """A retrospective candidate date where a surge appears to start."""

    symbol: str
    inflection_date: date
    method: str
    score: float
    explanation: str
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValidationError("symbol must not be empty")
        if not self.method.strip():
            raise ValidationError("method must not be empty")
        if not self.explanation.strip():
            raise ValidationError("explanation must not be empty")
        if not 0 <= self.score <= 1:
            raise ValidationError("inflection score must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible inflection candidate."""

        return {
            "symbol": self.symbol,
            "inflection_date": self.inflection_date.isoformat(),
            "method": self.method,
            "score": self.score,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


def detect_price_inflections(
    symbol: str,
    bars: Iterable[PriceBar],
    *,
    window_start: date,
    window_end: date,
    min_forward_return: float = 0.80,
) -> tuple[InflectionCandidate, ...]:
    """Detect factor-based retrospective surge inflection candidates."""

    if window_end <= window_start:
        raise ValidationError("window_end must be after window_start")
    ordered = sorted(
        (
            bar
            for bar in bars
            if bar.symbol.upper() == symbol.upper()
            and window_start <= bar.as_of_date <= window_end
        ),
        key=lambda bar: bar.as_of_date,
    )
    if len(ordered) < 30:
        return ()
    candidates: list[InflectionCandidate] = []
    for index in range(20, len(ordered)):
        current = ordered[index]
        prior_20 = ordered[index - 20 : index]
        forward = [bar for bar in ordered[index:] if bar.as_of_date <= current.as_of_date + timedelta(days=180)]
        if len(forward) < 20:
            continue
        prior_close = prior_20[0].close
        if prior_close <= 0 or current.close <= 0:
            continue
        return_20d = (current.close / prior_close) - 1
        avg_volume = sum(bar.volume for bar in prior_20) / len(prior_20)
        volume_expansion = 0.0 if avg_volume == 0 else (current.volume / avg_volume) - 1
        max_forward = max(bar.close for bar in forward)
        forward_return = (max_forward / current.close) - 1
        score = 0.45 * _scaled(return_20d, 0.08, 0.35)
        score += 0.25 * _scaled(volume_expansion, 0.25, 1.5)
        score += 0.30 * _scaled(forward_return, min_forward_return, min_forward_return * 2)
        if score >= 0.55:
            candidates.append(
                InflectionCandidate(
                    symbol=symbol.upper(),
                    inflection_date=current.as_of_date,
                    method="price_volume_factor",
                    score=round(min(1.0, score), 4),
                    explanation=(
                        "Candidate identified by 20-day price breakout, volume expansion, "
                        "and subsequent 180-day forward strength."
                    ),
                    evidence=(
                        f"20d_return={return_20d:.4f}",
                        f"volume_expansion={volume_expansion:.4f}",
                        f"forward_return_from_candidate={forward_return:.4f}",
                    ),
                )
            )
    return tuple(sorted(candidates, key=lambda item: (-item.score, item.inflection_date))[:5])


def fallback_inflection_from_case(
    symbol: str,
    inflection_date: date,
    *,
    explanation: str = "Fallback uses the case outcome start because no price-bar inflection scan was supplied.",
    evidence: tuple[str, ...] = ("No price-bar inflection scan available.",),
) -> InflectionCandidate:
    """Create an explicit fallback candidate when price bars are unavailable."""

    return InflectionCandidate(
        symbol=symbol.upper(),
        inflection_date=inflection_date,
        method="case_outcome_start_fallback",
        score=0.25,
        explanation=explanation,
        evidence=evidence,
    )


def _scaled(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return max(0.0, min(1.0, (value - floor) / (ceiling - floor)))
