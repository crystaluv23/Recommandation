# Evolution State Patch

## Purpose

Apply a model-authored incremental change to one exact runtime-owned JSON
snapshot. The helper owns patch mechanics only; the caller retains the original
whole-object parser, evidence, point-in-time, and transition validators.

## Contract

`restore_exactly` correction authority distinguishes an absent prior occurrence
from a validator-identified cosmetic returned occurrence. Only when the validator
supplies its exact `returned_path` may the patch replace that snapshot slot, and
only with `required_need`; this does not grant deletion or editing neighboring
needs. Without a returned slot, restoration retains the exact-text append budget.
A prior-state index never becomes returned-slot authority.

The runtime issues `structured-state-patch-v1`, a canonical `base_hash`, and
machine-readable operation permissions. The response is exactly
`{"base_hash": "<issued hash>", "operations": [...]}`. Operations are `replace`
or `add` with `path` and `value`, `remove` with `path`, and `append` with a list
`path` and one `value`. Paths use the existing `field.member[index]` notation.
`add` only creates an absent dictionary key; `append` only appends one list
member. An existing list cannot be replaced wholesale. The response never
repeats unchanged fields. A stale hash, unknown field, invalid operation, or
unauthorized scope fails closed before any mutation.
The shared prompt states the exact typed `invalid_container=true` exception
alongside its normal list prohibition; it never contradicts issued permissions.

The sole list-replacement exception is an owning shape validator's explicit
`invalid_container_paths`: a container supplied where a different type is
required (for example `H_init=[]` instead of a string) can be replaced at that
exact invalid field. An unexpected container field can similarly be removed
when the typed issue permits removal. Valid list fields never gain this
exception, and it grants no root-object or parent scope.

Every index refers to the issued base snapshot, including when several members
are removed. Validate the complete patch before applying it to a deep copy:
replacements/additions first, removals from higher to lower indices, appends
last. Duplicate writes, overlapping parent/child writes, and modifications of a
list's parent together with an append are rejected. Multiple appends to one list
are ordered by response order. A typed obligation's supplied item identity must
match its base-snapshot row; model output cannot rebind a path to another row.

Normal H_reflect deltas may update or remove individual ResearchState list
members, append new members, and replace `decision`. Previous validated fields
not mentioned in the delta remain exact. This mechanical permission does not
authorize research facts: the existing full-state validator still checks source
tuples, prior evidence identity, quantities, need ownership and PIT boundaries.

State mode accepts exactly the eight canonical ResearchState fields, or those
same fields plus the transient Reflect list `need_dispositions`. The latter is
part of the exact patch snapshot and allows ordinary member edits/appends like
other lists; no arbitrary ninth field is accepted. This envelope does not alter
ResearchState serialization. Correction mode still derives every disposition
edit from typed owning-validator paths and never inherits broad state-mode
permissions. The caller validates the whole envelope before accepting state or
persisting disposition metadata.

Correction permissions come only from typed validator obligations, including
explicit dependency paths, operation kinds, exact member-removal metadata, and
bounded append budgets. Diagnostic prose does not grant write authority. A leaf
permission does not authorize replacing or removing its containing row. Missing
dictionary fields may be added only with explicit add permission. Compaction
authorizes only its exact removal paths, never its broad container path.
An owning validator may give a dependency its own `dependency_allowed_repairs`
operation set: for example, removing an invalid last need permits replacing
`decision`, without permitting replacement of the invalid need itself. Append
budgets accumulate across independent obligations, counting each target list
once within an obligation.
Appending requires either an explicitly named list with add authority or an
owning validator's `permitted_append_paths`. An indexed field with add authority
does not authorize appending to its containing list. Missing exact need/residual
restoration appends the required literal by occurrence count, including when a
prior-state coordinate now addresses an unrelated returned sibling.
Exact restoration budgets are per required literal and occurrence count;
repeated obligations do not duplicate that budget, and the allowance to restore
one missing need cannot be spent on another. Invalid or non-finite JSON cannot
form a usable snapshot hash.

An authorized merged object that still has semantic failures becomes the next
correction baseline. Thus repaired siblings survive and only new/current
validator obligations may be edited. Invalid patch mechanics preserve the prior
baseline and semantic obligations, with the patch failure reported separately.
No partially valid object becomes accepted state until the complete validator
passes. Deterministic fallback and control-plane failures remain the caller's
responsibility.

## Offline compatibility

Immutable historical full-response recordings may be explicitly converted to
equivalent deltas in offline replay adapters. This proves interface composition
and regression behavior, not that a live model will produce a valid new delta.
Production roles using this protocol reject full-object correction responses;
only a role with no parseable full object may request a complete new object.

## Exact reference additions (2026-10-02)

An owning validator may supply `allowed_append_values`, a mapping from already
permitted list paths to a finite set of string values. Each value can be added
at most once and only if absent from the base snapshot. This is value-bound
repair authority, not a blanket larger append budget. It supplies the multiple
runtime statistic handles needed by a single cross-Plan assertion while
rejecting unrelated references. Exact duplicate operations retain the existing
mechanical deduplication; merged reference uniqueness remains domain-validated.
The metadata cannot grant an
unnamed path or bypass the existing add permission. Other obligation append
semantics, indexed writes and full merged-object validation remain unchanged.

## Mechanical patch correction (2026-10-02)

A parseable, finite native patch with the correct issued snapshot hash may receive
`state-patch-mechanics-repair-v1` when individual operation shape,
conflicting writes, or grouped append budgets make it invalid. The patch helper
identifies every participating operation index, including both sides of an
ambiguous conflict. It never selects a winning semantic value. Stale hashes or
failed identity guards cannot receive this repair contract. Out-of-authority
operations retain the original owning semantic correction context; a mechanics-
only view cannot reconstruct their research intent.

The correction is another standard snapshot-bound delta, this time against the
exact invalid patch object. It may only replace/remove named bad operation
members; other operations and the native base_hash remain immutable. It cannot
append unrelated operations, replace the entire operation list, or bypass the
original state contract. The runtime composes the repaired native patch, applies
its original authority against its original base, then runs the complete original
role parser. No intermediate patch or partial state is accepted. Exact duplicate
operations retain existing deterministic deduplication. Non-object operations
must reject instead of silently disappearing during deduplication.
