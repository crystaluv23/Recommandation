"""Industry-chain theme map construction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from stock_opportunity_agent.cases import CaseOutcomeLabel, HistoricalCase
from stock_opportunity_agent.cases.learning import ColdStartLearningResult
from stock_opportunity_agent.models import (
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    SegmentAssessment,
    ThemeMap,
    ValidationError,
)


@dataclass(frozen=True)
class ThemeMapBuildResult:
    """Cold-start theme map output."""

    theme_maps: tuple[ThemeMap, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result."""

        return {
            "theme_maps": [theme.to_dict() for theme in self.theme_maps],
            "warnings": list(self.warnings),
        }


def build_cold_start_theme_maps(
    cases: Iterable[HistoricalCase],
    learning_result: ColdStartLearningResult,
    *,
    stage_scale_version: str = "theme-stage-v0.1",
) -> ThemeMapBuildResult:
    """Build initial industry-chain maps from cold-start cases.

    The builder uses only point-in-time packet fields, known catalysts, and
    deterministic cold-start signal observations. It initializes hypotheses for
    later theme-first scans; it does not replace full theme discovery.
    """

    case_list = list(cases)
    if not case_list:
        raise ValidationError("theme map construction requires at least one case")
    if not stage_scale_version.strip():
        raise ValidationError("stage_scale_version must not be empty")
    cases_by_theme: dict[str, list[HistoricalCase]] = defaultdict(list)
    for case in case_list:
        theme_ids = case.packet.theme_ids or [_slug(case.packet.company.sector)]
        for theme_id in theme_ids:
            cases_by_theme[theme_id].append(case)
    warnings = []
    theme_maps = []
    for theme_id, theme_cases in sorted(cases_by_theme.items()):
        if not any(case.label is CaseOutcomeLabel.WINNER for case in theme_cases):
            warnings.append(f"Theme {theme_id} has no winner case.")
        theme_maps.append(
            _build_theme_map(
                theme_id,
                theme_cases,
                learning_result,
                stage_scale_version=stage_scale_version,
            )
        )
    return ThemeMapBuildResult(theme_maps=tuple(theme_maps), warnings=tuple(warnings))


def _build_theme_map(
    theme_id: str,
    cases: list[HistoricalCase],
    learning_result: ColdStartLearningResult,
    *,
    stage_scale_version: str,
) -> ThemeMap:
    as_of_date = min(case.packet.as_of.as_of_date for case in cases)
    segments = tuple(sorted({case.packet.company.industry for case in cases}))
    segment_assessments = [
        _segment_assessment(segment, [case for case in cases if case.packet.company.industry == segment], learning_result)
        for segment in segments
    ]
    candidate_symbols = sorted({case.packet.company.ticker.symbol for case in cases})
    evidence = [
        EvidenceItem(
            kind=EvidenceKind.INFERENCE,
            summary=(
                f"Cold-start theme map for {theme_id}: {len(cases)} case(s), "
                f"{len(segment_assessments)} segment(s), {len(candidate_symbols)} candidate symbol(s)."
            ),
            as_of_date=as_of_date,
            data_quality=DataQuality.CONFIRMED,
            inference=True,
        )
    ]
    leading_indicators = sorted(
        {
            indicator
            for segment in segment_assessments
            for indicator in segment.leading_indicators
        }
    )
    risks = sorted({risk for segment in segment_assessments for risk in segment.risks})
    crowdedness_flags = sorted(
        {
            flag
            for segment in segment_assessments
            for flag in segment.crowdedness_flags
        }
    )
    validation_state = {
        "text_evidence": any(case.packet.evidence or case.packet.catalysts for case in cases),
        "data_evidence": any(case.packet.features for case in cases),
        "market_evidence": any(_observed(case, learning_result, "sig-market-early-confirmation") for case in cases),
        "analyst_evidence": any(_observed(case, learning_result, "sig-analyst-expectation-gap") for case in cases),
    }
    return ThemeMap(
        theme_id=theme_id,
        name=_title(theme_id),
        as_of_date=as_of_date,
        segments=segment_assessments,
        leading_indicators=leading_indicators,
        evidence=evidence,
        risks=risks,
        stage_scale_version=stage_scale_version,
        candidate_symbols=candidate_symbols,
        validation_state=validation_state,
        crowdedness_flags=crowdedness_flags,
    )


