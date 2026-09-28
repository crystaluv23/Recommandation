# Evolution State Patch

## Purpose

Apply a model-authored incremental change to one exact runtime-owned JSON
snapshot. The helper owns patch mechanics only; the caller retains the original
whole-object parser, evidence, point-in-time, and transition validators.

## Contract

The runtime issues `structured-state-patch-v1`, a canonical `base_hash`, and
machine-readable operation permissions. The response is exactly
`{"base_hash": "<issued hash>", "operations": [...]}`. Operations are `replace`
or `add` with `path` and `value`, `remove` with `path`, and `append` with a list
`path` and one `value`. Paths use the existing `field.member[index]` notation.
`add` only creates an absent dictionary key; `append` only appends one list
member. An existing list cannot be replaced wholesale. The response never
repeats unchanged fields. A stale hash, unknown field, invalid operation, or
unauthorized scope fails closed before any mutation.

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
