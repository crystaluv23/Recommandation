# Continuous Round Commit Marker

visit_times: 12

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

## Limits

This guarantees process-interruption consistency, not distributed exactly-once
delivery. An HTTP request interrupted after transmission but before response
remains an uncertain, conservatively charged attempt and may require a separately
recorded retry.