def _segment_assessment(
    segment: str,
    cases: list[HistoricalCase],
    learning_result: ColdStartLearningResult,
) -> SegmentAssessment:
    as_of_date = min(case.packet.as_of.as_of_date for case in cases)
    candidate_symbols = sorted({case.packet.company.ticker.symbol for case in cases})
    signal_scores = [
        observation.score
        for case in cases
        for observation in learning_result.observations_by_case.get(case.case_id, ())
        if observation.observed
    ]
    winner_count = sum(1 for case in cases if case.label is CaseOutcomeLabel.WINNER)
    timing_score = _clamp((_average(signal_scores) * 0.70) + (0.15 * winner_count))
    transmission_score = _clamp((0.25 * len(candidate_symbols)) + (0.20 * winner_count) + (0.10 * _catalyst_count(cases)))
    stage = _stage(cases, learning_result)
    leading_indicators = _leading_indicators(cases, learning_result)
    risks = _segment_risks(cases, learning_result)
    crowdedness_flags = _crowdedness_flags(cases, learning_result)
    evidence = [
        EvidenceItem(
            kind=EvidenceKind.INFERENCE,
            summary=(
                f"Cold-start segment {segment}: stage {stage}, timing_score={timing_score:.2f}, "
                f"transmission_score={transmission_score:.2f}, candidates={', '.join(candidate_symbols)}."
            ),
            as_of_date=as_of_date,
            data_quality=DataQuality.CONFIRMED,
            inference=True,
        )
    ]
    return SegmentAssessment(
        segment_name=segment,
        timing_score=timing_score,
        transmission_score=transmission_score,
        evidence=evidence,
        risks=risks,
        transmission_stage=stage,
        candidate_symbols=candidate_symbols,
        leading_indicators=leading_indicators,
        crowdedness_flags=crowdedness_flags,
    )


def _stage(cases: list[HistoricalCase], learning_result: ColdStartLearningResult) -> int:
    stage = 1 if any(case.packet.catalysts or case.packet.evidence for case in cases) else 0
    if len(cases) > 1:
        stage = max(stage, 2)
    if any(_observed(case, learning_result, "sig-fundamental-revenue-acceleration") for case in cases):
        stage = max(stage, 3)
    if any(_observed(case, learning_result, "sig-analyst-expectation-gap") for case in cases):
        stage = max(stage, 4)
    if any(_observed(case, learning_result, "sig-market-early-confirmation") for case in cases):
        stage = max(stage, 5)
    if any(_valuation_crowding(case) for case in cases):
        stage = max(stage, 7)
    return stage


def _leading_indicators(cases: list[HistoricalCase], learning_result: ColdStartLearningResult) -> list[str]:
    indicators = set()
    signal_to_indicator = {
        "sig-fundamental-revenue-acceleration": "revenue and earnings acceleration",
        "sig-market-early-confirmation": "relative strength and price momentum",
        "sig-analyst-expectation-gap": "analyst target-price revision gap",
        "sig-catalyst-density": "near-term catalyst calendar",
        "sig-valuation-room-with-growth": "growth-adjusted valuation room",
        "sig-liquidity-expansion": "dollar-volume expansion",
    }
    for case in cases:
        for observation in learning_result.observations_by_case.get(case.case_id, ()):
            if observation.observed and observation.signal_id in signal_to_indicator:
                indicators.add(signal_to_indicator[observation.signal_id])
        for catalyst in case.packet.catalysts:
            indicators.add(catalyst.name)
    return sorted(indicators)


def _segment_risks(cases: list[HistoricalCase], learning_result: ColdStartLearningResult) -> list[str]:
    risks = set()
    if any(case.label is CaseOutcomeLabel.FAILURE for case in cases):
        risks.add("Segment includes a cold-start failure case.")
    if any(_valuation_crowding(case) for case in cases):
        risks.add("Valuation may already discount a large part of the theme.")
    if not any(case.label is CaseOutcomeLabel.CONTROL for case in cases):
        risks.add("Segment lacks a matched neutral control in the cold-start sample.")
    if any(_observed(case, learning_result, "sig-catalyst-density") and case.label is not CaseOutcomeLabel.WINNER for case in cases):
        risks.add("Catalyst density appeared in a non-winner case.")
    return sorted(risks)


def _crowdedness_flags(cases: list[HistoricalCase], learning_result: ColdStartLearningResult) -> list[str]:
    flags = set()
    if any(_valuation_crowding(case) for case in cases):
        flags.add("valuation_stretch")
    if any(_observed(case, learning_result, "sig-market-early-confirmation") for case in cases):
        flags.add("market_confirmation_started")
    return sorted(flags)


def _observed(case: HistoricalCase, learning_result: ColdStartLearningResult, signal_id: str) -> bool:
    return any(
        observation.signal_id == signal_id and observation.observed
        for observation in learning_result.observations_by_case.get(case.case_id, ())
    )


def _catalyst_count(cases: list[HistoricalCase]) -> int:
    return sum(len(case.packet.catalysts) for case in cases)


def _valuation_crowding(case: HistoricalCase) -> bool:
    features = {feature.name: feature.value for feature in case.packet.features}
    pe = _numeric(features.get("valuation.pe_ratio"))
    ps = _numeric(features.get("valuation.price_to_sales_ttm"))
    return pe >= 40 or ps >= 8


def _numeric(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _slug(value: str) -> str:
    chars = [char.lower() if char.isalnum() else "-" for char in value.strip()]
    return "-".join(part for part in "".join(chars).split("-") if part)


def _title(theme_id: str) -> str:
    return " ".join(part.capitalize() for part in theme_id.replace("_", "-").split("-") if part)
