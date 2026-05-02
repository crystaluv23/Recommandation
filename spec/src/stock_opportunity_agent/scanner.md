# Scanner

## Status
Not started

## Purpose

Reduce the investable universe to a manageable candidate set before expensive LLM research. The scanner is a cheap, repeatable filter, not a final decision maker.

## External Interface

The scanner should expose:

- universe selection,
- exclusion filters,
- coarse structured screens,
- theme-aware candidate expansion,
- and candidate reasons.

## Responsibilities

- Apply liquidity, market cap, price, listing, and risk exclusions.
- Run non-LLM screens for relative strength, financial improvement, revision trends, catalyst windows, valuation sanity, and volume behavior.
- Include theme-driven candidates even when they are not obvious from generic screens, as long as segment evidence exists.
- Produce a candidate set sized for downstream research.

## Dependencies

- Consumes config, data, signals, themes, and memory.
- Feeds research, scoring, ranking, and reports.

## Invariants

- Scanner reasons must be stored; a ticker cannot appear without an explanation.
- Exclusions must be explicit and reviewable.
- The scanner should not discard existing high-priority watchlist names solely because one current data source is stale.
- Coarse screens must not use future returns or future labels.

## Testing

Tests should cover universe filters, exclusion rules, candidate reasons, theme-aware inclusions, and stale or missing data handling.
