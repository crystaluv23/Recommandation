"""Fixed A/B/C label generation, walk-forward construction, and evaluation."""

from __future__ import annotations

import calendar
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution_records import (
    EvaluationContract,
    EvolutionFold,
    FixedEvolutionSpec,
    LabeledSample,
    OUTCOME_CLASSES,
    PredictionRecord,
    SchemeEvaluationResult,
    SchemeGenome,
)


def realized_max_multiple(
    prediction_adjusted_close: float,
    future_adjusted_closes: Sequence[float],
    *,
    smoothing_window_days: int = 5,
) -> float:
    """Return the maximum complete-window moving average divided by start price.

    The prediction-date close is the denominator. Only complete future windows
    are eligible, so a single isolated price spike cannot define the label.
    """

    if prediction_adjusted_close <= 0:
        raise ValidationError("prediction_adjusted_close must be positive")
    if smoothing_window_days < 1:
        raise ValidationError("smoothing_window_days must be positive")
    prices = [float(value) for value in future_adjusted_closes]
    if len(prices) < smoothing_window_days:
        raise ValidationError("future price history is shorter than the smoothing window")
    if any(value <= 0 for value in prices):
        raise ValidationError("future adjusted closes must be positive")
    moving_averages = [
        sum(prices[index : index + smoothing_window_days]) / smoothing_window_days
        for index in range(len(prices) - smoothing_window_days + 1)
    ]
    return max(moving_averages) / prediction_adjusted_close


def build_labeled_sample(
    *,
    sample_id: str,
    company_key: str,
    prediction_time: datetime,
    prediction_adjusted_close: float,
    future_adjusted_closes: Sequence[float],
    sector: str,
    market_cap_bucket: str,
    period: str,
    features: Mapping[str, float],
    evidence_source_ids: Sequence[str],
    document_available_dates: Sequence[Any],
    contract: EvaluationContract,
) -> LabeledSample:
    """Build a sample while keeping continuous and derived labels together."""

    multiple = realized_max_multiple(
        prediction_adjusted_close,
        future_adjusted_closes,
        smoothing_window_days=contract.smoothing_window_days,
    )
    true_class = contract.classify(multiple)
    return LabeledSample(
        sample_id=sample_id,
        company_key=company_key,
        prediction_time=prediction_time,
        realized_max_multiple=multiple,
        true_class=true_class,
        is_surge=contract.is_positive(true_class),
        sector=sector,
        market_cap_bucket=market_cap_bucket,
        period=period,
        features=dict(features),
        evidence_source_ids=list(evidence_source_ids),
        document_available_dates=list(document_available_dates),
    )


def build_walk_forward_folds(
    samples: Iterable[LabeledSample],
    admission_starts: Iterable[datetime],
    *,
    fixed_spec: FixedEvolutionSpec,
    admission_window_days: int = 45,
) -> list[EvolutionFold]:
    """Build expanding folds with full label horizon, purge, embargo, and issuer isolation."""

    if admission_window_days < 1:
        raise ValidationError("admission_window_days must be positive")
    rows = sorted(samples, key=lambda item: (item.prediction_time, item.sample_id))
    folds: list[EvolutionFold] = []
    for index, start in enumerate(sorted(admission_starts), start=1):
        end = start + timedelta(days=admission_window_days)
        admission = [sample for sample in rows if start <= sample.prediction_time < end]
        admission_companies = {sample.company_key for sample in admission}
        discovery = [
            sample
            for sample in rows
            if _label_observation_end(sample, fixed_spec) < start
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
    labels: Mapping[str, LabeledSample],
) -> SchemeEvaluationResult:
    """Compute fixed binary-F1 selection and ordinal multiclass diagnostics."""

    rows = list(predictions)
    if not rows:
        raise ValidationError("evaluation requires predictions")
    if {row.sample_id for row in rows} != set(labels):
        raise ValidationError("prediction ids must exactly match evaluation label ids")
    binary = _binary_metrics(
        [labels[row.sample_id].is_surge for row in rows],
        [row.is_surge for row in rows],
    )
    multiclass = _multiclass_metrics(
        [labels[row.sample_id].true_class for row in rows],
        [row.predicted_class for row in rows],
    )
    errors = _error_cases(rows, labels)
    data_cost = sum(float(row.model_metadata.get("data_cost_usd", 0.0)) for row in rows)
    token_cost = sum(float(row.model_metadata.get("token_cost_usd", 0.0)) for row in rows)
    latency = sum(float(row.model_metadata.get("latency_ms", 0.0)) for row in rows)
    return SchemeEvaluationResult(
        genome_id=genome.genome_id,
        sample_count=len(rows),
        confusion_matrix=binary["confusion_matrix"],
        binary_precision=binary["precision"],
        binary_recall=binary["recall"],
        binary_f1=binary["f1"],
        multiclass_confusion_matrix=multiclass["confusion_matrix"],
        per_class_recall=multiclass["per_class_recall"],
        multiclass_macro_f1=multiclass["macro_f1"],
        class_c_recall=multiclass["per_class_recall"]["C"],
        ordinal_distance=multiclass["ordinal_distance"],
        error_cases=errors,
        reflection_summary=_reflection_summary(rows, labels, errors),
        predictions_by_sample={row.sample_id: row.predicted_class for row in rows},
        binary_predictions_by_sample={row.sample_id: row.is_surge for row in rows},
        metrics_by_time_period=_slice_metrics(rows, labels, "period"),
        metrics_by_sector=_slice_metrics(rows, labels, "sector"),
        metrics_by_market_cap_bucket=_slice_metrics(rows, labels, "market_cap_bucket"),
        data_cost_usd=round(data_cost, 8),
        token_cost_usd=round(token_cost, 8),
        latency_ms=round(latency, 4),
    )


