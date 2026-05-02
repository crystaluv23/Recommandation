# Data

## Status
Not started

## Purpose

Provide structured and unstructured data to the rest of the system with point-in-time discipline. The data layer is the source of repeatability; LLM research should consume prepared data instead of improvising raw searches.

## External Interface

The module should expose services for:

- universe snapshots,
- price and volume history,
- financial statement features,
- valuation features,
- analyst revision features when available,
- events and catalysts,
- filings and transcript metadata,
- document retrieval,
- sector and benchmark context,
- and point-in-time `ResearchPacket` construction.

## Responsibilities

- Ingest and cache raw vendor responses or public filings when allowed.
- Normalize data into stable feature records.
- Construct point-in-time packets for live scans and historical case learning.
- Preserve source, timestamp, and availability metadata.
- Separate raw archives, feature stores, and document stores.

## Dependencies

- Uses `models` for packet and evidence records.
- Uses `config` for data-source and storage configuration.
- Feeds scanner, themes, cases, research, scoring, monitoring, review, and reports.

## Invariants

- Historical packets must not include documents or features unavailable as of `as_of_date`.
- Missing data must be explicit; absence cannot be silently treated as neutral evidence.
- Source freshness and retrieval time must be recorded for data used in scoring.
- LLM web findings, if used, must be converted into source-linked evidence before affecting durable records.

## Testing

Tests should cover point-in-time filtering, missing data semantics, packet construction, source metadata, and fixture-based feature normalization.
