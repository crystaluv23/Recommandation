"""Frozen constants shared by evolution runtime layers."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable
from stock_opportunity_agent.data.acquisition import (
    AlphaVantageNewsAdapter,
    AlphaVantageTranscriptAdapter,
    HistoricalPriceAdapter,
    SecCompanyFactsAdapter,
    SecFilingAdapter,
)
from stock_opportunity_agent.data.resolution import source_types_compatible


_FORBIDDEN_OUTCOME_KEYS = frozenset(
    {
        "ground_truth",
        "outcome",
        "outcome_label",
        "label",
        "is_surge",
        "magnitude_class",
        "realized_return",
        "realized_max_multiple",
        "future_price",
        "future_return",
        "post_outcome",
    }
)


MAX_LLM_SIGNAL_CONTEXT_CHARS = 32_000


LLM_SIGNAL_CONTEXT_CHUNK_CHARS = 2_000


LLM_SIGNAL_CONTEXT_CHUNK_OVERLAP = 200


_LLM_SIGNAL_QUERY_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "if",
        "in",
        "into",
        "is",
        "it",
        "not",
        "of",
        "on",
        "only",
        "or",
        "return",
        "signal",
        "source",
        "the",
        "these",
        "this",
        "to",
        "use",
        "with",
    }
)


HISTORICAL_PLAN_SEED_CAPACITY = 2


HISTORICAL_PLAN_SEED_QUALITY_RATIO = 0.85


HISTORICAL_PLAN_SEED_SIMILARITY_THRESHOLD = 0.90


HISTORICAL_PLAN_SEED_SCHEMA_VERSION = "historical-plan-seed-pool-v2"


FIXED_PREDICTOR_SEMANTICS = {
    "target": "adjusted_share_price_2x",
    "baseline": "mean_adjusted_close_last_5_complete_trading_days",
    "future": "maximum_5_complete_trading_day_mean",
    "horizon": "six_calendar_months",
    "judgments": ["likely", "possible", "unlikely", "insufficient_information"],
    "positive_judgments": ["likely", "possible"],
    "magnitude_classes": ["2-3x", "3-10x", "10x+"],
}


FIXED_PREDICTOR_SEMANTICS_HASH = hashlib.sha256(
    json.dumps(
        FIXED_PREDICTOR_SEMANTICS,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


REGISTERED_SOURCE_TYPE_CATALOG = tuple(
    sorted(
        {
            "news",
            "filing",
            "market_data",
            *SecCompanyFactsAdapter.source_types,
            *SecFilingAdapter.source_types,
            *AlphaVantageNewsAdapter.source_types,
            *AlphaVantageTranscriptAdapter.source_types,
            *HistoricalPriceAdapter.source_types,
        }
    )
)


REGISTERED_SOURCE_TYPE_CATALOG_HASH = hashlib.sha256(
    json.dumps(
        list(REGISTERED_SOURCE_TYPE_CATALOG),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def _model_available_source_types(
    available_source_types: Iterable[str],
) -> tuple[str, ...]:
    """Expand present Raw Info types to registered, resolver-usable aliases."""

    available = tuple(sorted(set(available_source_types)))
    return tuple(
        source_type
        for source_type in REGISTERED_SOURCE_TYPE_CATALOG
        if source_types_compatible((source_type,), available)
    )


ROLE_OUTPUT_TOKEN_LIMITS = {
    "controller": 8_000,
    "routing": 2_000,
    "predictor": 2_000,
    "posthoc": 2_000,
    "h1": 2_000,
    "h2": 2_000,
    "proposer": 4_000,
    "critic": 4_000,
    "signal_batch": 4_000,
    "h3": 8_000,
    "update": 8_000,
}
