# Evolution Plan Roles

## Purpose

Implement structured adapters for Plan proposal, criticism, adaptive research,
Signal retrieval, blind prediction, and Plan reflection.

## Invariants

- Adapters translate model output into core protocols; they do not own engine
  state or commit pointers.
- Prediction-time roles never receive labels or target identity.
- Correction and fallback behavior delegates to the shared validators.
- After bounded correction, typed answer-ownership failures may retain the same
  selected Signal as context only, with full revalidation and unresolved needs.
  This removes an unverified routing claim without inventing research evidence.
- ResearchState summary counts, text lengths, and summary bytes are advisory
  compression targets. Transport token budgets remain hard limits; evidence,
  provenance, PIT boundaries, and need ownership remain validated.
- A terminal batch containing only unavailable Signals has no new evidence to
  reflect on. Return the previous state with only decision changed to finalize,
  without a model call or fabricated findings.
