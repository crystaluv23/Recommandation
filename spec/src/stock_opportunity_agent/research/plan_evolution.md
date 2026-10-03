# Plan Evolution

## Restored technical failure provenance (2026-10-02)

Reusing a checkpointed technical-exclusion trajectory also restores its
`CaseEvaluationFailure` from the adjacent immutable failure checkpoint, bound to
the same input hash, schema and case. Restored and fresh failures have identical
attempt diagnostics and scoring. Missing/conflicting failure provenance fails
closed instead of producing an apparently clean `failures=[]` attempt. Restore
does not rerun research, rewrite history, or fabricate a replacement diagnosis.

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

The workspace derives opaque prediction observations from exact pointer-reachable
Plan records and loads inherited derivatives only from its hash-bound frozen
history/bootstrap manifests. These pure derivatives support the additive
cross-round reflection layer at the Slow boundary; they never affect Fast scores
or edit existing meta. Original source hashes and trajectory locators are retained.

Own crash-safe evolution workspace state, runtime Plan evaluation, and the Fast
Plan-evolution engine. It depends on `evolution_core.py` and has no dependency
on the Slow Signal engine.

## Invariants

- Only committed pointers define completed rounds and cycles.
- Staged artifacts remain recoverable but never count as progress.
- Plan evaluation retains Anchor/Random lineage and fitness gating.
- Case evaluation enters each participating caller's optional `anonymous_case`
  scope before executing the complete research chain. The scope receives the
  runtime case/company IDs and source identity inventory; original case records
  and source hashes remain local and unchanged. Production transport owns the
  model-facing projection and exact response restoration.
- The ordinary capability backlog is derived only from Plan records reachable
  through committed round checkpoints. Each committed round refreshes it after
  archive, learning, and meta publication; staged attempts may contribute a
  separate technical diagnostic but never formal Slow-learning needs.
- A resumed Slow loop refreshes the backlog before creating a new frozen Slow
  validation. An already staged validation retains its exact original backlog.
- Proposal progress hashes the complete retained `archive_view` for historical
  input identity and derives round/case coverage from those committed entries.
  This archive audit is distinct from the role's bounded model view and actual
  transmitted-request hash. The proposer builds its brief/read requests at the
  owning role boundary; archive serialization is never a model-payload shortcut.

## Per-case technical-exclusion carry-over (user-approved 2026-09-21)

A CandidateExecutionRejected case (bounded correction exhaustion, including
the same-request guard) records its failure artifact, abstains as a real
finalized negative prediction (`insufficient_information` with a persisted
prediction ref), stays in the label-blind confusion matrix, and never blocks
the candidate while at most `MAX_TECHNICAL_CASE_EXCLUSIONS` (6, raised from 2 on 2026-09-21 after live measurement: at the observed ~25-30% per-case correction-exhaustion rate a cap of 2 made round viability 1-4% statistically) cases are
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

Technical carry-over affects scoring but is not research evidence. Formal
Binary F1 and magnitude metrics retain the frozen cohort denominator: a failed
positive remains a false negative, while a failed negative is reported as a
technical abstention and must not be described as a successful negative
research judgment. Critic, Round reflector, proposer FIFO, capability backlog,
and Slow feedback receive an explicit technical-exclusion record instead of the
synthetic `insufficient_information` judgment, its four-way feedback, its empty
trajectory, or a fabricated magnitude miss. Magnitude diagnostics used for
research attribution are recomputed over research-completed trajectories and
carry the excluded count; the formal score-denominator metrics remain unchanged
beside them. Completion rate and failure classification are reported separately
from F1 and from Anchor/Random cohort metrics. Legacy committed reflections are
projected through the same separation at model-read time without rewriting the
historical artifact.

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

Production composition freezes `max_parallel_plans` in every newly created run
contract (default 2, bounded by the candidate count). A missing field in a
legacy readable contract means 1 and preserves the former V130 sequential
path. Parallel production creates a fresh evaluator, controller, retrieval
agent, Predictor, Signal runner, evidence-resolver context, and structured role
client for every candidate worker while sharing only frozen inputs and the
thread-safe cache/ledger boundaries. Runtime progress is serialized through one
coordinator-owned event writer so sequence numbers and JSONL records cannot
race. `max_parallel_plans=1` stays on the original direct sequential evaluator
path rather than introducing a worker thread.


## Committed Signal target tracking

The same post-commit/restart path publishes source-bound knowledge-use rows for
Experience and Signal via the memory-owned `KnowledgeUseStore`. A new PlanRecord
retains its exact frozen `knowledge_signal_refs` menu, enabling known non-use
controls without reconstructing historical menus from today's Registry.
Absent legacy menus are unknown. Explicit Experience adoption is retained with
the staged Plan. At round start the proposer receives a frozen performance
overlay; next-round/Slow consumers see updated committed observations. Complete
history derivatives survive FIFO eviction and hash-bound successor imports.

After round commit, and on rebuilding committed archive derivatives at restart,
`_record_signal_statistics` routes learning events through `signal_tracking`.
Target observations are derived after existing physical statistics and remain
separate from them. Missing derivatives recover from committed records; staged
attempts never create target evidence. Existing canonical records stay unchanged.
Both event and execution-statistics ids bind the same immutable Plan record hash;
local round/Plan names alone cannot suppress or collide with successor work.
Physical selected-use effect observations retain their existing deduplication.
