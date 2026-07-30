"""Walk-forward evaluation and paired admission statistics."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution_records import (
    AdmissionDecision,
    EvaluationSpec,
    EvolutionFold,
    FixedEvolutionSpec,
    LabeledSample,
    PredictionRecord,
    SchemeEvaluationResult,
    SchemeGenome,
)


def build_walk_forward_folds(
    samples: Iterable[LabeledSample],
    admission_starts: Iterable[datetime],
    *,
    fixed_spec: FixedEvolutionSpec,
    admission_window_days: int = 45,
) -> list[EvolutionFold]:
    """Build expanding folds with label-window purge/embargo and issuer isolation."""

    if admission_window_days < 1:
        raise ValidationError("admission_window_days must be positive")
    rows = sorted(samples, key=lambda item: (item.prediction_time, item.sample_id))
    folds: list[EvolutionFold] = []
    for index, start in enumerate(sorted(admission_starts), start=1):
        end = start + timedelta(days=admission_window_days)
        admission = [sample for sample in rows if start <= sample.prediction_time < end]
        admission_companies = {sample.company_key for sample in admission}
        discovery_cutoff = start - timedelta(
            days=(
                fixed_spec.label_spec.horizon_days
                + fixed_spec.split_spec.purge_days
                + fixed_spec.split_spec.embargo_days
            )
        )
        discovery = [
            sample
            for sample in rows
            if sample.prediction_time < discovery_cutoff
            and sample.company_key not in admission_companies
        ]
        if not discovery or not admission:
            continue
        folds.append(
            EvolutionFold(
                fold_id=f"walk-forward-{index:02d}-{start.date().isoformat()}",
                discovery_samples=discovery,
                admission_samples=admission,
                admission_start=start,
            )
        )
    return folds


def evaluate_predictions(
    genome: SchemeGenome,
    predictions: Iterable[PredictionRecord],
    labels: Mapping[str, int],
    metadata: Mapping[str, LabeledSample],
    *,
    spec: EvaluationSpec,
) -> SchemeEvaluationResult:
    """Compute deterministic binary, ranking, calibration, slice, cost, and utility metrics."""

    rows = list(predictions)
    if not rows:
        raise ValidationError("evaluation requires predictions")
    if {row.sample_id for row in rows} != set(labels):
        raise ValidationError("prediction ids must exactly match evaluation label ids")
    probabilities = [row.probability_of_surge for row in rows]
    y = [labels[row.sample_id] for row in rows]
    abstained = [row.binary_decision == "abstain" for row in rows]
    base = _binary_metrics(y, probabilities, abstained, spec)
    by_period = _slice_metrics(rows, labels, metadata, "period", spec)
    by_sector = _slice_metrics(rows, labels, metadata, "sector", spec)
    by_cap = _slice_metrics(rows, labels, metadata, "market_cap_bucket", spec)
    data_cost = sum(float(row.model_metadata.get("data_cost_usd", 0.0)) for row in rows)
    token_cost = sum(float(row.model_metadata.get("token_cost_usd", 0.0)) for row in rows)
    latency = sum(float(row.model_metadata.get("latency_ms", 0.0)) for row in rows)
    providers: dict[str, list[float]] = {}
    for row in rows:
        provider = str(row.model_metadata.get("provider", "unknown"))
        providers.setdefault(provider, []).append(row.probability_of_surge)
    sensitivity = {
        provider: round(sum(values) / len(values), 8)
        for provider, values in sorted(providers.items())
    }
    worst_period_f1 = min(
        (metrics["f1"] for metrics in by_period.values()),
        default=base["f1"],
    )
    complexity = _genome_complexity(genome)
    utility = _primary_utility(
        base,
        worst_period_f1=worst_period_f1,
        cost_usd=data_cost + token_cost,
        complexity=complexity,
        spec=spec,
    )
    intervals = _metric_confidence_intervals(y, probabilities, abstained, spec)
    return SchemeEvaluationResult(
        genome_id=genome.genome_id,
        sample_count=len(rows),
        confusion_matrix=base["confusion_matrix"],
        precision=base["precision"],
        recall=base["recall"],
        f1=base["f1"],
        pr_auc=base["pr_auc"],
        roc_auc=base["roc_auc"],
        brier_score=base["brier_score"],
        log_loss=base["log_loss"],
        precision_at_k=base["precision_at_k"],
        recall_at_k=base["recall_at_k"],
        coverage_rate=base["coverage_rate"],
        abstention_rate=base["abstention_rate"],
        metrics_by_time_period=by_period,
        metrics_by_sector=by_sector,
        metrics_by_market_cap_bucket=by_cap,
        model_provider_sensitivity=sensitivity,
        data_cost_usd=round(data_cost, 8),
        token_cost_usd=round(token_cost, 8),
        latency_ms=round(latency, 4),
        confidence_intervals=intervals,
        worst_period_f1=round(worst_period_f1, 8),
        primary_utility=round(utility, 8),
    )


def paired_admission_decision(
    incumbent_predictions: Iterable[PredictionRecord],
    candidate_predictions: Iterable[PredictionRecord],
    folds: Iterable[EvolutionFold],
    *,
    incumbent: SchemeEvaluationResult,
    candidate: SchemeEvaluationResult,
    spec: EvaluationSpec,
    candidate_complexity: float,
    incumbent_complexity: float,
) -> AdmissionDecision:
    """Block-bootstrap paired utility and apply fixed safety/cost gates."""

    incumbent_rows = {row.sample_id: row for row in incumbent_predictions}
    candidate_rows = {row.sample_id: row for row in candidate_predictions}
    if set(incumbent_rows) != set(candidate_rows):
        raise ValidationError("paired admission requires identical sample ids")
    sample_lookup = {
        sample.sample_id: sample
        for fold in folds
        for sample in fold.admission_samples
    }
    blocks: dict[str, list[str]] = {}
    for sample_id in sorted(candidate_rows):
        sample = sample_lookup[sample_id]
        block_value = getattr(sample, "period")
        blocks.setdefault(block_value, []).append(sample_id)
    reasons: list[str] = []
    if len(blocks) < spec.minimum_paired_blocks:
        reasons.append(
            f"insufficient paired blocks: {len(blocks)} < {spec.minimum_paired_blocks}"
        )
    differences = _paired_bootstrap_differences(
        incumbent_rows,
        candidate_rows,
        sample_lookup,
        blocks,
        spec=spec,
        incumbent_complexity=incumbent_complexity,
        candidate_complexity=candidate_complexity,
    )
    alpha = (1 - spec.confidence_level) / 2
    interval = [
        _quantile(differences, alpha),
        _quantile(differences, 1 - alpha),
    ]
    observed = candidate.primary_utility - incumbent.primary_utility
    if interval[0] <= 0:
        reasons.append("paired utility lower confidence bound is not above zero")
    degradation = incumbent.worst_period_f1 - candidate.worst_period_f1
    if degradation > spec.maximum_worst_period_degradation:
        reasons.append("worst-period degradation exceeds the fixed limit")
    if candidate.coverage_rate < spec.minimum_coverage:
        reasons.append("coverage is below the fixed floor")
    if candidate.data_cost_usd + candidate.token_cost_usd > spec.maximum_cost_usd:
        reasons.append("candidate cost exceeds the fixed evaluation budget")
    admitted = not reasons
    status = "admitted" if admitted else (
        "insufficient_evidence"
        if any(reason.startswith("insufficient paired blocks") for reason in reasons)
        else "rejected"
    )
    return AdmissionDecision(
        status=status,
        admitted=admitted,
        utility_difference=round(observed, 8),
        confidence_interval=[round(value, 8) for value in interval],
        paired_block_count=len(blocks),
        reasons=reasons,
    )


def _validate_folds(folds: Iterable[EvolutionFold], fixed_spec: FixedEvolutionSpec) -> None:
    seen_admission: set[str] = set()
    for fold in folds:
        cutoff = fold.admission_start - timedelta(
            days=(
                fixed_spec.label_spec.horizon_days
                + fixed_spec.split_spec.purge_days
                + fixed_spec.split_spec.embargo_days
            )
        )
        leaking = [
            sample.sample_id
            for sample in fold.discovery_samples
            if sample.prediction_time >= cutoff
        ]
        if leaking:
            raise ValidationError(
                f"fold {fold.fold_id} violates purge/embargo for discovery samples: {leaking}"
            )
        admission_ids = {sample.sample_id for sample in fold.admission_samples}
        if seen_admission & admission_ids:
            raise ValidationError("selected folds reuse admission samples")
        seen_admission.update(admission_ids)


def _binary_metrics(
    labels: list[int],
    probabilities: list[float],
    abstained: list[bool],
    spec: EvaluationSpec,
) -> dict[str, Any]:
    decisions = [probability >= spec.positive_threshold for probability in probabilities]
    tp = sum(label == 1 and decision and not abstain for label, decision, abstain in zip(labels, decisions, abstained))
    fp = sum(label == 0 and decision and not abstain for label, decision, abstain in zip(labels, decisions, abstained))
    tn = sum(label == 0 and not decision and not abstain for label, decision, abstain in zip(labels, decisions, abstained))
    fn = sum(label == 1 and not decision and not abstain for label, decision, abstain in zip(labels, decisions, abstained))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    positives = sum(labels)
    ranked = sorted(zip(probabilities, labels), reverse=True)
    k = min(spec.top_k, len(ranked))
    top_labels = [label for _probability, label in ranked[:k]]
    precision_at_k = sum(top_labels) / k if k else 0.0
    recall_at_k = sum(top_labels) / positives if positives else 0.0
    brier = sum((probability - label) ** 2 for probability, label in zip(probabilities, labels)) / len(labels)
    log_loss = -sum(
        label * math.log(min(1 - 1e-12, max(1e-12, probability)))
        + (1 - label) * math.log(min(1 - 1e-12, max(1e-12, 1 - probability)))
        for probability, label in zip(probabilities, labels)
    ) / len(labels)
    abstention_rate = sum(abstained) / len(abstained)
    return {
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision": round(precision, 8),
        "recall": round(recall, 8),
        "f1": round(f1, 8),
        "pr_auc": round(_average_precision(labels, probabilities), 8),
        "roc_auc": round(_roc_auc(labels, probabilities), 8),
        "brier_score": round(brier, 8),
        "log_loss": round(log_loss, 8),
        "precision_at_k": round(precision_at_k, 8),
        "recall_at_k": round(recall_at_k, 8),
        "coverage_rate": round(1 - abstention_rate, 8),
        "abstention_rate": round(abstention_rate, 8),
    }


def _slice_metrics(
    predictions: list[PredictionRecord],
    labels: Mapping[str, int],
    metadata: Mapping[str, LabeledSample],
    field_name: str,
    spec: EvaluationSpec,
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[PredictionRecord]] = {}
    for prediction in predictions:
        key = str(getattr(metadata[prediction.sample_id], field_name))
        grouped.setdefault(key, []).append(prediction)
    result: dict[str, dict[str, float]] = {}
    for key, rows in sorted(grouped.items()):
        values = _binary_metrics(
            [labels[row.sample_id] for row in rows],
            [row.probability_of_surge for row in rows],
            [row.binary_decision == "abstain" for row in rows],
            spec,
        )
        result[key] = {
            name: float(values[name])
            for name in ("precision", "recall", "f1", "brier_score", "coverage_rate")
        }
    return result


def _metric_confidence_intervals(
    labels: list[int],
    probabilities: list[float],
    abstained: list[bool],
    spec: EvaluationSpec,
) -> dict[str, list[float]]:
    import random

    randomizer = random.Random(spec.bootstrap_seed)
    values: dict[str, list[float]] = {"pr_auc": [], "brier_score": []}
    for _ in range(min(spec.bootstrap_replicates, 300)):
        indexes = [randomizer.randrange(len(labels)) for _ in labels]
        metrics = _binary_metrics(
            [labels[index] for index in indexes],
            [probabilities[index] for index in indexes],
            [abstained[index] for index in indexes],
            spec,
        )
        values["pr_auc"].append(metrics["pr_auc"])
        values["brier_score"].append(metrics["brier_score"])
    alpha = (1 - spec.confidence_level) / 2
    return {
        name: [
            round(_quantile(samples, alpha), 8),
            round(_quantile(samples, 1 - alpha), 8),
        ]
        for name, samples in values.items()
    }


def _paired_bootstrap_differences(
    incumbent: Mapping[str, PredictionRecord],
    candidate: Mapping[str, PredictionRecord],
    samples: Mapping[str, LabeledSample],
    blocks: Mapping[str, list[str]],
    *,
    spec: EvaluationSpec,
    incumbent_complexity: float,
    candidate_complexity: float,
) -> list[float]:
    import random

    randomizer = random.Random(spec.bootstrap_seed)
    block_names = sorted(blocks)
    differences: list[float] = []
    for _ in range(spec.bootstrap_replicates):
        chosen = [randomizer.choice(block_names) for _ in block_names]
        sample_ids = [sample_id for block in chosen for sample_id in blocks[block]]
        incumbent_utility = _sampled_utility(
            [incumbent[sample_id] for sample_id in sample_ids],
            samples,
            spec,
            complexity=incumbent_complexity,
        )
        candidate_utility = _sampled_utility(
            [candidate[sample_id] for sample_id in sample_ids],
            samples,
            spec,
            complexity=candidate_complexity,
        )
        differences.append(candidate_utility - incumbent_utility)
    return sorted(differences)


def _sampled_utility(
    rows: list[PredictionRecord],
    samples: Mapping[str, LabeledSample],
    spec: EvaluationSpec,
    *,
    complexity: float,
) -> float:
    labels = [samples[row.sample_id].label for row in rows]
    probabilities = [row.probability_of_surge for row in rows]
    metrics = _binary_metrics(
        labels,
        probabilities,
        [row.binary_decision == "abstain" for row in rows],
        spec,
    )
    by_period: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_period.setdefault(samples[row.sample_id].period, []).append(index)
    period_f1 = []
    for indexes in by_period.values():
        period_f1.append(
            _binary_metrics(
                [labels[index] for index in indexes],
                [probabilities[index] for index in indexes],
                [rows[index].binary_decision == "abstain" for index in indexes],
                spec,
            )["f1"]
        )
    cost = sum(
        float(row.model_metadata.get("data_cost_usd", 0.0))
        + float(row.model_metadata.get("token_cost_usd", 0.0))
        for row in rows
    )
    return _primary_utility(
        metrics,
        worst_period_f1=min(period_f1, default=metrics["f1"]),
        cost_usd=cost,
        complexity=complexity,
        spec=spec,
    )


def _primary_utility(
    metrics: Mapping[str, Any],
    *,
    worst_period_f1: float,
    cost_usd: float,
    complexity: float,
    spec: EvaluationSpec,
) -> float:
    values = {
        "pr_auc": float(metrics["pr_auc"]),
        "precision_at_k": float(metrics["precision_at_k"]),
        "recall_at_k": float(metrics["recall_at_k"]),
        "brier_score": float(metrics["brier_score"]),
        "worst_period_f1": worst_period_f1,
        "cost_usd": cost_usd,
        "complexity": complexity,
    }
    return sum(spec.utility_weights.get(name, 0.0) * value for name, value in values.items())


def _average_precision(labels: list[int], probabilities: list[float]) -> float:
    positives = sum(labels)
    if positives == 0:
        return 0.0
    ranked = sorted(zip(probabilities, labels), key=lambda item: item[0], reverse=True)
    true_positives = 0
    area = 0.0
    for rank, (_probability, label) in enumerate(ranked, start=1):
        if label:
            true_positives += 1
            area += true_positives / rank
    return area / positives


def _roc_auc(labels: list[int], probabilities: list[float]) -> float:
    positives = [probability for probability, label in zip(probabilities, labels) if label == 1]
    negatives = [probability for probability, label in zip(probabilities, labels) if label == 0]
    if not positives or not negatives:
        return 0.5
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return wins / (len(positives) * len(negatives))


def _genome_complexity(genome: SchemeGenome) -> float:
    return (
        len(genome.data_source_specs)
        + len(genome.seed_signal_specs)
        + float(genome.complexity_budget["max_context_tokens"]) / 1000
    )


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
