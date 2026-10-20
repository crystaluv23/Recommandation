# Historical Registry identity and current capability checks

2026-10-21. This addresses the historical-input prerequisite for bounded Slow
acceptance. It does not close S1/S2, publish a Signal, consume feedback with a
new model, or run a successor. The completed v182 Fast/Slow pointers remain1/1.

## Observed boundary

The native Slow-history builder calls `SignalRegistry.freeze()` to compare the
source Registry with its committed cycle pointer. That method first builds
performance-bearing cards and then audits every stable capability against the
current runtime. A historical definition identity read therefore depends on
both derived knowledge context and re-execution of old synthetic fixtures.

Three distinct observations are retained:

1. A minimal temporary copy of137 definition files and three source metadata
   files reached freeze but failed before capability audit because its knowledge
   checkpoint was absent. This was an incomplete diagnostic copy, not a defect
   established in the real source. No fixture or Signal ran in this attempt.
2. Direct native auditing of the exact published cash and revenue-growth
   positives rejected both with `opaque company has no explicit issuer binding`.
   Their memory-only counterfactuals adding consistent synthetic CIK passed with
   all other fields and original body bytes preserved. Four real fixture audits,
   internal single-ref batches and deterministic callable invocations occurred.
   The published records were not edited.
3. One read-only native builder preflight against the real v182 source passed
   its knowledge provenance prerequisites. Freeze then rejected nine financial
   fixtures with the same issuer error; the other three deterministic fixtures
   passed. This attempt performed12 native fixture batches/functions, no model,
   GET, LabelStore, promotion or manifest creation. All93 actual source reads
   stayed byte-identical, with no denied read or write attempt. Retrospective
   committed feedback was authorized for this S1 diagnostic and was never sent
   to a blind role.

The independent review verifies these different scopes. Pure reconstruction of
the18 v12 definitions reproduces the exact committed hash, but supplies neither
learned profiles nor current executability. Two successful CIK counterfactuals
do not prove that all nine historical versions can be made executable unchanged.

## Repair boundary

The owning specs now distinguish a historical definition/provenance read from
a fresh capability-audited execution freeze. The implementation must use the
existing `snapshot_from_refs` through a private reader of native stable manifests
and exact specs/skills. It must preserve stable ordering, committed version/hash,
source-file binding, knowledge and event validation, and reject empty/drifted
Registry identities. It must not read performance cards merely to enumerate
definitions, execute historical fixtures, edit old fixtures, or construct
learned profiles.

This applies to history export, initial/replayed materialization, and both
bootstrap source identity checks. Fresh runtime execution, candidate admission,
promotion and cycle completion retain the normal `freeze()` and all existing
issuer/PIT/schema requirements. Historical readability does not permit current
execution of an incompatible version.

The local implementation replaces exactly five historical freeze calls with a
26-line private definition reader. It also rejects coerced Registry-version
authorities through export, apply-before-write, history validation and the
bootstrap producer/validator chain. Independent controls found that `True` and
`1.9` previously passed as committed Registry version1 in both the old code and
the first candidate. That original counterexample is retained; final historical
callers and validators require positive JSON integers. Other runtime numeric
fields and the three fresh-cycle freeze sites are unchanged.

All65 associated tests pass with real-network/LabelStore tripwires zero; source
and test hashes remain fixed across the run. Ten independent temporary control
groups pass, covering exact definitions/order/skills, empty/duplicate/path and
version drift, source/target changes, committed-event cutoff, file validation,
typed authorities and bootstrap producer-to-consumer validation. An unknown
current callable can be read historically but still fails fresh capability
audit. The initial candidate's9 focused passes missed authority-side coercion;
checking only the new helper's raw header was insufficient. Root also initially
limited the repair to the five freeze sites, then included the actual bootstrap
validator consumer rather than leave that adjacent hole.

Diagnostic setup errors, an independent isolated-module registration error and
a post-test exclusive receipt-write collision are preserved separately. They
are not product semantic failures; the final65-test run completes successfully.
No corrected real-source export, fresh feedback consumption or whole-MVP pass is
claimed yet. The next check uses the new committed code for one bounded actual
history export/materialization; it must retain any next native failure.

## Evidence

- [Incomplete-copy result](../runs/diagnostics/slow_history_import_boundary_20261021_v1/result.json)
  and [direct fixture controls](../runs/diagnostics/slow_history_import_boundary_20261021_v1/direct-fixture-result.json).
- [Actual source preflight](../runs/diagnostics/slow_history_import_boundary_20261021_v1/actual-source-preflight.json).
- [First two-slice review](../runs/diagnostics/slow_history_import_boundary_20261021_v1/independent-review.json)
  and [actual-source review](../runs/diagnostics/slow_history_import_boundary_20261021_v1/actual-source-independent-review.json).
- [Owning control contract](../spec/src/stock_opportunity_agent/research/evolution_control.md)
  and [Registry contract](../spec/src/stock_opportunity_agent/signal_library.md).
- [Final65 associated checks](../runs/diagnostics/slow_history_import_boundary_20261021_v1/root/connected-final-result.json),
  [independent repair audit](../runs/diagnostics/slow_history_import_boundary_20261021_v1/independent-repair-review.json)
  and [original typed counterexample](../runs/diagnostics/slow_history_import_boundary_20261021_v1/independent-repair/pointer-counterexample.json).
