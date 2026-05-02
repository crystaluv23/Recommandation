"""Cold-start learning from labeled historical cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from stock_opportunity_agent.cases.outcomes import CaseOutcomeLabel
from stock_opportunity_agent.models import (
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    ResearchPacket,
    SignalDefinition,
    ValidationError,
)
from stock_opportunity_agent.signals import SignalObservation, SignalRule, default_signal_rules, measure_packet_signals


@dataclass(frozen=True)
class HistoricalCase:
    """One labeled historical case with a point-in-time packet.

    The first implementation expects labels and matched groups to be supplied
    by an outcome-definition and matching step. Automatic control construction
    is intentionally outside this learning function.
    """

    case_id: str
    label: CaseOutcomeLabel
    packet: ResearchPacket
    outcome_start_date: date
    outcome_end_date: date
    outcome_return: float | None
    matched_group_id: str
    hidden_outcome_summary: str
    outcome_definition_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.case_id, "case_id")
        _require_non_empty(self.matched_group_id, "matched_group_id")
        _require_non_empty(self.hidden_outcome_summary, "hidden_outcome_summary")
        if self.label is CaseOutcomeLabel.UNLABELED:
            raise ValidationError("historical learning cases must be winner, control, or failure")
        if self.outcome_end_date < self.outcome_start_date:
            raise ValidationError("outcome_end_date must be on or after outcome_start_date")
        if self.outcome_start_date <= self.packet.as_of.as_of_date:
            raise ValidationError("outcome_start_date must be after the packet as_of_date")


@dataclass(frozen=True)
class SignalCaseStats:
    """Aggregate signal behavior across winner and non-winner cases."""

    signal_id: str
    winner_count: int
    non_winner_count: int
    winner_hits: int
    non_winner_hits: int
    winner_prevalence: float
    non_winner_prevalence: float
    prevalence_lift: float
    winner_average_score: float
    non_winner_average_score: float
    average_score_lift: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible stats record."""

        return {
            "signal_id": self.signal_id,
            "winner_count": self.winner_count,
            "non_winner_count": self.non_winner_count,
            "winner_hits": self.winner_hits,
            "non_winner_hits": self.non_winner_hits,
            "winner_prevalence": self.winner_prevalence,
            "non_winner_prevalence": self.non_winner_prevalence,
            "prevalence_lift": self.prevalence_lift,
            "winner_average_score": self.winner_average_score,
            "non_winner_average_score": self.non_winner_average_score,
            "average_score_lift": self.average_score_lift,
        }


@dataclass(frozen=True)
class PreSurgeSignalLogic:
    """Cold-start signal logic learned from labeled historical cases."""

    signal_id: str
    name: str
    category: str
    description: str
    version: str
    logic: str
    source_feature_names: tuple[str, ...]
    statistics: SignalCaseStats
    positive_examples: tuple[str, ...]
    counterexamples: tuple[str, ...]
    false_positive_patterns: tuple[str, ...]
    hindsight_risk_notes: tuple[str, ...]
    promoted: bool
    promotion_reason: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible learned signal record."""

        return {
            "signal_id": self.signal_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "logic": self.logic,
            "source_feature_names": list(self.source_feature_names),
            "statistics": self.statistics.to_dict(),
            "positive_examples": list(self.positive_examples),
            "counterexamples": list(self.counterexamples),
            "false_positive_patterns": list(self.false_positive_patterns),
            "hindsight_risk_notes": list(self.hindsight_risk_notes),
            "promoted": self.promoted,
            "promotion_reason": self.promotion_reason,
        }


@dataclass(frozen=True)
class ColdStartLearningResult:
    """Cold-start case-learning output before persistence."""

    signal_logic: tuple[PreSurgeSignalLogic, ...]
    signal_definitions: tuple[SignalDefinition, ...]
    observations_by_case: dict[str, tuple[SignalObservation, ...]]
    warnings: tuple[str, ...]

    def observations_to_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Return case observations in JSON-compatible form."""

        return {
            case_id: [observation.to_dict() for observation in observations]
            for case_id, observations in sorted(self.observations_by_case.items())
        }


