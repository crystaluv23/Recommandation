# Evolution Plan Roles

## Purpose

Implement structured adapters for Plan proposal, criticism, adaptive research,
Signal retrieval, blind prediction, and Plan reflection.

## Invariants

- Adapters translate model output into core protocols; they do not own engine
  state or commit pointers.
- Prediction-time roles never receive labels or target identity.
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
  need's temporal scope. Selection validation rejects a residual that requests
  calendar scope beyond the targeted need's explicit as-of cutoff clause, using
  the targeted need's own bound as the reference, so the persisted residual is
  exactly representable downstream without violating the prediction-time
  boundary.
- Reflection validates persisted legacy selections against the actual runtime
  prediction boundary before building the H_reflect prompt. A partial answer
  whose residual need cannot be represented within that boundary is rejected
  fail-closed without a model call; the unresolved demand is never silently
  deleted, finalized away, or handed an impossible prompt. Without a runtime
  evaluation context there is no boundary to enforce, so legacy no-scope
  behavior is unchanged.
