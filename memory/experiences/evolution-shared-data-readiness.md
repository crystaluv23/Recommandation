# Shared Evaluation Data Is Not Plan Fitness

visit_times: 0

## Trigger

Read this before changing evaluation evidence gates, provider fallback,
round-wide missing-source handling, or Random-case readiness sampling.

## Lesson

When every candidate Plan loses evidence on the same case, the failure belongs
to shared point-in-time input preparation, not to Plan fitness. Resolve the
fixed market backbone before Plan proposals. Try authorized adapters in frozen
catalog order; for a new Random snapshot, continue through the same
deterministic label/issuer rotation when a prospective case is unavailable.
Never substitute a fixed Anchor or an already persisted snapshot.

A remaining shared-data failure must leave committed pointers unchanged and
write a replaceable pause diagnostic, not an immutable `round_rejected`
checkpoint. Only genuinely transient provider failures should use the
supervisor's retryable process status.

## Context

One round evaluated three Plans over the same 24 cases. Massive returned no
historical prices for PDC and the resolver never tried the contract-authorized
Stooq fallback. All three Plans therefore had 23/24 evidence coverage and were
permanently rejected as `no_fitness_eligible_candidates`; resume replayed the
rejection and the ten-hour launcher treated the normal CLI exit as completion.

## How to Apply

1. Keep fallback in the reusable Evidence Resolver, with every attempt charged
   to the frozen data budget.
2. Run a label-free source-readiness gate before model proposal/evaluation.
3. Preserve exact class quotas and one-company-per-round while skipping only
   not-yet-frozen Random candidates.
4. Persist shared-data pauses separately from candidate attempts and round
   rejection.
5. Regression-test that no proposer call or `rejected.json` occurs when the
   shared gate fails.

## Limits

Readiness filtering is not permission to weaken Anchor identity, label counts,
issuer disjointness, point-in-time cutoffs, data budgets, or Locked Test
sealing. A deterministic lack of ready Anchor/capacity remains a terminal
operator-visible failure rather than an infinite retry loop.