def validate_folds(folds: Iterable[EvolutionFold], fixed_spec: FixedEvolutionSpec) -> None:
    """Reject invalid time isolation, issuer leakage, or unsupported binary metrics."""

    seen_admission: set[str] = set()
    for fold in folds:
        leaking = [
            sample.sample_id
            for sample in fold.discovery_samples
            if _label_observation_end(sample, fixed_spec) >= fold.admission_start
        ]
        if leaking:
            raise ValidationError(
                f"fold {fold.fold_id} violates horizon/purge/embargo: {leaking}"
            )
        discovery_companies = {sample.company_key for sample in fold.discovery_samples}
        admission_companies = {sample.company_key for sample in fold.admission_samples}
        if discovery_companies & admission_companies:
            raise ValidationError("discovery and validation issuers overlap")
        admission_ids = {sample.sample_id for sample in fold.admission_samples}
        if seen_admission & admission_ids:
            raise ValidationError("selected folds reuse validation samples")
        seen_admission.update(admission_ids)
        for partition_name, samples in (
            ("signal-train", fold.discovery_samples),
            ("development validation", fold.admission_samples),
        ):
            binary_classes = {sample.is_surge for sample in samples}
            if binary_classes != {False, True}:
                raise ValidationError(
                    f"fold {fold.fold_id} {partition_name} requires both A and B/C classes"
                )


def prediction_agreement(
    left: Mapping[str, bool],
    right: Mapping[str, bool],
) -> float | None:
    """Return paired binary behavior agreement, or ``None`` for unmatched samples."""

    if set(left) != set(right) or not left:
        return None
    return sum(left[key] == right[key] for key in left) / len(left)


def _label_observation_end(sample: LabeledSample, fixed_spec: FixedEvolutionSpec) -> datetime:
    horizon_end = _add_months(
        sample.prediction_time,
        fixed_spec.evaluation_contract.horizon_months,
    )
    return horizon_end + timedelta(
        days=fixed_spec.split_spec.purge_days + fixed_spec.split_spec.embargo_days
    )


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _binary_metrics(labels: Sequence[bool], predictions: Sequence[bool]) -> dict[str, Any]:
    tp = sum(label and prediction for label, prediction in zip(labels, predictions))
    fp = sum(not label and prediction for label, prediction in zip(labels, predictions))
    tn = sum(not label and not prediction for label, prediction in zip(labels, predictions))
    fn = sum(label and not prediction for label, prediction in zip(labels, predictions))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision": round(precision, 8),
        "recall": round(recall, 8),
        "f1": round(f1, 8),
    }


def _multiclass_metrics(
    labels: Sequence[str],
    predictions: Sequence[str],
) -> dict[str, Any]:
    confusion = {
        actual: {predicted: 0 for predicted in OUTCOME_CLASSES}
        for actual in OUTCOME_CLASSES
    }
    for actual, predicted in zip(labels, predictions):
        confusion[actual][predicted] += 1
    recalls: dict[str, float] = {}
    f1_values: list[float] = []
    for outcome_class in OUTCOME_CLASSES:
        tp = confusion[outcome_class][outcome_class]
        false_negatives = sum(confusion[outcome_class].values()) - tp
        false_positives = sum(
            confusion[actual][outcome_class]
            for actual in OUTCOME_CLASSES
            if actual != outcome_class
        )
        recall = tp / (tp + false_negatives) if tp + false_negatives else 0.0
        precision = tp / (tp + false_positives) if tp + false_positives else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        recalls[outcome_class] = round(recall, 8)
        f1_values.append(f1)
    ordinal = {"A": 0, "B": 1, "C": 2}
    distance = sum(
        abs(ordinal[actual] - ordinal[predicted])
        for actual, predicted in zip(labels, predictions)
    ) / len(labels)
    return {
        "confusion_matrix": confusion,
        "per_class_recall": recalls,
        "macro_f1": round(sum(f1_values) / len(f1_values), 8),
        "ordinal_distance": round(distance, 8),
    }


