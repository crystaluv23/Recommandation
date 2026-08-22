# Continuous Round Commit Marker

visit_times: 27

## Trigger

Read this before changing continuous self-evolution persistence, Ctrl+C resume,
historical-round branching, or multi-trajectory dashboard recovery.

## Lesson

A round that writes several artifacts needs one small atomic commit marker.
Artifact existence alone cannot prove completion because interruption may occur
between any two writes. Treat `state.json:last_completed_iteration` as the only
authority for restore, branch selection, and visualization; files beyond that
pointer are staged recovery inputs, not committed history.

## Context

The continuous information-scheme loop writes predictions, evaluations,
Top-K, meta-memory, history, and a round checkpoint. A Ctrl+C between the
checkpoint write and state update could otherwise make an incomplete round
appear branchable even though its controller state was never committed.
The dual Fast/Slow loop adds a second, cycle-level pointer; completed cases
also need exact input-bound trajectory checkpoints so a late batch interruption
does not repay already completed model work.

## How to Apply

Write fine-grained task artifacts atomically as soon as they complete, then
write the immutable round checkpoint, and advance the single atomic completed
pointer last. Resume may reuse staged exact artifacts, but dashboards and
branch loaders must filter everything above the completed pointer. Never move
the pointer backward or infer completion from a directory listing. Derive an
active cycle's remaining Fast rounds from the round pointer, then advance the
cycle pointer only after an exact Slow result is durable. Keep debug JSONL
events non-authoritative and tolerant of a truncated last line.

When a Slow Loop mutates a versioned Registry, persist the exact validation
batch before changing stable manifests. It must bind the input version/hash,
input refs, and passing candidate hashes. Apply one cycle-identified idempotent
transition, persist its output version/hash, and advance the cycle pointer last.
The run contract may freeze the initial Registry, while committed cycle state,
not that initial hash, owns subsequent Registry continuity.

## Cross-workspace Warm Starts

Historical Plans may seed a new workspace only when their records are reachable
through the source workspace's committed round pointer and exact checkpoint.
Snapshot the selected Plan definitions and aggregate provenance before freezing
the new run contract, then bind the snapshot hash into that contract. Source
metrics are selection evidence only: seeds are parent context, never imported
Top-K records or fitness. Ignore staged attempts, tolerate an empty first-ever
pool, and keep the resulting parent snapshot immutable across resume.

## Limits

This guarantees process-interruption consistency, not distributed exactly-once
delivery. An HTTP request interrupted after transmission but before response
remains an uncertain, conservatively charged attempt and may require a separately
recorded retry.
