"""Measurable signal rules for point-in-time research packets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from stock_opportunity_agent.models import (
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    FeatureRecord,
    ResearchPacket,
    ValidationError,
)


FeatureValues = dict[str, float | int | str | bool | None]
MeasureFunction = Callable[[ResearchPacket, dict[str, FeatureRecord]], "SignalObservation"]


@dataclass(frozen=True)
class SignalObservation:
    """Measured signal state for one research packet.

    Example:
        ``measure_packet_signals(packet)[0].observed`` tells whether the rule
        fired using only packet data available as of the packet date.
    """

    signal_id: str
    name: str
    category: str
    score: float
    observed: bool
    logic: str
    feature_values: FeatureValues
    evidence: list[EvidenceItem]
    explanation: str

    def __post_init__(self) -> None:
        _require_non_empty(self.signal_id, "signal_id")
        _require_non_empty(self.name, "name")
        _require_non_empty(self.category, "category")
        _require_non_empty(self.logic, "logic")
        _require_score(self.score, "score")
        if not self.evidence:
            raise ValidationError("signal observation requires evidence")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible observation record."""

        return {
            "signal_id": self.signal_id,
            "name": self.name,
            "category": self.category,
            "score": self.score,
            "observed": self.observed,
            "logic": self.logic,
            "feature_values": dict(self.feature_values),
            "evidence": [item.to_dict() for item in self.evidence],
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class SignalRule:
    """Versioned measurable rule used by cold-start case learning."""

    signal_id: str
    name: str
    category: str
    description: str
    logic: str
    feature_names: tuple[str, ...]
    false_positive_patterns: tuple[str, ...]
    hindsight_risk_notes: tuple[str, ...]
    measure: MeasureFunction

    def __post_init__(self) -> None:
        for name in ("signal_id", "name", "category", "description", "logic"):
            _require_non_empty(getattr(self, name), name)
        if not self.feature_names:
            raise ValidationError("signal rule requires feature names")

    def observe(self, packet: ResearchPacket) -> SignalObservation:
        """Measure this rule on a packet."""

        return self.measure(packet, _feature_lookup(packet.features))


def default_signal_rules() -> tuple[SignalRule, ...]:
    """Return the deterministic MVP signal rules.

    These rules intentionally use structured packet features and packet
    catalysts only; qualitative LLM-only signals are left out until the
    research layer can attach source evidence.
    """

    return (
        SignalRule(
            signal_id="sig-fundamental-revenue-acceleration",
            name="Fundamental revenue acceleration",
            category="fundamental_inflection",
            description="Revenue and earnings growth are strong enough to suggest expectations may lag reality.",
            logic=(
                "Fire when revenue growth, earnings growth, and operating margin together show an "
                "inflection, with revenue growth weighted most heavily."
            ),
            feature_names=(
                "financial.revenue_growth_yoy",
                "financial.earnings_growth_yoy",
                "financial.operating_margin_ttm",
            ),
            false_positive_patterns=(
                "One-time rebound from a depressed base",
                "Growth without operating leverage",
            ),
            hindsight_risk_notes=(
                "Do not use later quarters to label the inflection as obvious.",
            ),
            measure=_measure_fundamental_acceleration,
        ),
        SignalRule(
            signal_id="sig-market-early-confirmation",
            name="Market early confirmation",
            category="market_early_confirmation",
            description="Price trend is already improving before the later outcome window.",
            logic=(
                "Fire when 20-day and 60-day returns are positive enough to show early confirmation "
                "without requiring the later surge."
            ),
            feature_names=("price.return_20d", "price.return_60d", "price.return_120d"),
            false_positive_patterns=(
                "Short-term rebound inside a long downtrend",
                "Momentum caused by already-known news",
            ),
            hindsight_risk_notes=(
                "The rule must be measured before the outcome window starts.",
            ),
            measure=_measure_market_confirmation,
        ),
        SignalRule(
            signal_id="sig-analyst-expectation-gap",
            name="Analyst expectation gap",
            category="analyst_disagreement",
            description="Sell-side target price implies upside while structured fundamentals are not deteriorating.",
            logic=(
                "Fire when target-price upside is positive and at least one growth feature is supportive."
            ),
            feature_names=(
                "analyst.target_price",
                "price.latest_close",
                "financial.revenue_growth_yoy",
                "financial.earnings_growth_yoy",
            ),
            false_positive_patterns=(
                "Stale target prices after a business slowdown",
                "Targets clustered above price after broad market drawdowns",
            ),
            hindsight_risk_notes=(
                "Target prices must be available as of the packet date.",
            ),
            measure=_measure_expectation_gap,
        ),
        SignalRule(
            signal_id="sig-catalyst-density",
            name="Catalyst density",
            category="catalyst_density",
            description="Multiple known catalysts are scheduled near the as-of date.",
            logic="Fire when the packet contains at least one near-term catalyst and score higher for two or more.",
            feature_names=("packet.catalyst_count_180d",),
            false_positive_patterns=(
                "Catalyst calendar is crowded but low materiality",
                "Expected catalysts already fully priced",
            ),
            hindsight_risk_notes=(
                "Only catalysts known as of the packet date may count.",
            ),
            measure=_measure_catalyst_density,
        ),
        SignalRule(
            signal_id="sig-valuation-room-with-growth",
            name="Valuation room with growth",
            category="valuation_room",
            description="Growth is visible while common valuation ratios are not extreme.",
            logic=(
                "Fire when revenue growth is positive and P/E or price-to-sales leaves room for multiple "
                "expansion instead of already discounting perfection."
            ),
            feature_names=(
                "financial.revenue_growth_yoy",
                "valuation.pe_ratio",
                "valuation.price_to_sales_ttm",
            ),
            false_positive_patterns=(
                "Low multiple because the market correctly expects growth to fade",
                "Cyclical peak earnings make valuation look deceptively cheap",
            ),
            hindsight_risk_notes=(
                "Do not use post-surge valuation to decide there was room before the surge.",
            ),
            measure=_measure_valuation_room,
        ),
        SignalRule(
            signal_id="sig-liquidity-expansion",
            name="Liquidity expansion",
            category="market_early_confirmation",
            description="Recent dollar volume is expanding relative to the medium-term baseline.",
            logic=(
                "Fire when 20-day average dollar volume is meaningfully above the 60-day baseline."
            ),
            feature_names=(
                "price.average_daily_dollar_volume_20d",
                "price.average_daily_dollar_volume_60d",
            ),
            false_positive_patterns=(
                "Temporary volume burst from non-repeatable news",
                "Liquidity expands after most repricing has already happened",
            ),
            hindsight_risk_notes=(
                "Measure volume expansion before the outcome window.",
            ),
            measure=_measure_liquidity_expansion,
        ),
    )


def measure_packet_signals(
    packet: ResearchPacket,
    rules: tuple[SignalRule, ...] | None = None,
) -> list[SignalObservation]:
    """Measure all signal rules on a point-in-time packet."""

    return [rule.observe(packet) for rule in (rules or default_signal_rules())]


def _measure_fundamental_acceleration(
    packet: ResearchPacket,
    features: dict[str, FeatureRecord],
) -> SignalObservation:
    revenue = _numeric(features.get("financial.revenue_growth_yoy"))
    earnings = _numeric(features.get("financial.earnings_growth_yoy"))
    margin = _numeric(features.get("financial.operating_margin_ttm"))
    parts = [
        0.50 * _scaled(revenue, floor=0.08, ceiling=0.35),
        0.30 * _scaled(earnings, floor=0.00, ceiling=0.50),
        0.20 * _scaled(margin, floor=0.04, ceiling=0.20),
    ]
    score = sum(parts)
    return _observation(
        packet,
        signal_id="sig-fundamental-revenue-acceleration",
        name="Fundamental revenue acceleration",
        category="fundamental_inflection",
        score=score,
        observed=score >= 0.55,
        logic="Weighted score from revenue growth, earnings growth, and operating margin.",
        feature_values=_values(
            features,
            "financial.revenue_growth_yoy",
            "financial.earnings_growth_yoy",
            "financial.operating_margin_ttm",
        ),
        explanation=(
            f"growth score={score:.2f}; revenue={_fmt(revenue)}, "
            f"earnings={_fmt(earnings)}, margin={_fmt(margin)}"
        ),
    )


def _measure_market_confirmation(
    packet: ResearchPacket,
    features: dict[str, FeatureRecord],
) -> SignalObservation:
    return_20d = _numeric(features.get("price.return_20d"))
    return_60d = _numeric(features.get("price.return_60d"))
    return_120d = _numeric(features.get("price.return_120d"))
    trend_score = 0.45 * _scaled(return_20d, floor=0.03, ceiling=0.18)
    trend_score += 0.45 * _scaled(return_60d, floor=0.08, ceiling=0.35)
    trend_score += 0.10 * _scaled(return_120d, floor=-0.05, ceiling=0.30)
    score = min(1.0, trend_score)
    return _observation(
        packet,
        signal_id="sig-market-early-confirmation",
        name="Market early confirmation",
        category="market_early_confirmation",
        score=score,
        observed=score >= 0.55,
        logic="Weighted 20-day, 60-day, and 120-day point-in-time returns.",
        feature_values=_values(features, "price.return_20d", "price.return_60d", "price.return_120d"),
        explanation=(
            f"trend score={score:.2f}; 20d={_fmt(return_20d)}, "
            f"60d={_fmt(return_60d)}, 120d={_fmt(return_120d)}"
        ),
    )


def _measure_expectation_gap(
    packet: ResearchPacket,
    features: dict[str, FeatureRecord],
) -> SignalObservation:
    target = _numeric(features.get("analyst.target_price"))
    close = _numeric(features.get("price.latest_close"))
    revenue = _numeric(features.get("financial.revenue_growth_yoy"))
    earnings = _numeric(features.get("financial.earnings_growth_yoy"))
    upside = None if target is None or close in (None, 0) else (target / close) - 1
    growth_support = max(_scaled(revenue, floor=0.05, ceiling=0.25), _scaled(earnings, floor=0.00, ceiling=0.35))
    score = 0.70 * _scaled(upside, floor=0.05, ceiling=0.35) + 0.30 * growth_support
    return _observation(
        packet,
        signal_id="sig-analyst-expectation-gap",
        name="Analyst expectation gap",
        category="analyst_disagreement",
        score=score,
        observed=score >= 0.55,
        logic="Target-price upside combined with at least one non-deteriorating growth feature.",
        feature_values=_values(
            features,
            "analyst.target_price",
            "price.latest_close",
            "financial.revenue_growth_yoy",
            "financial.earnings_growth_yoy",
        ),
        explanation=f"expectation-gap score={score:.2f}; target upside={_fmt(upside)}",
    )


def _measure_catalyst_density(
    packet: ResearchPacket,
    features: dict[str, FeatureRecord],
) -> SignalObservation:
    near_term = [
        catalyst
        for catalyst in packet.catalysts
        if 0 <= (catalyst.expected_date - packet.as_of.as_of_date).days <= 180
    ]
    score = min(1.0, len(near_term) / 2)
    catalyst_names = ", ".join(catalyst.name for catalyst in near_term) or "none"
    return _observation(
        packet,
        signal_id="sig-catalyst-density",
        name="Catalyst density",
        category="catalyst_density",
        score=score,
        observed=score >= 0.50,
        logic="Count known catalysts expected within 180 days of the packet date.",
        feature_values={"packet.catalyst_count_180d": len(near_term)},
        explanation=f"catalyst score={score:.2f}; catalysts={catalyst_names}",
    )


def _measure_valuation_room(
    packet: ResearchPacket,
    features: dict[str, FeatureRecord],
) -> SignalObservation:
    revenue = _numeric(features.get("financial.revenue_growth_yoy"))
    pe_ratio = _numeric(features.get("valuation.pe_ratio"))
    price_to_sales = _numeric(features.get("valuation.price_to_sales_ttm"))
    growth_score = _scaled(revenue, floor=0.08, ceiling=0.35)
    pe_room = _inverse_scaled(pe_ratio, floor=15.0, ceiling=45.0)
    sales_room = _inverse_scaled(price_to_sales, floor=2.0, ceiling=10.0)
    valuation_score = max(pe_room, sales_room)
    score = 0.55 * growth_score + 0.45 * valuation_score
    return _observation(
        packet,
        signal_id="sig-valuation-room-with-growth",
        name="Valuation room with growth",
        category="valuation_room",
        score=score,
        observed=score >= 0.55,
        logic="Revenue growth score combined with the better of P/E room and price-to-sales room.",
        feature_values=_values(
            features,
            "financial.revenue_growth_yoy",
            "valuation.pe_ratio",
            "valuation.price_to_sales_ttm",
        ),
        explanation=(
            f"valuation-room score={score:.2f}; growth={_fmt(revenue)}, "
            f"pe={_fmt(pe_ratio)}, ps={_fmt(price_to_sales)}"
        ),
    )


def _measure_liquidity_expansion(
    packet: ResearchPacket,
    features: dict[str, FeatureRecord],
) -> SignalObservation:
    adv_20d = _numeric(features.get("price.average_daily_dollar_volume_20d"))
    adv_60d = _numeric(features.get("price.average_daily_dollar_volume_60d"))
    expansion = None if adv_20d is None or adv_60d in (None, 0) else (adv_20d / adv_60d) - 1
    score = _scaled(expansion, floor=0.05, ceiling=0.45)
    return _observation(
        packet,
        signal_id="sig-liquidity-expansion",
        name="Liquidity expansion",
        category="market_early_confirmation",
        score=score,
        observed=score >= 0.55,
        logic="20-day dollar volume expansion relative to 60-day dollar volume.",
        feature_values=_values(
            features,
            "price.average_daily_dollar_volume_20d",
            "price.average_daily_dollar_volume_60d",
        ),
        explanation=f"liquidity-expansion score={score:.2f}; expansion={_fmt(expansion)}",
    )


def _observation(
    packet: ResearchPacket,
    *,
    signal_id: str,
    name: str,
    category: str,
    score: float,
    observed: bool,
    logic: str,
    feature_values: FeatureValues,
    explanation: str,
) -> SignalObservation:
    evidence = _source_evidence(packet, tuple(feature_values))
    if not evidence:
        evidence = [
            EvidenceItem(
                kind=EvidenceKind.INFERENCE,
                summary=f"{name} measured with missing or packet-level inputs: {explanation}",
                as_of_date=packet.as_of.as_of_date,
                data_quality=DataQuality.MISSING if any(value is None for value in feature_values.values()) else DataQuality.CONFIRMED,
                inference=True,
            )
        ]
    return SignalObservation(
        signal_id=signal_id,
        name=name,
        category=category,
        score=round(_clip(score), 4),
        observed=observed,
        logic=logic,
        feature_values=feature_values,
        evidence=evidence,
        explanation=explanation,
    )


def _feature_lookup(features: list[FeatureRecord]) -> dict[str, FeatureRecord]:
    selected: dict[str, FeatureRecord] = {}
    for feature in features:
        current = selected.get(feature.name)
        if current is None or feature.as_of_date >= current.as_of_date:
            selected[feature.name] = feature
    return selected


def _source_evidence(packet: ResearchPacket, names: tuple[str, ...]) -> list[EvidenceItem]:
    name_set = set(names)
    evidence: list[EvidenceItem] = []
    for feature in packet.features:
        if feature.name not in name_set:
            continue
        matching = [
            item
            for item in packet.evidence
            if item.summary.startswith(f"{feature.name} ") or (feature.source_id and item.source_id == feature.source_id)
        ]
        evidence.extend(matching)
    return evidence


def _values(features: dict[str, FeatureRecord], *names: str) -> FeatureValues:
    return {name: features[name].value if name in features else None for name in names}


def _numeric(feature: FeatureRecord | None) -> float | None:
    if feature is None or feature.data_quality is DataQuality.MISSING:
        return None
    if isinstance(feature.value, bool):
        return None
    if isinstance(feature.value, (int, float)):
        return float(feature.value)
    return None


def _scaled(value: float | None, *, floor: float, ceiling: float) -> float:
    if value is None or ceiling <= floor:
        return 0.0
    return _clip((value - floor) / (ceiling - floor))


def _inverse_scaled(value: float | None, *, floor: float, ceiling: float) -> float:
    if value is None or ceiling <= floor:
        return 0.0
    return _clip((ceiling - value) / (ceiling - floor))


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _fmt(value: float | None) -> str:
    if value is None:
        return "missing"
    return f"{value:.2f}"


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValidationError(f"{name} must not be empty")


def _require_score(value: float, name: str) -> None:
    if not 0 <= value <= 1:
        raise ValidationError(f"{name} must be between 0 and 1")
