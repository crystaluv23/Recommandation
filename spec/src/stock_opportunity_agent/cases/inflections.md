# Cases Inflections

## Status
Started

## Purpose

Locate retrospective surge inflection points before blind signal mining begins.
Inflection discovery may use future outcomes because it only anchors historical
slices; its output must not be inserted into blind packets.

## External Interface

The submodule exposes:

- `InflectionCandidate`: date, method, score, explanation, and evidence.
- `detect_price_inflections`: factor-based price/volume breakout scan.
- `fallback_inflection_from_case`: explicit fallback when no price scan is
  available.

## Invariants

- Inflection candidates are retrospective setup artifacts, not as-of evidence.
- Factor detection may use later price movement to confirm the candidate, but
  blind analysis must still receive only pre-inflection point-in-time data.
- LLM/web inflection discovery belongs under research, not inside this factor
  module.

## Testing

Tests should cover breakout detection, insufficient data, score bounds, and
separation from blind packet evidence.