def learn_pre_surge_signal_logic(
    cases: Iterable[HistoricalCase],
    *,
    signal_version: str = "signals-v0.1",
    rules: tuple[SignalRule, ...] | None = None,
    min_winner_prevalence: float = 0.50,
    min_prevalence_lift: float = 0.25,
    min_average_score_lift: float = 0.15,
) -> ColdStartLearningResult:
    """Learn pre-surge signal logic from supplied labeled historical cases."""

    case_list = list(cases)
    if not case_list:
        raise ValidationError("cold-start learning requires at least one historical case")
    _require_score(min_winner_prevalence, "min_winner_prevalence")
    _require_score(min_prevalence_lift, "min_prevalence_lift")
    _require_score(min_average_score_lift, "min_average_score_lift")

    selected_rules = rules or default_signal_rules()
    observations_by_case = {
        case.case_id: tuple(measure_packet_signals(case.packet, selected_rules))
        for case in case_list
    }
    warnings = _case_warnings(case_list)
    logic = tuple(
        _build_signal_logic(
            rule,
            case_list,
            observations_by_case,
            signal_version=signal_version,
            min_winner_prevalence=min_winner_prevalence,
            min_prevalence_lift=min_prevalence_lift,
            min_average_score_lift=min_average_score_lift,
        )
        for rule in selected_rules
    )
    definitions = tuple(
        _to_signal_definition(signal, case_list)
        for signal in logic
        if signal.promoted
    )
    return ColdStartLearningResult(
        signal_logic=logic,
        signal_definitions=definitions,
        observations_by_case=observations_by_case,
        warnings=warnings,
    )


def _build_signal_logic(
    rule: SignalRule,
    cases: list[HistoricalCase],
    observations_by_case: dict[str, tuple[SignalObservation, ...]],
    *,
    signal_version: str,
    min_winner_prevalence: float,
    min_prevalence_lift: float,
    min_average_score_lift: float,
) -> PreSurgeSignalLogic:
    observations = {
        case.case_id: _observation_for_signal(observations_by_case[case.case_id], rule.signal_id)
        for case in cases
    }
    winners = [case for case in cases if case.label is CaseOutcomeLabel.WINNER]
    non_winners = [case for case in cases if case.label is not CaseOutcomeLabel.WINNER]
    stats = _stats(rule.signal_id, winners, non_winners, observations)
    positive_examples = tuple(
        case.case_id
        for case in winners
        if observations[case.case_id].observed
    )
    counterexamples = tuple(
        case.case_id
        for case in non_winners
        if observations[case.case_id].observed
    )
    promoted, reason = _promotion_decision(
        stats,
        has_control=any(case.label is CaseOutcomeLabel.CONTROL for case in cases),
        min_winner_prevalence=min_winner_prevalence,
        min_prevalence_lift=min_prevalence_lift,
        min_average_score_lift=min_average_score_lift,
    )
    return PreSurgeSignalLogic(
        signal_id=rule.signal_id,
        name=rule.name,
        category=rule.category,
        description=rule.description,
        version=signal_version,
        logic=rule.logic,
        source_feature_names=rule.feature_names,
        statistics=stats,
        positive_examples=positive_examples,
        counterexamples=counterexamples,
        false_positive_patterns=rule.false_positive_patterns,
        hindsight_risk_notes=rule.hindsight_risk_notes,
        promoted=promoted,
        promotion_reason=reason,
    )


def _stats(
    signal_id: str,
    winners: list[HistoricalCase],
    non_winners: list[HistoricalCase],
    observations: dict[str, SignalObservation],
) -> SignalCaseStats:
    winner_scores = [observations[case.case_id].score for case in winners]
    non_winner_scores = [observations[case.case_id].score for case in non_winners]
    winner_hits = sum(1 for case in winners if observations[case.case_id].observed)
    non_winner_hits = sum(1 for case in non_winners if observations[case.case_id].observed)
    winner_prevalence = _safe_ratio(winner_hits, len(winners))
    non_winner_prevalence = _safe_ratio(non_winner_hits, len(non_winners))
    winner_average = _average(winner_scores)
    non_winner_average = _average(non_winner_scores)
    return SignalCaseStats(
        signal_id=signal_id,
        winner_count=len(winners),
        non_winner_count=len(non_winners),
        winner_hits=winner_hits,
        non_winner_hits=non_winner_hits,
        winner_prevalence=round(winner_prevalence, 4),
        non_winner_prevalence=round(non_winner_prevalence, 4),
        prevalence_lift=round(winner_prevalence - non_winner_prevalence, 4),
        winner_average_score=round(winner_average, 4),
        non_winner_average_score=round(non_winner_average, 4),
        average_score_lift=round(winner_average - non_winner_average, 4),
    )


