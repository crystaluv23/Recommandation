# Hand-Entered Ground Truth Bypasses Every Gate

visit_times: 0

## Trigger

When adding a test harness, evaluation, or experiment that needs realized
outcome labels, or when auditing why a prediction was scored wrong.

## Lesson

A hand-entered outcome constant in a harness is invisible to every downstream
gate: the point-in-time oracle cannot self-verify labels (it deliberately ends
at `as_of`), evidence validators check inputs rather than ground truth, and a
wrong label manufactures fictitious lessons for the reflection/learning loop
(a false negative becomes "we were too conservative"). The v151 minimal-rounds
table hand-wrote `3.5x surge` for Schwab while the project's own case library
recorded `1.1139 non-surge` at the same key, and the binary flip happened to
"help" balance a 4/4 class mix — class-balance pressure is exactly when
invented labels appear.

## Context

Fast round v151/v152 (2026-09-30/10-01): Schwab was scored a false negative
against the hand-written 3.5; web verification (max ~1.14x, all-time high
below a third of the implied $307) plus a library reconciliation (7/8 binary
agree, zero records anywhere near 3.5) proved the label wrong. Fixed by the
global label store (`cases/label_store.py`, `runs/cold_start/data/outcome-label-store-v1`)
whose build reconciled 6,552/6,552 historical records exactly.

## How to Apply

1. Ground truth is derived, never transcribed: every consumer loads
   `(company_id, as_of)` keys from the global label store, which is recomputed
   by the single shared calculator from a hash-bound frozen price archive.
2. Missing keys fail closed as explicit exclusions; a run prints the store
   version and archive hash it scored against.
3. A repository-lint rule rejects hand-written outcome constants; if you find
   yourself typing a number next to a cik, stop and rebuild the store instead.
4. Sampling for class balance is legitimate, but the label written next to the
   sampled company must come from the store — the selection decision and the
   label must never be the same keystroke.
5. Labels contain future data by design: the store is evaluation-only and must
   stay unimported by prediction-time paths.

## Limits

Single-source labels guarantee consistency and provenance, not truth: a bad
price bar in the archive distributes the same error everywhere. Keep the
reconciliation report, the implausible-multiple review list, and occasional
external spot checks (the Schwab catch came from web verification, not internal
consistency).
