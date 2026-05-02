# Themes

## Status
Not started

## Purpose

Discover and maintain industry-chain transmission maps. This layer answers which themes are active, which segments are becoming bottlenecks, and where market repricing may move next.

## External Interface

Expected outputs:

- `ThemeMap`
- `SegmentAssessment`
- `ThemeTransmissionScore`
- `SegmentTimingScore`
- theme-to-segment candidate lists
- leading indicator lists
- segment risks and crowdedness flags

## Responsibilities

- Identify current and emerging themes.
- Map upstream, midstream, downstream, infrastructure, and second-order beneficiaries.
- Score transmission stage from early text clues through crowded consensus.
- Detect narrative migration across companies and segments.
- Require text, data, and market validation before promoting a segment.

## Dependencies

- Consumes data packets, documents, memory, signals, and config.
- Feeds scanner, research, scoring, ranking, monitoring, review, and reports.

## Invariants

- A theme is not valid just because it is popular.
- Segment stage must distinguish early clue, financial validation, analyst revision, market confirmation, consensus, and valuation exhaustion.
- Theme evidence must separate company statements, customer evidence, supplier evidence, market data, and analyst interpretation.
- Candidate companies must include exposure rationale, not just keyword matches.

## Testing

Tests should use fixture theme maps to verify stage transitions, evidence requirements, scoring bounds, and candidate-company mapping.
