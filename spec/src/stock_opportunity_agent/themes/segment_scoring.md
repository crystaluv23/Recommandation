# Themes / Segment Scoring

## Status
Not started

## Purpose

Score theme transmission and segment timing.

## Responsibilities

- Estimate transmission stage and timing attractiveness.
- Penalize crowdedness and valuation exhaustion when evidence supports it.

## Dependencies

- Parent spec: [`../themes.md`](../themes.md).
- Consumes chain maps, data, signals, and scoring config.

## Invariants

- Stage thresholds materially affect results and must be confirmed before first implementation.
- Scores must keep component evidence visible.

## Testing

Use fixture segments to verify stage transitions, score bounds, and crowdedness penalties.