def _promotion_decision(
    stats: SignalCaseStats,
    *,
    has_control: bool,
    min_winner_prevalence: float,
    min_prevalence_lift: float,
    min_average_score_lift: float,
) -> tuple[bool, str]:
    if stats.winner_count == 0:
        return False, "not promoted: no winner cases were supplied"
    if stats.non_winner_count == 0:
        return False, "not promoted: no control or failure cases were supplied"
    if not has_control:
        return False, "not promoted: at least one matched control is required"
    if stats.winner_prevalence < min_winner_prevalence:
        return False, "not promoted: winner prevalence below threshold"
    if stats.prevalence_lift < min_prevalence_lift:
        return False, "not promoted: winner/non-winner prevalence lift below threshold"
    if stats.average_score_lift < min_average_score_lift:
        return False, "not promoted: winner/non-winner average score lift below threshold"
    return True, "promoted: passed prevalence, lift, and control-evidence gates"


def _to_signal_definition(
    signal: PreSurgeSignalLogic,
    cases: list[HistoricalCase],
) -> SignalDefinition:
    sectors = sorted(
        {
            case.packet.company.sector
            for case in cases
            if case.label is CaseOutcomeLabel.WINNER and case.case_id in signal.positive_examples
        }
    )
    evidence = EvidenceItem(
        kind=EvidenceKind.INFERENCE,
        summary=(
            f"Cold-start case comparison: winner prevalence {signal.statistics.winner_prevalence:.2f}, "
            f"non-winner prevalence {signal.statistics.non_winner_prevalence:.2f}, "
            f"average score lift {signal.statistics.average_score_lift:.2f}."
        ),
        as_of_date=max(case.packet.as_of.as_of_date for case in cases),
        data_quality=DataQuality.CONFIRMED,
        inference=True,
    )
    false_positive_patterns = list(signal.false_positive_patterns)
    if signal.counterexamples:
        false_positive_patterns.append(
            "Observed in non-winner cases: " + ", ".join(signal.counterexamples)
        )
    return SignalDefinition(
        signal_id=signal.signal_id,
        name=signal.name,
        description=f"{signal.description} Logic: {signal.logic}",
        version=signal.version,
        applicable_sectors=sectors or ["Unknown"],
        false_positive_patterns=false_positive_patterns,
        evidence=[evidence],
    )


def _observation_for_signal(
    observations: tuple[SignalObservation, ...],
    signal_id: str,
) -> SignalObservation:
    for observation in observations:
        if observation.signal_id == signal_id:
            return observation
    raise ValidationError(f"signal observation missing for {signal_id}")


def _case_warnings(cases: list[HistoricalCase]) -> tuple[str, ...]:
    warnings: list[str] = []
    labels = {case.label for case in cases}
    if CaseOutcomeLabel.WINNER not in labels:
        warnings.append("No winner cases supplied; no signal can be promoted.")
    if CaseOutcomeLabel.CONTROL not in labels:
        warnings.append("No matched control cases supplied; signals will not be promoted.")
    groups = {case.matched_group_id for case in cases}
    for group_id in sorted(groups):
        group = [case for case in cases if case.matched_group_id == group_id]
        group_labels = {case.label for case in group}
        if CaseOutcomeLabel.WINNER in group_labels and CaseOutcomeLabel.CONTROL not in group_labels:
            warnings.append(f"Matched group {group_id} has a winner but no control.")
    return tuple(warnings)


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValidationError(f"{name} must not be empty")


def _require_score(value: float, name: str) -> None:
    if not 0 <= value <= 1:
        raise ValidationError(f"{name} must be between 0 and 1")
