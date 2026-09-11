# Signal Learning Profile Cycle Freeze

visit_times: 5

## Trigger

When changing per-Signal learning events, learned routing profiles, Fast-loop
Signal selection context, or recovery across a partially completed Signal cycle.

## Lesson

Keep three identities separate: immutable Signal definition version, append-only
Plan selection event, and deduplicated case/input observation. Different Plans
may preserve different reasons for selecting the same exact Signal on the same
case/input, but efficacy summaries must count that observation once. Otherwise
popular Plans manufacture confidence without new issuers or evidence.

A learned profile is dynamic model input even though it is not a new Signal
definition. Freeze it at the Fast group's starting committed-round cutoff. On
resume, rebuilding from all currently committed events would expose earlier
rounds from that same group only in the restarted process, making interrupted
and uninterrupted runs semantically different.

Keep the full routing decision and the learning-event selection projection
separate. Routing-only closure fields can evolve quickly; persisting the whole
routing object into a strict learning schema makes an otherwise valid Fast
commit fail after its pointer advances. Derive learning through an explicit
stable projection, retain the complete decision in the trajectory, and replay
the projection idempotently from committed Plan records.

## Context

The first version-bound Signal-learning implementation appended events after
each committed Fast round and froze current profiles whenever a cycle resumed.
An uninterrupted cycle retained its original in-memory snapshot, while a
restart would have included the newly appended events. Rebuilding profiles from
events whose `round_id` is no later than the cycle's starting committed round
restored equivalence without delaying the audit ledger or hiding new evidence
from the following Slow Update.

## How to Apply

1. Append learning only after the authoritative round pointer advances.
2. Store Plan-specific selection reasons under an exact `signal_ref`.
3. Deduplicate state/outcome and attribution summaries by
   `(case_id, signal_ref, input fingerprint)`.
4. Derive an identity-free bounded profile; never send the raw ledger to blind
   selection.
5. Freeze profiles with `starting_round = last_completed_round -
   completed_rounds_in_cycle` during both fresh and resumed Fast execution.
6. Let Slow Update read the latest ledger after Fast completion, while its
   holdout remains issuer-disjoint and hidden from the update role.
7. If code repair makes the frozen source read-only after its Fast pointer,
   hand Slow an immutable manifest of exactly one pre-Slow committed Fast range;
   bind every contributing hash and reconstruct only derived learning/meta
   state without copying the source pointer.

## Limits

The profile remains observational routing evidence, not causal Signal credit.
Its cutoff does not freeze the global Raw Info oracle, relax point-in-time
rules, or permit uncommitted artifacts to enter learning.
