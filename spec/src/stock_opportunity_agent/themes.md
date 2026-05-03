# Themes

## Status
Started

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
- validation state for text, data, and market evidence
- stage history for themes and segments
- weekly theme-change summaries with upgraded, downgraded, newly observed, and crowded segments

Initial implementation provides `build_cold_start_theme_maps`, which initializes
theme and segment hypotheses from cold-start historical cases and learned signal
observations. It emits serializable `ThemeMap` records with segment stage,
timing/transmission scores, leading indicators, candidate symbols, validation
state, risks, and crowdedness flags. This is a cold-start initializer, not full
live theme discovery.

## Responsibilities

- Identify current and emerging themes.
- Map upstream, midstream, downstream, infrastructure, and second-order beneficiaries.
- Score transmission stage from early text clues through crowded consensus.
- Detect narrative migration across companies and segments.
- Require text, data, and market validation before promoting a segment.
- Record why a segment is becoming more or less central in the transmission chain.
- Mark late-stage consensus or valuation-exhausted segments so the scanner and scorer do not over-reward already crowded themes.
- Preserve leading indicators for each segment, such as demand-source metrics, backlog, pricing, margin, analyst revision, customer commentary, peer read-throughs, and relative strength when applicable.
- During cold start, group historical cases by supplied `theme_ids` or sector
  fallback, then use segment industries, catalysts, and learned signals to seed
  early industry-chain hypotheses.

## Transmission Stage Scale

The first implementation should use a versioned stage scale rather than prose-only labels. A useful default is:

- 0: not yet visible or not relevant.
- 1: early text clues in company, customer, supplier, or industry language.
- 2: cross-company resonance or leading indicators begin to align.
- 3: financial validation starts appearing in revenue, orders, backlog, pricing, margin, or comparable metrics.
- 4: analyst estimates, target prices, or coverage narratives begin adjusting.
- 5: market early confirmation appears in relative strength, volume, or segment-level breadth.
- 6: broad consensus forms and the theme is widely recognized.
- 7: valuation exhaustion, crowding, or late-cycle risk dominates the segment.

Exact thresholds for moving between stages remain an implementation-time research decision because they can materially change recommendations.

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