def _error_cases(
    predictions: Sequence[PredictionRecord],
    labels: Mapping[str, LabeledSample],
) -> list[dict[str, Any]]:
    ordinal = {"A": 0, "B": 1, "C": 2}
    errors: list[dict[str, Any]] = []
    for row in predictions:
        actual = labels[row.sample_id]
        if row.predicted_class == actual.true_class:
            continue
        if actual.is_surge and not row.is_surge:
            failure_type = "class_c_miss" if actual.true_class == "C" else "false_negative"
        elif not actual.is_surge and row.is_surge:
            failure_type = "false_positive"
        else:
            failure_type = "ordinal_misclassification"
        errors.append(
            {
                "sample_id": row.sample_id,
                "true_class": actual.true_class,
                "predicted_class": row.predicted_class,
                "is_surge": actual.is_surge,
                "ordinal_error": abs(
                    ordinal[actual.true_class] - ordinal[row.predicted_class]
                ),
                "realized_max_multiple": actual.realized_max_multiple,
                "failure_type": failure_type,
                "confidence_level": row.confidence_level,
                "difficulty_level": row.difficulty_level,
                "difficulty_reasons": list(row.difficulty_reasons),
                "conflicting_signals": list(row.conflicting_signals),
                "missing_information": list(row.missing_information),
            }
        )
    return sorted(
        errors,
        key=lambda row: (-row["ordinal_error"], -row["realized_max_multiple"], row["sample_id"]),
    )


def _reflection_summary(
    rows: Sequence[PredictionRecord],
    labels: Mapping[str, LabeledSample],
    errors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    correct_by_confidence: Counter[str] = Counter()
    count_by_confidence: Counter[str] = Counter()
    errors_by_difficulty: Counter[str] = Counter()
    count_by_difficulty: Counter[str] = Counter()
    for row in rows:
        actual = labels[row.sample_id]
        count_by_confidence[row.confidence_level] += 1
        count_by_difficulty[row.difficulty_level] += 1
        if row.predicted_class == actual.true_class:
            correct_by_confidence[row.confidence_level] += 1
        else:
            errors_by_difficulty[row.difficulty_level] += 1
    return {
        "failure_type_counts": dict(Counter(row["failure_type"] for row in errors)),
        "common_difficulty_reasons": _common_strings(
            value for row in errors for value in row["difficulty_reasons"]
        ),
        "common_conflicting_signals": _common_strings(
            value for row in errors for value in row["conflicting_signals"]
        ),
        "common_missing_information": _common_strings(
            value for row in errors for value in row["missing_information"]
        ),
        "accuracy_by_confidence": {
            key: round(correct_by_confidence[key] / count, 8)
            for key, count in sorted(count_by_confidence.items())
        },
        "error_rate_by_difficulty": {
            key: round(errors_by_difficulty[key] / count, 8)
            for key, count in sorted(count_by_difficulty.items())
        },
    }


def _common_strings(values: Iterable[str], limit: int = 10) -> list[dict[str, Any]]:
    counts = Counter(value.strip() for value in values if value.strip())
    return [
        {"value": value, "count": count}
        for value, count in counts.most_common(limit)
    ]


def _slice_metrics(
    predictions: Sequence[PredictionRecord],
    labels: Mapping[str, LabeledSample],
    field_name: str,
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[PredictionRecord]] = {}
    for prediction in predictions:
        key = str(getattr(labels[prediction.sample_id], field_name))
        grouped.setdefault(key, []).append(prediction)
    result: dict[str, dict[str, float]] = {}
    for key, rows in sorted(grouped.items()):
        metrics = _binary_metrics(
            [labels[row.sample_id].is_surge for row in rows],
            [row.is_surge for row in rows],
        )
        result[key] = {
            "binary_precision": metrics["precision"],
            "binary_recall": metrics["recall"],
            "binary_f1": metrics["f1"],
        }
    return result


def _genome_complexity(genome: SchemeGenome) -> float:
    """Return a deterministic diagnostic complexity score."""

    return (
        len(genome.data_source_specs)
        + len(genome.seed_signal_specs)
        + float(genome.complexity_budget["max_context_tokens"]) / 1000
    )
