# Evolution Plan Roles

## Purpose

Implement structured adapters for Plan proposal, criticism, adaptive research,
Signal retrieval, blind prediction, and Plan reflection.

## Invariants

- Adapters translate model output into core protocols; they do not own engine
  state or commit pointers.
- Prediction-time roles never receive labels or target identity.
- Post-label Jev feedback includes deterministic proper-score and concentration
  diagnostics. Post-hoc reflection and the Plan critic must explain recurring
  low-support correct calls, high-confidence errors, and collapsed magnitude
  choices. Proposer-visible meta derives the same aggregate from immutable case
  feedback and requires a concrete Plan change or explicit defer/reject rationale;
  confidence itself remains excluded from fitness and is never maximized alone.
- Correction and fallback behavior delegates to the shared validators. Plan
  proposal corrections are checked with the same field/member granularity as
  controller corrections: a leaf path such as `B.requests[i].description`
  authorizes only that field, never sibling fields, whole-request
  replacement, or inserting another request.
- After bounded correction, typed answer-ownership failures may retain the same
  selected Signal as context only, with full revalidation and unresolved needs.
  This removes an unverified routing claim without inventing research evidence.
- ResearchState summary counts, text lengths, and summary bytes are advisory
  compression targets. Transport token budgets remain hard limits; evidence,
  provenance, PIT boundaries, and need ownership remain validated.
- A terminal batch containing only unavailable Signals has no new evidence to
  reflect on. Return the previous state with only decision changed to finalize,
  without a model call or fabricated findings.
- Information Plan proposals express cross-issuer business/risk research through
  the generic `filing` capability unless an exact SEC form is itself material to
  the research question. They must not assume every U.S.-listed issuer files
  domestic `10-K`/`10-Q` forms; the resolver selects applicable domestic or
  foreign operating reports while preserving exact-form restrictions.
- Plan proposal receives the complete retained additive meta FIFO, validates all
  original, vertical, and horizontal layers, and submits it under one exact
  request-token preflight. It does not sample representative cases; transport
  budget refusal remains a control-plane pause rather than a proposal failure.
- A `partial` answer's residual need must retain the targeted information
  need's temporal scope. Production injects the actual runtime prediction
  date into the Signal Retrieval Agent through the same optional
  `set_evaluation_context` setter the controller uses, resets it per case so
  reuse cannot carry an earlier cutoff, and exposes it in the routing payload
  as control data. Explicit dated and symbolic prediction-time cutoffs are
  validated alike against that actual date through the shared bounded-residual
  representation: routing rejects a residual exactly when the reflection
  temporal guard finds no bounded restatement (realized future facts, an
  invalid parent, or an unbounded parent that lends no cutoff or framing),
  and a representable literal is accepted while the consumer normalizes once
  through the same shared rule, so producer and consumer never demand
  contradictory exact strings. The producer correction names the actual
  prediction boundary, the inherited cutoff clause, and the framing marker,
  so a truly unrepresentable residual is repaired before any Signal executes
  instead of failing only at the pre-reflection boundary. Called without a
  runtime date, routing never fabricates a date, parent year, or present day:
  it keeps only the sound dateless explicit-cutoff check, and a symbolic
  cutoff alone triggers no dateless producer rejection. Historical residuals
  that reference only years at or before the actual prediction date stay
  accepted and are never reframed as forecasts.
- Reflection validates persisted legacy selections against the actual runtime
  prediction boundary before building the H_reflect prompt. A partial answer
  whose residual need cannot be represented within that boundary is rejected
  fail-closed without a model call; the unresolved demand is never silently
  deleted, finalized away, or handed an impossible prompt. Without a runtime
  evaluation context there is no boundary to enforce, so legacy no-scope
  behavior is unchanged.
