# Evolution Core

The fixed Predictor price baseline is computed from complete, hash-verified,
point-in-time market documents selected by Basic Info resolution. Source excerpts
and model projection budgets affect presentation only, never its five-row window.

## Purpose

Own immutable evolution records, validation, scoring, evaluation-dataset
selection, role protocols, and pure research helpers. It has no workspace or
Fast/Slow engine dependency.

## Invariants

- `AgentStep` may carry bounded, non-authoritative role metadata alongside its
  value and usage. Controllers persist only the metadata fields defined by the
  owning role contract; metadata never changes domain success or commit state.
- A rejected candidate role may attach structured diagnostic details for
  persistence. These details explain failed work and its input identity; they
  never convert the rejection into a domain result or widen recovery scope.
- Stable-item correction may add one explicitly missing item only when its
  structured issue names the runtime-owned item ID and grants `add`. Existing
  siblings are copied from the failed response, so a correction cannot rewrite
  them while filling the omission.

- Point-in-time and identity masking rules remain fail closed.
- Record serialization stays explicit and schema-compatible.
- Scoring and fitness rules remain deterministic.
- The module may depend on Raw Info and Signal contracts, but not on Plan or
  Signal engine implementations.
