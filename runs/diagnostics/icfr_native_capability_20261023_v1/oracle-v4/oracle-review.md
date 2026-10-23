# Prospective v4 independent freeze review

Reviewer: `/root/budget_counterreview`, 2026-10-23. Parent explicitly declared
current product sources/specs stable and authorized this metadata-only freeze.
No stage, author answer, candidate/consumer output, external API or network call
was created. This review follows the independent budget/recovery implementation
counterreview; neither review establishes fresh model capability.

The new oracle retains every original protected semantic field by strict deep
equality against **all three** previous oracle versions. The protected set is
every original key other than `frozen_at_utc`, `freeze_revision` and
`contract_bindings`. Existing v3 fields are unchanged except those three metadata
fields, `predecessor_bindings` and `prospective_revision`; the only new top-level
metadata fields are the immutable v3 `historical_resource_prefix` and exact
current `runtime_archive`. No source fact, acceptance answer, applicability,
direction/orientation rule, counterexample, source qualification or fixed
denominator was changed.

`equivalence-evidence.json` records exact old/new hashes, per-field equality and
both source/runtime authority checks. All 263 source documents, 18 stable
definitions, original dev8/group map, 265 backlog needs, six memory disclosures,
candidate denominator 1 and four original consumer cases remain bound. Native
read-only `_stopped_predecessors()` verified 976 rows and actual historical
consumption 12/2,001,316, 11/1,837,419 and 10/2,055,941; all three old oracle byte
strings still equal committed originals. The v3 terminal seal and file bytes
remain unchanged. No old output, action, candidate or cache is imported.

Original ceilings remain global 728/56 MiB, Mining 80/12 MiB, candidate
300/16 MiB, each Fast case 12/3 MiB and complete request 262,144 logical units.
The v3 debt is charged to global and Mining, leaving Mining 70/10,526,971 and
global 718/56,664,315. These are logical reservations, not measured host tokens
or currency cost, and do not authorize resetting a terminal target.

The archive `frozen-runtime-5fcf473b.tar.gz` contains all 182 current `_code()`
files. Every archive member was independently read back and hashed against its
current file binding. The archive captures actual working-tree bytes, including
pre-existing authorized uncommitted spec changes; the Git revision alone does
not identify those bytes. Oracle contract bindings include the complete current
runtime plus previously bound companion tests.

The first freeze preflight compared the original custom compact-JSON hash with
the project's different canonical serializer and correctly stopped before any
oracle/archive creation. That harness error is preserved in
`freeze-first-harness-error.log`. The script now explicitly uses the original
compact serializer for its `4951c16c…` semantic digest. Deep equality is the
primary assertion; the project's canonical representation of the same protected
payload is `ae8300d1e87e8287c5e4e238d0209a8e191e50d97a521b92d89910d3c08122e6`.
No semantic content was edited to match a hash.

The formal oracle is now prospective and immutable. Parent may independently
verify it and then prepare the new stage using the unchanged driver. Fresh roles
must receive only the exact native inbox; private oracle passages, locators,
mapping and expected answers stay outside their prompts. Actual candidate
semantics and four consumer results still require later independent source
review under these frozen obligations.
