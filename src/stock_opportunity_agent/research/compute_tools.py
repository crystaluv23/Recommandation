"""Closed deterministic computation registry exposed as an LLM tool.

Computation before interpretation, generalized: the model chooses which
registered metric to compute and supplies bounded parameters, but never
writes a formula. The runtime computes closed-form statistics over
point-in-time documents and returns a computed card whose numbers carry
literal references to the underlying observations. Cards are citable
verbatim like the evaluation anchor; restated or derived arithmetic stays
the model's forbidden territory.

Every function here is pure over immutable documents plus the supplied
cutoff, so results replay deterministically offline.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.models import ValidationError

MARKET_SOURCE_TYPES = {
    "historical_price",
    "market_data",
    "price_daily",
    "prices",
}

COMPUTE_SCHEMA_VERSION = "computed-metric-card-v1"
_MAX_METRICS_PER_REQUEST = 2

# Human-readable labels for computed values: the model sees prose, not JSON
# keys, so computed results are consumed as narrative facts rather than
# miscited as raw evidence spans.
_VALUE_LABELS = {
    "window_trading_days": "window trading days",
    "first_close": "first close",
    "last_close": "last close",
    "high": "high",
    "low": "low",
    "return_pct": "return",
    "max_drawdown_pct": "max drawdown",
    "daily_volatility_pct": "daily volatility",
    "from_date": "from date",
    "from_close": "from close",
    "to_date": "to date",
    "to_close": "to close",
    "anchor_mean": "anchor mean",
    "multiple": "multiple",
    "derived_threshold": "derived threshold",
    "recent_close": "recent close",
    "recent_close_date": "recent close date",
    "gap_pct": "gap to threshold",
}
_LABEL_LABELS = {
    "trend": "trend",
    "crossing": "crossing",
}
_METRIC_TITLES = {
    "price_shape": "price shape",
    "return_between": "period return",
    "distance_to_threshold": "distance to threshold",
}


def format_computed_card_readable(card: Mapping[str, Any]) -> str:
    """Format one computed metric card as readable prose for model context.

    The JSON structure stays authoritative for audit and replay; the
    model-facing view is a single declarative sentence per metric so
    computed results are consumed as narrative control data, not cited
    as evidence exact_text spans.
    """

    metric = str(card.get("metric", "metric"))
    title = _METRIC_TITLES.get(metric, metric.replace("_", " "))
    params = card.get("params", {})
    parts: list[str] = []
    for key, value in card.get("values", {}).items():
        label = _VALUE_LABELS.get(key, key.replace("_", " "))
        if isinstance(value, float):
            if "pct" in key:
                parts.append(f"{label} {value:.2f}%")
            elif "close" in key or "high" in key or "low" in key or "threshold" in key:
                parts.append(f"{label} ${value:.2f}" if value > 1 else f"{label} {value:.4f}")
            else:
                parts.append(f"{label} {value:g}")
        else:
            parts.append(f"{label} {value}")
    for key, value in card.get("labels", {}).items():
        label = _LABEL_LABELS.get(key, key.replace("_", " "))
        parts.append(f"{label} {value}")
    param_suffix = ""
    if params:
        param_parts = [
            f"{key.replace('_', ' ')} {value}" for key, value in params.items()
        ]
        param_suffix = f" ({', '.join(param_parts)})"
    return f"{title}{param_suffix}: {'; '.join(parts)}."

# Closed, versioned registry. The model may request any entry with bounded
# parameters; the formulas live here and nowhere else.
COMPUTE_METRIC_REGISTRY: dict[str, dict[str, Any]] = {
    "price_shape": {
        "description": (
            "Closed-form price statistics over the trailing window: first and "
            "last close, high, low, window return percent, max drawdown "
            "percent, daily-return volatility, and a fixed-vocabulary trend "
            "label (uptrend/downtrend/range)."
        ),
        "params": {"window_days": (30, 365)},
        "requires_anchor": False,
    },
    "return_between": {
        "description": (
            "Percent return between two trailing trading-day offsets measured "
            "back from the most recent close (from_offset_days is the earlier "
            "boundary, to_offset_days the later one)."
        ),
        "params": {
            "from_offset_days": (1, 365),
            "to_offset_days": (0, 364),
        },
        "requires_anchor": False,
    },
    "distance_to_threshold": {
        "description": (
            "Distance of the most recent close to a multiple of the runtime "
            "evaluation anchor mean: derived threshold, gap percent, and a "
            "fixed-vocabulary crossing label (below_threshold/above_threshold)."
        ),
        "params": {"multiple": (1.0, 10.0)},
        "requires_anchor": True,
    },
}


def collect_adjusted_close_bars(
    documents: Iterable[RawInfoDocument], prediction_time: datetime
) -> dict[str, float]:
    """Collect PIT adjusted closes keyed by date across market documents."""

    bars: dict[str, float] = {}
    for document in documents:
        if document.source_type not in MARKET_SOURCE_TYPES:
            continue
        if document.available_at > prediction_time:
            raise ValidationError(
                "computation input document is not point-in-time"
            )
        for match in re.finditer(r"\{[^{}]*\}", document.content):
            try:
                value = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            if not isinstance(value, Mapping):
                continue
            raw_date = value.get("as_of_date")
            raw_close = value.get("adjusted_close")
            if (
                not isinstance(raw_date, str)
                or isinstance(raw_close, bool)
                or not isinstance(raw_close, (int, float))
                or not math.isfinite(float(raw_close))
                or float(raw_close) <= 0
            ):
                continue
            try:
                datetime.fromisoformat(raw_date)
            except ValueError:
                continue
            existing = bars.get(raw_date)
            close = float(raw_close)
            if existing is not None and not math.isclose(
                existing, close, rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValidationError(
                    "conflicting adjusted-close values in computation inputs "
                    f"for {raw_date}"
                )
            bars[raw_date] = close
    return bars


def _sorted_bars(bars: Mapping[str, float]) -> list[tuple[str, float]]:
    return sorted(bars.items())


def _validate_params(metric_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
    entry = COMPUTE_METRIC_REGISTRY.get(metric_id)
    if entry is None:
        raise ValidationError(
            "compute metric is not registered: "
            + ", ".join(sorted(COMPUTE_METRIC_REGISTRY))
        )
    if not isinstance(params, Mapping):
        raise ValidationError("compute params must be an object")
    if set(params) != set(entry["params"]):
        raise ValidationError(
            f"compute metric {metric_id} params must be exactly "
            f"{sorted(entry['params'])}"
        )
    validated: dict[str, Any] = {}
    for name, (low, high) in entry["params"].items():
        value = params[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(
                f"compute param {metric_id}.{name} must be numeric"
            )
        if not low <= float(value) <= high:
            raise ValidationError(
                f"compute param {metric_id}.{name} must be within "
                f"[{low}, {high}]"
            )
        validated[name] = type(low)(value) if isinstance(low, int) else float(value)
    return validated


def compute_metric(
    metric_id: str,
    params: Mapping[str, Any],
    *,
    documents: Iterable[RawInfoDocument],
    as_of: datetime,
    anchor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute one registered metric and return its citable card.

    Usage example:

        card = compute_metric(
            "price_shape", {"window_days": 180},
            documents=market_docs, as_of=prediction_time,
        )
        card["values"]["return_pct"], card["labels"]["trend"]
    """

    validated = _validate_params(metric_id, params)
    bars = collect_adjusted_close_bars(documents, as_of)
    series = _sorted_bars(bars)
    pit_series = [
        (date, close)
        for date, close in series
        if datetime.fromisoformat(date).date() < as_of.date()
    ]
    if len(pit_series) < 2:
        raise ValidationError(
            "compute metric requires at least two point-in-time closes"
        )
    card: dict[str, Any] = {
        "schema_version": COMPUTE_SCHEMA_VERSION,
        "metric": metric_id,
        "params": validated,
        "as_of": as_of.isoformat(),
        "values": {},
        "labels": {},
        "literal_refs": [],
    }
    if metric_id == "price_shape":
        window = validated["window_days"]
        # Trading-day lookback: take the trailing window of PIT closes.
        window_series = pit_series[-window:]
        if len(window_series) < 2:
            raise ValidationError("price_shape window has fewer than two closes")
        closes = [close for _date, close in window_series]
        peak = closes[0]
        max_drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            if peak > 0:
                max_drawdown = min(max_drawdown, close / peak - 1.0)
        returns = [
            closes[index] / closes[index - 1] - 1.0
            for index in range(1, len(closes))
            if closes[index - 1] > 0
        ]
        volatility = (
            math.sqrt(
                sum((item - (sum(returns) / len(returns))) ** 2 for item in returns)
                / len(returns)
            )
            if returns
            else 0.0
        )
        return_pct = closes[-1] / closes[0] - 1.0
        card["values"] = {
            "window_trading_days": len(window_series),
            "first_close": closes[0],
            "last_close": closes[-1],
            "high": max(closes),
            "low": min(closes),
            "return_pct": round(return_pct * 100.0, 4),
            "max_drawdown_pct": round(max_drawdown * 100.0, 4),
            "daily_volatility_pct": round(volatility * 100.0, 4),
        }
        card["labels"] = {
            "trend": (
                "uptrend"
                if return_pct >= 0.20
                else "downtrend" if return_pct <= -0.20 else "range"
            )
        }
        card["literal_refs"] = [
            {"as_of_date": date, "adjusted_close": close}
            for date, close in (window_series[0], window_series[-1])
        ]
        return card
    if metric_id == "return_between":
        from_offset = validated["from_offset_days"]
        to_offset = validated["to_offset_days"]
        if from_offset <= to_offset:
            raise ValidationError(
                "return_between requires from_offset_days > to_offset_days"
            )
        if from_offset > len(pit_series):
            raise ValidationError(
                "return_between from_offset exceeds available history"
            )
        earlier = pit_series[-from_offset]
        later = pit_series[-(to_offset + 1)] if to_offset > 0 else pit_series[-1]
        card["values"] = {
            "from_date": earlier[0],
            "from_close": earlier[1],
            "to_date": later[0],
            "to_close": later[1],
            "return_pct": round((later[1] / earlier[1] - 1.0) * 100.0, 4),
        }
        card["literal_refs"] = [
            {"as_of_date": earlier[0], "adjusted_close": earlier[1]},
            {"as_of_date": later[0], "adjusted_close": later[1]},
        ]
        return card
    if metric_id == "distance_to_threshold":
        if not isinstance(anchor, Mapping) or anchor.get("status") != "available":
            raise ValidationError(
                "distance_to_threshold requires an available evaluation anchor"
            )
        mean = anchor.get("mean_adjusted_close")
        if isinstance(mean, bool) or not isinstance(mean, (int, float)):
            raise ValidationError("evaluation anchor mean is invalid")
        multiple = validated["multiple"]
        threshold = multiple * float(mean)
        last = pit_series[-1]
        ratio = last[1] / threshold
        card["values"] = {
            "anchor_mean": float(mean),
            "multiple": multiple,
            "derived_threshold": threshold,
            "recent_close": last[1],
            "recent_close_date": last[0],
            "gap_pct": round((ratio - 1.0) * 100.0, 4),
        }
        card["labels"] = {
            "crossing": "above_threshold" if ratio >= 1.0 else "below_threshold"
        }
        card["literal_refs"] = [
            {"as_of_date": last[0], "adjusted_close": last[1]},
            {"source": "evaluation_anchor.mean_adjusted_close", "value": float(mean)},
        ]
        return card
    raise ValidationError("compute metric implementation is missing")


def compute_metric_requests(
    entries: Iterable[Mapping[str, Any]],
    *,
    documents: Iterable[RawInfoDocument],
    as_of: datetime,
    anchor: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Validate and compute one bounded batch of model-requested metrics."""

    rows = tuple(entries)
    if not rows or len(rows) > _MAX_METRICS_PER_REQUEST:
        raise ValidationError(
            "compute requests must contain between 1 and "
            f"{_MAX_METRICS_PER_REQUEST} metrics"
        )
    return [
        compute_metric(
            str(row.get("metric")),
            row.get("params") if isinstance(row.get("params"), Mapping) else {},
            documents=documents,
            as_of=as_of,
            anchor=anchor,
        )
        for row in rows
    ]
