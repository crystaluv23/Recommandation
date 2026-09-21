# Plan Evolution

Backlog refresh in a slow-only workspace consumes the hash-verified Fast context
seed in its v2 Slow-history manifest when the local Fast archive is empty. The
zero local pointer must not erase imported unmet needs. Refresh remains derived
and repeatable, including after Slow validation and restart; it never reads an
unbound ancestor's mutable backlog file.

## V8 Slow cycle persistence

`EvolutionWorkspace` owns immutable cycle files `slow_input.json`,
`slow_memory.json`, and `slow_experiments.json`. Loaders verify schema, cycle,
contract, upstream hashes, and committed source cutoffs. Only the currently
active cycle may resume its uncommitted artifacts. Later cycles enumerate Slow
history strictly through `last_completed_cycle`.

Staging validation requires the exact input/memory/experiments chain. Staging a
result additionally requires the recorded Registry transition output. Every
fresh and shortcut resume path revalidates that same chain. The atomic cycle
pointer advances after the result is durable and never from artifact presence.

## Purpose

Own crash-safe evolution workspace state, runtime Plan evaluation, and the Fast
Plan-evolution engine. It depends on `evolution_core.py` and has no dependency
on the Slow Signal engine.

## Invariants

- Only committed pointers define completed rounds and cycles.
- Staged artifacts remain recoverable but never count as progress.
- Plan evaluation retains Anchor/Random lineage and fitness gating.
- The ordinary capability backlog is derived only from Plan records reachable
  through committed round checkpoints. Each committed round refreshes it after
  archive, learning, and meta publication; staged attempts may contribute a
  separate technical diagnostic but never formal Slow-learning needs.
- A resumed Slow loop refreshes the backlog before creating a new frozen Slow
  validation. An already staged validation retains its exact original backlog.

## Per-case technical-exclusion carry-over (user-approved 2026-09-21)

A CandidateExecutionRejected case (bounded correction exhaustion, including
the same-request guard) records its failure artifact, abstains as a real
finalized negative prediction (`insufficient_information` with a persisted
prediction ref), stays in the label-blind confusion matrix, and never blocks
the candidate while at most `MAX_TECHNICAL_CASE_EXCLUSIONS` (2) cases are
excluded in one evaluation. Abstain rows are exempt only from the
source-evidence eligibility check — their absence of evidence reflects the
recorded failure, not a research gap; completeness, finalization, and
non-degenerate-fitness gates still apply unchanged. Above the cap, or for
control-plane errors (budget, shared-data availability), the attempt remains
a rejection exactly as before. `PlanEvaluationAttempt.technical_exclusion_case_ids`
persists the auditable exclusion list; the fitness reasons stay clean (an
exclusion never appears as a blocking reason). Corrected initialize output
must satisfy every prior obligation simultaneously: horizon compliance and
claim-quantity grounding are jointly required, and repairing one by
reintroducing the other is not a correction.

## Bounded parallel candidate evaluation

One coordinator (the engine, holding the workspace execution lock) may
evaluate the round's candidate plans with bounded worker threads. Frozen
inputs — round dataset snapshot, parents, meta, Signal registry snapshot,
limits — are shared read-only. All candidate proposals are generated and
persisted sequentially before any evaluation starts. Workers are dispatched
in ascending candidate-slot order, each worker owns one candidate at a time,
and each worker operates on its own mutable role instances (research
controller, Signal agent, Predictor, resolver context, provider client); no
role object is shared across workers. Case order inside a candidate and
research order inside a case are unchanged. Results are recombined,
validated, critiqued, reflected, and committed by the coordinator in the
original candidate-slot order, so completion order never influences metrics,
selection, meta, or the archive. Concurrency level is a frozen run-contract
parameter; level 1 must remain byte-equivalent to the sequential engine. Stop
handling lives solely in the coordinator's main thread: a stop signal marks a
shared cancel flag, admission of new work and requests stops immediately,
workers check the flag at safe boundaries, and waits on workers are bounded.
Slow never overlaps the same cycle's Fast.
