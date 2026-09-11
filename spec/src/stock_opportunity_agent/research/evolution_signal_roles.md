# Evolution Signal Roles

## Purpose

Implement structured adapters for deterministic/LLM Signal execution, Signal
mining, and Signal update proposals.

## Invariants

- Candidate execution is evidence-backed and cannot promote a Signal.
- Mining and update output remains bounded by the frozen contract.
- Promotion authority stays in the Slow engine after machine validation.
- Update candidate shape and immutable-field checks run inside the existing
  bounded correction loop, using the same validator as staging. E1's terminal
  fallback removes only observations that fail independent source validation;
  remaining signatures pass the full parser again and carry quarantine metadata.
- Shared soft-Signal source projections rank chunks by each Signal's versioned
  retrieval query and declared evidence phrases, not extraction-instruction prose.
  Selection alternates between Signals and prefers an unseen eligible document
  before another chunk from the same document. The shared character budget,
  deterministic ordering, exact raw-span lineage and per-Signal citation scope
  remain unchanged. A bounded view cannot prove absent data; unavailable results
  must remain distinct from technical failures and negative domain observations.
- Every shared payload declares each Signal's own eligible projection refs.
  Initial validation isolates omitted, cross-Signal, edge, and shape failures;
  its sole correction contains only failed Signals, their eligible evidence,
  and their feedback, while accepted siblings are retained without re-execution.
  A semantically unavailable result may consume that same single correction only
  when a declared comparison need or a truncated projection makes one bounded
  local re-projection meaningful. Exact request estimation and the original hard
  token ceiling apply before the correction; unchanged insufficient input remains
  unavailable rather than entering another retry loop.
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
  Facts contain only a supplied `document_ref` and literal `exact_span`; the
  runtime does not treat a model-authored paraphrase as source fact. A label is
  never accepted as evidence that an event or source fact exists.
- Every label-revealed Mining decision receives a runtime-derived sample basis
  in its persisted form. The basis names the exact positive and control packet
  or case refs used by that comparison, so a schema-valid association cannot be
  audited without its sample. This field is runtime-owned rather than copied by
  the model.
- Legacy v1 H1 and Update records remain parseable only at explicit
  compatibility boundaries. New Slow execution always requests the v2
  contracts.
