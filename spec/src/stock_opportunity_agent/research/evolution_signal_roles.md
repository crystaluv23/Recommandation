# Evolution Signal Roles

## Purpose

Implement structured adapters for deterministic/LLM Signal execution, Signal
mining, and Signal update proposals.

## Invariants

- Candidate execution is evidence-backed and cannot promote a Signal.
- Mining and update output remains bounded by the frozen contract.
- Promotion authority stays in the Slow engine after machine validation.
- Production H1 uses `signal-mining-hypothesis-v2`. The runtime supplies stable
  proposal refs, the fixed Discovery comparison, and the evidence lookback;
  the model supplies a structured measurement, canonical applicability,
  expected direction, retrieval intent, and falsifiers. Semantic validity must
  not depend on lexical overlap between an identifier, prose, and a query.
- H1 may return a structured `no_testable_hypothesis` conclusion even when the
  demand backlog is non-empty. It must include a bounded reason code and
  rationale, and remains distinct from malformed output or execution failure.
- Production Signal Update uses `signal-update-decision-v2`. Each case first
  records a source-cited evidence verdict; outcome relation is a separate field.
  A label is never accepted as evidence that an event or source fact exists.
- Legacy v1 H1 and Update records remain parseable only at explicit
  compatibility boundaries. New Slow execution always requests the v2
  contracts.
