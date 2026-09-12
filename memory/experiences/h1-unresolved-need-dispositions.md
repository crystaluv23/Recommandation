# H1 Unresolved Need Dispositions

visit_times: 0

## Trigger

When changing H1 need-ledger semantics, existing-Signal coverage claims, grouped
need dispositions, or the bounded hypothesis portfolio.

## Lesson

An upstream `unmatched_signal_need` is unresolved state, not merely prose. H1
cannot erase it with `already_covered` just because a stable Signal is cited.
Existing-Signal updates need a version-owned, per-need basis, and every member of
a grouped row must satisfy that basis independently.

A bounded hypothesis limit also needs an honest overflow state. A reusable,
measurable gap that was not selected this cycle is neither intrinsically
untestable nor already covered; persist it as `deferred_measurement` so the open
backlog remains eligible later.

## Context

V45 grouped 142 heterogeneous unmatched needs under
`guidance_acceleration:v1`. Shape correction succeeded once, but the same false
semantic coverage passed because the validator checked only Signal-ref existence.

## How to Apply

1. Preserve the upstream need kind in the H1 payload and validator.
2. For `update_existing`, accept only the row's exact Signal ref or a versioned
   `routing_answer_need_phrases` match for every grouped need.
3. Never infer coverage from arbitrary id, description, or query token overlap.
4. Use `deferred_measurement` for measurable portfolio overflow.
5. Mechanical field cleanup may run only before a complete semantic reparse.

## Limits

This rule does not locally choose a Signal or prove that a proposed measurement
is useful. H2/H3 and independent E1/E2 still own empirical comparison, and an
ignored model correction remains a technical failure.
