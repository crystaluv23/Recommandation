# Cases Matching

## Status
Started

## Purpose

Construct matched controls for historical winners so cold-start learning compares
pre-surge evidence against similar non-winners instead of polished winner-only
stories.

## External Interface

The submodule exposes:

- `ControlMatchCriteria`: versioned matching tolerances.
- `match_controls`: winner-to-control selection from labeled historical cases.
- `apply_matched_groups`: helper to write matched group ids back into cases.

Initial implementation uses same-sector filtering, market-cap log gap, prior
120-day return gap, and nearest-distance sorting. It is intentionally simple but
versioned so future definitions can be compared.

## Invariants

- Matching uses only point-in-time packet fields and retrospective outcome
  labels.
- Controls must be neutral outcome cases, not future winners.
- Missing matching fields may reduce match quality but must not leak future
  outcomes into packet evidence.

## Open Questions

The exact production matching definition still needs user confirmation:
taxonomy, size bands, volatility, valuation tolerance, prior-performance
tolerance, market-regime controls, and controls per winner.
