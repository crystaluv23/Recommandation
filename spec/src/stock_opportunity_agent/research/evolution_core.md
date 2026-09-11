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
  One- and two-character ticker aliases in prose require an explicit dollar,
  ticker, symbol, or exchange marker. This matches the outgoing transport guard
  and preserves ordinary text such as Gen Z, Q2, and AI. Full names and longer
  ticker aliases retain their existing identity handling.
  URL path/query identity matching remains case-insensitive for short tickers;
  the prose exception does not expose identities in source links.
  Shared masking/projection helpers accept an explicit strict-inventory mode
  for aggregate Slow roles, avoiding repeated brand derivation. A bounded cache
  reuses compiled patterns for identical inventory/mode pairs.
- Record serialization stays explicit and schema-compatible.
- Scoring and fitness rules remain deterministic.
- When an already executed, reflectable batch cannot fit an ordinary reflection
  into the adaptive budget, consume any paid usage and attempt that same batch
  once in terminal mode with the remaining total budget. Reapply the existing
  mandatory-finalize validation; never fabricate a finalized state. A failed
  terminal reservation remains budget-exhausted, without another retry. This
  fallback does not apply when no batch exists or when already in terminal mode.
- The module may depend on Raw Info and Signal contracts, but not on Plan or
  Signal engine implementations.

ResearchEvidenceRef claims require nonempty text and have no hard character ceiling.
Length is presentation guidance; evidence validation and transport budgets remain
independent. Existing serialized record shapes are unchanged.

Predictor's 24KB display target is advisory; complete validated state and citation
material cross this boundary unchanged, with target overflow explicitly recorded.
Hard request/case/cost limits remain enforced by transport. Meta model views select
whole reflection items and disclose omissions within their global budget; they
never cut claims mid-sentence or overwrite complete durable reflections.

For the supported SEC Company Facts response shape, model-facing document views
preserve taxonomy concept, provider label, unit, and up to the latest necessary
distinct reporting periods together. Every visible record carries its complete
literal raw JSON span and raw start/end offsets; wrapper fields explain meaning
but are not independently citable facts. Ambiguous raw matches, future-filed
records, unknown shapes, and budget omissions remain explicitly partial. The
combined structured view, including parent fields and record literals, stays
inside the existing document character bound and does not alter Raw Info.
